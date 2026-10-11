from qiskit import QuantumCircuit, transpile 
from qiskit_aer import AerSimulator
from cell_data import fresh_discharge, aged_discharge 
import pandas as pd 
import numpy as np

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
#data extraction  
# double check name of data after the ML post processing 
def calculate_capacity_from_df(df):
    discharge_df = df[df['Current'] > 0].copy()
    discharge_df['Delta_Time'] = discharge_df['Time'].diff().fillna(0) / 3600.0 
    capacity = np.sum(discharge_df['Current'] * discharge_df['Delta_Time']) 
    return capacity 

def diff_capacities_df(fresh_df, used_df): 
    initialc = calculate_capacity_from_df(fresh_df) 
    usedc = calculate_capacity_from_df(used_df) 
    if initialc == 0:
        return 0.0
    return abs((initialc - usedc) / initialc)

# 2. Resistance calculation directly from a DataFrame
def resist_values_from_df(df):
    discharge_df = df[df['Current'] > 0].copy()
    resistance = (discharge_df['Voltage'] / discharge_df['Current']).mean()
    return resistance

def diff_resist_df(fresh_df, used_df): 
    fresh_r = resist_values_from_df(fresh_df)
    used_r = resist_values_from_df(used_df)
    if fresh_r == 0:
        return 1.0
    return used_r / fresh_r

# 3. Temperature analysis directly from a DataFrame
def temp_analysis_from_df(df):
    discharge_df = df[df['Current'] > 0].copy()
    return discharge_df['Temperature'].std()

cell_dataset_pairs = [
    (fresh_discharge, aged_discharge),
    # Add other pairs here if you have them
]

n = len(cell_dataset_pairs)
linear_weights = []
capacities = []

for fresh_df, used_df in cell_dataset_pairs:
    cap_fade = diff_capacities_df(fresh_df, used_df)
    res_growth = diff_resist_df(fresh_df, used_df)
    t_stdev = temp_analysis_from_df(used_df)
    
    comp_weight = (0.4 * cap_fade) + (0.4 * res_growth) + (0.2 * t_stdev)
    linear_weights.append(comp_weight)
    capacities.append(cap_fade)    
    

quadratic = [[0.0 for _ in range(n)] for _ in range(n)]
weight_penalty_factor = 1.0

#PLACEHOLDER #2 --> NEED TO DET WEIGHT 
for i in range(n):
    for j in range(i+1, n):
        diffsq = (capacities[i] - capacities[j]) ** 2
        penalty = weight_penalty_factor * diffsq

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

#we still need gam from the sciply optimizer
function qaoa_circuit(gam, bet, linear_weight, quadratic_matrix)
    qubits = len(linear_weight)
    qc = QuantumCircuit(qubits, qubits)
    for i in range (qubits):
        qc.h(i) 

    for i in range(qubits) 
        qc.rz(2 * gam * linear_weight[i], i)
        for j in range(i+1, qubits): 
            if quadratic_matrix[i][j] != 0.0:
                #swap over i to j 
                qc.cx(i,j)
                #ONLY RETURN WHEN BOTH ARE 1 
                qc.rz(quadratic_matrix[i][j]*2*gam, j)
                #unentangle the cubits 
                qc.cx(i, j)

    #mixer layer for interference to dampen any unwanted ones  

    for i in range(qubits): 
        qc.rx(2*bet, i) 

    qc.measure(range(qubits), range(qubits)) 

#for visualization of shifted 
    return qc 
sample_qc = qaoa_circuit(0.5, 0.5, linear_weights, quadratic)
print(qaoa_qc.draw()) 


simulator = AerSimulator()
compiled_circuit = transpile(sample_qc, simulator)
result = simulator.run(compiled_circuit, shots=1000).result()

counts = result.get_counts()
print("\nMeasurement results:", counts)

correct = []
for key, count in counts.items():
    newindex = key[::-1]
    select = [cell_names[i] for i, bit in enumerate(newindex) if bit == '1']
    correct.append(select) 

print("Selected optimal cell combinations:", correct)




    


#print(qc.draw())

