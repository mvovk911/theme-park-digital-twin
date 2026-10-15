"""Upload an exact committed release via audited hgx exec; stage without restarting."""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile

from release_artifact import build, git, safe_path

ROOT = Path(__file__).resolve().parents[1]


def remote(worker: str, command: str):
    subprocess.run(['hgx', 'exec', worker, '--timeout', '120', '--', command], check=True)


def upload(worker: str, path: str, data: bytes):
    # Both transfer paths and payload use Python literals; no user input is shell code.
    remote(worker, 'python3 -c ' + shlex.quote(f'from pathlib import Path; p=Path({path!r}); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b"")'))
    for offset in range(0, len(data), 32000):
        encoded = base64.b64encode(data[offset:offset + 32000]).decode('ascii')
        script = f'import base64; open({path!r},"ab").write(base64.b64decode({encoded!r}))'
        remote(worker, 'python3 -c ' + shlex.quote(script))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', default='park-twin-rtx')
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--remote-root', default='/home/horde/park-twin-deploy')
    parser.add_argument('--activate', action='store_true', help='Promote current symlink after staging; does not restart services')
    args = parser.parse_args()
    root = args.remote_root
    if not root.startswith('/') or root == '/':
        parser.error('--remote-root must be an absolute dedicated release layout directory')
    safe_path(root.lstrip('/'))
    with tempfile.TemporaryDirectory(prefix='park-release-') as directory:
        archive = Path(directory) / 'release.tar.gz'
        manifest = build(ROOT, args.revision, archive)
        commit = manifest['commit']
        data = archive.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        # Run the committed verifier, not possibly modified local worktree code.
        verifier = git(ROOT, 'show', f'{commit}:scripts/release_artifact.py')
        incoming = f'{root}/incoming/{commit}-{digest[:16]}'
        remote_archive, remote_verifier = incoming + '/release.tar.gz', incoming + '/release_artifact.py'
        upload(args.worker, remote_archive, data)
        upload(args.worker, remote_verifier, verifier)
        verifier_digest = hashlib.sha256(verifier).hexdigest()
        check = f'import hashlib, sys; from pathlib import Path; actual=hashlib.sha256(Path({remote_verifier!r}).read_bytes()).hexdigest(); actual == {verifier_digest!r} or sys.exit("Verifier transfer SHA256 mismatch")'
        remote(args.worker, 'python3 -c ' + shlex.quote(check))
        invocation = ['python3', remote_verifier, 'stage', remote_archive, '--root', root,
                      '--sha256', digest, '--commit', commit]
        remote(args.worker, shlex.join(invocation))
        if args.activate:
            remote(args.worker, shlex.join(['python3', remote_verifier, 'activate', '--root', root, '--commit', commit]))
        print(f'Staged commit {commit} (tree {manifest["tree"]}, archive SHA256 {digest}) on {args.worker}')
        print('current source pointer promoted; processes unchanged' if args.activate else 'No source pointer or running process changed')


if __name__ == '__main__':
    main()
