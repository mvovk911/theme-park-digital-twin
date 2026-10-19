# Independent four-hour checkpoint review

**The halfway prefix is internally consistent, with no new failed checks or observations since the two-hour checkpoint. The requested eight-hour experiment is not complete.** This review used only frozen local files and the saved image; no live calls, application changes or test-suite reruns were performed.

I independently verified the byte sizes and SHA256 hashes of all **14 files** in the CPU/GPU capture manifests and all five analyzer inputs. Every capture reports `changed_during_read: false`. GPU files were captured at **23:48:20 UTC** and CPU files at **23:48:27 UTC on 19 October 2026**; these separate captures are not a globally atomic snapshot. The analyzer matches the accepted source SHA256 `7833c30d628d603873a876b121c78870b0c4735dde2083884d12b15e06d6719d`.

| Track | Independently recounted records | Reported elapsed | Failures |
|---|---|---:|---:|
| Fixed API | 49 full cycles; 491 checks including startup | 14,452.767 s | 0 |
| GPU observer | 482 sequential samples; 481 passing | 14,444.450 s | 1 |

The API summary exactly matches its journal, with all ten cycle check types appearing 49 times and valid serial execution timing. GPU sample indices run from 0 through 481. Its sole failure remains **sample 4 at 19:49:33.123754 UTC**, connection refused. The additional **24 API cycles and 239 GPU observations** since the two-hour checkpoint add no failure. The earlier failure remains counted, irrespective of deployment context.

CPU source identity remains `d3dca3d`. GPU evidence still spans `20f0ca8 → d3dca3d → 64c8bfa → afa84a1`; all four retained transitions have consistent verified-release metadata, without dirty flags or mismatch lists. No additional deployment appears in this prefix. This is startup file-verification evidence, not continuous process attestation or a single-release GPU soak.

I independently recomputed the cadence-window gaps: CPU total **6.358152 s**, largest **0.591203 s**; GPU total **4.385820 s**, largest **0.010451 s**. Both partial windows satisfy the declared two-second per-gap allowance, with zero reported pauses. Gaps remain disclosed; this is sampled schedule coverage, not continuous uptime. Both producers report incomplete, neither has a finish timestamp, the analysis has zero reconciliation errors, and no final `review-run.json` exists.

## Latest saved frame

`frame-00480.jpg` matches its event and manifest: **95,627 bytes**, SHA256 `589e153ea0a00d097240d6641293359edf7e6d6604f243edbefdbeee23873fbd`. Visual inspection confirms the 1280×720 park overview with rides, paths, buildings, water and perimeter.

Observation 480 passed at **23:47:37.466976 UTC**, in live `normal` context on `afa84a1`. Exact-image headers identify frame **131375**, rendered at **23:47:37.510 UTC**, using the unchanged baseline scene and source tick **77020**. The separately fetched view was already at tick **77021**. Measured frame age was **0.012 s**, while telemetry source age in the header was **1.602046 s**. A fresh JPEG therefore does not imply equally fresh underlying telemetry or equality with the separately fetched state. Camera, scene, view and projected-asset provenance remain attached to the saved event.

## Resource interval and end-user value

The CSV recount yields **218 measurements**, from **20:10:40.015 to 23:47:40.383**—about **217 minutes**, beginning after the experiment. Device memory remains **1–3,848 MiB**, from 2,935 initially to 2,919 at the last measurement; GPU utilization spans 0–11%. Extrema are retained. Measurements can include static rendering and other processes; this does not certify absence of leaks, attribute resource use to one app, or cover eight hours. UTC interpretation of the timezone-free CSV remains an explicit assumption.

No material new issue justifies changing the frozen application. Continued observation is appropriate. This checkpoint strengthens repeatability evidence for synthetic API contracts and ongoing rendering; it does not demonstrate faster operator work, completed real repairs, better guest throughput, calibrated forecasts or financial return. The customer-facing claim remains a functioning, instrumented proof of concept under a still-running experiment.
