"""Run: blender --background --python-exit-code 1 --python modeling/import_blender.py -- --output assets/park.blend

Requires Blender 4.x or newer with its USD importer enabled.
Imports the portable USD scene using Blender's official USD importer and saves
an editable .blend. This is a modeling handoff; the interactive app uses OVRTX.
"""
from pathlib import Path
import argparse
import sys
import json
import re
import bpy

base=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--usd',default=str(base/'assets/park.usdc'))
parser.add_argument('--output',default=str(base/'assets/park.blend'))
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
source=Path(args.usd).resolve(); target=Path(args.output).resolve()
if not source.is_file():raise FileNotFoundError(source)
bpy.ops.wm.read_factory_settings(use_empty=True)
# Defaults import meshes, lights, cameras, materials and non-mesh primitives.
bpy.ops.wm.usd_import(filepath=str(source))
# Blender imports analytic USD gprims as meshes but drops their material bindings.
# Restore exact bindings and PreviewSurface parameters from the generated manifest.
manifest_path=source.parent/'blender_materials.json'
if manifest_path.is_file():
    manifest=json.loads(manifest_path.read_text())
    for name,values in manifest['materials'].items():
        mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes=True
        bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value=(*values['color'],1)
        bsdf.inputs['Roughness'].default_value=values['roughness']
        bsdf.inputs['Metallic'].default_value=values['metallic']
        mat.diffuse_color=(*values['color'],1)
    repaired=0
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH':continue
        names=[];ancestor=obj
        while ancestor:
            names.append(re.sub(r'\.\d+$','',ancestor.name));ancestor=ancestor.parent
        path='/'+'/'.join(reversed(names))
        name=manifest['bindings'].get(path)
        if name is None:
            # Importer may omit redundant root Xforms; unique suffix still maps exactly.
            matches=[mat for prim,mat in manifest['bindings'].items() if prim.endswith(path)]
            if len(matches)==1:name=matches[0]
        if name:
            obj.data.materials.clear();obj.data.materials.append(bpy.data.materials[name]);repaired+=1
    unbound=[o.name for o in bpy.context.scene.objects if o.type=='MESH' and not o.data.materials]
    if unbound:raise RuntimeError(f'Material repair left {len(unbound)} meshes unbound: {unbound[:5]}')
    print(f'BLENDER_MATERIALS_OK repaired={repaired} unbound={len(unbound)}')
scene=bpy.context.scene
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.0
cameras=[obj for obj in scene.objects if obj.type=='CAMERA']
if cameras:scene.camera=cameras[0]
scene.render.resolution_x=1600;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.render.engine='CYCLES';scene.cycles.samples=32
scene.render.image_settings.file_format='PNG'
# Preserve spatial asset identities as object custom properties for modeling.
asset_ids=['RIDE_COASTER','RIDE_WHEEL','SHOW_ARENA','FOOD_COURT','POWER_HUB','WATER_PLANT','ENTRY_GATE','PARKING','HOTEL','FIRST_AID','RESTROOMS','WEATHER_STATION']
for obj in scene.objects:
    if obj.name in asset_ids:obj['assetId']=obj.name
if not cameras:raise RuntimeError('USD import did not produce a camera')
if len(scene.objects)<100:raise RuntimeError(f'USD import unexpectedly small: {len(scene.objects)} objects')
target.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(target))
print(f'BLENDER_IMPORT_OK objects={len(scene.objects)} materials={len(bpy.data.materials)} camera={scene.camera.name} output={target}')
