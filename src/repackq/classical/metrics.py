"""Measure a selected group; recorded future capacity is supplied separately."""
import math
from statistics import mean, pstdev


def divergence(capacities):
    """Population standard deviation / mean; undefined at zero mean."""
    average = mean(capacities)
    return pstdev(capacities) / average if average > 0 else None


def evaluate_selection(instance, selection, *, future_truth=None, optimum=None):
    """Report current and predicted spread, plus actual outcomes when revealed."""
    selected = instance.validate_selection(selection.selected_indices, require_size=True)
    cells = [instance.cells[i] for i in selected]
    capacities = [c.capacity_ah for c in cells]
    resistance = [c.internal_resistance_ohm for c in cells]
    predicted = [c.predicted_capacity_ah for c in cells]
    has_predictions = all(v is not None and math.isfinite(v) and v >= 0 for v in predicted)
    has_resistance = all(v is not None and math.isfinite(v) and v >= 0 for v in resistance)
    metrics = {"current_capacity_spread_ah": max(capacities) - min(capacities),
               "current_capacity_cv": divergence(capacities),
               "usable_pack_capacity_ah": min(capacities),
               "resistance_spread_ohm": max(resistance) - min(resistance) if has_resistance else None,
               "predicted_pack_divergence": divergence(predicted) if has_predictions else None,
               "predicted_capacity_spread_ah": max(predicted) - min(predicted) if has_predictions else None,
               "predicted_usable_capacity_ah": min(predicted) if has_predictions else None,
               "observed_pack_divergence": None, "observed_capacity_spread_ah": None,
               "observed_usable_capacity_ah": None}
    # leave actual metrics empty until the caller supplies the withheld measurements
    if future_truth is not None:
        try:
            actual = [future_truth[c.cell_id]["actual_capacity_ah"] for c in cells]
        except KeyError as error:
            raise ValueError("Future truth must cover every selected cell") from error
        if not all(math.isfinite(v) and v > 0 for v in actual):
            raise ValueError("Future capacities must be finite and positive")
        metrics.update(observed_pack_divergence=divergence(actual),
                       observed_capacity_spread_ah=max(actual) - min(actual),
                       observed_usable_capacity_ah=min(actual))
    if optimum is not None:
        gap = selection.objective_value - optimum.objective_value
        if gap < -1e-9:
            raise ValueError("Selection has lower cost than the supplied optimum")
        gap = max(0.0, gap)
        spread = optimum.metadata["worst_feasible_objective"] - optimum.objective_value
        metrics.update(objective_gap_abs=gap,
                       objective_gap_pct=gap / max(abs(optimum.objective_value), 1e-9) * 100,
                       normalized_regret=gap / spread if spread > 1e-9 else 0.0)
    return {**selection.to_dict(), **metrics}
