# Integrated checkpoint review: controllability and evidence

Reviewed revision: **`29c4091cf83827f782ccc8004fa74a44caafee9a`**, 2026-10-15 UTC. This review uses a clean Git archive of that exact revision. Later backend model extraction, source producers and runtime release identity work are outside scope. Earlier reviews remain historical snapshots: [architecture](2026-10-15-architecture-review.md), [connector acceptance](2026-10-15-connector-acceptance-review.md), [public-example benchmark](2026-10-15-digital-twin-benchmark.md).

**Decision: keep the project and make focused refactors. It has grown, but has not become an uncontrollable blob.** The increase largely adds explicit ingestion, durable inspection, lifecycle and release boundaries that the earlier prototype lacked. The critical remaining issues concern time/state identity across these boundaries and Python runtime writes into verified releases. A full restart would not resolve those semantics automatically.

This is a coherent **local candidate**, not a newly validated GPU deployment. The published `930acd3` application and revision 1 gallery remain the last externally verified baseline. Revision 2 assets, new source/provenance UI, replay and lifecycle changes still require native OVStage/OVRTX, Blender and browser acceptance after connectivity is available. Old images must not become evidence for new capabilities by proximity to current code.

## Evidence gathered

- Isolated `git archive 29c4091` under `/tmp/park-integrated-review-29c4091`; no current implementation files, compute sessions or commits changed.
- Reran all committed CPU/API targets with the recovered project environment and the integrator's test-process-only sandbox loop plugin:

  ```text
  98 passed in 14.07s
  ```

  Targets: `test_backend.py`, `test_connectors.py`, `test_connectors_http.py`, `test_gateway.py`, `test_release_artifact.py`, `test_renderer_runtime.py`, `test_replay.py`. The plugin affects test-loop wakeups; it is not shipped application code.
- Independently reproduced the release bytecode problem with an actual committed artifact, temporary release root and ordinary Python import.
- Independently reproduced false replay pose association with the actual application/capture API and a deliberately old fake renderer HTTP status. This proves a CPU association bug, not native rendering behavior.
- Deterministically demonstrated mixed status/frame metadata with a frame-cache interleaving fixture.
- Reviewed the parent's 15 JavaScript logic/57 DOM-reference checks as reported local checks. They were not rerun here, and they are not browser-layout/input/native evidence.

## Has the project become a blob?

At `930acd3`, the earlier review counted 2,212 application/model/script lines across 17 files, plus 458 test lines across two files. At this checkpoint the same source categories contain **4,966 lines across 33 files**, plus **1,984 test lines across nine files**. Generated USD/Blender, screenshots, deck and documentation are excluded from this comparison.

Doubling source size is justified only if the new responsibilities become easier to identify and change. Here there are useful named owners:

| Responsibility | Owner at this checkpoint | Assessment |
|---|---|---|
| Synthetic operational scenarios/actions/storage | `ParkSimulator` | Still concentrated; pure evaluator extraction is worthwhile |
| Mapping, acceptance, receipt decisions and source quality | Connector catalog/runtime/store | Clearer than baseline; keep this boundary |
| Public asset/KPI/alert projection | `ParkReadModel`, `project_alerts` | One canonical entry point exists; cross-view versioning remains incomplete |
| Recorded snapshots and selected historical view | `ReplayStore`, replay API/lifespan adapter | Useful separation; pose association needs stronger identity |
| Native SDK access | Renderer owner loop | Correct single-owner design; no actual new native validation yet |
| HTTP-to-native requests | `CommandMailbox` | Bounded, cancellable, testable without native objects |
| Atomic image bytes and basic provenance | `FrameCache` | Good boundary; camera/projection/status are not yet in the same publication |
| Committed artifact integrity/staging | `release_artifact.py` | Stronger and honestly scoped; normal bytecode writes break reuse |
| Browser transport/views/interactions | `frontend/app.js` | Growing concentration: 826-line IIFE, plus compressed CSS |

The dependency direction is mostly understandable. There is no need for a broker fleet, microservice split, new UI framework or generic adapter plugin loader to regain control. The important next decomposition is about contracts and identities, not moving arbitrary lines into smaller files.

## Prior findings: what is actually closed?

| Prior finding | Current evidence | Disposition |
|---|---|---|
| Accepted values overwritten by simulator | Projection keeps source observations separate; existing ownership tests pass | Resolved for the declared synthetic source/owner contract |
| Canonical fault missing/contradictory alerts | `project_alerts` now derives incidents from canonical fields, labels model forecasts and emits explicit source/model conflict evidence; regression tests pass | Reviewed connector defect closed at CPU/API scope |
| Snapshot cursor skips concurrent accepted event | `ConnectorRuntime.source_snapshot()` holds one lock across values/health/cursor; deterministic concurrent regression test proves catch-up delivers the waiting event | Reviewed connector defect closed |
| Late valid events disappear | Independent bounded decision journal retains late valid payload/time/reason without advancing accepted cursor; HTTP and retention tests pass | Late-event retention gap closed within documented in-memory scope |
| Cached image appears freshly rendered | Atomic frame cache retains render time/identity; gateway preserves headers; UI distinguishes old frame/source age | Core old-frame problem improved; complete alignment remains open below |
| Exception prevents native cleanup | Failure loop removed; `finally` closes mailbox and attempts query/path/stage/renderer/client cleanup; failed renderer rejects new controls | Implementation improved; fake-SDK initialization test only, actual native destruction/restart pending |
| Unbounded or obsolete requests | Mailbox has deadline/cancellation/backpressure; tests cover expiry/failure; owner checks pick activity before selection | Improved; native in-flight edge cases require GPU acceptance |
| Deployment reads dirty worktree/overlays old source | Artifact reads committed blobs, verifies manifest and stages fresh directories; corruption/deletion/activation tests pass | Prior artifact defects closed; runtime cache side effect remains below |
| One shared camera/view | Explicit shared-session labeling and serialized write/view guards | Deliberate prototype constraint, not silently solved |
| Duplicate IDs/names/capabilities/configuration | Stable IDs still useful; separate registries, names, action eligibility and motion constants persist | Open focused refactor |

The journal stores accepted/duplicate/conflicting/late events that pass validation far enough to reach the store. It is not a durable broker and does not retain arbitrary malformed raw payloads. Cursors/counters still have runtime epochs. Those limits remain explicit.

## P1: simulator tick is not an accepted-state identity

**Locations:** `backend/replay.py:capture`, `renderer/service.py:render_loop` frame metadata, `backend/connectors/runtime.py:ingest_demo`, `frontend/app.js:frameMatchesView`.

Accepted ingestion changes canonical source values without advancing simulator tick or its timestamp. A renderer frame produced before ingestion and a canonical snapshot produced afterwards can therefore have the same tick/time while containing different operating state.

The replay capture accepts a presentation pose when renderer status is ready/live and its scene hash and source tick match the captured snapshot. It does not require the same accepted-source state. A deterministic application probe did the following:

```text
normal live state: tick 1
old renderer-status fixture: tick 1, coaster operational, coaster_phase 0.123
pause SCADA; ingest accepted coaster fault
new canonical state: tick 1, coaster fault
new replay record: has_recorded_motion=true, coaster_phase 0.123 from old status
```

This does not prove that a stopped ride cannot legitimately be at phase 0.123. It proves the application's advertised association between that captured pose and that accepted snapshot is unproven: only a reused tick was checked.

The browser's live `frameMatchesView()` only checks `viewMode === 'live'`; it does not compare accepted state identity. Historical mode correctly checks selected snapshot ID. Scene revision is sent by the renderer but is not parsed/compared by the browser's frame-metadata function.

**Fix:** define a canonical content/revision identity that changes when authoritative observations/model state change, even within a simulator tick. Carry it through displayed state, rendered frame/status and recorded-pose capture. Keep age/quality evaluation time separate from content identity so merely reading a snapshot does not create a different revision every millisecond. Include scene/config identity where presentation depends on it.

**Acceptance:** inject a new authoritative status while tick stays constant; reject pose association from the previous revision. In live mode clearly label image/data skew or use the matching state. In replay require record and compatible scene identity. Test equal-tick different-source-content cases; the existing no-pose-without-GPU test does not cover them.

## P1: camera annotations are not published with their displayed image

**Locations:** `renderer/service.py:status`, `render_loop`; `frontend/app.js:renderLabels`, `renderDependencyLines`, `streamFrames`.

JPEG bytes and basic metadata move together, but camera/projected asset positions live in the separately polled mutable renderer state. The browser positions labels using the latest `/status` while showing an independently fetched JPEG. During camera movement those can describe different viewpoints.

There is also a smaller race inside `/status`: it copies `state` under the renderer lock, releases it, then reads the frame cache. A frame can publish between those operations. A deterministic interleaving returned `frame=2` and the new render timestamp alongside frame 1's camera and projected coordinates.

**Fix:** publish the full image-specific camera/projection/source/view metadata as a single immutable frame record. Return a status snapshot atomically, and only overlay coordinates associated with the displayed frame, or explicitly gate their use until frame IDs agree. Do not identify an old image using a newer status response. Keep existing letterbox handling.

**Acceptance:** force publication between status reads; returned frame/camera/projections remain one generation. Delay JPEG and status independently during a camera drag; labels and logical dependency endpoints remain attached to the geometry. This requires a browser/native run in addition to CPU publication tests.

## P1: normal Python execution dirties a verified release

**Locations:** `scripts/release_artifact.py:activate`; `scripts/start.py`.

Activation correctly checks the staged tree's exact inventory. The launcher does not disable or redirect Python bytecode caches. Python consequently creates source-local `__pycache__` directories during normal imports, and the next activation/rollback check rejects that release.

Verified using the actual artifact code and exact commit:

```text
build -> stage -> activate 29c4091: success
python -c 'import backend.simulator' in the staged release
new source entry: backend/__pycache__
activate the same verified release: Staged file/layout set mismatch
```

The trigger is ordinary application execution, not an intentionally modified source file.

**Fix:** launch with `-B`/`PYTHONDONTWRITEBYTECODE`, or route caches into a declared shared runtime location via `PYTHONPYCACHEPREFIX`. Ensure documented ad hoc runtime commands follow the same rule. Keep artifact verification strict rather than ignoring arbitrary unexpected source entries.

**Acceptance:** import/start actual Python modules from a staged release, stop them, then reactivate/rollback successfully without deleting undeclared files by hand. Source edits must still be detected. An activation-only filesystem test is insufficient.

## P2: finish boundaries already identified; avoid adding another abstraction layer

1. **Static identity/capability duplication.** Operational registry, scene registry, Blender ID list, connector mapping tables, frontend action eligibility and renderer motion constants still require coordinated changes. Ride metadata says 65/100-second periods; renderer still uses 42 seconds and 0.16 radians/second. Introduce a small shared validated identity/configuration manifest and backend capability output; do not put live readings, geometry generation and transport logic into a universal schema object.
2. **Simulator and browser concentration.** `ParkSimulator` still combines SQLite orchestration, commands, ticking and pure evaluation. Extract the pure evaluator while preserving tested semantics. Split browser API/view state, viewport/frame publication and operational/source panels when changing those areas. Format CSS to make diffs reviewable. A framework rewrite is not required.
3. **Release provenance is not runtime provenance.** Artifact manifests accurately identify staged source. Existing runtime status does not report the full deployed commit/tree/manifest. Documentation correctly says source-pointer promotion does not restart processes. Preserve that distinction until a runtime identity helper is actually integrated and tested.
4. **HTTP connection lifetime.** Gateway and recorder create an `AsyncClient` for each request/capture. A lifespan-owned client would simplify cleanup and pool frequent frame/control requests. This is a bounded optimization, not a prerequisite for the current correctness fixes.
5. **Native cleanup proof.** The fake-SDK test fails during population and proves attach/detach/stage/renderer cleanup at that boundary. It never maps a real render buffer or allocates query paths. Protect mapping/unmapping with appropriate lifetime handling and validate failure after population, during query use, during frame access and at shutdown on the GPU.

These are reasons for targeted next commits, not reasons to throw away tested code or restart the asset pipeline.

## Evidence hygiene and remaining acceptance

`docs/progress.md` and `docs/validation.md` explicitly distinguish R1 GPU evidence from R2 local code, which is the right approach. Some lower sections still say “current implemented model,” “current” renders or provide broad delivery-checklist completions. Read in isolation those phrases can imply R2 verification. Label the gallery/checklist block **R1 / `930acd3`** directly and link a separate R2 pending checklist. Do not alter old validation JSON to imply a newer deployment.

The recorded-view and source-health UI is substantial. Logic/identifier checks establish selected branches and DOM references; they do not prove CSS placement, modal/pointer behavior, image decode timing, replay switching under polling, or native picks. Fresh browser acceptance must exercise those exact behaviors. A larger test count cannot substitute for the missing environment.

The next integrated checkpoint should require:

- A canonical revision contract proving same-tick source changes cannot be confused with an older frame/recorded pose.
- Image/camera/projection consistency under controlled publication and browser fetch delays.
- A real Python-import/start-stop lifecycle inside a staged release, followed by successful verified reactivation.
- A runtime identity response matching the staged manifest, alongside explicit R1 versus R2 evidence.
- Actual Horde OVRTX render, native picks, articulated cars/upright cabins, stale-source freeze, replay/return-live behavior and clean stop/restart.
- Regenerated and reopened R2 Blender artifact before marking its editable handoff current.

Keep the established milestone-based review cadence. The next review should examine these changes at their committed revision, not merely repeat this report or infer completion from planned fixes. No full rewrite is justified by the current evidence.
