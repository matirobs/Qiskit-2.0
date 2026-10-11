"""Build candidate pools and keep their future measurements separate."""
import math
import random

from repackq.api import predict_snapshot
from repackq.optimization import CellSnapshot


def history_pool(data, model, *, seed=11, candidates=8, cutoff=0, horizon=200,
                 minimum_soh=.5, partition="test"):
    """Sample eligible cells from the requested dataset partition.

    Future measurement availability determines eligibility, but its capacity
    value never enters scoring."""
    if type(candidates) is not int or candidates < 1:
        raise ValueError("Candidate count must be a positive integer")
    if type(cutoff) is not int or cutoff < 0 or type(horizon) is not int or horizon < 1:
        raise ValueError("Cutoff must be nonnegative and horizon must be positive integers")
    if not math.isfinite(minimum_soh) or not 0 <= minimum_soh <= 1:
        raise ValueError("Minimum state of health must be between zero and one")
    if partition not in ("test", "all"):
        raise ValueError("Partition must be test or all")
    splits = model.artifact.get("cell_splits", {})
    allowed = set(splits.get("test", [])) if partition == "test" else None
    if partition == "test" and not allowed:
        raise ValueError("Model does not declare test-cell identities; cannot make a held-out trial")
    eligible, truths, skipped = [], {}, {}
    partition_count = 0
    identifiers = [str(c["cell_id"]) for c in data["cells"]]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate cell identities in histories")
    for cell in sorted(data["cells"], key=lambda c: str(c["cell_id"])):
        identifier = str(cell["cell_id"])
        if allowed is not None and identifier not in allowed:
            continue
        partition_count += 1
        known = [point for point in cell["second_life"] if point["cycle"] <= cutoff]
        if len(cell["primary"]) < 4 or (cutoff > 0 and len(known) < 4):
            skipped[identifier] = "insufficient observed reference history"
            continue
        later = [point for point in cell["second_life"] if point["cycle"] > cutoff]
        if not later:
            skipped[identifier] = "no later reference measurement"
            continue
        target = cutoff + horizon
        truth = min(later, key=lambda p: (abs(p["cycle"] - target), p["cycle"]))
        distance = abs(truth["cycle"] - target)
        if distance > max(5, round(.05 * horizon)):
            skipped[identifier] = "no reference measurement near requested future cycle"
            continue
        # only models trained with protocol categories need those extra inputs
        protocol_args = {}
        if (model.artifact.get("feature_spec") or {}).get("protocols"):
            protocol_args["primary_protocol_ids"] = cell.get("protocol_ids")
        snapshot = CellSnapshot.from_mapping(predict_snapshot(model, cell_id=identifier,
            primary_history=cell["primary"], observed_second_life=known, cutoff=cutoff,
            horizon=horizon, **protocol_args))
        if snapshot.soh < minimum_soh:
            skipped[identifier] = "below current health threshold"
            continue
        eligible.append(snapshot)
        truths[identifier] = {"actual_capacity_ah": truth["capacity_ah"],
                              "target_cycle_index": truth["cycle"], "nearest_cycle_distance": distance}
    if len(eligible) < candidates:
        raise ValueError(f"Need {candidates} eligible {partition} cells, found {len(eligible)}; skipped: {skipped}")
    selected = random.Random(seed).sample(eligible, candidates)
    # Sort after sampling so indices and tie handling are stable for the same pool.
    selected.sort(key=lambda c: c.cell_id)
    selected_ids = {c.cell_id for c in selected}
    candidate_partitions = {name: len(selected_ids.intersection(map(str, splits.get(name, []))))
                            for name in ("train", "validation", "test")}
    limitations = ["Previously inspected test cells; exploratory comparison, not a fresh blind test.",
                  "Repeated pools overlap and are not independent battery experiments.",
                  "Same dataset and test conditions; no arbitrary-load lifetime claim."]
    if partition == "all":
        limitations.append("All-cell pools can include batteries used to train or tune the predictor; not held-out prediction evaluation.")
    return tuple(selected), {c.cell_id: truths[c.cell_id] for c in selected}, {
        "source": "derived-real", "partition": partition, "seed": seed,
        "dataset_cells": len(data["cells"]), "partition_cells": partition_count,
        "selection_method": "seeded_random_sample", "candidate_partitions": candidate_partitions,
        "cutoff_cycle": cutoff, "horizon_cycles": horizon, "eligible_cells": len(eligible),
        "candidate_ids": [c.cell_id for c in selected], "minimum_soh": minimum_soh,
        "skipped": skipped, "held_out_from_predictor": partition == "test",
        "limitations": limitations}


def synthetic_pool():
    """Eight invented cells for running the project without local model files."""
    current = [2.00, 2.01, 1.99, 2.02, 1.97, 1.98, 2.03, 2.04]
    future = [1.80, 1.56, 1.79, 1.58, 1.78, 1.77, 1.60, 1.62]
    cells = tuple(CellSnapshot(chr(65 + i), c, internal_resistance_ohm=.04 + i * .0003,
                               predicted_capacity_ah=future[i], prediction_uncertainty_ah=.06)
                  for i, c in enumerate(current))
    return cells, None, {"source": "synthetic-fixture", "candidate_ids": [c.cell_id for c in cells],
                         "limitations": ["Invented values for software demonstration, not scientific evidence."]}
