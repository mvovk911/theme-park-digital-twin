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
| `review-run.json` | `schema_version: aster.review-run.v1`, compatible with `scripts/build_fox_review_deck.py`. Emitted only after both tracks meet the completion gate. |

The gate requires each producer to report `complete: true`, a monotonic elapsed duration of at least **28,800 seconds**, and valid timezone-aware start/finish timestamps spanning at least **28,800 seconds**. UTC span and reported elapsed must agree within two seconds. All summary/journal checks must reconcile, at least one full API cycle and one GPU observation must exist, and a full non-placeholder commit identity must be retained. A partial prefix, malformed/truncated journal, short run or count mismatch cannot yield the final deck contract.

Recorded failures do not prevent a run from being *completed*: they remain counted and disclosed. Completion also does not imply uninterrupted sampling. Gaps and leading/trailing unobserved periods are reported separately. A producer's complete flag is evidence from that producer, not external process attestation.

The final contract has `tracks.fixed_api` and `tracks.gpu_observer`. Each has `complete`, `started_at`, `finished_at`, `elapsed_seconds`, `cycles`, `cycle_unit`, `failures`, `source_identity`, `observed_commits` and `source_transition_count`. CPU `cycles` counts full functional cycles; GPU `cycles` counts observation samples. `source_identity` is the **last observed identity**, with all observed revisions retained in `source_identity.deployment_commits` and `observed_commits`. This does not claim that the GPU experiment used a single release. Full identity transition details remain in `analysis.json`.

## Reconciliation and measurement semantics

The API producer writes a `check` record for startup, each functional check, each cleanup and any paused health check. The analyzer compares the complete summary check list against journal check records, including content and order. It independently groups positive cycle IDs and requires the six ordinary checks, any enabled three planning checks, and final cleanup exactly once. The producer increments its `completed_cycles` counter before cycle work, so a snapshot during a cycle can legitimately expose a temporary mismatch. The analyzer flags that mismatch rather than promoting a started cycle to completed work.

GPU `observation` indices must be contiguous from zero. Journal sample count, failed count and failure list must agree with the summary. Malformed lines are reported with line number and SHA256; a final unterminated line is never silently discarded. Valid earlier records remain available for analysis, but malformed input blocks final completion. Every input is read once into bytes and its hash and size identify exactly those bytes. Files are captured separately, so this is **not an atomic multi-file snapshot**. File size/mtime changes during an individual read are recorded as well.

Health latency uses the journal's actual completed `/api/health` HTTP request `elapsed_ms` values, with linear-interpolated p50/p95/p99. HTTP error status counts remain visible. Transport errors have no elapsed latency in the producer format and are listed separately; the analyzer does not substitute a timeout value. The fixed CPU evaluator normally retains health timing only at startup and while paused, so its latency distribution is not a measurement of every functional cycle.

Frame ages use values retained beside the exact downloaded GPU image metadata. Missing ages are not replaced with zero; failed samples remain failed even if other fields were captured first. Fractions refer only to recorded passing checks/samples, **not continuous service uptime**. Sequences of failed samples, gaps exceeding 1.5 sampling intervals and the leading/trailing time outside retained observations are reported without inventing an outage start, duration or cause.

HTTP 4xx responses can be intentional negative-test results. They are not automatically counted as failed checks. Conversely, an actual failed observation is never erased or reclassified as an acceptable deployment event. Deployment records can contextualize a failure in a separate human review; this analyzer does not infer causation from temporal coincidence.

Commit and `checked_at` transitions come from retained health identities. A changed `checked_at` indicates changed startup verification context; it does not prove a crash or successful recovery by itself. Most fixed API cycles do not retain a health response body, so the single fixed startup identity is not continuous source attestation.

## Resource CSV limits

The supplied resource sampler began around **20:10:39 UTC**, after the experiments began around 19:47. The CSV's first actual measurement is 20:10:40.015. It covers its own observed interval, not the full eight hours. Numeric columns report count, minimum, maximum, median, first, last, endpoint difference and endpoint difference per hour. These are descriptive endpoint trends, not fitted leak estimates or causal attribution.

The NVIDIA CSV timestamps omit a timezone. The analyzer explicitly assumes UTC for their `YYYY/MM/DD HH:MM:SS.fraction` form based on this experiment context, and reports how many timestamps required that assumption. Other missing/unrecognized timestamps remain unparsed. Units and original column names are preserved. Static renderer and other processes can contribute to device memory/utilization; the output cannot certify absence of memory leaks or assign all consumption to the interactive app.

## Interim evidence and tests

The first supplied GPU prefix contains **145 observation samples, one failure and four observed commits**. The separate API snapshot has **15 full cycles, 151 checks and zero failures**. Both are incomplete. Their capture times differ, which is explicit in the input manifest. See [interim analysis](run-analysis/interim-2100/analysis.md) and [timeline](run-analysis/interim-2100/timeline.svg). No final `review-run.json` was generated from this prefix. A [second analysis](run-analysis/interim-2105/analysis.md) captures the independently advancing API ledger at 16 full cycles / 161 checks while deliberately reusing the same 145-sample GPU prefix; its exact input hashes and capture times distinguish those observations.

`tests/operator_run_analysis_test.py` covers short-but-producer-complete runs, truncated journal tails, count mismatch, multiple revisions with retained failure, an incomplete cycle mislabeled completed, and the resource interval/timezone assumption.

```bash
.venv/bin/python -m pytest tests/operator_run_analysis_test.py -q
```

These tests establish the analyzer's reporting boundaries. They do not validate the park model or business outcomes.

The final-contract shape was also checked against the actual deck consumer’s `stamp` and `run_summary` functions using a clearly synthetic temporary fixture. The fixture was not published as an experiment result. Full deck-module import was unavailable in the API venv because it lacks `fitz`; AST selection allowed the real validation functions to run without installing unrelated rendering dependencies.
