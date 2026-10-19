"""Geometric and routing invariants; no renderer, network, or runtime database."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import re

import pytest

from modeling.circulation import ROOT, find_route, load_graph, validate_graph, write_overlay


@pytest.fixture
def graph():
    return load_graph()


def test_source_scene_is_the_registered_artifact(graph):
    for path, digest in [(graph['source_scene'], graph['source_scene_sha256']),
                         (graph['source_geometry'], graph['source_geometry_sha256'])]:
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest


def test_paving_dimensions_match_actual_usda(graph):
    """Check copied footprint dimensions against source prims, not generator intent."""
    source = (ROOT / graph['source_geometry']).read_text()
    for surface in graph['surfaces']:
        name = surface['prim_path'].rsplit('/', 1)[-1]
        kind = 'Cube' if surface['shape'] == 'rectangle' else 'Cylinder'
        match = re.search(r'def ' + kind + r' "' + re.escape(name) + r'".*?\n\s*\{(.*?)\n\s*\}', source, re.S)
        assert match, surface['prim_path']
        body = match.group(1)
        position = re.search(r'xformOp:translate = \((.*?)\)', body)
        actual = [float(v) for v in position.group(1).split(',')]
        if kind == 'Cube':
            scale = re.search(r'xformOp:scale = \((.*?)\)', body)
            assert actual == surface['center_m']
            assert [float(v) for v in scale.group(1).split(',')] == surface['size_m']
        else:
            assert actual[:2] == surface['center_xy_m']
            assert float(re.search(r'double radius = ([\d.]+)', body).group(1)) == surface['radius_m']


def test_entry_wheel_uses_approach_not_boarding(graph):
    route = find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL')
    assert route['reachable']
    assert route['destination_node'] == 'wheel_approach'
    assert route['distance_m'] > 85
    assert route['assumed_walking_seconds'] == pytest.approx(route['distance_m'] / 1.2, abs=.01)
    assert not find_route(graph, 'ENTRY_GATE', 'wheel_boarding')['reachable']


def test_show_reached_via_west_not_invisible_lake_shortcut(graph):
    route = find_route(graph, 'ENTRY_GATE', 'SHOW_ARENA')
    assert route['reachable']
    assert 'west_north' in route['edge_ids']
    assert 'north_show' in route['edge_ids']
    assert route['distance_m'] > 190
    assert not find_route(graph, 'ENTRY_GATE', 'SHOW_ARENA', blocked_edges=['west_north'])['reachable']


@pytest.mark.parametrize('destination', ['FOOD_COURT', 'RIDE_COASTER', 'northeast_isolated'])
def test_known_missing_connections_are_unreachable(graph, destination):
    route = find_route(graph, 'ENTRY_GATE', destination)
    assert not route['reachable']
    assert route['distance_m'] is None
    assert route['assumed_walking_seconds'] is None
    assert not route['positions_m']


def test_coaster_closure_alternative_is_from_public_approach(graph):
    route = find_route(graph, 'coaster_approach', 'RIDE_WHEEL')
    assert route['reachable']
    assert 'coaster_missing_link' not in route['edge_ids']
    assert route['distance_m'] > math.dist(route['positions_m'][0], route['positions_m'][-1])
    assert not find_route(graph, 'RIDE_COASTER', 'RIDE_WHEEL')['reachable']


def test_blocked_edge_causes_a_real_detour(graph):
    normal = find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL')
    detour = find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL', blocked_edges=['plaza_south_e'])
    assert detour['reachable']
    assert 'plaza_south_e' not in detour['edge_ids']
    assert 'plaza_north' in detour['edge_ids']
    assert detour['distance_m'] > normal['distance_m']


def test_accessibility_filter_is_applied_and_labelled(graph):
    assert not find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL', accessible_only=True)['reachable']
    assert find_route(graph, 'wheel_junction', 'RIDE_WHEEL', accessible_only=True)['reachable']
    altered = deepcopy(graph)
    next(e for e in altered['edges'] if e['id'] == 'wheel_public_approach')['modeled_step_free'] = False
    assert find_route(altered, 'wheel_junction', 'RIDE_WHEEL')['reachable']
    restricted = find_route(altered, 'wheel_junction', 'RIDE_WHEEL', accessible_only=True)
    assert not restricted['reachable']
    assert 'not certified' in restricted['accessibility_basis']


def test_speed_changes_time_not_distance_or_path(graph):
    fast = find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL', walking_speed_mps=1.2)
    slow = find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL', walking_speed_mps=.6)
    assert fast['distance_m'] == slow['distance_m']
    assert fast['edge_ids'] == slow['edge_ids']
    assert slow['assumed_walking_seconds'] == pytest.approx(fast['assumed_walking_seconds'] * 2, abs=.02)


@pytest.mark.parametrize('speed', [0, -1, math.nan, math.inf, True])
def test_invalid_speed_rejected(graph, speed):
    with pytest.raises(ValueError):
        find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL', walking_speed_mps=speed)


def test_unknown_node_and_unknown_closure_are_errors(graph):
    with pytest.raises(ValueError, match='origin'):
        find_route(graph, 'UNMAPPED', 'RIDE_WHEEL')
    with pytest.raises(ValueError, match='blocked edge'):
        find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL', blocked_edges=['typo'])


def test_grass_shortcut_cannot_be_promoted_to_walkable(graph):
    broken = deepcopy(graph)
    edge = next(e for e in broken['edges'] if e['id'] == 'food_missing_link')
    edge['status'] = 'walkable'
    edge['surface_ids'] = ['main', 'food']
    with pytest.raises(ValueError, match='leaves its cited paving'):
        validate_graph(broken)


def test_fountain_shortcut_is_rejected_even_on_paving(graph):
    broken = deepcopy(graph)
    broken['edges'].append({'id': 'bad_shortcut', 'from': 'plaza_west', 'to': 'plaza_east',
                            'status': 'walkable', 'surface_ids': ['cross', 'plaza'],
                            'assumed_corridor_width_m': 2, 'modeled_step_free': True})
    with pytest.raises(ValueError, match='crosses fountain'):
        validate_graph(broken)


def test_queries_do_not_mutate_source(graph):
    before = deepcopy(graph)
    find_route(graph, 'ENTRY_GATE', 'RIDE_WHEEL', blocked_edges=['plaza_south_e'])
    assert graph == before


def test_overlay_is_reproducible_and_additive(graph, tmp_path):
    path = tmp_path / 'overlay.usda'
    write_overlay(graph, path)
    assert path.read_bytes() == (ROOT / 'assets/circulation_overlay.usda').read_bytes()
    text = path.read_text()
    assert 'def Xform "CirculationPreview"' in text
    assert 'def Xform "Park"' not in text
    assert 'subLayers' not in text
    assert 'missing_connection' in text and 'obstructed' in text
