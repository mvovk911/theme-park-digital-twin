# Aster Park scene

The procedural source is `modeling/generate_park.py`. It creates a portable OpenUSD scene with no texture or asset downloads. `assets/park.usdc` is the compact runtime stage and `assets/park.usda` is its readable counterpart. All physical dimensions are meters, Z is up, and the site covers 160 × 120 m with the entrance on the south edge. The ground plinth extends to 165 × 125 m.

## Rebuild

```bash
python3 -m venv modeling/.venv
modeling/.venv/bin/pip install usd-core
modeling/.venv/bin/python modeling/generate_park.py
```

Generation also writes `asset_registry.json`, `ride_paths.json`, and `scene_validation.json`. Geometry uses standard meshes and USD analytic gprims with UsdPreviewSurface materials. Rails and wheel rims are actual polygon tube meshes, not curves. Signs use vector-like polygon glyphs. There are no texture paths, payloads, external references, or custom shaders to resolve.

## Spatial and selection contract

All operational asset roots are identity Xforms below `/World/Park`. Each root carries custom data `assetId` and `assetName`, plus a string attribute `park:assetId`. A picked nested geometry path can be walked toward its ancestors until this attribute is found, or mapped by longest matching `prim_path` prefix in the registry. `LANDSCAPE` is intentionally decorative infrastructure rather than one of the 12 live operational IDs.

| Asset ID | Function | Approximate center (x, y, z) |
| --- | --- | --- |
| RIDE_COASTER | Comet Run, track, train, station, queues | (-35, 18, 7) |
| RIDE_WHEEL | Aster Wheel, cabins, boarding platform | (35, 25, 18) |
| SHOW_ARENA | Starlight stage and stepped seating | (-5, 45, 2) |
| FOOD_COURT | Food outlets, umbrellas, tables | (-25, -28, 2) |
| POWER_HUB | Battery cabinets, solar, electrical hub | (57, 47, 2) |
| WATER_PLANT | Water tanks, pipes, control building | (-61, 48, 2) |
| ENTRY_GATE | Main arch, turnstiles, ticket booths | (0, -53, 2) |
| PARKING | Parking, vehicles, EV charging | (52, -36, 1) |
| HOTEL | Aster Lodge | (-58, -29, 3) |
| FIRST_AID | Medical and guest-care building | (18, -35, 2) |
| RESTROOMS | Restroom building | (53, -16, 2) |
| WEATHER_STATION | Mast and local environment sensors | (16, 43, 3) |

`asset_registry.json` has both authored operational bounds and USD-computed geometry bounds, plus names, categories, system lists, and root paths. Use computed bounds for camera framing.

## Animation contract

`/World/Park/RIDE_COASTER/Train` contains `xformOp:translate` and `xformOp:rotateXYZ`. Interpolate the 240 centerline samples in `ride_paths.json`, wrap the segment index, and assign the position. The train's forward direction is local +X. Set rotateXYZ to `(0, -pitch_degrees, yaw_degrees)`, where yaw is `atan2(dy, dx)` and pitch is `atan2(dz, hypot(dx,dy))`. Nominal lap duration is 65 s. The scene geometry remains static unless a runtime updates these transforms.

`/World/Park/RIDE_WHEEL/Rotor` contains `xformOp:translate=(35,25,19)` and `xformOp:rotateY`. Its wheel is in the XZ plane. Assign `rotateY = elapsed_seconds * 3.6` for a 100 s revolution. For upright gondolas, add or update a `rotateY` op after each gondola's translate op and assign the negative rotor angle. The gondola paths are listed in `ride_paths.json`. Stopping a ride should stop phase progression while preserving the current pose.

## Lighting and camera

`/World/Camera` is a perspective camera at `(142,-180,155)`, aimed at `(0,0,2)`, with focal length 42 mm and aperture 36 × 20.25 mm. It is oriented through a USD transform matrix from `Gf.Matrix4d.SetLookAt(...).GetInverse()`. For narrower portrait windows, frame the scene explicitly rather than cropping this 16:9 composition.

`/World/Sun` is a warm distant light; `/World/Sky` is a blue ambient dome with no HDR texture. The water, cars, rails, glass, and solar panels use distinct roughness and metallic values. All preview materials are bound explicitly. The scene is a demonstration model, not an engineering design or safety simulation.

## Verification

The initial generation contains 2,299 prims, 26 polygon meshes, and 12 registered operational asset roots. The remainder is USD primitive geometry, materials, lights, transforms, and the camera. `modeling/validate_scene.py` verifies registry paths, required transforms, material bindings, finite bounds, camera presence, and external-reference absence. Runtime renderer integration should additionally validate picking and the final image on the target GPU.

## Validated runtime animation helpers

`modeling/animate.py` depends only on NumPy and supplies `wheel_transforms(angle_radians)`, `CoasterRoute(points).transform(normalized_phase)`, and `advance_phase(...)`. Its matrices use the same row-vector convention as `renderer/service.py`: translation is row 3 and child world composition is `child_local @ parent_world`.

The current renderer's rotor Y rotation and coaster forward/left/up basis are mathematically correct. The current rotor-only update makes cabins turn upside down; write the 12 cabin transforms returned by `wheel_transforms` at the same ordinal as the rotor. Each cabin matrix has inverse rotor rotation and its original local attachment translation. This keeps the cabin body vertical at every wheel angle while its attachment follows the rim. Create query paths for the rotor **and** all returned gondola paths before entering the render loop.

```python
from modeling.animate import wheel_transforms, CoasterRoute, advance_phase
route = CoasterRoute(ride['coaster']['points'])
# Register all keys from wheel_transforms(0) in the OVStage query dictionary.
wheel_phase = advance_phase(wheel_phase, dt, 100, wheel_running)
for path, matrix in wheel_transforms(wheel_phase * 2 * math.pi).items():
    write_transform(path, matrix, ordinal)
train_phase = advance_phase(train_phase, dt, 65, coaster_running)
write_transform('/World/Park/RIDE_COASTER/Train', route.transform(train_phase), ordinal)
```

The route helper smooths tangent directions between sampled track points and uses arc length for constant presentation speed. It does not represent gravitational acceleration, train dynamics, operating clearances, or a certified ride model. Run `python modeling/animate.py` to verify upright cabins at 25 rotor angles, right-handed orthonormal coaster frames at 401 positions, positive forward movement, and stopped-phase preservation.

A known presentation simplification is that the three coaster cars are one rigid train transform. Their bodies are spaced backward along local X, so cars can depart slightly from the centerline on tight curves or elevation changes. The visible front is local +X; the correct pitch in Euler form is negative for an uphill +X heading, consistent with the basis matrix already used in the renderer. A future articulated train can give each car its own root and use route transforms with rearward arc-length offsets.

## Blender editable handoff

After installing Blender 4.x or newer with USD import support, run:

```bash
blender --background --python-exit-code 1 --python modeling/import_blender.py -- --output assets/park.blend
```

This uses Blender's USD importer, preserves the camera, imports materials and geometry, sets metric units, and writes an editable `.blend`. It prints `BLENDER_IMPORT_OK` with object and material counts. The script requires the full scene to import and refuses to save if it contains fewer than 100 objects or no camera. Blender is a modeling handoff; the runtime app continues to use OVRTX rendering.

## GPU scene evidence plan

Capture images from the **OVRTX service**, with its `/status` response alongside them so image provenance includes renderer versions and the live frame counter:

1. **Whole park:** home camera, confirming the entrance, site railings, rides, lake, trees, buildings, utilities, and parking fit the view.
2. **Wheel detail:** focus RIDE_WHEEL, capture two different wheel angles, verify cabins stay upright and boarding platform remains visible.
3. **Coaster detail:** focus RIDE_COASTER, capture the train on a hill and a turn; verify track, supports, and train direction.
4. **Object selection:** pick an actual visible ride mesh, confirm an OVRTX pick-hit prim path maps to the expected asset ID and shows API data in the inspector.
5. **Utilities:** focus POWER_HUB and WATER_PLANT, showing distinctive solar/battery/tank geometry linked to synthetic measurements.
6. **Incident response:** capture a stopped ride plus incident/API evidence, then reset and confirm animation resumes from the stopped pose.

Keep a screenshot of the interactive browser and a direct `/frame.jpg` export. The browser screenshot demonstrates the interface; the direct frame demonstrates the actual rendered scene. A Blender save/import log is separate modeling evidence and should not be presented as an OVRTX render.

### Verified Blender artifact

The Horde worker `park-twin-rtx` now has Blender **4.5.3 LTS** at `/home/horde/tools/blender-4.5.3-linux-x64/blender`. The distribution-provided Blender 3.0.1 lacked its USD import operator, so the official standalone 4.5.3 binary was installed without changing the renderer environment.

`assets/park.blend` is an editable copy, imported, saved, reopened, and validated on Horde: **2,239 objects, 2,200 meshes, 28 retained materials, zero unbound meshes, and a valid scene camera**. Its size is 15,190,908 bytes. The same file has been copied into the local project. `assets/blender_validation.json` records this evidence.

Blender's USD importer did not transfer material bindings for analytic USD gprims. The importer script now repairs every mesh using `assets/blender_materials.json`, a full path-to-material mapping and PreviewSurface parameter export produced by the scene generator. This restores all 2,200 mesh bindings and makes the modeling handoff visually faithful to the runtime USD. The OVRTX stage needs no material repair.
