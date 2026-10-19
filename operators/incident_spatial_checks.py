#!/usr/bin/env python3
"""Independent HTTP-only current-incident and spatial design contract review."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import socket
import time
import urllib.error
import urllib.request
from api_operator import asset, require, utc
from workflow_checks import Gateway, Review


def direct(r, label, **extras):
    payload = {'asset_id': 'RIDE_COASTER', 'request_id': r.run_id+':direct:'+label,
               'ttl_seconds': 120, **extras}
    return r.http.call('/api/workflows/incidents', payload)['proposal'], payload


def fault(r):
    r.reset('normal')
    r.ingest('ride_scada', 'status', 'fault')


def direct_success(r):
    fault(r)
    bundles = r.http.call('/api/planning/evidence')['total']
    p, body = direct(r, 'no-plan')
    observation = p['creation_observation']
    require(p['origin'] == 'current_incident' and p['precondition_scope'] == 'target', 'Wrong direct scope')
    require(observation['scenario_context'] == 'normal' and observation['fields']['status']['value'] == 'fault', 'Fault under normal not captured')
    require(p['evidence_refs']['historical_evidence_is_authority'] is False, 'Historical authority claimed')
    with ThreadPoolExecutor(max_workers=3) as pool:
        retries = list(pool.map(lambda _: r.http.call('/api/workflows/incidents', body), range(3)))
    require(all(x['proposal'] == p and x['idempotency']['replayed'] for x in retries), 'Creation retry changed proposal')
    audit = r.http.call('/api/audit')['events']
    with ThreadPoolExecutor(max_workers=3) as pool:
        executions = list(pool.map(lambda _: r.execute(p, 'direct-no-plan'), range(3)))
    first = executions[0]
    require(all(x['proposal']['receipt'] == first['proposal']['receipt'] for x in executions), 'Concurrent receipt mismatch')
    require(sum(not x['idempotency']['replayed'] for x in executions) == 1, 'More than one acceptance')
    require(first['outcome'] == 'accepted_workflow_not_repair' and not first['physical_effect'], 'Claimed repair')
    require(first['proposal']['readback']['asset_status'] == 'fault', 'Dispatch removed fault')
    require(len(r.http.call('/api/audit')['events']) == len(audit)+1, 'Duplicate command audit')
    require(r.http.call('/api/planning/evidence')['total'] == bundles, 'Direct workflow created planner evidence')
    reopened = r.http.call('/api/workflows/proposals/'+p['id'])['proposal']
    require(reopened['creation_observation'] == observation, 'Creation evidence changed after execute')
    r.gateway.stop(); r.gateway.start()
    recovered = r.http.call('/api/workflows/proposals/'+p['id'])['proposal']
    require(recovered['creation_observation'] == observation and recovered['receipt'] == first['proposal']['receipt'], 'Restart changed frozen evidence/receipt')
    return {'proposal': p, 'accepted': first, 'concurrent_retries': 3, 'restart_preserved_evidence': True, 'planner_calls_required': 0}


def unrelated_scenario(r):
    fault(r)
    p, _ = direct(r, 'scenario-change')
    r.http.call('/api/scenarios', {'scenario': 'food_rush'})
    current = asset(r.http.call('/api/state'), 'RIDE_COASTER')
    require(current['status'] == 'fault', 'Fixture changed target status')
    accepted = r.execute(p, 'scenario-change')
    require(accepted['proposal']['creation_observation'] == p['creation_observation'], 'Scenario change rewrote creation evidence')
    return {'created_scenario': 'normal', 'execution_scenario': 'food_rush', 'accepted': accepted}


def optional_rationale(r):
    r.reset('normal'); bundle = r.evidence('ride_closure')
    r.ingest('ride_scada', 'status', 'fault')
    p, body = direct(r, 'rationale', rationale_bundle_id=bundle)
    require(p['evidence_refs']['historical_evidence_is_authority'] is False, 'Rationale grants authority')
    require(p['creation_observation']['scenario_context'] == 'normal', 'Historical scenario became current context')
    r.ingest('ride_scada', 'status', 'operational')
    blocked = r.execute(p, 'rationale', 409)
    fault(r)
    missing = r.http.call('/api/workflows/incidents', {**body, 'request_id': body['request_id']+'-missing', 'rationale_bundle_id': '0'*64}, 404)
    return {'rationale_bundle_id': bundle, 'proposal': p, 'changed_current_status_rejected': blocked, 'missing_rationale': missing,
            'limit': 'Historical scenario mismatch tested; old-model persisted bundle not constructed through storage or backend access.'}


def stale_required(r):
    fault(r); p, body = direct(r, 'stale')
    before = asset(r.http.call('/api/state'), 'RIDE_COASTER')['data_quality']['fields']['status']
    began = time.monotonic(); time.sleep(float(before['stale_after_seconds'])+1.1)
    after = asset(r.http.call('/api/state'), 'RIDE_COASTER')['data_quality']['fields']['status']
    require(after['status'] == 'stale', 'Target source did not become stale')
    rejected = r.execute(p, 'stale', 409)
    create = r.http.call('/api/workflows/incidents', {**body, 'request_id': body['request_id']+'-new'}, 409)
    return {'wait_seconds': time.monotonic()-began, 'canonical_status_quality': after, 'execute': rejected, 'create': create}


def unrelated_stale(r):
    r.reset('ride_closure')
    r.http.call('/api/connectors/erp/simulation', {'mode': 'paused'})
    # Maintenance sources keep advancing while only unrelated ERP expires.
    time.sleep(6.2)
    state = r.http.call('/api/state')
    p, _ = direct(r, 'stale-erp')
    accepted = r.execute(p, 'stale-erp')
    r.fault_readback(accepted)
    r.http.call('/api/connectors/erp/simulation', {'mode': 'live'})
    return {'accepted': accepted, 'connector_health': state['connector_health']}


def relevant_changes(r):
    fault(r); p, body = direct(r, 'changed-status')
    r.ingest('ride_scada', 'status', 'operational')
    status = r.execute(p, 'changed-status', 409)
    fault(r); p, body = direct(r, 'existing-order')
    dispatched = r.http.call('/api/actions', {'action': 'dispatch_maintenance', 'asset_id': 'RIDE_COASTER', 'request_id': r.run_id+':legacy'})
    order_id = dispatched['result']['work_order_id']
    conflict = r.execute(p, 'existing-order', 409)
    require(order_id in conflict['detail']['context']['current_work_order_ids'], 'Conflict lacks exact order')
    create = r.http.call('/api/workflows/incidents', {**body, 'request_id': body['request_id']+'-new'}, 409)
    detail = r.http.call(conflict['detail']['context']['asset_detail_url'])
    require(sum(w['status'] == 'open' for w in detail['work_orders']) == 1, 'Rejected dispatch duplicated orders')
    return {'status_change': status, 'existing_order_execution': conflict, 'existing_order_creation': create, 'exact_order_id': order_id}


def cross_origin_saved_replay(r):
    r.reset('ride_closure'); bundle = r.evidence()
    p, direct_body = direct(r, 'cross-origin')
    saved_body = r.payload(bundle, 'cross-origin'); saved_body['request_id'] = direct_body['request_id']
    conflict_one = r.http.call('/api/workflows/proposals', saved_body, 409)
    saved_body['request_id'] += '-saved'
    saved = r.http.call('/api/workflows/proposals', saved_body)['proposal']
    conflict_two = r.http.call('/api/workflows/incidents', {**direct_body, 'request_id': saved_body['request_id']}, 409)
    timeline = r.http.call('/api/timeline?limit=1')
    r.http.call('/api/view', {'mode': 'replay', 'snapshot_id': timeline['snapshots'][0]['id']})
    replay = r.http.call('/api/workflows/incidents', direct_body, 409)
    r.execute(p, 'replay', 409)
    r.http.call('/api/workflows/proposals/'+p['id'])
    r.http.call('/api/view', {'mode': 'live'})
    accepted = r.execute(saved, 'saved-regression'); r.fault_readback(accepted)
    require(saved['origin'] == 'saved_plan' and saved['precondition_scope'] == 'scenario_and_target', 'Saved flow lost scenario scope')
    return {'direct_to_saved_collision': conflict_one, 'saved_to_direct_collision': conflict_two,
            'direct_replay_guard': replay, 'saved_flow_acceptance': accepted}


def strict_incidents(r):
    fault(r)
    body = {'asset_id': 'RIDE_COASTER', 'request_id': r.run_id+':invalid', 'ttl_seconds': 120}
    cases = [dict(body, action='reopen_ride'), dict(body, asset_id='FOOD_COURT'), dict(body, ttl_seconds=29),
             dict(body, ttl_seconds=301), dict(body, request_id=''), dict(body, unknown=True)]
    return [r.http.call('/api/workflows/incidents', b, 422) for b in cases]


def route(r, **kwargs):
    return r.http.call('/api/spatial/route', {'origin': 'ENTRY_GATE', 'destination': 'FOOD_COURT', **kwargs})


def spatial_routes(r):
    r.reset('normal')
    audit = r.http.call('/api/audit')['events']; state = r.http.call('/api/state')
    cases = {'baseline': route(r), 'variant': route(r, variant='dining_connection'),
        'closure': route(r, variant='dining_connection', blocked_edges=['dining_connector_link']),
        'accessible': route(r, variant='dining_connection', accessible_only=True),
        'wheel_approach': route(r, destination='RIDE_WHEEL'), 'wheel_boarding': route(r, destination='wheel_boarding'),
        'slow': route(r, variant='dining_connection', walking_speed_mps=.6)}
    for name in ['baseline', 'closure', 'accessible', 'wheel_boarding']:
        x = cases[name]
        require(not x['reachable'] and x['distance_m'] is None and not x['edge_ids'], name+' invented a route')
    v = cases['variant']; require(v['reachable'] and abs(v['distance_m']-40.852) < .001, 'Variant distance mismatch')
    require(cases['wheel_approach']['reachable'], 'Wheel public approach absent')
    require(cases['slow']['distance_m'] == v['distance_m'] and cases['slow']['edge_ids'] == v['edge_ids'], 'Speed changed geometry')
    require(abs(cases['slow']['assumed_walking_seconds']-2*v['assumed_walking_seconds']) < .02, 'Speed/time mismatch')
    for x in cases.values():
        require(x['execution_authority'] == 'none' and not x['forecast_coupled'] and not x['mutates_live_state'], 'Spatial authority claim')
    require(r.http.call('/api/audit')['events'] == audit, 'Spatial requests wrote audit')
    require(r.http.call('/api/state')['scenario'] == state['scenario'], 'Spatial query changed scenario')
    timeline = r.http.call('/api/timeline?limit=1')
    r.http.call('/api/view', {'mode': 'replay', 'snapshot_id': timeline['snapshots'][0]['id']})
    before = r.http.call('/api/view/state')
    replay_route = route(r, variant='dining_connection')
    after = r.http.call('/api/view/state')
    require(before['view'] == after['view'] and before['assets'] == after['assets'] and before['kpis'] == after['kpis'], 'Spatial request changed replay view')
    require(replay_route == v, 'Authored design query coupled to replay view')
    require(r.http.call('/api/audit')['events'] == audit, 'Replay spatial query wrote audit')
    r.http.call('/api/view', {'mode': 'live'})
    return {'routes': cases, 'replay_view': before['view'], 'no_live_scenario_audit_or_replay_mutation': True}


def spatial_identities(r):
    files = {'baseline_graph_sha256': 'assets/circulation_graph.json', 'baseline_scene_sha256': 'assets/park.usdc',
             'baseline_geometry_sha256': 'assets/park.usda', 'variant_layer_sha256': 'assets/variants/dining_connection.usda',
             'variant_evidence_sha256': 'assets/variants/dining_connection_evidence.json'}
    hashes = {k: hashlib.sha256((r.gateway.project/v).read_bytes()).hexdigest() for k,v in files.items()}
    caps = r.http.call('/api/spatial/capabilities')
    graphs = {}
    for variant, filename in [('baseline','assets/circulation_graph.json'), ('dining_connection','assets/variants/dining_circulation_graph.json')]:
        response = r.http.call('/api/spatial/graphs/'+variant); graphs[variant] = response
        identity = response['identity']
        require(identity['graph_sha256'] == hashlib.sha256((r.gateway.project/filename).read_bytes()).hexdigest(), 'Graph file hash differs')
        for key, value in hashes.items():
            if variant == 'baseline' and key.startswith('variant_'): continue
            require(identity[key] == value, 'Artifact identity mismatch '+key)
        require(identity['verification'] == 'verified_at_installation' and identity['snapshot_policy'] == 'immutable_until_restart', 'Verification scope absent')
        require(response['graph'] == json.loads((r.gateway.project/filename).read_text()), 'Graph differs from hashed artifact')
        require(identity == next(v['identity'] for v in caps['variants'] if v['variant'] == variant), 'Capabilities identity mismatch')
    return {'identities': {k:v['identity'] for k,v in graphs.items()}, 'file_sha256': hashes}


def raw(r, body, status, media='application/json'):
    request = urllib.request.Request(r.gateway.url+'/api/spatial/route', data=body, headers={'Content-Type':media}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=10) as response: actual, data = response.status, response.read()
    except urllib.error.HTTPError as error: actual, data = error.code, error.read()
    parsed = json.loads(data)
    record = {'utc':utc(), 'method':'POST', 'path':'/api/spatial/route', 'status':actual,
              'request_bytes':len(body), 'request_sha256':hashlib.sha256(body).hexdigest(), 'response':parsed}
    r.journal(record); require(actual == status, f'Raw spatial request expected {status}, got {actual}')
    return record


def spatial_strict(r):
    base = {'origin':'ENTRY_GATE','destination':'FOOD_COURT'}
    cases = [dict(base, variant='other'), dict(base, origin='../etc/passwd'), dict(base, destination='UNKNOWN'),
        dict(base, accessible_only='false'), dict(base, walking_speed_mps='1.2'), dict(base, walking_speed_mps=True),
        dict(base, walking_speed_mps=.29), dict(base, walking_speed_mps=2.51), dict(base, activate=True),
        dict(base, blocked_edges=['UNKNOWN']), dict(base, blocked_edges=['entry_main','entry_main']),
        dict(base, blocked_edges=['edge'+str(i) for i in range(33)])]
    results = [r.http.call('/api/spatial/route', case, 422) for case in cases]
    raw_cases = [(b'{"origin":"ENTRY_GATE","origin":"entry","destination":"FOOD_COURT"}',422,'application/json'),
        (b'{"origin":"ENTRY_GATE","destination":"FOOD_COURT","walking_speed_mps":NaN}',422,'application/json'),
        (b'{',422,'application/json'), (json.dumps(base).encode(),415,'text/plain'), (b' '*16385,413,'application/json')]
    return {'strict_json_cases':len(cases), 'responses':results, 'raw_cases':[raw(r,*case) for case in raw_cases]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True);parser.add_argument('--python',required=True)
    parser.add_argument('--port',type=int,default=18150);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);probe.bind(('127.0.0.1',args.port))
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    gateway=Gateway(args.project,args.python,args.port,out);r=Review(gateway,out);started=utc()
    sources = {str(p.relative_to(gateway.project)):hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ['backend/spatial','assets/variants'] for p in (gateway.project/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    try:
        gateway.start()
        for fn in [direct_success,unrelated_scenario,optional_rationale,stale_required,unrelated_stale,
                   relevant_changes,cross_origin_saved_replay,strict_incidents,spatial_routes,spatial_identities,spatial_strict]:
            r.check(fn.__name__,lambda fn=fn:fn(r))
        r.check('cleanup',lambda:r.reset('normal'))
    finally:
        cleanup=gateway.stop()
        report={'started_at':started,'finished_at':utc(),'url':gateway.url,'checks':r.results,
            'failures':sum(c['status']!='pass' for c in r.results),'gateway_starts':gateway.starts,
            'process_cleanup':cleanup,'additional_source_sha256':sources,
            'client_source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('workflow_checks.py'),Path(__file__).with_name('api_operator.py')]},
            'scope':'Independent actual HTTP and owned process lifecycle; isolated four databases; no backend imports or database manipulation. Old-model stored rationale remains a separate coverage limit.'}
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(1 if report['failures'] else 0)

if __name__=='__main__':main()
