# RePack-Q: a beginner’s guide

Battery histories used by RePack-Q derive from Wang, Gao, and Tian’s *Data for: Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions* ([Zenodo record 14859405](https://zenodo.org/records/14859405)). The Zenodo record metadata lists the dataset under Creative Commons Attribution 4.0 International (CC BY 4.0). Reuse and redistribution require appropriate attribution, a link to the license, and an indication of changes.

RePack-Q is a learning and research demo about choosing used electric-vehicle battery cells for a second life. It estimates how cells may change, forms small groups whose cells match, and compares ordinary search methods with two quantum optimization methods.

You do **not** need to know batteries, machine learning, optimization, or quantum computing to begin. All of the project documentation is in this one file. Use the contents below to jump between sections, or read from top to bottom.

The workbench can help explain how prediction and optimization fit together. It is **not** a battery safety tool, engineering certification, lifetime guarantee, or proof that quantum computing is faster or better.

## Contents

- [Use the live workbench](#use-the-live-workbench)
- [What the workbench includes](#what-the-workbench-includes)
- [Start Here: run your first comparison](#start-here)
- [Battery basics](#battery-basics)
- [How it works](#how-it-works)
- [The selection algorithms](#selection-algorithms)
- [How to read results](#reading-results)
- [Quantum computing in this project](#quantum-computing)
- [Troubleshooting](#troubleshooting)
- [Glossary](#glossary)
- [Data, sources, and licenses](#data-sources-licenses)
- [Implementation overview](#implementation-overview)

<a id="use-the-live-workbench"></a>
## Use the live workbench

When this page opens, it loads the sample cell histories and starts a default comparison. Once results appear, use the controls to explore the settings or run another comparison. No local setup is needed. The browser interface calls the hosted Python bridge to prepare predictions, score cell groups, and return results for display.

When Qiskit is available to the hosted Python runtime, the two quantum methods are enabled alongside the classical methods. If it is unavailable, the classical comparison remains usable. The quantum methods use a local simulator and do not submit jobs to quantum hardware.

<a id="what-the-workbench-includes"></a>
## What the workbench includes

- An interactive battery-selection workbench with prediction, group scoring, and classical and quantum search methods.
- Compact derived histories for 86 battery records, a trained prediction model, and saved evidence summaries.
- The software license and information about the battery-data source and its reuse status.
- This complete beginner’s guide in one article.

The workbench uses derived histories rather than the source dataset’s multi-gigabyte raw measurement files. It also presents saved benchmark summaries rather than detailed per-trial records. See [Data, sources, and licenses](#data-sources-licenses) for the source and rights information.

<a id="start-here"></a>
## Start Here: run your first comparison

This page is a practical walkthrough. It assumes you have never used Qollab or a battery-optimization workbench before.


### First-run settings

The defaults are intentionally small enough for a classroom-scale demonstration.

| Control | Default | What it means |
| --- | --- | --- |
| Battery source | Full dataset | Candidate cells are sampled from the project’s 86 battery histories. This includes cells used while developing the predictor, so treat it as exploratory. |
| Forecast horizon | 200 cycles | Predict capacity 200 charge/discharge cycles after the decision point. A cycle is not a fixed amount of calendar time. |
| Known second-life history | First-life history only | Make the prediction without using later observations from the battery’s reuse phase. |
| Sampled candidate cells | 8 | Build a pool of eight eligible cells before searching. The project does not search all 86 cells at once. |
| Group size | 4 | Choose four cells from the eight candidates. |
| Pool seed | 11 | Make the sample and randomized search repeatable. Repeating a seed does not make the data independent or the prediction more accurate. |
| Matching objective | Match for the future | Include forecast capacity in the compatibility score. “Match for today” leaves forecasts out of the score. |
| Include both quantum algorithms | Depends on Qiskit | When active, run the two QAOA methods in addition to the classical methods. |

Available candidate counts are 6, 8, 10, and 12; group sizes are 2–5; horizons are 50, 100, and 200 cycles; and history cutoffs are 0, 20, 50, and 100 cycles. A chosen group cannot be larger than its candidate pool. Some combinations may fail if too few cells meet the history and evaluation requirements.

### A five-minute tour

1. **Look at the battery cards.** Each card shows the battery ID, present state of health, current capacity, predicted future capacity, resistance, and estimated capacity loss. Predictions are model outputs, not measurements of the future.
2. **Read the pool summary.** It tells you how many cells were eligible and selected, which source was used, and what seed sampled the pool. The sampled cells are not a “top eight” ranking.
3. **Read the comparison table.** It contains one row for each successful selection method. Click a row to display that method’s group in the inventory and chart.
4. **Compare the two matching objectives.** Switch between **Match for today** and **Match for the future**, then run again. The raw objective scores from these two modes are on different scales of meaning; compare their revealed physical metrics instead.
5. **Make a manual group.** Click battery cards until the required number is selected. The application computes the same score for your group. Remove a selected card by clicking it again.
6. **Reveal actual future measurements.** If the chosen source includes suitable recorded outcomes, click **Reveal actual future**. The values are then shown for retrospective evaluation. They were withheld from the model and selector before you pressed the button.
7. **Export the run.** **Export run** saves a JSON file containing settings, input snapshots, solver results, and scoring details. It includes actual future observations only if you explicitly revealed them.

### What to look at first

For a first pass, do not start with the quantum panel. Start with these questions:

- Does “healthiest first” select the same group as the lowest-score method?
- Does a group with a low predicted spread also have a low *actual* spread after reveal?
- Does a more closely matched group retain as much minimum capacity as another group?
- Does the exact method confirm that the heuristics found the best score for this small candidate pool?

These questions distinguish a good optimization result from a good real-world outcome. The optimization can only choose well if its measurements and predictions describe the future well.



<a id="battery-basics"></a>
## Battery basics

This project deals with individual lithium-ion **cells** that have already been used in an electric vehicle. The aim is to explore whether some can be grouped for another use. This section explains the battery words used in the interface.

### Cell, battery, and pack

A **cell** is one electrochemical unit. A **battery** is often made from many cells. A **pack** is an assembled set of cells and supporting electrical, thermal, and safety systems. In the workbench, a “group” is a simplified choice of cells; the app does not design the complete pack or its safety system.

When cells are connected **in series**, their voltages add. The same current passes through each cell. If one cell reaches its usable limit before the others, that cell can constrain the group. The workbench therefore reports the group’s **usable capacity proxy** as the smallest capacity among its selected cells. This is a simple teaching metric, not a full electrical simulation.

### Capacity and amp-hours

**Capacity** describes how much electric charge a cell can deliver under a specified measurement procedure. The project reports capacity in **amp-hours (Ah)**. One amp-hour means one amp of current for one hour in an idealized accounting sense. Ah is not the same as power (watts), energy (watt-hours), voltage, or remaining service life.

Capacity readings depend on how a cell is tested. This project uses comparable reference-discharge measurements from the source dataset. The model predicts the capacity at a future reference test; it does not predict every moment of operation between tests.

### State of health (SOH)

**State of health** is a ratio comparing present capacity with a nominal, or reference-new, capacity:

```text
SOH = present capacity / nominal capacity
```

The project uses a nominal capacity of 2.4 Ah for this data. For example, a 1.8 Ah reading corresponds to `1.8 / 2.4 = 0.75`, or 75% SOH. SOH is a convenient summary; it does not reveal every fault or determine whether a cell is safe.

### Resistance and temperature

**Internal resistance** describes opposition to current inside the cell. Higher resistance can mean more voltage drop and heat under load. Measurements can vary with test conditions and temperature. The scoring method compares normalized resistance measurements across the candidate pool; it does not simulate a load profile.

**Temperature** is collected in the underlying records, but temperature matching has zero requested weight in the shipped objective. It is not used to choose the displayed group under the default settings.

### Cycles and aging

A **cycle** is a charge/discharge aging unit in the dataset. It is not a day or month. A cell can accumulate partial cycles, and a cycle count alone does not specify the current, temperature, or depth of discharge of every event.

The interface’s “200 cycles” means the requested distance between the decision point and the future capacity target. It is not a promise that the cell or pack will last 200 more cycles. Calendar aging, use conditions, manufacturing variation, protection electronics, and many other factors are outside this model.

### First life and second life

**First life** means the original use phase represented in the recorded histories. **Second life** means a later reuse phase. The project asks whether cells with similar present and predicted future measurements could form a more consistent group for reuse.

The **history cutoff** controls how much second-life information is already known at the decision point. A cutoff of zero is a “cold start”: the prediction uses first-life history only. A cutoff of 20 may use qualifying second-life observations at or before cycle 20. Measurements after the cutoff must not influence that prediction or the selection.

### What a forecast means

For each eligible cell, the model returns one estimated capacity at the selected future horizon. The chart draws a line between the current and predicted endpoints to make the direction easy to see. The line is a visual guide; the model does not produce a measured or simulated curve for all intermediate cycles.

Forecast uncertainty in this project is a residual scale measured during validation. It is **not** a calibrated probability interval. A displayed forecast such as 1.7 Ah should be read as an estimate, not a promise that the actual future value will be close to 1.7 Ah.


<a id="how-it-works"></a>
## How it works: from history to a proposed group

RePack-Q combines two different tasks:

- **Prediction:** estimate a cell’s future capacity using information known at the decision point.
- **Optimization:** choose a fixed-size group whose cells score well against one another.

Keeping these tasks separate helps explain both what the project can do and where it can be wrong.

### The complete flow

```text
Recorded battery history
        ↓
Choose a decision point and forecast horizon
        ↓
Estimate each candidate's future capacity
        ↓
Build one shared score for groups of cells
        ↓
Search the same candidate pool with several algorithms
        ↓
Optionally reveal later measurements for retrospective checking
```

The future measurement is held back until after selection. See [Data, sources, and licenses](#data-sources-licenses) for the dataset and its limitations; see [Reading results](#reading-results) for each displayed metric.

### 1. Build the candidate pool

The package contains derived histories for 86 batteries. A run samples a smaller pool of 6, 8, 10, or 12 cells. Every algorithm in that run receives exactly the same pool. The seed makes sampling repeatable. It does not rank cells by their future outcome.

The source selector can choose:

- **Full dataset:** all eligible batteries, including batteries used during model development. This is exploratory.
- **Held-out test batteries:** identities excluded from model fitting. These identities have nevertheless been examined in earlier project experiments, so this is not a pristine independent test.

Eligibility is based on the availability of sufficient past information and a usable future reference measurement near the requested target, plus a minimum present SOH threshold of 50%. A future capacity value is not used to score or pick a group. The fact that a future reference is available can determine whether a cell can be retrospectively evaluated; this can affect which cells are eligible and is one reason not to treat the run as a deployment study.

### 2. Predict capacity

An already-trained neural network reads summarized history features such as capacity history, recent change, resistance, temperature when available, second-life history known by the cutoff, and the requested horizon. It produces a future capacity estimate in Ah. The app loads trained weights; it does not retrain the model when you press **Run comparison**.

In the saved experiment, battery identities were separated before model fitting: 60 cells for training, 12 for validation, and 14 for testing. In plain terms, training adjusts the network’s numeric weights using examples with known outcomes; validation helps choose a model; test measurements are reserved to evaluate it afterward. No cell identity crosses those partitions. The displayed test score includes 167 forecast cases from 14 cells, so those cases are repeated observations from a small number of batteries—not 167 independent batteries.

The active model is a small feed-forward neural network. It receives 15 summarized features plus a constant input used like an intercept, uses 12 hidden units, and outputs a capacity estimate. You do not need the network’s internal math to use the workbench: the practical point is that it learns a relationship from previous cell histories and measured later capacities, and can make errors on a new case.

The prediction is constrained to be between zero and the cell’s current capacity. That is a modeling choice for this application, not a universal rule about all batteries. Forecast errors are measured against the dataset’s later reference-discharge observations.

### 3. Score possible groups

For every candidate group, the project combines:

- how different the selected cells are in present capacity;
- how different they are in resistance;
- in trajectory-aware mode, how different their predicted future capacities are;
- a reward for cells with better current SOH;
- an optional prediction-uncertainty term.

Before comparing values, each feature is normalized using the current candidate pool. This prevents units like Ah and ohms from directly dominating just because their numeric scales differ. Pairwise mismatch is based on a weighted squared difference: cells farther apart contribute more cost. A health reward lowers the score for healthier cells.

The default requested weights are:

| Part of score | Weight | Plain-language role |
| --- | ---: | --- |
| Present capacity match | 30% | Favor similar capacity now. |
| Resistance match | 20% | Favor similar measured resistance. |
| Predicted future capacity match | 35% | Favor similar forecast capacity later. |
| Current health reward | 10% | Favor cells with stronger current health. |
| Forecast uncertainty | 5% | Allow the score to account for model uncertainty. |
| Temperature match | 0% | Collected if available, but not active in the default score. |

These are chosen design weights, not experimentally discovered physical constants. In current-only mode, the forecast, uncertainty, and temperature weights are disabled; active weights are re-normalized. In trajectory-aware mode, the model’s uncertainty value is currently a common validation residual scale, so it generally cannot distinguish one cell from another.

The resulting objective score is a mathematical ranking tool. It has no physical unit: it is not Ah, volts, joules, or percent. Because the health reward is subtracted from the cost, a score can be negative. Within one run and one objective mode, lower means the group better matches the chosen score.

### 4. Search for a group

The algorithms try to find the lowest-scoring group of the requested size. The application shows four classical methods and, when Qiskit is available, two QAOA methods. Each method uses the same cells and objective. See [Algorithms](#selection-algorithms) for how each search works.

### 5. Reveal and evaluate

Once selection is finished, **Reveal actual future** displays the recorded reference values near the requested horizon. The solver never receives those values. The comparison can then show whether a low predicted mismatch corresponded to a low observed mismatch on those selected cells.

This check is retrospective: after you reveal the data, the future is no longer hidden from you. Changing a selection or settings afterward is useful exploration, but it is no longer a blind evaluation.


<a id="selection-algorithms"></a>
## The selection algorithms

All methods are given the same candidate cells, requested group size, feature values, and scoring rules. They differ in how they search for a group. A method can find a group with a low score; it cannot make the prediction feeding that score more accurate.

### Four classical methods

| Name in app | What it does | Useful for | Main limitation |
| --- | --- | --- | --- |
| **Healthiest first** (`healthiest`) | Chooses cells with the strongest current state of health. | A simple reference for comparing compatibility-based choices. | It does not minimize the shared compatibility score. It may select healthy cells that are dissimilar to one another. |
| **Greedy matching** (`greedy`) | Tries different starting cells and repeatedly adds the next cell with the best incremental score. | A fast, intuitive search. | An early choice can block a better complete group later. |
| **Simulated annealing** (`annealing`) | Starts with a group, swaps one selected cell with one unselected cell, and repeats. It accepts improving swaps and sometimes accepts a worsening swap early in the search. | Escaping a locally good but globally worse group. | It is a heuristic. A run can miss the best group; its path depends on its seed and search budget. |
| **Exact search** (`exact`) | Scores every possible group in the candidate pool and returns a lowest-scoring one. | The answer key for the *current small pool and score*. | It only proves optimality for this sampled pool and this objective. It does not prove the group is physically safest or best in the full dataset. |

For eight candidates and a group size of four, there are only 70 possible groups (`8 choose 4`). Exact search can check all of them quickly. The app uses exact search as a reference because the pool is small.

### What “best” means here

The exact method finds the group with the lowest numerical objective score. That answer is optimal according to the project’s chosen weights and normalized features. It is **not** necessarily the group with:

- the smallest later measured imbalance;
- the greatest minimum cell capacity;
- the lowest resistance under a specific load;
- the longest real operating life;
- or an acceptable safety profile.

Those questions need additional data and engineering models.

### The two quantum methods in one paragraph

The two quantum methods encode the same group-scoring problem into Qiskit circuits. The first uses a penalty in its score to encourage the required number of selected cells. The second starts with exactly that number of cells selected and uses a swap-style mixer that preserves the count in ideal simulation. The app tunes circuit parameters on a local simulator, samples candidate groups, and returns the lowest-scoring valid measured group. This process is explained step by step in the [Quantum guide](#quantum-computing).

### Why use several methods?

Comparing methods on a common problem is a way to study search behavior:

- Does a heuristic match the exact score optimum on a tiny pool?
- How often does a quantum sample contain a valid group?
- Does the group with the lowest model-based score also look good after measurements are revealed?
- How do search time and result quality change as the pool changes?

This is an algorithm comparison, not a contest in which the fastest displayed time proves a general advantage. A fair performance study must fix the problem, resources, hardware, implementation overhead, repetitions, and evaluation criteria in advance.


<a id="reading-results"></a>
## How to read the workbench results

This guide separates the quantities the app displays. Some describe the model’s chosen score; others describe physical measurements. Do not treat them as interchangeable.

### The comparison table

| Column | Meaning | How to use it |
| --- | --- | --- |
| **Algorithm** | The search method that proposed the group. | Click a method to display its chosen cells. |
| **Selected cells** | Battery identifiers in that group. | Compare methods only when they used the same run and candidate pool. |
| **Group score** | The shared normalized optimization objective. | Lower is better within the same run and objective mode. It is not a physical unit and may be negative. |
| **Gap from best** | This score minus the exact search’s lowest score. | Zero means this group has an optimal score for this pool. A nonzero gap tells how far above the best model-based score it is. |
| **Runtime** | The time measured by the local Python implementation for that method. | Treat as a rough observation from this run, not a universal speed ranking. Platform, warm-up, workload, and Qiskit behavior affect it. |

The exact search row is the reference. A heuristic or quantum method that has a zero score gap has matched the exact optimum’s score. It does not follow that its cell group is safe or has the best actual future outcome.

### Capacity chart and group summary

- **Current capacity** comes from a recorded measurement at the decision point.
- **Predicted future capacity** is produced by the trained model.
- Dashed lines connect those two points as a visual guide. They are not intermediate measured capacities or a physical degradation simulation.
- **Current group capacity** is the smallest current capacity among selected cells. It is a simple series-group proxy.
- **Predicted future spread** is the largest predicted capacity minus the smallest predicted capacity in the selected group. Smaller means closer model forecasts.
- After revelation, **actual imbalance** is the population standard deviation of the selected cells’ measured future capacities divided by their mean. It is shown as a percentage; smaller means more similar relative capacities in this particular observation.
- **Actual minimum** is the lowest observed future capacity in the selected group. Higher can be desirable for retaining a basic capacity floor, but this metric is still only a proxy.
- **Actual spread** is the highest minus the lowest observed future capacity, in Ah.

The app can show a group with low imbalance but a lower minimum capacity than another group. Looking at more than one metric matters.

### “Match for today” and “Match for the future”

The two modes use different scoring inputs:

- **Match for today** scores present capacity, resistance, and current health.
- **Match for the future** additionally scores predicted capacity and can include forecast uncertainty.

Do not compare the raw score from one mode directly with the raw score from the other. Their active terms and weights differ. To compare which choice worked better, use the same revealed outcome metrics, especially actual imbalance and actual minimum capacity. Treat that comparison as exploratory because the cells and future outcomes have been studied before.

### Saved predictor baseline

The **How close were the forecasts?** panel reports a saved model evaluation, not the quality of the selected group in the current run. The stored evaluation contains 167 test forecasts across 14 held-out battery identities:

| Measure | Saved value | Meaning |
| --- | ---: | --- |
| Forecasts within 5% | 122 of 167 (73.1%) | Fraction of these forecast cases whose absolute error was at most 5% of actual capacity. |
| Forecasts within 10% | 157 of 167 (94.0%) | Fraction whose absolute error was at most 10% of actual capacity. |
| Mean absolute error | 0.059527 Ah | Average absolute difference between predicted and observed capacity. |

These cases are repeated forecasts from a small number of batteries, not 167 independent batteries. The test identities were inspected in project experiments. The numbers are a recorded baseline, not a guarantee about a new battery, pool, or deployment.

### Saved 20-pool selection benchmark

The evidence panel summarizes a pre-existing experiment: 20 seeded pools drawn from the same 14 test batteries, with 8 candidates, 4 selected, first-life-only inputs, and a 200-cycle horizon. Pools overlap, so the 20 runs are not independent samples.

| Objective | Method | Mean observed future imbalance | Mean observed minimum capacity |
| --- | --- | ---: | ---: |
| Current only | Healthiest first | 2.2498% | 1.5827 Ah |
| Current only | Greedy, annealing, exact | 3.4583% | 1.5682 Ah |
| Trajectory aware | Healthiest first | 2.2498% | 1.5827 Ah |
| Trajectory aware | Greedy | 3.1006% | 1.5180 Ah |
| Trajectory aware | Annealing, exact | 3.0909% | 1.5180 Ah |

In this saved experiment, healthiest-first had the lowest mean observed imbalance and a higher mean observed minimum capacity than the other methods. The exact method still optimizes the defined model score; the mismatch between that score and the retrospective physical measures illustrates why prediction and objective design matter. This one experiment does not establish a universal winner.

### A careful reading checklist

Before making a claim from a result, ask:

1. Were the methods given the same cells and objective?
2. Is the number a model score, a model prediction, or an observed measurement?
3. Was future truth revealed only after the group was selected?
4. Is the “test” data reused or previously inspected?
5. Do the groups trade off matching against minimum capacity?
6. Is the problem small enough that exact classical search is a practical baseline?
7. Does the result support the claim being made, or only a narrower statement about this run?


<a id="quantum-computing"></a>
## Quantum computing in this project

This guide assumes no quantum-computing background. It explains what the project’s “quantum” methods do and, just as importantly, what they do **not** demonstrate.

### First: what is being optimized?

The input to a quantum circuit is still an ordinary, classical list of candidate batteries and numbers. The task is: choose exactly `K` cells from `n` candidates so that their shared score is low. For example, `n = 8` and `K = 4` means choose four cells from eight.

The circuit does not receive battery chemistry or a continuous aging process. It represents a yes/no decision for each candidate.

### Qubits and bit strings

A classical bit is either 0 or 1. In this application, a result bit means:

- `0`: this candidate cell is not in the group;
- `1`: this candidate cell is in the group.

A **qubit** is the quantum information unit used by Qiskit. The circuit can put qubits into states whose measurement probabilities reflect many possible bit strings. When measured, one bit string is returned. A circuit with one qubit per candidate therefore uses eight qubits for an eight-candidate pool—not 86 qubits for the complete dataset.

The phrase **superposition** refers to a quantum state that can produce multiple measurement outcomes with different probabilities. It does not mean the app reads all answers out at once. Each sample is one result; repeated **shots** produce a frequency distribution.

### QAOA, step by step

**QAOA** means the *Quantum Approximate Optimization Algorithm*. It combines a parameterized quantum circuit with a classical parameter search:

1. Encode the cell-selection score into a mathematical function of 0/1 decisions.
2. Build a circuit that gives low-score decisions more favorable phases and mixes decisions so probability can move among them.
3. Simulate the circuit’s expected score for one set of angle parameters.
4. Have a classical optimizer try other angles to reduce that expected score.
5. Bind the best angles, measure the final circuit repeatedly, and score the bit strings that were sampled.
6. Return the best valid measured group—not necessarily the most frequent one.

The circuit parameters are often called **gamma** (cost-layer angle) and **beta** (mixer-layer angle). The number of cost/mixer repetitions is called depth `p` or `reps`. Tuning these angles is not neural-network training and does not change the battery predictor.

### QUBO: a compact way to describe the choice

The score can be written as a **Quadratic Unconstrained Binary Optimization (QUBO)** function:

```text
score(x) = sum of individual-cell terms
         + sum of cell-pair terms
         + (for the penalty method) λ × (number selected − K)²
```

Here each `xᵢ` is 0 or 1, and `λ` is a penalty large enough to discourage groups of the wrong size. The word “energy” sometimes used in optimization is only a mathematical analogy. It is **not** the physical energy stored in a battery.

### Method A: size-penalty QAOA (`qaoa_penalty`)

This method begins with a broad mixture of all possible 0/1 selections. A standard mixer can change the number of selected cells, so the score includes a penalty for selecting too few or too many. Samples with the wrong number are invalid for the requested group. Only valid groups can become recommendations.

The penalty method is flexible, but a poorly chosen penalty can make optimization difficult. This implementation calibrates a penalty for the small candidate pool before building the circuit.

### Method B: cell-swap QAOA (`qaoa_swap`)

This method starts in a state containing only groups of the requested size. A swap-style mixer trades a selected cell for an unselected one. In ideal simulation, the number selected stays fixed, so no group-size penalty is needed. The circuit uses Qiskit’s `XXPlusYYGate` for pairwise swaps.

### What is actually simulated here?

The QAOA path uses Qiskit’s **Statevector** to tune parameters and Qiskit’s local **StatevectorSampler** to draw final samples. This is a classical simulation of an ideal quantum circuit. It does not submit a circuit to a physical quantum processor or to an IonQ/Qollab hardware queue. A plotted or reported “quantum result” from this workbench is a local simulator result.

The hosted runtime must have Qiskit, NumPy, and SciPy available for the quantum path. The hosted runtime may provide those packages in `requirements.txt`, but the host controls which packages it installs. If the app cannot import Qiskit, it leaves classical comparison available and disables the quantum control.

The default run uses up to 160 expectation-value evaluations per quantum method, then samples 1,024 shots from the final circuit. Angle tuning and statevector simulation can take longer than the classical methods. At most 12 candidates are supported by the local quantum code.

### Why use a quantum algorithm if exact search works?

For a pool of eight candidates, exact search checks only 70 four-cell groups. This is easy for a laptop and gives a useful answer key. The quantum experiment is useful as a comparison of encodings, circuit behavior, sampling, and solver quality. This problem size and simulator setup are not evidence of quantum speedup.

The measured group is selected from classical post-processing of the circuit’s bit strings. The quantum circuit can return an invalid group under the penalty method, and it can sample a group that is not optimal. If no valid sample appears, the app reports no valid result rather than quietly substituting a classical one.

### Terms to remember

- **Shot:** one circuit sample/measurement.
- **Count:** how many shots produced a particular bit string.
- **Probability:** count divided by total shots.
- **Feasible:** selects exactly the requested number of cells.
- **Expected score:** probability-weighted average score used while tuning angles.
- **Circuit depth:** a rough count of sequential gate layers; not a direct runtime or accuracy measure.
- **QUBO:** an objective expressed using binary choices and terms up to pairs.
- **Mixer:** circuit operations that move probability among candidate choices.

For the official software references, see [QAOA](https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm), [StatevectorSampler](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.primitives.StatevectorSampler), and [XXPlusYYGate](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.circuit.library.XXPlusYYGate).


<a id="troubleshooting"></a>
## Troubleshooting

### The page looks unstyled or incomplete

Reload the Qollab page once and wait for it to finish loading. If the layout is still incomplete, the issue is with the hosted page and should be reported to the project maintainer; visitors do not need to install or edit files.

### The workbench does not start

Wait a few seconds for the hosted Python runtime to initialize, then try **Run comparison** again. If the page continues to show an error, report the message shown by Qollab. The workbench’s browser interface depends on the hosted Python bridge.

### The quantum option is disabled

The quantum controls are enabled only when Qiskit is available to the hosted Python runtime. The classical methods remain available without it. This workbench uses a local simulator and does not submit hardware jobs.

### Quantum runs are slow

The quantum methods tune circuit parameters with repeated local statevector simulations, then sample the circuit. Simulation cost grows quickly with the number of candidates. Start with the default, smaller pool; the local quantum implementation supports at most 12 candidates.

### “Reveal actual future” is unavailable

The control is unavailable when the selected pool has no qualifying recorded future measurements, or when those measurements have already been revealed. Candidate eligibility depends on the selected history cutoff and forecast horizon. A revealed run is no longer a blind experiment.

### The results look surprising

- A lower objective score can have a worse observed outcome because the forecast and scoring weights are imperfect.
- A group can have low capacity imbalance but also a low minimum capacity. Check both.
- “Exact” means the lowest score among groups in the sampled pool, not a globally best or safest battery pack.
- A quantum method’s best sampled group can differ from its most frequent group.
- Runtime varies by environment and should not be read as a universal speed ranking.

See [Reading results](#reading-results) before interpreting a surprising row.


<a id="glossary"></a>
## Glossary

| Term | Plain-language definition in this project |
| --- | --- |
| **Ah (amp-hour)** | Capacity unit used for cell measurements and forecasts. It measures charge under a test procedure, not power or lifetime. |
| **Annealing / simulated annealing** | A classical search that swaps cells and sometimes accepts a worse move early so it can escape a local dead end. |
| **Backend** | A Qiskit execution target. In this package, QAOA uses a local simulator; no physical backend job is submitted. |
| **Battery cell** | One electrochemical unit. The app’s selectable items are cells from recorded battery histories. |
| **Candidate pool** | The small sampled set of cells that all methods compare in one run. |
| **Capacity** | Measured or predicted charge a cell can deliver under a defined discharge test, expressed in Ah. |
| **Cell ID** | Dataset identifier used to refer to a recorded cell. It is not a recommendation or ranking. |
| **Classical algorithm** | A method executed on ordinary computing hardware, such as greedy search or exact enumeration. |
| **Cutoff / history cutoff** | The latest second-life cycle allowed as known information when making a decision. |
| **Exact search** | Checks every possible group in the current small pool and finds the minimum objective score. |
| **Feasible group** | A selected set containing exactly the requested number of cells. |
| **Forecast / prediction** | A model estimate of capacity at a future cycle count. It is not an observation or a guarantee. |
| **Future truth** | A later measured capacity held out from prediction and selection until the user reveals it. |
| **Greedy search** | Adds cells one at a time based on the best immediate improvement; an early choice can prevent a better final group. |
| **Health reward** | A score term that favors higher current SOH by reducing the objective. |
| **Internal resistance** | A cell measurement related to voltage drop and heat under current. It is compared across cells but not simulated under a real load. |
| **Objective / score** | The mathematical value used to rank groups. Lower is better within one run and one mode; it is not a physical unit. |
| **QAOA** | Quantum Approximate Optimization Algorithm; a parameterized circuit and classical tuning loop for sampling candidate solutions. |
| **Qiskit** | IBM’s software development kit used to build and locally simulate the quantum circuits. |
| **QUBO** | Quadratic Unconstrained Binary Optimization; a way to express yes/no decisions with individual and pairwise score terms. |
| **Series string** | Cells connected end-to-end electrically. The weakest capacity can constrain the group. |
| **Shot** | One circuit execution/measurement that returns a bit string. |
| **SOH (state of health)** | Present capacity divided by nominal capacity, expressed as a fraction or percentage. |
| **Statevector** | A classical mathematical representation of an ideal quantum state used by the local simulator. |
| **Trajectory-aware** | A scoring mode that includes predicted future capacity, as well as current measurements. |
| **Uncertainty scale** | A validation residual statistic attached to forecasts. In this model it is not a calibrated confidence interval. |
| **Validation set** | Data used while developing/selecting a model configuration, distinct from data used to fit its weights. |
| **Test set** | Cells held aside from model fitting for evaluation. The project’s test cells have still been examined in earlier experiments, so they are not a pristine external validation. |
| **Weight** | The chosen importance assigned to one part of the objective. The default values are design assumptions. |


<a id="data-sources-licenses"></a>
## Data, sources, and licenses

### Software license

The RePack-Q software is made available under the MIT License. That license applies to the software; it does not grant rights to the underlying battery data or settle the data’s reuse terms.

### Battery dataset

The battery histories derive from **“Data for: Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions”** by Shuquan Wang, Feng Gao, and Hao Tian of Shandong University. The Zenodo record describes a 30-month aging campaign involving 86 NMC/graphite batteries with a nominal capacity of 2.4 Ah. It also notes that data for batteries originally labeled 61 and 62 are unavailable.

- Dataset DOI: [10.5281/zenodo.14859405](https://doi.org/10.5281/zenodo.14859405)
- Record: [Zenodo record 14859405](https://zenodo.org/records/14859405)
- Published: February 12, 2025, version 1
- License: [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

The workbench uses compact derived histories rather than the original raw measurement files. When sharing or adapting data derived from this dataset, provide appropriate credit, link to the CC BY 4.0 license, and indicate whether changes were made. Do not imply that the dataset authors endorse this application. The project’s MIT license applies to software and does not replace the battery-data license.

Suggested source citation:

> Wang, S., Gao, F., and Tian, H. “Data for: Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions.” Zenodo record 14859405 (2025), licensed under CC BY 4.0. https://doi.org/10.5281/zenodo.14859405.

### Model and saved results

The trained capacity model, its saved evaluation summary, and the selection-evidence summary are project-generated artifacts based on battery-derived records. The evidence panel shows saved results; it does not represent a new evaluation of the cells selected in the current run. The presence of these artifacts does not establish a license for the underlying data.

### Qiskit references

- [Qiskit documentation](https://quantum.cloud.ibm.com/docs/en)
- [QAOA tutorial](https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm)
- [StatevectorSampler API](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.primitives.StatevectorSampler)
- [XXPlusYYGate API](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.circuit.library.XXPlusYYGate)


<a id="implementation-overview"></a>
## Implementation overview

This optional section gives a high-level picture of how the live workbench operates. You can use the project without knowing these implementation details.

### How a comparison runs

The browser collects the selected settings and sends them through Qollab’s Python bridge. Python applies the eligibility rules, prepares predictions, scores possible groups, and runs the requested search methods. The results return to the browser as structured data and are shown in the comparison table, charts, and summary panels.

The project prepares its model and derived histories for the hosted runtime. The browser does not need a separate local server. The QAOA implementation uses a local Qiskit simulator.

### Keeping future measurements hidden

A comparison is selected using information available at the decision point. Later measured capacities are kept separate from the prediction and selection results until **Reveal actual future** is selected. Exported results include those observations only after they have been revealed.

### What the simulation means

The “quantum” methods are QAOA circuits simulated on ordinary computing hardware. They illustrate how a quantum optimization formulation can be evaluated; they do not demonstrate a quantum hardware run or a quantum speed advantage.
