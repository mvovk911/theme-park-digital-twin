# Validation evidence — 15 October 2026

## Revision 2: actual application and asset evidence

Release `2e2b16b` ran from a verified immutable manifest on NVIDIA L40 (48 GB),
driver 570.158.01, Linux/Python 3.10, OVRTX 0.6.0.1791947691 and
OVStage 0.3.0.1791986420. [Browser evidence](images/revision2/final/browser-validation.json)
and [extended evidence](images/revision2/final/extended/extended-browser-validation.json)
include the exact commit, source identity, scene SHA, frame and timestamps.

| Actual runtime check | Result |
|---|---|
| Native geometry selection | Food court, hotel and power hub resolved to correct records; stale context returned 409 before each successful retry |
| Camera and scene | Orbit, zoom, focus and 1280×720 OVRTX image delivery passed; observed 12.5 fps at the configured render cap |
| Ride state | Closed coaster froze, wheel continued, reset resumed coaster |
| Incident workflows | Maintenance dispatch and simulated leak repair passed |
| Source quality | Pause → stale → offline → recovery passed |
| Historical view | Actions rejected with 409, live recording continued, no live-source fetches for historical inspection |
| Image annotations | 92/100 live samples visible versus 63/100 earlier; zero image/state revision mismatches |
| Browser layout | No page errors or desktop/mobile horizontal overflow observed |
| Native lifecycle | Real SDK probes at `154e746` and final `19cee1e`: 20 frames each, final stopped, no cleanup errors or outstanding commands |

[Exact JPEG capture manifests](images/revision2/final/gallery/render-captures.json)
record camera/source headers from the image response itself. Four viewpoints and
operator captures are displayed in the [progress gallery](progress.md).

Revision 2 USD has 12 canonical asset roots, 3,067 prims, 46 polygon meshes and 138
static connector declarations. Checks cover names/types, material bindings, finite
bounds, self-contained assets and deterministic inventory. Motion checks cover 25
wheel angles, 401 coaster frames and 101 articulated-car poses. See [scene checks](../assets/scene_validation.json)
and [quality fingerprints](../assets/scene_quality_validation.json).

Blender 4.5.3 LTS imported the current USD, saved `assets/park.blend` and reopened
it: **2,997 objects, 2,954 meshes, 33 materials, zero unbound meshes**. All 12 asset
IDs, material bindings/parameters and articulated-car transforms were checked.
The [handoff report](../assets/blender_validation.json) records USD and Blender
SHA256 values; ordinary USD validation only checks that evidence's fingerprints,
not a fresh Blender reopen.

## CPU/API acceptance and later API changes

At `19cee1e`, **184 CPU/API checks pass**, including receipt concurrency, restart,
lost-response and transaction rollback; all ten independent sources publishing
across replay; immutable retained revisions; pose/frame races and release integrity.
The reviewer independently reran the same suite in a clean archive. Tests use the
normal environment; no heartbeat workaround is needed for this run. The UI has
**28 JavaScript behavior checks and 58 DOM references**.

`2c763d2` fixes independent source ingestion during replay. `19cee1e` adds durable
action request IDs. Their CPU evidence is separate from the earlier `2e2b16b`
GPU/browser run. [Action contract](action-contract.md), [replay contract](replay.md),
and [independent maintainability review](reviews/2026-10-15-revision2-maintainability-review.md).

## Final deployed API/restart acceptance: `19cee1e`

The final committed application was staged and started on the same L40 with a
verified source manifest and unchanged revision 2 scene. A new [actual browser smoke
run](images/revision2/release19/browser/browser-validation.json) passed existing
camera, picks, motion and operator actions after the backend transaction change.
A separate [native lifecycle probe](images/revision2/release19/native-lifecycle-validation.json)
rendered 20 frames and completed actual SDK cleanup without reported errors.

The [actual HTTP workflow check](images/revision2/release19/workflow-initial.json)
used ten independent producer instances with unique sessions and concurrent HTTP
threads. It accepted **276 events in 20 batches**, recorded **22 new snapshots**
(including background recording), and preserved the selected historical assets,
KPIs and revision. Six concurrent action retries returned the same acknowledgement;
a conflicting payload returned 409, with one new audit row and work order overall.

The backend was then stopped and restarted while retaining the database. The
[restart check](images/revision2/release19/workflow-restart.json) returned the exact
original receipt without additional audit/work-order effects. Its changed startup
identity timestamp and matching release are recorded. These are real HTTP/persistence
checks, not physical equipment acknowledgements or multi-process source isolation.

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
Blender revision 1 counts above are historical; the current handoff report describes revision 2.

## Actual application captures

These historical screenshots show the original revision 1 GPU application. Current revision 2 captures are linked above.

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
animation. Revision 2 cars have independently computed presentation poses and actual GPU evidence; none of this establishes engineering dynamics. Telemetry overlays are DOM
annotations, not physically simulated heatmaps. All viewers share camera, selection
and scenario state. JPEG frame delivery is deliberately simple; an expanded service
would need session management and a suitable low-latency streaming transport.
