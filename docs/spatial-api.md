# Read-only spatial design API

The spatial API lets a user inspect the authored path network, test a closure, and compare the unchanged park with the separate dining-connection design. It answers whether a route exists **in that chosen graph**, and reports its plan distance and assumed walking time. It does not command signs, move guests, change live park state, or feed the operational forecasting model.

Install the module from the application factory:

```python
from backend.spatial import install_spatial_routes
install_spatial_routes(app)
```

Installation verifies source identities before registering any endpoints. If a required artifact is missing, malformed, or has a mismatching declared hash, it raises `SpatialIdentityError` and exposes no spatial routes. The application should fail startup instead of serving an unverified design. No database, GPU SDK, network service, or live-state object is required by this module.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/spatial/capabilities` | Available variants, bounded input limits, limitations and source identities |
| `GET /api/spatial/graphs/baseline` | Unchanged authored graph, returned as a fresh copy |
| `GET /api/spatial/graphs/dining_connection` | Graph for the separate graded dining connection |
| `POST /api/spatial/route` | Read-only shortest-path query with optional closures and authored accessibility filter |

Example request:

```json
{
  "variant": "dining_connection",
  "origin": "ENTRY_GATE",
  "destination": "FOOD_COURT",
  "blocked_edges": [],
  "accessible_only": false,
  "walking_speed_mps": 1.2
}
```

`variant` defaults to `baseline`. Origin and destination accept a graph node ID or an explicitly mapped asset ID. The graph endpoint exposes those mappings. In particular, `RIDE_WHEEL` maps to the **public approach**, not boarding, and the dining variant maps `FOOD_COURT` to its new plaza landing. Query `wheel_boarding` separately to see that the current graph does not provide a validated boarding route.

The route response includes:

- `reachable`, `distance_m`, `assumed_walking_seconds`, ordered node/edge IDs, and route positions.
- `entrance_scope` and destination notes explaining whether the endpoint is a public approach or an entrance.
- `variant`, `query`, and `variant_design` for explicit design context.
- `identity`: graph hash and version, baseline graph/scene/geometry hashes, and separate variant-layer/evidence hashes when applicable.
- `distance_basis`: **2D plan distance** on the authored graph. The dining grade exists in USD but is not integrated into this distance calculation.
- `synthetic: true`, `calibrated: false`, `execution_authority: "none"`, `physical_guidance: false`, `live_state_bound: false`, `forecast_coupled: false`, and `mutates_live_state: false`.

A valid query with no route returns HTTP 200 and `reachable: false`, with null distance/time and empty route arrays. It does not invent a straight-line shortcut. A bad node or closure identifier returns HTTP 422. Queries can close walkable edges; there is no request field that enables a missing or obstructed edge.

## Before/after checks

| Query | Result |
|---|---|
| Baseline entrance → food | Unreachable |
| Dining design entrance → new food landing | 40.852 m; 34.04 s at assumed 1.2 m/s |
| Same design with `dining_connector_link` closed | Unreachable |
| Same design with `accessible_only: true` | Unreachable: the separate park-entry threshold remains unresolved |
| Baseline entrance → wheel public approach | Reachable; boarding is not implied |
| Baseline entrance → `wheel_boarding` | Unreachable |

For example, close the design connection by setting:

```json
"blocked_edges": ["dining_connector_link"]
```

The accessibility filter uses authored step-free labels only. It is not an accessibility certification. The speed assumption changes time, not the selected distance or the physical geometry. Neither a route nor a short walking time establishes spare ride/food service capacity, crowd safety, evacuation performance, or an operating benefit.

## Identity and immutability

At installation the service reads fixed, allowlisted project paths and verifies:

1. Both graphs declare the actual baseline USDC and USDA hashes.
2. The dining graph declares the actual baseline graph and design-layer hashes.
3. The saved design evidence declares the actual variant graph, baseline graph/scene/geometry, and design-layer hashes.

The service retains validated graphs and identities as immutable serialized bytes behind a read-only mapping. Every API response is deserialized into a fresh object. Caller edits cannot affect later queries. Files edited after installation cannot enter the verified in-memory snapshot; a restart reloads and revalidates the artifacts. The identity therefore says `verification: "verified_at_installation"` and `snapshot_policy: "immutable_until_restart"`.

This is artifact consistency checking, not a cryptographic signature or an independent trust authority. The release manifest and repository history remain the provenance for the application package. The API does not read arbitrary paths supplied by request parameters or graph metadata.

## Input limits and errors

Requests require `Content-Type: application/json`. The body is streamed with a 16 KiB maximum. The parser rejects duplicate JSON keys and nonfinite numbers. The strict model rejects additional fields and type coercions such as `"false"` for a boolean or `"1.2"` for a speed.

- Origin/destination/edge IDs: 1–64 characters, beginning with a letter, then letters, digits, underscores or hyphens.
- Blocked edges: at most 32, with no duplicates and no unknown IDs.
- Walking speed: finite numeric value from 0.3 to 2.5 m/s; default 1.2.
- Variants: exactly `baseline` or `dining_connection`.
- Oversized body: HTTP 413. Wrong media type: HTTP 415. Invalid JSON, fields or graph query: HTTP 422.

Error responses have a stable `detail.code`, such as `invalid_spatial_request`, `invalid_spatial_query`, `spatial_request_too_large`, or `spatial_json_required`.

## Independence from live and replay state

These endpoints do not read the simulator, canonical observations, replay cursor, command receipts or renderer. They acquire no live-state write lock and perform no database writes. A spatial design query remains available while the UI shows a recorded view because it concerns the separately chosen authored design, not a new forecast from recorded observations. The UI must label that distinction clearly.

The existing planner's aggregate rerouting behavior is **not** validated or changed by this API. Connecting path availability and walking delays to a prospective operational forecast requires a separate, reviewed modeling step.

## Validation

`tests/test_spatial_api.py` contains **42 passing checks** covering before/after reachability, closure and accessibility abstention, endpoint scope, identity tampering, byte-level graph changes, returned-object and on-disk immutability, strict/oversized inputs, invalid JSON, unknown IDs, no live/replay access, and OpenAPI documentation.

```bash
python -m pytest tests/test_spatial_api.py -q
```

The related scene evidence remains in [circulation.md](circulation.md) and [dining-design-variant.md](dining-design-variant.md). The API itself neither renders nor claims new GPU evidence.

## Static native design previews

`GET /api/spatial/previews/{variant}` serves the matched dining close-up as `image/png`; `GET /api/spatial/previews/{variant}/metadata` returns its graph identity, camera, native OVStage/OVRTX versions, image/report/composition SHA256 values and capture/verification timestamps. Both responses carry `X-Spatial-Graph-Sha256`, `X-Spatial-Scene-Sha256`, `X-Spatial-Variant-Layer-Sha256` (empty for baseline), `X-Spatial-Preview-Image-Sha256`, `X-Spatial-Preview-Report-Sha256`, and `X-Spatial-Preview-Mode: static_native`. Clients can compare graph headers to their selected graph and hash the received image bytes before display.

These are static native captures of authored geometry, with the same camera for baseline and dining design: eye `[-1,-43,17]`, target `[-9,-26.4,0.3]`, 42 mm focal length and 1600×1000 pixels. They contain no live telemetry and do not establish accessibility, capacity, physical guidance or operating benefit. The API itself does not start a renderer.

At installation, optional files are read only from `docs/images/fox-cycle-20261019/dining-design/{baseline|dining_connection}/`: `report.json`, `dining-closeup.png`, and `dining-closeup-composition.usda`. Limits are 128 KiB, 16 MiB and 64 KiB respectively. Symlinks and nonregular files are rejected. Report file paths never select local files. Verification requires a complete native render without reported errors, no live data or diagnostic overlay, exact installed graph identity, expected layer order/roles/hashes, matching capture/composition digests, consistent camera metadata, PNG chunk checksums/dimensions and timestamp ordering. Report source paths may use a source-directory symlink while composition paths resolve to the release directory; both must retain the expected allowlisted asset suffixes. Neither remote path is opened locally or exposed in curated metadata.

Validated image bytes and metadata remain immutable until restart, matching the graph snapshot policy. A later on-disk replacement cannot acquire the installed preview's verified identity. If optional artifacts are missing, malformed or inconsistent, both preview endpoints return **503** with `detail.code: spatial_preview_unavailable`, without a substitute image; the graph API remains available. Restoring artifacts requires restart to install a new snapshot. Invalid core graph/source identity still prevents spatial installation entirely. Unknown variants return 422.

This is artifact consistency checking, not a signed rendering attestation. A self-consistent report is not independent proof of its origin. `tests/test_spatial_previews.py` exercises the actual captured artifacts, metadata and headers; missing/replaced/oversized/corrupted files; unsupported paths and symlinks; malformed/incomplete reports; graph/layer/camera mismatches; and separation of optional preview failure from mandatory graph identity.
