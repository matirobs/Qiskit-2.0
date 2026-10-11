"""Check history inputs, battery splits, and matching Java/Python predictions."""
import copy
import math
import tempfile
import unittest
from pathlib import Path

from repackq.prediction.features import FEATURE_NAMES, build_features, make_examples, split_cells
from repackq.training.java_bridge import JavaNetwork, export_weights, read_matrix, write_control, write_matrix
from repackq.prediction.model import CapacityModel, sigmoid
from repackq.training.train import fit_preprocessing


def point(cycle, capacity):
    return {"cycle": cycle, "capacity_ah": capacity, "resistance_ohm": .04, "temperature_c": 25}


def cell(identifier="1"):
    return {"cell_id": identifier, "primary": [point(i * 10 + 1, 2.4 - i * .05) for i in range(10)],
            "second_life": [point(i, 1.95 - i * .001) for i in range(1, 302, 5)]}


class FeaturesTest(unittest.TestCase):
    def test_future_mutation_changes_labels_but_not_features(self):
        original = cell()
        # future data can change the label, but must not change the features
        changed = copy.deepcopy(original)
        for observation in changed["second_life"]:
            if observation["cycle"] > 20:
                observation["capacity_ah"] *= .8
        before = make_examples([original], cutoffs=(20,), horizons=(50,))[0]
        after = make_examples([changed], cutoffs=(20,), horizons=(50,))[0]
        self.assertEqual(before["features"], after["features"])
        self.assertNotEqual(before["target_capacity_ah"], after["target_capacity_ah"])

    def test_future_observations_are_rejected(self):
        sample = cell()
        with self.assertRaisesRegex(ValueError, "Future"):
            build_features(sample["primary"], sample["second_life"], 20, 50)

    def test_cold_start_does_not_use_second_life(self):
        sample = cell()
        example = make_examples([sample], cutoffs=(0,), horizons=(50,))[0]
        self.assertEqual(example["features"]["current_capacity_ah"], sample["primary"][-1]["capacity_ah"])
        self.assertIsNone(example["features"]["second_life_recent_resistance_ohm"])

    def test_cells_do_not_cross_partitions(self):
        splits = split_cells([cell(str(i)) for i in range(20)])
        groups = [set(ids) for ids in splits.values()]
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertEqual(len(set.union(*groups)), 20)
        self.assertEqual(splits, split_cells([cell(str(i)) for i in reversed(range(20))]))

    def test_scaler_is_fitted_only_to_supplied_training_examples(self):
        examples = make_examples([cell()], cutoffs=(0,), horizons=(50, 100))
        fitted = fit_preprocessing(examples)
        unrelated_test = copy.deepcopy(examples[0])
        unrelated_test["features"]["current_capacity_ah"] = 1000
        self.assertEqual(fitted, fit_preprocessing(examples))
        self.assertNotEqual(fitted, fit_preprocessing(examples + [unrelated_test]))


class BinaryAndJavaTest(unittest.TestCase):
    def test_matrix_round_trip_and_corrupt_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "matrix.bin"
            write_matrix(path, [[1., 2.], [3., 4.]])
            self.assertEqual(read_matrix(path), [[1., 2.], [3., 4.]])
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaises(ValueError): read_matrix(path)
            with self.assertRaises(ValueError): write_matrix(path, [[math.nan]])
            with self.assertRaises(ValueError): write_matrix(path, [[1.], [1., 2.]])

    def test_java_learns_exports_and_is_reproducible(self):
        bridge = JavaNetwork()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            inputs, targets = directory / "inputs.bin", directory / "targets.bin"
            write_matrix(inputs, [[0., 1.], [1., 1.]])
            write_matrix(targets, [[.2], [.8]])
            binaries = []
            for run in range(2):
                weights, control = directory / f"weights{run}.bin", directory / f"train{run}.txt"
                write_control(control, inputs=inputs, targets=targets, weights=weights, rows=2, width=2,
                              hidden=4, epochs_per_block=1000)
                bridge.run(["train", str(control), "17", str(inputs), str(targets), "30", "5"])
                binaries.append(weights.read_bytes())
            self.assertEqual(*binaries)
            weights = directory / "weights0.bin"
            control, output = directory / "predict.txt", directory / "outputs.bin"
            write_control(control, inputs=inputs, weights=weights, rows=2, width=2, hidden=4)
            bridge.run(["predict", str(control), str(output)])
            actual = read_matrix(output)
            matrices = export_weights(weights, [2, 4, 1])
            for values, expected, java_prediction in zip([[0., 1.], [1., 1.]], [.2, .8], actual):
                for matrix in matrices:
                    values = [sigmoid(sum(value * row[column] for value, row in zip(values, matrix)))
                              for column in range(len(matrix[0]))]
                self.assertAlmostEqual(values[0], java_prediction[0], places=13)
                self.assertLess(abs(values[0] - expected), .1)


class PortableModelTest(unittest.TestCase):
    def test_predictions_are_bounded_and_future_input_rejected(self):
        sample = cell()
        example = make_examples([sample], cutoffs=(0,), horizons=(50,))[0]
        model = CapacityModel({"schema_version": 1, "feature_names": FEATURE_NAMES,
            "preprocessing": fit_preprocessing([example]),
            "weights": [[[0.] for _ in range(len(FEATURE_NAMES) + 1)]], "output_scale_ah": 3,
            "validation_residual_rmse_ah": .1, "training_data_sha256": "fixture",
            "domain": {"cutoff_max": 100, "horizon_min": 50, "horizon_max": 200}})
        result = model.predict(sample["primary"], [], horizon=50)
        self.assertLessEqual(result["predicted_capacity_ah"], result["current_capacity_ah"])
        self.assertGreaterEqual(result["predicted_capacity_ah"], 0)
        with self.assertRaises(ValueError): model.predict(sample["primary"], [], horizon=1000)
        with self.assertRaises(ValueError): model.predict(sample["primary"], sample["second_life"], cutoff=20, horizon=50)


if __name__ == "__main__":
    unittest.main()
