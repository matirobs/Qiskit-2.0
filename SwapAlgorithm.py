# optimization algorithm to find the best combination of 4 cells from a list of 86. applying quantum circuit with a classical computing frame.
# do this by not using penalization and by swapping. We have a data set

import numpy as np

NOMINAL_AH = 2.4
HORIZON = 200
n = 86

rng = np.random.default_rng(7)

protocol = rng.integers(0, 16, n)
protocol_fade = rng.lognormal(np.log(2e-4), 0.4, 16)

fade = protocol_fade[protocol] * rng.normal(1.0, 0.1, n)

print("number of fade rates:", len(fade))
for i in range(5):
    soh_now = rng.norm# optimization algorithm to find the best combination of 4 cells from a list of 86.
# applying a quantum circuit inside a classical computing frame.
# do this without penalization, by swapping.

import numpy as np

# ---------------- Step 1: stand-in data for 86 second-life cells ----------------
# (made-up numbers in realistic ranges; replaced by the real dataset later)

NOMINAL_AH = 2.4      # capacity of a brand-new cell, in amp-hours      (1b)
HORIZON = 200         # how many second-life cycles ahead we predict    (1b)
n = 86                # number of cells                                  (1b)

rng = np.random.default_rng(7)    # seed 7 = same "random" cells every run   (1c)

# each cell's first-life history: one of 16 test protocols, numbered 0-15   (1d)
protocol = rng.integers(0, 16, n)

# each protocol's typical second-life fade rate (health lost per cycle)     (1e)
protocol_fade = rng.lognormal(np.log(2e-4), 0.4, 16)

# each cell's own fade rate = its protocol's rate x a small wobble          (1f)
fade = protocol_fade[protocol] * rng.normal(1.0, 0.1, n)

# health today (SOH = capacity now / capacity new), about 0.80 for retired cells (1g)
soh_now = rng.normal(0.80, 0.02, n)

# predicted health HORIZON cycles from now                                  (1h)
soh_future = soh_now - fade * HORIZON

# numbers derived from health                                               (1i)
capacity_ah = soh_now * NOMINAL_AH                                   # Ah today
resistance = 0.045 + 0.10 * (0.80 - soh_now) + rng.normal(0, 0.002, n)  # ohms, rises as health drops

# names for the cells: SYN-01, SYN-02, ...  (SYN = synthetic)
ids = [f"SYN-{i + 1:02d}" for i in range(n)]

# ---------------- checks (delete later) ----------------
print("!! SYNTHETIC STAND-IN DATA, not real measurements !!")
print("health today:   ", round(soh_now.min(), 3), "to", round(soh_now.max(), 3))
print("health in", HORIZON, "cycles:", round(soh_future.min(), 3), "to", round(soh_future.max(), 3))
print()
print("cell     protocol  health now  health later  resistance")
for i in range(8):
    print(f"{ids[i]}   {protocol[i]:>5}     {soh_now[i]:.3f}       {soh_future[i]:.3f}       {resistance[i]:.4f}")

assert (soh_future < soh_now).all(), "health should only go down"
assert (soh_future > 0.5).all(), "nobody should reach end of life within 200 cycles"
print("\nStep 1 OK")al(0.80, 0.02, n)

print("lowest health today: ", round(soh_now.min(), 3))
print("highest health today:", round(soh_now.max(), 3))
for i in range(5):
    print("  cell", i, "health today", round(soh_now[i], 3), "fade", round(fade[i], 6))