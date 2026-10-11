from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from repackq.config import FREQUENCY_RESPONSE_MISSION, PV_TOU_MISSION
from repackq.models import (
    CellObservation,
    CellSnapshot,
    CellTrajectory,
    FutureTruth,
)
from repackq.prediction.metrics import evaluate_pack_metrics
from repackq.prediction.evaluation import evaluate_predictor
from repackq.prediction.split import future_tolerance_for_horizon, lookup_future_truth
from repackq.prediction.trajectory import (
    EstimatorConfig,
    build_snapshot,
    estimate_capacity_trajectory,
    median_pairwise_slope,
)
from repackq.prediction.trials import generate_candidate_pool


def observation(
    cell_id: str,
    cycle: int,
    capacity: float | None,
    *,
    resistance: float | None = None,
    temperature: float | None = None,
    protocol: str | None = "P-1",
) -> CellObservation:
    return CellObservation(
        cell_id=cell_id,
        protocol_id=protocol,
        phase="second_life",
        cycle_index=cycle,
        timestamp_s=None,
        capacity_ah=capacity,
        internal_resistance_ohm=resistance,
        temperature_c=temperature,
        voltage_v=None,
        current_a=None,
        source_dataset="synthetic_fixture",
    )


def linear_history(cell_id: str = "CELL", slope: float = -0.001) -> tuple[CellObservation, ...]:
    return tuple(
        observation(cell_id, cycle, 2.0 + slope * cycle, resistance=None)
        for cycle in (0, 10, 20, 30, 40)
    )


class TrajectoryEstimatorTests(unittest.TestCase):
    def test_exact_linear_trajectory_and_prediction(self) -> None:
        history = linear_history(slope=-0.001)
        estimate = estimate_capacity_trajectory(
            history,
            decision_cycle=40,
            horizon_cycles=100,
            nominal_capacity_ah=2.4,
        )
        self.assertAlmostEqual(estimate.recent_capacity_slope_ah_per_cycle, -0.001, places=12)
        self.assertAlmostEqual(estimate.predicted_capacity_ah, 1.86, places=12)
        self.assertAlmostEqual(estimate.prediction_uncertainty_ah, 0.0, places=12)
        self.assertEqual(estimate.diagnostics.fit_method, "weighted_least_squares")

    def test_positive_slope_is_clamped_and_uncertainty_has_a_cap(self) -> None:
        history = linear_history(slope=0.0005)
        estimate = estimate_capacity_trajectory(
            history,
            decision_cycle=40,
            horizon_cycles=100,
            nominal_capacity_ah=2.4,
        )
        self.assertTrue(estimate.diagnostics.positive_slope_clamped)
        self.assertEqual(estimate.recent_capacity_slope_ah_per_cycle, 0.0)
        self.assertEqual(estimate.predicted_capacity_ah, history[-1].capacity_ah)
        self.assertLessEqual(estimate.prediction_uncertainty_ah, 0.25 * 2.4)

    def test_median_pairwise_fallback_is_deterministic(self) -> None:
        cycles = [0, 10, 20, 30]
        capacities = [2.0, 1.99, 1.981, 1.97]
        expected = median_pairwise_slope(cycles, capacities)
        self.assertEqual(expected, median_pairwise_slope(cycles, capacities))
        with patch(
            "repackq.prediction.trajectory._weighted_linear_fit",
            side_effect=np.linalg.LinAlgError("injected singular fit"),
        ):
            estimate = estimate_capacity_trajectory(
                tuple(observation("CELL", cycle, capacity) for cycle, capacity in zip(cycles, capacities)),
                decision_cycle=30,
                horizon_cycles=10,
                nominal_capacity_ah=2.4,
            )
        self.assertEqual(estimate.diagnostics.fit_method, "median_pairwise_slope")
        self.assertEqual(estimate.diagnostics.fallback_reason, "injected singular fit")
        self.assertAlmostEqual(estimate.recent_capacity_slope_ah_per_cycle, expected)

    def test_insufficient_history_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "insufficient capacity history"):
            estimate_capacity_trajectory(
                linear_history()[-3:],
                decision_cycle=40,
                horizon_cycles=20,
                nominal_capacity_ah=2.4,
            )

    def test_snapshot_uses_latest_available_resistance_and_allows_missing_resistance(self) -> None:
        history = list(linear_history())
        history[1] = observation("CELL", 10, 1.99, resistance=0.045)
        snapshot = build_snapshot(
            history,
            decision_cycle=40,
            horizon_cycles=20,
            nominal_capacity_ah=2.4,
        )
        self.assertEqual(snapshot.internal_resistance_ohm, 0.045)
        self.assertAlmostEqual(snapshot.soh, snapshot.capacity_ah / 2.4)


class FutureTruthTests(unittest.TestCase):
    def test_tolerance_and_nearest_valid_measurement(self) -> None:
        future = (
            observation("CELL", 94, 1.7, resistance=0.06),
            observation("CELL", 104, 1.6, resistance=0.07),
        )
        self.assertEqual(future_tolerance_for_horizon(200), 10)
        truth = lookup_future_truth(
            future,
            decision_cycle=40,
            target_cycle=100,
            max_future_cycle_error=5,
        )
        self.assertIsNotNone(truth)
        assert truth is not None
        self.assertEqual(truth.actual_capacity_ah, 1.6)
        self.assertEqual(truth.nearest_cycle_distance, 4)

    def test_future_tolerance_returns_in_range_observation(self) -> None:
        truth = lookup_future_truth(
            (observation("CELL", 104, 1.6, resistance=0.07),),
            decision_cycle=40,
            target_cycle=100,
            max_future_cycle_error=3,
        )
        self.assertIsNone(truth)
        truth = lookup_future_truth(
            (observation("CELL", 104, 1.6, resistance=0.07),),
            decision_cycle=40,
            target_cycle=100,
            max_future_cycle_error=4,
        )
        self.assertIsNotNone(truth)
        assert truth is not None
        self.assertEqual(truth.nearest_cycle_distance, 4)
        self.assertEqual(truth.actual_capacity_ah, 1.6)


class PhysicalMetricTests(unittest.TestCase):
    def test_hand_calculated_current_predicted_and_observed_metrics(self) -> None:
        snapshots = (
            CellSnapshot("A", "P", 10, 1.0, 2.4, 1.0 / 2.4, 0.05, None, -0.001, 0.9, 0.01, 20, "synthetic_fixture"),
            CellSnapshot("B", "P", 10, 2.0, 2.4, 2.0 / 2.4, 0.07, None, -0.002, 1.1, 0.02, 20, "synthetic_fixture"),
        )
        truth = (
            FutureTruth("A", 30, 1.2, None, 0),
            FutureTruth("B", 30, 1.8, None, 0),
        )
        metrics = evaluate_pack_metrics(snapshots, truth)
        self.assertEqual(metrics.usable_pack_capacity_ah, 1.0)
        self.assertEqual(metrics.current_capacity_spread_ah, 1.0)
        self.assertAlmostEqual(metrics.current_capacity_cv, (0.5 / 1.5))
        self.assertAlmostEqual(metrics.resistance_spread_ohm or 0.0, 0.02)
        self.assertAlmostEqual(metrics.predicted_pack_divergence, 0.1 / 1.0)
        self.assertAlmostEqual(metrics.predicted_capacity_spread_ah, 0.2)
        self.assertAlmostEqual(metrics.observed_pack_divergence or 0.0, 0.3 / 1.5)
        self.assertEqual(metrics.observed_usable_capacity_ah, 1.2)

    def test_resistance_spread_is_null_when_any_cell_is_missing(self) -> None:
        snapshots = (
            CellSnapshot("A", "P", 10, 1.0, 2.4, 1 / 2.4, None, None, 0.0, 0.9, 0.01, 20, "synthetic_fixture"),
            CellSnapshot("B", "P", 10, 1.1, 2.4, 1.1 / 2.4, 0.07, None, 0.0, 1.0, 0.01, 20, "synthetic_fixture"),
        )
        self.assertIsNone(evaluate_pack_metrics(snapshots).resistance_spread_ohm)


class PredictorEvaluationTests(unittest.TestCase):
    def test_mae_rmse_and_truth_coverage_use_valid_held_out_points(self) -> None:
        observations = tuple(
            observation("EVAL", cycle, 2.0 - cycle * 0.001)
            for cycle in (0, 10, 20, 30, 40)
        ) + (observation("EVAL", 60, 1.90),)
        trajectory = CellTrajectory("EVAL", "P-1", 2.4, observations)
        result = evaluate_predictor((trajectory,), horizon_cycles=20)
        expected_error = abs(1.94 - 1.90)
        self.assertEqual(result.predictable_decision_points, 3)
        self.assertEqual(result.valid_held_out_forecasts, 1)
        self.assertAlmostEqual(result.future_truth_coverage, 1.0 / 3.0)
        self.assertAlmostEqual(result.mae_ah or 0.0, expected_error)
        self.assertAlmostEqual(result.rmse_ah or 0.0, expected_error)


class CandidatePoolTests(unittest.TestCase):
    def _trajectories(self) -> list[CellTrajectory]:
        trajectories = []
        for index in range(12):
            cell_id = f"CELL-{index:02d}"
            current = 1.40 + index * 0.035
            slope = -0.0004 - index * 0.00001
            observations = tuple(
                observation(
                    cell_id,
                    cycle,
                    current + slope * (cycle - 40),
                    resistance=0.04 + index * 0.0005,
                    protocol=f"P-{index % 3}",
                )
                for cycle in (0, 10, 20, 30, 40, 60)
            )
            trajectories.append(CellTrajectory(cell_id, f"P-{index % 3}", 2.4, observations))
        return trajectories

    def test_seeded_pool_reproducibility_and_validation(self) -> None:
        first = generate_candidate_pool(
            self._trajectories(), decision_cycle=40, horizon_cycles=20, seed=17, n=8, k=4
        )
        second = generate_candidate_pool(
            self._trajectories(), decision_cycle=40, horizon_cycles=20, seed=17, n=8, k=4
        )
        self.assertEqual(first.pool_id, second.pool_id)
        self.assertEqual(first.candidate_ids, second.candidate_ids)
        self.assertEqual(first.snapshots, second.snapshots)
        self.assertEqual(first.future_truth, second.future_truth)
        self.assertEqual(len(first.snapshots), 8)
        self.assertEqual(len(first.future_truth or ()), 8)
        with self.assertRaisesRegex(ValueError, "K cannot exceed N"):
            generate_candidate_pool(
                self._trajectories(), decision_cycle=40, horizon_cycles=20, seed=1, n=4, k=5
            )

    def test_protocol_stratification_and_heterogeneity_guard(self) -> None:
        pool = generate_candidate_pool(
            self._trajectories(),
            decision_cycle=40,
            horizon_cycles=20,
            seed=8,
            n=8,
            k=4,
            stratify_protocol=True,
        )
        counts: dict[str, int] = {}
        for snapshot in pool.snapshots:
            protocol = snapshot.protocol_id or "<unknown>"
            counts[protocol] = counts.get(protocol, 0) + 1
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        with self.assertRaisesRegex(ValueError, "below the required minimum heterogeneity"):
            generate_candidate_pool(
                self._trajectories(),
                decision_cycle=40,
                horizon_cycles=20,
                seed=8,
                n=8,
                k=4,
                minimum_soh_range=0.9,
            )

    def test_mission_defaults_and_stretch_placeholder_are_explicit(self) -> None:
        self.assertEqual(PV_TOU_MISSION.id, "pv_tou")
        self.assertEqual(PV_TOU_MISSION.horizon_cycles, 200)
        self.assertEqual(PV_TOU_MISSION.pack_size_k, 4)
        self.assertEqual(PV_TOU_MISSION.minimum_soh, 0.50)
        self.assertFalse(PV_TOU_MISSION.experimental)
        self.assertEqual(FREQUENCY_RESPONSE_MISSION.id, "frequency_response")
        self.assertTrue(FREQUENCY_RESPONSE_MISSION.experimental)
        self.assertIn("no frequency-response duty-specific", FREQUENCY_RESPONSE_MISSION.description)


if __name__ == "__main__":
    unittest.main()
