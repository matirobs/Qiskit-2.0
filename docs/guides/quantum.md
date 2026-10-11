# Quantum battery selection

Two versions of the **quantum approximate optimization algorithm (QAOA)** now
run against the same battery predictions and score as the classical methods.
They follow the approaches in `QUBO.py` and `SwapAlgorithm.py` fetched from
the project's GitHub remote. The first remote file was unfinished and could
not run as written. The maintained implementation is in `src/repackq/quantum/`;
the original local draft was removed during cleanup and remains recoverable
from Git commit `4264ed6` at `experiments/quantum/QUBO.py`.

## Run both

```bash
python3 -m pip install -e '.[quantum]'
PYTHONPATH=src python3 -m repackq dashboard

# Actual cached histories and the active predictor; test-only source by default.
PYTHONPATH=src python3 -m repackq compare --quantum

# Match the dashboard's full-dataset source, keeping one shared candidate pool.
PYTHONPATH=src python3 -m repackq compare --quantum --partition all

# Portable invented inputs, without the local model or battery histories.
PYTHONPATH=src python3 -m repackq compare --synthetic --quantum

# Save both objectives and all measured distributions; refuses existing files.
PYTHONPATH=src python3 -m repackq compare --quantum \
  --seeds 11 23 37 --shots 1024 --output results/quantum-comparison.json
```

In the dashboard, **Include both quantum algorithms** is checked automatically
when Qiskit is installed. Each comparison performs fresh local computation;
it does not replay results. Uncheck it for classical-only runs. Without Qiskit,
the checkbox is disabled and the four classical methods remain available.
The dashboard samples its shared pool from all 86 batteries by default; the
battery-source control can restrict it to 14 test batteries. All-cell runs
include batteries used for model training or tuning and are exploratory.
The command-line comparison retains its test-only default unless
`--partition all` is supplied. Neither path simulates an 86-qubit problem:
classical and quantum solvers receive the same smaller sampled candidate pool.

## What differs

| Method | Starting state | How it searches | Default depth |
| --- | --- | --- | --- |
| `qaoa_penalty` | Equal amplitude over every yes/no selection | Cost phases and single-qubit X rotations; penalizes the wrong group size | 1 layer |
| `qaoa_swap` | Equal amplitude over only groups of the requested size | Cost phases and `XXPlusYYGate` cell swaps; preserves group size | 2 layers |

The swap implementation keeps the upstream approach: prepare a uniform
fixed-size state, phase selected pairs, mix every pair with a swap rotation,
tune angles, and choose the best valid measured group. It now supports arbitrary
allowed pack sizes, includes unary rewards as well as pair costs, and receives
our predictor snapshots instead of upstream's invented candidates and fade rates.
Both methods use the complete shared objective, including current-only mode.
Only the standard mixer needs the calibrated size penalty.

The standard circuit uses the correct binary-to-Ising substitution
`x = (1 - Z) / 2`, including contributions of pair terms to the single-qubit
coefficients and the constant offset. Its circuit phase and every mapped energy
are tested. Reported group scores exclude the size penalty, so valid selections
can be compared directly with classical results within the same objective.

## Angle tuning and measurements

Angles control the cost and mixer layers. A 12-by-8 initial grid evaluates
expected cost using Qiskit `Statevector`, followed by COBYLA (Constrained
Optimization BY Linear Approximation) when SciPy is available. A coordinate
refinement fallback works with `--optimizer grid`. Defaults allow at most 160
cost evaluations per method; change this with `--quantum-evaluations 256`.
The Python interface also accepts `reps=1`, `2`, or `3`.

Tuning uses predicted/current inputs and expected objective cost. It never uses
recorded future capacities or the known exact-best pack as a training target.
The exact result is used afterward to assess selection quality. With the default
1024 shots (circuit measurements), each algorithm submits one sampling job after
local tuning. The default backend is Qiskit's free `StatevectorSampler`; no
Qiskit Aer installation, account, credential, or paid hardware is needed.

The recommendation is the best valid measured group, which can differ from the
most common measurement. Invalid samples are retained in diagnostics. If no
valid group is measured, that method gets `no_feasible_sample` and no selection;
it is not repaired or replaced by a classical answer. The swap circuit preserves
size in ideal simulation; noise on other backends can change that behavior.

Each report includes raw counts, probabilities, valid-measurement fraction,
fraction of shots matching an exact optimum, feasible measured groups, the modal
measurement, selected bitstring, angles, depth, gate counts, optimization budget,
backend, and timings. Gamma and beta parameters are bound by name. Candidate zero
corresponds to the rightmost measurement bit, handled by one shared decoder.
Batch summaries retain the number of attempted quantum runs and runs with no
valid sample; those failures are not hidden by averaging only successful rows.

## Use from Python or another backend

```python
from repackq.quantum import run_both, run_qaoa, prepare_qaoa, finish_qaoa

# `problem` is the same OptimizationInstance passed to the classical solvers.
runs = run_both(problem, seed=11, shots=1024)
for run in runs:
    selection = run['selection']  # None if no valid group was measured
    print(run['algorithm'], run['status'], run['diagnostics']['feasible_fraction'])

# Synchronous Qiskit backend supplied by the caller; no credentials created here.
run = run_qaoa(problem, algorithm='qaoa_swap', backend=provided_backend)
```

For a platform with asynchronous jobs, `prepare_qaoa` performs only local angle
tuning and returns a measured Qiskit circuit. Submit `prepared.circuit` through
the platform's verified backend adapter, await its result, then call
`finish_qaoa(prepared, counts, backend=label, shots=1024)`. This separation avoids
remote jobs inside the optimizer loop. The synchronous injected-backend contract
is tested, but is not evidence that the Qollab asynchronous adapter works.

## Evidence and limits

Local checks used Qiskit 2.5.2, SciPy 1.18.1, and NumPy 2.3.5. On one real
eight-candidate/four-selected pool drawn from the original 14 test batteries,
seed 11, first-life-only inputs, horizon 200,
trajectory-aware scoring, and 128 evaluations per circuit, both quantum methods
sampled the same best group as exact search: cells 29, 31, 57, and 63, score
approximately 2.5564. The included report is `results/quantum-first-run.json`.
This is a smoke test, not an aggregate benchmark or a quantum advantage claim.
The saved dashboard benchmark still contains only the earlier classical runs.

Local simulation and state preparation grow exponentially; runs are limited
to twelve candidates. Circuit preparation and local tuning can cost much more
than exact classical selection on these small pools. The two default depths
also differ, so this is not a controlled equal-resource mixer comparison.

Qollab's free local and IonQ simulator paths still require actual platform
adapter verification and execution. Qollab publishing,
the project page, demo video, and submission remain open release gates.
Compact histories and derived records are included under the source attribution
in data/LICENSE.md; large raw measurements stay excluded.
Upstream source details and the code-licensing gate are recorded in
[project sources and licensing](../../README.md#sources-and-licensing).

Qiskit references: [XXPlusYYGate](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.circuit.library.XXPlusYYGate),
[StatevectorSampler](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.primitives.StatevectorSampler).
