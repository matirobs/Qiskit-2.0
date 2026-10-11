# Expanded reference-history experiment

The larger model trained successfully, but it did not improve the original
benchmark. Both models are preserved. These are exploratory results on reused
held-out cell identities, not a new blind test or a generalization claim.

## Run

- Input: all cached reference histories, 9,905 first-life and 8,168 second-life
  observations across 86 cells. No all-measurement usage channels in this run.
- Entire-cell split: 60 training, 12 validation, 14 test; seed 2026.
- Dense forecast cases: 175,781 training, 33,108 validation, 40,346 test.
- First-life-only cases: 2,340 training, 468 validation, 546 test.
- Topology: 528 → 128 → 64 → 32 → 1; 77,856 weights.
- Hidden activation: hyperbolic tangent; output: sigmoid scaled to 3 amp-hours.
- Learning rate: 0.003; per-pass deterministic shuffling; no test-based selection.
- Java training job: **301.306 seconds**. Nine complete passes; best validation
  checkpoint at pass three, then six unimproved passes triggered stopping.
- Total history encoding, matrix preparation, training, export, and evaluation:
  **325.029 seconds**. Raw-file extraction is excluded from both timers.
- Maximum Java/Python prediction difference on 32 validation forecasts:
  0.000000000000000888 amp-hours.

## Shared original benchmark

Mean absolute capacity error in amp-hours; lower is better. These tasks use the
same held-out cells, cutoffs, horizons, and labels as the initial experiment.

| Known second-life cycles | Cases | Small network | Expanded network |
|---|---:|---:|---:|
| 0 | 42 | 0.049343 | 0.078136 |
| 20 | 42 | 0.059201 | 0.081893 |
| 50 | 42 | 0.065147 | 0.072386 |
| 100 | 41 | 0.064536 | 0.109143 |
| All | 167 | **0.059527** | **0.085247** |

On these cases, unchanged-capacity prediction has error 0.169056 and the recent
linear trend has error 0.164280. Both neural models beat those two comparisons,
but the small neural model is better than the expanded one.

## Dense test tasks

The dense tasks include many more decision points and short forecast horizons.
Their aggregate errors cannot be compared directly with the sparse benchmark.

| Method | Mean absolute error | Root mean squared error | Equal-cell mean absolute error |
|---|---:|---:|---:|
| Expanded network | 0.095503 | 0.124331 | 0.098606 |
| Unchanged capacity | 0.131051 | 0.161611 | 0.141249 |
| Recent linear trend | **0.058525** | **0.102243** | **0.059258** |

The recent linear trend wins across the full dense test set. On its 546
first-life-only forecasts, the expanded network's mean absolute error is
0.074947, versus 0.149783 for unchanged capacity and 0.247850 for the linear
trend. Forecasting before second life and updating from already-observed
second-life measurements are different tasks and should remain separate.

Validation mean absolute errors on the dense tasks were 0.086405 for the network,
0.131202 for unchanged capacity, and 0.064366 for the linear trend. The checkpoint
was selected by validation mean squared error, not these test results.

Increasing forecast count did not increase the number of independent batteries.
Related forecast windows are correlated, long records contribute more cases,
and the network has many more weights than independent training cells. These
results do not establish the cause of the loss in accuracy. Do not claim that
more layers or more forecast windows guarantee better prediction.

## All-measurement preparation status

Eleven raw files were fully processed and checksum-verified: **28,816,575 rows**.
The other **161 files** were marked cloud-only during preparation. The available
file cache was retained, but no partial all-measurement training dataset or model
was published or trained. Download the raw files locally and rerun the commands
in [the expanded model instructions](../guides/training.md).

Historical exports and logs were removed at the user's request; their Git
history is described in the [training guide](../guides/training.md).
Prepared histories remain under data/processed. New expanded runs write to
build/training/full_history. The initial small artifacts remain unchanged.
Dataset attribution and redistribution terms are recorded in data/LICENSE.md;
Qollab execution/publication remain pending. Original prepared-history checksum
before source-path anonymization (current hashes are in `data/runtime-assets.json`):
`278bf56b5b4b3c1d9fdebcf3b8b7ce11bff2c9bfb4bfb39911808c5ab7901e66`.
