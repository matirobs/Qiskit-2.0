# RePack-Q: Mission-Aware Quantum Recommissioning of Second-Life EV Batteries

**Match batteries by how they will age, not just how they look today.**

Two retired cells can have similar state of health (SOH) today and still follow different aging paths. RePack-Q explores whether including a simple forecast of future capacity in a battery-grouping objective can help select more balanced second-life series packs. It formulates the small selection problem as a fixed-cardinality QUBO, uses Qiskit QAOA to sample candidate packs, and compares those samples with classical methods.

RePack-Q is a retrospective optimization experiment. It is not a battery safety tool, an electrochemical digital twin, a lifetime guarantee, or evidence of quantum speedup.

## The problem

Second-life operators need to assemble groups of retired cells whose capacities remain compatible in use. Matching cells by current capacity or SOH alone may overlook differences in their aging histories. This project asks whether a leakage-free estimate of future capacity can be included in the grouping objective, then evaluates selected groups against measurements hidden from the optimizer.

The primary mission is a residential photovoltaic and time-of-use stationary-storage scenario. Its horizon is represented in dataset cycle indices; the MVP does not simulate an actual household load trace.

## Data and evaluation

The primary source is the public [Deep Sorting of Reused Batteries dataset](https://doi.org/10.5281/zenodo.14859405), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): 86 NMC/graphite cells measured during a 30-month aging campaign. RePack-Q independently preprocesses diagnostic capacity, resistance, and temperature summaries. The shipped interactive inventory is clearly labeled synthetic. The benchmark replay contains aggregate derived-real outcomes with source attribution; any reuse of derived data must link the license and identify changes.

The Task 6 retrospective benchmark used 20 fixed-seed pools, each selecting K=4 cells from N=8 at decision cycle 16 for a 200-cycle horizon. Candidate snapshots and predictions were fixed without future measurements; actual future capacity was used only for scoring. Pools are draws from one dataset inventory and may overlap.

## Hybrid architecture

```text
Deep Sorting public data
          │
          ▼
Classical diagnostic summaries
capacity · SOH · resistance · temperature
          │
          ▼
Leakage-free recent-capacity forecast
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
Measured candidate distribution and best feasible sample
          │
          ▼
Held-out future scoring and aggregate benchmark
```

For candidate binary variables `x_i`, the physical objective sums weighted squared differences between selected cells for normalized current capacity, resistance, and (in trajectory-aware mode) predicted future capacity. It adds an uncertainty penalty and a health reward. A calibrated penalty `λ(Σx_i − K)²` enforces the requested pack size. Qiskit represents the resulting QUBO as an Ising cost Hamiltonian using `x_i = (1 − Z_i)/2`.

The p=1 QAOA parameters are optimized locally with ideal Qiskit Statevector evaluations. The final measured circuit is transpiled for the Qiskit-compatible backend selected in Qollab, then submitted in one sampling job. The measured distribution comes from that selected backend: ideal simulators omit device noise, while hardware samples reflect device noise. In local development the backend is Qiskit's `BasicSimulator`. QAOA is an approximate solver; exact enumeration is practical for these N=8 instances and is included as an oracle.

## Baselines

Every benchmark pool is evaluated with SOH sorting, compatibility greedy search, simulated annealing, exact enumeration, and QAOA. An exact current-only versus exact trajectory-aware ablation isolates the objective choice from solver quality. Metrics include observed future pack divergence (population coefficient of variation), bottleneck capacity, objective gap, feasible-shot mass, and runtime.

## Results

Across the 20 retrospective trials:

- QAOA returned a feasible pack in **20/20** trials and sampled the exact optimum in **17/20 (85%)**. Mean best-sampled objective gap was **0.08948**; mean feasible shot mass was **29.3%**.
- Mean observed future divergence (OPD) was **0.07620** for the best feasible QAOA sample, **0.07321** for exact trajectory-aware selection, and **0.07672** for SOH sorting.
- The objective ablation did **not** support the hypothesis on this seed set: exact current-only mean OPD was **0.07188**, compared with **0.07321** for trajectory-aware selection. Trajectory-aware selection had lower OPD in **7/20** trials.
- Mean local runtime was about **1.51 s** for QAOA and **4.34 ms** for exact enumeration. No speedup is claimed.
- On 4,642 held-out cell-by-cutoff forecasts, the recent weighted linear predictor had **0.11465 Ah MAE**, **0.16498 Ah RMSE**, and **58.7% future-truth coverage** among 7,910 predictable decision points. Forecast cutoffs within a cell overlap.

These are descriptive results from one inventory and a fixed set of potentially overlapping pools, not independent-population estimates or a statistical significance test. See [`RESULTS.md`](RESULTS.md) for full metrics, timing definitions, provenance hashes, and limitations.

## How to run

### Local workbench

Install Python 3.10+ and the pinned dependency, then start the local app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python run_repackq_web.py
```

Open `http://127.0.0.1:8000/`. On Windows, use `Launch RePack-Q.bat`. The local app calls the Python API on the same origin. Its interactive cell data are synthetic; the benchmark panel replays aggregate derived-real results. The reveal action only reveals synthetic fixture data.

### Qollab package

Generate the standalone HTML/JS app package with:

```sh
python scripts/package_qollab_release.py
```

Upload `qollab-task8-app.zip` to Qollab in HTML/JS mode. The bundled page is self-contained and includes synthetic interaction data plus aggregate benchmark replay. Its Qollab entrypoint uses the documented JavaScript-to-Python module bridge and `.callPromising(...)` calls. Inventory, manual scoring, classical comparison, QAOA preparation, backend submission, result analysis, and explicit held-out reveal use the packaged Python API. The selected Qiskit-compatible backend is passed into QAOA preparation so Qiskit can transpile the measured circuit for that backend. After the user clicks **Run QAOA**, the bridge submits the final measured circuit and collects its counts inside a Python function invoked with `callPromising()`. Start with a simulator. The separate Qollab Python smoke package runs a synthetic QAOA check on Qiskit's local `BasicSimulator` and submits no remote job.

The Python smoke package was verified in Qollab on Python 3.14.2 and Qiskit 2.5.2, including the host-exposed local `BasicSimulator` instance. The test completed one 512-shot job with a feasible sample and no remote submission.

## Limitations

- The predictor is a simple weighted linear fit to recent capacity history; it is not a calibrated lifetime model.
- The 200-cycle horizon is not calendar time, a real residential duty trace, or electrochemical simulation.
- Dataset cycle cutoffs overlap, future-truth coverage is incomplete, and the benchmark pools may overlap.
- The trajectory-aware objective did not improve mean observed divergence in this benchmark.
- QAOA was slower than exact enumeration on these small instances. Results do not establish a quantum advantage.
- Qollab's built-in BasicSimulator and an AWS simulator have completed live QAOA runs, including the selected-backend transpilation path. The Qollab-selected IonQ Aria 1 backend was also tried through the documented Python `callPromising()` path, but `qiskit_ionq` still fails at browser `fetch` during job submission, before returning a job ID or measured counts. Qollab's runtime blocks outbound `POST` requests from project code, so IonQ hardware execution needs a Qollab-supported server-side submission path. No IonQ hardware result is claimed.
- Live support targets Qiskit-compatible backends exposed by Qollab. Other providers need a Qiskit backend adapter and a working provider network path in the Qollab runtime.
- The checked-in browser demo uses synthetic cell records. Full cell-level derived-real trajectories stay local to keep the demo compact; the source dataset is CC BY 4.0, and any shared derived data must retain attribution, link the license, and identify changes.

## Originality and dependencies

Pre-build work consisted of problem selection, dataset research, and implementation planning. Project implementation, integration, experiments, UI, and submission materials were developed during the hackathon build window. Codex was used as an AI coding assistant for implementation, debugging, and documentation. The Deep Sorting dataset is the scientific data source. Qiskit is a software dependency. The associated public code release is cited as a schema and sampling reference only; its source code was not copied. See [`ATTRIBUTION.md`](../ATTRIBUTION.md) for dataset, platform, and software references.

## Attribution and license

**This effort is supported by Qollab & IonQ**

The software is released under the [MIT License](../LICENSE). The battery dataset is separately licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The browser demo contains synthetic cell records and aggregate benchmark outcomes, not raw or cell-level real dataset records.

### References

- Wang, Gao, and Tian, [Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions](https://doi.org/10.5281/zenodo.14859405), Zenodo dataset.
- Associated public code release, [10.5281/zenodo.15350607](https://doi.org/10.5281/zenodo.15350607), cited as a research/schema reference; no source copied.
- [Qiskit API documentation](https://qiskit.qotlabs.org/docs/api/qiskit) and [Qiskit project](https://github.com/Qiskit/qiskit).
- [Qollab hackathon terms](https://qollab.xyz/programs/hackathon/terms) and [how it works](https://qollab.xyz/programs/hackathon/how-it-works).
