# Battery workbench

From the project folder, start the local browser interface with Python 3.10 or newer:

```bash
PYTHONPATH=src python3 -m repackq dashboard
```

The command opens `http://127.0.0.1:8765`. Stop it with Ctrl+C in the terminal.
Use `--no-browser` to start without opening a tab, or `--port 8766` if the
port is occupied. There is no frontend build step, Java runtime, training job,
paid service, or account. Quantum runs require `python3 -m pip install -e '.[quantum]'`.
Classical-only runs need no additional Python dependency.

The left sidebar contains only the section menu. Its highlight follows the
section you are reading as you scroll; click an item to jump there directly.
On phones, the same menu stays at the top while the content scrolls below it.

## Explore a run

1. Choose the battery source: **Full dataset · 86 batteries** is the default;
   **Held-out test batteries · 14** restricts the source to the original test set.
   Choose the forecast horizon, known history, sampled candidate count, and
   group size. The pool seed repeats a random candidate sample and also controls
   randomized solvers; it is not a model-training setting. Candidates are sampled,
   not ranked as the best batteries in the source inventory.
2. Choose **Match for today** or **Match for the future**. Changing settings
   clears the old selection so results cannot silently refer to a different run.
3. Press **Run comparison**. The existing Python predictor and four classical
   solvers compute on the same candidates. With **Include both quantum algorithms**
   enabled, both Qiskit circuits also run on the free local simulator. Click a method in the table to see
   its selection, or click cell cards to build and score a group yourself.
4. Inspect current capacity and predicted future spread. Capacity is in
   amp-hours, abbreviated Ah. Current group capacity uses the smallest cell's
   capacity as a simple series-string proxy. Chart lines only connect two
   endpoints; they are not measured or simulated degradation curves.
5. Press **Reveal actual future** to inspect recorded outcomes withheld from
   selection. Filled markers use the nearest eligible reference-test cycle;
   their tooltips show the measurement cycle and its distance from the target.
   Changing groups after revelation is exploratory, not a blind experiment.
6. **Export run** downloads a JSON (JavaScript Object Notation) file containing
   the settings, snapshots, selections, scoring coefficients, and any explicitly
   revealed measurements. An unrevealed export has no future measurements.

Actual future measurements are retained on the Python side until reveal. The
service keeps the most recent 32 trials in memory; restarting it clears them.
The interface serves only its four static assets and explicit operations on a
loopback address. It does not expose arbitrary repository files or raw data.

## Real data and portable sample mode

The repository includes `models/capacity_model.json` and
`data/processed/cell_histories.json`. Their dataset checksums must agree. The
interface reads compact cached histories, not the large raw phase folders.
Real pools default to the full 86-cell inventory, including batteries used to
train or tune the predictor. This is exploratory selection, not a held-out
accuracy assessment. Every solver receives the same smaller sampled pool of
6–12 cells. It does not optimize over all 86 simultaneously. The optional test
source retains the original restriction to 14 batteries excluded from fitting.

The pool summary displays the source size, eligible count, sample size, seed,
and selected candidates' training/validation/test membership. Eligibility needs
enough observed history, at least 50% current health, and a future reference
measurement close enough to check the chosen horizon afterward. Future capacity
values never determine eligibility, prediction, or selection. At cutoff zero
and horizon 200 all 86 cells qualify; other settings can exclude cells, with
identifiers and reasons shown below the summary. Too few eligible cells produce
an error instead of invented observations. Exports retain the scope and metadata.

A checkout missing these assets labels its battery source **Invented sample batteries**.
A normal clone includes them and uses real data. To force sample mode:

```bash
PYTHONPATH=src python3 -m repackq dashboard --synthetic
```

Sample mode uses eight invented cells and a fixed 200-cycle horizon, with no
recorded future. Group size, objective, and annealing seed remain adjustable;
the pool itself is fixed. It never invents prediction-accuracy or benchmark
results. Present but corrupt or mismatched real assets produce an error instead
of silently changing to sample data. Alternate assets can be selected with
`--model /path/to/model.json --data /path/to/cell_histories.json`.

The saved evaluation panel shows `models/evaluation.json` only when its dataset
checksum matches. It is labeled as the **recorded baseline** rather than the
accuracy of the current group or the full 86-cell inventory. The saved 20-pool comparison is loaded from
`results/classical-benchmark-20-seeds.json` only when both model and dataset
checksums match. Its horizon, cutoff, pool size, and group size remain explicitly
fixed to the original test-only experiment independently of workbench source
and settings. Switching the objective displays the
corresponding saved mode. These overlapping pools and previously inspected test
cells are exploratory evidence. Healthiest-first performed better on the saved
physical metrics; the interface does not hide that result.

## Quantum selection

`src/repackq/dashboard/quantum.py` connects the size-penalty and cell-swap versions
of the quantum approximate optimization algorithm to the same scoring instance.
With Qiskit installed, both run automatically when the workbench opens. Uncheck
**Include both quantum algorithms** for a faster classical-only comparison.
Without Qiskit, that control is disabled and the interface shows installation
instructions. No stored distribution is presented as live execution.

Quantum selections appear alongside classical methods in the comparison table.
The capacity outlook spans the available width; the separate quantum panel and
illustration have been removed. Detailed sampling diagnostics remain in the
exported run. Invalid samples are not silently repaired. A method with no valid
measured group has no selection row; its status remains in the export.

Both methods return the common selection contract only after Qiskit sampling,
with exactly the required number of indices and the shared objective score.
Future measurements are not passed to these solvers. The local
`GET /api/problem?trial_id=…` operation exports scoring inputs without future truth.
See the [quantum guide](quantum.md) for implementation, command options, source
provenance, and the backend-injection interface.

## Hackathon status

This is a local preview and reusable presentation layer, not evidence of Qollab
publication or simulator compatibility. Qollab's supported Python/browser bridge
must be verified and connected separately; judges must not need a separately
hosted server. Actual Qiskit execution on both required Qollab free simulator paths,
MIT publication on Qollab, the project page, public video, and submission remain
open requirements described in the [project overview](../../README.md).
Code uses the project's MIT license. Included compact
histories and derived records retain the source attribution and Creative Commons
Attribution 4.0 terms in data/LICENSE.md; large raw datasets and caches stay local.

## Verification

Dashboard checks cover missing/mismatched assets, hidden future measurements,
manual selection constraints, live quantum integration, missing quantum dependencies, static files,
operation round trips, and rejection of unrelated file paths and cross-origin
mutations. Run the full suite with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The HTTP (Hypertext Transfer Protocol) checks need permission to bind a temporary
localhost port. Browser checks cover real runs, manual groups, future reveal,
changed settings, recorded evidence, export, and desktop/mobile layouts.
