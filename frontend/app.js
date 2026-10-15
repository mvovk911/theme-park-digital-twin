/* Aster Park live twin. No client-side scene renderer: every park image comes
 * from NVIDIA OVRTX. DOM overlays carry explicitly synthetic operational data. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const $$ = query => [...document.querySelectorAll(query)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const number = (value, digits = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString('en-GB', {maximumFractionDigits:digits, minimumFractionDigits:digits}) : '—';
  const title = text => String(text ?? '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
  const time = stamp => stamp ? new Date(stamp).toLocaleTimeString('en-GB', {timeZone:'UTC', hour12:false, hour:'2-digit', minute:'2-digit', second:'2-digit'}) : '—';
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  let snapshot = null, selectedId = 'RIDE_COASTER', assetDetails = null, currentLayer = 'operations';
  let renderer = null, lastStateReceived = 0, lastFrameReceived = 0, liveFrameUrl = null, lastFrameNumber = -1;
  let scenarioPending = false, actionPending = false, detailsSequence = 0, lastDetailFetch = 0;
  let renderedSystems = '', renderedActions = '', renderedAlerts = '', renderedAudit = '';
  let renderControlsInFlight = false, pendingOrbit = null, pendingZoom = 0, lastControlError = 0;
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
  function setConnection(online, text) {
    $('data-connection').classList.toggle('offline', !online);
    $('data-connection').querySelector('span').textContent = text;
  }

  function applyState(data) {
    if (!Array.isArray(data.assets) || !data.kpis) throw new Error('The state service returned an unexpected response.');
    if (snapshot && Number.isFinite(data.tick) && data.tick < snapshot.tick && Date.parse(data.timestamp) <= Date.parse(snapshot.timestamp)) return;
    snapshot = data;
    lastStateReceived = Date.now();
    setConnection(true, `Synthetic services live · tick ${data.tick ?? '—'}`);
    const k = data.kpis;
    setText('kpi-attendance', number(k.attendance));
    setText('kpi-wait', number(k.average_wait_minutes, 1));
    setText('kpi-rides', `${number(k.open_rides)} / ${data.assets.filter(asset => asset.type === 'ride').length}`);
    setText('kpi-power', number(k.power_kw));
    setText('kpi-water', number(k.water_lpm));
    setText('kpi-alerts', number(k.active_alerts));
    $('kpi-alerts').closest('.kpi').classList.toggle('attention', k.active_alerts > 0);
    setText('alert-note', k.active_alerts ? 'Review operational response' : 'All systems within simulation limits');
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
    renderAsset(); renderBrief(); renderSystems(); renderActivity(); renderLabels();
    if (Date.now() - lastDetailFetch > 5000) refreshDetails();
  }

  async function pollState() {
    while (true) {
      if (!document.hidden) {
        try { applyState(await request('/api/state')); }
        catch (_) { setConnection(false, snapshot ? `Data connection lost · last ${time(snapshot.timestamp)} UTC` : 'Synthetic services unavailable · retrying'); }
      }
      await sleep(1000);
    }
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
    setText('asset-status', asset.status);
    $('asset-status').className = `status-badge ${esc(asset.status)}`;
    setText('asset-description', asset.description);
    setText('asset-id', asset.id);
    setText('asset-queue', asset.type === 'utility' || asset.type === 'sensor' ? '—' : number(asset.queue_minutes, 1));
    setText('asset-occupancy', asset.type === 'utility' || asset.type === 'sensor' ? '—' : `${number(asset.occupancy)} / ${number(asset.capacity)}`);
    $('asset-occupancy').style.fontSize = asset.capacity >= 100 ? '18px' : '';
    $('occupancy-meter').style.width = `${Math.max(0, Math.min(100, asset.capacity ? asset.occupancy / asset.capacity * 100 : 0))}%`;
    setText('asset-power', number(asset.power_kw, 1));
    setText('asset-health', number(asset.maintenance?.health_pct));
    setText('asset-staff', `${asset.staff?.on_duty ?? 0} on duty / ${asset.staff?.required ?? 0} needed`);
    setText('asset-water', `${number(asset.water_lpm, 1)} L/min`);
    setText('asset-inspection', title(asset.maintenance?.inspection_status));
    setText('asset-orders', number(asset.maintenance?.open_work_orders));
    setText('asset-stock', asset.type === 'food' ? `${number(asset.erp?.stock_units)} units` : '—');
    setText('asset-scene-path', asset.scene_path);
    setText('asset-updated', `Synthetic API → registry → USD · ${time(snapshot.timestamp)} UTC`);
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
    $$('#asset-actions button').forEach(button => button.disabled = actionPending);
    renderOrders();
  }

  function renderOrders() {
    let section = $('work-orders-detail');
    const orders = assetDetails?.id === selectedId ? assetDetails.work_orders || [] : [];
    if (!section && orders.length) {
      section = document.createElement('div');
      section.id = 'work-orders-detail';
      section.className = 'work-orders-detail';
      $('asset-actions').after(section);
    }
    if (section) {
      section.hidden = !orders.length;
      section.innerHTML = orders.slice(0, 3).map(order => `<div class="work-order"><span>WO #${esc(order.id)} · ${esc(title(order.status))}</span><small>${esc(order.title)}</small></div>`).join('');
    }
  }

  async function refreshDetails() {
    if (!selectedId) return;
    const id = selectedId, sequence = ++detailsSequence;
    lastDetailFetch = Date.now();
    try {
      const [detail, history] = await Promise.all([request(`/api/assets/${encodeURIComponent(id)}`), request(`/api/assets/${encodeURIComponent(id)}/history?limit=90`)]);
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

  function renderBrief() {
    const alerts = snapshot.alerts || [];
    const signature = JSON.stringify([snapshot.scenario, alerts]);
    if (signature === renderedAlerts) return;
    renderedAlerts = signature;
    if (!alerts.length) {
      const normal = snapshot.scenario === 'normal';
      $('operations-brief').innerHTML = `<h3>${normal ? 'The park is running within its operating plan.' : 'The simulated response is taking effect.'}</h3><p>${normal ? 'Both attractions are available. Explore an asset in the twin, or introduce a disruption to see its effect on queues, utilities and connected services.' : 'No active alerts remain in this scenario. Inspect telemetry and the activity trail to review what changed, or reset the simulation.'}</p>`;
      $('alert-actions').innerHTML = normal ? '' : '<button class="brief-action" data-action="reset">Reset simulation ↗</button>';
      return;
    }
    $('operations-brief').innerHTML = alerts.slice(0, 3).map(alert => `<div class="brief-alert"><h3><span class="alert-severity ${esc(alert.severity)}"></span>${esc(alert.title)} <button class="inspect-alert" data-asset="${esc(alert.asset_id)}">Inspect ↗</button></h3><p>${esc(alert.message)}</p></div>`).join('');
    const seen = new Set();
    $('alert-actions').innerHTML = alerts.filter(alert => {
      const signature = `${alert.recommended_action}:${alert.asset_id}`;
      if (!alert.recommended_action || seen.has(signature)) return false;
      seen.add(signature); return true;
    }).map(alert => `<button class="brief-action" data-action="${esc(alert.recommended_action)}" data-asset="${esc(alert.asset_id)}">${esc(actionLabels[alert.recommended_action] || title(alert.recommended_action))} ↗</button>`).join('') + '<button class="brief-action secondary" data-action="reset">Reset</button>';
  }

  function renderSystems() {
    const systems = snapshot.systems || [];
    const signature = JSON.stringify(systems.map(system => [system.id, system.name, system.protocol, system.status, system.asset_ids]));
    if (signature !== renderedSystems) {
      renderedSystems = signature;
      $('system-cards').innerHTML = systems.map(system => `<button class="system-card" data-system="${esc(system.id)}" title="Inspect synthetic ${esc(system.name)} feed"><span class="system-dot${system.status === 'connected' ? '' : ' warning'}"></span><span class="system-icon">${systemIcons[system.id] || '⌘'}</span><h3>${esc(system.name)}</h3><div class="system-meta"><span class="system-protocol" title="Intended production interface: ${esc(system.protocol)}">${esc(system.protocol)}</span><span>${system.asset_ids?.length || 0} assets</span></div><div class="system-source">SYNTHETIC HTTP ADAPTER</div></button>`).join('');
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
    if (scenarioPending || !scenarioAssets[scenario]) return;
    scenarioPending = true;
    $$('.scenario-chip').forEach(button => button.disabled = true);
    try {
      applyState(await post('/api/scenarios', {scenario}));
      await selectAsset(scenarioAssets[scenario]);
      toast(`${snapshot.scenarios?.find(item => item.id === scenario)?.label || title(scenario)} is now running. All effects are simulated.`);
    } catch (error) { toast(`Scenario could not be applied: ${error.message}`, true); }
    finally { scenarioPending = false; $$('.scenario-chip').forEach(button => button.disabled = false); }
  }

  async function runAction(action, assetId) {
    if (actionPending) return;
    actionPending = true;
    $$('[data-action]').forEach(button => button.disabled = true);
    try {
      const body = {action};
      if (assetId && action !== 'reset') body.asset_id = assetId;
      const response = await post('/api/actions', body);
      applyState(response.state);
      toast(response.result.message || 'Simulated action applied.');
      refreshDetails();
    } catch (error) { toast(`Action could not be applied: ${error.message}`, true); }
    finally { actionPending = false; $$('[data-action]').forEach(button => button.disabled = false); }
  }

  async function showSystem(id) {
    const system = snapshot?.systems?.find(source => source.id === id);
    if (!system) return;
    let dialog = $('system-dialog');
    if (!dialog) {
      dialog = document.createElement('dialog'); dialog.id = 'system-dialog'; document.body.append(dialog);
      dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    }
    dialog.innerHTML = `<div class="dialog-heading"><div><div class="eyebrow">SYNTHETIC SOURCE SERVICE</div><h2>${esc(system.name)}</h2></div><button class="icon-button close-system" aria-label="Close source detail">×</button></div><p class="dialog-intro">Intended production protocol: <strong>${esc(system.protocol)}</strong>. This POC exposes synthetic domain records through HTTP; it does not connect to physical equipment.</p><div class="source-context"><span class="tiny-badge">${system.asset_ids?.length || 0} CONNECTED ASSETS</span><code>GET /api/systems/${esc(id)}/data</code></div><div class="source-assets">${(system.asset_ids || []).map(assetId => `<button class="dependency-chip" data-source-asset="${esc(assetId)}">${esc(assetById(assetId)?.name || assetId)}</button>`).join('')}</div><div class="source-feed" id="source-feed">Fetching the current synthetic payload…</div>`;
    dialog.querySelector('.close-system').onclick = () => dialog.close();
    dialog.querySelectorAll('[data-source-asset]').forEach(button => button.onclick = () => { selectAsset(button.dataset.sourceAsset, true); dialog.close(); $('operations-view').scrollIntoView({behavior:'smooth', block:'start'}); });
    if (!dialog.open) dialog.showModal();
    try {
      const result = await request(`/api/systems/${encodeURIComponent(id)}/data`);
      if (dialog.open && dialog.querySelector('code')?.textContent.endsWith(`/${id}/data`)) {
        const pre = document.createElement('pre'); pre.textContent = JSON.stringify(result, null, 2); $('source-feed').replaceChildren(pre);
      }
    } catch (error) { if (dialog.open) $('source-feed').textContent = `Source unavailable: ${error.message}`; }
  }

  async function showComparison(scenario = 'ride_closure') {
    if (!snapshot) { toast('Connect to the synthetic services before comparing scenarios.'); return; }
    let dialog = $('comparison-dialog');
    if (!dialog) {
      dialog = document.createElement('dialog'); dialog.id = 'comparison-dialog'; document.body.append(dialog);
      dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    }
    dialog.innerHTML = `<div class="dialog-heading"><div><div class="eyebrow">SCENARIO LAB / READ-ONLY COMPARISON</div><h2>Explore the impact before you act.</h2></div><button class="icon-button close-comparison" aria-label="Close comparison">×</button></div><p class="dialog-intro">Synthetic estimate · same time · no live changes. Compare the current operating state with a hypothetical scenario at the same simulation tick.</p><div class="comparison-controls"><label>HYPOTHETICAL SCENARIO<select id="comparison-scenario">${(snapshot.scenarios || []).map(item => `<option value="${esc(item.id)}"${item.id === scenario ? ' selected' : ''}>${esc(item.label)}</option>`).join('')}</select></label><span class="tiny-badge">BASELINE: ${esc(title(snapshot.scenario)).toUpperCase()}</span></div><div id="comparison-result" class="comparison-result">Evaluating the synthetic scenario…</div>`;
    dialog.querySelector('.close-comparison').onclick = () => dialog.close();
    $('comparison-scenario').onchange = event => showComparison(event.target.value);
    if (!dialog.open) dialog.showModal();
    try {
      const comparison = await request(`/api/scenarios/compare?scenario=${encodeURIComponent(scenario)}`);
      if (!dialog.open || $('comparison-scenario').value !== scenario) return;
      $('comparison-result').innerHTML = `<div class="comparison-table-wrap"><table class="comparison-table"><thead><tr><th>Operating measure</th><th>Current state</th><th>Hypothetical</th><th>Change</th></tr></thead><tbody>${comparison.deltas.map(metric => `<tr><td>${esc(metric.label)}<small>${esc(metric.unit)}</small></td><td>${number(metric.before, metric.unit === 'min' ? 1 : 0)}</td><td>${number(metric.after, metric.unit === 'min' ? 1 : 0)}</td><td><span class="delta-chip${metric.delta !== 0 ? ' changed' : ''}">${metric.delta > 0 ? '+' : ''}${number(metric.delta, metric.unit === 'min' ? 1 : 0)}</span></td></tr>`).join('')}</tbody></table></div>${comparison.asset_changes?.length ? `<div class="comparison-assets"><div class="section-label">AFFECTED ASSETS</div>${comparison.asset_changes.slice(0, 8).map(asset => `<span class="comparison-asset"><strong>${esc(asset.name)}</strong><small>${esc(title(asset.before_status))} → ${esc(title(asset.after_status))}</small></span>`).join('')}</div>` : ''}<div class="comparison-assumptions"><strong>Model assumptions</strong><ul>${(comparison.assumptions || []).map(assumption => `<li>${esc(assumption)}</li>`).join('')}</ul></div><div class="comparison-footer"><span>Same-tick heuristic · baseline tick ${number(comparison.baseline_tick)}<br>Uncalibrated demonstration estimates; no real-world savings claim.</span><button class="asset-action apply-comparison">Run this scenario ↗</button></div>`;
      dialog.querySelector('.apply-comparison').onclick = () => { dialog.close(); runScenario(scenario); };
    } catch (error) { if (dialog.open && $('comparison-scenario')?.value === scenario) $('comparison-result').textContent = `Comparison unavailable: ${error.message}`; }
  }

  // The renderer publishes normalized positions in the image, not the browser.
  // Both annotations and picking use the same letterbox-aware image rectangle.
  function imageRect() {
    const viewport = $('viewport'), width = viewport.clientWidth, height = viewport.clientHeight;
    const ratio = (renderer?.width || 1280) / (renderer?.height || 720);
    const imageWidth = Math.min(width, height * ratio), imageHeight = imageWidth / ratio;
    return {x:(width - imageWidth) / 2, y:(height - imageHeight) / 2, width:imageWidth, height:imageHeight};
  }

  function renderLabels() {
    const container = $('scene-labels');
    if (!renderer?.ready || !snapshot || currentLayer === 'none' || !lastFrameReceived) { container.replaceChildren(); return; }
    const bounds = imageRect();
    let projected = (renderer.projected_assets || []).filter(point => point.visible && assetById(point.id));
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
      const metric = currentLayer === 'energy' ? `${number(asset.power_kw)} kW` : currentLayer === 'crowds' ? `${number(asset.occupancy)} guests` : ['closed','fault'].includes(asset.status) ? title(asset.status) : asset.queue_minutes > 0 ? `${number(asset.queue_minutes)} min` : title(asset.status);
      const shortName = asset.name.replace('Garden ', '').replace(' & Lake', '').replace('Arrival & EV ', '');
      labels.push({id:asset.id,status:asset.status,name:asset.name,shortName,metric,x,y});
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
          $('renderer-badge').querySelector('span').textContent = status.ready ? 'LIVE GPU' : 'WARMING UP';
          setText('render-stats', status.ready ? `OVRTX · ${number(status.fps, 1)} render fps · ${status.width} × ${status.height}` : 'GPU feed pending');
          if (!status.ready) setText('render-wait-message', status.error ? `Renderer initializing: ${status.error}` : `${title(status.phase || 'initializing')} on the GPU. The first frame may take a moment.`);
          if (status.frame !== lastFrameNumber) { lastFrameNumber = status.frame; }
          renderLabels();
        } catch (_) {
          if (renderer) renderer.ready = false;
          $('renderer-badge').classList.remove('ready');
          $('renderer-badge').querySelector('span').textContent = 'OFFLINE';
          setText('render-stats', 'GPU renderer reconnecting');
          setText('render-wait-message', 'The GPU render service is not available yet. Operational APIs remain usable. Retrying automatically.');
        }
      }
      await sleep(650);
    }
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
        $('viewport').classList.add('frame-ready'); $('viewport-wait').hidden = true;
        setText('frame-freshness', `GPU frame · ${time(new Date())} UTC`);
        await sleep(Math.max(40, 125 - (performance.now() - started)));
      } catch (_) {
        if (nextUrl) URL.revokeObjectURL(nextUrl);
        if (lastFrameReceived) setText('frame-freshness', 'Last GPU frame · reconnecting');
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
      const view = viewport.getBoundingClientRect(), bounds = imageRect();
      const x = (event.clientX - view.left - bounds.x) / bounds.width, y = (event.clientY - view.top - bounds.y) / bounds.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      viewport.classList.add('picking');
      try {
        const picked = await post('/render/pick', {x,y}, 19000);
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
    });
    $$('[data-layer]').forEach(button => button.onclick = () => {
      currentLayer = button.dataset.layer;
      $$('[data-layer]').forEach(item => { item.classList.toggle('active', item === button); item.setAttribute('aria-pressed', String(item === button)); });
      setText('scene-layer-name', {operations:'Operations',energy:'Energy overlay',crowds:'Guest flow overlay',none:'Clean view'}[currentLayer]);
      renderLabels(); control({action:'layer', layer:currentLayer}, false);
    });
    $$('[data-view]').forEach(button => button.onclick = () => {
      $$('[data-view]').forEach(item => item.classList.toggle('active', item === button));
      const section = {operations:'operations-view',systems:'systems-section',activity:'activity-section'}[button.dataset.view];
      $(section).scrollIntoView({behavior:'smooth', block:'start'});
    });
    $('show-system-map').onclick = () => $('architecture-dialog').showModal();
    $('compare-scenarios').onclick = () => showComparison(snapshot?.scenario === 'ride_closure' ? 'normal' : 'ride_closure');
    $('close-architecture').onclick = () => $('architecture-dialog').close();
    $('architecture-dialog').addEventListener('click', event => { if (event.target === $('architecture-dialog')) $('architecture-dialog').close(); });
    new ResizeObserver(renderLabels).observe($('viewport'));
    setupPointerControls();
  }

  bindEvents();
  setInterval(() => {
    setText('clock', `${time(new Date())} UTC`);
    if (lastStateReceived && Date.now() - lastStateReceived > 6000) setConnection(false, `Telemetry stale · last ${time(snapshot.timestamp)} UTC`);
    if (lastFrameReceived && Date.now() - lastFrameReceived > 5000) { setText('frame-freshness', `Last GPU image · ${Math.round((Date.now() - lastFrameReceived) / 1000)}s ago`); $('viewport').classList.add('frame-stale'); }
    else $('viewport').classList.remove('frame-stale');
  }, 1000);
  pollState(); pollRenderer(); streamFrames();
})();
