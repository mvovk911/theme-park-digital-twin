"""Build-time bridge from the sole operational catalog into portable USD metadata.

Importing this module does not open a database, start an app, or contact sources.
The exported USD and JSON remain usable without Python backend modules at runtime.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from backend.domain import registry as domain_registry
from backend.connectors.catalog import default_catalog


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def catalog_contract():
    """Return static declarations only, with names/IDs/mappings owned by backend."""
    specs = sorted(default_catalog(), key=lambda item: item.id)
    result = {}
    for item in sorted(domain_registry(), key=lambda row: row['id']):
        asset_id = item['id']
        bindings = []
        for spec in specs:
            mappings = [m for m in spec.mappings if m.asset_id == asset_id]
            if not mappings:
                continue
            bindings.append({
                'source_id': spec.id,
                'source_name': spec.name,
                'planned_protocol': spec.planned_protocol,
                'source_asset_ids': sorted({m.source_asset_id for m in mappings}),
                'metrics': [m.as_dict() for m in sorted(mappings, key=lambda m: (m.metric, m.source_asset_id))],
                'catalog_path': f'/api/connectors/{spec.id}',
                'observations_path': f'/api/observations?source_id={spec.id}&asset_id={asset_id}',
            })
        result[asset_id] = {
            'asset_id': asset_id,
            'name': item['name'],
            'category': item['type'],
            'prim_path': item['scene_path'],
            'asset_path': f'/api/assets/{asset_id}',
            'observations_path': f'/api/observations?asset_id={asset_id}',
            'connector_ids': [b['source_id'] for b in bindings],
            'bindings': bindings,
        }
    return {
        'schema_version': '1.0',
        'binding_mode': 'declarative_catalog',
        'catalog_sources': ['backend/domain.py:registry', 'backend/connectors/catalog.py:default_catalog'],
        'catalog_sha256': hashlib.sha256(canonical_json(result).encode()).hexdigest(),
        'contains_live_values': False,
        'assets': result,
    }


def apply_semantics(stage, scene_registry, contract):
    """Bind stable names and declarations while retaining designed sign aliases."""
    from pxr import Usd, Kind, Vt
    scene_ids = {item['asset_id'] for item in scene_registry}
    if scene_ids != set(contract['assets']):
        raise ValueError(f'Scene/domain IDs differ: {sorted(scene_ids ^ set(contract["assets"]))}')
    Usd.ModelAPI(stage.GetPrimAtPath('/World')).SetKind(Kind.Tokens.group)
    Usd.ModelAPI(stage.GetPrimAtPath('/World/Park')).SetKind(Kind.Tokens.assembly)
    Usd.ModelAPI(stage.GetPrimAtPath('/World/Park/LANDSCAPE')).SetKind(Kind.Tokens.component)
    for item in scene_registry:
        declaration = contract['assets'][item['asset_id']]
        if item['prim_path'] != declaration['prim_path']:
            raise ValueError(f'Scene path drift for {item["asset_id"]}')
        item['authored_name'] = item['name']
        item['authored_category'] = item['category']
        item['conceptual_tags'] = list(item['systems'])
        item['name'] = declaration['name']
        item['category'] = declaration['category']
        item['aliases'] = [item['authored_name']] if item['authored_name'] != item['name'] else []
        item['connector_ids'] = declaration['connector_ids']
        # Preserve the legacy field, now containing resolvable source IDs only.
        item['systems'] = declaration['connector_ids']
        item['semantic_binding'] = {
            'mode': contract['binding_mode'],
            'manifest': 'scene_bindings.json',
            'catalog_sha256': contract['catalog_sha256'],
            'asset_path': declaration['asset_path'],
            'observations_path': declaration['observations_path'],
        }
        prim = stage.GetPrimAtPath(item['prim_path'])
        prim.SetDisplayName(item['name'])
        prim.SetCustomDataByKey('assetName', item['name'])
        prim.SetCustomDataByKey('authoredName', item['authored_name'])
        prim.SetCustomDataByKey('systems', ', '.join(item['connector_ids']))
        Usd.ModelAPI(prim).SetKind(Kind.Tokens.component)
        Usd.ModelAPI(prim).SetAssetName(item['asset_id'])
        sources = {}
        for binding in declaration['bindings']:
            metrics = {}
            for mapping in binding['metrics']:
                metrics[mapping['metric']] = {
                    'sourceAssetId': mapping['source_asset_id'],
                    'destination': mapping['destination'],
                    'unit': mapping['unit'],
                    'valueType': mapping['value_type'],
                    'authoritative': mapping['authoritative'],
                }
            sources[binding['source_id']] = {'sourceAssetIds': Vt.StringArray(binding['source_asset_ids']), 'metrics': metrics}
        prim.SetCustomDataByKey('parkTwin', {
            'schemaVersion': contract['schema_version'],
            'bindingMode': contract['binding_mode'],
            'containsLiveValues': False,
            'catalogSha256': contract['catalog_sha256'],
            'assetPath': declaration['asset_path'],
            'observationsPath': declaration['observations_path'],
            'sourceIds': Vt.StringArray(item['connector_ids']),
            'conceptualTags': Vt.StringArray(item['conceptual_tags']),
            'sources': sources,
        })
    dynamic_paths = ['/World/Park/RIDE_COASTER/Train', '/World/Park/RIDE_WHEEL/Rotor']
    dynamic_paths += [f'/World/Park/RIDE_COASTER/Train/Car_{i:02d}' for i in range(3)]
    dynamic_paths += [f'/World/Park/RIDE_WHEEL/Rotor/Gondola_{i:02d}' for i in range(12)]
    for path in dynamic_paths:
        Usd.ModelAPI(stage.GetPrimAtPath(path)).SetKind(Kind.Tokens.subcomponent)


def build_inventory(stage, scene_registry, contract, scene_revision=2):
    """Count authored scene contents without inventing renderer tessellation counts."""
    from pxr import Usd, UsdGeom, UsdShade
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    assets = []
    for item in sorted(scene_registry, key=lambda row: row['asset_id']):
        root = stage.GetPrimAtPath(item['prim_path'])
        prims = list(Usd.PrimRange(root))
        types = Counter(prim.GetTypeName() for prim in prims)
        analytic = Counter()
        bound_materials = Counter()
        faces = triangles = gprims = 0
        subassemblies = []
        for prim in prims:
            if Usd.ModelAPI(prim).GetKind() == 'subcomponent':
                subassemblies.append(str(prim.GetPath()))
            if prim.IsA(UsdGeom.Gprim):
                gprims += 1
                mat = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
                if mat:
                    bound_materials[str(mat.GetPath())] += 1
                if prim.IsA(UsdGeom.Mesh):
                    counts = UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get() or []
                    faces += len(counts)
                    triangles += sum(max(0, count - 2) for count in counts)
                else:
                    analytic[prim.GetTypeName()] += 1
        bound = cache.ComputeWorldBound(root).ComputeAlignedBox()
        lo, hi = bound.GetMin(), bound.GetMax()
        assets.append({
            'asset_id': item['asset_id'], 'prim_path': item['prim_path'],
            'display_name': root.GetDisplayName(), 'authored_name': item['authored_name'],
            'aliases': item['aliases'], 'category': item['category'],
            'model_kind': Usd.ModelAPI(root).GetKind(),
            'direct_children': len(root.GetChildren()), 'descendant_prims': len(prims) - 1,
            'prim_types': dict(sorted(types.items())), 'gprim_count': gprims,
            'mesh_count': types.get('Mesh', 0), 'mesh_face_count': faces,
            'authored_mesh_fan_triangle_count': triangles,
            'analytic_primitive_counts': dict(sorted(analytic.items())),
            'analytic_triangle_count': None,
            'unique_bound_materials': len(bound_materials),
            'material_binding_counts': dict(sorted(bound_materials.items())),
            'world_bounds_m': [[round(float(v), 6) for v in lo], [round(float(v), 6) for v in hi]],
            'world_dimensions_m': [round(float(hi[i] - lo[i]), 6) for i in range(3)],
            'connector_ids': item['connector_ids'], 'conceptual_tags': item['conceptual_tags'],
            'dynamic_subassemblies': sorted(subassemblies),
        })
    prims = list(stage.Traverse())
    return {
        'schema_version': '1.0', 'scene_revision': scene_revision,
        'units': 'meters', 'up_axis': 'Z', 'measurement_time': 'authored_default_pose',
        'catalog_sha256': contract['catalog_sha256'],
        'triangle_count_scope': 'Fan triangulation of authored polygon meshes only; excludes analytic gprims whose tessellation is renderer-dependent.',
        'bounds_scope': 'USD world-aligned bounds at the authored default pose; decorative children assigned to an asset contribute to its bounds.',
        'stage_prim_count': len(prims),
        'stage_prim_types': dict(sorted(Counter(prim.GetTypeName() for prim in prims).items())),
        'operational_asset_count': len(assets),
        'assets': assets,
    }
