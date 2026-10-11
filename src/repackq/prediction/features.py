"""Build forecast inputs from first-life and known second-life history.

Future capacity is a training target, never an input feature."""
from __future__ import annotations

import math
import random
from statistics import mean

FEATURE_NAMES = [
    "primary_capacity_start_ah", "primary_capacity_quarter_ah",
    "primary_capacity_middle_ah", "primary_capacity_three_quarter_ah",
    "primary_capacity_end_ah", "primary_span_cycles", "primary_recent_slope_ah_per_cycle",
    "primary_recent_resistance_ohm", "primary_recent_temperature_c",
    "second_life_cutoff_cycles", "current_capacity_ah",
    "second_life_recent_slope_ah_per_cycle", "second_life_recent_resistance_ohm",
    "second_life_recent_temperature_c", "horizon_cycles",
]


def slope(points: list[dict]) -> float:
    """Unweighted capacity trend using only the explicitly supplied history."""
    if len(points) < 2:
        return 0.0
    x = [point["cycle"] for point in points]
    y = [point["capacity_ah"] for point in points]
    center_x, center_y = mean(x), mean(y)
    denominator = sum((value - center_x) ** 2 for value in x)
    return sum((a - center_x) * (b - center_y) for a, b in zip(x, y)) / denominator if denominator else 0.0


def _recent_mean(points: list[dict], key: str):
    """Average the last eight available observations for this measurement."""
    values = [point[key] for point in points[-8:] if point.get(key) is not None
              and math.isfinite(point[key])]
    return mean(values) if values else None


def build_features(primary_history: list[dict], second_life_history: list[dict],
                   cutoff: int, horizon: int) -> dict:
    """Use first-life history and second-life observations through cutoff.

    Retirement history is assumed known. Later observations, identities,
    filenames, and target capacities must stay out of the input vector."""
    if cutoff < 0 or horizon <= 0:
        raise ValueError("Cutoff must be nonnegative and horizon must be positive")
    primary = sorted(primary_history, key=lambda point: point["cycle"])
    secondary = sorted(second_life_history, key=lambda point: point["cycle"])
    if len(primary) < 4:
        raise ValueError("At least four first-life reference observations are required")
    if any(point["cycle"] > cutoff for point in secondary):
        raise ValueError("Future second-life observations must not enter features")
    if cutoff == 0 and secondary:
        raise ValueError("Cold-start forecasts cannot receive second-life observations")
    if cutoff > 0 and not secondary:
        raise ValueError("A positive cutoff requires observed second-life history")
    for point in primary + secondary:
        if not math.isfinite(point["capacity_ah"]) or not 0 < point["capacity_ah"] < 3.0:
            raise ValueError("Invalid reference capacity")
    # sample the shape of first-life aging, then add its recent trend
    primary_samples = [primary[round(fraction * (len(primary) - 1))]["capacity_ah"]
                       for fraction in (0, .25, .5, .75, 1)]
    current = secondary[-1]["capacity_ah"] if secondary else primary[-1]["capacity_ah"]
    values = primary_samples + [primary[-1]["cycle"] - primary[0]["cycle"],
        slope(primary[-8:]), _recent_mean(primary, "resistance_ohm"),
        _recent_mean(primary, "temperature_c"), cutoff, current,
        slope(secondary[-8:]), _recent_mean(secondary, "resistance_ohm"),
        _recent_mean(secondary, "temperature_c"), horizon]
    return dict(zip(FEATURE_NAMES, values))


def make_examples(cells: list[dict], cutoffs=(0, 20, 50, 100), horizons=(50, 100, 200)) -> list[dict]:
    """Attach future labels only after features have been built from truncated history."""
    examples = []
    for cell in cells:
        secondary = sorted(cell["second_life"], key=lambda point: point["cycle"])
        for cutoff in cutoffs:
            past = [point for point in secondary if point["cycle"] <= cutoff]
            if cutoff > 0 and len(past) < 4:
                continue
            for horizon in horizons:
                features = build_features(cell["primary"], past, cutoff, horizon)
                target_cycle = cutoff + horizon
                future = min(secondary, key=lambda point: abs(point["cycle"] - target_cycle))
                if future["cycle"] <= cutoff or abs(future["cycle"] - target_cycle) > max(5, round(.05 * horizon)):
                    continue
                examples.append({"cell_id": cell["cell_id"], "cutoff": cutoff,
                    "horizon": horizon, "target_cycle": future["cycle"], "features": features,
                    "target_capacity_ah": future["capacity_ah"]})
    return examples


def split_cells(cells: list[dict], seed: int = 2026) -> dict[str, list[str]]:
    """Split entire battery identities 70/15/15; no cell crosses partitions."""
    ids = sorted({cell["cell_id"] for cell in cells}, key=lambda value: int(value))
    if len(ids) < 7:
        raise ValueError("At least seven cells are needed for train/validation/test separation")
    random.Random(seed).shuffle(ids)
    training_end = max(1, int(.70 * len(ids)))
    validation_end = min(len(ids) - 1, training_end + max(1, int(.15 * len(ids))))
    return {"train": sorted(ids[:training_end]), "validation": sorted(ids[training_end:validation_end]),
            "test": sorted(ids[validation_end:])}
