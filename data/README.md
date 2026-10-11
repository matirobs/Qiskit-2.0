# Data locations and preprocessing

The official raw dataset belongs under `data/raw/`, which is ignored by Git.
The preprocessing CLI reads extracted CSV files, a phase directory, or the
official ZIP archive directly; it never modifies or extracts the raw files.

```sh
python src/scripts/inspect_dataset.py --raw-root data/raw --phase second_life --summary
python src/scripts/preprocess_primary.py \
  --raw-root data/raw/Second_life_phase.zip \
  --phase second_life \
  --nominal-capacity 2.4 \
  --output data/processed/trajectories.json
```

The first command scans every row by default and can take time on the original
large files. Use `--max-rows-per-file N` for an explicitly sampled inspection.
Use `--summary` to print global schema/range results and representative steps
without the per-file detail list.
The preprocessing command writes a compact trajectory JSON, a provenance file
with per-CSV SHA-256 checksums, and a data-quality report. Checksum values refer
to the uncompressed CSV contents, including when a CSV is read from a ZIP.
`--inspect-only` on the preprocessing command prints the raw inspection and
writes no files.

Zenodo’s record metadata lists the source dataset under the Creative Commons
Attribution 4.0 International license (CC BY 4.0). Derived data may be shared
under those terms when appropriate credit is given, the license is linked, and
changes are identified. The generated `derived-real` cell records remain local
to keep full cell-level measurement tables out of the committed demo. The
trajectory and per-file summary output paths are ignored by Git; the provenance
file contains no battery measurements. Synthetic adapter
fixtures live under `tests/fixtures/`, and `data/fixtures/synthetic_demo.json`
provides an eight-cell canonical example for local UI development. They are
hand-authored synthetic data, not observations or benchmark results from the
battery campaign. The demo asset follows only the source metadata's approximate
50%-80% SOH span; resistance and temperature are null because no synthetic
values are needed for the basic UI example.

For Deep Sorting, the filenames are original experiment identifiers while
`Battery_ID` values are separate manuscript identifiers. The unavailable
originally labeled cells 61 and 62 correspond to absent source files `61.csv`
and `62.csv`; an embedded `Battery_ID` of 61 or 62 can therefore identify a
different, present file. The canonical trajectory uses `Battery_ID` when it is
available. See the [Zenodo record](https://zenodo.org/records/14859405) for the
identifier distinction.

After producing a local real-data trajectory file, Task 3 outputs can be made
with `src/scripts/evaluate_predictor.py` and `src/scripts/build_demo_pools.py`.
Their default outputs are `data/processed/prediction_evaluation.json` and
`data/processed/demo_pools.json`. The demo-pool command refuses synthetic
fixtures, records its fixed seeds and default-pool selection rule, and stores
held-out future values separately from decision-time snapshots. These outputs remain local in this workflow. If derived data are shared, follow the source dataset’s CC BY 4.0 attribution, license-link, and change-notice requirements.
