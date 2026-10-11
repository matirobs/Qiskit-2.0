"""Load dashboard data, run selections, and reveal recorded outcomes."""
from collections import OrderedDict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from threading import RLock
from time import perf_counter
import uuid

from repackq.classical import exact_search, greedy_selection, healthiest_selection, simulated_annealing
from repackq.classical.common import result
from repackq.classical.metrics import evaluate_selection
from repackq.classical.trials import history_pool, synthetic_pool
from repackq.optimization import build_instance
from repackq.prediction.model import CapacityModel
from .quantum import capabilities, run_quantum

ROOT = Path(__file__).resolve().parents[3]
DEFAULTS = {"seed": 11, "candidates": 8, "pack_size": 4, "cutoff": 0,
            "horizon": 200, "mode": "trajectory_aware", "quantum": False, "partition": "all"}


class DashboardService:
    """Load local assets once and keep recent trials in memory.

    Missing assets use sample cells; mismatched real assets are rejected."""

    def __init__(self, root=ROOT, *, synthetic=False, model_path=None, data_path=None):
        self.root = Path(root)
        self.model_path = Path(model_path) if model_path else self.root / "models/capacity_model.json"
        self.data_path = Path(data_path) if data_path else self.root / "data/processed/cell_histories.json"
        self.synthetic = synthetic or not self.model_path.exists() or not self.data_path.exists()
        self.reason = "Sample data requested" if synthetic else "Local model or cached histories are missing"
        self.model = self.data = None
        self.model_hash = self.data_hash = None
        if not self.synthetic:
            model_bytes, data_bytes = self.model_path.read_bytes(), self.data_path.read_bytes()
            self.model_hash = hashlib.sha256(model_bytes).hexdigest()
            self.data_hash = hashlib.sha256(data_bytes).hexdigest()
            self.model = CapacityModel(json.loads(model_bytes))
            self.data = json.loads(data_bytes)
            if self.data_hash != self.model.artifact["training_data_sha256"]:
                raise ValueError("Cached histories do not match the selected model's dataset checksum")
        self.trials = OrderedDict()
        self.lock = RLock()

    def bootstrap(self):
        """Load matching saved reports and label the data source."""
        evaluation, benchmark = None, None
        if not self.synthetic:
            path = self.root / "models/evaluation.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved.get("data_sha256") == self.data_hash:
                    rows = saved["test"]["predictions"]
                    if rows:
                        errors = [abs(r["neural_network"] - r["actual_capacity_ah"]) / r["actual_capacity_ah"] for r in rows]
                        evaluation = {"source": "recorded_baseline", "forecasts": len(rows),
                            "test_cells": saved["cell_counts"]["test"],
                            "within_5_percent": 100 * sum(e <= .05 + 1e-12 for e in errors) / len(errors),
                            "within_10_percent": 100 * sum(e <= .10 + 1e-12 for e in errors) / len(errors),
                            "mean_absolute_error_ah": saved["test"]["overall"]["neural_network"]["mean_absolute_error_ah"]}
            path = self.root / "results/classical-benchmark-20-seeds.json"
            if path.exists():
                saved = json.loads(path.read_text())
                provenance = saved.get("provenance", {})
                if provenance.get("data_sha256") == self.data_hash and provenance.get("model_sha256") == self.model_hash:
                    benchmark = {"source": "recorded_benchmark", "trials": len(saved["trials"]),
                                 "settings": saved["settings"], "summary": saved["summary"],
                                 "limitations": saved["limitations"]}
        return {"source": "synthetic-fixture" if self.synthetic else "derived-real",
                "source_label": "Illustrative sample data" if self.synthetic else "Real battery data",
                "sample_reason": self.reason if self.synthetic else None,
                "defaults": DEFAULTS, "evaluation": evaluation, "benchmark": benchmark,
                "quantum": capabilities(),
                "dataset_cells": 8 if self.synthetic else len(self.data["cells"]),
                "test_cells": None if self.synthetic else len(self.model.artifact["cell_splits"]["test"])}

    @staticmethod
    def settings(payload):
        """Check settings before starting a new comparison."""
        unknown = set(payload) - set(DEFAULTS)
        if unknown:
            raise ValueError("Unknown trial settings")
        settings = {**DEFAULTS, **payload}
        choices = {"candidates": (6, 8, 10, 12), "pack_size": (2, 3, 4, 5),
                   "cutoff": (0, 20, 50, 100), "horizon": (50, 100, 200)}
        for key, allowed in choices.items():
            if type(settings[key]) is not int or settings[key] not in allowed:
                raise ValueError(f"Unsupported {key}")
        if type(settings["seed"]) is not int or not 0 <= settings["seed"] <= 2 ** 31 - 1:
            raise ValueError("Seed must be a nonnegative 32-bit integer")
        if settings["pack_size"] > settings["candidates"]:
            raise ValueError("Pack size exceeds candidate count")
        if settings["mode"] not in ("current_only", "trajectory_aware"):
            raise ValueError("Unknown objective mode")
        if settings["partition"] not in ("all", "test"):
            raise ValueError("Unknown battery source")
        if type(settings["quantum"]) is not bool:
            raise ValueError("Quantum selection must be true or false")
        return settings

    def create_trial(self, payload):
        """Predict and select first; keep actual future values on the server."""
        settings = self.settings(payload)
        if self.synthetic:
            if settings["partition"] != "all":
                raise ValueError("Sample data has no real training or test partitions")
            if settings["candidates"] != 8 or settings["cutoff"] != 0 or settings["horizon"] != 200:
                raise ValueError("Sample inputs support eight candidates, first-life history, and a 200-cycle horizon")
            cells, truth, metadata = synthetic_pool()
            metadata.update(seed=settings["seed"], cutoff_cycle=0, horizon_cycles=200)
        else:
            cells, truth, metadata = history_pool(self.data, self.model, seed=settings["seed"],
                candidates=settings["candidates"], cutoff=settings["cutoff"], horizon=settings["horizon"],
                partition=settings["partition"])
        started = perf_counter()
        problem = build_instance(cells, settings["pack_size"], mode=settings["mode"])
        optimum = exact_search(problem)
        selections = [healthiest_selection(problem), greedy_selection(problem),
                      simulated_annealing(problem, seed=settings["seed"]), optimum]
        quantum_selections, quantum = run_quantum(problem, seed=settings["seed"], enabled=settings["quantum"])
        for selection in quantum_selections:
            problem.validate_selection(selection.selected_indices, require_size=True)
            if abs(selection.objective_value - problem.energy(selection.selected_indices)) > 1e-9:
                raise ValueError("Quantum result does not match the shared objective")
            selections.append(selection)
        # the browser gets a trial ID, not the stored future capacities
        token = uuid.uuid4().hex
        trial = {"settings": settings, "cells": cells, "truth": truth, "problem": problem,
                 "selections": selections, "optimum": optimum, "revealed": False, "quantum": quantum,
                 "metadata": metadata}
        with self.lock:
            self.trials[token] = trial
            while len(self.trials) > 32:
                self.trials.popitem(last=False)
        snapshots = []
        for cell in cells:
            snapshot = asdict(cell)
            snapshot["health_percent"] = cell.soh * 100
            snapshot["predicted_loss_ah"] = cell.capacity_ah - cell.predicted_capacity_ah
            snapshots.append(snapshot)
        return {"trial_id": token, "settings": settings, "metadata": metadata,
                "snapshots": snapshots, "objective_metadata": problem.metadata,
                "results": [evaluate_selection(problem, s, optimum=optimum) for s in selections],
                "quantum": quantum,
                "computation_ms": (perf_counter() - started) * 1000,
                "future_available": truth is not None, "future_revealed": False}

    def get_trial(self, token):
        """Find a retained trial or ask the caller to run again."""
        with self.lock:
            if token not in self.trials:
                raise ValueError("This trial expired; run a new comparison")
            return self.trials[token]

    def reveal(self, token):
        """Return future measurements after selection has finished."""
        trial = self.get_trial(token)
        if trial["truth"] is None:
            raise ValueError("Sample data has no recorded future measurements")
        with self.lock:
            trial["revealed"] = True
        return {"trial_id": token, "truth": trial["truth"],
                "results": [evaluate_selection(trial["problem"], s, future_truth=trial["truth"],
                                               optimum=trial["optimum"]) for s in trial["selections"]],
                "note": "These measurements were excluded from selection and are shown only for retrospective validation."}

    def manual(self, token, indices):
        """Score a user-selected group using the same objective."""
        trial = self.get_trial(token)
        selected = result(trial["problem"], "manual", indices, perf_counter())
        return evaluate_selection(trial["problem"], selected, optimum=trial["optimum"],
                                  future_truth=trial["truth"] if trial["revealed"] else None)

    def export_problem(self, token):
        """Export solver inputs without recorded future measurements."""
        trial = self.get_trial(token)
        return {"settings": trial["settings"], "metadata": trial["metadata"],
                "snapshots": [asdict(c) for c in trial["cells"]],
                "objective_metadata": trial["problem"].metadata,
                "qubo": trial["problem"].qubo(), "quantum_status": trial["quantum"]["status"]}
