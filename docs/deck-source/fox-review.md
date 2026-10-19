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

The default is explicitly **INTERIM: eight-hour observation still in progress**. It cannot declare completion based on the current clock. Supply `--run-summary path.json` only after both ledgers have finished:

```json
{
  "schema_version": "aster.review-run.v1",
  "tracks": {
    "fixed_api": {
      "complete": true,
      "started_at": "2026-10-19T19:47:34+00:00",
      "finished_at": "2026-10-20T03:47:34+00:00",
      "elapsed_seconds": 28800,
      "cycles": 1,
      "failures": 0,
      "source_identity": {"commit": "0000000000000000000000000000000000000000"}
    },
    "gpu_observer": {
      "complete": true,
      "started_at": "2026-10-19T19:47:33+00:00",
      "finished_at": "2026-10-20T03:47:33+00:00",
      "elapsed_seconds": 28800,
      "cycles": 1,
      "failures": 1,
      "source_identity": {"commit": "0000000000000000000000000000000000000000", "deployment_commits": []}
    }
  }
}
```

The example is a schema illustration, **not run evidence**; replace all values from actual ledgers. The generator rejects placeholder commit hashes, incomplete tracks, missing timezone, less than 28,800 elapsed seconds, timestamp durations below eight hours, nonpositive cycle counts and negative failures. `cycles` means API cycles or observer samples as appropriate. `source_identity.commit` is the tool/source commit; GPU deployment revisions belong in `deployment_commits` because this observer spans development deployments. Both tracks appear with their actual start/end, elapsed duration, cycles/samples, failures and source commits. Nonzero failures remain visible and completion is never described as a pass. Full supplied identity objects remain in the manifest. This validator checks summary consistency, not independent truth of a ledger.

## Source scope

- NVIDIA's FOX announcement and repository research explain the architecture; no installed FOX package is claimed.
- `gpu-incident-afa84a1/report.json` and screenshots establish actual six-check GPU/browser behavior.
- Native dining reports and PNGs bind matching camera, layer, image and graph identities.
- `docs/reviews/2026-10-19-evidence-and-policy-review.md` independently recomputes 324-case accounting; it describes negative benefit and modeling omissions.
- `docs/progress.md` records the 407-check local and 40-check browser checkpoint. Counts retain that scope rather than implying all GPU runs used that suite.
- `docs/experiments/2026-10-19-run-status.md` describes the ongoing two-track experiment and known deployment interruption. Final counts require the explicit summary above.
