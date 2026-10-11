"""Train the Java network, select a validation checkpoint, and export its weights.

Split by battery before fitting or scaling. Test cells are evaluated after
checkpoint selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
from pathlib import Path
from statistics import mean, median, pstdev

from ..prediction.features import FEATURE_NAMES, make_examples, split_cells
from .java_bridge import JavaNetwork, export_weights, read_matrix, write_control, write_matrix
from ..prediction.model import CapacityModel


def fit_preprocessing(examples: list[dict]) -> dict:
    """Fit missing-value replacements and scaling exclusively on training cells."""
    statistics = {}
    for name in FEATURE_NAMES:
        observed = [example["features"][name] for example in examples
                    if example["features"][name] is not None]
        replacement = median(observed) if observed else 0.0
        complete = [example["features"][name] if example["features"][name] is not None
                    else replacement for example in examples]
        statistics[name] = {"median": replacement, "mean": mean(complete),
                            "scale": max(pstdev(complete), 1e-9), "observed_training_values": len(observed)}
    return statistics


def summarize_errors(truth: list[float], predicted: list[float]) -> dict:
    """Report mean absolute error and root mean squared error in amp-hours."""
    if not truth:
        return {"count": 0, "mean_absolute_error_ah": None, "root_mean_squared_error_ah": None}
    residuals = [prediction - actual for actual, prediction in zip(truth, predicted)]
    return {"count": len(truth), "mean_absolute_error_ah": mean(abs(error) for error in residuals),
            "root_mean_squared_error_ah": math.sqrt(mean(error * error for error in residuals))}


def evaluate(model: CapacityModel, examples: list[dict]) -> dict:
    """Compare bounded network forecasts with persistence and recent linear trends."""
    methods = {"neural_network": [], "unchanged_capacity": [], "recent_linear_trend": []}
    truth = []
    rows = []
    for example in examples:
        features = example["features"]
        current = features["current_capacity_ah"]
        neural = max(0, min(current, model.predict_raw(features)))
        trend = features["primary_recent_slope_ah_per_cycle"] if example["cutoff"] == 0 else features["second_life_recent_slope_ah_per_cycle"]
        linear = max(0, min(current, current + min(0, trend) * example["horizon"]))
        predictions = {"neural_network": neural, "unchanged_capacity": current, "recent_linear_trend": linear}
        truth.append(example["target_capacity_ah"])
        for name, prediction in predictions.items():
            methods[name].append(prediction)
        rows.append({"cell_id": example["cell_id"], "cutoff": example["cutoff"],
                     "horizon": example["horizon"], "target_cycle": example["target_cycle"],
                     "actual_capacity_ah": example["target_capacity_ah"], **predictions})
    groups = {}
    for cutoff, horizon in sorted({(example["cutoff"], example["horizon"]) for example in examples}):
        selected = [row for row in rows if row["cutoff"] == cutoff and row["horizon"] == horizon]
        groups[f"cutoff_{cutoff}_horizon_{horizon}"] = {
            name: summarize_errors([row["actual_capacity_ah"] for row in selected], [row[name] for row in selected])
            for name in methods}
    return {"overall": {name: summarize_errors(truth, values) for name, values in methods.items()},
            "by_cutoff_and_horizon": groups, "predictions": rows}


def train(data_path: Path, output: Path, seed=2026, hidden=12, blocks=20,
          epochs_per_block=100, patience=5) -> dict:
    """Fit training cells, choose weights on validation cells, then evaluate test cells."""
    if hidden < 1 or blocks < 1 or epochs_per_block < 1 or patience < 1:
        raise ValueError("Training sizes and budgets must be positive")
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(data_path.read_text())
    splits = split_cells(data["cells"], seed)
    examples = make_examples(data["cells"])
    partitions = {name: [example for example in examples if example["cell_id"] in ids]
                  for name, ids in splits.items()}
    if any(not partition for partition in partitions.values()):
        raise ValueError("Insufficient supported examples in a cell partition")
    random.Random(seed).shuffle(partitions["train"])
    # validation and test cells must not influence input scaling
    preprocessing = fit_preprocessing(partitions["train"])
    width = len(FEATURE_NAMES) + 1
    artifact = {"schema_version": 1, "feature_names": FEATURE_NAMES, "preprocessing": preprocessing,
                "weights": [[[0.0] * hidden for _ in range(width)], [[0.0] for _ in range(hidden)]],
                "output_scale_ah": 3.0, "validation_residual_rmse_ah": 0,
                "domain": {"cutoff_max": 100, "horizon_min": 50, "horizon_max": 200,
                           "trained_cutoffs": [0, 20, 50, 100], "trained_horizons": [50, 100, 200]},
                "training_data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
                "framework": {"name": "neuralnets",
                              "commit": "f0eebb0be2d256c2d93af95b114f1cd7458dee60", "activation": "sigmoid",
                              "bias": "constant input; no explicit hidden/output biases"},
                "split_seed": seed, "cell_splits": splits,
                "training": {"hidden_width": hidden, "max_blocks": blocks, "epochs_per_block": epochs_per_block,
                             "patience_blocks": patience, "learning_rate": .03,
                             "selection": "lowest validation mean squared error; no test-set tuning"}}
    placeholder = CapacityModel(artifact)
    paths = {}
    for name in ("train", "validation"):
        inputs, targets = output / f"{name}_inputs.bin", output / f"{name}_targets.bin"
        write_matrix(inputs, [placeholder.transform(example["features"]) for example in partitions[name]])
        write_matrix(targets, [[example["target_capacity_ah"] / 3.0] for example in partitions[name]])
        paths[name] = (inputs, targets)
    weights = output / "capacity_weights.bin"
    control = output / "train_control.txt"
    write_control(control, inputs=paths["train"][0], targets=paths["train"][1], weights=weights,
                  rows=len(partitions["train"]), width=width, hidden=hidden, epochs_per_block=epochs_per_block)
    java = JavaNetwork()
    log = java.run(["train", str(control.resolve()), str(seed), str(paths["validation"][0].resolve()),
                    str(paths["validation"][1].resolve()), str(blocks), str(patience)], timeout=600)
    (output / "training.log").write_text(log)
    print(log, flush=True)
    artifact["weights"] = export_weights(weights, [width, hidden, 1])
    model = CapacityModel(artifact)

    # Verify exported Python inference against the actual Java checkpoint.
    prediction_control, prediction_path = output / "predict_control.txt", output / "java_validation_predictions.bin"
    write_control(prediction_control, inputs=paths["validation"][0], weights=weights,
                  rows=len(partitions["validation"]), width=width, hidden=hidden)
    java.run(["predict", str(prediction_control.resolve()), str(prediction_path.resolve())])
    java_values = read_matrix(prediction_path)
    max_difference = max(abs(model.predict_raw(example["features"]) / 3.0 - row[0])
                         for example, row in zip(partitions["validation"], java_values))
    if len(java_values) != len(partitions["validation"]) or max_difference > 1e-12:
        raise RuntimeError(f"Java/Python inference disagree: {max_difference}")
    validation = evaluate(model, partitions["validation"])
    artifact["validation_residual_rmse_ah"] = validation["overall"]["neural_network"]["root_mean_squared_error_ah"]
    (output / "capacity_model.json").write_text(json.dumps(artifact, indent=2, allow_nan=False))
    report = {"schema_version": 1, "seed": seed, "python_version": platform.python_version(),
              "data_sha256": artifact["training_data_sha256"], "cell_splits": splits,
              "cell_counts": {name: len(ids) for name, ids in splits.items()},
              "example_counts": {name: len(values) for name, values in partitions.items()},
              "java_python_max_absolute_difference": max_difference,
              "validation": validation, "test": evaluate(model, partitions["test"]),
              "limitations": ["Small single-dataset evaluation; related cells may share first-life protocols.",
                              "Cold-start and early-second-life forecasts are different tasks.",
                              "Validation residual scale is not a calibrated uncertainty interval.",
                              "No evidence yet of generalization to other chemistries, sites, or missions.",
                              "Dataset redistribution permissions remain a publication gate."]}
    (output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({"cell_counts": report["cell_counts"], "example_counts": report["example_counts"],
                      "test": report["test"]["overall"], "java_python_difference": max_difference}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--output", type=Path, default=Path("build/training/baseline"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--hidden", type=int, default=12)
    parser.add_argument("--blocks", type=int, default=20)
    parser.add_argument("--epochs-per-block", type=int, default=100)
    parser.add_argument("--patience", type=int, default=5)
    args = parser.parse_args()
    train(args.data.resolve(), args.output.resolve(), args.seed, args.hidden, args.blocks,
          args.epochs_per_block, args.patience)


if __name__ == "__main__":
    main()
