# Active prediction model

This folder contains the model used by default:

- `capacity_model.json`: exported network weights and preprocessing settings.
- `evaluation.json`: the original predictor's measured evaluation results.

Both files are included in Git so a fresh clone has the trained weights and
recorded evaluation. Battery-derived records retain the attribution described
in [data/LICENSE.md](../data/LICENSE.md). The original smaller model remains the default because later
training did not consistently improve the evaluation measures.

Temporary matrices, controls, and logs do not belong here. New offline training
runs default to `build/training/`. Old models, binary checkpoints, and logs were
removed from the working tree; see [training history](../docs/guides/training.md).
To try another exported model, pass `--model PATH` to prediction or comparison;
this does not replace the active model.
