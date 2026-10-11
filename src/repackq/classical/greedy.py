"""Try each starting cell, adding the lowest-cost cell at each step."""
from time import perf_counter
from .common import ranking, result


def greedy_selection(instance):
    """Grow a group from each starting cell, then keep the best complete group."""
    started = perf_counter()
    groups = []
    evaluations = 0
    for seed in range(len(instance.cells)):
        selected = [seed]
        while len(selected) < instance.pack_size:
            remaining = [i for i in range(len(instance.cells)) if i not in selected]
            # Existing costs are constant; compare only the incremental cost.
            chosen = min(remaining, key=lambda i: (
                instance.unary[i] + sum(instance.pair[i][j] for j in selected),
                instance.cells[i].cell_id))
            evaluations += len(remaining)
            selected.append(chosen)
        groups.append(selected)
    best = min(groups, key=lambda group: ranking(instance, group))
    return result(instance, "greedy", best, started, starting_cells=len(instance.cells),
                  incremental_evaluations=evaluations)
