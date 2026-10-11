"""Scale measurements within the candidate pool."""
from dataclasses import dataclass
import math
from statistics import mean, median, pstdev

EPSILON = 1e-9


@dataclass(frozen=True)
class NormalizedFeature:
    values: tuple[float, ...]
    method: str
    center: float
    scale: float
    discriminates: bool


def quantile(sorted_values, fraction):
    """Interpolate between adjacent values in a sorted sequence."""
    position = (len(sorted_values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def normalize(values, *, unit_interval=False):
    """Scale by the interquartile range, falling back to standard deviation.

    Constant inputs become zero. Uncertainty uses [0, 1] so a larger value
    always adds a penalty."""
    values = tuple(float(value) for value in values)
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("Normalization requires nonempty finite values")
    ordered = sorted(values)
    if ordered[-1] - ordered[0] < EPSILON:
        return NormalizedFeature((0.0,) * len(values), "constant", ordered[0], 1.0, False)
    if unit_interval:
        center, scale, method = ordered[0], ordered[-1] - ordered[0], "min_max"
    else:
        center = median(values)
        scale = quantile(ordered, .75) - quantile(ordered, .25)
        method = "median_interquartile_range"
        if scale < EPSILON:
            center, scale, method = mean(values), max(pstdev(values), EPSILON), "standard_score"
    return NormalizedFeature(tuple((value - center) / scale for value in values),
                             method, center, scale, True)
