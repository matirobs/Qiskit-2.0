"""Baseline: select cells with the highest current state of health."""
from time import perf_counter
from .common import result


def healthiest_selection(instance):
    """Sort by current health, with stable tie-breaking by capacity and cell ID."""
    started = perf_counter()
    ordered = sorted(range(len(instance.cells)), key=lambda i: (
        -instance.cells[i].soh, -instance.cells[i].capacity_ah, instance.cells[i].cell_id))
    return result(instance, "healthiest", ordered[:instance.pack_size], started,
                  selection_rule="descending state of health, capacity, then cell identifier")
