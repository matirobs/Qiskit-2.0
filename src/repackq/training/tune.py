"""Compare network settings using validation forecasts.

Select models and ensembles before evaluating test cells. Success means a
fixed relative error tolerance, measured against actual capacity."""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import random
import re
import time
from pathlib import Path

from ..prediction.features import FEATURE_NAMES, build_features, make_examples, split_cells
from ..prediction.full_history import build_full_features, dense_cases, feature_names
from .java_bridge import JavaNetwork, export_weights, read_matrix, write_control, write_matrix
from ..prediction.model import CapacityModel
from .train import evaluate, summarize_errors


def success_metrics(truth, predictions):
    """Fixed tolerances relative to actual capacity, with counts and denominator."""
    if not truth or len(truth) != len(predictions) or any(y <= 0 for y in truth):
        raise ValueError("Success metrics need matching nonempty positive capacity targets")
    relative = [abs(p-y)/y for y,p in zip(truth,predictions)]
    counts = {str(t): sum(error <= t for error in relative) for t in (.05, .10)}
    return {**summarize_errors(truth, predictions), "within_5_percent_count": counts["0.05"],
            "within_10_percent_count": counts["0.1"],
            "within_5_percent": 100*counts["0.05"]/len(truth),
            "within_10_percent": 100*counts["0.1"]/len(truth),
            "mean_absolute_percentage_error": 100*sum(relative)/len(relative)}


def rank(metrics):
    """Prefer within-5% success, then within-10%, then lower relative error."""
    return (metrics["within_5_percent_count"], metrics["within_10_percent_count"],
            -metrics["mean_absolute_percentage_error"])


def fitted_statistics(examples, names):
    # fit each input statistic using training cases only
    import numpy as np
    array = np.array([[e["features"][n] if e["features"][n] is not None else np.nan
                       for n in names] for e in examples])
    result = {}
    for column, name in enumerate(names):
        values = array[:, column]
        finite = values[np.isfinite(values)]
        median = float(np.median(finite)) if len(finite) else 0.0
        complete = np.where(np.isfinite(values), values, median)
        result[name] = {"median": median, "mean": float(complete.mean()),
                        "scale": max(float(complete.std()), 1e-9), "observed_training_values": len(finite)}
    return result


def enrich(examples, cells, spec):
    """Replace summary inputs with pooled histories when the model needs them."""
    if not spec:
        return examples
    cells_by_id = {c["cell_id"]: c for c in cells}
    cache = {}
    enriched = []
    for example in examples:
        key = (example["cell_id"], example["cutoff"])
        if key not in cache:
            cell = cells_by_id[key[0]]
            past = [p for p in cell["second_life"] if p["cycle"] <= key[1]]
            primary = [{**p, "protocol_ids": cell.get("protocol_ids", [])} for p in cell["primary"]]
            cache[key] = build_full_features(primary, past, key[1], 50, spec)
        features = {**cache[key], "horizon_cycles": example["horizon"]}
        enriched.append({**example, "features": features})
    return enriched


def train_candidate(config, train_examples, validation, root, data_hash, splits):
    """Train one configuration and score its selected validation checkpoint."""
    started = time.perf_counter()
    directory = root / config["name"]
    directory.mkdir(parents=True, exist_ok=True)
    spec = config.get("feature_spec")
    names = feature_names(spec) if spec else FEATURE_NAMES
    preprocessing = fitted_statistics(train_examples, names)
    width = len(names)+1
    hidden = config["hidden"]
    dimensions = [width, *hidden, 1]
    artifact = {"schema_version": 2, "feature_names": names, "preprocessing": preprocessing,
        "weights": [[[0.] * b for _ in range(a)] for a,b in zip(dimensions, dimensions[1:])],
        "hidden_activation": config["activation"], "output_scale_ah": 3.0,
        "output_transform": config["output"], "validation_residual_rmse_ah": 0.,
        "training_data_sha256": data_hash, "cell_splits": splits,
        "domain": {"cutoff_max": max(e["cutoff"] for e in train_examples) if config["dataset"] == "all" else 100,
                   "horizon_min": 10 if config["dataset"] == "early" else 5 if config["dataset"] == "all" else 50,
                   "horizon_max": 200},
        "framework": {"name": "neuralnets",
                      "commit": "f0eebb0be2d256c2d93af95b114f1cd7458dee60"},
        "training": {**config, "selection": "validation mean squared error" if config.get("selection_metric")=="mse"
                     else "validation within5, then within10, then mean relative error"}}
    if spec:
        artifact["feature_spec"] = spec
    placeholder = CapacityModel(artifact)
    shuffled = list(train_examples)
    random.Random(config["seed"]).shuffle(shuffled)
    # repeat retirement cases so later-history cases do not dominate training
    # these are repeated forecasts, not additional batteries
    if config["dataset"] == "all":
        cold = [e for e in shuffled if e["cutoff"] == 0]
        shuffled += cold * 24
        random.Random(config["seed"] + 1).shuffle(shuffled)
    paths = {}
    for name, examples in (("train", shuffled), ("validation", validation)):
        inputs, targets = directory/f"{name}_inputs.bin", directory/f"{name}_targets.bin"
        write_matrix(inputs, [placeholder.transform(e["features"]) for e in examples])
        ys = [[e["target_capacity_ah"]/3 if config["output"] == "capacity"
               else .5 + (e["target_capacity_ah"] - e["features"]["current_capacity_ah"])/3] for e in examples]
        write_matrix(targets, ys)
        paths[name] = (inputs, targets)
    references = directory/"validation_references.bin"
    write_matrix(references, [[e["target_capacity_ah"], e["features"]["current_capacity_ah"],
        0. if config["output"] == "capacity" else e["features"]["current_capacity_ah"]] for e in validation])
    weights, control = directory/"capacity_weights.bin", directory/"train_control.txt"
    write_control(control, inputs=paths["train"][0], targets=paths["train"][1], weights=weights,
        rows=len(shuffled), width=width, hidden=hidden, hidden_activation=config["activation"],
        learning_rate=config["learning_rate"], epochs_per_block=config["epochs_per_block"], shuffle=config.get("shuffle",True))
    with control.open("a") as stream:
        stream.write(f"selectionMetric={config.get('selection_metric','success5')}\nvalidationReferenceFile={references.resolve()}\n")
        stream.write(f"outputScaleAh=3.0\noutputOffset={0. if config['output']=='capacity' else .5}\n")
        stream.write(f"weightDecay={config.get('weight_decay', 0.0)}\n")
        if config.get("relative_loss"):
            values = [1/e["target_capacity_ah"]**2 for e in shuffled]
            center = sum(values)/len(values)
            weight_path = directory/"case_weights.bin"
            write_matrix(weight_path, [[value/center] for value in values])
            stream.write(f"caseWeightsFile={weight_path.resolve()}\n")
    bridge = JavaNetwork()
    seconds = bridge.run_logged(["train", str(control.resolve()), str(config["seed"]),
        str(paths["validation"][0].resolve()), str(paths["validation"][1].resolve()),
        str(config["blocks"]), str(config["patience"])], directory/"training.log")
    artifact["weights"] = export_weights(weights, dimensions)
    artifact["training"]["java_seconds"] = seconds
    artifact["training"]["unique_forecast_cases"] = len(train_examples)
    artifact["training"]["training_rows_including_repeats"] = len(shuffled)
    artifact["training"]["completed_passes"] = len(re.findall(r"^block=", (directory/"training.log").read_text(), re.M))*config["epochs_per_block"]
    saved = re.findall(r"Saved weights to: [^\n]*\nblock=(\d+)", (directory/"training.log").read_text())
    artifact["training"]["selected_pass"] = int(saved[-1])*config["epochs_per_block"]
    model = CapacityModel(artifact)
    prediction_control, prediction_path = directory/"predict.txt", directory/"validation_predictions.bin"
    write_control(prediction_control, inputs=paths["validation"][0], weights=weights, rows=len(validation),
                  width=width, hidden=hidden, hidden_activation=config["activation"])
    bridge.run(["predict", str(prediction_control.resolve()), str(prediction_path.resolve())])
    raw_outputs = [row[0] for row in read_matrix(prediction_path)]
    python = [model.predict_raw(e["features"]) for e in validation]
    java = [(a*3 if config["output"] == "capacity" else e["features"]["current_capacity_ah"] + (a-.5)*3)
            for a,e in zip(raw_outputs, validation)]
    difference = max(abs(a-b) for a,b in zip(java,python))
    if difference > 1e-11:
        raise RuntimeError("Tuned Java/Python predictions disagree")
    predictions = [max(0, min(e["features"]["current_capacity_ah"], p)) for p,e in zip(python, validation)]
    metrics = success_metrics([e["target_capacity_ah"] for e in validation], predictions)
    artifact["validation_residual_rmse_ah"] = metrics["root_mean_squared_error_ah"]
    (directory/"capacity_model.json").write_text(json.dumps(artifact, indent=2, allow_nan=False))
    return {"name": config["name"], "config": config, "validation": metrics,
            "validation_predictions": predictions, "artifact": artifact,
            "java_python_max_absolute_difference_ah": difference, "total_seconds": time.perf_counter()-started}


def configurations():
    """List the network shapes, learning rates, and sampling choices to compare."""
    result = []
    def add(name, dataset, hidden, activation, output, rate, seed=2026, spec=None,
            epochs=100, blocks=80, patience=15):
        result.append({"name": name, "dataset": dataset, "hidden": hidden,
            "activation": activation, "output": output, "learning_rate": rate, "seed": seed,
            "feature_spec": spec, "epochs_per_block": epochs, "blocks": blocks, "patience": patience})
    for rate, seed in itertools.product((.01, .03, .08), (2026, 17)):
        add(f"long-small-lr{rate}-seed{seed}", "sparse", [12], "sigmoid", "capacity", rate, seed)
    for rate in (.003, .01):
        add(f"residual-sparse-lr{rate}", "sparse", [24,12], "tanh", "current_residual", rate)
    for rate in (.001, .003, .01):
        add(f"balanced-early-lr{rate}", "early", [24,12], "tanh", "current_residual", rate,
            epochs=10, blocks=60, patience=12)
    for rate in (.001, .003):
        spec = {"kind": "full_history_v2", "bins": 4, "usage": False}
        add(f"history-balanced-lr{rate}", "early", [32,16], "tanh", "current_residual", rate,
            spec=spec, epochs=10, blocks=40, patience=10)
    for rate in (.0003, .001):
        add(f"all-windows-balanced-lr{rate}", "all", [24,12], "tanh", "current_residual", rate,
            epochs=1, blocks=40, patience=12)
    return result


def tune(data_path: Path, output: Path):
    """Choose a model on validation forecasts, freeze it, then score test forecasts."""
    started = time.perf_counter()
    if (output/"selection.json").exists():
        raise FileExistsError("Use a new output folder to preserve the previous tuning experiment")
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(data_path.read_text())
    data_hash = hashlib.sha256(data_path.read_bytes()).hexdigest()
    splits = split_cells(data["cells"])
    sparse = make_examples([c for c in data["cells"] if c["cell_id"] not in splits["test"]])
    # Only training and validation identities enter search construction.
    training_cells = [c for c in data["cells"] if c["cell_id"] in splits["train"]]
    training_sparse = [e for e in sparse if e["cell_id"] in splits["train"]]
    validation = [e for e in sparse if e["cell_id"] in splits["validation"]]
    training_early = make_examples(training_cells, horizons=tuple(range(10, 201, 5)))
    training_all = dense_cases(training_cells)
    context_cache = {}
    by_id = {c["cell_id"]: c for c in training_cells}
    for case in training_all:
        key = (case["cell_id"], case["cutoff"])
        if key not in context_cache:
            cell = by_id[key[0]]
            past = [p for p in cell["second_life"] if p["cycle"] <= key[1]]
            context_cache[key] = build_features(cell["primary"], past, key[1], 50)
        case["features"] = {**context_cache[key], "horizon_cycles": case["horizon"]}
    datasets = {"sparse": training_sparse, "early": training_early, "all": training_all}
    truth = [e["target_capacity_ah"] for e in validation]
    results = []
    baseline_path = Path("models/capacity_model.json")
    if baseline_path.exists():
        baseline = CapacityModel.load(baseline_path)
        if baseline.artifact["cell_splits"] != splits or baseline.artifact["training_data_sha256"] != data_hash:
            raise ValueError("Baseline data or cell partitions differ")
        values = [max(0,min(e["features"]["current_capacity_ah"],baseline.predict_raw(e["features"]))) for e in validation]
        results.append({"name": "original-small", "validation": success_metrics(truth,values),
                        "validation_predictions": values, "artifact": baseline.artifact})
    configs = configurations()
    (output/"search_plan.json").write_text(json.dumps({"configs": configs, "cell_splits": splits,
        "validation_cases": len(validation), "data_sha256": data_hash,
        "selection": "within5 then within10 then mean relative error; validation only",
        "training_case_counts": {k:len(v) for k,v in datasets.items()}}, indent=2))
    for index, config in enumerate(configs, 1):
        print(f"Training candidate {index}/{len(configs)}: {config['name']}", flush=True)
        train_examples = enrich(datasets[config["dataset"]], training_cells, config["feature_spec"])
        val_examples = enrich(validation, data["cells"], config["feature_spec"])
        result = train_candidate(config, train_examples, val_examples, output, data_hash, splits)
        results.append(result)
        summary = [{k:v for k,v in r.items() if k not in ("artifact", "validation_predictions")} for r in results]
        (output/"validation_search.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
        print(json.dumps({"candidate": result["name"], "validation": result["validation"],
                          "seconds": result["total_seconds"]}), flush=True)
    # Predeclared ensemble options average the top 2/3/5 same-encoding candidates.
    for family in (None, {"kind":"full_history_v2", "bins":4,"usage":False}):
        ranked = sorted([r for r in results if "ensemble_members" not in r["artifact"]
                         and r["artifact"].get("feature_spec") == family], key=lambda r:rank(r["validation"]), reverse=True)
        for size in (2,3,5):
            if len(ranked) < size:
                continue
            members = ranked[:size]
            values = [sum(r["validation_predictions"][i] for r in members)/size for i in range(len(validation))]
            metrics = success_metrics(truth, values)
            artifact = copy.deepcopy(members[0]["artifact"])
            artifact["schema_version"] = 2
            artifact.pop("weights", None)
            artifact.pop("preprocessing", None)
            artifact["ensemble_members"] = [r["artifact"] for r in members]
            domains = [r["artifact"]["domain"] for r in members]
            artifact["domain"] = {"cutoff_max": min(d["cutoff_max"] for d in domains),
                "horizon_min": max(d["horizon_min"] for d in domains),
                "horizon_max": min(d["horizon_max"] for d in domains)}
            artifact["validation_residual_rmse_ah"] = metrics["root_mean_squared_error_ah"]
            artifact["training"] = {"selection": "validation only", "ensemble": [r["name"] for r in members]}
            results.append({"name": f"ensemble-{size}-{'summary' if family is None else 'history'}",
                "validation": metrics, "validation_predictions": values, "artifact": artifact})
    winner = max(results, key=lambda r:rank(r["validation"]))
    frozen = {"winner": winner["name"], "validation": winner["validation"], "cell_splits": splits,
              "data_sha256": data_hash, "test_used_for_selection": False,
              "candidates": [{k:v for k,v in r.items() if k not in ("artifact","validation_predictions")} for r in results]}
    # Freeze and persist the selected model before evaluating test predictions.
    (output/"selection.json").write_text(json.dumps(frozen, indent=2, allow_nan=False))
    (output/"capacity_model.json").write_text(json.dumps(winner["artifact"], indent=2, allow_nan=False))
    model = CapacityModel(winner["artifact"])
    selected_validation = enrich(validation, data["cells"], model.feature_spec)
    predictions = [max(0,min(e["features"]["current_capacity_ah"],model.predict_raw(e["features"]))) for e in selected_validation]
    if max(abs(a-b) for a,b in zip(predictions,winner["validation_predictions"])) > 1e-11:
        raise RuntimeError("Selected model does not reproduce validation selection")
    test = make_examples([c for c in data["cells"] if c["cell_id"] in splits["test"]])
    test = enrich(test, data["cells"], model.feature_spec)
    evaluation = evaluate(model, test)
    def groups(rows):
        return {name: success_metrics([r["actual_capacity_ah"] for r in subset], [r["neural_network"] for r in subset])
            for name,subset in (("all",rows), ("first_life_only",[r for r in rows if r["cutoff"]==0]),
                                ("updated",[r for r in rows if r["cutoff"]>0]))}
    report = {"winner": winner["name"], "validation": winner["validation"], "test": evaluation,
              "success": groups(evaluation["predictions"]), "cell_splits": splits,
              "total_seconds": time.perf_counter()-started,
              "selection": "validation-only; test assessed after selection.json was frozen",
              "limitations": ["Only 12 validation and 14 reused test cells; search may overfit validation.",
                "Repeated forecasts per cell are correlated; no independent external confirmation.",
                "Raw all-measurement variant is still pending locally readable source files."]}
    (output/"evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({"winner": report["winner"], "success": report["success"],
                      "total_seconds": report["total_seconds"]}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--output", type=Path, default=Path("build/training/tuned"))
    args = parser.parse_args()
    tune(args.data.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
