# Battery data attribution

Source: **Data for: Deep sorting of reused batteries for enabling long-term
consistency grouping with unknown prior conditions**, by Shuquan Wang, Feng Gao,
and Hao Tian (Shandong University), version v1, February 12, 2025.

- Dataset: https://doi.org/10.5281/zenodo.14859405
- Source record: https://zenodo.org/records/14859405
- License metadata: https://zenodo.org/api/records/14859405
- License: **Creative Commons Attribution 4.0 International (CC BY 4.0)**
- License terms: https://creativecommons.org/licenses/by/4.0/
- Legal code: https://creativecommons.org/licenses/by/4.0/legalcode.en

The Zenodo record's `metadata.license.id` was verified as `cc-by-4.0` on
October 11, 2026. This license permits sharing and adaptation with attribution,
a license link, and an indication of changes. No endorsement by the dataset
authors is claimed, and the dataset is supplied without warranties.

RePack-Q transforms the source measurements into per-cell first-life and
second-life reference-discharge summaries in `processed/cell_histories.json`.
It selects comparable diagnostic discharge tests and computes capacity,
resistance, temperature, and cycle summaries. This file is a reduced derivative,
not the full raw dataset. Its provenance retains source filenames, sizes, and
checksums. Local account paths were replaced with relative source paths;
measurements remain unchanged from the cache used to train the active model.
The model and reports retain original hashes in `metadata_revision` and
reference updated artifact checksums in their regular provenance fields.

Battery observations and derived values included in `models/evaluation.json`,
`results/*.json`, and the archived training records retain this attribution and
the source license where applicable. Learned weights and preprocessing settings
are our generated model artifacts. The repository's MIT license covers project
software; it does not replace the battery dataset's CC BY 4.0 terms.

The multi-gigabyte raw measurements are not included. They can be downloaded
from the source record when reproducing offline preparation or training.
