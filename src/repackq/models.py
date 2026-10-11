"""Canonical, dataset-independent records used by the RePack-Q pipeline."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class CellObservation:
    """One diagnostic-cycle summary, never a raw waveform sample."""

    cell_id: str
    protocol_id: str | None
    phase: Literal["primary", "second_life", "unknown"]
    cycle_index: int
    timestamp_s: float | None
    capacity_ah: float | None
    internal_resistance_ohm: float | None
    temperature_c: float | None
    voltage_v: float | None
    current_a: float | None
    source_dataset: str

    def __post_init__(self) -> None:
        if not self.cell_id:
            raise ValueError("observation cell_id must not be empty")
        if self.phase not in {"primary", "second_life", "unknown"}:
            raise ValueError(f"unsupported observation phase: {self.phase!r}")
        if isinstance(self.cycle_index, bool) or not isinstance(self.cycle_index, int):
            raise ValueError("cycle_index must be an integer")
        if not self.source_dataset:
            raise ValueError("source_dataset must not be empty")
        numeric_fields = (
            self.timestamp_s,
            self.capacity_ah,
            self.internal_resistance_ohm,
            self.temperature_c,
            self.voltage_v,
            self.current_a,
        )
        if any(
            value is not None
            and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            )
            for value in numeric_fields
        ):
            raise ValueError("observation values must be finite or null")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CellTrajectory:
    """Compact chronological observations for a single physical cell."""

    cell_id: str
    protocol_id: str | None
    nominal_capacity_ah: float
    observations: tuple[CellObservation, ...]

    def __post_init__(self) -> None:
        if not self.cell_id:
            raise ValueError("cell_id must not be empty")
        if (
            isinstance(self.nominal_capacity_ah, bool)
            or not isinstance(self.nominal_capacity_ah, (int, float))
            or not math.isfinite(self.nominal_capacity_ah)
            or self.nominal_capacity_ah <= 0
        ):
            raise ValueError("nominal_capacity_ah must be finite and positive")
        cycles = [observation.cycle_index for observation in self.observations]
        if cycles != sorted(cycles) or len(cycles) != len(set(cycles)):
            raise ValueError("trajectory observations must have unique, sorted cycles")
        if any(observation.cell_id != self.cell_id for observation in self.observations):
            raise ValueError("observation cell IDs must match the trajectory cell ID")

    def to_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "protocol_id": self.protocol_id,
            "nominal_capacity_ah": self.nominal_capacity_ah,
            "observations": [observation.to_dict() for observation in self.observations],
        }

    def history_through(self, decision_cycle: int) -> tuple[CellObservation, ...]:
        """Return only observations available at the decision cycle."""

        _validate_cycle(decision_cycle, "decision_cycle")
        return tuple(item for item in self.observations if item.cycle_index <= decision_cycle)

    def future_after(self, decision_cycle: int) -> tuple[CellObservation, ...]:
        """Return observations strictly after the decision cycle, for evaluation only."""

        _validate_cycle(decision_cycle, "decision_cycle")
        return tuple(item for item in self.observations if item.cycle_index > decision_cycle)


def _validate_cycle(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer cycle")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")


@dataclass(frozen=True)
class CellSnapshot:
    """Decision-time features computed exclusively from observations at or before t0."""

    cell_id: str
    protocol_id: str | None
    cycle_index: int
    capacity_ah: float
    nominal_capacity_ah: float
    soh: float
    internal_resistance_ohm: float | None
    temperature_c: float | None
    recent_capacity_slope_ah_per_cycle: float
    predicted_capacity_ah: float
    prediction_uncertainty_ah: float
    horizon_cycles: int
    source_dataset: str

    def __post_init__(self) -> None:
        if not self.cell_id or not self.source_dataset:
            raise ValueError("snapshot cell_id and source_dataset must not be empty")
        _validate_cycle(self.cycle_index, "cycle_index")
        if isinstance(self.horizon_cycles, bool) or not isinstance(self.horizon_cycles, int) or self.horizon_cycles <= 0:
            raise ValueError("horizon_cycles must be a positive integer")
        _finite_positive(self.capacity_ah, "capacity_ah")
        _finite_positive(self.nominal_capacity_ah, "nominal_capacity_ah")
        _finite_positive(self.soh, "soh")
        _finite(self.recent_capacity_slope_ah_per_cycle, "recent_capacity_slope_ah_per_cycle")
        _finite_nonnegative(self.predicted_capacity_ah, "predicted_capacity_ah")
        _finite_nonnegative(self.prediction_uncertainty_ah, "prediction_uncertainty_ah")
        _optional_finite(self.internal_resistance_ohm, "internal_resistance_ohm", positive=True)
        _optional_finite(self.temperature_c, "temperature_c")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FutureTruth:
    """Nearest measured future diagnostic value, kept separate from snapshots."""

    cell_id: str
    target_cycle_index: int
    actual_capacity_ah: float
    actual_internal_resistance_ohm: float | None
    nearest_cycle_distance: int

    def __post_init__(self) -> None:
        if not self.cell_id:
            raise ValueError("future truth cell_id must not be empty")
        _validate_cycle(self.target_cycle_index, "target_cycle_index")
        _finite_positive(self.actual_capacity_ah, "actual_capacity_ah")
        _optional_finite(self.actual_internal_resistance_ohm, "actual_internal_resistance_ohm", positive=True)
        if isinstance(self.nearest_cycle_distance, bool) or not isinstance(self.nearest_cycle_distance, int) or self.nearest_cycle_distance < 0:
            raise ValueError("nearest_cycle_distance must be a nonnegative integer")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MissionProfile:
    """Mission assumptions controlling the horizon and objective weights."""

    id: str
    label: str
    horizon_cycles: int
    pack_size_k: int
    minimum_soh: float
    current_capacity_weight: float
    resistance_weight: float
    future_capacity_weight: float
    health_reward_weight: float
    uncertainty_weight: float
    temperature_weight: float
    description: str
    experimental: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.label or not self.description:
            raise ValueError("mission id, label, and description must not be empty")
        if isinstance(self.horizon_cycles, bool) or not isinstance(self.horizon_cycles, int) or self.horizon_cycles <= 0:
            raise ValueError("mission horizon_cycles must be a positive integer")
        if isinstance(self.pack_size_k, bool) or not isinstance(self.pack_size_k, int) or self.pack_size_k <= 0:
            raise ValueError("mission pack_size_k must be a positive integer")
        _finite_unit(self.minimum_soh, "minimum_soh")
        weights = (
            self.current_capacity_weight,
            self.resistance_weight,
            self.future_capacity_weight,
            self.health_reward_weight,
            self.uncertainty_weight,
            self.temperature_weight,
        )
        for name, weight in zip(
            ("current_capacity_weight", "resistance_weight", "future_capacity_weight", "health_reward_weight", "uncertainty_weight", "temperature_weight"),
            weights,
        ):
            _finite_nonnegative(weight, name)
        if not any(weights):
            raise ValueError("at least one mission weight must be positive")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CandidatePool:
    """Candidate snapshots and held-out truth for one retrospective trial."""

    pool_id: str
    decision_cycle: int
    horizon_cycles: int
    candidate_ids: tuple[str, ...]
    snapshots: tuple[CellSnapshot, ...]
    future_truth: tuple[FutureTruth, ...] | None
    seed: int
    selection_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pool_id:
            raise ValueError("pool_id must not be empty")
        _validate_cycle(self.decision_cycle, "decision_cycle")
        if isinstance(self.horizon_cycles, bool) or not isinstance(self.horizon_cycles, int) or self.horizon_cycles <= 0:
            raise ValueError("horizon_cycles must be a positive integer")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        snapshot_ids = tuple(item.cell_id for item in self.snapshots)
        if not self.candidate_ids or len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("candidate_ids must be nonempty and unique")
        if self.candidate_ids != snapshot_ids:
            raise ValueError("candidate_ids must match snapshots in the same order")
        if any(item.cycle_index != self.decision_cycle or item.horizon_cycles != self.horizon_cycles for item in self.snapshots):
            raise ValueError("snapshot decision cycle and horizon must match the pool")
        if self.future_truth is not None:
            truth_ids = tuple(item.cell_id for item in self.future_truth)
            if len(set(truth_ids)) != len(truth_ids) or set(truth_ids) != set(self.candidate_ids):
                raise ValueError("future_truth must contain exactly one record for every candidate")
            if any(item.target_cycle_index != self.decision_cycle + self.horizon_cycles for item in self.future_truth):
                raise ValueError("future truth target cycles must match the pool horizon")

    def to_dict(self) -> dict[str, object]:
        return {
            "pool_id": self.pool_id,
            "decision_cycle": self.decision_cycle,
            "horizon_cycles": self.horizon_cycles,
            "candidate_ids": list(self.candidate_ids),
            "snapshots": [item.to_dict() for item in self.snapshots],
            "future_truth": None if self.future_truth is None else [item.to_dict() for item in self.future_truth],
            "seed": self.seed,
            "selection_metadata": self.selection_metadata,
        }


def _finite(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _finite_positive(value: float, name: str) -> None:
    _finite(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _finite_nonnegative(value: float, name: str) -> None:
    _finite(value, name)
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


def _finite_unit(value: float, name: str) -> None:
    _finite(value, name)
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")


def _optional_finite(value: float | None, name: str, *, positive: bool = False) -> None:
    if value is not None:
        (_finite_positive if positive else _finite)(value, name)
