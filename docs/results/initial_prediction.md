# Initial held-out prediction results

This is one deterministic within-dataset experiment, not a claim of general performance.

- Prepared raw rows: 145,112,317 across 86 cells and two phases.
- Cells: 60 training, 12 validation, 14 test; no cell crosses partitions.
- Forecast cases: 702 training, 141 validation, 167 test.
- Forecast horizons: 50, 100, 200 cycles.
- One 16-input, 12-hidden-neuron, 1-output sigmoid network; seed 2026.
- Maximum 2,000 training passes, with validation checkpoint selection.
- Test values were inspected only after checkpoint selection. No test-based tuning.

| Known second-life cycles | Test forecasts | Neural mean absolute error (amp-hours) | Unchanged-capacity error | Recent linear-trend error |
|---|---:|---:|---:|---:|
| 0 | 42 | 0.049343 | 0.174683 | 0.283464 |
| 20 | 42 | 0.059201 | 0.159047 | 0.215110 |
| 50 | 42 | 0.065147 | 0.167892 | 0.089518 |
| 100 | 41 | 0.064536 | 0.174736 | 0.066704 |

Zero known second-life cycles is the first-life-only cold-start task. Other rows
also use observations already available during second life. Multiple forecasts
belong to each cell and are not independent experimental subjects.

Overall neural mean absolute error: 0.059527 amp-hours. Overall root mean
squared error: 0.076914 amp-hours. Validation residual root mean squared error:
0.086715 amp-hours, used only as a rough uncertainty scale.

Maximum absolute Java/Python output difference before capacity scaling:
`1.1102230246251565e-16`.

Full per-horizon metrics, predictions, and cell partition lists are retained
locally in models/evaluation.json. The learned model is models/capacity_model.json.

Original prepared data SHA-256 before source-path anonymization: `278bf56b5b4b3c1d9fdebcf3b8b7ce11bff2c9bfb4bfb39911808c5ab7901e66`.
Current artifact hashes are listed in `data/runtime-assets.json`; observations
and weights are unchanged.
Source fingerprint at review: `8114fc0235b95493483f42223fae6acb71b1622e39e132e8de006ad378b75556`.

Limits: the split can share first-life protocols between partitions. Unseen
chemistries, test conditions, and household load scenarios are not validated.
The model constrains forecasts not to exceed current capacity. All derived
data and models remain local pending dataset redistribution review.
