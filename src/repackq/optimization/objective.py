"""Score battery groups using known measurements and predicted capacity.

Recorded future capacity is excluded. These weights describe our matching
objective, not a physical model of pack lifetime."""
from dataclasses import asdict, dataclass
from itertools import combinations
import math
from typing import Mapping

from .normalize import normalize


@dataclass(frozen=True)
class CellSnapshot:
    cell_id: str
    capacity_ah: float
    nominal_capacity_ah: float = 2.4
    internal_resistance_ohm: float | None = None
    predicted_capacity_ah: float | None = None
    prediction_uncertainty_ah: float | None = None
    temperature_c: float | None = None

    @property
    def soh(self):
        """State of health: measured capacity divided by nominal capacity."""
        return self.capacity_ah / self.nominal_capacity_ah

    @classmethod
    def from_mapping(cls, snapshot: Mapping):
        """Accept predictor snapshots, discarding unrelated fields explicitly."""
        fields = cls.__dataclass_fields__
        return cls(**{name: snapshot[name] for name in fields if name in snapshot})


@dataclass(frozen=True)
class MissionWeights:
    current: float = .30
    resistance: float = .20
    future: float = .35
    health: float = .10
    uncertainty: float = .05
    temperature: float = 0.0


@dataclass(frozen=True)
class OptimizationInstance:
    cells: tuple[CellSnapshot, ...]
    pack_size: int
    mode: str
    unary: tuple[float, ...]
    pair: tuple[tuple[float, ...], ...]
    components: dict
    metadata: dict

    def validate_selection(self, selected, *, require_size=False):
        """Reject repeated, out-of-range, or incorrectly sized selections."""
        selected = tuple(selected)
        if any(type(i) is not int or not 0 <= i < len(self.cells) for i in selected):
            raise ValueError("Selected indices must be distinct integers inside the pool")
        if len(set(selected)) != len(selected):
            raise ValueError("Selected indices must be distinct")
        if require_size and len(selected) != self.pack_size:
            raise ValueError(f"Select exactly {self.pack_size} cells")
        return tuple(sorted(selected))

    def energy(self, selected):
        """Score the group without a size penalty; partial groups are allowed."""
        selected = self.validate_selection(selected)
        return math.fsum([self.unary[i] for i in selected] +
                         [self.pair[i][j] for i, j in combinations(selected, 2)])

    def breakdown(self, selected):
        """Separate pairwise mismatch costs from per-cell rewards and penalties."""
        selected = self.validate_selection(selected)
        result = {}
        for name, costs in self.components.items():
            result[name] = math.fsum(costs[i][j] for i, j in combinations(selected, 2)) \
                if name.endswith("mismatch") else math.fsum(costs[i] for i in selected)
        result["cardinality_penalty"] = 0.0
        result["total"] = math.fsum(result.values())
        return result

    def qubo(self, *, penalty_multiplier=4.0, max_states=65536):
        """Export quadratic unconstrained binary optimization coefficients.

        Store each pair once, including the constant offset. Check all states
        within the budget to make sure global minima have the requested size."""
        if not math.isfinite(penalty_multiplier) or penalty_multiplier <= 0:
            raise ValueError("Penalty multiplier must be finite and positive")
        size = len(self.cells)
        if 2 ** size > max_states:
            raise ValueError("Pool exceeds exhaustive penalty-calibration budget")
        penalty = penalty_multiplier * max(1.0, *(abs(u) for u in self.unary),
                                           *(v for row in self.pair for v in row))
        # include wrong-size states when checking whether the size penalty is strong enough
        states = [(tuple(i for i in range(size) if mask & (1 << i))) for mask in range(2 ** size)]
        energies = [(selected, self.energy(selected)) for selected in states]
        best_feasible = min(energy for selected, energy in energies if len(selected) == self.pack_size)
        for attempt in range(6):
            infeasible = min((energy + penalty * (len(selected) - self.pack_size) ** 2
                              for selected, energy in energies if len(selected) != self.pack_size),
                             default=math.inf)
            if infeasible > best_feasible + 1e-9:
                return {"linear": [u + penalty * (1 - 2 * self.pack_size) for u in self.unary],
                        "quadratic": [[i, j, self.pair[i][j] + 2 * penalty]
                                      for i, j in combinations(range(size), 2)],
                        "constant": penalty * self.pack_size ** 2,
                        "cardinality_penalty": penalty, "calibration_doublings": attempt,
                        "variable_cell_ids": [cell.cell_id for cell in self.cells]}
            penalty *= 2
        raise ValueError("Unable to calibrate a feasible global minimum after five doublings")


def build_instance(cells, pack_size=4, *, mode="trajectory_aware", weights=None):
    """Build the same scoring problem for every solver.

    Missing optional measurements disable that term across the pool and
    renormalize weights. Current-only mode does not read predicted values."""
    cells = tuple(cells)
    if type(pack_size) is not int or not 1 <= pack_size <= len(cells):
        raise ValueError("Pack size must be between one and the candidate count")
    if mode not in ("current_only", "trajectory_aware"):
        raise ValueError("Unknown objective mode")
    if any(not isinstance(c.cell_id, str) or not c.cell_id for c in cells):
        raise ValueError("Cell identifiers must be nonempty strings")
    if len({c.cell_id for c in cells}) != len(cells):
        raise ValueError("Cell identifiers must be unique")
    for cell in cells:
        if not all(math.isfinite(x) and x > 0 for x in (cell.capacity_ah, cell.nominal_capacity_ah)):
            raise ValueError("Current and nominal capacities must be finite and positive")
    requested = asdict(weights or MissionWeights())
    if any(not math.isfinite(w) or w < 0 for w in requested.values()):
        raise ValueError("Weights must be finite and nonnegative")
    active = dict(requested)
    disabled = {}
    if mode == "current_only":
        for name in ("future", "uncertainty", "temperature"):
            active[name] = 0.0
            disabled[name] = "disabled in current-only objective"
    fields = {"current": "capacity_ah", "resistance": "internal_resistance_ohm",
              "future": "predicted_capacity_ah", "temperature": "temperature_c",
              "uncertainty": "prediction_uncertainty_ah"}
    scaled = {}
    for name, field in fields.items():
        if active[name] == 0:
            continue
        values = [getattr(cell, field) for cell in cells]
        if any(v is None for v in values):
            if name == "future":
                raise ValueError("Trajectory-aware scoring requires a forecast for every cell")
            active[name] = 0.0
            disabled[name] = "missing for at least one candidate"
            continue
        if any(not math.isfinite(v) for v in values):
            raise ValueError(f"Non-finite {field}")
        if name in ("resistance", "uncertainty") and any(v < 0 for v in values):
            raise ValueError(f"Negative {field}")
        if name == "future" and any(not 0 <= v <= c.capacity_ah for c, v in zip(cells, values)):
            raise ValueError("Forecast capacity must be between zero and current capacity")
        scaled[name] = normalize(values, unit_interval=name == "uncertainty")
    total_weight = math.fsum(active.values())
    if total_weight <= 0:
        raise ValueError("At least one available objective weight must be positive")
    active = {name: value / total_weight for name, value in active.items()}
    size = len(cells)
    pair_components = {}
    for name, label in (("current", "capacity"), ("resistance", "resistance"),
                        ("future", "future"), ("temperature", "temperature")):
        values = scaled[name].values if name in scaled else (0.0,) * size
        pair_components[label + "_mismatch"] = tuple(tuple(
            active[name] * (values[i] - values[j]) ** 2 for j in range(size)) for i in range(size))
    # health is a reward, so it lowers the score; uncertainty raises it
    health = tuple(-active["health"] * min(1.0, c.soh) for c in cells)
    uncertainties = scaled["uncertainty"].values if "uncertainty" in scaled else (0.0,) * size
    risk = tuple(active["uncertainty"] * v for v in uncertainties)
    unary = tuple(health[i] + risk[i] for i in range(size))
    pair = tuple(tuple(math.fsum(matrix[i][j] for matrix in pair_components.values())
                       for j in range(size)) for i in range(size))
    if not all(math.isfinite(v) for v in unary) or not all(math.isfinite(v) for row in pair for v in row):
        raise ValueError("Objective overflow; check feature magnitudes")
    metadata = {"requested_weights": requested, "effective_weights": active, "disabled_features": disabled,
                "normalization": {name: {k: v for k, v in asdict(feature).items() if k != "values"}
                                  for name, feature in scaled.items()},
                "health_reward": "capacity / nominal capacity, capped at 1",
                "uncertainty": "pool-scaled model residual; not a confidence interval"}
    return OptimizationInstance(cells, pack_size, mode, unary, pair,
                                {**pair_components, "health_reward": health, "uncertainty_penalty": risk}, metadata)
