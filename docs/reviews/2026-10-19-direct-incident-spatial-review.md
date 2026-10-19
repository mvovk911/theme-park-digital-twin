# Independent review: direct incidents and spatial design queries

Reviewed 19 October 2026 against `64c8bfa28b81030b61d3dd7b1589cf5e7902d4a4` plus changing workflow/UI/spatial working-tree additions. Read backend contracts/services, workflow UI, related documentation and tests. Independently ran workflow and spatial suites: **73 passed**, one dependency deprecation warning, 17.95 seconds. No shared HTTP service or GPU was accessed. This is not acceptance of an immutable deployed release or a human usability study.

**Verdict: direct incident proposals resolve a real product-design problem while preserving the existing execution safeguards. The spatial API also has a useful scope: comparing authored designs. Its next UI should answer one concrete access question rather than imply an operational navigation system.** No new P1 contract defect was found in this review.

## Direct incident: the right reduction in scope

The new path fixes the earlier requirement to create a forecast merely to request an inspection. It uses the same proposal builder, executor, durable request identities, expiry checks, source-quality gates and work-order readback as the saved-plan path. It does not create a parallel command system.

The current-incident predicate appropriately binds the target rather than an unrelated global scenario label. A source-observed fault can justify inspection while the synthetic global scenario remains normal. Required maintenance observations must still be fresh, consistent and synthetic. An unrelated stale ERP feed cannot invalidate those observations. A changed target status, inspection result, source owner or work order still prevents an unreviewed command.

`creation_observation` is valuable audit evidence: the exact status, inspection status and open-order count retain source identity, source/ingestion timestamps and quality at proposal creation. Later current-state checks and readbacks do not rewrite that historical observation. The UI source explicitly labels those frozen checks and displays later asset status separately from database read time. This is stronger than retaining a hash whose original values have disappeared.

Optional saved rationale is treated correctly as context. An old model's result need not reproduce on today's deployment merely to explain a past thought process. Its stored payload integrity is checked, current-model reproduction is explicitly not claimed, and it cannot replace the current target checks. Real source authenticity and operator authorization remain unimplemented; a matching content hash does not establish either.

### What the shorter path proves

The scripted comparison of four versus seven steps is evidence that prerequisites were removed from the designed interaction. It does not prove a corresponding percentage improvement in operator speed, error rate or workload. Reading the evidence, handling conflicts, recovering a request and deciding whether dispatch is warranted may dominate actual task time.

The next user-value experiment should compare the legacy immediate dispatch, saved-plan workflow and direct-incident workflow on the same small set of incidents. Include an obvious inspection need, a healthy closed attraction, stale required data, an already-open order and a lost acknowledgement. Measure correct outcomes, duplicate attempts, time to find the existing order, and whether the participant understands that dispatch did not repair the ride. If no park operator is available, keep the exercise explicitly scripted and report interaction outcomes without human-performance claims.

## Spatial API: useful separation, still limited evidence

The API verifies fixed graph/scene/variant identities at installation, retains immutable snapshots and returns fresh objects. It does not read live state or couple itself to the forecast. Route queries cannot enable excluded edges or mutate the scene. These boundaries prevent a design comparison from quietly becoming a command or claiming current guest conditions.

Its results are appropriately specific: dining is unreachable in the baseline graph; the authored connector makes the new dining landing reachable; closing that connection removes the route; an unresolved entrance threshold still prevents the authored step-free route. A wheel public approach is not boarding. The response preserves these endpoint scopes, assumptions and identity hashes.

### Smallest useful UI

Build one panel around **“Does this dining connection solve access from the entrance?”** Use the same origin, destination and speed assumption for both designs:

| View | Display |
|---|---|
| Baseline | No route in the authored graph; highlight the actual missing link |
| Dining design | 40.852 m plan distance and 34.04 s at assumed 1.2 m/s to the new plaza landing |
| Connector closed | No route; preserve the closure as a visible query input |
| Authored step-free filter | No entrance-to-dining route; identify the remaining entrance threshold |

Pair these results with matched native closeups and a small graph view. Keep chosen design, endpoint scope, query assumptions and graph/scene identities visible. A read-only route query can remain available while the operations UI shows replay, but label it **authored design** so its time basis is not confused with the recorded park.

Do not report a percentage walking-time saving when the baseline is unreachable: there is no finite baseline travel time to subtract. Do not color the new route “safe” or “accessible” merely because Dijkstra finds it. This panel is a test of modeled connectivity, not crowd performance, accessibility certification or permitted real-world guidance.

The existing aggregate planner still ignores this graph. That is an explicit limitation, not something the new UI should conceal. A future integration should retain graph identity in each branch and reject unsupported paths before assigning walking delay. It also needs service capacity and compliance assumptions; route existence alone cannot justify redirecting demand.

## P2: optional design failure currently stops the whole backend

`create_app()` installs the spatial module unconditionally. Its installation requires both baseline and dining artifacts; a missing or mismatched optional design artifact raises before the application can start. Failing closed for an invalid spatial capability is appropriate. Making maintenance workflows unavailable because an experimental design file is missing is a separate availability choice.

For this controlled prototype, a complete immutable release and rollback procedure can manage that coupling. Before supporting normal operations alongside design editing, decide whether spatial design is a mandatory release capability or an optional module that can explicitly report unavailable while unrelated operations remain healthy. Never serve an unverified graph as a fallback. This is a deployment-boundary improvement, not a reason for a rewrite.

**Implementation recommendation for this cycle: retain mandatory complete-release validation.** Do not catch a spatial hash failure simply to get an incomplete release running. `scripts/release_artifact.py` rejects missing/modified manifest members during verification, staging and activation. Separately, `project_revision.source_identity()` reports source integrity at process startup; it does not itself refuse application startup, and the existing health endpoint can still report `status:ok` alongside `verified:false`. Deployment acceptance must inspect that source identity rather than treating HTTP health alone as verified-release proof.

If a future release explicitly declares spatial design optional, define that capability policy in its versioned configuration. An intentionally absent/unconfigured spatial module may expose stable HTTP 503 responses such as `spatial_capability_unavailable`, with an explicit capability/health degraded reason and retained source identity; unrelated services may then continue under that declared policy. It must serve no unverified graph, fabricate no baseline or query result, and make the unavailability visible in the UI. An unexpected mismatch in a managed release remains a deployment failure requiring a correct artifact or rollback, regardless of optional-module policy. Thus graceful degradation must not mask missing promised assets or redefine a broken manifest as healthy.

## Maintainability and next decision

The direct path reuses existing domain logic and the spatial module remains independent of the simulator and renderer. Formatting the workflow JavaScript has made its recovery branches easier to inspect. Keep those boundaries. Avoid adding an autonomous agent or another database simply to present the design comparison.

The next milestone should show two complete, revision-bound stories: a current incident reaching one acknowledged work order without a forecast prerequisite, and an authored design moving from unreachable to reachable while its negative controls remain visible. Their value is clearer decisions and fewer unnecessary steps. Faster operators, better park economics and physically valid guest guidance still require separate evidence.
