# Saved comparison results

- `classical-first-run.json`: the first eight-candidate, four-selected comparison.
- `classical-benchmark-20-seeds.json`: every trial from the fixed 20-seed benchmark.
- `quantum-first-run.json`: one real pool with both Qiskit methods and all four
  classical methods, including actual sampling counts and solver settings.

These reports are included in Git and contain real derived battery measurements,
attributed under [data/LICENSE.md](../data/LICENSE.md). Open a report to inspect
selected cells, objective contributions, timing, and revealed future outcomes.

Generate another report without overwriting an existing one:

```bash
PYTHONPATH=src python3 -m repackq compare --output results/new-comparison.json
```

The [selection guide](../docs/guides/selection.md) explains the results and the
mixed tradeoff between future imbalance and minimum capacity. Prediction is
classical. Quantum results in the first-run report are a single local simulator
smoke test; the saved 20-seed benchmark contains classical results only.
