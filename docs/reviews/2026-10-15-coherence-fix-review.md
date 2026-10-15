# Coherence-fix closure review

Reviewed committed revision: **`cb114248923dcfbc6c13243dfe960c8c1455dd5f`**, isolated using `git archive`. Later producer/model/scene work is excluded. This is a closure check of the [integrated checkpoint review](2026-10-15-integrated-checkpoint-review.md), not a replacement for it.

**Decision: the fixes address the original three defects at their CPU/contract boundaries, but one remaining status/pose publication race prevents complete closure at this commit.** A targeted fix is sufficient. Keep the implementation; no component or project rewrite is warranted.

## Verified fixes

| Original defect | Inspection and verification | Disposition at `cb11424` |
|---|---|---|
| Equal simulator tick confused different accepted-source state | `ParkReadModel.snapshot()` now hashes canonical content/provenance/quality while excluding continuously changing age. Replay capture requires the same accepted revision. Regression cases reject an old revision after same-tick fault injection and accept a matching one. | Original association defect fixed, subject to status publication issue below |
| Latest camera/projections moved labels independently from image | Frame cache now includes camera, projected coordinates and dimensions; headers carry them with JPEG bytes. Browser annotations read captured context and require accepted-source revision agreement. Versioned picks compare camera/source/view at execution. | Original camera/annotation contract fixed; real browser/native validation pending |
| Python caches prevented verified reactivation | Launcher uses `-B` and `PYTHONDONTWRITEBYTECODE`. Artifact verification permits explicitly non-authoritative real cache directories while still rejecting redirecting cache symlinks/unexpected source. Adapted original artifact probe performs normal import, observes `backend/__pycache__`, and successfully reactivates the same release. | Reproduced defect closed |

The isolated focused suites passed **39 tests in 2.09 seconds**: `test_state_coherence.py`, `test_project_revision.py`, `test_release_artifact.py`, using the integrator's test-process-only sandbox loop plugin. The cache/import test explicitly clears inherited `PYTHONPATH`, so it imports the staged fixture rather than the test runner's backend. The original release probe was also rerun independently against this exact commit.

The reviewed revision adds startup source inspection with honest `verification_scope`: files on disk at startup, not executing-process attestation or GPU acceptance. Manifest verification and a running revision are related evidence, not interchangeable claims.

## Remaining P1 at this commit: `/status` can bind old motion to a new frame/revision

`renderer/service.py:status()` still copies mutable service state under the outer lock, releases it, and then reads `FrameCache`. A renderer publication can occur in between. Captured camera/projections override their older state counterparts, but `ride_motion`, `ride_status` and `motion_policy` are not in the frame metadata at this commit.

A deterministic interleaving returned:

```text
frame: 2
accepted_state_revision: new-revision
camera: new camera
ride_motion: coaster_phase 0.1, wheel_angle 0.2 (old generation)
```

The actual newly published motion was phase 0.8 / angle 0.9. Replay's stricter revision check can therefore pass while the pose still comes from another generation. The content-identity test is necessary but not sufficient if the status envelope itself mixes generations.

**Required fix:** hold the service publication lock across state and frame-cache reads, and publish pose/status/policy with the immutable frame record. Preserve lock order used by publication. Add deterministic concurrent coverage of the actual status handler.

At the parent's explicit request, this reviewer added `tests/test_status_coherence.py`. It forces a writer to attempt publication precisely between state copy and frame read. The test **fails the isolated `cb11424`** with `Publisher escaped status's generation lock`. It **passes the parent's subsequent local fix** (one CPU test, 0.27 seconds). That local fix is not retroactively part of this committed review; capture its commit and rerun the integrated suite before closing this finding.

## Remaining limits

- The parent's 19 JavaScript logic checks were not independently rerun in this audit. Such checks cannot replace Chromium behavior/layout/timing evidence.
- Native picking now protects camera/data/view context, but does not reconstruct moving geometry at the exact displayed image's animation phase. Picking a moving coaster car can still differ from picking static geometry under network/render delay. Treat this as a presentation limitation; validate the intended interaction on the GPU before promising exact historical-frame picks.
- Per-image context is transported in an HTTP header. Twelve park assets fit comfortably; substantially larger scenes need a bounded metadata/streaming design and payload-size checks rather than unlimited header growth.
- CPU tests still do not certify SDK buffer lifetime, clean native destruction, actual replay poses, articulated-car rendering or browser interaction under polling.
- R1 `930acd3` gallery remains the last externally verified GPU/browser evidence. R2 model/UI/Blender/native acceptance and publication/staging require their own revision-bound evidence.

**Next acceptance:** commit the status-publication fix and regression, rerun the combined CPU/API suite, then execute the native/browser workflow once Horde access returns. Preserve prior review snapshots and keep current implementation evidence distinct from the older gallery.
