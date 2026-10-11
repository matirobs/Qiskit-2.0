// dashboard controls, selections, and capacity charts
'use strict';
const $ = id => document.getElementById(id);
const names = {healthiest: 'Healthiest first', greedy: 'Greedy matching', annealing: 'Simulated annealing', exact: 'Exact search', manual: 'Your selection', qaoa_penalty: 'Quantum · size penalty', qaoa_swap: 'Quantum · cell swaps'};
const colors = ['#83e6b6', '#8bbcff', '#e7c081', '#c2a6f0', '#ed9caa'];
const state = {bootstrap: null, trial: null, reveal: null, selected: [], active: 'annealing', manual: null, mode: 'trajectory_aware', busy: false, revision: 0};
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (value, places = 3) => Number.isFinite(value) ? value.toFixed(places) : '—';
const name = method => names[method] || method;
const announce = message => { $('status-message').textContent = message; };
function showError(error) { $('error').textContent = error.message; $('error').hidden = false; announce(error.message); }
// send dashboard requests and surface server errors
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The request failed. Please try again.');
  return data;
}
// keep controls disabled during a run or when sample data cannot support them
function controls() {
  document.body.classList.toggle('busy', state.busy);
  document.querySelectorAll('.control-grid input, .control-grid select, .segmented button, #partition, #run').forEach(el => {
    el.disabled = state.busy || (state.bootstrap?.source === 'synthetic-fixture' && ['horizon','cutoff','candidates','partition'].includes(el.id));
  });
  $('run').querySelector('span').textContent = state.busy ? 'Computing locally…' : 'Run comparison';
  $('download').disabled = !state.trial || state.busy;
  $('reveal').disabled = state.busy || !state.trial?.future_available || !!state.reveal;
  document.querySelectorAll('.cell-card, .algorithm-button').forEach(el => { el.disabled = state.busy; });
  $('include-quantum').disabled = state.busy || !state.bootstrap?.quantum.available;
}
// settings changed, so the old results no longer describe this experiment
function invalidate() {
  state.revision++; state.trial = null; state.reveal = null; state.manual = null; state.selected = [];
  $('compute-status').textContent = 'Settings changed · run comparison'; $('compute-status').className = 'live-label dirty';
  $('inventory').innerHTML = '<div class="loading-card">Your settings are ready. Run a comparison to build a new pool.</div>';
  $('pool-count').textContent = '— cells'; $('algorithm-rows').replaceChildren(); $('weight-details').replaceChildren();
  $('pool-summary').textContent = 'Settings changed. Run a comparison to sample a new shared candidate pool.';
  $('pool-exclusions').hidden = true; renderDatasetCaption();
  $('error').hidden = true; renderSelection(); renderBenchmark(); controls();
}
function currentResult() {
  return state.active === 'manual' ? state.manual : state.trial?.results.find(r => r.algorithm === state.active);
}
function renderDatasetCaption() {
  $('dataset-caption').textContent = state.bootstrap?.source === 'synthetic-fixture'
    ? 'Eight invented sample batteries; no real training or test partitions.'
    : $('partition').value === 'all'
      ? 'Sample from the full dataset, including batteries used to train or tune the model. This is an exploratory comparison.'
      : 'Sample only from batteries excluded from model fitting. These test batteries were inspected in earlier experiments.';
}
// cell cards show current condition and the forecast, never hidden measurements
function renderInventory() {
  if (!state.trial) return;
  $('pool-count').textContent = `${state.trial.snapshots.length} cells`;
  const metadata = state.trial.metadata, splits = metadata.candidate_partitions;
  const sourceDescription = metadata.partition === 'all'
    ? `the full ${metadata.dataset_cells}-battery dataset`
    : `the ${metadata.partition_cells}-battery test set (${metadata.dataset_cells} in the full dataset)`;
  $('pool-summary').textContent = state.bootstrap.source === 'synthetic-fixture'
    ? 'All 8 invented sample batteries. No real measurements are represented.'
    : `${state.trial.snapshots.length} candidates sampled from ${metadata.eligible_cells} eligible batteries in ${sourceDescription}. Seed ${state.trial.settings.seed} controls the sample; these are not the top-ranked batteries. ${splits ? `Selected candidates: ${splits.train} training, ${splits.validation} validation, ${splits.test} test.` : ''}`;
  const excluded = Object.entries(metadata.skipped || {});
  $('pool-exclusions').hidden = excluded.length === 0;
  $('exclusions-title').textContent = `${excluded.length} batteries excluded by the current settings`;
  $('exclusions-reasons').textContent = excluded.map(([id, reason]) => `Cell ${id}: ${reason}`).join('; ');
  $('inventory').innerHTML = state.trial.snapshots.map((cell, i) => {
    const selected = state.selected.includes(i);
    return `<button class="cell-card ${selected ? 'selected' : ''}" data-index="${i}" aria-pressed="${selected}" aria-label="Cell ${escape(cell.cell_id)}, ${number(cell.health_percent,1)} percent health" aria-describedby="inventory-help">
      <div class="cell-top"><span class="cell-id">CELL ${escape(cell.cell_id)}</span><span class="cell-check" aria-hidden="true">${selected ? '<svg class="icon"><use href="#i-check"/></svg>' : ''}</span></div>
      <div class="cell-health"><strong>${number(cell.health_percent,1)}<span>%</span></strong><span>current health</span></div>
      <div class="health-meter" aria-hidden="true"><span style="width:${Math.min(100, Math.max(0,cell.health_percent))}%"></span></div>
      <div class="cell-stats"><div><span>Current capacity</span><strong>${number(cell.capacity_ah)} <small>Ah</small></strong></div><div><span>Predicted future</span><strong>${number(cell.predicted_capacity_ah)} <small>Ah</small></strong></div></div>
      <div class="cell-foot"><span>${Number.isFinite(cell.internal_resistance_ohm) ? number(cell.internal_resistance_ohm * 1000,1)+' milliohms' : 'Resistance unavailable'}</span><span class="loss">−${number(cell.predicted_loss_ah)} Ah forecast</span></div></button>`;
  }).join('');
  $('inventory-help').textContent = `Click cells to build your own group (${state.selected.length}/${state.trial.settings.pack_size} selected). Ah means amp-hours. ${state.bootstrap.source === 'synthetic-fixture' ? 'Invented sample values; no measured future available.' : state.reveal ? 'Recorded future measurements have been revealed.' : 'Future measurements stay hidden until you reveal them.'}`;
}
function renderSelection() {
  const trial = state.trial, result = currentResult(), cells = state.selected.map(i => trial.snapshots[i]);
  $('selection-method').textContent = trial ? name(state.active) : 'Waiting for a run';
  $('selection-title').textContent = trial ? `${cells.length} cells, one second life` : 'Your selected group';
  $('pack-slots').innerHTML = cells.map((c,i) => `<span class="pack-chip"><i style="background:${colors[i]}"></i>Cell ${escape(c.cell_id)}</span>`).join('') +
    Array.from({length: Math.max(0,(trial?.settings.pack_size || Number($('pack-size').value)) - cells.length)}, () => '<span class="pack-chip empty">Choose a cell</span>').join('');
  $('pack-capacity').textContent = number(result?.usable_pack_capacity_ah);
  $('pack-spread').textContent = number(result?.predicted_capacity_spread_ah);
  $('pack-gap').textContent = number(result?.objective_gap_abs);
  $('reveal-title').textContent = state.reveal ? 'The recorded future, revealed.' : trial && !trial.future_available ? 'Illustrative sample data.' : 'The future is still hidden.';
  $('reveal-caption').textContent = state.reveal ? 'These outcomes were excluded from prediction and selection.' : trial && !trial.future_available ? 'No recorded future exists for invented sample cells.' : 'Compare your choice with measurements excluded from selection.';
  const observed = result?.observed_pack_divergence;
  $('observed-result').hidden = !Number.isFinite(observed);
  $('observed-result').innerHTML = Number.isFinite(observed) ? `<span>Actual imbalance<strong>${number(observed*100,2)}%</strong></span><span>Actual minimum<strong>${number(result.observed_usable_capacity_ah)} amp-hours</strong></span><span>Actual spread<strong>${number(result.observed_capacity_spread_ah)} amp-hours</strong></span>` : '';
  renderChart();
}
// connect current capacity to its forecast; filled dots show actual results after reveal
function renderChart() {
  const trial = state.trial, cells = state.selected.map(i => trial.snapshots[i]), target = $('capacity-chart');
  if (!cells.length) { target.innerHTML = '<div class="empty-message">Select cells to explore their capacity outlook.</div>'; return; }
  const width = Math.max(260,target.clientWidth), height = 264, left = 48, right = width-64, top = 32, bottom = 220;
  const values = cells.flatMap(c => [c.capacity_ah,c.predicted_capacity_ah,...(state.reveal ? [state.reveal.truth[c.cell_id].actual_capacity_ah] : [])]);
  const low = Math.max(0,Math.min(...values)-.08), high = Math.max(...values)+.08;
  const y = v => bottom-(v-low)/(high-low)*(bottom-top);
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Capacity in amp-hours at the current cycle and forecast endpoint. ${state.reveal ? 'Recorded future endpoints are also shown.' : trial.future_available ? 'Future measurements are hidden.' : 'Invented sample endpoints; no recorded future exists.'}"><text x="${left}" y="14" fill="#a5bac8" font-size="9">Capacity · amp-hours</text>`;
  for(let i=0;i<5;i++) { const v=low+(high-low)*i/4; svg+=`<path d="M${left} ${y(v)}H${right}" stroke="#2a3c47" stroke-width="1"/><text x="${left-10}" y="${y(v)+3}" text-anchor="end" fill="#9eb5c3" font-size="9">${number(v,2)}</text>`; }
  svg += `<text x="${left}" y="244" text-anchor="middle" fill="#9eb5c3" font-size="9">Now</text><text x="${(left+right)/2}" y="244" text-anchor="middle" fill="#9eb5c3" font-size="9">+${trial.settings.horizon/2} cycles</text><text x="${right}" y="244" text-anchor="middle" fill="#9eb5c3" font-size="9">+${trial.settings.horizon} cycles</text>`;
  cells.forEach((cell,i) => {
    const color=colors[i];
    svg+=`<g stroke="${color}" fill="${color}"><path d="M${left} ${y(cell.capacity_ah)}L${right} ${y(cell.predicted_capacity_ah)}" stroke-width="1.8" stroke-dasharray="5 5" fill="none"/><circle cx="${left}" cy="${y(cell.capacity_ah)}" r="3"/><circle cx="${right}" cy="${y(cell.predicted_capacity_ah)}" r="4" fill="#101e28" stroke-width="1.8"/></g>`;
    // Separate labels in a legend instead of overlapping forecast endpoints.
    svg+=`<rect x="${left+i*(width-left-10)/cells.length}" y="255" width="5" height="5" rx="1" fill="${color}"/><text x="${left+9+i*(width-left-10)/cells.length}" y="261" fill="#b9cbd5" font-size="8">Cell ${escape(cell.cell_id)}</text>`;
    if(state.reveal) { const truth=state.reveal.truth[cell.cell_id]; svg+=`<circle cx="${left+(right-left)*(truth.target_cycle_index-trial.settings.cutoff)/trial.settings.horizon}" cy="${y(truth.actual_capacity_ah)}" r="4.5" fill="${color}" stroke="#eaf4f4" stroke-width="1.3"><title>Cell ${escape(cell.cell_id)}: ${number(truth.actual_capacity_ah)} amp-hours at cycle ${truth.target_cycle_index}; ${truth.nearest_cycle_distance} cycles from target</title></circle>`; }
  });
  target.innerHTML = svg+'</svg>';
}
// show measured quantum results alongside the same classical scores
function renderTable() {
  if (!state.trial) return;
  const rows = [...state.trial.results, ...(state.manual ? [state.manual] : [])];
  $('algorithm-rows').innerHTML = rows.map(r => `<tr data-algorithm="${escape(r.algorithm)}" class="${state.active === r.algorithm ? 'active' : ''}"><td><button class="algorithm-button" data-algorithm="${escape(r.algorithm)}" aria-pressed="${state.active === r.algorithm}"><span class="algorithm-dot"></span>${escape(name(r.algorithm))}${r.algorithm==='exact' ? '<span class="row-badge">REFERENCE</span>' : ''}</button></td><td>${r.selected_cell_ids.map(escape).join(' · ')}</td><td>${number(r.objective_value)}</td><td>${number(r.objective_gap_abs)}</td><td>${r.algorithm === 'manual' ? '—' : number(r.runtime_ms,2)+' ms'}</td></tr>`).join('');
}
// this saved benchmark keeps its own settings when the workbench changes
function renderBenchmark() {
  const benchmark = state.bootstrap?.benchmark;
  if(!benchmark) { $('benchmark-label').textContent='No saved benchmark'; $('benchmark-description').textContent='A matching local benchmark report is not available.'; $('benchmark-bars').innerHTML='<div class="empty-message">Run and save the classical benchmark to see measured outcomes here.</div>'; $('benchmark-takeaway').textContent='This panel displays saved measurements only; no benchmark values have been invented.'; return; }
  const rows=benchmark.summary.filter(r=>r.mode===state.mode), max=Math.max(...rows.map(r=>r.mean_observed_pack_divergence)), best=Math.min(...rows.map(r=>r.mean_observed_pack_divergence));
  $('benchmark-label').textContent=`Saved · ${benchmark.trials} test pools`;
  $('benchmark-description').textContent=`${state.mode==='current_only' ? 'Match for today' : 'Match for the future'} · ${benchmark.settings.candidate_count} candidates, choose ${benchmark.settings.pack_size} · first-life only · ${benchmark.settings.horizon} cycles ahead. Saved held-out test pools; independent of the workbench source and settings.`;
  $('benchmark-bars').innerHTML='<div class="benchmark-columns"><span>ALGORITHM</span><span>ACTUAL IMBALANCE ↓ / MINIMUM CAPACITY</span></div>'+rows.map(r=>`<div class="benchmark-row ${r.mean_observed_pack_divergence===best?'best':''}"><span class="benchmark-name">${escape(name(r.algorithm))}</span><div class="bar-track"><div class="bar-fill" style="width:${100*r.mean_observed_pack_divergence/max}%"></div></div><span class="benchmark-number">${number(100*r.mean_observed_pack_divergence,2)}%</span><span class="benchmark-capacity">${number(r.mean_observed_usable_capacity_ah)} Ah</span></div>`).join('');
  $('benchmark-takeaway').textContent=`${name(rows.find(r=>r.mean_observed_pack_divergence===best).algorithm)} had the lowest average actual imbalance in these saved pools. Optimizing the matching score did not guarantee better physical outcomes. Compare retained capacity too; pools overlap and test cells were previously inspected.`;
}
function renderWeights() {
  const labels={current:'Current capacity matching',future:'Future capacity matching',temperature:'Temperature matching',capacity:'Current capacity matching',resistance:'Resistance matching',trajectory:'Future capacity matching',health:'Current health reward',uncertainty:'Prediction uncertainty'};
  const weights=state.trial.objective_metadata.effective_weights || {};
  $('weight-details').innerHTML=Object.entries(weights).map(([key,value])=>`<div class="weight-row"><span>${escape(labels[key] || key.replaceAll('_',' '))}</span><span>${number(value*100,0)}%</span></div>`).join('');
}
async function run() {
  if(state.busy) return;
  $('error').hidden=true; state.busy=true; $('compute-status').textContent='Computing locally…'; $('compute-status').className='live-label busy'; controls();
  try {
    const trial=await api('/api/trial',{horizon:Number($('horizon').value),cutoff:Number($('cutoff').value),candidates:Number($('candidates').value),pack_size:Number($('pack-size').value),seed:Number($('seed').value),mode:state.mode,quantum:$('include-quantum').checked,partition:$('partition').value});
    state.revision++; state.trial=trial; state.reveal=null; state.manual=null; state.active='annealing'; state.selected=[...currentResult().selected_indices];
    renderInventory(); renderSelection(); renderTable(); renderWeights();
    $('compute-status').textContent=`Completed in ${number(trial.computation_ms,0)} ms`; $('compute-status').className='live-label';
    announce(`Comparison complete. ${trial.results.length} selections available; ${trial.quantum.executed_runs} quantum circuits sampled.`);
  } catch(error) { showError(error); $('compute-status').textContent='Run failed · try again'; $('compute-status').className='live-label dirty'; }
  finally { state.busy=false; controls(); }
}
// score a complete manual group using the same rules as the algorithms
async function toggleCell(index) {
  if(state.busy || !state.trial) return;
  if(state.selected.includes(index)) state.selected=state.selected.filter(i=>i!==index);
  else if(state.selected.length<state.trial.settings.pack_size) state.selected.push(index);
  else { announce('Your group is full. Remove one cell before adding another.'); $('inventory-help').textContent='Your group is full. Click a selected cell to remove it first.'; return; }
  state.selected.sort((a,b)=>a-b); state.active='manual'; state.manual=null; const revision=++state.revision, token=state.trial.trial_id; // ignore replies for an older selection
  renderInventory(); renderSelection(); renderTable(); controls();
  announce(`${state.selected.length} of ${state.trial.settings.pack_size} cells selected.`);
  if(state.selected.length===state.trial.settings.pack_size) {
    try { const result=await api('/api/manual',{trial_id:token,indices:state.selected}); if(revision===state.revision && token===state.trial?.trial_id) {state.manual=result; renderSelection(); renderTable(); controls();} }
    catch(error) { if(revision===state.revision) showError(error); }
  }
}
$('inventory').addEventListener('click',event=>{const card=event.target.closest('[data-index]'); if(card) toggleCell(Number(card.dataset.index));});
$('algorithm-rows').addEventListener('click',event=>{const button=event.target.closest('button[data-algorithm]'); if(!button || state.busy) return; state.revision++; state.active=button.dataset.algorithm; state.selected=[...currentResult().selected_indices]; renderInventory(); renderSelection(); renderTable(); controls();});
$('run').addEventListener('click',run);
['horizon','cutoff','candidates','pack-size','seed','include-quantum','partition'].forEach(id=>$(id).addEventListener('change',invalidate));
document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{
  if(state.busy || state.mode===button.dataset.mode) return;
  state.mode=button.dataset.mode; document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});
  $('objective-caption').textContent=state.mode==='current_only'?'Consider current condition only; future predictions stay out of scoring.':'Consider current condition and predicted future capacity.'; invalidate();
}));
$('reveal').addEventListener('click',async()=>{
  if(state.busy || !state.trial || state.reveal) return;
  state.busy=true; state.revision++; controls(); $('error').hidden=true;
  try {state.reveal=await api('/api/reveal',{trial_id:state.trial.trial_id}); state.trial.results=state.reveal.results;
    if(state.active==='manual' && state.selected.length===state.trial.settings.pack_size) state.manual=await api('/api/manual',{trial_id:state.trial.trial_id,indices:state.selected});
    renderInventory(); renderSelection(); renderTable(); announce('Recorded future measurements revealed. They were excluded from selection.');
  } catch(error) {showError(error);} finally {state.busy=false; controls();}
});
// export the current run and only the future values already revealed
$('download').addEventListener('click',async()=>{
  if(!state.trial || state.busy) return;
  try {const trial=state.trial, manual=state.manual, revealed=state.reveal, selected={algorithm:state.active,indices:[...state.selected]}, problem=await api('/api/problem?trial_id='+encodeURIComponent(trial.trial_id));
    const blob=new Blob([JSON.stringify({source:state.bootstrap.source,trial,workbench_selection:selected,manual_selection:manual,recorded_future:revealed,problem},null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url; a.download=`repackq-run-${trial.settings.seed}.json`; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    announce('Run exported as a local JSON file.');
  } catch(error) {showError(error);}
});
// follow the section near the top, including scrolling without a menu click
const sectionMenu = [...document.querySelectorAll('.nav-item')].map(link => ({
  link, section: document.querySelector(link.getAttribute('href'))
}));
const sidebar = document.querySelector('.sidebar');
let navigationFrame = null;
function updateNavigation() {
  navigationFrame = null;
  const menuBottom = getComputedStyle(sidebar).position === 'sticky' ? sidebar.getBoundingClientRect().bottom : 0;
  const readingLine = Math.max(menuBottom + 24, Math.min(160, innerHeight * .2));
  let current = sectionMenu[0];
  for (const item of sectionMenu) {
    if (item.section.getBoundingClientRect().top <= readingLine) current = item;
  }
  // short final sections may never reach the reading line
  if (scrollY > 0 && scrollY + innerHeight >= document.documentElement.scrollHeight - 2) current = sectionMenu.at(-1);
  for (const {link} of sectionMenu) {
    const active = link === current.link;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  }
}
function scheduleNavigation() {
  if (navigationFrame === null) navigationFrame = requestAnimationFrame(updateNavigation);
}
window.addEventListener('scroll', scheduleNavigation, {passive: true});
['resize', 'hashchange', 'pageshow'].forEach(event => window.addEventListener(event, scheduleNavigation));
new ResizeObserver(scheduleNavigation).observe(document.body);
scheduleNavigation();
new ResizeObserver(renderChart).observe($('capacity-chart'));
(async()=>{
  try {state.bootstrap=await api('/api/bootstrap');
    $('partition').value = state.bootstrap.defaults.partition;
    $('partition').querySelector('[value="all"]').textContent = state.bootstrap.source === 'synthetic-fixture' ? 'Invented sample batteries' : `Full dataset · ${state.bootstrap.dataset_cells} batteries`;
    $('partition').querySelector('[value="test"]').textContent = `Held-out test batteries · ${state.bootstrap.test_cells || 0}`;
    renderDatasetCaption();
    const evaluation=state.bootstrap.evaluation;
    if(evaluation) { $('accuracy-5').textContent=number(evaluation.within_5_percent,1)+'%'; $('accuracy-10').textContent=number(evaluation.within_10_percent,1)+'%'; $('average-error').textContent=number(evaluation.mean_absolute_error_ah)+' amp-hours'; $('forecast-count').textContent=evaluation.forecasts; $('test-count').textContent=evaluation.test_cells; } else { $('evaluation-label').textContent='No matching saved evaluation available'; $('evaluation-note').textContent='Accuracy requires measured test outcomes. No accuracy percentages are invented for sample inputs.'; }
    $('include-quantum').checked = state.bootstrap.quantum.available;
    $('quantum-capability').textContent = state.bootstrap.quantum.available ? 'Free local simulator · may take a few seconds' : state.bootstrap.quantum.message;
    renderBenchmark(); controls(); await run();
  } catch(error) {showError(error); $('compute-status').textContent='Connection failed';}
})();
