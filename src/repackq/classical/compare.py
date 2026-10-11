"""Compare classical selections using the same cells and scoring rules."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from repackq.optimization import build_instance
from repackq.prediction.model import CapacityModel
from .annealing import simulated_annealing
from .exact import exact_search
from .greedy import greedy_selection
from .metrics import evaluate_selection
from .soh import healthiest_selection
from .trials import history_pool, synthetic_pool


def compare(cells, *, pack_size=4, mode="trajectory_aware", future_truth=None, seed=11,
            annealing_steps=3000, annealing_restarts=4, export_qubo=False,
            quantum=False, shots=1024, optimizer="auto", quantum_evaluations=160):
    """Solve first, reveal future truth afterward. Scores across modes differ."""
    started = perf_counter()
    instance = build_instance(cells, pack_size, mode=mode)
    construction_ms = (perf_counter() - started) * 1000
    optimum = exact_search(instance)
    # all methods see the same problem; actual future values are used only below
    selections = [healthiest_selection(instance), greedy_selection(instance),
                  simulated_annealing(instance, seed=seed, steps=annealing_steps, restarts=annealing_restarts),
                  optimum]
    quantum_runs = []
    if quantum:
        from repackq.quantum import run_both
        runs = run_both(instance, seed=seed, shots=shots, optimizer=optimizer,
                        max_evaluations=quantum_evaluations)
        selections.extend(run["selection"] for run in runs if run["selection"] is not None)
        quantum_runs = [{k: v for k, v in run.items() if k != "selection"} for run in runs]
    return {"mode": mode, "pack_size": pack_size, "objective_metadata": instance.metadata,
            "objective_construction_ms": construction_ms,
            "results": [evaluate_selection(instance, selected, future_truth=future_truth, optimum=optimum)
                        for selected in selections],
            "quantum_runs": quantum_runs, "qubo": instance.qubo() if export_qubo else None}


def summarize(trials):
    """Average each method and objective separately across the recorded pools."""
    summaries = []
    for mode in sorted({comparison["mode"] for trial in trials for comparison in trial["comparisons"]}):
        algorithms = dict.fromkeys(r["algorithm"] for trial in trials for c in trial["comparisons"]
                                   if c["mode"] == mode for r in c["results"])
        algorithms.update(dict.fromkeys(r["algorithm"] for trial in trials for c in trial["comparisons"]
                                       if c["mode"] == mode for r in c.get("quantum_runs", [])))
        for algorithm in algorithms:
            rows = [r for trial in trials for comparison in trial["comparisons"] if comparison["mode"] == mode
                    for r in comparison["results"] if r["algorithm"] == algorithm]
            entry = {"mode": mode, "algorithm": algorithm, "trials": len(rows)}
            attempts = [run for trial in trials for c in trial["comparisons"] if c["mode"] == mode
                        for run in c.get("quantum_runs", []) if run["algorithm"] == algorithm]
            if attempts:
                entry.update(quantum_attempts=len(attempts),
                             no_feasible_sample_trials=sum(run["status"] == "no_feasible_sample" for run in attempts))
            for field in ("objective_gap_abs", "normalized_regret", "runtime_ms", "predicted_pack_divergence",
                          "observed_pack_divergence", "observed_usable_capacity_ah"):
                values = [row[field] for row in rows if row.get(field) is not None]
                entry["mean_" + field] = mean(values) if values else None
            summaries.append(entry)
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="Use invented demo inputs; no trained model required")
    parser.add_argument("--model", type=Path, default=Path("models/capacity_model.json"))
    parser.add_argument("--data", type=Path, default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--partition", choices=("test", "all"), default="test")
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--pack-size", type=int, default=4)
    parser.add_argument("--cutoff", type=int, default=0)
    parser.add_argument("--horizon", type=int, default=200)
    parser.add_argument("--minimum-soh", type=float, default=.5, help="Minimum capacity / nominal capacity")
    parser.add_argument("--mode", choices=("current_only", "trajectory_aware", "both"), default="both")
    parser.add_argument("--seeds", type=int, nargs="+", default=[11])
    parser.add_argument("--annealing-steps", type=int, default=3000)
    parser.add_argument("--annealing-restarts", type=int, default=4)
    parser.add_argument("--quantum", action="store_true", help="Also run both Qiskit selection methods")
    parser.add_argument("--shots", type=int, default=1024, help="Measurements per quantum circuit")
    parser.add_argument("--optimizer", choices=("auto", "grid", "cobyla"), default="auto")
    parser.add_argument("--quantum-evaluations", type=int, default=160, help="Local angle-search budget per circuit")
    parser.add_argument("--export-qubo", action="store_true", help="Include the calibrated binary coefficients used by quantum selection")
    parser.add_argument("--output", type=Path, help="Write full local report; must not already exist")
    args = parser.parse_args()
    try:
        if len(set(args.seeds)) != len(args.seeds):
            raise ValueError("Seeds must be distinct")
        if args.output and args.output.exists():
            raise ValueError(f"Refusing to overwrite existing report: {args.output}")
        if args.synthetic and args.candidates != 8:
            raise ValueError("The synthetic fixture contains exactly eight candidates")
        provenance = {"source": "synthetic-fixture"}
        if not args.synthetic:
            model_bytes, data_bytes = args.model.read_bytes(), args.data.read_bytes()
            model = CapacityModel(json.loads(model_bytes))
            data = json.loads(data_bytes)
            data_hash = hashlib.sha256(data_bytes).hexdigest()
            if data_hash != model.artifact["training_data_sha256"]:
                raise ValueError("Histories do not match the model's recorded dataset hash")
            provenance = {"source": "derived-real", "data_sha256": data_hash,
                          "model_sha256": hashlib.sha256(model_bytes).hexdigest()}
        trials = []
        modes = ("current_only", "trajectory_aware") if args.mode == "both" else (args.mode,)
        for seed in args.seeds:
            started = perf_counter()
            cells, truth, metadata = synthetic_pool() if args.synthetic else history_pool(
                data, model, seed=seed, candidates=args.candidates, cutoff=args.cutoff, horizon=args.horizon,
                minimum_soh=args.minimum_soh, partition=args.partition)
            preparation_ms = (perf_counter() - started) * 1000
            comparisons = [compare(cells, pack_size=args.pack_size, mode=mode, future_truth=truth, seed=seed,
                                   annealing_steps=args.annealing_steps, annealing_restarts=args.annealing_restarts,
                                   export_qubo=args.export_qubo, quantum=args.quantum, shots=args.shots,
                                   optimizer=args.optimizer, quantum_evaluations=args.quantum_evaluations) for mode in modes]
            trials.append({"metadata": {**metadata, "seed": seed}, "preparation_ms": preparation_ms,
                           "snapshots": [asdict(c) for c in cells], "comparisons": comparisons,
                           "revealed_future_truth": truth})
        report = {"schema_version": 1, "provenance": provenance, "settings": {
            "candidate_count": args.candidates, "pack_size": args.pack_size, "seeds": args.seeds,
            "cutoff": args.cutoff, "horizon": args.horizon, "partition": args.partition,
            "minimum_soh": args.minimum_soh, "annealing_steps": args.annealing_steps,
            "annealing_restarts": args.annealing_restarts, "quantum": args.quantum,
            "quantum_shots": args.shots if args.quantum else None,
            "quantum_optimizer": args.optimizer if args.quantum else None,
            "quantum_evaluations": args.quantum_evaluations if args.quantum else None},
            "trials": trials, "summary": summarize(trials),
            "limitations": ["Series capacity is a minimum-cell proxy, not a full electrical pack simulation.",
                            "Objective weights are assumptions; do not compare scores across objective modes.",
                            "Local simulator results do not establish quantum advantage or Qollab compatibility."]}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as stream:
                json.dump(report, stream, indent=2, allow_nan=False)
                stream.write("\n")
        print(f"Data source: {provenance['source']}; {len(trials)} trial(s)")
        if len(trials) == 1:
            print("Mode              Algorithm      Selected cells          Score       Gap       Future spread")
            for comparison in trials[0]["comparisons"]:
                for row in comparison["results"]:
                    spread = row["observed_capacity_spread_ah"]
                    shown = f"{spread:.4f} amp-hours" if spread is not None else "unavailable"
                    print(f"{comparison['mode']:<18}{row['algorithm']:<15}"
                          f"{','.join(row['selected_cell_ids']):<24}{row['objective_value']:>9.4f}"
                          f"{row['objective_gap_abs']:>10.4f}  {shown}")
        else:
            print("Mode              Algorithm      Mean gap    Mean observed divergence    Mean future minimum")
            for row in report["summary"]:
                divergence, capacity = row["mean_observed_pack_divergence"], row["mean_observed_usable_capacity_ah"]
                shown_divergence = f"{divergence:.4%}" if divergence is not None else "unavailable"
                shown_capacity = f"{capacity:.4f} amp-hours" if capacity is not None else "unavailable"
                shown_gap = f"{row['mean_objective_gap_abs']:.4f}" if row['mean_objective_gap_abs'] is not None else "no group"
                print(f"{row['mode']:<18}{row['algorithm']:<15}{shown_gap:>9}"
                      f"  {shown_divergence:<28}{shown_capacity}")
        if args.output:
            print(f"Full report: {args.output.resolve()}")
        for trial in trials:
            for comparison in trial["comparisons"]:
                for run in comparison["quantum_runs"]:
                    if run["status"] != "computed":
                        print(f"{run['algorithm']}: no feasible group observed in this circuit's samples")
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
