"""Acceptance checks for a reversible, provenance-bound dining design layer."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from modeling.circulation import ROOT, find_route, load_graph
from modeling.dining_variant import (BOUNDS, CURB_SEGMENTS, TOP_Z, X_STATIONS,
    paving_mesh, positive_intersection, sha256, surface_height, variant_graph,
    write_layer, xy_clearance)

VARIANTS = ROOT / 'assets/variants'


@pytest.fixture
def graph():
    return load_graph(VARIANTS / 'dining_circulation_graph.json')


@pytest.fixture
def evidence():
    return json.loads((VARIANTS / 'dining_connection_evidence.json').read_text())


def test_variant_has_separate_provenance_and_preserves_baseline(graph, evidence):
    assert graph['source_scene_sha256'] == sha256(ROOT / 'assets/park.usdc')
    assert graph['variant']['layer_sha256'] == sha256(VARIANTS / 'dining_connection.usda')
    assert graph['variant']['baseline_graph_sha256'] == sha256(ROOT / 'assets/circulation_graph.json')
    assert evidence['variant_graph_sha256'] == sha256(VARIANTS / 'dining_circulation_graph.json')
    for path, digest in evidence['preserved_baseline_artifact_hashes'].items():
        assert sha256(ROOT / path) == digest


def test_food_becomes_reachable_and_closing_connector_reverses_it(graph):
    assert not find_route(load_graph(), 'ENTRY_GATE', 'FOOD_COURT')['reachable']
    after = find_route(graph, 'ENTRY_GATE', 'FOOD_COURT')
    assert after['reachable']
    assert after['destination_node'] == 'food_connector_entrance'
    assert after['distance_m'] == pytest.approx(40.852, abs=.001)
    assert 'dining_connector_link' in after['edge_ids']
    assert not find_route(graph, 'ENTRY_GATE', 'FOOD_COURT', blocked_edges=['dining_connector_link'])['reachable']


def test_variant_does_not_claim_accessible_entry(graph):
    assert not find_route(graph, 'ENTRY_GATE', 'FOOD_COURT', accessible_only=True)['reachable']
    assert find_route(graph, 'dining_main_landing', 'FOOD_COURT', accessible_only=True)['reachable']
    assert '2D plan distance' in graph['variant']['distance_basis']


def test_endpoint_is_adjusted_without_moving_baseline_node(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    assert nodes['food_entrance']['position_m'] == [-12.5, -27, .3]
    assert nodes['food_connector_entrance']['position_m'] == [-12.5, -26.4, .3]
    route = find_route(graph, 'ENTRY_GATE', 'FOOD_COURT')
    assert 'food_service' not in route['node_ids']
    assert 'food_interior' not in route['edge_ids']


def test_grade_matches_both_surfaces_without_end_steps():
    assert surface_height(-13.5) == surface_height(-11.5) == .325
    assert surface_height(-5) == surface_height(-4.5) == .24
    assert surface_height(-8.25) == pytest.approx(.2825)
    assert (.325 - .24) / 6.5 * 100 == pytest.approx(1.3076923077)
    for x in (-13.5001, -4.4999):
        with pytest.raises(ValueError):
            surface_height(x)


def test_paving_mesh_has_continuous_surface_and_exact_footprint():
    points, faces = paving_mesh()
    assert len(points) == 16 and len(faces) == 14
    assert min(p[0] for p in points) == BOUNDS[0]
    assert max(p[0] for p in points) == BOUNDS[2]
    assert {p[1] for p in points} == {BOUNDS[1], BOUNDS[3]}
    for x, y, z in points[:8]:
        assert z == surface_height(x)
    # Every edge of the closed mesh occurs exactly twice, preventing a crack.
    counts = {}
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            key = tuple(sorted((a, b)))
            counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {2}


def test_curb_opening_preserves_original_extent_height_and_material(evidence):
    assert CURB_SEGMENTS == {'SouthCurb': (-46.5, -27.4), 'NorthCurb': (-25.4, -19.5)}
    assert evidence['original_curb']['path'] == '/World/Park/LANDSCAPE/PathCurb'
    assert evidence['original_curb']['bounds_m'] == [[-5.21, -46.5, .135], [-4.99, -19.5, .385]]
    assert evidence['original_curb']['material'] == '/World/Materials/cream'
    assert evidence['original_curb']['active_in_variant'] is False
    usd = (VARIANTS / 'dining_connection.usda').read_text()
    assert 'over "PathCurb" ( active = false )' in usd
    assert usd.count('rel material:binding = </World/Materials/cream>') == 2


def test_entire_paved_prism_has_no_fixed_or_guest_intersections(evidence):
    audit = evidence['after_audit']
    assert not audit['fixed_collision_paths']
    assert not audit['guest_intersection_paths']
    relevant = [r for r in audit['records'] if r['classification'] in ('fixed_obstacle', 'synthetic_guest_mesh')]
    assert len(relevant) >= 50
    assert all(not r['intersects_full_paving_clearance_prism'] for r in relevant)
    assert any('MenuBoard' in r['prim_path'] for r in relevant)
    assert any('Chair' in r['prim_path'] for r in relevant)
    assert any('Table' in r['prim_path'] for r in relevant)
    assert any('BinLid' in r['prim_path'] for r in relevant)
    assert any('Guest' in r['prim_path'] for r in relevant)


def test_full_width_check_catches_obstacle_away_from_centerline():
    # At the southern edge, outside a centerline-only check but inside the paving.
    bounds = [[-10, -27.3, .6], [-9.8, -27.1, 1.2]]
    assert positive_intersection(bounds)
    assert xy_clearance(bounds) == 0
    # A replacement curb touching the footprint boundary does not intrude.
    assert not positive_intersection([[-5.21, -46.5, .135], [-4.99, -27.4, .385]])


def test_nearby_bin_gap_is_geometry_not_capacity_claim(evidence):
    records = {r['prim_path']: r for r in evidence['after_audit']['records']}
    assert records['/World/Park/FOOD_COURT/BinLid_0002']['xy_gap_to_full_paving_m'] == pytest.approx(.24)
    assert any('crowd capacity' in limitation for limitation in evidence['limitations'])
    assert evidence['native_gpu_rendered'] is False


def test_layer_and_graph_rebuild_are_deterministic_and_nonmutating(tmp_path, graph):
    base = load_graph()
    before = deepcopy(base)
    layer = tmp_path / 'design.usda'
    write_layer(layer, base['source_scene_sha256'])
    assert layer.read_bytes() == (VARIANTS / 'dining_connection.usda').read_bytes()
    rebuilt = variant_graph(base, sha256(ROOT / 'assets/circulation_graph.json'), sha256(layer))
    assert rebuilt == graph
    assert base == before
