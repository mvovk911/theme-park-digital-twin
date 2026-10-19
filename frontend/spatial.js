/* Read-only authored design comparison. Independent of live operations/replay. */
(() => {
  'use strict';
  const panel = document.getElementById('spatial-panel');
  if (!panel) return;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const variants = ['baseline', 'dining_connection'];
  const names = {baseline:'Existing authored park', dining_connection:'Dining connection design'};
  const stores = Object.fromEntries(variants.map(variant => [variant, {graph:null, result:null, error:null, preview:null}]));
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const short = value => hash(value) ? value.slice(0,12) : 'unavailable';
  let capability = null, busy = false, generation = 0, complete = false;
  panel.innerHTML = `
    <div class="spatial-heading"><div><div class="eyebrow">DESIGN QUESTION / READ-ONLY</div><h3>Does the dining connection fix access?</h3><p>Compare the same entrance-to-dining journey in two authored designs.</p></div><span class="spatial-badge">AUTHORED DESIGN · SYNTHETIC</span></div>
    <div class="spatial-controls"><div class="spatial-journey"><span>FROM</span><strong>Park entrance</strong><b>→</b><span>TO</span><strong>Dining plaza</strong><small>Assumed walking speed: 1.2 m/s</small></div><div class="spatial-options"><label><input id="spatial-closed" type="checkbox"> Close the design connection</label><label><input id="spatial-accessible" type="checkbox"> Authored step-free links only</label></div><button id="spatial-compare" disabled>Compare access ↗</button></div>
    <div id="spatial-context" class="spatial-context">Authored design query · independent of live conditions and operational forecasts · no physical guidance.</div>
    <p id="spatial-status" class="spatial-status" role="status">Loading verified design sources…</p>
    <div class="spatial-cards">${variants.map(variant => `<article id="spatial-${variant}" class="spatial-card"><div class="spatial-card-heading"><span>${variant==='baseline'?'01 / BASELINE':'02 / SEPARATE DESIGN'}</span><h4>${names[variant]}</h4></div><div id="spatial-result-${variant}" class="spatial-result"><strong>Waiting for design data</strong></div><div id="spatial-graph-${variant}" class="spatial-graph"></div><p id="spatial-note-${variant}" class="spatial-note"></p><div class="spatial-preview"><img id="spatial-preview-${variant}" alt="Static native closeup of ${names[variant].toLowerCase()}" hidden><p id="spatial-preview-note-${variant}">Native closeup has not loaded.</p></div><p id="spatial-identity-${variant}" class="spatial-identity">Graph identity pending</p></article>`).join('')}</div>
    <div class="spatial-legend"><span><i class="spatial-key network"></i>Authored link</span><span><i class="spatial-key route"></i>Queried route</span><span><i class="spatial-key excluded"></i>Missing / closed / filtered</span><span>Graph detail · 2D plan view</span></div>
    <p class="spatial-limits">The dining endpoint moves to the new plaza landing, before tables and service queues. Distance excludes terrain grade; time excludes waiting and crowds. Step-free labels are authored assumptions, not accessibility certification. This graph does not feed the operational forecast.</p>
    <div class="spatial-footer"><span id="spatial-summary">No comparison is available yet.</span><div><button id="spatial-export" disabled>Download query & results</button><button id="spatial-reload">Reload design sources</button></div></div>`;

  async function request(path, payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(path, {cache:'no-store', signal:controller.signal,
        ...(payload ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)} : {})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail?.message || `Design service returned ${response.status}`);
      return data;
    } finally { clearTimeout(timer); }
  }
  function safeScope(value) {
    if (value?.synthetic !== true || value.calibrated !== false || value.mutates_live_state !== false || value.physical_guidance !== false || value.live_state_bound !== false || value.forecast_coupled !== false || value.execution_authority !== 'none') {
      throw new Error('The read-only authored-design scope could not be verified.');
    }
    return value;
  }
  function identityMatches(a, b) {
    return ['graph_sha256','baseline_scene_sha256','baseline_geometry_sha256','baseline_graph_sha256','variant_layer_sha256','variant_evidence_sha256']
      .every(key => a?.[key] === b?.[key]) && hash(a?.graph_sha256) && hash(a?.baseline_scene_sha256);
  }
  function query(variant) {
    return {variant, origin:'ENTRY_GATE', destination:'FOOD_COURT',
      blocked_edges:variant==='dining_connection' && $('spatial-closed').checked ? ['dining_connector_link'] : [],
      accessible_only:$('spatial-accessible').checked, walking_speed_mps:1.2};
  }
  function inputs(disabled) {
    busy = disabled;
    for (const id of ['spatial-closed','spatial-accessible','spatial-reload']) $(id).disabled = disabled;
    $('spatial-compare').disabled = disabled || !capability || !variants.some(variant => stores[variant].graph);
    $('spatial-export').disabled = disabled || !complete;
  }
  function draw(variant) {
    const item = stores[variant], envelope = item.graph;
    if (!envelope) { $('spatial-graph-'+variant).innerHTML = '<p class="spatial-graph-unavailable">Verified graph unavailable</p>'; return; }
    const graph = envelope.graph, nodes = new Map(graph.nodes.map(node => [node.id,node]));
    // A matched plan-detail window around the actual entrance/dining coordinates.
    const xy = position => [70+(position[0]+43)*6.2, 25+(-15-position[1])*6.2];
    const inside = p => p[0]>=-43 && p[0]<=13 && p[1]>=-59 && p[1]<=-15;
    const current = item.result?.query || query(variant), path = new Set(item.result?.edge_ids || []);
    const edges = graph.edges.map(edge => {
      const a = nodes.get(edge.from)?.position_m, b = nodes.get(edge.to)?.position_m;
      if (!a || !b || (!inside(a) && !inside(b))) return '';
      const [x1,y1] = xy(a), [x2,y2] = xy(b);
      const excluded = edge.status !== 'walkable' || current.blocked_edges.includes(edge.id) || (current.accessible_only && !edge.modeled_step_free);
      const type = excluded ? 'excluded' : path.has(edge.id) ? 'route' : 'network';
      return `<line class="spatial-edge ${type}" data-edge-id="${esc(edge.id)}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"><title>${esc(edge.id)}${excluded?' · excluded from this query':''}${edge.reason?': '+esc(edge.reason):''}</title></line>`;
    }).join('');
    const destination = graph.asset_entrances.FOOD_COURT;
    const points = graph.nodes.filter(node => inside(node.position_m)).map(node => {
      const [x,y] = xy(node.position_m), endpoint = node.id === 'entry' || node.id === destination;
      return `<g><circle class="spatial-node ${endpoint?'endpoint':''}" cx="${x}" cy="${y}" r="${endpoint?5:3}"><title>${esc(node.id)}${node.note?': '+esc(node.note):''}</title></circle>${endpoint?`<text x="${x+(node.id==='entry'?12:-12)}" y="${y+(node.id==='entry'?5:-12)}" text-anchor="${node.id==='entry'?'start':'end'}">${node.id==='entry'?'Park entrance':variant==='baseline'?'Dining entrance':'New dining landing'}</text>`:''}</g>`;
    }).join('');
    const warning = current.accessible_only ? 'Entry threshold excluded' : current.blocked_edges.length ? 'Design connection closed' : variant==='baseline' ? 'Missing dining link' : 'New connection';
    $('spatial-graph-'+variant).innerHTML = `<svg viewBox="0 0 490 325" role="img" aria-label="${esc(names[variant])} authored graph detail"><defs><clipPath id="spatial-clip-${variant}"><rect x="10" y="10" width="470" height="305" rx="8"/></clipPath></defs><g clip-path="url(#spatial-clip-${variant})"><rect x="20" y="20" width="450" height="285" class="spatial-map-background"/>${edges}${points}<text class="spatial-map-label" x="28" y="37">${esc(warning)}</text></g></svg>`;
  }
  function render(variant) {
    const item = stores[variant], result = item.result;
    const target = $('spatial-result-'+variant);
    target.classList.toggle('reachable', result?.reachable === true);
    if (item.error) target.innerHTML = `<strong>Comparison unavailable</strong><small>${esc(item.error)}</small>`;
    else if (!result) target.innerHTML = '<strong>Ready to query</strong><small>Run the comparison with the selected constraints.</small>';
    else if (result.reachable) target.innerHTML = `<strong>Route exists in this design</strong><div class="spatial-metrics"><b>${Number(result.distance_m).toFixed(3)}<small>m · plan distance</small></b><b>${Number(result.assumed_walking_seconds).toFixed(2)}<small>s · at assumed 1.2 m/s</small></b></div>`;
    else target.innerHTML = '<strong>No route in this authored graph</strong><div class="spatial-metrics"><b>—<small>No finite distance or time</small></b></div>';
    const current = result?.query;
    $('spatial-note-'+variant).textContent = item.error ? 'No route or benefit is inferred from missing evidence.' : !result ? '' : current.accessible_only ? 'The park-entry threshold has no authored step-free transition. The dining connection does not resolve that entrance barrier.' : current.blocked_edges.length ? 'The query closes dining_connector_link. The underlying design and live park are unchanged.' : result.entrance_scope?.destination_note || result.reason;
    const identity = item.graph?.identity;
    $('spatial-identity-'+variant).innerHTML = identity ? `<span title="${esc(identity.graph_sha256)}">Graph ${short(identity.graph_sha256)}</span> · <span title="${esc(identity.baseline_scene_sha256)}">Scene ${short(identity.baseline_scene_sha256)}</span>${identity.variant_layer_sha256?` · <span title="${esc(identity.variant_layer_sha256)}">Design ${short(identity.variant_layer_sha256)}</span>`:''}<small>Verified at service installation · immutable design snapshot</small>` : 'Graph identity unavailable';
    draw(variant);
  }
  async function preview(variant, token) {
    const item = stores[variant], image = $('spatial-preview-'+variant), note = $('spatial-preview-note-'+variant);
    image.hidden = true;
    if (item.preview) URL.revokeObjectURL(item.preview);
    item.preview = null;
    if (!item.graph) { note.textContent = 'Native closeup unavailable: graph identity is missing.'; return; }
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch('/api/spatial/previews/'+variant, {cache:'no-store',signal:controller.signal});
      if (!response.ok) throw new Error('not available for this design');
      const headers = response.headers, identity = item.graph.identity;
      if (headers.get('X-Spatial-Graph-Sha256') !== identity.graph_sha256 || headers.get('X-Spatial-Scene-Sha256') !== identity.baseline_scene_sha256 || (headers.get('X-Spatial-Variant-Layer-Sha256')||'') !== (identity.variant_layer_sha256||'') || headers.get('X-Spatial-Preview-Mode') !== 'static_native' || !hash(headers.get('X-Spatial-Preview-Image-Sha256')) || !hash(headers.get('X-Spatial-Preview-Report-Sha256')) || !headers.get('Content-Type')?.startsWith('image/png')) throw new Error('source identity does not match the graph');
      const blob = await response.blob();
      let byteVerified = false;
      if (globalThis.crypto?.subtle) {
        const digest = await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
        const receivedHash = Array.from(new Uint8Array(digest),byte => byte.toString(16).padStart(2,'0')).join('');
        if (receivedHash !== headers.get('X-Spatial-Preview-Image-Sha256')) throw new Error('image bytes do not match their declared hash');
        byteVerified = true;
      }
      if (token !== generation) return;
      const url = URL.createObjectURL(blob); item.preview = url;
      image.onload = () => { if (token !== generation) return; image.hidden = false; note.textContent = `Static native design closeup · matched graph / scene identities · ${byteVerified?'image bytes checked in browser':'image integrity checked by service'} · does not depict query closures or the live camera`; };
      image.onerror = () => { image.hidden = true; note.textContent = 'Native closeup unavailable: image could not be decoded.'; };
      image.src = url;
    } catch(error) {
      if (token === generation) note.textContent = 'Native closeup unavailable: '+error.message+'. Graph query remains independent.';
    } finally { clearTimeout(timer); }
  }
  function summary() {
    complete = variants.every(variant => stores[variant].result && !stores[variant].error);
    $('spatial-summary').textContent = !complete ? 'Comparison incomplete. No cross-design conclusion is available.' : stores.dining_connection.result.reachable ? 'The added link connects the authored dining landing. No percentage time saving exists against an unreachable baseline.' : 'The selected constraints leave dining unreachable. No operating benefit is inferred.';
    $('spatial-status').textContent = complete ? 'Both design queries completed. No live state or forecast was changed.' : 'Some design evidence is unavailable. Reload sources to retry.';
  }
  async function compare(token = generation) {
    inputs(true); complete = false; $('spatial-export').disabled = true;
    $('spatial-status').textContent = 'Querying both authored designs…';
    await Promise.all(variants.map(async variant => {
      const item = stores[variant]; item.result = null;
      if (!item.graph) { render(variant); return; }
      item.error = null; render(variant);
      const sent = query(variant);
      try {
        const result = safeScope(await request('/api/spatial/route',sent));
        if (token !== generation) return;
        if (result.variant !== variant || !identityMatches(result.identity,item.graph.identity) || !result.query || ['variant','origin','destination','accessible_only','walking_speed_mps'].some(key => result.query[key] !== sent[key]) || JSON.stringify(result.query.blocked_edges) !== JSON.stringify(sent.blocked_edges) || typeof result.reachable !== 'boolean' || (result.reachable && (!Number.isFinite(result.distance_m) || !Number.isFinite(result.assumed_walking_seconds)))) throw new Error('Route identity or query context does not match the displayed design.');
        item.result = result;
      } catch(error) { if (token === generation) item.error = error.message; }
      if (token === generation) render(variant);
    }));
    if (token === generation) { summary(); inputs(false); }
  }
  async function load() {
    const token = ++generation; inputs(true); complete = false; capability = null;
    $('spatial-status').textContent = 'Loading verified design sources…';
    for (const variant of variants) { stores[variant].graph = null; stores[variant].result = null; stores[variant].error = null; $('spatial-preview-'+variant).hidden = true; $('spatial-preview-note-'+variant).textContent = 'Native closeup identity pending.'; render(variant); }
    try {
      capability = safeScope(await request('/api/spatial/capabilities'));
      await Promise.all(variants.map(async variant => {
        try {
          const envelope = safeScope(await request('/api/spatial/graphs/'+variant));
          const expected = capability.variants.find(item => item.variant===variant);
          if (envelope.variant !== variant || !identityMatches(envelope.identity,expected?.identity) || !Array.isArray(envelope.graph?.nodes) || !Array.isArray(envelope.graph?.edges) || envelope.graph.up_axis !== 'Z') throw new Error('Graph identity or coordinate system could not be associated.');
          stores[variant].graph = envelope;
        } catch(error) { stores[variant].error = error.message; }
        render(variant);
      }));
      // A single optional preview request per explicit source load; never polls.
      variants.forEach(variant => void preview(variant,token));
      await compare(token);
    } catch(error) {
      for (const variant of variants) { stores[variant].error = error.message; render(variant); }
      $('spatial-status').textContent = 'Design sources unavailable: '+error.message;
      $('spatial-summary').textContent = 'No comparison is available. Reload design sources to retry.';
      inputs(false);
    }
  }
  function changed() {
    if (busy) return;
    complete = false;
    for (const variant of variants) { stores[variant].result = null; if (stores[variant].graph) stores[variant].error = null; render(variant); }
    $('spatial-status').textContent = 'Inputs changed. Run Compare access to evaluate these constraints.';
    $('spatial-summary').textContent = 'Results cleared until the new query completes.';
    $('spatial-export').disabled = true;
  }
  $('spatial-closed').addEventListener('change',changed);
  $('spatial-accessible').addEventListener('change',changed);
  $('spatial-compare').addEventListener('click',() => { if (!busy) void compare(); });
  $('spatial-reload').addEventListener('click',() => { if (!busy) void load(); });
  $('spatial-export').addEventListener('click',() => {
    if (!complete || busy) return;
    const evidence = {schema_version:'aster.spatial-comparison.v1',exported_at:new Date().toISOString(),scope:'authored_design_not_live_guidance',forecast_coupled:false,mutates_live_state:false,comparisons:variants.map(variant => ({query:stores[variant].result.query,response:stores[variant].result}))};
    const url = URL.createObjectURL(new Blob([JSON.stringify(evidence,null,2)],{type:'application/json'}));
    const link = document.createElement('a');link.href=url;link.download='aster-dining-design-comparison.json';link.click();setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  document.addEventListener('park:state',event => {
    $('spatial-context').textContent = event.detail?.mode === 'replay' ? 'Operations is showing replay. This read-only query still concerns the separately authored design; it is not the recorded park or a replay forecast.' : 'Authored design query · independent of live conditions and operational forecasts · no physical guidance.';
  });
  void load();
})();
