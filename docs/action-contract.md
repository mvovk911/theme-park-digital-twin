# Simulated action acknowledgements and durable retries

`POST /api/actions` accepts an optional `request_id` alongside the existing `action` and optional `asset_id`. All actions remain synthetic. No request operates a physical ride, sends a device command or confirms a real repair.

```json
{
  "action": "dispatch_maintenance",
  "asset_id": "RIDE_COASTER",
  "request_id": "operator-session-42:dispatch-1"
}
```

A request ID contains 1–128 ASCII letters, digits, dots, underscores, colons or hyphens and starts with a letter or digit. IDs are case-sensitive and unique across all action types in this park database. Generate a new ID for a new intended operation; preserve the same ID and payload when retrying an uncertain or lost response. Callers without a request ID retain the previous behavior: every successful call is a new audited operation.

## Response

```json
{
  "synthetic": true,
  "result": {
    "id": 7,
    "timestamp": "2026-10-15T20:00:00.000+00:00",
    "action": "dispatch_maintenance",
    "asset_id": "RIDE_COASTER",
    "message": "Synthetic work order #2 created and qualified maintenance assigned.",
    "synthetic": true,
    "request_id": "operator-session-42:dispatch-1",
    "acknowledgement": "accepted",
    "target": {"scope": "asset", "asset_id": "RIDE_COASTER"},
    "lifecycle": "work_order_open",
    "work_order_id": 2,
    "physical_effect": false
  },
  "idempotency": {"request_id": "operator-session-42:dispatch-1", "replayed": false},
  "state": {"synthetic": true, "tick": 42, "assets": []}
}
```

`result` is the immutable original acknowledgement. Its `id` is the audit ID, `timestamp` is the original acknowledgement time, and `target` describes the requested simulated target. The existing action-specific applicability checks still apply. Some model rules, such as guest rerouting and flexible-load reduction, affect several assets even when an asset identifies the action's context.

Maintenance dispatch acknowledges an open synthetic work order and returns its `work_order_id`; it does not reopen a closed ride. Other actions report `lifecycle: simulation_applied`. Simulated leak repair can complete synthetic water work orders and adjust the model, always with `physical_effect: false`. Reset's target scope is `park`, with `target.asset_id: null`. For compatibility, an explicitly supplied valid `asset_id` on reset remains in the legacy audit/acknowledgement field; it does not narrow reset's park-wide effect.

The acknowledgement lifecycle describes what was accepted **at the original request time**, not the work order's present status. A dispatch acknowledgement can still say `work_order_open` after a later reset closed that work order. Read current work-order details through the asset API.

The response's `state` is the current canonical snapshot, including on retries. It is not a retained copy of the state at acknowledgement time. Background ticks, new accepted observations, later actions or a restart can therefore change `state` while `result` remains identical. `idempotency.replayed` distinguishes a stored acknowledgement from a newly applied operation.

## Normalization and conflicts

An omitted or null asset resolves to the action's existing default before comparing payloads:

| Action | Default target |
| --- | --- |
| `dispatch_maintenance` | `RIDE_COASTER` |
| `reroute_guests` | `RIDE_WHEEL` |
| `add_staff` | `FOOD_COURT` |
| `shed_load` | `POWER_HUB` |
| `repair_leak` | `WATER_PLANT` |
| `replenish_stock` | `FOOD_COURT` |
| `reset` | null, park-wide |

The normalized payload is exactly the action ID plus resolved asset ID. Omitting `FOOD_COURT` for `add_staff` and explicitly supplying it are equivalent. No case folding or whitespace trimming applies to action, asset or request IDs. A supplied reset asset remains part of the normalized legacy payload even though reset is park-wide.

- Same request ID and normalized payload: HTTP 200, original `result`, `replayed: true`. No new audit row, work order, mitigation change, telemetry step or action receipt.
- Same request ID and a different valid normalized payload: HTTP 409 with `detail.code: request_id_conflict`. Nothing changes.
- Malformed input, unknown action or inapplicable target: HTTP 422. Unknown asset: HTTP 404. Input validity is checked before an operation can be acknowledged; a failed unacknowledged attempt does not reserve its request ID.

A previously acknowledged action stays a retry even if a later action reverses its effect. For example, retrying an old staff assignment after reset returns the old acknowledgement without assigning staff again. Use a new request ID to request a new assignment.

## Atomicity, restart and retention

The existing SQLite database stores `action_receipts(request_id PRIMARY KEY, payload, acknowledgement)`. Under the simulator lock, one `BEGIN IMMEDIATE` transaction covers receipt lookup, simulated effects, work-order changes, audit, telemetry/settings and receipt insertion, followed by one commit. Concurrent identical requests produce one new acknowledgement; other callers receive that stored acknowledgement. A failure before commit rolls back every database effect and restores in-memory scenario, mitigations, tick and state. This also protects legacy actions without a request ID.

If a transaction commits but the HTTP response is lost, retry with the same ID. The receipt survives process restart and is checked before applying effects. Restart still performs its usual initial simulator tick; the retried action itself performs none. Failed transactions have no success receipt and can be retried once the failure is resolved.

Receipts are retained for the lifetime of the park database, with **no automatic expiry or eviction**. Reset preserves them. Back up the database to preserve retry identity; deleting or replacing it removes that identity. Storage grows with the number of distinct acknowledged IDs; receipt retention is deliberately explicit rather than silently allowing an old operation to run again after eviction. This is a single active gateway's simulated workflow contract, not a multi-worker coordinator, durable external command broker or physical-control delivery guarantee.

`tests/test_action_idempotency.py` covers normalized retries, immutable acknowledgements, payload collisions, concurrent HTTP requests, lost responses, restart, legacy clients and injected transaction failures after side effects and telemetry have been written.


## Coordinated deployed HTTP acceptance

`tests/live_workflow_acceptance.py --url http://127.0.0.1:8100 --output /tmp/workflow-initial.json` exercises all ten independent synthetic producer instances over HTTP while a recorded view stays selected, checks new recordings and immutable historical assets/KPIs, then validates one dispatch with concurrent request-ID retries and a conflicting payload. Run it exclusively against a coordinated synthetic gateway: it changes shared view/source modes and intentionally leaves accepted observations, recordings, one synthetic work order and its audit/receipt as evidence. Cleanup returns the view to live and restores prior source modes and scenario; it does not erase history or existing workflows. Producer instances run in concurrent threads, not separate OS processes.

After the coordinator restarts the gateway, run the same script with `--verify-restart /tmp/workflow-initial.json --output /tmp/workflow-restart.json`. This retries the exact saved dispatch, checks unchanged acknowledgement/audit/work orders, and records the changed startup identity timestamp with the same source commit/tree. That timestamp is restart evidence, not OS process attestation. Both phases use bounded HTTP timeouts, save source identity, and refuse to overwrite an existing output; the restart report links the original evidence by SHA256. Neither phase validates physical systems or GPU rendering.
