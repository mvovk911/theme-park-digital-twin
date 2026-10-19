#!/usr/bin/env python3
"""Independent HTTP-only acceptance for bounded synthetic maintenance workflows.

Owns one isolated gateway process and four database files. No backend imports,
SQL reads, injected exceptions or simulated clocks are used.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlsplit
import uuid
from api_operator import HTTP, require, utc, asset


class Gateway:
    def __init__(self, project, python, port, output):
        self.project, self.python, self.port, self.output = Path(project).resolve(), os.path.abspath(python), port, output
        self.process = None
        self.url = f'http://127.0.0.1:{port}'
        self.starts = []

    def start(self):
        env = dict(os.environ, **{key: str(self.output/filename) for key, filename in [
            ('PARK_DB', 'park.db'), ('PARK_REPLAY_DB', 'replay.db'),
            ('PARK_PLANNING_DB', 'planning.db'), ('PARK_WORKFLOWS_DB', 'workflows.db')]})
        with (self.output/'backend.log').open('ab') as log:
            self.process = subprocess.Popen([self.python, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(self.port)],
                cwd=self.project, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        record = {'pid': self.process.pid, 'started_at': utc(), 'source_files': {
            str(p.relative_to(self.project)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [self.project/'backend/app.py', self.project/'main.py',
                *sorted((self.project/'backend/workflows').rglob('*.py')),
                *sorted((self.project/'backend/planning').rglob('*.py'))]}}
        self.starts.append(record)
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            try:
                import urllib.request
                with urllib.request.urlopen(self.url+'/api/health', timeout=2) as response:
                    record['health'] = json.load(response)
                require(record['health'].get('synthetic') is True, 'Gateway not synthetic')
                return record
            except OSError:
                require(self.process.poll() is None, 'Gateway exited during startup')
                time.sleep(.2)
        raise RuntimeError('Gateway startup timeout')

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        return {'pid': self.process.pid if self.process else None,
            'exit_code': self.process.returncode if self.process else None, 'stopped_at': utc()}


class Review:
    def __init__(self, gateway, output):
        self.gateway, self.output = gateway, output
        self.run_id = 'workflow-review-'+uuid.uuid4().hex[:12]
        self.http = HTTP(gateway.url, self.journal)
        self.results = []
        self.recovered = None

    def journal(self, value):
        with (self.output/'events.jsonl').open('a') as stream:
            stream.write(json.dumps(value)+'\n')

    def check(self, name, function):
        began = time.monotonic()
        result = {'check': name, 'started_at': utc()}
        try:
            result.update(status='pass', evidence=function())
        except Exception as error:
            result.update(status='fail', error=f'{type(error).__name__}: {error}')
        result['elapsed_seconds'] = time.monotonic()-began
        self.results.append(result)
        self.journal(result)
        (self.output/'checks.json').write_text(json.dumps(self.results, indent=2)+'\n')
        print(json.dumps({'check': name, 'status': result['status'], 'error': result.get('error')}), flush=True)

    def reset(self, scenario='ride_closure'):
        self.http.call('/api/view', {'mode': 'live'})
        for source in ['ride_scada', 'cmms', 'bms', 'water']:
            self.http.call('/api/connectors/'+source+'/simulation', {'mode': 'live'})
        self.http.call('/api/actions', {'action': 'reset', 'request_id': self.run_id+':reset:'+uuid.uuid4().hex[:10]})
        if scenario != 'normal':
            self.http.call('/api/scenarios', {'scenario': scenario})

    def evidence(self, scenario='ride_closure', candidates=None):
        request = {'scenario': scenario, 'horizon_minutes': 60}
        if candidates is not None:
            request['candidates'] = candidates
        result = self.http.call('/api/planning/simulate', request)
        saved = self.http.call('/api/planning/evidence', result['evidence_bundle'])
        require(saved['verified'] is True and saved['execution_authority'] is False, 'Saved evidence claims authority or did not verify')
        return result['evidence_bundle']['bundle_id']

    def payload(self, bundle, label, branch='simple_rule', index=0):
        return {'bundle_id': bundle, 'branch_id': branch, 'action_index': index,
            'request_id': self.run_id+':create:'+label, 'ttl_seconds': 30}

    def proposal(self, label):
        self.reset()
        bundle = self.evidence()
        payload = self.payload(bundle, label)
        proposal = self.http.call('/api/workflows/proposals', payload)['proposal']
        return proposal, payload

    def execute(self, proposal, label, expected=200):
        return self.http.call('/api/workflows/proposals/'+proposal['id']+'/execute',
            {'request_id': self.run_id+':execute:'+label}, expected)

    def fault_readback(self, response):
        p = response['proposal']
        require(response['outcome'] == 'accepted_workflow_not_repair', 'Workflow falsely reports repair or wrong lifecycle')
        require(p['physical_effect'] is False and p['receipt']['physical_effect'] is False and p['readback']['physical_completion'] is False,
            'Workflow claims physical action/completion')
        require(p['receipt']['work_order_id'] == p['readback']['work_order']['id'], 'Readback does not match acknowledged work order')
        require(p['readback']['asset_status'] == 'closed', 'Dispatch reopened closed coaster')
        require(asset(self.http.call('/api/state'), 'RIDE_COASTER')['status'] == 'closed', 'Canonical coaster reopened')
        return p

    def success_and_concurrent_retries(self):
        proposal, payload = self.proposal('concurrent')
        with ThreadPoolExecutor(max_workers=4) as pool:
            creation = list(pool.map(lambda _: self.http.call('/api/workflows/proposals', payload), range(4)))
        require(all(r['proposal']['id'] == proposal['id'] and r['proposal']['expires_at'] == proposal['expires_at'] and r['idempotency']['replayed'] for r in creation), 'Concurrent create retries changed identity/expiry')
        audit_before = self.http.call('/api/audit')['events']
        time.sleep(1.2)
        require(self.http.call('/api/state')['accepted_state_revision'] != proposal['creation_state_revision'], 'Ordinary-tick fixture did not advance')
        with ThreadPoolExecutor(max_workers=4) as pool:
            execution = list(pool.map(lambda _: self.execute(proposal, 'concurrent'), range(4)))
        accepted = self.fault_readback(execution[0])
        require(all(r['proposal']['receipt'] == accepted['receipt'] for r in execution), 'Concurrent executions changed receipt')
        require(sum(not r['idempotency']['replayed'] for r in execution) == 1, 'More than one new execution acknowledgement')
        audit_after = self.http.call('/api/audit')['events']
        require(len(audit_after) == len(audit_before)+1, 'Concurrent execution wrote duplicate audit events')
        detail = self.http.call('/api/assets/RIDE_COASTER')
        open_orders = [w for w in detail['work_orders'] if w['status'] == 'open']
        require(len(open_orders) == 1 and open_orders[0]['id'] == accepted['receipt']['work_order_id'], 'Work order missing or duplicated')
        self.http.call('/api/workflows/proposals', {**payload, 'ttl_seconds': 60}, 409)
        self.execute(proposal, 'different-caller', 409)
        return {'accepted': accepted, 'concurrent_creates': 4, 'concurrent_executes': 4,
            'audit_delta': 1, 'ordinary_tick_change_allowed': True}

    def changed_and_existing_work_order(self):
        proposal, payload = self.proposal('scenario-change')
        self.http.call('/api/scenarios', {'scenario': 'normal'})
        scenario_error = self.execute(proposal, 'scenario-change', 409)
        proposal, payload = self.proposal('intervening-order')
        legacy = self.http.call('/api/actions', {'action': 'dispatch_maintenance', 'asset_id': 'RIDE_COASTER',
            'request_id': self.run_id+':legacy-order'})
        execution_error = self.execute(proposal, 'intervening-order', 409)
        create_error = self.http.call('/api/workflows/proposals', {**payload, 'request_id': payload['request_id']+'-new'}, 409)
        open_orders = [w for w in self.http.call('/api/assets/RIDE_COASTER')['work_orders'] if w['status'] == 'open']
        require(len(open_orders) == 1 and open_orders[0]['id'] == legacy['result']['work_order_id'], 'Rejected workflow duplicated a work order')
        return {'scenario_change': scenario_error, 'intervening_work_order': execution_error,
            'existing_work_order_new_proposal': create_error, 'existing_work_order_id': open_orders[0]['id']}

    def ingest(self, source, metric, value, asset_id='RIDE_COASTER'):
        self.http.call('/api/connectors/'+source+'/simulation', {'mode': 'paused'})
        result = self.http.call('/api/connectors/'+source+'/ingest', {'synthetic': True, 'events': [{
            'event_id': self.run_id+':input:'+uuid.uuid4().hex[:10], 'source_asset_id': source+'/'+asset_id,
            'metric': metric, 'value': value, 'unit': 'work_orders' if metric.endswith('open_work_orders') else 'state',
            'source_timestamp': utc()}]})
        require(result['accepted'] == 1, 'Controlled observation was not accepted')

    def input_quality_and_change(self):
        proposal, payload = self.proposal('status-change')
        self.ingest('ride_scada', 'status', 'operational')
        changed = self.execute(proposal, 'status-change', 409)
        proposal, payload = self.proposal('stale')
        self.http.call('/api/connectors/cmms/simulation', {'mode': 'paused'})
        began = time.monotonic()
        while time.monotonic()-began < 6.3:
            time.sleep(.3)
        waited = time.monotonic()-began
        stale = self.execute(proposal, 'stale', 409)
        self.reset()
        bundle = self.evidence()
        self.ingest('cmms', 'maintenance.open_work_orders', 1)
        conflict = self.http.call('/api/workflows/proposals', self.payload(bundle, 'contradictory-count'), 409)
        self.reset()
        bundle = self.evidence()
        self.ingest('cmms', 'maintenance.inspection_status', 'passed')
        closed_only = self.http.call('/api/workflows/proposals', self.payload(bundle, 'closed-not-diagnosis'), 409)
        return {'changed_status': changed, 'stale_input': stale, 'actual_stale_wait_seconds': waited,
            'contradictory_cmms': conflict, 'closed_without_inspection_issue': closed_only}

    def unsupported_and_hypothetical(self):
        self.reset('normal')
        bundle = self.evidence()
        hypothetical = self.http.call('/api/workflows/proposals', self.payload(bundle, 'hypothetical'), 409)
        self.reset()
        bundle = self.evidence()
        unsupported = self.http.call('/api/workflows/proposals', self.payload(bundle, 'unsupported', 'coordinated', 1), 422)
        require(unsupported['detail']['code'] == 'unsupported_workflow_action', 'Wrong unsupported-action reason')
        future_bundle = self.evidence(candidates=[{'id': 'future', 'label': 'Future dispatch', 'actions': [
            {'action': 'dispatch_maintenance', 'asset_id': 'RIDE_COASTER', 'at_minute': 5}]}])
        future = self.http.call('/api/workflows/proposals', self.payload(future_bundle, 'future', 'future'), 422)
        return {'hypothetical_evidence': hypothetical, 'unsupported_action': unsupported, 'future_action': future}

    def replay_guards(self):
        proposal, payload = self.proposal('replay')
        timeline = self.http.call('/api/timeline?limit=1')
        self.http.call('/api/view', {'mode': 'replay', 'snapshot_id': timeline['snapshots'][0]['id']})
        self.http.call('/api/workflows/proposals', payload, 409)
        self.execute(proposal, 'replay', 409)
        reopened = self.http.call('/api/workflows/proposals/'+proposal['id'])
        require(reopened['proposal']['id'] == proposal['id'], 'Replay cannot read saved proposal')
        self.http.call('/api/view', {'mode': 'live'})
        result = self.execute(proposal, 'replay')
        self.fault_readback(result)
        return {'readable_in_replay': True, 'create_retry_blocked': True, 'execution_blocked': True,
            'live_execution': result['proposal']['receipt']}

    def discard_response(self, path, payload):
        parsed = urlsplit(self.gateway.url)
        body = json.dumps(payload).encode()
        request = (f'POST {path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()+body
        with socket.create_connection((parsed.hostname, parsed.port), timeout=5) as connection:
            connection.sendall(request)
            connection.shutdown(socket.SHUT_WR)
            # Intentionally consume no response bytes; readback must prove commit.
        self.journal({'type': 'discarded_http_response', 'path': path, 'request': payload, 'utc': utc(), 'response_bytes_consumed': 0})

    def lost_response_and_restart(self):
        self.reset()
        bundle = self.evidence()
        payload = self.payload(bundle, 'lost-response')
        self.discard_response('/api/workflows/proposals', payload)
        deadline = time.monotonic()+5
        original = None
        while time.monotonic() < deadline:
            records = self.http.call('/api/workflows/proposals?limit=100&offset=0')['items']
            original = next((p for p in records if p['create_request_id'] == payload['request_id']), None)
            if original:
                break
            time.sleep(.1)
        require(original is not None, 'Discarded create response did not leave a readable committed proposal')
        retry = self.http.call('/api/workflows/proposals', payload)
        require(retry['idempotency']['replayed'] and retry['proposal']['id'] == original['id'], 'Create recovery changed identity')
        execution_id = self.run_id+':execute:lost-response'
        self.discard_response('/api/workflows/proposals/'+original['id']+'/execute', {'request_id': execution_id})
        deadline = time.monotonic()+5
        completed = None
        while time.monotonic() < deadline:
            completed = self.http.call('/api/workflows/proposals/'+original['id'])['proposal']
            if completed['status'] == 'accepted_workflow_not_repair':
                break
            time.sleep(.1)
        require(completed['status'] == 'accepted_workflow_not_repair', 'Lost execution response did not commit')
        before = self.http.call('/api/health')
        stopped = self.gateway.stop()
        restarted = self.gateway.start()
        require(before['source_identity']['checked_at'] != restarted['health']['source_identity']['checked_at'], 'Restart identity did not change')
        recovered = self.http.call('/api/workflows/proposals/'+original['id']+'/execute', {'request_id': execution_id})
        require(recovered['idempotency']['replayed'] and recovered['proposal']['receipt'] == completed['receipt'], 'Restart recovery changed original receipt')
        self.fault_readback(recovered)
        self.recovered = {'proposal': original, 'execution_id': execution_id, 'receipt': completed['receipt']}
        return {'created_without_response_read': original['id'], 'receipt': completed['receipt'],
            'restart': {'stopped': stopped, 'new_pid': restarted['pid'],
                'same_source_files': self.gateway.starts[0]['source_files'] == restarted['source_files']},
            'receipt_survived_restart': True,
            'scope': 'Actual discarded client responses and graceful process restart; not injected crash between two database commits.'}

    def expiry_and_historical_recovery(self):
        proposal, payload = self.proposal('expires')
        began = time.monotonic()
        expiry = datetime.fromisoformat(proposal['expires_at'])
        while datetime.now(timezone.utc) <= expiry:
            time.sleep(min(1, max(.01, (expiry-datetime.now(timezone.utc)).total_seconds()+.05)))
        waited = time.monotonic()-began
        require(waited >= 29, 'TTL test did not wait real wall-clock interval')
        expired = self.execute(proposal, 'expires', 409)
        require('expir' in json.dumps(expired).lower(), 'Expired request rejected for an unrelated reason')
        retry_create = self.http.call('/api/workflows/proposals', payload)
        require(retry_create['idempotency']['replayed'] and retry_create['proposal']['id'] == proposal['id'] and retry_create['proposal']['expires_at'] == proposal['expires_at'], 'Expired create retry silently renewed or changed proposal')
        replacement = self.http.call('/api/workflows/proposals', {**payload, 'request_id': payload['request_id']+'-replacement'})
        require(replacement['proposal']['id'] != proposal['id'] and replacement['proposal']['status'] == 'proposed', 'Operator cannot make a fresh proposal after expiry')
        audit_before = self.http.call('/api/audit')['events']
        require(self.recovered is not None, 'No saved restart recovery fixture')
        old = self.recovered
        recovered = self.http.call('/api/workflows/proposals/'+old['proposal']['id']+'/execute', {'request_id': old['execution_id']})
        require(recovered['idempotency']['replayed'] and recovered['proposal']['receipt'] == old['receipt'], 'Expired accepted receipt was not recovered')
        require(recovered['proposal']['readback']['work_order']['status'] == 'closed_by_reset', 'Recovery hid changed current work-order status')
        require(recovered['proposal']['receipt']['lifecycle'] == 'work_order_open', 'Historical receipt was rewritten')
        require(self.http.call('/api/audit')['events'] == audit_before, 'Expired receipt recovery issued a new command')
        return {'actual_wall_wait_seconds': waited, 'unaccepted_expired_proposal': expired,
            'accepted_receipt_after_expiry_and_reset': recovered['proposal'], 'no_new_audit': True, 'expired_create_retry_preserved_identity': True,
            'replacement_proposal_after_expiry': replacement['proposal']['id']}

    def all_supported_targets(self):
        outcomes = []
        source_for = {'RIDE_COASTER': 'ride_scada', 'RIDE_WHEEL': 'ride_scada',
            'POWER_HUB': 'bms', 'WATER_PLANT': 'water'}
        capabilities = self.http.call('/api/workflows/capabilities')
        declared = capabilities['supported_actions'][0]['asset_ids']
        require(set(declared) == set(source_for), 'Advertised supported targets changed')
        for target, source in source_for.items():
            self.reset('normal')
            self.ingest(source, 'status', 'fault', target)
            bundle = self.evidence('normal', [{'id': 'maintenance', 'label': 'Inspect current fault',
                'actions': [{'action': 'dispatch_maintenance', 'asset_id': target, 'at_minute': 0}]}])
            proposal = self.http.call('/api/workflows/proposals', self.payload(bundle, 'target-'+target, 'maintenance'))['proposal']
            response = self.execute(proposal, 'target-'+target)
            p = response['proposal']
            require(response['outcome'] == 'accepted_workflow_not_repair' and p['readback']['asset_status'] == 'fault', 'Target dispatch claims repair')
            require(p['receipt']['work_order_id'] == p['readback']['work_order']['id'] and p['readback']['work_order']['asset_id'] == target, 'Target receipt/readback mismatch')
            require(asset(self.http.call('/api/state'), target)['status'] == 'fault', 'Dispatch changed canonical fault')
            outcomes.append({'asset_id': target, 'receipt': p['receipt'], 'readback': p['readback']})
        return outcomes

    def cross_proposal_id_conflict(self):
        require(self.recovered is not None, 'No execution ID fixture')
        proposal, payload = self.proposal('reuse-execution-id')
        conflict = self.http.call('/api/workflows/proposals/'+proposal['id']+'/execute',
            {'request_id': self.recovered['execution_id']}, 409)
        return {'reused_execution_id': conflict}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--port', type=int, default=18150)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', args.port))
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    gateway = Gateway(args.project, args.python, args.port, output)
    review = Review(gateway, output)
    started = utc()
    cleanup = None
    try:
        gateway.start()
        for name in ['success_and_concurrent_retries', 'changed_and_existing_work_order',
                'input_quality_and_change', 'unsupported_and_hypothetical', 'replay_guards',
                'lost_response_and_restart', 'expiry_and_historical_recovery', 'cross_proposal_id_conflict', 'all_supported_targets']:
            review.check(name, getattr(review, name))
        review.check('cleanup', lambda: review.reset('normal'))
    finally:
        cleanup = gateway.stop()
        report = {'started_at': started, 'finished_at': utc(), 'url': gateway.url,
            'check_count': len(review.results), 'failures': sum(r['status'] != 'pass' for r in review.results),
            'checks': review.results, 'gateway_starts': gateway.starts, 'process_cleanup': cleanup,
            'evaluator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope': 'Actual HTTP and process lifecycle, synthetic workflow acceptance only. No physical repair, authentication, external CMMS or crash-window injection.'}
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(1 if report['failures'] else 0)


if __name__ == '__main__':
    main()
