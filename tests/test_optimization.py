from __future__ import annotations

import itertools
import random
import unittest
from dataclasses import replace

from repackq.config import PV_TOU_MISSION
from repackq.models import CandidatePool, CellSnapshot, FutureTruth
from repackq.optimization import (
    build_optimization_instance,
    build_qubo,
    compatibility_greedy,
    exact_enumeration,
    qubo_to_ising,
    robust_scale,
    simulated_annealing,
    soh_sort,
    verify_ising_equivalence,
)


def make_pool(n: int = 8, *, seed: int = 19, predictions: list[float] | None = None) -> CandidatePool:
    rng = random.Random(seed)
    mission = PV_TOU_MISSION
    snapshots = []
    truths = []
    for index in range(n):
        capacity = 1.25 + 0.025 * index + rng.random() * 0.012
        predicted = predictions[index] if predictions is not None else capacity - 0.015 * (index % 3)
        cell_id = f"CELL-{index:02d}"
        snapshots.append(
            CellSnapshot(
                cell_id=cell_id,
                protocol_id=f"P-{index % 2}",
                cycle_index=10,
                capacity_ah=capacity,
                nominal_capacity_ah=2.4,
                soh=capacity / 2.4,
                internal_resistance_ohm=0.06 + 0.003 * index,
                temperature_c=25.0 + index * 0.4,
                recent_capacity_slope_ah_per_cycle=-0.0001 * (index + 1),
                predicted_capacity_ah=predicted,
                prediction_uncertainty_ah=0.003 + 0.001 * index,
                horizon_cycles=mission.horizon_cycles,
                source_dataset="synthetic_test",
            )
        )
        truths.append(
            FutureTruth(
                cell_id=cell_id,
                target_cycle_index=210,
                actual_capacity_ah=predicted - (index % 2) * 0.006,
                actual_internal_resistance_ohm=0.07 + 0.004 * index,
                nearest_cycle_distance=0,
            )
        )
    return CandidatePool(
        pool_id="unit-test-pool",
        decision_cycle=10,
        horizon_cycles=mission.horizon_cycles,
        candidate_ids=tuple(item.cell_id for item in snapshots),
        snapshots=tuple(snapshots),
        future_truth=tuple(truths),
        seed=seed,
    )


class NormalizationTests(unittest.TestCase):
    def test_robust_scaling_handles_iqr_fallback_constant_and_missing(self) -> None:
        robust = robust_scale("robust", [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(robust.method, "median_iqr")
        self.assertAlmostEqual(robust.scale or 0.0, 1.5)
        fallback = robust_scale("fallback", [0.0, 0.0, 0.0, 0.0, 3.0])
        self.assertEqual(fallback.method, "mean_std")
        constant = robust_scale("constant", [2.0, 2.0, 2.0])
        self.assertEqual(constant.method, "constant")
        self.assertEqual(constant.values, (0.0, 0.0, 0.0))
        missing = robust_scale("missing", [None, None])
        self.assertEqual(missing.method, "unavailable")
        self.assertEqual(missing.values, (None, None))

    def test_robust_scaling_rejects_nonfinite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            robust_scale("broken", [1.0, float("nan")])


class ObjectiveAndQuboTests(unittest.TestCase):
    def test_modes_report_component_breakdown_and_current_only_ignores_forecasts(self) -> None:
        pool = make_pool()
        current = build_optimization_instance(pool, mission=PV_TOU_MISSION, objective_mode="current_only")
        aware = build_optimization_instance(pool, mission=PV_TOU_MISSION, objective_mode="trajectory_aware")
        changed = make_pool(predictions=[4.0 + index for index in range(8)])
        current_changed = build_optimization_instance(
            changed, mission=PV_TOU_MISSION, objective_mode="current_only"
        )
        selected = [0, 2, 4, 6]
        current_breakdown = current.breakdown_for_indices(selected)
        aware_breakdown = aware.breakdown_for_indices(selected)
        self.assertAlmostEqual(
            current_breakdown.total,
            current_changed.breakdown_for_indices(selected).total,
        )
        self.assertNotIn("future_capacity", current.normalizations)
        self.assertNotIn("uncertainty", current.normalizations)
        self.assertEqual(current_breakdown.future_mismatch, 0.0)
        self.assertEqual(current_breakdown.uncertainty_penalty, 0.0)
        self.assertFalse(hasattr(current, "future_truth"))
        self.assertAlmostEqual(
            aware_breakdown.total,
            sum(aware_breakdown.to_dict()[name] for name in (
                "capacity_mismatch", "resistance_mismatch", "future_mismatch",
                "temperature_mismatch", "health_reward", "uncertainty_penalty",
            )),
        )

    def test_unavailable_measurements_omit_only_the_affected_pair_terms(self) -> None:
        pool = make_pool()
        snapshots = list(pool.snapshots)
        snapshots[0] = replace(snapshots[0], internal_resistance_ohm=None, temperature_c=None)
        pool = replace(pool, snapshots=tuple(snapshots))
        mission = replace(PV_TOU_MISSION, temperature_weight=0.15)
        instance = build_optimization_instance(pool, mission=mission)
        self.assertEqual(instance.pairwise_components["resistance_mismatch"][0][1], 0.0)
        self.assertGreater(instance.pairwise_components["resistance_mismatch"][1][2], 0.0)
        self.assertEqual(instance.pairwise_components["temperature_mismatch"][0][1], 0.0)
        self.assertGreater(instance.pairwise_components["temperature_mismatch"][1][2], 0.0)

    def test_qubo_expansion_and_penalty_are_exact(self) -> None:
        instance = build_optimization_instance(
            make_pool(6), mission=PV_TOU_MISSION, objective_mode="trajectory_aware"
        )
        model = build_qubo(instance)
        self.assertLessEqual(model.calibration_doublings, 5)
        for bits in itertools.product((0, 1), repeat=instance.n):
            selected = [index for index, bit in enumerate(bits) if bit]
            expected = instance.objective_for_indices(selected)
            expected += model.cardinality_penalty * (sum(bits) - instance.pack_size_k) ** 2
            self.assertAlmostEqual(model.energy(bits), expected, places=10)
            self.assertAlmostEqual(model.breakdown(instance, bits).total, model.energy(bits), places=10)
            self.assertAlmostEqual(model.physical_energy(bits), instance.objective_for_bits(bits), places=10)
        minimum = min(model.energy(bits) for bits in itertools.product((0, 1), repeat=instance.n))
        minimizers = [
            bits for bits in itertools.product((0, 1), repeat=instance.n)
            if abs(model.energy(bits) - minimum) < 1e-12
        ]
        self.assertTrue(minimizers)
        self.assertTrue(all(sum(bits) == instance.pack_size_k for bits in minimizers))

    def test_qubo_to_ising_equivalence_for_random_small_instances(self) -> None:
        for n in range(2, 9):
            pool = make_pool(n, seed=100 + n)
            mission = replace(PV_TOU_MISSION, pack_size_k=min(4, n))
            instance = build_optimization_instance(
                pool, mission=mission, objective_mode="trajectory_aware"
            )
            model = build_qubo(instance)
            self.assertTrue(verify_ising_equivalence(model))
            ising = qubo_to_ising(model)
            for bits in itertools.product((0, 1), repeat=n):
                self.assertAlmostEqual(model.energy(bits), ising.energy(bits), places=9)

    def test_exact_solver_matches_exhaustive_known_objective_and_shared_schema(self) -> None:
        pool = make_pool(8)
        instance = build_optimization_instance(
            pool, mission=PV_TOU_MISSION, objective_mode="trajectory_aware"
        )
        result = exact_enumeration(instance, future_truth=pool.future_truth)
        all_scores = [
            (instance.objective_for_indices(indices), indices)
            for indices in itertools.combinations(range(8), 4)
        ]
        expected_score = min(score for score, _ in all_scores)
        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.objective_value, expected_score)
        self.assertEqual(result.metadata["evaluated_subsets"], 70)
        self.assertTrue(result.metadata["qubo_global_minimum_feasible"])
        self.assertIsNotNone(result.observed_pack_divergence)
        self.assertEqual(len(result.selected_cell_ids), 4)


class BaselineTests(unittest.TestCase):
    def test_all_baselines_select_k_and_annealing_preserves_cardinality(self) -> None:
        pool = make_pool()
        instance = build_optimization_instance(
            pool, mission=PV_TOU_MISSION, objective_mode="trajectory_aware"
        )
        results = [
            soh_sort(instance, future_truth=pool.future_truth),
            compatibility_greedy(instance, future_truth=pool.future_truth),
            simulated_annealing(
                instance,
                seed=123,
                steps=250,
                future_truth=pool.future_truth,
                record_cardinality_trace=True,
            ),
        ]
        for result in results:
            self.assertTrue(result.feasible)
            self.assertEqual(len(result.selected_indices), instance.pack_size_k)
            self.assertEqual(result.metadata["objective_mode"], "trajectory_aware")
        trace = results[-1].metadata["cardinality_trace"]
        self.assertEqual(len(trace), 251)
        self.assertTrue(all(size == instance.pack_size_k for size in trace))

    def test_annealing_and_greedy_are_deterministic(self) -> None:
        pool = make_pool()
        instance = build_optimization_instance(pool, mission=PV_TOU_MISSION)
        left = simulated_annealing(instance, seed=42, steps=500)
        right = simulated_annealing(instance, seed=42, steps=500)
        self.assertEqual(left.selected_indices, right.selected_indices)
        self.assertEqual(left.objective_value, right.objective_value)
        self.assertEqual(
            compatibility_greedy(instance).selected_indices,
            compatibility_greedy(instance).selected_indices,
        )


if __name__ == "__main__":
    unittest.main()
