/* Aster Park live twin. No client-side scene renderer: every park image comes
 * from NVIDIA OVRTX. DOM overlays carry explicitly synthetic operational data. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const $$ = query => [...document.querySelectorAll(query)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const number = (value, digits = 0) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value).toLocaleString('en-GB', {maximumFractionDigits:digits, minimumFractionDigits:digits}) : '—';
  const title = text => String(text ?? '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
  const time = stamp => stamp ? new Date(stamp).toLocaleTimeString('en-GB', {timeZone:'UTC', hour12:false, hour:'2-digit', minute:'2-digit', second:'2-digit'}) : '—';
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  let snapshot = null, selectedId = 'RIDE_COASTER', assetDetails = null, currentLayer = 'operations';
  let renderer = null, lastStateReceived = 0, lastFrameReceived = 0, liveFrameUrl = null, lastFrameNumber = -1;
  let scenarioPending = false, actionPending = false, detailsSequence = 0, lastDetailFetch = 0;
  let renderedSystems = '', renderedActions = '', renderedAlerts = '', renderedAudit = '';
  let renderControlsInFlight = false, pendingOrbit = null, pendingZoom = 0, lastControlError = 0;
  let timeline = [], timelinePending = false, timelineDragging = false, viewPending = false, viewRequestVersion = 0;
  let frameMetadata = null, lastUniqueFrameAt = 0, displayedFrameIdentity = null;
  let openSourceId = null, sourceSequence = 0, sourcePending = false, connectorPending = false;
  const scenarioAssets = {normal:'RIDE_COASTER', ride_closure:'RIDE_COASTER', show_surge:'SHOW_ARENA', heatwave:'FIRST_AID', power_fault:'POWER_HUB', water_leak:'WATER_PLANT', food_rush:'FOOD_COURT'};
  const actionLabels = {dispatch_maintenance:'Dispatch maintenance', reroute_guests:'Reroute guests', add_staff:'Add qualified staff', shed_load:'Shed flexible load', repair_leak:'Simulate leak repair', replenish_stock:'Replenish stock', reset:'Reset simulation'};
  const systemIcons = {ride_scada:'⌁',ticketing:'⌑',vision:'◎',cmms:'⚒',erp:'▥',workforce:'♧',bms:'ϟ',water:'◈',weather:'☀',gis:'⌘'};

  async function request(path, options = {}, timeout = 9000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, {cache:'no-store', ...options, signal:controller.signal});
      if (!response.ok) {
        let message = `${response.status} ${response.statusText}`;
        try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : body.message || message; } catch (_) { /* Non-JSON upstream error. */ }
        throw new Error(message);
      }
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The service took too long to respond. Please try again.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  const post = (path, payload, timeout) => request(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}, timeout);
  function toast(message, error = false) {
    const item = document.createElement('div');
    item.className = `toast${error ? ' error' : ''}`;
    item.textContent = message;
    $('toasts').append(item);
    while ($('toasts').children.length > 3) $('toasts').firstElementChild.remove();
    setTimeout(() => item.remove(), error ? 8000 : 5500);
  }
  function setText(id, value) { $(id).textContent = value; }
  function assetById(id) { return snapshot?.assets?.find(asset => asset.id === id); }
  const fieldUnknown = (asset, metric) => asset?.data_quality?.fields?.[metric]?.status === 'unknown';
  const fieldModeled = (asset, metric) => snapshot?.read_model?.unmapped_fields_origin === 'synthetic_model' && !asset?.data_quality?.fields?.[metric];
  const assetStatus = asset => fieldUnknown(asset, 'status') ? 'unknown' : asset.status;
  const fieldNumber = (asset, metric, digits = 0) => fieldUnknown(asset, metric) ? '—' : number(metric.split('.').reduce((value,key) => value?.[key], asset), digits);
  const observationValue = observation => observation.quality?.status === 'unknown' || observation.value === null || observation.value === undefined ? '—' : typeof observation.value === 'number' ? number(observation.value, Number.isInteger(observation.value) ? 0 : 1) : typeof observation.value === 'object' ? JSON.stringify(observation.value) : String(observation.value);
  const replaying = () => snapshot?.view?.mode === 'replay';
  const viewKey = data => data?.view?.mode === 'replay' ? `replay:${data.view.snapshot_id}` : 'live';
  const sourceAge = stamp => stamp && Number.isFinite(Date.parse(stamp)) ? Math.max(0, (Date.now() - Date.parse(stamp)) / 1000) : null;
  const ageLabel = seconds => seconds === null || seconds === undefined ? 'age unknown' : seconds < 1 ? 'just received' : seconds < 60 ? `${number(seconds)}s old` : `${number(seconds / 60, 1)}m old`;
  function readOnlyGuard() {
    if (replaying() || viewPending) { toast('Recorded state is read only. Return to live to change the simulation.'); return true; }
    return false;
  }
  function setConnection(online, text) {
    $('data-connection').classList.toggle('offline', !online);
    $('data-connection').querySelector('span').textContent = text;
  }

  function applyState(data) {
    if (!Array.isArray(data.assets) || !data.kpis) throw new Error('The state service returned an unexpected response.');
    const changedView = snapshot && viewKey(data) !== viewKey(snapshot);
    if (snapshot && !changedView && data.view?.mode !== 'replay' && Number.isFinite(data.tick) && data.tick < snapshot.tick && Date.parse(data.timestamp) <= Date.parse(snapshot.timestamp)) return;
    if (changedView) {
      assetDetails = null; detailsSequence++; lastDetailFetch = 0; renderedAlerts = ''; renderedSystems = '';
      $('queue-sparkline').innerHTML = '';
      if ($('comparison-dialog')?.open) $('comparison-dialog').close();
      sourceSequence++;
      if (openSourceId) setTimeout(() => showSystem(openSourceId), 0);
    }
    snapshot = data;
    lastStateReceived = Date.now();
    setConnection(true, replaying() ? `Recorded state · tick ${data.tick ?? '—'}` : `Synthetic services live · tick ${data.tick ?? '—'}`);
    $('data-connection').classList.toggle('degraded', !replaying() && data.read_model?.quality_status === 'degraded');
    if (!replaying() && data.read_model?.quality_status === 'degraded') setConnection(true, `Live model · source quality degraded · tick ${data.tick ?? '—'}`);
    const k = data.kpis;
    setText('kpi-attendance', number(k.attendance));
    setText('kpi-wait', data.assets.some(asset => fieldUnknown(asset,'queue_minutes')) ? '—' : number(k.average_wait_minutes, 1));
    setText('kpi-rides', `${data.assets.some(asset => asset.type === 'ride' && fieldUnknown(asset,'status')) ? '—' : number(k.open_rides)} / ${data.assets.filter(asset => asset.type === 'ride').length}`);
    setText('kpi-power', data.assets.some(asset => fieldUnknown(asset,'power_kw')) ? '—' : number(k.power_kw));
    setText('kpi-water', data.assets.some(asset => fieldUnknown(asset,'water_lpm')) ? '—' : number(k.water_lpm));
    setText('kpi-alerts', number(k.active_alerts));
    $('kpi-alerts').closest('.kpi').classList.toggle('attention', k.active_alerts > 0);
    setText('alert-note', k.active_alerts ? 'Review operational response' : 'No active simulation alerts');
    setText('power-note', k.power_capacity_kw ? `${number(k.power_capacity_kw)} kW available capacity` : 'Park-wide energy meter');
    if (data.weather) setText('weather-label', `${number(data.weather.temperature_c, 1)}°C · ${title(data.weather.condition)} · Synthetic weather`);
    setText('system-count', data.systems?.length ?? '—');
    const scene = data.scenarios?.find(scenario => scenario.id === data.scenario);
    setText('scenario-current', (scene?.label ?? title(data.scenario)).toUpperCase());
    $$('.scenario-chip').forEach(button => {
      button.classList.toggle('active', button.dataset.scenario === data.scenario);
      button.setAttribute('aria-pressed', String(button.dataset.scenario === data.scenario));
      const info = data.scenarios?.find(scenario => scenario.id === button.dataset.scenario);
      if (info) button.title = info.description;
    });
    const options = data.assets.map(asset => `<option value="${esc(asset.id)}">${esc(asset.name)}</option>`).join('');
    if ($('asset-select').dataset.options !== options) { $('asset-select').innerHTML = options; $('asset-select').dataset.options = options; }
    if (!assetById(selectedId)) selectedId = data.assets[0]?.id;
    $('asset-select').value = selectedId ?? '';
    renderAsset(); renderBrief(); renderSystems(); renderActivity(); renderLabels(); renderView(); renderTimeline(); renderSourceHealth();
    updateWriteControls(); updateFrameContext();
    if (Date.now() - lastDetailFetch > 5000) refreshDetails();
  }

  async function pollState() {
    while (true) {
      if (!document.hidden && !viewPending) {
        const version = viewRequestVersion;
        try { const data = await request('/api/view/state'); if (version === viewRequestVersion && !viewPending) applyState(data); }
        catch (_) { setConnection(false, snapshot ? `Data connection lost · last ${time(snapshot.timestamp)} UTC` : 'Synthetic services unavailable · retrying'); }
      }
      await sleep(1000);
    }
  }

  function updateWriteControls() {
    const locked = replaying() || viewPending;
    $$('.scenario-chip').forEach(button => button.disabled = locked || scenarioPending);
    $$('[data-action]').forEach(button => button.disabled = locked || actionPending);
    $$('[data-connector-mode]').forEach(button => button.disabled = locked || connectorPending);
    $('compare-scenarios').disabled = locked;
    $('compare-scenarios').title = locked ? 'Return to live to compare hypothetical scenarios' : 'Compare a hypothetical scenario without changing live state';
    $('return-live').disabled = viewPending;
    $('timeline-live').disabled = viewPending;
    $$('.actions-section > .action-note').forEach(note => { note.textContent = locked ? 'Recorded state is read only. Return to live to take an action.' : 'Actions update synthetic services and the audit trail.'; });
  }

  function renderView() {
    const view = snapshot?.view || {mode:'live'};
    $('replay-banner').hidden = !replaying();
    document.body.classList.toggle('replay-mode', replaying());
    $('timeline-live').classList.toggle('is-live', !replaying());
    setText('timeline-live', replaying() ? 'Return live' : '● Live');
    if (!replaying()) return;
    setText('replay-title', `Recorded state · ${time(view.captured_at)} UTC · read only`);
    setText('replay-description', `Snapshot #${view.snapshot_id} · source ${time(view.source_timestamp || snapshot.timestamp)} UTC. The live simulation continues recording. This view is shared by all clients.`);
    const geometry = view.scene_matches_current === false ? 'Scene revision differs from the current model. ' : '';
    const pose = view.recorded_motion ? 'Ride poses were captured with this record; camera navigation remains available.' : 'No captured ride pose for this record. Historical data is available; the displayed ride pose is not historical evidence.';
    setText('replay-pose-note', geometry + pose);
  }

  function renderTimeline() {
    const slider = $('timeline-range');
    if (!timeline.length) { slider.disabled = true; return; }
    slider.disabled = viewPending;
    slider.max = String(timeline.length - 1);
    if (!timelineDragging) {
      const index = replaying() ? timeline.findIndex(record => String(record.id) === String(snapshot.view.snapshot_id)) : timeline.length - 1;
      slider.value = String(Math.max(0, index));
    }
    setText('timeline-first', `${time(timeline[0].captured_at)} UTC`);
    setText('timeline-last', `${time(timeline[timeline.length - 1].captured_at)} UTC`);
    renderTimelineSelection();
  }

  function renderTimelineSelection() {
    const index = Number($('timeline-range').value), record = timeline[index];
    if (!record) return;
    setText('timeline-selection', `${timelineDragging ? 'Preview' : replaying() ? 'Recorded' : 'Latest record'} · ${time(record.captured_at)} UTC · ${title(record.scenario)}`);
    setText('timeline-detail', `Record #${record.id} · tick ${record.tick} · ${record.has_recorded_motion ? 'captured ride pose' : 'ride pose not recorded'} · shared session`);
    $('timeline-previous').disabled = viewPending || index <= 0;
    $('timeline-next').disabled = viewPending || index >= timeline.length - 1;
  }

  async function refreshTimeline() {
    if (timelinePending || document.hidden || timelineDragging) return;
    timelinePending = true;
    try {
      const result = await request('/api/timeline?limit=300');
      timeline = [...(result.snapshots || [])];
      if (replaying() && !timeline.some(record => String(record.id) === String(snapshot.view.snapshot_id))) {
        timeline.push({id:snapshot.view.snapshot_id,captured_at:snapshot.view.captured_at,source_timestamp:snapshot.view.source_timestamp,tick:snapshot.tick,scenario:snapshot.scenario,has_recorded_motion:!!snapshot.view.recorded_motion});
      }
      timeline.sort((a, b) => Number(a.id) - Number(b.id));
      setText('timeline-recording', result.recording_error ? 'Recording interrupted · history retained' : `${timeline.length} records · every ${number(result.recording_interval_seconds || 1)}s`);
      $('timeline-recording').title = result.recording_error ? String(result.recording_error) : 'Live state continues recording while a historical record is inspected';
      renderTimeline();
    } catch (_) { setText('timeline-recording', 'Recording history unavailable'); }
    finally { timelinePending = false; }
  }

  async function switchView(mode, snapshotId) {
    if (viewPending) return;
    viewPending = true; viewRequestVersion++; updateWriteControls();
    try {
      const data = await post('/api/view', mode === 'replay' ? {mode, snapshot_id:Number(snapshotId)} : {mode:'live'});
      applyState(data); await refreshTimeline();
      toast(mode === 'replay' ? `Viewing recorded snapshot #${snapshotId}. Operational controls are read only.` : 'Returned to the live park.');
    } catch (error) { toast(`View could not be changed: ${error.message}`, true); }
    finally { viewPending = false; updateWriteControls(); renderTimeline(); }
  }

  function availableActions(asset) {
    const actions = [];
    if (['ride','utility','facility'].includes(asset.type)) actions.push('dispatch_maintenance');
    if (['ride','entertainment','admission','food'].includes(asset.type)) actions.push('reroute_guests');
    if (asset.staff?.required > 0) actions.push('add_staff');
    if (['POWER_HUB','HOTEL','PARKING','FOOD_COURT'].includes(asset.id)) actions.push('shed_load');
    if (asset.id === 'WATER_PLANT') actions.unshift('repair_leak');
    if (asset.id === 'FOOD_COURT') actions.unshift('replenish_stock');
    return actions;
  }

  function renderAsset() {
    const asset = assetById(selectedId);
    $('asset-empty').hidden = !!asset;
    $('asset-content').hidden = !asset;
    if (!asset) return;
    setText('asset-type', `${title(asset.type).toUpperCase()} / CONNECTED ASSET`);
    setText('asset-name', asset.name);
    const statusQuality = asset.data_quality?.fields?.status?.status;
    setText('asset-status', `${assetStatus(asset)}${fieldModeled(asset,'status') ? ' · modeled' : ['stale','uncertain'].includes(statusQuality) ? ` · ${statusQuality}` : ''}`);
    $('asset-status').className = `status-badge ${esc(assetStatus(asset))} ${['stale','uncertain'].includes(statusQuality) ? statusQuality : ''}`;
    setText('asset-description', asset.description);
    setText('asset-id', asset.id);
    setText('asset-queue', asset.type === 'utility' || asset.type === 'sensor' ? '—' : fieldNumber(asset,'queue_minutes',1));
    setText('asset-occupancy', asset.type === 'utility' || asset.type === 'sensor' ? '—' : `${fieldNumber(asset,'occupancy')} / ${fieldNumber(asset,'capacity')}`);
    $('asset-occupancy').style.fontSize = asset.capacity >= 100 ? '18px' : '';
    $('occupancy-meter').style.width = `${Math.max(0, Math.min(100, asset.capacity && !fieldUnknown(asset,'occupancy') && !fieldUnknown(asset,'capacity') ? asset.occupancy / asset.capacity * 100 : 0))}%`;
    setText('asset-power', fieldNumber(asset,'power_kw',1));
    setText('asset-health', fieldNumber(asset,'maintenance.health_pct'));
    setText('asset-staff', `${fieldNumber(asset,'staff.on_duty')} on duty / ${fieldNumber(asset,'staff.required')} needed`);
    setText('asset-water', `${fieldNumber(asset,'water_lpm',1)} L/min`);
    setText('asset-inspection', fieldUnknown(asset,'maintenance.inspection_status') ? 'Unknown' : title(asset.maintenance?.inspection_status));
    setText('asset-orders', fieldNumber(asset,'maintenance.open_work_orders'));
    setText('asset-stock', asset.type === 'food' ? `${fieldNumber(asset,'erp.stock_units')} units` : '—');
    setText('asset-scene-path', asset.scene_path);
    setText('asset-updated', `${replaying() ? 'Recorded' : 'Synthetic'} API → registry → USD · ${time(snapshot.timestamp)} UTC`);
    $('asset-staff').title = (asset.staff?.qualifications || []).map(title).join(', ');
    const deps = (asset.dependencies || []).map(id => `<button class="dependency-chip" data-asset="${esc(id)}" title="Inspect dependency">${esc(assetById(id)?.name || id)}</button>`).join('');
    if ($('asset-dependencies').innerHTML !== deps) $('asset-dependencies').innerHTML = deps;
    const actions = availableActions(asset);
    const signature = `${selectedId}:${actions.join(',')}`;
    if (renderedActions !== signature) {
      $('asset-actions').innerHTML = actions.map(action => `<button class="asset-action" data-action="${action}" data-asset="${esc(asset.id)}">${esc(actionLabels[action])}</button>`).join('');
      if (!actions.length) $('asset-actions').innerHTML = '<span class="action-note">Read-only sensor. No operational actions available.</span>';
      renderedActions = signature;
    }
    $$('#asset-actions button').forEach(button => button.disabled = actionPending || replaying() || viewPending);
    const metricFields = ['queue_minutes', 'occupancy', 'power_kw', 'maintenance.health_pct'];
    $$('.asset-metrics>div').forEach((element, index) => {
      const field = asset.data_quality?.fields?.[metricFields[index]];
      element.classList.toggle('metric-stale', ['stale','uncertain','unknown'].includes(field?.status));
      let badge = element.querySelector('.metric-quality');
      if (!badge) { badge = document.createElement('span'); badge.className = 'metric-quality'; element.append(badge); }
      badge.hidden = field?.status === 'good' || (!field && !fieldModeled(asset,metricFields[index]));
      badge.textContent = field ? title(field.status) : fieldModeled(asset,metricFields[index]) ? 'Modeled' : '';
      element.title = field ? `${title(field.status)} · ${field.source_id} · source ${time(field.source_timestamp)} UTC · ${ageLabel(field.age_seconds)}${field.reasons?.length ? ` · ${field.reasons.join(', ')}` : ''}` : fieldModeled(asset,metricFields[index]) ? 'Synthetic model value · no mapped accepted observation' : '';
    });
    const sources = (snapshot.systems || []).filter(source => source.asset_ids?.includes(asset.id));
    $('asset-sources').innerHTML = sources.length ? `<span class="section-label">${replaying() ? 'RECORDED SOURCE QUALITY' : 'SOURCE QUALITY'}</span><div>${sources.map(source => `<button data-system="${esc(source.id)}" class="asset-source ${esc(sourceStatus(source))}" title="Inspect source provenance"><i></i>${esc(source.name.replace(/^Simulated /,''))}</button>`).join('')}</div>` : '';
    const modeled = {status:'operating status',queue_minutes:'queue',occupancy:'occupancy',capacity:'capacity',power_kw:'power','maintenance.health_pct':'asset health','staff.on_duty':'staff on duty','staff.required':'required staff',water_lpm:'water flow','maintenance.inspection_status':'inspection','maintenance.open_work_orders':'work orders','erp.stock_units':'inventory',dependencies:'dependencies'};
    const modeledLabels = Object.entries(modeled).filter(([field]) => fieldModeled(asset,field)).map(([,label]) => label);
    if (modeledLabels.length) $('asset-sources').innerHTML += `<p class="modeled-fields"><strong>Model-derived:</strong> ${esc(modeledLabels.join(', '))}. These fields have no mapped accepted observation.</p>`;
    renderOrders(); renderDependencyContext();
  }

  function renderOrders() {
    let section = $('work-orders-detail');
    const orders = assetDetails?.id === selectedId ? assetDetails.work_orders || [] : [];
    const unavailable = replaying() && assetDetails?.view?.work_orders_recorded === false;
    if (!section && (orders.length || unavailable)) {
      section = document.createElement('div');
      section.id = 'work-orders-detail';
      section.className = 'work-orders-detail';
      $('asset-actions').after(section);
    }
    if (section) {
      section.hidden = !orders.length && !unavailable;
      section.innerHTML = unavailable ? '<p class="action-note">Detailed work orders were not captured with this record. The displayed count is the recorded CMMS observation.</p>' : orders.slice(0, 3).map(order => `<div class="work-order"><span>WO #${esc(order.id)} · ${esc(title(order.status))}</span><small>${esc(order.title)}</small></div>`).join('');
    }
  }

  async function refreshDetails() {
    if (!selectedId) return;
    const id = selectedId, sequence = ++detailsSequence;
    lastDetailFetch = Date.now();
    try {
      const [detail, history] = await Promise.all([request(`/api/view/assets/${encodeURIComponent(id)}`), request(`/api/view/assets/${encodeURIComponent(id)}/history?limit=90`)]);
      if (selectedId !== id || sequence !== detailsSequence) return;
      assetDetails = detail;
      drawSparkline(history.history || detail.history || []);
      renderOrders();
    } catch (_) { /* Live state remains useful when historical data is temporarily unavailable. */ }
  }

  function drawSparkline(history) {
    const values = history.map(sample => Number(sample.queue_minutes)).filter(Number.isFinite);
    if (values.length < 2) { $('queue-sparkline').innerHTML = ''; return; }
    const low = Math.min(...values), high = Math.max(...values), span = Math.max(high - low, 2);
    const points = values.map((value, index) => `${(index / (values.length - 1) * 108 + 1).toFixed(1)},${(22 - (value - low) / span * 19).toFixed(1)}`).join(' ');
    $('queue-sparkline').innerHTML = `<polyline points="${points}" fill="none" stroke="#7b9d60" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`;
  }

  async function selectAsset(id, focus = false, tellRenderer = true) {
    if (!assetById(id)) return;
    selectedId = id; assetDetails = null; renderedActions = ''; detailsSequence++;
    $('asset-select').value = id;
    $('queue-sparkline').innerHTML = '';
    renderAsset(); renderLabels(); refreshDetails();
    if (tellRenderer) await control({action:focus ? 'focus' : 'select', asset_id:id}, false);
  }

  function alertProvenance(alert) {
    const origin = {canonical_rule:'Operational rule',synthetic_model:'Synthetic model estimate',model_source_conflict:'Source / model conflict'}[alert.origin] || 'Synthetic alert';
    const evidence = (alert.evidence || []).map(row => row.origin === 'accepted_observation' ? `${title(row.metric)}: ${row.source_id} · ${row.quality || 'quality unknown'}` : `${title(row.metric || 'model')}: modeled`);
    return `${origin}${evidence.length ? ' · ' + evidence.join('; ') : ''}`;
  }

  function renderBrief() {
    const alerts = snapshot.alerts || [];
    const signature = JSON.stringify([snapshot.scenario, alerts, snapshot.read_model?.quality_status, viewKey(snapshot)]);
    if (signature === renderedAlerts) return;
    renderedAlerts = signature;
    if (!alerts.length) {
      const normal = snapshot.scenario === 'normal';
      if (snapshot.read_model?.quality_status === 'degraded') {
        $('operations-brief').innerHTML = '<h3>Source quality needs attention.</h3><p>No operational alert is available for this view. Inspect paused, stale or unknown sources before interpreting the displayed operating state.</p>';
        $('alert-actions').innerHTML = '<button class="brief-action secondary" data-show-dependencies>Trace dependencies ↗</button>';
        return;
      }
      $('operations-brief').innerHTML = `<h3>${replaying() ? 'No operational alerts were recorded at this moment.' : normal ? 'The park is running within its operating plan.' : 'The simulated response is taking effect.'}</h3><p>${replaying() ? 'Inspect the recorded asset context, source quality and logical dependencies. Operational actions are disabled until you return to live.' : normal ? 'Both attractions are available. Explore an asset in the twin, or introduce a disruption to see its effect on queues, utilities and connected services.' : 'No active alerts remain in this scenario. Inspect telemetry and the activity trail to review what changed, or reset the simulation.'}</p>`;
      $('alert-actions').innerHTML = normal ? '' : '<button class="brief-action" data-action="reset">Reset simulation ↗</button>';
      return;
    }
    $('operations-brief').innerHTML = alerts.slice(0, 3).map(alert => `<div class="brief-alert"><h3><span class="alert-severity ${esc(alert.severity)}"></span>${esc(alert.title)} ${assetById(alert.asset_id) ? `<button class="inspect-alert" data-asset="${esc(alert.asset_id)}">Inspect ↗</button>` : ''}</h3><p>${esc(alert.message)}</p><small class="alert-provenance">${esc(alertProvenance(alert))}</small></div>`).join('');
    const seen = new Set();
    $('alert-actions').innerHTML = alerts.filter(alert => {
      const signature = `${alert.recommended_action}:${alert.asset_id}`;
      if (!alert.recommended_action || seen.has(signature)) return false;
      seen.add(signature); return true;
    }).map(alert => `<button class="brief-action" data-action="${esc(alert.recommended_action)}" data-asset="${esc(alert.asset_id)}">${esc(actionLabels[alert.recommended_action] || title(alert.recommended_action))} ↗</button>`).join('') + '<button class="brief-action secondary" data-show-dependencies>Trace dependencies ↗</button><button class="brief-action secondary" data-action="reset">Reset</button>';
  }

  function sourceStatus(system) { return system.health?.status || (system.status === 'connected' ? 'healthy' : system.status || 'unknown'); }

  function renderSourceHealth() {
    const systems = snapshot?.systems || [];
    const healthy = systems.filter(source => sourceStatus(source) === 'healthy').length;
    const stale = systems.filter(source => ['stale','paused','degraded'].includes(sourceStatus(source))).length;
    const unavailable = systems.length - healthy - stale;
    $('source-health-summary').innerHTML = `<span><i class="source-health-dot healthy"></i>${healthy} healthy</span><span><i class="source-health-dot stale"></i>${stale} paused / stale</span><span><i class="source-health-dot offline"></i>${unavailable} unavailable / unknown</span><small>${replaying() ? 'Recorded source quality · ages measured at capture' : 'Accepted observations + labeled model values · click a source for freshness'}</small>`;
  }

  function renderSystems() {
    const systems = snapshot.systems || [];
    const signature = JSON.stringify(systems.map(system => [system.id, system.name, system.protocol, sourceStatus(system), system.health?.mode, system.asset_ids]));
    if (signature !== renderedSystems) {
      renderedSystems = signature;
      $('system-cards').innerHTML = systems.map(system => `<button class="system-card ${esc(sourceStatus(system))}" data-system="${esc(system.id)}" title="Inspect synthetic ${esc(system.name)} feed"><span class="system-dot ${esc(sourceStatus(system))}"></span><span class="system-icon">${systemIcons[system.id] || '⌘'}</span><h3>${esc(system.name)}</h3><div class="system-meta"><span class="system-protocol" title="Intended production interface: ${esc(system.protocol)}">${esc(system.protocol)}</span><span>${system.asset_ids?.length || 0} assets</span></div><div class="system-source"><strong>${esc(title(sourceStatus(system)))}</strong> · ${system.health?.mode === 'paused' ? 'INGESTION PAUSED' : system.health?.mode === 'offline' ? 'SIMULATED OFFLINE' : 'SYNTHETIC ADAPTER'}</div></button>`).join('');
      $('architecture-sources').innerHTML = systems.map(system => `<div class="architecture-source"><strong>${esc(system.name)}</strong><small>${esc(system.protocol)} · ${system.asset_ids?.length || 0} assets</small></div>`).join('');
    }
  }

  function renderActivity() {
    const events = snapshot.recent_actions || [];
    const signature = JSON.stringify(events);
    if (signature === renderedAudit) return;
    renderedAudit = signature;
    $('activity-list').innerHTML = events.length ? events.slice(0, 12).map(event => `<div class="activity-item"><span class="activity-icon">${event.action === 'scenario' ? '↳' : '✓'}</span><span class="activity-message">${esc(event.message || title(event.action))}${event.asset_id ? `<small>${esc(assetById(event.asset_id)?.name || event.asset_id)} · ${esc(title(event.action))}</small>` : ''}</span><time datetime="${esc(event.timestamp)}">${time(event.timestamp)} UTC</time></div>`).join('') : '<div class="empty-activity">Run a scenario or take an action to begin the audit trail.</div>';
  }

  async function runScenario(scenario) {
    if (readOnlyGuard()) return;
    if (scenarioPending || !scenarioAssets[scenario]) return;
    scenarioPending = true;
    $$('.scenario-chip').forEach(button => button.disabled = true);
    try {
      await post('/api/scenarios', {scenario});
      applyState(await request('/api/view/state'));
      await selectAsset(scenarioAssets[scenario]);
      toast(`${snapshot.scenarios?.find(item => item.id === scenario)?.label || title(scenario)} is now running. All effects are simulated.`);
    } catch (error) { toast(`Scenario could not be applied: ${error.message}`, true); }
    finally { scenarioPending = false; updateWriteControls(); }
  }

  async function runAction(action, assetId) {
    if (readOnlyGuard()) return;
    if (actionPending) return;
    actionPending = true;
    $$('[data-action]').forEach(button => button.disabled = true);
    try {
      const body = {action};
      if (assetId && action !== 'reset') body.asset_id = assetId;
      const response = await post('/api/actions', body);
      applyState(await request('/api/view/state'));
      toast(response.result.message || 'Simulated action applied.');
      refreshDetails();
    } catch (error) { toast(`Action could not be applied: ${error.message}`, true); }
    finally { actionPending = false; updateWriteControls(); }
  }

  async function showSystem(id) {
    const system = snapshot?.systems?.find(source => source.id === id);
    if (!system) return;
    let dialog = $('system-dialog');
    if (!dialog) {
      dialog = document.createElement('dialog'); dialog.id = 'system-dialog'; document.body.append(dialog);
      dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
      dialog.addEventListener('close', () => { openSourceId = null; sourceSequence++; });
    }
    openSourceId = id; sourceSequence++;
    dialog.innerHTML = `<div class="dialog-heading"><div><div class="eyebrow">${replaying() ? 'RECORDED SOURCE PROVENANCE' : 'SYNTHETIC SOURCE / DATA QUALITY'}</div><h2>${esc(system.name)}</h2></div><button class="icon-button close-system" aria-label="Close source detail">×</button></div><p class="dialog-intro">Intended production protocol: <strong>${esc(system.protocol)}</strong>. ${replaying() ? 'This inspector uses only captured source health and accepted asset fields. No live source payload is fetched.' : 'Only accepted observations update the shared park model. Pause ingestion or simulate a lost connection to inspect how data becomes stale.'}</p><div id="source-health-detail" class="source-health-detail"></div><div class="connector-controls"><span>${replaying() ? 'RECORDED VIEW · READ ONLY' : 'SIMULATE CONNECTOR CONDITION'}</span><div><button data-connector-mode="live">Live ingestion</button><button data-connector-mode="paused">Pause ingestion</button><button data-connector-mode="offline">Simulate offline</button></div></div><div class="source-context"><span class="tiny-badge">${system.asset_ids?.length || 0} CONNECTED ASSETS</span><code>${replaying() ? `Recorded snapshot #${snapshot.view.snapshot_id}` : `GET /api/observations?source_id=${esc(id)}`}</code></div><div class="source-assets">${(system.asset_ids || []).map(assetId => `<button class="dependency-chip" data-source-asset="${esc(assetId)}">${esc(assetById(assetId)?.name || assetId)}</button>`).join('')}</div><div class="source-tabs"><button class="active" data-source-tab="observations">Accepted fields & provenance</button><button data-source-tab="raw">Raw payload</button></div><div id="source-observations" class="observation-table-wrap">Loading accepted observations…</div><div class="source-feed" id="source-feed" hidden><pre></pre></div><p class="source-footnote" id="source-footnote"></p>`;
    dialog.querySelector('.close-system').onclick = () => dialog.close();
    dialog.querySelectorAll('[data-source-asset]').forEach(button => button.onclick = () => { selectAsset(button.dataset.sourceAsset, true); dialog.close(); $('operations-view').scrollIntoView({behavior:'smooth', block:'start'}); });
    dialog.querySelectorAll('[data-connector-mode]').forEach(button => button.onclick = () => setConnectorMode(id, button.dataset.connectorMode));
    dialog.querySelectorAll('[data-source-tab]').forEach(button => button.onclick = () => {
      dialog.querySelectorAll('[data-source-tab]').forEach(tab => tab.classList.toggle('active', tab === button));
      $('source-feed').hidden = button.dataset.sourceTab !== 'raw'; $('source-observations').hidden = button.dataset.sourceTab !== 'observations';
    });
    if (!dialog.open) dialog.showModal();
    updateWriteControls(); await refreshSource();
  }

  async function refreshSource() {
    const id = openSourceId, system = snapshot?.systems?.find(item => item.id === id);
    if (!id || !system || !$('system-dialog')?.open || sourcePending || document.hidden) return;
    const sequence = sourceSequence, mode = viewKey(snapshot);
    sourcePending = true;
    try {
      let health, observations, payload;
      if (replaying()) {
        health = system.health || {status:sourceStatus(system), mode:'unknown'};
        observations = (snapshot.assets || []).flatMap(asset => Object.entries(asset.data_quality?.fields || {}).filter(([,field]) => field.source_id === id).map(([metric,field]) => ({
          source_id:id,asset_id:asset.id,metric,value:field.status === 'unknown' ? null : metric.split('.').reduce((value,key) => value?.[key],asset),unit:field.unit,
          source_timestamp:field.source_timestamp,ingested_at:field.ingested_at,quality:field,authoritative:true,
          provenance:{adapter:'captured accepted field',synthetic:true,transport:'recorded snapshot'}
        })));
        payload = {view:snapshot.view, source:system, accepted_fields:observations, note:'Captured accepted fields only; original raw connector responses are not reconstructed.'};
      } else {
        const result = await Promise.all([request(`/api/connectors/${encodeURIComponent(id)}/health`), request(`/api/observations?source_id=${encodeURIComponent(id)}`)]);
        health = result[0]; observations = result[1].observations || []; payload = {health, ...result[1]};
      }
      if (openSourceId !== id || sequence !== sourceSequence || mode !== viewKey(snapshot) || !$('system-dialog')?.open) return;
      const status = health.status || 'unknown';
      $('source-health-detail').innerHTML = `<div><label>SOURCE HEALTH</label><strong class="quality-tag ${esc(status)}" id="source-health-status">${esc(title(status))}</strong></div><div><label>SOURCE OBSERVED</label><strong>${time(health.last_source_timestamp || system.source_timestamp)}<small>UTC</small></strong></div><div><label>LAST INGESTED</label><strong>${time(health.last_ingested_at || system.last_sync)}<small>UTC</small></strong></div><div><label>OLDEST FIELD</label><strong>${esc(ageLabel(health.freshness?.max_age_seconds))}</strong><small>Stale after ${number(health.freshness?.stale_after_seconds)}s</small></div>`;
      $$('[data-connector-mode]').forEach(button => button.classList.toggle('active', button.dataset.connectorMode === health.mode));
      const records = [...observations].sort((a,b) => Number(b.authoritative) - Number(a.authoritative)).slice(0, 120);
      $('source-observations').innerHTML = records.length ? `<table class="observation-table"><thead><tr><th>Asset / field</th><th>Source value</th><th>Quality / age</th><th>Provenance</th></tr></thead><tbody>${records.map(observation => `<tr><td><strong>${esc(assetById(observation.asset_id)?.name || observation.asset_id)}</strong><code>${esc(observation.metric)}</code></td><td>${esc(observationValue(observation))}<small>${esc(observation.unit || '')}</small></td><td><span class="quality-tag ${esc(observation.quality?.status || 'unknown')}">${esc(title(observation.quality?.status || 'unknown'))}</span><small>${esc(ageLabel(observation.quality?.age_seconds))} · ${time(observation.source_timestamp)} UTC</small>${observation.quality?.reasons?.length ? `<small>${esc(observation.quality.reasons.join(', '))}</small>` : ''}</td><td>${esc(observation.provenance?.adapter || 'unknown adapter')}<small>${observation.quality?.status === 'unknown' ? 'No accepted observation' : observation.authoritative ? 'Projects into twin' : 'Informational source'} · ${esc(observation.provenance?.transport || 'unknown transport')}</small></td></tr>`).join('')}</tbody></table>` : '<div class="empty-activity">No accepted observations from this source.</div>';
      $('source-feed').querySelector('pre').textContent = JSON.stringify(payload, null, 2);
      setText('source-footnote', replaying() ? `Recorded snapshot #${snapshot.view.snapshot_id}. Quality ages are those captured with the record. Live connector controls are disabled.` : `${number(observations.length)} normalized observations. ${health.last_error ? `Last error: ${health.last_error}` : 'Synthetic adapter; no physical equipment connection.'} Pausing preserves accepted values while their age increases.`);
      updateWriteControls();
    } catch (error) {
      if (openSourceId === id && sequence === sourceSequence && $('source-footnote')) setText('source-footnote', `Source inspection unavailable: ${error.message}`);
    } finally { sourcePending = false; }
  }

  async function setConnectorMode(id, mode) {
    if (readOnlyGuard() || connectorPending) return;
    connectorPending = true; updateWriteControls();
    try {
      await post(`/api/connectors/${encodeURIComponent(id)}/simulation`, {mode});
      applyState(await request('/api/view/state'));
      toast(mode === 'live' ? 'Synthetic ingestion resumed.' : mode === 'paused' ? 'Synthetic ingestion paused. Accepted values will age into stale quality.' : 'Connector is now simulated offline. Last accepted values remain identifiable.');
      await refreshSource();
    } catch (error) { toast(`Connector condition could not be changed: ${error.message}`, true); }
    finally { connectorPending = false; updateWriteControls(); }
  }

  async function showComparison(scenario = 'ride_closure') {
    if (readOnlyGuard()) return;
    if (!snapshot) { toast('Connect to the synthetic services before comparing scenarios.'); return; }
    let dialog = $('comparison-dialog');
    if (!dialog) {
      dialog = document.createElement('dialog'); dialog.id = 'comparison-dialog'; document.body.append(dialog);
      dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    }
    dialog.innerHTML = `<div class="dialog-heading"><div><div class="eyebrow">SCENARIO LAB / READ-ONLY COMPARISON</div><h2>Explore the impact before you act.</h2></div><button class="icon-button close-comparison" aria-label="Close comparison">×</button></div><p class="dialog-intro">Synthetic model estimate · same time · no live changes. The comparison uses the simulator baseline; injected connector observations are not inputs to this scenario model.</p><div class="comparison-controls"><label>HYPOTHETICAL SCENARIO<select id="comparison-scenario">${(snapshot.scenarios || []).map(item => `<option value="${esc(item.id)}"${item.id === scenario ? ' selected' : ''}>${esc(item.label)}</option>`).join('')}</select></label><span class="tiny-badge">MODEL BASELINE: ${esc(title(snapshot.scenario)).toUpperCase()}</span></div><div id="comparison-result" class="comparison-result">Evaluating the synthetic scenario…</div>`;
    dialog.querySelector('.close-comparison').onclick = () => dialog.close();
    $('comparison-scenario').onchange = event => showComparison(event.target.value);
    if (!dialog.open) dialog.showModal();
    try {
      const comparison = await request(`/api/scenarios/compare?scenario=${encodeURIComponent(scenario)}`);
      if (!dialog.open || $('comparison-scenario').value !== scenario) return;
      $('comparison-result').innerHTML = `<div class="comparison-table-wrap"><table class="comparison-table"><thead><tr><th>Operating measure</th><th>Model baseline</th><th>Hypothetical</th><th>Change</th></tr></thead><tbody>${comparison.deltas.map(metric => `<tr><td>${esc(metric.label)}<small>${esc(metric.unit)}</small></td><td>${number(metric.before, metric.unit === 'min' ? 1 : 0)}</td><td>${number(metric.after, metric.unit === 'min' ? 1 : 0)}</td><td><span class="delta-chip${metric.delta !== 0 ? ' changed' : ''}">${metric.delta > 0 ? '+' : ''}${number(metric.delta, metric.unit === 'min' ? 1 : 0)}</span></td></tr>`).join('')}</tbody></table></div>${comparison.asset_changes?.length ? `<div class="comparison-assets"><div class="section-label">AFFECTED ASSETS</div>${comparison.asset_changes.slice(0, 8).map(asset => `<span class="comparison-asset"><strong>${esc(asset.name)}</strong><small>${esc(title(asset.before_status))} → ${esc(title(asset.after_status))}</small></span>`).join('')}</div>` : ''}<div class="comparison-assumptions"><strong>Model assumptions</strong><ul>${(comparison.assumptions || []).map(assumption => `<li>${esc(assumption)}</li>`).join('')}</ul></div><div class="comparison-footer"><span>Same-tick heuristic · baseline tick ${number(comparison.baseline_tick)}<br>Uncalibrated demonstration estimates; no real-world savings claim.</span><button class="asset-action apply-comparison">Run this scenario ↗</button></div>`;
      dialog.querySelector('.apply-comparison').onclick = () => { dialog.close(); runScenario(scenario); };
    } catch (error) { if (dialog.open && $('comparison-scenario')?.value === scenario) $('comparison-result').textContent = `Comparison unavailable: ${error.message}`; }
  }

  // The renderer publishes normalized positions in the image, not the browser.
  // Both annotations and picking use the same letterbox-aware image rectangle.
  function imageRect() {
    const viewport = $('viewport'), width = viewport.clientWidth, height = viewport.clientHeight;
    const ratio = frameMetadata?.context ? frameMetadata.context.width / frameMetadata.context.height : ($('render-frame').naturalWidth || 1280) / ($('render-frame').naturalHeight || 720);
    const imageWidth = Math.min(width, height * ratio), imageHeight = imageWidth / ratio;
    return {x:(width - imageWidth) / 2, y:(height - imageHeight) / 2, width:imageWidth, height:imageHeight};
  }

  function frameMatchesView() {
    if (!frameMetadata || !snapshot || !frameMetadata.context) return false;
    if (!frameMetadata.sourceRevision || !snapshot.accepted_state_revision || frameMetadata.sourceRevision !== snapshot.accepted_state_revision) return false;
    if (replaying()) return frameMetadata.viewMode === 'replay' && String(frameMetadata.snapshotId) === String(snapshot.view.snapshot_id);
    return frameMetadata.viewMode === 'live';
  }

  function pickViewUnchanged(requestedView, requestedVersion) {
    return viewKey(snapshot) === requestedView && viewRequestVersion === requestedVersion;
  }

  function dependencyEdges() {
    if (!snapshot) return [];
    const all = snapshot.assets.flatMap(asset => (fieldUnknown(asset,'dependencies') ? [] : asset.dependencies || []).filter(id => assetById(id)).map(id => ({from:id,to:asset.id})));
    const upstream = new Set([selectedId]), downstream = new Set([selectedId]);
    for (let iteration = 0; iteration < snapshot.assets.length; iteration++) {
      for (const edge of all) {
        if (upstream.has(edge.to)) upstream.add(edge.from);
        if (downstream.has(edge.from)) downstream.add(edge.to);
      }
    }
    return all.filter(edge => upstream.has(edge.to) && upstream.has(edge.from) || downstream.has(edge.from) && downstream.has(edge.to));
  }

  function renderDependencyContext() {
    const card = $('dependency-card'), selected = assetById(selectedId);
    card.hidden = currentLayer !== 'dependencies' || !selected;
    if (card.hidden) return;
    setText('dependency-title', `${selected.name} · required services and downstream assets`);
    const edges = dependencyEdges();
    $('dependency-context').innerHTML = edges.length ? edges.map(edge => `<div class="dependency-relation"><button data-asset="${esc(edge.from)}" class="dependency-node ${esc(assetStatus(assetById(edge.from)))}">${esc(assetById(edge.from).name)}<small>${esc(title(assetStatus(assetById(edge.from))))}</small></button><span>supplies →</span><button data-asset="${esc(edge.to)}" class="dependency-node ${esc(assetStatus(assetById(edge.to)))}">${esc(assetById(edge.to).name)}<small>${esc(title(assetStatus(assetById(edge.to))))}</small></button></div>`).join('') : '<div class="empty-activity">No accepted logical service dependencies are available for this asset.</div>';
  }

  function renderDependencyLines() {
    const svg = $('dependency-lines');
    const hidden = currentLayer !== 'dependencies' || !renderer?.ready || !frameMatchesView();
    svg.toggleAttribute('hidden', hidden);
    if (hidden) { svg.replaceChildren(); return; }
    const bounds = imageRect();
    svg.setAttribute('viewBox', `0 0 ${$('viewport').clientWidth} ${$('viewport').clientHeight}`);
    const points = new Map((frameMetadata.context.projected_assets || []).filter(point => point.visible).map(point => [point.id,{x:bounds.x + point.x * bounds.width,y:bounds.y + point.y * bounds.height}]));
    svg.innerHTML = '<defs><marker id="dependency-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#536d59"/></marker></defs>' + dependencyEdges().filter(edge => points.has(edge.from) && points.has(edge.to)).map(edge => {
      const from = points.get(edge.from), to = points.get(edge.to), source = assetById(edge.from), target = assetById(edge.to);
      const status = ['fault','closed'].includes(source.status) ? 'fault' : source.status === 'warning' || target.status === 'warning' ? 'warning' : 'operational';
      return `<g><line class="dependency-edge ${status}" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" marker-end="url(#dependency-arrow)"/><circle class="dependency-anchor ${status}" cx="${from.x}" cy="${from.y}" r="4"/><title>${esc(source.name)} supplies ${esc(target.name)} · logical relationship</title></g>`;
    }).join('');
  }

  function renderLabels() {
    const container = $('scene-labels');
    renderDependencyLines();
    if (!renderer?.ready || !snapshot || currentLayer === 'none' || !lastFrameReceived || !frameMatchesView()) { container.replaceChildren(); return; }
    const bounds = imageRect();
    let projected = (frameMetadata.context.projected_assets || []).filter(point => point.visible && assetById(point.id));
    if (currentLayer === 'dependencies') {
      const relevant = new Set([selectedId, ...dependencyEdges().flatMap(edge => [edge.from,edge.to])]);
      projected = projected.filter(point => relevant.has(point.id));
    }
    // Keep the overview legible; selected and alerting assets have priority.
    projected = projected.sort((a, b) => (a.id === selectedId ? -10 : assetById(a.id)?.status === 'operational' ? 1 : 0) - (b.id === selectedId ? -10 : assetById(b.id)?.status === 'operational' ? 1 : 0));
    const placed = [];
    const labels = [];
    for (const point of projected) {
      const asset = assetById(point.id);
      if (currentLayer === 'crowds' && ['utility','sensor'].includes(asset.type) && asset.id !== selectedId) continue;
      const x = bounds.x + point.x * bounds.width, y = bounds.y + point.y * bounds.height;
      if (x < 65 || x > bounds.width + bounds.x - 50 || y < 75 || y > bounds.height + bounds.y - 15) continue;
      if (asset.id !== selectedId && placed.some(position => Math.abs(position.x - x) < (bounds.width < 500 ? 87 : 120) && Math.abs(position.y - y) < 36)) continue;
      let metric = currentLayer === 'dependencies' ? title(assetStatus(asset)) : currentLayer === 'energy' ? `${fieldNumber(asset,'power_kw')} kW` : currentLayer === 'crowds' ? `${fieldNumber(asset,'occupancy')} guests` : ['closed','fault','unknown'].includes(assetStatus(asset)) ? title(assetStatus(asset)) : fieldUnknown(asset,'queue_minutes') ? 'Wait unknown' : asset.queue_minutes > 0 ? `${number(asset.queue_minutes)} min` : title(assetStatus(asset));
      const metricField = currentLayer === 'energy' ? 'power_kw' : currentLayer === 'crowds' ? 'occupancy' : currentLayer === 'dependencies' || ['closed','fault','unknown'].includes(assetStatus(asset)) || !asset.queue_minutes ? 'status' : 'queue_minutes';
      const quality = asset.data_quality?.fields?.[metricField]?.status;
      if (fieldModeled(asset,metricField)) metric += ' · modeled';
      else if (['stale','uncertain'].includes(quality)) metric += ` · ${quality}`;
      const shortName = asset.name.replace('Garden ', '').replace(' & Lake', '').replace('Arrival & EV ', '');
      labels.push({id:asset.id,status:assetStatus(asset),name:asset.name,shortName,metric,x,y});
      placed.push({x,y});
      if (labels.length >= (bounds.width < 500 ? 4 : 7)) break;
    }
    const existing = new Map([...container.children].map(button => [button.dataset.labelAsset, button]));
    for (const label of labels) {
      let button = existing.get(label.id);
      if (!button) {
        button = document.createElement('button');
        button.dataset.labelAsset = label.id;
        button.append(document.createElement('strong'), document.createElement('small'));
        container.append(button);
      }
      button.className = `scene-label ${label.status}${label.id === selectedId ? ' selected' : ''}`;
      button.style.left = `${label.x.toFixed(1)}px`; button.style.top = `${label.y.toFixed(1)}px`;
      button.style.zIndex = label.id === selectedId ? '2' : '1';
      button.title = `${label.name} · synthetic ${currentLayer} telemetry`;
      button.firstElementChild.textContent = label.shortName;
      button.lastElementChild.textContent = label.metric;
      existing.delete(label.id);
    }
    for (const button of existing.values()) button.remove();
  }

  async function control(payload, feedback = true) {
    try { return await post('/render/control', payload); }
    catch (error) {
      if (feedback && Date.now() - lastControlError > 4000) { toast(`Camera control unavailable: ${error.message}`, true); lastControlError = Date.now(); }
      return null;
    }
  }

  async function flushCamera() {
    if (renderControlsInFlight) return;
    renderControlsInFlight = true;
    try {
      while (pendingOrbit || pendingZoom) {
        if (pendingOrbit) { const movement = pendingOrbit; pendingOrbit = null; await control({action:'orbit', dx:Math.max(-2, Math.min(2, movement.dx)), dy:Math.max(-2, Math.min(2, movement.dy))}); }
        if (pendingZoom) { const delta = pendingZoom; pendingZoom = 0; await control({action:'zoom', delta:Math.max(-2000, Math.min(2000, delta))}); }
      }
    } finally { renderControlsInFlight = false; }
  }

  async function pollRenderer() {
    while (true) {
      if (!document.hidden) {
        try {
          const status = await request('/render/status', {}, 6000);
          renderer = status;
          $('renderer-badge').classList.toggle('ready', !!status.ready);
          $('renderer-badge').querySelector('span').textContent = status.ready ? replaying() ? 'RECORDED VIEW' : 'LIVE GPU' : lastFrameReceived ? 'LAST FRAME' : 'WARMING UP';
          setText('render-stats', status.ready ? `OVRTX · ${number(status.fps, 1)} render fps · ${status.width} × ${status.height}` : 'GPU feed pending');
          if (!status.ready) setText('render-wait-message', status.error ? `Renderer initializing: ${status.error}` : `${title(status.phase || 'initializing')} on the GPU. The first frame may take a moment.`);
          if (status.frame !== lastFrameNumber) { lastFrameNumber = status.frame; }
          renderLabels(); updateFrameContext();
        } catch (_) {
          if (renderer) renderer.ready = false;
          $('renderer-badge').classList.remove('ready');
          $('renderer-badge').querySelector('span').textContent = 'OFFLINE';
          setText('render-stats', 'GPU renderer reconnecting');
          setText('render-wait-message', 'The GPU render service is not available yet. Operational APIs remain usable. Retrying automatically.');
          updateFrameContext();
        }
      }
      await sleep(650);
    }
  }

  function updateFrameContext() {
    const context = $('frame-context');
    if (!frameMetadata || !lastFrameReceived) { context.hidden = true; return; }
    const renderedAge = sourceAge(frameMetadata.renderedAt);
    const frameStale = renderedAge === null ? Date.now() - lastUniqueFrameAt > 5000 : renderedAge > 5;
    const observedAge = sourceAge(frameMetadata.sourceTimestamp);
    const stalePose = frameMetadata.poseSource === 'stale_frozen';
    const sourceStale = !replaying() && (stalePose || observedAge !== null && observedAge > 6);
    const missingFrameTime = !frameMetadata.renderedAt;
    $('viewport').classList.toggle('frame-stale', frameStale);
    $('viewport').classList.toggle('source-stale', sourceStale);
    const frameLabel = frameMetadata.frame === null ? 'GPU image' : `Frame #${frameMetadata.frame}`;
    setText('frame-freshness', `${frameLabel} · ${frameMetadata.renderedAt ? `rendered ${time(frameMetadata.renderedAt)} UTC` : 'render time unavailable'}`);
    $('frame-freshness').title = `Source tick ${frameMetadata.sourceTick ?? 'unknown'} · source ${time(frameMetadata.sourceTimestamp)} UTC · ${ageLabel(observedAge)}`;
    let message = '';
    if (!frameMetadata.viewMode || !frameMetadata.sourceRevision || !frameMetadata.context) message = 'FRAME PROVENANCE UNAVAILABLE · image cannot be associated with the displayed data';
    else if (!frameMatchesView()) message = `VIEW SWITCH IN PROGRESS · image does not yet match ${replaying() ? `record #${snapshot.view.snapshot_id}` : 'live state'}`;
    else if (frameStale) message = `LAST GPU IMAGE · ${ageLabel(renderedAge)} · renderer reconnecting`;
    else if (stalePose) message = 'SOURCE QUALITY DEGRADED · affected ride poses frozen until fresh accepted status';
    else if (sourceStale) message = `SOURCE DATA STALE · last source ${time(frameMetadata.sourceTimestamp)} UTC · ${ageLabel(observedAge)}`;
    else if (replaying()) message = frameMetadata.poseSource === 'recorded' ? `RECORDED SNAPSHOT #${snapshot.view.snapshot_id} · captured ride pose` : 'RECORDED DATA · historical ride pose unavailable';
    else if (missingFrameTime) message = 'GPU IMAGE · rendered timestamp not supplied';
    else if (currentLayer === 'dependencies') message = 'LOGICAL DEPENDENCIES · not physical routes';
    context.textContent = message; context.hidden = !message;
    context.classList.toggle('warning', !frameMatchesView() || frameStale || sourceStale || missingFrameTime);
    $('renderer-badge').classList.toggle('stale', frameStale || sourceStale);
    if (frameStale || sourceStale) $('renderer-badge').querySelector('span').textContent = frameStale ? 'LAST FRAME' : 'STALE SOURCE';
  }

  function parseFrameContext(value) {
    try {
      const context = typeof value === 'string' ? JSON.parse(value) : value;
      if (!context || !Number.isInteger(context.width) || !Number.isInteger(context.height) || context.width <= 0 || context.height <= 0 || context.width > 32768 || context.height > 32768) return null;
      if (!context.camera || typeof context.camera !== 'object' || Array.isArray(context.camera)) return null;
      if (!Array.isArray(context.projected_assets) || context.projected_assets.length > 10000) return null;
      if (!context.projected_assets.every(point => point && typeof point.id === 'string' && typeof point.visible === 'boolean' && Number.isFinite(point.x) && Number.isFinite(point.y))) return null;
      // Copy immutable per-image coordinates; later status responses cannot move them.
      return {width:context.width,height:context.height,camera:JSON.parse(JSON.stringify(context.camera)),projected_assets:context.projected_assets.map(point => ({id:point.id,x:point.x,y:point.y,visible:point.visible}))};
    } catch (_) { return null; }
  }

  function metadataFromHeaders(headers) {
    const header = name => headers.get(name), frameId = header('X-Frame-Number');
    const knownId = frameId !== null && Number.isFinite(Number(frameId)) ? Number(frameId) : null;
    // A newer /status response cannot identify an older image. Its metadata is
    // a valid fallback only when the image itself names that exact frame.
    const matchingStatus = knownId !== null && knownId === renderer?.frame ? renderer : null;
    const rawContext = header('X-Frame-Context');
    const context = parseFrameContext(rawContext !== null ? rawContext : matchingStatus);
    return {
      frame:knownId,
      context,
      sourceRevision:header('X-Source-Revision') || matchingStatus?.accepted_state_revision || null,
      cameraToken:header('X-Frame-Camera-Token') || matchingStatus?.camera_token || null,
      renderedAt:header('X-Frame-Rendered-At') || matchingStatus?.rendered_at || null,
      sourceTimestamp:header('X-Source-Timestamp') || matchingStatus?.source_timestamp || null,
      sourceTick:header('X-Source-Tick') || matchingStatus?.source_tick || null,
      viewMode:header('X-View-Mode') || matchingStatus?.view_mode || null,
      snapshotId:header('X-View-Snapshot-Id') || matchingStatus?.snapshot_id || null,
      poseSource:header('X-Pose-Source') || matchingStatus?.pose_source || null
    };
  }

  async function streamFrames() {
    while (true) {
      if (document.hidden) { await sleep(700); continue; }
      const started = performance.now();
      let nextUrl = null;
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 8000);
        let response;
        try { response = await fetch(`/render/frame.jpg?t=${Date.now()}`, {cache:'no-store', signal:controller.signal}); }
        finally { clearTimeout(timer); }
        if (!response.ok) throw new Error('GPU frame not available');
        const blob = await response.blob();
        if (!blob.type.startsWith('image/')) throw new Error('Render service did not return an image');
        nextUrl = URL.createObjectURL(blob);
        const preload = new Image(); preload.src = nextUrl; await preload.decode();
        const previous = liveFrameUrl; liveFrameUrl = nextUrl; nextUrl = null;
        $('render-frame').src = liveFrameUrl;
        if (previous) URL.revokeObjectURL(previous);
        lastFrameReceived = Date.now();
        const metadata = metadataFromHeaders(response.headers);
        const identity = `${metadata.frame}:${metadata.renderedAt}`;
        if (identity !== displayedFrameIdentity) { displayedFrameIdentity = identity; lastUniqueFrameAt = Date.now(); }
        frameMetadata = metadata;
        $('viewport').classList.add('frame-ready'); $('viewport-wait').hidden = true;
        updateFrameContext(); renderLabels();
        await sleep(Math.max(40, 125 - (performance.now() - started)));
      } catch (_) {
        if (nextUrl) URL.revokeObjectURL(nextUrl);
        if (lastFrameReceived) updateFrameContext();
        await sleep(1800);
      }
    }
  }

  function setupPointerControls() {
    const viewport = $('viewport'); let drag = null;
    viewport.addEventListener('pointerdown', event => {
      if (event.button !== 0 || event.target.closest('button')) return;
      drag = {id:event.pointerId, x:event.clientX, y:event.clientY, startX:event.clientX, startY:event.clientY, moved:false};
      viewport.setPointerCapture(event.pointerId);
    });
    viewport.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 4) return;
      drag.moved = true;
      const bounds = imageRect();
      pendingOrbit ||= {dx:0, dy:0};
      pendingOrbit.dx += (event.clientX - drag.x) / bounds.width;
      pendingOrbit.dy += (event.clientY - drag.y) / bounds.height;
      drag.x = event.clientX; drag.y = event.clientY;
      flushCamera();
    });
    viewport.addEventListener('pointerup', async event => {
      if (!drag || event.pointerId !== drag.id) return;
      const gesture = drag; drag = null;
      if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
      if (gesture.moved) return;
      if (!renderer?.ready) { toast('The GPU renderer is warming up. You can inspect assets using the registry selector.'); return; }
      if (!frameMatchesView()) { toast('The GPU image is synchronizing with the selected record. The asset selector remains available.'); return; }
      if (!frameMetadata.cameraToken) { toast('Image camera identity is unavailable. Select an asset from the registry or its projected label.'); return; }
      const pickContext = {expected_camera_token:frameMetadata.cameraToken,expected_source_revision:frameMetadata.sourceRevision,expected_view_mode:frameMetadata.viewMode,expected_snapshot_id:frameMetadata.snapshotId};
      const requestedView = viewKey(snapshot), requestedVersion = viewRequestVersion;
      const view = viewport.getBoundingClientRect(), bounds = imageRect();
      const x = (event.clientX - view.left - bounds.x) / bounds.width, y = (event.clientY - view.top - bounds.y) / bounds.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      viewport.classList.add('picking');
      try {
        const picked = await post('/render/pick', {x,y,...pickContext}, 19000);
        if (!pickViewUnchanged(requestedView,requestedVersion)) { toast('The displayed view changed during selection. Select the asset again.'); return; }
        if (picked.asset_id) await selectAsset(picked.asset_id, false, false);
        else toast('No connected asset here. Click a ride, facility or utility building.');
      } catch (error) { toast(`Object selection failed: ${error.message}`, true); }
      finally { viewport.classList.remove('picking'); }
    });
    viewport.addEventListener('pointercancel', () => { drag = null; });
    viewport.addEventListener('wheel', event => {
      event.preventDefault();
      pendingZoom += event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1);
      flushCamera();
    }, {passive:false});
    viewport.addEventListener('keydown', event => {
      if (event.target !== viewport) return;
      const movement = {ArrowLeft:[-.05,0], ArrowRight:[.05,0], ArrowUp:[0,-.05], ArrowDown:[0,.05]}[event.key];
      if (movement) { event.preventDefault(); control({action:'orbit', dx:movement[0], dy:movement[1]}); }
      if (event.key === 'Home') { event.preventDefault(); control({action:'home'}); }
      if (event.key === '+' || event.key === '=') { event.preventDefault(); control({action:'zoom', delta:-140}); }
      if (event.key === '-') { event.preventDefault(); control({action:'zoom', delta:140}); }
    });
  }

  function setLayer(layer) {
    currentLayer = layer;
    $$('[data-layer]').forEach(item => { item.classList.toggle('active', item.dataset.layer === layer); item.setAttribute('aria-pressed', String(item.dataset.layer === layer)); });
    setText('scene-layer-name', {operations:'Operations',energy:'Energy overlay',crowds:'Guest flow overlay',dependencies:'Logical dependencies',none:'Clean view'}[layer]);
    renderLabels(); renderDependencyContext(); updateFrameContext(); control({action:'layer', layer}, false);
  }

  function bindEvents() {
    $('asset-select').addEventListener('change', event => selectAsset(event.target.value));
    $('focus-asset').onclick = () => control({action:'focus', asset_id:selectedId});
    $('camera-home').onclick = () => control({action:'home'});
    $('camera-zoom-in').onclick = () => control({action:'zoom', delta:-180});
    $('camera-zoom-out').onclick = () => control({action:'zoom', delta:180});
    $('fullscreen').onclick = async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else await $('viewport').requestFullscreen(); } catch (_) { toast('Fullscreen is not available in this browser.', true); } };
    $('scenario-options').addEventListener('click', event => { const button = event.target.closest('[data-scenario]'); if (button) runScenario(button.dataset.scenario); });
    document.addEventListener('click', event => {
      const action = event.target.closest('[data-action]');
      if (action) runAction(action.dataset.action, action.dataset.asset);
      const dependency = event.target.closest('[data-asset]:not([data-action])');
      if (dependency) selectAsset(dependency.dataset.asset);
      const label = event.target.closest('[data-label-asset]');
      if (label) selectAsset(label.dataset.labelAsset);
      const source = event.target.closest('[data-system]');
      if (source) showSystem(source.dataset.system);
      if (event.target.closest('[data-show-dependencies]')) setLayer('dependencies');
    });
    $$('[data-layer]').forEach(button => button.onclick = () => setLayer(button.dataset.layer));
    $$('[data-view]').forEach(button => button.onclick = () => {
      $$('[data-view]').forEach(item => item.classList.toggle('active', item === button));
      const section = {operations:'operations-view',systems:'systems-section',activity:'activity-section'}[button.dataset.view];
      $(section).scrollIntoView({behavior:'smooth', block:'start'});
    });
    $('show-system-map').onclick = () => $('architecture-dialog').showModal();
    $('compare-scenarios').onclick = () => showComparison(snapshot?.scenario === 'ride_closure' ? 'normal' : 'ride_closure');
    $('close-architecture').onclick = () => $('architecture-dialog').close();
    $('architecture-dialog').addEventListener('click', event => { if (event.target === $('architecture-dialog')) $('architecture-dialog').close(); });
    $('return-live').onclick = $('timeline-live').onclick = () => switchView('live');
    $('timeline-range').addEventListener('input', () => { timelineDragging = true; renderTimelineSelection(); });
    $('timeline-range').addEventListener('change', () => {
      const record = timeline[Number($('timeline-range').value)]; timelineDragging = false;
      if (record) switchView('replay', record.id);
    });
    $('timeline-previous').onclick = () => { const record = timeline[Math.max(0, Number($('timeline-range').value) - 1)]; if (record) switchView('replay', record.id); };
    $('timeline-next').onclick = () => { const record = timeline[Math.min(timeline.length - 1, Number($('timeline-range').value) + 1)]; if (record) switchView('replay', record.id); };
    new ResizeObserver(renderLabels).observe($('viewport'));
    setupPointerControls();
  }

  bindEvents();
  setInterval(() => {
    setText('clock', `${time(new Date())} UTC`);
    if (lastStateReceived && Date.now() - lastStateReceived > 6000) setConnection(false, `View API unavailable · last response ${time(new Date(lastStateReceived))} UTC`);
    updateFrameContext();
  }, 1000);
  setInterval(refreshTimeline, 3000);
  setInterval(refreshSource, 2000);
  refreshTimeline();
  pollState(); pollRenderer(); streamFrames();
})();
