"""Local-optimization, one-job-safe Qiskit QAOA execution and diagnostics."""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from repackq.models import FutureTruth
from repackq.optimization.objective import (
    OptimizationInstance,
    build_qubo,
    indices_from_bits,
    qubo_to_ising,
    verify_ising_equivalence,
)
from repackq.optimization.solvers import OptimizationResult, _make_result
from repackq.quantum.bitstrings import bits_to_qiskit_key, qiskit_key_to_bits, selected_indices
from repackq.quantum.qiskit_compat import (
    bind_qaoa_parameters,
    build_cost_operator,
    build_qaoa_ansatz,
    get_statevector,
    transpile_for_backend,
)


@dataclass(frozen=True)
class QAOAParams:
    """Project-owned parameter convention, independent of Qiskit ordering."""

    gamma: tuple[float, ...]
    beta: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.gamma or len(self.gamma) != len(self.beta):
            raise ValueError("gamma and beta must have the same positive length")
        if any(not math.isfinite(value) for value in (*self.gamma, *self.beta)):
            raise ValueError("QAOA parameters must be finite")

    @property
    def reps(self) -> int:
        return len(self.gamma)

    def to_dict(self) -> dict[str, list[float]]:
        return {"gamma": list(self.gamma), "beta": list(self.beta)}


@dataclass(frozen=True)
class _OptimizationReport:
    params: QAOAParams
    expected_energy: float
    method: str
    evaluations: int
    budget: int
    initial_expected_energy: float
    success: bool | None
    message: str
    elapsed_ms: float


@dataclass(frozen=True)
class QAOASample:
    """A distinct measured state with its decoded pack and measured mass."""

    bitstring: str
    bits: tuple[int, ...]
    selected_indices: tuple[int, ...]
    selected_cell_ids: tuple[str, ...]
    count: int
    probability: float
    cardinality: int
    feasible: bool
    objective_value: float
    qubo_energy: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "bitstring": self.bitstring,
            "bits": list(self.bits),
            "selected_indices": list(self.selected_indices),
            "selected_cell_ids": list(self.selected_cell_ids),
            "count": self.count,
            "probability": self.probability,
            "cardinality": self.cardinality,
            "feasible": self.feasible,
            "objective_value": self.objective_value,
            "qubo_energy": self.qubo_energy,
        }


@dataclass(frozen=True)
class QAOAResult:
    """Serializable QAOA diagnostics and the best measured feasible pack."""

    feasible: bool
    status_message: str
    params: QAOAParams
    expected_energy: float
    raw_counts: dict[str, int]
    probabilities: dict[str, float]
    feasible_samples: tuple[QAOASample, ...]
    modal_sample: QAOASample | None
    best_feasible_sample: QAOASample | None
    cardinality_violation_sample: QAOASample | None
    feasible_probability_mass: float
    optimum_probability_mass: float | None
    exact_optimal_objective_value: float | None
    best_feasible_optimality_gap: float | None
    recommended_result: OptimizationResult | None
    backend: str
    shots_requested: int
    shots_observed: int
    reps: int
    optimizer: dict[str, Any]
    circuit: dict[str, Any]
    penalty: dict[str, Any]
    timings_ms: dict[str, float]
    backend_jobs_submitted: int
    single_backend_job: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "qaoa",
            "feasible": self.feasible,
            "status_message": self.status_message,
            "params": self.params.to_dict(),
            "expected_energy": self.expected_energy,
            "raw_counts": dict(self.raw_counts),
            "probabilities": dict(self.probabilities),
            "feasible_samples": [sample.to_dict() for sample in self.feasible_samples],
            "modal_sample": self.modal_sample.to_dict() if self.modal_sample else None,
            "best_feasible_sample": (
                self.best_feasible_sample.to_dict() if self.best_feasible_sample else None
            ),
            "cardinality_violation_sample": (
                self.cardinality_violation_sample.to_dict()
                if self.cardinality_violation_sample
                else None
            ),
            "feasible_probability_mass": self.feasible_probability_mass,
            "optimum_probability_mass": self.optimum_probability_mass,
            "exact_optimal_objective_value": self.exact_optimal_objective_value,
            "best_feasible_optimality_gap": self.best_feasible_optimality_gap,
            "recommended_result": (
                self.recommended_result.to_dict() if self.recommended_result else None
            ),
            "backend": self.backend,
            "shots_requested": self.shots_requested,
            "shots_observed": self.shots_observed,
            "reps": self.reps,
            "optimizer": dict(self.optimizer),
            "circuit": dict(self.circuit),
            "penalty": dict(self.penalty),
            "timings_ms": dict(self.timings_ms),
            "backend_jobs_submitted": self.backend_jobs_submitted,
            "single_backend_job": self.single_backend_job,
        }


@dataclass
class QAOAPreparation:
    """Locally optimized measured circuit awaiting exactly one sampling job."""

    instance: OptimizationInstance
    qubo: Any
    params: QAOAParams
    expected_energy: float
    circuit: Any
    circuit_info: dict[str, Any]
    optimal_vectors: set[tuple[int, ...]] | None
    exact_optimal_objective: float | None
    future_truth: Sequence[FutureTruth] | None
    shots: int
    reps: int
    optimizer: dict[str, Any]
    penalty: dict[str, Any]
    timings_ms: dict[str, float]
    started_at: float


def _initial_params(reps: int) -> QAOAParams:
    return QAOAParams(
        gamma=tuple(math.pi / 4.0 for _ in range(reps)),
        beta=tuple(math.pi / 8.0 for _ in range(reps)),
    )


def _energy_for_params(circuit: Any, operator: Any, params: QAOAParams) -> float:
    bound = bind_qaoa_parameters(circuit, gamma=params.gamma, beta=params.beta)
    state = get_statevector(bound)
    value = complex(state.expectation_value(operator))
    if not math.isfinite(value.real) or abs(value.imag) > 1e-8:
        raise ValueError(f"QAOA expected cost is not a finite real value: {value!r}")
    return float(value.real)


def _grid_optimize(
    circuit: Any,
    operator: Any,
    *,
    max_evaluations: int,
) -> _OptimizationReport:
    """Deterministic 12×8 p=1 grid followed by three coordinate refinements."""

    if max_evaluations < 121:
        raise ValueError("grid optimizer needs at least 121 evaluations for the 12×8 grid and three refinements")
    started = time.perf_counter()
    initial = _initial_params(1)
    initial_energy = _energy_for_params(circuit, operator, initial)
    evaluations = 1
    seen: set[tuple[float, float]] = {
        (round(initial.gamma[0] % (2.0 * math.pi), 12), round(initial.beta[0] % math.pi, 12))
    }
    best_params: QAOAParams | None = initial
    best_energy = initial_energy

    def evaluate(gamma: float, beta: float) -> float | None:
        nonlocal evaluations, best_params, best_energy
        gamma = gamma % (2.0 * math.pi)
        beta = beta % math.pi
        key = (round(gamma, 12), round(beta, 12))
        if key in seen or evaluations >= max_evaluations:
            return None
        seen.add(key)
        params = QAOAParams((gamma,), (beta,))
        energy = _energy_for_params(circuit, operator, params)
        evaluations += 1
        if energy < best_energy - 1e-12 or (
            abs(energy - best_energy) <= 1e-12
            and (best_params is None or (params.gamma, params.beta) < (best_params.gamma, best_params.beta))
        ):
            best_params = params
            best_energy = energy
        return energy

    for gamma_index in range(12):
        for beta_index in range(8):
            evaluate(2.0 * math.pi * gamma_index / 12.0, math.pi * beta_index / 8.0)

    assert best_params is not None
    center_gamma, center_beta = best_params.gamma[0], best_params.beta[0]
    gamma_step, beta_step = math.pi / 12.0, math.pi / 16.0
    for _round in range(3):
        for gamma_delta, beta_delta in itertools.product((-1, 0, 1), repeat=2):
            if evaluations >= max_evaluations:
                break
            evaluate(
                center_gamma + gamma_delta * gamma_step,
                center_beta + beta_delta * beta_step,
            )
        assert best_params is not None
        center_gamma, center_beta = best_params.gamma[0], best_params.beta[0]
        gamma_step /= 2.0
        beta_step /= 2.0

    assert best_params is not None
    return _OptimizationReport(
        params=best_params,
        expected_energy=best_energy,
        method="coarse_to_fine_grid",
        evaluations=evaluations,
        budget=max_evaluations,
        initial_expected_energy=initial_energy,
        success=None,
        message="Completed deterministic 12×8 grid search and local coordinate refinement.",
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def _cobyla_optimize(
    circuit: Any,
    operator: Any,
    *,
    reps: int,
    max_evaluations: int,
) -> _OptimizationReport:
    try:
        from scipy.optimize import minimize
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("SciPy COBYLA was requested but SciPy is unavailable") from exc

    started = time.perf_counter()
    initial = _initial_params(reps)
    initial_vector = [*initial.gamma, *initial.beta]
    bounds = [(0.0, 2.0 * math.pi)] * reps + [(0.0, math.pi)] * reps
    evaluations = 0
    best_params: QAOAParams | None = None
    best_energy = math.inf

    def objective(vector: Sequence[float]) -> float:
        nonlocal evaluations, best_params, best_energy
        gamma = tuple(min(2.0 * math.pi, max(0.0, float(value))) for value in vector[:reps])
        beta = tuple(min(math.pi, max(0.0, float(value))) for value in vector[reps:])
        params = QAOAParams(gamma, beta)
        energy = _energy_for_params(circuit, operator, params)
        evaluations += 1
        if energy < best_energy - 1e-12 or (
            abs(energy - best_energy) <= 1e-12
            and (best_params is None or (params.gamma, params.beta) < (best_params.gamma, best_params.beta))
        ):
            best_params = params
            best_energy = energy
        return energy

    initial_energy = objective(initial_vector)
    result = minimize(
        objective,
        initial_vector,
        method="COBYLA",
        bounds=bounds,
        options={
            "maxiter": max_evaluations - 1,
            "rhobeg": 0.35,
            "tol": 1e-4,
            "catol": 1e-8,
        },
    )
    assert best_params is not None
    return _OptimizationReport(
        params=best_params,
        expected_energy=best_energy,
        method="scipy_cobyla",
        evaluations=evaluations,
        budget=max_evaluations,
        initial_expected_energy=initial_energy,
        success=bool(result.success),
        message=str(result.message),
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def optimize_qaoa_parameters(
    circuit: Any,
    cost_operator: Any,
    *,
    reps: int = 1,
    optimizer_mode: str = "auto",
    max_evaluations: int = 160,
) -> _OptimizationReport:
    """Optimize with local exact statevectors; this function never sees a backend."""

    if optimizer_mode not in {"auto", "cobyla", "grid"}:
        raise ValueError("optimizer_mode must be one of: auto, cobyla, grid")
    if isinstance(max_evaluations, bool) or not isinstance(max_evaluations, int) or max_evaluations < 2:
        raise ValueError("max_evaluations must be an integer of at least two")
    mode = optimizer_mode
    if mode == "auto":
        try:
            import scipy.optimize  # noqa: F401

            mode = "cobyla"
        except ImportError:  # pragma: no cover - optional dependency
            mode = "grid"
    if mode == "grid":
        if reps != 1:
            raise ValueError("the portable grid optimizer currently supports only p=1")
        return _grid_optimize(circuit, cost_operator, max_evaluations=max_evaluations)
    return _cobyla_optimize(
        circuit,
        cost_operator,
        reps=reps,
        max_evaluations=max_evaluations,
    )


def _run_backend_once(
    backend: Any,
    circuit: Any,
    *,
    shots: int,
    simulator_seed: int | None,
) -> tuple[dict[str, int], str]:
    run = getattr(backend, "run", None)
    if not callable(run):
        raise TypeError("backend must provide run(circuit, shots=...)")
    options: dict[str, Any] = {"shots": shots}
    if simulator_seed is not None:
        # This is an explicit caller choice. In particular, do not retry with
        # altered options: remote backends still receive at most one job call.
        options["seed_simulator"] = simulator_seed
    job = run(circuit, **options)
    result_method = getattr(job, "result", None)
    result = result_method() if callable(result_method) else job
    get_counts = getattr(result, "get_counts", None)
    if callable(get_counts):
        try:
            counts = get_counts(circuit)
        except TypeError:
            counts = get_counts()
    elif isinstance(result, dict):
        counts = result
    else:
        raise TypeError("backend result must expose get_counts() or be a count mapping")
    if not isinstance(counts, dict):
        raise TypeError("backend counts must be a mapping")

    normalized: dict[str, int] = {}
    width = int(circuit.num_clbits)
    if width < 1:
        raise ValueError("measured backend circuit must contain classical bits")
    for key, raw_count in counts.items():
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
            raise ValueError("backend counts must be nonnegative integers")
        if raw_count == 0:
            continue
        if isinstance(key, bool):
            raise ValueError("boolean measurement keys are invalid")
        if isinstance(key, int):
            if not 0 <= key < 2**width:
                raise ValueError(f"integer measurement key {key} is outside circuit width")
            key_text = format(key, f"0{width}b")
        else:
            key_text = str(key)
        bits = qiskit_key_to_bits(key_text, width)
        canonical = bits_to_qiskit_key(bits)
        normalized[canonical] = normalized.get(canonical, 0) + raw_count
    if not normalized or sum(normalized.values()) <= 0:
        raise ValueError("backend returned no measured shots")
    backend_name = getattr(backend, "name", None)
    if callable(backend_name):
        backend_name = backend_name()
    return normalized, str(backend_name or type(backend).__name__)


def _make_sample(
    instance: OptimizationInstance,
    qubo: Any,
    bitstring: str,
    count: int,
    total_shots: int,
) -> QAOASample:
    bits = qiskit_key_to_bits(bitstring, instance.n)
    selected = tuple(selected_indices(bits))
    return QAOASample(
        bitstring=bitstring,
        bits=bits,
        selected_indices=selected,
        selected_cell_ids=tuple(instance.candidate_ids[index] for index in selected),
        count=count,
        probability=count / total_shots,
        cardinality=len(selected),
        feasible=len(selected) == instance.pack_size_k,
        objective_value=instance.objective_for_indices(selected),
        qubo_energy=qubo.energy(bits),
    )


def prepare_qaoa(
    instance: OptimizationInstance,
    *,
    shots: int = 1024,
    reps: int = 1,
    optimizer_mode: str = "auto",
    max_evaluations: int = 160,
    penalty_multiplier: float = 4.0,
    exact_optimal_bitstrings: Sequence[Sequence[int]] | None = None,
    future_truth: Sequence[FutureTruth] | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> QAOAPreparation:
    """Build and optimize locally, then return one measured circuit to sample."""

    if isinstance(shots, bool) or not isinstance(shots, int) or shots < 1:
        raise ValueError("shots must be a positive integer")
    if isinstance(reps, bool) or not isinstance(reps, int) or reps < 1:
        raise ValueError("reps must be a positive integer")
    if instance.n > 12:
        raise ValueError("QAOA statevector and mandatory exhaustive mapping check support N <= 12")

    optimal_vectors: set[tuple[int, ...]] | None = None
    exact_optimal_objective: float | None = None
    if exact_optimal_bitstrings is not None:
        optimal_vectors = {
            tuple(indices_from_bits(bits, instance.n)) for bits in exact_optimal_bitstrings
        }
        if not optimal_vectors:
            raise ValueError("exact_optimal_bitstrings must contain at least one optimum")
        if any(len(vector) != instance.pack_size_k for vector in optimal_vectors):
            raise ValueError("exact optimum bitstrings must have cardinality K")
        exact_optimal_objective = min(
            instance.objective_for_indices(vector) for vector in optimal_vectors
        )
    if future_truth is not None:
        truth_ids = [item.cell_id for item in future_truth]
        if len(truth_ids) != len(set(truth_ids)):
            raise ValueError("future truth contains duplicate cell IDs")
        if set(truth_ids) != set(instance.candidate_ids):
            raise ValueError("future truth must contain exactly the candidate pool cells")

    started_at = time.perf_counter()
    timings: dict[str, float] = {}
    if on_stage is not None:
        on_stage("preparing")

    stage_started = time.perf_counter()
    qubo = build_qubo(instance, penalty_multiplier=penalty_multiplier)
    ising = qubo_to_ising(qubo)
    verify_ising_equivalence(qubo)
    cost_operator = build_cost_operator(ising)
    timings["qubo_mapping_operator_ms"] = (time.perf_counter() - stage_started) * 1000.0

    stage_started = time.perf_counter()
    ansatz = build_qaoa_ansatz(cost_operator, reps=reps)
    circuit_info = {
        "qubits": ansatz.num_qubits,
        "depth": ansatz.depth(),
        "size": ansatz.size(),
        "reps": reps,
        "measurement_depth": None,
        "transpiled_qubits": None,
        "transpiled_depth": None,
        "transpiled_size": None,
        "mapping_verified_exhaustively": True,
    }
    timings["ansatz_build_ms"] = (time.perf_counter() - stage_started) * 1000.0

    if on_stage is not None:
        on_stage("parameter_optimization")
    optimization = optimize_qaoa_parameters(
        ansatz,
        cost_operator,
        reps=reps,
        optimizer_mode=optimizer_mode,
        max_evaluations=max_evaluations,
    )
    timings["parameter_optimization_ms"] = optimization.elapsed_ms

    bound = bind_qaoa_parameters(
        ansatz,
        gamma=optimization.params.gamma,
        beta=optimization.params.beta,
    )
    circuit = bound.copy()
    circuit.name = "repackq_qaoa_measured"
    circuit.measure_all()
    circuit_info["measurement_depth"] = circuit.depth()

    return QAOAPreparation(
        instance=instance,
        qubo=qubo,
        params=optimization.params,
        expected_energy=optimization.expected_energy,
        circuit=circuit,
        circuit_info=circuit_info,
        optimal_vectors=optimal_vectors,
        exact_optimal_objective=exact_optimal_objective,
        future_truth=future_truth,
        shots=shots,
        reps=reps,
        optimizer={
            "mode": optimization.method,
            "evaluation_model": "ideal_local_statevector",
            "evaluations": optimization.evaluations,
            "evaluation_budget": optimization.budget,
            "initial_expected_energy": optimization.initial_expected_energy,
            "optimized_expected_energy": optimization.expected_energy,
            "success": optimization.success,
            "message": optimization.message,
            "seed": "deterministic_initial_point",
        },
        penalty={
            "cardinality_penalty": qubo.cardinality_penalty,
            "penalty_multiplier": qubo.penalty_multiplier,
            "calibration_doublings": qubo.calibration_doublings,
            "base_pair_scale": qubo.base_pair_scale,
            "global_minimum_feasible": True,
        },
        timings_ms=timings,
        started_at=started_at,
    )


def _normalize_counts(counts: Any, width: int) -> dict[str, int]:
    if not isinstance(counts, dict):
        raise TypeError("backend counts must be a mapping")
    normalized: dict[str, int] = {}
    for key, raw_count in counts.items():
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
            raise ValueError("backend counts must be nonnegative integers")
        if raw_count == 0:
            continue
        if isinstance(key, bool):
            raise ValueError("boolean measurement keys are invalid")
        if isinstance(key, int):
            if not 0 <= key < 2**width:
                raise ValueError(f"integer measurement key {key} is outside circuit width")
            key_text = format(key, f"0{width}b")
        else:
            key_text = str(key)
        bits = qiskit_key_to_bits(key_text, width)
        canonical = bits_to_qiskit_key(bits)
        normalized[canonical] = normalized.get(canonical, 0) + raw_count
    if not normalized or sum(normalized.values()) <= 0:
        raise ValueError("backend returned no measured shots")
    return normalized


def complete_qaoa(
    preparation: QAOAPreparation,
    counts: Any,
    backend_name: str,
    *,
    backend_sampling_ms: float = 0.0,
) -> QAOAResult:
    """Analyze measured counts for a previously prepared QAOA circuit."""

    counts = _normalize_counts(counts, int(preparation.circuit.num_clbits))
    if not math.isfinite(float(backend_sampling_ms)) or backend_sampling_ms < 0:
        raise ValueError("backend_sampling_ms must be a finite nonnegative number")
    timings = dict(preparation.timings_ms)
    timings["backend_sampling_ms"] = float(backend_sampling_ms)
    stage_started = time.perf_counter()
    instance = preparation.instance
    qubo = preparation.qubo
    total_observed = sum(counts.values())
    probabilities = {key: count / total_observed for key, count in sorted(counts.items())}
    samples = tuple(
        _make_sample(instance, qubo, bitstring, count, total_observed)
        for bitstring, count in counts.items()
    )
    feasible_samples = tuple(
        sorted(
            (sample for sample in samples if sample.feasible),
            key=lambda sample: (sample.objective_value, sample.bits),
        )
    )
    modal_sample = min(samples, key=lambda sample: (-sample.count, sample.bits))
    best_feasible = feasible_samples[0] if feasible_samples else None
    violating_samples = [sample for sample in samples if not sample.feasible]
    violation_sample = (
        min(
            violating_samples,
            key=lambda sample: (
                abs(sample.cardinality - instance.pack_size_k),
                sample.qubo_energy,
                sample.bits,
            ),
        )
        if violating_samples
        else None
    )
    feasible_mass = sum(sample.count for sample in feasible_samples) / total_observed
    optimum_mass: float | None = None
    if preparation.optimal_vectors is not None:
        optimum_mass = sum(
            sample.count
            for sample in samples
            if sample.feasible and sample.selected_indices in preparation.optimal_vectors
        ) / total_observed

    gap: float | None = None
    if best_feasible is not None and preparation.exact_optimal_objective is not None:
        gap = best_feasible.objective_value - preparation.exact_optimal_objective
        if abs(gap) < 1e-12:
            gap = 0.0

    recommended: OptimizationResult | None = None
    if best_feasible is not None:
        recommended = _make_result(
            instance,
            best_feasible.selected_indices,
            algorithm="qaoa_best_feasible_sample",
            runtime_ms=(time.perf_counter() - preparation.started_at) * 1000.0,
            future_truth=preparation.future_truth,
            metadata={
                "qaoa_bitstring": best_feasible.bitstring,
                "qaoa_sample_count": best_feasible.count,
                "qaoa_sample_probability": best_feasible.probability,
                "qaoa_expected_energy": preparation.expected_energy,
                "backend": backend_name,
                "recommended_sample_rule": "minimum_objective_among_feasible_measured_states",
            },
        )
    timings["result_diagnostics_ms"] = (time.perf_counter() - stage_started) * 1000.0
    timings["total_ms"] = (time.perf_counter() - preparation.started_at) * 1000.0

    return QAOAResult(
        feasible=best_feasible is not None,
        status_message=(
            "QAOA produced at least one feasible K-cell sample."
            if best_feasible is not None
            else "No feasible K-cell sample observed."
        ),
        params=preparation.params,
        expected_energy=preparation.expected_energy,
        raw_counts=counts,
        probabilities=probabilities,
        feasible_samples=feasible_samples,
        modal_sample=modal_sample,
        best_feasible_sample=best_feasible,
        cardinality_violation_sample=violation_sample,
        feasible_probability_mass=feasible_mass,
        optimum_probability_mass=optimum_mass,
        exact_optimal_objective_value=preparation.exact_optimal_objective,
        best_feasible_optimality_gap=gap,
        recommended_result=recommended,
        backend=backend_name,
        shots_requested=preparation.shots,
        shots_observed=total_observed,
        reps=preparation.reps,
        optimizer=dict(preparation.optimizer),
        circuit=dict(preparation.circuit_info),
        penalty=dict(preparation.penalty),
        timings_ms=timings,
        backend_jobs_submitted=1,
        single_backend_job=True,
    )


def run_qaoa(
    instance: OptimizationInstance,
    backend: Any | None = None,
    *,
    shots: int = 1024,
    reps: int = 1,
    optimizer_mode: str = "auto",
    max_evaluations: int = 160,
    penalty_multiplier: float = 4.0,
    single_backend_job: bool = True,
    exact_optimal_bitstrings: Sequence[Sequence[int]] | None = None,
    future_truth: Sequence[FutureTruth] | None = None,
    simulator_seed: int | None = None,
    transpiler_seed: int | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> QAOAResult:
    """Run QAOA with local optimization and one final backend sampling job."""

    if not isinstance(single_backend_job, bool):
        raise ValueError("single_backend_job must be a boolean")
    if not single_backend_job:
        raise ValueError("Task 5 supports local optimization followed by one backend sampling job")
    for value, name in ((simulator_seed, "simulator_seed"), (transpiler_seed, "transpiler_seed")):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"{name} must be an integer or None")

    preparation = prepare_qaoa(
        instance,
        shots=shots,
        reps=reps,
        optimizer_mode=optimizer_mode,
        max_evaluations=max_evaluations,
        penalty_multiplier=penalty_multiplier,
        exact_optimal_bitstrings=exact_optimal_bitstrings,
        future_truth=future_truth,
        on_stage=on_stage,
    )
    if on_stage is not None:
        on_stage("sampling")
    stage_started = time.perf_counter()
    if backend is None:
        from qiskit.providers.basic_provider import BasicSimulator

        backend = BasicSimulator()
    transpiled = transpile_for_backend(preparation.circuit, backend, seed=transpiler_seed)
    preparation.circuit_info["transpiled_depth"] = transpiled.depth()
    preparation.circuit_info["transpiled_qubits"] = transpiled.num_qubits
    preparation.circuit_info["transpiled_size"] = transpiled.size()
    preparation.timings_ms["transpilation_ms"] = (time.perf_counter() - stage_started) * 1000.0

    stage_started = time.perf_counter()
    counts, backend_name = _run_backend_once(
        backend,
        transpiled,
        shots=shots,
        simulator_seed=simulator_seed,
    )
    result = complete_qaoa(
        preparation,
        counts,
        backend_name,
        backend_sampling_ms=(time.perf_counter() - stage_started) * 1000.0,
    )
    if on_stage is not None:
        on_stage("complete")
    return result


__all__ = [
    "QAOAParams",
    "QAOAResult",
    "QAOASample",
    "optimize_qaoa_parameters",
    "run_qaoa",
]
