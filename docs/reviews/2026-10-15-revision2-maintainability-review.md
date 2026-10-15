# Revision 2: maintainability and coherence checkpoint

**Recommendation: keep the project and refactor bounded components as they change. A full restart still has no demonstrated payoff.** The project is larger, but its main responsibilities now have identifiable owners, enforceable contracts and revision-bound runtime evidence. The remaining concentration in the browser and native owner loop warrants targeted cleanup before another broad feature cycle.

This independent review inspected committed `2e2b16b` in an isolated archive, then separately reviewed source/replay fix `2c763d2` and action receipts `19cee1e`. Application implementation was not edited. Earlier reviews remain historical snapshots; their failures are not rewritten as later successes.

## What is proved, and at which revision?

| Scope | Evidence inspected or rerun | Practical limit |
|---|---|---|
| `2e2b16b` CPU/API | Independently reran all 160 checks in a clean archive, normal environment: 14.29 seconds | Does not prove native or browser behavior |
| `2e2b16b` browser logic | Independently reran 28 JavaScript behavior checks and 58 DOM references | Simulated DOM logic, separate from Chromium |
| `2e2b16b` actual GPU/browser | [Native browser results](../images/revision2/final/browser-validation.json), [extended results](../images/revision2/final/extended/extended-browser-validation.json), four [render captures](../images/revision2/final/gallery/render-captures.json); renderer reports a verified manifest for this exact commit | One synthetic shared session, not production certification |
| Annotation usability | [100-sample cadence](../images/revision2/final/extended/annotation-cadence.json): visible in 92% of samples, zero annotation/image revision mismatches; previous measured visibility was 63% | Roughly ten seconds on one host; not an availability SLA |
| Real native lifecycle | [20-frame native probe](../images/revision2/native-lifecycle-validation.json) at `154e746`: ready before stop, final stopped, no cleanup errors or outstanding commands | Real SDK calls, but not exhaustive leak/concurrency testing or a new probe of every later commit |
| R2 editable Blender | `73bb9bd` handoff evidence; independently checked USD and Blender hashes against the `2e2b16b` files | Downstream editable handoff, not arbitrary Blender-to-generator round-trip support |
| `2c763d2` source acquisition during replay | Independently reran 20 replay/producer checks, including all ten domains: 5.85 seconds | In-process HTTP test transport; deployment evidence is separate |
| `19cee1e` durable action retries | Independently reran all 184 CPU/API checks in a clean archive: 15.98 seconds; also reviewed the transaction and 50 focused checks | Optional request IDs; single active gateway; no physical command delivery claim |

The new actual browser run shows three distinct native asset resolutions. Each changed-context attempt was correctly rejected with 409, followed by a successful 200 retry. The coaster phase remained unchanged during closure while the wheel advanced; reset resumed coaster motion. Source pause/stale/offline/recovery, read-only replay, continuing recording and no live-source fetches during recorded inspection passed. Reported JavaScript errors and mobile overflow were zero.

The old R1 gallery is no longer the only GPU evidence. Keep it as R1 history and use the explicitly revisioned R2 captures for this checkpoint. Do not apply the `2e2b16b` GPU result to the newer `19cee1e` transaction paths until their runtime checks are recorded.

## Has it become an uncontrollable blob?

At `930acd3`, handwritten application/model/script source totaled 2,212 lines across 17 files, with 458 test lines across two files. The same categories at `2e2b16b`, including the new producer and revision helper, total **5,786 lines across 39 files**, plus **2,864 test lines across 15 files**. Generated scenes, Blender, images and documents are excluded. Compressed CSS still makes line counts an incomplete complexity measure.

The increase bought useful boundaries:

- `backend/domain.py` owns static definitions; `model_rules.py` evaluates scenarios without storage. Producers and the gateway reuse those rules.
- `ConnectorRuntime` owns acceptance, source quality and ordering; `ParkReadModel` owns canonical projection and its short retained revision window.
- `ReplayStore` owns durable historical payloads and selected inspection state. It is distinct from the in-memory connector stream and short annotation cache.
- One renderer thread owns SDK resources; mailbox, frame publication and motion policy have independent tests.
- Scene semantics bind the operational catalog into portable USD metadata and retain designed names as aliases. Geometry is not a separate invented asset database.
- Release artifacts identify committed source and assets; startup inspection, activation and actual running acceptance are explicitly separate concepts.

These are controllable responsibilities. The bounded revision cache is justified by an observed usability problem: requiring every image to equal the latest dashboard state hid annotations repeatedly. It retains exact historical image values instead of weakening equality or attaching current values to an old frame. Backend retention is capped at 64 entries/4 MiB, oversized states are unavailable without flushing the useful window, and lookup cannot poll or mutate sources. The browser has a bounded cache, one lookup in flight, throttled failures and no live revision lookup during replay. Missing state hides annotations rather than substituting values.

The practical weak spots are still concentrated files: `frontend/app.js` is 905 lines and `renderer/service.py` is 633. Both contain several change reasons. That is a signal for focused extraction before further growth, not evidence that all working behavior should be discarded.

## What this review cycle actually corrected

Earlier independent reviews reproduced competing operational truth, inconsistent alerts, non-atomic source snapshots/cursors, discarded late receipts, mixed frame/pose generations and release reactivation failures after Python imports. Subsequent commits added regression checks and corrected those boundaries. Actual native cleanup and browser acceptance now supplement the earlier CPU-only evidence.

Two additional integration seams were important:

1. **Source collection versus operator inspection.** At `2e2b16b`, selecting replay blocked independent HTTP producer ingestion. `2c763d2` separates acquisition from operator commands while keeping successful ingestion recorded. Tests prove selected assets/KPIs/revision/time remain immutable, all ten producers continue, and operator actions/mode changes remain blocked. This fix has its own acceptance scope.
2. **Acknowledgement versus current state.** `19cee1e` stores an original request-ID acknowledgement atomically with effects, audit, settings and telemetry. Retries return that acknowledgement without repeating effects, while their `state` is explicitly current. Collision, concurrency, restart, lost response and rollback tests cover the contract. It does not imply real equipment delivery or unlimited multi-worker coordination.

This is evidence that another implementation pass is valuable **at a learned boundary**. The pure evaluator extraction, coherent frame publication and receipt transaction are successful examples. Rebuilding the entire project would also have to preserve their real SDK, persistence and selection behavior, and no replacement experiment has demonstrated an advantage.

## Next targeted refactors

1. **Extract browser transport/store and viewport code before another major UI feature.** Preserve the no-build browser deployment unless a concrete requirement warrants a toolchain. Keep exact-image annotations separate from latest inspector state; format CSS for reviewable diffs.
2. **Make presentation configuration authoritative.** Runtime motion still uses a 42-second coaster period and 0.16 radians/second wheel rate while ride metadata declares 65/100-second periods. Consume the declared configuration or explicitly distinguish authored versus runtime settings. Replace frontend action-eligibility duplication with backend capability output when extending actions; retain server validation.
3. **Keep process control separate and improve it deliberately.** Artifact integrity is stronger than the launcher: startup checks a recorded PID's project directory and reports a spawned process without proving its role/health/port ownership. Share role-aware identity checks with stop logic and validate readiness before calling a deployment healthy. Avoid turning this into a new orchestration platform.

No new blocker was found in the bounded annotation implementation. Remaining UX limits include changed-context pick retries, exact animation-phase picking, finite cache retention under much faster source rates, and the shared camera/view. Increase their scope only with measured requirements.

## Benchmark progress and next review trigger

The original benchmark's semantic ingestion, source trust, canonical incident evidence, recorded inspection and asset-quality directions now have substantial implementation and test evidence. Request-ID action acknowledgements additionally address a specific incident-loop gap at the API layer. A durable immutable comparison branch remains unimplemented; the existing same-tick comparison is correctly labeled synthetic and uncalibrated. Native vendor protocols, real park sources, calibrated forecasts and financial savings remain future work.

Run the next independent review after the first real connector, any second state writer, per-user sessions, a new scene/schema revision, or a major UI/renderer extension. During sustained development, retain milestone reviews roughly every 60–90 minutes only when meaningful integration has completed. Each review should name its exact commit and deployed identity, trace source → projection → image/action → history, check previous findings, and record reproducible evidence and unresolved limits.

A component rewrite should earn its cost by passing the same boundary and GPU acceptance checks with a simpler implementation. A full restart should require a demonstrated requirement the current architecture cannot meet economically, a bounded replacement experiment and a migration plan for assets, history and acknowledgements. Neither threshold is met here.

## Closing runtime evidence audit — `19cee1e`

The later runtime checks are now available; the earlier distinction between CPU-only follow-ups and deployed evidence can be closed for these tested paths. This reviewer inspected the reports and committed acceptance script (`ed2b940`), independently recomputed their recorded hashes/counts, and found them consistent:

- [Fresh browser smoke](../images/revision2/release19/browser/browser-validation.json), 21:26 UTC: verified `19cee1e` manifest/tree and matching R2 scene hash; three successful native asset resolutions, changed-context 409 rejections followed by successful retries, coaster freeze/resume with independent wheel motion, and zero page errors. The 92% cadence figure above remains the separately measured `2e2b16b` result; it was not remeasured by this smoke.
- [Native lifecycle](../images/revision2/release19/native-lifecycle-validation.json): actual OVStage/OVRTX, 20 frames, ready before stop, final phase stopped, no cleanup errors, no outstanding requests. This adds native evidence at the newer release; it is still a short acceptance run rather than exhaustive leak certification.
- [Actual HTTP workflow](../images/revision2/release19/workflow-initial.json): ten producer instances with ten unique sessions used concurrent HTTP threads, not ten isolated subprocesses. Twenty batches accepted all **276 events** without rejection/duplication; **22 new recordings** appeared while the selected historical payload's recomputed SHA256 remained unchanged. Six concurrent action retries returned the same acknowledgement, collision returned the documented conflict, and exactly one audit row/work order was added.
- [Post-restart verification](../images/revision2/release19/workflow-restart.json): the referenced initial report's file SHA256 recomputes correctly; source commit/tree stay unchanged while startup inspection time changes. The exact original acknowledgement returns with `replayed=true`, and audit/work orders remain unchanged. The operator performed a backend stop/start while keeping the renderer running; the report proves application startup identity and durable HTTP receipt behavior, not independent OS-process attestation.

All reported workflow cleanup operations succeeded. Scene hashes agree across the browser, native probe, both workflow reports and the actual committed USD. These checks support the synthetic operational-twin incident/acquisition/replay story at the tested release. They do not establish vendor protocol compatibility, calibrated park models, multi-user isolation, or physical control.

**Closing decision:** no unresolved blocker was found for publishing this reviewed prototype milestone. Preserve the targeted-refactor list and recurring review triggers above; broader production or new-feature claims require their own acceptance evidence.
