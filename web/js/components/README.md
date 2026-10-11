# Browser/Python adapter contract

`quantumBridge.js` is the browser-facing boundary for Python work. When the
workbench is opened on `localhost`, `127.0.0.1`, or `::1`, it automatically
registers the same-origin HTTP adapter served by `run_repackq_web.py`. The
Qollab release builder adds a separate entrypoint adapter based on Qollab's
documented Python-module import and `.callPromising(...)` API. Other hosts
remain in fixture/replay mode unless a supported host bootstrap registers an
adapter.

The adapter methods correspond to these local routes:

| Browser method | Local route | Purpose |
| --- | --- | --- |
| `getCapabilities()` | `GET /api/capabilities` | Report Python and Qiskit support without starting a job. |
| `getDemoState(options)` | `GET /api/state` | Return decision-time snapshots and history only. |
| `evaluateSelection(indices, options)` | `POST /api/evaluate` | Score a manual pack before future reveal. |
| `runClassicalComparison(options)` | `POST /api/classical` | Run SOH sort, greedy, annealing, and exact enumeration. |
| `runQaoa(options)` | `POST /api/qaoa` | Stream stage events and then return measured QAOA results. |
| `revealFuture(indices, options)` | `POST /api/future` | Return held-out synthetic fixture data after explicit reveal. |

Options use the Python API names: `horizon_cycles`, `pack_size_k`,
`objective_mode`, `annealing_seed`, `annealing_steps`, `shots`, `reps`,
`optimizer_mode`, and `max_evaluations`. The QAOA progress stream is newline-
delimited JSON. Stage events invoke JS `onStage(stage)`; the final result is
returned only after a result event. A stream error rejects the call and never
substitutes a replay result.

The corresponding host-callable Python functions live in root `main.py` and
delegate to `src/repackq/ui.py`:

- `get_repackq_demo_state(**options)` returns decision-time snapshots and
  observations only.
- `evaluate_repackq_selection(indices, **options)` computes pre-reveal pack
  metrics.
- `run_repackq_classical(**options)` runs four classical methods without
  future truth.
- `run_repackq_qaoa(**options)` runs QAOA and accepts Python `on_stage`.
- `reveal_repackq_future(indices, **options)` exposes held-out values only
  after the user chooses Reveal future.

Qollab's Python project mode runs `main.py` and displays text output. The
HTML/JS release package supplies a Qollab-specific `main.js` and
`repackq_qollab_bridge.py`; it imports Python functions by module name and calls
them with `.callPromising(...)`. QAOA receives the backend selected in
Qollab's Run dialog and submits one sampling call only after the user clicks
**Run QAOA**. Live runs have completed on Qollab's built-in BasicSimulator and
AWS simulator. IonQ Aria currently fails before returning a job ID because the
Qollab runtime blocks the provider's outbound `POST` request; see
[`docs/QOLLAB_SPIKE.md`](../../../docs/QOLLAB_SPIKE.md).
The Python wrapper serializes API results as JSON strings before they cross the
runtime boundary, and the JavaScript adapter parses those strings into ordinary
browser objects.
Use `python run_repackq_web.py` locally to run the UI and Python API on one
origin. The QAOA control requires Qiskit Statevector support; classical and
reveal actions use the Python API independently of that QAOA capability.

Run `python scripts/package_qollab_release.py` to build
`qollab-task8-app.zip` and `qollab-task8-python-smoke.zip`. The first archive
is the self-contained HTML/JS app package. The second runs a synthetic p=1
QAOA trial on the local Qiskit `BasicSimulator` and prints a JSON diagnostic;
it does not submit a remote Qollab or IonQ job.
