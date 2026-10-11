"""Seeded, eligibility-filtered retrospective candidate-pool generation."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from typing import Sequence

from repackq.config import PV_TOU_MISSION
from repackq.models import CandidatePool, CellSnapshot, CellTrajectory, FutureTruth, MissionProfile
from repackq.prediction.split import (
    future_tolerance_for_horizon,
    lookup_future_truth,
    split_history_future,
)
from repackq.prediction.trajectory import (
    DEFAULT_ESTIMATOR_CONFIG,
    EstimatorConfig,
    build_snapshot,
)


DEFAULT_MIN_SOH_RANGE = 0.02
DEFAULT_POOL_ATTEMPTS = 512


def _validate_pool_sizes(n: int, k: int) -> None:
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("N must be a positive integer")
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("K must be a positive integer")
    if k > n:
        raise ValueError("K cannot exceed N")


def _sample_stratified(
    candidates: Sequence[tuple[CellSnapshot, FutureTruth | None]],
    n: int,
    rng: random.Random,
) -> list[tuple[CellSnapshot, FutureTruth | None]]:
    strata: dict[str, list[tuple[CellSnapshot, FutureTruth | None]]] = defaultdict(list)
    for candidate in candidates:
        protocol = candidate[0].protocol_id or "<unknown>"
        strata[protocol].append(candidate)
    protocol_ids = sorted(strata)
    rng.shuffle(protocol_ids)
    for values in strata.values():
        values.sort(key=lambda entry: entry[0].cell_id)
        rng.shuffle(values)

    selected: list[tuple[CellSnapshot, FutureTruth | None]] = []
    cursor = 0
    while len(selected) < n:
        progressed = False
        for offset in range(len(protocol_ids)):
            protocol = protocol_ids[(cursor + offset) % len(protocol_ids)]
            if strata[protocol]:
                selected.append(strata[protocol].pop())
                progressed = True
                if len(selected) == n:
                    break
        if not progressed:
            break
        cursor = (cursor + 1) % len(protocol_ids)
    return selected


def generate_candidate_pool(
    trajectories: Sequence[CellTrajectory],
    *,
    decision_cycle: int,
    seed: int,
    n: int = 8,
    k: int | None = None,
    mission: MissionProfile = PV_TOU_MISSION,
    horizon_cycles: int | None = None,
    include_future_truth: bool = True,
    stratify_protocol: bool = False,
    minimum_soh_range: float = DEFAULT_MIN_SOH_RANGE,
    estimator_config: EstimatorConfig = DEFAULT_ESTIMATOR_CONFIG,
    max_pool_attempts: int = DEFAULT_POOL_ATTEMPTS,
) -> CandidatePool:
    """Create one reproducible N-candidate pool and its separate future truth.

    Eligibility can depend on whether a valid held-out observation exists, but
    the measured future value is never used to construct or sample snapshots.
    Sampling heterogeneity is checked only on recommissioning-time SOH.
    """

    if isinstance(decision_cycle, bool) or not isinstance(decision_cycle, int) or decision_cycle < 0:
        raise ValueError("decision_cycle must be a nonnegative integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    horizon = mission.horizon_cycles if horizon_cycles is None else horizon_cycles
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("horizon_cycles must be a positive integer")
    pack_size = mission.pack_size_k if k is None else k
    _validate_pool_sizes(n, pack_size)
    if not math.isfinite(minimum_soh_range) or minimum_soh_range < 0:
        raise ValueError("minimum_soh_range must be finite and nonnegative")
    if isinstance(max_pool_attempts, bool) or not isinstance(max_pool_attempts, int) or max_pool_attempts <= 0:
        raise ValueError("max_pool_attempts must be a positive integer")
    if not trajectories:
        raise ValueError("cannot generate a candidate pool from an empty dataset")

    datasets = {item.observations[0].source_dataset for item in trajectories if item.observations}
    if len(datasets) > 1:
        raise ValueError("a candidate pool must use trajectories from one source dataset")
    nominal_capacities = {item.nominal_capacity_ah for item in trajectories}
    if len(nominal_capacities) > 1:
        raise ValueError("a candidate pool must use one nominal capacity convention")

    tolerance = future_tolerance_for_horizon(horizon)
    target_cycle = decision_cycle + horizon
    eligible: list[tuple[CellSnapshot, FutureTruth | None]] = []
    excluded = {
        "insufficient_history_or_missing_current": 0,
        "below_minimum_soh": 0,
        "missing_weighted_resistance": 0,
        "missing_weighted_temperature": 0,
        "no_future_truth_within_tolerance": 0,
    }
    for trajectory in sorted(trajectories, key=lambda item: item.cell_id):
        split = split_history_future(trajectory, decision_cycle)
        try:
            snapshot = build_snapshot(
                split.history,
                decision_cycle=decision_cycle,
                horizon_cycles=horizon,
                nominal_capacity_ah=trajectory.nominal_capacity_ah,
                config=estimator_config,
            )
        except ValueError:
            excluded["insufficient_history_or_missing_current"] += 1
            continue
        if snapshot.soh < mission.minimum_soh:
            excluded["below_minimum_soh"] += 1
            continue
        if mission.resistance_weight > 0 and snapshot.internal_resistance_ohm is None:
            excluded["missing_weighted_resistance"] += 1
            continue
        if mission.temperature_weight > 0 and snapshot.temperature_c is None:
            excluded["missing_weighted_temperature"] += 1
            continue
        truth: FutureTruth | None = None
        if include_future_truth:
            truth = lookup_future_truth(
                split.future,
                decision_cycle=decision_cycle,
                target_cycle=target_cycle,
                max_future_cycle_error=tolerance,
            )
            if truth is None:
                excluded["no_future_truth_within_tolerance"] += 1
                continue
        eligible.append((snapshot, truth))

    if len(eligible) < n:
        raise ValueError(
            f"only {len(eligible)} cells are eligible for N={n} at cycle {decision_cycle}; "
            f"eligibility exclusions: {excluded}"
        )
    global_soh_range = max(item[0].soh for item in eligible) - min(item[0].soh for item in eligible)
    if global_soh_range < minimum_soh_range:
        raise ValueError(
            f"eligible pool SOH range {global_soh_range:.6g} is below the required "
            f"minimum heterogeneity {minimum_soh_range:.6g}"
        )

    rng = random.Random(seed)
    selected: list[tuple[CellSnapshot, FutureTruth | None]] | None = None
    selected_soh_range = 0.0
    accepted_attempt = 0
    for attempt in range(1, max_pool_attempts + 1):
        if stratify_protocol:
            trial = _sample_stratified(eligible, n, rng)
        else:
            trial = rng.sample(eligible, n)
        soh_values = [entry[0].soh for entry in trial]
        trial_range = max(soh_values) - min(soh_values)
        if trial_range >= minimum_soh_range:
            selected = trial
            selected_soh_range = trial_range
            accepted_attempt = attempt
            break
    if selected is None:
        raise ValueError(
            f"no seeded sample met minimum SOH range {minimum_soh_range:.6g} "
            f"after {max_pool_attempts} attempts; lower the threshold or use a different seed"
        )

    selected.sort(key=lambda entry: entry[0].cell_id)
    snapshots = tuple(entry[0] for entry in selected)
    truths = tuple(entry[1] for entry in selected) if include_future_truth else None
    if truths is not None and any(item is None for item in truths):
        raise AssertionError("retrospective candidate unexpectedly lacks held-out truth")
    future_truth = None if truths is None else tuple(item for item in truths if item is not None)
    candidate_ids = tuple(item.cell_id for item in snapshots)
    identity = {
        "source_dataset": next(iter(datasets), None),
        "mission": mission.to_dict(),
        "decision_cycle": decision_cycle,
        "horizon_cycles": horizon,
        "n": n,
        "k": pack_size,
        "seed": seed,
        "candidate_ids": candidate_ids,
        "snapshot_features": [item.to_dict() for item in snapshots],
        "stratify_protocol": stratify_protocol,
        "minimum_soh_range": minimum_soh_range,
        "include_future_truth": include_future_truth,
    }
    encoded_identity = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    pool_id = "pool-" + hashlib.sha256(encoded_identity.encode("utf-8")).hexdigest()[:16]
    return CandidatePool(
        pool_id=pool_id,
        decision_cycle=decision_cycle,
        horizon_cycles=horizon,
        candidate_ids=candidate_ids,
        snapshots=snapshots,
        future_truth=future_truth,
        seed=seed,
        selection_metadata={
            "mission_id": mission.id,
            "n": n,
            "k": pack_size,
            "eligible_cell_count": len(eligible),
            "eligibility_exclusions": excluded,
            "future_tolerance_cycles": tolerance if include_future_truth else None,
            "minimum_soh_range": minimum_soh_range,
            "selected_soh_range": selected_soh_range,
            "protocol_stratified": stratify_protocol,
            "accepted_sampling_attempt": accepted_attempt,
            "sampling_basis": "decision-time SOH only; held-out values are not inspected",
        },
    )
