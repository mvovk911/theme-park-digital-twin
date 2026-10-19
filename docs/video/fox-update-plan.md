# Short feature update: incident to evidence, design to access

This recording adds an approximately **88-second content segment** to the existing
3-minute-34-second presentation. It demonstrates the direct incident workflow and
read-only spatial comparison in the actual browser application. It is a capture
plan and reproducible recorder, not a claim that this new video has already been
recorded or accepted.

The browser records at 1920×960. An editor may add a 120-pixel caption band beneath
the content for a 1920×1080 export. This does not upgrade the native renderer's
1280×720 images or approximately 12.5 fps to native 1080p rendering. The recorder
retains the actual renderer's resolution, rate and release metadata in its manifest.
There is no audio, generated application imagery, replaced value, hidden error or
accelerated playback.

## Storyboard

Times below are relative to the ready live-overview content start. The generated
WebVTT uses the actual monotonic capture timestamps, including initial loading.

| Content time | Real interaction | Evidence and limitation |
|---|---|---|
| 00–09 s | Live RTX overview of the synthetic coaster closure | Wait for an advancing frame and matched annotations; actual scene and asset inspector |
| 09–18 s | Prepare selected incident, then explicitly create proposal | Preparation alone sends no workflow request; no forecast/save prerequisite |
| 18–29 s | Review the frozen three-field source evidence | Source timestamps, quality and proposal expiry stay visible |
| 29–42 s | Explicitly execute; inspect receipt and independent status | Same work-order ID in receipt/readback; good observed closed status; no physical completion |
| 42–49 s | Return to the live viewport and inspector | Coaster still closed, one open synthetic work order |
| 49–57 s | Compare baseline and dining design | Baseline unreachable; variant 40.852 m and 34.04 s at assumed 1.2 m/s |
| 57–65 s | Inspect matched before/after native closeups | Static native images, independently checked graph/scene identity and PNG hash |
| 65–74 s | Close the design connection in the query | Variant becomes unreachable; no scene or live-state mutation |
| 74–82 s | Apply the authored step-free filter | Unresolved entrance threshold remains; no accessibility certification |
| 82–88 s | Export the exact queries and responses | Identity-bearing design evidence; graph remains independent of forecast |

No finite or percentage travel-time saving is claimed against an unreachable
baseline. The design endpoint is the new plaza landing, not restaurant interiors
or service queues. Query closures do not change the static preview images.

## Run on the existing GPU machine

Reserve the shared application for this capture. The recorder verifies both the
healthy gateway and ready NVIDIA OVRTX renderer against the **exact full deployed
commit** before any setup mutation. It also verifies the rendered scene identity,
actual JPEG provenance, direct-incident capability and both static native preview
PNG hashes and graph/scene/layer headers. Missing, unauthorized or unverified
services fail the preflight; no renderer fixture is supported.

Use the already installed browser environment; keep it separate from the GPU SDK
environment. Replace `DEPLOYED_COMMIT` with the actual full 40-character commit.
The output directory must be new.

```sh
python3 scripts/capture_fox_update.py --plan

# Read-only preflight: no files, no live/view/camera mutations.
env -u NODE_OPTIONS \
  PLAYWRIGHT_BROWSERS_PATH=/home/horde/park-twin-browser/browsers \
  /home/horde/park-twin-browser/bin/python scripts/capture_fox_update.py \
  --url http://127.0.0.1:8100 \
  --expected-commit DEPLOYED_COMMIT \
  --preflight-only

# Run only in a reserved demo window.
env -u NODE_OPTIONS \
  PLAYWRIGHT_BROWSERS_PATH=/home/horde/park-twin-browser/browsers \
  /home/horde/park-twin-browser/bin/python scripts/capture_fox_update.py \
  --url http://127.0.0.1:8100 \
  --expected-commit DEPLOYED_COMMIT \
  --output runtime/presentation/fox-update/take01
```

`PLAYWRIGHT_BROWSERS_PATH` must match the Chromium installation on that machine;
change only that environment value if the existing browser cache lives elsewhere.
Do not use another operator's active shared session. No connector modes are changed.
Setup returns to live, resets synthetic state, uses the home camera and operations
layer, then applies the coaster-closure scenario through the visible UI. The
recorder never retries creation or execution automatically. Retained browser
workflow keys are saved in the manifest for uncertainty recovery.

Cleanup attempts live view, an explicit uniquely identified synthetic reset, home
camera and operations layer, then reads back live/normal. It closes the recorded
browser before cleanup. Context/video-finalization failures cannot skip restoration
or API disposal; failures are recorded independently without replacing the primary
error. Cleanup does not restore an arbitrary previous operator session. The reset
closes the demo work order; the earlier accepted receipt remains historical evidence.

## Outputs and acceptance

- `fox-feature-update-raw.webm`: original browser recording, with SHA-256 in the manifest.
- `captions.vtt`: actual chapter boundaries relative to page creation; first encoded-frame alignment is approximate.
- `capture-manifest.json`: preflight/final release identity, native preview metadata and hashes, source frame headers/JPEG hashes, screenshots and their hashes, workflow request/response evidence, page errors, request failures and cleanup results.
- `01-…png` through `09-…png`: actual viewport captures at the story beats.
- `spatial-query-evidence.json`: downloaded unchanged through the real application UI.
- `failure.png` and the incomplete manifest when a take fails; existing output directories are never overwritten.

The script checks frame advance and waits until exact-frame annotations resolve
at least once before showing the live overview and post-dispatch viewport. It does
not suppress the synchronization guard if it appears again. Screenshot metadata
records frame IDs before and after capture; if a frame advances, no exact pixel-to-
frame association is claimed. It never substitutes latest-renderer metadata for
missing screenshot context.

Accept a take only when the manifest says `captured`, there are no page errors,
cleanup readback is live/normal, native provenance matches, and the video is
visually inspected and fully decoded. Request failures at browser shutdown may be
aborted frame fetches; inspect their timing rather than silently deleting them.
The script rejects a content timeline reaching 100 seconds. Setup/loading and
browser-close overhead are recorded separately. Measure the encoded container's
actual duration before publishing; the manifest's duration fallback is monotonic
content timing and is explicitly not an FFprobe measurement.

For postproduction, burn or render the WebVTT in the lower caption band and leave
all application pixels untouched. Trim initial loading only after subtracting the
same offset from caption/chapter timestamps. Preserve the raw video and manifest;
label any failed or overlong take as such rather than editing away missing checks.

## Preparation validation

The script was syntax-compiled and its offline storyboard inspected. A real GPU
capture is intentionally left to the root deployment operator in a reserved window.
No GPU or shared service was changed while preparing these files.
