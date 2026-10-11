import * as quantumBridge from "./quantumBridge.js";

const ASSET_ROOT = new URL("../data/", import.meta.url).href.replace(/\/$/, "");
const ALGORITHM_ORDER = [
  ["soh_sort", "SOH sort", "Current health first"],
  ["compatibility_greedy", "Compatibility greedy", "Multi-start local construction"],
  ["simulated_annealing", "Simulated annealing", "Fixed-cardinality swaps"],
  ["exact_enumeration", "Exact enumeration", "Global optimum · oracle"],
];
const QAOA_STAGES = ["preparing", "parameter_optimization", "sampling", "complete"];
const MISSION_COPY = {
  pv_tou: "Daily solar shifting with evening peak support. The mission sets the future horizon and compatibility weights.",
  frequency_response: "Experimental placeholder. It currently reuses the PV + TOU estimator and weights; no frequency-specific degradation calibration is included.",
};
const OBJECTIVE_COPY = {
  trajectory_aware: "Balances present capacity and estimated capacity at the selected horizon.",
  current_only: "Matches present capacity and health while leaving forecasts out of the objective.",
};

const dom = {
  runtimeDot: document.querySelector("#runtime-dot"),
  runtimeLabel: document.querySelector("#runtime-label"),
  classification: document.querySelector("#data-classification"),
  status: document.querySelector("#workspace-status"),
  mission: document.querySelector("#mission-select"),
  missionDescription: document.querySelector("#mission-description"),
  horizon: document.querySelector("#horizon-select"),
  packSize: document.querySelector("#pack-size-select"),
  objectiveCopy: document.querySelector("#objective-copy"),
  objectiveButtons: [...document.querySelectorAll("[data-objective]")],
  assumptions: document.querySelector("#assumptions"),
  inventoryCount: document.querySelector("#inventory-count"),
  candidateGrid: document.querySelector("#candidate-grid"),
  packTitleCount: document.querySelector("#pack-title-count"),
  packTray: document.querySelector("#pack-tray"),
  manualMetrics: document.querySelector("#manual-metrics"),
  useExact: document.querySelector("#use-exact-button"),
  revealButton: document.querySelector("#reveal-button"),
  revealNote: document.querySelector("#reveal-note"),
  algorithms: document.querySelector("#algorithm-list"),
  comparisonLabel: document.querySelector("#comparison-label"),
  runClassical: document.querySelector("#run-classical-button"),
  quantumState: document.querySelector("#quantum-state"),
  stages: [...document.querySelectorAll(".stage")],
  inspectorQubits: document.querySelector("#inspector-qubits"),
  inspectorDepth: document.querySelector("#inspector-depth"),
  inspectorBackend: document.querySelector("#inspector-backend"),
  inspectorShots: document.querySelector("#inspector-shots"),
  feasibleMass: document.querySelector("#feasible-mass"),
  probabilityChart: document.querySelector("#probability-chart"),
  qaoaDetails: document.querySelector("#qaoa-details"),
  runQaoa: document.querySelector("#run-qaoa-button"),
  qaoaNote: document.querySelector("#qaoa-note"),
  revealBody: document.querySelector("#reveal-body"),
  heldoutBadge: document.querySelector(".heldout-badge"),
  revealPlaceholder: document.querySelector("#reveal-placeholder"),
  revealedResults: document.querySelector("#revealed-results"),
  trialCount: document.querySelector("#trial-count"),
  benchmarkChart: document.querySelector("#benchmark-chart"),
  benchmarkFoot: document.querySelector("#benchmark-foot"),
  toastRegion: document.querySelector("#toast-region"),
};

const state = {
  mode: "synthetic-demo",
  missionId: "pv_tou",
  objectiveMode: "trajectory_aware",
  horizonCycles: 200,
  packSizeK: 4,
  demoState: null,
  manualSelection: [],
  manualEvaluation: null,
  classicalResults: null,
  comparisonSource: null,
  qaoaResult: null,
  qaoaStatus: "idle",
  qaoaStage: null,
  qaoaErrorDetail: null,
  futureRevealed: false,
  futureReveal: null,
  runtimeCapabilities: null,
  runtimeConnected: false,
  benchmarkSummary: null,
  benchmarkTrials: null,
  staticClassical: null,
  staticQaoaReplay: null,
  assumptionsOpen: false,
  toast: null,
  statusMessage: "Loading decision-time inventory…",
  statusKind: "",
  busy: false,
  focusAfterRender: null,
  problemRequestId: 0,
};

function formatNumber(value, digits = 3) {
  return Number.isFinite(value) ? Number(value).toFixed(digits) : "—";
}

function formatPercent(value, digits = 1) {
  return Number.isFinite(value) ? `${(Number(value) * 100).toFixed(digits)}%` : "—";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function cellById(cellId) {
  const index = state.demoState?.candidate_ids?.indexOf(cellId) ?? -1;
  return index < 0 ? null : state.demoState.snapshots[index];
}

function indexById(cellId) {
  return state.demoState?.candidate_ids?.indexOf(cellId) ?? -1;
}

function selectionCells() {
  return state.manualSelection.map((index) => state.demoState?.snapshots?.[index]).filter(Boolean);
}

function coefficientOfVariation(values) {
  if (!values.length) return null;
  const mean = values.reduce((total, value) => total + value, 0) / values.length;
  if (!(mean > 0)) return null;
  const variance = values.reduce((total, value) => total + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance) / mean;
}

function manualMetrics() {
  if (state.manualEvaluation && state.manualSelection.length === state.packSizeK) {
    const truthById = new Map((state.futureReveal?.truth ?? []).map((truth) => [truth.cell_id, truth]));
    const selectedIds = state.manualSelection.map((index) => state.demoState.candidate_ids[index]);
    const observed = selectedIds.every((id) => truthById.has(id));
    return {
      ...state.manualEvaluation,
      observed_pack_divergence: state.futureRevealed && observed ? coefficientOfVariation(selectedIds.map((id) => truthById.get(id).actual_capacity_ah)) : null,
      observed_usable_capacity_ah: state.futureRevealed && observed ? Math.min(...selectedIds.map((id) => truthById.get(id).actual_capacity_ah)) : null,
    };
  }
  const cells = selectionCells();
  if (!cells.length) return null;
  const capacity = cells.map((cell) => Number(cell.capacity_ah));
  const predicted = cells.map((cell) => Number(cell.predicted_capacity_ah));
  const currentSpread = Math.max(...capacity) - Math.min(...capacity);
  const metrics = {
    usable_pack_capacity_ah: Math.min(...capacity),
    current_capacity_spread_ah: currentSpread,
    current_capacity_cv: coefficientOfVariation(capacity),
    predicted_pack_divergence: coefficientOfVariation(predicted),
    predicted_capacity_spread_ah: Math.max(...predicted) - Math.min(...predicted),
  };
  const truthById = new Map((state.futureReveal?.truth ?? []).map((truth) => [truth.cell_id, truth]));
  if (state.futureRevealed && cells.length === state.packSizeK && cells.every((cell) => truthById.has(cell.cell_id))) {
    const future = cells.map((cell) => truthById.get(cell.cell_id).actual_capacity_ah);
    metrics.observed_pack_divergence = coefficientOfVariation(future);
    metrics.observed_usable_capacity_ah = Math.min(...future);
  }
  return metrics;
}

function pushToast(message, tone = "") {
  state.toast = { message, tone };
  renderToast();
  window.clearTimeout(pushToast.timer);
  pushToast.timer = window.setTimeout(() => {
    state.toast = null;
    renderToast();
  }, 3600);
}

function setStatus(message, kind = "") {
  state.statusMessage = message;
  state.statusKind = kind;
  dom.status.textContent = message;
  dom.status.dataset.kind = kind;
}

function invalidateProblem(message = "Results reset because the optimization problem changed.") {
  state.classicalResults = null;
  state.comparisonSource = null;
  state.qaoaResult = null;
  state.qaoaStatus = "idle";
  state.qaoaStage = null;
  state.qaoaErrorDetail = null;
  state.futureRevealed = false;
  state.futureReveal = null;
  state.manualEvaluation = null;
  state.focusAfterRender = null;
  setStatus(message);
}

function currentProblemOptions() {
  return {
    horizon_cycles: state.horizonCycles,
    pack_size_k: state.packSizeK,
    objective_mode: state.objectiveMode,
  };
}

function liveQaoaReady() {
  return state.runtimeConnected && state.runtimeCapabilities?.statevector_available === true;
}

function staticInventoryState(horizonCycles) {
  return state.inventoryAsset?.by_horizon?.[String(horizonCycles)] ?? null;
}

async function refreshDemoState(requestId = null) {
  if (state.runtimeConnected) {
    const response = await quantumBridge.getDemoState(currentProblemOptions());
    if (!response || response.data_classification !== "synthetic-fixture" || response.future_disclosed) {
      console.error("RePack-Q rejected an invalid pre-reveal candidate pool:", response);
      throw new Error(
        `Python returned an invalid inventory payload (classification=${String(response?.data_classification)}, future_disclosed=${String(response?.future_disclosed)}).`,
      );
    }
    if (requestId !== null && requestId !== state.problemRequestId) return;
    state.demoState = response;
  } else {
    state.demoState = staticInventoryState(state.horizonCycles);
    if (!state.demoState) throw new Error("The checked-in demo inventory is missing this horizon.");
  }
}

function sparklineSvg(cell, history, { revealed = false, futurePoints = [] } = {}) {
  const width = 150;
  const height = 48;
  const padX = 5;
  const padY = 5;
  const cutoff = Number(cell.cycle_index);
  const horizon = Number(cell.horizon_cycles);
  const target = cutoff + horizon;
  const historical = (history ?? []).filter((item) => Number.isFinite(item.capacity_ah));
  const actual = revealed ? futurePoints.filter((item) => Number.isFinite(item.capacity_ah)) : [];
  const values = [...historical.map((item) => Number(item.capacity_ah)), Number(cell.predicted_capacity_ah)];
  if (actual.length) values.push(...actual.map((item) => Number(item.capacity_ah)));
  const minValue = Math.min(...values) - 0.025;
  const maxValue = Math.max(...values) + 0.025;
  const range = Math.max(maxValue - minValue, 0.001);
  const point = (cycle, capacity) => {
    const x = padX + ((cycle - Number(historical[0]?.cycle_index ?? cutoff)) / Math.max(target - Number(historical[0]?.cycle_index ?? cutoff), 1)) * (width - padX * 2);
    const y = height - padY - ((capacity - minValue) / range) * (height - padY * 2);
    return [x, y];
  };
  const pathFor = (items) => items.map((item, index) => {
    const [x, y] = point(Number(item.cycle_index), Number(item.capacity_ah));
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const historicalPath = pathFor(historical);
  const lastHistory = historical.at(-1);
  const [forecastX, forecastY] = point(target, Number(cell.predicted_capacity_ah));
  const [cutoffX, cutoffY] = point(cutoff, Number(lastHistory?.capacity_ah ?? cell.capacity_ah));
  const actualPath = actual.length ? pathFor([lastHistory, ...actual]) : "";
  const label = `${cell.cell_id}: observed history through cycle ${cutoff}; predicted capacity ${formatNumber(cell.predicted_capacity_ah, 3)} Ah at cycle ${target}${actual.length ? `; held-out observations revealed through cycle ${actual.at(-1).cycle_index}` : ""}.`;
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}"><title>${escapeHtml(label)}</title><desc>Solid dark line is pre-recommissioning history. Dashed blue line is the forecast. A lighter line appears after explicit future reveal.</desc><path d="${historicalPath}" fill="none" stroke="#315d3e" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M${cutoffX.toFixed(1)},${cutoffY.toFixed(1)} L${forecastX.toFixed(1)},${forecastY.toFixed(1)}" fill="none" stroke="#80a9c1" stroke-width="1.7" stroke-dasharray="3 3" stroke-linecap="round"/><circle cx="${forecastX.toFixed(1)}" cy="${forecastY.toFixed(1)}" r="2.7" fill="#78a5bd"/>${actualPath ? `<path d="${actualPath}" fill="none" stroke="#8f9f3d" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${point(Number(actual.at(-1).cycle_index), Number(actual.at(-1).capacity_ah))[0].toFixed(1)}" cy="${point(Number(actual.at(-1).cycle_index), Number(actual.at(-1).capacity_ah))[1].toFixed(1)}" r="3" fill="#a8bd49"/>` : ""}</svg>`;
}

function renderHeader() {
  const connected = state.runtimeConnected;
  dom.runtimeDot.classList.toggle("connected", connected);
  dom.runtimeLabel.textContent = connected ? "Python bridge ready" : "Local demo · replay mode";
  dom.classification.textContent = "Synthetic interaction fixture";
  dom.mission.value = state.missionId;
  dom.mission.disabled = state.busy;
  dom.missionDescription.textContent = MISSION_COPY[state.missionId];
  dom.horizon.value = String(state.horizonCycles);
  dom.horizon.disabled = state.busy;
  dom.packSize.value = String(state.packSizeK);
  dom.packSize.disabled = state.busy;
  dom.objectiveCopy.textContent = OBJECTIVE_COPY[state.objectiveMode];
  dom.objectiveButtons.forEach((button) => {
    const active = button.dataset.objective === state.objectiveMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.disabled = state.busy;
  });
  dom.assumptions.open = state.assumptionsOpen;
  dom.status.textContent = state.statusMessage;
  dom.status.dataset.kind = state.statusKind;
}

function renderInventory() {
  const snapshots = state.demoState?.snapshots ?? [];
  const histories = state.demoState?.histories ?? [];
  const ids = state.demoState?.candidate_ids ?? [];
  dom.inventoryCount.textContent = String(snapshots.length).padStart(2, "0");
  if (!snapshots.length) {
    dom.candidateGrid.innerHTML = `<div class="empty-candidates">No eligible candidates are available for this configuration.</div>`;
    return;
  }
  dom.candidateGrid.innerHTML = snapshots.map((cell, index) => {
    const selected = state.manualSelection.includes(index);
    const full = state.manualSelection.length >= state.packSizeK;
    const disabled = state.busy || (!selected && full);
    const revealedPoints = (state.futureReveal?.observations ?? []).filter((item) => item.cell_id === cell.cell_id);
    const isRevealed = state.futureRevealed && state.manualSelection.includes(index) && revealedPoints.length > 0;
    const buttonLabel = selected ? `Remove ${cell.cell_id} from manual pack` : `Add ${cell.cell_id} to manual pack`;
    return `<article class="cell-card${selected ? " in-pack" : ""}" data-cell="${escapeHtml(cell.cell_id)}"><div class="cell-card-head"><span class="cell-id">${escapeHtml(cell.cell_id)}</span><span class="cell-health">${formatPercent(cell.soh, 0)} SOH</span></div><div class="cell-battery">${sparklineSvg(cell, histories[index] ?? [], { revealed: isRevealed, futurePoints: revealedPoints })}</div><div class="cell-card-stats"><div class="cell-stat"><span>Now</span><strong>${formatNumber(cell.capacity_ah, 3)} <small>Ah</small></strong></div><div class="cell-stat"><span>At H=${state.horizonCycles}</span><strong>${formatNumber(cell.predicted_capacity_ah, 3)} <small>Ah</small></strong></div><div class="cell-stat"><span>Fade</span><strong>${formatNumber(Math.abs(cell.recent_capacity_slope_ah_per_cycle) * 1000, 2)} <small>mAh/cyc</small></strong></div><div class="cell-stat"><span>Uncertainty</span><strong>±${formatNumber(cell.prediction_uncertainty_ah, 3)} <small>Ah</small></strong></div></div><button class="cell-add" id="cell-add-${escapeHtml(cell.cell_id)}" type="button" data-action="toggle-cell" data-index="${index}" aria-pressed="${selected}" aria-label="${escapeHtml(buttonLabel)}"${disabled ? " disabled" : ""}><span aria-hidden="true">${selected ? "−" : "+"}</span><span>${selected ? "Remove" : "Add to pack"}</span></button></article>`;
  }).join("");
}

function renderPack() {
  const selected = selectionCells();
  dom.packTitleCount.textContent = `${state.manualSelection.length} / ${state.packSizeK}`;
  dom.packTray.innerHTML = Array.from({ length: state.packSizeK }, (_, slot) => {
    const index = state.manualSelection[slot];
    const cell = Number.isInteger(index) ? state.demoState?.snapshots?.[index] : null;
    if (!cell) return `<div class="pack-slot" aria-label="Empty series slot ${slot + 1}"><span class="slot-number">${String(slot + 1).padStart(2, "0")}</span><span class="slot-empty">Open position</span></div>`;
    return `<div class="pack-slot filled"><span class="slot-number">${String(slot + 1).padStart(2, "0")}</span><span class="slot-copy"><strong>${escapeHtml(cell.cell_id)}</strong><span>${formatNumber(cell.capacity_ah, 3)} Ah · ${formatPercent(cell.soh, 0)} SOH</span></span><button class="slot-remove" type="button" data-action="remove-cell" data-index="${index}" aria-label="Remove ${escapeHtml(cell.cell_id)} from series slot ${slot + 1}">×</button></div>`;
  }).join("");
  const metrics = manualMetrics();
  const metricRows = metrics ? [
    ["Usable capacity", `${formatNumber(metrics.usable_pack_capacity_ah, 3)} <small class="metric-unit">Ah</small>`],
    ["Now · spread", `${formatNumber(metrics.current_capacity_spread_ah, 3)} <small class="metric-unit">Ah</small>`],
    [metrics.observed_pack_divergence == null ? "Predicted OPD" : "Observed OPD", metrics.observed_pack_divergence == null ? formatPercent(metrics.predicted_pack_divergence) : formatPercent(metrics.observed_pack_divergence)],
  ] : [["Usable capacity", "—"], ["Now · spread", "—"], ["Predicted OPD", "—"]];
  dom.manualMetrics.innerHTML = metricRows.map(([label, value]) => `<div class="metric-cell"><span class="metric-label">${label}</span><strong class="metric-value">${value}</strong></div>`).join("");
  const complete = state.manualSelection.length === state.packSizeK;
  dom.revealButton.disabled = !complete || state.busy;
  dom.revealButton.innerHTML = `<span>${state.futureRevealed && complete ? "Reveal this pack again" : "Reveal future"}</span><span aria-hidden="true">↗</span>`;
  dom.revealNote.textContent = complete
    ? (state.futureRevealed ? "Held-out fixture values are visible for the current pack." : "Only post-cutoff observations are evaluated after this action.")
    : `Build a complete ${state.packSizeK}-cell pack to unlock the held-out reveal.`;
  dom.useExact.disabled = !state.classicalResults?.results?.exact_enumeration || state.busy;
  if (state.focusAfterRender) {
    document.querySelector(state.focusAfterRender)?.focus({ preventScroll: true });
    state.focusAfterRender = null;
  }
}

function resultNames(id) {
  return ALGORITHM_ORDER.find(([key]) => key === id)?.slice(1) ?? [id, "Solver result"];
}

function displayObservedResult(result) {
  if (!result || !state.futureRevealed) return null;
  const truthById = new Map((state.futureReveal?.truth ?? []).map((truth) => [truth.cell_id, truth]));
  if (!result.selected_cell_ids?.length || result.selected_cell_ids.some((id) => !truthById.has(id))) return null;
  const values = result.selected_cell_ids.map((id) => Number(truthById.get(id).actual_capacity_ah));
  return { opd: coefficientOfVariation(values), usable: Math.min(...values) };
}

function renderClassical() {
  const results = state.classicalResults?.results;
  if (!results) {
    dom.algorithms.innerHTML = `<div class="empty-result"><span class="empty-mark">◎</span><p>Run the comparison to score the candidate pool.</p></div>`;
    dom.comparisonLabel.textContent = state.runtimeConnected ? "Ready · live Python" : "Fixture preview · synthetic";
    dom.runClassical.disabled = state.busy || !state.demoState;
    dom.runClassical.innerHTML = `<span>${state.runtimeConnected ? "Run classical solvers" : "Load fixture comparison"}</span><span aria-hidden="true">→</span>`;
    return;
  }
  dom.algorithms.innerHTML = ALGORITHM_ORDER.map(([key, title, subtitle]) => {
    const result = results[key];
    if (!result) return "";
    const resultIds = (result.selected_cell_ids ?? []).slice().sort().join("|");
    const manualIds = state.manualSelection.map((index) => state.demoState.candidate_ids[index]).sort().join("|");
    const selected = state.manualSelection.length === state.packSizeK && resultIds === manualIds;
    const exact = key === "exact_enumeration";
    const observed = displayObservedResult(result);
    const exactValue = results.exact_enumeration?.objective_value;
    const objectiveGap = exact && Number.isFinite(exactValue)
      ? 0
      : Number.isFinite(exactValue)
        ? Math.max(0, result.objective_value - exactValue)
        : result.objective_gap;
    const forecastMetric = observed
      ? `OPD <strong>${formatPercent(observed.opd)}</strong>`
      : `PPD <strong>${formatPercent(result.predicted_pack_divergence)}</strong>`;
    const scoreCaption = observed ? "observed" : "predicted";
    return `<button class="algorithm-row${selected ? " selected" : ""}" type="button" data-action="choose-result" data-algorithm="${key}" aria-label="Load ${escapeHtml(title)} result pack ${escapeHtml((result.selected_cell_ids ?? []).join(", "))}"><span><span class="algorithm-label"><i class="algo-dot"></i><span class="algorithm-name">${escapeHtml(title)}${exact ? " · oracle" : ""}</span></span><span class="algorithm-metrics">${forecastMetric} &nbsp;·&nbsp; gap <strong>${formatNumber(objectiveGap, 3)}</strong></span></span><span class="algorithm-score">${formatNumber(result.objective_value, 3)}<small>${scoreCaption} objective</small></span><span class="algorithm-cells">${escapeHtml((result.selected_cell_ids ?? []).join("  /  "))} · ${escapeHtml(subtitle)}</span></button>`;
  }).join("");
  dom.comparisonLabel.textContent = state.comparisonSource === "live"
    ? "Live Python · future hidden"
    : "Precomputed fixture · synthetic";
  dom.runClassical.disabled = state.busy || !state.demoState;
  dom.runClassical.innerHTML = state.busy
    ? `<span>${state.runtimeConnected ? "Solving the pool…" : "Loading fixture results…"}</span><span aria-hidden="true">· · ·</span>`
    : `<span>${state.runtimeConnected ? "Run classical solvers again" : "Reload fixture comparison"}</span><span aria-hidden="true">→</span>`;
}

function decodeQiskitCountKey(key, qubitCount) {
  const compact = String(key).replaceAll(" ", "");
  if (compact.length !== qubitCount || /[^01]/.test(compact)) return null;
  return [...compact].reverse().map((bit) => Number(bit));
}

function renderQaoa() {
  const active = ["preparing", "parameter_optimization", "sampling", "running_python"].includes(state.qaoaStatus);
  const result = state.qaoaResult;
  const stageIndex = QAOA_STAGES.indexOf(state.qaoaStage);
  dom.quantumState.dataset.status = active ? "active" : (state.qaoaStatus === "complete" ? "complete" : (state.qaoaStatus === "error" ? "error" : "idle"));
  const statuses = {
    idle: state.runtimeConnected ? "Ready · live Python bridge" : "Local replay · live bridge unavailable",
    preparing: "Preparing QUBO and QAOA circuit",
    parameter_optimization: "Optimizing parameters with local statevectors",
    sampling: "Sampling the final circuit once",
    running_python: "Running QAOA in Qollab Python; internal stage is unavailable",
    complete: result?.mode === "precomputed-synthetic-replay" ? "Synthetic QAOA replay loaded" : "QAOA run complete",
    error: "QAOA run failed",
  };
  dom.quantumState.lastElementChild.textContent = statuses[state.qaoaStatus] ?? "QAOA state unavailable";
  dom.stages.forEach((element, index) => {
    element.classList.toggle("active", active && index === stageIndex);
    element.classList.toggle("done", result ? index <= Math.max(stageIndex, 3) : active && index < stageIndex);
  });
  dom.runQaoa.disabled = active || state.busy || !state.demoState || (!liveQaoaReady() && !state.staticQaoaReplay);
  dom.runQaoa.innerHTML = active
    ? `<span>${state.qaoaStage === "parameter_optimization" ? "Optimizing parameters" : state.qaoaStage === "sampling" ? "Sampling one circuit" : state.qaoaStage === "running_python" ? "Running QAOA in Python" : "Preparing QAOA"}</span><span aria-hidden="true">⌁</span>`
    : `<span>${liveQaoaReady() ? "Run QAOA" : (result?.mode === "precomputed-synthetic-replay" ? "Reload QAOA replay" : "View QAOA replay")}</span><span aria-hidden="true">⌁</span>`;
  dom.qaoaNote.textContent = liveQaoaReady()
    ? "Parameters are optimized on an ideal local statevector, then one backend-specific compiled circuit is sampled. Hardware counts include device noise; simulator behavior follows its configured noise model."
    : state.runtimeConnected
      ? "This runtime does not report Qiskit Statevector support. The replay is precomputed and synthetic."
      : "This is a precomputed synthetic BasicSimulator replay. Connect the verified Python bridge to run QAOA live.";
  if (!result) {
    dom.inspectorQubits.textContent = String(state.demoState?.snapshots?.length ?? 8);
    dom.inspectorDepth.textContent = "1";
    dom.inspectorBackend.textContent = "—";
    dom.inspectorShots.textContent = "—";
    dom.feasibleMass.textContent = "Feasible mass —";
    dom.probabilityChart.innerHTML = `<div class="chart-empty">Run QAOA to inspect measured bitstrings.</div>`;
    if (state.qaoaStatus === "error") {
      dom.qaoaDetails.replaceChildren();
      const details = document.createElement("details");
      details.className = "qaoa-error-details";
      const summary = document.createElement("summary");
      summary.textContent = "Show full Python error (common credential formats redacted)";
      const pre = document.createElement("pre");
      pre.textContent = state.qaoaErrorDetail || "No error details were returned.";
      details.append(summary, pre);
      dom.qaoaDetails.append(details);
    } else {
      dom.qaoaDetails.textContent = "Gamma, beta, penalty, measured states, and circuit metadata appear here after a run.";
    }
    return;
  }
  const circuit = result.circuit ?? {};
  dom.inspectorQubits.textContent = String(circuit.qubits ?? state.demoState?.snapshots?.length ?? 8);
  dom.inspectorDepth.textContent = String(result.reps ?? circuit.reps ?? 1);
  dom.inspectorBackend.textContent = String(result.backend ?? "unknown").replaceAll("_", " ");
  dom.inspectorShots.textContent = String(result.shots_observed ?? result.shots_requested ?? "—");
  dom.feasibleMass.textContent = `Feasible mass ${formatPercent(result.feasible_probability_mass, 1)}`;
  const countEntries = Object.entries(result.raw_counts ?? {}).map(([key, count]) => ({ key, count, probability: Number(result.probabilities?.[key] ?? 0) }));
  const topStates = countEntries.sort((left, right) => right.count - left.count || left.key.localeCompare(right.key)).slice(0, 6);
  const maxProbability = Math.max(...topStates.map((item) => item.probability), 0.0001);
  dom.probabilityChart.innerHTML = topStates.length
    ? topStates.map((item) => {
      const bits = decodeQiskitCountKey(item.key, Number(circuit.qubits ?? state.demoState.snapshots.length));
      const chosen = bits ? bits.flatMap((bit, index) => bit ? [state.demoState.candidate_ids[index]] : []) : [];
      const feasible = chosen.length === state.packSizeK;
      const label = chosen.length ? chosen.join(", ") : "no selected cells";
      return `<div class="probability-row" role="group" aria-label="Measured state ${escapeHtml(item.key)} selects ${escapeHtml(label)} with probability ${formatPercent(item.probability, 1)}" title="${escapeHtml(item.key)} → ${escapeHtml(label)}"><span class="probability-state">${escapeHtml(item.key)}${feasible ? " · K" : ""}</span><span class="probability-track" aria-hidden="true"><span class="probability-fill${feasible ? "" : " infeasible"}" style="display:block;width:${Math.max(3, item.probability / maxProbability * 100)}%"></span></span><span class="probability-value">${formatPercent(item.probability, 1)}</span></div>`;
    }).join("")
    : `<div class="chart-empty">No measured bitstrings were returned.</div>`;
  const params = result.params ?? {};
  const penalty = result.penalty?.cardinality_penalty;
  const circuitText = circuit.transpiled_depth == null ? `depth ${circuit.depth ?? "—"}` : `depth ${circuit.transpiled_depth} · ${circuit.transpiled_size ?? "—"} ops`;
  const best = result.best_feasible_sample;
  dom.qaoaDetails.innerHTML = `<span>γ ${escapeHtml((params.gamma ?? []).map((value) => formatNumber(value, 3)).join(", ") || "—")} &nbsp; β ${escapeHtml((params.beta ?? []).map((value) => formatNumber(value, 3)).join(", ") || "—")} &nbsp; penalty ${formatNumber(penalty, 3)}<br>${escapeHtml(circuitText)} · feasible mass ${formatPercent(result.feasible_probability_mass)} · best gap ${formatNumber(result.best_feasible_optimality_gap, 3)}</span>${best ? `<button class="text-button" type="button" data-action="use-qaoa">Use best measured pack ↗</button>` : "<span>No feasible K-cell sample was observed.</span>"}`;
}

function renderReveal() {
  const truth = state.futureReveal?.truth ?? [];
  const selectedIds = state.manualSelection.map((index) => state.demoState?.candidate_ids?.[index]).filter(Boolean);
  const revealedIds = new Set(truth.map((item) => item.cell_id));
  const complete = selectedIds.length === state.packSizeK && selectedIds.every((id) => revealedIds.has(id));
  dom.heldoutBadge.innerHTML = state.futureRevealed && complete
    ? `<span aria-hidden="true">✓</span> Held-out values revealed`
    : `<span aria-hidden="true">⌑</span> Hidden before reveal`;
  if (!state.futureRevealed || !complete) {
    dom.revealBody.hidden = false;
    dom.revealedResults.hidden = true;
    if (state.futureRevealed && !complete) {
      dom.revealPlaceholder.innerHTML = `<span class="placeholder-label">This pack includes cells not yet revealed. Choose “Reveal future” again for the current pack.</span>`;
    } else {
      dom.revealPlaceholder.innerHTML = `<span class="placeholder-line"></span><span class="placeholder-line short"></span><span class="placeholder-label">No post-cutoff measurements shown</span>`;
    }
    return;
  }
  const metrics = manualMetrics();
  dom.revealBody.hidden = true;
  dom.revealedResults.hidden = false;
  const observationById = new Map();
  for (const item of state.futureReveal.observations ?? []) {
    if (!observationById.has(item.cell_id)) observationById.set(item.cell_id, []);
    observationById.get(item.cell_id).push(item);
  }
  const trajectories = selectedIds.map((cellId) => {
    const points = observationById.get(cellId) ?? [];
    const cell = cellById(cellId);
    const history = state.demoState.histories[indexById(cellId)] ?? [];
    return `<div class="revealed-traj"><strong>${escapeHtml(cellId)} · actual vs forecast</strong>${sparklineSvg(cell, history, { revealed: true, futurePoints: points })}</div>`;
  }).join("");
  dom.revealedResults.innerHTML = `<p class="reveal-label">Synthetic held-out fixture reveal · target cycle ${state.futureReveal.target_cycle}</p><div class="reveal-summary"><div class="metric-cell"><span class="metric-label">Observed Pack Divergence</span><strong class="metric-value">${formatPercent(metrics?.observed_pack_divergence)}</strong></div><div class="metric-cell"><span class="metric-label">Observed bottleneck</span><strong class="metric-value">${formatNumber(metrics?.observed_usable_capacity_ah, 3)} <small class="metric-unit">Ah</small></strong></div><div class="metric-cell"><span class="metric-label">Predicted divergence</span><strong class="metric-value">${formatPercent(metrics?.predicted_pack_divergence)}</strong></div><div class="metric-cell"><span class="metric-label">Current bottleneck</span><strong class="metric-value">${formatNumber(metrics?.usable_pack_capacity_ah, 3)} <small class="metric-unit">Ah</small></strong></div></div><div class="trajectory-wrap"><h4>Selected cell trajectories · history → forecast → actual</h4><div class="revealed-trajectories">${trajectories}</div></div><p class="reveal-disclaimer">${escapeHtml(state.futureReveal.extrapolation_note ?? "Held-out fixture observations are revealed only for evaluation. No future values were used to rank or optimize this pack.")}</p>`;
}

function renderBenchmark() {
  const summary = state.benchmarkSummary;
  if (!summary) {
    dom.benchmarkChart.innerHTML = `<p class="chart-empty">The aggregate benchmark summary is unavailable.</p>`;
    dom.benchmarkFoot.textContent = "The UI can still use the synthetic interaction fixture.";
    return;
  }
  const algorithms = summary.algorithms ?? {};
  const benchmarkOrder = [
    ["soh_sort", "SOH sort"],
    ["compatibility_greedy", "Greedy"],
    ["simulated_annealing", "Annealing"],
    ["exact_enumeration", "Exact"],
    ["qaoa", "QAOA"],
  ];
  const values = benchmarkOrder.map(([id]) => Number(algorithms[id]?.observed_opd_mean)).filter(Number.isFinite);
  const maxValue = Math.max(...values, 0.001);
  dom.trialCount.textContent = String(summary.trial_count ?? "—");
  dom.benchmarkChart.innerHTML = benchmarkOrder.map(([id, label]) => {
    const result = algorithms[id];
    if (!result || !Number.isFinite(result.observed_opd_mean)) return "";
    const percent = result.observed_opd_mean * 100;
    const width = percent / (maxValue * 100) * 100;
    return `<div class="benchmark-bar-card" role="listitem" aria-label="${label}: mean observed pack divergence ${percent.toFixed(2)} percent, ${result.valid_trials ?? 0} trials" data-algorithm="${id}"><div class="benchmark-bar-top"><span>${label}</span><strong>${percent.toFixed(2)}%</strong></div><div class="benchmark-track" aria-hidden="true"><div class="benchmark-fill" style="width:${width.toFixed(1)}%"></div></div><small>mean observed divergence · ${result.valid_trials ?? 0} trials</small></div>`;
  }).join("");
  const quality = summary.qaoa_quality ?? {};
  const ablation = summary.objective_ablation ?? {};
  const qaoaTime = quality.mean_timings_ms?.total_ms;
  const exactTime = algorithms.exact_enumeration?.runtime_ms_mean;
  const lower = Number(ablation.exact_trajectory_aware_opd_mean) < Number(ablation.exact_current_only_opd_mean);
  dom.benchmarkFoot.innerHTML = `<span><strong>QAOA exact optimum sampled:</strong> ${formatPercent(quality.optimum_sample_rate)} (${quality.trials_with_feasible_sample ?? 0}/${quality.valid_trials ?? 0} feasible samples)</span><span><strong>Mean QAOA / exact runtime:</strong> ${formatNumber(qaoaTime, 0)} ms / ${formatNumber(exactTime, 2)} ms</span><span class="benchmark-caveat"><strong>Ablation:</strong> current-only OPD ${formatPercent(ablation.exact_current_only_opd_mean)}; trajectory-aware ${formatPercent(ablation.exact_trajectory_aware_opd_mean)}. The trajectory-aware objective ${lower ? "was lower" : "was not lower"} on average in this seed set; this does not establish a general effect. <a href="../docs/RESULTS.md" target="_blank" rel="noopener">Read the full results and limitations</a>.</span><span class="benchmark-caveat">Derived-real aggregate replay from ${escapeHtml(summary.source_dataset ?? "the primary battery dataset")}; no cell-level data is shipped. QAOA used a local BasicSimulator. No speedup claim.</span>`;
}

function renderToast() {
  dom.toastRegion.innerHTML = state.toast
    ? `<div class="toast${state.toast.tone ? ` ${state.toast.tone}` : ""}" role="status">${escapeHtml(state.toast.message)}</div>`
    : "";
}

function render() {
  renderHeader();
  renderInventory();
  renderPack();
  renderClassical();
  renderQaoa();
  renderReveal();
  renderBenchmark();
  renderToast();
}

function safeErrorSummary(error) {
  const rawName = String(error?.name ?? "Error");
  const name = rawName.replace(/[^\w.-]/g, "").slice(0, 48) || "Error";
  let message = String(error?.message ?? error ?? "Unknown error");
  message = message
    .replace(/\b(api[-_ ]?key|access[-_ ]?token|token|authorization)\b(\s*[:=]\s*|\s+)[^\s,;]+/gi, "$1$2[redacted]")
    .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, "Bearer [redacted]")
    .replace(/\b(?:sk|qk|ionq)_[A-Za-z0-9_-]{12,}\b/gi, "[redacted credential]")
    .slice(0, 6000);
  return `${name}: ${message || "No error message was provided."}`;
}

function safeErrorHeadline(error) {
  const lines = safeErrorSummary(error).split(/\r?\n/).filter(Boolean);
  return (lines.at(-1) ?? "Unknown error").replace(/\s+/g, " ").slice(0, 180);
}

function friendlyError(error, action, stage = "") {
  const code = error?.code ?? error?.name ?? "";
  const messages = {
    QiskitUnavailableError: "Qiskit is unavailable in this Python runtime. Classical solvers and benchmark replay remain available.",
    TimeoutError: "The Python runtime did not respond in time. Try the run again when the runtime is ready.",
    BackendError: "The selected backend could not complete the sampling request. No replay result was substituted.",
  };
  if (action === "qaoa" && code !== "QiskitUnavailableError") {
    const stageNames = {
      preparing: "Prepare",
      parameter_optimization: "Optimize",
      sampling: "Sample",
      running_python: "the Qollab Python call (internal stage unavailable)",
    };
    const stageText = stageNames[stage] ? ` during ${stageNames[stage]}` : "";
    return `QAOA could not complete${stageText} (${safeErrorHeadline(error)}). Full error details are in the QAOA inspector. Classical results remain visible; no replay result was substituted.`;
  }
  return messages[code] ?? (action === "reveal"
    ? "The held-out fixture could not be loaded. No future values were added to the current results."
    : "The requested solver action could not complete. Check the Python runtime connection and try again.");
}

async function loadClassicalResults() {
  state.busy = true;
  render();
  try {
    if (state.runtimeConnected) {
      state.classicalResults = await quantumBridge.runClassicalComparison(currentProblemOptions());
      state.comparisonSource = "live";
    } else {
      const key = `h${state.horizonCycles}-k${state.packSizeK}-${state.objectiveMode}`;
      state.classicalResults = state.staticClassical?.results?.[key] ?? null;
      state.comparisonSource = state.classicalResults ? "replay" : null;
      if (!state.classicalResults) {
        pushToast("No precomputed fixture result exists for this setting.", "warning");
      }
    }
    if (state.classicalResults) setStatus(state.runtimeConnected
      ? "Classical comparison complete. Held-out future values remain hidden."
      : "Precomputed synthetic fixture comparison loaded. Held-out values remain hidden.", "success");
  } catch (error) {
    setStatus(friendlyError(error, "classical"), "error");
    pushToast("Classical comparison did not complete.", "error");
  } finally {
    state.busy = false;
    render();
  }
}

async function loadQaoa() {
  if (["preparing", "parameter_optimization", "sampling", "running_python"].includes(state.qaoaStatus)) return;
  state.qaoaResult = null;
  if (!liveQaoaReady()) {
    if (state.horizonCycles !== 200 || state.packSizeK !== 4 || state.objectiveMode !== "trajectory_aware" || !state.staticQaoaReplay) {
      state.qaoaStatus = "error";
      state.qaoaStage = null;
      setStatus("There is no synthetic QAOA replay for this configuration. Connect the Python bridge to run QAOA.", "error");
      pushToast("No QAOA replay exists for the current setting.", "warning");
      render();
      return;
    }
    state.qaoaResult = state.staticQaoaReplay;
    state.qaoaStage = "complete";
    state.qaoaStatus = "complete";
    setStatus("Synthetic QAOA replay loaded. This is not a live Qollab run.", "success");
    render();
    return;
  }
  state.qaoaStatus = "preparing";
  state.qaoaStage = "preparing";
  state.qaoaErrorDetail = null;
  state.busy = true;
  render();
  try {
    const result = await quantumBridge.runQaoa({
      ...currentProblemOptions(),
      shots: 1024,
      reps: 1,
      optimizer_mode: "grid",
      max_evaluations: 121,
      onStage: (stage) => {
        if ((!QAOA_STAGES.includes(stage) && stage !== "running_python") || stage === "complete") return;
        state.qaoaStatus = stage;
        state.qaoaStage = stage;
        render();
      },
    });
    state.qaoaResult = result;
    state.qaoaStage = "complete";
    state.qaoaStatus = "complete";
    state.qaoaErrorDetail = null;
    if (!state.qaoaResult) throw new Error("No QAOA result was returned.");
    setStatus("Live QAOA completed; future values remain hidden.", "success");
  } catch (error) {
    const failedStage = state.qaoaStage;
    state.qaoaErrorDetail = safeErrorSummary(error);
    state.qaoaResult = null;
    state.qaoaStatus = "error";
    state.qaoaStage = null;
    setStatus(friendlyError(error, "qaoa", failedStage), "error");
    pushToast("QAOA did not complete.", "error");
  } finally {
    state.busy = false;
    render();
  }
}

async function refreshManualEvaluation() {
  state.manualEvaluation = null;
  if (!state.runtimeConnected || state.manualSelection.length !== state.packSizeK) return;
  const indices = [...state.manualSelection];
  const options = currentProblemOptions();
  const problemSignature = JSON.stringify(options);
  try {
    const result = await quantumBridge.evaluateSelection(indices, options);
    if (indices.join(",") === state.manualSelection.join(",") && problemSignature === JSON.stringify(currentProblemOptions())) {
      state.manualEvaluation = result;
      renderPack();
    }
  } catch {
    if (indices.join(",") === state.manualSelection.join(",") && problemSignature === JSON.stringify(currentProblemOptions())) {
      pushToast("Live manual metrics are unavailable; current and predicted metrics remain visible.", "warning");
    }
  }
}

async function revealFuture() {
  if (state.manualSelection.length !== state.packSizeK || state.busy) return;
  state.busy = true;
  render();
  try {
    let payload;
    if (state.runtimeConnected) {
      const { horizon_cycles, pack_size_k } = currentProblemOptions();
      payload = await quantumBridge.revealFuture(state.manualSelection, { horizon_cycles, pack_size_k });
    } else {
      const response = await fetch(`${ASSET_ROOT}/demo/future.json`, { cache: "no-store" });
      if (!response.ok) throw new Error("The held-out fixture asset could not be loaded.");
      const asset = await response.json();
      const horizon = asset.by_horizon?.[String(state.horizonCycles)];
      const ids = state.manualSelection.map((index) => state.demoState.candidate_ids[index]);
      if (!horizon || ids.some((id) => !horizon.by_cell?.[id])) throw new Error("The held-out fixture does not cover this pack.");
      payload = {
        data_classification: "synthetic-fixture",
        label: "Synthetic held-out fixture reveal",
        decision_cycle: asset.decision_cycle,
        target_cycle: horizon.target_cycle,
        selected_cell_ids: ids,
        truth: ids.map((id) => horizon.by_cell[id].truth),
        observations: ids.flatMap((id) => horizon.by_cell[id].observations),
        extrapolation_note: asset.source,
        future_disclosed: true,
      };
    }
    if (payload?.data_classification !== "synthetic-fixture" || !payload.future_disclosed) {
      throw new Error("The reveal service returned an invalid held-out payload.");
    }
    const selectedIds = state.manualSelection.map((index) => state.demoState.candidate_ids[index]);
    if (selectedIds.some((id) => !(payload.truth ?? []).some((truth) => truth.cell_id === id))) {
      throw new Error("The reveal did not include every cell in the current pack.");
    }
    state.futureReveal = payload;
    state.futureRevealed = true;
    setStatus(`Held-out future revealed for ${state.packSizeK} selected cells at cycle ${payload.target_cycle}.`, "success");
  } catch (error) {
    setStatus(friendlyError(error, "reveal"), "error");
    pushToast("Future reveal could not complete.", "error");
  } finally {
    state.busy = false;
    render();
  }
}

function chooseResult(algorithm) {
  const result = state.classicalResults?.results?.[algorithm];
  if (!result || result.selected_indices?.length !== state.packSizeK) return;
  state.manualSelection = [...result.selected_indices];
  state.manualEvaluation = null;
  if (state.futureRevealed && state.futureReveal) {
    const truthIds = new Set((state.futureReveal.truth ?? []).map((item) => item.cell_id));
    const ids = state.manualSelection.map((index) => state.demoState.candidate_ids[index]);
    if (ids.some((id) => !truthIds.has(id))) state.futureRevealed = false;
  }
  setStatus(`${resultNames(algorithm)[0]} pack loaded into the manual string.`);
  render();
  void refreshManualEvaluation();
}

function toggleCell(index) {
  if (!Number.isInteger(index) || !state.demoState?.snapshots?.[index]) return;
  const alreadySelected = state.manualSelection.includes(index);
  if (alreadySelected) {
    state.manualSelection = state.manualSelection.filter((selected) => selected !== index);
    const cellId = state.demoState.candidate_ids[index];
    state.focusAfterRender = `#cell-add-${CSS.escape(cellId)}`;
    if (state.futureReveal && !state.manualSelection.every((selected) => (state.futureReveal.truth ?? []).some((truth) => truth.cell_id === state.demoState.candidate_ids[selected]))) state.futureRevealed = false;
  } else {
    if (state.manualSelection.length >= state.packSizeK) {
      pushToast(`The series string is full at K=${state.packSizeK}. Remove a cell before adding another.`, "warning");
      return;
    }
    state.manualSelection = [...state.manualSelection, index];
    const cellId = state.demoState.candidate_ids[index];
    state.focusAfterRender = `#cell-add-${CSS.escape(cellId)}`;
  }
  if (state.futureRevealed) {
    state.futureRevealed = false;
    state.futureReveal = null;
    setStatus("Pack changed. Reveal the held-out future again for this string.");
  }
  state.manualEvaluation = null;
  render();
  void refreshManualEvaluation();
}

function handleProblemChange(change) {
  if (change === "mission") state.missionId = dom.mission.value;
  if (change === "horizon") state.horizonCycles = Number(dom.horizon.value);
  if (change === "pack-size") state.packSizeK = Number(dom.packSize.value);
  if (state.manualSelection.length > state.packSizeK) state.manualSelection = state.manualSelection.slice(0, state.packSizeK);
  invalidateProblem();
  const requestId = ++state.problemRequestId;
  if (state.runtimeConnected && (change === "horizon" || change === "pack-size")) {
    state.demoState = null;
    setStatus("Loading candidate features for the updated problem…");
  }
  const load = async () => {
    if (state.runtimeConnected) {
      try {
        await refreshDemoState(requestId);
        if (requestId !== state.problemRequestId) return;
      } catch (error) {
        if (requestId !== state.problemRequestId) return;
        state.demoState = null;
        setStatus("The Python runtime could not load candidates for this setting.", "error");
        pushToast("Candidate pool could not be refreshed.", "error");
      }
    } else {
      state.demoState = staticInventoryState(state.horizonCycles);
    }
    render();
    void refreshManualEvaluation();
  };
  void load();
  render();
}

function setManualPack(indices) {
  if (!Array.isArray(indices) || indices.length !== state.packSizeK || new Set(indices).size !== indices.length) {
    pushToast("The recommendation does not match the current pack size.", "warning");
    return;
  }
  state.manualSelection = [...indices];
  state.manualEvaluation = null;
  if (state.futureRevealed) {
    state.futureRevealed = false;
    state.futureReveal = null;
  }
  setStatus("Recommended cells loaded into the manual series string.");
  render();
  void refreshManualEvaluation();
}

function handleAction(action, target) {
  if (action === "toggle-cell") toggleCell(Number(target.dataset.index));
  if (action === "remove-cell") toggleCell(Number(target.dataset.index));
  if (action === "clear-pack") {
    state.manualSelection = [];
    state.manualEvaluation = null;
    state.futureRevealed = false;
    state.futureReveal = null;
    setStatus("Manual pack cleared.");
    render();
  }
  if (action === "run-classical") void loadClassicalResults();
  if (action === "choose-result") chooseResult(target.dataset.algorithm);
  if (action === "use-exact") chooseResult("exact_enumeration");
  if (action === "run-qaoa") void loadQaoa();
  if (action === "use-qaoa") {
    const indices = state.qaoaResult?.best_feasible_sample?.selected_indices;
    if (indices) setManualPack(indices);
    else pushToast("QAOA did not produce a feasible measured pack.", "warning");
  }
  if (action === "reveal") void revealFuture();
  if (action === "open-assumptions") {
    state.assumptionsOpen = true;
    renderHeader();
    dom.assumptions.scrollIntoView({ block: "nearest", behavior: motionAllowed() ? "smooth" : "auto" });
    dom.assumptions.querySelector("summary")?.focus();
  }
}

function motionAllowed() {
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

document.addEventListener("click", (clickEvent) => {
  const objective = clickEvent.target.closest("[data-objective]");
  if (objective) {
    state.objectiveMode = objective.dataset.objective;
    invalidateProblem();
    render();
    return;
  }
  const actionTarget = clickEvent.target.closest("[data-action]");
  if (actionTarget) handleAction(actionTarget.dataset.action, actionTarget);
});

dom.mission.addEventListener("change", () => handleProblemChange("mission"));
dom.horizon.addEventListener("change", () => handleProblemChange("horizon"));
dom.packSize.addEventListener("change", () => handleProblemChange("pack-size"));
dom.assumptions.addEventListener("toggle", () => {
  if (state.assumptionsOpen !== dom.assumptions.open) {
    state.assumptionsOpen = dom.assumptions.open;
    renderHeader();
  }
});

function validateBenchmarkAssets(summary, trials) {
  return summary?.data_classification === "derived-real"
    && summary?.contains_cell_level_records === false
    && Number.isInteger(summary?.trial_count)
    && trials?.data_classification === "derived-real"
    && trials?.contains_cell_level_records === false
    && Array.isArray(trials?.trials);
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}

async function initialize() {
  render();
  const [inventory, classical, qaoaReplay, benchmark, trials, capabilities] = await Promise.allSettled([
    loadJson(`${ASSET_ROOT}/demo/inventory.json`),
    loadJson(`${ASSET_ROOT}/demo/classical.json`),
    loadJson(`${ASSET_ROOT}/demo/qaoa-replay.json`),
    loadJson(`${ASSET_ROOT}/benchmark/summary.json`),
    loadJson(`${ASSET_ROOT}/benchmark/trials.json`),
    quantumBridge.getCapabilities(),
  ]);
  if (inventory.status === "fulfilled" && inventory.value.data_classification === "synthetic-fixture" && inventory.value.future_values_included === false) {
    state.inventoryAsset = inventory.value;
  }
  if (classical.status === "fulfilled" && classical.value.data_classification === "synthetic-fixture" && classical.value.future_values_used === false) {
    state.staticClassical = classical.value;
  }
  if (qaoaReplay.status === "fulfilled" && qaoaReplay.value.mode === "precomputed-synthetic-replay") {
    state.staticQaoaReplay = qaoaReplay.value;
  }
  if (benchmark.status === "fulfilled" && trials.status === "fulfilled" && validateBenchmarkAssets(benchmark.value, trials.value)) {
    state.benchmarkSummary = benchmark.value;
    state.benchmarkTrials = trials.value;
  }
  state.runtimeCapabilities = capabilities.status === "fulfilled" ? capabilities.value : null;
  const pythonAvailable = state.runtimeCapabilities?.available
    ?? state.runtimeCapabilities?.qiskit_available
    ?? false;
  state.runtimeConnected = quantumBridge.hasInteractiveRuntime() && pythonAvailable === true;
  try {
    await refreshDemoState();
    setStatus(state.runtimeConnected
      ? "Python bridge ready. The inventory contains decision-time features only."
      : "Synthetic interaction fixture loaded. Benchmark results below are replayed aggregate data.", "success");
  } catch (error) {
    state.demoState = null;
    console.error("RePack-Q candidate inventory could not load:", error);
    const errorText = String(error?.message ?? error?.stack ?? error?.name ?? "unknown error")
      .replace(/\u001b\[[0-9;]*m/g, "");
    const errorLines = errorText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    let detail = errorLines.at(-1) ?? "unknown error";
    for (let index = errorLines.length - 1; index >= 0; index -= 1) {
      if (/^[A-Za-z_][\w.]*Error:|^[A-Za-z_][\w.]*Exception:/.test(errorLines[index])) {
        detail = errorLines[index];
        break;
      }
    }
    detail = detail.slice(0, 320);
    setStatus(`Candidate inventory failed: ${detail}`, "error");
  }
  if (!state.staticClassical) {
    state.classicalResults = null;
  }
  render();
}

await initialize();
