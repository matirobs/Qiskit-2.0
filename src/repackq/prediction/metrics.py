"""Interpretable present-state and held-out pack metrics."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import fmean, pstdev
from typing import Sequence

from repackq.models import CellSnapshot, FutureTruth


@dataclass(frozen=True)
class PackMetrics:
    usable_pack_capacity_ah: float
    current_capacity_spread_ah: float
    current_capacity_cv: float | None
    resistance_spread_ohm: float | None
    predicted_pack_divergence: float | None
    predicted_capacity_spread_ah: float
    observed_pack_divergence: float | None
    observed_usable_capacity_ah: float | None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


def _cv(values: Sequence[float]) -> float | None:
    mean = fmean(values)
    return pstdev(values) / mean if mean > 0 else None


def evaluate_pack_metrics(
    snapshots: Sequence[CellSnapshot],
    future_truth: Sequence[FutureTruth] | None = None,
) -> PackMetrics:
    """Compute current, predicted, and optionally observed metrics for a pack.

    In a series string, usable Ah capacity is the weakest selected cell. PPD
    and OPD are population coefficient of variation, matching SPEC §14. PPD
    is null when its mean predicted capacity is zero because CV is undefined.
    Resistance spread is null if any selected cell lacks a valid measurement.
    """

    if not snapshots:
        raise ValueError("pack metrics require at least one selected snapshot")
    capacities = [float(item.capacity_ah) for item in snapshots]
    predicted = [float(item.predicted_capacity_ah) for item in snapshots]
    current_spread = max(capacities) - min(capacities)
    resistance_values = [item.internal_resistance_ohm for item in snapshots]
    resistance_spread = (
        max(float(value) for value in resistance_values)
        - min(float(value) for value in resistance_values)
        if all(value is not None and value > 0 and math.isfinite(value) for value in resistance_values)
        else None
    )

    observed_divergence: float | None = None
    observed_usable: float | None = None
    if future_truth is not None:
        truth_by_id = {item.cell_id: item for item in future_truth}
        if len(truth_by_id) != len(future_truth):
            raise ValueError("future truth contains duplicate cell IDs")
        snapshot_ids = {item.cell_id for item in snapshots}
        if set(truth_by_id) != snapshot_ids:
            raise ValueError("future truth must contain exactly the selected cells")
        observed = [float(truth_by_id[item.cell_id].actual_capacity_ah) for item in snapshots]
        observed_divergence = _cv(observed)
        observed_usable = min(observed)

    return PackMetrics(
        usable_pack_capacity_ah=min(capacities),
        current_capacity_spread_ah=current_spread,
        current_capacity_cv=_cv(capacities),
        resistance_spread_ohm=resistance_spread,
        predicted_pack_divergence=_cv(predicted),
        predicted_capacity_spread_ah=max(predicted) - min(predicted),
        observed_pack_divergence=observed_divergence,
        observed_usable_capacity_ah=observed_usable,
    )
