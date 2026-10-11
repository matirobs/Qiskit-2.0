# RePack-Q: Swap Algorithm

Picks the best group of 4 second-life battery cells so they stay matched as they age. It uses a quantum circuit (QAOA) inside a classical optimizer loop.
Built for the Qollab × IonQ 2026 hackathon.

> TODO: one or two sentences on why matching cells matters for reused batteries.

---

## The problem

- A pack is made of cells wired in series, so the weakest cell limits the whole pack.
- Goal: choose **K = 4** cells out of **n = 8** candidates that match well **today** and still match **after 200 cycles**.
- There are 70 possible packs, which is small enough to check classically and grade the quantum answer.

> TODO: say where the 8 candidates come from (made in `candidates.py` from real fresh and aged cell measurements) and the plan to scale up to the full dataset.

## How it works

| Step | What happens | Where in `SwapAlgorithm.py` |
| --- | --- | --- |
| 1. Score | Mismatch between two cells = 0.4 × (gap today)² + 0.6 × (gap in 200 cycles)². Pack score = sum over all 6 pairs. | Part 2 |
| 2. Answer key | Brute force all 70 packs to find the true best. | Part 3 |
| 3. Start state | Equal mix of every 4-cell pack (Dicke state). | Part 4 |
| 4. Cost layer | Phase on each pair of chosen cells, based on their mismatch. | Part 6 |
| 5. Swap mixer | `XXPlusYYGate` on every pair swaps cells in and out. | Part 5 |
| 6. Tune angles | Grid search, then COBYLA, minimizes the average pack score. | Part 7 |
| 7. Measure | 1024 shots; best-scoring pack measured = answer. | Part 8 |

### Why no penalty term

The swap gate only moves a "1" from one qubit to another, so every measurement has exactly 4 cells. A normal QAOA mixer can pick 3 or 5 cells and needs an extra penalty to stop that. This version does not.

> TODO: add a circuit diagram (one layer: cost layer → swap mixer).

## Run it

```bash
pip install -r requirements.txt   # qiskit, numpy, scipy
python smoke_test.py              # quick check that Qiskit works
python SwapAlgorithm.py           # runs the full algorithm and prints the result
```

## Files

| File | What it does |
| --- | --- |
| `SwapAlgorithm.py` | The swap-mixer QAOA (main algorithm) |
| `candidates.py` | Makes the 8 candidate cells |
| `health.py` | Measures the real fresh and aged cells |
| `cell_data.py` | TODO |
| `QUBO.py` | TODO (earlier penalty-based version?) |
| `smoke_test.py` | Checks that Qiskit is installed and working |
| `Experimental_data_*.csv` | Raw cell measurements |

## Results

> TODO: paste the output from `python SwapAlgorithm.py`.

| | Random guess | Quantum circuit |
| --- | --- | --- |
| Chance of best pack | 1/70 ≈ 0.014 | TODO |
| Average pack score | TODO | TODO |

- Best pack found: TODO
- Matches classical best? TODO
- Spread after 200 cycles: TODO Ah (vs. TODO Ah for the today-only pack)

## Limitations and next steps

- Runs on a simulator only so far.
- 8 candidates (8 qubits); the full dataset needs more qubits or pre-filtering.
- The final pick is the best-scoring pack among measured shots, which is a classical step.
- TODO: anything else the team wants to add.

## Team

TODO: names and roles.

## Data and credits

- Cell data: Zenodo 6985321 (TODO: full citation and license).
- Supported by Qollab & IonQ.

