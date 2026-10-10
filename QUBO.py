from qiskit import QuantumCircuit, transpile 
from qiskit_aer import AerSimulator

qc = QuantumCircuit(4, 4)

i = 0 
while i < 4:
    qc.h(i)
    qc.measure(i, i)
    i = i + 1

simulator = AerSimulator()

compiled_circuit = transpile(qc, simulator)
result = simulator.run(compiled_circuit, shots = 1000).result()


counts = result.get_counts()
print("Measurement results:", counts)

cell_names = ["A", "B", "C", "D"]
correct = []
for key, count in counts.items():
    newindex = (key[::-1])
    select = [cell_names[i] for i, bit in enumerate(newindex) if bit == '1']
    correct.append(select) 
        #print(i, bit) 
print(correct)

#MISSING LINEAR HEALTH RATING, DEAL WITH LATER


#quadratic matrix to compare the pairwise incompatibility 
#CONTAINS PLACEHOLDER FOR ACTUAL DATA SOURCING. DO NOT RUN. 
capacities = [#EXTRACTDATA]
n = len(capacities)

quadratic = [[0.0 for _ in range(n)] for _ in range(n)]

#PLACEHOLDER #2 --> NEED TO DET WEIGHT 
for i in range(n):
    for j in range(i+1, n):
        diffsq = (capacities[i] - capacities[j]) ** 2
        penalty = weight * diffsq

        quadratic[i][j] = penalty
        quadratic[j][i] = penalty 


function QUBO_energy(bits):
    energy = 0.0
    for idx, bit in enumerate(newindex):
    if bit == '1':
        energy += linear[idx]

    for i in range(len(bits)):
        for j in range(i + 1, len(bits)):
            if bits[i] == 1 and bits[j] == 1:
                energy += quadratic[i][j]


function numpen(bits):
    penalty2 = (4 - sum(bits)) ** 2
    #WE NEED NEW PENALTY WEIGHTING 
    energy += penalty2 




    


#print(qc.draw())

