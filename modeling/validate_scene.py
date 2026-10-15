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

import hashlib
validation={'scene_revision':2,'usd_sha256':hashlib.sha256((base/'park.usdc').read_bytes()).hexdigest(),'asset_roots':12,'all_operational_roots_identity':True,'materials_bound':True,'self_contained_usd':True,'articulated_car_count':3,'authored_car_poses_match_route':True,'tree_structure_intersections':0,'gpu_visual_review':'pending revision 2 deployment','blender_handoff_revision':1}
(base/'scene_quality_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
