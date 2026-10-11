# Attribution

**This effort is supported by Qollab & IonQ**

RePack-Q uses the following external resources. The raw battery data are not
included in this repository. The independent adapter and preprocessing
pipeline cite the dataset and the public code release used to verify the raw
schema and diagnostic-cycle cadence.

- Primary battery dataset: Wang, Gao, and Tian, *Data for: Deep sorting of reused batteries for enabling long-term consistency grouping with unknown prior conditions*, Zenodo DOI [10.5281/zenodo.14859405](https://doi.org/10.5281/zenodo.14859405), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Zenodo API metadata reports `cc-by-4.0`; when sharing derived data, retain attribution, link the license, and identify changes.
- Associated public code release, for research reference only: Zenodo DOI [10.5281/zenodo.15350607](https://doi.org/10.5281/zenodo.15350607). No code from this release has been copied into this repository.
- Dataset file/schema reference: [version 1.0.0 extraction script](https://github.com/wshuquan/Deep_sorting_of_reused_batteries/blob/v1.0.0/Feature_engineering/3_capa_trajectory_extraction.py). It is cited as a schema and sampling reference only; RePack-Q independently implements CSV parsing and summaries.
- Qiskit: the open-source quantum software development kit by IBM and its contributors. See the [Qiskit project](https://github.com/Qiskit/qiskit) and [official API documentation](https://qiskit.qotlabs.org/docs/api/qiskit).
- Qollab hackathon information: [terms](https://qollab.xyz/programs/hackathon/terms) and [how it works](https://qollab.xyz/programs/hackathon/how-it-works), as listed in `SPEC.md`. Platform-specific runtime details still require verification in Qollab.

## Originality disclosure

Pre-build work consisted of problem selection, dataset research, and implementation planning. Project implementation, integration, experiments, UI, and submission materials were developed during the hackathon build window. Codex was used as an AI coding assistant for implementation, debugging, and documentation. Public datasets, Qiskit, and cited open-source references are used as a data source, software dependency, or research reference and are attributed. No source code from the associated Deep Sorting code release was copied.
