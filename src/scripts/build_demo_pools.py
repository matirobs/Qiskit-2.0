"""Generate reproducible retrospective demo pools from processed real data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from statistics import median

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.config import PV_TOU_MISSION
from repackq.data.serialization import load_trajectory_dataset, write_json_atomic
from repackq.prediction.metrics import evaluate_pack_metrics
from repackq.prediction.trajectory import DEFAULT_ESTIMATOR_CONFIG
from repackq.prediction.trials import DEFAULT_MIN_SOH_RANGE, generate_candidate_pool
from repackq.prediction.evaluation import select_decision_cycle


DEFAULT_SEEDS = (11, 29, 47)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build at least three seeded candidate pools from a real canonical "
            "trajectory asset. Synthetic fixtures are rejected."
        )
    )
    parser.add_argument("--input", required=True, help="real/derived-real canonical trajectory JSON")
    parser.add_argument(
        "--output", default="data/processed/demo_pools.json",
        help="local generated pool JSON output path",
    )
    parser.add_argument("--decision-cycle", type=int, help="use this cutoff; otherwise maximize eligible coverage")
    parser.add_argument("--horizon", type=int, default=PV_TOU_MISSION.horizon_cycles)
    parser.add_argument("--n", type=int, default=8, help="candidate pool size")
    parser.add_argument("--k", type=int, default=PV_TOU_MISSION.pack_size_k, help="selected pack size")
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS),
        help="predeclared pool seeds (at least three required; default: 11 29 47)",
    )
    parser.add_argument(
        "--minimum-soh-range", type=float, default=DEFAULT_MIN_SOH_RANGE,
        help="minimum SOH range within each sampled pool (default: 0.02)",
    )
    parser.add_argument("--stratify-protocol", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if len(set(args.seeds)) < 3:
        parser.error("at least three distinct seeds are required to create benchmark candidate pools")
    try:
        payload, trajectories = load_trajectory_dataset(args.input)
        if payload["data_classification"] not in {"real", "derived-real"}:
            parser.exit(
                2,
                "build_demo_pools: error: synthetic fixtures cannot be used to create retrospective demo pools\n",
            )
        if payload["phase"] != "second_life":
            parser.exit(
                2,
                "build_demo_pools: error: the recommissioning benchmark requires second_life trajectories\n",
            )
        mission = replace(
            PV_TOU_MISSION,
            horizon_cycles=args.horizon,
            pack_size_k=args.k,
        )
        if args.decision_cycle is None:
            decision_cycle, eligible_count = select_decision_cycle(
                trajectories,
                horizon_cycles=args.horizon,
                minimum_candidate_soh=mission.minimum_soh,
                minimum_soh_range=args.minimum_soh_range,
                require_resistance=mission.resistance_weight > 0,
                require_temperature=mission.temperature_weight > 0,
            )
            decision_cycle_selection = (
                "maximum eligible coverage among cutoffs meeting the SOH-range check; "
                "earliest cycle breaks ties"
            )
        else:
            decision_cycle = args.decision_cycle
            eligible_count = None
            decision_cycle_selection = "user-specified"

        pools = [
            generate_candidate_pool(
                trajectories,
                decision_cycle=decision_cycle,
                horizon_cycles=args.horizon,
                seed=seed,
                n=args.n,
                k=args.k,
                mission=mission,
                stratify_protocol=args.stratify_protocol,
                minimum_soh_range=args.minimum_soh_range,
            )
            for seed in args.seeds
        ]
        # The illustrative default is selected using only the optimizer-visible
        # predicted capacities, never the separate held-out future truth.
        predicted_divergence = {
            pool.pool_id: evaluate_pack_metrics(pool.snapshots).predicted_pack_divergence
            for pool in pools
        }
        if any(value is None for value in predicted_divergence.values()):
            raise ValueError("a candidate pool has zero predicted mean capacity; predicted CV is undefined")
        median_divergence = median(predicted_divergence.values())
        default_pool = min(
            pools,
            key=lambda pool: (abs(predicted_divergence[pool.pool_id] - median_divergence), pool.pool_id),
        )
        output = {
            "schema_version": "1.0",
            "source_dataset": payload["source_dataset"],
            "data_classification": payload["data_classification"],
            "cell_id_convention": (
                "Canonical cell_id uses the embedded Battery_ID (manuscript identifier); "
                "the unavailable original experiment labels 61 and 62 are absent source filenames."
            ),
            "unavailable_original_file_ids": ["61", "62"],
            "input_sha256": _sha256(Path(args.input)),
            "mission": mission.to_dict(),
            "decision_cycle": decision_cycle,
            "decision_cycle_selection": decision_cycle_selection,
            "eligible_cell_count_at_decision_cycle": eligible_count,
            "horizon_cycles": args.horizon,
            "candidate_size_n": args.n,
            "pack_size_k": args.k,
            "predeclared_seeds": list(args.seeds),
            "default_pool_id": default_pool.pool_id,
            "default_pool_selection": {
                "criterion": "predicted pack divergence closest to the median across the predeclared seeded pool set",
                "selected_pool_predicted_divergence": predicted_divergence[default_pool.pool_id],
                "median_predicted_divergence": median_divergence,
                "held_out_future_values_used": False,
            },
            "selection_criteria": {
                "minimum_soh": mission.minimum_soh,
                "minimum_history_points": DEFAULT_ESTIMATOR_CONFIG.minimum_history_points,
                "minimum_soh_range_per_pool": args.minimum_soh_range,
                "decision_cycle_minimum_eligible_soh_range": args.minimum_soh_range,
                "requires_resistance": mission.resistance_weight > 0,
                "future_truth_tolerance_cycles": max(5, round(0.05 * mission.horizon_cycles)),
                "protocol_stratified": args.stratify_protocol,
                "future_measurements_fabricated": False,
            },
            "pools": [pool.to_dict() for pool in pools],
            "redistribution_license_verified": False,
        }
        write_json_atomic(args.output, output)
    except (OSError, ValueError) as error:
        parser.exit(2, f"build_demo_pools: error: {error}\n")
    print(json.dumps({
        "decision_cycle": decision_cycle,
        "pool_count": len(pools),
        "default_pool_id": default_pool.pool_id,
        "output": args.output,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
