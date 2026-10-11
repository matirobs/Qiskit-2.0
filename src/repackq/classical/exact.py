"""Check every possible group to find the best score for a small pool."""
from itertools import combinations
from math import comb, isclose
from time import perf_counter
from .common import ranking, result


def exact_search(instance, *, max_subsets=100000, max_ties=100):
    """Enumerate fixed-size groups, recording the best score and any ties."""
    started = perf_counter()
    count = comb(len(instance.cells), instance.pack_size)
    if count > max_subsets:
        raise ValueError(f"Exact search needs {count} subsets; budget is {max_subsets}")
    if type(max_ties) is not int or max_ties < 1:
        raise ValueError("Tie recording limit must be a positive integer")
    # enumerate combinations so each fixed-size group is checked once
    groups = combinations(range(len(instance.cells)), instance.pack_size)
    best = min(groups, key=lambda group: ranking(instance, group))
    best_energy = instance.energy(best)
    tied, tie_count, worst = [], 0, best_energy
    for group in combinations(range(len(instance.cells)), instance.pack_size):
        energy = instance.energy(group)
        worst = max(worst, energy)
        if isclose(energy, best_energy, rel_tol=0.0, abs_tol=1e-9):
            tie_count += 1
            if len(tied) < max_ties:
                tied.append([instance.cells[i].cell_id for i in group])
    return result(instance, "exact", best, started, evaluated_subsets=count,
                  subset_scoring_passes=2, tied_optima=tied, tied_optima_count=tie_count,
                  tie_tolerance=1e-9, ties_truncated=tie_count > max_ties,
                  worst_feasible_objective=worst)
