# optimization algorithm to find the best combination of 4 cells from a list of 86. applying quantum circuit with a classical computing frame.
# do this by not using penalization and by swapping. We have a data set

import numpy as np   # math on lists of numbers
from itertools import combinations   # makes every possible group of cells

# get the 8 candidate cells from candidates.py
from candidates import names, capacity_now, capacity_future

from qiskit import QuantumCircuit                      # builds quantum circuits
from qiskit.circuit.library import StatePreparation   # sets qubits to any starting state we want
from qiskit.primitives import StatevectorSampler       # simulates measuring the circuit
from qiskit.circuit.library import XXPlusYYGate   # the swap gate
from qiskit.quantum_info import Statevector   # gives exact probabilities (no random shots)
from scipy.optimize import minimize   # classical optimizer

n = len(names)   # 8 cells to choose from
K = 4            # cells in one pack


# ---------- Part 4: mismatch between every pair of cells ----------

# difference between every pair of cells (makes an 8 x 8 table)
diff_now = capacity_now[:, None] - capacity_now[None, :]
diff_future = capacity_future[:, None] - capacity_future[None, :]

# mismatch = difference squared (always positive, big gaps count extra)
# more weight on the future, bc cells should STAY matched
mismatch = 0.4 * diff_now ** 2 + 0.6 * diff_future ** 2


# score for a whole pack,     add up the mismatch of every pair inside it (lower = better)
def pack_score(pack):
    score = 0
    for i in pack:
        for j in pack:
            if i < j:                       # count each pair once
                score += mismatch[i, j]
    return score


# checks
print("mismatch table (rounded):")
print(np.round(mismatch, 3))
print("C3 vs C5 mismatch:", round(mismatch[3, 5], 4))
print("score of pack C0, C1, C2, C3:", round(pack_score([0, 1, 2, 3]), 4))


# every way to pick 4 cells out of 8
all_packs = list(combinations(range(n), K))
print("\nnumber of possible packs:", len(all_packs))

# best pack = the one with the lowest score
best_pack = min(all_packs, key=pack_score)
print("best pack:", [names[i] for i in best_pack], "score", round(pack_score(best_pack), 4))


# for comparison: pick a pack using ONLY today's numbers (ignoring the future)
def today_score(pack):
    score = 0
    for i in pack:
        for j in pack:
            if i < j:
                score += diff_now[i, j] ** 2
    return score

today_pack = min(all_packs, key=today_score)
print("pack chosen by today only:", [names[i] for i in today_pack])


# how far apart each pack's cells end up after 200 cycles (smaller = stays matched)
def future_spread(pack):
    future = capacity_future[list(pack)]
    return future.max() - future.min()

print("\nafter 200 cycles, spread between strongest and weakest cell:")
print("  our pack (now + future):", round(future_spread(best_pack), 3), "Ah")
print("  today-only pack:        ", round(future_spread(today_pack), 3), "Ah")


# a list of 256 numbers (one for every possible 8-bit pattern)
# patterns with exactly four 1s get an equal share, everything else gets 0
amps = np.zeros(2 ** n)
for b in range(2 ** n):
    if bin(b).count("1") == K:      # does this pattern pick exactly 4 cells?
        amps[b] = 1
amps = amps / np.sqrt(amps.sum())   # quantum rule: squares must add up to 1

start = QuantumCircuit(n)
start.append(StatePreparation(amps), range(n))


# turn a measured bit pattern back into cell numbers
# Qiskit puts qubit 0 on the RIGHT, so we read the string backwards
def decode(key):
    return [i for i, bit in enumerate(reversed(key)) if bit == "1"]


# test: measure the starting state 1000 times
test = start.copy()
test.measure_all()
counts = StatevectorSampler(seed=1).run([test], shots=1000).result()[0].data.meas.get_counts()

print("\n[6a] different packs measured:", len(counts))
print("every measurement picks exactly 4 cells?", all(key.count("1") == K for key in counts))
example = list(counts)[0]
print("example:", example, "->", [names[i] for i in decode(example)])


# test on 2 qubits: start with qubit 0 = 1 (cell 0 in, cell 1 out)
for angle, label in [(np.pi, "full swap"), (np.pi / 2, "half swap")]:
    demo = QuantumCircuit(2)
    demo.x(0)                                        # turn qubit 0 on
    demo.append(XXPlusYYGate(angle), [0, 1])         # swap between qubit 0 and 1
    demo.measure_all()
    c = StatevectorSampler(seed=1).run([demo], shots=100).result()[0].data.meas.get_counts()
    print("[6b]", label, "->", c)



# a swap gate between EVERY pair of cells, so any cell can trade places with any other
# beta = how strongly the cells swap
def swap_mixer(qc, beta):
    for i in range(n):
        for j in range(i + 1, n):                       # every pair once
            qc.append(XXPlusYYGate(2 * beta), [i, j])


# test: start with all 70 packs, run the swap mixer, measure
test2 = start.copy()
swap_mixer(test2, 0.4)
test2.measure_all()
counts2 = StatevectorSampler(seed=1).run([test2], shots=1000).result()[0].data.meas.get_counts()

print("\n[6c] swap gates used:", n * (n - 1) // 2)
print("still exactly 4 cells in every measurement?", all(key.count("1") == K for key in counts2))



M = mismatch / mismatch.max()     # scale mismatch to 0..1 so angles stay simple

# for every pair: if BOTH cells are in the pack, add a phase based on their mismatch
def cost_layer(qc, gamma):
    for i in range(n):
        for j in range(i + 1, n):
            qc.cp(-gamma * M[i, j], i, j)


# full circuit: start state, then (cost layer -> swap mixer) for each layer
def qaoa_circuit(gammas, betas):
    qc = start.copy()
    for gamma, beta in zip(gammas, betas):
        cost_layer(qc, gamma)
        swap_mixer(qc, beta)
    return qc


# the best pack as a number: qubit i on = 2 to the power i
best_index = sum(2 ** i for i in best_pack)

# exact chance that the circuit gives the best pack
def prob_best(gammas, betas):
    probs = Statevector(qaoa_circuit(gammas, betas)).probabilities()
    return probs[best_index]


print("\n[6d] chance of best pack if you guess randomly:", round(1 / 70, 3))
for g, b in [(0, 0), (1, 0.3), (2, 0.3), (3, 0.5), (-2, 0.3)]:
    print("  gamma", g, "beta", b, "-> chance of best pack:", round(prob_best([g], [b]), 3))





# score of every 8-bit pattern (only 4-cell patterns can appear, the rest stay 0)
pattern_score = np.zeros(2 ** n)
for b in range(2 ** n):
    if bin(b).count("1") == K:
        cells = decode(format(b, "08b"))      # reuse our decode function
        pattern_score[b] = pack_score(cells)


# average score of the packs the circuit gives (lower = better)
def expected_score(angles):
    p = len(angles) // 2                       # first half = gammas, second half = betas
    probs = Statevector(qaoa_circuit(angles[:p], angles[p:])).probabilities()
    return probs @ pattern_score               # sum of (chance x score) over all patterns


P = 2   # number of layers

# step 1: rough search - try a grid of angles, keep the best as a starting point
best_value = float("inf")
for g in np.linspace(0.2, 6, 8):
    for b in np.linspace(0.1, 1.5, 6):
        angles = np.array([g] * P + [b] * P)
        value = expected_score(angles)
        if value < best_value:
            best_value = value
            best_start = angles

# step 2: fine-tune from there with an optimizer called COBYLA
result = minimize(expected_score, best_start, method="COBYLA", options={"maxiter": 150})
gammas = result.x[:P]
betas = result.x[P:]

# compare with random guessing
four_cells = np.array([bin(b).count("1") == K for b in range(2 ** n)])
random_average = pattern_score[four_cells].mean()

print("\n[6e] best angles: gammas", np.round(gammas, 3), "betas", np.round(betas, 3))
print("average pack score, random guessing:", round(random_average, 4))
print("average pack score, quantum circuit:", round(result.fun, 4))
print("chance of best pack: random", round(1 / 70, 3), "| quantum", round(prob_best(gammas, betas), 3))