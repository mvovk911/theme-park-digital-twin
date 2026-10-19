# Independent API operator and eight-hour evaluation

The operator in [`operators/api_operator.py`](../operators/api_operator.py) is a
**deterministic HTTP policy and contract evaluator**, not an LLM agent. It consumes
published API contracts and actual HTTP responses; it imports no backend modules,
reads no database, and cannot operate physical equipment. This makes it a useful
independent consumer of the same surface a future reasoning agent would use.

Its first local run on 19 October 2026 completed one approximately ten-second
cycle with eight passing checks. That proves a short API integration run only,
not eight hours of reliability, GPU rendering quality, calibrated prediction or
real-world value. The source identity returned by the server is preserved in each
run's summary. The eight-hour run must have its own measured elapsed time and
completion status.

## Observe, compare, act, verify

1. Refuse a gateway that does not explicitly identify its data as synthetic.
   Require live view and live source modes at the beginning of an exclusively
   scheduled evaluation.
2. Read canonical state, source health and available scenarios. Ask the existing
   read-only comparison endpoint about all seven scenarios; verify that live
   scenario and action audit remain unchanged.
3. Run six predefined incident/action pairs. Check target quality before submitting
   an action, supply a unique durable request ID, inspect acknowledgement and
   postconditions, and record every KPI before and after the action.
4. Attempt concurrent identical retries, a conflicting retry payload, unknown and
   inapplicable actions, and a retry after reset. Require immutable acknowledgement
   and no duplicate audit/work-order effects.
5. Pause a source; inject valid, duplicate, conflicting, wrong-unit and late events;
   verify source ownership, freshness and canonical state. Abstain when required
   telemetry is stale. Exercise explicit outage and recovery. Separately inject a
   ride-status disagreement and require the model/source conflict to remain visible.
6. Inspect a historical record. Verify that action, scenario and source-mode writes
   are rejected, historical assets/KPIs stay immutable, and live ingestion continues.
7. Return to live, restore changed sources to live and reset the synthetic scenario.
   Record cleanup failures as failures rather than claiming the system was restored.

All outcomes are append-only JSONL records. The HTTP journal records method, path,
status, latency, request and SHA256 of the response; check evidence stores the
relevant receipts, conflicts and KPI values. Full canonical snapshots may contain
operational data in a real deployment, so this evaluator is restricted to the
synthetic project. Runtime evidence remains outside Git until reviewed and copied
into a revision-specific public evidence folder.

## What counts as useful

| Workflow | Verified synthetic outcome | What the result does not establish |
|---|---|---|
| Closed ride → dispatch | One work-order identity; closed ride stays closed | Repair, safe reopening or reduced downtime |
| Show surge → guidance | Illustrative queue mean falls without losing a ride | Guest compliance or pedestrian safety |
| Heatwave → staff | Two qualified simulated staff; cost increases | Fewer medical events or reduced queue time |
| Power fault → shed flexible load | Lower modeled load; ride availability unchanged | Electrical protection or measured energy savings |
| Water leak → simulated repair | Flow/status recover in the model | Physical isolation or net water savings |
| Food rush → replenishment | Inventory increases; remaining service constraint is visible | Faster service or real stock arrival |

The current before/after actions occur at different simulator ticks. These are
postcondition checks, **not controlled counterfactual estimates**. Ambient demand
and utility drift can alter deltas. Queue mean excludes closed/faulted assets and
is not a guest-weighted service metric. Water sums monitored flows, including
circulation. An action returning HTTP 200 is never sufficient evidence of value.

## Planner evaluation additions

The new planning API is being developed separately. Once its published contract is
available, extend this black-box consumer to require:

- A frozen canonical baseline revision, input provenance and explicit assumptions.
- An automatic do-nothing baseline, bounded time horizon and comparable outcomes.
- Identical exogenous demand draws for alternatives, with low/central/high demand
  sensitivity reported separately from statistical confidence.
- No live/audit mutation from simulation; reproducible branches from the same
  frozen input, including connector-injected observations.
- Stale/missing/conflicting required inputs produce abstention, not confident advice.
- Zero qualified staff prevents staff-dependent action. Delayed intervention cannot
  receive benefits before its scheduled activation. An unneeded intervention in a
  normal period must be allowed to lose to doing nothing.
- Closed-ride demand remains visible as unmet/redistributed demand; dropping a long
  queue from an average must not manufacture a benefit.
- Constraint violations remain visible and cannot enter the shortlist as feasible.

No planner recommendation currently authorizes a physical action. The legacy
`POST /api/actions` has durable retry identity but no expected-state/freshness
prerequisite, and this operator's quality check is a client-side gate. Between
observation and execution the world can change. A real execution broker would need
versioned preconditions, authorization, bounded command lifetime, vendor
acknowledgement and reconciliation; safety-related ride control stays with the
certified local system.

## Reproduce a short run

Use an isolated gateway/database or a scheduled exclusive window. The evaluator
changes shared scenario, replay and source modes; it preserves audit history and
receipts, but resets synthetic operational state. It is not suitable for a gateway
where another operator is working.

```sh
PARK_DB="$PWD/runtime/operator-local/park.db" \
PARK_REPLAY_DB="$PWD/runtime/operator-local/replay.db" \
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 18120

python3 operators/api_operator.py \
  --url http://127.0.0.1:18120 \
  --output runtime/operator-local/check-001 \
  --allow-synthetic-writes
```

Each output directory must be new. The script uses only the Python standard
library. HTTP calls have bounded timeouts. Mutation requests are not automatically
retried after transport failure; an uncertain action must be reconciled using its
recorded request ID.

## Eight-hour run

```sh
python3 operators/api_operator.py \
  --url http://127.0.0.1:18120 \
  --output runtime/operator-soak/run-001 \
  --duration-seconds 28800 \
  --interval-seconds 300 \
  --allow-synthetic-writes
```

This schedules approximately 96 cycles over eight actual elapsed hours. The
summary updates at least every ten seconds while waiting. `complete` is true only
after the requested wall-clock interval is reached; `failures` must also be zero
for a clean result. Completion does not imply success. Interrupted runs preserve
their partial results and do not claim eight-hour completion. A healthy eight-hour
API run is one reliability observation, not evidence of deployment-grade uptime.

Use a separate gateway for destructive fault tests during visual design/browser
work. For a shared GPU gateway, the coordinator must schedule exclusive operator
windows or run an observer-only monitor instead. GPU frame freshness, native picks,
source/frame identity and visible UX remain separate acceptance checks; this
HTTP-only evaluator does not claim to have inspected rendered images.

## Shared-app observation without mutations

[`operators/observe.py`](../operators/observe.py) performs only HTTP GETs and can
run alongside browser/design activity. It records health latency, canonical view,
source quality and advancing simulator tick. With `--require-renderer`, it fetches
actual JPEG bytes, verifies render-time age and required image-bound provenance,
and saves one original frame per hour by default. It does not infer frame metadata
from a newer status response, and it does not equate a fresh render with fresh
source telemetry. These samples establish availability/provenance, not visual
quality or interaction correctness.

```sh
python3 operators/observe.py \
  --url http://127.0.0.1:18765 \
  --output runtime/operator-observer/run-001 \
  --duration-seconds 28800 --interval-seconds 30 --require-renderer
```

Failures remain in the journal and summary even after recovery. A run can finish
its requested duration with `complete: true` and a nonzero `failed_samples` count;
that is a completed observation with failures, not a passing reliability claim.

### Coordinate mutation windows

Pass `--pause-file runtime/operator.pause` to the mutating evaluator. Creating that
file requests a pause; it does not interrupt a partly completed contract test.
Wait until `summary.json` reports `phase: paused` before another process changes the
shared app. The evaluator first finishes the current cycle and its cleanup, then
performs read-only health checks approximately every ten seconds while paused.
Remove the file to resume. `pause_events` and `pause_seconds` distinguish paused
wall-clock exposure from active mutation cycles. If the duration expires while
paused, the evaluator does not perform another mutation just to finish.

Pass `--include-planner` once the gateway exposes the new planning routes. This adds
black-box frozen-input determinism, no-op equality, shared sensitivity demand,
guest conservation, unavailable staff, intervention-after-horizon, zero guidance
compliance, invalid request, replay, canonical injected stock and stale-source
abstention checks. These evaluate model consistency and workflow behavior; they do
not independently validate the model's assumed effect sizes.

### Supervised isolated experiment

`operators/supervise.py` starts one backend on a free loopback port with dedicated
park/replay databases, then runs the planner-enabled evaluator. Use a frozen source
tree and launch the supervisor in a detached process group. It records source-file
hashes, health identity, process IDs and start/end timestamps. Unexpected backend
exits are recorded and may be restarted at most three times; an operator process
is never silently restarted. The backend and operator stop at experiment completion
or supervisor termination. A restart remains a reliability failure even if later
checks pass.

The client also tests twelve separately selected scenario/assumption combinations
(demand multiplier, available staff and guidance compliance). This is assumption
stress testing, not held-out empirical forecast validation. The post-horizon staff
case explicitly tests that doing nothing can dominate a costly intervention with
no benefit. Production validation still requires real observations, predetermined
accuracy metrics, withheld operating days and operational review.
