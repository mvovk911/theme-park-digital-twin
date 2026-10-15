"""Stop only the demo processes recorded by start.py; retain all runtime data."""
import argparse
import os
from pathlib import Path
import signal
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('role',nargs='?',choices=['backend','renderer','all'],default='all')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
for role in (['backend','renderer'] if args.role=='all' else [args.role]):
    pidfile=root/'runtime'/f'{role}.pid'
    if not pidfile.exists():
        print(f'{role}: no recorded process');continue
    pid=int(pidfile.read_text())
    proc=Path(f'/proc/{pid}')
    try:
        command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
        marker='renderer/service.py' if role=='renderer' else 'uvicorn main:app'
        if (proc/'cwd').resolve()!=root or marker not in command:
            print(f'{role}: recorded PID no longer belongs to this service; left untouched')
            continue
        os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+15
        while (proc/'cwd').exists() and time.monotonic()<deadline:
            time.sleep(.1)
        if (proc/'cwd').exists():
            raise SystemExit(f'{role}: still shutting down; inspect PID {pid} before restarting')
        pidfile.unlink(missing_ok=True)
        print(f'{role}: stopped')
    except (ProcessLookupError,FileNotFoundError):
        pidfile.unlink(missing_ok=True)
        print(f'{role}: already stopped')
