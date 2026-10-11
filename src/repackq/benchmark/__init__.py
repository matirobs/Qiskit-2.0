"""Reproducible, resumable retrospective benchmark execution and exports."""

from __future__ import annotations

import hashlib
import importlib
import itertools
import json
import math
import os
import statistics
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from repackq.config import PV_TOU_MISSION
from repackq.data.serialization import (
    canonical_json_bytes,
    trajectories_from_dict,
    write_json_atomic,
)
from repackq.models import CandidatePool, CellSnapshot, FutureTruth, MissionProfile
from repackq.optimization.objective import build_optimization_instance
from repackq.optimization.solvers import (
    OptimizationResult,
    compatibility_greedy,
    exact_enumeration,
    simulated_annealing,
    soh_sort,
)
from repackq.prediction.evaluation import select_decision_cycle
from repackq.prediction.trials import generate_candidate_pool
from repackq.quantum.engine import QAOAResult, run_qaoa


BENCHMARK_SCHEMA_VERSION = "1.0"
_CLASSICAL_ALGORITHMS = (
    "soh_sort",
    "compatibility_greedy",
    "simulated_annealing",
    "exact_enumeration",
)


@dataclass(frozen=True)
class BenchmarkConfig:
    """Validated, immutable settings that define a benchmark run."""

    seeds: tuple[int, ...]
    candidate_sizes: tuple[int, ...]
    pack_size_k: int
    horizon_cycles: int
    decision_cycle: int | None
    minimum_soh_range: float
    stratify_protocol: bool
    annealing_steps: int
    qaoa_shots: int
    qaoa_reps: int
    qaoa_optimizer: str
    qaoa_max_evaluations: int
    simulator_seed_base: int

    def __post_init__(self) -> None:
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("benchmark seeds must be nonempty and unique")
        if any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in self.seeds):
            raise ValueError("benchmark seeds must be nonnegative integers")
        if not self.candidate_sizes or len(set(self.candidate_sizes)) != len(self.candidate_sizes):
            raise ValueError("candidate_sizes must be nonempty and unique")
        if any(
            isinstance(n, bool) or not isinstance(n, int) or n < self.pack_size_k or n > 12
            for n in self.candidate_sizes
        ):
            raise ValueError("each candidate size must be an integer at least pack_size_k")
        for value, name in (
            (self.pack_size_k, "pack_size_k"),
            (self.horizon_cycles, "horizon_cycles"),
            (self.annealing_steps, "annealing_steps"),
            (self.qaoa_shots, "qaoa_shots"),
            (self.qaoa_reps, "qaoa_reps"),
            (self.qaoa_max_evaluations, "qaoa_max_evaluations"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.decision_cycle is not None and (
            isinstance(self.decision_cycle, bool)
            or not isinstance(self.decision_cycle, int)
            or self.decision_cycle < 0
        ):
            raise ValueError("decision_cycle must be a nonnegative integer or null")
        if not math.isfinite(self.minimum_soh_range) or self.minimum_soh_range < 0:
            raise ValueError("minimum_soh_range must be finite and nonnegative")
        if not isinstance(self.stratify_protocol, bool):
            raise ValueError("stratify_protocol must be a boolean")
        if self.qaoa_optimizer not in {"auto", "cobyla", "grid"}:
            raise ValueError("qaoa_optimizer must be auto, cobyla, or grid")
        if self.qaoa_reps != 1 and self.qaoa_optimizer == "grid":
            raise ValueError("the portable grid optimizer only supports qaoa_reps=1")
        if self.qaoa_max_evaluations < 2:
            raise ValueError("qaoa_max_evaluations must be at least 2")
        if self.qaoa_optimizer == "grid" and self.qaoa_max_evaluations < 121:
            raise ValueError("the p=1 grid optimizer requires at least 121 evaluations")
        if isinstance(self.simulator_seed_base, bool) or not isinstance(self.simulator_seed_base, int):
            raise ValueError("simulator_seed_base must be an integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": list(self.seeds),
            "candidate_sizes": list(self.candidate_sizes),
            "pack_size_k": self.pack_size_k,
            "horizon_cycles": self.horizon_cycles,
            "decision_cycle": self.decision_cycle,
            "minimum_soh_range": self.minimum_soh_range,
            "stratify_protocol": self.stratify_protocol,
            "annealing_steps": self.annealing_steps,
            "qaoa": {
                "shots": self.qaoa_shots,
                "reps": self.qaoa_reps,
                "optimizer": self.qaoa_optimizer,
                "max_evaluations": self.qaoa_max_evaluations,
                "simulator_seed_base": self.simulator_seed_base,
            },
        }


def load_benchmark_config(path: str | Path) -> BenchmarkConfig:
    """Read the strict JSON config schema used by the CLI."""

    with Path(path).open("r", encoding="utf-8") as source:
        raw = json.load(source)
    if not isinstance(raw, dict) or raw.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise ValueError("benchmark config must be a schema_version 1.0 JSON object")
    required = {
        "schema_version", "seeds", "candidate_sizes", "pack_size_k", "horizon_cycles",
        "decision_cycle", "minimum_soh_range", "stratify_protocol", "annealing_steps", "qaoa",
    }
    missing = required - raw.keys()
    extra = raw.keys() - required
    if missing or extra:
        raise ValueError(f"benchmark config keys mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    qaoa = raw["qaoa"]
    if not isinstance(qaoa, dict):
        raise ValueError("qaoa config must be an object")
    qaoa_required = {"shots", "reps", "optimizer", "max_evaluations", "simulator_seed_base"}
    if qaoa.keys() != qaoa_required:
        raise ValueError(
            "qaoa config keys mismatch; "
            f"missing={sorted(qaoa_required - qaoa.keys())}, extra={sorted(qaoa.keys() - qaoa_required)}"
        )
    if not isinstance(raw["seeds"], list) or not isinstance(raw["candidate_sizes"], list):
        raise ValueError("seeds and candidate_sizes must be JSON arrays")
    return BenchmarkConfig(
        seeds=tuple(raw["seeds"]),
        candidate_sizes=tuple(raw["candidate_sizes"]),
        pack_size_k=raw["pack_size_k"],
        horizon_cycles=raw["horizon_cycles"],
        decision_cycle=raw["decision_cycle"],
        minimum_soh_range=raw["minimum_soh_range"],
        stratify_protocol=raw["stratify_protocol"],
        annealing_steps=raw["annealing_steps"],
        qaoa_shots=qaoa["shots"],
        qaoa_reps=qaoa["reps"],
        qaoa_optimizer=qaoa["optimizer"],
        qaoa_max_evaluations=qaoa["max_evaluations"],
        simulator_seed_base=qaoa["simulator_seed_base"],
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_pool(raw: Mapping[str, Any], mission: MissionProfile) -> CandidatePool:
    snapshots_raw = raw.get("snapshots")
    if not isinstance(snapshots_raw, list):
        raise ValueError("each benchmark pool must contain a snapshots array")
    truth_raw = raw.get("future_truth")
    if truth_raw is not None and not isinstance(truth_raw, list):
        raise ValueError("pool future_truth must be an array or null")
    snapshots = tuple(CellSnapshot(**item) for item in snapshots_raw)
    truth = None if truth_raw is None else tuple(FutureTruth(**item) for item in truth_raw)
    pool = CandidatePool(
        pool_id=raw["pool_id"],
        decision_cycle=raw["decision_cycle"],
        horizon_cycles=raw["horizon_cycles"],
        candidate_ids=tuple(raw["candidate_ids"]),
        snapshots=snapshots,
        future_truth=truth,
        seed=raw["seed"],
        selection_metadata=raw.get("selection_metadata", {}),
    )
    if pool.future_truth is None:
        raise ValueError(f"pool {pool.pool_id!r} has no held-out future truth")
    if pool.horizon_cycles != mission.horizon_cycles:
        raise ValueError(f"pool {pool.pool_id!r} does not match the configured horizon")
    if len(pool.snapshots) > 12:
        raise ValueError("Task 6 QAOA requires candidate sizes N <= 12")
    return pool


def load_or_generate_pools(
    input_path: str | Path,
    config: BenchmarkConfig,
) -> tuple[list[CandidatePool], str, dict[str, Any]]:
    """Load a pool export or construct seeded trials from canonical trajectories."""

    path = Path(input_path)
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("benchmark input root must be a JSON object")
    classification = payload.get("data_classification")
    if classification not in {"real", "derived-real"}:
        raise ValueError("scientific benchmarks require real or derived-real input; synthetic data is rejected")
    if payload.get("source_dataset") != "deep_sorting_reused_batteries":
        raise ValueError("Task 6 core benchmark requires the Deep Sorting reused-battery dataset")
    mission = replace(
        PV_TOU_MISSION,
        horizon_cycles=config.horizon_cycles,
        pack_size_k=config.pack_size_k,
    )
    metadata: dict[str, Any] = {
        "source_dataset": payload.get("source_dataset"),
        "data_classification": classification,
        "input_sha256": sha256_file(path),
        "input_kind": None,
        "decision_cycle": config.decision_cycle,
    }
    pools: list[CandidatePool] = []
    if isinstance(payload.get("pools"), list):
        metadata["input_kind"] = "candidate_pool_export"
        if not isinstance(payload.get("mission"), dict):
            raise ValueError("candidate pool export has no mission metadata")
        source_mission = MissionProfile(**payload["mission"])
        if source_mission != mission:
            raise ValueError("candidate pool export mission differs from the fixed benchmark config")
        requested = {(n, seed) for n in config.candidate_sizes for seed in config.seeds}
        available: dict[tuple[int, int], CandidatePool] = {}
        for raw in payload["pools"]:
            if not isinstance(raw, dict):
                raise ValueError("candidate pool entries must be objects")
            pool = _decode_pool(raw, source_mission)
            if config.decision_cycle is not None and pool.decision_cycle != config.decision_cycle:
                raise ValueError(f"pool {pool.pool_id!r} decision cycle differs from the benchmark config")
            key = (len(pool.snapshots), pool.seed)
            if key in available:
                raise ValueError(f"duplicate candidate pool for N={key[0]}, seed={key[1]}")
            available[key] = pool
        missing = requested - available.keys()
        if missing:
            raise ValueError(
                "candidate pool export is missing configured (N, seed) trials: "
                + ", ".join(f"({n}, {seed})" for n, seed in sorted(missing))
                + "; pass the canonical trajectories JSON to generate the fixed seed set"
            )
        pools = [available[key] for key in sorted(requested, key=lambda pair: (pair[1], pair[0]))]
        metadata["decision_cycle"] = sorted({pool.decision_cycle for pool in pools})
    elif isinstance(payload.get("cells"), list):
        metadata["input_kind"] = "canonical_trajectories"
        if payload.get("phase") != "second_life":
            raise ValueError("the retrospective benchmark requires second_life trajectories")
        trajectories = trajectories_from_dict(payload)
        decision_cycle = config.decision_cycle
        if decision_cycle is None:
            decision_cycle, eligible_count = select_decision_cycle(
                trajectories,
                horizon_cycles=config.horizon_cycles,
                minimum_candidate_soh=mission.minimum_soh,
                minimum_soh_range=config.minimum_soh_range,
                require_resistance=mission.resistance_weight > 0,
                require_temperature=mission.temperature_weight > 0,
            )
            metadata["decision_cycle_selection"] = "maximum valid coverage; earliest cycle breaks ties"
            metadata["eligible_cell_count_at_decision_cycle"] = eligible_count
        metadata["decision_cycle"] = decision_cycle
        for seed, n in itertools.product(config.seeds, config.candidate_sizes):
            pools.append(
                generate_candidate_pool(
                    trajectories,
                    decision_cycle=decision_cycle,
                    horizon_cycles=config.horizon_cycles,
                    seed=seed,
                    n=n,
                    k=config.pack_size_k,
                    mission=mission,
                    include_future_truth=True,
                    stratify_protocol=config.stratify_protocol,
                    minimum_soh_range=config.minimum_soh_range,
                )
            )
    else:
        raise ValueError("input must be a canonical trajectory asset or candidate-pool export")

    if not pools:
        raise ValueError("benchmark input contains no configured trial pools")
    return pools, str(classification), metadata


def _metric_row(result: OptimizationResult, objective_gap: float | None) -> dict[str, Any]:
    return {
        "feasible": result.feasible,
        "objective_value": result.objective_value,
        "objective_gap": objective_gap,
        "current_capacity_spread_ah": result.current_capacity_spread_ah,
        "current_capacity_cv": result.current_capacity_cv,
        "predicted_pack_divergence": result.predicted_pack_divergence,
        "observed_pack_divergence": result.observed_pack_divergence,
        "observed_usable_capacity_ah": result.observed_usable_capacity_ah,
        "runtime_ms": result.runtime_ms,
    }


def _qaoa_row(result: QAOAResult, exact_objective: float) -> dict[str, Any]:
    recommended = result.recommended_result
    gap = None if recommended is None else max(0.0, recommended.objective_value - exact_objective)
    return {
        "feasible": result.feasible,
        "status_message": result.status_message,
        "objective_value": recommended.objective_value if recommended else None,
        "objective_gap": gap,
        "current_capacity_spread_ah": recommended.current_capacity_spread_ah if recommended else None,
        "current_capacity_cv": recommended.current_capacity_cv if recommended else None,
        "predicted_pack_divergence": recommended.predicted_pack_divergence if recommended else None,
        "observed_pack_divergence": recommended.observed_pack_divergence if recommended else None,
        "observed_usable_capacity_ah": recommended.observed_usable_capacity_ah if recommended else None,
        "runtime_ms": result.timings_ms.get("total_ms"),
        "feasible_probability_mass": result.feasible_probability_mass,
        "optimum_probability_mass": result.optimum_probability_mass,
        "best_feasible_optimality_gap": result.best_feasible_optimality_gap,
        "shots_requested": result.shots_requested,
        "shots_observed": result.shots_observed,
        "backend": result.backend,
        "optimizer": {
            "method": result.optimizer.get("method"),
            "evaluations": result.optimizer.get("evaluations"),
            "budget": result.optimizer.get("budget"),
        },
        "circuit": result.circuit,
        "timings_ms": result.timings_ms,
        "backend_jobs_submitted": result.backend_jobs_submitted,
        "single_backend_job": result.single_backend_job,
    }


def run_trial(
    pool: CandidatePool,
    config: BenchmarkConfig,
    *,
    backend: Any | None = None,
    simulator_seed_offset: int = 0,
) -> dict[str, Any]:
    """Run the required algorithms and paired objective ablation for one pool."""

    mission = replace(
        PV_TOU_MISSION,
        horizon_cycles=config.horizon_cycles,
        pack_size_k=config.pack_size_k,
    )
    truth = pool.future_truth
    if truth is None:
        raise ValueError("benchmark trials require held-out future truth")
    current = build_optimization_instance(pool, mission=mission, objective_mode="current_only")
    aware = build_optimization_instance(pool, mission=mission, objective_mode="trajectory_aware")

    exact_current = exact_enumeration(current, future_truth=truth)
    exact_aware = exact_enumeration(aware, future_truth=truth)
    current_optimum = exact_current.objective_value
    aware_optimum = exact_aware.objective_value

    soh = soh_sort(current, future_truth=truth)
    greedy = compatibility_greedy(aware, future_truth=truth)
    annealing = simulated_annealing(
        aware,
        seed=pool.seed,
        steps=config.annealing_steps,
        future_truth=truth,
    )

    exact_current_row = _metric_row(exact_current, 0.0)
    exact_aware_row = _metric_row(exact_aware, 0.0)
    exact_aware_bits = [
        tuple(1 if index in indices else 0 for index in range(aware.n))
        for indices in exact_aware.metadata["tied_optima"]
    ]
    qaoa = run_qaoa(
        aware,
        backend,
        shots=config.qaoa_shots,
        reps=config.qaoa_reps,
        optimizer_mode=config.qaoa_optimizer,
        max_evaluations=config.qaoa_max_evaluations,
        exact_optimal_bitstrings=exact_aware_bits,
        future_truth=truth,
        simulator_seed=config.simulator_seed_base + pool.seed + simulator_seed_offset,
        transpiler_seed=config.simulator_seed_base + pool.seed + simulator_seed_offset,
    )
    constrained_results = (soh, exact_current, greedy, annealing, exact_aware)
    if any(
        not result.feasible or len(result.selected_indices) != config.pack_size_k
        for result in constrained_results
    ):
        raise AssertionError("a constrained classical algorithm did not select exactly K cells")
    qaoa_result = _qaoa_row(qaoa, aware_optimum)

    return {
        "trial_id": f"n{len(pool.snapshots)}-seed{pool.seed}",
        "seed": pool.seed,
        "candidate_count": len(pool.snapshots),
        "pack_size": config.pack_size_k,
        "decision_cycle": pool.decision_cycle,
        "horizon_cycles": pool.horizon_cycles,
        "algorithms": {
            "soh_sort": _metric_row(soh, max(0.0, soh.objective_value - current_optimum)),
            "compatibility_greedy": _metric_row(greedy, max(0.0, greedy.objective_value - aware_optimum)),
            "simulated_annealing": _metric_row(annealing, max(0.0, annealing.objective_value - aware_optimum)),
            "exact_enumeration": exact_aware_row,
            "qaoa": qaoa_result,
        },
        "objective_ablation": {
            "exact_current_only": exact_current_row,
            "exact_trajectory_aware": exact_aware_row,
            "opd_improvement_trajectory_aware_minus_current": (
                exact_current.observed_pack_divergence - exact_aware.observed_pack_divergence
                if exact_current.observed_pack_divergence is not None
                and exact_aware.observed_pack_divergence is not None
                else None
            ),
            "trajectory_aware_lower_opd": (
                exact_aware.observed_pack_divergence < exact_current.observed_pack_divergence
                if exact_current.observed_pack_divergence is not None
                and exact_aware.observed_pack_divergence is not None
                else None
            ),
        },
    }


def _mean(values: Sequence[float | int | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.fmean(finite) if finite else None


def _median(values: Sequence[float | int | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(finite) if finite else None


def _aggregate_rows(rows: Sequence[Mapping[str, Any]], *, valid_trials: int) -> dict[str, Any]:
    feasible = [row for row in rows if row.get("feasible") is True]
    return {
        "valid_trials": valid_trials,
        "feasible_trials": len(feasible),
        "success_rate": len(feasible) / valid_trials if valid_trials else None,
        "observed_opd_mean": _mean([row.get("observed_pack_divergence") for row in rows]),
        "observed_opd_median": _median([row.get("observed_pack_divergence") for row in rows]),
        "observed_usable_capacity_ah_mean": _mean([row.get("observed_usable_capacity_ah") for row in rows]),
        "observed_usable_capacity_ah_median": _median([row.get("observed_usable_capacity_ah") for row in rows]),
        "current_capacity_spread_ah_mean": _mean([row.get("current_capacity_spread_ah") for row in rows]),
        "current_capacity_spread_ah_median": _median([row.get("current_capacity_spread_ah") for row in rows]),
        "objective_gap_mean": _mean([row.get("objective_gap") for row in rows]),
        "objective_gap_median": _median([row.get("objective_gap") for row in rows]),
        "runtime_ms_mean": _mean([row.get("runtime_ms") for row in rows]),
        "runtime_ms_median": _median([row.get("runtime_ms") for row in rows]),
    }


def summarize_trials(trials: Sequence[Mapping[str, Any]], provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact aggregate report directly from completed trial rows."""

    if not trials:
        raise ValueError("cannot summarize an empty benchmark")
    names = ("soh_sort", "compatibility_greedy", "simulated_annealing", "exact_enumeration", "qaoa")
    algorithms = {
        name: _aggregate_rows(
            [trial["algorithms"][name] for trial in trials],
            valid_trials=len(trials),
        )
        for name in names
    }
    current_rows = [trial["objective_ablation"]["exact_current_only"] for trial in trials]
    aware_rows = [trial["objective_ablation"]["exact_trajectory_aware"] for trial in trials]
    paired_deltas = [
        trial["objective_ablation"]["opd_improvement_trajectory_aware_minus_current"]
        for trial in trials
    ]
    bool_results = [trial["objective_ablation"]["trajectory_aware_lower_opd"] for trial in trials]
    qaoa_rows = [trial["algorithms"]["qaoa"] for trial in trials]
    timing_keys = sorted({key for row in qaoa_rows for key in row.get("timings_ms", {})})
    qaoa_timing = {
        key: _mean([row.get("timings_ms", {}).get(key) for row in qaoa_rows])
        for key in timing_keys
    }
    qaoa_quality = {
        "valid_trials": len(trials),
        "trials_with_feasible_sample": sum(row.get("feasible") is True for row in qaoa_rows),
        "mean_feasible_probability_mass": _mean([row.get("feasible_probability_mass") for row in qaoa_rows]),
        "mean_optimum_probability_mass": _mean([row.get("optimum_probability_mass") for row in qaoa_rows]),
        "optimum_sample_rate": (
            sum((row.get("optimum_probability_mass") or 0.0) > 0 for row in qaoa_rows) / len(qaoa_rows)
        ),
        "mean_best_sampled_gap": _mean([row.get("best_feasible_optimality_gap") for row in qaoa_rows]),
        "median_best_sampled_gap": _median([row.get("best_feasible_optimality_gap") for row in qaoa_rows]),
        "mean_timings_ms": qaoa_timing,
        "backend_labels": sorted({str(row.get("backend")) for row in qaoa_rows}),
    }
    ablation = {
        "valid_paired_trials": len(trials),
        "exact_current_only_opd_mean": _mean([row.get("observed_pack_divergence") for row in current_rows]),
        "exact_trajectory_aware_opd_mean": _mean([row.get("observed_pack_divergence") for row in aware_rows]),
        "exact_current_only_bottleneck_ah_mean": _mean([row.get("observed_usable_capacity_ah") for row in current_rows]),
        "exact_trajectory_aware_bottleneck_ah_mean": _mean([row.get("observed_usable_capacity_ah") for row in aware_rows]),
        "mean_opd_improvement": _mean(paired_deltas),
        "median_opd_improvement": _median(paired_deltas),
        "trajectory_aware_lower_opd_trials": sum(value is True for value in bool_results),
        "trajectory_aware_equal_or_higher_opd_trials": sum(value is False for value in bool_results),
        "fraction_trajectory_aware_lower_opd": sum(value is True for value in bool_results) / len(trials),
    }
    candidate_sizes = sorted({int(trial["candidate_count"]) for trial in trials})
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "data_classification": provenance["data_classification"],
        "source_dataset": provenance.get("source_dataset"),
        "trial_count": len(trials),
        "candidate_sizes": candidate_sizes,
        "pack_size_k": trials[0]["pack_size"],
        "decision_cycles": sorted({trial["decision_cycle"] for trial in trials}),
        "horizon_cycles": trials[0]["horizon_cycles"],
        "algorithms": algorithms,
        "objective_ablation": ablation,
        "qaoa_quality": qaoa_quality,
        "redistribution_license_verified": False,
        "contains_cell_level_records": False,
        "provenance": dict(provenance),
    }


def validate_benchmark_exports(summary: Mapping[str, Any], trials: Mapping[str, Any]) -> None:
    """Reject malformed, non-finite, or internally inconsistent export payloads."""

    if summary.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise ValueError("unsupported benchmark summary schema")
    if trials.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise ValueError("unsupported benchmark trials schema")
    rows = trials.get("trials")
    if not isinstance(rows, list) or not rows:
        raise ValueError("benchmark trials export must contain a nonempty array")
    is_replay_subset = trials.get("selection", {}).get("mode") == "predeclared_seed_subset"
    if (not is_replay_subset and summary.get("trial_count") != len(rows)) or (
        is_replay_subset and len(rows) > summary.get("trial_count", 0)
    ):
        raise ValueError("summary trial_count does not match exported trial rows")
    ids = [row.get("trial_id") for row in rows]
    if any(not isinstance(trial_id, str) for trial_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("benchmark trial IDs must be unique strings")
    if summary.get("provenance") != trials.get("provenance"):
        raise ValueError("summary and trials provenance differ")
    # This validates JSON portability and rejects NaN/Infinity and Python-only values.
    canonical_json_bytes(dict(summary))
    canonical_json_bytes(dict(trials))


def select_replay_trials(trials: Sequence[Mapping[str, Any]], count: int = 3) -> list[dict[str, Any]]:
    """Select a predeclared-seed prefix for the small browser replay export."""

    if count < 1:
        raise ValueError("replay trial count must be positive")
    ordered = sorted(trials, key=lambda trial: (int(trial["seed"]), int(trial["candidate_count"])))
    selected: list[dict[str, Any]] = []
    seen_sizes: set[int] = set()
    # Prefer the first predeclared trial at each candidate size, then fill the
    # remaining slots by seed order. Selection does not inspect future outcomes.
    for trial in ordered:
        size = int(trial["candidate_count"])
        if size not in seen_sizes:
            selected.append(dict(trial))
            seen_sizes.add(size)
            if len(selected) == count:
                return selected
    for trial in ordered:
        if trial not in selected:
            selected.append(dict(trial))
            if len(selected) == count:
                break
    return selected


def _checkpoint_line(value: Mapping[str, Any]) -> bytes:
    """Encode one compact JSONL record so each fsynced trial is independently readable."""

    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_checkpoint_header(path: Path, header: Mapping[str, Any], *, fresh: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh:
        mode = "wb"
    else:
        mode = "xb"
    with path.open(mode) as target:
        target.write(_checkpoint_line(header))
        target.flush()
        os.fsync(target.fileno())


def _load_checkpoint(
    path: Path,
    header: Mapping[str, Any],
    *,
    fresh: bool,
) -> tuple[dict[str, dict[str, Any]], bool]:
    expected = _checkpoint_line(header).rstrip(b"\n")
    if fresh or not path.exists():
        _write_checkpoint_header(path, header, fresh=fresh)
        return {}, False
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    if not lines or lines[0].rstrip(b"\r\n") != expected:
        raise ValueError(
            f"checkpoint {path} belongs to another config/input; use --fresh or a new checkpoint path"
        )
    results: dict[str, dict[str, Any]] = {}
    backend_attempted = False
    valid_end = len(lines[0])
    for line_index, line in enumerate(lines[1:], start=1):
        is_last = line_index == len(lines) - 1
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            if not is_last or line.endswith((b"\n", b"\r")):
                raise ValueError(f"checkpoint has a corrupt completed record at line {line_index + 1}") from error
            # A process can be interrupted during a final append. Discard only
            # that incomplete tail; all prior fsynced trial records stay intact.
            with path.open("r+b") as target:
                target.truncate(valid_end)
                target.flush()
                os.fsync(target.fileno())
            break
        if "trial" in item:
            trial = item["trial"]
            trial_id = trial["trial_id"]
            if not isinstance(trial_id, str) or trial_id in results:
                raise ValueError("checkpoint contains an invalid or duplicate trial ID")
            results[trial_id] = trial
        elif "update_trial" in item:
            trial = item["update_trial"]
            trial_id = trial["trial_id"]
            if not isinstance(trial_id, str) or trial_id not in results:
                raise ValueError("checkpoint update references an unknown trial")
            results[trial_id] = trial
        elif item.get("backend_attempt"):
            if backend_attempted:
                raise ValueError("checkpoint contains duplicate backend attempt markers")
            backend_attempted = True
        else:
            raise ValueError("checkpoint record type is unknown")
        valid_end += len(line)
        if line and not line.endswith((b"\n", b"\r")) and valid_end == len(data):
            with path.open("ab") as target:
                target.write(b"\n")
                target.flush()
                os.fsync(target.fileno())
    return results, backend_attempted


def _append_checkpoint(path: Path, trial: Mapping[str, Any]) -> None:
    record = _checkpoint_line({"trial": dict(trial)})
    with path.open("ab") as target:
        target.write(record)
        target.flush()
        os.fsync(target.fileno())


def _append_checkpoint_event(path: Path, event: Mapping[str, Any]) -> None:
    record = _checkpoint_line(event)
    with path.open("ab") as target:
        target.write(record)
        target.flush()
        os.fsync(target.fileno())


def _load_backend_factory(specification: str) -> Any:
    if ":" not in specification:
        raise ValueError("backend factory must use module.path:function syntax")
    module_name, function_name = specification.split(":", 1)
    if not module_name or not function_name:
        raise ValueError("backend factory must use module.path:function syntax")
    factory = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(factory):
        raise ValueError(f"backend factory {specification!r} is not callable")
    return factory()


def _provenance_record(
    input_metadata: Mapping[str, Any],
    config: BenchmarkConfig,
    source_path: Path,
) -> tuple[dict[str, Any], str, str]:
    config_payload = config.to_dict()
    config_hash = _sha256_bytes(canonical_json_bytes(config_payload))
    source_provenance_path = source_path.parent / "provenance.json"
    source_provenance_hash = (
        sha256_file(source_provenance_path) if source_provenance_path.exists() else None
    )
    provenance_core = {
        "source_dataset": input_metadata.get("source_dataset"),
        "data_classification": input_metadata.get("data_classification"),
        "input_kind": input_metadata.get("input_kind"),
        "input_sha256": input_metadata.get("input_sha256"),
        "source_provenance_sha256": source_provenance_hash,
        "config_sha256": config_hash,
    }
    provenance_hash = _sha256_bytes(canonical_json_bytes(provenance_core))
    return {
        **provenance_core,
        "provenance_sha256": provenance_hash,
    }, config_hash, provenance_hash


def execute_benchmark(
    input_path: str | Path,
    config: BenchmarkConfig,
    *,
    output_dir: str | Path,
    web_output_dir: str | Path | None = None,
    checkpoint_path: str | Path | None = None,
    resume: bool = True,
    backend_factory: str | None = None,
    backend_trial_seed: int | None = None,
    predictor_evaluation_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run/resume all configured trials and write compact replay exports."""

    if (backend_factory is None) != (backend_trial_seed is None):
        raise ValueError("backend_factory and backend_trial_seed must be supplied together")
    if backend_trial_seed is not None and backend_trial_seed not in config.seeds:
        raise ValueError("backend_trial_seed must be one of the configured benchmark seeds")
    if backend_factory is not None and len(config.candidate_sizes) != 1:
        raise ValueError("the selected backend experiment requires exactly one configured candidate size")
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    pools, classification, input_metadata = load_or_generate_pools(input_path, config)
    input_metadata = {**input_metadata, "data_classification": classification}
    provenance, config_hash, provenance_hash = _provenance_record(input_metadata, config, input_path)
    header = {
        "record_type": "repackq_benchmark_checkpoint",
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "config_sha256": config_hash,
        "provenance_sha256": provenance_hash,
        "input_sha256": provenance["input_sha256"],
        "backend_factory": backend_factory,
        "backend_trial_seed": backend_trial_seed,
    }
    checkpoint = Path(checkpoint_path) if checkpoint_path is not None else output_dir / "checkpoint.jsonl"
    completed, backend_attempted = _load_checkpoint(checkpoint, header, fresh=not resume)
    expected_ids = {f"n{len(pool.snapshots)}-seed{pool.seed}" for pool in pools}
    unexpected = completed.keys() - expected_ids
    if unexpected:
        raise ValueError(f"checkpoint has trials absent from this input: {sorted(unexpected)}")

    for pool in pools:
        trial_id = f"n{len(pool.snapshots)}-seed{pool.seed}"
        if trial_id in completed:
            continue
        trial = run_trial(
            pool,
            config,
            simulator_seed_offset=0,
        )
        _append_checkpoint(checkpoint, trial)
        completed[trial_id] = trial

    if backend_factory is not None:
        if backend_attempted and not any("backend_experiment" in trial for trial in completed.values()):
            raise RuntimeError(
                "checkpoint records a selected backend attempt with no saved result; "
                "refusing to risk submitting a duplicate backend job. Use --fresh only after reviewing the backend job state."
            )
        if not backend_attempted:
            target_pool = next(pool for pool in pools if pool.seed == backend_trial_seed)
            _append_checkpoint_event(checkpoint, {"backend_attempt": {"seed": backend_trial_seed}})
            backend_attempted = True
            backend = _load_backend_factory(backend_factory)
            mission = replace(
                PV_TOU_MISSION,
                horizon_cycles=config.horizon_cycles,
                pack_size_k=config.pack_size_k,
            )
            instance = build_optimization_instance(target_pool, mission=mission, objective_mode="trajectory_aware")
            exact = exact_enumeration(instance)
            exact_bits = [
                tuple(1 if index in indices else 0 for index in range(instance.n))
                for indices in exact.metadata["tied_optima"]
            ]
            backend_result = run_qaoa(
                instance,
                backend,
                shots=config.qaoa_shots,
                reps=config.qaoa_reps,
                optimizer_mode=config.qaoa_optimizer,
                max_evaluations=config.qaoa_max_evaluations,
                exact_optimal_bitstrings=exact_bits,
                future_truth=target_pool.future_truth,
                simulator_seed=None,
                transpiler_seed=config.simulator_seed_base + target_pool.seed,
            )
            if backend_result.backend_jobs_submitted != 1:
                raise AssertionError("selected backend experiment must submit exactly one sampling job")
            trial_id = f"n{len(target_pool.snapshots)}-seed{target_pool.seed}"
            updated = dict(completed[trial_id])
            updated["backend_experiment"] = _qaoa_row(backend_result, exact.objective_value)
            _append_checkpoint_event(checkpoint, {"update_trial": updated})
            completed[trial_id] = updated

    ordered_trials = [completed[f"n{len(pool.snapshots)}-seed{pool.seed}"] for pool in pools]
    summary = summarize_trials(ordered_trials, provenance)
    # Predictor results are included only when their checksum matches the exact
    # trajectory asset used to build the trials.
    prediction_path = Path(predictor_evaluation_path) if predictor_evaluation_path else input_path.parent / "prediction_evaluation.json"
    if prediction_path.exists():
        with prediction_path.open("r", encoding="utf-8") as source:
            prediction_payload = json.load(source)
        expected_trajectory_hash = input_metadata.get("input_sha256")
        if prediction_payload.get("input_sha256") == expected_trajectory_hash:
            summary["prediction_evaluation"] = {
                "prediction_method": prediction_payload.get("prediction_method"),
                "metrics": prediction_payload.get("metrics"),
                "limitations": prediction_payload.get("limitations", []),
            }
            provenance["prediction_evaluation_sha256"] = sha256_file(prediction_path)
            summary["provenance"] = dict(provenance)

    trial_payload = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "data_classification": classification,
        "source_dataset": provenance.get("source_dataset"),
        "redistribution_license_verified": False,
        "contains_cell_level_records": False,
        "provenance": dict(provenance),
        "trials": ordered_trials,
    }
    validate_benchmark_exports(summary, trial_payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "summary.json", summary)
    write_json_atomic(output_dir / "trials.json", trial_payload)
    replay_payload = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "data_classification": classification,
        "source_dataset": provenance.get("source_dataset"),
        "redistribution_license_verified": False,
        "contains_cell_level_records": False,
        "provenance": dict(provenance),
        "trials": select_replay_trials(ordered_trials),
        "selection": {
            "mode": "predeclared_seed_subset",
            "basis": "first configured seed per candidate size, then seed order; no held-out outcomes inspected",
        },
    }
    replay_summary = dict(summary)
    validate_benchmark_exports(replay_summary, replay_payload)
    # Both are valid small UI payloads with identical aggregate provenance.
    write_json_atomic(output_dir / "web_summary.json", replay_summary)
    write_json_atomic(output_dir / "web_trials.json", replay_payload)
    if web_output_dir is not None:
        web_directory = Path(web_output_dir)
        web_directory.mkdir(parents=True, exist_ok=True)
        write_json_atomic(web_directory / "summary.json", replay_summary)
        write_json_atomic(web_directory / "trials.json", replay_payload)
    return summary, trial_payload


def render_results_markdown(summary: Mapping[str, Any]) -> str:
    """Render the generated aggregate results as a restrained scientific note."""

    algorithms = summary["algorithms"]
    ablation = summary["objective_ablation"]
    qaoa = summary["qaoa_quality"]
    lines = [
        "# RePack-Q benchmark results",
        "",
        f"This report summarizes {summary['trial_count']} valid retrospective trials "
        f"from `{summary.get('source_dataset')}` ({summary['data_classification']}). "
        f"Each trial selected K={summary['pack_size_k']} from N={', '.join(map(str, summary['candidate_sizes']))} "
        f"at decision cycle(s) {', '.join(map(str, summary['decision_cycles']))}, with a "
        f"{summary['horizon_cycles']}-cycle prediction horizon.",
        "",
        "## Pack outcomes",
        "",
        "Observed pack divergence is the population CV of held-out capacity. A lower value means "
        "the selected cells were more balanced at the retrospective horizon. The usable capacity "
        "is the minimum held-out cell capacity in the selected series string.",
        "",
        "| Method | Mean OPD | Median OPD | Mean future bottleneck (Ah) | Mean current spread (Ah) | Mean objective gap | Mean runtime (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, label in (
        ("soh_sort", "SOH sort (current-only score)"),
        ("compatibility_greedy", "Compatibility greedy"),
        ("simulated_annealing", "Simulated annealing"),
        ("exact_enumeration", "Exact trajectory-aware"),
        ("qaoa", "QAOA best sampled feasible pack"),
    ):
        row = algorithms[name]
        lines.append(
            f"| {label} | {_fmt(row['observed_opd_mean'])} | {_fmt(row['observed_opd_median'])} | "
            f"{_fmt(row['observed_usable_capacity_ah_mean'])} | "
            f"{_fmt(row['current_capacity_spread_ah_mean'])} | {_fmt(row['objective_gap_mean'])} | "
            f"{_fmt(row['runtime_ms_mean'])} |"
        )
    lines.extend([
        "",
        "All runtimes were measured locally. QAOA time includes statevector parameter optimization, "
        "transpilation, and one local BasicSimulator sampling job; it does not include remote queue time.",
    ])
    lines.extend([
        "",
        "## Objective ablation",
        "",
        f"- Exact current-only mean OPD: **{_fmt(ablation['exact_current_only_opd_mean'])}**.",
        f"- Exact trajectory-aware mean OPD: **{_fmt(ablation['exact_trajectory_aware_opd_mean'])}**.",
        f"- Paired mean improvement (current-only OPD minus trajectory-aware OPD): "
        f"**{_fmt(ablation['mean_opd_improvement'])}**; trajectory-aware had lower OPD in "
        f"{ablation['trajectory_aware_lower_opd_trials']}/{ablation['valid_paired_trials']} trials.",
        f"- Mean future bottleneck capacity was {_fmt(ablation['exact_current_only_bottleneck_ah_mean'])} Ah "
        f"for current-only and {_fmt(ablation['exact_trajectory_aware_bottleneck_ah_mean'])} Ah "
        "for trajectory-aware exact selection.",
        "",
        "This ablation isolates the objective formulation from the optimizer: both selections "
        "use exact enumeration over the same candidate pool, then are evaluated against the same "
        "held-out truth. It is descriptive for this predeclared seed set; it is not a significance test.",
        "SOH-sort objective gaps are measured against the current-only exact oracle; other classical "
        "gaps and the QAOA gap are measured against the trajectory-aware exact oracle, so gaps "
        "from different rows use different objective scales.",
        "",
        "## QAOA diagnostics",
        "",
        f"A feasible K-cell result was sampled in {qaoa['trials_with_feasible_sample']}/{qaoa['valid_trials']} "
        f"trials (mean feasible shot mass {_fmt(qaoa['mean_feasible_probability_mass'])}). "
        f"The exact optimum appeared in the measured samples in {qaoa['optimum_sample_rate']:.1%} "
        f"of trials; mean best-sampled objective gap was {_fmt(qaoa['mean_best_sampled_gap'])}. "
        f"Average parameter-optimization time was {_fmt(qaoa['mean_timings_ms'].get('parameter_optimization_ms'))} ms, "
        f"and average local sampling time was {_fmt(qaoa['mean_timings_ms'].get('backend_sampling_ms'))} ms.",
        "",
        "QAOA is an approximate solver here. These measurements do not establish quantum speedup; "
        "the instances are small enough for exact enumeration and classical methods.",
    ])
    prediction = summary.get("prediction_evaluation")
    if prediction:
        metrics = prediction.get("metrics", {})
        lines.extend([
            "",
            "## Predictor validation",
            "",
            f"Across {metrics.get('valid_held_out_forecasts')} valid cell-by-cutoff forecasts, "
            f"the weighted recent linear model had MAE {_fmt(metrics.get('mae_ah'))} Ah, RMSE "
            f"{_fmt(metrics.get('rmse_ah'))} Ah, median absolute percentage error "
            f"{_fmt(metrics.get('median_absolute_percentage_error'))}%, and future-truth coverage "
            f"{_fmt(metrics.get('future_truth_coverage'))}. Cutoffs within a cell overlap.",
        ])
    lines.extend([
        "",
        "## Limits and reproducibility",
        "",
        "The horizon uses dataset cycle indices, not calendar time. The predictor is a simple "
        "recent linear fit, and the mission does not model a household load trace or electrochemical "
        "response. Held-out truth is used only after the candidate pools and solver-visible snapshots "
        "are fixed. The 20 seeded pools are draws from one inventory and can overlap; they are not "
        "independent battery populations. The dataset record does not state redistribution terms, so generated full cell "
        "trajectories remain local; checked-in replay exports contain only aggregate trial outcomes "
        "and no cell identifiers or snapshots.",
        "",
        f"- Config SHA-256: `{summary['provenance']['config_sha256']}`",
        f"- Input SHA-256: `{summary['provenance']['input_sha256']}`",
        f"- Provenance SHA-256: `{summary['provenance']['provenance_sha256']}`",
        "",
        "Re-run with `PYTHONPATH=src python src/scripts/run_benchmarks.py --input "
        "data/processed/trajectories.json --config configs/task6_benchmark.json`.",
        "",
    ])
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.5f}"
    return str(value)


def write_results_markdown(path: str | Path, summary: Mapping[str, Any]) -> None:
    """Atomically write the generated result narrative."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(render_results_markdown(summary))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    except Exception:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
        raise

