"""Native preview consistency, bounded fixed paths, and immutable HTTP serving."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.spatial import SpatialIdentityError, install_spatial_routes
from backend.spatial import previews
from backend.spatial.service import ROOT, BASE_GRAPH, VARIANT_GRAPH, BASE_SCENE, BASE_GEOMETRY, VARIANT_LAYER, VARIANT_EVIDENCE


def app(root):
    application = FastAPI()
    install_spatial_routes(application, project_root=root)
    return application


@pytest.fixture
def project(tmp_path):
    for name in (BASE_GRAPH, VARIANT_GRAPH, BASE_SCENE, BASE_GEOMETRY, VARIANT_LAYER, VARIANT_EVIDENCE):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    shutil.copytree(ROOT / previews.PREVIEW_ROOT, tmp_path / previews.PREVIEW_ROOT)
    return tmp_path


def folder(project, variant='baseline'):
    return project / previews.PREVIEW_ROOT / variant


def change_report(project, change, variant='baseline'):
    path = folder(project, variant) / 'report.json'
    data = json.loads(path.read_bytes())
    change(data)
    path.write_text(json.dumps(data))


def unavailable(client, variant='baseline'):
    for suffix in ('', '/metadata'):
        reply = client.get('/api/spatial/previews/' + variant + suffix)
        assert reply.status_code == 503
        assert reply.json()['detail']['code'] == 'spatial_preview_unavailable'
    assert client.get('/api/spatial/graphs/' + variant).status_code == 200


def test_actual_native_captures_match_graph_and_expose_curated_metadata(project):
    with TestClient(app(project)) as client:
        cameras = []
        for variant in previews.VARIANTS:
            image = client.get('/api/spatial/previews/' + variant)
            meta = client.get('/api/spatial/previews/' + variant + '/metadata')
            assert image.status_code == meta.status_code == 200
            assert image.headers['content-type'] == 'image/png'
            body = meta.json()
            identity = client.get('/api/spatial/graphs/' + variant).json()['identity']
            assert body['identity'] == identity
            assert image.content == (folder(project, variant) / previews.IMAGE_NAME).read_bytes()
            assert body['image_sha256'] == hashlib.sha256(image.content).hexdigest()
            assert body['report_sha256'] == hashlib.sha256((folder(project, variant) / 'report.json').read_bytes()).hexdigest()
            assert body['native_sdk_versions']['ovstage_version']
            assert body['native_sdk_versions']['ovrtx_version']
            assert body['capture_finished_at'] and body['verified_at']
            assert body['live_telemetry'] is False and body['execution_authority'] == 'none'
            assert body['snapshot_policy'] == 'immutable_until_restart'
            assert '/home/horde' not in meta.text
            assert 'composition_layers_strongest_first' not in body
            for key, expected in {
                'X-Spatial-Graph-Sha256': identity['graph_sha256'],
                'X-Spatial-Scene-Sha256': identity['baseline_scene_sha256'],
                'X-Spatial-Variant-Layer-Sha256': identity['variant_layer_sha256'] or '',
                'X-Spatial-Preview-Image-Sha256': body['image_sha256'],
                'X-Spatial-Preview-Report-Sha256': body['report_sha256'],
                'X-Spatial-Preview-Mode': 'static_native',
            }.items():
                assert image.headers[key] == meta.headers[key] == expected
            cameras.append(body['camera'])
        assert cameras[0] == cameras[1] == previews.CAMERA
        assert client.get('/api/spatial/previews/unknown').status_code == 422


@pytest.mark.parametrize('change', [
    lambda d: d.update(complete=False),
    lambda d: d.update(native_rendered=False),
    lambda d: d.update(prepared=False),
    lambda d: d.update(mode='cpu_preparation_only'),
    lambda d: d.update(live_telemetry=True),
    lambda d: d.update(cleanup_errors=['detach failure']),
    lambda d: d.update(error='failed'),
    lambda d: d.update(variant='dining_connection'),
    lambda d: d.update(overlay_mode='diagnostic'),
    lambda d: d.update(scene_sha256='0' * 64),
    lambda d: d['identity'].update(graph_sha256='0' * 64),
    lambda d: d['composition_layers_strongest_first'][0].update(role='diagnostic_overlay'),
    lambda d: d['composition_layers_strongest_first'][0].update(sha256='0' * 64),
    lambda d: d['composition_layers_strongest_first'].append(copy.deepcopy(d['composition_layers_strongest_first'][0])),
    lambda d: d['captures'][0].update(native_rendered=False),
    lambda d: d['captures'][0].update(sha256='0' * 64),
    lambda d: d['captures'][0].update(composition_sha256='0' * 64),
    lambda d: d['captures'][0].update(file='/etc/passwd'),
    lambda d: d['captures'][0].update(composition_file='../../outside.usda'),
    lambda d: d['captures'][0].update(eye_m=[-2., -43., 17.]),
    lambda d: d['captures'][0].update(width=800),
    lambda d: d['prepared_views'][0].update(focal_length_mm=21),
    lambda d: d.update(finished_at='2000-01-01T00:00:00Z'),
    lambda d: d.update(ovrtx_version=None),
])
def test_invalid_optional_report_has_no_fallback_and_preserves_core_graph(project, change):
    change_report(project, change)
    with TestClient(app(project)) as client:
        unavailable(client)
        assert client.get('/api/spatial/previews/dining_connection').status_code == 200


@pytest.mark.parametrize('name', ['report.json', previews.IMAGE_NAME, previews.COMPOSITION_NAME])
def test_missing_optional_file_stays_unavailable_until_restart(project, name):
    path = folder(project) / name
    contents = path.read_bytes()
    path.unlink()
    application = app(project)
    path.write_bytes(contents)
    with TestClient(application) as client:
        unavailable(client)
    with TestClient(app(project)) as restarted:
        assert restarted.get('/api/spatial/previews/baseline').status_code == 200


def test_replacement_after_installation_does_not_change_verified_bytes(project):
    application = app(project)
    with TestClient(application) as client:
        first = client.get('/api/spatial/previews/baseline')
        initial_metadata = client.get('/api/spatial/previews/baseline/metadata').json()
        (folder(project) / previews.IMAGE_NAME).write_bytes(b'changed')
        (folder(project) / 'report.json').write_text('{}')
        second = client.get('/api/spatial/previews/baseline')
        assert first.content == second.content
        assert first.headers['x-spatial-preview-image-sha256'] == second.headers['x-spatial-preview-image-sha256']
        assert client.get('/api/spatial/previews/baseline/metadata').json() == initial_metadata
    with TestClient(app(project)) as restarted:
        unavailable(restarted)


@pytest.mark.parametrize('limit', ['MAX_REPORT_BYTES', 'MAX_IMAGE_BYTES', 'MAX_COMPOSITION_BYTES'])
def test_optional_files_are_bounded(project, monkeypatch, limit):
    monkeypatch.setattr(previews, limit, 1)
    with TestClient(app(project)) as client:
        unavailable(client)


def test_corrupted_png_with_updated_report_hash_is_not_served(project):
    image = folder(project) / previews.IMAGE_NAME
    data = bytearray(image.read_bytes())
    data[45] ^= 1
    image.write_bytes(data)
    change_report(project, lambda d: d['captures'][0].update(sha256=hashlib.sha256(data).hexdigest()))
    with TestClient(app(project)) as client:
        unavailable(client)


def test_composition_layer_order_is_checked_even_with_consistent_file_hash(project):
    variant = 'dining_connection'
    path = folder(project, variant) / previews.COMPOSITION_NAME
    data = path.read_text().replace('assets/variants/dining_connection.usda', 'assets/park.usdc')
    path.write_text(data)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    def update(report):
        report['captures'][0]['composition_sha256'] = sha
        report['prepared_views'][0]['composition_sha256'] = sha
    change_report(project, update, variant)
    with TestClient(app(project)) as client:
        unavailable(client, variant)


def test_preview_symlink_and_fifo_are_not_read(project, tmp_path):
    target = folder(project) / previews.IMAGE_NAME
    original = target.read_bytes()
    target.unlink()
    outside = tmp_path / 'outside.png'
    outside.write_bytes(original)
    target.symlink_to(outside)
    with TestClient(app(project)) as client:
        unavailable(client)
    target.unlink()
    os.mkfifo(target)
    with TestClient(app(project)) as client:
        unavailable(client)


def test_invalid_core_identity_still_fails_installation(project):
    path = project / BASE_GRAPH
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(SpatialIdentityError):
        app(project)


@pytest.mark.parametrize('raw', [b'[]', b'null', b'{"complete":true,"complete":false}', b'{"frames":NaN}', b'{'])
def test_malformed_report_is_optional_unavailable(project, raw):
    (folder(project) / 'report.json').write_bytes(raw)
    with TestClient(app(project)) as client:
        unavailable(client)


@pytest.mark.parametrize('change', [
    lambda d: d.update(captures=[[]]),
    lambda d: d.update(composition_layers_strongest_first=['bad']),
    lambda d: d['composition_layers_strongest_first'][0].update(file=123),
    lambda d: d.update(started_at=123),
])
def test_malformed_nested_report_is_optional_unavailable(project, change):
    change_report(project, change)
    with TestClient(app(project)) as client:
        unavailable(client)
