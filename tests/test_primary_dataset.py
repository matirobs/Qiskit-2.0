from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from repackq.data.adapters.deep_sorting import (
    enumerate_raw_files,
    extract_cell,
    parse_number,
    preprocess_dataset,
    resolve_columns,
)
from repackq.data.inspection import inspect_dataset
from repackq.data.serialization import (
    canonical_json_bytes,
    load_trajectory_dataset,
    trajectories_to_dict,
    trajectories_from_dict,
)
from src.scripts.inspect_dataset import main as inspect_cli_main


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "raw"


class DeepSortingAdapterTests(unittest.TestCase):
    def test_alias_resolution_and_robust_number_parsing(self) -> None:
        columns = resolve_columns(
            [
                "Battery_ID", "Protocol_ID", "Cycle_Index", "Step_Index",
                "Discharge_Capacity(Ah)", "Internal_Resistance(Ohm)",
                "Aux_Temperature_1(C)",
            ]
        )
        self.assertEqual(columns["cell_id"], "Battery_ID")
        self.assertEqual(columns["protocol_id"], "Protocol_ID")
        self.assertEqual(columns["capacity_ah"], "Discharge_Capacity(Ah)")
        self.assertEqual(columns["temperature_c"], "Aux_Temperature_1(C)")
        self.assertEqual(parse_number("1,91"), 1.91)
        self.assertEqual(parse_number("1,234.5"), 1234.5)
        self.assertIsNone(parse_number("NaN"))
        self.assertIsNone(parse_number("Infinity"))

    def test_extracts_only_diagnostic_cycles_and_preserves_ids(self) -> None:
        source = next(
            item for item in enumerate_raw_files(FIXTURE_ROOT, "second_life")
            if item.stem == "1"
        )
        result = extract_cell(source, phase="second_life", nominal_capacity_ah=2.4)
        self.assertIsNotNone(result.trajectory)
        assert result.trajectory is not None
        self.assertEqual(result.trajectory.cell_id, "Cell-01")
        self.assertEqual(result.trajectory.protocol_id, "P-04")
        observations = result.trajectory.observations
        self.assertEqual([item.cycle_index for item in observations], [1, 6, 11])
        self.assertEqual(observations[0].capacity_ah, 1.90)
        self.assertEqual(observations[0].internal_resistance_ohm, 0.041)
        self.assertEqual(observations[0].temperature_c, 25.3)
        self.assertTrue(result.raw_sha256)
        self.assertEqual(result.row_count, 5)

    def test_alternate_aliases_and_invalid_values_are_reported(self) -> None:
        files = enumerate_raw_files(FIXTURE_ROOT, "second_life")
        alternate = next(item for item in files if item.stem == "3")
        parsed = extract_cell(alternate, phase="second_life", nominal_capacity_ah=2.4)
        assert parsed.trajectory is not None
        self.assertEqual(parsed.trajectory.cell_id, "Cell-X")
        self.assertEqual(parsed.trajectory.protocol_id, "Route-B")
        self.assertEqual([item.cycle_index for item in parsed.trajectory.observations], [1, 6])
        self.assertEqual(parsed.trajectory.observations[0].capacity_ah, 1.91)

        invalid = next(item for item in files if item.stem == "4")
        rejected = extract_cell(invalid, phase="second_life", nominal_capacity_ah=2.4)
        self.assertIsNone(rejected.trajectory)
        self.assertIn("capacity_ah", rejected.invalid_counts)
        self.assertIn("temperature_c", rejected.invalid_counts)
        self.assertTrue(any("invalid" in warning for warning in rejected.warnings))

    def test_inspection_reports_schema_ranges_steps_and_missing_files(self) -> None:
        raw_file = FIXTURE_ROOT / "Second_life_phase" / "1.csv"
        before = hashlib.sha256(raw_file.read_bytes()).hexdigest()
        report = inspect_dataset(str(FIXTURE_ROOT), phase="second_life")
        after = hashlib.sha256(raw_file.read_bytes()).hexdigest()
        self.assertEqual(before, after, "inspection must not modify raw CSV files")
        self.assertEqual(report["file_count"], 3)
        self.assertIn("Battery_ID", report["columns_union"])
        self.assertIn("Protocol_ID", report["columns_union"])
        self.assertEqual(report["likely_fields"]["cycle_index"], "Cycle_Index")
        self.assertEqual(
            report["representative_files"][0]["unique_step_indices"], ["14", "15"]
        )
        self.assertAlmostEqual(
            report["valid_numeric_ranges"]["capacity_ah"]["max"], 1.91
        )
        self.assertIn("2", report["expected_missing_cell_file_ids"])
        self.assertNotIn("61", report["expected_missing_cell_file_ids"])
        self.assertEqual(report["unavailable_cell_file_ids"], ["61", "62"])

    def test_inspection_cli_summary_is_compact_json(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = inspect_cli_main(
                ["--raw-root", str(FIXTURE_ROOT), "--phase", "second_life", "--summary"]
            )
        report = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertNotIn("files", report)
        self.assertIn("valid_numeric_ranges", report)
        self.assertIn("representative_files", report)

    def test_preprocessor_reads_a_zip_without_extracting_and_hashes_content(self) -> None:
        fixture = FIXTURE_ROOT / "Second_life_phase" / "1.csv"
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "Second_life_phase.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(fixture, arcname="1.csv")
            sources = enumerate_raw_files(archive_path, "second_life")
            result = preprocess_dataset(archive_path)
            self.assertEqual(len(sources), 1)
            self.assertEqual(len(result.trajectories), 1)
            digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
            self.assertEqual(result.file_reports[0]["sha256_uncompressed_csv"], digest)
            self.assertEqual(result.file_reports[0]["file"], "Second_life_phase.zip!/1.csv")
            self.assertNotIn(temporary, result.file_reports[0]["file"])
            self.assertEqual(result.trajectories[0].cell_id, "Cell-01")

    def test_duplicate_battery_ids_are_excluded_instead_of_silently_merged(self) -> None:
        fixture = FIXTURE_ROOT / "Second_life_phase" / "1.csv"
        with tempfile.TemporaryDirectory() as temporary:
            phase_root = Path(temporary) / "Second_life_phase"
            phase_root.mkdir()
            shutil.copyfile(fixture, phase_root / "1.csv")
            shutil.copyfile(fixture, phase_root / "2.csv")
            result = preprocess_dataset(phase_root)
        self.assertEqual(result.trajectories, [])
        self.assertEqual(len(result.excluded_cells), 2)
        self.assertTrue(all("multiple raw files" in item["reason"] for item in result.excluded_cells))

    def test_json_serialization_is_stable_and_explicitly_classified(self) -> None:
        result = preprocess_dataset(FIXTURE_ROOT)
        payload = trajectories_to_dict(
            result.trajectories,
            phase="second_life",
            nominal_capacity_ah=2.4,
        )
        first = canonical_json_bytes(payload)
        second = canonical_json_bytes(
            trajectories_to_dict(
                result.trajectories,
                phase="second_life",
                nominal_capacity_ah=2.4,
            )
        )
        self.assertEqual(first, second)
        decoded = json.loads(first)
        self.assertEqual(decoded["data_classification"], "derived-real")
        self.assertEqual(len(decoded["cells"]), 2)
        self.assertEqual(decoded["schema_version"], "1.0")

    def test_synthetic_runtime_example_is_labeled_and_uses_canonical_fields(self) -> None:
        path = Path(__file__).parents[1] / "data" / "fixtures" / "synthetic_demo.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["data_classification"], "synthetic-fixture")
        self.assertEqual(payload["source_dataset"], "synthetic_fixture")
        self.assertEqual(len(payload["cells"]), 8)
        self.assertTrue(all(len(cell["observations"]) == 9 for cell in payload["cells"]))
        self.assertTrue(
            all(
                observation["source_dataset"] == "synthetic_fixture"
                for cell in payload["cells"]
                for observation in cell["observations"]
            )
        )
        self.assertTrue(
            all(
                observation["temperature_c"] is None
                and observation["internal_resistance_ohm"] is None
                for cell in payload["cells"]
                for observation in cell["observations"]
            )
        )
        loaded_payload, trajectories = load_trajectory_dataset(path)
        self.assertEqual(loaded_payload["data_classification"], "synthetic-fixture")
        self.assertEqual(len(trajectories), 8)
        self.assertEqual(trajectories[0].observations[0].cycle_index, 1)

    def test_loader_rejects_incomplete_or_unlabeled_payloads(self) -> None:
        with self.assertRaisesRegex(ValueError, "data_classification"):
            trajectories_from_dict({"schema_version": "1.0", "cells": []})
        with self.assertRaisesRegex(ValueError, "schema version"):
            trajectories_from_dict({"schema_version": "99", "cells": []})


if __name__ == "__main__":
    unittest.main()

