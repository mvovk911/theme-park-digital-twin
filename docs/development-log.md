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
