#!/usr/bin/env python3
"""Independent one-minute food-service policy stress test; no planner imports."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import uuid
from api_operator import HTTP, require, asset, utc

HORIZON = 60
SCHEDULES = {'baseline': (), 'stock': ('replenish_stock',),
             'staff': ('add_staff',), 'both': ('replenish_stock', 'add_staff')}
PROFILES = {
    'canceled_rush': [.20]*60,
    'sustained': [.90]*60,
    'early_burst': [1.80]*20+[.45]*40,
    'late_burst': [.45]*40+[1.80]*20,
}
SPEC = {'version': '1.0', 'horizon_minutes': HORIZON, 'step_minutes': 1,
    'initial_variants': ['low_stock_short_staff', 'low_stock_covered', 'full_stock_short_staff'],
    'schedules': SCHEDULES, 'arrival_profiles_service_multipliers': PROFILES,
    'staff_effect_fractions': [0, .05, .15], 'staff_delay_minutes': [10, 20, 30],
    'delivery_delay_minutes': [20, 40, None], 'stock_order_units': 300,
    'extra_staff': 2, 'staff_cost_eur_per_hour': 28,
    'policy_selection': 'explicit planner preferred baseline; otherwise minimum predicted queue guest-minutes, labor cost, action count, id among feasible shortlisted candidates',
    'scope': 'Independent synthetic assumption stress, not empirical validation or a business score.'}


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def evaluate(initial, schedule_id, arrivals, staff_effect, staff_delay, delivery_delay):
    """One-minute queue + service + stock balances; independent of planner equations."""
    actions = SCHEDULES[schedule_id]
    rate = initial['throughput_per_hour']/60
    queue = initial['queue_minutes']*rate
    initial_queue = queue
    stock = float(initial['stock_units'])
    initial_stock = stock
    served = waiting = delivered = 0.0
    trajectory = []
    for minute, incoming in enumerate(arrivals):
        if 'replenish_stock' in actions and delivery_delay == minute:
            receipt = min(300, max(0, initial['stock_capacity']-stock))
            stock += receipt
            delivered += receipt
        capacity = rate
        if 'add_staff' in actions and minute >= staff_delay:
            capacity *= 1+staff_effect
        before = queue
        queue += incoming
        completed = min(queue, capacity, stock)
        served += completed
        stock -= completed
        queue -= completed
        waiting += (before+queue)/2
        trajectory.append({'minute': minute+1, 'queue': queue, 'stock': stock,
            'arrivals': incoming, 'served': completed, 'capacity': capacity})
    visit_residual = initial_queue+sum(arrivals)-served-queue
    stock_residual = initial_stock+delivered-served-stock
    require(abs(visit_residual) < 1e-7 and abs(stock_residual) < 1e-7,
        'Independent evaluator violates visit or stock conservation')
    return {'queue_guest_minutes': waiting, 'served_visits': served, 'residual_visits': queue,
        'labor_eur': 56.0 if 'add_staff' in actions else 0.0,
        'stock_remaining': stock, 'stock_delivered': delivered, 'command_count': len(actions),
        'visit_conservation_residual': visit_residual, 'stock_conservation_residual': stock_residual,
        'trajectory': trajectory}


def dominates(left, right, epsilon=1e-7):
    better_or_equal = left['queue_guest_minutes'] <= right['queue_guest_minutes']+epsilon and left['served_visits'] >= right['served_visits']-epsilon and left['labor_eur'] <= right['labor_eur']+epsilon
    strictly = left['queue_guest_minutes'] < right['queue_guest_minutes']-epsilon or left['served_visits'] > right['served_visits']+epsilon or left['labor_eur'] < right['labor_eur']-epsilon
    return better_or_equal and strictly


def equal_effect(left, right):
    return all(abs(left[k]-right[k]) < 1e-7 for k in ['queue_guest_minutes', 'served_visits', 'labor_eur'])


def simple_rule(initial):
    stock = initial['stock_units'] < initial['queue_minutes']*initial['throughput_per_hour']/60 + .9*initial['throughput_per_hour']
    staff = initial['on_duty'] < initial['required']
    return 'both' if stock and staff else 'stock' if stock else 'staff' if staff else 'baseline'


def planner_selection(plan):
    if plan['decision'].get('preferred_policy') == 'baseline':
        return 'baseline'
    require(plan['decision']['status'] != 'insufficient_data', 'Planner abstained; do not invent a recommendation')
    shortlist = plan['decision']['shortlist']
    candidates = [b for b in plan['branches'] if b['id'] in shortlist and b['constraints']['feasible']]
    require(candidates, 'Planner has no explicit usable shortlist or preferred baseline')
    choice = min(candidates, key=lambda b: (b['summary']['queue_guest_minutes'],
        b['summary']['staff_cost_eur'], len(b['action_schedule']), b['id']))
    return choice['id']


def collect_inputs(http, run_id):
    health = http.call('/api/health')
    require(health.get('synthetic') is True, 'Refusing non-synthetic gateway')
    http.synthetic_verified = True
    http.call('/api/view', {'mode': 'live'})
    base_state = http.call('/api/scenarios', {'scenario': 'food_rush'})
    seed = asset(base_state, 'FOOD_COURT')
    baseline = {'throughput_per_hour': seed['throughput_per_hour'], 'queue_minutes': seed['queue_minutes'],
        'stock_units': seed['erp']['stock_units'], 'stock_capacity': seed['erp']['stock_capacity'],
        'on_duty': seed['staff']['on_duty'], 'required': seed['staff']['required']}
    inputs = []
    for index, name in enumerate(SPEC['initial_variants']):
        # Each fixture starts from a fresh scenario, then receives accepted source values.
        for source in ['erp', 'workforce', 'vision']:
            http.call('/api/connectors/'+source+'/simulation', {'mode': 'live'})
        http.call('/api/scenarios', {'scenario': 'food_rush'})
        initial = dict(baseline)
        if name == 'low_stock_covered':
            initial['on_duty'] = initial['required']
        elif name == 'full_stock_short_staff':
            initial['stock_units'] = initial['stock_capacity']
        mappings = {'erp': [('erp.stock_units', initial['stock_units'], 'items'),
                            ('throughput_per_hour', initial['throughput_per_hour'], 'people/h')],
                    'workforce': [('staff.on_duty', initial['on_duty'], 'people')],
                    'vision': [('queue_minutes', initial['queue_minutes'], 'min')]}
        for source, fields in mappings.items():
            http.call('/api/connectors/'+source+'/simulation', {'mode': 'paused'})
            events = [{'event_id': f'{run_id}:{index}:{source}:{metric}',
                'source_asset_id': source+'/FOOD_COURT', 'metric': metric, 'value': value,
                'unit': unit, 'source_timestamp': utc()} for metric, value, unit in fields]
            accepted = http.call('/api/connectors/'+source+'/ingest', {'synthetic': True, 'events': events})
            require(accepted['accepted'] == len(events), f'{source} fixture was not accepted')
        state = http.call('/api/state')
        frozen = asset(state, 'FOOD_COURT')
        require(frozen['erp']['stock_units'] == initial['stock_units'] and frozen['staff']['on_duty'] == initial['on_duty'] and frozen['queue_minutes'] == initial['queue_minutes'], 'Canonical fixture mismatch')
        request = {'scenario': 'normal', 'horizon_minutes': 60,
            'expected_state_revision': state['accepted_state_revision'],
            'candidates': [{'id': name, 'label': name, 'actions': [{'action': action, 'asset_id': 'FOOD_COURT', 'at_minute': 0} for action in actions]}
                for name, actions in SCHEDULES.items() if name != 'baseline']}
        plan = http.call('/api/planning/simulate', request)
        inputs.append({'variant': name, 'initial': initial, 'state_revision': state['accepted_state_revision'],
            'planner_request': request, 'planner_response': plan,
            'policies': {'do_nothing': 'baseline', 'simple_rule': simple_rule(initial),
                         'planner_selected': planner_selection(plan)}})
    return health, inputs



def analytical_checks():
    initial = {'throughput_per_hour': 60, 'queue_minutes': 0,
        'stock_units': 100, 'stock_capacity': 600}
    steady = evaluate(initial, 'baseline', [1]*60, .15, 10, 20)
    require(steady['served_visits'] == 60 and steady['queue_guest_minutes'] == 0
        and steady['stock_remaining'] == 40, 'Steady service analytical check failed')
    delayed = evaluate({**initial, 'stock_units': 0}, 'stock', [1]*60, 0, 10, 20)
    require(delayed['served_visits'] == 40 and delayed['residual_visits'] == 20
        and delayed['queue_guest_minutes'] == 1000, 'Delayed supply analytical check failed')
    redundant_staff = evaluate(initial, 'staff', [1]*60, 0, 10, 20)
    require(dominates(steady, redundant_staff), 'Zero-effect staffing should lose to baseline')
    unavailable = evaluate({**initial, 'stock_units': 0}, 'stock', [1]*60, 0, 10, None)
    require(unavailable['served_visits'] == 0 and unavailable['residual_visits'] == 60
        and unavailable['queue_guest_minutes'] == 1800, 'Unavailable supply analytical check failed')
    return ['steady service exact balance', 'delayed supply known backlog integral',
        'zero-effect staff baseline dominance', 'unavailable supply full demand conservation']


def summarize(records):
    summaries = {}
    for policy in ['do_nothing', 'simple_rule', 'planner_selected']:
        rows = [r for r in records if r['policy'] == policy]
        summaries[policy] = {'case_count': len(rows),
            'dominated_cases': sum(bool(r['dominated_by']) for r in rows),
            'baseline_strictly_better_cases': sum('baseline' in r['dominated_by'] for r in rows),
            'unnecessary_action_cases': sum(r['unnecessary_actions'] for r in rows),
            'mean_queue_guest_minutes': statistics.mean(r['queue_guest_minutes'] for r in rows),
            'mean_served_visits': statistics.mean(r['served_visits'] for r in rows),
            'mean_labor_eur': statistics.mean(r['labor_eur'] for r in rows),
            'max_waiting_regret': max(r['waiting_regret'] for r in rows),
            'max_service_regret': max(r['service_regret'] for r in rows),
            'max_labor_regret': max(r['labor_regret'] for r in rows)}
    selected = {r['case_id']: r for r in records if r['policy'] == 'planner_selected'}
    rule = {r['case_id']: r for r in records if r['policy'] == 'simple_rule'}
    paired = [{'case_id': key, 'planner_minus_rule_waiting': selected[key]['queue_guest_minutes']-rule[key]['queue_guest_minutes'],
        'planner_minus_rule_service': selected[key]['served_visits']-rule[key]['served_visits'],
        'planner_minus_rule_labor': selected[key]['labor_eur']-rule[key]['labor_eur'],
        'same_schedule': selected[key]['schedule'] == rule[key]['schedule']} for key in selected]
    return summaries, paired


def run(args):
    require(args.allow_synthetic_writes, 'Requires an exclusively assigned synthetic fixture gateway')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    run_id = 'policy-stress-'+uuid.uuid4().hex[:12]
    checks = analytical_checks()
    declared = {'analytical_checks_passed': checks, 'declared_at': utc(), 'specification': SPEC, 'specification_sha256': stable_hash(SPEC),
        'evaluator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'predeclared-protocol.json').write_text(json.dumps(declared, indent=2)+'\n')
    def journal(record):
        with (output/'http.jsonl').open('a') as stream:
            stream.write(json.dumps(record)+'\n')
    http = HTTP(args.url, journal)
    cleanup = []
    http.synthetic_verified = False
    try:
        health, inputs = collect_inputs(http, run_id)
        # Selection is complete and saved before any held-out outcome is evaluated.
        (output/'selected-policies.json').write_text(json.dumps({'health': health, 'inputs': inputs}, indent=2)+'\n')
    finally:
        cleanup_requests = [('/api/connectors/'+s+'/simulation', {'mode': 'live'}) for s in ['erp', 'workforce', 'vision']]+[('/api/actions', {'action': 'reset', 'request_id': run_id+':cleanup'})]
        for path, payload in cleanup_requests if http.synthetic_verified else []:
            try:
                http.call(path, payload)
                cleanup.append({'path': path, 'ok': True})
            except Exception as error:
                cleanup.append({'path': path, 'ok': False, 'error': str(error)})
        (output/'cleanup.json').write_text(json.dumps(cleanup, indent=2)+'\n')
    require(all(c['ok'] for c in cleanup), 'Fixture cleanup failed')
    records, examples = [], []
    for fixture in inputs:
        for profile, effect, staff_delay, stock_delay in itertools.product(PROFILES,
                SPEC['staff_effect_fractions'], SPEC['staff_delay_minutes'], SPEC['delivery_delay_minutes']):
            case_id = f'{fixture["variant"]}:{profile}:effect{effect}:staff{staff_delay}:stock{stock_delay}'
            arrivals = [multiplier*fixture['initial']['throughput_per_hour']/60 for multiplier in PROFILES[profile]]
            outcomes = {name: evaluate(fixture['initial'], name, arrivals, effect, staff_delay, stock_delay) for name in SCHEDULES}
            oracle_wait = min(o['queue_guest_minutes'] for o in outcomes.values())
            oracle_service = max(o['served_visits'] for o in outcomes.values())
            oracle_labor = min(o['labor_eur'] for o in outcomes.values())
            for policy, schedule in fixture['policies'].items():
                outcome = outcomes[schedule]
                record = {'case_id': case_id, 'variant': fixture['variant'], 'arrival_profile': profile,
                    'staff_effect': effect, 'staff_delay_minutes': staff_delay, 'stock_delay_minutes': stock_delay,
                    'policy': policy, 'schedule': schedule, **{k:v for k,v in outcome.items() if k != 'trajectory'},
                    'waiting_regret': outcome['queue_guest_minutes']-oracle_wait,
                    'service_regret': oracle_service-outcome['served_visits'], 'labor_regret': outcome['labor_eur']-oracle_labor,
                    'dominated_by': [name for name, other in outcomes.items() if dominates(other, outcome)],
                    'unnecessary_actions': any(equal_effect(other, outcome) and other['command_count'] < outcome['command_count'] for other in outcomes.values())}
                records.append(record)
            if profile in ['canceled_rush', 'early_burst'] and effect == 0 and staff_delay == 30 and stock_delay is None:
                examples.append({'case_id': case_id, 'initial': fixture['initial'], 'outcomes': outcomes, 'policies': fixture['policies']})
    summaries, paired = summarize(records)
    differing = [item for item in paired if not item['same_schedule']]
    covered_variants = {f['variant'] for f in inputs if f['initial']['on_duty'] >= f['initial']['required']}
    result = {'run_id': run_id, 'completed_at': utc(), 'specification_sha256': declared['specification_sha256'],
        'source_identity': health['source_identity'], 'case_count': len(records)//3, 'policy_outcome_count': len(records),
        'policies_by_variant': {f['variant']: f['policies'] for f in inputs}, 'summaries': summaries,
        'paired_planner_vs_rule': {'identical_schedule_cases': sum(p['same_schedule'] for p in paired),
            'lower_waiting_cases': sum(p['planner_minus_rule_waiting'] < -1e-7 for p in paired),
            'higher_waiting_cases': sum(p['planner_minus_rule_waiting'] > 1e-7 for p in paired),
            'higher_labor_cases': sum(p['planner_minus_rule_labor'] > 1e-7 for p in paired),
            'mean_waiting_delta': statistics.mean(p['planner_minus_rule_waiting'] for p in paired),
            'mean_service_delta': statistics.mean(p['planner_minus_rule_service'] for p in paired),
            'mean_labor_delta': statistics.mean(p['planner_minus_rule_labor'] for p in paired),
            'differing_schedule_subset': {'case_count': len(differing),
                'mean_waiting_delta': statistics.mean(p['planner_minus_rule_waiting'] for p in differing) if differing else 0,
                'mean_service_delta': statistics.mean(p['planner_minus_rule_service'] for p in differing) if differing else 0,
                'mean_labor_delta': statistics.mean(p['planner_minus_rule_labor'] for p in differing) if differing else 0,
                'no_waiting_gain_cases': sum(p['planner_minus_rule_waiting'] >= -1e-7 for p in differing),
                'no_service_gain_cases': sum(p['planner_minus_rule_service'] <= 1e-7 for p in differing)}},
        'planner_baseline_dominated_cases_with_initial_staff_coverage': sum(r['policy'] == 'planner_selected' and r['variant'] in covered_variants and 'baseline' in r['dominated_by'] for r in records),
        'model_limits': ['Required staffing coverage and donor-team impact are not enforced; baseline dominance is not permission to operate understaffed.',
            'The canceled-rush profile still retains the initial observed/inferred queue backlog.',
            'Nonnegative staffing effects and no adverse capacity interactions favor maximal staffing on service-only metrics.'],
        'scope': SPEC['scope'], 'grid_frequency_is_probability': False}
    for filename, value in [('results.json', result), ('cases.json', records), ('paired-deltas.json', paired), ('counterexamples.json', examples)]:
        (output/filename).write_text(json.dumps(value, indent=2)+'\n')
    with (output/'cases.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--allow-synthetic-writes', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
