"""Startup provenance inspects local source, never a remote repository or GPU."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location('project_revision', Path(__file__).parents[1] / 'project_revision.py')
revision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(revision)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args]).decode().strip()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'source'
    (root / 'assets').mkdir(parents=True)
    (root / 'app.py').write_text('source\n')
    (root / 'assets/park.usdc').write_bytes(b'scene bytes')
    return root


def write_manifest(root):
    files = {}
    for path in [root / 'app.py', root / 'assets/park.usdc']:
        files[path.relative_to(root).as_posix()] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                                   'size': path.stat().st_size, 'mode': path.stat().st_mode & 0o777}
    manifest = {'schema_version': 1, 'commit': 'a' * 40, 'tree': 'b' * 40,
                'files': files, 'shared_links': revision._SHARED, 'excluded': []}
    (root / 'release-manifest.json').write_text(json.dumps(manifest))
    return manifest


def test_clean_manifest_and_actual_scene_hash(source):
    write_manifest(source)
    for name in ['runtime', 'backend/data', '.venv', '__pycache__']:
        target = source / name
        target.mkdir(parents=True)
        (target / 'ignored').write_text('shared state or cache')
    result = revision.source_identity(source)
    assert result['source'] == 'release_manifest'
    assert result['disposition'] == 'verified_manifest'
    assert result['verified'] is True and result['dirty'] is False
    assert result['commit'] == 'a' * 40 and result['tree'] == 'b' * 40
    assert result['scene_sha256'] == hashlib.sha256(b'scene bytes').hexdigest()
    assert result['mismatches'] == []
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize('change', ['mutated', 'missing', 'extra', 'mode', 'symlink_parent'])
def test_changed_staged_source_is_unverified(source, tmp_path, change):
    write_manifest(source)
    if change == 'mutated':
        (source / 'app.py').write_text('changed')
    elif change == 'missing':
        (source / 'app.py').unlink()
    elif change == 'extra':
        (source / 'new.py').write_text('untracked source')
    elif change == 'mode':
        (source / 'app.py').chmod(0o755)
    else:
        (source / 'assets').rename(tmp_path / 'outside')
        (source / 'assets').symlink_to(tmp_path / 'outside', target_is_directory=True)
    result = revision.source_identity(source)
    assert result['disposition'] == 'modified_manifest'
    assert result['dirty'] is True and result['verified'] is False
    assert result['mismatches']


def test_missing_manifest_unknown_does_not_guess_parent_git(source, tmp_path):
    for path in [source, tmp_path / 'does-not-exist']:
        result = revision.source_identity(path)
        assert result['source'] == 'unknown' and result['commit'] is None
        assert result['disposition'] == 'unknown' and result['dirty'] is None
        assert result['verified'] is False
    git(source, 'init', '-q')
    nested = source / 'nested'
    nested.mkdir()
    assert revision.source_identity(nested)['source'] == 'unknown'


def test_local_git_clean_staged_unstaged_and_untracked(source):
    git(source, 'init', '-q')
    git(source, 'config', 'user.name', 'Source identity test')
    git(source, 'config', 'user.email', 'test@example.invalid')
    git(source, 'add', '.')
    git(source, 'commit', '-qm', 'source')
    clean = revision.source_identity(source)
    assert clean['disposition'] == 'clean_git' and clean['verified'] is True
    assert clean['commit'] == git(source, 'rev-parse', 'HEAD')
    (source / 'app.py').write_text('dirty')
    assert revision.source_identity(source)['disposition'] == 'dirty_git'
    git(source, 'add', 'app.py')
    assert revision.source_identity(source)['dirty'] is True
    git(source, 'reset', '--hard', 'HEAD')
    (source / 'untracked').write_text('new')
    dirty = revision.source_identity(source)
    assert dirty['disposition'] == 'dirty_git' and dirty['verified'] is False


@pytest.mark.parametrize('malformed', ['json', 'unsafe_path', 'schema', 'symlink'])
def test_invalid_manifest_never_falls_back_to_git(source, tmp_path, malformed):
    manifest = write_manifest(source)
    git(source, 'init', '-q')
    path = source / 'release-manifest.json'
    if malformed == 'json':
        path.write_text('{invalid')
    elif malformed == 'unsafe_path':
        manifest['files']['../outside'] = next(iter(manifest['files'].values()))
        path.write_text(json.dumps(manifest))
    elif malformed == 'schema':
        manifest['schema_version'] = 900
        path.write_text(json.dumps(manifest))
    else:
        target = tmp_path / 'manifest'
        path.rename(target)
        path.symlink_to(target)
    result = revision.source_identity(source)
    assert result['source'] == 'release_manifest'
    assert result['disposition'] == 'invalid_manifest' and result['verified'] is False
    assert result['mismatches'] == ['invalid release-manifest.json']


@pytest.mark.parametrize('name', ['__pycache__', '.pytest_cache'])
def test_cache_named_symlink_is_modified_source_not_exempt(source, tmp_path, name):
    write_manifest(source)
    (source / name).symlink_to(tmp_path, target_is_directory=True)
    result = revision.source_identity(source)
    assert result['disposition'] == 'modified_manifest'
    assert result['verified'] is False
    assert name in result['mismatches']
