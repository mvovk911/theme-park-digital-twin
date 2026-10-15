"""Manual GPU acceptance: run the real render owner through startup and cleanup.

Stop the serving renderer first; keep its backend running. This probe starts no
HTTP server and writes only the requested evidence file. It exercises actual SDK
cleanup calls, not a GPU leak benchmark or simulated-resource unit test.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--api-url', default='http://127.0.0.1:8100')
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 600:
        parser.error('timeout must be between 10 and 600 seconds')
    sys.path.insert(0, str(args.project.resolve()))
    os.environ['PARK_API_URL'] = args.api_url
    from renderer import service

    samples = []
    deadline = time.monotonic() + args.timeout
    def observe():
        while time.monotonic() < deadline:
            status = service.status()
            if status.get('phase') == 'failed':
                break
            if status.get('ready') and status.get('frame', 0) >= 20:
                samples.append(status)
                break
            time.sleep(.1)
        service.stop_event.set()
    monitor = threading.Thread(target=observe, daemon=True)
    monitor.start()
    try:
        service.render_loop()
    finally:
        service.stop_event.set()
        monitor.join(timeout=2)
    final = service.status()
    passed = bool(samples) and final.get('phase') == 'stopped' and final.get('cleanup_errors') == [] and service.commands.outstanding == 0
    report = {
        'kind': 'actual_ovstage_ovrtx_startup_and_cleanup',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'passed': passed, 'source_identity': final.get('source_identity'),
        'scene_revision': final.get('scene_revision'),
        'ovstage_version': final.get('ovstage_version'),
        'ovrtx_version': final.get('ovrtx_version'),
        'rendered_frames': final.get('frame'),
        'ready_before_stop': bool(samples), 'final_phase': final.get('phase'),
        'cleanup_errors': final.get('cleanup_errors'), 'error': final.get('error'),
        'outstanding_commands': service.commands.outstanding,
        'scope': 'Real render loop and native cleanup calls; no claim of exhaustive leak or concurrency certification',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
