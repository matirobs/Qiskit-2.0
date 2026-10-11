"""Score the leakage-free trajectory predictor on held-out real observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.data.serialization import load_trajectory_dataset, write_json_atomic
from repackq.prediction.evaluation import evaluate_predictor
from repackq.prediction.trajectory import DEFAULT_ESTIMATOR_CONFIG


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate horizon capacity predictions against held-out diagnostic "
            "measurements. The input must be a real or derived-real canonical trajectory dataset."
        )
    )
    parser.add_argument("--input", required=True, help="canonical trajectory JSON from preprocessing")
    parser.add_argument(
        "--output", default="data/processed/prediction_evaluation.json",
        help="compact summary JSON output path",
    )
    parser.add_argument("--horizon", type=int, default=200, help="forecast horizon in cycles")
    parser.add_argument(
        "--max-future-cycle-error", type=int,
        help="future diagnostic tolerance (default: max(5, round(0.05 * horizon)))",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    input_path = Path(args.input)
    try:
        payload, trajectories = load_trajectory_dataset(input_path)
        if payload["data_classification"] not in {"real", "derived-real"}:
            parser.exit(2, "evaluate_predictor: error: synthetic fixtures cannot be reported as predictor validation\n")
        if payload["phase"] != "second_life":
            parser.exit(2, "evaluate_predictor: error: predictor validation expects second_life trajectories\n")
        report = evaluate_predictor(
            trajectories,
            horizon_cycles=args.horizon,
            max_future_cycle_error=args.max_future_cycle_error,
        )
        output = {
            "schema_version": "1.0",
            "source_dataset": payload["source_dataset"],
            "data_classification": payload["data_classification"],
            "input_sha256": _sha256(input_path),
            "prediction_method": {
                "name": "weighted_recent_linear_capacity",
                "window_size": DEFAULT_ESTIMATOR_CONFIG.window_size,
                "minimum_history_points": DEFAULT_ESTIMATOR_CONFIG.minimum_history_points,
                "weights_oldest_to_newest": "linear from 0.5 to 1.0",
                "positive_slope_clamp": 0.0,
                "prediction_clamp": "[0, current capacity]",
                "uncertainty_cap_fraction_of_nominal": (
                    DEFAULT_ESTIMATOR_CONFIG.maximum_uncertainty_fraction_of_nominal
                ),
            },
            "metrics": report.to_dict(),
            "limitations": [
                "Forecasts are evaluated at cell-by-decision-cycle cutoffs; cutoffs within a cell overlap.",
                "The horizon is measured in dataset cycle indices, not calendar time or a household duty trace.",
                "This metric evaluates the predictor only; it does not establish pack or solver performance.",
            ],
            "redistribution_license_verified": False,
        }
        write_json_atomic(args.output, output)
    except (OSError, ValueError) as error:
        parser.exit(2, f"evaluate_predictor: error: {error}\n")
    print(json.dumps(output["metrics"], indent=2, sort_keys=True, allow_nan=False))
    print(f"Wrote compact evaluation summary to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
