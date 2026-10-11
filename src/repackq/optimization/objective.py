"""Mission-weighted subset objective, fixed-cardinality QUBO, and Ising map."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from repackq.models import CandidatePool, CellSnapshot, MissionProfile
from repackq.optimization.normalization import FeatureScaling, normalize_bounded_soh, robust_scale


OBJECTIVE_MODES = ("current_only", "trajectory_aware")
PAIR_COMPONENTS = (
    "capacity_mismatch",
    "resistance_mismatch",
    "future_mismatch",
    "temperature_mismatch",
)
UNARY_COMPONENTS = ("health_reward", "uncertainty_penalty")


@dataclass(frozen=True)
class ObjectiveBreakdown:
    capacity_mismatch: float
    resistance_mismatch: float
    future_mismatch: float
    temperature_mismatch: float
    health_reward: float
    uncertainty_penalty: float
    cardinality_penalty: float
    total: float

    def to_dict(self) -> dict[str, float]:
        return {
            "capacity_mismatch": self.capacity_mismatch,
            "resistance_mismatch": self.resistance_mismatch,
            "future_mismatch": self.future_mismatch,
            "temperature_mismatch": self.temperature_mismatch,
            "health_reward": self.health_reward,
            "uncertainty_penalty": self.uncertainty_penalty,
            "cardinality_penalty": self.cardinality_penalty,
            "total": self.total,
        }


@dataclass(frozen=True)
class OptimizationInstance:
    """Optimizer-visible data only; held-out future truth is deliberately absent."""

    pool_id: str
    candidate_ids: tuple[str, ...]
    snapshots: tuple[CellSnapshot, ...]
    pack_size_k: int
    objective_mode: str
    mission: MissionProfile
    normalizations: Mapping[str, FeatureScaling]
    pairwise_components: Mapping[str, tuple[tuple[float, ...], ...]]
    unary_components: Mapping[str, tuple[float, ...]]

    @property
    def n(self) -> int:
        return len(self.snapshots)

    @property
    def feature_weights(self) -> dict[str, float]:
        weights = {
            "capacity_mismatch": self.mission.current_capacity_weight,
            "resistance_mismatch": self.mission.resistance_weight,
            "future_mismatch": (
                self.mission.future_capacity_weight
                if self.objective_mode == "trajectory_aware"
                else 0.0
            ),
            "temperature_mismatch": self.mission.temperature_weight,
        }
        return weights

    def validate_indices(self, indices: Sequence[int]) -> tuple[int, ...]:
        normalized: list[int] = []
        for index in indices:
            if isinstance(index, bool) or not isinstance(index, int):
                raise ValueError("selected indices must be integers")
            if not 0 <= index < self.n:
                raise ValueError(f"selected index {index} is outside [0, {self.n})")
            normalized.append(index)
        if len(normalized) != len(set(normalized)):
            raise ValueError("selected indices must not contain duplicates")
        return tuple(normalized)

    def breakdown_for_indices(
        self,
        indices: Sequence[int],
        *,
        cardinality_penalty: float = 0.0,
    ) -> ObjectiveBreakdown:
        selected = self.validate_indices(indices)
        if not math.isfinite(cardinality_penalty):
            raise ValueError("cardinality_penalty must be finite")
        pair_totals = {name: 0.0 for name in PAIR_COMPONENTS}
        for left_position, left in enumerate(selected):
            for right in selected[left_position + 1 :]:
                for name in PAIR_COMPONENTS:
                    pair_totals[name] += self.pairwise_components[name][left][right]
        unary_totals = {
            name: sum(self.unary_components[name][index] for index in selected)
            for name in UNARY_COMPONENTS
        }
        # Disabled objective modes expose a stable schema with zero-valued terms.
        if self.objective_mode == "current_only":
            pair_totals["future_mismatch"] = 0.0
            unary_totals["uncertainty_penalty"] = 0.0
        total = sum(pair_totals.values()) + sum(unary_totals.values()) + cardinality_penalty
        values = (*pair_totals.values(), *unary_totals.values(), cardinality_penalty, total)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("objective evaluation produced a non-finite value")
        return ObjectiveBreakdown(
            capacity_mismatch=pair_totals["capacity_mismatch"],
            resistance_mismatch=pair_totals["resistance_mismatch"],
            future_mismatch=pair_totals["future_mismatch"],
            temperature_mismatch=pair_totals["temperature_mismatch"],
            health_reward=unary_totals["health_reward"],
            uncertainty_penalty=unary_totals["uncertainty_penalty"],
            cardinality_penalty=cardinality_penalty,
            total=total,
        )

    def objective_for_indices(self, indices: Sequence[int]) -> float:
        """Physical compatibility objective, without a cardinality penalty."""

        return self.breakdown_for_indices(indices).total

    def objective_for_bits(self, bits: Sequence[int]) -> float:
        selected = indices_from_bits(bits, self.n)
        return self.objective_for_indices(selected)

    def to_dict(self) -> dict[str, object]:
        return {
            "pool_id": self.pool_id,
            "candidate_ids": list(self.candidate_ids),
            "pack_size_k": self.pack_size_k,
            "objective_mode": self.objective_mode,
            "mission": self.mission.to_dict(),
            "feature_weights": self.feature_weights,
            "normalizations": {
                name: scaling.to_dict()
                for name, scaling in sorted(self.normalizations.items())
            },
        }


def _pair_matrix(values: Sequence[float | None], weight: float) -> tuple[tuple[float, ...], ...]:
    count = len(values)
    matrix = [[0.0] * count for _ in range(count)]
    if weight > 0:
        for left in range(count):
            left_value = values[left]
            if left_value is None:
                continue
            for right in range(left + 1, count):
                right_value = values[right]
                if right_value is None:
                    continue
                value = weight * (left_value - right_value) ** 2
                if not math.isfinite(value) or value < 0:
                    raise ValueError("pairwise incompatibility must be finite and nonnegative")
                matrix[left][right] = value
                matrix[right][left] = value
    return tuple(tuple(row) for row in matrix)


def build_optimization_instance(
    pool: CandidatePool,
    *,
    mission: MissionProfile,
    objective_mode: str = "trajectory_aware",
) -> OptimizationInstance:
    """Normalize one candidate pool and construct its physical objective.

    Only ``CandidatePool.snapshots`` are read. ``pool.future_truth`` is never
    copied into the instance or consulted while normalizing/scoring candidates.
    """

    if objective_mode not in OBJECTIVE_MODES:
        raise ValueError(f"objective_mode must be one of {', '.join(OBJECTIVE_MODES)}")
    snapshots = tuple(pool.snapshots)
    n = len(snapshots)
    if n == 0 or n != len(pool.candidate_ids):
        raise ValueError("optimization requires a nonempty pool with one snapshot per candidate")
    if pool.horizon_cycles != mission.horizon_cycles:
        raise ValueError(
            f"pool horizon H={pool.horizon_cycles} does not match mission "
            f"horizon H={mission.horizon_cycles}"
        )
    if not 1 <= mission.pack_size_k <= n:
        raise ValueError(f"pack size K={mission.pack_size_k} must be between 1 and N={n}")

    normalizations: dict[str, FeatureScaling] = {
        "capacity": robust_scale("capacity", [item.capacity_ah for item in snapshots]),
        "soh": normalize_bounded_soh([item.soh for item in snapshots]),
    }
    if mission.resistance_weight > 0:
        normalizations["resistance"] = robust_scale(
            "resistance", [item.internal_resistance_ohm for item in snapshots]
        )
    if mission.temperature_weight > 0:
        normalizations["temperature"] = robust_scale(
            "temperature", [item.temperature_c for item in snapshots]
        )
    if objective_mode == "trajectory_aware":
        if mission.future_capacity_weight > 0:
            normalizations["future_capacity"] = robust_scale(
                "future_capacity", [item.predicted_capacity_ah for item in snapshots]
            )
        if mission.uncertainty_weight > 0:
            normalizations["uncertainty"] = robust_scale(
                "uncertainty", [item.prediction_uncertainty_ah for item in snapshots]
            )

    weights = {
        "capacity_mismatch": mission.current_capacity_weight,
        "resistance_mismatch": mission.resistance_weight,
        "future_mismatch": (
            mission.future_capacity_weight if objective_mode == "trajectory_aware" else 0.0
        ),
        "temperature_mismatch": mission.temperature_weight,
    }
    pair_values = {
        "capacity_mismatch": normalizations["capacity"].values,
        "resistance_mismatch": normalizations.get(
            "resistance", FeatureScaling("resistance", tuple(None for _ in snapshots), "disabled", None, None, n, False)
        ).values,
        "future_mismatch": normalizations.get(
            "future_capacity", FeatureScaling("future_capacity", tuple(None for _ in snapshots), "disabled", None, None, n, False)
        ).values,
        "temperature_mismatch": normalizations.get(
            "temperature", FeatureScaling("temperature", tuple(None for _ in snapshots), "disabled", None, None, n, False)
        ).values,
    }
    pairwise = {
        name: _pair_matrix(pair_values[name], weights[name])
        for name in PAIR_COMPONENTS
    }
    soh_values = normalizations["soh"].values
    unary: dict[str, tuple[float, ...]] = {
        "health_reward": tuple(-mission.health_reward_weight * float(value) for value in soh_values)
    }
    if objective_mode == "trajectory_aware" and mission.uncertainty_weight > 0:
        uncertainty_values = normalizations["uncertainty"].values
        unary["uncertainty_penalty"] = tuple(
            mission.uncertainty_weight * float(value) if value is not None else 0.0
            for value in uncertainty_values
        )
    else:
        unary["uncertainty_penalty"] = tuple(0.0 for _ in snapshots)

    return OptimizationInstance(
        pool_id=pool.pool_id,
        candidate_ids=tuple(pool.candidate_ids),
        snapshots=snapshots,
        pack_size_k=mission.pack_size_k,
        objective_mode=objective_mode,
        mission=mission,
        normalizations=normalizations,
        pairwise_components=pairwise,
        unary_components=unary,
    )


def bits_from_indices(indices: Sequence[int], n: int) -> tuple[int, ...]:
    """Build a canonical candidate-index-order binary vector."""

    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    bits = [0] * n
    seen: set[int] = set()
    for index in indices:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < n:
            raise ValueError(f"selected index {index!r} is outside [0, {n})")
        if index in seen:
            raise ValueError("selected indices must not contain duplicates")
        bits[index] = 1
        seen.add(index)
    return tuple(bits)


def indices_from_bits(bits: Sequence[int], n: int | None = None) -> tuple[int, ...]:
    """Decode a binary vector in canonical candidate-index order."""

    if n is not None and len(bits) != n:
        raise ValueError(f"bit vector has length {len(bits)}, expected {n}")
    selected: list[int] = []
    for index, bit in enumerate(bits):
        if isinstance(bit, bool):
            bit = int(bit)
        if not isinstance(bit, int) or bit not in (0, 1):
            raise ValueError("bit vector entries must be binary integers")
        if bit:
            selected.append(index)
    return tuple(selected)


@dataclass(frozen=True)
class QUBOModel:
    """Upper-triangular QUBO with an explicit constant energy offset."""

    linear: tuple[float, ...]
    quadratic: Mapping[tuple[int, int], float]
    constant: float
    cardinality_penalty: float
    penalty_multiplier: float
    calibration_doublings: int
    base_pair_scale: float
    physical_linear: tuple[float, ...]
    physical_quadratic: Mapping[tuple[int, int], float]
    physical_constant: float

    @property
    def n(self) -> int:
        return len(self.linear)

    def energy(self, bits: Sequence[int]) -> float:
        selected = indices_from_bits(bits, self.n)
        energy = self.constant + sum(self.linear[index] for index in selected)
        energy += sum(
            coefficient
            for (left, right), coefficient in self.quadratic.items()
            if left in selected and right in selected
        )
        if not math.isfinite(energy):
            raise ValueError("QUBO energy is non-finite")
        return float(energy)

    def physical_energy(self, bits: Sequence[int]) -> float:
        selected = indices_from_bits(bits, self.n)
        energy = self.physical_constant + sum(self.physical_linear[index] for index in selected)
        energy += sum(
            coefficient
            for (left, right), coefficient in self.physical_quadratic.items()
            if left in selected and right in selected
        )
        return float(energy)

    def breakdown(
        self,
        instance: OptimizationInstance,
        bits: Sequence[int],
    ) -> ObjectiveBreakdown:
        """Return named physical terms plus the encoded cardinality penalty."""

        if instance.n != self.n:
            raise ValueError("QUBO and optimization instance widths do not match")
        indices = indices_from_bits(bits, self.n)
        penalty = self.cardinality_penalty * (len(indices) - instance.pack_size_k) ** 2
        return instance.breakdown_for_indices(indices, cardinality_penalty=penalty)

    def to_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "linear": list(self.linear),
            "quadratic": [
                {"i": left, "j": right, "value": value}
                for (left, right), value in sorted(self.quadratic.items())
            ],
            "constant": self.constant,
            "cardinality_penalty": self.cardinality_penalty,
            "penalty_multiplier": self.penalty_multiplier,
            "calibration_doublings": self.calibration_doublings,
            "base_pair_scale": self.base_pair_scale,
        }


def _minimum_qubo_state_is_feasible(model: QUBOModel, k: int) -> bool:
    minimum_energy = math.inf
    feasible_minimum = False
    for bits in itertools.product((0, 1), repeat=model.n):
        value = model.energy(bits)
        cardinality_ok = sum(bits) == k
        if value < minimum_energy - 1e-12:
            minimum_energy = value
            feasible_minimum = cardinality_ok
        elif abs(value - minimum_energy) <= 1e-12 and not cardinality_ok:
            # Any infeasible global tie means the penalty has not enforced K.
            feasible_minimum = False
    return feasible_minimum


def build_qubo(
    instance: OptimizationInstance,
    *,
    penalty_multiplier: float = 4.0,
    max_calibration_doublings: int = 5,
    calibrate: bool = True,
) -> QUBOModel:
    """Expand the physical objective and calibrate its exact-K penalty."""

    if not math.isfinite(penalty_multiplier) or penalty_multiplier <= 0:
        raise ValueError("penalty_multiplier must be finite and positive")
    if (
        isinstance(max_calibration_doublings, bool)
        or not isinstance(max_calibration_doublings, int)
        or max_calibration_doublings < 0
    ):
        raise ValueError("max_calibration_doublings must be a nonnegative integer")
    if calibrate and instance.n > 20:
        raise ValueError("exact cardinality calibration is limited to N <= 20")

    physical_linear = tuple(
        sum(instance.unary_components[name][i] for name in UNARY_COMPONENTS)
        for i in range(instance.n)
    )
    physical_quadratic = {
        (left, right): sum(
            instance.pairwise_components[name][left][right] for name in PAIR_COMPONENTS
        )
        for left in range(instance.n)
        for right in range(left + 1, instance.n)
    }
    physical_constant = 0.0
    base_pair_scale = max(
        1.0,
        max(physical_quadratic.values(), default=0.0),
        max((abs(value) for value in physical_linear), default=0.0),
    )
    penalty = penalty_multiplier * base_pair_scale

    def make_model(value: float, doublings: int) -> QUBOModel:
        linear = tuple(
            physical_linear[i] + value * (1.0 - 2.0 * instance.pack_size_k)
            for i in range(instance.n)
        )
        quadratic = {
            pair: coefficient + 2.0 * value
            for pair, coefficient in physical_quadratic.items()
        }
        constant = physical_constant + value * instance.pack_size_k**2
        return QUBOModel(
            linear=linear,
            quadratic=quadratic,
            constant=constant,
            cardinality_penalty=value,
            penalty_multiplier=penalty_multiplier,
            calibration_doublings=doublings,
            base_pair_scale=base_pair_scale,
            physical_linear=physical_linear,
            physical_quadratic=physical_quadratic,
            physical_constant=physical_constant,
        )

    model = make_model(penalty, 0)
    if not calibrate:
        return model
    for doublings in range(max_calibration_doublings + 1):
        model = make_model(penalty, doublings)
        if _minimum_qubo_state_is_feasible(model, instance.pack_size_k):
            return model
        penalty *= 2.0
    raise ValueError(
        "cardinality penalty calibration failed: penalized QUBO still has an "
        "infeasible global minimum after the configured doublings"
    )


@dataclass(frozen=True)
class IsingModel:
    """Ising energy using x_i = (1 - Z_i) / 2."""

    h: tuple[float, ...]
    couplings: Mapping[tuple[int, int], float]
    offset: float

    @property
    def n(self) -> int:
        return len(self.h)

    def energy(self, bits: Sequence[int]) -> float:
        selected = set(indices_from_bits(bits, self.n))
        spins = tuple(-1 if index in selected else 1 for index in range(self.n))
        energy = self.offset + sum(self.h[i] * spins[i] for i in range(self.n))
        energy += sum(
            coupling * spins[left] * spins[right]
            for (left, right), coupling in self.couplings.items()
        )
        if not math.isfinite(energy):
            raise ValueError("Ising energy is non-finite")
        return float(energy)

    def to_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "h": list(self.h),
            "couplings": [
                {"i": left, "j": right, "value": value}
                for (left, right), value in sorted(self.couplings.items())
            ],
            "offset": self.offset,
            "mapping": "x_i = (1 - Z_i) / 2",
        }


def qubo_to_ising(model: QUBOModel) -> IsingModel:
    """Map all QUBO linear/quadratic terms and preserve the energy offset."""

    n = model.n
    z_coefficients = [0.0] * n
    couplings = {
        pair: value / 4.0 for pair, value in model.quadratic.items()
    }
    offset = model.constant + sum(model.linear) / 2.0 + sum(model.quadratic.values()) / 4.0
    for index, linear in enumerate(model.linear):
        z_coefficients[index] = -linear / 2.0
    for (left, right), quadratic in model.quadratic.items():
        z_coefficients[left] -= quadratic / 4.0
        z_coefficients[right] -= quadratic / 4.0
    return IsingModel(h=tuple(z_coefficients), couplings=couplings, offset=offset)


def verify_ising_equivalence(
    model: QUBOModel,
    *,
    tolerance: float = 1e-9,
    maximum_n: int = 12,
) -> bool:
    """Exhaustively assert QUBO/Ising equality for a small binary model."""

    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and positive")
    if model.n > maximum_n:
        raise ValueError(f"exhaustive equivalence is limited to N <= {maximum_n}")
    ising = qubo_to_ising(model)
    for bits in itertools.product((0, 1), repeat=model.n):
        if abs(model.energy(bits) - ising.energy(bits)) >= tolerance:
            raise AssertionError(
                f"QUBO/Ising mismatch at bits={bits}: "
                f"{model.energy(bits)} != {ising.energy(bits)}"
            )
    return True
