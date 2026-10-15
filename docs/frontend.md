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

A frame must match the selected live/replay mode and snapshot before native
picking or projected annotations are enabled. This avoids overlaying recorded
values on an image still showing another state during a view change.

The image retains its actual aspect ratio. Native picks and projected labels
use the same letterbox-aware image rectangle, including fullscreen. Picks submit
normalized `{x,y}` to `/render/pick`; dragging submits accumulated orbit fractions
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
mobile. New timeline/source UI awaits a fresh browser layout check as noted below.

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

**Replay and source-quality milestone:** JavaScript syntax, Python test syntax,
57 referenced DOM identifiers and 15 JavaScript behavior checks pass. These checks
cover unknown-value masking, replay write locks, view/frame mismatch, actual image
timestamps, cached-frame staleness, frozen source presentation and dependency SVG
visibility. In-process HTTP checks against the actual application also verified
view/detail/history contracts, ten source services, health/observations, timeline,
replay selection, connector mutation rejection and return to live.

The current execution sandbox blocks Chromium startup and local TCP binding;
network restrictions prevent a fresh GPU connection. Therefore new browser layout,
interactive replay and latest GPU integration remain unverified. No new GPU
screenshots were fabricated or substituted for the original evidence.

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
mobile layout. To test frame metadata failures without a GPU, use its explicitly
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
