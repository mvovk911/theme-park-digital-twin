# Architecture review: evolve, refactor, or start again?

Review date: 2026-10-15 UTC. Reviewer: independent architecture-review agent. Baseline: `930acd3`. Scope: application, procedural assets, API boundaries, renderer lifecycle, deployment and evidence. This is an implementation review; the [digital-twin benchmark](2026-10-15-digital-twin-benchmark.md) separately evaluates product direction against public examples.

## Decision

**Keep the project and refactor selected boundaries while developing it. A complete restart has no demonstrated payoff today.** The baseline is a small, comprehensible prototype: 2,212 application/model/script lines across 17 files, plus 458 backend/browser test lines across two files (counted from `930acd3`). The handwritten system is not the apparent size of its generated USD, Blender files, images or documentation. Those artifacts should be assessed separately from source complexity.

The separation into a Python operational service, a GPU-owning render process, NumPy-only motion helpers, a procedural asset generator and a browser interface is useful. The native rendering/picking work and material-repaired Blender handoff represent working knowledge worth preserving. A rewrite would have to rediscover those details and revalidate them on a GPU.

There are early concentration and truth-management problems. Address them before adding replay, external writers or more viewers. The primary risk is divergent representations of the same park: source simulation, operational state, database seed, scene metadata, UI annotations and rendered motion. Adding directories alone would not resolve that risk.

**Value in doing something a second time:** yes, for bounded components after their contracts have been learned. Rebuild the renderer lifecycle around an explicit owner, extract pure evaluation from persistence, and make connector mappings authoritative. Do these as replacement implementations behind existing interfaces, with baseline evidence retained. Redrawing the entire project around a new framework would presently deliver less value than those changes.

## Evidence and limits

- Reviewed `930acd3` and the live worktree. `backend/connectors/` and edits to `modeling/animate.py` / `modeling/generate_park.py` were **uncommitted work in progress** during review. They are promising changes, not shipped functionality. Re-review after integration.
- Inspected backend API/simulator, gateway, renderer, frontend, scene generator/importer, launch/deploy scripts, tests and checked-in evidence.
- The baseline has existing GPU/browser captures and validation JSON. Their presence supports previous demonstration work; it does not prove the current changing worktree is deployed or that new connector behavior works.
- Attempted `.venv/bin/python -m pytest -q tests/test_backend.py` in this review environment. It stopped with `No module named pytest`; no fresh passing test run is claimed here. Dependencies can be installed and the existing suite rerun by the integrator.
- No application code, GPU session, database or published branch was changed by this review. File/function references below describe the reviewed snapshot; names are more durable than line numbers while agents are editing.

## Ranked findings

### P1. Define operational truth before introducing independently writable connectors

**Evidence.** `backend/simulator.py:102` (`ParkSimulator`) owns a SQLite connection, seeded base assets, the scenario, mitigations, tick and current state. `act()` performs validation, creates work orders, changes mitigation state, records audit and advances time. `_evaluate()` derives all asset values, alerts, system connectivity and KPIs. `advance()` reads work orders, evaluates state, appends telemetry, prunes history, persists settings and commits. The WIP connector catalog imports `SYSTEM_DEFS` and `registry()` from this simulator; its synthetic adapters sample simulator state.

**Consequence.** Today this is a coherent synthetic simulator. If ingestion overwrites the same output that the next simulator tick regenerates, accepted measurements can disappear or compete with scenario estimates. A connector facade that only re-exports that output would not demonstrate independent source integration. That distinction must remain explicit.

**Refactor.** Separate pure scenario evaluation from orchestration and storage. Keep simulation output as source samples; let a connector pipeline validate/retain those observations; let one projection combine authoritative observations, derived values and scenario state. Distinguish `observed` / `estimated` / `derived` / `scenario` origin in addition to the synthetic flag. Each asset/metric needs one declared owner, with alternatives retained as evidence rather than silently overwriting it. This can remain one process and SQLite.

**Acceptance.** A valid independently posted event changes the declared projection and survives unrelated ticks according to its ownership/freshness rules. A duplicate is idempotent; a late event is retained without replacing fresher truth. Scenario comparison performs no live-state or database mutation. Pausing a producer stales its own source while other sources advance. Existing action, persistence and comparison behavior remains tested.

### P1. Synchronize source age, rendered state and displayed frame identity

**Evidence.** `renderer/service.py:192–199` polls `/api/state` and only toggles `api_connected` after failure; the previous `assets` dictionary remains. Motion at lines 219–224 continues using those statuses. Missing asset status also passes the `not in {'closed','fault'}` test. `/frame.jpg` returns the cached JPEG whenever any frame has been produced; failure marks state unavailable but does not invalidate that JPEG. `frontend/app.js:388` (`streamFrames`) stamps each successful image download with the current browser receipt time. Operational polling, renderer-status polling and JPEG polling run separately.

**Consequence.** A last known operational state can look current, a cached frame can look newly rendered, and annotations can describe another operational tick. This matters more than photorealism for an operational twin. It is a consistency limitation of a prototype, not a claim that a physical ride should be automatically controlled.

**Refactor.** Attach frame ID, render UTC/monotonic age, operational snapshot/tick and scene revision to each published image and status. Preserve the last image when useful, but label it as last known after failure. Define an explicit unknown/stale presentation-motion policy and expose that mode. Keep current operational data separate from any replay cursor.

**Acceptance.** Disconnect backend access and verify source/snapshot age becomes stale; the viewport does not claim current operational alignment. Force a render failure and verify repeated downloads of the cached image retain its original frame identity/time. An incident capture identifies which operational snapshot drove its status/motion and overlays. Camera movement cannot accidentally relabel an old image as a new frame.

### P1. Make renderer lifetime and command completion bounded

**Evidence.** The renderer correctly confines SDK calls to `render_loop()` and HTTP handlers submit to a bounded queue. However, `render_loop()` runs indefinitely; its exception handler loops forever at `renderer/service.py:275–279`, preventing normal execution of the `finally` releases beneath it. The control endpoint accepts work without checking failed state. Picks wait 15 seconds but have no cancellation/deadline marker; a queued command can execute after its request timed out. Readiness and other state keys are also written outside the lock used by status reads.

**Consequence.** Failure leaves a process alive for diagnostics but unable to recover or drain accepted work. Camera/pick retries can apply obsolete intent. Multiple HTTP threads and shutdown become difficult to reason about even though native SDK ownership itself is sound.

**Refactor.** Keep one native owner. Extract a runtime object with explicit initializing/running/stopping/failed states, stop event, a synchronized published status snapshot, and command IDs/deadlines. Reject commands when unavailable, coalesce transient camera input, complete or fail pending commands on shutdown, and release SDK resources in a reachable `finally`. A diagnostics server may stay alive independently if desired. No need to create multiple native render threads.

**Acceptance.** Initialization failure, runtime exception, normal stop and full queue each produce bounded responses and predictable terminal state. Expired picks never change selection later. Pending callers are completed on failure. A GPU smoke verifies real resource destruction/restart, native picks, camera controls and stopped/resumed motion; CPU tests alone cannot certify SDK lifetime.

### P1. Publish and deploy an identifiable release, rather than a mixture of tracked working files

**Evidence.** `scripts/deploy_horde.py:16–23` lists tracked paths but reads bytes from the current worktree, so a tracked dirty file is deployed despite the docstring's instruction to commit first. It extracts into the existing live directory and does not remove files deleted from the new revision. There is no committed-source/asset hash manifest or atomic release activation. `scripts/start.py:15–23` checks that a recorded live process has a working directory containing the project path; that is weaker than the command/role check used by `scripts/stop.py`.

**Consequence.** Repository commit, running code and gallery can diverge. Removed modules survive remote deployments. A reused PID in the same project directory can make startup skip a missing service. An interrupted archive upload/extraction leaves an uncertain release.

**Refactor.** Package a specific commit's blobs and generated-asset hashes, or refuse a dirty tree unless an explicitly labeled development build is requested. Upload to a clean release directory, verify hashes, install/check dependencies and activate a complete release; keep SQLite/runtime paths outside replaceable source. Retain one prior release for rollback. Share role-aware process identity logic between start/stop. A manifest and staged directory are sufficient; Kubernetes is unnecessary here.

**Acceptance.** Deployed status reports commit plus asset/schema versions, matching the evidence capture. A removed file is absent after upgrade. Incomplete upload never becomes active. Restart preserves operational data. Launch detects wrong-role/reused PIDs and occupied ports without declaring success. Rollback restores the previous source/asset revision.

### P2. Consolidate stable identity and capability contracts; avoid a new all-knowing schema module

**Evidence.** `backend/simulator.py:35` defines identities/names/types/paths and `SYSTEM_DEFS` defines domain membership. `modeling/generate_park.py:138` builds a separate asset registry with independent names/categories/system labels. `modeling/import_blender.py:62` repeats all 12 IDs. `frontend/app.js:97` (`availableActions`) repeats restrictions implemented by `ParkSimulator.act()`. Backend system field selections are repeated in `backend/app.py:83` and the WIP catalog's `DOMAIN_FIELDS`/`LEGACY_FIELDS`. Baseline ride-path period metadata and the scene documentation specify 65/100-second periods; renderer motion currently hardcodes 42 seconds and 0.16 radians/second.

**Consequence.** Adding an asset or changing eligibility requires synchronized edits. Geometry labels, source ownership, UI actions and movement can disagree without a syntax error. Names/categories are not all required to match: a spatial category and an operational type may intentionally differ, but their relationship should be explicit.

**Refactor.** Establish a small versioned park identity manifest: canonical ID, display name, USD root, semantic type and relevant domain mappings. Keep geometry parameters/materials and live readings in their own modules. Have the backend return available actions and restrictions, keeping server validation authoritative. Generate or validate transport contracts, and make renderer motion consume declared ride configuration.

**Acceptance.** The set of scene IDs equals operational IDs; each referenced USD root exists and carries the ID. All dependencies/domain mappings reference known IDs; no authoritative metric has two owners. An added asset requires no frontend ID list edit. UI capability and backend validation agree. Motion periods/configuration are verified against the declared contract.

### P2. Clarify editable asset ownership and extract the generator incrementally

**Evidence.** `modeling/generate_park.py` creates a stage and writes assets at module top level. Geometry helpers use global stage/material/name-counter/registry state. Generated files and editable `park.blend` coexist. The documented Blender workflow imports USD and repairs materials using a generated manifest; it does not provide a round trip from hand edits to the procedural generator. The WIP articulated train changes geometry/motion contracts together, which will require renderer query changes and regenerated assets.

**Consequence.** Re-importing the generator is not a harmless library operation. Manual Blender work can be overwritten by regeneration or fail to reach the runtime USD. A changed hierarchy can leave render animation paths invalid even when scene generation succeeds.

**Refactor.** Add a `main()`/CLI and explicit scene-builder context, then extract ride, utility, landscape and building assembly functions when they change. State whether `.blend` is a downstream modeling handoff or a maintained authoring source. For manual contributions, define an authored USD layer/payload and ownership boundary, rather than attempting arbitrary bidirectional synchronization. Stage generated outputs in a temporary directory before replacing the validated asset set.

**Acceptance.** Importing a builder module performs no writes. Rebuild produces a self-consistent bundle with scene/config hashes. All animation query paths exist. A documented manual edit survives its supported rebuild path and reaches OVRTX. Regeneration never silently overwrites a declared authored layer. Scene validation checks actual bounds/identity/materials, not just summary counts.

### P2. Strengthen boundary tests and reproducibility before increasing breadth

**Evidence.** `tests/test_backend.py` has useful integration checks for scenario effects, persistent audit/history and read-only same-tick comparison. It does not inspect the real USD/asset registry to prove cross-component identity. `tests/browser_smoke.py` exercises actual GPU picks, camera, closure/resume and UI behavior, but couples many checks and mutates the shared demo. Dependencies are pinned for the SDK/backend; `numpy`, Pillow and modeling `usd-core` are ranges/unpinned, and Playwright installation is a separate instruction. Checked-in validation JSON has SDK versions/time but not a uniform source commit/asset hash envelope.

**Consequence.** Happy-path behavior has meaningful evidence, but schema drift, failed sources, invalid lifecycle transitions and deployment mismatch can escape it. A future bulk refactor would be risky without contract checks. Fresh installation results can vary.

**Refactor.** Add a small CPU contract suite, explicit modeling/dev requirements or resolved environment record, and an isolated operational test database. Keep a targeted GPU acceptance lane with unambiguous revision metadata. Split browser workflows so a later failure does not hide earlier evidence. Avoid tests that merely restate implementation details.

**Acceptance.** A clean environment can execute documented backend/model checks. Tests catch missing scene IDs, invalid/late/duplicate events, unknown units, source staleness, command expiry and immutable comparison/replay. GPU evidence proves real render/pick behavior for the deployed revision. Test runs preserve reviewer state or clearly announce/use a dedicated demo instance.

### P3. Improve reviewability of browser code and styles when their features change

**Evidence.** `frontend/app.js` is a 515-line IIFE containing transport, operational view rendering, modal composition, frame streaming, annotations and camera interaction. `styles.css` uses 13 extremely long lines; line count understates its size. `main.py` opens a new `httpx.AsyncClient` for every renderer proxy request.

**Consequence.** Changes are harder to isolate/diff, and frequent JPEG proxying misses connection pooling. This is maintenance/performance debt, not evidence that a frontend framework rewrite is necessary.

**Refactor.** Format CSS without visual changes; extract a few browser ES modules for API/store, viewport and operational panels as those areas evolve. Share a lifespan-managed HTTP client in the gateway. Preserve the current no-build browser deployment unless a measured need justifies introducing a toolchain.

**Acceptance.** Formatting has no visual regression; existing GPU/browser smoke passes. Transport and viewport can be changed independently. Pollers remain single-flight and abort/stop deliberately. Pooling is closed during shutdown. No unrequested framework migration is needed.

## What to preserve

- Separate native GPU process and loopback gateway. SDK import isolation from `pxr` modeling is intentional and useful.
- Single native thread/owner and ordinal-based transform batches. Preserve this invariant through lifecycle refactoring.
- NumPy-only transform helpers and their upright-cabin/right-handed-frame checks. They are a useful boundary for articulated train work.
- Stable USD operational roots, nested-pick-to-asset mapping, self-contained materials, generated registry and material manifest.
- Deterministic same-tick scenario evaluation and comparison isolation. Make the evaluator easier to reuse, rather than changing semantics accidentally.
- SQLite, bounded telemetry retention, persistent work orders/audit and explicit synthetic labels. The prototype's scale does not justify a broker/database fleet by itself.
- Actual GPU/browser evidence and honest limitations. Keep old captures attached to their old revision when publishing new evidence.

## Small refactor, component replacement, or full rebuild?

| Choice | When it pays | Migration risk | Decision now |
|---|---|---|---|
| Small refactors | Shared identity/capability contract; pure evaluator extraction; manifest; CSS formatting; pooled proxy client | Low if API shape and acceptance tests remain stable | Start at the next integrated milestone |
| Renderer lifecycle replacement | Stop/restart, commands, failures and replay need controlled ownership | Medium: native resources, ordinals and query lifetime need GPU validation | Worth doing behind current HTTP endpoints |
| Simulator/projection replacement | Independent sources and historical snapshots need distinct ownership | Medium: persistence semantics and derived KPIs can change | Introduce explicit boundaries now; migrate one domain end to end |
| Asset generator reorganization | New zones/rides/manual contributions make one script difficult to change | Low–medium; path/material/animation contracts are the risk | Extract by changed subsystem; keep generated identity stable |
| Whole browser rewrite | Measured state/interaction complexity exceeds small module boundaries | Medium–high: visual, picking and input regressions | Not justified by current evidence |
| Entire project restart | A demonstrated non-negotiable requirement cannot fit existing boundaries, or a measured replacement prototype is materially simpler and passes the same full acceptance suite | High: reconnect all domains, assets, SDK behavior and evidence | Not justified today |

A full restart should require a written decision naming the failing requirement, evidence that incremental change costs more, a bounded replacement experiment, migration/persistence plan and a proven end-to-end slice. Code aesthetics or file length alone are insufficient. Compare equal behavior: a tiny replacement without native picks, persistent audit or real rendering is not evidence of lower complexity.

Suggested order: first finish the current connector/asset milestone, commit it and record deployed evidence. Then isolate truth/contracts and lifecycle/deploy identity, each in a separate reviewable commit. Only after these are stable add replay or multi-viewer/session behavior. Estimates depend on SDK behavior; do not promise a whole rewrite within a few hours.

## Lightweight recurring architecture review

Run this review **after each integrated milestone**, after any new source/transport or state owner, and before replay, multi-user operation or a new deployment model. During an extended build, one checkpoint every 60–90 minutes is enough if a meaningful milestone has completed; do not interrupt agents merely because a timer elapsed.

1. Record baseline and candidate commits, working-tree status, deployed build ID, schema/scene versions and the exact changed behavior. Review uncommitted work as WIP.
2. Trace one story through all boundaries: source event → validation/mapping → projection/storage → API → overlay/motion/frame → action acknowledgement → audit/history. Name the sole owner at every transition.
3. Check the seven architectural invariants below and compare known open findings. Look for newly duplicated truth or dependencies in both directions.
4. Run the CPU contract/behavior checks, then targeted GPU acceptance for any changed native, hierarchy, motion or interaction boundary. Record limitations and failures, not only passes.
5. Review one fixed overview and three detail captures at the deployed revision; ensure visual improvements retain selection and data identity. Review API/error evidence alongside images.
6. Publish a short dated delta review: resolved findings, new findings with file/function evidence, next three actions, and keep/refactor/replace decision. Commit completed code/assets/evidence together in logical milestones; update progress with that commit, UTC time and remaining work.

### Architectural invariants

- **Identity:** every operational ID and USD root resolve consistently; mappings/dependencies reference known objects.
- **Truth:** one authoritative writer per metric; raw receipts, projections, derived/scenario values and histories remain distinct.
- **Time:** operational snapshots and GPU frames expose identity/age; replay never silently mixes live state or writes live actions.
- **Ownership:** only one thread owns native SDK objects; resource lifetime and command termination are explicit.
- **Reproduction:** a documented clean build/deploy identifies source, dependencies and generated assets; persisted runtime data is separate.
- **Failure:** source loss, malformed/late data, renderer failure and shutdown give bounded, honest behavior.
- **Evidence:** progress links to the actual deployed revision and verifiable checks; proposed/native-protocol/real-source capabilities are not conflated.

If two successive milestones must patch the same boundary in several unrelated modules, or a new feature cannot be tested without starting every subsystem, schedule a focused refactor. If the same issue merely moves to newly named modules, the refactor has not earned its cost. A recurring reviewer should be independent of the implementation author and should not silently fix the application while reviewing it.
