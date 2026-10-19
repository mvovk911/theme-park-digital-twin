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
  let evidenceBusy = false, historical = false, evidenceVerification = null, libraryOffset = 0, libraryTotal = 0;
  const savedBundles = new Set();
  let workflowContextKey = null;

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
    $('planning-run').disabled = busy || evidenceBusy || locked() || !capabilities || !fresh || !/^[a-f0-9]{64}$/i.test(observation?.revision || '');
    $('planning-run').innerHTML = busy ? 'Comparing branches…' : 'Freeze & compare <span>↗</span>';
    $('planning-form').querySelectorAll('input,select').forEach(input => input.disabled=busy);
    if (locked()) setStatus('Recorded view · return to live before starting a prospective comparison. Previous results remain frozen.', 'warning');
    else if (!fresh) setStatus('Waiting for a fresh observation from the park. Existing results remain tied to their original observation.', 'warning');
    else if (notice && !busy) setStatus(notice.message, notice.type);
    else if (!busy && result?.decision.status === 'insufficient_data' && !inputsChanged) setStatus('Input quality is insufficient. Diagnostic estimates are shown; no decision shortlist is available.', 'warning');
    else if (!busy && result) setStatus(inputsChanged ? 'Inputs changed. Freeze & compare again to calculate a new set of branches.' : 'Frozen comparison · live telemetry continues independently. Estimates require operator review.', inputsChanged ? 'warning' : '');
    else if (!busy && capabilities) setStatus('Ready to compare · synthetic, uncalibrated estimates. No actions will be applied.');
    updateEvidenceControls();
    $('planning-observation').textContent = observation ? `${observation.mode === 'replay' ? 'Recorded' : 'Latest'} · ${stamp(observation.timestamp)}` : 'Waiting for park data';
    $('planning-observation-detail').textContent = observation ? `Tick ${observation.tick} · ${labels[observation.scenario] || title(observation.scenario)} · captured source quality ${observation.quality || 'unknown'}. Freeze occurs when you compare.` : 'Every branch starts from the same accepted observations.';
  }

  function violationText(violation) {
    if (typeof violation === 'string') return violation;
    if (violation.code === 'staff_budget_exceeded') return `${violation.requested} qualified staff requested; ${violation.available} assumed available.`;
    return violation.reason || title(violation.code);
  }
  function outcomeMessage(decision) {
    if (decision.status === 'insufficient_data' || decision.outcome === 'insufficient_data') return ['Insufficient evidence to choose a response', 'Source quality blocks a decision shortlist. The numbers below are diagnostic estimates only.', 'warning'];
    if (decision.preferred_policy === 'baseline' && decision.outcome === 'no_intervention_benefit') return ['The model prefers no additional intervention', 'None of these candidate responses demonstrates an undominated benefit under the stated model. Retain the do-nothing reference for review; this does not authorize real-world action or inaction.', 'baseline'];
    if (decision.outcome === 'no_feasible_response') return ['No feasible response identified', 'Review resource constraints and revise the assumptions or candidate responses before deciding.', 'warning'];
    return ['Tradeoffs require an operator decision', 'The central-case shortlist is not an automatic recommendation. Check paired demand cases below: an option can help in the central case and cause harm under higher demand.', ''];
  }
  function robustnessMarkup(branch) {
    if (!branch.robustness) return '';
    const adverse = [...(branch.robustness.worse_than_baseline_cases || [])].sort((a,b) => ['high','central','low'].indexOf(a.case)-['high','central','low'].indexOf(b.case));
    if (!adverse.length) return branch.id === 'baseline' ? '' : '<p class="planning-tested">No adverse outcome in the tested demand cases. Staff cost remains a separate tradeoff.</p>';
    return `<div class="planning-adverse"><strong>Worse than do nothing in a tested demand case</strong>${adverse.map(item => {
      const paired = branch.sensitivity?.[item.case];
      const differences = (item.metrics || []).map(metric => {
        const delta = paired?.deltas_vs_baseline?.[metric];
        if (!Number.isFinite(delta)) return `${esc(metrics[metric]?.[0] || title(metric))}: delta unavailable`;
        return `${delta > 0 ? '+' : '−'}${num(Math.abs(delta),Math.abs(delta)<1 ? 3 : 1)} ${esc(metrics[metric]?.[1] || '')} ${esc((metrics[metric]?.[0] || title(metric)).toLowerCase())}`;
      });
      return `<p><b>${esc(title(item.case))} demand${Number.isFinite(paired?.demand_factor) ? ` (${num(paired.demand_factor,2)}× central)` : ''}</b><span>${differences.join('; ')}</span></p>`;
    }).join('')}<small>Paired differences against do nothing under the same demand. Tested cases only; staff cost is shown separately.</small></div>`;
  }
  function renderBranch(branch, index) {
    const summary = branch.summary, feasible = branch.constraints?.feasible === true;
    const shortlisted = result.decision.shortlist?.includes(branch.id), delta = branch.deltas_vs_baseline?.queue_guest_minutes;
    const deltaText = branch.id === 'baseline' ? 'Reference branch · no new intervention' : Number.isFinite(delta) ? `${num(Math.abs(delta))} guest-min ${delta <= 0 ? 'less' : 'more'} waiting vs do nothing` : 'Waiting difference unavailable';
    const schedule = branch.action_schedule || [];
    return `<article class="planning-branch ${feasible ? '' : 'infeasible'}" style="--branch-color:${colors[index % colors.length]}"><span class="planning-branch-type">${branch.id === 'baseline' ? result.decision.preferred_policy === 'baseline' ? 'Model-preferred reference' : 'Reference' : shortlisted ? 'Review option · no automatic ranking' : feasible ? 'Alternative' : 'Resource constraint'}</span><h4>${esc(branch.label)}</h4><strong class="planning-branch-number">${num(summary.queue_guest_minutes)}<small>guest-min of waiting · central case</small></strong><p class="planning-branch-delta">${esc(deltaText)}</p>${robustnessMarkup(branch)}<dl><div><dt>Service visits completed</dt><dd>${num(summary.served_guests)}</dd></div><div><dt>Visits still unserved</dt><dd>${num(summary.unserved_guests)}</dd></div><div><dt>Extra staff cost</dt><dd>€${num(summary.staff_cost_eur,1)}</dd></div></dl><ul class="planning-schedule">${schedule.length ? schedule.map(action => `<li>${esc(actionLabels[action.action] || title(action.action))}<small>${esc(assetLabels[action.asset_id] || title(action.asset_id))} · ${action.already_active ? 'already observed; no additional effect or cost' : `request +${num(action.at_minute)}m / ${action.action === 'dispatch_maintenance' ? 'work order' : 'effect'} +${num(action.effective_at_minute)}m`}</small></li>`).join('') : '<li>Keep the current operating response.<small>Existing observed mitigations remain in the starting state.</small></li>'}</ul><p class="planning-feasibility">${feasible ? `${num(branch.constraints.qualified_staff_requested)} / ${num(branch.constraints.qualified_staff_available)} reserve staff · modeled limits met` : `Not feasible · ${(branch.constraints?.violations || []).map(violationText).map(esc).join(' ')}`}</p>${(branch.tradeoffs || []).map(text => `<p class="planning-tradeoff">${esc(text)}</p>`).join('')}</article>`;
  }

  function renderResults() {
    $('planning-empty').hidden = true; $('planning-results').hidden = false;
    $('planning-result-title').textContent = `${labels[result.input.requested_scenario] || title(result.input.requested_scenario)} · ${result.horizon_minutes}-minute horizon`;
    const insufficient = result.decision.status === 'insufficient_data';
    $('planning-review-badge').textContent = insufficient ? 'INSUFFICIENT DATA · DO NOT RELY ON ESTIMATES' : 'OPERATOR REVIEW REQUIRED';
    $('planning-frozen').textContent = `Frozen ${stamp(result.input.timestamp)} · tick ${result.input.tick} · observed ${labels[result.input.current_scenario] || title(result.input.current_scenario)} · revision ${result.input.state_revision?.slice(0,12) || 'unavailable'}`;
    const p = result.parameters;
    $('planning-result-inputs').textContent = `Arrival demand ${num(p.arrival_multiplier,2)}× · sensitivity ±${num(p.demand_uncertainty_pct)}% · qualified reserve ${num(p.available_qualified_staff)} · routing compliance ${num(p.routing_compliance_pct)}%`;
    const [outcomeTitle,outcomeDescription,outcomeClass] = outcomeMessage(result.decision);
    $('planning-outcome').className = `planning-outcome ${outcomeClass}`;
    $('planning-outcome').innerHTML = `<strong>${esc(outcomeTitle)}</strong><p>${esc(outcomeDescription)}</p>`;
    $('planning-branches').innerHTML = result.branches.map(renderBranch).join('');
    $('planning-comparison').innerHTML = `<caption class="sr-only">Modeled resource tradeoffs across operating branches</caption><thead><tr><th scope="col">Over ${num(result.horizon_minutes)} minutes</th>${result.branches.map(branch => `<th scope="col">${esc(branch.label)}${branch.constraints?.feasible ? '' : ' · infeasible'}</th>`).join('')}</tr></thead><tbody>${Object.entries(metrics).map(([key,[label,unit]]) => `<tr><td title="${esc(result.metric_definitions?.[key]?.meaning)}">${esc(label)}<small>${esc(unit)}</small></td>${result.branches.map(branch => { const range = branch.ranges?.[key]; return `<td>${key === 'staff_cost_eur' ? '€' : ''}${num(branch.summary[key],1)}<small>${range ? `${num(range.min,1)}–${num(range.max,1)} · demand cases` : 'Sensitivity unavailable'}</small></td>`; }).join('')}</tr>`).join('')}</tbody>`;
    $('planning-quality-title').textContent = insufficient ? 'Input quality blocks decision support' : 'Comparable estimates, subject to review';
    $('planning-quality').parentElement.classList.toggle('warning', insufficient);
    const issues = result.input.quality_issues || [];
    $('planning-quality').innerHTML = `<p>${insufficient ? 'The model returned diagnostic estimates, but source issues prevent a decision shortlist. Restore source quality before relying on a comparison.' : 'Source quality was accepted at capture. The model is synthetic and uncalibrated; no real-world savings or safe operating outcome is established.'}</p>${issues.length ? `<ul>${issues.map(issue => `<li>${esc(assetLabels[issue.asset_id] || issue.asset_id || 'Snapshot')}: ${esc(issue.quality)} · ${esc(issue.reason)}</li>`).join('')}</ul>` : ''}${(result.decision.rationale || []).map(text => `<p>${esc(text)}</p>`).join('')}<p>No physical control. These branches neither apply actions nor change the live scenario.</p><code>Plan ${esc(result.plan_id)}<br>Model ${esc(result.model.id)} · ${esc(result.model.version)}</code>`;
    $('planning-assumptions').innerHTML = `<ul>${(result.assumptions || []).map(text => `<li>${esc(text)}</li>`).join('')}</ul><h5>Outside this model</h5><ul>${(result.unsupported || []).map(text => `<li>${esc(text)}</li>`).join('')}</ul>`;
    renderChart(); renderEvidenceContext(); updateEvidenceControls();
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

  function evidenceNotice(message, error = false) {
    $('planning-evidence-notice').textContent = message;
    $('planning-evidence-notice').classList.toggle('error', error);
  }
  function currentBundle() { return result?.evidence_bundle; }
  function updateEvidenceControls() {
    const bundle = currentBundle(), saved = bundle && savedBundles.has(bundle.bundle_id);
    $('planning-save').disabled = busy || evidenceBusy || !bundle || saved;
    $('planning-save').textContent = saved ? 'Saved comparison ✓' : 'Save comparison';
    $('planning-export').disabled = busy || evidenceBusy || !bundle;
    $('planning-import').disabled = busy || evidenceBusy;
    $('planning-library-toggle').disabled = busy || evidenceBusy;
    $('planning-library-refresh').disabled = busy || evidenceBusy;
    $('planning-library-previous').disabled = busy || evidenceBusy || libraryOffset === 0;
    $('planning-library-next').disabled = busy || evidenceBusy || libraryOffset + 20 >= libraryTotal;
    $('planning-library-items').querySelectorAll('button').forEach(button => button.disabled = busy || evidenceBusy);
    const context = bundle ? {bundle_id:bundle.bundle_id,saved:!!saved,scenario:result.input.requested_scenario,branches:result.branches.map(branch => ({id:branch.id,label:branch.label,action_schedule:branch.action_schedule}))} : null;
    const contextKey=JSON.stringify(context);
    if (contextKey!==workflowContextKey) { workflowContextKey=contextKey; document.dispatchEvent(new CustomEvent('park:planning-evidence',{detail:context})); }
  }
  function renderEvidenceContext() {
    const box = $('planning-evidence-context'), bundle = currentBundle();
    box.hidden = !bundle;
    if (!bundle) return;
    box.innerHTML = `<strong>${historical ? 'Reopened historical comparison' : 'Frozen comparison evidence'}</strong><p>${historical ? 'These are the saved observations, assumptions and results. They do not describe the current park or change its view. A new comparison uses the three default operating responses.' : 'Save or download this exact observation, request and result for later review.'}</p><small>${evidenceVerification?.verified ? 'Numerical reproduction verified · observation origin not authenticated · no execution authority.' : 'Synthetic observations · no execution authority.'}</small><code title="${esc(bundle.bundle_id)}">Evidence ${esc(bundle.bundle_id.slice(0,16))} · evaluated ${esc(stamp(bundle.payload?.evaluation_as_of))}</code>`;
  }
  function downloadBundle(bundle) {
    const blob = new Blob([JSON.stringify(bundle, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob), anchor = document.createElement('a');
    anchor.href=url; anchor.download=`aster-comparison-${bundle.bundle_id}.json`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  }
  function validHistoricalResult(bundle) {
    const saved = bundle?.payload?.result;
    if (!/^[a-f0-9]{64}$/.test(bundle?.bundle_id || '') || !saved || saved.model?.calibrated !== false || saved.mutates_live_state !== false || saved.physical_effect !== false || !Array.isArray(saved.branches) || !saved.branches.length) throw new Error('This file does not contain a supported frozen comparison.');
    return saved;
  }
  async function openBundle(bundle, expectedId = null, originalJSON = null) {
    const saved = validHistoricalResult(bundle);
    if (expectedId && bundle.bundle_id !== expectedId) throw new Error('The server returned a different evidence identifier.');
    const verified = await request('/api/planning/evidence/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:originalJSON ?? JSON.stringify(bundle)});
    if (verified.verified !== true || verified.bundle_id !== bundle.bundle_id || verified.scope !== 'historical_reproduction' || verified.execution_authority !== false || verified.origin_authenticated !== false) throw new Error('Historical reproduction could not be verified.');
    // Replace results only after full server verification; failures preserve the old view.
    result={...saved,evidence_bundle:bundle}; historical=true; evidenceVerification=verified; inputsChanged=false; notice=null;
    const input=bundle.payload.request;
    $('planning-scenario').value=input.scenario; $('planning-horizon').value=input.horizon_minutes;
    $('planning-horizon-value').textContent=`${input.horizon_minutes} minutes`;
    const p=input.assumptions;
    $('planning-demand').value=p.arrival_multiplier; $('planning-uncertainty').value=p.demand_uncertainty_pct;
    $('planning-staff').value=p.available_qualified_staff; $('planning-routing').value=p.routing_compliance_pct;
    renderResults(); evidenceNotice('Historical comparison reproduced from its enclosed inputs. Origin is not authenticated; live state is unchanged.');
  }
  async function loadLibrary() {
    if (busy || evidenceBusy) return;
    evidenceBusy=true; updateAvailability();
    try {
      const listing=await request(`/api/planning/evidence?limit=20&offset=${libraryOffset}`);
      if (!Array.isArray(listing.items) || listing.scope !== 'historical_evidence' || listing.execution_authority !== false) throw new Error('Unexpected evidence library response.');
      libraryTotal=listing.total;
      listing.items.forEach(item => savedBundles.add(item.bundle_id));
      $('planning-library-summary').textContent=`${num(libraryTotal)} saved · ${num(listing.retention?.max_bundles)} comparison limit · ${num(listing.stored_payload_bytes/1048576,2)} / ${num(listing.retention?.max_payload_bytes/1048576)} MiB · no automatic eviction`;
      $('planning-library-items').innerHTML=listing.items.length ? listing.items.map(item => `<div class="planning-saved-item"><div><strong>${esc(labels[item.scenario] || title(item.scenario))} · ${num(item.horizon_minutes)} min</strong><small>Evaluated ${esc(stamp(item.evaluation_as_of))}</small><code>${esc(item.bundle_id.slice(0,16))}</code></div><div><button data-evidence-open="${esc(item.bundle_id)}">Open</button><button data-evidence-download="${esc(item.bundle_id)}" title="Download saved JSON even if the current model cannot reproduce it">JSON ↓</button></div></div>`).join('') : '<p class="planning-library-empty">No saved comparisons yet. Compare a response, then save its evidence.</p>';
    } catch (error) { evidenceNotice(`Saved comparisons unavailable: ${error.message}`,true); }
    finally { evidenceBusy=false; updateAvailability(); }
  }
  $('planning-save').addEventListener('click',async () => {
    const bundle=currentBundle(); if (!bundle || busy || evidenceBusy) return;
    evidenceBusy=true; updateAvailability(); evidenceNotice('Verifying and saving the frozen comparison…');
    try {
      const saved=await request('/api/planning/evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(bundle)});
      if (saved.saved !== true || saved.bundle_id !== bundle.bundle_id || saved.verified !== true || saved.scope !== 'historical_reproduction' || saved.execution_authority !== false || saved.origin_authenticated !== false) throw new Error('The save acknowledgement could not be associated with this comparison.');
      savedBundles.add(bundle.bundle_id); evidenceVerification=saved; renderEvidenceContext(); evidenceNotice(`Comparison ${saved.already_saved ? 'already saved' : 'saved'} at ${stamp(saved.stored_at)}. This does not authorize an operational action.`);
    } catch (error) { evidenceNotice(`Could not save comparison: ${error.message}`,true); }
    finally { evidenceBusy=false; updateAvailability(); }
    if (!$('planning-library').hidden) await loadLibrary();
  });
  $('planning-export').addEventListener('click',() => { if (currentBundle()) downloadBundle(currentBundle()); });
  $('planning-library-toggle').addEventListener('click',async () => {
    const open=$('planning-library').hidden; $('planning-library').hidden=!open; $('planning-library-toggle').setAttribute('aria-expanded',String(open));
    if (open) { libraryOffset=0; await loadLibrary(); }
  });
  $('planning-library-refresh').addEventListener('click',loadLibrary);
  $('planning-library-previous').addEventListener('click',() => { libraryOffset=Math.max(0,libraryOffset-20); loadLibrary(); });
  $('planning-library-next').addEventListener('click',() => { libraryOffset+=20; loadLibrary(); });
  $('planning-library-items').addEventListener('click',async event => {
    const button=event.target.closest('button'); if (!button || busy || evidenceBusy) return;
    const id=button.dataset.evidenceOpen || button.dataset.evidenceDownload;
    if (!/^[a-f0-9]{64}$/.test(id || '')) return;
    evidenceBusy=true; updateAvailability(); evidenceNotice(button.dataset.evidenceOpen ? 'Reproducing the saved comparison…' : 'Downloading saved evidence…');
    try {
      const bundle=await request(`/api/planning/evidence/${id}`);
      if (bundle.bundle_id !== id) throw new Error('Saved evidence identifier mismatch.');
      if (button.dataset.evidenceOpen) await openBundle(bundle,id);
      else { downloadBundle(bundle); evidenceNotice('Saved JSON downloaded. Downloading does not establish reproduction under the current model.'); }
    } catch (error) { evidenceNotice(`Evidence could not be opened: ${error.message}. The previous comparison remains unchanged.`,true); }
    finally { evidenceBusy=false; updateAvailability(); }
  });
  $('planning-import').addEventListener('click',() => $('planning-import-file').click());
  $('planning-import-file').addEventListener('change',async event => {
    const file=event.target.files[0]; event.target.value=''; if (!file || busy || evidenceBusy) return;
    evidenceBusy=true; updateAvailability(); evidenceNotice('Checking imported historical evidence…');
    try {
      if (file.size>1024*1024) throw new Error('Evidence files must be no larger than 1 MiB.');
      const contents=await file.text(); await openBundle(JSON.parse(contents),null,contents);
    } catch (error) { evidenceNotice(`Evidence could not be opened: ${error.message}. The previous comparison remains unchanged.`,true); }
    finally { evidenceBusy=false; updateAvailability(); }
  });

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
      let response=await request('/api/planning/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if (viewVersion!==pendingViewVersion || locked()) throw new Error('The shared view changed during comparison. Return to live and compare again.');
      if (response.input?.state_revision!==revision || response.model?.calibrated!==false || response.mutates_live_state!==false || response.physical_effect!==false || !Array.isArray(response.branches) || !response.branches.length) throw new Error('The planning result could not be associated with the requested frozen observation.');
      if (response.evidence_bundle) {
        const enclosed=validHistoricalResult(response.evidence_bundle);
        if (enclosed.plan_id!==response.plan_id || enclosed.input?.state_revision!==revision) throw new Error('Evidence does not match the displayed plan identity.');
        response={...enclosed,evidence_bundle:response.evidence_bundle};
      }
      result=response; historical=false; evidenceVerification=null; inputsChanged=false; $('planning-evidence-notice').textContent=''; renderResults();
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
