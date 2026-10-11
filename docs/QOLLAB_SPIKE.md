# Qollab Python runner and UI bridge

The root `main.py` is the Python-mode entry point. Running it directly prints a
dependency-free environment report and exits without importing Qiskit or
running a circuit. The Task 8 release adds a separate Python smoke package that
imports the project, checks Qiskit, and runs a small synthetic QAOA circuit on
Qiskit's local `BasicSimulator`.

## Task 8 clean-session check

Build the two release archives from the project root:

```sh
python scripts/package_qollab_release.py
```

Upload `qollab-task8-python-smoke.zip` as a Python-mode project and run its
`main.py`. Copy the complete JSON output. This checks Qollab's Python package
environment and local Qiskit `BasicSimulator` execution. It does **not** call a
Qollab-provided free simulator/backend, submit an IonQ job, or test browser to
Python calls. The report lists names, types, and public method names for any
backend-like objects exposed in the entry-point namespace; it does not print
object values or credentials.

The clean-session run succeeded on Python 3.14.2 with Qiskit 2.5.2, NumPy
2.4.6, and SciPy 1.18.0. The synthetic p=1, four-qubit, K=2 trial used 512
shots, returned a feasible sample with zero objective gap, and completed one
`BasicSimulator` sampling job. The report exposed a global `backend` instance
whose exact type is Qiskit's `BasicSimulator`. A second run passed that injected
instance into QAOA and confirmed `available: true`, `used_for_qaoa: true`, one
sampling job, and no remote submission. This completes the clean Python and
host-exposed local simulator check; sampling counts vary between runs.

The user uploaded `qollab-task8-app.zip` in HTML/JS mode and confirmed that the
page loads, replay labels and reload/reset behavior work, and no browser errors
were found. The Qollab guide now documents importing Python modules from
JavaScript and using `.callPromising(...)` for Python calls that submit
circuits. The bridge has completed live QAOA sampling on the built-in and AWS
simulators. The IonQ Aria path was retried after moving submission and result
collection inside a Python function invoked through Qollab's documented
`.callPromising(...)` API. It still fails before returning a submission
response, job ID, or result; details are recorded below.

## Dependencies and execution scope

The Qollab ZIP places the Python package at its root so the project loader can
resolve the explicit `repackq.*` imports without a runtime-added `src` search
path. The repository itself retains its normal `src/` layout.

The implementation uses Qiskit core (`QuantumCircuit`, `SparsePauliOp`,
`Statevector`, `transpile`, and `BasicSimulator`). It has its own p=1 QAOA
parameter optimizer and does not require the Qiskit Algorithms or Qiskit
Optimization add-on packages. It does not draw circuits, so Qiskit
Visualizations is also unnecessary. SciPy is optional: it enables COBYLA for
direct callers, while the packaged demo uses a deterministic grid optimizer.
No paid service or separate deployment is required.

The optimizer uses a deterministic grid/refinement method, so SciPy is not
required. `run_task5_toy_demo()` uses synthetic cells only and does not submit
a Qollab or IonQ backend job. The package-version diagnostic does not prove
that Qiskit imports or runs successfully; the separate `qollab_runtime_probe()`
can perform that smoke check if the host can invoke Python functions.

## Qollab runtime validation

The Task 5 record reports a Qollab Python-runner check on Qiskit 2.5.2. Its
p=1, four-qubit, K=2 run used 512 local `BasicSimulator` shots and one local
sampling call. Exhaustive QUBO mapping verification passed. The best measured
feasible sample matched the exact optimum (`TOY-0`, `TOY-1`) with zero
objective gap; feasible sampling mass was 0.6074 and exact-optimum sampling
mass was 0.2441. The report also identified an infeasible cardinality-1
sample, as expected from the raw counts.

The Task 5 and Task 8 Python smoke runs validate the Qollab Python environment
and its host-exposed local `BasicSimulator` path. A separate HTML/JS project run
completed on the AWS simulator after the bridge was added. The circuit uses
synthetic data and is not a battery-data result.

## Task 7 browser application

The project includes the RePack-Q workbench at `web/index.html`, host-callable
UI functions in root `main.py`, and a local HTTP server in
`run_repackq_web.py`. The complete Python API lives in `src/repackq/ui.py`; it
returns decision-time snapshots separately from held-out fixture observations.
The optimizer and QAOA wrapper never receive future truth. Future values are
returned only by the reveal API after the UI's explicit reveal action.

The local browser/Python contract is documented in
[`web/js/components/README.md`](../web/js/components/README.md). On loopback
hosts, the browser registers a same-origin HTTP adapter and QAOA stages stream
back to the UI as they occur. Other hosts require their own verified adapter.
Qollab's Python project mode runs `main.py` and displays text output. Its
HTML/JS mode requires root `index.html` and `main.js`, which now boot the
workbench; root `styles.css` supplies the preview stylesheet.

Build the app and Python smoke packages on Windows, macOS, or Linux:

```sh
python scripts/package_qollab_release.py
```

The command creates `qollab-task8-app.zip` and
`qollab-task8-python-smoke.zip`. The app ZIP contains both project modes:
Python API entrypoint `main.py` and standalone HTML/JS entrypoints `index.html`
and `main.js`. The packager embeds `styles.css`, compiles the browser modules,
and inlines preview assets. The HTML/JS page does not fetch nested modules,
stylesheets, or JSON assets. Its interactive inventory and held-out reveal are
synthetic, while the benchmark panel shows aggregate derived-real results.

The Python smoke ZIP is a separate Python-mode project. Its `main.py` prints a
safe runtime report, runs Qiskit's local `BasicSimulator` smoke test, and runs
the four-candidate synthetic p=1 QAOA demo with 512 shots. It never discovers
or submits a remote backend job. This is the package to upload to Qollab's
Python mode when checking the current Python/Qiskit environment. Copy the
complete JSON output for review.

The Qollab HTML/JS package uses the documented Python-module import and
`.callPromising(...)` interface through `repackq_qollab_bridge.py`. Its
interactive inventory, evaluation, classical solvers, QAOA preparation and
result analysis, and explicit future reveal use the packaged Python API. For
QAOA, Python optimizes parameters on an ideal local statevector and transpiles
the measured circuit against the selected Qiskit-compatible backend. The
JavaScript adapter calls `submit_qaoa_circuit()` through `.callPromising(...)`;
that Python function invokes the selected backend's `run()` and collects the
result counts. Only the explicit **Run QAOA** action submits a sampling job.
If a live QAOA call fails, the page reports a shortened exception summary with
common credential formats redacted and exposes the traceback in the inspector.
The Qollab call reports the Python preparation and sampling stages; the local
HTTP adapter reports the finer internal stages. The replay remains available
if the Python bridge cannot load.
The bridge embeds the synthetic fixture in a generated Python module and loads
it in memory. This avoids fixture file reads, which the hosted runtime rejected
with `OSError: [Errno 29]` during inventory initialization. The hosted AWS
simulator and the local BasicSimulator have each completed live QAOA runs. The
selected-backend transpilation path also completed
on the AWS simulator (8 logical qubits, transpiled depth 42, 108 operations,
27.9% feasible mass, and zero best-sample objective gap for that synthetic
pool). The Qollab-selected IonQ Aria 1 backend was retried through the updated
`.callPromising(...)` submission path. The traceback reaches
`qiskit_ionq.IonQBackend.run()` → `IonQJob.submit()` →
`IonQClient.submit_job()` → `requests.post()`, then urllib3's Emscripten fetch
raises `TypeError: Failed to fetch`. No submission response, job ID, or
measured counts were returned. An earlier OPTIONS check to IonQ used origin
`https://qollab.xyz` and returned no `Access-Control-Allow-Origin` header,
though Qollab's runtime documentation says JS project requests use origin
`null`, so the check does not exactly match the app request. More directly,
Qollab's [runtime environment documentation](https://qollab.xyz/learn/docs/runtime-environment)
states that project network access allows `GET` requests while blocking
`POST`, `PUT`, and `DELETE`. Since `qiskit_ionq` submits jobs with `POST`, the
current browser-side provider cannot submit an Aria job in this runtime. A
Qollab-supported server-side IonQ submission path is required; changing the
QAOA circuit or Python call wrapper cannot override this policy. Qollab offers
no IonQ simulator in the available QPU list. Do not present simulator results
as IonQ hardware results.

The app targets Qiskit-compatible backends exposed by Qollab and compiles the
final measured circuit for the selected backend. Submission and result polling
now run in `submit_qaoa_circuit()` through the Python bridge's
`.callPromising(...)` invocation. This follows Qollab's documented pattern for
Python calls that submit IonQ jobs, but Qollab's network policy still blocks
the provider's outgoing `POST`. Other providers need a Qiskit-compatible
backend adapter and a Qollab-supported job submission path in the hosted
runtime.

## Run the hosted bridge check

1. Rebuild the archives with `python scripts/package_qollab_release.py` and
   upload the new `qollab-task8-app.zip` as an HTML/JS Qollab project. The
   package embeds the synthetic fixture in `repackq_qollab_fixture.py` so the
   hosted bridge does not need to read JSON files.
2. Start the project using Qollab's Run Project flow and choose a free
   simulator in the Select QPU dialog.
3. Confirm the page says **Python bridge ready**, change a horizon or pack
   size, and run the classical comparison. These actions call Python but do
   not submit a quantum backend job.
4. Click **Run QAOA**. This runs local statevector parameter optimization and
   submits one final sampling job to the selected simulator. Confirm that a
   live result appears with a backend name, shot count, feasible samples, and
   circuit summary.
5. Copy the `RePack-Q live QAOA result` entry from Qollab's run console, or the
   `RePack-Q live QAOA failed` error if it does not complete. Do not select
   hardware during this check; hardware use can consume credits.

The Qollab JavaScript guide describes the runtime contract at
<https://qollab.xyz/learn/building-your-first-qollab-project/run-in-javascript>.

On Windows, `Launch RePack-Q.bat` creates a project-local environment, installs
the pinned dependency on first use, and opens the live local workbench. On any
platform, `python run_repackq_web.py` serves the same-origin Python API at
`http://127.0.0.1:8000/` and uses `BasicSimulator` for local QAOA.
