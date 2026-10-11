"""Build both circuits from the same battery-group objective."""
from itertools import combinations
import math


def qubo_to_ising(qubo):
    """Substitute x = (1 - Z) / 2, keeping the constant energy shift."""
    linear = qubo["linear"]
    z = [-value / 2 for value in linear]
    zz = []
    offset = qubo["constant"] + sum(linear) / 2
    for i, j, value in qubo["quadratic"]:
        z[i] -= value / 4
        z[j] -= value / 4
        zz.append((i, j, value / 4))
        offset += value / 4
    return z, zz, offset


def cost_operator(qubo):
    """Qiskit labels put candidate zero at the right end."""
    from qiskit.quantum_info import SparsePauliOp
    z, zz, offset = qubo_to_ising(qubo)
    n = len(z)
    terms = [("I" * n, offset)]
    for indices, value in [*(([i], v) for i, v in enumerate(z)),
                           *(([i, j], v) for i, j, v in zz)]:
        label = ["I"] * n
        for i in indices:
            label[n - 1 - i] = "Z"
        terms.append(("".join(label), value))
    return SparsePauliOp.from_list(terms).simplify()


def objective_qubo(instance, algorithm):
    """Only the standard mixer needs a penalty for selecting the wrong count."""
    if algorithm == "qaoa_penalty":
        return instance.qubo()
    if algorithm != "qaoa_swap":
        raise ValueError("Unknown quantum algorithm")
    return {"linear": list(instance.unary),
            "quadratic": [[i, j, instance.pair[i][j]]
                          for i, j in combinations(range(len(instance.cells)), 2)],
            "constant": 0.0, "cardinality_penalty": 0.0,
            "variable_cell_ids": [cell.cell_id for cell in instance.cells]}


def build_circuit(instance, algorithm, reps=1):
    """Return the template, named parameters, and unscaled scoring operator."""
    import numpy as np
    from qiskit import QuantumCircuit
    from qiskit.circuit import ParameterVector
    from qiskit.circuit.library import StatePreparation, XXPlusYYGate
    if type(reps) is not int or not 1 <= reps <= 3:
        raise ValueError("Quantum depth must be between one and three")
    n = len(instance.cells)
    if n > 12:
        raise ValueError("Local quantum runs support at most twelve candidates")
    qubo = objective_qubo(instance, algorithm)
    z, zz, _ = qubo_to_ising(qubo)
    # scale angles without changing the score reported against classical methods
    scale = max(1.0, *(abs(v) for v in z), *(abs(v) for _, _, v in zz))
    gamma, beta = ParameterVector("gamma", reps), ParameterVector("beta", reps)
    circuit = QuantumCircuit(n)
    if algorithm == "qaoa_swap":
        amplitudes = np.zeros(2 ** n)
        for group in combinations(range(n), instance.pack_size):
            amplitudes[sum(1 << i for i in group)] = 1 / math.sqrt(math.comb(n, instance.pack_size))
        circuit.append(StatePreparation(amplitudes), range(n))
    else:
        circuit.h(range(n))
    for g, b in zip(gamma, beta):
        if algorithm == "qaoa_swap":
            # phase only the selected cells and pairs, then trade membership
            for i, value in enumerate(qubo["linear"]):
                if value:
                    circuit.p(-g * value / scale, i)
            for i, j, value in qubo["quadratic"]:
                if value:
                    circuit.cp(-g * value / scale, i, j)
            for i, j in combinations(range(n), 2):
                circuit.append(XXPlusYYGate(2 * b), [i, j])
        else:
            for i, value in enumerate(z):
                if value:
                    circuit.rz(2 * g * value / scale, i)
            for i, j, value in zz:
                if value:
                    circuit.rzz(2 * g * value / scale, i, j)
            circuit.rx(2 * b, range(n))
    return circuit, tuple(gamma), tuple(beta), cost_operator(qubo), qubo, scale
