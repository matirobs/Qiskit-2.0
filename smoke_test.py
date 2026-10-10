from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

qc = QuantumCircuit(2)
qc.x(0)          # flip qubit 0 only
qc.measure_all()

result = StatevectorSampler().run([qc], shots=100).result()
print(result[0].data.meas.get_counts())