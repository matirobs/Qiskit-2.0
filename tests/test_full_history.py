"""Check pooled histories, measured forecast targets, and larger network exports."""
import copy
import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from repackq.prediction.full_history import build_full_features, dense_cases, feature_names
from repackq.training.java_bridge import JavaNetwork, export_weights, read_matrix, write_control, write_matrix
from repackq.prediction.model import CapacityModel, sigmoid
from repackq.training.train_full import build_contexts, fit_full_preprocessing, write_cases, train_full
from test_prediction import cell


class DenseHistoryTest(unittest.TestCase):
    def setUp(self):
        self.spec = {"kind": "full_history_v2", "bins": 4, "usage": False}

    def test_dense_targets_are_measured_and_future_mutation_cannot_change_inputs(self):
        sample = cell()
        cases = dense_cases([sample])
        self.assertGreater(len(cases), 100)
        target = next(c for c in cases if c["cutoff"] == 16 and c["horizon"] == 50)
        self.assertEqual(target["target_cycle"], 66)
        # changing future measurements should change targets but leave known inputs alone
        changed = copy.deepcopy(sample)
        for point in changed["second_life"]:
            if point["cycle"] > 16:
                point["capacity_ah"] *= .5
        def inputs(c):
            return build_full_features(c["primary"], [p for p in c["second_life"] if p["cycle"] <= 16],
                                       16, 50, self.spec)
        self.assertEqual(inputs(sample), inputs(changed))
        with self.assertRaisesRegex(ValueError, "Future"):
            build_full_features(sample["primary"], sample["second_life"], 16, 50, self.spec)

    def test_every_primary_observation_contributes_even_between_old_sample_points(self):
        sample = cell()
        original = build_full_features(sample["primary"], [], 0, 50, self.spec)
        changed = copy.deepcopy(sample)
        # Index 1 was absent from the old five capacity samples and recent-eight slope.
        changed["primary"][1]["capacity_ah"] -= .1
        after = build_full_features(changed["primary"], [], 0, 50, self.spec)
        self.assertNotEqual(original["primary_00_capacity_mean"], after["primary_00_capacity_mean"])
        self.assertEqual(sum(original[f"primary_{i:02d}_observed"] for i in range(4)), 4)
        usage_names = feature_names({**self.spec, "usage": True})
        self.assertEqual(len(usage_names), len(set(usage_names)))

    def test_scaling_ignores_held_out_histories_and_disk_matrix_matches(self):
        samples = [cell("1"), cell("2")]
        cases = dense_cases(samples, 50, 50)
        keys, contexts = build_contexts(cases, samples, self.spec)
        training = [c for c in cases if c["cell_id"] == "1"]
        names = feature_names(self.spec)
        fitted = fit_full_preprocessing(keys, contexts, {"1"}, training, names)
        modified = contexts.copy()
        modified[[k[0] == "2" for k in keys]] = 1e6
        self.assertEqual(fitted, fit_full_preprocessing(keys, modified, {"1"}, training, names))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.bin"
            write_cases(path, training[:3], contexts, dict(zip(keys, range(len(keys)))), fitted, names)
            matrix = read_matrix(path)
            self.assertEqual(len(matrix), 3)
            self.assertEqual(len(matrix[0]), len(names) + 1)
            self.assertEqual(matrix[0][-1], 1)
            self.assertTrue(np.isfinite(matrix).all())


class DeepJavaTest(unittest.TestCase):
    def test_complete_dense_training_export_and_portable_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            samples = [cell(str(i)) for i in range(1, 8)]
            data = directory / "histories.json"
            data.write_text(json.dumps({"cells": samples}))
            with contextlib.redirect_stdout(io.StringIO()):
                report = train_full(data, directory / "model", bins=2, hidden=[8, 4, 2],
                                    blocks=2, patience=2, minimum_horizon=50, maximum_horizon=50)
            self.assertEqual(report["completed_passes"], 2)
            self.assertGreater(report["java_training_seconds"], 0)
            self.assertLess(report["java_python_max_absolute_difference_ah"], 1e-11)
            model = CapacityModel.load(directory / "model/capacity_model.json")
            self.assertEqual(len(model.weights), 4)
            forecast = model.predict(samples[0]["primary"], [], horizon=50)
            self.assertTrue(math.isfinite(forecast["predicted_capacity_ah"]))

    def test_three_hidden_layers_learn_and_export_matching_tanh_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            inputs, targets = directory / "x.bin", directory / "y.bin"
            write_matrix(inputs, [[0., 1.], [1., 1.]])
            write_matrix(targets, [[.2], [.8]])
            weights, control = directory / "weights.bin", directory / "train.txt"
            write_control(control, inputs=inputs, targets=targets, weights=weights, rows=2, width=2,
                          hidden=[8, 6, 4], hidden_activation="tanh", epochs_per_block=500, shuffle=True)
            bridge = JavaNetwork()
            bridge.run(["train", str(control), "17", str(inputs), str(targets), "8", "3"])
            matrices = export_weights(weights, [2, 8, 6, 4, 1])
            write_control(control, inputs=inputs, weights=weights, rows=2, width=2,
                          hidden=[8, 6, 4], hidden_activation="tanh")
            output = directory / "out.bin"
            bridge.run(["predict", str(control), str(output)])
            for values, expected, actual in zip([[0., 1.], [1., 1.]], [.2, .8], read_matrix(output)):
                for index, matrix in enumerate(matrices):
                    activation = sigmoid if index == len(matrices) - 1 else math.tanh
                    values = [activation(sum(x * row[column] for x, row in zip(values, matrix)))
                              for column in range(len(matrix[0]))]
                self.assertAlmostEqual(values[0], actual[0], places=12)
                self.assertLess(abs(values[0] - expected), .04)
