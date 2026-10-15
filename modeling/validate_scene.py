from pathlib import Path
import json, math
from pxr import Usd, UsdGeom, UsdShade
base=Path(__file__).resolve().parents[1]/'assets'
stage=Usd.Stage.Open(str(base/'park.usdc'))
assert stage and UsdGeom.GetStageUpAxis(stage)=='Z'
assert UsdGeom.GetStageMetersPerUnit(stage)==1
registry=json.loads((base/'asset_registry.json').read_text())
assert len(registry['assets'])==12
for a in registry['assets']:
    root=stage.GetPrimAtPath(a['prim_path'])
    assert root and root.GetCustomDataByKey('assetId')==a['asset_id']
    assert not UsdGeom.Xformable(root).GetOrderedXformOps(), 'operational roots must be identity'
    assert all(math.isfinite(x) for b in a['computed_bounds'] for x in b)
    for child in Usd.PrimRange(root):
        if child.IsA(UsdGeom.Gprim):
            material=UsdShade.MaterialBindingAPI(child).ComputeBoundMaterial()[0]
            assert material, f'unbound material: {child.GetPath()}'
for prim in stage.Traverse():
    if prim.IsA(UsdGeom.Gprim):
        assert UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0], f'unbound material: {prim.GetPath()}'
assert stage.GetPrimAtPath('/World/Camera').IsA(UsdGeom.Camera)
assert stage.GetPrimAtPath('/World/Park/RIDE_WHEEL/Rotor').GetAttribute('xformOp:rotateY')
assert stage.GetPrimAtPath('/World/Park/RIDE_COASTER/Train').GetAttribute('xformOp:translate')
assert len([layer for layer in stage.GetUsedLayers() if not layer.anonymous])==1, 'scene should not depend on external layers'
paths=json.loads((base/'ride_paths.json').read_text())
assert len(paths['coaster']['points'])==240
print('PASS: 12 assets, identity roots, bound materials, finite bounds, self-contained USD, camera and animation contracts')

# Articulated car transforms are authored and agree with the runtime helper.
import numpy as np
from animate import CoasterRoute, train_transforms, TRAIN_ROOT
route=CoasterRoute(paths['coaster']['points'])
poses=train_transforms(route,.77)
cache=UsdGeom.XformCache(Usd.TimeCode.Default())
assert paths['coaster']['car_offsets_m']==[0,-2.3,-4.6]
for i in range(3):
    path=f'{TRAIN_ROOT}/Car_{i:02d}'
    car=stage.GetPrimAtPath(path)
    assert car and car.GetCustomDataByKey('carIndex')==i
    actual=np.array(cache.GetLocalToWorldTransform(car))
    desired=poses[path]@poses[TRAIN_ROOT]
    assert np.allclose(actual,desired,atol=1e-5),(path,actual,desired)
# Explicitly prevent landscape tree trunks intersecting buildings/tanks/solar.
boxcache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render'])
obstacles=[]
for prim in stage.Traverse():
    if prim.GetName().startswith(('Building','WaterTank','BatteryCabinet','SolarPanel')):
        b=boxcache.ComputeWorldBound(prim).ComputeAlignedBox();obstacles.append((str(prim.GetPath()),b.GetMin(),b.GetMax()))
for prim in stage.Traverse():
    if prim.GetName().startswith('Trunk'):
        b=boxcache.ComputeWorldBound(prim).ComputeAlignedBox();position=(b.GetMin()+b.GetMax())/2
        for obstacle,lo,hi in obstacles:
            assert not (lo[0]<=position[0]<=hi[0] and lo[1]<=position[1]<=hi[1]),f'{prim.GetPath()} intersects {obstacle}'
print('PASS: three articulated cars match authored route poses; no tree trunks inside buildings, tanks, batteries, or solar panels')

# Crosscheck portable declarations against the current sole backend catalog.
from scene_semantics import catalog_contract, build_inventory
contract=catalog_contract()
exported=json.loads((base/'scene_bindings.json').read_text())
assert exported==contract, 'scene binding manifest drifted from operational catalog'
assert {a['asset_id'] for a in registry['assets']}==set(contract['assets'])
binding_count=0
for item in registry['assets']:
    expected=contract['assets'][item['asset_id']]
    prim=stage.GetPrimAtPath(item['prim_path'])
    assert item['name']==expected['name']==prim.GetDisplayName()==prim.GetCustomDataByKey('assetName')
    assert item['category']==expected['category']
    assert item['prim_path']==expected['prim_path']
    assert item['systems']==item['connector_ids']==expected['connector_ids']
    assert prim.GetCustomDataByKey('authoredName')==item['authored_name']
    assert Usd.ModelAPI(prim).GetKind()=='component'
    declarations=prim.GetCustomDataByKey('parkTwin')
    assert declarations['containsLiveValues'] is False
    assert declarations['bindingMode']=='declarative_catalog'
    assert declarations['catalogSha256']==contract['catalog_sha256']
    assert list(declarations['sourceIds'])==expected['connector_ids']
    assert list(declarations['conceptualTags'])==item['conceptual_tags']
    assert set(declarations['sources'])==set(expected['connector_ids'])
    for binding in expected['bindings']:
        source=declarations['sources'][binding['source_id']]
        assert list(source['sourceAssetIds'])==binding['source_asset_ids']
        assert set(source['metrics'])=={m['metric'] for m in binding['metrics']}
        for mapping in binding['metrics']:
            actual=source['metrics'][mapping['metric']]
            expected_mapping={'sourceAssetId':mapping['source_asset_id'],'destination':mapping['destination'],
                              'unit':mapping['unit'],'valueType':mapping['value_type'],'authoritative':mapping['authoritative']}
            assert actual==expected_mapping, (item['asset_id'],binding['source_id'],mapping['metric'])
            binding_count+=1
assert Usd.ModelAPI(stage.GetPrimAtPath('/World/Park')).GetKind()=='assembly'
inventory=json.loads((base/'scene_inventory.json').read_text())
assert inventory==build_inventory(stage,registry['assets'],contract), 'inventory is stale for the USD stage'
print(f'PASS: canonical names/types, explicit authored aliases, {binding_count} static metric bindings and inventory match the sole operational catalog')

import hashlib
validation={'scene_revision':2,'usd_sha256':hashlib.sha256((base/'park.usdc').read_bytes()).hexdigest(),'asset_roots':12,'all_operational_roots_identity':True,'materials_bound':True,'self_contained_usd':True,'articulated_car_count':3,'authored_car_poses_match_route':True,'tree_structure_intersections':0,'gpu_visual_review':'pending revision 2 deployment','blender_handoff_revision':1,'canonical_identity_matches_domain':True,'catalog_sha256':contract['catalog_sha256'],'static_metric_bindings':binding_count,'inventory_matches_usd':True}
(base/'scene_quality_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
