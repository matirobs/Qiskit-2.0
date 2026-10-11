from __future__ import annotations

import unittest
from dataclasses import replace

from repackq.models import CellObservation, CellTrajectory
from repackq.prediction.split import lookup_future_truth, split_history_future
from repackq.prediction.trajectory import build_snapshot, estimate_capacity_trajectory


def make_trajectory() -> CellTrajectory:
    observations = []
    for cycle in range(0, 101, 10):
        observations.append(
            CellObservation(
                cell_id="CELL-LEAK",
                protocol_id="P-1",
                phase="second_life",
                cycle_index=cycle,
                timestamp_s=None,
                capacity_ah=1.90 - cycle * 0.001,
                internal_resistance_ohm=0.04 + cycle * 0.00001,
                temperature_c=25.0 + cycle * 0.01,
                voltage_v=None,
                current_a=None,
                source_dataset="synthetic_fixture",
            )
        )
    return CellTrajectory("CELL-LEAK", "P-1", 2.4, tuple(observations))


class LeakagePreventionTests(unittest.TestCase):
    def test_mutating_every_future_measurement_does_not_change_snapshot_or_prediction(self) -> None:
        trajectory = make_trajectory()
        split = split_history_future(trajectory, decision_cycle=40)
        snapshot_before = build_snapshot(
            split.history,
            decision_cycle=40,
            horizon_cycles=20,
            nominal_capacity_ah=trajectory.nominal_capacity_ah,
        )
        estimate_before = estimate_capacity_trajectory(
            split.history,
            decision_cycle=40,
            horizon_cycles=20,
            nominal_capacity_ah=trajectory.nominal_capacity_ah,
        )

        mutated_future = tuple(
            replace(
                observation,
                capacity_ah=observation.capacity_ah + 0.7,
                internal_resistance_ohm=0.9,
                temperature_c=90.0,
                voltage_v=4.9,
                current_a=8.0,
            )
            for observation in split.future
        )
        changed = CellTrajectory(
            trajectory.cell_id,
            trajectory.protocol_id,
            trajectory.nominal_capacity_ah,
            split.history + mutated_future,
        )
        changed_split = split_history_future(changed, decision_cycle=40)
        snapshot_after = build_snapshot(
            changed_split.history,
            decision_cycle=40,
            horizon_cycles=20,
            nominal_capacity_ah=changed.nominal_capacity_ah,
        )
        estimate_after = estimate_capacity_trajectory(
            changed_split.history,
            decision_cycle=40,
            horizon_cycles=20,
            nominal_capacity_ah=changed.nominal_capacity_ah,
        )

        self.assertEqual(snapshot_before, snapshot_after)
        self.assertEqual(estimate_before, estimate_after)
        original_truth = lookup_future_truth(
            split.future,
            decision_cycle=40,
            target_cycle=60,
            max_future_cycle_error=5,
        )
        changed_truth = lookup_future_truth(
            changed_split.future,
            decision_cycle=40,
            target_cycle=60,
            max_future_cycle_error=5,
        )
        self.assertNotEqual(original_truth, changed_truth)

    def test_predictor_rejects_a_sequence_containing_future_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "future leakage rejected"):
            estimate_capacity_trajectory(
                make_trajectory().observations,
                decision_cycle=40,
                horizon_cycles=20,
                nominal_capacity_ah=2.4,
            )


if __name__ == "__main__":
    unittest.main()
