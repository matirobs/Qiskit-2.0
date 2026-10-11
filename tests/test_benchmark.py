from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from repackq.benchmark import (
    _append_checkpoint,
    _load_checkpoint,
    load_benchmark_config,
    load_or_generate_pools,
    select_replay_trials,
    validate_benchmark_exports,
)


class BenchmarkConfigTests(unittest.TestCase):
    def test_fixed_task6_config_contains_twenty_seeds_and_qaoa_defaults(self) -> None:
        config = load_benchmark_config("configs/task6_benchmark.json")
        self.assertEqual(len(config.seeds), 20)
        self.assertEqual(config.candidate_sizes, (8,))
        self.assertEqual(config.pack_size_k, 4)
        self.assertEqual(config.horizon_cycles, 200)
        self.assertEqual(config.qaoa_shots, 1024)
        self.assertEqual(config.qaoa_reps, 1)

    def test_scientific_input_rejects_wrong_dataset_even_when_labeled_real(self) -> None:
        config = load_benchmark_config("configs/task6_benchmark.json")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(
                json.dumps({"data_classification": "derived-real", "source_dataset": "other"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Deep Sorting"):
                load_or_generate_pools(path, config)


class BenchmarkExportTests(unittest.TestCase):
    def test_selected_replay_trials_follow_seed_order_without_metric_selection(self) -> None:
        trials = [
            {"trial_id": f"n8-seed{seed}", "seed": seed, "candidate_count": 8}
            for seed in (37, 11, 23, 41)
        ]
        selected = select_replay_trials(trials, count=3)
        self.assertEqual([trial["seed"] for trial in selected], [11, 23, 37])

    def test_export_schema_accepts_predeclared_subset_and_rejects_provenance_mismatch(self) -> None:
        provenance = {"config_sha256": "config", "provenance_sha256": "source"}
        summary = {"schema_version": "1.0", "trial_count": 4, "provenance": provenance}
        selected = {
            "schema_version": "1.0",
            "provenance": provenance,
            "selection": {"mode": "predeclared_seed_subset"},
            "trials": [{"trial_id": f"n8-seed{seed}"} for seed in (11, 23, 37)],
        }
        validate_benchmark_exports(summary, selected)
        selected["provenance"] = {"config_sha256": "different"}
        with self.assertRaisesRegex(ValueError, "provenance"):
            validate_benchmark_exports(summary, selected)


class IncrementalCheckpointTests(unittest.TestCase):
    def test_checkpoint_is_single_line_jsonl_and_recovers_a_torn_final_record(self) -> None:
        header = {
            "record_type": "repackq_benchmark_checkpoint",
            "schema_version": "1.0",
            "config_sha256": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.jsonl"
            completed, attempted = _load_checkpoint(path, header, fresh=True)
            self.assertEqual(completed, {})
            self.assertFalse(attempted)
            trial = {"trial_id": "n8-seed11", "seed": 11}
            _append_checkpoint(path, trial)
            with path.open("ab") as target:
                target.write(b'{"trial":')
            loaded, attempted = _load_checkpoint(path, header, fresh=False)
            self.assertEqual(loaded, {"n8-seed11": trial})
            self.assertFalse(attempted)
            self.assertTrue(path.read_bytes().endswith(b"\n"))
            self.assertEqual(len(path.read_bytes().splitlines()), 2)

    def test_checkpoint_rejects_another_run_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.jsonl"
            _load_checkpoint(path, {"config_sha256": "first"}, fresh=True)
            with self.assertRaisesRegex(ValueError, "another config/input"):
                _load_checkpoint(path, {"config_sha256": "second"}, fresh=False)


if __name__ == "__main__":
    unittest.main()
