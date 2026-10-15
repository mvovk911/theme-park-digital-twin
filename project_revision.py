"""Inspect source bytes once at startup; this is not executing-code attestation."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

_SHARED = {'runtime': 'runtime', 'backend/data': 'data', '.venv': '.venv'}
_TRANSIENT = {'__pycache__', '.pytest_cache'}


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _safe(name):
    return isinstance(name, str) and name and '\\' not in name and not PurePosixPath(name).is_absolute() and all(p not in {'', '.', '..'} for p in name.split('/'))


def source_identity(root):
    """Return plain JSON values describing this root at inspection time only."""
    root = Path(root).resolve()
    result = dict(source='unknown', commit=None, tree=None, disposition='unknown', verified=False,
                  dirty=None, scene_path='assets/park.usdc', scene_sha256=None, mismatches=[],
                  checked_at=datetime.now(timezone.utc).isoformat(),
                  verification_scope='Source files on disk at startup; not process attestation or GPU acceptance')
    scene = root / result['scene_path']
    try:
        if scene.is_file() and not scene.is_symlink():
            result['scene_sha256'] = _hash(scene)
    except OSError:
        pass
    manifest_path = root / 'release-manifest.json'
    if manifest_path.exists() or manifest_path.is_symlink():
        result.update(source='release_manifest', disposition='invalid_manifest')
        try:
            if manifest_path.is_symlink():
                raise ValueError('manifest symlink')
            manifest = json.loads(manifest_path.read_text())
            if manifest['schema_version'] != 1 or manifest['shared_links'] != _SHARED:
                raise ValueError('manifest layout/schema')
            if any(not isinstance(manifest[k], str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', manifest[k]) for k in ('commit', 'tree')):
                raise ValueError('manifest Git identity')
            files = manifest['files']
            if not isinstance(files, dict) or not all(_safe(p) and not any(p == link or p.startswith(link + '/') for link in _SHARED) for p in files):
                raise ValueError('manifest file paths')
            result.update(commit=manifest['commit'], tree=manifest['tree'])
            mismatches = set()
            for name, meta in files.items():
                if meta['mode'] not in {0o644, 0o755} or not isinstance(meta['size'], int) or meta['size'] < 0 or not re.fullmatch(r'[0-9a-f]{64}', meta['sha256']):
                    raise ValueError('manifest file metadata')
                path = root / name
                if any(p.is_symlink() for p in [path, *list(path.parents)[:len(PurePosixPath(name).parts)-1]]) or not path.is_file() or path.stat().st_size != meta['size'] or path.stat().st_mode & 0o777 != meta['mode'] or _hash(path) != meta['sha256']:
                    mismatches.add(name)
            found = set()
            for directory, dirs, names in os.walk(root, followlinks=False):
                for name in dirs[:]:
                    path = Path(directory) / name
                    rel = path.relative_to(root).as_posix()
                    if rel in _SHARED:
                        dirs.remove(name)
                    elif path.is_symlink():
                        mismatches.add(rel)
                        dirs.remove(name)
                    elif name in _TRANSIENT:
                        dirs.remove(name)
                found.update((Path(directory) / n).relative_to(root).as_posix() for n in names)
            mismatches.update(found - set(files) - {'release-manifest.json'})
            result.update(disposition='modified_manifest' if mismatches else 'verified_manifest',
                          verified=not mismatches, dirty=bool(mismatches), mismatches=sorted(mismatches))
        except (OSError, ValueError, KeyError, TypeError):
            result['mismatches'] = ['invalid release-manifest.json']
        return result
    if (root / '.git').exists():
        try:
            def git(*args):
                return subprocess.check_output(['git', '-c', 'core.fsmonitor=false', '-C', str(root), *args], stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if Path(git('rev-parse', '--show-toplevel')).resolve() != root.resolve():
                return result
            dirty = bool(git('status', '--porcelain', '--untracked-files=all'))
            result.update(source='git', commit=git('rev-parse', 'HEAD'), tree=git('rev-parse', 'HEAD^{tree}'),
                          disposition='dirty_git' if dirty else 'clean_git', dirty=dirty, verified=not dirty)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return result
