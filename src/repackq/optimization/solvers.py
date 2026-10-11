"""Shared-schema deterministic and stochastic classical subset solvers."""

from __future__ import annotations

import itertools
import math
import random
import time
from dataclasses import asdict, dataclass, field
from statistics import pstdev
from typing import Any, Sequence

from repackq.models import FutureTruth
from repackq.optimization.objective import (
    OptimizationInstance,
    build_qubo,
)
from repackq.prediction.metrics import evaluate_pack_metrics


@dataclass
class OptimizationResult:
    """Common result record consumed by reports, benchmarks, and the UI."""

    algorithm: str
    selected_indices: list[int]
    selected_cell_ids: list[str]
    feasible: bool
    objective_value: float
    current_capacity_spread_ah: float
    current_capacity_cv: float | None
    resistance_spread_ohm: float | None
    usable_pack_capacity_ah: float
    predicted_pack_divergence: float | None
    observed_pack_divergence: float | None
    observed_usable_capacity_ah: float | None
    runtime_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _make_result(
    instance: OptimizationInstance,
    selected_indices: Sequence[int],
    *,
    algorithm: str,
    runtime_ms: float,
    future_truth: Sequence[FutureTruth] | None = None,
    metadata: dict[str, Any] | None = None,
) -> OptimizationResult:
    selected = tuple(sorted(instance.validate_indices(selected_indices)))
    if not selected:
        raise ValueError("solver result must select at least one candidate")
    feasible = len(selected) == instance.pack_size_k
    snapshots = [instance.snapshots[index] for index in selected]
    truth_by_id = None
    if future_truth is not None:
        truth_by_id = {item.cell_id: item for item in future_truth}
        if len(truth_by_id) != len(future_truth):
            raise ValueError("future truth contains duplicate cell IDs")
        missing = {item.cell_id for item in snapshots} - truth_by_id.keys()
        if missing:
            raise ValueError(f"future truth is missing selected cells: {sorted(missing)}")
        selected_truth = [truth_by_id[item.cell_id] for item in snapshots]
    else:
        selected_truth = None
    metrics = evaluate_pack_metrics(snapshots, selected_truth)
    breakdown = instance.breakdown_for_indices(selected)
    result_metadata = {
        "pool_id": instance.pool_id,
        "objective_mode": instance.objective_mode,
        "objective_breakdown": breakdown.to_dict(),
        "source_dataset": sorted({item.source_dataset for item in snapshots}),
    }
    if metadata:
        result_metadata.update(metadata)
    return OptimizationResult(
        algorithm=algorithm,
        selected_indices=list(selected),
        selected_cell_ids=[instance.candidate_ids[index] for index in selected],
        feasible=feasible,
        objective_value=breakdown.total,
        current_capacity_spread_ah=metrics.current_capacity_spread_ah,
        current_capacity_cv=metrics.current_capacity_cv,
        resistance_spread_ohm=metrics.resistance_spread_ohm,
        usable_pack_capacity_ah=metrics.usable_pack_capacity_ah,
        predicted_pack_divergence=metrics.predicted_pack_divergence,
        observed_pack_divergence=metrics.observed_pack_divergence,
        observed_usable_capacity_ah=metrics.observed_usable_capacity_ah,
        runtime_ms=max(0.0, runtime_ms),
        metadata=result_metadata,
    )


def soh_sort(
    instance: OptimizationInstance,
    *,
    future_truth: Sequence[FutureTruth] | None = None,
) -> OptimizationResult:
    """Pick the healthiest cells, using the required stable tie breaks."""

    started = time.perf_counter()
    order = sorted(
        range(instance.n),
        key=lambda index: (
            -instance.snapshots[index].soh,
            -instance.snapshots[index].capacity_ah,
            instance.candidate_ids[index],
        ),
    )
    selected = order[: instance.pack_size_k]
    return _make_result(
        instance,
        selected,
        algorithm="soh_sort",
        runtime_ms=(time.perf_counter() - started) * 1000.0,
        future_truth=future_truth,
        metadata={"tie_breaks": ["descending_soh", "descending_capacity", "cell_id"]},
    )


def compatibility_greedy(
    instance: OptimizationInstance,
    *,
    future_truth: Sequence[FutureTruth] | None = None,
) -> OptimizationResult:
    """Try each seed, growing the group by minimum physical-objective cost."""

    started = time.perf_counter()
    best_indices: tuple[int, ...] | None = None
    best_value = math.inf
    for seed in range(instance.n):
        selected = [seed]
        remaining = set(range(instance.n)) - {seed}
        while len(selected) < instance.pack_size_k:
            next_index = min(
                remaining,
                key=lambda index: (
                    instance.objective_for_indices((*selected, index)),
                    instance.candidate_ids[index],
                ),
            )
            selected.append(next_index)
            remaining.remove(next_index)
        candidate = tuple(sorted(selected))
        value = instance.objective_for_indices(candidate)
        if (
            value < best_value - 1e-12
            or (
                abs(value - best_value) <= 1e-12
                and (best_indices is None or candidate < best_indices)
            )
        ):
            best_indices = candidate
            best_value = value
    assert best_indices is not None
    return _make_result(
        instance,
        best_indices,
        algorithm="compatibility_greedy",
        runtime_ms=(time.perf_counter() - started) * 1000.0,
        future_truth=future_truth,
        metadata={"starting_seeds_evaluated": instance.n},
    )


def _swap_neighbor(
    selected: set[int],
    n: int,
    rng: random.Random,
) -> set[int]:
    """Return a one-out/one-in neighbor while preserving exact cardinality."""

    unselected = [index for index in range(n) if index not in selected]
    if not selected or not unselected:
        return set(selected)
    neighbor = set(selected)
    neighbor.remove(rng.choice(tuple(sorted(selected))))
    neighbor.add(rng.choice(unselected))
    return neighbor


def simulated_annealing(
    instance: OptimizationInstance,
    *,
    seed: int = 0,
    steps: int = 3000,
    future_truth: Sequence[FutureTruth] | None = None,
    record_cardinality_trace: bool = False,
) -> OptimizationResult:
    """Seeded fixed-cardinality swap annealing, returning the best state seen."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise ValueError("steps must be a positive integer")
    started = time.perf_counter()
    rng = random.Random(seed)
    current = set(rng.sample(range(instance.n), instance.pack_size_k))
    current_value = instance.objective_for_indices(tuple(sorted(current)))
    best = set(current)
    best_value = current_value
    pair_costs = [
        sum(matrix[left][right] for matrix in instance.pairwise_components.values())
        for left in range(instance.n)
        for right in range(left + 1, instance.n)
    ]
    pair_scale = pstdev(pair_costs) if pair_costs else 0.0
    t_start = max(1.0, pair_scale or 1.0)
    t_end = 1e-3
    cardinality_trace = [len(current)] if record_cardinality_trace else None

    for step in range(steps):
        candidate = _swap_neighbor(current, instance.n, rng)
        if cardinality_trace is not None:
            cardinality_trace.append(len(candidate))
        candidate_value = instance.objective_for_indices(tuple(sorted(candidate)))
        delta = candidate_value - current_value
        fraction = step / max(steps - 1, 1)
        temperature = t_start * (t_end / t_start) ** fraction
        if delta <= 0.0 or rng.random() < math.exp(-delta / temperature):
            current = candidate
            current_value = candidate_value
            if current_value < best_value - 1e-12:
                best = set(current)
                best_value = current_value

    details: dict[str, Any] = {"seed": seed, "steps": steps, "schedule": "geometric"}
    if cardinality_trace is not None:
        details["cardinality_trace"] = cardinality_trace
    return _make_result(
        instance,
        tuple(sorted(best)),
        algorithm="simulated_annealing",
        runtime_ms=(time.perf_counter() - started) * 1000.0,
        future_truth=future_truth,
        metadata=details,
    )


def exact_enumeration(
    instance: OptimizationInstance,
    *,
    future_truth: Sequence[FutureTruth] | None = None,
    penalty_multiplier: float = 4.0,
) -> OptimizationResult:
    """Enumerate all C(N,K) feasible packs and verify QUBO feasible ranking."""

    started = time.perf_counter()
    best_value = math.inf
    best_indices: tuple[int, ...] | None = None
    tied: list[tuple[int, ...]] = []
    tied_count = 0
    tied_limit = 1000
    evaluated = 0
    for indices in itertools.combinations(range(instance.n), instance.pack_size_k):
        evaluated += 1
        value = instance.objective_for_indices(indices)
        if value < best_value - 1e-12:
            best_value = value
            best_indices = indices
            tied = [indices]
            tied_count = 1
        elif abs(value - best_value) <= 1e-12:
            tied_count += 1
            if len(tied) < tied_limit:
                tied.append(indices)
            if best_indices is None or indices < best_indices:
                best_indices = indices
    if best_indices is None:
        raise ValueError("exact enumeration found no feasible subset")

    qubo = build_qubo(instance, penalty_multiplier=penalty_multiplier)
    feasible_energies = [
        (qubo.energy(_indices_to_bits(indices, instance.n)), indices)
        for indices in itertools.combinations(range(instance.n), instance.pack_size_k)
    ]
    qubo_best_energy = min(value for value, _ in feasible_energies)
    selected_qubo_energy = qubo.energy(_indices_to_bits(best_indices, instance.n))
    if abs(selected_qubo_energy - qubo_best_energy) > 1e-9:
        raise AssertionError("exact physical optimum disagrees with feasible penalized QUBO ranking")

    return _make_result(
        instance,
        best_indices,
        algorithm="exact_enumeration",
        runtime_ms=(time.perf_counter() - started) * 1000.0,
        future_truth=future_truth,
        metadata={
            "evaluated_subsets": evaluated,
            "tied_optima": [list(indices) for indices in tied],
            "tied_optima_count": tied_count,
            "tied_optima_truncated": tied_count > tied_limit,
            "qubo_penalty": qubo.cardinality_penalty,
            "penalty_calibration_doublings": qubo.calibration_doublings,
            "qubo_global_minimum_feasible": True,
            "feasible_qubo_optimum_energy": qubo_best_energy,
        },
    )


def _indices_to_bits(indices: Sequence[int], n: int) -> tuple[int, ...]:
    selected = set(indices)
    return tuple(1 if index in selected else 0 for index in range(n))
