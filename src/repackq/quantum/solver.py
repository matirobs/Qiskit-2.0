"""Tune angles locally, then sample each Qiskit circuit once."""
from dataclasses import dataclass
from importlib.util import find_spec
from itertools import combinations
import math
from time import perf_counter

from repackq.classical.common import ranking, result
from .bitstrings import qiskit_key_to_bits, selected_indices
from .circuits import build_circuit

ALGORITHMS = ("qaoa_penalty", "qaoa_swap")


def capabilities():
    available = find_spec("qiskit") is not None
    return {"available": available, "status": "ready" if available else "not_installed",
            "algorithms": list(ALGORITHMS),
            "message": "Qiskit local simulator ready" if available else
                       "Install quantum support: python3 -m pip install -e '.[quantum]'"}


@dataclass
class PreparedRun:
    instance: object
    algorithm: str
    circuit: object
    metadata: dict
    started: float


def prepare_qaoa(instance, *, algorithm="qaoa_penalty", seed=11, reps=None,
                 optimizer="auto", max_evaluations=160):
    """Finish classical angle tuning before submitting any backend job."""
    if algorithm not in ALGORITHMS:
        raise ValueError("Unknown quantum algorithm")
    if optimizer not in ("auto", "grid", "cobyla"):
        raise ValueError("Unknown angle optimizer")
    if type(max_evaluations) is not int or not 96 <= max_evaluations <= 2000:
        raise ValueError("Angle evaluation budget must be between 96 and 2000")
    if type(seed) is not int or not 0 <= seed < 2 ** 32:
        raise ValueError("Seed must be a nonnegative 32-bit integer")
    if not capabilities()["available"]:
        raise ValueError(capabilities()["message"])
    import numpy as np
    from qiskit.quantum_info import Statevector
    started = perf_counter()
    reps = (2 if algorithm == "qaoa_swap" else 1) if reps is None else reps
    circuit, gammas, betas, operator, qubo, scale = build_circuit(instance, algorithm, reps)
    parameters = gammas + betas
    # expand preparation once instead of synthesizing it at every angle trial
    template = circuit.decompose(reps=2)
    evaluations, best_value, best_angles = 0, math.inf, None

    def bind(angles):
        return template.assign_parameters(dict(zip(parameters, angles)))

    def expected(angles):
        nonlocal evaluations, best_value, best_angles
        state = Statevector.from_instruction(bind(angles))
        value = float(state.expectation_value(operator).real)
        evaluations += 1
        if value < best_value:
            best_value, best_angles = value, np.array(angles, dtype=float)
        return value

    # shared rough search; no measured future or exact-best pack enters tuning
    for g in np.linspace(0, 2 * np.pi, 12, endpoint=False):
        for b in np.linspace(0, np.pi, 8, endpoint=False):
            expected([g] * reps + [b] * reps)
    method = "grid"
    if optimizer != "grid" and find_spec("scipy") is not None and max_evaluations - evaluations >= 2 * reps + 2:
        from scipy.optimize import minimize
        method = "cobyla"
        minimize(expected, best_angles, method="COBYLA",
                 options={"maxiter": max_evaluations - evaluations, "rhobeg": .5})
    elif optimizer == "cobyla" and find_spec("scipy") is None:
        raise ValueError("COBYLA requires SciPy; use --optimizer grid")
    else:
        step = np.pi / 8
        while evaluations < max_evaluations and step > 1e-5:
            improved = False
            for i in range(2 * reps):
                for sign in (-1, 1):
                    if evaluations >= max_evaluations:
                        break
                    angles = best_angles.copy()
                    angles[i] += sign * step
                    before = best_value
                    expected(angles)
                    improved |= best_value < before
            if not improved:
                step /= 2
    bound = bind(best_angles)
    probabilities = Statevector.from_instruction(bound).probabilities()
    feasible_mass = float(sum(p for mask, p in enumerate(probabilities)
                              if mask.bit_count() == instance.pack_size))
    bound.measure_all()
    metadata = {"framework": "Qiskit", "seed": seed, "reps": reps, "optimizer": method,
                "optimizer_evaluations": evaluations, "max_evaluations": max_evaluations,
                "gammas": best_angles[:reps].tolist(), "betas": best_angles[reps:].tolist(),
                "expected_cost": best_value, "angle_cost_scale": scale,
                "cardinality_penalty": qubo["cardinality_penalty"],
                "statevector_feasible_probability": feasible_mass,
                "optimization_ms": (perf_counter() - started) * 1000,
                "qubits": bound.num_qubits, "circuit_depth": bound.depth(),
                "gate_counts": dict(bound.count_ops())}
    return PreparedRun(instance, algorithm, bound, metadata, started)


def finish_qaoa(prepared, counts, *, backend, shots, sampling_ms=0.0):
    """Recommend the best valid measured group; never repair an invalid sample."""
    instance = prepared.instance
    if not counts or any(type(value) is not int or value <= 0 for value in counts.values()):
        raise ValueError("Backend returned invalid measurement counts")
    if sum(counts.values()) != shots:
        raise ValueError("Backend shot count does not match the request")
    samples = []
    for key, count in counts.items():
        indices = selected_indices(qiskit_key_to_bits(key, len(instance.cells)))
        if len(indices) == instance.pack_size:
            samples.append({"bitstring": key, "selected_indices": indices,
                            "objective_value": instance.energy(indices), "count": count,
                            "probability": count / shots})
    samples.sort(key=lambda row: ranking(instance, row["selected_indices"]))
    modal = max(counts, key=lambda key: (counts[key], key))
    # exact search is a diagnostic after sampling, never an angle-training target
    optimum = min(instance.energy(group) for group in
                  combinations(range(len(instance.cells)), instance.pack_size))
    metadata = {**prepared.metadata, "backend": backend, "execution": "live_simulator",
                "shots": shots, "backend_jobs": 1, "sampling_ms": sampling_ms,
                "counts": counts, "probabilities": {key: value / shots for key, value in counts.items()},
                "feasible_fraction": sum(row["count"] for row in samples) / shots,
                "sampled_optimal_fraction": sum(row["count"] for row in samples
                    if abs(row["objective_value"] - optimum) <= 1e-9) / shots,
                "most_probable_bitstring": modal, "feasible_samples": samples,
                "best_feasible_bitstring": samples[0]["bitstring"] if samples else None}
    selection = result(instance, prepared.algorithm, samples[0]["selected_indices"],
                       prepared.started, **metadata) if samples else None
    return {"algorithm": prepared.algorithm, "status": "computed" if samples else "no_feasible_sample",
            "selection": selection, "diagnostics": metadata}


def run_qaoa(instance, *, algorithm="qaoa_penalty", backend=None, shots=1024, seed=11,
             reps=None, optimizer="auto", max_evaluations=160):
    """Use Qiskit's free local sampler or an injected synchronous backend."""
    if type(shots) is not int or not 1 <= shots <= 100000:
        raise ValueError("Shots must be between one and 100000")
    prepared = prepare_qaoa(instance, algorithm=algorithm, seed=seed, reps=reps,
                            optimizer=optimizer, max_evaluations=max_evaluations)
    started = perf_counter()
    if backend is None:
        from qiskit.primitives import StatevectorSampler
        sampled = StatevectorSampler(seed=seed).run([prepared.circuit], shots=shots).result()
        counts = sampled[0].data.meas.get_counts()
        label = "qiskit.primitives.StatevectorSampler"
    else:
        from qiskit import transpile
        circuit = transpile(prepared.circuit, backend, seed_transpiler=seed)
        counts = backend.run(circuit, shots=shots).result().get_counts()
        label = backend.name
        label = label() if callable(label) else label
    return finish_qaoa(prepared, counts, backend=label, shots=shots,
                       sampling_ms=(perf_counter() - started) * 1000)


def run_both(instance, **settings):
    return [run_qaoa(instance, algorithm=algorithm, **settings) for algorithm in ALGORITHMS]
