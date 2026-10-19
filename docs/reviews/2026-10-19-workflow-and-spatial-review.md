# Independent review: bounded maintenance and spatial credibility

Reviewed 19 October 2026 against working-tree additions above `a13b656fadfa0e976397d1900c1b1859be6e5836`. Scope: `backend/workflows`, workflow UI source, workflow/API documentation and reports, circulation graph/query implementation and tests. No shared test gateway, Horde allocation or GPU renderer was modified. The dining design variant was still being developed; it is not accepted by this report.

**Verdict: this is a coherent FOX-inspired coordination loop with one useful action boundary, but an obvious maintenance incident should not require running a forecast first. The circulation audit also reveals why the numerical routing model cannot yet be presented as physical guest guidance.** Keep both developments, reduce unnecessary operator steps, and connect spatial constraints only after their geometry is verified.

## Evidence and scope

Independently ran `tests/test_workflows.py` and `tests/test_circulation.py`: **40 passed**, one dependency deprecation warning, 7.51 seconds. Read the independent actual HTTP report with ten passing groups, including lost responses, duplicate requests, real process restart and an actually elapsed 30-second expiry. Its report explicitly identifies a candidate dirty working tree and does not claim GPU or clean-release acceptance.

The newer conflict-context change was present in the local suite: existing order IDs, changed predicate fields and an asset-detail URL now explain what an operator should inspect. That is a meaningful usability fix, not simply a different error code. It was not part of the earlier ten-group HTTP result; keep those evidence scopes separate.

Inspected source fingerprints at this checkpoint:

| Artifact | SHA256 |
|---|---|
| Workflow service | `8a4d3724a15b08f858dd084e39ac1ce88da5b49f0035e4f3e365ee2ea6c2fa80` |
| Workflow store | `6aee0d00b0555d7ca3dd4889e201db0c784d8f23187fa735e9dc53984c70a61c` |
| Circulation query module | `e38e7316c56891cb183c9389cbfc159c2c8aafef49c0e539470e5c6ec0254f4c` |
| Circulation graph | `ae518e995a906d4797579c53597e065d3824165884a6675a91bd4c0d9f82c919` |

Native circulation capture had not completed. Opening USD and passing CPU geometry checks do not establish that the overlay renders correctly, remains legible, or represents an operationally usable route.

## Maintenance: value and boundaries

The useful outcome is narrow and concrete: a current fault or inspection issue can produce one synthetic work order whose exact identity is read back. Dispatch does not reopen the ride. Current field quality, source ownership, work-order consistency and a bounded relevant-state predicate are checked at proposal and execution time. Normal telemetry ticks do not invalidate a proposal merely because a whole-state hash changes.

Durable intent plus the existing action receipt makes recovery across two database transactions understandable. A committed acknowledgement survives a lost response or later expiry; the old acceptance and new database readback can legitimately show different work-order lifecycle states. Explicitly distinguishing acceptance from completed physical work is central to a credible manager agent.

The design does not implement user/role authorization, a real CMMS connector, distributed exactly-once delivery or physical actuation. Legacy synthetic action APIs still exist independently. Those limits are documented, and the new workflow does not imply they have disappeared.

### P2: forecast-first maintenance adds steps without demonstrated benefit

The current operator path is compare → save comparison → choose a dispatch action → create proposal → execute. Yet the dispatch decision is actually justified by independently checked current fault/inspection evidence, and dispatch has no forecast restoration benefit. Requiring a forecast makes a straightforward incident slower and couples it to a global scenario label that is not itself a maintenance diagnosis.

An unrelated stale source can make the forecast say insufficient data even when the maintenance-specific observations are fresh. The API still permits saving a diagnostic bundle and checks its own fields, so this is not a hard dispatch blockade. It is confusing product behavior: the operator is asked to save a comparison that may explicitly say it cannot support a decision, then use it merely as an action selector.

Add an optional **current-incident proposal**: select the actual asset/alert, freeze the relevant observed evidence, state the requested inspection, and use the same TTL, current-state checks, duplicate prevention, explicit execution and receipt/readback contract. A saved comparison can remain optional rationale when it genuinely informed a choice. Do not create a second executor or weaken any existing checks.

For this direct path, the important predicate is current target condition/source/work-order state. Avoid making an unrelated whole-park scenario label an authorization substitute. An actual current fault can exist through accepted source observations while the simulator remains in its normal scenario.

Measure the improvement with an ordinary operator task: time and clicks from opening a fault alert to a correctly acknowledged work order, incorrect/duplicate orders, and whether the user can explain what remains unrepaired. Compare with the existing legacy dispatch workflow; a more elaborate path is not automatically more valuable.

### P2 reproduced: a fresh database read can make stale asset status look fresh

After a successful dispatch, I paused `ride_scada` and advanced only an isolated connector clock by ten seconds. Canonical coaster status correctly became stale, retaining source time `20:19:06.996 UTC`. Retrying the accepted workflow correctly returned HTTP 200, but its readback contained `asset_status:closed`, `source:synthetic_work_order_database` and `observed_at:20:19:17.036 UTC`, without the asset status's source time or stale quality.

The work order was freshly read from its database; the asset status came from a separate accepted observation. Presenting both under one readback source/time can make stale telemetry appear freshly confirmed. The UI labels that whole block as database readback, reinforcing the ambiguity.

Retain receipt recovery even when telemetry is stale. Add separate `asset_status_evidence` with source ID, source timestamp and quality, and keep the work-order database read time distinct. Label stale/unknown asset status accordingly. This is a provenance/UI correction, not a reason to reject historical acknowledgement recovery or claim the work order vanished.

**Local backend resolution verified:** service SHA256 `530c95ef5a2c5ce15ae4275069304131226d71d728439deb339ddffa2928f07d` now returns independent asset-status evidence, its original source timestamp/quality and an explicit work-order-only source scope. Independently reran three focused stale-input/recovery checks: all passed, 17 other checks deselected. The new regression demonstrates unchanged receipt/work-order identity while asset status remains visibly stale in the API. Frontend display changes were still in progress at this verification point; actual UI proof remains separate.

## Spatial audit: an unusually useful negative result

The graph finds real contradictions between an attractive scene and a route a person could plausibly follow: dining paving gaps, an unreachable coaster gate, wheel rails blocking a shortcut, a utility fence across a promenade and unmodeled level transitions. Keeping those connections excluded is more valuable than adding invisible graph edges to make the demo succeed.

The authored graph reports distances and assumed walking seconds, distinguishes public approaches from boarding, and marks step-free labels as unvalidated. Its centerline/paving checks are deliberately narrower than a full corridor clearance or obstacle-complete navmesh. This is honest design-diagnostic evidence. It does not validate accessibility, crowd capacity, evacuation or spare attraction capacity.

### P2: numerical demand transfer is not yet an executable route

The planner currently transfers service demand among coaster, wheel and food queues without consulting this graph. The graph now shows that some corresponding entrances are unreachable. Those two models can coexist only if the numerical result is described as abstract service-demand redistribution under omitted route assumptions. It must not be presented as verified guest guidance or an instruction ready for signs/apps.

The new bounded workflow wisely has no rerouting executor. Preserve that limit. Before adding one, query graph reachability between explicitly scoped approach/entrance nodes; require a path compatible with the intended mobility assumptions; include travel time and service availability; and retain graph/scene versions in the branch evidence. When the route is unknown, return unknown/infeasible rather than inventing a shortcut.

The proposed dining connector is a good next design experiment because it has a falsifiable question: does a separately authored, inspectable paved connection change an unreachable destination into a reachable one without crossing the known fixtures or curb? Prove that geometry change first. Do not convert a two-meter assumed width into a crowd throughput figure without a pedestrian model and supporting calibration.

## Maintainability judgment

No full rewrite is justified. Workflow contracts, persistence, current-state service and HTTP boundary are separate; the circulation tool can run without database/GPU dependencies; the additive layer preserves the baseline. This fits the coordination pattern better than a single agent owning geometry, simulation and commands.

Four SQLite stores and wrapped application lifespans are still manageable at this scope because ownership and closure are tested. Avoid adding more persistence services casually. Keep lock order documented, external network calls outside those locks, and model/scene/evidence identities explicit. The workflow UI is compact but densely formatted; format it as it changes so recovery/error logic remains reviewable. Consolidate repeated browser transport or identity helpers only when doing so preserves the distinct retry semantics.

## Next milestone acceptance

1. Exercise the corrected stale asset-status readback provenance through the actual UI.
2. Demonstrate direct current-incident proposal alongside optional saved rationale using the same executor.
3. Capture real workflow UI success, stale-input refusal, existing-order navigation, replay restrictions and retry recovery at a committed revision.
4. Keep diagnostic baseline and dining variant separate; record geometry/hash/route differences and actual native OVRTX views.
5. Connect the route graph to a future branch only after the modeled entrance/path semantics are explicit, with no claim of certified guest routing.

These changes advance user value by removing unnecessary steps and making impossible plans visible. The number of agents or rendered objects is not the measure of progress.
