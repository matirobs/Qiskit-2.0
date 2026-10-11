"""Run exported network weights in Python without Java or training packages."""
from __future__ import annotations

import json
import math
from pathlib import Path
from .features import FEATURE_NAMES, build_features
from .full_history import build_full_features, feature_names


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)


class CapacityModel:
    """Capacity forecast in amp-hours, with training-only scaling and physical bounds."""

    def __init__(self, artifact: dict):
        self.feature_spec = artifact.get("feature_spec")
        if self.feature_spec is not None and (self.feature_spec.get("kind") != "full_history_v2"
                or not isinstance(self.feature_spec.get("bins"), int) or not 1 <= self.feature_spec["bins"] <= 256):
            raise ValueError("Unsupported history encoding")
        self.feature_names = feature_names(self.feature_spec) if self.feature_spec else FEATURE_NAMES
        if artifact.get("schema_version") not in (1, 2) or artifact.get("feature_names") != self.feature_names:
            raise ValueError("Unsupported model schema or feature order")
        self.hidden_activation = artifact.get("hidden_activation", "sigmoid")
        if self.hidden_activation not in ("sigmoid", "tanh"):
            raise ValueError("Unsupported hidden activation")
        self.artifact = artifact
        if not math.isfinite(artifact["output_scale_ah"]) or artifact["output_scale_ah"] <= 0:
            raise ValueError("Output capacity scale must be finite and positive")
        if not math.isfinite(artifact["validation_residual_rmse_ah"]) or artifact["validation_residual_rmse_ah"] < 0:
            raise ValueError("Invalid validation residual scale")
        self.output_transform = artifact.get("output_transform", "capacity")
        if self.output_transform not in ("capacity", "current_residual"):
            raise ValueError("Unsupported output transform")
        # an exported artifact may contain a single network, an average, or task-specific models
        self.members = [CapacityModel(a) for a in artifact.get("ensemble_members", [])]
        self.experts = {k: CapacityModel(a) for k,a in artifact.get("routing_experts", {}).items()}
        if self.experts:
            if set(self.experts) != {"first_life", "updated"} or self.members:
                raise ValueError("Invalid forecast experts")
            if any(not set(m.feature_names) <= set(self.feature_names) for m in self.experts.values()):
                raise ValueError("Expert input features exceed routing model features")
            self.preprocessing = self.experts["first_life"].preprocessing
            self.weights = []
            return
        if self.members:
            if any(member.feature_names != self.feature_names or member.feature_spec != self.feature_spec
                   for member in self.members):
                raise ValueError("Ensemble members must share history encoding")
            self.preprocessing = self.members[0].preprocessing
            self.weights = []
            return
        self.weights = artifact["weights"]
        self.preprocessing = artifact["preprocessing"]
        width = len(self.feature_names) + 1
        if not self.weights:
            raise ValueError("Network must have weights")
        for matrix in self.weights:
            if len(matrix) != width or not matrix or not matrix[0]:
                raise ValueError("Invalid network dimensions")
            next_width = len(matrix[0])
            if any(len(row) != next_width or any(not math.isfinite(x) for x in row) for row in matrix):
                raise ValueError("Invalid network weights")
            width = next_width
        if width != 1:
            raise ValueError("Capacity model must have one output")
        for name in self.feature_names:
            values = self.preprocessing[name]
            if any(not math.isfinite(values[key]) for key in ("median", "mean", "scale")) or values["scale"] <= 0:
                raise ValueError("Invalid preprocessing statistics")

    @classmethod
    def load(cls, path: str | Path):
        return cls(json.loads(Path(path).read_text()))

    def transform(self, features: dict) -> list[float]:
        """Fill missing inputs, scale them, and append a constant for the first-layer bias."""
        values = []
        for name in self.feature_names:
            statistics = self.preprocessing[name]
            value = features[name]
            if value is None:
                value = statistics["median"]
            if not math.isfinite(value):
                raise ValueError(f"Non-finite feature: {name}")
            values.append((value - statistics["mean"]) / statistics["scale"])
        return values + [1.0]  # Explicit first-layer intercept for the original bias-free network.

    def predict_raw(self, features: dict) -> float:
        """Run the selected expert, ensemble, or network before physical bounds are applied."""
        if self.experts:
            return self.experts["first_life" if features["second_life_cutoff_cycles"] == 0 else "updated"].predict_raw(features)
        if self.members:
            current = features["current_capacity_ah"]
            return sum(max(0, min(current, m.predict_raw(features))) for m in self.members) / len(self.members)
        activations = self.transform(features)
        for index, matrix in enumerate(self.weights):
            activation = math.tanh if index < len(self.weights) - 1 and self.hidden_activation == "tanh" else sigmoid
            activations = [activation(sum(value * row[column] for value, row in zip(activations, matrix)))
                           for column in range(len(matrix[0]))]
        if self.output_transform == "current_residual":
            return features["current_capacity_ah"] + (activations[0] - .5) * self.artifact["output_scale_ah"]
        return activations[0] * self.artifact["output_scale_ah"]

    def predict(self, primary_history: list[dict], second_life_history: list[dict],
                *, cutoff: int = 0, horizon: int = 200, primary_protocol_ids=None) -> dict:
        """Forecast within the trained cutoff and horizon ranges.

        Later measurements are not inputs. The uncertainty field is the
        validation residual scale, not a confidence interval."""
        domain = self.artifact["domain"]
        if not domain["horizon_min"] <= horizon <= domain["horizon_max"] or not 0 <= cutoff <= domain["cutoff_max"]:
            raise ValueError("Requested forecast is outside the training domain")
        if self.feature_spec and self.feature_spec.get("protocols") and primary_protocol_ids is not None:
            primary_history = [{**p, "protocol_ids": list(primary_protocol_ids)} for p in primary_history]
        if self.feature_spec and self.feature_spec.get("usage"):
            if any("usage" not in p for p in primary_history + second_life_history):
                raise ValueError("This model requires all-measurement usage summaries in history points")
        features = (build_full_features(primary_history, second_life_history, cutoff, horizon, self.feature_spec)
                    if self.feature_spec else build_features(primary_history, second_life_history, cutoff, horizon))
        current = features["current_capacity_ah"]
        predicted = max(0.0, min(current, self.predict_raw(features)))
        return {"predicted_capacity_ah": predicted, "current_capacity_ah": current,
                "predicted_loss_ah": current - predicted, "cutoff_cycle": cutoff,
                "horizon_cycles": horizon, "prediction_uncertainty_ah": self.artifact["validation_residual_rmse_ah"],
                "uncertainty_kind": "validation residual scale; not a confidence interval",
                "model": "java-neuralnets-export", "training_data_sha256": self.artifact["training_data_sha256"]}
