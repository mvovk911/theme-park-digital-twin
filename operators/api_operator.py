#!/usr/bin/env python3
"""Independent HTTP-only synthetic operator/evaluator. No backend imports or LLM.

Mutating evaluations require --allow-synthetic-writes and an exclusively scheduled
synthetic gateway. Evidence is append-only; failures never become passing results.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid


class ContractFailure(RuntimeError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat()


def asset(state, asset_id):
    return next(a for a in state['assets'] if a['id'] == asset_id)


def require(condition, message):
    if not condition:
        raise ContractFailure(message)


class HTTP:
    def __init__(self, base, journal):
        self.base = base.rstrip('/')
        self.journal = journal

    def call(self, path, payload=None, expected=200):
        started = time.monotonic()
        request = urllib.request.Request(self.base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                status, body = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, body = error.code, error.read()
        except Exception as error:
            self.journal({'type': 'transport_error', 'path': path,
                'method': request.get_method(), 'error': str(error), 'utc': utc()})
            raise
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            data = {'non_json_sha256': hashlib.sha256(body).hexdigest()}
        self.journal({'type': 'http', 'utc': utc(), 'method': request.get_method(),
            'path': path, 'status': status, 'elapsed_ms': round((time.monotonic()-started)*1000, 2),
            'request': payload, 'response_sha256': hashlib.sha256(body).hexdigest()})
        allowed = [expected] if isinstance(expected, int) else expected
        require(status in allowed, f'{request.get_method()} {path}: expected {allowed}, received {status}: {data}')
        return data


class Evaluator:
    def __init__(self, http, output):
        self.http = http
        self.output = output
        self.run_id = 'operator-' + uuid.uuid4().hex[:16]
        self.results = []
        self.cycle = 0
        self.include_planner = False

    def check(self, name, fn):
        started = time.monotonic()
        record = {'type': 'check', 'cycle': self.cycle, 'check': name, 'utc': utc()}
        try:
            record.update(status='pass', evidence=fn())
        except Exception as error:
            record.update(status='fail', error=f'{type(error).__name__}: {error}')
        record['duration_seconds'] = round(time.monotonic()-started, 3)
        self.results.append(record)
        self.http.journal(record)
        print(json.dumps(record), flush=True)
        return record

    def action(self, action, asset_id=None, request_id=None, expected=200):
        return self.http.call('/api/actions', {'action': action, 'asset_id': asset_id,
            'request_id': request_id or f'{self.run_id}:{self.cycle}:{uuid.uuid4().hex[:12]}'}, expected)

    def state(self):
        return self.http.call('/api/state')

    def setup(self):
        health = self.http.call('/api/health')
        require(health.get('synthetic') is True, 'Refusing non-synthetic gateway')
        state = self.state()
        require(state.get('synthetic') is True, 'Refusing non-synthetic state')
        view = self.http.call('/api/view/state')['view']
        require(view['mode'] == 'live', 'Exclusive test must begin in live mode')
        modes = {v['source_id']: v['mode'] for v in self.http.call('/api/connectors/health')['health']}
        require(all(v == 'live' for v in modes.values()), 'Exclusive test must begin with all source modes live')
        return {'health': health, 'source_modes': modes, 'original_scenario': state['scenario']}

    def cleanup(self):
        evidence = []
        for path, payload in [('/api/view', {'mode': 'live'}),
                ('/api/connectors/water/simulation', {'mode': 'live'}),
                ('/api/connectors/ride_scada/simulation', {'mode': 'live'}),
                ('/api/connectors/erp/simulation', {'mode': 'live'}),
                ('/api/actions', {'action': 'reset', 'request_id': self.run_id + ':cleanup:' + str(self.cycle)})]:
            try:
                self.http.call(path, payload)
                evidence.append({'path': path, 'ok': True})
            except Exception as error:
                evidence.append({'path': path, 'ok': False, 'error': str(error)})
        require(all(x['ok'] for x in evidence), f'Cleanup failed: {evidence}')
        return evidence

    def compare_read_only(self):
        self.action('reset')
        before = self.state()
        audit = self.http.call('/api/audit')['events']
        comparisons = []
        for scenario in before['scenarios']:
            result = self.http.call('/api/scenarios/compare?scenario=' + scenario['id'])
            require(result['mutates_live_state'] is False, 'Comparison claims mutation')
            require(result['method'] == 'heuristic_same_tick_comparison', 'Unexpected comparison method')
            comparisons.append({'scenario': scenario['id'], 'method': result['method'],
                'baseline_tick': result['baseline_tick'], 'deltas': result['deltas']})
        require(self.state()['scenario'] == before['scenario'], 'Comparison changed live scenario')
        require(self.http.call('/api/audit')['events'] == audit, 'Comparison wrote an audit event')
        self.http.call('/api/scenarios/compare?scenario=not_a_scenario', expected=422)
        return {'comparisons': comparisons, 'limitation': 'Same-tick heuristic scenario changes; no action counterfactual or time forecast.'}

    def interventions(self):
        policies = [
            ('ride_closure', 'dispatch_maintenance', 'RIDE_COASTER'),
            ('show_surge', 'reroute_guests', 'SHOW_ARENA'),
            ('heatwave', 'add_staff', 'FIRST_AID'),
            ('power_fault', 'shed_load', 'POWER_HUB'),
            ('water_leak', 'repair_leak', 'WATER_PLANT'),
            ('food_rush', 'replenish_stock', 'FOOD_COURT')]
        evidence = []
        for scenario, action, target in policies:
            before = self.http.call('/api/scenarios', {'scenario': scenario})
            target_before = asset(before, target)
            required_quality = target_before['data_quality']['status']
            require(required_quality == 'good', f'Abstain: {target} quality is {required_quality}')
            response = self.action(action, target)
            receipt, after = response['result'], response['state']
            require(receipt['acknowledgement'] == 'accepted', 'Missing accepted acknowledgement')
            require(receipt['physical_effect'] is False, 'Unexpected physical-effect claim')
            target_after = asset(after, target)
            if action == 'dispatch_maintenance':
                require(receipt.get('work_order_id'), 'No work order identity')
                require(target_after['status'] == 'closed', 'Dispatch incorrectly reopened ride')
                detail = self.http.call('/api/assets/' + target)
                require(any(w['id'] == receipt['work_order_id'] for w in detail['work_orders']), 'Receipt work order missing')
            elif action == 'reroute_guests':
                require(after['kpis']['average_wait_minutes'] < before['kpis']['average_wait_minutes'], 'Guidance did not reduce illustrative wait')
                require(after['kpis']['open_rides'] == before['kpis']['open_rides'], 'Guidance reduced ride availability')
            elif action == 'add_staff':
                require(target_after['staff']['on_duty'] == target_before['staff']['on_duty'] + 2, 'Staff assignment missing')
                require(after['kpis']['estimated_operating_cost_eur_per_hour'] > before['kpis']['estimated_operating_cost_eur_per_hour'], 'Staff cost tradeoff missing')
            elif action == 'shed_load':
                require(after['kpis']['power_kw'] < before['kpis']['power_kw'] - 40, 'Flexible load effect absent')
                require(after['kpis']['open_rides'] == before['kpis']['open_rides'], 'Load shedding changed ride availability')
            elif action == 'repair_leak':
                require(target_after['water_lpm'] < target_before['water_lpm'] - 200, 'Simulated leak flow not reduced')
                require(target_after['status'] == 'operational', 'Simulated repair did not recover status')
            elif action == 'replenish_stock':
                require(target_after['erp']['stock_units'] > target_before['erp']['stock_units'], 'Inventory did not increase')
            evidence.append({'scenario': scenario, 'action': action, 'target': target,
                'receipt': receipt, 'before_tick': before['tick'], 'after_tick': after['tick'],
                'before_kpis': before['kpis'], 'after_kpis': after['kpis'],
                'kpi_delta': {k: round(after['kpis'][k]-v, 3) for k,v in before['kpis'].items()
                              if isinstance(v, (int,float))},
                'value_scope': 'Synthetic workflow/postcondition, not causal real-world benefit; sequential ticks differ.'})
        return evidence

    def retries_and_errors(self):
        self.http.call('/api/scenarios', {'scenario': 'ride_closure'})
        rid = f'{self.run_id}:{self.cycle}:dispatch-retry'
        payload = {'action': 'dispatch_maintenance', 'asset_id': 'RIDE_COASTER', 'request_id': rid}
        first = self.http.call('/api/actions', payload)
        audit = self.http.call('/api/audit')['events']
        with ThreadPoolExecutor(max_workers=4) as pool:
            repeated = list(pool.map(lambda _: self.http.call('/api/actions', payload), range(4)))
        require(all(x['result'] == first['result'] and x['idempotency']['replayed'] for x in repeated), 'Retry receipt changed or effect repeated')
        require(self.http.call('/api/audit')['events'] == audit, 'Concurrent retries wrote duplicate audits')
        conflict = self.http.call('/api/actions', {**payload, 'action': 'reroute_guests'}, 409)
        require(conflict['detail']['code'] == 'request_id_conflict', 'Wrong conflict reason')
        self.http.call('/api/actions', {'action': 'launch_physical_ride'}, 422)
        self.http.call('/api/actions', {'action': 'add_staff', 'asset_id': 'UNKNOWN'}, 404)
        self.http.call('/api/actions', {'action': 'repair_leak', 'asset_id': 'RIDE_COASTER'}, 422)
        self.action('reset')
        reset_state = self.state()
        again = self.http.call('/api/actions', payload)
        require(again['result'] == first['result'], 'Retry after reset changed receipt')
        require(asset(again['state'], 'RIDE_COASTER')['maintenance']['open_work_orders'] == asset(reset_state, 'RIDE_COASTER')['maintenance']['open_work_orders'], 'Old retry recreated work order')
        return {'immutable_receipt': first['result'], 'concurrent_retries': 4,
            'retry_after_reset': True, 'invalid_actions_rejected': True}

    def source_failures(self):
        self.action('reset')
        source = '/api/connectors/water'
        self.http.call(source + '/simulation', {'mode': 'paused'})
        initial = self.http.call(source + '/health')
        event = {'event_id': f'{self.run_id}:{self.cycle}:water', 'source_asset_id': 'water/WATER_PLANT',
            'metric': 'water_lpm', 'value': 610.0, 'unit': 'L/min', 'source_timestamp': utc()}
        body = {'synthetic': True, 'events': [event]}
        accepted = self.http.call(source + '/ingest', body)
        require(accepted['accepted'] == 1, 'Valid observation not accepted')
        require(asset(self.state(), 'WATER_PLANT')['water_lpm'] == 610, 'Canonical projection ignored accepted observation')
        duplicate = self.http.call(source + '/ingest', body)
        require(duplicate['duplicates'] == 1, 'Identical source event was not deduplicated')
        conflict = self.http.call(source + '/ingest', {'synthetic': True, 'events': [{**event, 'value': 999}]})
        require(conflict['rejected'] == 1, 'Conflicting source event was accepted')
        malformed = self.http.call(source + '/ingest', {'synthetic': True, 'events': [{**event, 'event_id': event['event_id'] + '-unit', 'unit': 'gallons'}]})
        require(malformed['rejected'] == 1, 'Wrong unit was accepted')
        late = self.http.call(source + '/ingest', {'synthetic': True, 'events': [{**event,
            'event_id': event['event_id'] + '-late', 'source_timestamp': (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(), 'value': 50}]})
        require(late['rejected'] == 1, 'Late observation was applied')
        require(asset(self.state(), 'WATER_PLANT')['water_lpm'] == 610, 'Late/conflict observation corrupted latest value')
        deadline = time.monotonic() + 9
        while time.monotonic() < deadline:
            health = self.http.call(source + '/health')
            if health['status'] == 'stale' and asset(self.state(), 'WATER_PLANT')['data_quality']['fields']['water_lpm']['status'] == 'stale':
                break
            time.sleep(0.5)
        require(health['status'] == 'stale', 'Paused source never became stale')
        state = self.state()
        require(asset(state, 'WATER_PLANT')['data_quality']['fields']['water_lpm']['status'] == 'stale', 'Asset hid stale input')
        # This deterministic policy abstains. Legacy /api/actions does not enforce this gate.
        abstention = {'decision': 'abstain', 'reason': 'Required water telemetry is stale', 'action_submitted': False}
        self.http.call(source + '/simulation', {'mode': 'offline'})
        require(self.http.call(source + '/health')['status'] == 'offline', 'Offline state missing')
        self.http.call(source + '/simulation', {'mode': 'live'})
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            recovered = self.http.call(source + '/health')
            if recovered['status'] == 'healthy':
                break
            time.sleep(.25)
        require(recovered['status'] == 'healthy', 'Source did not recover')
        return {'before': initial, 'stale': health, 'recovered': recovered,
            'operator_abstention': abstention, 'conflicting_event': conflict, 'late_event': late,
            'server_enforcement': 'Legacy action API has no source freshness or expected-revision prerequisite.'}

    def source_model_conflict(self):
        self.http.call('/api/scenarios', {'scenario': 'ride_closure'})
        source = '/api/connectors/ride_scada'
        self.http.call(source + '/simulation', {'mode': 'paused'})
        self.http.call(source + '/ingest', {'synthetic': True, 'events': [{
            'event_id': f'{self.run_id}:{self.cycle}:ride-status', 'source_asset_id': 'ride_scada/RIDE_COASTER',
            'metric': 'status', 'value': 'operational', 'unit': 'state', 'source_timestamp': utc()}]})
        state = self.state()
        require(asset(state, 'RIDE_COASTER')['status'] == 'operational', 'Canonical status did not follow owning source')
        require(state['source_conflicts'], 'Model/source conflict is hidden')
        self.http.call(source + '/simulation', {'mode': 'live'})
        return {'conflicts': state['source_conflicts'], 'decision': 'abstain', 'action_submitted': False}

    def replay_guards(self):
        self.action('reset')
        timeline = self.http.call('/api/timeline?limit=3')
        require(timeline['snapshots'], 'No recording available')
        selected = timeline['snapshots'][0]['id']
        self.http.call('/api/view', {'mode': 'replay', 'snapshot_id': selected})
        historical = self.http.call('/api/view/state')
        for path, payload in [('/api/actions', {'action': 'add_staff'}),
                ('/api/scenarios', {'scenario': 'food_rush'}),
                ('/api/connectors/water/simulation', {'mode': 'offline'})]:
            self.http.call(path, payload, 409)
        self.http.call('/api/scenarios/compare?scenario=food_rush', expected=409)
        tick = self.state()['tick']
        time.sleep(1.3)
        require(self.state()['tick'] > tick, 'Replay stopped live ingestion')
        current = self.http.call('/api/view/state')
        require(current['assets'] == historical['assets'] and current['kpis'] == historical['kpis'], 'Historical payload changed')
        self.http.call('/api/view', {'mode': 'live'})
        return {'snapshot_id': selected, 'write_guards': 4, 'history_immutable': True, 'live_ingestion_continues': True}

    def cycle_once(self):
        self.cycle += 1
        for name in ['compare_read_only', 'interventions', 'retries_and_errors',
                     'source_failures', 'source_model_conflict', 'replay_guards']:
            self.check(name, getattr(self, name))
        if self.include_planner:
            import planning_checks
            self.check('planning_counterfactuals', lambda: planning_checks.run(self))
            self.check('planning_degraded_input', lambda: planning_checks.degraded_input(self))
            self.check('planning_assumption_stress', lambda: planning_checks.assumption_stress(self))
        self.check('cleanup', self.cleanup)


def run(args):
    require(args.allow_synthetic_writes, 'Pass --allow-synthetic-writes only for an exclusively scheduled synthetic gateway')
    require(args.duration_seconds >= 0 and args.interval_seconds >= 1, 'Invalid duration/interval')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    journal_file = output / 'events.jsonl'
    def journal(event):
        with journal_file.open('a') as handle:
            handle.write(json.dumps(event, sort_keys=True) + '\n')
    http = HTTP(args.url, journal)
    evaluator = Evaluator(http, output)
    evaluator.include_planner = args.include_planner
    started = time.monotonic()
    start_utc = utc()
    summary = {'operator': 'deterministic_http_policy_and_contract_evaluator', 'uses_llm': False,
        'url': args.url, 'run_id': evaluator.run_id, 'started_at': start_utc,
        'requested_duration_seconds': args.duration_seconds, 'interval_seconds': args.interval_seconds,
        'setup': None, 'complete': False, 'phase': 'starting',
        'pause_file': args.pause_file, 'pause_seconds': 0.0, 'pause_events': []}
    def save():
        summary.update(elapsed_seconds=round(time.monotonic()-started, 3),
            completed_cycles=evaluator.cycle, checks=evaluator.results,
            failures=sum(x['status'] == 'fail' for x in evaluator.results))
        temp = output / 'summary.json.tmp'
        temp.write_text(json.dumps(summary, indent=2) + '\n')
        temp.replace(output / 'summary.json')
    def wait_if_paused():
        if not args.pause_file or not Path(args.pause_file).exists():
            return
        began = time.monotonic()
        event = {'started_at': utc(), 'ended_at': None, 'duration_seconds': 0.0}
        summary['pause_events'].append(event)
        summary['phase'] = 'paused'
        previous_total = summary['pause_seconds']
        while Path(args.pause_file).exists() and (args.duration_seconds == 0 or time.monotonic()-started < args.duration_seconds):
            event['duration_seconds'] = round(time.monotonic()-began, 3)
            summary['pause_seconds'] = previous_total + event['duration_seconds']
            save()
            evaluator.check('paused_read_only_health', lambda: http.call('/api/health'))
            time.sleep(10 if args.duration_seconds == 0 else min(10, max(0, args.duration_seconds-(time.monotonic()-started))))
        event.update(ended_at=utc(), duration_seconds=round(time.monotonic()-began, 3))
        summary['pause_seconds'] = previous_total + event['duration_seconds']
        summary['phase'] = 'idle'
        save()
    save()
    try:
        startup = evaluator.check('startup', evaluator.setup)
        require(startup['status'] == 'pass', startup.get('error', 'Startup failed'))
        summary['setup'] = startup['evidence']
        while True:
            wait_if_paused()
            if args.duration_seconds > 0 and time.monotonic()-started >= args.duration_seconds:
                break
            summary['phase'] = 'mutating_cycle'
            save()
            cycle_start = time.monotonic()
            evaluator.cycle_once()
            summary['phase'] = 'idle'
            save()
            if time.monotonic() - started >= args.duration_seconds:
                break
            until = min(cycle_start + args.interval_seconds, started + args.duration_seconds)
            while time.monotonic() < until:
                wait_if_paused()
                if time.monotonic() < until:
                    time.sleep(min(1, until-time.monotonic()))
                save()
            if time.monotonic() - started >= args.duration_seconds:
                break
        summary.update(complete=True, finished_at=utc())
    except BaseException as error:
        summary['interruption'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        if summary['phase'] == 'mutating_cycle':
            evaluator.check('final_cleanup', evaluator.cleanup)
        summary['phase'] = 'finished' if summary['complete'] else 'interrupted'
        save()
    return 1 if summary['failures'] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--duration-seconds', type=float, default=0,
        help='0 = one cycle; 28800 = measured eight-hour test, never inferred from cycle count')
    parser.add_argument('--interval-seconds', type=float, default=300)
    parser.add_argument('--include-planner', action='store_true', help='Also test the planning API and negative controls')
    parser.add_argument('--pause-file', help='While this file exists, finish the current cycle, then perform read-only health checks; inspect summary.phase=paused before shared work')
    parser.add_argument('--allow-synthetic-writes', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == '__main__':
    main()
