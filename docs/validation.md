# Validation evidence — 15 October 2026

## Current development versus GPU baseline

The GPU/browser evidence below belongs to the original revision 1 application
(`930acd3`). New revision 2 assets, accepted-event connectors, replay and renderer
lifecycle changes have **not** yet passed a new GPU/browser deployment check.
Network/process restrictions currently prevent Horde access and Chromium here.

A clean candidate built from committed connector baseline `cf4d621` plus the
recorded-view/renderer/gateway changes passed **73 CPU/API tests**: 51 existing
backend/connector checks, 10 replay checks, 10 renderer-boundary checks and two
gateway checks. These include actual background recording during replay and
historical values reopened after an application restart. Native cleanup tests
use an explicit fake SDK at failure boundaries; they do not certify actual SDK
resource destruction. New asset checks are in `assets/scene_quality_validation.json`.

The independent [connector acceptance review](reviews/2026-10-15-connector-acceptance-review.md)
identified additional projection/snapshot issues at `cf4d621`. Its findings are
retained as that commit's review; follow-up fixes have their own checkpoint and
are not retroactively claimed by the 73-test candidate.

After the reviewed connector fixes and release work, the combined stable local
suite passed **98 CPU/API checks**. The operator UI separately passed **15 JavaScript
behavior checks** and **57 DOM identifier checks**. These newer local gates do not
replace the pending Chromium/native-GPU acceptance described above.

## Latest integrated local acceptance

Committed `7b27281` passed **149 CPU/API checks in 28.54 seconds**, plus **19
JavaScript logic checks** and **57 DOM references**. This includes the recurring
review fixes, external synthetic source ingestion, source ownership/staleness,
recorded-state restart/retention, same-tick accepted revision changes, concurrent
status publication, stale/missing/future pose rejection, and actual staged Python
import followed by release reactivation. The restricted sandbox test run uses a
temporary test-process heartbeat plugin; no production event-loop workaround is
installed. Native failure-boundary tests use explicit fixtures.

Current revision 2 USD validation independently checks 12 stable roots, 3,067
prims, 46 polygon meshes, 138 static connector declarations, canonical names/types,
material bindings, finite bounds, self-contained assets and deterministic inventory.
Motion checks cover 25 wheel angles, 401 coaster positions and 101 articulated-car
poses. See [current scene results](../assets/scene_validation.json) and
[exact USD/catalog fingerprints](../assets/scene_quality_validation.json).

## Original revision 1 GPU/browser acceptance

The actual application was run on an NVIDIA L40 (48 GB), driver 570.158.01,
Linux/Python 3.10, OVRTX 0.6.0.1791947691 and OVStage 0.3.0.1791986420.
This is application evidence, not a performance benchmark.

| Check | Result |
|---|---|
| Native GPU rendering | Actual 1280×720 OVRTX output displayed in browser; observed 12.5 render fps at the configured cap |
| Camera | Browser drag/orbit, zoom and asset focus passed |
| Native geometry picks | Food court plaza, hotel roof and power-hub solar panel resolved to three distinct correct asset records |
| Ride closure | Coaster phase remained exactly unchanged across samples while wheel angle advanced; coaster resumed after reset |
| Operator workflows | Closure → maintenance work order and water leak → repair passed |
| Overlays and source data | Projected labels, energy overlay, JSON source inspector and architecture view passed |
| Browser | No JavaScript page errors in live check; mobile view had no horizontal overflow |
| Backend | 19 tests passed on both local Python 3.12 and GPU-host Python 3.10 |
| Scenario comparison | Deterministic same-tick results; comparison cannot read/write SQLite or mutate live state |
| History | Bounded retention tested with more than 3,600 samples and simulator restart |
| Animation transforms | Upright cabins checked at 25 angles; right-handed coaster frames checked at 401 positions |
| OpenUSD | Scene identity, bounds and required geometry validated; 2,299 prims / 12 asset roots |
| Blender | Saved and reopened in 4.5.3 LTS: 2,239 objects, 2,200 meshes, 28 materials, zero unbound meshes |
| Project deck | Ten pages; regenerated text and rendered pixels matched the original; repeat source builds deterministic |

[Machine-readable browser results](images/browser-validation.json),
[revision 1 scene results](evidence/revision1-scene-validation.json), and
[Blender results](../assets/blender_validation.json).

## Actual application captures

These screenshots show the running GPU application, not conceptual renders.

- [Live operations console](images/operations-live.png)
- [OVRTX viewport](images/ovrtx-viewport.png)
- [Ride closure and maintenance](images/operations-ride-closure.png)
- [Scenario comparison](images/scenario-comparison.png)
- [Connected architecture](images/connected-architecture.png)
- [Mobile console](images/mobile-live.png)

## Limits of the evidence

The tests cover a single demonstration session and synthetic services. They do not
establish calibrated forecasts, ride dynamics, large-scale streaming performance,
production availability or real ERP/SCADA compatibility. The rides use presentation
animation. The GPU-verified revision 1 cars share a rigid transform; revision 2 has independently posed cars with local transform checks and pending GPU acceptance. Telemetry overlays are DOM
annotations, not physically simulated heatmaps. All viewers share camera, selection
and scenario state. JPEG frame delivery is deliberately simple; an expanded service
would need session management and a suitable low-latency streaming transport.
