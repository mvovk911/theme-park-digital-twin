# Independent HTTP review: current incidents and spatial design queries

The candidate passed **11 functional groups plus cleanup, with no failures**, through an actual isolated gateway on port 18150, from **2026-10-19 20:42:25 to 20:42:44 UTC**. The owned service used four separate databases, restarted once to verify persistence, and was stopped afterward. It did not touch the fixed eight-hour experiment, UI test service, or GPU application.

This review uses public HTTP contracts and owned process lifecycle only. The client imports no backend code and never reads or alters database tables. Source and asset files were hashed to identify the bytes under test. The report describes a working-tree candidate, rather than claiming a clean release revision.

## Results that matter to an operator

| Check | Actual observed result |
|---|---|
| Current fault without a saved forecast | A coaster fault observed under global `normal` produced a direct proposal and one verified synthetic work order. No planning evidence was required or created. The observed fault remained. |
| Duplicate submissions and restart | Three concurrent creation retries preserved identity and expiry. Three execution requests produced one command/audit effect and one receipt. Restart retained receipt and frozen creation evidence. |
| Unrelated scenario change | Moving global context from `normal` to `food_rush`, while the target fault remained unchanged, did not invalidate a direct proposal. |
| Historical comparison as optional rationale | A saved hypothetical ride-closure comparison could accompany a direct current fault under `normal`. Changing current status to operational still blocked execution. Historical context granted no authority. Missing rationale returned 404. |
| Required source stale | Paused ride SCADA aged beyond its five-second freshness interval using real wall time. Both new proposal creation and execution were rejected. |
| Unrelated ERP stale | ERP became stale while ride SCADA and CMMS stayed fresh; dispatch remained possible and the closed coaster remained closed. |
| Relevant status/order changes | A status change rejected execution. An intervening work order blocked both execution and a new proposal, with the exact current order and inspection URL in the conflict. No duplicate order appeared. |
| Shared creation identity and replay | Reusing a creation key across direct and saved-plan origins returned 409 in both directions. Direct POSTs were blocked in recorded view, while proposal GET worked. Existing saved-plan execution still worked with its scenario-bound scope. |
| Direct input bounds | Unsupported target, added action/unknown field, empty request ID and TTL outside 30–300 seconds returned 422. |
| Spatial before/after | Baseline entrance-to-food had no route; dining design had a 40.852 m authored route; closing `dining_connector_link` removed it. An accessible entrance route remained unavailable. |
| Endpoint meaning | The wheel public approach was reachable, while wheel boarding remained unreachable. Slower assumed walking speed changed time without changing path geometry. |
| Spatial independence | Route queries left audit history and scenario unchanged. During replay they preserved cursor, displayed assets and KPIs and returned the same authored-design result. |
| Spatial identities and strictness | API graph data matched hashed local artifacts, and capability/graph identities agreed. Unknown IDs, type coercions, extra fields, duplicate closures, excessive closure count, duplicate JSON keys, NaN, malformed JSON, wrong media type and oversized body were rejected. |

The required-source freshness check waited more than six real seconds. The unrelated ERP fixture had ten stale metrics and an approximately 6.3-second maximum age; the maintenance sources remained healthy. These are actual connector-clock transitions, not a mocked clock.

## Value and limits

The direct path removes the need to run and save an irrelevant forecast before handling an already observed maintenance issue. In the tested no-plan case, the application needed a proposal POST and a separate execute POST to reach a verified work-order acknowledgement. This demonstrates fewer API prerequisites than the saved-plan route; it does **not** establish faster human task completion, reduced downtime or benefit over a real CMMS's native interface. The legacy synthetic dispatch endpoint is already a shorter single-command path, so the added proposal step must earn its value through the explicit evidence, precondition checking and recoverability it provides.

The spatial service is useful for identifying an authored design gap and testing whether a proposed connection actually closes it. Its refusal to invent a route, claim boarding access, or infer accessibility is valuable. The reported 34.04-second walk is distance divided by an assumed speed, with no crowd/queue/grade integration. Neither the route nor this review demonstrates extra food-service capacity, evacuation safety, guest throughput or improved operational forecasts. The forecasting planner remains separate from this graph.

No new blocking defect was found. One deliberately unfilled coverage gap remains: this independent HTTP run did not seed an evidence database with an older model fingerprint. The current save API rejects unsupported model fingerprints, and this client did not bypass that boundary by modifying storage. The backend's separate unit coverage of old-model optional rationale is not counted as this client's evidence. Historical scenario mismatch and current-condition enforcement were tested here.

The no-mutation conclusion concerns observable audit, scenario and recorded-view state. Background live telemetry continued to advance, as expected; this review does not claim byte-identical live snapshots or perform a database-diff proof. Asset identity checks establish consistency with the candidate's files, not cryptographic authenticity or trust in an external author.

## Reproduce and inspect

```bash
.venv/bin/python operators/incident_spatial_checks.py \
  --project . --python .venv/bin/python --port 18150 \
  --output runtime/incident-spatial-review/new-run
```

The output directory must be new and the port free. The client starts and stops only its own gateway and stores four databases beneath that output directory.

- [Complete check evidence](incident-spatial-api-review/report.json)
- [HTTP journal](incident-spatial-api-review/events.jsonl)
- [Source and artifact manifest](incident-spatial-api-review/source-manifest.json)
- [Reusable HTTP client](../../operators/incident_spatial_checks.py)

The earlier maintenance review and focused stale-readback retake remain unchanged in [workflow-api-review.md](workflow-api-review.md).
