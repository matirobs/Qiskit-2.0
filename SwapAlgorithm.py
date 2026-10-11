# optimization algorithm to find the best combination of 4 cells from a list of 86. applying quantum circuit with a classical computing frame.
# do this by not using penalization and by swapping. We have a data set

import numpy as np   # math on lists of numbers
from itertools import combinations   # makes every possible group of cells

# get the 8 candidate cells from candidates.py
from candidates import names, capacity_now, capacity_future

n = len(names)   # 8 cells to choose from
K = 4            # cells in one pack


# ---------- Part 4: mismatch between every pair of cells ----------

# difference between every pair of cells (makes an 8 x 8 table)
diff_now = capacity_now[:, None] - capacity_now[None, :]
diff_future = capacity_future[:, None] - capacity_future[None, :]

# mismatch = difference squared (always positive, big gaps count extra)
# more weight on the future, bc cells should STAY matched
mismatch = 0.4 * diff_now ** 2 + 0.6 * diff_future ** 2


# score for a whole pack,     add up the mismatch of every pair inside it (lower = better)
def pack_score(pack):
    score = 0
    for i in pack:
        for j in pack:
            if i < j:                       # count each pair once
                score += mismatch[i, j]
    return score


# checks
print("mismatch table (rounded):")
print(np.round(mismatch, 3))
print("C3 vs C5 mismatch:", round(mismatch[3, 5], 4))
print("score of pack C0, C1, C2, C3:", round(pack_score([0, 1, 2, 3]), 4))


# every way to pick 4 cells out of 8
all_packs = list(combinations(range(n), K))
print("\nnumber of possible packs:", len(all_packs))

# best pack = the one with the lowest score
best_pack = min(all_packs, key=pack_score)
print("best pack:", [names[i] for i in best_pack], "score", round(pack_score(best_pack), 4))


# for comparison: pick a pack using ONLY today's numbers (ignoring the future)
def today_score(pack):
    score = 0
    for i in pack:
        for j in pack:
            if i < j:
                score += diff_now[i, j] ** 2
    return score

today_pack = min(all_packs, key=today_score)
print("pack chosen by today only:", [names[i] for i in today_pack])


# how far apart each pack's cells end up after 200 cycles (smaller = stays matched)
def future_spread(pack):
    future = capacity_future[list(pack)]
    return future.max() - future.min()

print("\nafter 200 cycles, spread between strongest and weakest cell:")
print("  our pack (now + future):", round(future_spread(best_pack), 3), "Ah")
print("  today-only pack:        ", round(future_spread(today_pack), 3), "Ah")