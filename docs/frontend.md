# Aster Park browser experience

The frontend is plain HTML, CSS and JavaScript in `frontend/`. Serve it through
`main:app` so operational APIs and the GPU renderer share one browser origin.
There is no build step or client-side 3D renderer. Google Fonts are optional;
the interface falls back to system fonts when offline.

## Operator experience

- Six operational KPIs, seven synthetic scenarios, actionable alerts, an asset
  inspector, telemetry history, staffing, inventory and maintenance work orders.
  The queue KPI includes active ride, food, admission and facility queues;
  closed assets are excluded.
- Read-only scenario comparison shows an uncalibrated synthetic model baseline
  and hypothetical response. Injected connector observations are not comparison
  inputs. Applying a scenario is a separate explicit action.
- Actual OVRTX JPEG frames support orbit, zoom, home, focus, fullscreen, native
  GPU object picking and projected data labels. The registry remains usable
  when the GPU is unavailable.
- Ten source cards display connector health. Their inspector exposes accepted
  observations, authority, quality, source and ingestion times, provenance and
  JSON. Live / paused / offline controls affect synthetic connectors only.
  Missing accepted fields display an em dash, not a plausible baseline value;
  stale accepted values remain visible with quality labels. Unmapped fields
  retain explicitly labeled model-derived values. Alert evidence identifies
  accepted source quality separately from model estimates.
- Dependencies appear as projected SVG arrows and an asset relationship panel.
  These are logical service dependencies, not physical pipe or cable geometry.
- A timeline selects recorded states. Replay visibly identifies capture time,
  source time and scene compatibility, locks operational mutations and comparison,
  and allows camera interaction. Returning live restores controls. Live recording
  continues while a recorded state is displayed.

All data and operator actions are synthetic. No physical controls or external
enterprise systems connect. Browser clients share the simulation, displayed
replay cursor, renderer camera and selection; this POC does not isolate sessions.

## Consistent live and recorded data

The browser polls `GET /api/view/state` once per second. Asset detail and history
use `/api/view/assets/{id}` and `/api/view/assets/{id}/history` on selection and
approximately every five seconds. The timeline refreshes every three seconds;
`POST /api/view` changes the shared displayed state. Request sequencing prevents
an earlier live response from overwriting a subsequent replay selection.

While a live source dialog is open, its health and normalized observations
refresh every two seconds. In replay it reads captured source health and accepted
field metadata from the selected snapshot, with no live source, observation or
connector requests. Recorded raw inspection is explicitly captured accepted
fields; original raw connector responses are not reconstructed. Uncaptured work
order details are disclosed. The backend also rejects operational changes during
replay, independent of disabled browser controls.

Recorded operational data does not imply recorded geometry animation. If no
matching GPU pose was captured, the banner and frame context disclose that the
visible ride pose is not historical evidence. Otherwise the renderer uses the
captured pose. A recorded scene revision mismatch is also surfaced.

## Image provenance and controls

Renderer status is polled about every 650 ms. The frame loop requests
`/render/frame.jpg` at up to eight frames per second, waits for image decode,
then replaces the prior image and revokes its object URL. Polling pauses while
the browser tab is hidden.

The image's own `X-Frame-*`, `X-Source-*`, `X-View-*` and `X-Pose-Source` headers
identify its rendered time, frame number, input state and view. A newer status
response cannot supply a timestamp for an older JPEG; status metadata is only
used when its frame identity matches. Repeated delivery of a cached image does
not refresh its age. A fresh image with stale source data or frozen affected ride
poses produces a separate source warning. Missing frame metadata is disclosed.
Deploy the frontend, gateway and renderer together to preserve this contract.

A frame must match the selected live/replay mode and snapshot. Annotation values
and dependency edges must also match its exact accepted-state revision. Its
`X-Frame-Context` supplies the exact camera, image dimensions and projected asset
coordinates used for that JPEG. Newer renderer status cannot move annotations
on an older image. Missing or malformed context, or an absent/mismatched data
revision, suppresses annotations; same-frame status is the only metadata fallback.

The live dashboard and inspector continue showing the latest API state. Image
annotations use a separate immutable snapshot for the frame's revision, from a
32-entry browser cache or `GET /api/state/revisions/{revision}`. The visible
caption distinguishes captured annotation time from latest dashboard/inspector
time. Snapshot quality ages belong to capture time, not current connector health.
The dependency panel below the viewport is separately labeled as latest context.

Only one revision lookup is in flight, failed lookups are throttled for five
seconds, and late responses populate the cache without replacing a newer image
or recorded view. Missing/expired/oversized snapshots suppress annotations; they
never substitute latest values. Replay uses only its selected captured snapshot
and does not request the live revision endpoint. This keeps accurate association
without hiding labels merely because the latest dashboard tick advanced.

The image retains its actual aspect ratio. Native picks and projected labels
use the same letterbox-aware image rectangle, including fullscreen. Picks submit
normalized `{x,y}` plus the image camera token, accepted-state revision and view
identity to `/render/pick`. The renderer validates that context at the native
render owner and rejects changed state with HTTP 409. The browser also discards
a response after its displayed view/cursor changes. Ordinary live telemetry
updates do not invalidate a successful stable asset-ID selection. This selects an asset in current
geometry: it does not certify a historical pixel hit on animated geometry. Direct
legacy API requests without version fields remain unversioned; browser requests
require the camera token. Dragging submits accumulated orbit fractions
of image width and height. Camera changes are coalesced while a request is in
flight. Registry selection calls `select`; Locate calls `focus`.

Operations, Energy, Guest Flow and Dependencies are **browser data overlays**
anchored to projected OpenUSD asset positions, not physically rendered heatmaps.
The layer control also records the chosen layer in renderer state.

## Accessibility and responsive behavior

Controls use native buttons, selects and a timeline range input. Focus states,
ARIA labels, live status messages, keyboard-accessible dialogs and reduced-motion
preferences are present. With viewport focus, arrows orbit, `+`/`-` zoom and
`Home` resets the camera. The desktop inspector stacks below the viewport on
mobile. Desktop and mobile source/replay layout were checked against actual
GPU releases `154e746` and `2e2b16b`; acceptance evidence is tracked below.

## Evidence and validation boundaries

**Original GPU milestone:** Headless Chromium at 1440 × 1100 and 390 × 844
reported no JavaScript page errors or horizontal overflow. The actual NVIDIA
OVRTX `0.6.0.1791947691` / OVStage `0.3.0.1791986420` renderer reported about
12.5 frames/second. Browser orbit, zoom and focus changed the server camera.
Native image clicks selected the food-court plaza, hotel roof and energy-center
solar geometry, resolving each to its correct database asset. Closing the coaster
stopped its rendered train while the wheel continued; normal operation resumed
it. Scenario comparison, work orders, guest rerouting, simulated leak repair,
ERP inspection and architecture dialog passed.

The original evidence remains in
[`images/browser-validation.json`](images/browser-validation.json),
[`operations-live.png`](images/operations-live.png),
[`operations-ride-closure.png`](images/operations-ride-closure.png),
[`ovrtx-viewport.png`](images/ovrtx-viewport.png),
[`scenario-comparison.png`](images/scenario-comparison.png),
[`connected-architecture.png`](images/connected-architecture.png) and
[`mobile-live.png`](images/mobile-live.png). These predate timeline and connector
quality additions; they do not validate the new features.

**Replay and source-quality milestone:** On real GPU release `154e746`, the
extended browser acceptance passed connector pause → stale → offline → resumed
health, recorded state selection, read-only HTTP enforcement, recorded source
inspection without live requests, continued recording, return to live, and mobile
layout. No JavaScript page errors or horizontal overflow were reported. See
[`revision2/extended/extended-browser-validation.json`](images/revision2/extended/extended-browser-validation.json)
and its screenshots. The release manifest and actual frame/source metadata are in
[`initial-release-provenance.json`](images/revision2/initial-release-provenance.json).

That release's smoke test found a real selection bug: a correct native pick was
discarded when live telemetry advanced during the response. The browser now
rejects changed views/cursors while preserving successful stable asset selection
across later telemetry updates. An actual 10-second cadence sample also found
annotations visible for only 63% of samples because each latest dashboard tick
hid labels on the previous matching image. The revision-cache design above fixes
that association path without relaxing exact matching.

**Final GPU acceptance (`2e2b16b`):** Both durable browser suites passed on the
verified release manifest, with scene SHA-256
`7e9f430e5302a9469e68fa649f2a1cbb0784bdf519a7a41421a96124b87a0c1c`.
Native picks selected food-court, hotel and power-center roof geometry and updated
the inspector. Each initial request was correctly rejected with HTTP 409 after
its context changed; the retry succeeded. Coaster closure froze its pose while
the wheel continued, and normal operation resumed it. Camera controls, dispatch,
leak repair, comparison and source inspection passed. No page errors or desktop /
mobile overflow were observed.

The extended suite passed source condition changes, replay write rejection,
recorded source isolation (including no live revision lookups), and ongoing
recording. In comparable 100-sample / ten-second measurements, annotation
visibility improved from 63% to 92%; all visible labels matched the displayed
JPEG revision. This is a short acceptance sample, not a sustained benchmark;
brief gaps remain while resolving a new exact snapshot.

See [`final/browser-validation.json`](images/revision2/final/browser-validation.json),
[`final/extended/extended-browser-validation.json`](images/revision2/final/extended/extended-browser-validation.json),
and [`final/extended/annotation-cadence.json`](images/revision2/final/extended/annotation-cadence.json).
Screenshots include [`live operations`](images/revision2/final/operations-live.png),
[`recorded view`](images/revision2/final/extended/recorded-view.png), and
[`source quality`](images/revision2/final/extended/source-stale.png).
Four actual JPEG gallery views and per-image provenance are in
[`final/gallery/render-captures.json`](images/revision2/final/gallery/render-captures.json).

**Current local checks:** JavaScript syntax, Python test syntax, 58 referenced
DOM identifiers and 28 JavaScript behavior checks pass. They cover missing-field
truthfulness, read-only replay, frame provenance, immutable/bounded annotation
caches, exact older-frame values versus latest inspector values, single-flight
lookup, bounded retries, failed/mismatched responses, and late responses during
replay. In-process HTTP checks also verified the operational view/source/replay
contracts. Earlier sandbox/network restrictions prevented browser tests; the
actual GPU evidence above was captured once access became available. The original
GPU milestone screenshots remain unchanged.

## Repeat validation

Logic checks need Node, but no browser, backend or GPU:

```bash
python tests/browser_extended.py --logic-only
```

For browser checks, start the application separately and install Playwright:

```bash
python -m pip install playwright
python -m playwright install chromium
PARK_URL=http://127.0.0.1:8100 python tests/browser_extended.py
PARK_URL=http://127.0.0.1:8100 python tests/browser_smoke.py
```

The extended test exercises connector pause → stale → offline → resumed health,
recorded selection, disabled mutations and server rejections, captured source
inspection without live requests, continued recording, dependency overlays and
mobile layout. It also samples annotation visibility 100 times and rejects any
visible annotation whose revision differs from the displayed image. To test frame metadata failures without a GPU, use its explicitly
labeled CPU image fixture with the real backend:

```bash
PARK_URL=http://127.0.0.1:8100 python tests/browser_extended.py --mock-renderer
```

This fixture validates browser behavior, not NVIDIA rendering or native picking.
Extended artifacts default to `docs/images/extended-ui`, or `docs/images/offline-ui`
for the CPU fixture. The original smoke test requires the actual GPU application
and defaults to `docs/images`; use `PARK_SCREENSHOTS` to redirect any test's output.
`PARK_URL` defaults to `http://127.0.0.1:8100`. If global Node CA flags conflict,
prefix Playwright commands with `env -u NODE_OPTIONS`.

Tests change shared synthetic state. Cleanup returns to live, restores normal
operations and the home camera; the extended test resumes the water connector.
The audit trail is intentionally preserved.

Final backend release `19cee1e` also passed the actual GPU browser smoke suite after
the durable action change: [report](images/revision2/release19/browser/browser-validation.json).
Native context-change rejections and successful retries remain explicit in the report.
The earlier full extended/cadence run remains bound to `2e2b16b`.
