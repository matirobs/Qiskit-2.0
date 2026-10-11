# Classical battery selection

The predictor estimates each battery's capacity after a chosen number of cycles.
These algorithms choose a fixed-size group from those predictions and current
measurements. They do not train the predictor or estimate calendar lifetime.

## Four algorithms

| Method | What it does | Guarantee |
| --- | --- | --- |
| Healthiest | Pick the highest current capacity divided by nominal capacity | Simple reference; does not optimize compatibility |
| Greedy | Try every starting battery and repeatedly add the least costly match | Fast heuristic; may miss the best group |
| Simulated annealing | Swap selected/unselected batteries, sometimes accepting worse moves to escape local choices | Seeded heuristic; returns the best group encountered |
| Exact search | Evaluate every group of the required size | Best score for this pool and objective |

Eight candidates with four selected have 70 possible groups. Exact search is
therefore practical here, and gives the reference against which to assess other
solvers. Its default budget is 100,000 groups; larger jobs fail explicitly.
Ties within an absolute score tolerance of one billionth are counted, with at
most 100 groups recorded. The strict lowest score wins, followed by stable cell
identifiers on exact ties. A second pass records ties and the worst feasible score.

Annealing defaults to four independently initialized runs of 3,000 swaps. Every
swap preserves the selected count. Temperature decreases geometrically from the
greater of one and the pair-cost standard deviation, to 0.001. A seed makes
choices repeatable; runtime measurements naturally vary.

## Run from the project root

These modules and exported-model prediction use Python 3.10+ and the standard
library. Java and training libraries are not required to run selection.

```bash
# Invented, clearly labeled inputs; works without battery data or a trained model.
PYTHONPATH=src python3 -m repackq compare --synthetic

# Actual cached histories and the original trained model; test batteries only.
PYTHONPATH=src python3 -m repackq compare

# Sample the candidate pool from the full 86-battery dataset.
PYTHONPATH=src python3 -m repackq compare --partition all

# Include calibrated binary coefficients for inspecting the quantum problem.
PYTHONPATH=src python3 -m repackq compare \
  --export-qubo --output results/classical-comparison.json

# Updated forecast using only observations through second-life cycle 20.
PYTHONPATH=src python3 -m repackq compare --cutoff 20 --horizon 100
```

Real-data runs require `data/processed/cell_histories.json` and
`models/capacity_model.json`, created by the optional offline preparation and training
workflow. Existing local exports remain in place; new runs write to build/training
and can be selected explicitly with --model. Their byte hash must match the model's recorded dataset
hash. The active model and compact histories are included in Git. Raw files are not reread or modified.
Reports refuse to overwrite an existing output path. Store local reports under
`results/` (new JSON reports are ignored by default). The saved baseline reports
are included with source attribution in data/LICENSE.md.

Command-line comparisons default to the model's 14 declared test-cell identities.
`--partition all` samples from the full 86-battery dataset, including batteries
used to train or tune the predictor, and must not be presented as held-out
evaluation. The [dashboard](dashboard.md) defaults to this all-cell source and
offers an optional test-only source. Both paths sample a smaller shared candidate
pool before choosing a group; they do not search all 86 simultaneously or rank
the sampled candidates as the best batteries in the dataset.

Other options: `--candidates 8`, `--pack-size 4`, `--minimum-soh 0.5`,
`--mode current_only|trajectory_aware|both`, `--seeds 11 23 37`,
`--annealing-steps 3000`, `--annealing-restarts 4`, `--model`, and `--data`.
The synthetic fixture always has eight candidates and has no real future truth.

## Use from Python

```python
from repackq.api import predict_snapshot
from repackq.optimization import CellSnapshot, build_instance
from repackq.classical import exact_search, greedy_selection, simulated_annealing

# `prediction_snapshots` contains dictionaries returned by predict_snapshot(...).
# Build every snapshot from history available at the same decision point.
snapshots = [CellSnapshot.from_mapping(s) for s in prediction_snapshots]
problem = build_instance(snapshots, pack_size=4, mode="trajectory_aware")

exact = exact_search(problem)
greedy = greedy_selection(problem)
annealed = simulated_annealing(problem, seed=11)
print(exact.selected_cell_ids, exact.objective_value)
```

All four solvers return the same `SelectionResult` structure: selected indices,
cell identifiers, score, feasibility, local runtime in milliseconds, objective
contributions, and algorithm metadata. `result.to_dict()` is JSON-serializable.
`evaluate_selection` separately adds physical metrics, revealed future metrics,
and distance from the exact best score.

## Shared scoring

Two modes isolate two different scientific questions:

- `current_only`: current capacity mismatch, resistance mismatch, and a reward
  for better current health. Predicted capacity and uncertainty are not read.
- `trajectory_aware`: also consider predicted future capacity mismatch and
  optional model uncertainty. Temperature mismatch is disabled by default.

The default requested weights are 0.30 current mismatch, 0.20 resistance mismatch,
0.35 future mismatch, 0.10 health reward, and 0.05 uncertainty. These are assumptions
from the original project plan, not experimentally established physical constants. Custom
`MissionWeights` can be passed to `build_instance`.

For each feature, scaling uses only the candidate pool: median and interquartile
range, falling back to mean and population standard deviation. Constant features
contribute zero. Pair costs use weighted squared differences. The health reward
uses capacity / nominal capacity, capped at one. Unary uncertainty uses pool
minimum/maximum scaling to remain nonnegative; the exported predictor currently
provides the same residual scale for every cell, so it contributes zero variation.
It is not a calibrated confidence interval.

If an optional feature is missing for any candidate, that feature is disabled
across the whole pool and remaining active weights are normalized to sum to one.
Missing required future predictions in trajectory mode raise an error. Requested
weights, effective weights, disabled terms, and scaling statistics are recorded.
Weights for constant but available features are retained; their contribution is
zero and their lack of discrimination is recorded.

All classical solvers select exactly the requested count and score the group
without a size penalty. Optional `problem.qubo()` exports the identical score
plus a penalty for the wrong count. Here QUBO means **Quadratic Unconstrained
Binary Optimization**: a yes/no selection problem with individual and pair costs.
The export includes linear terms, each pair once, the constant offset, and the
cell order. Penalty calibration exhaustively checks that every global optimum
has the correct count; it doubles the penalty if necessary, at most five times.
Calibration is limited to 65,536 binary states by default. The Qiskit integration
uses these coefficients for the size-penalty circuit; the swap-based circuit
uses the same score without the penalty. Add `--quantum` to compare both.
See the [quantum guide](quantum.md) for installation, settings, and diagnostics.

## Evaluation without future leakage

The real adapter pairs histories by recorded battery identity. It supplies the
predictor with complete first-life history and, for positive cutoffs, only
second-life observations already available at the cutoff. For a positive cutoff,
at least four second-life reference observations are required. Candidate health
eligibility uses present capacity only. Sampling is seeded and does not rank
cells by future results or reject pools after seeing solver performance.

For retrospective evaluation, a future reference observation must exist near
cutoff + horizon, within the greater of five cycles and 5% of the horizon. Its
availability can determine eligibility; its capacity value cannot influence
predictions, the score, or selection. The nearest measurement and its distance
are reported. Future truth is passed to evaluation only after every solver runs.

The report includes:

- Current capacity spread and population standard deviation divided by mean.
- Predicted future spread and population standard deviation divided by mean.
- The same metrics from revealed actual future capacity.
- Minimum individual capacity, a simplified proxy for a series group's capacity.
- Absolute score gap from exact search, percentage gap, and regret normalized by
  the range of feasible scores. Percentage gaps can be misleading near a zero
  optimum; use the absolute gap and normalized regret as well.

Compare solvers **within the same objective mode**. Compare current-only and
trajectory-aware selection using actual future metrics, not their differently
weighted objective values. Better matching alone is insufficient if it selects
uniformly weak cells, so report future minimum capacity too. These proxies do not
simulate voltage behavior, balancing, safety, or real pack lifetime.

## Fixed exploratory benchmark

The specification's predeclared 20 seeds can be run as follows:

```bash
PYTHONPATH=src python3 -m repackq compare \
  --seeds 11 23 37 41 59 71 83 97 101 127 149 163 181 197 211 227 241 263 281 307 \
  --output results/classical-benchmark.json
```

These sample overlapping pools from the same test batteries. They are not 20
independent experiments. Those test identities have also been inspected during
earlier predictor comparisons, so the result remains exploratory. Do not tune
weights against these future outcomes and then call them an untouched test set.

On October 10, the original predictor was run on eight-candidate/four-selected
pools sampled from its 14 test batteries, at cutoff zero and horizon 200 cycles.
All 20 declared seeds were retained. The local report is
`results/classical-benchmark-20-seeds.json` (included as a saved runtime asset).

| Selection rule | Mean actual future divergence | Mean future minimum capacity |
| --- | ---: | ---: |
| Healthiest-first | 2.2498% | 1.5827 amp-hours |
| Exact current-only matching | 3.4583% | 1.5682 amp-hours |
| Exact trajectory-aware matching | 3.0909% | 1.5180 amp-hours |

Annealing matched the exact best score in 20/20 trials for each objective mode.
Greedy matched in 20/20 current-only trials and 19/20 trajectory-aware trials.
These counts describe score optimization, not prediction accuracy or a general
success guarantee. Future-aware matching reduced average actual imbalance
relative to current-only matching, but chose groups with lower minimum capacity.
Healthiest-first had the lowest actual imbalance in this run. Thus these results
do not establish that predicted-future matching is the best selection policy.

Original data SHA-256 before source-path anonymization: `278bf56b5b4b3c1d9fdebcf3b8b7ce11bff2c9bfb4bfb39911808c5ab7901e66`.
Original model SHA-256: `8a9beac45adf23214a99db3496c8b43734d84f90c4a198f2dec6de3bc5182502`.
Current metadata-only revisions are listed in `data/runtime-assets.json`;
weights, battery measurements, and recorded numerical results are unchanged.
SHA-256 is a file checksum used to identify the exact local inputs.

Tests cover a known exact optimum, every binary-state coefficient expansion for
random sizes 2 through 8, penalty feasibility, deterministic selection, every
annealing move's cardinality, constant/missing measurements, and future-data
mutation. The command-line fixture is tested without installed site packages.

Both Qiskit selection methods and their energy mapping run locally. Qollab local
and IonQ simulator verification, publication, and submission requirements remain pending.
