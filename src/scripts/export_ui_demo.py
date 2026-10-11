"""Export the small synthetic UI fixture and replay assets.

This output is for interaction design only. Task 6 benchmark assets remain the
only aggregate real-data result replay in the browser.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
_ROOT = _SRC.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.ui import (
    _DECISION_CYCLE,
    _SUPPORTED_HORIZONS,
    _SUPPORTED_PACK_SIZES,
    _load_fixture,
    _synthetic_future_observations,
    get_demo_state,
    run_classical_comparison,
    run_live_qaoa,
)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def export(destination: Path, *, include_qaoa: bool = True) -> None:
    inventory = {
        "schema_version": "1.0",
        "data_classification": "synthetic-fixture",
        "decision_cycle": _DECISION_CYCLE,
        "supported_horizons": list(_SUPPORTED_HORIZONS),
        "supported_pack_sizes": list(_SUPPORTED_PACK_SIZES),
        "by_horizon": {
            str(horizon): get_demo_state(horizon_cycles=horizon)
            for horizon in _SUPPORTED_HORIZONS
        },
        "future_values_included": False,
    }
    _write(destination / "inventory.json", inventory)

    _, trajectories = _load_fixture()
    by_id = {item.cell_id: item for item in trajectories}
    future: dict[str, Any] = {
        "schema_version": "1.0",
        "data_classification": "synthetic-fixture",
        "source": "hand-authored demo fixture; long horizons extrapolate its last two points",
        "decision_cycle": _DECISION_CYCLE,
        "by_horizon": {},
    }
    for horizon in _SUPPORTED_HORIZONS:
        target = _DECISION_CYCLE + horizon
        by_cell: dict[str, Any] = {}
        for cell_id, trajectory in sorted(by_id.items()):
            observations, truth = _synthetic_future_observations(
                trajectory,
                target_cycle=target,
                horizon_cycles=horizon,
            )
            by_cell[cell_id] = {"observations": observations, "truth": truth.to_dict()}
        future["by_horizon"][str(horizon)] = {
            "target_cycle": target,
            "by_cell": by_cell,
        }
    _write(destination / "future.json", future)

    comparisons: dict[str, Any] = {
        "schema_version": "1.0",
        "data_classification": "synthetic-fixture",
        "generated_by": "src/scripts/export_ui_demo.py",
        "future_values_used": False,
        "results": {},
    }
    for horizon in _SUPPORTED_HORIZONS:
        for pack_size in _SUPPORTED_PACK_SIZES:
            for objective in ("trajectory_aware", "current_only"):
                key = f"h{horizon}-k{pack_size}-{objective}"
                comparisons["results"][key] = run_classical_comparison(
                    horizon_cycles=horizon,
                    pack_size_k=pack_size,
                    objective_mode=objective,
                )
    _write(destination / "classical.json", comparisons)

    if include_qaoa:
        qaoa = run_live_qaoa(
            horizon_cycles=200,
            pack_size_k=4,
            objective_mode="trajectory_aware",
            shots=1024,
            reps=1,
            optimizer_mode="grid",
            max_evaluations=121,
        )
        qaoa["mode"] = "precomputed-synthetic-replay"
        qaoa["purpose"] = "UI preview only; this is not a Task 6 battery-data benchmark result."
        _write(destination / "qaoa-replay.json", qaoa)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=str(_ROOT / "web" / "data" / "demo"),
        help="directory for compact synthetic UI assets",
    )
    parser.add_argument("--skip-qaoa", action="store_true", help="omit the local synthetic QAOA replay")
    args = parser.parse_args(argv)
    export(Path(args.output), include_qaoa=not args.skip_qaoa)
    print(json.dumps({
        "output": args.output,
        "data_classification": "synthetic-fixture",
        "horizons": list(_SUPPORTED_HORIZONS),
        "pack_sizes": list(_SUPPORTED_PACK_SIZES),
        "qaoa_replay_included": not args.skip_qaoa,
        "source_fixture_classification": fixture_payload_classification(),
    }, indent=2, sort_keys=True))
    return 0


def fixture_payload_classification() -> str:
    payload, _ = _load_fixture()
    return str(payload["data_classification"])


if __name__ == "__main__":
    raise SystemExit(main())
