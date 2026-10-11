"""Select separate predictors for retirement and later second-life forecasts.

Optional protocol categories come from first-life training records. These
experiments do not establish accuracy on unseen protocols."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path

from ..prediction.features import make_examples, split_cells
from ..prediction.full_history import feature_names
from ..prediction.model import CapacityModel
from .train import evaluate
from .tune import enrich, rank, success_metrics, train_candidate


def expert_configs(task, spec):
    """List candidate settings for one forecasting task."""
    result = []
    for width in (6, 12):
        for rate in (.03, .08, .2):
            result.append({"name":f"{task}-summary-{width}-lr{rate}", "dataset":"sparse",
                "hidden":[width], "activation":"sigmoid", "output":"capacity",
                "learning_rate":rate, "seed":2026, "feature_spec":None,
                "epochs_per_block":100, "blocks":120, "patience":20,
                "weight_decay":.0001, "relative_loss":True})
    for rate in (.03, .08, .2):
        for decay in (0., .0001):
            result.append({"name":f"{task}-protocol-lr{rate}-decay{decay}", "dataset":"sparse",
                "hidden":[12], "activation":"sigmoid", "output":"capacity",
                "learning_rate":rate, "seed":2026, "feature_spec":spec,
                "epochs_per_block":100, "blocks":120, "patience":20,
                "weight_decay":decay, "relative_loss":True})
    return result


def tune_experts(data_path, output):
    """Choose retirement and updated-history models separately on validation cells."""
    started = time.perf_counter()
    if (output/"selection.json").exists():
        raise FileExistsError("Use a new output folder to preserve this experiment")
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(data_path.read_text())
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    splits = split_cells(data["cells"])
    training_cells = [c for c in data["cells"] if c["cell_id"] in splits["train"]]
    validation_cells = [c for c in data["cells"] if c["cell_id"] in splits["validation"]]
    # Categories are derived exclusively from recorded first-life training metadata.
    protocols = sorted({identifier for c in training_cells for identifier in c["protocol_ids"]})
    spec = {"kind":"full_history_v2", "bins":4, "usage":False, "protocols":protocols}
    train = make_examples(training_cells)
    validation = make_examples(validation_cells)
    plans = {task: expert_configs(task, spec) for task in ("first_life", "updated")}
    (output/"search_plan.json").write_text(json.dumps({"configs":plans, "cell_splits":splits,
        "data_sha256":digest, "protocol_categories_from_training_only":protocols,
        "selection":"validation within5, within10, mean relative error; separate tasks",
        "assumption":"Recorded first-life experimental protocol is known at prediction time"}, indent=2))
    selections, summaries = {}, []
    fallback_models = [Path("models/capacity_model.json"), Path("build/training/tuned/capacity_model.json")]
    for task in ("first_life", "updated"):
        is_cold = task == "first_life"
        training = [e for e in train if (e["cutoff"]==0)==is_cold]
        val = [e for e in validation if (e["cutoff"]==0)==is_cold]
        truth = [e["target_capacity_ah"] for e in val]
        candidates = []
        for path in fallback_models:
            if not path.exists():
                continue
            model = CapacityModel.load(path)
            if model.artifact["training_data_sha256"] != digest or model.artifact["cell_splits"] != splits:
                raise ValueError("Fallback model uses different data or cell partitions")
            encoded = enrich(val, validation_cells, model.feature_spec)
            values = [max(0,min(e["features"]["current_capacity_ah"],model.predict_raw(e["features"]))) for e in encoded]
            candidates.append({"name":str(path), "artifact":model.artifact,
                "validation_predictions":values, "validation":success_metrics(truth,values)})
        for index, config in enumerate(plans[task],1):
            print(f"{task}: training {index}/{len(plans[task])}: {config['name']}", flush=True)
            training_encoded = enrich(training, training_cells, config["feature_spec"])
            val_encoded = enrich(val, validation_cells, config["feature_spec"])
            result = train_candidate(config, training_encoded, val_encoded, output, digest, splits)
            candidates.append(result)
            summary = {k:v for k,v in result.items() if k not in ("artifact","validation_predictions")}
            summaries.append(summary)
            (output/"validation_search.json").write_text(json.dumps(summaries, indent=2))
            print(json.dumps({"candidate":result["name"], "validation":result["validation"],
                              "seconds":result["total_seconds"]}), flush=True)
        for family in (None, spec):
            ranked = sorted([r for r in candidates if r["artifact"].get("feature_spec")==family
                             and "ensemble_members" not in r["artifact"]],
                            key=lambda r:rank(r["validation"]), reverse=True)
            for size in (2,3,5):
                if len(ranked)<size:
                    continue
                members = ranked[:size]
                values = [sum(r["validation_predictions"][i] for r in members)/size for i in range(len(val))]
                metrics = success_metrics(truth,values)
                artifact = copy.deepcopy(members[0]["artifact"])
                artifact.pop("weights",None)
                artifact.pop("preprocessing",None)
                artifact["schema_version"] = 2
                artifact["ensemble_members"] = [r["artifact"] for r in members]
                artifact["validation_residual_rmse_ah"] = metrics["root_mean_squared_error_ah"]
                artifact["training"] = {"ensemble":[r["name"] for r in members],"selection":"validation only"}
                candidates.append({"name":f"{task}-ensemble-{size}-{'summary' if family is None else 'protocol'}",
                    "artifact":artifact, "validation":metrics, "validation_predictions":values})
        winner = max(candidates,key=lambda r:rank(r["validation"]))
        selections[task] = winner
        print(json.dumps({"task_winner":task,"name":winner["name"],"validation":winner["validation"]}), flush=True)
    needs_protocol = any(r["artifact"].get("feature_spec") for r in selections.values())
    parent_spec = spec if needs_protocol else None
    validation_encoded = enrich(validation, validation_cells, parent_spec)
    artifact = {"schema_version":2, "feature_names":feature_names(spec) if parent_spec else selections["first_life"]["artifact"]["feature_names"],
        "routing_experts":{task:r["artifact"] for task,r in selections.items()},
        "output_scale_ah":3., "validation_residual_rmse_ah":0.,
        "training_data_sha256":digest, "cell_splits":splits,
        "domain":{"cutoff_max":100,"horizon_min":50,"horizon_max":200},
        "training":{"selection":"validation only; separate first-life and updated experts",
                    "experts":{task:r["name"] for task,r in selections.items()}},
        "framework":{"name":"neuralnets",
                     "commit":"f0eebb0be2d256c2d93af95b114f1cd7458dee60"}}
    if parent_spec:
        artifact["feature_spec"] = parent_spec
    model = CapacityModel(artifact)
    values = [max(0,min(e["features"]["current_capacity_ah"],model.predict_raw(e["features"]))) for e in validation_encoded]
    val_metrics = success_metrics([e["target_capacity_ah"] for e in validation],values)
    artifact["validation_residual_rmse_ah"] = val_metrics["root_mean_squared_error_ah"]
    frozen = {"winner":artifact["training"]["experts"], "validation":val_metrics,
        "tasks":{task:{"name":r["name"],"validation":r["validation"]} for task,r in selections.items()},
        "test_used_for_selection":False,"cell_splits":splits,"requires_first_life_protocol":needs_protocol,
        "data_sha256":digest}
    (output/"selection.json").write_text(json.dumps(frozen, indent=2))
    (output/"capacity_model.json").write_text(json.dumps(artifact, indent=2))
    # Test labels/predictions are constructed only after the selection is frozen.
    test_cells = [c for c in data["cells"] if c["cell_id"] in splits["test"]]
    test = enrich(make_examples(test_cells), test_cells, parent_spec)
    evaluation = evaluate(CapacityModel(artifact), test)
    rows = evaluation["predictions"]
    success = {task:success_metrics([r["actual_capacity_ah"] for r in selected], [r["neural_network"] for r in selected])
        for task,selected in (("all",rows),("first_life_only",[r for r in rows if r["cutoff"]==0]),
                              ("updated",[r for r in rows if r["cutoff"]>0]))}
    report = {**frozen, "test":evaluation,"success":success,"total_seconds":time.perf_counter()-started,
        "limitations":["Exploratory repeated use of 12 validation and 14 test cell identities.",
            "First-life protocol is recorded before second life; shared protocols across splits limit transfer claims.",
            "Forecasts from the same cell are correlated; confirm with new cells/programs before deployment.",
            "Only the validation-selected experts were evaluated here; test did not choose the models."]}
    (output/"evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"winner":report["winner"],"success":success,"total_seconds":report["total_seconds"]},indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--output",type=Path,default=Path("build/training/tuned/experts"))
    args = parser.parse_args()
    tune_experts(args.data.resolve(),args.output.resolve())


if __name__ == "__main__":
    main()
