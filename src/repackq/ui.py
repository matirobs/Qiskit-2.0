"""Task 7 callable API for the RePack-Q browser application.

The checked-in UI demo uses the explicitly synthetic fixture. Decision-time
functions see only observations through the cutoff; held-out fixture values are
loaded only by :func:`reveal_future` after the user requests a reveal.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Sequence

from repackq.config import PV_TOU_MISSION, get_mission_profile
from repackq.models import CandidatePool, CellObservation, CellSnapshot, FutureTruth
from repackq.optimization.objective import build_optimization_instance
from repackq.optimization.solvers import (
    _make_result,
    compatibility_greedy,
    exact_enumeration,
    simulated_annealing,
    soh_sort,
)
from repackq.prediction.metrics import evaluate_pack_metrics
from repackq.prediction.split import future_tolerance_for_horizon, lookup_future_truth
from repackq.prediction.trajectory import build_snapshot
from repackq.quantum.engine import QAOAPreparation, complete_qaoa, prepare_qaoa, run_qaoa
from repackq.quantum.qiskit_compat import transpile_for_backend
from repackq.data.serialization import trajectories_from_dict


_DECISION_CYCLE = 76
_DEFAULT_HORIZON = 200
_SUPPORTED_HORIZONS = (100, 150, 200)
_SUPPORTED_PACK_SIZES = (3, 4, 5)
_DEFAULT_SEED = 20261010
_QAOA_PENDING: dict[str, tuple[QAOAPreparation, CandidatePool, Any]] = {}


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "fixtures" / "synthetic_demo.json").is_file():
            return parent
    raise FileNotFoundError("could not locate data/fixtures/synthetic_demo.json")


def _load_fixture() -> tuple[dict[str, Any], list[Any]]:
    fixture_path = _project_root() / "data" / "fixtures" / "synthetic_demo.json"
    with fixture_path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if payload.get("data_classification") != "synthetic-fixture":
        raise ValueError("Task 7 interactive demo must use a clearly synthetic fixture")
    return payload, trajectories_from_dict(payload)


def _validate_problem(horizon_cycles: int, pack_size_k: int) -> None:
    if horizon_cycles not in _SUPPORTED_HORIZONS:
        raise ValueError(f"horizon must be one of {_SUPPORTED_HORIZONS}")
    if pack_size_k not in _SUPPORTED_PACK_SIZES:
        raise ValueError(f"pack size must be one of {_SUPPORTED_PACK_SIZES}")


def _decision_data(horizon_cycles: int, pack_size_k: int) -> tuple[CandidatePool, list[list[dict[str, Any]]]]:
    _validate_problem(horizon_cycles, pack_size_k)
    _, trajectories = _load_fixture()
    snapshots: list[CellSnapshot] = []
    histories: list[list[dict[str, Any]]] = []
    for trajectory in sorted(trajectories, key=lambda item: item.cell_id):
        history = trajectory.history_through(_DECISION_CYCLE)
        snapshot = build_snapshot(
            history,
            decision_cycle=_DECISION_CYCLE,
            horizon_cycles=horizon_cycles,
            nominal_capacity_ah=trajectory.nominal_capacity_ah,
        )
        if snapshot.soh >= PV_TOU_MISSION.minimum_soh:
            snapshots.append(snapshot)
            histories.append([item.to_dict() for item in history])
    if not snapshots:
        raise ValueError("the synthetic demo fixture has no eligible candidates")
    pool = CandidatePool(
        pool_id=f"synthetic-ui-cycle-{_DECISION_CYCLE}-h{horizon_cycles}",
        decision_cycle=_DECISION_CYCLE,
        horizon_cycles=horizon_cycles,
        candidate_ids=tuple(item.cell_id for item in snapshots),
        snapshots=tuple(snapshots),
        future_truth=None,
        seed=_DEFAULT_SEED,
        selection_metadata={"data_classification": "synthetic-fixture"},
    )
    return pool, histories


def get_demo_state(
    *,
    horizon_cycles: int = _DEFAULT_HORIZON,
    pack_size_k: int = 4,
) -> dict[str, Any]:
    """Return candidate data at recommissioning time, with no future values."""

    pool, histories = _decision_data(horizon_cycles, pack_size_k)
    return {
        "schema_version": "1.0",
        "pool_id": pool.pool_id,
        "decision_cycle": pool.decision_cycle,
        "horizon_cycles": pool.horizon_cycles,
        "candidate_ids": list(pool.candidate_ids),
        "snapshots": [item.to_dict() for item in pool.snapshots],
        "histories": histories,
        "data_classification": "synthetic-fixture",
        "source_dataset": "synthetic_fixture",
        "pack_size_k": pack_size_k,
        "supported_horizons": list(_SUPPORTED_HORIZONS),
        "supported_pack_sizes": list(_SUPPORTED_PACK_SIZES),
        "future_available": True,
        "future_disclosed": False,
        "mission": replace(
            PV_TOU_MISSION,
            horizon_cycles=horizon_cycles,
            pack_size_k=pack_size_k,
        ).to_dict(),
        "fixture_note": (
            "All records are hand-authored synthetic UI examples. The forecast uses "
            "only cycles through 76; later fixture values are withheld until reveal."
        ),
    }


def _problem(
    *,
    horizon_cycles: int,
    pack_size_k: int,
    objective_mode: str,
) -> tuple[CandidatePool, Any]:
    if objective_mode not in {"current_only", "trajectory_aware"}:
        raise ValueError("objective_mode must be current_only or trajectory_aware")
    pool, _ = _decision_data(horizon_cycles, pack_size_k)
    mission = replace(
        get_mission_profile("pv_tou"),
        horizon_cycles=horizon_cycles,
        pack_size_k=pack_size_k,
    )
    instance = build_optimization_instance(pool, mission=mission, objective_mode=objective_mode)
    return pool, instance


def evaluate_selection(
    selected_indices: Sequence[int],
    *,
    horizon_cycles: int = _DEFAULT_HORIZON,
    pack_size_k: int = 4,
    objective_mode: str = "trajectory_aware",
) -> dict[str, Any]:
    """Evaluate a manually assembled pack using present and predicted data only."""

    _, instance = _problem(
        horizon_cycles=horizon_cycles,
        pack_size_k=pack_size_k,
        objective_mode=objective_mode,
    )
    selected = instance.validate_indices(selected_indices)
    if len(selected) != pack_size_k:
        raise ValueError(f"manual pack must contain exactly K={pack_size_k} unique cells")
    return _make_result(
        instance,
        selected,
        algorithm="manual_pack",
        runtime_ms=0.0,
    ).to_dict()


def run_classical_comparison(
    *,
    horizon_cycles: int = _DEFAULT_HORIZON,
    pack_size_k: int = 4,
    objective_mode: str = "trajectory_aware",
    annealing_seed: int = _DEFAULT_SEED,
    annealing_steps: int = 3000,
) -> dict[str, Any]:
    """Run all classical methods and exact enumeration without held-out truth."""

    pool, instance = _problem(
        horizon_cycles=horizon_cycles,
        pack_size_k=pack_size_k,
        objective_mode=objective_mode,
    )
    results = [
        soh_sort(instance),
        compatibility_greedy(instance),
        simulated_annealing(
            instance,
            seed=annealing_seed,
            steps=annealing_steps,
        ),
        exact_enumeration(instance),
    ]
    return {
        "pool_id": pool.pool_id,
        "objective_mode": objective_mode,
        "data_classification": "synthetic-fixture",
        "future_disclosed": False,
        "exact_algorithm": "exact_enumeration",
        "results": {item.algorithm: item.to_dict() for item in results},
    }


def run_live_qaoa(
    *,
    horizon_cycles: int = _DEFAULT_HORIZON,
    pack_size_k: int = 4,
    objective_mode: str = "trajectory_aware",
    shots: int = 1024,
    reps: int = 1,
    optimizer_mode: str = "auto",
    max_evaluations: int = 160,
    backend: Any | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the project QAOA engine and forward truthful stage transitions."""

    pool, instance = _problem(
        horizon_cycles=horizon_cycles,
        pack_size_k=pack_size_k,
        objective_mode=objective_mode,
    )
    exact = exact_enumeration(instance)
    exact_vectors = [
        tuple(1 if bit_index in selected else 0 for bit_index in range(instance.n))
        for selected in exact.metadata["tied_optima"]
    ]
    result = run_qaoa(
        instance,
        backend,
        shots=shots,
        reps=reps,
        optimizer_mode=optimizer_mode,
        max_evaluations=max_evaluations,
        exact_optimal_bitstrings=exact_vectors,
        simulator_seed=_DEFAULT_SEED if backend is None else None,
        on_stage=on_stage,
    ).to_dict()
    result["data_classification"] = "synthetic-fixture"
    result["pool_id"] = pool.pool_id
    result["exact_result"] = exact.to_dict()
    return result


def prepare_live_qaoa_circuit(
    *,
    backend: Any,
    horizon_cycles: int = _DEFAULT_HORIZON,
    pack_size_k: int = 4,
    objective_mode: str = "trajectory_aware",
    shots: int = 1024,
    reps: int = 1,
    optimizer_mode: str = "grid",
    max_evaluations: int = 121,
) -> Any:
    """Optimize locally and compile one measured circuit for the selected backend."""

    if backend is None or not callable(getattr(backend, "run", None)):
        raise TypeError("selected backend must provide run(circuit, shots=...)")

    pool, instance = _problem(
        horizon_cycles=horizon_cycles,
        pack_size_k=pack_size_k,
        objective_mode=objective_mode,
    )
    exact = exact_enumeration(instance)
    exact_vectors = [
        tuple(1 if bit_index in selected else 0 for bit_index in range(instance.n))
        for selected in exact.metadata["tied_optima"]
    ]
    preparation = prepare_qaoa(
        instance,
        shots=shots,
        reps=reps,
        optimizer_mode=optimizer_mode,
        max_evaluations=max_evaluations,
        exact_optimal_bitstrings=exact_vectors,
    )
    transpilation_started = time.perf_counter()
    transpiled = transpile_for_backend(
        preparation.circuit,
        backend,
        seed=_DEFAULT_SEED,
    )
    preparation.circuit_info["transpiled_depth"] = transpiled.depth()
    preparation.circuit_info["transpiled_qubits"] = transpiled.num_qubits
    preparation.circuit_info["transpiled_size"] = transpiled.size()
    preparation.timings_ms["transpilation_ms"] = (
        time.perf_counter() - transpilation_started
    ) * 1000.0
    # Keep the backend-specific compiled circuit for Qollab's single sampling
    # call. It retains the original classical register used to decode counts.
    preparation.circuit = transpiled
    run_id = uuid.uuid4().hex
    preparation.circuit.name = f"repackq_qaoa_{run_id}"
    _QAOA_PENDING[run_id] = (preparation, pool, exact)
    return preparation.circuit


def complete_live_qaoa_circuit(
    circuit_name: str,
    counts: dict[str, int],
    backend_name: str,
    backend_sampling_ms: float,
) -> dict[str, Any]:
    """Analyze Qollab JavaScript-submitted counts for a prepared circuit."""

    prefix = "repackq_qaoa_"
    if not str(circuit_name).startswith(prefix):
        raise ValueError("QAOA circuit identifier is invalid")
    run_id = str(circuit_name)[len(prefix):]
    pending = _QAOA_PENDING.pop(run_id, None)
    if pending is None:
        raise ValueError("QAOA preparation expired or was already finalized")
    preparation, pool, exact = pending
    result = complete_qaoa(
        preparation,
        counts,
        str(backend_name),
        backend_sampling_ms=float(backend_sampling_ms),
    ).to_dict()
    result["data_classification"] = "synthetic-fixture"
    result["pool_id"] = pool.pool_id
    result["exact_result"] = exact.to_dict()
    return result


def discard_live_qaoa_circuit(circuit_name: str) -> bool:
    """Release local preparation state when Qollab sampling fails."""

    prefix = "repackq_qaoa_"
    if not str(circuit_name).startswith(prefix):
        return False
    return _QAOA_PENDING.pop(str(circuit_name)[len(prefix):], None) is not None


def _synthetic_future_observations(
    trajectory: Any,
    *,
    target_cycle: int,
    horizon_cycles: int,
) -> tuple[list[dict[str, Any]], FutureTruth]:
    """Make visibly synthetic held-out points by extending the fixture trend.

    The source fixture stops at cycle 201. Longer UI horizons use linear
    extrapolation from its final two points. This is only an interaction demo,
    not a claim about measured battery data.
    """

    after_cutoff = list(trajectory.future_after(_DECISION_CYCLE))
    match = lookup_future_truth(
        after_cutoff,
        decision_cycle=_DECISION_CYCLE,
        target_cycle=target_cycle,
        max_future_cycle_error=future_tolerance_for_horizon(horizon_cycles),
    )
    if match is not None:
        return [item.to_dict() for item in after_cutoff], match
    valid = [
        item for item in after_cutoff
        if item.capacity_ah is not None and item.capacity_ah > 0
    ]
    if len(valid) < 2:
        raise ValueError(f"synthetic fixture has no future trend for {trajectory.cell_id}")
    left, right = valid[-2:]
    assert left.capacity_ah is not None and right.capacity_ah is not None
    slope = (right.capacity_ah - left.capacity_ah) / (right.cycle_index - left.cycle_index)
    capacity = max(0.0, right.capacity_ah + slope * (target_cycle - right.cycle_index))
    point = CellObservation(
        cell_id=trajectory.cell_id,
        protocol_id=trajectory.protocol_id,
        phase="second_life",
        cycle_index=target_cycle,
        timestamp_s=None,
        capacity_ah=capacity,
        internal_resistance_ohm=None,
        temperature_c=None,
        voltage_v=None,
        current_a=None,
        source_dataset="synthetic_fixture_extrapolation",
    )
    after_cutoff.append(point)
    after_cutoff.sort(key=lambda item: item.cycle_index)
    truth = FutureTruth(
        cell_id=trajectory.cell_id,
        target_cycle_index=target_cycle,
        actual_capacity_ah=capacity,
        actual_internal_resistance_ohm=None,
        nearest_cycle_distance=0,
    )
    return [item.to_dict() for item in after_cutoff], truth


def reveal_future(
    selected_indices: Sequence[int],
    *,
    horizon_cycles: int = _DEFAULT_HORIZON,
    pack_size_k: int = 4,
) -> dict[str, Any]:
    """Return held-out fixture trajectories only after an explicit reveal call."""

    pool, _ = _decision_data(horizon_cycles, pack_size_k)
    selected = tuple(selected_indices)
    if len(selected) != pack_size_k or len(set(selected)) != len(selected):
        raise ValueError(f"future reveal requires exactly K={pack_size_k} unique cell indices")
    if any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(pool.snapshots) for index in selected):
        raise ValueError("future reveal contains an invalid candidate index")
    _, trajectories = _load_fixture()
    by_id = {item.cell_id: item for item in trajectories}
    target = _DECISION_CYCLE + horizon_cycles
    observations: list[dict[str, Any]] = []
    truths: list[FutureTruth] = []
    selected_ids = [pool.candidate_ids[index] for index in selected]
    for cell_id in selected_ids:
        trajectory_observations, truth = _synthetic_future_observations(
            by_id[cell_id],
            target_cycle=target,
            horizon_cycles=horizon_cycles,
        )
        observations.extend(trajectory_observations)
        truths.append(truth)
    snapshots = [pool.snapshots[index] for index in selected]
    metrics = evaluate_pack_metrics(snapshots, truths)
    return {
        "pool_id": pool.pool_id,
        "data_classification": "synthetic-fixture",
        "label": "Synthetic held-out fixture reveal",
        "decision_cycle": _DECISION_CYCLE,
        "target_cycle": target,
        "selected_cell_ids": selected_ids,
        "truth": [item.to_dict() for item in truths],
        "observations": observations,
        "metrics": metrics.to_dict(),
        "future_disclosed": True,
        "extrapolation_note": (
            "Where the hand-authored fixture has no point near the target, a synthetic "
            "future value is linearly extrapolated from its final two fixture points."
        ),
    }


__all__ = [
    "evaluate_selection",
    "get_demo_state",
    "reveal_future",
    "run_classical_comparison",
    "run_live_qaoa",
]
