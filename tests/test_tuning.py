"""Check fixed success tolerances, model averaging, and Java checkpoint selection."""
import copy
import tempfile
import unittest
from pathlib import Path

from repackq.prediction.features import FEATURE_NAMES, make_examples
from repackq.prediction.full_history import feature_names
from repackq.training.java_bridge import read_matrix
from repackq.prediction.model import CapacityModel
from repackq.training.train import fit_preprocessing
from repackq.training.tune import success_metrics, rank, train_candidate, enrich, fitted_statistics
from repackq.training.tune_refit import cell_folds, refit
from test_prediction import cell


class TuningTest(unittest.TestCase):
    def test_cross_validation_excludes_each_cell_once_and_fixed_refit_matches_java(self):
        ids=[str(i) for i in range(1,11)]
        # the same seed must keep each battery in exactly one repeatable fold
        folds=cell_folds(ids)
        self.assertEqual(sorted(i for fold in folds for i in fold),sorted(ids))
        self.assertEqual(folds,cell_folds(list(reversed(ids))))
        for fold in folds:
            self.assertFalse(set(fold) & (set(ids)-set(fold)))
        examples=make_examples([cell()],cutoffs=(0,),horizons=(50,100))
        config={"hidden":[4],"seed":17,"learning_rate":.03,"epochs_per_block":10,
                "shuffle":False,"weight_decay":0.}
        with tempfile.TemporaryDirectory() as tmp:
            artifact=refit(config,examples,20,Path(tmp),"fixture",["1"],["2"])
            self.assertEqual(artifact["cell_splits"]["validation"],[])
            self.assertEqual(artifact["training"]["refit_passes"],20)
            self.assertLess(artifact["training"]["java_python_max_absolute_difference_ah"],1e-11)
            log=(Path(tmp)/"fit.log").read_text()
            self.assertEqual(log.count("fit_block="),2)
            self.assertIn("training=true",(Path(tmp)/"fit_control.txt").read_text())
            self.assertIn("training=false",(Path(tmp)/"predict_control.txt").read_text())

    def test_success_denominator_and_fixed_relative_tolerance(self):
        metrics = success_metrics([2., 1.], [1.92, .8])
        self.assertEqual(metrics["within_5_percent_count"], 1)
        self.assertEqual(metrics["within_5_percent"], 50)
        self.assertEqual(metrics["within_10_percent"], 50)
        other = success_metrics([2., 1.], [1.92, .95])
        self.assertGreater(rank(other), rank(metrics))
        with self.assertRaises(ValueError): success_metrics([0.], [1.])

    def test_current_residual_and_bounded_ensemble_inference(self):
        example = make_examples([cell()], cutoffs=(0,), horizons=(50,))[0]
        artifact = {"schema_version": 2, "feature_names": FEATURE_NAMES,
            "weights": [[[0.] for _ in range(len(FEATURE_NAMES)+1)]],
            "preprocessing": fit_preprocessing([example]), "output_scale_ah": 3.,
            "validation_residual_rmse_ah": .1, "training_data_sha256": "fixture",
            "domain": {"cutoff_max": 100, "horizon_min": 50, "horizon_max": 200}}
        features = example["features"]
        original = CapacityModel(artifact)
        residual_artifact = {**artifact, "output_transform": "current_residual"}
        residual = CapacityModel(residual_artifact)
        self.assertEqual(residual.predict_raw(features), features["current_capacity_ah"])
        combined = copy.deepcopy(artifact)
        combined.pop("weights")
        combined.pop("preprocessing")
        combined["ensemble_members"] = [artifact, residual_artifact]
        ensemble = CapacityModel(combined)
        self.assertAlmostEqual(ensemble.predict_raw(features),
            (original.predict_raw(features) + residual.predict_raw(features))/2)
        self.assertGreater(ensemble.predict(cell()["primary"], [], horizon=50)["predicted_capacity_ah"], 0)

    def test_java_relative_success_checkpoint_and_residual_export_agree(self):
        examples = make_examples([cell()], cutoffs=(0,), horizons=(50,100))
        config = {"name":"test", "dataset":"sparse", "hidden":[8,4], "activation":"tanh",
            "output":"current_residual", "learning_rate":.01, "seed":17,
            "feature_spec":None, "epochs_per_block":100, "blocks":4, "patience":2,
            "weight_decay":.0001,"relative_loss":True}
        with tempfile.TemporaryDirectory() as tmp:
            result = train_candidate(config, examples, examples, Path(tmp), "fixture",
                                     {"train":["1"],"validation":[],"test":[]})
            self.assertLess(result["java_python_max_absolute_difference_ah"], 1e-11)
            self.assertIn("validation_within5=", (Path(tmp)/"test/training.log").read_text())
            weights = read_matrix(Path(tmp)/"test/case_weights.bin")
            self.assertAlmostEqual(sum(row[0] for row in weights)/len(weights), 1.)
            self.assertNotEqual(weights[0][0], weights[1][0])
            selected = CapacityModel(result["artifact"])
            values = [selected.predict_raw(e["features"]) for e in examples]
            metrics = success_metrics([e["target_capacity_ah"] for e in examples], values)
            self.assertEqual(metrics["within_5_percent_count"], result["validation"]["within_5_percent_count"])

    def test_protocol_history_is_explicit_and_experts_route_by_known_cutoff(self):
        sample = cell()
        sample["protocol_ids"] = [1]
        spec = {"kind":"full_history_v2","bins":2,"usage":False,"protocols":[1,2]}
        examples = make_examples([sample], cutoffs=(0,20), horizons=(50,))
        encoded = enrich(examples,[sample],spec)
        names = feature_names(spec)
        self.assertEqual(encoded[0]["features"]["primary_protocol_1"],1.)
        self.assertEqual(encoded[0]["features"]["primary_protocol_2"],0.)
        self.assertNotIn("cell_id", names)
        base = {"schema_version":2,"feature_names":FEATURE_NAMES,
            "weights":[[[0.] for _ in range(16)]],"preprocessing":fit_preprocessing(examples),
            "output_scale_ah":3.,"validation_residual_rmse_ah":.1,"training_data_sha256":"fixture",
            "domain":{"cutoff_max":100,"horizon_min":50,"horizon_max":200}}
        updated = {**base,"feature_spec":spec,"feature_names":names,"output_transform":"current_residual",
            "weights":[[[0.] for _ in range(len(names)+1)]],"preprocessing":fitted_statistics(encoded,names)}
        routed = {**updated,"routing_experts":{"first_life":base,"updated":updated}}
        routed.pop("weights")
        routed.pop("preprocessing")
        model = CapacityModel(routed)
        self.assertEqual(model.predict(sample["primary"],[],horizon=50,primary_protocol_ids=[1])["predicted_capacity_ah"],1.5)
        past = [p for p in sample["second_life"] if p["cycle"]<=20]
        result = model.predict(sample["primary"],past,cutoff=20,horizon=50,primary_protocol_ids=[1])
        self.assertEqual(result["predicted_capacity_ah"],past[-1]["capacity_ah"])
        with self.assertRaisesRegex(ValueError,"requires recorded"):
            model.predict(sample["primary"],[],horizon=50)
        with self.assertRaisesRegex(ValueError,"outside the trained"):
            model.predict(sample["primary"],[],horizon=50,primary_protocol_ids=[3])
