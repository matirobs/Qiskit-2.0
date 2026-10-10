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
    print("  cell", i, "is protocol", protocol[i], "-> fade", round(fade[i], 6))