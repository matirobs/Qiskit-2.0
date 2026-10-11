"""Stable JSON encoding and safe writing for compact dataset assets."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from repackq.models import CellObservation, CellTrajectory


TRAJECTORY_SCHEMA_VERSION = "1.0"


def trajectories_to_dict(
    trajectories: list[CellTrajectory] | tuple[CellTrajectory, ...],
    *,
    phase: str,
    nominal_capacity_ah: float,
    data_classification: str = "derived-real",
) -> dict[str, Any]:
    """Return a deterministic root object around canonical cell trajectories."""

    if data_classification not in {"real", "derived-real", "synthetic-fixture"}:
        raise ValueError("unsupported data_classification")
    if phase not in {"primary", "second_life", "unknown"}:
        raise ValueError("unsupported phase")
    if not math.isfinite(nominal_capacity_ah) or nominal_capacity_ah <= 0:
        raise ValueError("nominal_capacity_ah must be finite and positive")
    ordered = sorted(trajectories, key=lambda item: item.cell_id)
    return {
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "source_dataset": (
            "synthetic_fixture"
            if data_classification == "synthetic-fixture"
            else "deep_sorting_reused_batteries"
        ),
        "data_classification": data_classification,
        "phase": phase,
        "nominal_capacity_ah": nominal_capacity_ah,
        "cells": [trajectory.to_dict() for trajectory in ordered],
    }


def _decode_observation(value: Any) -> CellObservation:
    if not isinstance(value, dict):
        raise ValueError("each trajectory observation must be a JSON object")
    required = {
        "cell_id", "protocol_id", "phase", "cycle_index", "timestamp_s",
        "capacity_ah", "internal_resistance_ohm", "temperature_c",
        "voltage_v", "current_a", "source_dataset",
    }
    missing = required - value.keys()
    if missing:
        raise ValueError(f"trajectory observation is missing fields: {sorted(missing)}")
    if not isinstance(value["cell_id"], str) or not isinstance(value["source_dataset"], str):
        raise ValueError("observation cell_id and source_dataset must be strings")
    if not isinstance(value["phase"], str):
        raise ValueError("observation phase must be a string")
    if value["protocol_id"] is not None and not isinstance(value["protocol_id"], str):
        raise ValueError("observation protocol_id must be a string or null")
    if isinstance(value["cycle_index"], bool) or not isinstance(value["cycle_index"], int):
        raise ValueError("observation cycle_index must be an integer")
    for field in (
        "timestamp_s", "capacity_ah", "internal_resistance_ohm", "temperature_c",
        "voltage_v", "current_a",
    ):
        item = value[field]
        if item is not None and (isinstance(item, bool) or not isinstance(item, (int, float))):
            raise ValueError(f"observation {field} must be a number or null")
    return CellObservation(
        cell_id=str(value["cell_id"]),
        protocol_id=value["protocol_id"],
        phase=value["phase"],
        cycle_index=value["cycle_index"],
        timestamp_s=value["timestamp_s"],
        capacity_ah=value["capacity_ah"],
        internal_resistance_ohm=value["internal_resistance_ohm"],
        temperature_c=value["temperature_c"],
        voltage_v=value["voltage_v"],
        current_a=value["current_a"],
        source_dataset=str(value["source_dataset"]),
    )


def _decode_trajectory(value: Any) -> CellTrajectory:
    if not isinstance(value, dict):
        raise ValueError("each cell trajectory must be a JSON object")
    required = {"cell_id", "protocol_id", "nominal_capacity_ah", "observations"}
    missing = required - value.keys()
    if missing:
        raise ValueError(f"cell trajectory is missing fields: {sorted(missing)}")
    if not isinstance(value["observations"], list):
        raise ValueError("trajectory observations must be a JSON array")
    if not isinstance(value["cell_id"], str):
        raise ValueError("trajectory cell_id must be a string")
    if value["protocol_id"] is not None and not isinstance(value["protocol_id"], str):
        raise ValueError("trajectory protocol_id must be a string or null")
    nominal_capacity = value["nominal_capacity_ah"]
    if isinstance(nominal_capacity, bool) or not isinstance(nominal_capacity, (int, float)):
        raise ValueError("trajectory nominal_capacity_ah must be numeric")
    return CellTrajectory(
        cell_id=str(value["cell_id"]),
        protocol_id=value["protocol_id"],
        nominal_capacity_ah=nominal_capacity,
        observations=tuple(_decode_observation(item) for item in value["observations"]),
    )


def trajectories_from_dict(payload: dict[str, Any]) -> list[CellTrajectory]:
    """Validate a serialized trajectory dataset and rebuild canonical models."""

    if payload.get("schema_version") != TRAJECTORY_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported trajectory schema version: {payload.get('schema_version')!r}"
        )
    if payload.get("data_classification") not in {
        "real", "derived-real", "synthetic-fixture",
    }:
        raise ValueError("trajectory dataset has an unknown data_classification")
    expected_source = (
        "synthetic_fixture"
        if payload["data_classification"] == "synthetic-fixture"
        else "deep_sorting_reused_batteries"
    )
    if payload.get("source_dataset") != expected_source:
        raise ValueError("trajectory dataset source_dataset conflicts with its classification")
    if payload.get("phase") not in {"primary", "second_life", "unknown"}:
        raise ValueError("trajectory dataset has an unsupported phase")
    nominal_capacity = payload.get("nominal_capacity_ah")
    if (
        isinstance(nominal_capacity, bool)
        or not isinstance(nominal_capacity, (int, float))
        or not math.isfinite(nominal_capacity)
        or nominal_capacity <= 0
    ):
        raise ValueError("trajectory dataset nominal_capacity_ah must be finite and positive")
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise ValueError("trajectory dataset 'cells' must be a JSON array")
    return [_decode_trajectory(cell) for cell in cells]


def load_trajectory_dataset(path: str | Path) -> tuple[dict[str, Any], list[CellTrajectory]]:
    """Load root metadata plus validated canonical trajectories from JSON."""

    with Path(path).open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("trajectory dataset root must be a JSON object")
    return payload, trajectories_from_dict(payload)


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON with stable key order and reject non-finite float values."""

    text = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    )
    return (text + "\n").encode("utf-8")


def write_json_atomic(path: str | Path, value: Any) -> None:
    """Write one JSON file through a temporary sibling then atomically replace."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        raise

