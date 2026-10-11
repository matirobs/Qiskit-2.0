"""Train the larger network on pooled histories and measured future targets.

Reuse encoded inputs for each cell and cutoff. Training matrices stay on disk
to keep memory use manageable."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import time
from pathlib import Path

import numpy as np

from ..prediction.features import make_examples, split_cells
from ..prediction.full_history import case_features, dense_cases, feature_names
from .java_bridge import JavaNetwork, export_weights, read_matrix, write_control, write_matrix
from ..prediction.model import CapacityModel
from .train import evaluate, summarize_errors


def build_contexts(cases, cells, spec):
    """Encode each (cell, cutoff) once; forecast distance is replaced per case."""
    names = feature_names(spec)
    keys = list(dict.fromkeys((c["cell_id"], c["cutoff"]) for c in cases))
    cells_by_id = {c["cell_id"]: c for c in cells}
    rows = np.empty((len(keys), len(names)))
    for index, (cell_id, cutoff) in enumerate(keys):
        values = case_features({"cell_id": cell_id, "cutoff": cutoff, "horizon": 5}, cells_by_id, spec)
        rows[index] = [values[name] if values[name] is not None else np.nan for name in names]
    return keys, rows


def fit_full_preprocessing(keys, rows, training_ids, training_cases, names):
    """Fit history statistics to training contexts only; all-missing features use zero."""
    selected = rows[[key[0] in training_ids for key in keys]]
    fitted = {}
    for column, name in enumerate(names):
        values = (np.array([c["horizon"] for c in training_cases], dtype=float)
                  if name == "horizon_cycles" else selected[:, column])
        finite = values[np.isfinite(values)]
        replacement = float(np.median(finite)) if len(finite) else 0.0
        complete = np.where(np.isfinite(values), values, replacement)
        fitted[name] = {"median": replacement, "mean": float(complete.mean()),
                       "scale": max(float(complete.std()), 1e-9), "observed_training_values": len(finite)}
    return fitted


def write_cases(path, cases, rows, context_indices, preprocessing, names):
    """Write big-endian Java input using a disk-backed matrix and bounded chunks."""
    width = len(names) + 1
    with path.open("wb") as stream:
        stream.write(struct.pack(">ii", len(cases), width))
        stream.truncate(8 + 8 * len(cases) * width)
    matrix = np.memmap(path, mode="r+", dtype=">f8", offset=8, shape=(len(cases), width))
    medians = np.array([preprocessing[n]["median"] for n in names])
    centers = np.array([preprocessing[n]["mean"] for n in names])
    scales = np.array([preprocessing[n]["scale"] for n in names])
    horizon_column = names.index("horizon_cycles")
    for start in range(0, len(cases), 1024):
        chunk = cases[start:start + 1024]
        raw = rows[[context_indices[(c["cell_id"], c["cutoff"])] for c in chunk]].copy()
        raw[:, horizon_column] = [c["horizon"] for c in chunk]
        raw = np.where(np.isfinite(raw), raw, medians)
        matrix[start:start + len(chunk), :-1] = (raw - centers) / scales
        matrix[start:start + len(chunk), -1] = 1.0
    matrix.flush()
    del matrix


def evaluate_dense(cases, predictions, contexts, keys, names):
    """Report forecast and per-cell errors, including first-life-only forecasts."""
    current_column = names.index("current_capacity_ah")
    primary_slope = names.index("primary_recent_slope_ah_per_cycle")
    second_slope = names.index("second_life_recent_slope_ah_per_cycle")
    current = np.array([contexts[keys[(c["cell_id"], c["cutoff"])]][current_column] for c in cases])
    trends = np.array([contexts[keys[(c["cell_id"], c["cutoff"])]][
        primary_slope if c["cutoff"] == 0 else second_slope] for c in cases])
    horizons = np.array([c["horizon"] for c in cases])
    truth = np.array([c["target_capacity_ah"] for c in cases])
    methods = {"neural_network": np.clip(predictions, 0, current), "unchanged_capacity": current,
               "recent_linear_trend": np.clip(current + np.minimum(0, trends) * horizons, 0, current)}
    def metrics(mask):
        return {name: summarize_errors(truth[mask].tolist(), values[mask].tolist())
                for name, values in methods.items()}
    cold = np.array([c["cutoff"] == 0 for c in cases])
    per_cell = {identifier: metrics(np.array([c["cell_id"] == identifier for c in cases]))
                for identifier in sorted({c["cell_id"] for c in cases}, key=int)}
    return {"overall": metrics(np.ones(len(cases), dtype=bool)),
            "first_life_only": metrics(cold), "updated_forecasts": metrics(~cold),
            "per_cell": per_cell,
            "cell_macro_mean_absolute_error_ah": {name: float(np.mean([
                row[name]["mean_absolute_error_ah"] for row in per_cell.values()])) for name in methods}}


def train_full(data_path: Path, output: Path, *, hidden=(128, 64, 32), bins=32,
               blocks=30, patience=6, seed=2026, learning_rate=.003,
               minimum_horizon=5, maximum_horizon=200, usage=False):
    """Train on dense forecast cases and verify the exported Python predictions."""
    if (not 1 <= bins <= 256 or blocks < 1 or patience < 1 or learning_rate <= 0
            or not hidden or any(not isinstance(size, int) or size < 1 for size in hidden)):
        raise ValueError("Invalid model size or training budget")
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(data_path.read_text())
    if usage and not all("usage" in p for c in data["cells"] for phase in ("primary", "second_life") for p in c[phase]):
        raise ValueError("Run repackq.training.prepare_full before --usage training")
    spec = {"kind": "full_history_v2", "bins": bins, "usage": usage}
    names = feature_names(spec)
    splits = split_cells(data["cells"], seed)
    cases = dense_cases(data["cells"], minimum_horizon, maximum_horizon)
    partitions = {name: [case for case in cases if case["cell_id"] in ids] for name, ids in splits.items()}
    if any(not rows for rows in partitions.values()):
        raise ValueError("Every cell partition needs supported forecasts")
    # Reproducible initial ordering plus a fresh Java shuffle on every pass.
    import random
    random.Random(seed).shuffle(partitions["train"])
    keys, contexts = build_contexts(cases, data["cells"], spec)
    indices = {key: index for index, key in enumerate(keys)}
    preprocessing = fit_full_preprocessing(keys, contexts, set(splits["train"]), partitions["train"], names)
    width = len(names) + 1
    paths = {}
    for name, selected in partitions.items():
        path = output / f"{name}_inputs.bin"
        write_cases(path, selected, contexts, indices, preprocessing, names)
        paths[name] = path
    target_paths = {}
    for name in ("train", "validation"):
        target_paths[name] = output / f"{name}_targets.bin"
        write_matrix(target_paths[name], [[c["target_capacity_ah"] / 3] for c in partitions[name]])
    # append a constant input because the Java network has no separate bias weights
    dimensions = [width, *hidden, 1]
    weights_path = output / "capacity_weights.bin"
    control = output / "train_control.txt"
    write_control(control, inputs=paths["train"], targets=target_paths["train"], weights=weights_path,
        rows=len(partitions["train"]), width=width, hidden=hidden, epochs_per_block=1,
        hidden_activation="tanh", learning_rate=learning_rate, shuffle=True)
    summary = {"dimensions": dimensions, "weight_count": sum(a*b for a,b in zip(dimensions, dimensions[1:])),
               "cell_counts": {k: len(v) for k,v in splits.items()},
               "example_counts": {k: len(v) for k,v in partitions.items()},
               "cold_start_examples": {k: sum(c["cutoff"] == 0 for c in v) for k,v in partitions.items()},
               "reference_observations": {phase: sum(len(c[phase]) for c in data["cells"])
                                          for phase in ("primary", "second_life")},
               "prepared_seconds": time.perf_counter() - started}
    (output / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    bridge = JavaNetwork()
    java_seconds = bridge.run_logged(["train", str(control.resolve()), str(seed),
        str(paths["validation"].resolve()), str(target_paths["validation"].resolve()), str(blocks), str(patience)],
        output / "training.log")
    artifact = {"schema_version": 2, "feature_spec": spec, "feature_names": names,
        "preprocessing": preprocessing, "hidden_activation": "tanh",
        "weights": export_weights(weights_path, dimensions), "output_scale_ah": 3.0,
        "validation_residual_rmse_ah": 0, "training_data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "domain": {"cutoff_max": max(c["cutoff"] for c in partitions["train"]),
                   "horizon_min": minimum_horizon, "horizon_max": maximum_horizon},
        "framework": {"name": "neuralnets",
                      "commit": "f0eebb0be2d256c2d93af95b114f1cd7458dee60",
                      "bias": "constant input; no explicit hidden/output biases"},
        "cell_splits": splits, "split_seed": seed,
        "training": {"hidden_sizes": list(hidden), "max_passes": blocks, "patience_passes": patience,
            "learning_rate": learning_rate, "shuffle_each_pass": True,
            "scaler": "unique training histories; horizon fitted to training forecast cases",
            "selection": "lowest validation mean squared error; no test-based selection",
            "java_seconds": java_seconds}}
    model = CapacityModel(artifact)
    outputs = {}
    for name in ("validation", "test"):
        prediction_control = output / f"predict_{name}.txt"
        prediction_path = output / f"java_{name}_predictions.bin"
        write_control(prediction_control, inputs=paths[name], weights=weights_path, rows=len(partitions[name]),
                      width=width, hidden=hidden, hidden_activation="tanh")
        bridge.run(["predict", str(prediction_control.resolve()), str(prediction_path.resolve())], timeout=1800)
        outputs[name] = np.array([p[0] * 3 for p in read_matrix(prediction_path)])
    # check that exported weights give the same predictions in Python and Java
    checks = np.linspace(0, len(partitions["validation"]) - 1, min(32, len(partitions["validation"])), dtype=int)
    cells_by_id = {c["cell_id"]: c for c in data["cells"]}
    difference = max(abs(model.predict_raw(case_features(partitions["validation"][i], cells_by_id, spec))
                         - outputs["validation"][i]) for i in checks)
    if difference > 1e-11:
        raise RuntimeError(f"Deep Java/Python inference disagree: {difference}")
    validation = evaluate_dense(partitions["validation"], outputs["validation"], contexts, indices, names)
    artifact["validation_residual_rmse_ah"] = validation["overall"]["neural_network"]["root_mean_squared_error_ah"]
    (output / "capacity_model.json").write_text(json.dumps(artifact, indent=2, allow_nan=False))
    # Same sparse forecast tasks as the initial model make comparisons interpretable.
    benchmark = [case for case in make_examples(data["cells"]) if case["cell_id"] in splits["test"]
                 and minimum_horizon <= case["horizon"] <= maximum_horizon]
    for case in benchmark:
        case["features"] = case_features(case, cells_by_id, spec)
    report = {**summary, "seed": seed, "feature_spec": spec, "cell_splits": splits,
        "data_sha256": artifact["training_data_sha256"], "java_training_seconds": java_seconds,
        "completed_passes": len(re.findall(r"^block=", (output / "training.log").read_text(), re.M)),
        "java_python_checked_forecasts": len(checks), "java_python_max_absolute_difference_ah": difference,
        "validation": validation,
        "test": evaluate_dense(partitions["test"], outputs["test"], contexts, indices, names),
        "initial_benchmark_test": evaluate(model, benchmark),
        "total_seconds": time.perf_counter() - started,
        "limitations": ["Dense forecasts from one cell are correlated; only 86 independent cell identities.",
            "Existing test cells were examined in the initial experiment; this is an exploratory reused holdout.",
            "History pooling retains all observations but does not preserve every raw waveform sample.",
            "All-measurement usage channels are included only when feature_spec.usage is true.",
            "Validation residual scale is not calibrated uncertainty; chemistry/protocol transfer is unverified."]}
    (output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({"java_training_seconds": java_seconds, "completed_passes": report["completed_passes"],
                      "dense_test": report["test"]["overall"],
                      "initial_benchmark_test": report["initial_benchmark_test"]["overall"]}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--output", type=Path, default=Path("build/training/full_history"))
    parser.add_argument("--hidden", type=int, nargs="+", default=[128, 64, 32])
    parser.add_argument("--bins", type=int, default=32)
    parser.add_argument("--blocks", type=int, default=30, help="Maximum complete training passes")
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--learning-rate", type=float, default=.003)
    parser.add_argument("--minimum-horizon", type=int, default=5)
    parser.add_argument("--maximum-horizon", type=int, default=200)
    parser.add_argument("--usage", action="store_true", help="Require all-measurement usage histories")
    args = vars(parser.parse_args())
    data, output = args.pop("data"), args.pop("output")
    train_full(data.resolve(), output.resolve(), **args)


if __name__ == "__main__":
    main()
