# Second-life degradation predictor

This page describes the initial small baseline. See [the expanded history
model](training.md) for the newer dense training pipeline, deeper layers,
and optional all-measurement inputs. Both model formats support the same Python
prediction boundary; choose the exported model path explicitly.

The model forecasts reference discharge capacity in amp-hours at a specified
number of cycles after the decision point. Predicted degradation is the
difference between current capacity and predicted future capacity.

## Java and Python responsibilities

1. Python streams the raw files into reference-capacity histories.
2. Python builds 15 history features and appends a constant intercept input.
3. Java trains the user's existing fully connected sigmoid network.
4. Validation cells select the best checkpoint; test cells are held out.
5. Python exports weights and scaling to JSON and checks Java/Python agreement.
6. The rest of the application calls Python-only inference. No Java process,
   training library, credentials, or external service is needed for inference.

The default network has 16 inputs (15 features plus a constant), 12 hidden
neurons, and one sigmoid output scaled to 3 amp-hours. The framework has no
explicit neuron biases; the constant supplies a first-layer intercept. Features
include sampled first-life capacities, lifetime span and recent decline,
resistance, temperature, available second-life history, and forecast horizon.
Cell IDs and future measurements are not model inputs.

## Run locally

Use Python 3.10 or newer. With existing local weights and cached histories:

```bash
export PYTHONPATH=src
python3 -m repackq predict --cell 9 --cutoff 0 --horizon 200
python3 -m repackq predict --cell 9 --cutoff 20 --horizon 100
```

Alternatively install with `python3 -m pip install -e .`, then run `repackq predict`.
No Java or third-party numerical libraries are required for prediction.

Preparation and training are optional offline steps documented in the
[training guide](training.md). New training outputs go under `build/training/`;
`models/` keeps only the active exported model and its evaluation. Old experiment
artifacts were removed; their Git history is described in the
[training guide](training.md).
Raw measurements and prepared caches were retained during cleanup.

## Forecast from the rest of the Python project

```python
from repackq.api import predict_snapshot
from repackq.prediction.model import CapacityModel

model = CapacityModel.load("models/capacity_model.json")
snapshot = predict_snapshot(
    model,
    cell_id="9",
    primary_history=known_first_life_points,
    observed_second_life=known_second_life_points,
    cutoff=20,
    horizon=100,
)
future_capacity = snapshot["predicted_capacity_ah"]
```

Each history point contains cycle, capacity_ah, resistance_ohm, and temperature_c
(the latter two may be null). With cutoff zero, pass an empty second-life list.
At positive cutoffs, every second-life point must be at or before that cutoff.
Passing future points raises an error. The selection objective can consume the
predicted_capacity_ah and prediction_uncertainty_ah fields from this snapshot.
The latter is a validation residual scale, not a calibrated confidence interval.

## Scientific limits

- Training, validation, and test sets share no cells. They may share first-life
  protocols, so this is within-dataset evaluation, not proof of unseen-protocol
  or real-world deployment performance.
- Cold-start uses first-life history alone. Updated forecasts also use already
  observed second-life history; their errors are reported separately.
- Available training cutoffs are 0, 20, 50, and 100 cycles; horizons are 50, 100,
  and 200 cycles. In-range interpolation is possible but not separately validated.
- Targets are actual reference measurements within the documented cycle tolerance;
  unavailable targets are omitted based on coverage, not solver/model performance.
- Forecasts assume no capacity increase. This does not model recovery, arbitrary
  household loads, chemistry changes, or certified battery safety.
- Persistence and recent linear trends are reported alongside the neural model.
  An inferior model result must remain visible.
- Qollab packaging and an actual Qiskit simulator run are still separate tasks.
  A Python export avoids a Java runtime dependency but does not prove deployment.
