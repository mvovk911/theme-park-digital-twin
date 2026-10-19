"""Public HTTP contracts, fail-closed provenance, and live-state independence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.spatial import SpatialIdentityError, SpatialService, install_spatial_routes
from backend.spatial.contracts import RouteRequest
from backend.spatial.service import (ROOT, BASE_GRAPH, VARIANT_GRAPH, BASE_SCENE,
                                    BASE_GEOMETRY, VARIANT_LAYER, VARIANT_EVIDENCE)


@pytest.fixture
def app():
    app = FastAPI()
    install_spatial_routes(app)
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def copied_project(tmp_path):
    for name in (BASE_GRAPH, VARIANT_GRAPH, BASE_SCENE, BASE_GEOMETRY, VARIANT_LAYER, VARIANT_EVIDENCE):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def request(client, **kwargs):
    return client.post('/api/spatial/route', json={'origin': 'ENTRY_GATE', 'destination': 'FOOD_COURT', **kwargs})


def test_capabilities_and_graphs_expose_read_only_identity(client):
    capabilities = client.get('/api/spatial/capabilities').json()
    assert capabilities['execution_authority'] == 'none'
    assert capabilities['live_state_bound'] is capabilities['forecast_coupled'] is False
    assert capabilities['request_limits']['max_blocked_edges'] == 32
    assert {x['variant'] for x in capabilities['variants']} == {'baseline', 'dining_connection'}
    base = client.get('/api/spatial/graphs/baseline').json()
    variant = client.get('/api/spatial/graphs/dining_connection').json()
    assert base['identity']['variant_layer_sha256'] is None
    assert len(variant['identity']['variant_layer_sha256']) == 64
    assert variant['identity']['baseline_graph_sha256'] == base['identity']['graph_sha256']
    assert base['graph']['asset_entrances']['FOOD_COURT'] == 'food_entrance'
    assert variant['graph']['asset_entrances']['FOOD_COURT'] == 'food_connector_entrance'


def test_before_after_closure_and_accessibility_abstention(client):
    before = request(client)
    assert before.status_code == 200 and before.json()['reachable'] is False
    after = request(client, variant='dining_connection')
    assert after.status_code == 200
    result = after.json()
    assert result['reachable'] and result['distance_m'] == pytest.approx(40.852, abs=.001)
    assert result['execution_authority'] == 'none' and result['mutates_live_state'] is False
    assert result['calibrated'] is result['forecast_coupled'] is result['physical_guidance'] is False
    assert '2D plan distance' in result['distance_basis']
    assert result['entrance_scope']['destination_node'] == 'food_connector_entrance'
    assert result['variant_design']['layer_sha256'] == result['identity']['variant_layer_sha256']
    closed = request(client, variant='dining_connection', blocked_edges=['dining_connector_link']).json()
    assert closed['reachable'] is False and closed['distance_m'] is None
    restricted = request(client, variant='dining_connection', accessible_only=True).json()
    assert restricted['reachable'] is False


def test_reachable_wheel_is_approach_not_boarding(client):
    result = request(client, destination='RIDE_WHEEL').json()
    assert result['reachable']
    assert result['entrance_scope']['destination_node'] == 'wheel_approach'
    assert 'boarding' in result['entrance_scope']['destination_note']
    assert request(client, destination='wheel_boarding').json()['reachable'] is False


@pytest.mark.parametrize('update', [
    {'origin': 'UNKNOWN'}, {'destination': 'UNKNOWN'}, {'blocked_edges': ['does_not_exist']},
    {'blocked_edges': ['entry_main', 'entry_main']}, {'blocked_edges': ['x'] * 33},
    {'origin': 'A' * 65}, {'destination': '../FOOD_COURT'}, {'blocked_edges': ['X' * 65]},
    {'variant': 'real_park'}, {'walking_speed_mps': .29}, {'walking_speed_mps': 2.51},
    {'walking_speed_mps': '1.2'}, {'walking_speed_mps': True}, {'accessible_only': 'false'},
    {'accessible_only': 0}, {'blocked_edges': 'entry_main'}, {'origin': 1},
    {'execute': True}, {'enable_edges': ['food_missing_link']},
])
def test_strict_unknown_and_bounded_requests(client, update):
    assert request(client, **update).status_code == 422


def test_unknown_graph_rejected(client):
    assert client.get('/api/spatial/graphs/unknown').status_code == 422


@pytest.mark.parametrize('body', [
    '{"origin":"ENTRY_GATE","origin":"UNKNOWN","destination":"FOOD_COURT"}',
    '{"origin":"ENTRY_GATE","destination":"FOOD_COURT","walking_speed_mps":NaN}',
    '{"origin":"ENTRY_GATE","destination":"FOOD_COURT","walking_speed_mps":Infinity}',
    '{', 'null', '[]',
])
def test_malformed_duplicate_or_nonfinite_json_rejected(client, body):
    result = client.post('/api/spatial/route', content=body, headers={'content-type': 'application/json'})
    assert result.status_code == 422


def test_oversized_and_wrong_media_type_rejected(client):
    assert client.post('/api/spatial/route', content=b' ' * (16 * 1024 + 1),
                       headers={'content-type': 'application/json'}).status_code == 413
    assert client.post('/api/spatial/route', content='{}', headers={'content-type': 'text/plain'}).status_code == 415


@pytest.mark.parametrize('path', [BASE_SCENE, BASE_GEOMETRY, BASE_GRAPH, VARIANT_GRAPH, VARIANT_LAYER])
def test_tampered_identity_refuses_installation_and_exposes_no_routes(copied_project, path):
    target = copied_project / path
    target.write_bytes(target.read_bytes() + b'\n')  # Also catches semantically unchanged JSON byte tampering.
    app = FastAPI()
    with pytest.raises(SpatialIdentityError):
        install_spatial_routes(app, project_root=copied_project)
    assert not getattr(app.state, 'spatial_installed', False)
    assert all(not route.path.startswith('/api/spatial') for route in app.routes)


def test_tampered_evidence_declaration_refuses_installation(copied_project):
    target = copied_project / VARIANT_EVIDENCE
    evidence = json.loads(target.read_text())
    evidence['variant_graph_sha256'] = '0' * 64
    target.write_text(json.dumps(evidence))
    with pytest.raises(SpatialIdentityError):
        SpatialService(copied_project)


def test_graph_metadata_cannot_choose_arbitrary_local_paths(copied_project):
    target = copied_project / BASE_GRAPH
    graph = json.loads(target.read_text())
    graph['source_scene'] = '/etc/passwd'
    target.write_text(json.dumps(graph))
    with pytest.raises(SpatialIdentityError, match='Unexpected source asset path'):
        SpatialService(copied_project)


def test_returned_graph_edits_cannot_change_installed_snapshot(client):
    first = client.get('/api/spatial/graphs/baseline').json()
    before = deepcopy(first)
    first['graph']['asset_entrances']['FOOD_COURT'] = 'entry'
    first['identity']['graph_sha256'] = '0' * 64
    assert client.get('/api/spatial/graphs/baseline').json() == before
    assert request(client).json()['reachable'] is False


def test_disk_edits_after_installation_cannot_enter_verified_snapshot(copied_project):
    service = SpatialService(copied_project)
    query = RouteRequest(origin='ENTRY_GATE', destination='FOOD_COURT', variant='dining_connection')
    before = service.route(query)
    (copied_project / VARIANT_GRAPH).write_text('{}')
    assert service.route(query) == before
    assert before['identity']['snapshot_policy'] == 'immutable_until_restart'
    with pytest.raises(SpatialIdentityError):
        SpatialService(copied_project)


def test_queries_do_not_access_or_mutate_live_or_replay_state(app):
    class Forbidden:
        def __getattribute__(self, name):
            raise AssertionError('Spatial query touched live/replay state')
    app.state.park = app.state.read_model = app.state.replay = Forbidden()
    before = {key: value for key, value in app.state._state.items()}
    with TestClient(app) as client:
        assert request(client, variant='dining_connection').status_code == 200
        assert client.get('/api/spatial/graphs/baseline').status_code == 200
    assert app.state._state == before


def test_duplicate_installation_rejected(app):
    with pytest.raises(ValueError, match='already'):
        install_spatial_routes(app)


def test_openapi_documents_strict_request_body(client):
    operation = client.get('/openapi.json').json()['paths']['/api/spatial/route']['post']
    schema = operation['requestBody']['content']['application/json']['schema']
    assert schema['additionalProperties'] is False
    assert schema['properties']['blocked_edges']['maxItems'] == 32
