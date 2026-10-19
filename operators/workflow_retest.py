#!/usr/bin/env python3
"""Focused HTTP retake of workflow conflict navigation and stale readback evidence."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import time
from api_operator import asset, require, utc
from workflow_checks import Gateway, Review


def conflict_navigation(review):
    proposal, payload = review.proposal('context-navigation')
    dispatched = review.http.call('/api/actions', {'action': 'dispatch_maintenance',
        'asset_id': 'RIDE_COASTER', 'request_id': review.run_id+':existing-order'})
    order_id = dispatched['result']['work_order_id']
    conflict = review.execute(proposal, 'context-navigation', 409)
    duplicate = review.http.call('/api/workflows/proposals',
        {**payload, 'request_id': payload['request_id']+'-new'}, 409)
    navigation = []
    for name, response in [('execution_conflict', conflict), ('already_open', duplicate)]:
        context = response['detail']['context']
        require(order_id in context['current_work_order_ids'], f'{name}: existing work-order identity missing')
        route = context['asset_detail_url']
        require(route == '/api/assets/RIDE_COASTER', f'{name}: asset-detail destination is incorrect')
        step = context['next_step']
        require('existing' in step.lower() and 'work' in step.lower(), f'{name}: next step does not direct operator to existing work')
        detail = review.http.call(route)
        order = next((w for w in detail['work_orders'] if w['id'] == order_id), None)
        require(order is not None and order['status'] == 'open', f'{name}: linked asset does not contain exact open order')
        navigation.append({'conflict': name, 'next_step': step, 'url': route, 'work_order': order})
    changed = conflict['detail']['context']['changed_fields']
    require(changed and 'work_order' in json.dumps(changed), 'Execution conflict omitted changed work-order predicates')
    return {'execution_conflict': conflict, 'new_proposal_conflict': duplicate,
        'read_only_navigation': navigation, 'exact_existing_order_id': order_id}


def stale_readback(review):
    proposal, payload = review.proposal('stale-readback')
    initial = review.execute(proposal, 'stale-readback')
    review.fault_readback(initial)
    initial_receipt = initial['proposal']['receipt']
    require('asset_status_evidence' in initial['proposal']['readback'], 'Readback has no separate asset-status evidence')
    review.http.call('/api/connectors/ride_scada/simulation', {'mode': 'paused'})
    before = asset(review.http.call('/api/state'), 'RIDE_COASTER')['data_quality']['fields']['status']
    threshold = float(before['stale_after_seconds'])
    original_timestamp = before['source_timestamp']
    began = time.monotonic()
    while time.monotonic()-began <= threshold+1.1:
        time.sleep(.2)
    waited = time.monotonic()-began
    after = asset(review.http.call('/api/state'), 'RIDE_COASTER')['data_quality']['fields']['status']
    require(after['status'] == 'stale' and after['source_timestamp'] == original_timestamp,
        'SCADA fixture did not retain its original timestamp as stale')
    audit = review.http.call('/api/audit')['events']
    recovered = review.execute(proposal, 'stale-readback')
    require(recovered['idempotency']['replayed'] and recovered['proposal']['receipt'] == initial_receipt,
        'Stale-source recovery changed original acknowledgement')
    readback = recovered['proposal']['readback']
    evidence = readback['asset_status_evidence']
    (review.output/'stale-recovery-response.json').write_text(json.dumps(recovered, indent=2)+'\n')
    quality = evidence.get('quality')
    quality_status = quality.get('status') if isinstance(quality, dict) else quality
    if quality_status is None:
        quality_status = evidence.get('status')
    require(quality_status == 'stale', 'Current work-order readback promoted stale asset status to fresh')
    require(evidence['source_timestamp'] == original_timestamp, 'Readback restamped stale source status')
    require(evidence['source_id'] == 'ride_scada', 'Readback lost asset-status source ownership')
    require(datetime.fromisoformat(readback['observed_at']) > datetime.fromisoformat(original_timestamp),
        'Database readback and original telemetry times are not distinguished')
    require(readback['work_order']['id'] == initial_receipt['work_order_id'], 'Recovery read a different work order')
    require(readback['physical_completion'] is False and recovered['physical_effect'] is False, 'Readback claims physical completion')
    require(review.http.call('/api/audit')['events'] == audit, 'Readback recovery issued a new command')
    return {'actual_wall_wait_seconds': waited, 'declared_stale_after_seconds': threshold,
        'canonical_before': before, 'canonical_after': after,
        'initial_receipt': initial_receipt, 'recovered_readback': readback,
        'original_receipt_preserved': True, 'no_new_audit': True}


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
    try:
        gateway.start()
        review.check('existing_work_order_navigation', lambda: conflict_navigation(review))
        review.check('stale_scada_receipt_recovery', lambda: stale_readback(review))
        review.check('cleanup', lambda: review.reset('normal'))
    finally:
        cleanup = gateway.stop()
        scripts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            Path(__file__), Path(__file__).with_name('workflow_checks.py'), Path(__file__).with_name('api_operator.py')]}
        report = {'started_at': started, 'finished_at': utc(), 'url': gateway.url,
            'checks': review.results, 'failures': sum(c['status'] != 'pass' for c in review.results),
            'gateway_starts': gateway.starts, 'process_cleanup': cleanup, 'client_source_sha256': scripts,
            'scope': 'Two targeted HTTP checks plus cleanup; actual wall-clock stale transition, no simulated clocks or backend imports. Earlier full-suite evidence remains separate.'}
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(1 if report['failures'] else 0)


if __name__ == '__main__':
    main()
