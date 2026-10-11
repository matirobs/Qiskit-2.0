"""Convert a capacity forecast into the fields needed for group selection."""
from __future__ import annotations

from .prediction.model import CapacityModel


def predict_snapshot(model: CapacityModel, *, cell_id: str, primary_history: list[dict],
                     observed_second_life: list[dict], cutoff: int = 0, horizon: int = 200,
                     primary_protocol_ids=None) -> dict:
    """Build a selection snapshot from observed history. Capacity is in amp-hours
    and resistance is in ohms; nominal cell capacity is 2.4 amp-hours."""
    forecast = model.predict(primary_history, observed_second_life, cutoff=cutoff, horizon=horizon,
                             primary_protocol_ids=primary_protocol_ids)
    latest = max(observed_second_life or primary_history, key=lambda point: point["cycle"])
    return {"cell_id": str(cell_id), "capacity_ah": forecast["current_capacity_ah"],
            "nominal_capacity_ah": 2.4, "soh": forecast["current_capacity_ah"] / 2.4,
            "internal_resistance_ohm": latest.get("resistance_ohm"),
            "temperature_c": latest.get("temperature_c"), **forecast}
