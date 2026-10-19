/* Decision Lab is an isolated, read-only consumer of the planning API. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('planning-section')) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const num = (value, digits = 0) => Number.isFinite(value) ? value.toLocaleString('en-GB', {maximumFractionDigits:digits}) : '—';
  const title = value => String(value || '').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
  const stamp = value => { const date = new Date(value); return Number.isFinite(date.getTime()) ? `${date.toISOString().slice(0,19).replace('T',' ')} UTC` : 'time unavailable'; };
  const colors = ['#8d9b82','#aa8241','#3e7b69','#6579a3','#9d7198','#b16f56','#647051'];
  const labels = {normal:'Normal operations',ride_closure:'Coaster closure',show_surge:'Show exit surge',heatwave:'Heatwave',power_fault:'Reduced power capacity',water_leak:'Water leak',food_rush:'Food court rush'};
  const actionLabels = {dispatch_maintenance:'Dispatch maintenance',reroute_guests:'Redirect arrivals',add_staff:'Assign two reserve staff',shed_load:'Reduce discretionary power',repair_leak:'Repair leak',replenish_stock:'Replenish food stock'};
  const assetLabels = {RIDE_COASTER:'Coaster',RIDE_WHEEL:'Observation wheel',FOOD_COURT:'Food court',FIRST_AID:'Guest care',POWER_HUB:'Power hub',WATER_PLANT:'Water plant',HOTEL:'Hotel',PARKING:'Parking'};
  const metrics = {queue_guest_minutes:['Accumulated waiting','guest-min'],served_guests:['Completed service visits','visits'],unserved_guests:['Unserved at horizon','visits'],staff_cost_eur:['Incremental staff cost','EUR'],energy_kwh:['Energy use','kWh'],feeder_exceedance_minutes:['Over feeder capacity','min'],excess_leak_liters:['Excess leak volume','L'],food_stockout_minutes:['Food stockout duration','min']};
  let observation = null, observedAt = 0, viewPending = false, busy = false, capabilities = null, result = null, pendingViewVersion = 0, inputsChanged = false, notice = null;

  async function request(path, options = {}) {
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {...options,cache:'no-store',signal:controller.signal});
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail;
        const message = typeof detail === 'string' ? detail : detail?.message || (Array.isArray(detail) ? detail.map(item => item.msg).join('; ') : `Service returned ${response.status}`);
        throw new Error(message);
      }
      return data;
    } finally { clearTimeout(timeout); }
  }

  function setStatus(message, type = '') { $('planning-status').textContent = message; $('planning-status').className = `planning-status ${type}`; }
  function locked() { return viewPending || observation?.mode === 'replay'; }
  function updateAvailability() {
    const fresh = observation && Date.now() - observedAt < 10000;
    $('planning-run').disabled = busy || locked() || !capabilities || !fresh || !/^[a-f0-9]{64}$/i.test(observation?.revision || '');
    $('planning-run').innerHTML = busy ? 'Comparing branches…' : 'Freeze & compare <span>↗</span>';
    $('planning-form').querySelectorAll('input,select').forEach(input => input.disabled=busy);
    if (locked()) setStatus('Recorded view · return to live before starting a prospective comparison. Previous results remain frozen.', 'warning');
    else if (!fresh) setStatus('Waiting for a fresh observation from the park. Existing results remain tied to their original observation.', 'warning');
    else if (notice && !busy) setStatus(notice.message, notice.type);
    else if (!busy && result?.decision.status === 'insufficient_data' && !inputsChanged) setStatus('Input quality is insufficient. Diagnostic estimates are shown; no decision shortlist is available.', 'warning');
    else if (!busy && result) setStatus(inputsChanged ? 'Inputs changed. Freeze & compare again to calculate a new set of branches.' : 'Frozen comparison · live telemetry continues independently. Estimates require operator review.', inputsChanged ? 'warning' : '');
    else if (!busy && capabilities) setStatus('Ready to compare · synthetic, uncalibrated estimates. No actions will be applied.');
    $('planning-observation').textContent = observation ? `${observation.mode === 'replay' ? 'Recorded' : 'Latest'} · ${stamp(observation.timestamp)}` : 'Waiting for park data';
    $('planning-observation-detail').textContent = observation ? `Tick ${observation.tick} · ${labels[observation.scenario] || title(observation.scenario)} · captured source quality ${observation.quality || 'unknown'}. Freeze occurs when you compare.` : 'Every branch starts from the same accepted observations.';
  }

  function violationText(violation) {
    if (typeof violation === 'string') return violation;
    if (violation.code === 'staff_budget_exceeded') return `${violation.requested} qualified staff requested; ${violation.available} assumed available.`;
    return violation.reason || title(violation.code);
  }
  function renderBranch(branch, index) {
    const summary = branch.summary, feasible = branch.constraints?.feasible === true;
    const shortlisted = result.decision.shortlist?.includes(branch.id), delta = branch.deltas_vs_baseline?.queue_guest_minutes;
    const deltaText = branch.id === 'baseline' ? 'Reference branch · no new intervention' : Number.isFinite(delta) ? `${num(Math.abs(delta))} guest-min ${delta <= 0 ? 'less' : 'more'} waiting vs do nothing` : 'Waiting difference unavailable';
    const schedule = branch.action_schedule || [];
    return `<article class="planning-branch ${feasible ? '' : 'infeasible'}" style="--branch-color:${colors[index % colors.length]}"><span class="planning-branch-type">${branch.id === 'baseline' ? 'Reference' : shortlisted ? 'Review option · no automatic ranking' : feasible ? 'Alternative' : 'Resource constraint'}</span><h4>${esc(branch.label)}</h4><strong class="planning-branch-number">${num(summary.queue_guest_minutes)}<small>guest-min of waiting</small></strong><p class="planning-branch-delta">${esc(deltaText)}</p><dl><div><dt>Service visits completed</dt><dd>${num(summary.served_guests)}</dd></div><div><dt>Visits still unserved</dt><dd>${num(summary.unserved_guests)}</dd></div><div><dt>Extra staff cost</dt><dd>€${num(summary.staff_cost_eur,1)}</dd></div></dl><ul class="planning-schedule">${schedule.length ? schedule.map(action => `<li>${esc(actionLabels[action.action] || title(action.action))}<small>${esc(assetLabels[action.asset_id] || title(action.asset_id))} · ${action.already_active ? 'already observed; no additional effect or cost' : `request +${num(action.at_minute)}m / ${action.action === 'dispatch_maintenance' ? 'work order' : 'effect'} +${num(action.effective_at_minute)}m`}</small></li>`).join('') : '<li>Keep the current operating response.<small>Existing observed mitigations remain in the starting state.</small></li>'}</ul><p class="planning-feasibility">${feasible ? `${num(branch.constraints.qualified_staff_requested)} / ${num(branch.constraints.qualified_staff_available)} reserve staff · modeled limits met` : `Not feasible · ${(branch.constraints?.violations || []).map(violationText).map(esc).join(' ')}`}</p>${(branch.tradeoffs || []).map(text => `<p class="planning-tradeoff">${esc(text)}</p>`).join('')}</article>`;
  }

  function renderResults() {
    $('planning-empty').hidden = true; $('planning-results').hidden = false;
    $('planning-result-title').textContent = `${labels[result.input.requested_scenario] || title(result.input.requested_scenario)} · ${result.horizon_minutes}-minute horizon`;
    const insufficient = result.decision.status === 'insufficient_data';
    $('planning-review-badge').textContent = insufficient ? 'INSUFFICIENT DATA · DO NOT RELY ON ESTIMATES' : 'OPERATOR REVIEW REQUIRED';
    $('planning-frozen').textContent = `Frozen ${stamp(result.input.timestamp)} · tick ${result.input.tick} · observed ${labels[result.input.current_scenario] || title(result.input.current_scenario)} · revision ${result.input.state_revision?.slice(0,12) || 'unavailable'}`;
    const p = result.parameters;
    $('planning-result-inputs').textContent = `Arrival demand ${num(p.arrival_multiplier,2)}× · sensitivity ±${num(p.demand_uncertainty_pct)}% · qualified reserve ${num(p.available_qualified_staff)} · routing compliance ${num(p.routing_compliance_pct)}%`;
    $('planning-branches').innerHTML = result.branches.map(renderBranch).join('');
    $('planning-comparison').innerHTML = `<caption class="sr-only">Modeled resource tradeoffs across operating branches</caption><thead><tr><th scope="col">Over ${num(result.horizon_minutes)} minutes</th>${result.branches.map(branch => `<th scope="col">${esc(branch.label)}${branch.constraints?.feasible ? '' : ' · infeasible'}</th>`).join('')}</tr></thead><tbody>${Object.entries(metrics).map(([key,[label,unit]]) => `<tr><td title="${esc(result.metric_definitions?.[key]?.meaning)}">${esc(label)}<small>${esc(unit)}</small></td>${result.branches.map(branch => { const range = branch.ranges?.[key]; return `<td>${key === 'staff_cost_eur' ? '€' : ''}${num(branch.summary[key],1)}<small>${range ? `${num(range.min,1)}–${num(range.max,1)} · demand cases` : 'Sensitivity unavailable'}</small></td>`; }).join('')}</tr>`).join('')}</tbody>`;
    $('planning-quality-title').textContent = insufficient ? 'Input quality blocks decision support' : 'Comparable estimates, subject to review';
    $('planning-quality').parentElement.classList.toggle('warning', insufficient);
    const issues = result.input.quality_issues || [];
    $('planning-quality').innerHTML = `<p>${insufficient ? 'The model returned diagnostic estimates, but source issues prevent a decision shortlist. Restore source quality before relying on a comparison.' : 'Source quality was accepted at capture. The model is synthetic and uncalibrated; no real-world savings or safe operating outcome is established.'}</p>${issues.length ? `<ul>${issues.map(issue => `<li>${esc(assetLabels[issue.asset_id] || issue.asset_id || 'Snapshot')}: ${esc(issue.quality)} · ${esc(issue.reason)}</li>`).join('')}</ul>` : ''}${(result.decision.rationale || []).map(text => `<p>${esc(text)}</p>`).join('')}<p>No physical control. These branches neither apply actions nor change the live scenario.</p><code>Plan ${esc(result.plan_id)}<br>Model ${esc(result.model.id)} · ${esc(result.model.version)}</code>`;
    $('planning-assumptions').innerHTML = `<ul>${(result.assumptions || []).map(text => `<li>${esc(text)}</li>`).join('')}</ul><h5>Outside this model</h5><ul>${(result.unsupported || []).map(text => `<li>${esc(text)}</li>`).join('')}</ul>`;
    renderChart();
  }

  function renderChart() {
    if (!result) return;
    const metric = $('planning-chart-metric').value;
    const value = point => metric === 'queue' ? Object.values(point.queue_guests || {}).reduce((a,b) => a+b,0) : point[{served:'cumulative_served_guests',power:'power_kw',stock:'food_stock_units',leak:'excess_leak_lpm'}[metric]];
    const series = result.branches.map((branch,index) => ({label:branch.label,color:colors[index % colors.length],points:branch.trajectory.map(point => [point.minute,value(point)]),infeasible:!branch.constraints?.feasible}));
    if (metric === 'power') series.push({label:'Feeder capacity',color:'#b46c59',points:result.branches[0].trajectory.map(point => [point.minute,point.feeder_capacity_kw]),dashed:true});
    const values = series.flatMap(item => item.points.map(point => point[1])).filter(Number.isFinite);
    const max = Math.max(1,...values)*1.12, width = 720, height = 220, left = 50, right = 14, top = 12, bottom = 29;
    const x = minute => left+(minute/result.horizon_minutes)*(width-left-right), y = number => height-bottom-(number/max)*(height-top-bottom);
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="planning-chart-title planning-chart-description"><title id="planning-chart-title">${esc($('planning-chart-metric').selectedOptions[0].textContent)}</title><desc id="planning-chart-description">Central modeled trajectories over ${result.horizon_minutes} minutes. Five-minute samples; summary metrics appear in the resource comparison.</desc>`;
    for (let i=0;i<=4;i++) { const v = max*i/4; svg += `<line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" stroke="#e6ecdf"/><text x="${left-9}" y="${y(v)+3}" text-anchor="end" font-size="9" fill="#93a180">${num(v)}</text>`; }
    for (let i=0;i<=4;i++) { const minute=result.horizon_minutes*i/4; svg += `<text x="${x(minute)}" y="${height-8}" text-anchor="middle" font-size="9" fill="#93a180">+${num(minute,1)}m</text>`; }
    series.forEach(item => { const points=item.points.filter(point => point.every(Number.isFinite)); svg += `<polyline points="${points.map(([minute,v]) => `${x(minute).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}" fill="none" stroke="${item.color}" stroke-width="2.5" ${item.dashed || item.infeasible ? 'stroke-dasharray="6 4"' : ''}><title>${esc(item.label)}${item.infeasible ? ' · infeasible resources' : ''}</title></polyline>`; svg += points.map(([minute,v]) => `<circle cx="${x(minute).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2.5" fill="${item.color}"><title>${esc(item.label)} · +${num(minute)} min: ${num(v,1)}</title></circle>`).join(''); });
    $('planning-chart').className='planning-chart'; $('planning-chart').innerHTML=svg+'</svg>';
    $('planning-chart-legend').innerHTML=series.map(item => `<span><i style="background:${item.color}"></i>${esc(item.label)}${item.infeasible ? ' · infeasible' : ''}</span>`).join('');
    $('planning-chart-note').textContent=`Central demand case · ${result.step_minutes}-minute intervals · estimates over ${result.horizon_minutes} minutes`;
  }

  async function loadCapabilities() {
    try {
      const data = await request('/api/planning/capabilities');
      if (data.model?.calibrated !== false || data.mutates_live_state !== false || !Array.isArray(data.scenarios)) throw new Error('Unexpected planning capability contract.');
      capabilities=data;
      [...$('planning-scenario').options].forEach(option => option.disabled=!data.scenarios.includes(option.value));
      updateAvailability();

    } catch (error) { capabilities=null; notice={message:`Decision Lab unavailable: ${error.message}. Reload the page after the service is available.`,type:'error'}; updateAvailability(); }
  }

  $('planning-form').addEventListener('submit', async event => {
    event.preventDefault(); updateAvailability(); if ($('planning-run').disabled) return;
    const revision=observation.revision, viewVersion=pendingViewVersion;
    const payload={scenario:$('planning-scenario').value,horizon_minutes:Number($('planning-horizon').value),expected_state_revision:revision,assumptions:{arrival_multiplier:Number($('planning-demand').value),demand_uncertainty_pct:Number($('planning-uncertainty').value),available_qualified_staff:Number($('planning-staff').value),routing_compliance_pct:Number($('planning-routing').value)}};
    busy=true; notice=null; updateAvailability(); setStatus('Freezing accepted observations and comparing independent branches…');
    try {
      const response=await request('/api/planning/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if (viewVersion!==pendingViewVersion || locked()) throw new Error('The shared view changed during comparison. Return to live and compare again.');
      if (response.input?.state_revision!==revision || response.model?.calibrated!==false || response.mutates_live_state!==false || response.physical_effect!==false || !Array.isArray(response.branches) || !response.branches.length) throw new Error('The planning result could not be associated with the requested frozen observation.');
      result=response; inputsChanged=false; renderResults();
    } catch (error) { notice={message:`Comparison unavailable: ${error.message}${result ? ' Previous results are unchanged.' : ''}`,type:'error'}; }
    finally { busy=false; updateAvailability(); }
  });
  $('planning-form').addEventListener('input', () => { $('planning-horizon-value').textContent=`${$('planning-horizon').value} minutes`; if (result) inputsChanged=true; notice=null; updateAvailability(); });
  $('planning-chart-metric').addEventListener('change',renderChart);
  document.addEventListener('park:state',event => { const previousMode=observation?.mode; observation=event.detail; observedAt=Date.now(); if (previousMode && previousMode!==observation.mode) pendingViewVersion++; updateAvailability(); });
  document.addEventListener('park:view-pending',event => { viewPending=!!event.detail; if (viewPending) pendingViewVersion++; updateAvailability(); });
  setInterval(updateAvailability,3000);
  loadCapabilities();
})();
