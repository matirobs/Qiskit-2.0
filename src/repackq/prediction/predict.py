"""Predict capacity for a recorded cell using only history through the cutoff."""
import argparse
import json
from pathlib import Path

from repackq.api import predict_snapshot
from .model import CapacityModel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("models/capacity_model.json"))
    parser.add_argument("--data", type=Path, default=Path("data/processed/cell_histories.json"))
    parser.add_argument("--cell", required=True, help="Recorded Battery_ID, not the filename")
    parser.add_argument("--cutoff", type=int, default=0)
    parser.add_argument("--horizon", type=int, default=200)
    args = parser.parse_args()
    data = json.loads(args.data.read_text())
    cells = [cell for cell in data["cells"] if cell["cell_id"] == args.cell]
    if not cells:
        parser.error(f"Unknown recorded Battery_ID: {args.cell}")
    cell = cells[0]
    observed = [point for point in cell["second_life"] if point["cycle"] <= args.cutoff]
    result = predict_snapshot(CapacityModel.load(args.model), cell_id=cell["cell_id"],
                              primary_history=cell["primary"], observed_second_life=observed,
                              cutoff=args.cutoff, horizon=args.horizon, primary_protocol_ids=cell.get("protocol_ids"))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
