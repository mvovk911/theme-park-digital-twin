# Aster Park — FOX-inspired review deck

Editable five-page landscape review of implemented behavior and remaining value questions. The original `docs/project-concept.pdf` is unchanged. Edit the JSON copy below, or the vector layout in `scripts/build_fox_review_deck.py`. Existing native images and actual browser captures are reused; the generator creates no synthetic evidence.

```deck-json
{
  "title": "Aster Park / from digital shadow to decisions",
  "subtitle": "FOX-inspired operations proof of concept • evidence review • 19 October 2026",
  "architecture": {
    "title": "Observe. Compare. Request. Verify.",
    "subtitle": "An operations data backbone, with explicit decision and command boundaries.",
    "steps": [
      ["OBSERVED", "10 synthetic source domains", "Asset IDs, units, timestamps, ownership and quality."],
      ["ALTERNATIVES", "Frozen what-if branches", "15–120 min; queue/resource balances; common demand cases."],
      ["REVIEW", "Do nothing + simple rule", "Waiting, served/backlog, cost, constraints and adverse cases."],
      ["BOUNDED REQUEST", "One synthetic executor", "Maintenance proposal, expiry, current preconditions and explicit execute."],
      ["VERIFY", "Receipt + readback", "Exact work-order identity; accepted workflow does not mean repaired."]
    ],
    "api_groups": [
      ["SYNTHETIC READ FEEDS", "Ride SCADA • ticketing • vision • CMMS • ERP/POS • workforce • BMS • water • weather • GIS"],
      ["CONTEXT / IMPLEMENTED", "OpenUSD + native OVStage/OVRTX; quality-aware live view, replay, saved comparisons and static design queries."],
      ["ENTERPRISE / PROPOSED", "Vendor read adapters, authenticated CMMS writes, qualified roster evidence and approved signage requests."]
    ],
    "boundary": "FOX-inspired architecture; NVIDIA FOX, NemoClaw and OpenShell are not installed. Spatial queries and weather previews remain separate from the uncalibrated forecast."
  },
  "incident": {
    "title": "An incident can reach a work order directly",
    "subtitle": "Actual Horde L40 app/browser acceptance • verified application release afa84a1",
    "checks": ["Live asset entry selects the target without a write or forecast", "Explicit direct execution creates an order; ride remains closed", "Reload retrieves the accepted receipt using GET only", "Mobile layout fits the viewport", "Saved-comparison workflow still functions", "Lost response + reload retries the same request and expiry"],
    "outcome": "4 scripted steps instead of 7 via a saved comparison. This is a UI path comparison, not a measured human productivity gain.",
    "boundary": "Current status, inspection and open orders are frozen with source evidence. Dispatch accepts a synthetic workflow; it does not repair equipment or reopen a ride."
  },
  "spatial": {
    "title": "Does the dining connection fix access?",
    "subtitle": "Matched native OVStage/OVRTX captures • same camera • separate authored design layer",
    "before": "BASELINE: unreachable in authored graph",
    "after": "DINING DESIGN: 40.852 m route in the graph",
    "controls": ["Close connector → unreachable", "Step-free filter → unreachable; entry threshold unresolved", "34.04 s assumes 1.2 m/s; no density or queue delay"],
    "boundary": "Static geometry and a partial authored graph. This is not certified accessibility, physical guest guidance, spare service capacity or forecast validation."
  },
  "value": {
    "title": "A useful test can reject the cleverer policy",
    "subtitle": "Independent policy accounting • 324 synthetic cases • 972 outcomes • source d3dca3d",
    "results": [
      ["216 / 324", "Planner and simple rule choose identical schedules"],
      ["108", "Different choices: extra staff costs EUR56 per case"],
      ["52 / 108", "Extra staff produces no waiting improvement"],
      ["92 / 324", "Doing nothing strictly dominates the planner choice"]
    ],
    "tradeoff": "Across all cases: +1.701 completed service visits, −28.883 guest-min waiting and +EUR18.667 labor versus the simple rule. Different-choice subgroup: +5.102 visits, −86.648 guest-min and +EUR56. These are grid averages, not expected real outcomes.",
    "validation": "Local checkpoint: 407 CPU/application checks passed; three browser modules skipped there. Separate browser environment: 40 checks passed. Actual GPU incident walkthrough: six checks. Scopes and revisions differ; these are not one combined production qualification.",
    "boundary": "The evaluator omits minimum-coverage constraints, donor depletion/setup loss and replenishment cost. Doing nothing is not advice to understaff. No measured ROI or real park productivity claim."
  },
  "pilot": {
    "title": "A narrow pilot can answer the value question",
    "subtitle": "Start with one ride, its maintenance process and one duty-manager workflow.",
    "steps": [
      ["1 / Establish evidence", "Map OEM/CMMS asset IDs, timestamps, inspection states and actual work-order history. Read-only integration first."],
      ["2 / Measure the task", "Compare alert-to-verified-order time, clicks, incorrect/duplicate orders and operator understanding against today's workflow."],
      ["3 / Test decisions", "Calibrate arrivals, service, staffing qualifications, delivery delays and cost. Keep do-nothing and simple-rule baselines."],
      ["4 / Expand deliberately", "Only then add a scoped authenticated CMMS request; validate path geometry before coupling guest movement to forecasts."]
    ],
    "boundary": "Next success criterion: a verified operational outcome that an operator values, with measured effort, error rates and clear limits."
  }
}
```

## Reproduce and inspect

Use a separate tooling environment; do not change application dependencies:

```bash
python3 -m venv /tmp/park-review-tools
/tmp/park-review-tools/bin/pip install -r docs/deck-source/requirements-fox-review.txt
/tmp/park-review-tools/bin/python scripts/build_fox_review_deck.py
```

Default output: `runtime/fox-cycle-20261019/review-deck/fox-review-interim.pdf`, five PNG page previews, a text/layout validation report, and a manifest of input hashes. The PDF uses embedded DejaVu Sans fonts and deterministic ReportLab metadata (`invariant=1`). The manifest captures full source/report identities; footer links point to source files at the selected Git revision. Repeat with identical inputs and options to obtain the same PDF bytes. Optional `--source-revision <40hex>` pins those links; by default the current HEAD is used. `--output` selects a separate destination; the generator refuses the original concept PDF.

The default is explicitly **INTERIM: eight-hour observation still in progress**. It cannot declare completion from a clock or a count alone. Final mode consumes the analyzer's `aster.review-run.v2` contract through the shared dependency-free `validate_review_contract` in `operators/analyze_fox_run.py`. The old minimal v1 contract is rejected. There is one declared two-second tolerance, not separate producer and deck thresholds.

Generate the final contract from stable completed producer files using the offline analyzer, then supply its `review-run.json` to the deck. If the analyzer cannot establish adequate schedule coverage and verified source identities, it does not emit that file; retain the interim deck and publish the detailed analysis/limitations instead. Do not construct a completion summary manually to bypass missing observations.

```bash
python3 operators/analyze_fox_run.py \
  --api-dir <completed-api-directory> --gpu-dir <completed-observer-directory> \
  --output <new-analysis-directory>
/tmp/park-review-tools/bin/python scripts/build_fox_review_deck.py \
  --run-summary <new-analysis-directory>/review-run.json \
  --source-revision <published-evidence-commit> --output <new-final-pdf-path>
```

The shared v2 contract requires:

| Evidence | Required contract data and interpretation |
|---|---|
| Stable input capture | Top-level `input_capture_consistent: true`; analyzer refuses files changed during its reads. |
| Elapsed completion | Both tracks have `complete` and `elapsed_reconciled_complete`; actual timezone-aware start/end and monotonic elapsed each span at least 28,800 seconds and agree within 2 seconds. |
| Repeated observations | Positive repeated functional cycles/API checks or GPU samples; one t=0 sample plus eight elapsed hours cannot establish coverage. `cycle_unit` distinguishes functional cycles and observation samples. |
| Schedule coverage | `coverage.adequate`, configured interval, fixed 2-second scheduling tolerance, observed count, complete `uncovered_intervals`, total/max unobserved seconds, functional-window duration, startup duration and health-only pause windows. The declared union-of-schedule-windows method is not continuous observation. |
| Pauses | `pause_seconds` and full `pause_events` remain separate. Explicit paused health checks do not count as functional interventions. |
| Verification | `source_identity.verification` retains verified/unverified/unknown transition counts, and `source_transitions` preserves full observed identities. Unknown or unverified source evidence cannot finalize. `source_identity.commit` is the last observed application source, not necessarily the observer tool or the whole run's only release. |
| Outcomes | Cycles/samples, failed checks/samples and source revisions remain visible. A recorded failure is an observation and is never silently changed into a pass. |

The final badge is **8H SAMPLED REVIEW**, not a generic uptime-completion claim. Page 5 shows each track's actual UTC window, elapsed duration, cycle/sample count, failures, configured cadence, total/max uncovered time, functional observation windows, recorded pauses, health-only pause windows, identity-verification counts and last observed source. It explicitly states that schedule windows plus the fixed allowance do not establish continuous uptime, and that GPU request duration is unavailable. Full leading/inter-sample/trailing interval details, warnings, pause events and source transitions remain in the supplied contract and PDF manifest; the shared validator source hash is also recorded.

The input cap is 4 MiB so hundreds of retained interval timestamps are not discarded to fit the old 64 KiB envelope. This validator checks consistency of the supplied summary and its required evidence fields; it is not a cryptographic attestation of independent ledger truth. The published interim PDF is unchanged by these final-mode corrections.

## Source scope

- NVIDIA's FOX announcement and repository research explain the architecture; no installed FOX package is claimed.
- `gpu-incident-afa84a1/report.json` and screenshots establish actual six-check GPU/browser behavior.
- Native dining reports and PNGs bind matching camera, layer, image and graph identities.
- `docs/reviews/2026-10-19-evidence-and-policy-review.md` independently recomputes 324-case accounting; it describes negative benefit and modeling omissions.
- `docs/progress.md` records the 407-check local and 40-check browser checkpoint. Counts retain that scope rather than implying all GPU runs used that suite.
- `docs/experiments/2026-10-19-run-status.md` describes the ongoing two-track experiment and known deployment interruption. Final counts require the explicit summary above.

## Published interim artifact

The review PDF is [docs/fox-review-interim.pdf](../fox-review-interim.pdf), with source/evidence links pinned to `c6d15163b4773bb23796ac6f6ce77131d4d69440`. It remains an **interim** review while the eight-hour ledgers run. The cover preview is [review-deck-cover.png](../images/fox-cycle-20261019/review-deck-cover.png); all five full-size page previews are kept under the ignored runtime review directory. Reproducibility and text-bound validation records are under [fox-review-interim/](fox-review-interim/).

Rebuild the published PDF from this pinned source/evidence checkpoint:

```bash
/tmp/park-review-tools/bin/python scripts/build_fox_review_deck.py \
  --source-revision c6d15163b4773bb23796ac6f6ce77131d4d69440 \
  --output docs/fox-review-interim.pdf
```

The generator initially writes its `.manifest.json`, `.validation.json` and five PNG previews beside the PDF. Packaging moves the two JSON records to `docs/deck-source/fox-review-interim/`, copies page 1 to the cover path above, and retains full page previews in `runtime/fox-cycle-20261019/review-deck/public-pinned/`. Moving these records does not alter the PDF or its input hashes. PDF metadata and content remain deterministic; the full editorial Markdown hash also records non-slide reproduction instructions.
