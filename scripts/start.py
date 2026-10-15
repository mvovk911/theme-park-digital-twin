"""Start the two loopback-only demo processes; logs/PIDs live in runtime/."""
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
runtime = root / 'runtime'
runtime.mkdir(exist_ok=True)
# Runtime caches are not release source; keep child imports from writing into it.
env = dict(os.environ, PARK_API_URL=os.environ.get('PARK_API_URL', 'http://127.0.0.1:8100'),
           PYTHONDONTWRITEBYTECODE='1')
python = str(root / '.venv/bin/python')
for role, command in {
    'backend': [python, '-B', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8100'],
    'renderer': [python, '-B', 'renderer/service.py'],
}.items():
    pidfile = runtime / f'{role}.pid'
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text())
            os.kill(pid, 0)
            if str(root) in str(Path(f'/proc/{pid}/cwd').resolve()):
                print(f'{role} already running: {pid}')
                continue
        except (ValueError, ProcessLookupError, FileNotFoundError):
            pass
    with (runtime / f'{role}.log').open('ab') as log:
        process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    pidfile.write_text(str(process.pid))
    print(f'Started {role}: {process.pid}')
