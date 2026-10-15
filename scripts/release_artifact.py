"""Build and stage immutable Git releases. Standard library only; no service control."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

MANIFEST = 'release-manifest.json'
SCHEMA = 1
MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 20000
# Non-authoritative interpreter/test outputs; matches project_revision inspection.
TRANSIENT_DIRS = {'__pycache__', '.pytest_cache'}
SHARED_LINKS = {'runtime': 'runtime', 'backend/data': 'data', '.venv': '.venv'}
EXCLUDED_PARTS = {'.git', '.venv', 'runtime', '__pycache__', '.pytest_cache', 'data', 'reference', 'tools'}
EXCLUDED_SUFFIXES = {'.pyc', '.db', '.log', '.zip', '.gz', '.blend', '.pem', '.key', '.p12', '.pfx'}


class ReleaseError(ValueError):
    """Unsafe or inconsistent release input."""


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(repo), *args])


def safe_path(name: str) -> str:
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ReleaseError(f'Invalid release path: {name!r}')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in {'', '.', '..'} for p in name.split('/')):
        raise ReleaseError(f'Unsafe release path: {name!r}')
    return name


def exclusion(name: str) -> str | None:
    path = PurePosixPath(name)
    if any(p in EXCLUDED_PARTS for p in path.parts):
        return 'environment, runtime, cache or non-runtime tooling'
    if path.name.startswith('.env'):
        return 'environment configuration'
    if path.suffix in EXCLUDED_SUFFIXES or path.name.endswith(('.db-shm', '.db-wal')):
        return 'non-runtime binary, runtime data or credential file'
    return None


def build(repo: Path, revision: str, output: Path) -> dict:
    """Read committed objects only, including when the index/worktree are dirty."""
    commit = git(repo, 'rev-parse', '--verify', f'{revision}^{{commit}}').decode().strip()
    tree = git(repo, 'rev-parse', f'{commit}^{{tree}}').decode().strip()
    files, excluded, payload = {}, [], {}
    total = 0
    for entry in git(repo, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not entry:
            continue
        header, raw_name = entry.split(b'\t', 1)
        mode, kind, oid = header.decode().split()
        name = safe_path(raw_name.decode('utf-8'))
        reason = exclusion(name)
        if reason:
            excluded.append({'path': name, 'reason': reason})
            continue
        if name == MANIFEST or kind != 'blob' or mode not in {'100644', '100755'}:
            raise ReleaseError(f'Unsupported Git entry (links/submodules/reserved manifest): {name}')
        data = git(repo, 'cat-file', 'blob', oid)
        total += len(data)
        if total > MAX_BYTES or len(files) >= MAX_FILES:
            raise ReleaseError('Release exceeds size/file-count limit')
        files[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
                       'mode': int(mode[-3:], 8)}
        payload[name] = data
    manifest = {'schema_version': SCHEMA, 'commit': commit, 'tree': tree,
                'files': files, 'excluded': excluded, 'shared_links': SHARED_LINKS}
    encoded = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temp:
        temp_path = Path(temp.name)
        try:
            with gzip.GzipFile(fileobj=temp, mode='wb', mtime=0, filename='') as zipped:
                with tarfile.open(fileobj=zipped, mode='w') as archive:
                    for name, data in [(MANIFEST, encoded), *sorted(payload.items())]:
                        info = tarfile.TarInfo(name)
                        info.size = len(data)
                        info.mode = files[name]['mode'] if name in files else 0o644
                        archive.addfile(info, io.BytesIO(data))
            temp.flush()
            os.fsync(temp.fileno())
            os.replace(temp_path, output)
        finally:
            temp_path.unlink(missing_ok=True)
    return manifest


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def verify(archive_path: Path, expected_sha256: str | None = None,
           expected_commit: str | None = None) -> tuple[dict, dict[str, bytes]]:
    """Validate every member before extraction; never use tar.extract/extractall."""
    if archive_path.stat().st_size > MAX_BYTES:
        raise ReleaseError('Compressed archive exceeds size limit')
    if expected_sha256 and hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected_sha256:
        raise ReleaseError('Archive SHA256 mismatch')
    payload = {}
    total = 0
    try:
        with tarfile.open(archive_path, 'r:gz') as archive:
            for member in archive:
                name = safe_path(member.name)
                if not member.isfile() or member.linkname or name in payload:
                    raise ReleaseError(f'Non-regular or duplicate archive member: {name}')
                total += member.size
                if member.size < 0 or total > MAX_BYTES or len(payload) >= MAX_FILES + 1:
                    raise ReleaseError('Expanded release exceeds limit')
                payload[name] = archive.extractfile(member).read()
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ReleaseError(f'Invalid release archive: {exc}') from exc
    try:
        manifest = json.loads(payload.pop(MANIFEST), object_pairs_hook=_unique_json)
        if manifest['schema_version'] != SCHEMA:
            raise ReleaseError('Unsupported manifest schema')
        if any(not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', manifest[key]) for key in ('commit', 'tree')):
            raise ReleaseError('Invalid Git identity')
        if expected_commit and manifest['commit'] != expected_commit:
            raise ReleaseError('Manifest commit mismatch')
        if manifest['shared_links'] != SHARED_LINKS:
            raise ReleaseError('Unexpected shared paths')
        files = manifest['files']
        if set(files) != set(payload):
            raise ReleaseError('Manifest file set mismatch')
        for name, meta in files.items():
            safe_path(name)
            if exclusion(name) or name == MANIFEST:
                raise ReleaseError(f'Excluded path in release: {name}')
            if meta['mode'] not in {0o644, 0o755} or meta['size'] != len(payload[name]):
                raise ReleaseError(f'File metadata mismatch: {name}')
            if hashlib.sha256(payload[name]).hexdigest() != meta['sha256']:
                raise ReleaseError(f'File SHA256 mismatch: {name}')
        for item in manifest['excluded']:
            safe_path(item['path'])
            if not exclusion(item['path']) or item['path'] in files:
                raise ReleaseError('Invalid exclusion ledger')
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f'Invalid release manifest: {exc}') from exc
    return manifest, payload


def _directory(path: Path):
    """Managed layout must not redirect writes through preexisting symlinks."""
    for item in [path, *path.parents]:
        if item.is_symlink():
            raise ReleaseError(f'Symlink in managed directory path: {item}')
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ReleaseError(f'Not a directory: {path}')


def stage(archive: Path, root: Path, expected_sha256: str, expected_commit: str) -> Path:
    manifest, payload = verify(archive, expected_sha256, expected_commit)
    root = root.absolute()
    _directory(root)
    releases, shared = root / 'releases', root / 'shared'
    _directory(releases)
    _directory(shared)
    destination = releases / manifest['commit']
    if destination.exists() or destination.is_symlink():
        raise ReleaseError(f'Release already exists; never overlay it: {destination}')
    temporary = Path(tempfile.mkdtemp(prefix='.staging-', dir=releases))
    try:
        for name, data in payload.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(manifest['files'][name]['mode'])
        (temporary / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
        for name, shared_name in SHARED_LINKS.items():
            target = shared / shared_name
            _directory(target)
            link = temporary / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def activate(root: Path, commit: str) -> Path:
    """Atomic source pointer promotion only. Caller owns compatibility and restart."""
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise ReleaseError('Activation requires a full commit SHA')
    root = root.absolute()
    _directory(root)
    release = root / 'releases' / commit
    _directory(release.parent)
    if release.is_symlink() or not release.is_dir():
        raise ReleaseError('Release has not been staged')
    manifest = json.loads((release / MANIFEST).read_text(), object_pairs_hook=_unique_json)
    if manifest['commit'] != commit or manifest['schema_version'] != SCHEMA or manifest['shared_links'] != SHARED_LINKS:
        raise ReleaseError('Staged identity/layout mismatch')
    files = manifest['files']
    expected_files = set(files) | {MANIFEST}
    expected_dirs = set()
    for name in [*expected_files, *SHARED_LINKS]:
        safe_path(name)
        expected_dirs.update(str(p) for p in PurePosixPath(name).parents if str(p) != '.')
    found_files, found_links, found_dirs = set(), set(), set()
    for directory, dirs, names in os.walk(release, followlinks=False):
        for name in [*dirs, *names]:
            path = Path(directory) / name
            relative = path.relative_to(release).as_posix()
            if path.is_symlink():
                if relative not in SHARED_LINKS or path.resolve() != root / 'shared' / SHARED_LINKS[relative]:
                    raise ReleaseError(f'Unexpected staged symlink: {relative}')
                _directory(root / 'shared' / SHARED_LINKS[relative])
                found_links.add(relative)
            elif path.is_dir():
                if name in TRANSIENT_DIRS:
                    dirs.remove(name)
                    continue
                found_dirs.add(relative)
            elif path.is_file():
                found_files.add(relative)
            else:
                raise ReleaseError(f'Unexpected staged entry: {relative}')
    if found_files != expected_files or found_links != set(SHARED_LINKS) or found_dirs != expected_dirs:
        raise ReleaseError('Staged file/layout set mismatch')
    for name, meta in files.items():
        path = release / safe_path(name)
        if exclusion(name) or meta['mode'] not in {0o644, 0o755}:
            raise ReleaseError(f'Invalid staged metadata: {name}')
        if path.stat().st_size != meta['size'] or path.stat().st_mode & 0o777 != meta['mode'] or hashlib.sha256(path.read_bytes()).hexdigest() != meta['sha256']:
            raise ReleaseError(f'Staged file changed: {name}')
    current = root / 'current'
    if current.exists() and not current.is_symlink():
        raise ReleaseError('Current pointer is an existing non-symlink path')
    temporary = root / '.current-next'
    if temporary.exists() or temporary.is_symlink():
        raise ReleaseError('Another activation or stale .current-next needs inspection')
    try:
        temporary.symlink_to(Path('releases') / commit, target_is_directory=True)
        os.replace(temporary, current)
    finally:
        temporary.unlink(missing_ok=True)
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    builder = commands.add_parser('build')
    builder.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    builder.add_argument('--revision', default='HEAD')
    builder.add_argument('--output', type=Path, required=True)
    for command in ('verify', 'stage'):
        sub = commands.add_parser(command)
        sub.add_argument('archive', type=Path)
        sub.add_argument('--sha256', required=True)
        sub.add_argument('--commit', required=True)
        if command == 'stage':
            sub.add_argument('--root', type=Path, required=True)
    promoter = commands.add_parser('activate')
    promoter.add_argument('--root', type=Path, required=True)
    promoter.add_argument('--commit', required=True)
    args = parser.parse_args()
    if args.command == 'build':
        manifest = build(args.repo, args.revision, args.output)
        print(json.dumps({'commit': manifest['commit'], 'tree': manifest['tree'],
                          'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(), 'archive': str(args.output)}))
    elif args.command == 'verify':
        manifest, _ = verify(args.archive, args.sha256, args.commit)
        print(json.dumps({'verified': True, 'commit': manifest['commit']}))
    elif args.command == 'stage':
        print(stage(args.archive, args.root, args.sha256, args.commit))
    else:
        print(activate(args.root, args.commit))


if __name__ == '__main__':
    main()
