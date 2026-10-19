"""Planner contract checks driven only through the HTTP operator interface."""
from datetime import datetime, timezone
from api_operator import require, asset


def branches(plan):
    return {item['id']: item for item in plan['branches']}


def run(evaluator):
    http = evaluator.http
    evaluator.action('reset')
    capabilities = http.call('/api/planning/capabilities')
    require(capabilities['model']['calibrated'] is False, 'Planner lacks calibration disclosure')
    state = evaluator.state()
    revision = state['accepted_state_revision']
    audit = http.call('/api/audit')['events']
    base_request = {'scenario': 'food_rush', 'horizon_minutes': 60, 'expected_state_revision': revision}
    first = http.call('/api/planning/simulate', base_request)
    again = http.call('/api/planning/simulate', base_request)
    require(first['input']['state_revision'] == revision, 'Planner did not use frozen requested revision')
    require(first['plan_id'] == again['plan_id'], 'Frozen input changed plan identity')
    require(first['branches'] == again['branches'], 'Frozen input changed predicted branches')
    require(first['mutates_live_state'] is False and first['physical_effect'] is False, 'Planner claims side effects')
    require(first['decision']['auto_execute'] is False, 'Planner auto-executes')
    require(evaluator.state()['scenario'] == state['scenario'], 'Planning changed live scenario')
    require(http.call('/api/audit')['events'] == audit, 'Planning wrote action audit')
    b = branches(first)
    require('baseline' in b and 'simple_rule' in b, 'Missing baseline policies')
    factors = b['baseline']['sensitivity']
    for branch in b.values():
        for case, result in branch['sensitivity'].items():
            require(result['demand_factor'] == factors[case]['demand_factor'], 'Alternatives have unequal demand factors')
            conservation = result['conservation']
            summary = result['summary']
            residual = conservation['initial_queue_guests'] + conservation['arrivals'] - summary['served_guests'] - summary['unserved_guests']
            require(abs(residual) < .01 and abs(conservation['residual_guests']) < .01, 'Demand silently disappears')
        if not branch['constraints']['feasible']:
            require(branch['id'] not in first['decision']['shortlist'], 'Infeasible plan shortlisted')
    no_op = http.call('/api/planning/simulate', {**base_request,
        'candidates': [{'id': 'noop', 'label': 'Explicit no action', 'actions': []}]})
    no_op_branches = branches(no_op)
    require(no_op_branches['noop']['summary'] == no_op_branches['baseline']['summary'], 'Explicit no-op differs from baseline')
    require(no_op_branches['noop']['trajectory'] == no_op_branches['baseline']['trajectory'], 'No-op trajectory differs')
    zero_staff = http.call('/api/planning/simulate', {**base_request,
        'assumptions': {'available_qualified_staff': 0},
        'candidates': [{'id': 'staff', 'label': 'Unavailable staffing',
            'actions': [{'action': 'add_staff', 'asset_id': 'FOOD_COURT', 'at_minute': 0}]}]})
    require(not branches(zero_staff)['staff']['constraints']['feasible'], 'Unavailable staff was treated as feasible')
    require('staff' not in zero_staff['decision']['shortlist'], 'Unavailable staff entered shortlist')
    late = http.call('/api/planning/simulate', {**base_request,
        'candidates': [{'id': 'late', 'label': 'Staff arrives after horizon',
            'actions': [{'action': 'add_staff', 'asset_id': 'FOOD_COURT', 'at_minute': 55}]}]})
    late_branches = branches(late)
    for key in ['served_guests', 'unserved_guests', 'queue_guest_minutes']:
        require(late_branches['late']['summary'][key] == late_branches['baseline']['summary'][key], 'Delayed staff has premature modeled benefit')
    require(late['decision'].get('preferred_policy') == 'baseline' and late['decision'].get('outcome') == 'no_intervention_benefit' and 'late' not in late['decision']['shortlist'],
        'Do-nothing did not dominate costly post-horizon staffing')
    compliance = http.call('/api/planning/simulate', {**base_request,
        'assumptions': {'routing_compliance_pct': 0},
        'candidates': [{'id': 'ignored-guidance', 'label': 'Guests ignore guidance',
            'actions': [{'action': 'reroute_guests', 'asset_id': 'RIDE_WHEEL', 'at_minute': 0}]}]})
    cb = branches(compliance)
    require(cb['ignored-guidance']['summary'] == cb['baseline']['summary'], 'Zero-compliance guidance manufactures benefit')
    for payload in [{**base_request, 'horizon_minutes': 1},
                    {**base_request, 'scenario': 'unbounded_optimization'},
                    {**base_request, 'candidates': [{'id': 'invalid', 'label': 'Invalid action', 'actions': [{'action': 'open_ride', 'asset_id': 'RIDE_COASTER'}]}]}]:
        http.call('/api/planning/simulate', payload, 422)
    # Replay must reject branch requests even though planning itself is read-only.
    recorded = http.call('/api/timeline?limit=1')['snapshots'][0]['id']
    http.call('/api/view', {'mode': 'replay', 'snapshot_id': recorded})
    http.call('/api/planning/simulate', base_request, 409)
    http.call('/api/view', {'mode': 'live'})
    return {'plan_id': first['plan_id'], 'frozen_revision': revision,
        'branches': [{k: v[k] for k in ['id', 'summary', 'constraints', 'deltas_vs_baseline', 'tradeoffs']} for v in first['branches']],
        'decision': first['decision'], 'countercontrols': ['no-op', 'zero-qualified-staff', 'post-horizon-staff', 'zero-routing-compliance', 'shared-demand', 'demand-conservation'],
        'value_scope': 'Internal model and contract consistency, not calibrated benefit or LLM reasoning.'}


def degraded_input(evaluator):
    """Use actual connector ingestion to test planner input provenance and abstention."""
    import time
    http = evaluator.http
    evaluator.action('reset')
    erp_path = '/api/connectors/erp'
    http.call(erp_path + '/simulation', {'mode': 'paused'})
    erp_event = {'event_id': f'{evaluator.run_id}:{evaluator.cycle}:planner-stock',
        'source_asset_id': 'erp/FOOD_COURT', 'metric': 'erp.stock_units', 'value': 7,
        'unit': 'items', 'source_timestamp': datetime.now(timezone.utc).isoformat()}
    accepted = http.call(erp_path + '/ingest', {'synthetic': True, 'events': [erp_event]})
    require(accepted['accepted'] == 1, 'Planner stock fixture rejected')
    stock_state = evaluator.state()
    stock_plan = http.call('/api/planning/simulate', {'scenario': 'normal', 'horizon_minutes': 15,
        'expected_state_revision': stock_state['accepted_state_revision']})
    require(branches(stock_plan)['baseline']['trajectory'][0]['food_stock_units'] == 7,
        'Planner ignores accepted canonical stock value')
    http.call(erp_path + '/simulation', {'mode': 'live'})
    path = '/api/connectors/water'
    http.call(path + '/simulation', {'mode': 'paused'})
    event = {'event_id': f'{evaluator.run_id}:{evaluator.cycle}:planner-flow',
        'source_asset_id': 'water/WATER_PLANT', 'metric': 'water_lpm', 'value': 701,
        'unit': 'L/min', 'source_timestamp': datetime.now(timezone.utc).isoformat()}
    response = http.call(path + '/ingest', {'synthetic': True, 'events': [event]})
    require(response['accepted'] == 1, 'Planner fixture observation rejected')
    state = evaluator.state()
    require(asset(state, 'WATER_PLANT')['water_lpm'] == 701, 'Fixture not canonical')
    fresh = http.call('/api/planning/simulate', {'scenario': 'water_leak', 'horizon_minutes': 60,
        'expected_state_revision': state['accepted_state_revision']})
    require(fresh['input']['state_revision'] == state['accepted_state_revision'], 'Injected canonical revision was ignored')
    deadline = time.monotonic() + 9
    while time.monotonic() < deadline:
        if asset(evaluator.state(), 'WATER_PLANT')['data_quality']['fields']['water_lpm']['status'] == 'stale':
            break
        time.sleep(.5)
    old_frozen = http.call('/api/planning/simulate', {'scenario': 'water_leak', 'horizon_minutes': 60,
        'expected_state_revision': state['accepted_state_revision']})
    require(old_frozen['decision']['status'] == 'insufficient_data' and not old_frozen['decision']['shortlist'],
        'Retained formerly-good input bypassed request-time freshness')
    require(old_frozen['branches'] == fresh['branches'], 'Frozen branches changed when only input age changed')
    stale_state = evaluator.state()
    require(asset(stale_state, 'WATER_PLANT')['data_quality']['fields']['water_lpm']['status'] == 'stale', 'Fixture did not become stale')
    stale = http.call('/api/planning/simulate', {'scenario': 'water_leak', 'horizon_minutes': 60,
        'expected_state_revision': stale_state['accepted_state_revision']})
    require(stale['decision']['status'] == 'insufficient_data', 'Planner did not abstain on stale relevant source')
    require(not stale['decision']['shortlist'], 'Stale-data recommendation was shortlisted')
    http.call(path + '/simulation', {'mode': 'live'})
    return {'injected_stock_units': 7, 'stock_plan_id': stock_plan['plan_id'], 'fresh_input': fresh['input'], 'stale_input': stale['input'], 'stale_decision': stale['decision'], 'aged_frozen_decision': old_frozen['decision']}


def assumption_stress(evaluator):
    """Client-selected sensitivity cases, not held-out real observations or validation."""
    http = evaluator.http
    evaluator.action('reset')
    cases = [
        {'arrival_multiplier': .35, 'routing_compliance_pct': 0, 'available_qualified_staff': 0},
        {'arrival_multiplier': 1.7, 'routing_compliance_pct': 0, 'available_qualified_staff': 2},
        {'arrival_multiplier': 1.3, 'routing_compliance_pct': 60, 'available_qualified_staff': 2},
        {'arrival_multiplier': .8, 'routing_compliance_pct': 100, 'available_qualified_staff': 4}]
    evidence = []
    for scenario in ['food_rush', 'show_surge', 'heatwave']:
        for assumptions in cases:
            revision = evaluator.state()['accepted_state_revision']
            plan = http.call('/api/planning/simulate', {'scenario': scenario, 'horizon_minutes': 45,
                'expected_state_revision': revision, 'assumptions': assumptions})
            for branch in plan['branches']:
                for case in branch['sensitivity'].values():
                    result, conservation = case['summary'], case['conservation']
                    residual = conservation['initial_queue_guests']+conservation['arrivals']-result['served_guests']-result['unserved_guests']
                    require(abs(residual) < .01, 'Demand conservation fails under client-selected assumptions')
                require(branch['constraints']['feasible'] or branch['id'] not in plan['decision']['shortlist'],
                    'Infeasible branch recommended in assumption stress')
            evidence.append({'scenario': scenario, 'assumptions': assumptions, 'plan_id': plan['plan_id'],
                'decision': plan['decision'], 'outcomes': [{'id': b['id'], 'summary': b['summary'],
                    'constraints': b['constraints']} for b in plan['branches']]})
    return {'cases': evidence, 'scope': 'Independent client-selected assumption stress; not held-out empirical data, calibrated forecast skill, or causal value.'}
