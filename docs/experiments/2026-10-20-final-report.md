# Eight-hour FOX-inspired theme-park experiment

**Both measured tracks completed eight hours. The temporary GPU is stopped; the project workspace is retained.** This cycle produced a working decision and maintenance demonstration, design comparisons, independent reviews and reproducible evidence. It did not establish real-world optimization or ROI.

[Final presentation (PDF)](../fox-review-final.pdf) · [Actual-browser update video](../video/fox-update/README.md) · [Detailed analysis](run-analysis/final/analysis.md) · [Independent evidence review](run-analysis/final/review.md) · [Timeline](run-analysis/final/timeline.svg) · [Raw evidence and reproduction](run-analysis/final/README.md) · [Closing value/architecture review](../reviews/2026-10-20-final-value-review.md)

## What now works

- **Decision Lab:** compare do-nothing, simple-rule and candidate responses across seven synthetic scenarios, over 15–120 minutes. Freeze observations and assumptions, expose resource limits and sensitivity cases, and save durable comparison evidence.
- **Incident to maintenance:** prepare a request directly from a current incident, review three frozen source observations, explicitly execute a synthetic work order and verify readback. Expiry, changed conditions and retry identity constrain execution. A dispatched order leaves the ride closed.
- **Design comparison:** inspect a separate dining-path proposal using matched native RTX images and a partial route graph. Closing the connector removes its route; the authored step-free entrance problem remains visible. Geometry and service forecasts are separate models.
- **Connected context:** synthetic operational feeds share asset identity, freshness and quality. A real read-only weather preview remains distinct from synthetic park observations. Proposed production integrations retain ERP, CMMS, workforce and ride-system authority.

The application uses real NVIDIA OVStage and OVRTX on an L40. FOX supplies architectural inspiration; no installed FOX runtime or autonomous LLM park operator is claimed. The [88-second actual-browser update](../video/fox-update/README.md) demonstrates the incident and design workflows.

## Measured outcome

| Track | Actual UTC window | Recorded result |
|---|---|---|
| Fixed API exercise | 19 October 19:47:34.209802 → 20 October 03:47:34.450673 | 28,800.241 seconds; 96 full cycles; **961 checks passed, zero failures** |
| GPU observation | 19 October 19:47:33.091451 → 20 October 03:47:33.093044 | 28,800.002 seconds; **960 samples, 959 passed, one failed** |

The API track stayed on `d3dca3d`; the GPU observer recorded four verified application revisions, ending at `afa84a1`. New incident and spatial features have separate actual GPU/browser acceptance. The final GPU application remained unchanged after 20:52 UTC. Neither track recorded a pause. The local API supervisor finished with exit code zero and no backend restarts.

The failed GPU sample, index 4 at 19:49:33 UTC, records connection refused. It coincided with an early deployment and remains a failure. Later successful samples do not erase it or prove uninterrupted service between observations.

The declared cadence rule passed for both complete ledgers. It retains **19.438464 seconds** of uncovered API schedule intervals (largest 0.591203 seconds) and **8.691523 seconds** for GPU observations (largest 0.010451 seconds), within the fixed two-second per-gap scheduling allowance. These are scheduled samples, not continuous uptime. Actual UTC spans, monotonic durations, summary/journal contents, input stability and verified source transitions all reconcile before the final v2 contract is emitted.

The coordinator progress watcher exited with code 143 and was restored at 23:57 UTC. Its exact termination time and cause are unknown. Independent review found producer records continued through the reporting interruption; neither producer nor the application was restarted. This monitoring event remains documented separately.

GPU resources contain 457 measurements from 20:10:40 to 03:46:40, approximately 456 minutes. Device memory spans 1–3,848 MiB and ends at 2,919 MiB. Sampling began later than the experiment and includes development activity; it cannot certify full-run resource coverage, workload attribution or absence of leaks. Eight saved native images cover sample indices 0–840; the last saved image is from hour seven, while observations continue to index 959.

## What the value review found

The strongest next pilot is **one ride, one duty manager, one read-only incident feed and a CMMS sandbox**. Compare correct-asset identification, verified-order time, duplicate/incorrect orders, corrections and stale-data recovery against the existing operator workflow. Agree useful improvements and error limits before measuring them.

The independent 324-case food-service grid is deliberately unfavorable in places: the planner and rule agree in 216 cases; in the remaining 108, added labor costs EUR56 per case, and 52 show no waiting benefit. Across all cases, mean differences versus the rule are only +1.701 completed service visits, −28.883 guest-minutes waiting and +EUR18.667 labor. These synthetic averages are not expected returns; omitted staffing feasibility and donor-team costs prevent operational recommendations.

The architecture review recommends **keep and improve the modules, not a rewrite**. Shared evidence validation was a useful targeted refactor. Further visual detail or more agents would not replace missing operator, source-system and calibration evidence.

## Compute closure

The final GPU archive was downloaded and verified before shutdown. Horde reported `park-fox-rtx` **stopped at the 03:50:03 UTC verification**. The expected persistent workspace was still present at 03:50:25. The local API supervisor, backend, evaluator and coordinator watcher had exited. [Sanitized closure record](run-analysis/final/compute-release.json) retains these observations. No workspace deletion was requested.
