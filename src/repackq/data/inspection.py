"""Read-only raw dataset profiling used by the inspection command line tool."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from typing import Any

from repackq.data.adapters.deep_sorting import (
    FIELD_ALIASES,
    RANGE_FIELDS,
    RawDatasetFile,
    _field_value,
    enumerate_raw_files,
    expected_missing_cell_files,
    parse_number,
    resolve_columns,
)


@dataclass
class _Range:
    minimum: float | None = None
    maximum: float | None = None
    count: int = 0

    def add(self, value: float) -> None:
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        self.count += 1

    def as_dict(self) -> dict[str, float | int | None]:
        return {"min": self.minimum, "max": self.maximum, "count": self.count}


# Broad data-quality envelopes. Values outside them remain visible in invalid
# counters instead of pulling reported engineering ranges into nonsense values.
_VALID_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "capacity_ah": (0.0, 4.8),
    "internal_resistance_ohm": (0.0, 10.0),
    "temperature_c": (-50.0, 120.0),
}


def inspect_dataset(
    raw_root: str,
    *,
    phase: str = "second_life",
    representative_files: int = 2,
    max_rows_per_file: int | None = None,
) -> dict[str, Any]:
    """Profile schemas, field ranges, representative steps, and missing files.

    The default scans every row. ``max_rows_per_file`` is a clearly labeled
    quick sample for very large raw files; it does not change any source data.
    """

    if representative_files < 1:
        raise ValueError("representative_files must be at least 1")
    if max_rows_per_file is not None and max_rows_per_file < 1:
        raise ValueError("max_rows_per_file must be positive when provided")
    files = enumerate_raw_files(raw_root, phase)
    raw_ranges = {field: _Range() for field in RANGE_FIELDS}
    invalid_counts = {field: 0 for field in RANGE_FIELDS}
    all_columns: set[str] = set()
    file_reports: list[dict[str, Any]] = []
    cell_ids: set[str] = set()
    total_rows = 0
    step_truncated: set[str] = set()
    representative = {source.display_path for source in files[:representative_files]}

    for source in files:
        columns_in_file: list[str] = []
        resolved: dict[str, str] = {}
        rows_read = 0
        file_invalid = {field: 0 for field in RANGE_FIELDS}
        file_steps: set[str] = set()
        file_cell_ids: set[str] = set()
        was_truncated = False
        with source.open_csv() as (stream, _digest):
            reader = csv.DictReader(stream)
            columns_in_file = list(reader.fieldnames or [])
            all_columns.update(columns_in_file)
            resolved = resolve_columns(columns_in_file)
            for row in reader:
                if max_rows_per_file is not None and rows_read >= max_rows_per_file:
                    was_truncated = True
                    break
                rows_read += 1
                row_cell_id = _field_value(row, resolved, "cell_id")
                if row_cell_id and str(row_cell_id).strip():
                    file_cell_ids.add(str(row_cell_id).strip())
                raw_step = _field_value(row, resolved, "step_index")
                if raw_step not in (None, "") and source.display_path in representative:
                    step = str(raw_step).strip()
                    if len(file_steps) < 1000 or step in file_steps:
                        file_steps.add(step)
                    else:
                        step_truncated.add(source.display_path)
                for field in RANGE_FIELDS:
                    raw_value = _field_value(row, resolved, field)
                    if raw_value in (None, ""):
                        continue
                    number = parse_number(raw_value)
                    lower, upper = _VALID_BOUNDS[field]
                    if number is None or (lower is not None and number < lower) or (
                        upper is not None and number > upper
                    ):
                        file_invalid[field] += 1
                        invalid_counts[field] += 1
                    elif field in {"capacity_ah", "internal_resistance_ohm"} and number == 0:
                        # Zero is a normal cumulative-capacity reset or an
                        # unmeasured IR placeholder, not a physical summary.
                        continue
                    else:
                        raw_ranges[field].add(number)
        total_rows += rows_read
        cell_ids.update(file_cell_ids)
        if not file_cell_ids:
            fallback = _cell_id_from_filename(source)
            if fallback:
                cell_ids.add(fallback)
        file_reports.append(
            {
                "file": source.display_path,
                "columns": columns_in_file,
                "likely_fields": resolved,
                "rows_scanned": rows_read,
                "rows_truncated": was_truncated,
                "invalid_counts": file_invalid,
                "unique_step_indices": sorted(file_steps, key=_natural_key),
                "step_indices_truncated": source.display_path in step_truncated,
            }
        )

    schema_counts: dict[str, int] = {}
    for report in file_reports:
        signature = ", ".join(report["columns"])
        schema_counts[signature] = schema_counts.get(signature, 0) + 1
    likely_fields: dict[str, str | None] = {}
    for canonical in FIELD_ALIASES:
        likely_fields[canonical] = next(
            (
                report["likely_fields"][canonical]
                for report in file_reports
                if canonical in report["likely_fields"]
            ),
            None,
        )
    return {
        "phase": phase,
        "raw_root": raw_root,
        "file_count": len(files),
        "total_rows_scanned": total_rows,
        "sampled": max_rows_per_file is not None,
        "max_rows_per_file": max_rows_per_file,
        "cell_ids_found": sorted(cell_ids, key=_natural_key),
        "expected_missing_cell_file_ids": expected_missing_cell_files(files),
        "unavailable_cell_file_ids": ["61", "62"],
        "columns_union": sorted(all_columns),
        "schema_counts": schema_counts,
        "likely_fields": likely_fields,
        "valid_numeric_ranges": {
            field: raw_ranges[field].as_dict() for field in RANGE_FIELDS
        },
        "invalid_numeric_counts": invalid_counts,
        "representative_files": file_reports[:representative_files],
        "files": file_reports,
        "warnings": [
            "Ranges use broad engineering bounds; zero capacity/IR placeholders are ignored and rejected values are counted separately."
        ],
    }


def _cell_id_from_filename(source: RawDatasetFile) -> str | None:
    match = re.fullmatch(r"(?:battery|cell|bat)?[_-]?(\d+)", source.stem, re.IGNORECASE)
    return str(int(match.group(1))) if match else None


def _natural_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value))

