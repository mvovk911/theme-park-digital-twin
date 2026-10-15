# Editable project assets

**USD and Blender revision 2 are current.** The Blender handoff was saved, reopened, and verified from source release `154e746`; its stored hashes match the local files. GPU/browser screenshots carry separate capture provenance and are not validated by the Blender report.

All park geometry is procedural and created for this project. No third-party
texture downloads are required. Lengths are meters and the USD stage is Z-up.

| File | Purpose |
|---|---|
| [park.blend](park.blend) | Editable revision 2 Blender 4.5.3 LTS handoff, saved/reopened and hash-verified |
| [park.usdc](park.usdc) | Compact binary OpenUSD scene loaded by the GPU application |
| [park.usda](park.usda) | Human-readable OpenUSD source for inspection and diffs |
| [asset_registry.json](asset_registry.json) | Twelve stable asset IDs, USD paths, bounds and source-system associations |
| [ride_paths.json](ride_paths.json) | Coaster route and Ferris wheel geometry parameters |
| [blender_materials.json](blender_materials.json) | Material binding manifest used to repair analytic-primitive import in Blender |
| [scene_validation.json](scene_validation.json) | USD scene validation results |
| [scene_bindings.json](scene_bindings.json) | Static source/metric declarations exported from the sole operational catalog; contains no live telemetry |
| [scene_inventory.json](scene_inventory.json) | Deterministic asset names, model kinds, geometry counts, materials and dimensions |
| [scene_quality_validation.json](scene_quality_validation.json) | Exact USD hash, catalog fingerprint and semantic/geometry validation results |
| [blender_validation.json](blender_validation.json) | Blender object/material verification results |

Generation and editing instructions: [scene documentation](../docs/scene.md).
Identity, source bindings and inventory: [authoring contract](../docs/scene-authoring.md).
Animation transforms: [modeling/animate.py](../modeling/animate.py).
Rendered progress gallery: [project progress](../docs/progress.md).

The Blender file is an editable handoff. The live renderer loads `park.usdc`; edits
made only to the `.blend` file do not automatically update the runtime USD. Export
and validate a replacement USD while preserving the registry's prim paths before
using edited geometry in the application.
