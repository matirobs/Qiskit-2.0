"""Selection results shared by all solvers. Runtime covers the solver only."""
from dataclasses import asdict, dataclass
from time import perf_counter

from repackq.optimization.objective import OptimizationInstance


@dataclass(frozen=True)
class SelectionResult:
    algorithm: str
    selected_indices: tuple[int, ...]
    selected_cell_ids: tuple[str, ...]
    feasible: bool
    objective_value: float
    runtime_ms: float
    objective_breakdown: dict
    metadata: dict

    def to_dict(self):
        return asdict(self)


def result(instance: OptimizationInstance, algorithm, selected, started, **metadata):
    """Validate the chosen indices and attach the shared score and elapsed time."""
    selected = instance.validate_selection(selected, require_size=True)
    return SelectionResult(algorithm, selected, tuple(instance.cells[i].cell_id for i in selected),
                           True, instance.energy(selected), (perf_counter() - started) * 1000,
                           instance.breakdown(selected), metadata)


def ranking(instance, selected):
    """Objective first, then stable cell identifiers for reproducible ties."""
    selected = instance.validate_selection(selected)
    return instance.energy(selected), tuple(sorted(instance.cells[i].cell_id for i in selected))
