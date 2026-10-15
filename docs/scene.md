# Aster Park scene

The procedural source is `modeling/generate_park.py`, with the landscaping and guest-scale additions in `modeling/detail_pass.py`. The generator creates a portable OpenUSD scene with no texture downloads or external geometry. `assets/park.usdc` is the compact runtime stage; `assets/park.usda` is its readable counterpart.

**Current USD revision: 2.** It contains 3,067 prims, 46 polygon meshes, and 12 operational asset roots. The remaining geometry uses standard USD analytic gprims. Physical dimensions are meters, Z is up, and the site covers 160 × 120 m with the entrance on the south edge. The ground plinth extends to 165 × 125 m.

**Current Blender handoff: revision 2.** It was regenerated from immutable source release `154e74688d46583dde9e869bf8dc105a5881669d`, saved, reopened, verified on Horde, and downloaded. Its USD and Blender SHA-256 hashes match the local files. This confirms the editable modeling handoff; native OVRTX rendering and browser/picking acceptance are separate evidence.

## Rebuild and validate

```bash
python3 -m venv modeling/.venv
modeling/.venv/bin/pip install -r modeling/requirements.txt
modeling/.venv/bin/python modeling/generate_park.py
modeling/.venv/bin/python modeling/validate_scene.py
modeling/.venv/bin/python modeling/animate.py
```

Generation writes `park.usda`, `park.usdc`, `asset_registry.json`, `ride_paths.json`, `blender_materials.json`, and `scene_validation.json`. Rails and wheel rims are actual polygon tube meshes, rather than curves. Signs use polygon glyphs. There are no external references, textures, payloads, or custom shader dependencies. Materials use UsdPreviewSurface.

`validate_scene.py` verifies registered asset paths, identity roots, bindings, finite bounds, camera and animation contracts, authored articulated-car poses, and tree-trunk intersections with buildings, tanks, batteries, and solar panels. `animate.py` verifies upright cabins at 25 wheel angles, orthonormal coaster frames at 401 positions, and articulated cars at 101 positions.

## Spatial and selection contract

All operational roots are identity Xforms below `/World/Park`. Each carries custom data `assetId` and `assetName`, plus the string attribute `park:assetId`. Walk the ancestors of a picked geometry path until this attribute is found, or use the longest matching registry `prim_path` prefix. `LANDSCAPE` is decorative infrastructure rather than one of the 12 live operational asset IDs.

| Asset ID | Function | Approximate center (x, y, z) |
| --- | --- | --- |
| RIDE_COASTER | Comet Run, articulated train, station, shaded queue | (-35, 18, 7) |
| RIDE_WHEEL | Aster Wheel, upright cabins, boarding platform, queue sails | (35, 25, 18) |
| SHOW_ARENA | Starlight stage and stepped seating | (-5, 45, 2) |
| FOOD_COURT | Outlets, counters, menus, umbrellas and dining | (-25, -28, 2) |
| POWER_HUB | Batteries, solar, transformer and control building | (57, 47, 2) |
| WATER_PLANT | Tanks, pipes, ladders, valves and control building | (-61, 48, 2) |
| ENTRY_GATE | Arch, turnstiles, ticket booths and banners | (0, -53, 2) |
| PARKING | Vehicles, accessible bays, EV chargers and crossing | (52, -36, 1) |
| HOTEL | Aster Lodge, glazing and rooftop mechanical equipment | (-58, -29, 3) |
| FIRST_AID | Medical and guest-care building | (18, -35, 2) |
| RESTROOMS | Restroom building | (53, -16, 2) |
| WEATHER_STATION | Mast and local environmental sensors | (16, 43, 3) |

`asset_registry.json` retains authored operational bounds and USD-computed geometry bounds, names, categories, and system lists. Use computed bounds for camera framing. Decorative additions do not change these IDs or top-level paths.

## Animation and native renderer integration

`modeling/animate.py` is NumPy-only. It imports no pxr, OVRTX, GPU, or runtime modules. Matrices use USD/OVStage row-vector conventions: translation is row 3 and child world composition is `child_local @ parent_world`.

The wheel is in the XZ plane. `/World/Park/RIDE_WHEEL/Rotor` has its pivot at `(35,25,19)` and rotates about Y. `wheel_transforms(angle_radians)` returns its matrix plus the 12 local gondola matrices. Each gondola retains its attachment translation while its inverse Y rotation keeps the cabin upright. Register every returned path with OVStage and write all matrices at the same ordinal.

The coaster's forward axis is local +X. `CoasterRoute(points).transform(phase, offset_m=0)` interpolates by arc length with a smooth tangent basis. `phase` is normalized to `[0,1)`. Positive direction follows increasing sample order. The frame's +Y is left and +Z is up. In Euler form, uphill pitch is negative about Y for a +X-forward car; the matrix helper handles this directly.

Revision 2 preserves `/World/Park/RIDE_COASTER/Train` and adds:

- `/World/Park/RIDE_COASTER/Train/Car_00`
- `/World/Park/RIDE_COASTER/Train/Car_01`
- `/World/Park/RIDE_COASTER/Train/Car_02`

Each car is modeled around its own local origin. `train_transforms(route, phase)` returns the Train world pose and each car's local pose. Rear cars follow their own arc-length positions at offsets `-2.3` and `-4.6` m. Each car matrix is `car_world @ inverse(train_world)`, so multiplying it by the Train matrix produces its correct world pose. Register these three new child paths in the renderer before writing them. The generator authors valid initial poses at phase `0.77`, so the USD opens with the cars on the track even without a runtime.

```python
from modeling.animate import (
    CoasterRoute, wheel_transforms, train_transforms, advance_phase,
)
route = CoasterRoute(ride['coaster']['points'])
# Register keys from wheel_transforms(0) and train_transforms(route, 0).
wheel_phase = advance_phase(wheel_phase, dt, 100, wheel_running)
for path, matrix in wheel_transforms(wheel_phase * 2 * math.pi).items():
    write_transform(path, matrix, ordinal)
train_phase = advance_phase(train_phase, dt, 65, coaster_running)
for path, matrix in train_transforms(route, train_phase).items():
    write_transform(path, matrix, ordinal)
```

Stopping a ride freezes phase; resuming continues from that pose. Motion is a presentation model with constant travel speed. It does not model gravitational acceleration, train dynamics, operating clearances, or a certified ride design.

## Revision 2 visual changes

The detail pass adds planted beds, a coaster rock garden, lake island and lilies, reeds, deck handrails and ramps, paving joints and curbs, queue shades and fans, operator cabinets, menus and counters, waste stations, wayfinding, hotel side windows and HVAC, water-tank ladders and valves, transformer hardware, charger cables, accessible parking, and entrance banners. Guest silhouettes have arms, and train cars carry riders.

Tree trunks previously intersecting the first-aid building, restrooms, a water tank, and solar panels have been moved. The layout remains stylized. Accessible features are represented for demonstration, not assessed against a building or accessibility code. Utility relationships remain data-driven overlays; decorative hardware does not claim surveyed underground cable or pipe routes.

The scene remains texture-free and small enough for the native runtime: this revision adds 768 prims, retaining the same 12 operational roots. All geometry and material content is original procedural work for the project.

## Lighting and camera

`/World/Camera` is at `(142,-180,155)`, aimed at `(0,0,2)`, with focal length 42 mm and aperture 36 × 20.25 mm. Its USD transform comes from `Gf.Matrix4d.SetLookAt(...).GetInverse()`. The runtime can override focal length and view. For portrait windows, reframe instead of cropping the authored 16:9 composition.

`/World/Sun` is a warm distant light; `/World/Sky` is a blue ambient dome without an HDR texture. Water, cars, rails, glass, and solar panels have distinct roughness and metallic values. The scene is a demonstration model, not an engineering design or safety simulation.

## Blender handoff

Blender 4.x or newer with USD import support is required:

```bash
blender --background --python-exit-code 1 \
  --python modeling/import_blender.py -- --output assets/park.blend
```

On Horde worker `park-twin-rtx`, the installed official standalone binary is `/home/horde/tools/blender-4.5.3-linux-x64/blender`. The distribution's older Blender 3.0.1 lacked the USD import operator.

Blender imports analytic USD primitives as meshes but omits their material bindings. `import_blender.py` restores them using the generated `assets/blender_materials.json`, which contains full prim paths and PreviewSurface parameters. The script rejects a missing camera, unexpectedly small imports, and unbound meshes after repair. The OVRTX USD stage needs no repair.

The revision 2 `park.blend` was imported, saved, reopened, and validated on Blender 4.5.3 LTS: **2,997 objects, 2,954 meshes, 33 materials, zero unbound meshes**, a valid camera, all 12 stable asset IDs, and all three articulated-car world matrices. Every mesh material binding and its color, roughness, and metallic parameters were checked. The file is 20,242,246 bytes.

`blender_validation.json` records source commit, source USD hash, Blender file hash, and the worker verification. The maximum articulated-car matrix discrepancy was below `4.8e-7`. Artifacts were written to `/home/horde/park-twin-artifacts/154e746/`, leaving the immutable release unchanged. The local scene validator checks that this stored report matches the actual local USD and Blender bytes; it does not claim to rerun Blender. If either file changes or evidence is missing, the handoff becomes pending in `scene_quality_validation.json`.

## GPU evidence plan

Capture images from the OVRTX service with its `/status` response alongside them to preserve renderer versions and frame-counter provenance:

1. **Whole park:** confirm the entrance, railings, rides, lake, planting, utilities, buildings and parking fit the view.
2. **Wheel:** capture two angles with upright cabins and the new shaded queue.
3. **Coaster:** capture the train on a hill and curve, confirming all three articulated cars follow the rails.
4. **Object selection:** pick a visible mesh and verify the actual OVRTX hit path resolves to the expected asset/API record.
5. **Utilities:** focus the transformer/batteries and water tanks/valves, with synthetic measurements in the inspector.
6. **Incident response:** stop a ride, record scenario/API state, then resume and verify motion continues from its stopped pose.

Keep both a browser screenshot and direct `/frame.jpg` export, recording their source-release and frame provenance. A Blender import/reopen report is separate modeling evidence, not an OVRTX rendering or browser-picking claim. The revision 2 Blender handoff is verified; native rendering and interactive acceptance must be assessed using their separate runtime/browser evidence.
