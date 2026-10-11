# RePack-Q submission checklist

## Project and evidence

- [x] MIT `LICENSE` is present.
- [x] Required attribution text is present: **This effort is supported by Qollab & IonQ**.
- [x] Main README includes the project architecture, actual benchmark results, local/Qollab run instructions, limitations, and licensing notes.
- [x] Originality, AI assistance, dataset, and open-source disclosures are included in the README and project-page copy.
- [x] Qollab project-page copy is ready in [`QOLLAB_PROJECT_PAGE.md`](QOLLAB_PROJECT_PAGE.md).
- [x] Benchmark results and provenance are documented in [`RESULTS.md`](RESULTS.md).
- [x] Two-to-three-minute video script is ready in [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).
- [x] Run the Task 8 Python smoke ZIP in a clean Qollab Python project and retain its JSON output; Python 3.14.2/Qiskit 2.5.2 passed.
- [x] Identify and test the host-exposed local `BasicSimulator` backend (one QAOA sampling job; no remote submission).
- [x] Complete one live QAOA sampling run on Qollab's AWS simulator.
- [x] Recheck the AWS simulator path after adding selected-backend transpilation; 8-qubit circuit completed, transpiled depth 42, 108 operations, 27.9% feasible mass, zero best-sample objective gap.
- [x] Upload the standalone app to Qollab and verify that the page renders without browser errors.
- [x] Verify replay labels and reload/reset behavior in Qollab.
- [x] Package the Qollab JavaScript-to-Python adapter using the documented module import and `.callPromising(...)` API.
- [x] Verify live QAOA result rendering through the Qollab browser-to-Python bridge on an AWS simulator.
- [x] Retry IonQ Aria 1 through the `.callPromising(...)` path. The provider still fails at Emscripten `fetch` during `requests.post()` before returning a job ID or measured counts.
- [ ] Ask Qollab for a supported server-side IonQ submission path, then rerun Aria and record the QPU job/result. Qollab's browser runtime blocks outbound POST requests; it does not expose an IonQ simulator.
- [ ] Complete the final keyboard and accessibility pass; record the result.
- [ ] Run the documented local test suite from a clean environment and record the result if this has not already been completed.
- [ ] Record and publish the public demo video; add its URL to the README, project page, and submission.
- [ ] Publish the MIT-licensed project on Qollab.
- [ ] Submit before the hackathon deadline.

## Data and release hygiene

- [x] No raw dataset files are included.
- [x] The shipped interactive inventory and reveal are labeled synthetic.
- [x] The benchmark replay contains aggregate derived-real metrics without cell IDs or pack membership.
- [x] Source dataset CC BY 4.0 terms are documented; derived-data reuse requires attribution, a license link, and a change notice. The browser demo uses synthetic cell records and aggregate benchmark outcomes.
- [x] External dataset, code-reference, Qiskit, and Qollab references are listed in [`ATTRIBUTION.md`](../ATTRIBUTION.md).
- [ ] Review the final rebuilt ZIP and Qollab page before submission.
