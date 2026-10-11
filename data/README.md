# Battery data

`processed/cell_histories.json` contains the cached reference-capacity histories
used by the active model. Its checksum must match the model's recorded input
checksum. Other files under `processed/` are reusable preparation caches.

The original measurements remain in `Primary_use_phase/` and
`Second_life_phase/` at the project root. They were not moved or deleted during
cleanup, so existing provenance and resumable preparation remain valid.
Some source files are cloud-only; full measurement preparation is still pending.

The compact `processed/cell_histories.json` is included in Git, allowing normal
prediction and selection without downloading raw measurements. Raw datasets,
diagnostic caches, and usage caches stay local and ignored. The source record's
Creative Commons Attribution 4.0 license was verified on October 11, 2026;
see [LICENSE.md](LICENSE.md) for attribution and transformation details.
Local account paths in the runtime file were replaced with relative source
paths. Battery observations and trained weights are unchanged. The model and
saved reports reference the current file checksums; `metadata_revision` retains
the original hashes and explains the metadata-only changes. Current artifact
checksums are listed in `runtime-assets.json`. Its embedded redistribution-status string
records the earlier preparation decision; this notice supersedes that status.
