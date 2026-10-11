"""Small Qiskit helpers verified against the local Task 1 environment.

The backend is injected instead of constructed here so a Qollab-provided
backend can be passed through without credentials or platform assumptions.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import math
from typing import Any

from repackq.optimization.objective import IsingModel
from repackq.quantum.bitstrings import qiskit_key_to_bits


class QiskitUnavailableError(RuntimeError):
    """Raised when a Qiskit operation is requested without Qiskit installed."""


def get_qiskit_version() -> str | None:
    """Return the installed Qiskit distribution version, if available."""
    try:
        return version("qiskit")
    except PackageNotFoundError:
        return None


def _qiskit_types() -> tuple[Any, Any]:
    try:
        from qiskit import QuantumCircuit
        from qiskit.providers.basic_provider import BasicSimulator
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise QiskitUnavailableError(
            "Qiskit is required. Install the pinned dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc
    return QuantumCircuit, BasicSimulator


def _qiskit_quantum_types() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from qiskit import QuantumCircuit, transpile
        from qiskit.circuit import Parameter
        from qiskit.quantum_info import SparsePauliOp, Statevector
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise QiskitUnavailableError(
            "This Qiskit operation requires QuantumCircuit, SparsePauliOp, "
            "and Statevector from the pinned Qiskit installation."
        ) from exc
    return QuantumCircuit, Parameter, SparsePauliOp, Statevector, transpile


def build_cost_operator(ising: IsingModel) -> Any:
    """Build Qiskit's diagonal cost operator for a project Ising model.

    Project bit/qubit index zero maps to the rightmost Pauli-label character,
    following Qiskit's little-endian Pauli convention.
    """

    if ising.n < 1:
        raise ValueError("an Ising cost operator requires at least one qubit")
    if not math.isfinite(ising.offset) or any(not math.isfinite(value) for value in ising.h):
        raise ValueError("Ising coefficients must be finite")
    QuantumCircuit, Parameter, SparsePauliOp, Statevector, transpile = _qiskit_quantum_types()
    del QuantumCircuit, Parameter, Statevector, transpile

    terms: list[tuple[str, float]] = []
    identity = "I" * ising.n
    if ising.offset != 0.0:
        terms.append((identity, float(ising.offset)))
    for qubit, coefficient in enumerate(ising.h):
        if not math.isfinite(coefficient):
            raise ValueError("Ising coefficients must be finite")
        if coefficient != 0.0:
            label = ["I"] * ising.n
            label[ising.n - 1 - qubit] = "Z"
            terms.append(("".join(label), float(coefficient)))
    for pair, coefficient in sorted(ising.couplings.items()):
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or isinstance(pair[0], bool)
            or isinstance(pair[1], bool)
            or not isinstance(pair[0], int)
            or not isinstance(pair[1], int)
            or not 0 <= pair[0] < pair[1] < ising.n
        ):
            raise ValueError(f"invalid Ising coupling indices: {pair!r}")
        if not math.isfinite(coefficient):
            raise ValueError("Ising coefficients must be finite")
        if coefficient != 0.0:
            label = ["I"] * ising.n
            label[ising.n - 1 - pair[0]] = "Z"
            label[ising.n - 1 - pair[1]] = "Z"
            terms.append(("".join(label), float(coefficient)))
    if not terms:
        terms.append((identity, 0.0))
    return SparsePauliOp.from_list(terms).simplify()


def build_qaoa_ansatz(cost_operator: Any, reps: int = 1) -> Any:
    """Build a standard Hadamard/X-mixer QAOA ansatz for a diagonal cost."""

    if isinstance(reps, bool) or not isinstance(reps, int) or reps < 1:
        raise ValueError("reps must be a positive integer")
    QuantumCircuit, Parameter, SparsePauliOp, Statevector, transpile = _qiskit_quantum_types()
    del SparsePauliOp, Statevector, transpile
    try:
        n = int(cost_operator.num_qubits)
        terms = cost_operator.to_list()
    except (AttributeError, TypeError, ValueError) as exc:
        raise TypeError("cost_operator must be a Qiskit Pauli operator") from exc
    if n < 1:
        raise ValueError("cost_operator must contain at least one qubit")

    gamma = tuple(Parameter(f"gamma_{layer}") for layer in range(reps))
    beta = tuple(Parameter(f"beta_{layer}") for layer in range(reps))
    circuit = QuantumCircuit(n, name=f"repackq_qaoa_p{reps}")
    circuit.h(range(n))
    for layer in range(reps):
        for label, raw_coefficient in terms:
            coefficient = complex(raw_coefficient)
            if abs(coefficient.imag) > 1e-12:
                raise ValueError("QAOA cost operator must be Hermitian with real coefficients")
            support: list[int] = []
            for position, pauli in enumerate(label):
                if pauli == "Z":
                    support.append(n - 1 - position)
                elif pauli != "I":
                    raise ValueError("QAOA cost operator must be diagonal (I/Z terms only)")
            if not support or abs(coefficient.real) <= 1e-15:
                # Identity terms contribute only a global phase.
                continue
            if len(support) == 1:
                circuit.rz(2.0 * coefficient.real * gamma[layer], support[0])
                continue
            target = support[-1]
            for control in support[:-1]:
                circuit.cx(control, target)
            circuit.rz(2.0 * coefficient.real * gamma[layer], target)
            for control in reversed(support[:-1]):
                circuit.cx(control, target)
        for qubit in range(n):
            circuit.rx(2.0 * beta[layer], qubit)
    return circuit


def bind_qaoa_parameters(
    circuit: Any,
    *,
    gamma: tuple[float, ...] | list[float],
    beta: tuple[float, ...] | list[float],
) -> Any:
    """Bind named gamma/beta parameters without depending on set ordering."""

    if len(gamma) != len(beta) or not gamma:
        raise ValueError("gamma and beta must have the same positive length")
    by_name = {parameter.name: parameter for parameter in circuit.parameters}
    expected = {f"gamma_{layer}" for layer in range(len(gamma))}
    expected |= {f"beta_{layer}" for layer in range(len(beta))}
    if set(by_name) != expected:
        raise ValueError("circuit parameters do not match the RePack-Q gamma/beta convention")
    bindings = {
        by_name[f"gamma_{layer}"]: float(value)
        for layer, value in enumerate(gamma)
    }
    bindings.update(
        {
            by_name[f"beta_{layer}"]: float(value)
            for layer, value in enumerate(beta)
        }
    )
    return circuit.assign_parameters(bindings, inplace=False)


def get_statevector(circuit: Any) -> Any:
    """Return the exact state produced by an unmeasured Qiskit circuit."""

    QuantumCircuit, Parameter, SparsePauliOp, Statevector, transpile = _qiskit_quantum_types()
    del QuantumCircuit, Parameter, SparsePauliOp, transpile
    if circuit.parameters:
        raise ValueError("statevector circuit must have all parameters bound")
    if circuit.num_clbits:
        raise ValueError("statevector circuit must not contain classical bits")
    return Statevector.from_instruction(circuit)


def transpile_for_backend(circuit: Any, backend: Any, *, seed: int | None = None) -> Any:
    """Transpile one final circuit for the injected Qiskit-compatible backend."""

    QuantumCircuit, Parameter, SparsePauliOp, Statevector, transpile = _qiskit_quantum_types()
    del QuantumCircuit, Parameter, SparsePauliOp, Statevector
    options: dict[str, Any] = {"backend": backend, "optimization_level": 1}
    if seed is not None:
        options["seed_transpiler"] = seed
    try:
        return transpile(circuit, **options)
    except (TypeError, AttributeError, ValueError) as exc:
        raise TypeError(
            "backend must expose a Qiskit target/backend for circuit transpilation"
        ) from exc


def make_smoke_circuit() -> Any:
    """Build a deterministic two-qubit circuit that measures q0 as one.

    Qiskit prints classical bits with the highest-index bit on the left, so
    measuring X on q0 and zero on q1 is returned as the string ``"01"``.
    """
    QuantumCircuit, _ = _qiskit_types()
    circuit = QuantumCircuit(2, 2, name="repackq_bit_order_smoke")
    circuit.x(0)
    circuit.measure([0, 1], [0, 1])
    return circuit


def make_known_state_circuit() -> Any:
    """Prepare and measure the known qubit-index state q0=q2=1 (four qubits)."""

    QuantumCircuit, _ = _qiskit_types()
    circuit = QuantumCircuit(4, 4, name="repackq_bit_order_q0_q2")
    circuit.x(0)
    circuit.x(2)
    circuit.measure(range(4), range(4))
    return circuit


def decode_qiskit_bitstring(bitstring: str, num_bits: int) -> list[int]:
    """Decode a single Qiskit register string into bit-index order.

    Spaces are accepted for Qiskit results containing multiple classical
    registers. The returned list is ordered ``c[0], c[1], ...``.
    """
    return list(qiskit_key_to_bits(bitstring, num_bits))


def _display_counts(counts: dict[Any, Any]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for state, count in counts.items():
        if isinstance(state, int):
            # Integer keys are common in simulator results; format to the
            # expected width in the caller after reading this mapping.
            key = format(state, "b")
        else:
            key = str(state)
        normalized[key] = int(count)
    return normalized


def _result_counts(job_result: Any, circuit: Any) -> dict[str, int]:
    if isinstance(job_result, dict):
        counts = job_result
    else:
        get_counts = getattr(job_result, "get_counts", None)
        if not callable(get_counts):
            raise TypeError("Backend result does not provide get_counts().")
        try:
            counts = get_counts(circuit)
        except TypeError:
            # Some backend-compatible result objects expose only no-arg form.
            counts = get_counts()
    if not isinstance(counts, dict):
        raise TypeError("Backend get_counts() must return a count dictionary.")
    normalized = _display_counts(counts)
    if any(" " in state for state in normalized):
        raise ValueError("Smoke test expects one classical register.")
    width = circuit.num_clbits
    return {state.zfill(width): count for state, count in normalized.items()}


def run_smoke_test(backend: Any | None = None, shots: int = 32) -> dict[str, Any]:
    """Run the deterministic X-on-q0 circuit on an injected or local backend.

    The default uses Qiskit's bundled ``BasicSimulator``. An injected backend
    needs only the public ``run(circuit, shots=...)`` job interface and a
    result that exposes ``get_counts``. Backend setup and authentication are
    intentionally left to the host application.
    """
    if shots < 1:
        raise ValueError("shots must be a positive integer")
    QuantumCircuit, BasicSimulator = _qiskit_types()
    del QuantumCircuit  # Circuit construction already validated the import.
    circuit = make_smoke_circuit()
    selected_backend = backend if backend is not None else BasicSimulator()
    run = getattr(selected_backend, "run", None)
    if not callable(run):
        raise TypeError("Backend must provide run(circuit, shots=...).")

    job = run(circuit, shots=shots)
    result = job.result() if callable(getattr(job, "result", None)) else job
    counts = _result_counts(result, circuit)
    expected = {"01": shots}
    if counts != expected:
        raise AssertionError(
            f"Deterministic smoke circuit returned {counts}, expected {expected}."
        )

    name = getattr(selected_backend, "name", None)
    if callable(name):
        name = name()
    if name is None:
        name = type(selected_backend).__name__
    return {
        "ok": True,
        "qiskit_version": get_qiskit_version(),
        "backend": str(name),
        "shots": shots,
        "counts": counts,
        "display_bitstring": "01",
        "decoded_qubit_bits": decode_qiskit_bitstring("01", 2),
        "bit_order": "Qiskit display order is c[1] c[0]; decoded list is [c[0], c[1]].",
    }


def run_bit_order_sanity(backend: Any | None = None, shots: int = 32) -> dict[str, Any]:
    """Check candidate/qubit decoding on the deterministic q0/q2 state."""

    if shots < 1:
        raise ValueError("shots must be a positive integer")
    _, BasicSimulator = _qiskit_types()
    circuit = make_known_state_circuit()
    selected_backend = backend if backend is not None else BasicSimulator()
    run = getattr(selected_backend, "run", None)
    if not callable(run):
        raise TypeError("Backend must provide run(circuit, shots=...).")
    job = run(circuit, shots=shots)
    result = job.result() if callable(getattr(job, "result", None)) else job
    counts = _result_counts(result, circuit)
    if sum(counts.values()) != shots or len(counts) != 1:
        raise AssertionError(f"Known-state circuit returned unexpected counts: {counts}")
    bitstring = next(iter(counts))
    bits = qiskit_key_to_bits(bitstring, 4)
    selected = [index for index, bit in enumerate(bits) if bit]
    if selected != [0, 2]:
        raise AssertionError(f"Known-state circuit decoded {selected}, expected [0, 2].")
    name = getattr(selected_backend, "name", None)
    if callable(name):
        name = name()
    return {
        "ok": True,
        "backend": str(name or type(selected_backend).__name__),
        "shots": shots,
        "counts": counts,
        "display_bitstring": bitstring,
        "decoded_qubit_bits": list(bits),
        "selected_indices": selected,
    }


def get_capabilities() -> dict[str, Any]:
    """Describe locally available Qiskit support without starting a job."""
    qiskit_version = get_qiskit_version()
    capabilities: dict[str, Any] = {
        "qiskit_available": qiskit_version is not None,
        "qiskit_version": qiskit_version,
        "numpy_available": False,
        "scipy_available": False,
        "statevector_available": False,
        "qollab_bridge_available": None,
        "local_backend": "qiskit.providers.basic_provider.BasicSimulator",
        "backend_contract": "backend.run(circuit, shots=...).result().get_counts(circuit)",
    }
    try:
        from importlib.util import find_spec

        capabilities["numpy_available"] = find_spec("numpy") is not None
        capabilities["scipy_available"] = find_spec("scipy") is not None
        capabilities["statevector_available"] = find_spec("qiskit.quantum_info") is not None
    except (ImportError, ValueError):  # pragma: no cover - unusual import state
        pass
    return capabilities
