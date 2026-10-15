# Project progress and review gallery

**Snapshot: 15 October 2026. Working GPU proof of concept.**

This page is the review entry point. It tracks the [original project request](project-prompt.md),
links editable deliverables, and shows actual renders from the running application.
The concept deck is a design proposal; the captures below are implementation evidence.

## Active development and independent reviews

A further development goal began at 20:04 UTC (22:04 CEST) on 15 October.
The [independent digital-twin benchmark](reviews/2026-10-15-digital-twin-benchmark.md)
is complete and evaluates the published baseline against current examples.
The [independent architecture review](reviews/2026-10-15-architecture-review.md)
recommends keeping the project and refactoring state ownership, renderer lifecycle,
freshness and release boundaries. It finds no demonstrated payoff from a full
restart. [Recurring review protocol](reviews/README.md). Reviews will be repeated
after integrated milestones. [Development log](development-log.md).

Current work in progress: ten-domain connector ingestion and provenance,
improved park landscaping and articulated coaster cars, then coherent historical
replay and operator source-health views. These are not marked delivered by this
checkpoint; the gallery below remains evidence of the last verified application.

## Revision 2 asset checkpoint — locally validated

The new procedural scene retains all 12 asset identities and adds landscaping,
shaded queues, accessible deck details, utility hardware and independently posed
coaster cars. It has 3,067 prims and a 433 KiB binary USD. Static scene, material,
bounds and articulated-motion checks pass; [revision 2 evidence](../assets/scene_quality_validation.json).

**Deployment status:** revision 2 has not yet been rendered on the Horde GPU.
The Blender handoff and the images below still show revision 1 and are labeled
accordingly. New GPU captures and Blender regeneration await worker connectivity.

## Connector checkpoint — locally tested

All ten synthetic domains now pass through typed mappings, accepted-event
validation and a canonical read model. Source pause/offline controls expose actual
freshness behavior; duplicate, conflict and out-of-order semantics are tested.
[Connector contracts and limits](connectors.md). Backend/connector suite: 51 local
checks passed. Deployment and publication of this checkpoint are pending network
access; existing GPU screenshots do not validate these new paths.

## Delivery checklist

| Requested outcome | Status | Review evidence |
|---|---|---|
| Explore the API ecosystem and operational value | Complete for concept stage | [Integration roadmap](integration-roadmap.md), [research sources](deck-source/sources.md) |
| Illustrated project slide deck | Complete | [Ten-page PDF](project-concept.pdf), [editable deck source](deck-source/) |
| Provision a Horde GPU and use actual OVStage/OVRTX | Implemented and run on L40 | [Validation record](validation.md), SDK versions in [capture manifest](images/render-captures.json) |
| Park with fence, trees, water and rides | Complete for POC | [OpenUSD scene](../assets/park.usdc), [editable Blender model](../assets/park.blend), renders below |
| Synthetic Python systems and database | Implemented | [Backend contract](backend.md), 12 assets, 10 source feeds, 19 passing tests |
| Click geometry to identify an asset | Verified | Three distinct native picks in [browser results](images/browser-validation.json) |
| Interactive operations application | Verified | Camera controls, live telemetry, asset inspection, scenario comparison and audited actions |
| Ride state affects animation | Verified | Closed coaster pauses; wheel continues; reset resumes coaster |
| Public source, assets, prompts and progress | Included in this repository | [Prompt](project-prompt.md), [asset index](../assets/README.md), [README](../README.md) |

## Actual RTX renders

Four views of the current implemented model, captured through the running OVRTX
service. These are different viewpoints of the same milestone, not invented
historical stages. [Capture metadata](images/render-captures.json) records UTC time,
renderer versions, camera and frame number.

### Whole park

![Actual OVRTX park overview](images/render-overview.jpg)

### Ferris wheel and lake

![Actual OVRTX Ferris wheel render](images/render-wheel.jpg)

### Coaster and queue area

![Actual OVRTX coaster render](images/render-coaster.jpg)

### Utility infrastructure

![Actual OVRTX utility render](images/render-utilities.jpg)

## Application progress

### Live operations and connected asset data

![Running operations application](images/operations-live.png)

### Ride closure and response workflow

![Ride closure in the running application](images/operations-ride-closure.png)

### Compare a scenario before applying it

![Read-only scenario comparison](images/scenario-comparison.png)

More captures: [connected architecture](images/connected-architecture.png),
[mobile view](images/mobile-live.png), [clean viewport](images/ovrtx-viewport.png).

## What remains beyond this POC

- [ ] Select a real park pilot, decision owner and baseline success measurements.
- [ ] Connect authorized read-only data from one ride/queue source and one utility system.
- [ ] Replace synthetic IDs with governed asset mappings; validate timestamps, units and quality.
- [ ] Add real acknowledgements and permissions before any external operational writeback.
- [ ] Calibrate queue/crowd/resource models and evaluate forecasts against held-out days.
- [ ] Add replay and separate scenario branches using recorded observations.
- [ ] Add per-user camera/session isolation and production streaming, authentication and monitoring.
- [ ] Improve geometry, terrain and multi-car coaster motion using measured engineering inputs.
- [ ] Add an optional AI assistant only once source provenance and action permissions are defined.

The prototype currently uses synthetic HTTP feeds, heuristic scenarios and one
shared GPU session. It does not yet connect commercial ERP/SCADA, control physical
rides, predict real crowd behavior, or demonstrate financial savings. See the
[validation limits](validation.md#limits-of-the-evidence).

## How to control the next iteration

1. Review the PDF and the four model renders for scope and appearance.
2. Follow the [five-minute walkthrough](demo-walkthrough.md) in the running demo.
3. Compare behavior with the checklist above and record desired changes as GitHub
   issues, referencing an asset ID, scenario and screenshot where possible.
4. Choose one pilot direction: operations response, utilities/maintenance, or
   planning/guest experience. The [roadmap](integration-roadmap.md) gives measurable
   starting criteria for each.

For future snapshots, rerun `scripts/capture_progress.py` against the running GPU
service, update this page's date/checklist, and commit the captures with the code
change. Git history preserves earlier versions of the gallery.
