# RePack-Q

Choosing matched groups of second-life battery cells with quantum and classical
optimization. Built for the Qollab × IonQ 2026 hackathon.

Retired lithium-ion cells can be reused in new packs, but a pack wired in series
is only as good as its weakest cell. Cells that look matched today can drift
apart as they age. RePack-Q predicts how each cell will age, then chooses the
group that stays matched, and compares two Qiskit quantum methods against four
classical methods on the same problem.

## How it works

The project runs in four stages:

1. **Predict.** A neural network predicts each cell's capacity after up to 200
   more charge/discharge cycles, using its recorded history.
2. **Score.** Every candidate group gets a mismatch score that weighs both how
   close the cells are today and how close they will be after aging. Lower is
   better. All solvers share this objective
   ([src/repackq/optimization](src/repackq/optimization)).
3. **Select.** Quantum and classical solvers search for the lowest-scoring group.
   Groups of 4, 8, or 12 cells are supported.
4. **Compare.** Results are checked for runtime, score, and how far each answer
   is from the best possible group.

### Aging prediction

The prediction model started as a Java neural network written by a teammate
(see [Sources and licensing](#sources-and-licensing)). For this project it was
extended with battery features, training and tuning, and a portable Python
inference path, so prediction and selection run without Java. The original
smaller model is the default; larger networks and longer training did not
consistently predict better.

### Quantum method 1: Size-penalty QAOA

- Each cell gets an "energy" from linear weights on general measurements:
  capacity fade (current integrated over each cycle), resistance fade (from
  Ohm's law), and the spread in temperature, which flags cells that are
  breaking down. Using general measurements means the method can apply to
  other cell datasets, not only this one.
- The cost layer applies an Rz–CNOT–Rz block to each pair of qubits, so a phase
  shift happens only when both cells are selected.
- A standard mixer can pick groups of 2, 3, 5, or more cells, so a quadratic
  penalty pushes the answer toward exactly the target group size.
- The lowest-energy measured group is the answer. Qiskit orders bits in reverse,
  so outputs are reversed when decoded.

### Quantum method 2: Cell-swap QAOA

This method needs no penalty term. It starts in an equal mix of every valid
group (a Dicke state), and its mixer only swaps a selected cell for an
unselected one, so every measurement has exactly the right number of cells.

| Step | What happens |
| --- | --- |
| Score | Mismatch between two cells = 0.4 × (gap today)² + 0.6 × (gap after 200 cycles)². Group score = sum over all pairs. |
| Start state | Equal mix of every 4-cell group (Dicke state). |
| Cost layer | Phase on each pair of chosen cells, based on their mismatch. |
| Swap mixer | `XXPlusYYGate` on every pair swaps cells in and out. |
| Tune angles | Grid search, then COBYLA, minimizes the average group score. |
| Measure | 1,024 shots; the best-scoring measured group is the answer. |

The standalone version in [SwapAlgorithm.py](SwapAlgorithm.py) picks 4 of 8
candidate cells (70 possible groups), small enough to brute-force the true best
and grade the quantum answer. See [READMEswap.md](READMEswap.md) for a full
walkthrough of that script and its output.

### Classical methods

Four classical solvers in [src/repackq/classical](src/repackq/classical) act as
baselines, including:

- **Simulated annealing:** random restarts and a cooling schedule. Each step
  swaps one cell in the group for one outside it (like the swap mixer) and uses
  the Metropolis rule to sometimes accept worse groups to escape local minima.
- **Multi-start greedy:** starts from each cell in turn, repeatedly adds the
  cell with the lowest added cost until the group is full, then keeps the best
  group overall.

Shared evaluation reports usable pack capacity, resistance spread, coefficient
of variation, the gap and normalized regret against the known best group, and
real observed outcomes when available. Ties are broken by cell ID so runs are
reproducible.

## Run the project

With Python 3.10 or newer, from the repository folder:

```bash
# macOS / Linux
export PYTHONPATH=src
```

```powershell
# Windows PowerShell
$env:PYTHONPATH = "src"
```

Then:

```bash
# Add Qiskit support for the two quantum algorithms (optional for classical runs).
python3 -m pip install -e '.[quantum]'

# Open the interactive battery workbench in your browser.
python3 -m repackq dashboard

# Compare four classical algorithms using the cached real battery histories.
python3 -m repackq compare

# Compare both quantum algorithms with the four classical algorithms.
python3 -m repackq compare --quantum

# Predict capacity after another 200 cycles for recorded battery 9.
python3 -m repackq predict --cell 9 --cutoff 0 --horizon 200

# Demonstrate selection without a trained model or real data.
python3 -m repackq compare --synthetic

# Show available commands and options.
python3 -m repackq --help
python3 -m repackq compare --help
```

On Windows, use `python` in place of `python3` if that is how Python is installed.

### The battery workbench

The [battery workbench](docs/guides/dashboard.md) shows interactive predictions,
classical and quantum comparisons, and recorded benchmarks. With Qiskit
installed, both quantum methods run automatically when it opens. Uncheck
**Include both quantum algorithms** for a faster classical-only run.

The workbench samples its candidate pool from all 86 batteries by default; the
battery-source control can restrict it to the 14 held-out test batteries.
All-cell comparisons include batteries used in training or tuning and are
exploratory. The command-line comparison and saved benchmark default to
test batteries only; use `python3 -m repackq compare --partition all` for all
cells there too.

### What needs what

- Prediction, classical selection, and the workbench without quantum runs use
  only Python's standard library. They do not retrain the model, reread raw
  measurements, or need Java.
- A clean clone includes the trained weights (`models/`), compact real battery
  histories (`data/processed/`), and saved results.
- `python3 -m pip install -e .` installs the `repackq` command directly.
- Offline preparation and training need `python3 -m pip install -e '.[training]'`
  and a Java Development Kit 17 or newer; see the
  [training guide](docs/guides/training.md).

### Standalone swap demo

The original swap algorithm also runs on its own from the repository root:

```bash
pip install -r requirements.txt
python smoke_test.py      # quick check that Qiskit works
python SwapAlgorithm.py   # runs the swap QAOA and prints the result
```

## Results so far

Latest local simulator runtimes:

| Method | Runtime |
| --- | --- |
| Size-penalty QAOA | 355 ms |
| Cell-swap QAOA | 3,771 ms |
| Classical solvers (with neural-network preprocessing) | 0.02 ms, 0.27 ms, 0.93 ms |

The classical solvers are by far the fastest. Of the quantum methods, the
size-penalty QAOA is faster than the cell-swap QAOA, and the two quantum
methods agree with each other on their choices. The team also observed that the
classical outputs rated about 94% of cells as within 10% of one another, which
does not match the data. The classical benchmark shows tradeoffs between
future matching and retained capacity.

All quantum results so far come from simulators. See the
[documentation index](docs/README.md) for full results and limitations.

## Repository layout

### Main package

| Folder | Contents |
| --- | --- |
| [src/repackq/dashboard](src/repackq/dashboard) | Local browser interface and solver integration |
| [src/repackq/quantum](src/repackq/quantum) | Size-penalty and cell-swap quantum algorithms in Qiskit |
| [src/repackq/prediction](src/repackq/prediction) | Runtime prediction and history features |
| [src/repackq/classical](src/repackq/classical) | The four selection algorithms and comparison command |
| [src/repackq/optimization](src/repackq/optimization) | Shared group-scoring problem for all solvers |
| [src/repackq/training](src/repackq/training) | Optional offline trainers and tuning programs |
| [models](models/README.md) | Active model and its evaluation |
| [results](results/README.md) | Saved classical benchmark and quantum smoke-test reports |
| [data](data/README.md) | Prepared battery histories and preparation caches |
| [docs](docs/README.md) | Guides and experiment findings |
| [java](java) | Neural-network source, training bridge, and MIT license |
| [tests](tests) | Verification of prediction, selection, and training |

### Standalone scripts (repository root)

| File | What it does |
| --- | --- |
| [SwapAlgorithm.py](SwapAlgorithm.py) | Original swap-mixer QAOA demo |
| [QUBO.py](QUBO.py) | Early 4-qubit quantum sketch on the Aer simulator |
| [candidates.py](candidates.py) | Builds the 8 candidate cells from real fresh and aged cell data |
| [cell_data.py](cell_data.py) | Loads fresh and aged cell data and splits it into charge and discharge |
| [health.py](health.py) | Measures how much charge each real cell holds per discharge |
| [smoke_test.py](smoke_test.py) | Checks that Qiskit is installed and working |
| `Experimental_data_*.csv` | Raw fresh and aged cell measurements used by the demo |
| [READMEswap.md](READMEswap.md) | Detailed guide to the swap demo |
| [DEMOEXPLANATION.md](DEMOEXPLANATION.md) | Team notes on every method and findings |

The full raw measurements live locally in `Primary_use_phase/` and
`Second_life_phase/` and are excluded from GitHub. They are only needed to
reproduce preparation or training. Temporary training outputs go under the
ignored `build/training/` folder.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Install the training extra first. Old training archives were removed; see the
[training guide](docs/guides/training.md) for their Git history.

## Limitations

- Quantum methods run on simulators only so far.
- Each cell needs one qubit, so the full 86-cell dataset needs more qubits or
  pre-filtering to a smaller candidate pool.
- The final quantum pick is the best-scoring group among measured shots, which
  is a classical step.

## Project status and hackathon requirements

Qollab simulator runs, publication, the project page, and the public demo video
are still pending; this is not yet a completed hackathon submission.

The submission must:

- Use Qiskit and run on Qollab's free local and IonQ simulators.
- Be published and runnable on Qollab under the MIT license before the
  organizer's deadline. Any required outside code repositories must also be MIT.
- Have a Qollab project page explaining the problem, approach, and how to
  reproduce the results.
- Include this GitHub repository and a public 2–3 minute demo video that opens
  without signing in.
- Disclose reused work. Judging covers what was added during the build window.

## Sources and licensing

The software is released under the MIT license in [LICENSE](LICENSE).

**Neural network.** Java `Network.java` and `Parser.java` predate the hackathon.
They began as Spring 2026 ATCS Neural Networks coursework at The Harker School,
with original header dates of May 8 and April 29, 2026. Source: the owner's
`neuralnets` framework, revision `f0eebb0be2d256c2d93af95b114f1cd7458dee60`
from July 9, 2026. The owner authorized MIT licensing on October 10; the notice
is in [java/LICENSE](java/LICENSE). Battery features, Java/Python integration,
validation, tuning, portable inference, selection, and the dashboard were added
for this project.

**Quantum methods.** The package's quantum modules reimplement the two earlier
sketches at this repository's root (`QUBO.py` and `SwapAlgorithm.py`, first
inspected at revision
[`2147ecb`](https://github.com/matirobs/Qiskit-2.0/tree/2147ecb0d929b48be3667c5c31795ac9ecf172fd)
on October 10) using the shared battery objective. The root scripts are
standalone demos, not runtime dependencies of the package.

**Battery data.** Cell data comes from Zenodo record 6985321 and is licensed
separately under Creative Commons Attribution 4.0; see
[data/LICENSE.md](data/LICENSE.md). No battery-sorting source code from the
dataset authors' repository was copied.

**Disclosures.** Coding assistance was provided by Codex. Pre-existing planning
and the starting repository must also be disclosed in the submission.

This effort is supported by Qollab & IonQ.
