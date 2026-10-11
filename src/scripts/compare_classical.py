"""Compare Task 4 classical solvers on a replayable candidate pool."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.config import PV_TOU_MISSION
from repackq.data.serialization import load_trajectory_dataset
from repackq.models import CandidatePool, CellSnapshot, FutureTruth, MissionProfile
from repackq.optimization import (
    build_optimization_instance,
    compatibility_greedy,
    exact_enumeration,
    simulated_annealing,
    soh_sort,
)
from repackq.prediction.trajectory import build_snapshot


def _decode_pool(value: dict[str, Any]) -> CandidatePool:
    """Rebuild validated canonical models from a serialized benchmark pool."""

    required = {
        "pool_id", "decision_cycle", "horizon_cycles", "candidate_ids",
        "snapshots", "future_truth", "seed",
    }
    missing = required - value.keys()
    if missing:
        raise ValueError(f"candidate pool is missing fields: {sorted(missing)}")
    snapshots = tuple(CellSnapshot(**item) for item in value["snapshots"])
    future_value = value["future_truth"]
    future_truth = None if future_value is None else tuple(FutureTruth(**item) for item in future_value)
    return CandidatePool(
        pool_id=value["pool_id"],
        decision_cycle=value["decision_cycle"],
        horizon_cycles=value["horizon_cycles"],
        candidate_ids=tuple(value["candidate_ids"]),
        snapshots=snapshots,
        future_truth=future_truth,
        seed=value["seed"],
        selection_metadata=value.get("selection_metadata", {}),
    )


def _decode_mission(value: dict[str, Any]) -> MissionProfile:
    fields = {
        "id", "label", "horizon_cycles", "pack_size_k", "minimum_soh",
        "current_capacity_weight", "resistance_weight", "future_capacity_weight",
        "health_reward_weight", "uncertainty_weight", "temperature_weight", "description",
    }
    missing = fields - value.keys()
    if missing:
        raise ValueError(f"mission is missing fields: {sorted(missing)}")
    return MissionProfile(**{key: value[key] for key in fields}, experimental=value.get("experimental", False))


def _fixture_pool(path: Path) -> tuple[CandidatePool, MissionProfile, str]:
    payload, trajectories = load_trajectory_dataset(path)
    if payload["data_classification"] != "synthetic-fixture":
        raise ValueError("fixture fallback must be explicitly labeled synthetic-fixture")
    decision_cycle = 101
    horizon = 100
    mission = replace(PV_TOU_MISSION, horizon_cycles=horizon)
    snapshots = []
    truth = []
    for trajectory in sorted(trajectories, key=lambda item: item.cell_id):
        history = trajectory.history_through(decision_cycle)
        snapshots.append(
            build_snapshot(
                history,
                decision_cycle=decision_cycle,
                horizon_cycles=horizon,
                nominal_capacity_ah=trajectory.nominal_capacity_ah,
            )
        )
        target = decision_cycle + horizon
        match = next(
            (item for item in trajectory.observations if item.cycle_index == target),
            None,
        )
        if match is None or match.capacity_ah is None:
            raise ValueError(f"synthetic fixture has no measured future capacity for {trajectory.cell_id}")
        truth.append(
            FutureTruth(
                cell_id=trajectory.cell_id,
                target_cycle_index=target,
                actual_capacity_ah=match.capacity_ah,
                actual_internal_resistance_ohm=match.internal_resistance_ohm,
                nearest_cycle_distance=0,
            )
        )
    pool = CandidatePool(
        pool_id="synthetic-fixture-cycle-101-horizon-100",
        decision_cycle=decision_cycle,
        horizon_cycles=horizon,
        candidate_ids=tuple(item.cell_id for item in snapshots),
        snapshots=tuple(snapshots),
        future_truth=tuple(truth),
        seed=0,
        selection_metadata={"data_classification": "synthetic-fixture", "purpose": "CLI path demonstration only"},
    )
    return pool, mission, "synthetic-fixture"


def load_demo_pool(path: Path, pool_id: str | None = None) -> tuple[CandidatePool, MissionProfile, str]:
    """Load either exported real-data pools or the checked-in synthetic fixture."""

    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("input root must be a JSON object")
    if "pools" not in payload:
        if payload.get("data_classification") == "synthetic-fixture":
            return _fixture_pool(path)
        raise ValueError("input is not an exported demo-pool JSON or supported synthetic fixture")
    if payload.get("data_classification") not in {"real", "derived-real"}:
        raise ValueError("retrospective demo pools must be labeled real or derived-real")
    pools = payload.get("pools")
    if not isinstance(pools, list) or not pools:
        raise ValueError("demo-pool file must contain a nonempty pools array")
    default_id = payload.get("default_pool_id")
    selected_id = pool_id or default_id or pools[0].get("pool_id")
    selected = next((item for item in pools if item.get("pool_id") == selected_id), None)
    if selected is None:
        raise ValueError(f"pool_id {selected_id!r} was not found in the input")
    mission_payload = payload.get("mission")
    if not isinstance(mission_payload, dict):
        raise ValueError("demo-pool file is missing its mission definition")
    return _decode_pool(selected), _decode_mission(mission_payload), str(payload["data_classification"])


def _default_input() -> Path:
    real_pool = Path("data/processed/demo_pools.json")
    return real_pool if real_pool.is_file() else Path("data/fixtures/synthetic_demo.json")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare SOH sort, compatibility greedy, simulated annealing, and exact enumeration."
    )
    parser.add_argument("--input", type=Path, default=_default_input(), help="demo_pools.json or synthetic fixture JSON")
    parser.add_argument("--pool-id", help="pool ID to replay (defaults to the predeclared default pool)")
    parser.add_argument("--objective-mode", choices=("current_only", "trajectory_aware"), default="trajectory_aware")
    parser.add_argument("--seed", type=int, default=7, help="simulated annealing seed")
    parser.add_argument("--annealing-steps", type=int, default=3000)
    parser.add_argument("--penalty-multiplier", type=float, default=4.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        pool, mission, classification = load_demo_pool(args.input, args.pool_id)
        instance = build_optimization_instance(
            pool,
            mission=mission,
            objective_mode=args.objective_mode,
        )
        exact = exact_enumeration(
            instance,
            future_truth=pool.future_truth,
            penalty_multiplier=args.penalty_multiplier,
        )
        results = [
            soh_sort(instance, future_truth=pool.future_truth),
            compatibility_greedy(instance, future_truth=pool.future_truth),
            simulated_annealing(
                instance,
                seed=args.seed,
                steps=args.annealing_steps,
                future_truth=pool.future_truth,
            ),
            exact,
        ]
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"compare_classical: error: {error}\n")

    print(
        f"Pool: {pool.pool_id} | source: {classification} | "
        f"objective: {args.objective_mode} | N={instance.n}, K={instance.pack_size_k}"
    )
    print("Algorithm             Selected cells                       Objective   Current spread   Predicted CV   Observed CV")
    for result in results:
        ids = ",".join(result.selected_cell_ids)
        predicted = "—" if result.predicted_pack_divergence is None else f"{result.predicted_pack_divergence:.5f}"
        observed = "—" if result.observed_pack_divergence is None else f"{result.observed_pack_divergence:.5f}"
        print(
            f"{result.algorithm:<21} {ids:<36} {result.objective_value:>10.6f}"
            f" {result.current_capacity_spread_ah:>14.5f} {predicted:>14} {observed:>12}"
        )
    print(
        "Exact oracle: "
        f"{exact.metadata['evaluated_subsets']} feasible subsets; "
        f"QUBO penalty A={exact.metadata['qubo_penalty']:.6g} "
        f"(doublings={exact.metadata['penalty_calibration_doublings']})."
    )
    if classification == "synthetic-fixture":
        print("Synthetic fixture output is for implementation demonstration only; it is not scientific benchmark evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
