"""Streaming adapter for the public Deep Sorting second-life dataset.

This module converts raw per-sample CSVs into compact diagnostic-cycle
observations. It does not use the authors' grouping or feature-engineering code.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import zipfile
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator, TextIO

from repackq.models import CellObservation, CellTrajectory


DATASET_NAME = (
    "Data for: Deep sorting of reused batteries for enabling long-term "
    "consistency grouping with unknown prior conditions"
)
DATASET_KEY = "deep_sorting_reused_batteries"
DATASET_DOI = "10.5281/zenodo.14859405"
CODE_REFERENCE_DOI = "10.5281/zenodo.15350607"
DATASET_URL = "https://doi.org/10.5281/zenodo.14859405"
CODE_REFERENCE_URL = "https://doi.org/10.5281/zenodo.15350607"
CODE_REFERENCE_REPOSITORY = (
    "https://github.com/wshuquan/Deep_sorting_of_reused_batteries/tree/v1.0.0"
)

# The dataset's diagnostic cadence is one diagnostic cycle followed by four
# operational cycles. The associated public extraction release selects cycles
# 1, 6, 11, ... (Cycle_Index % 5 == 1). Keeping this rule explicit avoids
# treating every logged waveform cycle as a capacity diagnostic.
DIAGNOSTIC_CYCLE_STRIDE = 5
DIAGNOSTIC_CYCLE_OFFSET = 1
UNAVAILABLE_CELL_FILE_IDS = ("61", "62")
EXPECTED_CELL_FILE_IDS = tuple(
    str(cell_id)
    for cell_id in range(1, 89)
    if str(cell_id) not in UNAVAILABLE_CELL_FILE_IDS
)


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "cell_id": (
        "Battery_ID", "Cell_ID", "Battery", "Cell", "Battery_Number",
        "Cell_Number", "BatteryID", "CellID",
    ),
    "protocol_id": (
        "Protocol_ID", "Protocol", "ProtocolID", "Test_Protocol",
    ),
    "cycle_index": (
        "Cycle_Index", "Cycle", "Cycle_ID", "CycleIndex", "CycleNumber",
    ),
    "step_index": (
        "Step_Index", "Step", "Step_ID", "StepIndex", "StepNumber",
    ),
    "capacity_ah": (
        "Discharge_Capacity(Ah)", "Discharge_Capacity_Ah",
        "DischargeCapacity(Ah)", "DischargeCapacityAh", "Capacity(Ah)",
        "Capacity_Ah", "Capacity", "Discharge_Capacity",
    ),
    "internal_resistance_ohm": (
        "Internal_Resistance(Ohm)", "Internal_Resistance_Ohm",
        "InternalResistance(Ohm)", "InternalResistanceOhm", "IR(Ohm)",
        "Resistance(Ohm)", "Resistance_Ohm", "Resistance",
    ),
    "temperature_c": (
        "Aux_Temperature_1(C)", "Aux_Temperature_1(°C)",
        "Aux_Temperature_1_C", "AuxTemperature1C",
        "Surface_Temperature(C)", "Surface_Temperature(°C)",
        "Temperature(C)", "Temperature(°C)", "Temperature_C",
        "SurfaceTemperatureC", "Temp(C)", "Temperature",
    ),
}

REQUIRED_FIELDS = ("cycle_index", "capacity_ah")
RANGE_FIELDS = (
    "capacity_ah", "internal_resistance_ohm", "temperature_c",
)


def normalize_column_name(value: str) -> str:
    """Normalize unit punctuation, spaces, and case for alias matching."""

    return "".join(character.lower() for character in value if character.isalnum())


NORMALIZED_ALIASES = {
    canonical: tuple(normalize_column_name(alias) for alias in aliases)
    for canonical, aliases in FIELD_ALIASES.items()
}


def resolve_columns(fieldnames: list[str] | None) -> dict[str, str]:
    """Map canonical names to available raw headers, preferring known aliases."""

    if not fieldnames:
        return {}
    by_normalized: dict[str, str] = {}
    for name in fieldnames:
        if name is not None:
            by_normalized.setdefault(normalize_column_name(name), name)
    result: dict[str, str] = {}
    for canonical, aliases in NORMALIZED_ALIASES.items():
        for alias in aliases:
            actual = by_normalized.get(alias)
            if actual is not None:
                result[canonical] = actual
                break
    return result


def parse_number(value: object) -> float | None:
    """Parse finite numeric text while tolerating common missing-value forms."""

    if value is None:
        return None
    text = str(value).strip().replace("−", "-")
    if not text or text.lower() in {"nan", "na", "n/a", "none", "null", "-", "--"}:
        return None
    # Be tolerant of decimal-comma exports without misreading 1,234 as 1.234.
    if "," in text and "." not in text:
        if text.count(",") == 1 and len(text.rsplit(",", 1)[1]) != 3:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "")
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _parse_cycle(value: object) -> int | None:
    number = parse_number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _canonical_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    number = parse_number(text)
    if number is not None and number.is_integer() and re.fullmatch(r"[+-]?\d+(?:\.0+)?", text):
        return str(int(number))
    return text


class _HashingReader(io.RawIOBase):
    """Hash bytes while csv.DictReader consumes a regular or ZIP CSV stream."""

    def __init__(self, source: object, digest: object) -> None:
        super().__init__()
        self._source = source
        self._digest = digest

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray) -> int:
        chunk = self._source.read(len(buffer))  # type: ignore[attr-defined]
        if not chunk:
            return 0
        self._digest.update(chunk)  # type: ignore[attr-defined]
        buffer[: len(chunk)] = chunk
        return len(chunk)


@dataclass(frozen=True)
class RawDatasetFile:
    """A CSV path that may be inside a ZIP archive, without extracting it."""

    container: Path
    member: str | None = None
    source_label: str | None = None

    @property
    def display_path(self) -> str:
        if self.source_label is not None:
            return self.source_label
        if self.member is None:
            return self.container.name
        return f"{self.container.name}!/{self.member}"

    @property
    def filename(self) -> str:
        return PurePosixPath(self.member).name if self.member else self.container.name

    @property
    def stem(self) -> str:
        return Path(self.filename).stem

    @contextmanager
    def open_csv(self) -> Iterator[tuple[TextIO, object]]:
        """Yield UTF-8 text and a SHA-256 object updated as the file is read."""

        digest = hashlib.sha256()
        with ExitStack() as stack:
            if self.member is None:
                raw = stack.enter_context(self.container.open("rb"))
            else:
                archive = stack.enter_context(zipfile.ZipFile(self.container))
                raw = stack.enter_context(archive.open(self.member, "r"))
            hashing = _HashingReader(raw, digest)
            buffered = io.BufferedReader(hashing)
            text = io.TextIOWrapper(buffered, encoding="utf-8-sig", errors="replace", newline="")
            stack.callback(text.close)
            yield text, digest


def _phase_token(value: str) -> str:
    return value.lower().replace("_", "").replace("-", "")


def _path_contains_phase(path_text: str, phase: str) -> bool:
    token = _phase_token(phase)
    parts = [_phase_token(part) for part in re.split(r"[/\\!]+", path_text)]
    return any(token in part for part in parts)


def _zip_csv_files(archive_path: Path, archive_label: str | None = None) -> list[RawDatasetFile]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = [
                name for name in archive.namelist()
                if name.lower().endswith(".csv") and not name.endswith("/")
            ]
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"Cannot read ZIP archive {archive_path}: {error}") from error
    label = archive_label or archive_path.name
    return [
        RawDatasetFile(archive_path, name, f"{label}!/{name}")
        for name in names
    ]


def enumerate_raw_files(raw_root: str | Path, phase: str) -> list[RawDatasetFile]:
    """Find phase-specific CSVs under a directory, or directly in a ZIP/file."""

    root = Path(raw_root).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Raw data path does not exist: {root}")
    candidates: list[RawDatasetFile] = []
    if root.is_file():
        if root.suffix.lower() == ".csv":
            candidates = [RawDatasetFile(root, source_label=root.name)]
        elif root.suffix.lower() == ".zip":
            candidates = _zip_csv_files(root, root.name)
        else:
            raise ValueError(f"Expected a CSV, ZIP, or directory: {root}")
    else:
        for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".csv":
                relative_label = f"{root.name}/{path.relative_to(root).as_posix()}"
                candidates.append(RawDatasetFile(path, source_label=relative_label))
            elif path.suffix.lower() == ".zip":
                relative_label = f"{root.name}/{path.relative_to(root).as_posix()}"
                candidates.extend(_zip_csv_files(path, relative_label))

    phase_matches = [
        source for source in candidates
        if _path_contains_phase(source.display_path, phase)
    ]
    if phase_matches:
        candidates = phase_matches
    elif root.is_file() and root.suffix.lower() == ".zip":
        # A phase-specific archive often stores its CSVs at archive root.
        if _path_contains_phase(root.name, phase):
            pass
        elif any(
            _path_contains_phase(source.member or "", "primary" if phase == "second_life" else "second_life")
            for source in candidates
        ):
            candidates = []
    elif root.is_dir():
        # A supplied phase directory is a valid root even if child paths omit it.
        if not _path_contains_phase(str(root), phase):
            other_phase = "primary" if phase == "second_life" else "second_life"
            other_matches = [
                source for source in candidates
                if _path_contains_phase(source.display_path, other_phase)
            ]
            if other_matches:
                candidates = [source for source in candidates if source not in other_matches]

    unique: dict[str, RawDatasetFile] = {}
    for source in candidates:
        unique[source.display_path] = source
    result = sorted(unique.values(), key=_natural_source_key)
    if not result:
        raise FileNotFoundError(
            f"No {phase} CSV files found under {root}. Download the official archive "
            "or extract it under a phase-named directory."
        )
    return result


def _natural_source_key(source: RawDatasetFile) -> tuple[object, ...]:
    text = source.filename.lower()
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text))


def expected_missing_cell_files(files: list[RawDatasetFile]) -> list[str]:
    present: set[str] = set()
    for source in files:
        match = re.fullmatch(r"(?:battery|cell|bat)?[_-]?(\d+)", source.stem, re.IGNORECASE)
        if match:
            present.add(str(int(match.group(1))))
    if not present:
        return []
    return [cell_id for cell_id in EXPECTED_CELL_FILE_IDS if cell_id not in present]


@dataclass
class _CycleAccumulator:
    capacity_ah: float | None = None
    resistance_sum: float = 0.0
    resistance_count: int = 0
    temperature_sum: float = 0.0
    temperature_count: int = 0

    def add_capacity(self, value: float) -> None:
        self.capacity_ah = value if self.capacity_ah is None else max(self.capacity_ah, value)

    def add_resistance(self, value: float) -> None:
        self.resistance_sum += value
        self.resistance_count += 1

    def add_temperature(self, value: float) -> None:
        self.temperature_sum += value
        self.temperature_count += 1

    @property
    def mean_resistance(self) -> float | None:
        return self.resistance_sum / self.resistance_count if self.resistance_count else None

    @property
    def mean_temperature(self) -> float | None:
        return self.temperature_sum / self.temperature_count if self.temperature_count else None


@dataclass
class CellExtraction:
    trajectory: CellTrajectory | None
    raw_file: str
    row_count: int
    raw_sha256: str
    invalid_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _field_value(row: dict[str, str | None], columns: dict[str, str], key: str) -> str | None:
    actual = columns.get(key)
    return row.get(actual) if actual is not None else None


def _valid_positive(value: float | None, upper: float | None = None) -> bool:
    return value is not None and value > 0 and (upper is None or value <= upper)


def extract_cell(
    source: RawDatasetFile,
    *,
    phase: str,
    nominal_capacity_ah: float,
) -> CellExtraction:
    """Stream a cell CSV and retain one summary per verified diagnostic cycle."""

    invalid = Counter()
    cycles: dict[int, _CycleAccumulator] = {}
    row_count = 0
    cell_id: str | None = None
    protocol_id: str | None = None
    seen_cell_ids: set[str] = set()
    seen_protocol_ids: set[str] = set()
    with source.open_csv() as (stream, digest):
        reader = csv.DictReader(stream)
        headers = list(reader.fieldnames or [])
        columns = resolve_columns(headers)
        missing = [key for key in REQUIRED_FIELDS if key not in columns]
        if missing:
            skipped_rows = sum(1 for _ in reader)
            raw_sha256 = digest.hexdigest()
            return CellExtraction(
                trajectory=None,
                raw_file=source.display_path,
                row_count=skipped_rows,
                raw_sha256=raw_sha256,
                warnings=[
                    f"Missing required raw columns {missing}; found headers {headers!r}."
                ],
            )
        for row in reader:
            row_count += 1
            row_cell_id = _canonical_id(_field_value(row, columns, "cell_id"))
            row_protocol_id = _canonical_id(_field_value(row, columns, "protocol_id"))
            if row_cell_id:
                seen_cell_ids.add(row_cell_id)
                cell_id = cell_id or row_cell_id
            if row_protocol_id:
                seen_protocol_ids.add(row_protocol_id)
                protocol_id = protocol_id or row_protocol_id

            cycle = _parse_cycle(_field_value(row, columns, "cycle_index"))
            if cycle is None:
                invalid["cycle_index"] += 1
                continue
            accumulator = cycles.setdefault(cycle, _CycleAccumulator())

            raw_capacity = _field_value(row, columns, "capacity_ah")
            if raw_capacity not in (None, ""):
                capacity = parse_number(raw_capacity)
                # The loose 2x nominal bound catches corrupted unit/column data
                # while allowing real cell-to-cell variation and initial peaks.
                if capacity == 0:
                    pass  # Zero is the normal cumulative-capacity reset/sentinel.
                elif _valid_positive(capacity, nominal_capacity_ah * 2.0):
                    accumulator.add_capacity(capacity)  # type: ignore[arg-type]
                else:
                    invalid["capacity_ah"] += 1

            raw_resistance = _field_value(row, columns, "internal_resistance_ohm")
            if raw_resistance not in (None, ""):
                resistance = parse_number(raw_resistance)
                if resistance == 0:
                    pass  # Zero commonly marks a row without an IR diagnostic.
                elif _valid_positive(resistance, 10.0):
                    accumulator.add_resistance(resistance)  # type: ignore[arg-type]
                else:
                    invalid["internal_resistance_ohm"] += 1

            raw_temperature = _field_value(row, columns, "temperature_c")
            if raw_temperature not in (None, ""):
                temperature = parse_number(raw_temperature)
                if temperature is not None and -50.0 <= temperature <= 120.0:
                    accumulator.add_temperature(temperature)
                else:
                    invalid["temperature_c"] += 1

        raw_sha256 = digest.hexdigest()

    if len(seen_cell_ids) > 1:
        invalid["conflicting_cell_ids"] += len(seen_cell_ids) - 1
    if len(seen_protocol_ids) > 1:
        invalid["conflicting_protocol_ids"] += len(seen_protocol_ids) - 1
    cell_id = cell_id or _canonical_id(source.stem)
    if cell_id is None:
        return CellExtraction(
            trajectory=None, raw_file=source.display_path, row_count=row_count,
            raw_sha256=raw_sha256, invalid_counts=dict(invalid),
            warnings=["Could not resolve a cell ID from the CSV rows or filename."],
        )

    observations: list[CellObservation] = []
    for cycle_index in sorted(cycles):
        if cycle_index % DIAGNOSTIC_CYCLE_STRIDE != DIAGNOSTIC_CYCLE_OFFSET:
            continue
        summary = cycles[cycle_index]
        if summary.capacity_ah is None:
            invalid["diagnostic_cycles_without_capacity"] += 1
            continue
        observations.append(
            CellObservation(
                cell_id=cell_id,
                protocol_id=protocol_id,
                phase=phase,  # type: ignore[arg-type]
                cycle_index=cycle_index,
                timestamp_s=None,
                capacity_ah=summary.capacity_ah,
                internal_resistance_ohm=summary.mean_resistance,
                temperature_c=summary.mean_temperature,
                voltage_v=None,
                current_a=None,
                source_dataset=DATASET_KEY,
            )
        )

    messages: list[str] = []
    if not headers:
        messages.append("CSV has no header row.")
    if "cell_id" not in columns:
        messages.append(f"Battery_ID alias absent; used filename-derived ID {cell_id!r}.")
    for optional_field in ("internal_resistance_ohm", "temperature_c"):
        if optional_field not in columns:
            messages.append(
                f"Optional {optional_field} raw column not found; canonical values are null."
            )
    if len(seen_cell_ids) > 1:
        messages.append(f"Conflicting Battery_ID values found: {sorted(seen_cell_ids)!r}.")
    if len(seen_protocol_ids) > 1:
        messages.append(f"Conflicting Protocol_ID values found: {sorted(seen_protocol_ids)!r}.")
    if "protocol_id" not in columns:
        messages.append("Protocol_ID alias absent; canonical protocol_id is null.")
    if not observations:
        messages.append("No valid diagnostic-cycle capacity observations were extracted.")
    for key, count in sorted(invalid.items()):
        messages.append(f"Ignored or flagged {count} invalid {key} value(s).")

    identity_conflict = len(seen_cell_ids) > 1 or len(seen_protocol_ids) > 1
    trajectory = None
    if observations and not identity_conflict:
        trajectory = CellTrajectory(
            cell_id=cell_id,
            protocol_id=protocol_id,
            nominal_capacity_ah=nominal_capacity_ah,
            observations=tuple(observations),
        )
    return CellExtraction(
        trajectory=trajectory,
        raw_file=source.display_path,
        row_count=row_count,
        raw_sha256=raw_sha256,
        invalid_counts=dict(sorted(invalid.items())),
        warnings=messages,
    )


@dataclass
class PreprocessingResult:
    trajectories: list[CellTrajectory]
    file_reports: list[dict[str, object]]
    excluded_cells: list[dict[str, str]]
    missing_expected_cell_files: list[str]
    total_raw_rows: int


def preprocess_dataset(
    raw_root: str | Path,
    *,
    phase: str = "second_life",
    nominal_capacity_ah: float = 2.4,
    progress: Callable[[int, int, str], None] | None = None,
) -> PreprocessingResult:
    if phase not in {"primary", "second_life"}:
        raise ValueError("phase must be 'primary' or 'second_life'")
    if not math.isfinite(nominal_capacity_ah) or nominal_capacity_ah <= 0:
        raise ValueError("nominal_capacity_ah must be a finite positive number")
    files = enumerate_raw_files(raw_root, phase)
    reports: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    extractions: list[CellExtraction] = []
    total_rows = 0
    for file_index, source in enumerate(files, start=1):
        if progress is not None:
            progress(file_index, len(files), source.display_path)
        result = extract_cell(
            source,
            phase=phase,
            nominal_capacity_ah=nominal_capacity_ah,
        )
        total_rows += result.row_count
        if result.trajectory is None:
            excluded.append({"file": result.raw_file, "reason": "; ".join(result.warnings)})
        extractions.append(result)
        reports.append(
            {
                "file": result.raw_file,
                "cell_id": result.trajectory.cell_id if result.trajectory else None,
                "rows": result.row_count,
                "observations": len(result.trajectory.observations) if result.trajectory else 0,
                "sha256_uncompressed_csv": result.raw_sha256,
                "invalid_counts": result.invalid_counts,
                "warnings": result.warnings,
            }
        )
    trajectory_file_indices: dict[str, list[int]] = {}
    for index, extraction in enumerate(extractions):
        if extraction.trajectory is not None:
            trajectory_file_indices.setdefault(extraction.trajectory.cell_id, []).append(index)
    duplicate_indices = {
        index
        for indices in trajectory_file_indices.values()
        if len(indices) > 1
        for index in indices
    }
    trajectories: list[CellTrajectory] = []
    for index, extraction in enumerate(extractions):
        if extraction.trajectory is None:
            continue
        if index in duplicate_indices:
            reason = (
                f"Cell ID {extraction.trajectory.cell_id!r} appears in multiple raw files; "
                "all matching files were excluded to avoid silently merging cells."
            )
            excluded.append({"file": extraction.raw_file, "reason": reason})
            reports[index]["warnings"].append(reason)  # type: ignore[union-attr]
            reports[index]["excluded_reason"] = reason
            continue
        trajectories.append(extraction.trajectory)
    trajectories.sort(key=lambda trajectory: _natural_text_key(trajectory.cell_id))
    return PreprocessingResult(
        trajectories=trajectories,
        file_reports=reports,
        excluded_cells=excluded,
        missing_expected_cell_files=expected_missing_cell_files(files),
        total_raw_rows=total_rows,
    )


def _natural_text_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value))

