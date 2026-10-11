"""Summarize every measurement step while keeping reference-capacity targets.

Each second-life summary stops at its reference cycle to exclude later data."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from ..data.prepare import sha256

MEASUREMENTS = {"current": "Current(A)", "voltage": "Voltage(V)",
                "temperature": "Aux_Temperature_1(C)", "resistance": "Internal_Resistance(Ohm)"}
MAXIMA = {"charge_capacity_max": "Charge_Capacity(Ah)",
          "discharge_capacity_max": "Discharge_Capacity(Ah)",
          "charge_energy_max": "Charge_Energy(Wh)", "discharge_energy_max": "Discharge_Energy(Wh)"}


def summarize_usage(path: Path, chunksize=200_000):
    """Streaming all-step, per-cycle aggregates; combine split cycles exactly."""
    import pandas as pd
    columns = ["Battery_ID", "Protocol_ID", "Cycle_Index", "Test_Time(s)",
               *MEASUREMENTS.values(), *MAXIMA.values()]
    cycles, identities, protocols = {}, set(), set()
    raw_rows = 0
    for chunk in pd.read_csv(path, usecols=columns, chunksize=chunksize):
        raw_rows += len(chunk)
        identities.update(chunk["Battery_ID"].dropna().astype(int).unique())
        protocols.update(chunk["Protocol_ID"].dropna().astype(int).unique())
        if chunk["Cycle_Index"].isna().any():
            raise ValueError(f"Missing cycle identity in {path}")
        chunk["current_abs"] = chunk["Current(A)"].abs()
        chunk["Internal_Resistance(Ohm)"] = chunk["Internal_Resistance(Ohm)"].where(
            chunk["Internal_Resistance(Ohm)"] > 0)
        aggregations = {"rows": ("Cycle_Index", "size"), "time_min": ("Test_Time(s)", "min"),
                        "time_max": ("Test_Time(s)", "max")}
        for name, column in {**MEASUREMENTS, "current_abs": "current_abs"}.items():
            for operation in ("sum", "count", "min", "max"):
                aggregations[name + "_" + operation] = (column, operation)
        for name, column in MAXIMA.items():
            aggregations[name] = (column, "max")
        grouped = chunk.groupby("Cycle_Index").agg(**aggregations)
        for cycle, row in grouped.iterrows():
            values = cycles.setdefault(int(cycle), {})
            for name, value in row.items():
                if not math.isfinite(value):
                    continue
                if name.endswith("_min"):
                    values[name] = min(values.get(name, value), float(value))
                elif name.endswith("_max"):
                    values[name] = max(values.get(name, value), float(value))
                else:
                    values[name] = values.get(name, 0) + float(value)
    if len(identities) != 1 or not raw_rows:
        raise ValueError(f"Expected one nonempty recorded battery in {path}")
    records = [{"cycle": cycle, **values} for cycle, values in sorted(cycles.items())]
    if sum(r["rows"] for r in records) != raw_rows:
        raise RuntimeError("All-row accounting failed")
    return {"cell_id": str(next(iter(identities))), "protocol_ids": sorted(map(int, protocols)),
            "raw_rows": raw_rows, "cycles": records}


def pool_usage(records):
    """Combine an interval of raw-cycle aggregates without mixing future intervals."""
    if not records:
        raise ValueError("Reference observation has no raw usage interval")
    pooled = {}
    for name in ("current", "current_abs", "voltage", "temperature", "resistance"):
        count = sum(r.get(name + "_count", 0) for r in records)
        pooled[name + "_mean"] = sum(r.get(name + "_sum", 0) for r in records) / count if count else None
        for operation, reducer in (("min", min), ("max", max)):
            values = [r[name + "_" + operation] for r in records if name + "_" + operation in r]
            pooled[name + "_" + operation] = reducer(values) if values else None
    for name in MAXIMA:
        values = [r[name] for r in records if name in r]
        pooled[name] = max(values) if values else None
    times_min = [r["time_min"] for r in records if "time_min" in r]
    times_max = [r["time_max"] for r in records if "time_max" in r]
    pooled["duration_span_s"] = max(times_max) - min(times_min) if times_min and times_max else None
    pooled["log_rows"] = math.log1p(sum(r["rows"] for r in records))
    return pooled


def attach_usage(points, cycles, phase):
    """Attach usage intervals ending at each reference cycle.

    First-life history is known at retirement. For second life, include only
    usage up to the current observation."""
    points = copy.deepcopy(sorted(points, key=lambda p: p["cycle"]))
    start = 0
    for index, point in enumerate(points):
        end = start
        while end < len(cycles) and cycles[end]["cycle"] <= point["cycle"]:
            end += 1
        if phase == "primary" and index == len(points) - 1:
            end = len(cycles)
        point["usage"] = pool_usage(cycles[start:end])
        start = end
    return points, int(sum(r["rows"] for r in cycles[start:]))


def prepare_full(root: Path, baseline: Path, output: Path, available_only=False):
    """Attach per-cycle usage summaries to the reference histories."""
    data = json.loads(baseline.read_text())
    data = copy.deepcopy(data)
    cache = output.parent / "usage_cache"
    cache.mkdir(parents=True, exist_ok=True)
    cells = {c["cell_id"]: c for c in data["cells"]}
    pending, coverage = [], []
    for source in data["provenance"]["sources"]:
        original = Path(source["path"])
        path = root / original.parent.name / original.name
        phase = "primary" if path.parent.name == "Primary_use_phase" else "second_life"
        stamp = [path.stat().st_size, path.stat().st_mtime_ns]
        cached = cache / f"{phase}-{path.stem}.json"
        record = json.loads(cached.read_text()) if cached.exists() else None
        if (record is None or record.get("stamp") != stamp
                or record.get("source_sha256") != source["sha256"]):
            # UF_DATALESS on macOS means opening may block on a cloud download.
            if getattr(path.stat(), "st_flags", 0) & 0x40000000:
                pending.append(str(path))
                if available_only:
                    continue
                raise OSError(f"Cloud-only raw file: {path}; download it in Finder, then rerun")
            print(f"Reading every measurement: {path}", flush=True)
            record = summarize_usage(path)
            if sha256(path) != source["sha256"]:
                raise ValueError(f"Raw data differs from the original extraction: {path}")
            if [path.stat().st_size, path.stat().st_mtime_ns] != stamp:
                raise OSError(f"Raw file changed while reading: {path}")
            record["stamp"] = stamp
            record["source_sha256"] = source["sha256"]
            if record["raw_rows"] != source["rows"]:
                raise ValueError(f"Raw row count changed: {path}")
            cached.write_text(json.dumps(record, allow_nan=False))
        cell = cells[record["cell_id"]]
        points, trailing = attach_usage(cell[phase], record["cycles"], phase)
        cell[phase] = points
        coverage.append({"cell_id": record["cell_id"], "phase": phase,
                         "rows": record["raw_rows"], "trailing_rows_without_later_reference": trailing})
    status = {"completed_files": len(coverage), "pending_files": pending,
              "raw_rows_processed": sum(r["rows"] for r in coverage), "coverage": coverage}
    (output.parent / "usage_availability.json").write_text(json.dumps(status, indent=2))
    if pending:
        print(json.dumps({"completed_files": len(coverage), "pending_files": len(pending)}, indent=2), flush=True)
        return status
    data["schema_version"] = 2
    data["all_measurement_usage"] = status
    output.write_text(json.dumps(data, indent=2, allow_nan=False))
    print(f"All {status['raw_rows_processed']:,} raw rows accounted for in {len(coverage)} files", flush=True)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--baseline", type=Path, default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cell_histories_full.json"))
    parser.add_argument("--available-only", action="store_true", help="Cache readable files and report cloud-only files")
    args = parser.parse_args()
    prepare_full(args.root.resolve(), args.baseline.resolve(), args.output.resolve(), args.available_only)


if __name__ == "__main__":
    main()
