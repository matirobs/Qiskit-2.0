"""Battery-matching objective, QUBO/Ising tools, and classical baselines."""

from repackq.optimization.normalization import FeatureScaling, normalize_bounded_soh, robust_scale
from repackq.optimization.objective import (
    OBJECTIVE_MODES,
    IsingModel,
    ObjectiveBreakdown,
    OptimizationInstance,
    QUBOModel,
    bits_from_indices,
    build_optimization_instance,
    build_qubo,
    indices_from_bits,
    qubo_to_ising,
    verify_ising_equivalence,
)
from repackq.optimization.solvers import (
    OptimizationResult,
    compatibility_greedy,
    exact_enumeration,
    simulated_annealing,
    soh_sort,
)

__all__ = [
    "FeatureScaling",
    "IsingModel",
    "OBJECTIVE_MODES",
    "ObjectiveBreakdown",
    "OptimizationInstance",
    "OptimizationResult",
    "QUBOModel",
    "bits_from_indices",
    "build_optimization_instance",
    "build_qubo",
    "compatibility_greedy",
    "exact_enumeration",
    "indices_from_bits",
    "normalize_bounded_soh",
    "qubo_to_ising",
    "robust_scale",
    "simulated_annealing",
    "soh_sort",
    "verify_ising_equivalence",
]
