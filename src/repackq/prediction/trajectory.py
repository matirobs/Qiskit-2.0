"""Leakage-free weighted linear capacity estimates and decision snapshots."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from repackq.models import CellObservation, CellSnapshot


@dataclass(frozen=True)
class EstimatorConfig:
    """Configuration for the intentionally simple MVP degradation estimator."""

    window_size: int = 8
    minimum_history_points: int = 4
    maximum_uncertainty_fraction_of_nominal: float = 0.25

    def __post_init__(self) -> None:
        if isinstance(self.window_size, bool) or not isinstance(self.window_size, int) or self.window_size < 2:
            raise ValueError("window_size must be an integer of at least 2")
        if (
            isinstance(self.minimum_history_points, bool)
            or not isinstance(self.minimum_history_points, int)
            or self.minimum_history_points < 2
        ):
            raise ValueError("minimum_history_points must be an integer of at least 2")
        if self.minimum_history_points > self.window_size:
            raise ValueError("minimum_history_points cannot exceed window_size")
        if (
            isinstance(self.maximum_uncertainty_fraction_of_nominal, bool)
            or not isinstance(self.maximum_uncertainty_fraction_of_nominal, (int, float))
            or not math.isfinite(self.maximum_uncertainty_fraction_of_nominal)
            or self.maximum_uncertainty_fraction_of_nominal <= 0
        ):
            raise ValueError("maximum uncertainty fraction must be finite and positive")


DEFAULT_ESTIMATOR_CONFIG = EstimatorConfig()


def _validate_history(history: Sequence[CellObservation], decision_cycle: int) -> None:
    if any(item.cycle_index > decision_cycle for item in history):
        raise ValueError("history contains an observation after decision_cycle; future leakage rejected")
    cycles = [item.cycle_index for item in history]
    if cycles != sorted(cycles) or len(cycles) != len(set(cycles)):
        raise ValueError("history observations must have unique, sorted cycle indices")
    cell_ids = {item.cell_id for item in history}
    if len(cell_ids) > 1:
        raise ValueError("history observations must belong to one cell")


@dataclass(frozen=True)
class TrajectoryPredictionDiagnostics:
    fit_method: str
    fallback_reason: str | None
    available_history_points: int
    used_history_points: int
    window_start_cycle: int
    decision_cycle: int
    raw_slope_ah_per_cycle: float
    applied_slope_ah_per_cycle: float
    positive_slope_clamped: bool
    weighted_residual_std_ah: float
    uncertainty_ah: float
    uncertainty_clamped: bool
    unclamped_prediction_ah: float
    prediction_clamped: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TrajectoryEstimate:
    predicted_capacity_ah: float
    recent_capacity_slope_ah_per_cycle: float
    prediction_uncertainty_ah: float
    diagnostics: TrajectoryPredictionDiagnostics


def median_pairwise_slope(cycle_indices: Sequence[int], capacities_ah: Sequence[float]) -> float:
    """Return the deterministic median of all distinct-cycle pairwise slopes."""

    if len(cycle_indices) != len(capacities_ah) or len(cycle_indices) < 2:
        raise ValueError("median pairwise slope requires matching arrays with at least two points")
    slopes: list[float] = []
    for left in range(len(cycle_indices)):
        for right in range(left + 1, len(cycle_indices)):
            delta_cycle = cycle_indices[right] - cycle_indices[left]
            if delta_cycle == 0:
                continue
            slope = (capacities_ah[right] - capacities_ah[left]) / delta_cycle
            if math.isfinite(slope):
                slopes.append(slope)
    if not slopes:
        raise ValueError("median pairwise slope requires at least one distinct cycle pair")
    slopes.sort()
    midpoint = len(slopes) // 2
    if len(slopes) % 2:
        return slopes[midpoint]
    return (slopes[midpoint - 1] + slopes[midpoint]) / 2.0


def _weighted_linear_fit(
    cycle_indices: Sequence[int], capacities_ah: Sequence[float], decision_cycle: int
) -> tuple[float, float]:
    """Fit an intercept/slope with newer observations receiving larger weights."""

    x = np.asarray([cycle - decision_cycle for cycle in cycle_indices], dtype=float)
    y = np.asarray(capacities_ah, dtype=float)
    weights = np.linspace(0.5, 1.0, len(x), dtype=float)
    design = np.column_stack((np.ones(len(x), dtype=float), x))
    root_weights = np.sqrt(weights)
    coefficients, _, rank, _ = np.linalg.lstsq(
        design * root_weights[:, None], y * root_weights, rcond=None
    )
    if rank < 2 or coefficients.shape != (2,) or not np.isfinite(coefficients).all():
        raise np.linalg.LinAlgError("weighted regression was rank-deficient or non-finite")
    return float(coefficients[0]), float(coefficients[1])


def estimate_capacity_trajectory(
    history: Sequence[CellObservation],
    *,
    decision_cycle: int,
    horizon_cycles: int,
    nominal_capacity_ah: float,
    config: EstimatorConfig = DEFAULT_ESTIMATOR_CONFIG,
) -> TrajectoryEstimate:
    """Estimate capacity at ``t0 + H`` from a history-only observation sequence.

    The function rejects any observation after ``decision_cycle``. This makes
    accidental future-array passage fail closed instead of silently filtering
    leaked values. A valid capacity measurement at exactly t0 is required so
    the forecast horizon has one unambiguous anchor.
    """

    if isinstance(decision_cycle, bool) or not isinstance(decision_cycle, int) or decision_cycle < 0:
        raise ValueError("decision_cycle must be a nonnegative integer")
    if isinstance(horizon_cycles, bool) or not isinstance(horizon_cycles, int) or horizon_cycles <= 0:
        raise ValueError("horizon_cycles must be a positive integer")
    if (
        isinstance(nominal_capacity_ah, bool)
        or not isinstance(nominal_capacity_ah, (int, float))
        or not math.isfinite(nominal_capacity_ah)
        or nominal_capacity_ah <= 0
    ):
        raise ValueError("nominal_capacity_ah must be finite and positive")
    _validate_history(history, decision_cycle)

    valid = [
        item for item in history
        if item.capacity_ah is not None and math.isfinite(item.capacity_ah) and item.capacity_ah > 0
    ]
    if not valid or valid[-1].cycle_index != decision_cycle:
        raise ValueError("history must include a valid capacity observation at decision_cycle")
    selected = valid[-config.window_size :]
    if len(selected) < config.minimum_history_points:
        raise ValueError(
            f"insufficient capacity history: need {config.minimum_history_points} points, "
            f"found {len(selected)}"
        )

    cycles = [item.cycle_index for item in selected]
    capacities = [float(item.capacity_ah) for item in selected if item.capacity_ah is not None]
    current_capacity = capacities[-1]
    fallback_reason: str | None = None
    try:
        intercept, raw_slope = _weighted_linear_fit(cycles, capacities, decision_cycle)
        fit_method = "weighted_least_squares"
    except (np.linalg.LinAlgError, FloatingPointError, ValueError) as error:
        raw_slope = median_pairwise_slope(cycles, capacities)
        x_values = [cycle - decision_cycle for cycle in cycles]
        intercept_values = [capacity - raw_slope * x for x, capacity in zip(x_values, capacities)]
        intercept = float(np.median(np.asarray(intercept_values, dtype=float)))
        fit_method = "median_pairwise_slope"
        fallback_reason = str(error)

    if not math.isfinite(raw_slope) or not math.isfinite(intercept):
        raise ValueError("trajectory fit produced a non-finite result")
    applied_slope = min(raw_slope, 0.0)
    positive_slope_clamped = raw_slope > 0.0

    x_values = np.asarray([cycle - decision_cycle for cycle in cycles], dtype=float)
    y_values = np.asarray(capacities, dtype=float)
    weights = np.linspace(0.5, 1.0, len(cycles), dtype=float)
    residuals = y_values - (intercept + raw_slope * x_values)
    residual_std = float(np.sqrt(np.average(np.square(residuals), weights=weights)))
    history_span = max(cycles) - min(cycles)
    uncertainty = residual_std * math.sqrt(1.0 + horizon_cycles / max(history_span, 1))
    uncertainty_cap = config.maximum_uncertainty_fraction_of_nominal * nominal_capacity_ah
    uncertainty_clamped = uncertainty > uncertainty_cap
    uncertainty = min(uncertainty, uncertainty_cap)

    raw_prediction = current_capacity + applied_slope * horizon_cycles
    prediction = min(current_capacity, max(0.0, raw_prediction))
    diagnostics = TrajectoryPredictionDiagnostics(
        fit_method=fit_method,
        fallback_reason=fallback_reason,
        available_history_points=len(valid),
        used_history_points=len(selected),
        window_start_cycle=cycles[0],
        decision_cycle=decision_cycle,
        raw_slope_ah_per_cycle=raw_slope,
        applied_slope_ah_per_cycle=applied_slope,
        positive_slope_clamped=positive_slope_clamped,
        weighted_residual_std_ah=residual_std,
        uncertainty_ah=uncertainty,
        uncertainty_clamped=uncertainty_clamped,
        unclamped_prediction_ah=raw_prediction,
        prediction_clamped=prediction != raw_prediction,
    )
    return TrajectoryEstimate(
        predicted_capacity_ah=prediction,
        recent_capacity_slope_ah_per_cycle=applied_slope,
        prediction_uncertainty_ah=uncertainty,
        diagnostics=diagnostics,
    )


def _latest_valid_optional(
    history: Sequence[CellObservation], field_name: str
) -> float | None:
    for item in reversed(history):
        value = getattr(item, field_name)
        if value is not None and math.isfinite(value):
            if field_name != "temperature_c" and value <= 0:
                continue
            return float(value)
    return None


def build_snapshot(
    history: Sequence[CellObservation],
    *,
    decision_cycle: int,
    horizon_cycles: int,
    nominal_capacity_ah: float,
    config: EstimatorConfig = DEFAULT_ESTIMATOR_CONFIG,
) -> CellSnapshot:
    """Build a decision-time cell record using only the supplied history."""

    if not history:
        raise ValueError("cannot build a snapshot from empty history")
    _validate_history(history, decision_cycle)
    current = next(
        (
            item for item in reversed(history)
            if item.cycle_index == decision_cycle
            and item.capacity_ah is not None
            and math.isfinite(item.capacity_ah)
            and item.capacity_ah > 0
        ),
        None,
    )
    if current is None:
        raise ValueError("history must include valid current capacity at decision_cycle")
    estimate = estimate_capacity_trajectory(
        history,
        decision_cycle=decision_cycle,
        horizon_cycles=horizon_cycles,
        nominal_capacity_ah=nominal_capacity_ah,
        config=config,
    )
    assert current.capacity_ah is not None
    return CellSnapshot(
        cell_id=current.cell_id,
        protocol_id=current.protocol_id,
        cycle_index=decision_cycle,
        capacity_ah=float(current.capacity_ah),
        nominal_capacity_ah=nominal_capacity_ah,
        soh=float(current.capacity_ah) / nominal_capacity_ah,
        internal_resistance_ohm=_latest_valid_optional(history, "internal_resistance_ohm"),
        temperature_c=_latest_valid_optional(history, "temperature_c"),
        recent_capacity_slope_ah_per_cycle=estimate.recent_capacity_slope_ah_per_cycle,
        predicted_capacity_ah=estimate.predicted_capacity_ah,
        prediction_uncertainty_ah=estimate.prediction_uncertainty_ah,
        horizon_cycles=horizon_cycles,
        source_dataset=current.source_dataset,
    )
