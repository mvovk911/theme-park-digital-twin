#!/usr/bin/env python3
"""Supervise one isolated backend and measured-duration API evaluation.

Launch this script detached (start_new_session=True) from a frozen source tree.
Unexpected backend exits are journaled and restarted at most three times. The
operator is never silently restarted or its failed evidence rewritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--port', type=int, default=18120)
    parser.add_argument('--duration-seconds', type=float, default=28800)
    parser.add_argument('--interval-seconds', type=float, default=300)
    parser.add_argument('--pause-file', required=True)
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.interval_seconds <= 0:
        raise ValueError('Duration and interval must be positive')
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    project = Path(args.project).resolve()
    python = os.path.abspath(args.python)  # Preserve venv symlink identity.
    base = f'http://127.0.0.1:{args.port}'
    # Never adopt or terminate an unrelated server already on the requested port.
    with socket.socket() as check:
        check.bind(('127.0.0.1', args.port))
    summary = {'started_at': utc(), 'supervisor_pid': os.getpid(), 'project': str(project),
        'python': python, 'url': base, 'requested_duration_seconds': args.duration_seconds,
        'backend_restarts': [], 'complete': False, 'phase': 'starting',
        'source_files': {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ['backend', 'operators'] for p in sorted((project/directory).rglob('*.py'))}}
    summary['source_files']['main.py'] = hashlib.sha256((project/'main.py').read_bytes()).hexdigest()
    backend = operator = None
    def event(kind, **fields):
        with (root/'supervisor-events.jsonl').open('a') as handle:
            handle.write(json.dumps({'utc': utc(), 'event': kind, **fields})+'\n')
    def save():
        temporary = root/'supervisor.json.tmp'
        temporary.write_text(json.dumps(summary, indent=2)+'\n')
        temporary.replace(root/'supervisor.json')
    def start_backend():
        env = dict(os.environ, PARK_DB=str(root/'park.db'), PARK_REPLAY_DB=str(root/'replay.db'))
        with (root/'backend.log').open('ab') as log:
            child = subprocess.Popen([python, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(args.port)],
                cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        summary['backend_pid'] = child.pid
        event('backend_started', pid=child.pid)
        return child
    def stop(child, name):
        if child is None or child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
            event('forced_kill', process=name)
        event('process_stopped', process=name, exit_code=child.returncode)
    def interrupt(signum, frame):
        raise KeyboardInterrupt(f'Signal {signum}')
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        backend = start_backend()
        ready_deadline = time.monotonic()+45
        while True:
            try:
                with urllib.request.urlopen(base+'/api/health', timeout=3) as response:
                    health = json.load(response)
                if health.get('synthetic') is not True or health.get('status') != 'ok':
                    raise RuntimeError('Backend is not healthy and synthetic')
                summary['initial_health'] = health
                break
            except (OSError, ValueError):
                if backend.poll() is not None or time.monotonic() > ready_deadline:
                    raise RuntimeError('Isolated backend failed startup')
                time.sleep(.5)
        command = [python, str(project/'operators/api_operator.py'), '--url', base,
            '--output', str(root/'evaluation'), '--duration-seconds', str(args.duration_seconds),
            '--interval-seconds', str(args.interval_seconds), '--pause-file', str(Path(args.pause_file).resolve()),
            '--include-planner', '--allow-synthetic-writes']
        with (root/'operator.log').open('ab') as log:
            operator = subprocess.Popen(command, cwd=project, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        summary.update(operator_pid=operator.pid, operator_command=command, phase='running')
        event('operator_started', pid=operator.pid)
        save()
        # The operator owns the eight-hour clock. This outer bound allows startup,
        # a final cycle and cleanup without turning a stuck process into completion.
        deadline = time.monotonic()+args.duration_seconds+120
        while operator.poll() is None:
            if backend.poll() is not None:
                restart = {'utc': utc(), 'exit_code': backend.returncode, 'old_pid': backend.pid}
                summary['backend_restarts'].append(restart)
                event('backend_exited_unexpectedly', **restart)
                if len(summary['backend_restarts']) > 3:
                    raise RuntimeError('Backend restart budget exhausted')
                backend = start_backend()
            if time.monotonic() > deadline:
                raise RuntimeError('Operator exceeded duration plus cleanup allowance')
            summary['last_checked_at'] = utc()
            save()
            time.sleep(2)
        summary['operator_exit_code'] = operator.returncode
        evaluated = json.loads((root/'evaluation/summary.json').read_text())
        summary.update(complete=evaluated.get('complete') is True,
            operator_started_at=evaluated.get('started_at'), operator_finished_at=evaluated.get('finished_at'),
            measured_operator_elapsed_seconds=evaluated.get('elapsed_seconds'),
            operator_failures=evaluated.get('failures'), completed_cycles=evaluated.get('completed_cycles'),
            phase='finished' if evaluated.get('complete') else 'interrupted')
    except BaseException as error:
        summary.update(phase='interrupted', error=f'{type(error).__name__}: {error}')
        event('supervisor_interrupted', error=summary['error'])
    finally:
        stop(operator, 'operator')
        stop(backend, 'backend')
        summary['finished_at'] = utc()
        save()
    raise SystemExit(0 if summary['complete'] and not summary.get('operator_failures') and not summary['backend_restarts'] else 1)


if __name__ == '__main__':
    main()
