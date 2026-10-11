"""Choose settings with five-fold cross-validation, then refit development cells.

The 14 original test cells stay out of fitting. They were inspected in earlier
experiments, so this is not a fresh blind test."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

from ..prediction.features import FEATURE_NAMES, make_examples, split_cells
from .java_bridge import JavaNetwork, export_weights, read_matrix, write_control, write_matrix
from ..prediction.model import CapacityModel
from .train import evaluate
from .tune import fitted_statistics, rank, success_metrics, train_candidate


def configurations():
    """List the settings tested in the five-fold experiment."""
    shapes = [(12,.03,False,0.),(12,.08,False,0.),(12,.15,False,0.),
              (12,.03,True,0.),(12,.08,True,0.),(6,.08,False,.00001),
              (24,.03,False,.00001),(24,.08,False,.00001)]
    return [{"name":f"cv-h{width}-lr{rate}-shuffle{shuffle}","dataset":"sparse",
        "hidden":[width],"activation":"sigmoid","output":"capacity","learning_rate":rate,
        "seed":2026,"feature_spec":None,"epochs_per_block":100,"blocks":120,"patience":20,
        "weight_decay":decay,"shuffle":shuffle,"relative_loss":False,"selection_metric":"mse"}
        for width,rate,shuffle,decay in shapes]


def cell_folds(development, seed=2026, count=5):
    """Shuffle battery identities into folds without splitting a battery's history."""
    if len(development)<count or len(set(development))!=len(development):
        raise ValueError("Distinct development cells are required for every fold")
    ids=sorted(development,key=int)
    random.Random(seed).shuffle(ids)
    return [ids[index::count] for index in range(count)]


def refit(config, examples, passes, directory, data_hash, development, test_ids):
    """Fixed-budget Java fit; no held-out observations are supplied to Java."""
    directory.mkdir(parents=True,exist_ok=True)
    preprocessing = fitted_statistics(examples,FEATURE_NAMES)
    dimensions = [16,*config["hidden"],1]
    artifact = {"schema_version":2,"feature_names":FEATURE_NAMES,"preprocessing":preprocessing,
        "weights":[[[0.] * b for _ in range(a)] for a,b in zip(dimensions,dimensions[1:])],
        "hidden_activation":"sigmoid","output_scale_ah":3.,"validation_residual_rmse_ah":0.,
        "training_data_sha256":data_hash,"cell_splits":{"train":development,"validation":[],"test":test_ids},
        "domain":{"cutoff_max":100,"horizon_min":50,"horizon_max":200},
        "training":{**config,"refit_passes":passes,"selection":"fixed median cross-validation-selected pass budget"},
        "framework":{"name":"neuralnets",
                     "commit":"f0eebb0be2d256c2d93af95b114f1cd7458dee60"}}
    initial = CapacityModel(artifact)
    ordered = list(examples)
    random.Random(config["seed"]).shuffle(ordered)
    inputs,targets = directory/"inputs.bin",directory/"targets.bin"
    write_matrix(inputs,[initial.transform(e["features"]) for e in ordered])
    write_matrix(targets,[[e["target_capacity_ah"]/3] for e in ordered])
    weights,control = directory/"weights.bin",directory/"fit_control.txt"
    write_control(control,inputs=inputs,targets=targets,weights=weights,rows=len(ordered),width=16,
                  hidden=config["hidden"],learning_rate=config["learning_rate"],
                  epochs_per_block=config["epochs_per_block"],shuffle=config["shuffle"])
    with control.open("a") as stream:
        stream.write(f"weightDecay={config['weight_decay']}\n")
    bridge = JavaNetwork()
    seconds = bridge.run_logged(["fit",str(control.resolve()),str(config["seed"]),
        str(passes//config["epochs_per_block"])],directory/"fit.log")
    artifact["weights"] = export_weights(weights,dimensions)
    artifact["training"]["java_seconds"] = seconds
    model = CapacityModel(artifact)
    checks = ordered[::max(1,len(ordered)//32)][:32]
    check_inputs,predictions = directory/"check_inputs.bin",directory/"predictions.bin"
    write_matrix(check_inputs,[model.transform(e["features"]) for e in checks])
    prediction_control=directory/"predict_control.txt"
    write_control(prediction_control,inputs=check_inputs,weights=weights,rows=len(checks),width=16,hidden=config["hidden"])
    bridge.run(["predict",str(prediction_control.resolve()),str(predictions.resolve())])
    difference = max(abs(model.predict_raw(e["features"])-row[0]*3)
                     for e,row in zip(checks,read_matrix(predictions)))
    if difference>1e-11:
        raise RuntimeError("Final refit Java/Python inference disagree")
    artifact["training"]["java_python_max_absolute_difference_ah"] = difference
    return artifact


def tune_refit(data_path,output):
    """Select settings across folds and refit using the median selected pass count."""
    started = time.perf_counter()
    if (output/"selection.json").exists():
        raise FileExistsError("Use a new output directory to preserve this experiment")
    output.mkdir(parents=True,exist_ok=True)
    data = json.loads(data_path.read_text())
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    original_splits = split_cells(data["cells"])
    test_ids = original_splits["test"]
    development = sorted(original_splits["train"]+original_splits["validation"],key=int)
    # hold out entire cells in each fold so their other forecasts cannot enter fitting
    folds = cell_folds(development)
    dev_cells = [c for c in data["cells"] if c["cell_id"] in development]
    examples = make_examples(dev_cells)
    configs = configurations()
    (output/"search_plan.json").write_text(json.dumps({"configs":configs,"folds":folds,
        "development_ids":development,"excluded_test_ids":test_ids,"data_sha256":digest,
        "checkpoint":"fold validation mean squared error",
        "hyperparameters":"pooled out-of-fold within5, within10, then mean relative error",
        "refit":"all development cells, median selected pass count, no final early stopping"},indent=2))
    candidates=[];truth=[]
    for config in configs:
        predictions=[];budgets=[];fold_metrics=[]
        for index,held_out in enumerate(folds):
            training=[e for e in examples if e["cell_id"] not in held_out]
            validation=[e for e in examples if e["cell_id"] in held_out]
            fold_config={**config,"name":config["name"]+f"-fold{index+1}"}
            print(f"Cross-validation: {config['name']}, fold {index+1}/5",flush=True)
            result=train_candidate(fold_config,training,validation,output,digest,
                {"train":[i for i in development if i not in held_out],"validation":held_out,"test":test_ids})
            predictions+=result["validation_predictions"]
            budgets.append(result["artifact"]["training"]["selected_pass"])
            fold_metrics.append(result["validation"])
            if not candidates:
                truth += [e["target_capacity_ah"] for e in validation]
        candidate={"name":config["name"],"config":config,"predictions":predictions,"passes":budgets,
            "metrics":success_metrics(truth,predictions),"fold_metrics":fold_metrics}
        candidates.append(candidate)
        (output/"cross_validation.json").write_text(json.dumps([
            {k:v for k,v in r.items() if k!="predictions"} for r in candidates],indent=2))
        print(json.dumps({"config":config["name"],"cross_validation":candidate["metrics"],"selected_passes":budgets}),flush=True)
    ranked=sorted(candidates,key=lambda r:rank(r["metrics"]),reverse=True)
    options=[{"name":r["name"],"members":[r],"metrics":r["metrics"]} for r in ranked]
    for size in (2,3,5):
        members=ranked[:size]
        values=[sum(m["predictions"][i] for m in members)/size for i in range(len(truth))]
        options.append({"name":f"cv-ensemble-{size}","members":members,"metrics":success_metrics(truth,values)})
    selected=max(options,key=lambda r:rank(r["metrics"]))
    frozen={"winner":selected["name"],"cross_validation":selected["metrics"],
        "members":[{"name":m["name"],"config":m["config"],"refit_passes":int(statistics.median(m["passes"]))}
                   for m in selected["members"]],"development_ids":development,"excluded_test_ids":test_ids,
        "test_used_for_selection":False,"data_sha256":digest}
    (output/"selection.json").write_text(json.dumps(frozen,indent=2))
    print(json.dumps({"frozen_selection":frozen}),flush=True)
    fitted=[]
    for member in frozen["members"]:
        fitted.append(refit(member["config"],examples,member["refit_passes"],output/member["name"]/"final",
                            digest,development,test_ids))
    artifact=copy.deepcopy(fitted[0])
    if len(fitted)>1:
        artifact.pop("weights");artifact.pop("preprocessing")
        artifact["ensemble_members"]=fitted
    artifact["validation_residual_rmse_ah"]=selected["metrics"]["root_mean_squared_error_ah"]
    artifact["training"]["cross_validation_selection"]=frozen
    (output/"capacity_model.json").write_text(json.dumps(artifact,indent=2))
    # The selected hyperparameters and final model are frozen before test evaluation.
    test=make_examples([c for c in data["cells"] if c["cell_id"] in test_ids])
    evaluation=evaluate(CapacityModel(artifact),test)
    rows=evaluation["predictions"]
    success={name:success_metrics([r["actual_capacity_ah"] for r in subset],[r["neural_network"] for r in subset])
        for name,subset in (("all",rows),("first_life_only",[r for r in rows if r["cutoff"]==0]),
                            ("updated",[r for r in rows if r["cutoff"]>0]))}
    report={**frozen,"test":evaluation,"success":success,"total_seconds":time.perf_counter()-started,
        "limitations":["The original validation cells enter cross-validation and final refitting; 72 final fit cells.",
            "The same 14 test identities were previously inspected; this is an exploratory reused holdout.",
            "Forecasts are correlated within a cell; independent cells/data are needed for confirmation.",
            "Protocol identifiers are not inputs to this refit experiment."]}
    (output/"evaluation.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({"winner":report["winner"],"success":success,"total_seconds":report["total_seconds"]},indent=2),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--output",type=Path,default=Path("build/training/tuned/refit"))
    args=parser.parse_args()
    tune_refit(args.data.resolve(),args.output.resolve())


if __name__=="__main__":
    main()
