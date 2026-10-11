# RePack-Q

**Mission-Aware Quantum Recommissioning of Second-Life EV Batteries**

Match batteries by how they will age, not just how they look today.

RePack-Q is a hybrid optimization experiment for selecting a fixed-size series string from retired lithium-ion cells. It uses public longitudinal battery data, compares Qiskit QAOA with strong classical baselines, and evaluates held-out future capacity imbalance. It does not claim quantum speedup, predict certified pack lifetime, or determine whether a cell is safe to deploy.

The repository includes a read-only raw-data inspector and a streaming preprocessing pipeline for the primary Deep Sorting battery dataset. Zenodo lists the source dataset under CC BY 4.0; shared derived data must include attribution, a license link, and a note about changes. Full cell-level trajectories are generated locally, while the committed interactive inventory is synthetic and the benchmark replay contains aggregate results. Task 7 connects the browser workbench to the Python UI API through a local, same-origin HTTP service. The Qollab release package also includes an HTML/JS adapter built on Qollab's documented Python-module imports and `.callPromising(...)` API. See [the adapter contract](web/js/components/README.md) and [the Qollab integration notes](docs/QOLLAB_SPIKE.md).

## Problem and architecture

Two used cells with similar SOH can have different histories and future capacity trajectories. RePack-Q estimates near-term capacity from measurements available at recommissioning time, then scores fixed-size groups for current and predicted compatibility. Future measurements are kept out of optimization and used only for retrospective scoring.

```text
Public longitudinal battery data
          │
          ▼
Classical diagnostic summaries
capacity · SOH · resistance · temperature
          │
          ▼
Leakage-free capacity forecast
          │
          ▼
Classical eligibility filter
          │
          ├────────────► SOH sort · greedy · annealing · exact
          │
          ▼
Mission-weighted fixed-size QUBO
          │
          ▼
QUBO → Ising → Qiskit QAOA (p=1)
          │
          ▼
Measured feasible samples and held-out scoring
```

The QUBO minimizes weighted squared differences between selected cells for normalized present capacity, resistance, and predicted future capacity. It includes health and forecast-uncertainty terms plus a calibrated `λ(Σxᵢ − K)²` penalty for selecting exactly K cells. Qiskit QAOA optimizes parameters using an ideal local Statevector, transpiles the final measured circuit for the injected Qiskit-compatible backend, then submits one sampling job. Ideal simulators omit device noise; hardware results reflect device noise. The included local path uses `BasicSimulator`.

## Benchmark result snapshot

Task 6 evaluated 20 fixed-seed N=8, K=4 pools at cycle 16 with a 200-cycle horizon. QAOA found a feasible sample in 20/20 trials and sampled an exact optimum in 17/20; its mean best-sampled objective gap was 0.08948. Mean observed future divergence was 0.07620 for QAOA, 0.07321 for exact trajectory-aware selection, and 0.07672 for SOH sorting. The objective ablation did not support the trajectory-awareness hypothesis on these trials: exact current-only mean OPD was 0.07188 versus 0.07321 for trajectory-aware selection. Mean local QAOA runtime was about 1.51 s, compared with 4.34 ms for exact enumeration. These descriptive results do not establish a quantum speedup or a general improvement. Full metrics and limitations are in [docs/RESULTS.md](docs/RESULTS.md).

## Demo video

The 2-minute-40-second recording script is in
[`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md). It uses a live Qollab simulator
run or the local `BasicSimulator`, and distinguishes the synthetic UI fixture
from the aggregate derived-real benchmark. The public video still needs to be
recorded and published; its URL will be added after publication.

## Development setup

Use Python 3.10 or newer and install the pinned Qiskit dependency. In Windows
PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

For a Windows machine without a command-line workflow, extract
`qollab-task8-app.zip` and double-click `Launch RePack-Q.bat`. On first launch
it creates a project-local virtual environment, installs the pinned
dependency, starts the local server, and opens the browser. Keep the server
window open while using the app.

Run the deterministic local simulator smoke test and import check:

```sh
PYTHONPATH=src python -m repackq.api
PYTHONPATH=src python -m unittest discover -s tests -v
```

Start the workbench and its local Python API from the repository root:

```sh
python run_repackq_web.py
```

Open the URL printed by the server, normally `http://127.0.0.1:8000/`. The browser registers its HTTP adapter only on loopback hosts and calls the Python API on that same origin. The workbench uses checked-in, clearly synthetic cell records for interaction and solver examples; the Task 6 chart replays aggregate derived-real benchmark results. The held-out future fixture is served only through the explicit reveal API action. No CDN, external API, credential, or remote backend is required.

## Task 7: interactive workbench

The app supports mission selection, the current-only and trajectory-aware
objectives, fixture-valid horizon/pack-size controls, accessible keyboard pack
assembly, classical comparisons, a measured-state QAOA inspector, a held-out
future reveal, and the aggregate Task 6 replay. When started with
`run_repackq_web.py`, Python solver actions and QAOA run live through the local
HTTP adapter. QAOA is enabled only when the installed Qiskit runtime reports
Statevector support. When opened as static files or in a host without an
adapter, the app clearly labels its synthetic solver and QAOA examples as
precomputed replays.

The Python callables for a host adapter are in root `main.py`; their
implementation is in `src/repackq/ui.py`. The local HTTP routes and streamed
QAOA stage events are in `run_repackq_web.py`; the browser contract is in
[`web/js/components/README.md`](web/js/components/README.md).

Build both Qollab packages on Windows, macOS, or Linux with:

```sh
python scripts/package_qollab_release.py
```

The command creates `qollab-task8-app.zip` and
`qollab-task8-python-smoke.zip`. The app ZIP uses Qollab's documented
JavaScript-to-Python module bridge for live inventory, evaluation, classical
solvers, future reveal, and QAOA. QAOA uses the backend selected in Qollab's Run
dialog and is submitted only after clicking **Run QAOA**; start with a free
simulator. The synthetic replay remains available if the Python runtime is not
ready. The separate Python smoke ZIP runs a synthetic p=1 QAOA check with
Qiskit's local `BasicSimulator`, prints a JSON runtime/QAOA report, and does
not submit an IonQ or other remote job. Project-page copy, a timed video script,
and the publication checklist are in `docs/`.

The Task 5 record includes a Qollab Python-runner check using Qiskit's local
`BasicSimulator`. The Task 8 Python smoke package completed in a clean Qollab
session on Python 3.14.2/Qiskit 2.5.2, and a second run verified the host's
injected `BasicSimulator` instance. The HTML/JS bridge completed live runs on
the built-in and AWS simulators, including backend-specific transpilation. No
IonQ simulator is available in the Qollab QPU list. The
updated Aria submission was retried through Qollab's documented
`.callPromising(...)` API, but `qiskit_ionq` still fails at `requests.post()`
with Emscripten `Failed to fetch`; no submission response, job ID, or measured
counts were returned. Qollab's [runtime policy](https://qollab.xyz/learn/docs/runtime-environment)
blocks project `POST` requests, which IonQ job submission requires. Running
this provider on Qollab needs a Qollab-supported server-side submission path.
No IonQ hardware result is claimed. See
[docs/QOLLAB_SPIKE.md](docs/QOLLAB_SPIKE.md) for the exact hosted checks and
[docs/SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md) for current status.

## Primary dataset preprocessing

Download the official `Second_life_phase.zip` from [Zenodo record 10.5281/zenodo.14859405](https://doi.org/10.5281/zenodo.14859405) into `data/raw/`, then run:

```sh
python src/scripts/inspect_dataset.py --raw-root data/raw --phase second_life --summary
python src/scripts/preprocess_primary.py \
  --raw-root data/raw/Second_life_phase.zip \
  --phase second_life \
  --nominal-capacity 2.4 \
  --output data/processed/trajectories.json
```

The inspector scans raw rows without changing them. Preprocessing also reads ZIP files without extraction and writes `trajectories.json`, `provenance.json`, and `preprocessing_summary.json`. See [data/README.md](data/README.md) for sampling, schema, and attribution details. The source dataset is licensed CC BY 4.0; any redistribution of derived observations must retain attribution, link to the license, and identify changes.

## Task 3: trajectory forecasts and retrospective pools

The classical modeling layer uses the default `pv_tou` mission (200-cycle
horizon, pack size 4, minimum SOH 0.50). It fits a weighted linear regression
to the latest eight valid capacity diagnostics (minimum four), clamps positive
fade slopes to zero, clamps predictions to `[0, current capacity]`, and reports
a residual-based uncertainty proxy. `frequency_response` is exposed only as an
experimental placeholder: it uses the same model and weights and has no
frequency-response-specific degradation calibration.

Prediction functions accept only a history sequence and reject any observation
after the decision cycle. `split_history_future` creates separate history and
held-out sequences; `lookup_future_truth` accepts only the future side. Series
pack metrics include weakest-cell usable capacity, capacity spread/CV,
resistance spread, predicted divergence, observed future divergence, and the
observed future bottleneck.

After preprocessing the real dataset, predictor quality can be summarized with:

```sh
PYTHONPATH=src python src/scripts/evaluate_predictor.py \
  --input data/processed/trajectories.json \
  --output data/processed/prediction_evaluation.json
```

Generate three or more seeded retrospective candidate pools with:

```sh
PYTHONPATH=src python src/scripts/build_demo_pools.py \
  --input data/processed/trajectories.json \
  --output data/processed/demo_pools.json
```

The pool builder requires `real` or `derived-real` input and refuses the
synthetic UI fixture. It chooses a decision cycle with the largest eligible
cell count unless `--decision-cycle` is supplied. The default demo pool is the
seeded pool whose predicted pack divergence is nearest the median across the
predeclared pool set; held-out outcomes do not select it. Generated pool files
contain held-out future observations and are ignored by Git along with the
processed cell trajectories to keep full cell-level measurement tables out of the committed demo.

## Task 4: matching objective and classical solvers

`src/repackq/optimization/` implements pool-local median/IQR normalization
(with z-score and constant-feature fallbacks), the `current_only` and
`trajectory_aware` objective modes, the fixed-cardinality QUBO, and the exact
`x = (1 - Z) / 2` Ising mapping. Missing resistance or temperature values stay
missing and omit only the affected pair term. The current-only builder does
not normalize or score forecast capacity or uncertainty. QUBO cardinality
penalties are calibrated by exhaustive small-instance enumeration, and the
exact solver checks that the penalized global minimum is feasible.

The classical comparison uses SOH sorting, multi-seed compatibility greedy,
fixed-cardinality swap simulated annealing, and exact enumeration. For a real
retrospective comparison, first generate `data/processed/demo_pools.json` with
the Task 3 command above, then run:

```sh
PYTHONPATH=src python src/scripts/compare_classical.py \
  --input data/processed/demo_pools.json \
  --objective-mode trajectory_aware
```

When that local real-data export is absent, the CLI uses the checked-in
`synthetic-fixture` solely to demonstrate the solver path and labels that
output as non-scientific. Select `--objective-mode current_only` to compare
the present-state formulation with the trajectory-aware formulation under
the same candidate pool.

## Task 5: Qiskit QAOA engine

The QAOA engine verifies the QUBO-to-Ising mapping exhaustively for `N <= 12`,
builds the diagonal cost operator and p-layer X-mixer circuit, and optimizes
parameters with local Qiskit Statevector evaluations. It uses SciPy COBYLA
when available and includes a dependency-light p=1 grid/refinement fallback.
The final measured circuit is transpiled and submitted once through an injected
backend; the local demo uses Qiskit's bundled `BasicSimulator` and needs no
credentials.

After generating a real or derived-real pool export with the Task 3 commands,
run the default `N=8`, `K=4`, 1024-shot experiment locally:

```sh
PYTHONPATH=src python src/scripts/run_qaoa_demo.py \
  --input data/processed/demo_pools.json
```

The script compares the best feasible measured state against exact enumeration
and labels the pool's data classification. It refuses synthetic fixtures for
this scientific run. `run_qaoa()` also accepts a Qiskit-compatible backend
object from a host application; the Qollab runtime entry point is documented in
[docs/QOLLAB_SPIKE.md](docs/QOLLAB_SPIKE.md).

Running the root `main.py` prints Python and installed package versions, then
exits without importing Qiskit or starting a simulation. The four-cell
synthetic demo remains callable as `run_task5_toy_demo()` when a host imports
the API and requests an explicit QAOA run. This runtime check does not replace
the N=8/K=4 scientific run above.

## Task 6: reproducible benchmark

The fixed 20-seed Task 6 configuration is in
[`configs/task6_benchmark.json`](configs/task6_benchmark.json). After preprocessing
the primary dataset, run the complete local comparison with:

```sh
PYTHONPATH=src python src/scripts/run_benchmarks.py \
  --input data/processed/trajectories.json \
  --config configs/task6_benchmark.json
```

The command resumes from a fsynced JSONL checkpoint in
`data/processed/benchmark/`, writes full local aggregate outputs there, creates
small replay assets under `web/data/benchmark/`, and regenerates
[`docs/RESULTS.md`](docs/RESULTS.md). It runs SOH sorting, greedy, simulated
annealing, exact enumeration, and local p=1 QAOA, plus an exact current-only vs
trajectory-aware ablation. The web export contains three trials chosen by the
predeclared seed order and candidate size; each row contains aggregate pack
metrics, with no cell identifiers or snapshot values.

The full canonical trajectory asset stays local; the committed web export contains only aggregate benchmark outcomes. The source dataset is licensed CC BY 4.0, so any shared derived data must include attribution, link to the license, and note modifications. Rerun the command locally to regenerate the
metrics from the source asset. No Qollab backend is used by this command.

## Repository map

- `src/repackq/` — Python package, Qiskit compatibility layer/QAOA engine, and Task 7 UI API (`ui.py`).
- `src/scripts/` — dataset inspection, preprocessing, predictor evaluation, candidate-pool, classical solver comparison, local QAOA demo, and benchmark CLIs.
- `configs/task6_benchmark.json` — fixed benchmark seeds and solver settings.
- `web/data/benchmark/` — small aggregate-only benchmark replay assets.
- `web/` — zero-build accessible workbench, safe runtime probe, synthetic interaction/replay assets, and derived-real aggregate benchmark assets.
- `index.html`, `main.js`, and `styles.css` — Qollab HTML/JS preview entrypoints; the package builder creates a self-contained browser bundle from `web/js/`.
- `run_repackq_web.py` — local static-file server and same-origin Python API for the browser workbench.
- `Launch RePack-Q.bat` — Windows double-click setup and local browser launcher.
- `scripts/package_qollab_release.py` — builds the standalone Qollab app ZIP and Python runtime/QAOA smoke ZIP.
- `scripts/` — Qollab runtime introspection probe.
- `tests/` — Qiskit operator/circuit/bit-order and QAOA coverage, dataset adapter coverage, Task 3 leakage/prediction/trial metrics, Task 4 optimization, and Task 6 benchmark exports/checkpoint coverage.
- `data/raw/` — ignored location for downloaded raw datasets; no raw data is included.
- `data/processed/` — local generated trajectories, provenance, and QA report; cell-level trajectories and the per-file QA report are ignored by Git to keep full cell-level measurement tables out of the committed demo.
- `data/fixtures/synthetic_demo.json` — clearly labeled eight-cell synthetic fixture for UI development, not scientific results.
- `tests/fixtures/` — clearly synthetic adapter fixtures, not benchmark observations.

## Originality, AI assistance, and sources

Pre-build work consisted of problem selection, dataset research, and
implementation planning. Project implementation, integration, experiments,
UI, and submission materials were developed during the hackathon build window.
Codex was used as an AI coding assistant for implementation, debugging, and
documentation. The project-specific data pipeline, optimization model, QAOA
engine, benchmark, and interface are implemented in this repository. The
associated Deep Sorting code release was consulted as a schema and sampling
reference; no code from it was copied. External data and software are listed in
[`ATTRIBUTION.md`](ATTRIBUTION.md).

## License and attribution

The project is licensed under MIT. Dataset and platform references are listed in [ATTRIBUTION.md](ATTRIBUTION.md). The required attribution is: **This effort is supported by Qollab & IonQ**.
