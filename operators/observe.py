#!/usr/bin/env python3
"""Read-only HTTP availability and optional GPU frame-provenance observation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import time
import urllib.request
from api_operator import HTTP, require, utc


def timestamp_age(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'Timestamp has no timezone')
    return (datetime.now(timezone.utc)-parsed).total_seconds()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--duration-seconds', type=float, default=28800)
    parser.add_argument('--interval-seconds', type=float, default=30)
    parser.add_argument('--require-renderer', action='store_true')
    parser.add_argument('--save-frame-every-seconds', type=float, default=3600)
    args = parser.parse_args()
    require(args.duration_seconds >= 0 and args.interval_seconds > 0, 'Invalid timing')
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    def journal(event):
        with (root/'events.jsonl').open('a') as handle:
            handle.write(json.dumps(event, sort_keys=True)+'\n')
    client = HTTP(args.url, journal)
    started = time.monotonic()
    summary = {'mode': 'read_only_http_observer', 'uses_llm': False, 'started_at': utc(),
        'url': args.url, 'requested_duration_seconds': args.duration_seconds,
        'interval_seconds': args.interval_seconds, 'requires_renderer': args.require_renderer,
        'complete': False, 'samples': 0, 'failed_samples': 0, 'failures': [],
        'max_health_latency_ms': 0, 'max_frame_age_seconds': None}
    last_saved = float('-inf')
    previous = None
    def save():
        summary['elapsed_seconds'] = round(time.monotonic()-started, 3)
        temporary = root/'summary.json.tmp'
        temporary.write_text(json.dumps(summary, indent=2)+'\n')
        temporary.replace(root/'summary.json')
    try:
        while True:
            sample_started = time.monotonic()
            sample = {'type': 'observation', 'utc': utc(), 'index': summary['samples']}
            try:
                before = time.monotonic()
                health = client.call('/api/health')
                latency = round((time.monotonic()-before)*1000, 2)
                summary['max_health_latency_ms'] = max(latency, summary['max_health_latency_ms'])
                require(health.get('status') == 'ok' and health.get('synthetic') is True, 'Gateway unhealthy or not synthetic')
                view = client.call('/api/view/state')
                sample.update(health=health, view=view['view'], source_tick=view['tick'],
                    scenario=view['scenario'], accepted_state_revision=view.get('accepted_state_revision'),
                    connector_health=view.get('connector_health'), kpis=view['kpis'])
                if previous and health['source_identity'].get('checked_at') == previous['health']['source_identity'].get('checked_at'):
                    require(health['tick'] > previous['health']['tick'], 'Simulator tick did not progress between observations')
                if args.require_renderer:
                    with urllib.request.urlopen(args.url.rstrip('/')+'/render/frame.jpg', timeout=20) as response:
                        body = response.read()
                        headers = {k.lower(): v for k,v in response.headers.items()}
                        require(response.status == 200, 'Frame not available')
                    require(body[:2] == b'\xff\xd8', 'Renderer response is not a JPEG')
                    # Frame metadata is read only from the exact downloaded image.
                    sample['frame'] = {'headers': {k:v for k,v in headers.items() if k.startswith(('x-frame-', 'x-source-', 'x-view-', 'x-scene-', 'x-accepted-'))},
                        'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
                    require(re.fullmatch(r'[0-9a-f]{64}', headers.get('x-source-revision', '')), 'Frame lacks canonical state identity')
                    require(headers.get('x-frame-camera-token'), 'Frame lacks camera identity')
                    require(headers.get('x-view-mode') in ('live', 'replay'), 'Frame lacks view identity')
                    context = json.loads(headers.get('x-frame-context', '{}'))
                    require(context.get('width', 0) > 0 and context.get('height', 0) > 0 and 'camera' in context, 'Frame lacks image/camera context')
                    rendered_at = headers.get('x-frame-rendered-at') or headers.get('x-frame-timestamp')
                    require(rendered_at, 'Frame lacks rendered timestamp')
                    age = timestamp_age(rendered_at)
                    sample['frame']['age_seconds'] = round(age, 3)
                    require(-1 <= age <= 15, f'Frame age outside observation limit: {age:.2f}s')
                    summary['max_frame_age_seconds'] = max(summary['max_frame_age_seconds'] or 0, age)
                    if sample_started-last_saved >= args.save_frame_every_seconds:
                        filename = f'frame-{summary["samples"]:05d}.jpg'
                        (root/filename).write_bytes(body)
                        sample['frame']['saved_file'] = filename
                        last_saved = sample_started
                sample['status'] = 'pass'
                previous = sample
            except Exception as error:
                sample.update(status='fail', error=f'{type(error).__name__}: {error}')
                summary['failed_samples'] += 1
                summary['failures'].append({'index': summary['samples'], 'utc': sample['utc'], 'error': sample['error']})
            summary['samples'] += 1
            journal(sample)
            print(json.dumps({'index': sample['index'], 'status': sample['status'], 'utc': sample['utc']}), flush=True)
            save()
            if time.monotonic()-started >= args.duration_seconds:
                break
            until = min(started+args.duration_seconds, sample_started+args.interval_seconds)
            while time.monotonic() < until:
                time.sleep(min(10, until-time.monotonic()))
                save()
            if time.monotonic()-started >= args.duration_seconds:
                break
        summary.update(complete=True, finished_at=utc())
    except BaseException as error:
        summary['interruption'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        save()
    raise SystemExit(1 if summary['failed_samples'] else 0)


if __name__ == '__main__':
    main()
