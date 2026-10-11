# Optional offline training

Training programs live in `src/repackq/training/` and are separate from runtime
prediction and selection. New jobs write disposable matrices, controls, logs, and
exports under `build/training/`; they do not replace the active model.

Install optional dependencies with `python3 -m pip install -e '.[training]'`.
A Java Development Kit version 17 or newer is also required. With
`PYTHONPATH=src`, reproduce the original small baseline using:

```bash
python3 -m repackq prepare
python3 -m repackq train
python3 -m repackq predict --model build/training/baseline/capacity_model.json \
  --cell 9 --cutoff 0 --horizon 200
python3 -m repackq compare --model build/training/baseline/capacity_model.json
```

Preparation is unnecessary when the existing cached histories are available.
The active original model remains in `models/capacity_model.json`. The user
requested removal of old experiment exports and logs on October 11. Their
archive remains recoverable from Git commit `4264ed6` at
`experiments/results/training-2026-10-10.zip`; it is not needed to run the app.
The result summaries in `docs/results/` and optional training source remain.
The old `repackq.prediction.train*` and `repackq.prediction.tune*` commands moved
to `repackq.training`; use the commands below rather than the previous paths.

## Expanded history model

The expanded model uses all extracted reference observations, many more forecast
tasks, and three hidden activation layers. It remains the classical predictor;
the planned Qiskit quantum-selection subroutine is unchanged.

## Size and inputs

| | Initial model | Expanded reference-history model |
|---|---:|---:|
| Training cells | 60 | 60 |
| Training forecast examples | 702 | 175,781 |
| First-life-only training examples | 180 | 2,340 |
| Numerical history and horizon inputs | 15 | 527 |
| Hidden layers | 12 | 128 → 64 → 32 |
| Learned weights | 204 | 77,856 |

The expanded topology is **528 → 128 → 64 → 32 → 1**, including a constant input
for the original framework's first-layer intercept. This is five activation
layers when counting the input and output, or three hidden layers. Hidden
neurons use the hyperbolic tangent function; the output uses sigmoid, scaled to
3 amp-hours. The original framework still has no separate hidden/output biases.
New initialization scales each layer's weights to its input/output width, and
training cases are shuffled reproducibly on every complete pass.

The completed first run took 301.3 seconds for the Java training job and selected
pass three after stopping at pass nine. On the original 167-case benchmark its
mean absolute error was 0.085247 amp-hours, versus 0.059527 for the small model.
The larger model is currently less accurate on that comparison. See
[expanded results](../results/expanded_prediction.md). The all-measurement variant remains
untrained while raw files are cloud-only.

The original 15 inputs are retained. Each life phase also has 32 chronological
bins, each containing mean/minimum/maximum capacity, mean resistance, mean
temperature, relative cycle position, logarithmic observation count, and an
observed/empty indicator. Every reference observation contributes to its bin.
Pooling preserves broad history shape and extrema; it is not a raw-waveform
sequence network and does not retain the exact order within a bin.

Dense forecast cases use zero known second-life cycles and every subsequent
reference observation with at least four known reference points. Each starting
point is paired with every measured future capacity 5–200 cycles later. Targets
are measured values, never interpolated or generated. All 9,905 first-life and
8,168 second-life reference observations are retained in the prepared dataset;
a late observation may serve as a target without supporting a later forecast.

## Train and run

```bash
export PYTHONPATH=src
python3 -m repackq.training.train_full
python3 -m repackq.prediction.predict \
  --model build/training/full_history/capacity_model.json \
  --cell 9 --cutoff 0 --horizon 200
```

The default budget is 30 full training passes, with stopping after six passes
without improved validation error. The best validation checkpoint is exported,
not necessarily the final training state. Direct timers report Java training
and total preparation/training/evaluation separately. Progress is written live
to build/training/full_history/training.log; run_summary.json records dimensions/counts.
The Java job timer includes process startup, matrix loading, validation, and
checkpoint writes; Java compilation happens before that timer starts.

Architecture and budget are configurable, for example:

```bash
python3 -m repackq.training.train_full \
  --hidden 256 128 64 32 --bins 64 --blocks 50 \
  --output build/training/full_history/extra_large
```

That command builds an additional experiment; larger size is not an accuracy
guarantee. The original small model remains under models/capacity_model.json.
Use the explicit model path when forecasting with a larger model. The Python
application can load either version through CapacityModel without Java or
third-party numerical libraries at prediction time.

## Include all raw measurement steps

The default expanded experiment uses the cached reference histories. A second
preparation path processes every row and operating step, including operational
discharges previously excluded from the capacity target. It adds current,
voltage, temperature, resistance, charge/discharge capacity and energy extrema,
row count, and elapsed-time summaries to each known history interval.

```bash
python3 -m repackq.training.prepare_full --available-only
python3 -m repackq.training.prepare_full
python3 -m repackq.training.train_full \
  --data data/processed/cell_histories_full.json --usage \
  --output build/training/all_measurements
python3 -m repackq.prediction.predict \
  --model build/training/all_measurements/capacity_model.json \
  --data data/processed/cell_histories_full.json \
  --cell 9 --cutoff 0 --horizon 200
```

All source files must be locally readable. On macOS, cloud-only files are
reported explicitly rather than blocking indefinitely or being silently
discarded. The available-only option caches readable files and reports missing
ones in data/processed/usage_availability.json; it never writes an incomplete
training dataset. Rerunning resumes the cache. Source checksums and row counts
must match the original extraction.

This optional topology is **1552 → 128 → 64 → 32 → 1**, with 208,928 weights.
It still summarizes raw measurements instead of treating 145 million correlated
sensor readings as independent degradation examples. Means are weighted by
measurement count within each usage interval, not by time; charge/energy values
are maxima, not estimates of cumulative lifetime throughput. Interval summaries
are pooled equally when multiple intervals fall into one history bin.

Second-life usage ends at the observation defining each interval. Future usage
cannot enter an earlier history. First-life trailing measurements are known at
retirement and join its final interval. Second-life trailing rows without a later
reference observation are counted explicitly and excluded from earlier inputs.
Comparable reference discharges remain the prediction targets: operational
discharges at different currents/endpoints do not become misleading labels.

## Evaluation and limits

Entire batteries remain separated: 60 train, 12 validation, and 14 test. Scaling
and missing-value replacements use unique training histories only; the horizon
input uses the training forecast cases. Validation selects the checkpoint.
Java/Python agreement is checked on 32 validation forecasts for the deeper model.

Reports include dense-forecast errors, first-life-only errors, per-cell errors,
and a mean giving each test cell equal weight. A separate 167-case test benchmark
repeats the initial model's tasks for comparison. The same test identities were
already examined in the initial experiment: this is an exploratory reused
holdout, not a new independent blind test. No test-based architecture selection
is performed by the trainer.

More forecast windows do not create more independent batteries. Long records
contribute more dense cases, and early second-life forecasts greatly outnumber
first-life-only forecasts. Both tasks are reported separately. Deeper layers
may overfit or perform worse, particularly on the first-life-only task. Results
must be reported even when the expanded model loses to the small model or a
simple classical baseline. Models assume no capacity increase; transfer to new
chemistries/protocols and calibrated uncertainty remain unverified.

Raw data, extracted usage histories, and trained artifacts remain local. Dataset
redistribution permission, Qollab simulator validation, publication, and the
other hackathon submission requirements remain separate pending gates.
