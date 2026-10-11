"""Build local compact trajectories, provenance, and a preprocessing report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.data.adapters.deep_sorting import (
    CODE_REFERENCE_DOI,
    CODE_REFERENCE_REPOSITORY,
    CODE_REFERENCE_URL,
    DATASET_DOI,
    DATASET_KEY,
    DATASET_NAME,
    DATASET_URL,
    DIAGNOSTIC_CYCLE_OFFSET,
    DIAGNOSTIC_CYCLE_STRIDE,
    UNAVAILABLE_CELL_FILE_IDS,
    enumerate_raw_files,
    preprocess_dataset,
)
from repackq.data.inspection import inspect_dataset
from repackq.data.serialization import (
    canonical_json_bytes,
    trajectories_to_dict,
    write_json_atomic,
)


def _git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _trajectory_ranges(dataset: dict[str, Any]) -> dict[str, dict[str, float | int | None]]:
    fields = ("capacity_ah", "internal_resistance_ohm", "temperature_c")
    values: dict[str, list[float]] = {field: [] for field in fields}
    for cell in dataset["cells"]:
        for observation in cell["observations"]:
            for field in fields:
                value = observation[field]
                if isinstance(value, (int, float)):
                    values[field].append(float(value))
    return {
        field: {
            "min": min(numbers) if numbers else None,
            "max": max(numbers) if numbers else None,
            "count": len(numbers),
        }
        for field, numbers in values.items()
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stream the official Deep Sorting raw CSV/ZIP data into compact "
            "canonical trajectories. Generated real-data records are local "
            "outputs; the source record does not declare a redistribution license."
        )
    )
    parser.add_argument("--raw-root", required=True, help="raw dataset directory, CSV, or ZIP")
    parser.add_argument(
        "--output", default="data/processed/trajectories.json",
        help="compact trajectory JSON output path",
    )
    parser.add_argument(
        "--phase", choices=("primary", "second_life"), default="second_life",
        help="raw dataset phase (default: second_life)",
    )
    parser.add_argument(
        "--nominal-capacity", type=float, default=2.4,
        help="nominal capacity in Ah (default: 2.4)",
    )
    parser.add_argument(
        "--inspect-only", action="store_true",
        help="profile the raw files and exit without writing generated assets",
    )
    parser.add_argument("--provenance-output", help="override provenance JSON path")
    parser.add_argument("--summary-output", help="override preprocessing summary JSON path")
    return parser


def _report_progress(index: int, total: int, source: str) -> None:
    print(f"[{index}/{total}] Reading {source}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    output = Path(args.output)
    provenance_output = Path(args.provenance_output) if args.provenance_output else output.parent / "provenance.json"
    summary_output = Path(args.summary_output) if args.summary_output else output.parent / "preprocessing_summary.json"
    try:
        if args.inspect_only:
            report = inspect_dataset(args.raw_root, phase=args.phase)
            print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
            return 0

        result = preprocess_dataset(
            args.raw_root,
            phase=args.phase,
            nominal_capacity_ah=args.nominal_capacity,
            progress=_report_progress,
        )
        if not result.trajectories:
            parser.exit(2, "preprocess_primary: error: no cells had valid observations; no output written\n")

        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        dataset_object = trajectories_to_dict(
            result.trajectories,
            phase=args.phase,
            nominal_capacity_ah=args.nominal_capacity,
            data_classification="derived-real",
        )
        processed_dataset_sha256 = hashlib.sha256(
            canonical_json_bytes(dataset_object)
        ).hexdigest()
        raw_files = [
            {
                "file": report["file"],
                "rows": report["rows"],
                "sha256_uncompressed_csv": report["sha256_uncompressed_csv"],
            }
            for report in result.file_reports
        ]
        valid_observation_count = sum(
            len(trajectory.observations) for trajectory in result.trajectories
        )
        provenance = {
            "dataset_name": DATASET_NAME,
            "dataset_doi": DATASET_DOI,
            "code_reference_doi": CODE_REFERENCE_DOI,
            "source_urls": [
                DATASET_URL,
                CODE_REFERENCE_URL,
                CODE_REFERENCE_REPOSITORY,
            ],
            "source_dataset_key": DATASET_KEY,
            "phase": args.phase,
            "raw_root_name": Path(args.raw_root).expanduser().name,
            "raw_files": raw_files,
            "raw_checksums": {
                entry["file"]: entry["sha256_uncompressed_csv"] for entry in raw_files
            },
            "number_of_cells": len(result.trajectories),
            "number_of_valid_observations": valid_observation_count,
            "processed_dataset_sha256": processed_dataset_sha256,
            "excluded_cells": result.excluded_cells,
            "missing_expected_cell_files": result.missing_expected_cell_files,
            "unavailable_cell_file_ids": list(UNAVAILABLE_CELL_FILE_IDS),
            "processing_date_utc": generated_at,
            "processing_script": "src/scripts/preprocess_primary.py",
            "processing_commit": _git_revision(),
            "python_version": platform.python_version(),
            "nominal_capacity_ah": args.nominal_capacity,
            "capacity_convention": (
                "The maximum finite positive Discharge_Capacity(Ah) recorded "
                "within a diagnostic cycle is used as cycle capacity; SOH is "
                "computed downstream as capacity_ah / nominal_capacity_ah."
            ),
            "diagnostic_cycle_rule": (
                f"Cycle_Index % {DIAGNOSTIC_CYCLE_STRIDE} == "
                f"{DIAGNOSTIC_CYCLE_OFFSET}, matching the dataset's one-in-five "
                "diagnostic cadence and the published extraction reference."
            ),
            "resistance_summary": "Arithmetic mean of valid positive resistance samples within each cycle.",
            "temperature_summary": "Arithmetic mean of valid -50 C to 120 C samples within each cycle.",
            "redistribution_license_verified": False,
            "redistribution_note": (
                "Zenodo record 10.5281/zenodo.14859405 has no license value in its "
                "public Rights section. Treat generated cell-level records as local "
                "derived data; do not redistribute until terms are clarified."
            ),
            "warnings": [
                "Cell IDs use Battery_ID when present and the source filename only as fallback.",
                "Cells 61 and 62 are documented as unavailable in the source dataset.",
            ],
        }
        summary = {
            "dataset_name": DATASET_NAME,
            "source_dataset": DATASET_KEY,
            "data_classification": "derived-real",
            "phase": args.phase,
            "generated_at_utc": generated_at,
            "raw_file_count": len(result.file_reports),
            "raw_rows_scanned": result.total_raw_rows,
            "cell_count": len(result.trajectories),
            "valid_observation_count": valid_observation_count,
            "missing_expected_cell_files": result.missing_expected_cell_files,
            "excluded_cells": result.excluded_cells,
            "valid_observation_ranges": _trajectory_ranges(dataset_object),
            "files": result.file_reports,
            "processed_dataset_sha256": processed_dataset_sha256,
            "redistribution_license_verified": False,
        }
        write_json_atomic(output, dataset_object)
        write_json_atomic(provenance_output, provenance)
        write_json_atomic(summary_output, summary)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        parser.exit(2, f"preprocess_primary: error: {error}\n")

    print(f"Wrote {len(result.trajectories)} cell trajectories to {output}")
    print(f"Wrote source checksums and provenance to {provenance_output}")
    print(f"Wrote preprocessing report to {summary_output}")
    print(
        "Generated trajectories are derived-real local assets. The dataset's "
        "redistribution license is unspecified; do not publish the cell records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

