#!/usr/bin/env python3
"""Author a separate dining connector experiment, preserving baseline assets.

Building/auditing requires pxr (usd-core). Graph and mesh helpers are pure Python.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

try:
    from .circulation import ROOT, find_route, load_graph, validate_graph
except ImportError:
    from circulation import ROOT, find_route, load_graph, validate_graph

BOUNDS = (-13.5, -27.4, -4.5, -25.4)
ORIGINAL_CURB = "/World/Park/LANDSCAPE/PathCurb"
DESIGN_ROOT = "/World/Park/DINING_CONNECTION_DESIGN"
X_STATIONS = (-13.5, -11.5, -5.0, -4.5)
TOP_Z = (.325, .325, .24, .24)
CURB_SEGMENTS = {"SouthCurb": (-46.5, -27.4), "NorthCurb": (-25.4, -19.5)}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def surface_height(x: float) -> float:
    if not X_STATIONS[0] <= x <= X_STATIONS[-1]:
        raise ValueError("Point is outside connector")
    for i in range(3):
        if x <= X_STATIONS[i + 1]:
            t = (x - X_STATIONS[i]) / (X_STATIONS[i + 1] - X_STATIONS[i])
            return TOP_Z[i] + t * (TOP_Z[i + 1] - TOP_Z[i])
    return TOP_Z[-1]


def paving_mesh() -> tuple[list, list]:
    points = [(x, y, z) for x, z in zip(X_STATIONS, TOP_Z) for y in (BOUNDS[1], BOUNDS[3])]
    points += [(x, y, .1) for x in X_STATIONS for y in (BOUNDS[1], BOUNDS[3])]
    faces = []
    for i in range(3):
        a, b = i * 2, (i + 1) * 2
        faces.extend([(a, b, b + 1, a + 1), (a + 8, a + 9, b + 9, b + 8),
                      (a, a + 8, b + 8, b), (a + 1, b + 1, b + 9, a + 9)])
    faces.extend([(0, 1, 9, 8), (6, 14, 15, 7)])
    return points, faces


def write_layer(path: Path, scene_sha: str) -> None:
    points, faces = paving_mesh()
    content = ['#usda 1.0', '(', '    defaultPrim = "World"', '    upAxis = "Z"', '    metersPerUnit = 1', ')',
               'over "World" {', '    over "Park" {', '        over "LANDSCAPE" {',
               '            over "PathCurb" ( active = false ) {}', '        }',
               '        def Xform "DINING_CONNECTION_DESIGN" {',
               '            custom string park:designVariant = "dining-connection-v1"',
               f'            custom string park:baselineSceneSha256 = "{scene_sha}"',
               '            custom string park:scope = "Synthetic design experiment; not an as-built or accessibility certificate"',
               '            def Mesh "GradedPaving" ( prepend apiSchemas = ["MaterialBindingAPI"] ) {',
               f'                point3f[] points = {points}',
               f'                int[] faceVertexCounts = {[len(f) for f in faces]}',
               f'                int[] faceVertexIndices = {[j for f in faces for j in f]}',
               '                uniform token subdivisionScheme = "none"',
               '                bool doubleSided = true',
               '                rel material:binding = </World/Materials/path>',
               '                custom double park:gradeRiseM = 0.085',
               '                custom double park:gradeRunM = 6.5', '            }']
    for name, (south, north) in CURB_SEGMENTS.items():
        content += [f'            def Cube "{name}" ( prepend apiSchemas = ["MaterialBindingAPI"] ) {{',
                    '                double size = 1',
                    f'                double3 xformOp:translate = (-5.1, {(south + north) / 2:.8f}, 0.26)',
                    f'                float3 xformOp:scale = (0.22, {north - south:.8f}, 0.25)',
                    '                uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]',
                    '                rel material:binding = </World/Materials/cream>', '            }']
    content += ['        }', '    }', '}', '']
    path.write_text('\n'.join(content))


def variant_graph(base: dict, base_graph_sha: str, layer_sha: str) -> dict:
    graph = deepcopy(base)
    graph['version'] = 'aster-circulation-v1+dining-connection-v1'
    graph['variant'] = {
        'id': 'dining-connection-v1', 'baseline_graph': 'assets/circulation_graph.json',
        'baseline_graph_sha256': base_graph_sha,
        'layer': 'assets/variants/dining_connection.usda', 'layer_sha256': layer_sha,
        'distance_basis': '2D plan distance on nominal graph Z=0.30 m; graded surface is separately modeled in USD',
        'superseded_excluded_edge_ids': ['food_missing_link'],
        'entrance_change': 'FOOD_COURT maps to a new landing point at (-12.5,-26.4), 0.6 m north of the baseline point to keep the 2 m connector clear of bin bounds.',
        'accessibility': 'Local grade is modeled; unresolved baseline entrance/plaza thresholds remain. No accessible route from ENTRY_GATE is asserted.',
    }
    graph['surfaces'].append({
        'id': 'dining_connector', 'prim_path': DESIGN_ROOT + '/GradedPaving',
        'source_layer': graph['variant']['layer'], 'shape': 'rectangle', 'bounds_xy_m': list(BOUNDS),
        'top_profile_xz_m': [[x, z] for x, z in zip(X_STATIONS, TOP_Z)],
    })
    graph['nodes'] += [
        {'id': 'dining_main_landing', 'position_m': [-4.5, -26.4, .3], 'kind': 'junction'},
        {'id': 'food_connector_entrance', 'position_m': [-12.5, -26.4, .3], 'kind': 'entrance',
         'note': 'New design-variant landing inside the dining plaza; route ends before restaurant interior, tables or service queues.'},
    ]
    graph['edges'] = [edge for edge in graph['edges'] if edge['id'] != 'food_missing_link']
    graph['edges'] += [
        {'id': 'dining_main_link', 'from': 'main_food_junction', 'to': 'dining_main_landing',
         'status': 'walkable', 'surface_ids': ['main'], 'assumed_corridor_width_m': 2,
         'modeled_step_free': True},
        {'id': 'dining_connector_link', 'from': 'dining_main_landing', 'to': 'food_connector_entrance',
         'status': 'walkable', 'surface_ids': ['dining_connector', 'food', 'main'],
         'assumed_corridor_width_m': 2, 'modeled_step_free': True,
         'reason': 'Separate design layer adds a continuous graded surface and opens the existing curb; local synthetic label only.'},
    ]
    graph['asset_entrances']['FOOD_COURT'] = 'food_connector_entrance'
    graph['entrance_scope_notes']['FOOD_COURT'] = 'New variant landing only; original interior node is preserved but no new path through furniture is inferred.'
    validate_graph(graph)
    return graph


def xy_clearance(bounds: list, corridor=BOUNDS) -> float:
    low, high = bounds
    dx = max(corridor[0] - high[0], low[0] - corridor[2], 0)
    dy = max(corridor[1] - high[1], low[1] - corridor[3], 0)
    return math.hypot(dx, dy)


def positive_intersection(bounds: list, corridor=BOUNDS) -> bool:
    low, high = bounds
    return (min(high[0], corridor[2]) - max(low[0], corridor[0]) > 1e-6 and
            min(high[1], corridor[3]) - max(low[1], corridor[1]) > 1e-6 and
            min(high[2], 2.425) - max(low[2], .24) > 1e-6)


def audit_stage(stage) -> dict:
    """Conservative static AABB audit of the entire paving footprint + headroom.

    Support surfaces and paving-joint decals are recorded separately. Guests are
    reported too, but not reclassified as permanent structures or silently moved.
    """
    from pxr import Usd, UsdGeom
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    records = []
    supports = {'/World/Park/LANDSCAPE/EarthPlinth', '/World/Park/LANDSCAPE/Ground',
                '/World/Park/LANDSCAPE/MainPromenade', '/World/Park/FOOD_COURT/DiningPlaza',
                DESIGN_ROOT + '/GradedPaving'}
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Gprim):
            continue
        aligned = cache.ComputeWorldBound(prim).ComputeAlignedBox()
        low, high = list(aligned.GetMin()), list(aligned.GetMax())
        # Include nearby furniture even when it does not intersect the candidate.
        if (high[0] < BOUNDS[0] - 3 or low[0] > BOUNDS[2] + 3 or
            high[1] < BOUNDS[1] - 3 or low[1] > BOUNDS[3] + 3 or
            high[2] < .1 or low[2] > 2.425):
            continue
        path = str(prim.GetPath())
        if path in supports:
            classification = 'support_surface'
        elif path.startswith('/World/Park/LANDSCAPE/PavingJoints'):
            classification = 'paving_joint_decal'
        elif path == ORIGINAL_CURB:
            classification = 'curb_to_replace'
        elif '/Guest' in path:
            classification = 'synthetic_guest_mesh'
        else:
            classification = 'fixed_obstacle'
        bounds = [low, high]
        records.append({'prim_path': path, 'classification': classification,
                        'bounds_m': [[round(v, 6) for v in values] for values in bounds],
                        'xy_gap_to_full_paving_m': round(xy_clearance(bounds), 6),
                        'intersects_full_paving_clearance_prism': positive_intersection(bounds)})
    fixed = [r for r in records if r['classification'] == 'fixed_obstacle']
    guests = [r for r in records if r['classification'] == 'synthetic_guest_mesh']
    collisions = [r['prim_path'] for r in fixed if r['intersects_full_paving_clearance_prism']]
    return {'method': 'USD world-space aligned bounds against entire 9x2m paving rectangle and z=.24..2.425m prism; conservative static geometry check, not crowd/clearance certification',
            'corridor_bounds_xy_m': list(BOUNDS), 'vertical_prism_m': [.24, 2.425],
            'fixed_collision_paths': collisions,
            'guest_intersection_paths': [r['prim_path'] for r in guests if r['intersects_full_paving_clearance_prism']],
            'minimum_fixed_xy_gap_m': min((r['xy_gap_to_full_paving_m'] for r in fixed), default=None),
            'records': sorted(records, key=lambda r: r['prim_path'])}


def build(output: Path) -> dict:
    from pxr import Sdf, Usd, UsdGeom, UsdShade
    output.mkdir(parents=True, exist_ok=True)
    baseline_path = ROOT / 'assets/circulation_graph.json'
    base = load_graph(baseline_path)
    scene = ROOT / base['source_scene']
    if sha256(scene) != base['source_scene_sha256']:
        raise ValueError('Source scene changed; re-audit baseline before rebuilding variant')
    baseline_graph_sha = sha256(baseline_path)
    preserved_paths = ['assets/park.usdc', 'assets/park.usda', 'assets/park.blend', 'assets/circulation_graph.json']
    baseline_artifact_hashes = {p: sha256(ROOT / p) for p in preserved_paths}
    if baseline_artifact_hashes[base['source_geometry']] != base['source_geometry_sha256']:
        raise ValueError('Source USDA changed; re-audit baseline before rebuilding variant')
    baseline_stage = Usd.Stage.Open(str(scene))
    curb = baseline_stage.GetPrimAtPath(ORIGINAL_CURB)
    curb_bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(curb).ComputeAlignedBox()
    expected = [[-5.21, -46.5, .135], [-4.99, -19.5, .385]]
    actual = [list(curb_bound.GetMin()), list(curb_bound.GetMax())]
    if any(abs(v - e) > 1e-5 for row, wanted in zip(actual, expected) for v, e in zip(row, wanted)):
        raise ValueError('Original curb geometry changed')
    material = UsdShade.MaterialBindingAPI(curb).ComputeBoundMaterial()[0]
    if str(material.GetPath()) != '/World/Materials/cream':
        raise ValueError('Original curb material changed')
    layer_path = output / 'dining_connection.usda'
    write_layer(layer_path, base['source_scene_sha256'])
    graph = variant_graph(base, baseline_graph_sha, sha256(layer_path))
    graph_path = output / 'dining_circulation_graph.json'
    graph_path.write_text(json.dumps(graph, indent=2) + '\n')
    composition = Sdf.Layer.CreateAnonymous('dining-variant-composition.usda')
    composition.subLayerPaths = [str(layer_path.resolve()), str(scene)]
    composed = Usd.Stage.Open(composition)
    UsdGeom.SetStageUpAxis(composed, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(composed, 1)
    if composed.GetPrimAtPath(ORIGINAL_CURB).IsActive():
        raise ValueError('Original curb was not overridden')
    variant_prims = {}
    bound_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    for name in ('GradedPaving', 'SouthCurb', 'NorthCurb'):
        prim = composed.GetPrimAtPath(DESIGN_ROOT + '/' + name)
        bound = bound_cache.ComputeWorldBound(prim).ComputeAlignedBox()
        material_path = str(UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0].GetPath())
        variant_prims[name] = {'bounds_m': [[round(v, 6) for v in bound.GetMin()], [round(v, 6) for v in bound.GetMax()]], 'material': material_path}
    actual_points = UsdGeom.Mesh(composed.GetPrimAtPath(DESIGN_ROOT + '/GradedPaving')).GetPointsAttr().Get()
    if any(abs(actual_points[i][axis] - expected) > 1e-6 for i, point in enumerate(paving_mesh()[0]) for axis, expected in enumerate(point)):
        raise ValueError('Composed paving points differ from graded design')
    before_audit, after_audit = audit_stage(baseline_stage), audit_stage(composed)
    if after_audit['fixed_collision_paths'] or after_audit['guest_intersection_paths']:
        raise ValueError('Full connector footprint intersects scene obstacles')
    before = find_route(base, 'ENTRY_GATE', 'FOOD_COURT')
    after = find_route(graph, 'ENTRY_GATE', 'FOOD_COURT')
    closed = find_route(graph, 'ENTRY_GATE', 'FOOD_COURT', blocked_edges=['dining_connector_link'])
    accessible = find_route(graph, 'ENTRY_GATE', 'FOOD_COURT', accessible_only=True)
    if before['reachable'] or not after['reachable'] or closed['reachable'] or accessible['reachable']:
        raise ValueError('Variant route claims failed their acceptance checks')
    evidence = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'synthetic': True, 'calibrated': False,
        'baseline_scene_sha256': base['source_scene_sha256'], 'baseline_graph_sha256': baseline_graph_sha,
        'preserved_baseline_artifact_hashes': baseline_artifact_hashes,
        'variant_layer_sha256': sha256(layer_path), 'variant_graph_sha256': sha256(graph_path),
        'original_curb': {'path': ORIGINAL_CURB, 'bounds_m': expected, 'material': str(material.GetPath()), 'active_in_variant': False},
        'replacement_curb_y_intervals_m': CURB_SEGMENTS, 'paving_bounds_xy_m': BOUNDS,
        'composed_variant_prims': variant_prims,
        'top_profile_xz_m': list(zip(X_STATIONS, TOP_Z)), 'grade_percent': .085 / 6.5 * 100,
        'distance_basis': graph['variant']['distance_basis'],
        'before_audit': before_audit, 'after_audit': after_audit,
        'routes': {'before': before, 'after': after, 'connector_closed': closed, 'accessible_entry': accessible},
        'native_gpu_rendered': False,
        'limitations': ['Geometry-only design experiment, not a real-world construction proposal',
                        'Adjacent furniture gaps do not establish safe passing clearance or crowd capacity',
                        'Source meshes are synthetic, not surveyed; aligned bounds are conservative',
                        'No restaurant interior, service queue, or evacuation route is introduced',
                        'Entry and central-plaza thresholds remain unresolved'],
    }
    (output / 'dining_connection_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    if any(sha256(ROOT / p) != digest for p, digest in baseline_artifact_hashes.items()):
        raise ValueError('Baseline assets unexpectedly changed')
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'assets/variants')
    args = parser.parse_args()
    evidence = build(args.output_dir)
    print(json.dumps({k: evidence[k] for k in ('variant_layer_sha256', 'grade_percent', 'distance_basis')}, indent=2))
    print('After route:', evidence['routes']['after']['distance_m'], 'm; fixed intersections:', evidence['after_audit']['fixed_collision_paths'])


if __name__ == '__main__':
    main()
