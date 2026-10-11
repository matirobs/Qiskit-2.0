# RePack-Q

Predict how retired batteries will age, then compare algorithms for choosing
compatible groups. The working project includes capacity prediction, four
classical selection methods, and two Qiskit quantum selection methods.

## Run the project

From this folder, with Python 3.10 or newer:

```bash
export PYTHONPATH=src

# Add Qiskit support for the two quantum algorithms (optional for classical runs).
python3 -m pip install -e '.[quantum]'

# Open the interactive battery workbench in your browser.
python3 -m repackq dashboard

# Compare four classical algorithms using the cached real battery histories.
python3 -m repackq compare

# Predict capacity after another 200 cycles for recorded battery 9.
python3 -m repackq predict --cell 9 --cutoff 0 --horizon 200

# Demonstrate selection without a trained model or real data.
python3 -m repackq compare --synthetic

# Compare both quantum algorithms with the four classical algorithms.
python3 -m repackq compare --quantum

# Show available commands and options.
python3 -m repackq --help
python3 -m repackq compare --help
```

The [battery workbench](docs/guides/dashboard.md) shows interactive predictions,
classical and quantum comparisons, and recorded benchmarks. With Qiskit installed,
both quantum methods run automatically when the workbench opens. Uncheck
**Include both quantum algorithms** for a faster classical-only run. A clean clone
includes the trained weights, compact real battery histories, and saved results.
The dashboard samples its shared candidate pool from all 86 batteries by default;
the battery-source control can restrict it to the 14 held-out test batteries.
All-cell comparisons include batteries used in training or tuning and are
exploratory. The command-line comparison and saved benchmark retain their
test-only defaults; use `python3 -m repackq compare --partition all` for an
all-cell source there too.

Prediction, classical selection, and the dashboard without quantum runs use Python's standard library. They do
not retrain the model, reread the raw measurements, or require Java. Real-data commands use the
included model in `models/` and compact histories in `data/processed/`.
Use `--synthetic` for the explicitly invented demonstration.

Optionally install with `python3 -m pip install -e .` to use `repackq compare`
directly. Offline preparation/training dependencies are a separate extra:
`python3 -m pip install -e '.[training]'`. Training also needs a Java Development
Kit version 17 or newer; see the [training guide](docs/guides/training.md).

## Find things

| Folder | Contents |
| --- | --- |
| [src/repackq/dashboard](src/repackq/dashboard) | Local browser interface and solver integration |
| [src/repackq/quantum](src/repackq/quantum) | Size-penalty and cell-swap quantum algorithms in Qiskit |
| [src/repackq/prediction](src/repackq/prediction) | Runtime prediction and history features |
| [src/repackq/classical](src/repackq/classical) | The four selection algorithms and comparison command |
| [src/repackq/optimization](src/repackq/optimization) | Shared group-scoring problem for all solvers |
| [models](models/README.md) | Active model and its evaluation |
| [results](results/README.md) | Saved classical benchmark and quantum smoke-test reports |
| [data](data/README.md) | Prepared battery histories and preparation caches |
| [docs](docs/README.md) | Guides and experiment findings |
| [src/repackq/training](src/repackq/training) | Optional offline trainers and tuning programs |
| [java](java) | Neural-network source, training bridge, and MIT license |
| [tests](tests) | Verification of prediction, selection, and training |

Raw measurements remain local in `Primary_use_phase/` and `Second_life_phase/` at the
root and are excluded from GitHub. They are only needed to reproduce preparation
or training. New temporary training
outputs go under ignored `build/training/`, rather than cluttering `models/`.

## Results and project status

The original smaller model remains the default: larger networks and longer
training did not consistently improve prediction. The classical benchmark also
shows tradeoffs between future matching and retained capacity. Read the
[documentation index](docs/README.md) for the actual results and limitations.

Run all checks with `python3 -m unittest discover -s tests -v` after installing
training dependencies. The active weights, evaluation, compact histories, saved
reports are included. Old training archives were removed; see the
[training guide](docs/guides/training.md) for their Git history. Source data
uses Creative Commons Attribution 4.0, separately from the software's MIT license;
see [data attribution](data/LICENSE.md). Qollab simulator runs, publication, the project
page, and the public demo video remain pending; this is not yet a completed
hackathon submission.

The submission must use Qiskit, run on Qollab's free local and IonQ simulators,
and be published and runnable on Qollab under MIT before the organizer's
deadline. Required outside code repositories must also use MIT. The Qollab
project page must explain the problem, approach, and reproduction steps. Submit
the GitHub repository with a public 2–3 minute demo video that opens without
signing in. Disclose reused work; judging concerns additions during the build
window. These requirements remain mandatory as development continues.

## Sources and licensing

Java `Network.java` and `Parser.java` predate the hackathon,
originating as Spring 2026 ATCS Neural Networks coursework at The Harker School.
Their original header dates are May 8 and April 29, 2026, respectively. Source:
the owner's `neuralnets` framework, revision
`f0eebb0be2d256c2d93af95b114f1cd7458dee60` from July 9, 2026.
The owner authorized MIT licensing on October 10;
the notice remains in [java/LICENSE](java/LICENSE). Battery features,
Java/Python integration, validation, tuning, portable inference, selection,
and the dashboard were added for this project. Coding assistance was provided
by Codex. Pre-existing planning and the starting repository must also be
disclosed in the submission.

Quantum approaches reference the unfinished standard sketch and swap algorithm
in [matirobs/Qiskit-2.0](https://github.com/matirobs/Qiskit-2.0/tree/2147ecb0d929b48be3667c5c31795ac9ecf172fd),
inspected October 10. Project modules reimplement the approaches using the shared
battery objective; upstream demonstration scripts are not runtime dependencies.
That revision had no license file, and MIT permission for upstream source
remains unconfirmed. The removed local draft and detailed historical notes are
recoverable from Git history. Local completion does not resolve this licensing
gate or prove Qollab compatibility.

Battery data attribution and its separate Creative Commons Attribution 4.0
terms remain in [data/LICENSE.md](data/LICENSE.md). No battery-sorting source
code from the dataset authors' repository was copied.

This effort is supported by Qollab & IonQ
