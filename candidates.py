# candidates.py - makes 8 candidate cells based on the 2 real cells measured in health.py

import numpy as np   # numpy does math on lists of numbers

# REAL numbers measured in health.py (Zenodo 6985321)
FRESH_AH = 20.02   # capacity of the real fresh cell
AGED_AH = 16.65    # capacity of the real aged cell

real_soh = AGED_AH / FRESH_AH   # real aged cell's health (0.832)

n = 8                            # how many candidate cells
rng = np.random.default_rng(7)   # seed 7 = same cells every run

# health today: spread around the real aged cell (ASSUMPTION: spread of 0.02)
soh_now = rng.normal(real_soh, 0.02, n)

# health lost per cycle - each cell fades a bit differently (ASSUMPTION)
fade = rng.normal(0.0002, 0.00006, n)

# health after 200 more cycles
soh_future = soh_now - fade * 200

# turn health into amp-hours using the real fresh capacity
capacity_now = soh_now * FRESH_AH
capacity_future = soh_future * FRESH_AH

names = [f"C{i}" for i in range(n)]   # C0, C1, ... C7

# checks - only when running this file directly
if __name__ == "__main__":
    print("real aged cell health:", round(real_soh, 3))
    print("cell  now(Ah)  in 200 cycles(Ah)")
    for i in range(n):
        print(names[i], "  ", round(capacity_now[i], 2), "     ", round(capacity_future[i], 2))