"""Extract comparable reference-discharge measurements from the raw files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

COLUMNS = ["Battery_ID", "Protocol_ID", "Cycle_Index", "Step_Index", "Current(A)",
           "Voltage(V)", "Discharge_Capacity(Ah)", "Internal_Resistance(Ohm)",
           "Aux_Temperature_1(C)"]


def sha256(path: Path) -> str:
    """Hash a source file in chunks without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def summarize_file(path: Path, phase: str) -> dict:
    """Extract completed reference-discharge cycles without loading raw traces whole."""
    import numpy as np
    import pandas as pd
    pieces = []
    identifiers = set()
    protocols = set()
    row_count = 0
    for chunk in pd.read_csv(path, usecols=COLUMNS, chunksize=200_000):
        row_count += len(chunk)
        identifiers.update(chunk["Battery_ID"].dropna().astype(int).unique().tolist())
        protocols.update(chunk["Protocol_ID"].dropna().astype(int).unique().tolist())
        pieces.append(chunk.loc[chunk["Step_Index"].isin([14, 15, 17])])
    if len(identifiers) != 1:
        raise ValueError(f"Expected one Battery_ID in {path}, found {identifiers}")
    records = pd.concat(pieces, ignore_index=True)
    # step 15 is the comparable reference discharge; other discharge steps are excluded
    discharge = records.loc[(records["Step_Index"] == 15) & (records["Current(A)"] < -0.1)]
    if discharge.empty or abs(float(discharge["Current(A)"].median()) + 0.48) > 0.05:
        raise ValueError(f"Unverified reference-discharge current/step in {path}")
    # use the recorded capacity counter rather than integrating current again
    capacities = discharge.groupby("Cycle_Index").agg(
        capacity_ah=("Discharge_Capacity(Ah)", "max"),
        end_voltage_v=("Voltage(V)", "last"),
        temperature_c=("Aux_Temperature_1(C)", "mean"),
    )
    resistance = records.loc[records["Internal_Resistance(Ohm)"] > 0].groupby(
        "Cycle_Index")["Internal_Resistance(Ohm)"].median()
    capacities["resistance_ohm"] = resistance
    capacities = capacities.loc[(capacities.capacity_ah > 0) &
                                (capacities.capacity_ah < 3.0) &
                                (capacities.end_voltage_v <= 3.1)].sort_index()
    points = []
    for cycle, row in capacities.iterrows():
        points.append({"cycle": int(cycle), "capacity_ah": float(row.capacity_ah),
                       "resistance_ohm": float(row.resistance_ohm) if np.isfinite(row.resistance_ohm) else None,
                       "temperature_c": float(row.temperature_c) if np.isfinite(row.temperature_c) else None})
    if len(points) < 4:
        raise ValueError(f"Too few complete reference cycles in {path}")
    return {"cell_id": str(next(iter(identifiers))), "phase": phase, "points": points,
            "protocol_ids": sorted(protocols), "source": {"path": str(path),
            "bytes": path.stat().st_size, "sha256": sha256(path), "rows": row_count}}


def prepare(root: Path, output: Path) -> dict:
    """Join phases using recorded identity, never filenames or future outcomes."""
    cache = output.parent / "diagnostic_cache"
    cache.mkdir(parents=True, exist_ok=True)
    paired = {}
    sources = []
    for phase, folder in (("primary", "Primary_use_phase"), ("second_life", "Second_life_phase")):
        files = sorted((root / folder).glob("*.csv"), key=lambda p: int(p.stem))
        if not files:
            raise ValueError(f"No CSV files in {root / folder}")
        for index, path in enumerate(files, 1):
            cached = cache / f"{phase}-{path.stem}.json"
            stamp = [path.stat().st_size, path.stat().st_mtime_ns]
            record = json.loads(cached.read_text()) if cached.exists() else None
            if record is None or record.get("stamp") != stamp:
                record = summarize_file(path, phase)
                if [path.stat().st_size, path.stat().st_mtime_ns] != stamp:
                    raise OSError(f"Raw file changed during preprocessing; retry after copying completes: {path}")
                record["stamp"] = stamp
                cached.write_text(json.dumps(record, allow_nan=False))
            cell = paired.setdefault(record["cell_id"], {"cell_id": record["cell_id"]})
            if phase in cell:
                raise ValueError(f"Duplicate Battery_ID {record['cell_id']} in {phase}")
            cell[phase] = record["points"]
            cell.setdefault("protocol_ids", record["protocol_ids"])
            # Keep provenance portable without storing the local account's path.
            sources.append({**record["source"], "path": str(Path(folder) / path.name)})
            print(f"{phase} {index}/{len(files)}: cell {record['cell_id']}, {len(record['points'])} diagnostics", flush=True)
    unmatched = [key for key, value in paired.items() if not {"primary", "second_life"} <= value.keys()]
    if unmatched:
        raise ValueError(f"Cells missing a phase: {unmatched}")
    result = {"schema_version": 1, "nominal_capacity_ah": 2.4,
              "reference_discharge": {"step": 15, "current_a": -0.48, "endpoint_v": 3.0},
              "cells": sorted(paired.values(), key=lambda c: int(c["cell_id"])),
              "provenance": {"dataset_doi": "10.5281/zenodo.14859405", "sources": sources,
                             "redistribution_status": "not yet independently verified"}}
    output.write_text(json.dumps(result, indent=2, allow_nan=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cell_histories.json"))
    args = parser.parse_args()
    prepare(args.root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
