# RePack-Q benchmark results

This report summarizes 20 valid retrospective trials from `deep_sorting_reused_batteries` (derived-real). Each trial selected K=4 from N=8 at decision cycle(s) 16, with a 200-cycle prediction horizon.

## Pack outcomes

Observed pack divergence is the population CV of held-out capacity. A lower value means the selected cells were more balanced at the retrospective horizon. The usable capacity is the minimum held-out cell capacity in the selected series string.

| Method | Mean OPD | Median OPD | Mean future bottleneck (Ah) | Mean current spread (Ah) | Mean objective gap | Mean runtime (ms) |
|---|---:|---:|---:|---:|---:|---:|
| SOH sort (current-only score) | 0.07672 | 0.08256 | 1.46037 | 0.02756 | 1.79250 | 0.02189 |
| Compatibility greedy | 0.07321 | 0.07017 | 1.43518 | 0.02952 | 0.00000 | 2.30908 |
| Simulated annealing | 0.07321 | 0.07017 | 1.43518 | 0.02952 | 0.00000 | 69.27853 |
| Exact trajectory-aware | 0.07321 | 0.07017 | 1.43518 | 0.02952 | 0.00000 | 4.33836 |
| QAOA best sampled feasible pack | 0.07620 | 0.07288 | 1.42906 | 0.03026 | 0.08948 | 1509.01034 |

All runtimes were measured locally. QAOA time includes statevector parameter optimization, transpilation, and one local BasicSimulator sampling job; it does not include remote queue time.

## Objective ablation

- Exact current-only mean OPD: **0.07188**.
- Exact trajectory-aware mean OPD: **0.07321**.
- Paired mean improvement (current-only OPD minus trajectory-aware OPD): **-0.00133**; trajectory-aware had lower OPD in 7/20 trials.
- Mean future bottleneck capacity was 1.43987 Ah for current-only and 1.43518 Ah for trajectory-aware exact selection.

This ablation isolates the objective formulation from the optimizer: both selections use exact enumeration over the same candidate pool, then are evaluated against the same held-out truth. It is descriptive for this predeclared seed set; it is not a significance test.
SOH-sort objective gaps are measured against the current-only exact oracle; other classical gaps and the QAOA gap are measured against the trajectory-aware exact oracle, so gaps from different rows use different objective scales.

## QAOA diagnostics

A feasible K-cell result was sampled in 20/20 trials (mean feasible shot mass 0.29307). The exact optimum appeared in the measured samples in 85.0% of trials; mean best-sampled objective gap was 0.08948. Average parameter-optimization time was 1383.42040 ms, and average local sampling time was 12.98147 ms.

QAOA is an approximate solver here. These measurements do not establish quantum speedup; the instances are small enough for exact enumeration and classical methods.

## Predictor validation

Across 4642 valid cell-by-cutoff forecasts, the weighted recent linear model had MAE 0.11465 Ah, RMSE 0.16498 Ah, median absolute percentage error 5.55159%, and future-truth coverage 0.58685. Cutoffs within a cell overlap.

## Limits and reproducibility

The horizon uses dataset cycle indices, not calendar time. The predictor is a simple recent linear fit, and the mission does not model a household load trace or electrochemical response. Held-out truth is used only after the candidate pools and solver-visible snapshots are fixed. The 20 seeded pools are draws from one inventory and can overlap; they are not independent battery populations. The source dataset is licensed under CC BY 4.0. Generated full cell trajectories remain local to keep the repository limited to the synthetic interactive demo and aggregate replay exports; those exports contain no cell identifiers or snapshots. Any shared derived data must include attribution, a license link, and an indication of changes.

- Config SHA-256: `7cab10792735141bd72eafb4021afbcb0ee695612f6320d44cf9e3d6bd0b62f5`
- Input SHA-256: `93b5e9edba0d0fecb9de1e3bbccfdd8c46882901175ea58b77da2a3f24977b29`
- Provenance SHA-256: `69f4aa0217531db817c00528211f6862d134e4fc419105a6ff7ba3f36c4a8dd3`

Re-run with `PYTHONPATH=src python src/scripts/run_benchmarks.py --input data/processed/trajectories.json --config configs/task6_benchmark.json`.
