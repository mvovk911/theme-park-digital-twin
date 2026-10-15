# Scene identity, bindings and inventory

The park now has one operational identity source. `backend/domain.py:registry()` owns asset IDs, canonical names, categories and scene paths. `backend/connectors/catalog.py:default_catalog()` owns source IDs, source-asset IDs, metrics, units and authoritative-source declarations. The scene generator reads these definitions at build time and exports portable declarations. It starts no application, opens no database, and contacts no source.

The native renderer still loads self-contained USD. It does not need to import the backend to render a scene. Embedded relative API paths are declarations for application clients; neither USD nor its metadata establishes a live connection.

## Names and physical signs

`assets/asset_registry.json` now uses the canonical operational `name` and `category`. The corresponding USD root has the same `displayName` and `assetName` custom data. Every asset keeps the same stable ID and prim path.

Existing designed signage is preserved as an explicit authored alias. For example, the operational **Skyline Coaster** record points to `/World/Park/RIDE_COASTER`; its modeled **Comet Run Coaster** branding is recorded in `authored_name`, `aliases`, and the USD `authoredName` field. This resolves metadata drift without silently changing the physical artwork. The complete mapping is in the registry and inventory rather than duplicated in application code.

The operational category is canonical. Earlier authoring categories remain available as `authored_category` when useful for the modeling context.

## Real connector IDs versus conceptual tags

Earlier `systems` entries mixed concepts such as `queues`, `energy`, and `maintenance` with actual source IDs. They now have distinct fields:

- `connector_ids`: actual IDs derived from the current connector catalog.
- `systems`: compatibility field containing the same resolvable source IDs.
- `conceptual_tags`: the earlier authoring concepts, retained as descriptive tags.

A concept is not automatically mapped to a source. An asset only advertises connectors that actually have mappings for that asset in the sole operational catalog. For example, a facility may have a conceptual cleaning tag without a cleaning connector implementation.

## Static semantic declarations

`assets/scene_bindings.json` contains 138 catalog metric mappings across the 12 assets. It includes a deterministic SHA-256 fingerprint of the relevant names, source identities and mappings. The same fingerprint is embedded in USD and the asset registry.

Each operational USD component has a `parkTwin` custom-data dictionary containing:

- `bindingMode = declarative_catalog` and `containsLiveValues = false`.
- Canonical source IDs and separate conceptual tags.
- Relative asset and observation API paths.
- For each source and metric: source-asset ID, destination property, unit, value type, and authoritative flag.

For example, a binding says which connector owns `queue_minutes` and that its unit is minutes. It does **not** store the latest wait, a timestamp, a quality status, or a claim that the source is connected. Read those from accepted observations and their runtime provenance. Neither conceptual tags nor static USD declarations should be used as a substitute for current connector health.

## Assembly semantics

The USD hierarchy now carries standard model-kind metadata:

| Root | Model kind |
| --- | --- |
| `/World` | `group` |
| `/World/Park` | `assembly` |
| Each operational asset root | `component` |
| `/World/Park/LANDSCAPE` | `component` |
| Train, individual cars, wheel rotor and gondolas | `subcomponent` |

Operational component roots also have an `assetInfo:name` equal to their stable asset ID. These declarations do not change geometry, transforms, picking paths, or the ride animation contract.

## Deterministic inventory

`assets/scene_inventory.json` reports each asset's canonical and authored names, path, model kind, child counts, prim types, geometry counts, material usage, default-pose world bounds and dimensions, connector IDs, and dynamic subassemblies. It also reports stage-wide prim counts.

Triangle counts are deliberately limited to **fan triangulation of authored polygon mesh faces**. USD cubes, cylinders, spheres and cones remain analytic primitives; their rendering tessellation depends on the renderer. Their counts are reported separately and their triangle count is `null`. Do not present the polygon count as the total rendered triangle count or a GPU performance measurement.

Bounds are USD world-aligned bounds at the authored default pose, in meters. They include decorative children assigned to the asset. For example, guests under an entrance root can broaden its spatial extent; bounds are scene selection/framing bounds, not a surveyed facility footprint.

## Rebuild and acceptance checks

Run from the project root:

```bash
modeling/.venv/bin/python modeling/generate_park.py
modeling/.venv/bin/python modeling/validate_scene.py
modeling/.venv/bin/python modeling/animate.py
```

`modeling/scene_semantics.py` implements the build-time export. The validator compares the generated registry, every embedded metric binding, and the exported binding manifest against the current authoritative Python definitions. It also recomputes the inventory from the actual USD and rejects stale output. The current generation remains byte-identical when repeated without input changes.

`assets/scene_quality_validation.json` identifies the exact validated USD hash and catalog fingerprint. The scene remains revision 2 because this milestone adds metadata and assembly semantics without changing its geometry. The revision 2 Blender handoff has been regenerated from immutable source release `154e74688d46583dde9e869bf8dc105a5881669d`, saved, reopened, verified, and downloaded. Its report records all 12 stable IDs, 2,954 bound meshes, material parameters, camera, and three articulated car matrices. Native GPU rendering and browser/picking acceptance remain separate evidence.

Ordinary scene validation does not rerun Blender. It verifies the stored worker report against the actual local Blender and USD hashes, byte count, scene revision, IDs, and recorded reopen result. Matching evidence yields `blender_handoff.status = verified_matching_artifact`; missing, stale, or mismatched evidence yields `pending` with reasons. The handoff revision is derived from matching evidence rather than hard-coded.

When changing an operational name or connector mapping, edit its authoritative backend definition, regenerate the scene, and run the validator. Do not hand-edit generated binding metadata or create a second hard-coded connector mapping in the modeler or viewer.
