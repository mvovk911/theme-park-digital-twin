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
assert stage.GetPrimAtPath('/World/Camera').IsA(UsdGeom.Camera)
assert stage.GetPrimAtPath('/World/Park/RIDE_WHEEL/Rotor').GetAttribute('xformOp:rotateY')
assert stage.GetPrimAtPath('/World/Park/RIDE_COASTER/Train').GetAttribute('xformOp:translate')
assert len([layer for layer in stage.GetUsedLayers() if not layer.anonymous])==1, 'scene should not depend on external layers'
paths=json.loads((base/'ride_paths.json').read_text())
assert len(paths['coaster']['points'])==240
print('PASS: 12 assets, identity roots, bound materials, finite bounds, self-contained USD, camera and animation contracts')
