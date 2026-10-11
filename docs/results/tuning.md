# Capacity success tuning

Retraining produced a modest improvement at the 5% tolerance and regressions at
other comparisons. The original predictor remains the default; the tuned models
are additional experiments, not a demonstrated overall replacement.

Success means absolute prediction error divided by actual capacity is at most
0.05 or 0.10. Tolerances, test cell identities, and the 167 benchmark labels were
kept fixed. These are correlated forecasts from 14 cells whose earlier results
were already inspected, so this is an exploratory reused holdout.

## Shared test results

| Model | Within 5% | Within 10% | Mean absolute error, amp-hours |
|---|---:|---:|---:|
| Original small network | 122/167 (73.1%) | 157/167 (94.0%) | 0.059527 |
| Expanded history network | 94/167 (56.3%) | 148/167 (88.6%) | 0.085247 |
| First tuning sweep winner | 122/167 (73.1%) | 153/167 (91.6%) | 0.066235 |
| Cross-validation-selected final refit | **124/167 (74.3%)** | 153/167 (91.6%) | 0.061934 |

For first-life-only forecasts, the original small model achieves 36/42 (85.7%)
within 5%; the final refit achieves 34/42 (81.0%). Both achieve 41/42 (97.6%)
within 10%. The first tuning sweep achieves 32/42 (76.2%) within 5%.

The final refit adds two successes at the 5% tolerance across all cases, but loses
four successes at 10% and two first-life-only successes at 5%. This is not
evidence of a reliable broad improvement. No statistical significance is claimed.

## Search stages

1. **Mixed-task tuning:** 15 Java training configurations tested learning rates,
   initial seeds, one/two hidden layers, capacity versus current-residual targets,
   balanced early-life examples, chronological history inputs, and all-window
   training with explicitly repeated first-life-only cases. Same-encoding
   averaging ensembles were also compared. The original 12 validation cells
   selected checkpoints/candidates using success within 5%, then within 10%,
   then mean absolute percentage error. The winner was a 12-neuron sigmoid model,
   learning rate 0.08, seed 2026. Workflow runtime: 146.724 seconds.
2. **Task-specific tuning:** 24 new Java configurations separately trained
   first-life-only and updated forecasts. These included relative-error loss
   weighting, weight decay, and optional known first-life protocol categories.
   Maximum budgets increased to 12,000 passes. Neither task selected these new
   models over the first sweep's model, so the routed export duplicates that
   model's predictions. Protocol inputs were not selected. Workflow runtime:
   47.652 seconds.
3. **Cross-validation and refit:** Eight settings were compared across five cell
   folds of the 72 development batteries, giving 40 fold fits and 843 pooled
   out-of-fold forecasts per setting. Fold checkpoints minimized validation mean
   squared error; pooled success selected settings and compared averaging
   ensembles. Settings and the median pass budget were frozen before final
   refitting and test prediction. Workflow runtime: 93.992 seconds.

There were **80 Java fitting jobs** including the final refit. These are repeated
experiments on the same batteries, not independent datasets. Search plans,
validation results, logs, selected settings, and exports are retained locally.

## Final refit configuration

- Model: 16 inputs including a constant → 12 sigmoid hidden neurons → one sigmoid
  output scaled to 3 amp-hours. Fifteen history/horizon features; 204 weights.
- Learning rate: 0.03; seed 2026; no weight decay, relative-loss weighting, or
  reshuffling between passes. The initial example order is reproducibly shuffled.
- Maximum cross-validation budget: 12,000 passes per fold, with 2,000 unimproved
  passes allowed before stopping. Checkpoints are inspected every 100 passes.
- Selected fold pass counts: 3,200, 400, 2,600, 1,500, 3,300. Median: **2,600**.
- Final training: **72 development cells, 843 forecast examples, 2,600 passes**.
  This is 30% more passes than the initial model's 2,000.
- Final preprocessing is fitted to these 72 cells. Their labels are fitting data,
  so the original 12 validation cells are no longer independent validation cells.
- The original 14 test cells are excluded from every fold and final fitting.
- Pooled cross-validation success: 610/843 (72.36%) within 5%, 780/843 (92.53%)
  within 10%. Cross-validation residual scale is not calibrated uncertainty.
- Protocol identifiers, battery identities, and future observations are not model
  inputs in the final refit. Protocol-informed candidates remain optional trials.

Increasing iterations and changing settings did not consistently increase all
success percentages. These experiments do not isolate a single cause. More
independent cells and richer historical inputs remain directions to investigate,
not guarantees of improvement. The all-measurement variant still awaits readable
raw files; it was not silently substituted with partial data.

## Reproduce and run

The completed run's models, settings, and logs were removed from the working
tree at the user's request. The [training guide](../guides/training.md) records
the archived files' Git history. Regenerable matrices were also removed during
cleanup. The active original predictor remains available without retraining.

To reproduce the searches, with training dependencies and Java installed:

```bash
export PYTHONPATH=src
python3 -m repackq.training.tune
python3 -m repackq.training.tune_experts
python3 -m repackq.training.tune_refit
python3 -m unittest discover -s tests -v
```

New outputs default to `build/training/tuned`, with `experts` and `refit`
subfolders. Run the first sweep before the expert sweep: the expert sweep uses
`build/training/tuned/capacity_model.json` as a validation fallback. The refit
experiment is independent and can run on its own. Use a separate --output path
for additional trials; the active model in models/ is not replaced by defaults.

Exported inference uses Python's standard library. All recorded artifacts stay
local pending dataset permission review. The previously described Qollab and
hackathon release gates remain pending.
