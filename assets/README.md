# Editable project assets

All park geometry is procedural and created for this project. No third-party
texture downloads are required. Lengths are meters and the USD stage is Z-up.

| File | Purpose |
|---|---|
| [park.blend](park.blend) | Editable Blender 4.5.3 LTS scene; validated after saving and reopening |
| [park.usdc](park.usdc) | Compact binary OpenUSD scene loaded by the GPU application |
| [park.usda](park.usda) | Human-readable OpenUSD source for inspection and diffs |
| [asset_registry.json](asset_registry.json) | Twelve stable asset IDs, USD paths, bounds and source-system associations |
| [ride_paths.json](ride_paths.json) | Coaster route and Ferris wheel geometry parameters |
| [blender_materials.json](blender_materials.json) | Material binding manifest used to repair analytic-primitive import in Blender |
| [scene_validation.json](scene_validation.json) | USD scene validation results |
| [blender_validation.json](blender_validation.json) | Blender object/material verification results |

Generation and editing instructions: [scene documentation](../docs/scene.md).
Animation transforms: [modeling/animate.py](../modeling/animate.py).
Rendered progress gallery: [project progress](../docs/progress.md).

The Blender file is an editable handoff. The live renderer loads `park.usdc`; edits
made only to the `.blend` file do not automatically update the runtime USD. Export
and validate a replacement USD while preserving the registry's prim paths before
using edited geometry in the application.
