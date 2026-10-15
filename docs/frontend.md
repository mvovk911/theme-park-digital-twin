# Aster Park browser experience

The frontend is plain HTML, CSS and JavaScript in `frontend/`. Serve it through
`main:app` so operational APIs and the GPU renderer share one browser origin.
There is no build step and no client-side 3D renderer. Google Fonts are optional;
the interface falls back to system fonts when offline.

## Operator experience

- Six live KPIs, seven synthetic disruption scenarios, and an operational brief
  driven by current alerts.
- Read-only scenario comparison: before/after metrics, affected assets, model
  assumptions, and an explicit button to apply the scenario. The comparison
  itself does not change live state.
- Actual OVRTX JPEG frames with camera orbit, wheel/button zoom, home, focus,
  fullscreen, native GPU object picking, and projected operational annotations.
- Asset selection from the rendered scene, projected labels, registry selector,
  dependencies, or source-service records. The inspector displays registry data,
  current telemetry, recent queue history, dependencies, staffing, inventory,
  and maintenance work orders.
- Applicable operator actions call synthetic service APIs and display results in
  the audit trail. No physical controls or external enterprise systems connect.
- Ten source-service cards expose their current domain JSON payloads. Architecture
  dialog explains the source → context API → OpenUSD / RTX / workflows relationship.
- Explicit synthetic-data labels, data freshness, renderer warming/offline states,
  stale-image warning, and readable request failures.

## API and rendering behavior

`GET /api/state` is polled once per second. Asset detail/history are fetched on
selection and approximately every five seconds. Renderer status is polled about
every 650 ms. The frame loop requests `/render/frame.jpg` at up to eight frames
per second, waits for image decode, then replaces the prior image and revokes its
object URL. All polling pauses while the browser tab is hidden.

The image is contained at its actual aspect ratio. Native picks and projected
labels use the same letterbox-aware image rectangle, including in fullscreen.
Picking submits image-normalized `{x,y}` to `/render/pick`. Drag submits accumulated
`{action:"orbit",dx,dy}` fractions of image width/height. Scroll submits pixel-like
`delta` to `{action:"zoom"}`. The frontend coalesces movement while a camera request
is in flight so the renderer queue does not accumulate a separate call per DOM
event. Selection from the registry calls `select`; the explicit Locate button
calls `focus`. Native pick already applies renderer selection.

Operations, Energy, and Guest Flow are **DOM data overlays** anchored to projected
OpenUSD asset positions. They do not claim to be physically rendered heatmaps.
The `layer` control also records the chosen layer in renderer state.

## Accessibility and responsive behavior

Controls are native buttons and selects. Focus states, ARIA labels, live status
messages, keyboard-accessible dialogs, and reduced-motion preferences are present.
When the viewport itself has focus, arrows orbit, `+`/`-` zoom, and `Home` resets
the camera. Layout adapts from a desktop inspector sidebar to a stacked mobile
view. The registry remains usable when the GPU is unavailable.

## Validation performed

- `node --check frontend/app.js` passes.
- Headless Chromium at 1440 × 1100 and 390 × 844 reports no JavaScript page errors
  and no horizontal page overflow.
- Browser smoke checks against the actual FastAPI backend with an isolated SQLite
  database: initial state, twelve-asset registry, ten source cards, seven-row
  read-only comparison with unchanged live scenario, ride closure, work-order
  dispatch, guest rerouting, water leak repair, source JSON inspection, and
  architecture dialog all pass.
- Those initial checks used an unavailable GPU service to verify its honest
  warming/offline experience.
- Live GPU acceptance then passed against NVIDIA OVRTX `0.6.0.1791947691` and
  OVStage `0.3.0.1791986420`, reporting approximately 12.5 renderer frames/second.
  Browser drag changed the server camera, zoom changed its radius, and focus
  moved to the selected asset. Three image clicks returned distinct native GPU
  hits: food-court plaza, hotel roof, and a solar-cell line on the energy center.
  Each resolved to the correct database asset and updated the inspector.
- Closing the coaster stopped its rendered train phase while the wheel continued
  moving. Restoring normal operations resumed the coaster. The browser also
  completed a maintenance dispatch and a simulated leak repair, verified
  read-only comparison and an ERP source payload, and produced no JavaScript
  page errors or horizontal overflow on desktop/mobile.

See [`images/browser-validation.json`](images/browser-validation.json) for the
actual motion measurements and pick paths. Screenshots include
[`operations-live.png`](images/operations-live.png),
[`operations-ride-closure.png`](images/operations-ride-closure.png),
[`ovrtx-viewport.png`](images/ovrtx-viewport.png),
[`scenario-comparison.png`](images/scenario-comparison.png),
[`connected-architecture.png`](images/connected-architecture.png), and
[`mobile-live.png`](images/mobile-live.png).

## Repeat the live browser test

The standalone [`tests/browser_smoke.py`](../tests/browser_smoke.py) exercises the
actual running GPU application. Install Playwright in a development environment:

```bash
python -m pip install playwright
python -m playwright install chromium
PARK_URL=http://127.0.0.1:8100 python tests/browser_smoke.py
```

`PARK_URL` defaults to `http://127.0.0.1:8100`. Set `PARK_SCREENSHOTS` to direct
screenshots and the JSON report elsewhere; its default is `docs/images` relative
to the project. On environments that globally set conflicting Node CA flags,
prefix the Playwright commands with `env -u NODE_OPTIONS`.

The test changes synthetic scenarios, dispatches a simulated work order, and
changes the camera. It restores normal operations and the home camera in cleanup;
the audit trail is intentionally preserved. Browser clients share one renderer
camera/selection and one simulation state in this POC. Per-user sessions are a
future deployment capability.
