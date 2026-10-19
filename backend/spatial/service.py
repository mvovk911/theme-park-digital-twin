"""Immutable, provenance-verified spatial design queries; no live park access."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType

from modeling.circulation import find_route, validate_graph
from .contracts import MAX_REQUEST_BYTES, RouteRequest

ROOT = Path(__file__).resolve().parents[2]
BASE_GRAPH = 'assets/circulation_graph.json'
VARIANT_GRAPH = 'assets/variants/dining_circulation_graph.json'
BASE_SCENE = 'assets/park.usdc'
BASE_GEOMETRY = 'assets/park.usda'
VARIANT_LAYER = 'assets/variants/dining_connection.usda'
VARIANT_EVIDENCE = 'assets/variants/dining_connection_evidence.json'
MAX_GRAPH_BYTES = 256 * 1024

FLAGS = {
    'synthetic': True, 'calibrated': False, 'execution_authority': 'none',
    'physical_guidance': False, 'live_state_bound': False, 'forecast_coupled': False,
    'mutates_live_state': False,
}
LIMITATIONS = [
    'Read-only query of an authored design; not current park conditions or physical navigation guidance',
    'Partial graph and synthetic accessibility labels; not obstacle-complete or certified',
    'Plan distance divided by assumed speed excludes queues, stops, density and mobility variability',
    'A reachable public approach does not imply a boarding route or spare service capacity',
    'The scenario planner does not use this graph; this query does not validate a rerouting forecast',
]


class SpatialIdentityError(ValueError):
    """Installation must stop when graph/source identity cannot be verified."""


class SpatialQueryError(ValueError):
    pass


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON keys')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON value')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def _bounded_graph(data: bytes) -> dict:
    if len(data) > MAX_GRAPH_BYTES:
        raise ValueError('Graph artifact exceeds bounded size')
    graph = _json(data)
    if not isinstance(graph, dict) or not 1 <= len(graph['nodes']) <= 128 or not 1 <= len(graph['edges']) <= 256:
        raise ValueError('Graph node/edge count exceeds supported bounds')
    nodes = {}
    for node in graph['nodes']:
        position = node['position_m']
        if len(position) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                                      not math.isfinite(v) or abs(v) > 1000 for v in position):
            raise ValueError('Graph coordinates exceed supported bounds')
        nodes[node['id']] = position
    for edge in graph['edges']:
        if math.dist(nodes[edge['from']], nodes[edge['to']]) > 500:
            raise ValueError('Graph edge exceeds supported length')
    validate_graph(graph)
    return graph


@dataclass(frozen=True)
class _Snapshot:
    graph_json: bytes
    identity_json: bytes


class SpatialService:
    """Verify all identities once, then retain immutable serialized snapshots.

    Fixed asset paths prevent graph metadata from choosing arbitrary local files.
    Returned objects are fresh copies. Disk edits after installation neither alter
    the snapshot nor acquire its verified identity; restart requires revalidation.
    """
    def __init__(self, project_root: Path = ROOT):
        root = Path(project_root)
        try:
            raw = {name: (root / name).read_bytes() for name in
                   (BASE_GRAPH, VARIANT_GRAPH, BASE_SCENE, BASE_GEOMETRY, VARIANT_LAYER, VARIANT_EVIDENCE)}
            hashes = {name: _hash(data) for name, data in raw.items()}
            base = _bounded_graph(raw[BASE_GRAPH])
            variant = _bounded_graph(raw[VARIANT_GRAPH])
            for graph in (base, variant):
                if graph.get('synthetic') is not True:
                    raise ValueError('Authored graph must be explicitly synthetic')
                if graph.get('source_scene') != BASE_SCENE or graph.get('source_geometry') != BASE_GEOMETRY:
                    raise ValueError('Unexpected source asset path')
                if graph.get('source_scene_sha256') != hashes[BASE_SCENE]:
                    raise ValueError('Baseline scene hash mismatch')
                if graph.get('source_geometry_sha256') != hashes[BASE_GEOMETRY]:
                    raise ValueError('Baseline geometry hash mismatch')
            if 'variant' in base:
                raise ValueError('Baseline graph unexpectedly declares a variant')
            design = variant['variant']
            if design.get('id') != 'dining-connection-v1':
                raise ValueError('Unexpected design variant')
            if design.get('baseline_graph') != BASE_GRAPH or design.get('baseline_graph_sha256') != hashes[BASE_GRAPH]:
                raise ValueError('Baseline graph identity mismatch')
            if design.get('layer') != VARIANT_LAYER or design.get('layer_sha256') != hashes[VARIANT_LAYER]:
                raise ValueError('Design layer identity mismatch')
            if len(raw[VARIANT_EVIDENCE]) > 512 * 1024:
                raise ValueError('Variant evidence exceeds supported size')
            evidence = _json(raw[VARIANT_EVIDENCE])
            expected_hashes = {'baseline_graph_sha256': BASE_GRAPH, 'baseline_scene_sha256': BASE_SCENE,
                               'variant_graph_sha256': VARIANT_GRAPH, 'variant_layer_sha256': VARIANT_LAYER}
            if any(evidence.get(key) != hashes[path] for key, path in expected_hashes.items()):
                raise ValueError('Variant evidence identity mismatch')
            if evidence.get('preserved_baseline_artifact_hashes', {}).get(BASE_GEOMETRY) != hashes[BASE_GEOMETRY]:
                raise ValueError('Variant evidence baseline geometry mismatch')
            snapshots = {}
            for name, graph, graph_path in [('baseline', base, BASE_GRAPH), ('dining_connection', variant, VARIANT_GRAPH)]:
                identity = {
                    'graph_sha256': hashes[graph_path], 'graph_version': graph['version'],
                    'baseline_graph_sha256': hashes[BASE_GRAPH],
                    'baseline_scene_sha256': hashes[BASE_SCENE],
                    'baseline_geometry_sha256': hashes[BASE_GEOMETRY],
                    'variant_layer_sha256': hashes[VARIANT_LAYER] if name != 'baseline' else None,
                    'variant_evidence_sha256': hashes[VARIANT_EVIDENCE] if name != 'baseline' else None,
                    'verification': 'verified_at_installation',
                    'snapshot_policy': 'immutable_until_restart',
                }
                snapshots[name] = _Snapshot(json.dumps(graph).encode(), json.dumps(identity).encode())
            self._snapshots = MappingProxyType(snapshots)
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
            raise SpatialIdentityError(f'Spatial design installation refused: {exc}') from exc

    def _snapshot(self, variant: str) -> _Snapshot:
        try:
            return self._snapshots[variant]
        except KeyError:
            raise SpatialQueryError('Unknown spatial variant') from None

    def _envelope(self, variant: str) -> dict:
        return {**FLAGS, 'variant': variant, 'identity': json.loads(self._snapshot(variant).identity_json),
                'distance_basis': '2D plan distance on authored graph; terrain grade is not integrated',
                'limitations': list(LIMITATIONS)}

    def capabilities(self) -> dict:
        return {**FLAGS, 'purpose': 'Authored spatial design comparison, independent of live/replay state',
                'variants': [self._envelope(name) for name in self._snapshots],
                'request_limits': {'max_request_bytes': MAX_REQUEST_BYTES, 'max_blocked_edges': 32,
                                   'walking_speed_mps': {'min': .3, 'max': 2.5, 'default': 1.2}},
                'operations': ['inspect_graph', 'query_route'], 'limitations': list(LIMITATIONS)}

    def graph(self, variant: str) -> dict:
        return {**self._envelope(variant), 'graph': json.loads(self._snapshot(variant).graph_json)}

    def route(self, request: RouteRequest) -> dict:
        graph = json.loads(self._snapshot(request.variant).graph_json)
        try:
            result = find_route(graph, request.origin, request.destination,
                                blocked_edges=request.blocked_edges, accessible_only=request.accessible_only,
                                walking_speed_mps=request.walking_speed_mps)
        except ValueError as exc:
            raise SpatialQueryError(str(exc)) from exc
        envelope = self._envelope(request.variant)
        return {**result, **envelope, 'limitations': result['limitations'] + envelope['limitations'],
                'query': request.model_dump(),
                'entrance_scope': {'destination_node': result['destination_node'],
                                   'destination_note': result.get('destination_note', ''),
                                   'asset_mapping_note': result.get('entrance_scope_note', '')},
                'variant_design': deepcopy_json(graph.get('variant'))}


def deepcopy_json(value):
    return json.loads(json.dumps(value))
