"""Explicit history/future separation and held-out truth lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from repackq.models import CellObservation, CellTrajectory, FutureTruth


@dataclass(frozen=True)
class TrajectorySplit:
    """Disjoint observations on either side of a recommissioning cutoff."""

    decision_cycle: int
    history: tuple[CellObservation, ...]
    future: tuple[CellObservation, ...]

    def __post_init__(self) -> None:
        if any(item.cycle_index > self.decision_cycle for item in self.history):
            raise ValueError("history side contains observations after decision_cycle")
        if any(item.cycle_index <= self.decision_cycle for item in self.future):
            raise ValueError("future side contains observations at or before decision_cycle")


def split_history_future(trajectory: CellTrajectory, decision_cycle: int) -> TrajectorySplit:
    """Split once, then pass ``history`` and ``future`` to separate APIs."""

    history = trajectory.history_through(decision_cycle)
    future = trajectory.future_after(decision_cycle)
    return TrajectorySplit(decision_cycle, history, future)


def future_tolerance_for_horizon(horizon_cycles: int) -> int:
    """Default nearest-diagnostic tolerance: max(5 cycles, 5% of H)."""

    if isinstance(horizon_cycles, bool) or not isinstance(horizon_cycles, int) or horizon_cycles <= 0:
        raise ValueError("horizon_cycles must be a positive integer")
    return max(5, round(0.05 * horizon_cycles))


def lookup_future_truth(
    future: Sequence[CellObservation],
    *,
    decision_cycle: int,
    target_cycle: int,
    max_future_cycle_error: int,
) -> FutureTruth | None:
    """Find the closest valid held-out capacity measurement inside tolerance.

    ``future`` must already be separated from history. Passing a full trajectory
    is rejected, and no prediction or snapshot function accepts this argument.
    Ties choose the earlier cycle deterministically.
    """

    if isinstance(decision_cycle, bool) or not isinstance(decision_cycle, int) or decision_cycle < 0:
        raise ValueError("decision_cycle must be a nonnegative integer")
    if isinstance(target_cycle, bool) or not isinstance(target_cycle, int) or target_cycle <= decision_cycle:
        raise ValueError("target_cycle must be an integer after decision_cycle")
    if (
        isinstance(max_future_cycle_error, bool)
        or not isinstance(max_future_cycle_error, int)
        or max_future_cycle_error < 0
    ):
        raise ValueError("max_future_cycle_error must be a nonnegative integer")
    if any(item.cycle_index <= decision_cycle for item in future):
        raise ValueError("future side contains an observation at or before decision_cycle")
    cell_ids = {item.cell_id for item in future}
    if len(cell_ids) > 1:
        raise ValueError("future truth lookup accepts observations for one cell only")

    valid = [
        item for item in future
        if item.capacity_ah is not None and item.capacity_ah > 0
    ]
    if not valid:
        return None
    nearest = min(valid, key=lambda item: (abs(item.cycle_index - target_cycle), item.cycle_index))
    distance = abs(nearest.cycle_index - target_cycle)
    if distance > max_future_cycle_error:
        return None
    resistance = nearest.internal_resistance_ohm
    if resistance is not None and resistance <= 0:
        resistance = None
    assert nearest.capacity_ah is not None
    return FutureTruth(
        cell_id=nearest.cell_id,
        target_cycle_index=target_cycle,
        actual_capacity_ah=float(nearest.capacity_ah),
        actual_internal_resistance_ohm=resistance,
        nearest_cycle_distance=distance,
    )
