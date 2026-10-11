# RePack-Q demo video script

**Target length: 2 minutes 40 seconds.** For the live QAOA segment, use the Qollab HTML/JS package with its built-in or AWS simulator; both paths have completed live runs. The local workbench with `BasicSimulator` is also suitable. Do not select IonQ Aria: Qollab's runtime blocks the provider's outgoing `POST`, so an Aria job cannot currently be submitted from this project. If a live simulator run is unavailable while recording, use the clearly labeled replay. Never describe the synthetic reveal as real battery truth or a simulator run as hardware execution.

| Time | Visual and narration |
| --- | --- |
| 0:00–0:20 | **Show two cells with similar present SOH.** “Two used cells can look alike today and still age differently. RePack-Q asks whether matching on estimated future capacity can form more balanced second-life groups.” |
| 0:20–0:43 | **Show the synthetic-fixture label, then the benchmark panel's Deep Sorting source and 20-trial summary.** “The interactive inventory is synthetic. Separately, the retrospective study uses the public 86-cell Deep Sorting battery dataset. At each decision cutoff, the offline evaluation uses historical measurements and a simple forecast, then scores against later measurements held out until evaluation.” |
| 0:43–1:02 | **Build a deliberately mismatched four-cell pack in the workbench.** Point to its spread and bottleneck metrics. “The demo fixture is synthetic, so this interaction explains the workflow; it is not a measured pack recommendation.” |
| 1:02–1:30 | **Select Qollab's built-in or AWS simulator and run QAOA once.** Show the QUBO-to-Ising mapping, p=1 circuit summary, simulator label, shots, feasible mass, and measured-state probabilities. “Each of eight candidates is a binary variable. QAOA samples fixed-size selections; we rank measured feasible packs by the physical objective. Parameter search is local, followed by one simulator sampling job.” |
| 1:30–1:49 | **Compare QAOA with greedy, annealing, exact enumeration, and SOH sort.** “On the 20-trial benchmark, QAOA found a feasible sample every time and sampled the exact optimum in 17 trials. Exact enumeration remained much faster at this small size.” |
| 1:49–2:08 | **Use the reveal control.** “This shipped UI reveal is synthetic. The scientific benchmark scored against held-out real-derived measurements separately; the app shows aggregate trial outcomes. The source dataset is CC BY 4.0 and is cited with a license link.” |
| 2:08–2:29 | **Show benchmark summary and objective ablation.** “Trajectory awareness did not improve mean observed divergence in this seed set: exact current-only averaged 0.07188 OPD, versus 0.07321 for trajectory-aware selection.” |
| 2:29–2:40 | **Close on limitations and attribution.** “These small experiments show a way to test mission-aware battery grouping with QAOA. They establish no quantum speedup, battery safety, or lifetime gain. This effort is supported by Qollab & IonQ.” |

## Recording notes

- Keep the benchmark panel and synthetic/derived-real labels visible when discussing results.
- Name the selected simulator in the narration. QAOA samples and counts vary between runs; show the output from the recorded run rather than quoting a fixed feasible mass or bitstring.
- State that the app's interactive candidate inventory and reveal are synthetic. The 20-trial benchmark figures are aggregate results from the separate derived-real evaluation.
- Do not describe simulator output as an IonQ Aria result. The hosted Aria path currently fails before returning a job ID or measured counts.
- Do not imply that the app contains cell-level real data or that the future-reveal fixture is from the Deep Sorting dataset.
- Keep the final video under three minutes and add captions for spoken narration.
- After publishing, add the public video URL to the README and Qollab project page.
