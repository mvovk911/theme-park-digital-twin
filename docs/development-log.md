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
