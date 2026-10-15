"""Release boundary tests use local temporary Git repositories, never a GPU/network."""
import gzip
import hashlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
import subprocess
import tarfile

import pytest

SPEC = importlib.util.spec_from_file_location('release_artifact', Path(__file__).parents[1] / 'scripts/release_artifact.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args]).decode().strip()


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / 'repo'
    path.mkdir()
    git(path, 'init', '-q')
    git(path, 'config', 'user.name', 'Release test')
    git(path, 'config', 'user.email', 'test@example.invalid')
    (path / 'backend').mkdir()
    (path / 'backend/app.py').write_text('committed source\n')
    (path / 'obsolete.py').write_text('old module\n')
    for name in ['runtime/token', '.env', '.venv/secret', 'backend/data/park.db', 'private.key']:
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('SECRET_DO_NOT_TRANSFER')
    git(path, 'add', '.')
    git(path, 'commit', '-qm', 'fixture')
    return path


def artifact(repo, tmp_path):
    archive = tmp_path / 'release.tar.gz'
    manifest = release.build(repo, 'HEAD', archive)
    return archive, manifest, hashlib.sha256(archive.read_bytes()).hexdigest()


def rewrite(archive, mutate):
    with tarfile.open(archive, 'r:gz') as source:
        members = [(m, source.extractfile(m).read()) for m in source]
    members = mutate(members)
    with tarfile.open(archive, 'w:gz') as target:
        for member, data in members:
            member.size = len(data)
            target.addfile(member, io.BytesIO(data) if member.isfile() else None)


def test_commit_bytes_not_dirty_worktree_or_index(repo, tmp_path):
    before = tmp_path / 'before.tar.gz'
    release.build(repo, 'HEAD', before)
    (repo / 'backend/app.py').write_text('uncommitted malicious edit')
    (repo / 'obsolete.py').unlink()
    (repo / 'untracked.py').write_text('not committed')
    git(repo, 'add', '-A')
    archive, manifest, digest = artifact(repo, tmp_path)
    assert archive.read_bytes() == before.read_bytes()
    verified, files = release.verify(archive, digest, git(repo, 'rev-parse', 'HEAD'))
    assert files['backend/app.py'] == b'committed source\n'
    assert 'obsolete.py' in files and 'untracked.py' not in files
    assert b'SECRET_DO_NOT_TRANSFER' not in gzip.decompress(archive.read_bytes())
    assert {entry['path'] for entry in verified['excluded']} >= {'.env', 'private.key', 'runtime/token'}


def test_fresh_stage_removes_deleted_source_preserves_shared_runtime(repo, tmp_path):
    archive, first, digest = artifact(repo, tmp_path)
    root = tmp_path / 'deployment'
    old = release.stage(archive, root, digest, first['commit'])
    (old / 'runtime/state').write_text('persistent')
    (old / 'backend/data/db').write_text('database')
    release.activate(root, first['commit'])
    (repo / 'obsolete.py').unlink()
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'remove obsolete')
    archive, second, digest = artifact(repo, tmp_path)
    new = release.stage(archive, root, digest, second['commit'])
    assert not (new / 'obsolete.py').exists()
    assert (old / 'obsolete.py').is_file()
    assert (new / 'runtime/state').read_text() == 'persistent'
    assert (new / 'backend/data/db').read_text() == 'database'
    assert (root / 'current').resolve() == old
    release.activate(root, second['commit'])
    assert (root / 'current').resolve() == new
    release.activate(root, first['commit'])
    assert (root / 'current').resolve() == old
    with pytest.raises(release.ReleaseError, match='never overlay'):
        release.stage(archive, root, digest, second['commit'])


@pytest.mark.parametrize('attack', ['../escape', '/absolute', 'x/../../escape', 'x\\escape', './relative'])
def test_reject_unsafe_archive_paths_before_any_write(repo, tmp_path, attack):
    archive, manifest, digest = artifact(repo, tmp_path)
    def mutate(members):
        info = tarfile.TarInfo(attack)
        return members + [(info, b'bad')]
    rewrite(archive, mutate)
    with pytest.raises(release.ReleaseError, match='path'):
        release.stage(archive, tmp_path / 'deployment', hashlib.sha256(archive.read_bytes()).hexdigest(), manifest['commit'])
    assert not (tmp_path / 'deployment').exists()


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE])
def test_reject_links_and_nonregular_members(repo, tmp_path, kind):
    archive, manifest, _ = artifact(repo, tmp_path)
    def mutate(members):
        info = tarfile.TarInfo('link')
        info.type = kind
        info.linkname = '/etc/passwd'
        return members + [(info, b'')]
    rewrite(archive, mutate)
    with pytest.raises(release.ReleaseError, match='Non-regular'):
        release.verify(archive)


def test_corruption_manifest_and_identity_mismatch(repo, tmp_path):
    archive, manifest, digest = artifact(repo, tmp_path)
    with pytest.raises(release.ReleaseError, match='commit mismatch'):
        release.verify(archive, digest, '0' * 40)
    def mutate(members):
        return [(member, b'corrupt' if member.name == 'backend/app.py' else data) for member, data in members]
    rewrite(archive, mutate)
    with pytest.raises(release.ReleaseError, match='Archive SHA256'):
        release.verify(archive, digest)
    with pytest.raises(release.ReleaseError, match='metadata mismatch|SHA256 mismatch'):
        release.verify(archive)


def test_missing_file_duplicate_member_and_invalid_manifest(repo, tmp_path):
    archive, manifest, digest = artifact(repo, tmp_path)
    original = archive.read_bytes()
    rewrite(archive, lambda members: [(m, d) for m, d in members if m.name != 'obsolete.py'])
    with pytest.raises(release.ReleaseError, match='file set mismatch'):
        release.verify(archive)
    archive.write_bytes(original)
    rewrite(archive, lambda members: members + [members[-1]])
    with pytest.raises(release.ReleaseError, match='duplicate'):
        release.verify(archive)
    archive.write_bytes(original)
    def mutate(members):
        changed = []
        for m, data in members:
            if m.name == release.MANIFEST:
                value = json.loads(data)
                value['shared_links']['runtime'] = '/outside'
                data = json.dumps(value).encode()
            changed.append((m, data))
        return changed
    rewrite(archive, mutate)
    with pytest.raises(release.ReleaseError, match='shared paths'):
        release.verify(archive)


def test_git_symlinks_and_managed_path_symlinks_refused(repo, tmp_path):
    (repo / 'evil').symlink_to('/etc/passwd')
    git(repo, 'add', 'evil')
    git(repo, 'commit', '-qm', 'unsupported link')
    with pytest.raises(release.ReleaseError, match='Unsupported Git entry'):
        artifact(repo, tmp_path)
    git(repo, 'rm', 'evil')
    git(repo, 'commit', '-qm', 'remove link')
    archive, manifest, digest = artifact(repo, tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'deployment'
    root.symlink_to(outside)
    with pytest.raises(release.ReleaseError, match='Symlink'):
        release.stage(archive, root, digest, manifest['commit'])
    assert not list(outside.iterdir())


def test_activation_rejects_changed_staged_bytes(repo, tmp_path):
    archive, manifest, digest = artifact(repo, tmp_path)
    root = tmp_path / 'deployment'
    staged = release.stage(archive, root, digest, manifest['commit'])
    (staged / 'backend/app.py').write_text('modified after staging')
    with pytest.raises(release.ReleaseError, match='Staged file changed'):
        release.activate(root, manifest['commit'])
    assert not (root / 'current').exists()


@pytest.mark.parametrize('change', ['extra', 'shared_redirect', 'mode'])
def test_activation_inventory_and_shared_link_integrity(repo, tmp_path, change):
    archive, manifest, digest = artifact(repo, tmp_path)
    root = tmp_path / 'deployment'
    staged = release.stage(archive, root, digest, manifest['commit'])
    if change == 'extra':
        (staged / 'untracked.py').write_text('leftover')
    elif change == 'shared_redirect':
        (staged / 'runtime').unlink()
        (staged / 'runtime').symlink_to(tmp_path)
    else:
        (staged / 'backend/app.py').chmod(0o755)
    with pytest.raises(release.ReleaseError, match='Staged|staged'):
        release.activate(root, manifest['commit'])
    assert not (root / 'current').exists()


def test_reactivation_after_real_python_import_ignores_only_transient_dirs(repo, tmp_path):
    (repo / 'backend/simulator.py').write_text('VALUE = 42\n')
    git(repo, 'add', 'backend/simulator.py')
    git(repo, 'commit', '-qm', 'importable backend module')
    archive, manifest, digest = artifact(repo, tmp_path)
    root = tmp_path / 'deployment'
    staged = release.stage(archive, root, digest, manifest['commit'])
    release.activate(root, manifest['commit'])
    env = dict(os.environ)
    env.pop('PYTHONDONTWRITEBYTECODE', None)
    env.pop('PYTHONPYCACHEPREFIX', None)
    env.pop('PYTHONPATH', None)  # Import the staged fixture, never the test runner's tree.
    subprocess.run([sys.executable, '-c', 'import backend.simulator; assert backend.simulator.VALUE == 42'],
                   cwd=staged, env=env, check=True)
    assert list((staged / 'backend/__pycache__').glob('simulator.*.pyc'))
    cache = staged / '.pytest_cache'
    cache.mkdir()
    (cache / 'README.md').write_text('non-authoritative test output')
    assert release.activate(root, manifest['commit']) == staged
    (staged / 'backend/unknown_source.py').write_text('unexpected = True')
    with pytest.raises(release.ReleaseError, match='layout set mismatch'):
        release.activate(root, manifest['commit'])


@pytest.mark.parametrize('name', ['__pycache__', '.pytest_cache'])
def test_transient_directory_exemption_never_allows_symlink(repo, tmp_path, name):
    archive, manifest, digest = artifact(repo, tmp_path)
    root = tmp_path / 'deployment'
    staged = release.stage(archive, root, digest, manifest['commit'])
    (staged / name).symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(release.ReleaseError, match='Unexpected staged symlink'):
        release.activate(root, manifest['commit'])
