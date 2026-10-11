"""Pool reference histories into chronological bins for the larger model.

Optional usage summaries cover all measurement steps. Forecast targets remain
comparable reference-discharge capacities."""
from __future__ import annotations

import math
from bisect import bisect_right
from statistics import mean

from .features import FEATURE_NAMES, build_features

CHANNELS = ("capacity_mean", "capacity_min", "capacity_max", "resistance_mean",
            "temperature_mean", "cycle_fraction", "log_count", "observed")
USAGE_CHANNELS = ("current_abs_mean", "current_min", "current_max", "voltage_mean",
                  "voltage_min", "voltage_max", "temperature_mean", "temperature_min",
                  "temperature_max", "resistance_mean", "log_rows", "charge_capacity_max",
                  "discharge_capacity_max", "charge_energy_max", "discharge_energy_max", "duration_span_s")


def feature_names(spec: dict) -> list[str]:
    """Keep input names in the same order as the encoded history values."""
    channels = CHANNELS + (tuple("usage_" + name for name in USAGE_CHANNELS) if spec.get("usage") else ())
    return FEATURE_NAMES + [f"{phase}_{slot:02d}_{channel}"
        for phase in ("primary", "second") for slot in range(spec["bins"]) for channel in channels] + [
            f"primary_protocol_{identifier}" for identifier in spec.get("protocols", [])]


def _finite_mean(values):
    available = [x for x in values if x is not None and math.isfinite(x)]
    return mean(available) if available else None


def encode_phase(points: list[dict], bins: int, usage: bool) -> list:
    """Pool all observations into equal cycle-span bins, retaining empty-bin masks."""
    groups = [[] for _ in range(bins)]
    if points:
        start, end = points[0]["cycle"], points[-1]["cycle"]
        span = max(1, end - start)
        for point in points:
            groups[min(bins - 1, int((point["cycle"] - start) / span * bins))].append(point)
    values = []
    for group in groups:
        if group:
            capacity = [p["capacity_ah"] for p in group]
            values.extend([mean(capacity), min(capacity), max(capacity),
                _finite_mean([p.get("resistance_ohm") for p in group]),
                _finite_mean([p.get("temperature_c") for p in group]),
                mean((p["cycle"] - start) / span for p in group), math.log1p(len(group)), 1.0])
        else:
            values.extend([None] * 6 + [0.0, 0.0])
        if usage:
            for channel in USAGE_CHANNELS:
                # Usage records cover only the interval ending at this observation.
                values.append(_finite_mean([p.get("usage", {}).get(channel) for p in group]))
    return values


def build_full_features(primary, secondary, cutoff, horizon, spec):
    """Add pooled history to the summary features after checking the cutoff."""
    base = build_features(primary, secondary, cutoff, horizon)  # validates future boundary
    primary = sorted(primary, key=lambda p: p["cycle"])
    secondary = sorted(secondary, key=lambda p: p["cycle"])
    values = list(base.values()) + encode_phase(primary, spec["bins"], spec.get("usage", False))
    values += encode_phase(secondary, spec["bins"], spec.get("usage", False))
    if spec.get("protocols"):
        protocols = {identifier for p in primary for identifier in p.get("protocol_ids", [])}
        if not protocols:
            raise ValueError("This model requires recorded first-life protocol identifiers")
        if not protocols <= set(spec["protocols"]):
            raise ValueError("First-life protocol is outside the trained categories")
        values += [float(identifier in protocols) for identifier in spec["protocols"]]
    return dict(zip(feature_names(spec), values))


def dense_cases(cells, minimum_horizon=5, maximum_horizon=200):
    """Pair each valid cutoff with measured future capacities in range.

    Cutoff zero uses first-life history only. Later cutoffs need four known
    reference tests. Reuse each encoded history across its forecast horizons."""
    if minimum_horizon < 1 or maximum_horizon < minimum_horizon:
        raise ValueError("Invalid forecast horizon range")
    cases = []
    for cell in cells:
        secondary = sorted(cell["second_life"], key=lambda p: p["cycle"])
        cycles = [p["cycle"] for p in secondary]
        cutoffs = [0] + cycles[3:]
        for cutoff in cutoffs:
            first = bisect_right(cycles, cutoff + minimum_horizon - 1)
            last = bisect_right(cycles, cutoff + maximum_horizon)
            for future in secondary[first:last]:
                cases.append({"cell_id": cell["cell_id"], "cutoff": cutoff,
                    "horizon": future["cycle"] - cutoff, "target_cycle": future["cycle"],
                    "target_capacity_ah": future["capacity_ah"]})
    return cases


def case_features(case, cells_by_id, spec):
    """Retrieve only the history known at this case's cutoff."""
    cell = cells_by_id[case["cell_id"]]
    known = [p for p in cell["second_life"] if p["cycle"] <= case["cutoff"]]
    return build_full_features(cell["primary"], known, case["cutoff"], case["horizon"], spec)
