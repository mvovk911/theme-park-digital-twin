# Development log

## 15 October 2026, 20:04 UTC — extended development goal

The owner requested continued holistic development over the next few hours,
covering assets, API connectors for every synthetic domain, and an independent
review against current digital-twin examples in public media.

Active workstreams:

- **Connector architecture:** explicit event contracts, stable mappings, units,
  validation, deduplication, freshness and accepted-event provenance for all ten
  sources. Demonstrate source failure and recovery without claiming real PLC or
  commercial ERP connectivity.
- **Assets:** more useful guest-scale landscape and queue detail; articulated
  coaster cars while preserving stable scene identities.
- **Operations experience:** coherent historical replay, visible source health and
  logical dependency context for incidents. Preserve live data while inspecting
  history.
- **Independent review:** [current-practice benchmark](reviews/2026-10-15-digital-twin-benchmark.md),
  followed by acceptance review of the implemented changes.

Baseline: public commit `930acd3`, validated OVStage/OVRTX application on one L40.
New work is only marked complete after integration checks and actual GPU/browser
captures. The current published gallery remains the last verified checkpoint
until the next release is recorded here.

## 15 October 2026, 20:09 UTC — architecture and milestone review

The owner requested an additional independent architecture review: assess whether
this is becoming an uncontrolled blob, whether targeted refactoring or component
rewrites are worthwhile, and whether a full restart has value. Repeat the review
at completed milestones and publish finished steps rather than leaving all
progress uncommitted.

The [external digital-twin benchmark](reviews/2026-10-15-digital-twin-benchmark.md)
is complete against baseline `930acd3`. Its priorities are accepted-event ingestion,
source trust, a visible incident/acknowledgement loop and coherent replay. The
separate architecture review is in progress. Connector and asset changes remain
work in progress until their implementation and checks are finished.

## 15 October 2026 — architecture review completed

The [architecture review](reviews/2026-10-15-architecture-review.md) recommends
retaining the working application and making bounded refactors. A full restart
has no demonstrated payoff. Highest priorities are explicit state ownership,
source/frame freshness, bounded renderer lifecycle and identifiable releases.
Duplicated asset/capability definitions should be consolidated as contracts settle.

[The review protocol](reviews/README.md) defines repeat checks at meaningful
integrated milestones. A new review must examine current evidence and previous
findings, rather than endorse a rewrite by default.

Documentation checkpoint `dd4affe` is committed locally. Network access to GitHub
and Horde is currently unavailable in this execution environment; publication
and new GPU verification remain pending. Locally cached Python dependencies have
been recovered so backend and pure runtime tests can continue offline.

## Revision 2 asset checkpoint — local checks passed

Procedural scene and articulation are ready: all 12 operational roots preserved,
3,067 prims, bound materials and finite bounds, no detected tree/structure
intersections, and three independently positioned coaster cars. Static scene
validation and motion checks (25 wheel angles, 401 train poses, 101 articulated
configurations) pass. Source and generated outputs are committed together.

The Blender file and checked-in GPU images remain revision 1. Worker connectivity
is unavailable, so revision 2 GPU/native-pick evidence and Blender re-import are
still pending. This checkpoint does not claim those gates passed.

## Ten-domain connector checkpoint — 51 local checks passed

The accepted-event boundary is implemented for all ten synthetic domains with 137
mapped fields. Modular adapters, catalog, validation, bounded event storage,
runtime and read-model projection now own separate responsibilities. Ingestion
validates source/asset identity, units, types, ranges and timestamps; duplicates,
conflicts, late events and expired cursors have explicit behavior. Freshness and
source status derive from accepted events. Synthetic producers can be paused or
offlined independently and resumed through the demo API.

Existing application APIs consume the accepted projection. A faulted ride is
excluded from open-ride and active-queue KPIs. Scenario comparison remains an
explicit synthetic-model calculation rather than a prediction from injected
measurements. The event journal is bounded in memory and its restart limitation
is documented; durable full-state recording is a separate workstream.

51 backend/connector checks passed locally. The restricted execution environment
requires a test-only event-loop heartbeat; no production scheduling workaround
was added. Remote deployment, GPU checks and publication remain pending network
access.

## Recorded-view and renderer-boundary checkpoint — 73 local checks passed

Full accepted operational snapshots now persist with scene/configuration hashes,
source timestamps, optional matching recorded presentation pose and bounded
retention. Replay keeps live production running, serves historical detail/history,
serializes view changes with write guards and resumes current state on return.
Recorded values survive restart without rerunning today's model rules.

The render process now has cancellable/deadlined commands, reachable native
cleanup on failure/stop, source-quality motion policy and atomic image/provenance
publication. JPEG timestamps/frame IDs survive cached delivery and the gateway.
Articulated car transforms are integrated into the native-owner code.

An isolated candidate consisting of committed `cf4d621` plus these exact changes
passed 73 CPU/API checks. This is not new GPU evidence: native resource destruction,
rendered replay, revision 2 visuals and actual picking remain pending worker access.
Concurrent source-acceptance follow-up work and frontend changes were excluded
from that candidate so the checkpoint's evidence is identifiable.

## Immutable release artifact checkpoint — 17 local boundary checks passed

Release packaging now reads exact committed Git blobs, records commit/tree and
per-file SHA256/size/mode in a manifest, and rejects dirty working bytes from the
artifact boundary. New source stages into a fresh release directory with declared
shared runtime/database/environment links. Removed files cannot survive through
an overlay, because staging never overlays an old source tree.

17 local boundary checks passed, including tampering, manifest/path/link rejection,
deleted files, retained shared data and explicit activation/rollback. Activation
only promotes a source pointer; it does not claim dependency compatibility,
process restart or GPU acceptance. The legacy worker deployment remains untouched.

## Connector acceptance fixes — 59 local checks passed

The independent review of `cf4d621` is preserved in
[its dated report](reviews/2026-10-15-connector-acceptance-review.md). Three concrete
findings now have targeted fixes: canonical alerts follow accepted values with
source/model conflict evidence; snapshot observations/health/cursor are returned
under one acceptance lock; late valid observations remain in a bounded decision
journal without replacing fresher projected values.

The accepted-event cursor and decision-journal cursor are separate documented
contracts. Unmapped model fields remain explicitly labeled as model-derived.
59 backend/connector checks pass. This fixes the reviewed boundary at code/API
level; new end-to-end GPU/browser evidence and external publication are still
pending the current environment restrictions.

## Operator experience checkpoint — local logic/API validation

The browser code now uses a consistent recorded-view API, exposes source health
and provenance, supports synthetic connector pause/offline/recovery, and draws
logical utility dependencies. Replay has a prominent read-only state, historical
source inspection and disabled mutation/comparison controls. Image freshness uses
original JPEG frame identity/time; stale source presentation and missing historical
poses are disclosed. Unmapped model values are distinguished from accepted
unknown values, and alerts display source/model evidence.

15 JavaScript behavior checks and 57 DOM identifier checks pass, plus syntax and
in-process API contract checks. The combined stable backend/replay/render/gateway/
release suite passes 98 CPU/API checks. Chromium and loopback listener startup are
blocked in this sandbox, so fresh visual layout, interactive browser and native
GPU acceptance remain unverified. Existing real GPU images were preserved and are
not relabeled as evidence for these changes.


## Recurring independent review and source provenance checkpoint

Review `699d33b` preserves the independent inspection of exact `29c4091`.
The reviewer ran all 98 CPU/API checks and found three additional boundary defects
rather than recommending a rewrite. The previous canonical-alert, atomic-cursor
and late-event fixes were confirmed at CPU scope. Native cleanup remains
unverified on the actual SDK.

Commit `55f4b33` adds once-at-startup source identity (Git/release manifest,
dirty disposition, actual scene SHA), exposed by backend health. It also fixes
release reactivation after ordinary Python imports: real cache directories are
explicitly transient, cache-name symlinks remain invalid, and both child services
start with bytecode writes disabled. A real subprocess import between activation
and reactivation is part of the 34 passing release/provenance checks.

The push retried at 20:47 UTC failed because github.com could not resolve.
These commits are preserved locally and are not represented as published.

## Accepted-state/image coherence checkpoint

Canonical snapshots now carry an accepted-state content identity; same-tick sensor
updates cannot borrow earlier recorded ride poses. Replay capture requires a
matching revision as well as scene/tick. Each JPEG carries its own immutable camera,
projection coordinates, dimensions and revision. Operator annotations fail closed
on missing/mismatched evidence instead of using newer status projections.
Versioned UI picking checks camera/state/view at the render owner; the documented
scope is current-geometry asset selection, not reconstruction of historical pixels.
Five focused CPU regressions include stale-pose rejection, matching-pose acceptance,
quality transitions, immutable frame context and changed pick context. 19 UI logic
checks and 57 DOM references pass. Native GPU and Chromium evidence remain pending.

## Pure model and standalone synthetic producers checkpoint

Definitions and scenario evaluation are now separate from SQLite persistence and
workflow orchestration. Existing simulator imports and API behavior remain
compatible; a pre/post extraction comparison matched 42 scenario combinations.
The standalone CLI can emit any of the ten source feeds without a database or
application server. Networking requires an explicit URL and a pre-paused synthetic
source. Bounded retries reuse event IDs; natural staleness and source ownership
remain enforced by the gateway. HTTP observations have distinct transport provenance.

25 producer checks plus the existing 59 backend/connector checks pass. Tests send
all ten source batches across all seven scenario profiles through real ASGI routes;
they do not claim a network listener, GPU execution, vendor connector or physical
control. [Usage and limits](synthetic-producers.md).

## Independent coherence closure audit

The follow-up reviewer preserved a second report for exact `cb11424`, confirmed
39 focused checks and reproduced an additional status/pose publication race.
The fix now reads status and frame metadata under the same publication lock and
publishes ride motion/status/quality with each immutable frame. Its deterministic
thread regression fails the reviewed baseline and passes the fix without claiming
native GPU execution. Motion capture additionally rejects stale/missing/future
render times and preserves the original frame/time/revision provenance.

The new [implemented architecture](implemented-architecture.md) documents actual
module ownership and the difference between model history, accepted observations,
recorded state and GPU frame evidence.

## Scene identity, source binding and inventory checkpoint

The generated USD now derives canonical names/types from the shared domain and
source IDs/138 metric declarations from the sole connector catalog. Physical signs
remain as explicit authored aliases. Static declarations carry no current sensor
values or claim of connection. USD assembly kinds and a deterministic inventory
make the model easier to inspect and extend without duplicating operational truth.

All 12 identity roots, bound materials, finite bounds, self-contained geometry,
138 mapping declarations and recomputed inventory pass validation. Animation checks
cover 25 wheel angles, 401 coaster frames and 101 articulated-car poses. Repeated
generation is byte-identical. Geometry remains 3,067 prims/46 meshes; added metadata
brings the binary USD to 459 KiB. Blender and actual GPU captures remain revision 1.
[Authoring contract](scene-authoring.md).


## Integrated local checkpoint `7b27281`

149 CPU/API checks passed in 28.54 seconds, plus 19 JavaScript behavior checks,
57 DOM identifiers, current USD/catalog/inventory validation and articulated motion
checks. Status/pose publication fix `e477a12` is included. The historical closure
report remains an exact snapshot of its reviewed earlier baseline, not a false
claim that it independently approved later code. Public origin remains `930acd3`;
GitHub/Horde access, new native/browser checks and the Blender refresh are pending.

## Published revision 2 and actual native acceptance

External access was restored. All checkpoints through `19cee1e` were published to
public `main`, preserving their exact commit/tree identities through GitHub's API
when ordinary Git transport returned HTTP 503. No branch was force-updated.

Revision 2 USD was imported, saved and reopened in Blender 4.5.3 LTS. The editable
handoff has 2,997 objects, 2,954 meshes, 33 materials, all 12 asset identities and
zero unbound meshes. Material and articulated-car transforms match the USD;
`73bb9bd` records the verified handoff and derived evidence checks.

An immutable `154e746` deployment rendered on the L40. Real browser checks exposed
successful native picks discarded on a later telemetry tick and intermittent
annotations while image/API revisions differed. `3336f6d` fixes result handling;
`89b0e27` and `2e2b16b` retain bounded immutable state for exact-image annotations.
The dashboard/inspector remains current and annotation capture time is explicit.

Actual browser suites on verified release `2e2b16b` pass native picks, orbit/zoom/
focus, source failures/recovery, replay isolation, continued recording, incident
workflows and ride freeze/resume. Across 100 cadence samples, annotations were
visible 92% of the time versus 63% before the fix, with zero revision mismatches.
Native picks correctly rejected a changed context before succeeding on retry.
Desktop/mobile checks observed no page errors or horizontal overflow. Four new
OVRTX viewpoints include exact JPEG headers and release/scene provenance.

A separate real SDK lifecycle probe on `154e746` rendered 20 frames and returned
phase `stopped`, zero outstanding commands and no cleanup errors. It exercises
actual native calls, not exhaustive leak or failure certification.

## Independent review follow-ups: acquisition and durable actions

The recurring reviewer found a replay guard also stopped independent HTTP source
producers. `2c763d2` distinguishes acquisition from operator commands: all ten
sources continue ingesting into live state/new recordings while the selected
historical payload stays immutable; actions/source-mode changes remain locked.
20 replay/producer checks pass independently. `35b4f90` bounds explicit Horde
busy-rejection retries and documents recovery without retrying ambiguous appends.

`19cee1e` adds optional durable action request IDs with one SQLite transaction for
receipt, effects, work orders, audit, telemetry and settings. Exact retries return
the original acknowledgement; conflicts return 409; failures restore database and
memory. Concurrent/restart/lost-response cases pass. The reviewer independently
approved the bounded change. Full integrated CPU/API suite: **184 passed**, plus
**28 JavaScript logic checks / 58 DOM references**. Browser/GPU proof is bound to
`2e2b16b`; final HTTP/restart acceptance on `19cee1e` is recorded separately.

## Final deployed integration: `19cee1e`

Fresh actual GPU browser smoke passed on the final backend release. A second real
native lifecycle probe rendered 20 frames and stopped without reported cleanup
errors; the serving renderer was then restarted. Ten independently identified
producer instances submitted 20 HTTP batches / 276 accepted events during replay.
22 newer recordings appeared while selected historical assets, KPIs and revision
remained unchanged. Six concurrent action retries and a conflicting reuse produced
no extra effects. After an actual backend stop/restart, the same request returned
the exact original receipt. Final health reports both services on verified
`19cee1e`, renderer ready, live view and normal scenario. The synthetic cleanup
reset is audited and preserves prior receipts. [Evidence](images/revision2/release19/).

The main progress/validation pages now show current evidence; historical review
and log entries remain dated snapshots. The application stays on its authenticated
GPU deployment for review; source changes after `19cee1e` are acceptance tooling,
documents and captured media, not a silently changed running release.
