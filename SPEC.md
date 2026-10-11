# RePack-Q — Technical Product & Implementation Specification

**Project:** RePack-Q: Mission-Aware Quantum Recommissioning of Second-Life EV Batteries  
**Primary hackathon track:** Qollab × IonQ 2026 — Quantum Impact  
**Implementation target:** Qollab JS/Qiskit project using Qiskit, local classical/statevector computation, and Qollab-provided free backends  
**License:** MIT  
**Status:** Pre-build implementation specification  
**Primary audience:** Codex or another coding agent executing the project across multiple independent sessions  
**Source of truth:** This document. If implementation decisions conflict with ad-hoc chat instructions, update this specification first or explicitly document the deviation in `DECISIONS.md`.

---

## 0. Executive mandate

Build a polished, reproducible, hackathon-ready hybrid quantum-classical application that answers a narrow, technically defensible question:

> **Can a Qiskit QAOA subroutine select groups of retired lithium-ion cells that are not only well matched at recommissioning time, but are also more likely to remain balanced over a defined second-life stationary-storage horizon?**

The application must use real public battery-aging data, must compare the quantum result against strong classical baselines, must avoid claiming quantum speedup, and must make the quantum contribution visible and understandable to judges.

The product name is **RePack-Q**. The preferred submission subtitle is:

> **Mission-Aware Quantum Recommissioning of Second-Life EV Batteries**

Preferred tagline:

> **Match batteries by how they will age, not just how they look today.**

The MVP will model a **single fixed-size series string**. A classical eligibility stage narrows a larger inventory to a small candidate pool. QAOA then solves the discrete subset-selection problem. Classical postprocessing evaluates the selected pack using physically interpretable metrics and, where longitudinal ground truth exists, reveals future observations that were intentionally hidden from the optimizer.

This is not an electrochemical digital twin, a BMS controller, or a claim of quantum advantage. It is a **trajectory-aware battery recommissioning optimization experiment with a polished interactive visualization**.

---

## 1. Hackathon compliance constraints

The implementation must remain aligned with the Qollab 2026 hackathon terms as verified on October 9, 2026.

Required constraints:

1. Use **Qiskit**.
2. Run on Qollab's free simulators, including the free IonQ simulator path.
3. Publish the project on Qollab under an **MIT license**.
4. Any external repository required by the project must also be MIT licensed.
5. Follow industry UI accessibility best practices.
6. Include a project page explaining the problem, approach, how to run it, results, limitations, and reproducibility.
7. Include a public 2–3 minute demo video.
8. Include exact attribution text: **“This effort is supported by Qollab & IonQ”**.
9. Go beyond tutorial-level work through a novel domain formulation, comparative benchmarking, and at least one technical extension/analysis.
10. Use a relevant public dataset and a strong classical baseline, consistent with the Quantum Impact theme.

Qollab timeline relevant to development:

- Build window starts: **October 9, 2026 at 19:00 ET**.
- Submission deadline: **October 11, 2026 at 19:00 ET**.

### 1.1 Pre-build originality disclosure

This `SPEC.md` is planning work prepared before implementation. The coding agent must not pretend that pre-existing planning or external source code was created during the build window. The final README/project page must include an originality disclosure stating approximately:

> “Pre-build work consisted of problem selection, dataset research, and implementation planning. Project implementation, integration, experiments, UI, and submission artifacts were developed during the hackathon build window. Public datasets, Qiskit, and cited open-source references were used as dependencies or research references and are attributed.”

Do not copy third-party battery sorting code into the submission unless its license is verified and reuse is explicitly disclosed. Prefer implementing the project-specific pipeline independently.

---

## 2. Product definition

### 2.1 Core user story

A second-life battery operator has an inventory of retired NMC cells. The cells may have similar present-day state of health but different aging histories. The operator wants to build a small stationary-storage series pack for a specified second-life duty scenario. RePack-Q evaluates candidate cells, estimates short-horizon degradation trajectories using only information available at recommissioning time, constructs a mission-weighted compatibility QUBO, runs Qiskit QAOA to select a fixed-size subset, and compares that selection with classical methods.

The user can then “reveal the future” on a retrospective benchmark trial and see whether the selected cells actually remained balanced in the real recorded data.

### 2.2 Primary mission profile

The default mission is:

**Residential PV + time-of-use stationary storage**

For the MVP, “mission-aware” means the mission controls:

- prediction/evaluation horizon,
- weight assigned to future capacity divergence,
- optional temperature-risk multiplier if reliable temperature features are available,
- required pack size,
- minimum health eligibility.

It does **not** mean the MVP simulates electrochemical response to an arbitrary second-by-second household load trace. Full load-profile-conditioned degradation is a stretch feature.

### 2.3 Default optimization instance

- Candidate pool size `N = 8`.
- Selected series pack size `K = 4`.
- Benchmark scaling targets: `N = 6, 8, 10, 12`, with `K` configurable but normally 3–5.
- Quantum qubits: one binary variable / one qubit per candidate cell.
- QAOA depth: `p = 1` for MVP.
- Default shots: `1024`, configurable to `512` or `2048` if runtime requires.

### 2.4 Non-goals

Do not implement these as MVP requirements:

- full EV pack topology optimization,
- multi-string series-parallel pack design,
- cell balancing control,
- charging firmware,
- thermal runaway/safety certification,
- electrochemical PDE models,
- PyBaMM integration,
- deep neural networks/LSTMs for degradation prediction,
- quantum speedup claims,
- 86-qubit QAOA over the complete inventory,
- live cloud services other than the backend exposed by Qollab,
- external API calls required at runtime,
- a backend server that judges must deploy separately.

---

## 3. Scientific framing

### 3.1 Hypothesis

Traditional second-life screening often emphasizes present-day explicit features such as capacity, SOH, and internal resistance. Two cells can look similar at recommissioning time while following different subsequent degradation trajectories.

RePack-Q tests this hypothesis:

> **Including a simple estimate of future degradation divergence in the combinatorial selection objective can produce groups with lower observed future imbalance than selection based only on current SOH/capacity. QAOA can approximate this fixed-size grouping objective on small instances and can be quantitatively compared with classical methods.**

### 3.2 Defensible claim boundary

Allowed claims:

- QAOA is used as the quantum subroutine for the discrete grouping problem.
- The project explores trajectory-aware selection.
- The algorithm can be compared with exact and heuristic classical baselines.
- If results support it, trajectory-aware objectives can reduce future divergence relative to naive present-state sorting on retrospective trials.

Disallowed/unsubstantiated claims:

- “Quantum computers are faster for battery sorting.”
- “QAOA outperforms classical optimization at scale.”
- “This system extends battery life by X%” unless that percentage is directly produced by this implementation under a clearly defined metric.
- “These selected cells are safe to deploy.”
- “The mission model predicts real residential pack lifetime.”

### 3.3 Research-mode experiment

The main experiment is a **retrospective recommissioning test**:

1. Select a real battery and a recommissioning cutoff `t0` or second-life early-cycle window.
2. Hide all observations after `t0` from the optimizer.
3. Build features only from data at or before `t0`.
4. Estimate each candidate's future capacity at `t0 + H` using a simple leakage-free predictor.
5. Build a candidate pool.
6. Run SOH sorting, compatibility greedy, simulated annealing, exact enumeration, and QAOA.
7. Evaluate each algorithm using current-state metrics and predicted divergence.
8. Reveal actual measured capacity at/near `t0 + H`.
9. Compute observed future divergence and realized bottleneck capacity.
10. Repeat across multiple candidate pools / seeds.

The UI demo should expose one or several representative benchmark trials, but the underlying benchmark runner must support batch evaluation so the project is not dependent on a single cherry-picked example.

---

## 4. Dataset strategy

### 4.1 Primary required dataset

**Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions**  
Zenodo DOI: `10.5281/zenodo.14859405`  
Associated public code release DOI: `10.5281/zenodo.15350607`

Dataset facts relevant to this project:

- 86 NMC(532)/graphite cells, nominal 2.4 Ah.
- 30-month aging campaign.
- >88,000 charge-discharge cycles.
- ~145 million recorded datapoints.
- Primary-use phase: 16 distinct protocols until approximately 80% SOH.
- Second-life phase: standardized protocol until approximately 50% SOH.
- Recorded signals include voltage, current, internal resistance, and surface temperature.
- Diagnostic cycles include capacity and resistance measurements.
- Cells 61 and 62 are unavailable/damaged and must not be assumed present.

This dataset is the **only dataset required for the core retrospective benchmark**.

### 4.2 Secondary validation dataset

**NASA Randomized and Recommissioned Battery Dataset**

Use as an optional independent validation path because it includes:

- 26 two-cell 18650 packs,
- constant and randomized loading,
- capacity/current/degradation/temperature/voltage signals,
- second-life packs assembled from surviving aged cells.

The NASA adapter must be architecturally isolated. Failure to complete NASA ingestion must not block the primary submission.

### 4.3 Mission-context / robustness datasets

These are research references or stretch adapters, not MVP dependencies:

- Loughborough long-term second-life “sweat testing” dataset — multiple stationary-storage use cases including PV, PV+TOU, TOU, FFR, EFR, and day-ahead trading.
- CALCE battery archive — useful for temperature sensitivity and dynamic loading context.
- Oxford path-dependent degradation datasets — useful for motivating why present SOH alone does not define future trajectory.
- Other recent second-life datasets may be cited only if provenance and license are verified.

### 4.4 No naive cross-dataset merging

Do **not** concatenate cells from different datasets into one optimization population unless chemistry, form factor, nominal capacity, test conditions, and feature definitions are explicitly harmonized. Cross-dataset use is for validation or contextualization, not for pretending unlike cells are physically interchangeable.

### 4.5 Runtime dataset packaging

The raw primary dataset is several GB and cannot be a runtime dependency inside Qollab. Implement two layers:

**Offline preprocessing layer**

- Downloads/reads official raw files locally.
- Produces a compact canonical dataset containing only fields required by RePack-Q.
- Records provenance and checksums.

**Qollab runtime layer**

- Loads a compact checked-in processed JSON/CSV asset.
- Requires no network access.
- Contains enough real derived observations to run the demo and benchmark.

Before checking processed real-data records into the public project, verify the dataset's redistribution/license terms. If redistribution is ambiguous, use one of these fallbacks:

1. Package only derived aggregate/features allowed by the license and provide preprocessing instructions.
2. Package a small explicitly attributed sample if permitted.
3. If necessary, package a synthetic demo fixture generated from documented ranges **only for UI development**, while the final scientific benchmark must still be produced from the public dataset and included as exported results with provenance.

The final app must clearly distinguish `real`, `derived-real`, and `synthetic-fixture` data sources.

---

## 5. Canonical data model

All optimization code must depend on canonical schemas, not raw column names.

### 5.1 `CellObservation`

```python
@dataclass(frozen=True)
class CellObservation:
    cell_id: str
    protocol_id: str | None
    phase: Literal["primary", "second_life", "unknown"]
    cycle_index: int
    timestamp_s: float | None
    capacity_ah: float | None
    internal_resistance_ohm: float | None
    temperature_c: float | None
    voltage_v: float | None
    current_a: float | None
    source_dataset: str
```

Observations may be diagnostic-cycle summaries rather than raw 1 Hz records. The core optimizer should never require full raw traces.

### 5.2 `CellSnapshot`

Snapshot at decision time `t0`:

```python
@dataclass(frozen=True)
class CellSnapshot:
    cell_id: str
    protocol_id: str | None
    cycle_index: int
    capacity_ah: float
    nominal_capacity_ah: float
    soh: float
    internal_resistance_ohm: float | None
    temperature_c: float | None
    recent_capacity_slope_ah_per_cycle: float
    predicted_capacity_ah: float
    prediction_uncertainty_ah: float
    horizon_cycles: int
    source_dataset: str
```

`soh = capacity_ah / nominal_capacity_ah` unless the dataset provides a more authoritative normalized capacity definition. Record the chosen convention in provenance metadata.

### 5.3 `FutureTruth`

```python
@dataclass(frozen=True)
class FutureTruth:
    cell_id: str
    target_cycle_index: int
    actual_capacity_ah: float
    actual_internal_resistance_ohm: float | None
    nearest_cycle_distance: int
```

Future truth must never be passed into candidate scoring or QUBO construction.

### 5.4 `MissionProfile`

```python
@dataclass(frozen=True)
class MissionProfile:
    id: str
    label: str
    horizon_cycles: int
    pack_size_k: int
    minimum_soh: float
    current_capacity_weight: float
    resistance_weight: float
    future_capacity_weight: float
    health_reward_weight: float
    uncertainty_weight: float
    temperature_weight: float
    description: str
```

MVP default:

```text
id: pv_tou
horizon_cycles: 200
pack_size_k: 4
minimum_soh: 0.50
current_capacity_weight: 0.30
resistance_weight: 0.20
future_capacity_weight: 0.35
health_reward_weight: 0.10
uncertainty_weight: 0.05
temperature_weight: 0.00 by default unless robust temperature summary exists
```

Weights are model assumptions, not universal physical constants. They must be normalized and exposed in an “Assumptions” UI panel.

### 5.5 `CandidatePool`

```python
@dataclass(frozen=True)
class CandidatePool:
    pool_id: str
    decision_cycle: int
    horizon_cycles: int
    candidate_ids: tuple[str, ...]
    snapshots: tuple[CellSnapshot, ...]
    future_truth: tuple[FutureTruth, ...] | None
    seed: int
```

### 5.6 `OptimizationResult`

```python
@dataclass
class OptimizationResult:
    algorithm: str
    selected_indices: list[int]
    selected_cell_ids: list[str]
    feasible: bool
    objective_value: float
    current_capacity_spread_ah: float
    current_capacity_cv: float
    resistance_spread_ohm: float | None
    usable_pack_capacity_ah: float
    predicted_pack_divergence: float
    observed_pack_divergence: float | None
    observed_usable_capacity_ah: float | None
    runtime_ms: float
    metadata: dict[str, Any]
```

### 5.7 `BenchmarkTrial`

Must contain:

- pool definition,
- normalization statistics,
- weights,
- every algorithm result,
- exact optimum,
- QAOA raw counts/probabilities,
- QAOA parameters,
- circuit depth/width after transpilation if available,
- backend label,
- random seeds,
- timings,
- data provenance.

Serialize benchmark trials to JSON so the UI can replay benchmark results without rerunning expensive optimization.

---

## 6. Primary dataset preprocessing

### 6.1 Adapter design

Create `src/data/adapters/deep_sorting.py` with explicit raw-column alias handling. The associated public reference code indicates fields such as:

- `Battery_ID` / battery number,
- `Protocol_ID`,
- `Step_Index`,
- `Step_Time(s)`,
- `Voltage(V)`,
- `Current(A)`,
- `Charge_Capacity(Ah)`,
- `Discharge_Capacity(Ah)`,
- `Internal_Resistance(Ohm)`,
- `Aux_Temperature_1(C)`.

Do not hardcode a single spelling without validation. Add a `resolve_column(df, aliases)` utility and fail with a descriptive exception if required fields are missing.

### 6.2 Feature scope for MVP

Do not reproduce the source paper's 108-feature deep sorting model. RePack-Q intentionally uses a smaller interpretable feature set:

- current diagnostic discharge capacity,
- normalized SOH,
- current internal resistance when available,
- recent capacity fade slope,
- predicted capacity at horizon,
- prediction uncertainty,
- optional average or diagnostic temperature.

This is both easier to explain and keeps the novel contribution focused on quantum subset selection rather than duplicating the paper's classifier.

### 6.3 Diagnostic cycle extraction

Implement dataset inspection first. Do not assume fixed `Step_Index` values globally until verified on representative primary and second-life files.

The adapter should:

1. Discover cell files.
2. Read metadata / column names.
3. Identify cycle identifiers and diagnostic cycles.
4. Extract per-cycle final discharge capacity.
5. Extract a representative internal resistance measurement from the corresponding diagnostic sequence.
6. Extract temperature summary if reliable.
7. Sort by cycle index.
8. Remove clearly invalid rows (`NaN`, negative capacity, nonpositive resistance).
9. Emit canonical `CellObservation` summaries.

A `--inspect` CLI must print the discovered schema, unique step indices, example ranges, and number of valid diagnostic observations before bulk processing.

### 6.4 Data quality rules

Minimum validation:

- capacity must be `> 0` and plausibly `< 1.25 * nominal_capacity` unless source metadata justifies another range,
- resistance must be `> 0` and finite,
- cycles must be strictly sortable,
- duplicate diagnostic entries must be resolved deterministically,
- cells with insufficient historical points for trajectory estimation are excluded from trajectory-aware pools but may remain usable in current-state-only tests,
- future-truth lookup must require an observation within configurable tolerance of the target horizon.

Default future target tolerance:

```text
max_future_cycle_error = max(5 cycles, round(0.05 * H))
```

If no actual measurement exists within tolerance, the cell is ineligible for retrospective trial generation at that `t0`.

### 6.5 Leakage prevention

This is a hard requirement.

Any function that builds `CellSnapshot` at `t0` receives only observations where `cycle_index <= t0`. It must not receive the full trajectory and then slice internally in a way that could accidentally leak future statistics.

Recommended API:

```python
history = trajectory.history_through(t0)
future = trajectory.future_truth_near(t0 + H)
snapshot = build_snapshot(history=history, horizon=H)
```

Add a unit test proving that mutating observations after `t0` does not change the snapshot or predicted capacity.

---

## 7. Degradation trajectory estimator

### 7.1 MVP model

Use a simple, interpretable leakage-free model based on recent capacity history.

Default algorithm:

1. Take the latest `W` valid capacity observations at or before `t0`; default `W = 8` diagnostic points, minimum 4.
2. Convert cycle indices to relative `x = cycle - t0` so the latest point is near zero.
3. Fit a weighted least-squares line `capacity = a + b*x` using NumPy only.
4. Weight newer observations more heavily with exponentially decaying or linearly increasing weights.
5. Clamp positive capacity slope to zero unless positive recovery is scientifically justified; capacity predictions should not increase simply because of short-term noise.
6. Predict `C_hat(t0+H) = C_now + b*H`.
7. Clamp prediction to `[0, C_now]` for MVP.
8. Estimate uncertainty from weighted residual standard deviation propagated with a simple horizon multiplier.

Suggested weights for `m` historical points, oldest to newest:

```python
weights = np.linspace(0.5, 1.0, m)
```

### 7.2 Fallback slope estimator

If weighted regression is numerically unstable, use median pairwise slope across recent observations. This fallback must be deterministic and unit tested.

### 7.3 Uncertainty

MVP uncertainty need not be a statistically rigorous prediction interval. It is a model-risk proxy used only as a mild optimization penalty and UI indicator.

Example:

```text
sigma_pred = residual_std * sqrt(1 + H / max(history_span_cycles, 1))
```

Cap uncertainty to a sensible fraction of nominal capacity to prevent single outliers from dominating.

### 7.4 Prediction evaluation

Report prediction quality separately from optimization quality:

- MAE at horizon,
- RMSE at horizon,
- median absolute percentage error only if denominator behavior is safe,
- coverage of available retrospective trials.

The project should not hide a weak predictor. If the simple predictor performs poorly, the project can still compare current-state versus trajectory-aware selection and discuss the limitation.

---

## 8. Candidate filtering and trial generation

### 8.1 Why filtering is classical

Safety/eligibility constraints that are deterministic should remain classical. Quantum resources are used for the combinatorial choice among feasible candidates.

### 8.2 Eligibility rules

A candidate must satisfy:

- same dataset/chemistry group for a trial,
- valid current capacity,
- `SOH >= mission.minimum_soh`,
- sufficient recent history for trajectory prediction,
- valid future truth when generating retrospective benchmark trials,
- valid resistance if resistance weighting is enabled.

Do not reject a cell because it is merely “worse” than other candidates; the optimizer should make comparative decisions.

### 8.3 Pool construction

Provide two modes:

**Benchmark mode**
- deterministically sample `N` eligible cells using seeded PRNG,
- enforce enough health heterogeneity to avoid trivial all-identical pools,
- optionally stratify by first-life protocol ID.

**Demo mode**
- use one curated but non-fabricated pool selected from benchmark candidates because it demonstrates the bottleneck problem clearly,
- store `pool_id` and provenance so it is reproducible,
- never modify actual future outcomes to make QAOA look better.

### 8.4 Anti-cherry-picking rule

The final reported aggregate results must include a predeclared set of seeds (for example 20 or 30 trials). The demo may highlight one representative trial, but the README must state aggregate metrics across all benchmark trials.


---

## 9. Optimization model

### 9.1 Binary decision variables

For `N` candidate cells define:

```text
x_i = 1 if candidate i is selected
x_i = 0 otherwise
```

Exactly `K` cells should be selected.

### 9.2 Feature normalization

Never mix raw Ah, ohms, and unitless SOH directly in pairwise penalties.

For each candidate pool, normalize each feature across the pool. Prefer robust scaling when enough points exist:

```text
z_i = (v_i - median(v)) / max(IQR(v), epsilon)
```

Fallback to z-score if `IQR < epsilon`:

```text
z_i = (v_i - mean(v)) / max(std(v), epsilon)
```

If the feature is effectively constant across the pool, set all normalized values to zero and record that the feature contributed no discrimination.

Use `epsilon = 1e-9`.

Normalize these independently:

- current capacity,
- internal resistance,
- predicted future capacity,
- optional temperature feature,
- prediction uncertainty if used pairwise (normally uncertainty is a unary penalty).

SOH reward may be normalized to `[0, 1]` over the physically valid range or left as unitless SOH if bounded.

### 9.3 Pairwise mission incompatibility

For candidates `i` and `j` define:

```text
D_ij =
    w_current * (Cz_i - Cz_j)^2
  + w_resistance * (Rz_i - Rz_j)^2
  + w_future * (Fz_i - Fz_j)^2
  + w_temperature * (Tz_i - Tz_j)^2
```

Terms unavailable or disabled for the mission contribute zero.

All `D_ij` values must be finite and nonnegative.

### 9.4 Unary cell value / risk

Define a unary reward/penalty:

```text
U_i = - w_health * normalized_soh_i
      + w_uncertainty * normalized_uncertainty_i
```

Because the objective is minimized, better SOH lowers energy and higher uncertainty raises energy.

### 9.5 Fixed-cardinality penalty

The intended cardinality constraint is:

```text
sum_i x_i = K
```

Encode:

```text
P_cardinality = A * (sum_i x_i - K)^2
```

Using `x_i^2 = x_i`:

```text
P_cardinality =
    A * (1 - 2K) * sum_i x_i
  + 2A * sum_{i<j} x_i x_j
  + A*K^2
```

The constant `A*K^2` does not affect the optimizer but must be retained if comparing reconstructed Hamiltonian energies with original QUBO objective values.

### 9.6 Final QUBO

Minimize:

```text
E(x) = sum_{i<j} D_ij x_i x_j
     + sum_i U_i x_i
     + A (sum_i x_i - K)^2
```

Equivalent coefficient form:

```text
linear_i = U_i + A*(1 - 2K)
pair_ij  = D_ij + 2A
constant = A*K^2
```

### 9.7 Penalty magnitude selection

A too-small cardinality penalty produces infeasible high-quality-looking bitstrings. A wildly large penalty can distort the energy landscape and make QAOA harder.

Use an adaptive deterministic penalty:

```text
base_pair_scale = max(1.0, max(D_ij), max(abs(U_i)))
A = penalty_multiplier * base_pair_scale
```

Default `penalty_multiplier = 4.0`.

Before running QAOA, exact enumeration must verify that the global minimum of the penalized QUBO is feasible. If not, multiply `A` by 2 and retry up to 5 times. Record the final `A`.

This exact feasibility calibration is cheap for the small `N` used in the demo and prevents a common QAOA implementation failure.

### 9.8 Objective variants

Implement two named objective modes:

**`current_only`**

- current capacity mismatch,
- resistance mismatch,
- SOH reward,
- no future-capacity term.

**`trajectory_aware`**

- current capacity mismatch,
- resistance mismatch,
- predicted future-capacity mismatch,
- SOH reward,
- uncertainty penalty.

The UI and benchmark must be able to compare these objective formulations independently of the solver. This is central to separating “is trajectory awareness useful?” from “how good is QAOA?”.

---

## 10. QUBO to Ising Hamiltonian mapping

### 10.1 Mapping convention

Use:

```text
x_i = (1 - Z_i) / 2
```

For a QUBO:

```text
E(x) = c + sum_i l_i x_i + sum_{i<j} q_ij x_i x_j
```

the Ising form is:

```text
H = offset * I + sum_i h_i Z_i + sum_{i<j} J_ij Z_i Z_j
```

with:

```text
J_ij = q_ij / 4
h_i  = -l_i/2 - sum_{j != i} q_min(i,j),max(i,j) / 4
offset = c + sum_i l_i/2 + sum_{i<j} q_ij/4
```

### 10.2 Verification requirement

Implement `verify_ising_equivalence()` that exhaustively checks every bitstring for `N <= 12`:

```text
abs(QUBO(x) - IsingEnergy(x)) < 1e-9
```

This verification runs in unit tests and once during development on representative instances.

Do not proceed to QAOA if mapping verification fails.

### 10.3 Qiskit operator

Construct the cost Hamiltonian with `qiskit.quantum_info.SparsePauliOp` or the current equivalent supported by the installed Qiskit version.

Because Qiskit APIs may differ slightly across versions, create a compatibility wrapper in:

```text
src/quantum/qiskit_compat.py
```

No other module may directly depend on fragile version-specific constructors.

The compatibility wrapper must expose stable project APIs such as:

```python
def build_cost_operator(ising: IsingModel) -> SparsePauliOp: ...
def build_qaoa_ansatz(cost_operator, reps: int): ...
def get_statevector(circuit): ...
def transpile_for_backend(circuit, backend): ...
```

Task 1 must inspect the exact Qiskit/Qollab versions available and pin behavior accordingly.

---

## 11. Qiskit QAOA implementation

### 11.1 QAOA depth

MVP:

```text
p = 1
```

Stretch benchmark:

```text
p = 1, 2, 3
```

Do not let p>1 delay the MVP.

### 11.2 Initial state

Standard QAOA initial state is the uniform superposition produced by Hadamards unless the chosen Qiskit ansatz creates it internally.

MVP uses penalty-based standard X-mixer QAOA.

Stretch only: implement a fixed-Hamming-weight initial state + XY mixer that preserves cardinality. This is not required for submission unless all core features are complete.

### 11.3 Parameter convention

For p=1, maintain a stable internal representation:

```python
QAOAParams(gamma=[...], beta=[...])
```

Do not rely on arbitrary Qiskit parameter ordering. Query the ansatz parameter objects and bind them through a project-owned mapping. Add a unit test that changing gamma and beta produces different expected energies.

### 11.4 Parameter optimization strategy

The project must not require repeated IonQ backend jobs during classical optimization.

Primary strategy:

1. Build the parameterized QAOA circuit locally.
2. Evaluate expected cost with `Statevector` for candidate parameter values.
3. Optimize parameters classically.
4. Bind the best parameters.
5. Add measurements.
6. Transpile for the Qollab-provided backend.
7. Submit the final circuit for sampling.

Preferred optimizer when SciPy is confirmed available:

- `COBYLA` for p=1/p=2,
- deterministic seed/initial point.

Mandatory fallback requiring only NumPy/Python:

**coarse-to-fine grid + coordinate refinement**

For p=1:

- gamma search domain `[0, 2π)`;
- beta search domain `[0, π)`;
- coarse 12×8 grid;
- choose best point;
- refine around it for 3 rounds with shrinking step size.

This fallback must be fully implemented even if SciPy works, because it makes the project portable in a browser/Pyodide environment.

### 11.5 Multi-start behavior

For p=1, optional multi-start:

- deterministic initial points `[0.25π, 0.125π]`, `[0.75π, 0.25π]`, and one seeded pseudo-random point,
- keep best expected energy.

For the hackathon runtime, cap optimization evaluations to a configurable budget to avoid UI stalls.

### 11.6 Statevector objective

The local objective must use the cost Hamiltonian expectation value:

```python
energy = real(state.expectation_value(cost_operator))
```

If Qiskit `Statevector` behavior in the Qollab runtime is unavailable, fallback options in order:

1. Qollab local free simulator with repeated local jobs if allowed.
2. Pure NumPy statevector for the small p=1 circuit **only if necessary** and clearly documented; the project must still use Qiskit to construct/run the submission circuit.

Do not use IonQ simulator calls inside the optimizer loop.

### 11.7 Backend execution contract

`run_qaoa()` receives an injected/provided backend rather than constructing cloud credentials.

Interface:

```python
async_or_sync def run_qaoa(
    instance: OptimizationInstance,
    backend,
    shots: int = 1024,
    reps: int = 1,
    optimizer_mode: str = "auto",
) -> QAOAResult:
    ...
```

The backend adapter must support:

- Qollab-provided free local simulator,
- IonQ simulator path exposed by Qollab,
- local dev fallback if available.

Never require secrets/API keys from the judge.

### 11.8 One-job-safe mode

Implement a `single_backend_job=True` mode where all parameter optimization happens locally and exactly one backend sampling job is submitted.

This mode should be the default for remote/IonQ backend choices.

### 11.9 Measurements and shot distribution

Return:

- raw counts,
- normalized probabilities,
- all feasible sampled bitstrings sorted by QUBO objective,
- most probable bitstring,
- best feasible sampled bitstring,
- probability mass on feasible states,
- probability assigned to the exact-optimal bitstring(s), if known.

The **recommended QAOA pack** is the best feasible sampled bitstring by objective, not automatically the modal bitstring. Show both when they differ.

### 11.10 No feasible sample fallback

If no measured sample satisfies cardinality:

1. Mark QAOA run as infeasible.
2. Do not silently repair the sample and call it QAOA.
3. UI should say “No feasible K-cell sample observed.”
4. Optionally show the lowest-cardinality-violation sample for diagnostics.
5. In local simulator mode, permit one retry with increased penalty only when backend policy allows; in one-job remote mode do not automatically submit another job.

---

## 12. Qiskit bit ordering and decoding

This is a major correctness risk.

### 12.1 Internal convention

Internal bit vector:

```text
bits[i] corresponds to candidate/qubit i
```

Example:

```python
bits = [1, 0, 1, 0]
```

means candidates 0 and 2 are selected.

### 12.2 Qiskit count strings

Qiskit commonly displays classical bitstrings most-significant classical bit first. If qubit `i` is measured into classical bit `i`, the printed string usually needs reversal before mapping string character positions to candidate indices.

Never scatter `[::-1]` throughout the project.

Create exactly one codec module:

```text
src/quantum/bitstrings.py
```

Required APIs:

```python
def qiskit_key_to_bits(key: str, n: int) -> tuple[int, ...]: ...
def bits_to_qiskit_key(bits: Sequence[int]) -> str: ...
def selected_indices(bits: Sequence[int]) -> list[int]: ...
```

Unit tests must verify all 2^N strings for `N <= 5` round-trip correctly.

### 12.3 Sanity circuit test

Create a circuit that deterministically prepares a known computational state such as qubits 0 and 2 = 1. Run it on the same local backend path and assert decoded selected indices equal `[0, 2]`.

Do this before trusting QAOA results.

---

## 13. Classical baseline algorithms

Every baseline must consume the same `OptimizationInstance` and return the same result schema.

### 13.1 SOH sorting baseline

Algorithm:

1. Sort candidates by descending current SOH.
2. Tie break by descending current capacity.
3. Tie break again by stable `cell_id`.
4. Select first K.

Purpose: naive “pick healthiest cells” reference.

### 13.2 Compatibility greedy baseline

Algorithm:

1. Try each eligible candidate as a starting seed.
2. Repeatedly add the remaining cell that minimizes incremental QUBO objective of the partial group, ignoring cardinality penalty until final size.
3. Evaluate all seed-generated groups.
4. Return the best deterministic group.

This avoids arbitrary dependence on a single first seed and remains cheap for small N.

### 13.3 Simulated annealing baseline

Implement project-owned binary swap annealing constrained to exactly K selected cells.

State representation: a fixed-cardinality set.

Neighbor move:

- randomly deselect one selected index,
- randomly select one unselected index.

Energy:

- use the physical/compatibility objective **without cardinality penalty** because cardinality is preserved by the move.

Default schedule:

```text
steps = 3000 for N <= 12
t_start = max(1.0, std(pair costs) or 1.0)
t_end = 1e-3
T(step) = t_start * (t_end/t_start)^(step/(steps-1))
```

Acceptance:

```text
accept if ΔE <= 0 else rand() < exp(-ΔE/T)
```

Use a seeded `random.Random` or NumPy generator. Return best-ever state, not final state.

### 13.4 Exact enumeration oracle

For small N, enumerate all `C(N,K)` fixed-cardinality subsets using `itertools.combinations`.

Return:

- globally optimal feasible subset,
- objective,
- number of evaluated subsets,
- all tied optima if ties are manageable.

Use the non-penalized physical compatibility objective for exact feasible optimization and confirm it matches the feasible penalized QUBO ranking.

Exact enumeration is the ground truth for solution quality, not a production-scale claim.

### 13.5 Optional MILP/IP baseline

Do not implement unless core work is complete and a compatible solver is available without jeopardizing portability. Exact enumeration is sufficient for N<=12.

---

## 14. Physical and optimization evaluation metrics

### 14.1 Current usable series capacity

For selected pack `S`:

```text
usable_capacity_now = min(C_i for i in S)
```

This is a simplified series-string bottleneck metric.

### 14.2 Current capacity spread

```text
capacity_spread_now = max(C_i) - min(C_i)
```

### 14.3 Current capacity coefficient of variation

```text
capacity_cv_now = std(C_i) / mean(C_i)
```

Use population standard deviation consistently.

### 14.4 Resistance spread

```text
resistance_spread = max(R_i) - min(R_i)
```

If resistance is missing for any selected cell in a mode where resistance is optional, report `null` rather than fake zero.

### 14.5 Predicted Pack Divergence (PPD)

Primary normalized definition:

```text
PPD_H = std(C_hat_i(H)) / mean(C_hat_i(H))
```

Lower is better.

Also expose absolute predicted spread in Ah.

### 14.6 Observed Pack Divergence (OPD)

Using hidden future truth:

```text
OPD_H = std(C_actual_i(H)) / mean(C_actual_i(H))
```

This is the headline retrospective metric.

### 14.7 Observed future usable capacity

```text
usable_capacity_future = min(C_actual_i(H))
```

### 14.8 Objective gap to optimum

Use a robust denominator:

```text
gap_abs = E_algorithm - E_optimal
gap_pct = gap_abs / max(abs(E_optimal), 1e-9) * 100
```

If objective energies can be negative because of health rewards, also report absolute gap and a normalized regret relative to the spread of feasible objective values if useful.

### 14.9 QAOA sample metrics

- feasible shot fraction,
- optimum probability mass,
- best-sampled objective gap,
- modal-sample objective gap,
- number of unique feasible states sampled.

### 14.10 Runtime metrics

Time independently:

- data preparation per trial,
- QUBO construction,
- classical solver runtime,
- QAOA parameter optimization,
- circuit transpilation,
- backend job wall-clock if measurable,
- result decoding.

Do not compare asynchronous remote queue time against local CPU time as if it were algorithmic runtime. Label runtime categories clearly.

---

## 15. Benchmark protocol

### 15.1 Fixed seed set

Check in a benchmark configuration such as:

```json
{
  "seeds": [11, 23, 37, 41, 59, 71, 83, 97, 101, 127, 149, 163, 181, 197, 211, 227, 241, 263, 281, 307],
  "candidate_sizes": [8],
  "pack_size": 4,
  "horizon_cycles": 200
}
```

If data coverage cannot support all seeds, generate a valid deterministic seed list once and commit it with rationale. Do not delete trials merely because QAOA performs poorly.

### 15.2 Required benchmark comparisons

At minimum compare:

1. SOH sort + current-only objective reporting.
2. Greedy + trajectory-aware objective.
3. Simulated annealing + trajectory-aware objective.
4. Exact + trajectory-aware objective.
5. QAOA + trajectory-aware objective.

Additionally, to test the scientific contribution, compare **exact current-only** versus **exact trajectory-aware** on OPD. This isolates the value of the objective design from solver quality.

### 15.3 Aggregate reporting

For each algorithm report across trials:

- mean/median OPD,
- mean/median future bottleneck capacity,
- mean current capacity spread,
- mean objective gap,
- success rate / valid trial count,
- runtime summary.

For QAOA additionally report:

- mean feasible shot fraction,
- fraction of trials where exact optimum was sampled,
- mean best-sampled optimality gap.

### 15.4 Statistical restraint

The hackathon project does not need formal inferential statistics, but include bootstrap confidence intervals if easy. Do not claim statistical significance without performing a valid test.

### 15.5 Scalability experiment

Optional but valuable:

```text
N = 6, 8, 10, 12
K = min(4, floor(N/2)) or controlled fixed K
```

Measure exact enumeration growth, classical heuristic runtime, circuit width, transpiled depth, and QAOA optimization cost.

The purpose is to show problem scaling, not to imply quantum advantage.

---

## 16. Noise/backend experiment

If Qollab exposes a built-in noisy simulator or IonQ simulator compatible with the project:

Compare the same fixed QAOA parameters/circuit under:

- ideal local simulation,
- available noisy/free simulator,
- IonQ simulator if practical.

Report:

- feasible probability mass,
- optimum probability mass,
- best sampled objective gap.

Do not tune parameters separately using paid/remote hardware loops. If backend semantics make this experiment fragile, omit it rather than compromise the core submission.


---

## 17. Application architecture

### 17.1 Design goals

The application must be:

- runnable without a separate server,
- portable to Qollab,
- deterministic enough for judges to reproduce a demo,
- visually polished,
- accessible,
- resilient when the remote simulator is slow or unavailable,
- able to replay precomputed benchmark results while still supporting a genuine live QAOA run.

### 17.2 Preferred stack

Use the simplest stack that Qollab supports reliably:

**Frontend**

- vanilla HTML,
- modern CSS,
- vanilla JavaScript modules,
- inline/local SVG for charts and diagrams,
- no build step unless Qollab explicitly supports it and the benefit is compelling.

**Quantum / scientific code**

- Python,
- Qiskit,
- NumPy,
- Python standard library,
- SciPy only as an optional accelerator/optimizer if environment verification confirms support.

Avoid React/Vite/npm dependencies for MVP unless Qollab's current project runtime specifically recommends them. Zero-build vanilla assets reduce deployment risk during a 48-hour hackathon.

### 17.3 JS↔Python/Qiskit bridge

Qollab integration details are platform-specific and must be verified in Task 1. Encapsulate them behind:

```text
web/js/quantumBridge.js
```

The rest of the UI should call stable functions:

```javascript
await quantumBridge.getCapabilities()
await quantumBridge.loadDemoPool(poolId)
await quantumBridge.runOptimization(config)
await quantumBridge.runBenchmarkPreview(config)
```

The bridge may call Qollab Python modules, a platform-provided execution API, or another supported mechanism. Do not let Qollab-specific invocation syntax leak into UI components.

If direct JS→Python calls are unsupported, implement the UI in the Qollab-supported equivalent and preserve the same logical architecture. Record the decision in `DECISIONS.md`.

### 17.4 Live vs replay mode

The application needs two result paths:

**Live mode**
- builds the selected demo instance,
- runs parameter optimization locally,
- submits the final Qiskit circuit to the selected Qollab backend,
- displays real returned counts.

**Replay mode**
- loads previously exported benchmark JSON,
- renders aggregate charts instantly,
- does not pretend the replay is a live quantum run.

The UI must label these modes explicitly.

### 17.5 Python module boundaries

Recommended tree:

```text
repack-q/
├── SPEC.md
├── README.md
├── LICENSE
├── DECISIONS.md
├── ATTRIBUTION.md
├── requirements.txt
├── pyproject.toml                 # optional if supported/valuable
├── src/
│   ├── repackq/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── models.py
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── canonical.py
│   │   │   ├── provenance.py
│   │   │   ├── trials.py
│   │   │   └── adapters/
│   │   │       ├── __init__.py
│   │   │       ├── deep_sorting.py
│   │   │       └── nasa_recommissioned.py
│   │   ├── prediction/
│   │   │   ├── __init__.py
│   │   │   └── trajectory.py
│   │   ├── optimization/
│   │   │   ├── __init__.py
│   │   │   ├── normalize.py
│   │   │   ├── objective.py
│   │   │   ├── qubo.py
│   │   │   ├── ising.py
│   │   │   ├── metrics.py
│   │   │   └── baselines.py
│   │   ├── quantum/
│   │   │   ├── __init__.py
│   │   │   ├── bitstrings.py
│   │   │   ├── qiskit_compat.py
│   │   │   ├── parameters.py
│   │   │   ├── qaoa.py
│   │   │   └── backend.py
│   │   ├── benchmark/
│   │   │   ├── __init__.py
│   │   │   ├── runner.py
│   │   │   └── summarize.py
│   │   └── api.py
│   └── scripts/
│       ├── inspect_dataset.py
│       ├── preprocess_primary.py
│       ├── build_demo_pools.py
│       ├── run_benchmarks.py
│       └── export_web_assets.py
├── data/
│   ├── README.md
│   ├── raw/                       # gitignored
│   ├── processed/
│   │   ├── cell_trajectories.json
│   │   ├── demo_pools.json
│   │   └── provenance.json
│   └── benchmark/
│       ├── config.json
│       ├── trials.json
│       └── summary.json
├── web/
│   ├── index.html
│   ├── styles.css
│   ├── js/
│   │   ├── app.js
│   │   ├── state.js
│   │   ├── quantumBridge.js
│   │   ├── formatting.js
│   │   ├── charts.js
│   │   ├── accessibility.js
│   │   └── components/
│   │       ├── cellCard.js
│   │       ├── packTray.js
│   │       ├── missionPanel.js
│   │       ├── comparisonTable.js
│   │       ├── probabilityChart.js
│   │       ├── quantumInspector.js
│   │       └── validationTimeline.js
│   └── assets/
│       └── icons.svg
└── tests/
    ├── test_data_adapter.py
    ├── test_no_leakage.py
    ├── test_prediction.py
    ├── test_normalization.py
    ├── test_qubo.py
    ├── test_ising_equivalence.py
    ├── test_bitstrings.py
    ├── test_baselines.py
    ├── test_qaoa_local.py
    ├── test_metrics.py
    └── fixtures/
```

Keep raw multi-GB data outside git.

---

## 18. Python application API

Create `src/repackq/api.py` as the stable interface used by the UI bridge and scripts.

Required functions:

```python
def get_app_metadata() -> dict: ...

def list_missions() -> list[dict]: ...

def list_demo_pools() -> list[dict]: ...

def get_demo_pool(pool_id: str) -> dict: ...

def evaluate_manual_pack(pool_id: str, selected_cell_ids: list[str]) -> dict: ...

def solve_classical(pool_id: str, mission_id: str) -> dict: ...

def prepare_quantum_instance(pool_id: str, mission_id: str) -> dict: ...

def run_quantum(pool_id: str, mission_id: str, backend, shots: int = 1024) -> dict: ...

def reveal_future(pool_id: str, selected_by_algorithm: dict) -> dict: ...

def get_benchmark_summary() -> dict: ...
```

All dictionaries returned to JS must be JSON-serializable. Convert NumPy scalars to Python primitives.

### 18.1 Error format

Never expose raw tracebacks in the UI.

Stable error payload:

```json
{
  "ok": false,
  "error": {
    "code": "NO_FEASIBLE_QAOA_SAMPLE",
    "message": "No 4-cell feasible state was observed in 1024 shots.",
    "details": {}
  }
}
```

Log detailed stack traces to developer console when possible.

### 18.2 Capabilities endpoint

`get_app_metadata()` or `getCapabilities()` must report:

- Qiskit version,
- available optimizer modes,
- selected backend label,
- statevector availability,
- optional SciPy availability,
- app version/commit hash if available,
- data provenance version.

This helps judges understand what actually ran.

---

## 19. UI/UX specification

### 19.1 Visual direction

The UI should feel like a **clean energy systems lab / battery recommissioning workstation**, not a generic dashboard template.

Use a dark technical visual system with restrained luminous accents and high information density without clutter.

Suggested design tokens:

```css
--bg: #081018;
--surface-1: #0d1823;
--surface-2: #122232;
--surface-3: #172b3d;
--text: #f4f7fa;
--text-muted: #aab8c5;
--border: #294153;
--accent: #58d6c7;
--accent-2: #7cb7ff;
--warning: #f6c667;
--danger: #ff7a7a;
--success: #7edc9a;
```

These are starting values. Adjust only if contrast testing shows a problem.

Visual character:

- subtle grid/noise background, implemented in CSS and disabled under reduced-motion if animated,
- rounded 12–16px panels,
- crisp monospace numeric labels paired with readable sans-serif body text using system fonts,
- battery cells visualized as compact technical cards,
- quantum section uses circuit-like line motifs, not sci-fi neon overload,
- charts use direct labels and patterns/icons in addition to color.

Do not load external web fonts; use a system stack for portability.

### 19.2 Responsive layout

Desktop target: 1280–1600px wide judge screen.

Primary desktop grid:

```text
┌─────────────────────────────────────────────────────────────┐
│ top nav / title / backend status                           │
├───────────────────┬─────────────────────────────────────────┤
│ mission +         │ candidate inventory / pack bench       │
│ assumptions       │                                         │
├───────────────────┴─────────────────────────────────────────┤
│ algorithm results comparison                              │
├────────────────────────────┬────────────────────────────────┤
│ QAOA probability / circuit │ future validation timeline    │
├────────────────────────────┴────────────────────────────────┤
│ methodology / limitations / provenance                    │
└─────────────────────────────────────────────────────────────┘
```

Mobile/tablet:

- stack panels vertically,
- pack tray remains horizontally scrollable if needed,
- controls remain at least 44×44 CSS px touch target,
- tables convert to stacked cards under ~760px.

### 19.3 Page sections

#### A. Top bar

Contains:

- RePack-Q logo/wordmark,
- subtitle,
- “Quantum Impact” badge,
- backend status chip: `Local simulator`, `IonQ simulator`, `Replay data`, etc.,
- dataset badge: `86-cell NMC longitudinal dataset`,
- small “Methodology” link.

#### B. Hero / problem explanation

Keep compact. One sentence plus three-stat summary:

- candidate cells,
- selected cells,
- future horizon.

Avoid a giant marketing hero that pushes the demo below the fold.

#### C. Mission panel

Controls:

- mission dropdown (MVP default PV + TOU; other entries may be labeled experimental),
- horizon selector if data supports it,
- pack size K selector bounded to allowed values,
- objective toggle: `Current-state` vs `Trajectory-aware`,
- advanced weights disclosure panel.

Changing mission/weights invalidates prior optimization results and must visibly reset them.

#### D. Candidate inventory

Render N candidate `CellCard`s.

Each card shows:

- Cell ID,
- SOH,
- current capacity,
- resistance,
- predicted capacity at H,
- uncertainty,
- tiny sparkline using pre-t0 history only until future is revealed,
- “Add to Pack” button.

Do not show actual future capacity before reveal.

#### E. Manual pack tray

K slots.

Supports:

- click “Add to Pack”,
- remove button,
- optional drag/drop enhancement.

Drag/drop is never the only interaction.

As cells are added, update:

- current bottleneck cell,
- usable capacity,
- capacity spread,
- resistance spread,
- predicted divergence.

Highlight the bottleneck with icon + text, not color alone.

#### F. Run panel

Primary CTA:

**Run Quantum Match**

Secondary CTA:

**Compare All Algorithms**

When clicked:

1. show staged progress indicators:
   - building compatibility model,
   - mapping QUBO to Ising,
   - optimizing QAOA angles,
   - sampling backend,
   - decoding pack,
2. keep UI responsive,
3. surface actual backend label,
4. prevent double submission.

If the platform cannot stream stages, animate deterministic front-end progress only for completed local stages and use an indeterminate state for backend sampling. Never fabricate a finished result before it arrives.

#### G. Algorithm comparison

Show cards or a table for:

- Manual,
- SOH Sort,
- Greedy,
- Annealing,
- QAOA,
- Exact optimum.

Columns/metrics:

- selected cell IDs,
- usable capacity now,
- current spread,
- predicted divergence,
- objective gap,
- runtime category.

Clearly badge `Exact oracle` and `Quantum`.

Do not visually hide a classical method if it beats QAOA.

#### H. Quantum inspector

A polished educational panel showing:

- number of qubits,
- p depth,
- gamma/beta values,
- final penalty A,
- Hamiltonian term count,
- circuit depth/width if available,
- feasible shot percentage,
- top measured bitstrings with probabilities.

Optional circuit rendering:

- if Qiskit textual/SVG circuit output is easy to transfer, show it;
- otherwise render an explanatory simplified circuit diagram without pretending it is the exact transpiled circuit.

Label exact vs schematic visualization.

#### I. Probability distribution

SVG horizontal bars for top 6–10 sampled states.

Each bar:

- decoded cell IDs or compact bitstring,
- probability,
- feasibility badge,
- objective score.

Highlight the selected best feasible sample and exact optimum if sampled.

#### J. Reveal Future interaction

This is the narrative payoff.

Before reveal:

- candidate sparklines stop at `t0`,
- “Future observations hidden from optimizer” status is visible.

Button:

**Reveal Recorded Future**

After reveal:

- extend capacity trajectory lines to `t0 + H`,
- show actual future capacity for selected cells,
- animate slowly enough to understand but respect reduced-motion,
- update OPD and observed bottleneck metrics,
- compare predicted vs observed pack divergence.

A small explanatory banner should say:

> “These measurements were excluded from selection and are shown only for retrospective validation.”

#### K. Benchmark summary

Render aggregate benchmark results from checked-in benchmark JSON:

- OPD by algorithm,
- optimality gap by solver,
- feasible QAOA mass,
- future bottleneck capacity,
- perhaps a scatter of predicted PPD vs observed OPD.

Avoid overloading the main demo. Put aggregate results in a tab or lower section.

#### L. Methodology / limitations

Accordion/drawer with:

- simplified series-pack assumption,
- mission abstraction,
- dataset provenance,
- QUBO formula,
- no quantum advantage claim,
- data/model limitations.

### 19.4 Microinteractions

Use subtle transitions:

- cell cards lift 2px on hover/focus,
- pack slot insertion uses 150–220ms transform/opacity,
- result cards fade in sequentially by at most ~60ms stagger,
- future reveal line animates over ~700ms unless `prefers-reduced-motion`.

No long splash screens, particle effects, or distracting glowing animations.

---

## 20. Accessibility requirements

Treat these as acceptance criteria, not polish.

### 20.1 Keyboard

Everything must work without a mouse:

- Tab order follows visual order,
- all custom controls use native buttons/selects whenever possible,
- Add/Remove pack operations keyboard accessible,
- drag/drop is optional enhancement only,
- Escape closes drawers/modals,
- focus returns sensibly when a dialog closes.

### 20.2 Semantics

- one `<h1>`, logical heading hierarchy,
- `<main>`, `<nav>`, `<section>`, `<button>`, `<table>` where appropriate,
- ARIA only when native semantics are insufficient,
- `aria-live="polite"` for optimization completion/status,
- backend errors announced accessibly.

### 20.3 Contrast and color

- WCAG AA contrast for text,
- success/warning/error include icon/text labels,
- chart series distinguished by labels/markers/patterns, not color alone.

### 20.4 Motion

Honor:

```css
@media (prefers-reduced-motion: reduce)
```

Remove nonessential animation and smooth scrolling.

### 20.5 Screen reader labels

Cell cards need concise accessible names, e.g.:

> “Cell 47, state of health 81 percent, capacity 1.94 amp-hours, predicted 1.83 amp-hours at 200 cycles.”

### 20.6 Testing

At minimum:

- keyboard-only manual pass,
- Lighthouse/axe equivalent if available locally,
- browser zoom 200% check,
- mobile width check,
- no focus trap.

---

## 21. Frontend state model

Use a single explicit state object rather than hidden DOM state.

Example:

```javascript
const initialState = {
  mode: "live", // live | replay
  missionId: "pv_tou",
  objectiveMode: "trajectory_aware",
  poolId: null,
  pool: null,
  manualSelection: [],
  algorithms: {},
  quantumStatus: "idle", // idle | preparing | optimizing | sampling | complete | error
  quantumResult: null,
  futureRevealed: false,
  backend: null,
  error: null,
};
```

State transitions should rerender only affected components where practical.

### 21.1 Invalidations

Changing any of these invalidates previous algorithm results:

- mission,
- horizon,
- objective mode,
- weights,
- candidate pool,
- K.

Display a brief “Results reset because the optimization problem changed” notice.

### 21.2 URL state

Stretch: encode `pool`, `mission`, and `mode` in query parameters so a judge can open a stable demo link.

---

## 22. Charts

Implement charts with local SVG helpers to avoid external dependencies.

Required charts:

1. **Cell trajectory sparkline** — history, prediction, then actual future after reveal.
2. **QAOA probability bars** — top measured states.
3. **Algorithm comparison bars** — OPD or PPD.
4. **Benchmark summary** — compact grouped bars or dot plot.

Rules:

- axes/units visible when needed,
- tooltips are supplemental; values also accessible in text/table,
- SVG includes `<title>`/`<desc>` where practical,
- no 3D charts,
- no pie charts.

---

## 23. Performance and reliability

### 23.1 Frontend budget

Target:

- first meaningful render under 1 second for local assets on a normal laptop,
- processed runtime dataset under a few MB if possible,
- no blocking parse of multi-megabyte raw logs,
- no external CDN dependency.

### 23.2 Quantum runtime budget

For demo N=8, p=1:

- local parameter optimization should target a few seconds or less,
- UI must remain usable during computation,
- cache parameter results per `(pool, mission, objective, reps)` in-memory during the session,
- backend sampling may take longer; show status without time promises.

### 23.3 Determinism

Store and expose seeds for:

- candidate pool construction,
- simulated annealing,
- QAOA initial parameter selection,
- local simulator seed if supported.

Remote simulator/hardware sampling may still vary; do not require byte-identical counts.

### 23.4 Graceful degradation

If live backend fails:

- show a clear error,
- keep classical results visible,
- allow user to switch to local simulator if available,
- allow benchmark replay view,
- do not silently replace a failed live result with precomputed counts.

---

## 24. Testing strategy

### 24.1 Unit tests

Required:

**Data**
- alias resolution,
- invalid value filtering,
- diagnostic summary extraction on fixtures,
- future-truth tolerance behavior.

**Leakage**
- future mutations cannot affect snapshot/prediction.

**Prediction**
- known linear fade recovered within tolerance,
- positive slope clamps correctly,
- uncertainty finite,
- short-history fallback works.

**Normalization**
- constant features yield zero normalized values,
- robust scaling finite.

**QUBO**
- exact cardinality penalty expansion,
- adaptive A yields feasible exact global optimum,
- current-only mode excludes future term.

**Ising**
- energy equivalence for all bitstrings for random small QUBOs.

**Bitstrings**
- Qiskit display-order conversion round trip.

**Baselines**
- exact oracle finds known optimum,
- greedy returns K,
- annealing preserves K,
- deterministic seeds reproduce result.

**Metrics**
- bottleneck capacity,
- PPD/OPD,
- null resistance behavior.

**QAOA local**
- p=1 ansatz builds,
- optimizer returns finite parameters,
- deterministic toy problem samples a feasible high-quality solution with a forgiving statistical threshold.

### 24.2 Integration tests

1. Compact fixture → trial → QUBO → exact solver → result JSON.
2. Compact fixture → QAOA local statevector optimization → local sampling → decoded result.
3. API function returns JSON-serializable values.
4. Demo pool loads in UI and manual selection metrics update.
5. Qollab backend smoke test with a 2-qubit known circuit.
6. Qollab live QAOA smoke test for N=4 or N=6 before N=8.

### 24.3 Statistical test caution

Tests involving finite-shot QAOA must not assert exact counts. Assert broad properties such as:

- result has expected shot total,
- decoder works,
- feasible mass exceeds a low threshold on deterministic ideal toy instance,
- best feasible sampled energy is within a tolerable bound when shots are high enough.

### 24.4 UI acceptance tests

Manual checklist:

- all buttons work,
- no console errors,
- no NaN/undefined labels,
- pool reset works,
- changing mission clears stale results,
- future remains hidden until reveal,
- replay mode is labeled,
- backend status truthful,
- mobile layout usable,
- keyboard navigation complete,
- reduced motion respected.

---

## 25. Logging, provenance, and reproducibility

### 25.1 Provenance file

`data/processed/provenance.json` should include:

```json
{
  "dataset_name": "Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions",
  "dataset_doi": "10.5281/zenodo.14859405",
  "code_reference_doi": "10.5281/zenodo.15350607",
  "raw_files": [],
  "raw_checksums": {},
  "processing_script": "src/scripts/preprocess_primary.py",
  "processing_commit": "...",
  "nominal_capacity_ah": 2.4,
  "notes": []
}
```

### 25.2 Benchmark provenance

Every benchmark summary must record:

- source processed data hash,
- config hash,
- git commit,
- Qiskit version,
- Python version if available,
- backend type,
- shot count,
- seeds.

### 25.3 Decision log

Use `DECISIONS.md` for decisions discovered during implementation that differ from this spec. Format each entry:

```text
## YYYY-MM-DD — Decision title
Context:
Decision:
Alternatives considered:
Consequences:
```

Do not silently diverge from architecture.

---

## 26. Documentation requirements

### 26.1 README structure

Final README should contain:

1. one-sentence pitch,
2. screenshot/GIF if permitted,
3. problem,
4. why cell trajectories matter,
5. architecture diagram,
6. dataset/provenance,
7. QUBO formulation,
8. QAOA implementation,
9. classical baselines,
10. benchmark protocol,
11. results,
12. how to run locally,
13. how to run on Qollab,
14. limitations,
15. originality/AI/open-source disclosure,
16. attribution,
17. citations,
18. MIT license note.

### 26.2 Architecture diagram

Create a simple SVG/Markdown diagram:

```text
Public longitudinal battery data
          │
          ▼
 Classical preprocessing
  capacity / SOH / R
          │
          ▼
 Leakage-free trajectory estimate
          │
          ▼
 Classical eligibility filter
          │
          ▼
 Mission-weighted compatibility QUBO
          │
          ├──────────────► classical baselines
          │
          ▼
 QUBO → Ising → Qiskit QAOA
          │
          ▼
 Backend measurement distribution
          │
          ▼
 Best feasible sampled pack
          │
          ▼
 Reveal hidden future measurements
          │
          ▼
 PPD / OPD / bottleneck / gap
```

### 26.3 Project page wording

Avoid dense implementation detail above the fold. Lead with the actual insight:

> “Two used cells can have the same SOH today and still age very differently tomorrow. RePack-Q turns future compatibility into a fixed-cardinality QUBO and uses Qiskit QAOA to search for second-life groups that are expected to remain balanced.”

### 26.4 Required attribution

Include exactly:

> **This effort is supported by Qollab & IonQ**

### 26.5 External citations

At minimum cite:

- Qollab hackathon terms/how-it-works,
- primary Zenodo dataset DOI,
- associated deep-sorting paper/code repository,
- NASA recommissioned dataset if used,
- Qiskit documentation relevant to QAOA/ansatz/operator APIs.

---

## 27. Security and privacy

There is no user PII requirement.

Rules:

- no API keys committed,
- no secret environment variables required for free Qollab path,
- no arbitrary file upload parser in MVP,
- sanitize any text inserted into DOM; prefer `textContent` over `innerHTML`,
- processed data is read-only in browser,
- no analytics/tracking scripts required.

---

## 28. Failure modes and explicit mitigations

### 28.1 Primary raw dataset is too large/slow to parse

Mitigation:

- preprocess offline once,
- use authors' published extraction logic only as reference,
- focus on diagnostic summaries,
- package compact derived data.

### 28.2 Dataset license does not clearly allow redistributing processed records

Mitigation:

- verify license before public packaging,
- package preprocessing scripts and provenance,
- use permitted small derivative sample if allowed,
- otherwise use precomputed aggregate benchmark output plus a clearly labeled synthetic UI fixture; do not mislabel synthetic data as real.

### 28.3 Internal resistance is sparse or inconsistent

Mitigation:

- make resistance term optional per pool,
- renormalize active objective weights,
- do not impute fake resistance merely to fill the UI.

### 28.4 Too few cells have future truth at H=200

Mitigation:

- reduce H to a documented value such as 100 diagnostic-cycle equivalent interval,
- or use nearest future observation within tolerance,
- choose the largest horizon that supports enough valid trials.

Record the actual choice in `DECISIONS.md`.

### 28.5 Simple trajectory predictor performs poorly

Mitigation:

- keep prediction metrics transparent,
- compare trajectory-aware objective against current-only objective,
- optionally upgrade to a quadratic/robust regression only after leakage-safe baseline works,
- do not hide negative results.

### 28.6 QAOA produces many invalid cardinalities

Mitigation:

- adaptive penalty calibration via exact enumeration,
- report feasible shot fraction,
- optional retry on local backend,
- stretch: fixed-Hamming-weight/XY mixer.

### 28.7 QAOA does not beat classical heuristics

This is not a blocker.

Report:

- exact optimality gap,
- probability of sampling optimum,
- solution distribution,
- runtime honestly.

The contribution remains the hybrid formulation, benchmarking, and domain application.

### 28.8 Qollab JS↔Python bridge differs from assumptions

Mitigation:

- Task 1 performs a platform spike before building UI around it,
- bridge abstraction isolates platform syntax,
- preserve Python core independently.

### 28.9 IonQ simulator job semantics are restrictive

Mitigation:

- single-backend-job QAOA mode,
- local statevector parameter optimization,
- only final bound circuit sampled remotely.

### 28.10 Backend outage near demo

Mitigation:

- local simulator remains primary judge-compatible path,
- replay aggregate benchmark available,
- video recorded from verified functioning run,
- no fabricated “live” result.

---

## 29. Definition of done

The project is submission-ready only when all of the following are true:

### Core science

- [ ] Real longitudinal public battery data is processed with provenance.
- [ ] No-future-leakage test passes.
- [ ] Trajectory estimator has measured prediction error.
- [ ] Candidate pools are reproducible.
- [ ] QUBO formulation implemented and tested.
- [ ] QUBO↔Ising exhaustive equivalence test passes.
- [ ] Exact classical oracle works.
- [ ] QAOA runs with Qiskit.
- [ ] QAOA returns decoded feasible samples on the default demo.
- [ ] Aggregate benchmark results exist.

### UI

- [ ] Manual pack interaction works by keyboard and pointer.
- [ ] Bottleneck metrics update immediately.
- [ ] “Run Quantum Match” works.
- [ ] Comparison results show all algorithms honestly.
- [ ] Quantum inspector shows real parameters/counts.
- [ ] Future data is hidden before reveal.
- [ ] Future reveal shows actual held-out observations.
- [ ] Responsive layout works.
- [ ] Accessibility checklist passes.

### Qollab

- [ ] Runs on free local simulator.
- [ ] IonQ simulator path tested if available.
- [ ] Qiskit dependency confirmed.
- [ ] MIT license present.
- [ ] required attribution present.
- [ ] project page complete.
- [ ] 2–3 minute demo video ready.
- [ ] originality/source disclosure complete.

### Engineering

- [ ] tests pass,
- [ ] no raw multi-GB dataset committed,
- [ ] no secrets committed,
- [ ] no console errors in demo,
- [ ] repository clean,
- [ ] every implementation task committed locally,
- [ ] no push performed unless user explicitly requests it.


---

# 30. Codex execution plan — 8 independent implementation sessions

## 30.0 Mandatory protocol for every Codex session

Each task below is designed to be completed in a **fresh Codex session**. Do not rely on conversational memory from an earlier session.

At the start of every session, Codex must execute this checklist:

1. `pwd` and confirm it is in the RePack-Q repository.
2. Read `SPEC.md` completely enough to understand the current task and cross-cutting constraints.
3. Read `DECISIONS.md` if present.
4. Run `git status --short`.
5. Run `git log --oneline -10`.
6. Inspect files created by preceding tasks that this task depends on.
7. Do **not** undo user changes or changes from prior tasks unless they are demonstrably broken and the reason is documented.
8. Work only on the assigned task plus small prerequisite fixes required to make that task correct.
9. Run the task's required test/validation commands.
10. Update `DECISIONS.md` for material deviations or newly discovered platform facts.
11. Run `git diff --check`.
12. Review `git diff` for accidental data/secrets/generated junk.
13. Commit the completed work **locally** using the specified commit message or a very close semantic equivalent.
14. Run `git status --short` after commit; it should be clean except for intentionally ignored/untracked raw data.
15. **Do not push. Do not create a remote. Do not publish.** The user requested local commits only for now.

If a task encounters a true blocker:

- do not invent platform behavior or dataset fields,
- investigate enough to characterize the blocker,
- implement the documented fallback when possible,
- record the decision in `DECISIONS.md`,
- leave the repository in a runnable/testable state,
- commit only coherent work, not broken half-integrations.

The exact file layout may evolve if Qollab imposes constraints, but architectural boundaries and correctness requirements in this spec must remain intact.

---

## Task 1 — Repository scaffold, environment verification, and Qollab integration spike

### Objective

Create the runnable project skeleton and eliminate platform uncertainty before deeper implementation. Verify the exact Qiskit version/API, the Qollab backend contract, and the supported mechanism for a JS/Qiskit or equivalent interactive project.

### Why this task is first

The largest avoidable implementation risk is writing an entire frontend or QAOA wrapper against an imagined Qollab API. This task must establish a minimal known-good end-to-end path.

### Required work

#### A. Repository scaffold

Create:

- `README.md` with temporary development instructions and project pitch,
- `LICENSE` containing MIT license,
- `DECISIONS.md`,
- `ATTRIBUTION.md`,
- `.gitignore`,
- package/source structure from Section 17,
- minimal tests directory,
- minimal web directory.

`.gitignore` must include at least:

```text
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
data/raw/
.DS_Store
node_modules/
coverage/
htmlcov/
*.log
```

Do not ignore processed provenance assets intended for final submission.

#### B. Python dependency verification

Record:

- Python version,
- Qiskit version,
- presence/absence of NumPy,
- presence/absence of SciPy,
- any Qollab-specific Python bridge/runtime package.

Create `src/repackq/quantum/qiskit_compat.py` with only the minimal verified compatibility helpers required by the smoke test.

#### C. Backend smoke test

Implement a tiny Qiskit circuit with deterministic expected output, e.g. X on qubit 0 followed by measurement.

Verify:

- local/free simulator works,
- returned counts can be read,
- bitstring decoding convention is understood,
- Qollab-provided backend can be passed into project code without secrets.

If IonQ simulator is available during the task, run the same tiny circuit there once. This is a smoke test, not an optimization loop.

#### D. JS/Python bridge spike

Create the smallest interactive page that:

- renders “RePack-Q environment check”,
- has a button,
- invokes a Python/Qiskit function through the exact supported Qollab mechanism,
- displays returned JSON/text safely.

If Qollab's preferred project type is not literally vanilla JS + Python modules, adapt the outer shell while preserving the logical bridge abstraction.

#### E. Stable bridge contract

Create `web/js/quantumBridge.js` (or Qollab-equivalent) so later UI code is platform agnostic.

At minimum:

```javascript
getCapabilities()
runSmokeTest()
```

#### F. Qollab constraints note

Record verified facts in `DECISIONS.md`, including:

- exact backend object behavior,
- sync vs async job API,
- how to retrieve counts,
- how Python functions are called from the UI,
- whether Statevector works in the runtime,
- whether SciPy works,
- whether arbitrary local JSON assets are supported,
- any limitations on multiple remote simulator jobs.

### Tests / validation

- Python import test.
- Qiskit deterministic 1–2 qubit smoke test.
- Bitstring sanity check.
- Browser/Qollab button invokes quantum function and shows result.
- No external credentials.
- MIT license exists.

### Acceptance criteria

Task is complete only if there is a verified path from UI action → project quantum Python → Qiskit circuit → simulator result → UI output, or a documented Qollab-supported equivalent.

### Local commit

```text
chore: scaffold RePack-Q and verify Qollab Qiskit runtime
```

---

## Task 2 — Primary dataset adapter, preprocessing pipeline, and compact runtime assets

### Objective

Turn the 86-cell public longitudinal dataset into a clean, canonical, leakage-safe compact dataset suitable for optimization and Qollab runtime use.

### Prerequisite

Task 1 complete and committed.

### Required work

#### A. Raw-data inspection CLI

Implement `src/scripts/inspect_dataset.py`.

It must:

- accept raw dataset root path,
- enumerate cell files,
- print columns,
- identify likely battery/protocol/cycle fields,
- show unique step indices on representative files,
- report capacity/resistance/temp ranges,
- identify missing cells/files,
- never modify raw files.

#### B. Primary adapter

Implement `src/repackq/data/adapters/deep_sorting.py`.

Requirements:

- column alias resolution,
- robust numeric parsing,
- cell/protocol ID preservation,
- diagnostic cycle extraction based on verified raw schema,
- capacity extraction,
- resistance extraction,
- optional temperature summary,
- explicit warnings for missing/invalid data,
- no use of future data at this layer beyond storing chronological trajectories.

Do not blindly copy authors' source code. Reimplement only necessary extraction, cite their public repository as a reference, and keep the feature set deliberately small/interpretable.

#### C. Canonical trajectory model

Implement canonical dataclasses/models and serialization.

Processed per-cell trajectory should resemble:

```json
{
  "cell_id": "...",
  "protocol_id": "...",
  "nominal_capacity_ah": 2.4,
  "observations": [
    {
      "cycle_index": 0,
      "capacity_ah": 1.92,
      "internal_resistance_ohm": 0.041,
      "temperature_c": 25.6
    }
  ]
}
```

Do not store thousands of unnecessary raw waveform points in runtime JSON.

#### D. Preprocessing CLI

Implement `src/scripts/preprocess_primary.py`.

Options should include:

```text
--raw-root
--output
--phase second_life
--nominal-capacity 2.4
--inspect-only
```

Output:

- compact trajectories JSON,
- provenance JSON,
- preprocessing summary report.

#### E. Provenance

Include:

- DOI,
- source URLs,
- raw filenames/checksums where practical,
- number of cells,
- number of valid observations,
- excluded cells/reasons,
- processing date,
- git commit if available.

#### F. Licensing decision

Verify whether derived compact records may be redistributed in the public Qollab project. Record the conclusion with source in `DECISIONS.md`.

If license remains ambiguous, do **not** guess. Implement the fallback packaging strategy from Section 4.5 while preserving a real-data local benchmark path.

#### G. Tiny fixtures

Create small hand-authored/synthetic test fixtures for tests; do not make tests depend on GB-scale raw data.

### Tests / validation

- adapter tests on fixtures,
- column alias tests,
- invalid row tests,
- deterministic serialization,
- no raw data accidentally tracked,
- processed summary contains expected number/order of cells from available raw data,
- spot-check 3 cells manually against raw diagnostic values.

### Acceptance criteria

There is a compact canonical dataset or a license-safe equivalent, provenance is explicit, and the core code no longer depends on raw dataset-specific column names.

### Local commit

```text
data: add second-life battery preprocessing and provenance pipeline
```

---

## Task 3 — Leakage-free trajectory prediction, mission profiles, trial generation, and physical metrics

### Objective

Implement the classical scientific layer that transforms cell histories into decision-time snapshots and hidden future truth.

### Required work

#### A. Mission definitions

Implement mission config with at least:

- `pv_tou` default,
- optional placeholder `frequency_response` marked experimental/stretch if not scientifically parameterized.

Do not imply multiple mission-specific degradation models unless they actually exist.

#### B. Trajectory estimator

Implement weighted linear recent-history estimator from Section 7.

Include:

- minimum history points,
- window size,
- fallback median slope,
- positive-slope clamp,
- prediction clamp,
- uncertainty proxy,
- diagnostics.

#### C. Leakage-safe split API

Implement explicit history/future separation before prediction.

No predictor function may receive future arrays.

#### D. Snapshot generation

Create `CellSnapshot` from history only.

#### E. Future truth lookup

Implement nearest valid future diagnostic observation with configured tolerance.

#### F. Candidate pool generator

Implement:

- deterministic seeded sampling,
- N and K validation,
- minimum heterogeneity check,
- eligibility filtering,
- protocol stratification option,
- stable pool IDs.

#### G. Demo pool builder

Create `src/scripts/build_demo_pools.py`.

Generate:

- at least 3 candidate pools,
- one default demo pool,
- no fabricated future data,
- recorded selection criteria for why default demo is representative.

#### H. Physical metrics

Implement:

- usable current capacity,
- current capacity spread/CV,
- resistance spread,
- predicted pack divergence,
- observed pack divergence,
- observed future bottleneck.

#### I. Predictor evaluation script/summary

Measure prediction MAE/RMSE on valid held-out future observations. Save a compact summary JSON.

### Tests / validation

Hard requirement:

- `test_no_leakage.py` modifies all future measurements and proves snapshots/predictions are unchanged.

Also test:

- exact linear synthetic trajectories,
- missing resistance,
- insufficient history,
- future tolerance,
- seeded pool reproducibility,
- metrics on hand-calculated examples.

### Acceptance criteria

Given processed trajectories and a seed, the code deterministically produces a candidate pool with present snapshots and separately stored hidden future truth, and predictor quality is quantified.

### Local commit

```text
feat: add leakage-free trajectory modeling and benchmark trials
```

---

## Task 4 — Optimization objective, QUBO/Ising mapping, classical baselines, and exact oracle

### Objective

Implement and mathematically validate the entire optimization problem before introducing QAOA.

### Required work

#### A. Normalization

Implement robust pool-level scaling and constant-feature handling.

#### B. Objective modes

Implement `current_only` and `trajectory_aware` exactly as specified.

Provide a structured objective breakdown so UI can display contributions:

```json
{
  "capacity_mismatch": 0.12,
  "resistance_mismatch": 0.05,
  "future_mismatch": 0.09,
  "health_reward": -0.03,
  "uncertainty_penalty": 0.01,
  "cardinality_penalty": 0.0,
  "total": 0.24
}
```

#### C. QUBO builder

Implement:

- linear coefficients,
- quadratic coefficients,
- constant,
- adaptive cardinality penalty calibration,
- objective evaluator from bits.

#### D. Ising mapper

Implement exact mapping and offset.

#### E. Exhaustive equivalence verification

For random N=2..8 test instances, compare QUBO and Ising energy on every bitstring.

#### F. Baselines

Implement:

- SOH sort,
- multi-seed compatibility greedy,
- constrained simulated annealing,
- exact enumeration.

All use shared result schema.

#### G. Solver comparison CLI

Create a CLI that loads a demo pool and prints a concise table of selected cells/objectives/metrics for all classical solvers.

### Tests / validation

- normalization tests,
- exact QUBO expansion tests,
- cardinality penalty calibration test,
- exhaustive Ising equivalence,
- exact known optimum,
- annealing preserves K every move,
- deterministic baseline results under seed,
- current-only objective does not inspect predicted future capacity field.

### Acceptance criteria

For the default demo pool, exact enumeration returns a valid K-cell optimum and all classical baselines return valid results. QUBO↔Ising equivalence is exhaustively verified.

### Local commit

```text
feat: implement battery matching QUBO and classical optimization baselines
```

---

## Task 5 — Qiskit QAOA engine, parameter optimization, backend sampling, and quantum diagnostics

### Objective

Implement the actual quantum subroutine with enough diagnostics to prove it is integral to the application.

### Required work

#### A. Qiskit compatibility wrapper

Expand Task 1 wrapper using only verified APIs.

#### B. Cost Hamiltonian

Build `SparsePauliOp`/supported equivalent from `IsingModel`.

#### C. QAOA ansatz

Implement p=1 first.

Expose p through configuration, but do not require p>1.

#### D. Parameter binding correctness

Create project-owned gamma/beta mapping independent of arbitrary Qiskit parameter order.

#### E. Statevector objective

Implement expected energy evaluation.

#### F. Optimizers

Implement:

- SciPy COBYLA if available,
- mandatory NumPy/Python coarse-to-fine fallback,
- deterministic initialization,
- evaluation budget.

#### G. Bitstring codec

Implement centralized Qiskit count decoding and deterministic sanity circuit.

#### H. Single-job-safe final sampling

Final circuit only is submitted to remote/IonQ path.

#### I. QAOA result diagnostics

Return:

- gamma/beta,
- expected energy,
- raw counts,
- probabilities,
- feasible mass,
- optimum mass if oracle supplied,
- best feasible sample,
- modal sample,
- circuit qubits/depth/size if available,
- transpiled depth if available,
- timing breakdown.

#### J. Local toy problems

Include at least one tiny QUBO with known optimum to validate QAOA independently of battery data.

#### K. Default battery run

Run QAOA on default N=8/K=4 pool using local free simulator. Tune only generic optimizer settings/penalty behavior; do not alter future truth.

### Tests / validation

- Qiskit operator energies consistent with Ising evaluator,
- bitstring round-trip,
- known-state measurement decoding,
- p=1 ansatz constructs,
- fallback optimizer works without SciPy,
- no-feasible-sample behavior is explicit,
- default demo returns at least one feasible sample under verified settings,
- no remote backend called in parameter optimizer.

### Acceptance criteria

The project can run a real Qiskit QAOA circuit end to end, produce counts, decode them correctly, and quantify how the best sampled solution compares with exact optimum.

### Local commit

```text
feat: add Qiskit QAOA engine and one-job-safe backend sampling
```

---

## Task 6 — Reproducible benchmark suite, experiments, result assets, and scientific narrative

### Objective

Produce the evidence judges will evaluate instead of relying on one demo.

### Required work

#### A. Benchmark config

Commit fixed seed/trial configuration.

#### B. Benchmark runner

Implement CLI capable of:

- generating/reloading trial pools,
- running all baselines,
- running QAOA locally,
- optionally running selected backend experiment,
- writing incremental results safely so a crash does not erase completed trials.

#### C. Core experiment

Run enough valid trials (target 20+, adjust only if data coverage forces otherwise).

Compare:

- SOH sort,
- greedy,
- annealing,
- exact,
- QAOA.

#### D. Objective-ablation experiment

Use exact solver to compare:

- current-only selection,
- trajectory-aware selection,

then evaluate both with actual OPD. This is essential because it tests the domain hypothesis independently of QAOA performance.

#### E. QAOA quality report

Aggregate:

- best-sampled gap,
- optimum sampling rate,
- feasible mass,
- runtime breakdown.

#### F. Optional p/noise/scaling experiment

Only after required benchmark completes.

Priority order:

1. N scaling 6/8/10 if cheap,
2. p=1 vs p=2,
3. ideal vs available noisy simulator.

#### G. Export web assets

Create small `summary.json` and selected `trials.json` for instant UI replay.

#### H. Result integrity

Do not hand-edit benchmark JSON numbers. Generated assets should include config/provenance hashes.

#### I. Narrative summary

Add `docs/RESULTS.md` or README draft containing:

- what improved,
- where QAOA approximated exact well/poorly,
- predictor accuracy,
- limitations,
- no speedup claim.

### Tests / validation

- rerunning same config/seeds reproduces classical outputs,
- result JSON schema validates,
- all trials select K cells for constrained classical algorithms,
- no future truth included in pre-selection inputs,
- aggregate counts match number of valid trials,
- benchmark export loads without Python-specific types.

### Acceptance criteria

There is a credible aggregate result set with exact-oracle comparison and a domain ablation proving whether trajectory awareness helped on the available data.

### Local commit

```text
bench: add reproducible RePack-Q experiments and result exports
```

---

## Task 7 — Production-quality interactive UI and complete Python↔frontend integration

### Objective

Turn the scientific pipeline into a judge-friendly, visually distinctive, accessible interactive product.

### Required work

#### A. Implement design system

Create polished `styles.css` with tokens, responsive grid, panels, buttons, forms, charts, focus states, reduced-motion handling.

#### B. Implement state store

No hidden state in DOM.

#### C. Implement mission panel

- default mission,
- objective toggle,
- horizon/K controls only if valid for current data,
- assumptions disclosure.

#### D. Implement candidate inventory

Cell cards with pre-reveal information only.

#### E. Implement manual pack tray

- keyboard Add/Remove,
- optional drag/drop,
- K slots,
- live bottleneck metrics.

#### F. Integrate classical comparison

Render all classical solvers and exact oracle.

#### G. Integrate live QAOA

Use bridge from Task 1.

Display truthful staged state:

- preparing,
- parameter optimization,
- sampling,
- complete/error.

#### H. Implement quantum inspector

- qubits,
- p,
- gamma/beta,
- penalty,
- backend,
- shots,
- feasible probability,
- circuit metadata.

#### I. Implement probability chart

Top measured states, decoded correctly.

#### J. Implement future reveal

- hidden before reveal,
- explicit held-out label,
- extend trajectories after reveal,
- update OPD/future bottleneck.

#### K. Implement benchmark summary

Use precomputed exports; clearly label replayed aggregate data.

#### L. Error/loading/empty states

Design these intentionally. No raw Python errors shown.

#### M. Accessibility pass

Keyboard, semantics, contrast, 200% zoom, reduced motion, aria-live statuses.

#### N. Mobile/responsive pass

Test at roughly 390px, 768px, 1280px widths.

### Visual acceptance bar

The app should look intentionally designed, not like a form around console output. At minimum:

- consistent spacing/radii/typography,
- no default unstyled inputs,
- no layout jumps during runs,
- attractive battery cards and pack visualization,
- clear visual hierarchy,
- crisp SVG charts,
- quantum details integrated into the aesthetic,
- no decorative effects that obscure data.

### Tests / validation

Manual browser checklist from Section 24.4 plus:

- manual pack can be built without drag/drop,
- live QAOA button cannot double-submit,
- state resets when problem parameters change,
- future truth never leaks before reveal,
- exact and QAOA labels not confused,
- replay mode visually distinct from live mode,
- no console errors.

### Acceptance criteria

A judge can understand the problem, create a bad pack, run the quantum optimizer, compare algorithms, inspect QAOA measurements, and reveal held-out future data without reading source code.

### Local commit

```text
feat: build polished accessible RePack-Q interactive demo
```

---

## Task 8 — Qollab hardening, documentation, submission assets, and final local release commit

### Objective

Make the project submission-ready and eliminate last-mile failures.

### Required work

#### A. End-to-end Qollab verification

Test from a clean project/session:

- free local simulator,
- IonQ simulator if available,
- default live demo,
- result rendering,
- reload/reset behavior.

#### B. Dependency audit

Remove unused dependencies. Ensure no package requires paid services or separate deployment.

#### C. README finalization

Follow Section 26.

Include actual benchmark numbers generated by Task 6, not placeholder claims.

#### D. Qollab project-page copy

Create `docs/QOLLAB_PROJECT_PAGE.md` with polished copy ready to paste into Qollab.

Must cover:

- problem,
- public dataset,
- hybrid architecture,
- quantum subroutine,
- baselines,
- results,
- how to run,
- limitations,
- originality disclosure,
- attribution.

#### E. Demo video script

Create `docs/DEMO_SCRIPT.md` for a 2–3 minute video.

Suggested sequence:

1. 0:00–0:20 — why same-SOH cells can age differently.
2. 0:20–0:45 — real longitudinal dataset and held-out-future concept.
3. 0:45–1:05 — manually build a poor pack and show bottleneck.
4. 1:05–1:35 — run QAOA; show QUBO→Ising/Qiskit and probability distribution.
5. 1:35–1:55 — compare QAOA/classical/exact.
6. 1:55–2:20 — reveal real future data and OPD.
7. 2:20–2:40 — aggregate benchmark + limitations/impact.

Keep under 3 minutes.

#### F. Attribution and licensing

Verify:

- MIT `LICENSE`,
- required Qollab/IonQ sentence,
- external datasets/citations,
- external source-code references and disclosure,
- no copied incompatible assets.

#### G. Accessibility final pass

Run available audit tooling and manual keyboard pass.

#### H. Clean-run instructions

From a clean environment, execute documented local test/run commands. Fix stale documentation.

#### I. Repository hygiene

Before final commit:

- no raw datasets,
- no secrets,
- no temp screenshots unless intentionally used,
- no giant generated files,
- no failed experiment dumps,
- tests pass,
- benchmark provenance present.

#### J. Release checklist

Create `docs/SUBMISSION_CHECKLIST.md` with checkboxes for:

- Qollab publish,
- MIT license,
- public video URL,
- simulator test,
- attribution,
- project page,
- final deadline submission.

Do not actually push/publish unless the user explicitly asks.

### Tests / validation

- full automated test suite,
- clean local run,
- Qollab free simulator run,
- IonQ simulator smoke/live run if available,
- browser console clean,
- accessibility audit/manual pass,
- all README commands correct,
- links/citations valid.

### Acceptance criteria

The repository is locally complete, clean, documented, benchmarked, visually polished, and ready for the user to publish to Qollab without substantive engineering work.

### Local commit

```text
release: harden RePack-Q for Qollab hackathon submission
```

**Do not push this commit.**

---

# 31. Optional stretch backlog — only after Task 8 core requirements are safe

Prioritize by expected judging value versus implementation risk.

## Stretch A — Fixed-Hamming-weight QAOA / XY mixer

Goal: eliminate invalid cardinality samples by preserving exactly K excitations.

Requirements before attempting:

- standard QAOA works,
- benchmark exists,
- UI complete.

Compare:

- feasible shot fraction,
- best-sampled objective,
- circuit depth/gate count,
- runtime.

If implementation is uncertain, do not destabilize MVP.

## Stretch B — Multiple missions

Use Loughborough second-life stationary profiles to motivate distinct mission settings. Only claim mission-specific modeling if weights/horizons are tied to documented assumptions or data.

Possible second mission:

- frequency response: shorter/high-frequency cycling emphasis, stronger resistance/power sensitivity.

## Stretch C — NASA independent validation

Implement adapter and a small pack-level retrospective demonstration using the recommissioned NASA packs.

Keep chemistry/dataset separate from primary NMC trials.

## Stretch D — p-depth study

Compare p=1/2/3 on a fixed small trial set.

Report improvement versus increased circuit depth.

## Stretch E — noisy simulation

Evaluate fixed optimized parameters under available noise model.

## Stretch F — sensitivity analysis

Perturb objective weights ±20–30% and show whether selected packs/results are stable.

This directly addresses the arbitrariness concern around mission weights and could be especially valuable if time permits.

---

# 32. Final engineering principles for Codex

1. **Correctness over spectacle.** A beautiful wrong QUBO or reversed bitstring is worse than a simple correct implementation.
2. **No data leakage.** Future observations are sacred held-out validation data.
3. **Quantum is narrow and real.** QAOA solves the subset-selection QUBO; do not sprinkle quantum terminology over classical steps.
4. **Classical baselines must be strong.** Exact enumeration is the oracle at hackathon scale.
5. **Do not hide classical wins.** Honest benchmarking increases credibility.
6. **No quantum advantage claim.** This project demonstrates formulation and solution quality, not asymptotic supremacy.
7. **Portable by default.** No unnecessary servers, credentials, CDNs, or build systems.
8. **Accessibility is part of done.** Drag/drop cannot be mandatory.
9. **Every displayed number needs a source.** It must derive from live computation, stored benchmark output, or documented dataset metadata.
10. **Never call replayed results live.** Clearly label them.
11. **Keep the repository clean.** Raw GB-scale datasets stay out of git.
12. **Document deviations.** `DECISIONS.md` exists so new sessions do not repeat uncertainty.
13. **Commit locally after each task.** No push until the user explicitly requests it.
14. **Stop adding scope when the submission is already strong.** A finished p=1 system with rigorous validation beats a half-working advanced mixer.

---

# 33. Source and research references used for this specification

These are research/planning references; implementation must re-check platform APIs during Task 1.

## Qollab

- Hackathon terms: `https://qollab.xyz/programs/hackathon/terms`
- How it works: `https://qollab.xyz/programs/hackathon/how-it-works`
- Qollab learning/docs pages for runtime, Qiskit backends, primitives, and JS/Qiskit projects should be re-opened during implementation because platform APIs may change.

Verified hackathon requirements include use of Qiskit, accessibility best practices, free-simulator compatibility including IonQ's simulator, MIT licensing, a runnable Qollab project page, a public 2–3 minute demo video, and the Quantum Impact emphasis on a public dataset + strong classical baseline + quantum subroutine.

## Primary battery dataset

- Wang, Gao, Tian, **Data for: Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions**, Zenodo DOI `10.5281/zenodo.14859405`.
- Associated code release, Zenodo DOI `10.5281/zenodo.15350607`.
- Public repository: `https://github.com/wshuquan/Deep_sorting_of_reused_batteries`

Important facts to preserve: 86 NMC(532)/graphite batteries; 2.4 Ah nominal capacity; primary-use aging to ~80% SOH; standardized second-life cycling toward ~50%; voltage/current/internal-resistance/surface-temperature signals; 88k+ cycles; ~145M datapoints.

## Independent validation dataset

- NASA, **Randomized and Recommissioned Battery Dataset**: `https://data.nasa.gov/dataset/randomized-and-recommissioned-battery-dataset`

Important relevance: 26 two-cell 18650 packs and second-life packs assembled from surviving previously aged cells.

## Mission context

- **Long-Term Sweat Testing Dataset for Second-Life Batteries**, Scientific Data (2025), with multiple real-world-inspired stationary storage use cases including PV, PV+TOU, TOU, frequency-response cases, and day-ahead trading.

---

# 34. Spec approval state

Unless the user explicitly changes a major design decision, the following are considered **locked defaults** for implementation:

```text
Project name: RePack-Q
Primary dataset: 86-cell NMC reused-battery longitudinal dataset
External validation: NASA recommissioned dataset (optional but prioritized stretch)
Default mission: residential PV + time-of-use
Pack topology: one series string
Default candidate size: N=8
Default pack size: K=4
Primary horizon: H=200 cycles, adjustable if data coverage requires
Prediction: leakage-free weighted linear recent-trajectory estimate
Quantum formulation: fixed-cardinality QUBO via penalty
Quantum algorithm: Qiskit QAOA p=1
QAOA parameter optimization: local statevector; COBYLA when available; built-in fallback otherwise
Backend strategy: final sampling through Qollab; single-job-safe remote path
Classical baselines: SOH sort, compatibility greedy, simulated annealing, exact enumeration
Headline validation metric: Observed Pack Divergence (OPD)
Headline quantum metric: best-sampled optimality gap + feasible probability mass
UI stack: minimal/portable Qollab-compatible HTML/CSS/JS + Python/Qiskit bridge
License: MIT
Git policy: local commits only until user explicitly asks to push/publish
```

Any change to a locked default must be written to `DECISIONS.md` with a reason.

