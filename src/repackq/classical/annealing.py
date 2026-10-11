"""Search for a low-score group by swapping one selected cell at a time."""
import math
import random
from statistics import pstdev
from time import perf_counter
from .common import ranking, result


def simulated_annealing(instance, *, seed=11, steps=3000, restarts=4,
                        t_start=None, t_end=1e-3):
    """Keep the group size fixed; allow worse swaps less often as the search cools."""
    started = perf_counter()
    if type(steps) is not int or steps < 1 or type(restarts) is not int or restarts < 1:
        raise ValueError("Steps and restarts must be positive integers")
    costs = [instance.pair[i][j] for i in range(len(instance.cells)) for j in range(i + 1, len(instance.cells))]
    t_start = max(1.0, pstdev(costs) if costs else 1.0) if t_start is None else t_start
    if not all(math.isfinite(t) and t > 0 for t in (t_start, t_end)) or t_end > t_start:
        raise ValueError("Temperatures must be positive, finite, and decreasing")
    rng = random.Random(seed)
    size, wanted = len(instance.cells), instance.pack_size
    best = tuple(range(wanted))
    best_key = ranking(instance, best)
    accepted = proposed = 0
    for _ in range(restarts):
        selected = tuple(sorted(rng.sample(range(size), wanted)))
        energy = instance.energy(selected)
        key = ranking(instance, selected)
        if key < best_key:
            best, best_key = selected, key
        if size == wanted:
            break
        for step in range(steps):
            outside = [i for i in range(size) if i not in selected]
            removed, added = rng.choice(selected), rng.choice(outside)
            proposal = tuple(sorted((set(selected) - {removed}) | {added}))
            # No penalty is needed: a swap always selects exactly K cells.
            new_energy = instance.energy(proposal)
            temperature = t_start * (t_end / t_start) ** (step / max(1, steps - 1))
            delta = new_energy - energy
            proposed += 1
            if delta <= 0 or rng.random() < math.exp(-delta / temperature):
                selected, energy = proposal, new_energy
                accepted += 1
                key = ranking(instance, selected)
                if key < best_key:
                    best, best_key = selected, key
    return result(instance, "annealing", best, started, seed=seed, steps_per_restart=steps,
                  restarts=restarts, proposed_moves=proposed, accepted_moves=accepted,
                  t_start=t_start, t_end=t_end, returns="best visited group")
