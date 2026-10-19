# Offline analysis of the FOX experiment ledgers

`operators/analyze_fox_run.py` reads the fixed API evaluator's and GPU observer's recorded files. It reconciles their counts, reports actual timing and retained failures, and creates a concise JSON report, Markdown report and standalone SVG timeline. It makes no live HTTP calls, reads no provider inventory, and never alters sources, inputs or running processes.

```bash
.venv/bin/python operators/analyze_fox_run.py \
  --api-dir runtime/fox-cycle-20261019/api-soak/evaluation \
  --gpu-dir runtime/fox-cycle-20261019/gpu-checkpoint-2100/gpu-observation \
  --resource-csv runtime/fox-cycle-20261019/gpu-checkpoint-2100/gpu-resources.csv \
  --output docs/experiments/run-analysis/new-checkpoint
```

The output directory must not exist. Each track directory must contain `summary.json` and `events.jsonl`. The resource CSV is optional. For final reporting, supply freshly captured **completed** track files; the example GPU directory is a historical partial prefix, not the final run.

## Outputs and completion boundary

| File | Meaning |
|---|---|
| `analysis.json` | `aster.run-analysis.v1`: exact input hashes/sizes/capture times; reconciled tracks; failures; timing distributions; source transitions; resource observations; warnings and inconsistencies. Always emitted for valid input documents, including incomplete runs. |
| `analysis.md` | Human-readable summary, including every recorded failed check/sample and any reconciliation error. |
| `timeline.svg` | Standalone schematic of reported wall-clock windows, failed records and source identity transitions. Bars are not continuous uptime. |
| `review-run.json` | `schema_version: aster.review-run.v2`, compatible with `scripts/build_fox_review_deck.py`. Emitted only after both tracks meet the completion gate. |

There are now **two separate conclusions**:

1. `elapsed_reconciled_complete` requires the producer's complete flag, monotonic elapsed and actual timezone-aware UTC start/finish span of at least **28,800 seconds**, agreement within two seconds, and fully reconciled summary/journal records. Invalid required check/observation timestamps, missing CPU execution durations, and an input changing during its read block this conclusion.
2. `coverage.adequate` requires repeated functional cycles/observations and adequate coverage of the producer's configured observation schedule. A single observation followed by eight hours on the producer clock has elapsed duration, but does **not** have adequate sampled coverage.

Final `review-run.json` additionally requires every retained source-identity transition to contain consistent verified-release evidence: `verified: true`, `source: release_manifest`, `disposition: verified_manifest`, `dirty: false`, and an empty mismatch list. A bare true flag does not override contradictory fields; missing required fields are unknown. This remains retained startup file-verification evidence, not independent process attestation. It is emitted only when both tracks meet elapsed reconciliation, scheduled coverage and source-verification requirements and every supplied input (including optional resource CSV) was stable during its read. `validate_review_contract` in the analyzer is the shared fail-closed validator used by the deck builder; missing coverage, pause or verification fields are rejected. The shared validator also checks coverage gap totals and timestamp spans, matching observation/cycle counts, retained commit-list consistency, and recomputed verification counts. The stronger contract is **`aster.review-run.v2`**, so earlier v1 summaries cannot silently acquire the new meaning.

Recorded failures do not prevent completed observation coverage: they remain failed observations. Completion is neither continuous uptime nor eight hours of uninterrupted functional exercise. Paused health-only time is reported separately, with its actual observations required.

### Transparent scheduled-coverage rule

For a full CPU cycle, the expected next-cycle boundary is `max(cycle_start + configured_interval, cleanup_utc + cleanup_duration_seconds)`. Thus a legitimately long recorded cycle is accounted for using its actual execution finish rather than mislabeled as a missing sample. Required CPU checks are serial: each reported execution end must be no later than the next check start or the reported run finish, allowing only **0.002 seconds** for durations rounded to milliseconds. A duration extending beyond the run or overlapping later checks is contradictory evidence and blocks elapsed reconciliation; it cannot manufacture coverage. A GPU observation has no retained execution-finish timestamp: its supported schedule window ends at `observation_utc + configured_interval`; the analyzer cannot excuse a long gap by assuming a slow frame download.

The analyzer takes the union of those schedule windows, clipped to the actual run window, and reports every uncovered leading, intermediate and trailing interval. **A fixed two-second scheduling/bookkeeping allowance** is declared in code (`SCHEDULING_TOLERANCE_SECONDS`), reflecting the CPU producer's idle polling of up to one second plus bookkeeping. It is not estimated from successful observations or adjusted to make this run pass. Any uncovered interval exceeding that allowance makes coverage inadequate. Even tolerated gaps retain their exact timestamps and contribute to the reported total unobserved seconds. At least two repeated functional cycles or observations are required to establish sampling over time.

An explicit CPU pause removes that interval from functional cycle windows. Only matching `paused_read_only_health` checks may cover it, using the producer's documented ten-second pause cadence and actual check execution duration. A preceding cycle's interval cannot hide missing pause observations. Startup-check execution is separately identified, and never described as functional cycle activity. `functional_observation_window_seconds`, `health_only_pause_seconds` and `startup_check_seconds` describe schedule windows, **not continuously observed service availability**.

The final contract has `tracks.fixed_api` and `tracks.gpu_observer`. Each contains `complete`, `elapsed_reconciled_complete`, start/finish/elapsed, `cycles`, `cycle_unit`, `failures`, full `coverage`, `pause_seconds`, `pause_events`, `availability_intervals`, `source_identity`, `observed_commits` and `source_transitions`. CPU cycles are full functional cycles; GPU cycles are samples. The primary identity is the last observed source, while every observed revision remains in `source_identity.deployment_commits` and `observed_commits`. `source_identity.verification` retains verified/unverified/unknown transition counts, and the full source transitions retain their original verification fields. This does not claim a single-release GPU soak. Exact input hashes and capture metadata also accompany the final contract.

## Reconciliation and measurement semantics

The API producer writes a `check` record for startup, each functional check, each cleanup and any paused health check. The analyzer compares the complete summary check list against journal check records, including content and order. It independently groups positive cycle IDs and requires the six ordinary checks, any enabled three planning checks, and final cleanup exactly once. The producer increments its `completed_cycles` counter before cycle work, so a snapshot during a cycle can legitimately expose a temporary mismatch. The analyzer flags that mismatch rather than promoting a started cycle to completed work.

GPU `observation` indices must be contiguous from zero. Journal sample count, failed count and failure list must agree with the summary. Malformed lines are reported with line number and SHA256; a final unterminated line is never silently discarded. Valid earlier records remain available for analysis, but malformed input blocks final completion. Every input is read once into bytes and its hash and size identify exactly those bytes. Files are captured separately, so this is **not an atomic multi-file snapshot**. File size/mtime changes during an individual read are recorded and block finalization. Sequential cross-file capture can still produce a transient inconsistency; this remains a reported error rather than an automatic repair.

Health latency uses the journal's actual completed `/api/health` HTTP request `elapsed_ms` values, with linear-interpolated p50/p95/p99. HTTP error status counts remain visible. Transport errors have no elapsed latency in the producer format and are listed separately; the analyzer does not substitute a timeout value. The fixed CPU evaluator normally retains health timing only at startup and while paused, so its latency distribution is not a measurement of every functional cycle.

Frame ages use values retained beside the exact downloaded GPU image metadata. Missing ages are not replaced with zero; failed samples remain failed even if other fields were captured first. Fractions refer only to recorded passing checks/samples, **not continuous service uptime**. Sequences of failed samples, gaps exceeding 1.5 sampling intervals and the leading/trailing time outside retained observations are reported without inventing an outage start, duration or cause.

HTTP 4xx responses can be intentional negative-test results. They are not automatically counted as failed checks. Conversely, an actual failed observation is never erased or reclassified as an acceptable deployment event. Deployment records can contextualize a failure in a separate human review; this analyzer does not infer causation from temporal coincidence.

Commit and `checked_at` transitions come from retained health identities. A changed `checked_at` indicates changed startup verification context; it does not prove a crash or successful recovery by itself. Most fixed API cycles do not retain a health response body, so the single fixed startup identity is not continuous source attestation.

## Resource CSV limits

The supplied resource sampler began around **20:10:39 UTC**, after the experiments began around 19:47. The CSV's first actual measurement is 20:10:40.015. It covers its own observed interval, not the full eight hours. Numeric columns report count, minimum, maximum, median, first, last, endpoint difference and endpoint difference per hour. These are descriptive endpoint trends, not fitted leak estimates or causal attribution.

The NVIDIA CSV timestamps omit a timezone. The analyzer explicitly assumes UTC for their `YYYY/MM/DD HH:MM:SS.fraction` form based on this experiment context, and reports how many timestamps required that assumption. Other missing/unrecognized timestamps remain unparsed. Units and original column names are preserved. Static renderer and other processes can contribute to device memory/utilization; the output cannot certify absence of memory leaks or assign all consumption to the interactive app.

## Interim evidence and tests

The historical interim artifacts below were produced by the **earlier analyzer**, whose exact hash is retained in each JSON. They remain unchanged as historical evidence; they do not demonstrate the revised v2 completion gate. The first supplied GPU prefix contains **145 observation samples, one failure and four observed commits**. The separate API snapshot has **15 full cycles, 151 checks and zero failures**. Both are incomplete. Their capture times differ, which is explicit in the input manifest. See [interim analysis](run-analysis/interim-2100/analysis.md) and [timeline](run-analysis/interim-2100/timeline.svg). No final `review-run.json` was generated from this prefix. A [second analysis](run-analysis/interim-2105/analysis.md) captures the independently advancing API ledger at 16 full cycles / 161 checks while deliberately reusing the same 145-sample GPU prefix; its exact input hashes and capture times distinguish those observations.

`tests/operator_run_analysis_test.py` covers short runs, a single observation plus an eight-hour clock, invalid required UTC, changed-during-read detection, truncated tails, count mismatch, multiple revisions with retained failure, missing final coverage/verification, an unverified intermediate deployment, contradictory dirty/mismatching manifest flags despite `verified: true`, incomplete cycles, long CPU execution, contradictory cleanup durations beyond run finish or subsequent checks, explicit health-only pauses, hidden pause gaps, and resource interval/timezone assumptions.

```bash
.venv/bin/python -m pytest tests/operator_run_analysis_test.py -q
```

These tests establish the analyzer's reporting boundaries. The analyzer checks internal consistency of the actual producer records; it does not authenticate logs or protect against a deliberately fabricated but internally consistent ledger. Input hashes identify bytes, not their trustworthiness. They do not validate the park model or business outcomes.

The earlier v1 shape was checked with a clearly synthetic temporary fixture, not an experiment result. The v2 deck consumer now imports the analyzer’s shared validator directly; its independent fixture verification is recorded by the deck reviewer. No historical interim PDF is rewritten by this analyzer.

### Revised v2 checkpoint, still incomplete

The frozen analyzer source SHA256 for the reviewed checkpoint is `7833c30d628d603873a876b121c78870b0c4735dde2083884d12b15e06d6719d`. Its **16 focused tests pass**, including the independently reproduced serial-duration contradiction and a legitimate slow-check control.

At **2026-10-19 21:18:18 UTC**, the [idle API checkpoint analysis](run-analysis/coverage-v2-idle-checkpoint/analysis.md) captured **19 full cycles / 191 checks / zero failures**, with 5,443.408 reported elapsed seconds. Its summary and journal reconcile. It deliberately reuses the **historical GPU prefix supplied from around 20:59 UTC**: 145 samples / one failure / four deployments and 4,321.336 reported elapsed seconds. These are **not current GPU counts at 21:18**. Both tracks remain incomplete, so no final `review-run.json` was emitted. The exact input hashes and capture times are in [analysis.json](run-analysis/coverage-v2-idle-checkpoint/analysis.json).

The declared cadence rule finds adequate *partial-window* schedule coverage in both inputs. It still reports 1.730 seconds of total uncovered API schedule intervals (largest 0.367 seconds), and 1.282 seconds in the historical GPU prefix (largest 0.011 seconds). These tolerated scheduling gaps remain visible and do not become claims of continuous uptime.

An immediately preceding unpublished mid-cycle capture is preserved byte-for-byte in the ignored runtime review archive (analysis SHA256 `4233105f2b8cc31648f9f83e5a9d0834994c9bfe262742acda9791f1fe810ad5`): its summary had 181 checks while the advancing journal already held 188. The analyzer correctly reported this cross-file inconsistency and refused elapsed reconciliation. The subsequent idle capture records a new independent read after the producer finished the cycle; it does not rewrite or erase that earlier discrepancy. The files were not globally atomic snapshots, and the mismatch was not counted as an application check failure.
