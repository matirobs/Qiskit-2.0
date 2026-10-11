"""Run the default N=8/K=4 QAOA experiment on Qiskit BasicSimulator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.models import CandidatePool, CellSnapshot, FutureTruth, MissionProfile
from repackq.optimization.objective import build_optimization_instance
from repackq.optimization.solvers import exact_enumeration
from repackq.quantum.engine import run_qaoa


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay one saved real-data candidate pool, optimize QAOA parameters "
            "locally, and sample once on Qiskit's bundled BasicSimulator."
        )
    )
    parser.add_argument("--input", required=True, help="local data/processed/demo_pools.json export")
    parser.add_argument("--pool-id", help="pool to run; defaults to the export's preselected pool")
    parser.add_argument("--objective-mode", choices=("current_only", "trajectory_aware"), default="trajectory_aware")
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--optimizer", choices=("auto", "cobyla", "grid"), default="auto")
    parser.add_argument("--max-evaluations", type=int, default=160)
    parser.add_argument("--simulator-seed", type=int, default=20261010)
    return parser


def _load_pool(path: Path, requested_pool_id: str | None) -> tuple[str, CandidatePool, MissionProfile]:
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("candidate-pool export root must be a JSON object")
    classification = payload.get("data_classification")
    if classification not in {"real", "derived-real"}:
        raise ValueError(
            "the real-data QAOA demo requires a real or derived-real pool export; "
            "synthetic fixtures are restricted to tests and UI development"
        )
    pools = payload.get("pools")
    if not isinstance(pools, list) or not pools:
        raise ValueError("candidate-pool export must contain a nonempty pools array")
    pool_id = requested_pool_id or payload.get("default_pool_id")
    raw = next((item for item in pools if item.get("pool_id") == pool_id), None)
    if raw is None:
        raise ValueError(f"pool {pool_id!r} was not found in the export")
    mission = MissionProfile(**payload["mission"])
    snapshots = tuple(CellSnapshot(**item) for item in raw["snapshots"])
    future_raw = raw.get("future_truth")
    future_truth = None if future_raw is None else tuple(FutureTruth(**item) for item in future_raw)
    pool = CandidatePool(
        pool_id=raw["pool_id"],
        decision_cycle=raw["decision_cycle"],
        horizon_cycles=raw["horizon_cycles"],
        candidate_ids=tuple(raw["candidate_ids"]),
        snapshots=snapshots,
        future_truth=future_truth,
        seed=raw["seed"],
        selection_metadata=raw.get("selection_metadata", {}),
    )
    return str(classification), pool, mission


def _bits(indices: list[int], n: int) -> tuple[int, ...]:
    selected = set(indices)
    return tuple(1 if index in selected else 0 for index in range(n))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.shots < 1:
        parser.error("--shots must be positive")
    if args.reps < 1:
        parser.error("--reps must be positive")
    if args.max_evaluations < 2:
        parser.error("--max-evaluations must be at least 2")
    try:
        classification, pool, mission = _load_pool(Path(args.input), args.pool_id)
        instance = build_optimization_instance(
            pool,
            mission=mission,
            objective_mode=args.objective_mode,
        )
        exact = exact_enumeration(instance, future_truth=pool.future_truth)
        exact_bits = [_bits(indices, instance.n) for indices in exact.metadata["tied_optima"]]
        result = run_qaoa(
            instance,
            shots=args.shots,
            reps=args.reps,
            optimizer_mode=args.optimizer,
            max_evaluations=args.max_evaluations,
            exact_optimal_bitstrings=exact_bits,
            future_truth=pool.future_truth,
            simulator_seed=args.simulator_seed,
        )
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(2, f"run_qaoa_demo: error: {error}\n")

    selected = result.best_feasible_sample
    report: dict[str, Any] = {
        "data_classification": classification,
        "pool_id": pool.pool_id,
        "objective_mode": args.objective_mode,
        "candidate_count": instance.n,
        "pack_size": instance.pack_size_k,
        "backend": result.backend,
        "shots_requested": result.shots_requested,
        "shots_observed": result.shots_observed,
        "feasible": result.feasible,
        "status_message": result.status_message,
        "params": result.params.to_dict(),
        "expected_energy": result.expected_energy,
        "feasible_probability_mass": result.feasible_probability_mass,
        "optimum_probability_mass": result.optimum_probability_mass,
        "best_feasible_optimality_gap": result.best_feasible_optimality_gap,
        "best_feasible_sample": selected.to_dict() if selected else None,
        "modal_sample": result.modal_sample.to_dict() if result.modal_sample else None,
        "observed_pack_divergence": (
            result.recommended_result.observed_pack_divergence
            if result.recommended_result
            else None
        ),
        "exact_observed_pack_divergence": exact.observed_pack_divergence,
        "optimizer": result.optimizer,
        "circuit": result.circuit,
        "penalty": result.penalty,
        "timings_ms": result.timings_ms,
        "backend_jobs_submitted": result.backend_jobs_submitted,
        "single_backend_job": result.single_backend_job,
    }
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result.feasible else 1


if __name__ == "__main__":
    raise SystemExit(main())
