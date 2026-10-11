"""Pool-local robust feature scaling used by the matching objective."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, median, pstdev
from typing import Sequence


EPSILON = 1e-9


@dataclass(frozen=True)
class FeatureScaling:
    """Auditable normalization result for one feature in one candidate pool."""

    name: str
    values: tuple[float | None, ...]
    method: str
    center: float | None
    scale: float | None
    missing_count: int
    discriminative: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "method": self.method,
            "center": self.center,
            "scale": self.scale,
            "missing_count": self.missing_count,
            "discriminative": self.discriminative,
            "values": list(self.values),
        }


def _quantile(values: Sequence[float], probability: float) -> float:
    """Linear-interpolated quantile, matching the usual inclusive convention."""

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def robust_scale(
    name: str,
    values: Sequence[float | None],
    *,
    epsilon: float = EPSILON,
) -> FeatureScaling:
    """Median/IQR scale values, falling back to z-scores and then zero.

    Missing measurements remain ``None``.  Pairwise objective terms that need
    a missing measurement are omitted; they are never fabricated as zero-valued
    sensor readings.
    """

    if not name:
        raise ValueError("feature name must not be empty")
    if not math.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("epsilon must be finite and positive")
    valid: list[float] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} values must be finite numbers or null")
        valid.append(float(value))
    missing_count = len(values) - len(valid)
    if not valid:
        return FeatureScaling(
            name=name,
            values=tuple(None for _ in values),
            method="unavailable",
            center=None,
            scale=None,
            missing_count=missing_count,
            discriminative=False,
        )

    center = float(median(valid))
    iqr = _quantile(valid, 0.75) - _quantile(valid, 0.25)
    if iqr >= epsilon:
        scale = iqr
        method = "median_iqr"
    else:
        center = float(fmean(valid))
        standard_deviation = float(pstdev(valid))
        if standard_deviation >= epsilon:
            scale = standard_deviation
            method = "mean_std"
        else:
            return FeatureScaling(
                name=name,
                values=tuple(0.0 if value is not None else None for value in values),
                method="constant",
                center=center,
                scale=0.0,
                missing_count=missing_count,
                discriminative=False,
            )

    normalized = tuple(
        None if value is None else (float(value) - center) / scale
        for value in values
    )
    if any(value is not None and not math.isfinite(value) for value in normalized):
        raise ValueError(f"normalizing {name} produced a non-finite value")
    return FeatureScaling(
        name=name,
        values=normalized,
        method=method,
        center=center,
        scale=scale,
        missing_count=missing_count,
        discriminative=True,
    )


def normalize_bounded_soh(values: Sequence[float]) -> FeatureScaling:
    """Keep SOH anchored to its physical unit interval for the unary reward."""

    normalized: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("SOH values must be finite numbers")
        normalized.append(min(1.0, max(0.0, float(value))))
    discriminative = len(set(normalized)) > 1
    return FeatureScaling(
        name="soh",
        values=tuple(normalized),
        method="unit_interval_clamp",
        center=0.0,
        scale=1.0,
        missing_count=0,
        discriminative=discriminative,
    )
