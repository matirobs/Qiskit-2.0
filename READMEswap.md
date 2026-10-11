# RePack-Q: Swap Algorithm

Picks the best group of 4 second-life battery cells so they stay matched as they age. It uses a quantum circuit (QAOA) inside a classical optimizer loop.
Built for the Qollab × IonQ 2026 hackathon.

---

## The problem

- A pack is made of cells wired in series, so the weakest cell limits the whole pack.
- Goal: choose **K = 4** cells out of **n = 8** candidates that match well **today** and still match **after 200 cycles**.
- The 8 candidates are made in `candidates.py`, based on a real fresh cell and a real aged cell from the dataset.
- There are 70 possible packs, which is small enough to check classically and grade the quantum answer.

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

## Run it

```bash
pip install -r requirements.txt   # qiskit, numpy, scipy
python smoke_test.py              # quick check that Qiskit works
python SwapAlgorithm.py           # runs the full algorithm and prints the result
```

## What it prints

- The mismatch table between all 8 cells.
- The classical best pack, and the pack you would pick using only today's numbers.
- Checks that every measurement picks exactly 4 cells.
- The tuned angles, plus the quantum circuit's average pack score and chance of the best pack, each compared with random guessing (1 in 70).
- The top 5 measured packs and whether the quantum answer matches the classical best.
- The final pack: each cell's capacity now and in 200 cycles, and the pack's usable capacity.

## Files

| File | What it does |
| --- | --- |
| `SwapAlgorithm.py` | The swap-mixer QAOA (main algorithm) |
| `candidates.py` | Makes the 8 candidate cells |
| `cell_data.py` | Loads the fresh and aged cell data and splits it into charge and discharge |
| `health.py` | Measures how much charge each real cell holds per discharge |
| `QUBO.py` | Early quantum sketch with 4 qubits on the Aer simulator |
| `smoke_test.py` | Checks that Qiskit is installed and working |
| `Experimental_data_*.csv` | Raw fresh and aged cell measurements |

## Limitations and next steps

- Runs on a simulator only so far.
- 8 candidates (8 qubits); the full dataset needs more qubits or pre-filtering.
- The final pick is the best-scoring pack among measured shots, which is a classical step.

## Data and credits

- Cell data: Zenodo record 6985321.
- Supported by Qollab & IonQ.
