# Independent final eight-hour evidence review

**Both tracks completed the requested eight-hour elapsed window, and their reconciled ledgers meet the declared sampled-coverage criteria. One GPU observation failed and remains counted.** This supports an eight-hour sampled experiment, not uninterrupted uptime, a single-release GPU soak or demonstrated business benefit. Review used local archives, the shared contract validator and the saved image; no live calls, application changes or test-suite reruns were performed.

All **17 capture-manifest files and five analyzer inputs** independently match their recorded sizes and SHA256 hashes. Every capture reports `changed_during_read: false`. CPU and GPU archives were captured separately at **03:47:57.890675** and **03:47:58.343602 UTC on 20 October 2026**, after both producer finish timestamps; they are not globally atomic. Analyzer SHA256 matches the accepted `7833c30d628d603873a876b121c78870b0c4735dde2083884d12b15e06d6719d`.

| Track | Recounted records | Exact start → finish, UTC | Reported elapsed | Failures |
|---|---|---|---:|---:|
| Fixed API | 96 complete cycles; 961 checks including startup | Oct 19 19:47:34.209802 → Oct 20 03:47:34.450673 | 28,800.241 s | 0 |
| GPU observer | 960 sequential samples; 959 passing | Oct 19 19:47:33.091451 → Oct 20 03:47:33.093044 | 28,800.002 s | 1 |

Independent UTC subtraction gives **28,800.240871 s** and **28,800.001593 s**, respectively. Both producer flags are complete. CPU summary checks exactly match its journal, all ten cycle check types occur 96 times, and check execution timing is serial and bounded by finish. GPU indices are exactly 0–959. No new failure occurred after the six-hour prefix.

The sole GPU failure remains **sample 4 at 19:49:33.123754 UTC**, connection refused; its transport-error record is retained. Deployment context does not erase this observation. CPU identity stays `d3dca3d`; GPU identities remain `20f0ca8 → d3dca3d → 64c8bfa → afa84a1`. All retained identities have consistent verified-release metadata, with no dirty state or mismatch list. These are startup file checks, not continuous process attestation.

## Coverage and contract acceptance

Independent schedule-window recomputation matches the analyzer: CPU gaps total **19.438464 s**, largest **0.591203 s**; GPU gaps total **8.691523 s**, largest **0.010451 s**. Every gap is below the predeclared two-second scheduling allowance. No pauses were recorded. CPU windows account for actual cycle execution finish; GPU windows use the configured 30-second cadence because observation execution duration is not retained. These windows describe sampling coverage, not continuous functional activity.

The shared `validate_review_contract` accepts the actual **`aster.review-run.v2`** file. Its inputs, coverage, failures, transport errors, warnings, pause totals and observed GPU commit list match the analysis. Reconciliation errors are empty. Completion is supported by elapsed time **and** repeated observed coverage; it is not inferred from a producer clock alone. Hashes establish file identity, not authentication of deliberately fabricated records.

The separate coordinator reporting interruption remains documented: last checkpoint **23:39:30.122740**, restart **23:57:33.877290**, resumed checkpoint **23:57:35.411877 UTC**. Exact watcher termination time/cause is unknown. Between those checkpoint boundaries, the producer ledgers contain **30 passing CPU checks across cycles 48–50** and **36 passing GPU observations, indices 464–499**. Their cadence gaps remain below the declared allowance. There is no associated missed scheduled cycle/sample or failed producer observation; the coordinator interruption must not be presented as an application outage.

## Images, resources and customer-facing limits

All **eight saved JPEGs**, indices 0, 120, 240, 360, 480, 600, 720 and 840, match their observation hashes and byte counts. The latest saved image is therefore a **seven-hour image**, not a completion screenshot. `frame-00840.jpg` is **95,559 bytes**, SHA256 `6d3f931367b8edbf128b411b6aed24239b2d22224157e0a067db99c1ed0f186a`; visual inspection confirms the 1280×720 park overview. Observation 840 passed at **02:47:40.693256 UTC**. Its frame 266269 rendered at **02:47:40.735**, source tick **87398**, while the separately fetched view was at **87399**. JPEG age **0.010 s** differs from header telemetry age **1.182652 s**. The final observer sample is **959 at 03:47:11.782974**, passing in live `normal` context; it was not saved as another JPEG.

Resource evidence contains **457 measurements**, **20:10:40.015–03:46:40.604 UTC**, about **456 minutes**. Memory spans **1–3,848 MiB**, first 2,935 and last 2,919; GPU utilization spans 0–11%. UTC interpretation of timezone-free CSV timestamps remains an assumption. Sampling began later than the experiment and may include other processes or static rendering; no full-eight-hour resource, leak-free or workload-attribution claim follows.

No material evidence issue blocks publication of this scoped result. The experiment demonstrates repeatable synthetic API checks and sampled rendering availability. It does not establish calibrated forecasts, autonomous real-world control, actual repairs, operator time savings, increased guest throughput or financial return. The deterministic API operator is not evidence of LLM reasoning. A next pilot should measure a concrete operator task and real outcome against a baseline before claiming customer value.

## Delivered-package verification

The published `raw-evidence.tar.gz` independently matches SHA256 **`1a00d1da71a20b7ddea64cfe3bb3c63353340069f40f102ab91ceff1c89c57b8`** and **3,357,074 bytes**. Its 14 regular-file members comprise 13 evidence files and `manifest.json`; the embedded and published manifests agree, every evidence member matches its size/hash, and all five analyzer inputs match the accepted ledgers exactly.

I extracted the delivered archive into a fresh ignored runtime directory and ran the documented analyzer command. It exited zero, emitted a complete v2 contract and reported zero reconciliation errors. Reproduced track data, numerical resource results, contract track data, source identities, failures and all input hashes/sizes exactly match the accepted outputs; only expected path/capture metadata changes. The final report's measured counts, timestamps, cadence gaps, resource and saved-frame scope agree with these ledgers. Its policy-grid numbers agree with the earlier independently reviewed evaluation; supervisor and sanitized closure records support the stated zero restarts, exit code and recorded shutdown times. This packaging check adds reproducibility evidence, without extending the operational or business-value claims above.
