# Short feature update: incident to evidence, design to access

This recording adds an approximately **88-second content segment** to the existing
3-minute-34-second presentation. It demonstrates the direct incident workflow and
read-only spatial comparison in the actual browser application. The [accepted export](fox-update/README.md) is **87.77 seconds** after the
measured-container trim described below. This document retains the storyboard,
preparation checks and reproduction procedure.

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


## Encode the accepted take

`scripts/edit_fox_update.py` is a separate editor for this recorder's schema. It
requires a successful capture, empty page/observation/finalization error lists,
successful POST responses, all required cleanup attempts and live/normal readback.
The gateway and renderer must both retain the same verified commit and scene at
both boundaries. Only explicitly timed `ERR_ABORTED` frame fetches at browser
shutdown may be classified as shutdown cleanup rather than a capture failure;
those entries remain in the edit manifest.

On the GPU host, use the separate CPU video-tools environment:

```sh
/home/horde/park-twin-video-tools/bin/python scripts/edit_fox_update.py \
  /home/horde/park-twin-runs/fox-20261019/fox-update-take01/capture-manifest.json \
  --output /home/horde/park-twin-runs/fox-20261019/fox-update-edit01
```

The editor verifies the raw file's SHA-256 against the capture manifest, measures
its actual container duration with FFmpeg, and refuses a content end beyond that
duration. It trims from `presentation_start_seconds` to
`recording_content_end_seconds` as one continuous stream at normal speed. It does
not cut and concatenate the application footage chapter by chapter. There is no
intro/outro or viewport scaling. A 120-pixel Pillow-rendered band is added beneath
the 1920×960 application, with up to two caption lines. The output is 1920×1080,
H.264, 30 fps, no audio. Frame-rate conversion does not imply higher native RTX
rendering performance.

Outputs are `aster-park-fox-update.mp4`, its `.srt`, `poster.png`,
`edit-manifest.json` and `verification.json`. The reports retain the raw/capture/
recorder/editor/FFmpeg hashes, precise trim values, approximate capture-to-container
timing basis, measured raw and output durations, caption boundaries, decode frame
count and full decode-log hash. The MP4 must pass a complete FFmpeg decode with
errors treated as failures. Automated decode does not establish visual quality;
inspect the poster, captions and footage separately before publication. Existing
output directories and the original long presentation are never overwritten.

Preparation validation used the actual take01 manifest: its recorded content
interval is 2.137–90.138 seconds, or 88.001 seconds after trimming. The metadata
gates accepted it and rejected deliberately changed status, page error, cleanup,
commit, timing and missing raw-hash cases. All ten actual chapter caption bands
rendered within the 120-pixel area in temporary files. This validates the editor
preparation only; it does not claim that encoding, full decode or visual acceptance
has already completed.


### Explicit bounded clipping of an unencoded tail

The actual take01 container measured **89.92 seconds**, while its monotonic content
end was **90.138 seconds**. Browser page creation and the first encoded frame do
not share an exact known origin. The editor correctly rejects this mismatch by
default. Do not alter the capture manifest or claim that the full requested
88.001-second content interval exists in the file.

An explicit `--clip-unencoded-tail` permits at most **0.5 seconds** of unavailable
tail to be removed against the measured raw-container bound. For this take it
clips **0.218 seconds**, producing a requested edit duration of **87.783 seconds**
before frame-boundary quantization. The original capture and raw chapter times
remain intact in the report. Only the final edited chapter/SRT end is clamped; no
earlier chapter can be removed or shortened. No tail padding, frozen last frame,
repeated tail, speed change or inferred first-frame-offset correction is applied.
The actual MP4 duration must still be measured and pass full decode.

```sh
/home/horde/park-twin-video-tools/bin/python scripts/edit_fox_update.py \
  /home/horde/park-twin-runs/fox-20261019/fox-update-take01/capture-manifest.json \
  --output /home/horde/park-twin-runs/fox-20261019/fox-update-edit01 \
  --clip-unencoded-tail
```

The edit manifest records both requested and effective boundaries and an explicit
`unencoded_tail` policy/measurement. A mismatch above 0.5 seconds still fails, even
with the flag. The last chapter remains visible for approximately 5.8 seconds;
visual inspection must confirm that all demonstrated features and the export
are present. This policy is a bounded measured-container trim, not a claim that
monotonic and encoded-frame timestamps have been precisely aligned.
