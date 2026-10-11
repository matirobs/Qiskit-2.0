"""Check group scores, solver selections, and the separation of future measurements."""
from dataclasses import replace
from itertools import combinations
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repackq.classical import exact_search, greedy_selection, healthiest_selection, simulated_annealing
from repackq.classical.compare import compare
from repackq.classical.metrics import evaluate_selection
from repackq.classical.trials import history_pool, synthetic_pool
from repackq.optimization import CellSnapshot, MissionWeights, build_instance
from repackq.optimization.normalize import normalize


class NormalizationTests(unittest.TestCase):
    def test_constant_robust_and_outlier_fallback(self):
        constant = normalize([2, 2, 2])
        self.assertEqual(constant.values, (0, 0, 0))
        self.assertFalse(constant.discriminates)
        robust = normalize([1, 2, 3, 4, 5])
        self.assertEqual(robust.values, (-1, -.5, 0, .5, 1))
        fallback = normalize([0, 0, 0, 0, 10])
        self.assertEqual(fallback.method, "standard_score")
        self.assertAlmostEqual(sum(fallback.values), 0)
        for actual, expected in zip(normalize([.1, .2, .3], unit_interval=True).values, (0, .5, 1)):
            self.assertAlmostEqual(actual, expected)
        with self.assertRaises(ValueError): normalize([math.nan])


# compare the expanded binary objective with direct group scores
class ObjectiveTests(unittest.TestCase):
    def test_current_only_ignores_future_fields_completely(self):
        cells, _, _ = synthetic_pool()
        before = build_instance(cells, mode="current_only")
        changed = [replace(c, predicted_capacity_ah=math.nan, prediction_uncertainty_ah=math.inf) for c in cells]
        after = build_instance(changed, mode="current_only")
        self.assertEqual(before.pair, after.pair)
        self.assertEqual(before.unary, after.unary)
        self.assertEqual(before.metadata, after.metadata)
        with self.assertRaises(ValueError): build_instance(changed)

    def test_missing_features_disabled_and_weights_renormalized(self):
        cells, _, _ = synthetic_pool()
        cells = [replace(cells[0], internal_resistance_ohm=None), *cells[1:]]
        instance = build_instance(cells)
        self.assertEqual(instance.metadata["effective_weights"]["resistance"], 0)
        self.assertAlmostEqual(sum(instance.metadata["effective_weights"].values()), 1)
        self.assertIn("resistance", instance.metadata["disabled_features"])
        self.assertEqual(instance.components["resistance_mismatch"][0][1], 0)
        missing_future = [replace(cells[0], predicted_capacity_ah=None), *cells[1:]]
        with self.assertRaises(ValueError): build_instance(missing_future)

    def test_breakdown_and_binary_expansion_for_every_state(self):
        rng = random.Random(17)
        for size in range(2, 9):
            cells = [CellSnapshot(str(i), 1.8 + rng.random() * .2,
                                  predicted_capacity_ah=1.3 + rng.random() * .3,
                                  prediction_uncertainty_ah=rng.random() * .1,
                                  internal_resistance_ohm=.03 + rng.random() * .01) for i in range(size)]
            instance = build_instance(cells, max(1, size // 2))
            qubo = instance.qubo()
            minima = []
            for mask in range(2 ** size):
                bits = [(mask >> i) & 1 for i in range(size)]
                selected = [i for i, bit in enumerate(bits) if bit]
                expected = instance.energy(selected) + qubo["cardinality_penalty"] * (len(selected) - instance.pack_size) ** 2
                actual = qubo["constant"] + sum(c * b for c, b in zip(qubo["linear"], bits))
                actual += sum(v * bits[i] * bits[j] for i, j, v in qubo["quadratic"])
                self.assertAlmostEqual(actual, expected, places=10)
                self.assertAlmostEqual(instance.breakdown(selected)["total"], instance.energy(selected))
                minima.append((actual, len(selected)))
            best = min(energy for energy, _ in minima)
            self.assertTrue(all(k == instance.pack_size for energy, k in minima if abs(energy - best) < 1e-9))

    def test_penalty_increases_when_initial_value_is_insufficient(self):
        cells = [CellSnapshot(str(i), 2, predicted_capacity_ah=1.8) for i in range(4)]
        instance = build_instance(cells, 2, weights=MissionWeights(0, 0, 0, 1, 0, 0))
        qubo = instance.qubo(penalty_multiplier=.1)
        self.assertGreater(qubo["calibration_doublings"], 0)
        with self.assertRaisesRegex(ValueError, "calibration"):
            instance.qubo(max_states=8)

    def test_rejects_invalid_pools_and_selections(self):
        cells, _, _ = synthetic_pool()
        for size in (0, 9, True):
            with self.assertRaises(ValueError): build_instance(cells, size)
        with self.assertRaises(ValueError): build_instance([cells[0], cells[0]], 1)
        with self.assertRaises(ValueError): build_instance([replace(cells[0], capacity_ah=math.nan)], 1)
        with self.assertRaises(ValueError): build_instance(cells, weights=MissionWeights(future=-1))
        instance = build_instance(cells)
        for selected in ([0, 0], [-1], [8], [True]):
            with self.assertRaises(ValueError): instance.energy(selected)


class SolverTests(unittest.TestCase):
    def setUp(self):
        self.cells, _, _ = synthetic_pool()
        self.instance = build_instance(self.cells)

    def test_exact_finds_independently_known_optimum_and_counts(self):
        # Only future mismatch matters: A/C/D are equal; B is incompatible.
        cells = [CellSnapshot(name, 2, predicted_capacity_ah=future)
                 for name, future in (("A", 1.8), ("B", 1.2), ("C", 1.8), ("D", 1.8))]
        instance = build_instance(cells, 3, weights=MissionWeights(0, 0, 1, 0, 0, 0))
        result = exact_search(instance)
        self.assertEqual(result.selected_cell_ids, ("A", "C", "D"))
        self.assertEqual(result.objective_value, 0)
        self.assertEqual(result.metadata["evaluated_subsets"], 4)
        with self.assertRaises(ValueError): exact_search(instance, max_subsets=3)

    def test_baselines_return_valid_groups_and_never_beat_oracle(self):
        optimum = exact_search(self.instance)
        self.assertEqual(optimum.metadata["evaluated_subsets"], 70)
        for method in (healthiest_selection, greedy_selection, simulated_annealing):
            result = method(self.instance)
            self.assertEqual(len(set(result.selected_indices)), 4)
            self.assertGreaterEqual(result.objective_value + 1e-12, optimum.objective_value)
            self.assertAlmostEqual(result.objective_value, result.objective_breakdown["total"])
        expected = sorted(self.cells, key=lambda c: -c.capacity_ah)[:4]
        self.assertEqual(set(healthiest_selection(self.instance).selected_cell_ids), {c.cell_id for c in expected})

    def test_greedy_tries_all_seeds(self):
        result = greedy_selection(self.instance)
        seeded_groups = []
        for start in range(8):
            selected = [start]
            while len(selected) < 4:
                remaining = [i for i in range(8) if i not in selected]
                selected.append(min(remaining, key=lambda i: (
                    self.instance.energy([*selected, i]), self.cells[i].cell_id)))
            seeded_groups.append(selected)
        self.assertAlmostEqual(result.objective_value, min(self.instance.energy(g) for g in seeded_groups))
        self.assertEqual(result.metadata["starting_cells"], 8)

    def test_annealing_preserves_size_every_move_and_returns_best_seen(self):
        original = type(self.instance).energy
        seen = []
        def checked(instance, selected):
            self.assertEqual(len(selected), instance.pack_size)
            self.assertEqual(len(set(selected)), instance.pack_size)
            value = original(instance, selected)
            seen.append(value)
            return value
        with patch.object(type(self.instance), "energy", checked):
            result = simulated_annealing(self.instance, seed=37, steps=200, restarts=3)
        self.assertAlmostEqual(result.objective_value, min(seen))
        self.assertEqual(result.metadata["proposed_moves"], 600)
        again = simulated_annealing(self.instance, seed=37, steps=200, restarts=3)
        self.assertEqual(result.selected_indices, again.selected_indices)
        self.assertEqual(result.metadata, again.metadata)

    def test_ties_and_singleton_or_full_pool(self):
        equal = [CellSnapshot(name, 2, predicted_capacity_ah=1.8) for name in ("D", "B", "A", "C")]
        instance = build_instance(equal, 2)
        optimum = exact_search(instance, max_ties=2)
        self.assertEqual(set(optimum.selected_cell_ids), {"A", "B"})
        self.assertEqual(optimum.metadata["tied_optima_count"], 6)
        self.assertTrue(optimum.metadata["ties_truncated"])
        for wanted in (1, 4):
            instance = build_instance(equal, wanted)
            for method in (healthiest_selection, greedy_selection, exact_search, simulated_annealing):
                self.assertEqual(len(method(instance).selected_indices), wanted)

    def test_metrics_use_population_spread_and_separate_future_truth(self):
        truth = {cell.cell_id: {"actual_capacity_ah": 1 + .1 * i} for i, cell in enumerate(self.cells)}
        result = exact_search(self.instance)
        metrics = evaluate_selection(self.instance, result, future_truth=truth, optimum=result)
        actual = [truth[name]["actual_capacity_ah"] for name in result.selected_cell_ids]
        self.assertEqual(metrics["observed_usable_capacity_ah"], min(actual))
        self.assertAlmostEqual(metrics["observed_capacity_spread_ah"], max(actual) - min(actual))
        self.assertEqual(metrics["objective_gap_abs"], 0)
        changed = {name: {"actual_capacity_ah": v["actual_capacity_ah"] * .8} for name, v in truth.items()}
        other = compare(self.cells, future_truth=changed, annealing_steps=20)
        first = compare(self.cells, future_truth=truth, annealing_steps=20)
        self.assertEqual([r["selected_indices"] for r in first["results"]],
                         [r["selected_indices"] for r in other["results"]])
        self.assertNotEqual(first["results"][-1]["observed_usable_capacity_ah"],
                            other["results"][-1]["observed_usable_capacity_ah"])
        with self.assertRaises(ValueError): evaluate_selection(self.instance, result, future_truth={})


class HistoryIntegrationTests(unittest.TestCase):
    def test_all_cells_scope_samples_training_validation_and_test_without_future_inputs(self):
        class FakeModel:
            artifact = {"cell_splits": {"train": [str(i) for i in range(60)],
                         "validation": [str(i) for i in range(60, 72)],
                         "test": [str(i) for i in range(72, 86)]}}
            def predict(self, primary, second, **kwargs):
                if second:
                    raise AssertionError("Future observations reached a first-life-only prediction")
                return {"current_capacity_ah": primary[-1]["capacity_ah"],
                        "predicted_capacity_ah": 1.7, "prediction_uncertainty_ah": .06}
        data = {"cells": [{"cell_id": str(i),
                          "primary": [{"cycle": c, "capacity_ah": 2} for c in range(4)],
                          "second_life": [{"cycle": 200, "capacity_ah": 1.6}]}
                         for i in range(86)]}
        cells, _, metadata = history_pool(data, FakeModel(), partition="all", candidates=86)
        self.assertEqual(len(cells), 86)
        self.assertEqual(metadata["eligible_cells"], 86)
        self.assertEqual(metadata["partition_cells"], 86)
        self.assertEqual(metadata["candidate_partitions"], {"train": 60, "validation": 12, "test": 14})
        self.assertFalse(metadata["held_out_from_predictor"])
        before, truth, _ = history_pool(data, FakeModel(), partition="all")
        other_seed, _, _ = history_pool(data, FakeModel(), partition="all", seed=42)
        self.assertNotEqual(before, other_seed)
        for cell in data["cells"]:
            cell["second_life"][0]["capacity_ah"] = 1.2
        after, changed_truth, _ = history_pool(data, FakeModel(), partition="all")
        self.assertEqual(before, after)
        self.assertNotEqual(truth, changed_truth)
        held_out, _, test_metadata = history_pool(data, FakeModel())
        self.assertTrue(all(int(c.cell_id) >= 72 for c in held_out))
        self.assertEqual(test_metadata["partition_cells"], 14)
        self.assertEqual(test_metadata["dataset_cells"], 86)

    def test_real_adapter_withholds_future_and_excludes_training_cells(self):
        import copy
        received = []
        class FakeModel:
            artifact = {"cell_splits": {"test": [str(i) for i in range(8)]}}
            def predict(self, primary, second, **kwargs):
                received.append(copy.deepcopy(second))
                self_cutoff = kwargs["cutoff"]
                if any(p["cycle"] > self_cutoff for p in second):
                    raise AssertionError("Future reached predictor")
                return {"current_capacity_ah": primary[-1]["capacity_ah"],
                        "predicted_capacity_ah": primary[-1]["capacity_ah"] * .9,
                        "prediction_uncertainty_ah": .06}
        def point(cycle, capacity):
            return {"cycle": cycle, "capacity_ah": capacity, "resistance_ohm": .04, "temperature_c": 25}
        data = {"cells": [{"cell_id": str(i), "primary": [point(c, 2 - i * .001) for c in range(4)],
                           "second_life": [point(c, 1.9 - c * .001) for c in (1, 20, 100, 200)]}
                          for i in range(9)]}
        # Plain models must also work with the original predictor's signature.
        from repackq.api import predict_snapshot
        def original_boundary(model, *, cell_id, primary_history, observed_second_life, cutoff, horizon):
            return predict_snapshot(model, cell_id=cell_id, primary_history=primary_history,
                                    observed_second_life=observed_second_life, cutoff=cutoff, horizon=horizon)
        with patch("repackq.classical.trials.predict_snapshot", original_boundary):
            before, truths, metadata = history_pool(data, FakeModel())
        self.assertNotIn("8", metadata["candidate_ids"])
        self.assertEqual(received, [[]] * 8)
        changed = copy.deepcopy(data)
        for cell in changed["cells"]:
            for p in cell["second_life"]: p["capacity_ah"] *= .8
        after, other_truths, _ = history_pool(changed, FakeModel())
        self.assertEqual(before, after)
        self.assertNotEqual(truths, other_truths)
        with self.assertRaises(ValueError): history_pool(data, FakeModel(), candidates=9)

    def test_cli_runs_without_training_dependencies_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            command = [sys.executable, "-S", "-m", "repackq.classical.compare", "--synthetic",
                       "--annealing-steps", "30", "--export-qubo", "--output", str(output)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            report = json.loads(original)
            self.assertEqual(report["provenance"]["source"], "synthetic-fixture")
            self.assertEqual(len(report["trials"][0]["comparisons"]), 2)
            self.assertIsNone(report["trials"][0]["revealed_future_truth"])
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("Refusing to overwrite", second.stderr)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
