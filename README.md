# RePack-Q

Choosing matched groups of second-life battery cells with quantum and classical
optimization. Built for the Qollab × IonQ 2026 hackathon.

Retired lithium-ion cells can be reused in new packs, but a pack wired in series
is only as good as its weakest cell. Cells that look matched today can drift
apart as they age. RePack-Q predicts how each cell will age, then chooses the
group that stays matched, and compares two Qiskit quantum methods against four
classical methods on the same problem.


Disclaimer: AI was utilized for checking syntax and setting up the framework/interface as we had little to no experience in html. The foundations of the quantum algorithms were made by us, with tweaks in our optimization to debug done by AI. 

CITATIONS: 
Mary. (2026, June 24). Quantum computing fundamentals: Quantum bits vs classical bits explained. QuantumOps School. https://quantumopsschool.com/blog/quantum-computing-fundamentals-quantum-bits-vs-classical-bits-explained/

Harini Hapuarachchi. (2024, May 26). A beginners’ guide to qiskit 1.0 - harini hapuarachchi - medium. Medium; Medium. https://medium.com/@harini.hapuarachchi/a-beginners-guide-to-qiskit-1-0-c8e3e854d732

Introduction to qiskit | IBM quantum documentation. (2017). IBM Quantum Documentation. https://quantum.cloud.ibm.com/docs/en/guides/tools-intro

Quantum approximate optimization algorithm | IBM quantum documentation. (2017). IBM Quantum Documentation. https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm

Build a qiskit function template for hamiltonian simulation | IBM quantum documentation. (2024). IBM Quantum Documentation. https://quantum.cloud.ibm.com/docs/en/guides/function-template-hamiltonian-simulation


Predict how retired batteries will age, then compare algorithms for choosing
compatible groups. The working project includes capacity prediction, four
classical selection methods, and two Qiskit quantum selection methods.

BASIC EXPLANATION: Goal: Given a data set containing general characteristics of cells (temperature, voltage, current, time, etc.) compare two quantum algorithms, a modified neural network, and a classical algorithm to see which is the most efficient and accurate to find the optimal combination of four cells based on their initial use and second use (recycling).

Quantum Algorithm #1: QAOA Penalization Algorithm

Using the inputs of voltage, current, time, and temperature, the values were used to create linear weights to make a "score" for each of the cell cycles

The first project our team submitted utilized SOH (State of Health), Capacity, and Resistance, so we used more general values which could viably be used to analyze any form of cell (not just our data set) to see if the algorithms could be efficiently expanded. Capacity was calculated by integrating the current over a given time cycle (and then the linear weight was found by comparing the original capacity from the new cells and the capacity from the second round of cells), and then resistance was found with ohm's law and comparing the values from the new and old cycles. We used the percent difference (fade) for those, and then found the standard deviation of temperature in the cycle to find any outliers in the temperature data (cells that were breaking down)

These values were pushed through a linear weight for an "energy" rating to be imposed upon each cell

Quadratic penalization: We find the combinations with the closest energy values --> it can return combinations of 2, 3, 5, etc.. so we penalize it for any combination that is not of four cells

We started off with a simplified algorithm. We took a different route from the other project our team submitted (though from the same algorithm, it was just approached differently given two different team members tackled it)-> finding a pair of cells out of four, and then expanded it to iterate for a greater group

Used Rz, CNOT, then Rz --> entangles qubits, then only imposes shift if both qubits are selected (both 1), then unentangles

Hamiltonian: We used the linear weights to impose a phase shift on the qubits.

We then run interference to remove any cells with unfavorable amplitude

Find output with least "energy"

qiskit indexes backwards, so we decoded by reversing the outputted bits

SWAP algo: 2. Compare capacities with future projections --> makes a mismatching table that'll compare the present differences of 40% weight with the future degradation diff 3. Cells that stay matched in the future will be favored 4. Quantum Part: Instead of starting with all of the cells, we narrow them down finding ones where 4 bits are 1 5. Quantum algorithm: using CNOT to find mismatched cells to penalize them 6. Use a XXPlusYY Gate to swap gates across qubit pairs --> gates let us keep the 4 cells 7. Uses a hamiltonian angle shift like the previous algorithm until we find the combination with the lowest possible energy state through 1,024 shots 8. Filters out the most common and top measured packs, while also sending out the predicted capacity.

Neural Network:

We adapted a neural network that our teammate had priorly made in java (used for the sake of speed) and altered it to be used in python for the sake of expanding our SWAP and Quantum algorithms to be used for any combination of cells out of a sample of any size
CLASSICAL #1 Setup & Cooling Schedule:initializes a random seed, sets up temperatures, and picks random starting cell packs across multiple restarts.

The Neighborhood Swap: swaps one cell currently in the pack with one outside it, keeping the group size (like the SWAP algo)

The Acceptance Rule (Metropolis): Always accepts better energy scores, but conditionally accepts worse scores based on a declining temperature probability to escape traps.

Tracking & Output: Continuously updates and saves the global best pack found during the search, retrning full performance statistics at end

Classical #2 Multi-Start: Loops through each cell in the dataset as starting pt to for search multiple independent attempts.

Incremental Greedy Addition: it evaluates all remaining unchosen cells and appends the one with the lowest incremental cost relative to the current group.

Group Completion: Continues adding cells until each group reaches the target pack size (pack_size).

Best Group Selection: Ranks all generated groups, picks the one with the lowest global score, and returns performance stats.

Classical #3 Baseline Metrics Calculation: Computes core performance indicators like usable pack capacity, internal resistance spread, and statistical divergence (coefficient of variation).

Future Truth Integration: Optionally incorporates real-world observed outcomes so evaluates how accurately the pack performed after actual cycling.

Optimality & Regret Analysis: Compares the selection's score against a known optimum to calculate absolute performance gaps, percentage error, and normalized regret.

Classical 4:

Result Builder (result): Validates the chosen indices, calculates the final objective energy score from the basic parameters found, measures the exact execution time in milliseconds, and bundles it with any extra solver metadata.

Deterministic Ranking (ranking): Evaluates the primary objective energy score first, then falls back on sorted cell identifiers to ensure reliable, reproducible tie-breaking across different runs.

Edits: In combination with the machine learning preprocessing and framework, we were able to further our algorithms to be able to find groups of 4, 8, or even 12 out of a provided set and predict which ones would still be efficiently running after up to 200 cycles of charging and discharging

FINDINGS:

Runtimes for quantum #1: latest run 355 ms

Cell swap: 3771 ms

Classical with neural network preprocessing: .02 ms, .27ms, .93ms for each version

The swap algorithm was our least efficient. The QAOA penalization algorithm remains the most efficient.

In the end: Classical seems to run significantly faster than our quantum algorithms, but each of the classical algorithms seemed to have more error as they generally outputted that 94% of the cells were within 10% of one another, which is incorrect. The quantum algorithms are consistent with one another and provide a more efficient overall.

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
