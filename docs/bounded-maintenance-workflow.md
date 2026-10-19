# From a current incident or saved comparison to a bounded maintenance workflow

This first execution slice supports one action: **create a synthetic maintenance work order** for a current fault or inspection issue. It does not repair equipment, reopen a ride, actuate an external system or claim that a technician completed work. Its successful outcome is `accepted_workflow_not_repair`.

An operator can start directly from a current fault or inspection issue, without running or saving a forecast. Alternatively, a saved comparison supplies an action reference and historical rationale. Both entry points share one proposal builder, store and executor. Its hash, numerical reproduction and shortlist are never treated as execution authority. The workflow independently checks current canonical observations and current synthetic work orders before creating a proposal, and again immediately before accepting a new command. An explicit execute request is required; the planner does not execute automatically.

## HTTP contract

`GET /api/workflows/capabilities` lists the supported action, four CMMS-backed targets (`RIDE_COASTER`, `RIDE_WHEEL`, `POWER_HUB`, `WATER_PLANT`), required observations and unsupported actions. Staff reassignment, routing, load shedding, leak repair, replenishment and reset have no executor in this service. Future scheduled actions are unsupported; the saved action must have `at_minute: 0`.

Create a proposal directly from a current incident:

```http
POST /api/workflows/incidents
Content-Type: application/json

{
  "asset_id": "RIDE_COASTER",
  "request_id": "operator-session:create-incident-1",
  "ttl_seconds": 120
}
```

The action is fixed to `dispatch_maintenance`; callers cannot supply another action. Optional `rationale_bundle_id` references an already saved comparison. The service checks its payload digest against its identifier and retains its model/plan references as context. It does not require the historical model to reproduce on today's deployment, match today's scenario, or approve the action. A missing bundle returns 404; a changed payload fails integrity checking. Omit the field when a forecast did not inform the incident. Current target observations remain mandatory in every case.

Alternatively, create a proposal from an already saved evidence bundle:

```http
POST /api/workflows/proposals
Content-Type: application/json

{
  "bundle_id": "<saved evidence SHA256>",
  "branch_id": "simple_rule",
  "action_index": 0,
  "request_id": "operator-session:create-inspection-1",
  "ttl_seconds": 120
}
```

Both responses contain `proposal` and `idempotency.replayed`. `origin` is `current_incident` or `saved_plan`. A proposal has a server-generated `id`, timestamps, the exact selected action/target, evidence references, fresh relevant preconditions, a creation revision for traceability, and a stable internal command request ID. The accepted TTL range is 30–300 seconds. Save the create request ID to recover a lost response: the same ID and same normalized payload returns the original proposal; a changed payload returns 409. Creation IDs share a namespace across both entry points, so reusing one for the other route also returns 409. A retry does not renew expiry or silently rebase the proposal onto newer state.

New proposals preserve `creation_observation`: capture time, accepted-state revision, asset identity/type, scenario context, current open-order IDs and the three required observed values. Each value retains its original source identity, source and ingestion timestamps, synthetic provenance and quality/freshness metadata. This evidence is frozen at creation and remains unchanged after later ticks, execution, retry or restart; command receipts and subsequent readbacks are separate evidence. Existing older proposals remain readable without this additive field.

Execute that exact proposal with a separate stable caller request ID:

```http
POST /api/workflows/proposals/<proposal-id>/execute
Content-Type: application/json

{"request_id":"operator-session:execute-inspection-1"}
```

`GET /api/workflows/proposals/{id}` reopens the durable proposal, receipt and most recent verified readback. `GET /api/workflows/proposals?limit=100&offset=0` lists stored records. Reads work in recorded view. Creating or executing proposals requires live view and returns 409 while replay is selected, including retry POSTs; historical acknowledgements remain readable through GET.

## Fresh conditions, rather than a constantly changing whole-state hash

Saved-plan proposals require the selected hypothetical scenario to be currently active. A saved “coaster closure” forecast cannot dispatch against a normal current park through that route. Direct incident proposals instead bind actual target observations: a source-observed current fault can justify inspection even while the global simulator scenario is `normal`. In both cases, the target must currently have a fault or an inspection issue. A ride being closed alone is not treated as a maintenance diagnosis. A current open work order blocks a new proposal.

The required canonical fields are status, inspection status and open-work-order count. Each must have good quality, a known synthetic source, synthetic provenance and a source timestamp inside its declared freshness interval. The observed CMMS count must agree with the synthetic work-order database. Missing, stale, uncertain, non-synthetic or contradictory input blocks the workflow.

The stored predicate includes target identity/type, status, inspection status, relevant source ownership, observed count and exact open-work-order IDs. Saved-plan proposals additionally bind the scenario (`precondition_scope: scenario_and_target`); direct incident proposals use `precondition_scope: target`, with scenario recorded only as historical context. Old proposals without this discriminator retain the original scenario-bound behavior. Execution checks the applicable predicate again. New timestamps or ordinary simulator ticks can advance the full accepted-state revision without changing these conditions; such harmless changes do not invalidate a proposal. An unrelated global scenario change does not invalidate a direct proposal when its target conditions remain identical. A stale unrelated ERP source likewise does not prevent dispatch when all required maintenance-specific evidence remains fresh. A new work order, changed inspection/status or changed source ownership does invalidate either proposal; scenario changes additionally invalidate saved-plan proposals. Conflict responses include changed predicate fields and the current work-order IDs. If an order already exists, `next_step` directs the caller to inspect it through the provided asset-detail URL instead of repeatedly creating another proposal. Expiry is checked against the current connector clock before a new dispatch.

This is an application contract for synthetic data. It is not a real operator-authentication or role-authorization service, and existing legacy synthetic `/api/actions` endpoints remain separate. A real CMMS connector would require actual identity, scoped credentials, vendor state-transition rules and deployment access controls before external writes were enabled.

## Durable execution and crash recovery

Before dispatch, the workflow binds the caller's execution request ID to the proposal and persists `execution_intent_recorded` in its own database. It then invokes the existing synthetic action implementation with `request_id: proposal:<proposal-id>`. The park database atomically stores the work-order change, audit and immutable command receipt using its existing retry contract.

The workflow reads that exact work-order ID back from the synthetic database, records its current status and the asset's observed status, and persists `accepted_workflow_not_repair`. The work-order database read time does not refresh ride telemetry. `asset_status_evidence` separately retains status value, source ID, source timestamp and quality, including stale status during historical receipt recovery. Receipt and readback are different evidence: the receipt proves acceptance at its original time; readback states what the synthetic database contains at the recorded readback time. `physical_effect` and `physical_completion` remain false. A coaster closed by the fault stays closed after dispatch.

The two databases do not share a distributed transaction. If the park command commits but workflow completion or the HTTP response is lost, retry the same proposal and caller execution ID. The durable park receipt is detected before checking expiry or new operational conditions, and its work order is read back without issuing another effect. Thus an accepted command remains acknowledged even after the proposal expires or a later reset closes its work order. Its original acknowledgement can say `work_order_open` while the new readback says `closed_by_reset`; that is intentional historical versus current evidence.

A receipt without this proposal's previously persisted execution intent is rejected, rather than being adopted as a valid recovery. A different caller execution ID for an already bound proposal returns 409. Reusing an execution ID for another proposal also returns 409. These guarantees are limited to the existing SQLite receipts and one active synthetic gateway; this is not an external exactly-once command broker.

If the work order cannot be read back, acceptance is not upgraded to a verified workflow result. Keep the same request ID when retrying. Storage or process failures after the park transaction may leave a durable execution intent plus receipt awaiting reconciliation; they must not prompt a new command identity.

## Lifecycle and storage

Root application integration calls `install_workflow_routes(app)` after installing planning routes. The workflow installer wraps the existing lifespan and closes its own connection. `PARK_WORKFLOWS_DB` selects a separate SQLite file; the default is `workflows.db` beside the park database. An in-memory park defaults to an independent in-memory workflow store. The service refuses configured collisions with live park, planning evidence or configured replay storage, and refuses databases containing another application's tables.

Retention is at most 256 proposals, 16 MiB of serialized proposal-body data and 64 KiB per body. This excludes SQLite/index/journal overhead and the small create-request metadata. Records are never automatically evicted. A full store rejects new writes while preserving existing evidence. Deployment must retain both the workflow database and the park database to preserve execution intent and command receipts together.

Mutation locks follow the established order: recorded-view lock, connector lock, park lock, workflow-store lock. The workflow routes enforce replay policy themselves, avoiding double acquisition through the existing legacy-action middleware. HTTP calls do not hold these locks while waiting on an external network service; there is no such service in this synthetic executor.

## Verification

`tests/test_workflows.py` covers successful receipt/readback with a still-closed ride; stable create and execution identity; expiry and stale data; changed canonical status/inspection/scenario; intervening work orders; ordinary tick changes; concurrent duplicate requests; a crash after park commit before workflow completion, including restart recovery; hypothetical and forged historical evidence failing current-state gates; replay rejection; separate database lifecycle closure; unsupported actions and retention caps. Direct-incident cases additionally exercise faults under a normal global label, unrelated scenario changes, stale ERP with fresh target observations, frozen creation evidence, optional old-model rationale and digest corruption, shared creation-ID conflicts, concurrent retries and restart using the same executor. Legacy proposals retain their scenario check. A real CMMS pilot would need additional vendor integration and outcome checks.

The intended product benefit is fewer steps for an obvious maintenance incident. The direct API removes forecast and save prerequisites; it does not by itself demonstrate faster operator work or better outcomes. Measure time/clicks from fault inspection to verified work order, duplicate/incorrect dispatches, and whether the operator understands that the ride remains unrepaired. Compare against the existing synthetic dispatch workflow before claiming an operational improvement.
