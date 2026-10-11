"""Held-out evaluation of the simple capacity trajectory predictor."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Sequence

from repackq.models import CellTrajectory
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


@dataclass(frozen=True)
class PredictionEvaluation:
    horizon_cycles: int
    max_future_cycle_error: int
    trajectory_count: int
    predictable_decision_points: int
    valid_held_out_forecasts: int
    future_truth_coverage: float
    mae_ah: float | None
    rmse_ah: float | None
    median_absolute_percentage_error: float | None
    evaluation_unit: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_predictor(
    trajectories: Sequence[CellTrajectory],
    *,
    horizon_cycles: int = 200,
    estimator_config: EstimatorConfig = DEFAULT_ESTIMATOR_CONFIG,
    max_future_cycle_error: int | None = None,
) -> PredictionEvaluation:
    """Measure horizon prediction errors over every valid decision cutoff.

    Every forecast is built before the corresponding future tuple is queried.
    A decision point counts as predictable only when it has enough history and
    a valid capacity reading exactly at t0. Coverage then measures how often a
    future diagnostic falls within tolerance. Repeated cutoffs from one cell
    are overlapping forecasts and are reported as such in ``evaluation_unit``.
    """

    if isinstance(horizon_cycles, bool) or not isinstance(horizon_cycles, int) or horizon_cycles <= 0:
        raise ValueError("horizon_cycles must be a positive integer")
    tolerance = (
        future_tolerance_for_horizon(horizon_cycles)
        if max_future_cycle_error is None
        else max_future_cycle_error
    )
    if isinstance(tolerance, bool) or not isinstance(tolerance, int) or tolerance < 0:
        raise ValueError("max_future_cycle_error must be a nonnegative integer")

    absolute_errors: list[float] = []
    squared_errors: list[float] = []
    percentage_errors: list[float] = []
    predictable = 0
    for trajectory in sorted(trajectories, key=lambda item: item.cell_id):
        for decision_cycle in sorted({item.cycle_index for item in trajectory.observations}):
            split = split_history_future(trajectory, decision_cycle)
            try:
                snapshot = build_snapshot(
                    split.history,
                    decision_cycle=decision_cycle,
                    horizon_cycles=horizon_cycles,
                    nominal_capacity_ah=trajectory.nominal_capacity_ah,
                    config=estimator_config,
                )
            except ValueError:
                continue
            predictable += 1
            truth = lookup_future_truth(
                split.future,
                decision_cycle=decision_cycle,
                target_cycle=decision_cycle + horizon_cycles,
                max_future_cycle_error=tolerance,
            )
            if truth is None:
                continue
            error = snapshot.predicted_capacity_ah - truth.actual_capacity_ah
            absolute = abs(error)
            absolute_errors.append(absolute)
            squared_errors.append(error * error)
            if truth.actual_capacity_ah > 0:
                percentage_errors.append(absolute / truth.actual_capacity_ah * 100.0)

    valid_count = len(absolute_errors)
    median_absolute_percentage_error: float | None = None
    if percentage_errors:
        ordered_percentages = sorted(percentage_errors)
        middle = len(ordered_percentages) // 2
        if len(ordered_percentages) % 2:
            median_absolute_percentage_error = ordered_percentages[middle]
        else:
            median_absolute_percentage_error = (
                ordered_percentages[middle - 1] + ordered_percentages[middle]
            ) / 2.0
    return PredictionEvaluation(
        horizon_cycles=horizon_cycles,
        max_future_cycle_error=tolerance,
        trajectory_count=len(trajectories),
        predictable_decision_points=predictable,
        valid_held_out_forecasts=valid_count,
        future_truth_coverage=valid_count / predictable if predictable else 0.0,
        mae_ah=fmean(absolute_errors) if absolute_errors else None,
        rmse_ah=math.sqrt(fmean(squared_errors)) if squared_errors else None,
        median_absolute_percentage_error=median_absolute_percentage_error,
        evaluation_unit=(
            "cell-by-decision-cycle forecasts; cutoffs within each cell overlap"
        ),
    )


def select_decision_cycle(
    trajectories: Sequence[CellTrajectory],
    *,
    horizon_cycles: int,
    minimum_candidate_soh: float = 0.50,
    minimum_soh_range: float = 0.0,
    require_resistance: bool = False,
    require_temperature: bool = False,
    estimator_config: EstimatorConfig = DEFAULT_ESTIMATOR_CONFIG,
) -> tuple[int, int]:
    """Choose the earliest cutoff among those with maximum retrospective coverage."""

    if not trajectories:
        raise ValueError("cannot choose a decision cycle from an empty dataset")
    if not math.isfinite(minimum_candidate_soh) or not 0 <= minimum_candidate_soh <= 1:
        raise ValueError("minimum_candidate_soh must be between 0 and 1")
    if not math.isfinite(minimum_soh_range) or minimum_soh_range < 0:
        raise ValueError("minimum_soh_range must be finite and nonnegative")
    tolerance = future_tolerance_for_horizon(horizon_cycles)
    decision_cycles = sorted(
        {item.cycle_index for trajectory in trajectories for item in trajectory.observations}
    )
    coverage: list[tuple[int, int]] = []
    for decision_cycle in decision_cycles:
        eligible = 0
        eligible_soh: list[float] = []
        for trajectory in trajectories:
            split = split_history_future(trajectory, decision_cycle)
            try:
                snapshot = build_snapshot(
                    split.history,
                    decision_cycle=decision_cycle,
                    horizon_cycles=horizon_cycles,
                    nominal_capacity_ah=trajectory.nominal_capacity_ah,
                    config=estimator_config,
                )
            except ValueError:
                continue
            if snapshot.soh < minimum_candidate_soh:
                continue
            if require_resistance and snapshot.internal_resistance_ohm is None:
                continue
            if require_temperature and snapshot.temperature_c is None:
                continue
            truth = lookup_future_truth(
                split.future,
                decision_cycle=decision_cycle,
                target_cycle=decision_cycle + horizon_cycles,
                max_future_cycle_error=tolerance,
            )
            if truth is not None:
                eligible += 1
                eligible_soh.append(snapshot.soh)
        if eligible_soh and max(eligible_soh) - min(eligible_soh) < minimum_soh_range:
            eligible = 0
        coverage.append((eligible, decision_cycle))
    if not coverage:
        raise ValueError("no decision cycles were present in the trajectories")
    eligible_count, decision_cycle = max(coverage, key=lambda value: (value[0], -value[1]))
    return decision_cycle, eligible_count
