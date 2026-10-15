# Connector boundary and accepted observations

All ten shipped adapters are **synthetic in-process sources**. The HTTP endpoints expose simulated domain data. “Planned OPC UA”, “planned MQTT”, “planned BACnet” and vendor REST labels identify replacement boundaries; those protocol servers and vendor integrations are not implemented.

The useful increment is a real acceptance boundary: source events pass mapping, type, unit, identity and timestamp validation before entering a bounded store. The asset view projects accepted observations using declared source ownership. A source can stop reporting while the park simulator continues, and the UI retains its last accepted value with visible stale/offline quality.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `backend/connectors/catalog.py` | Stable IDs, source-to-asset mappings, units, value constraints and one authoritative owner per asset/property |
| `adapters.py` | Source `snapshot(context)` / `poll(after, context)` contract and one synthetic adapter instance per domain |
| `validation.py` | Event shape, field/unit/type/range/reference validation and timestamp parsing |
| `store.py` | Accepted events, latest values, deduplication and bounded cursor polling |
| `runtime.py` | Adapter polling, ingestion, source health, freshness and simulation modes |
| `readmodel.py` | Existing asset/system view projected from accepted authoritative observations |
| `api.py` | HTTP route and request validation |

`app.state.read_model.snapshot()` is the public full-view interface for browser APIs and replay capture. `app.state.park.snapshot()` remains the underlying synthetic scenario model. `app.state.park.workflow_snapshot()` supplies `{tick, work_orders}` with at most 300 recent orders for replay without fetching asset telemetry histories.

## Sources and ownership

| Source ID | Domain | Main canonical properties |
|---|---|---|
| `ride_scada` | Ride operations | Ride status, throughput, power; maintenance is informational here |
| `ticketing` | Admission/reservations | Occupancy, capacity, reservations and queues for gate, rides and show |
| `vision` | People-count estimates | Food-court/parking counts and queues; gate/show values remain inspectable but ticketing owns their canonical view |
| `cmms` | Maintenance | Inspection status, health and open work orders |
| `erp` | ERP/POS | Inventory, reorder points, illustrative cost and service throughput |
| `workforce` | Staffing | On-duty/required staffing and qualifications |
| `bms` | Buildings/energy | Building power and temperature |
| `water` | Water/facilities | Plant/restroom flow and operational status |
| `weather` | Local weather | Weather-station temperature |
| `gis` | Spatial asset registry | OpenUSD paths, accessibility text and dependencies |

Mappings are listed by the catalog endpoint. Source asset IDs are stable, e.g. `water/WATER_PLANT`; canonical IDs remain `WATER_PLANT`, with `/World/Park/WATER_PLANT` in the scene. No source may invent a canonical asset ID or USD path. Canonical units include `kW`, `L/min`, `Cel`, `min`, `people`, `vehicles`, `items` and `EUR/h`. Conversion must occur in the adapter before submission; a mislabeled unit is rejected.

## HTTP contracts

- `GET /api/connectors`: `{schema_version:"1.0", connectors:[...]}` with adapter identity, transport, future protocol boundary, mapped assets/properties, capabilities and current health.
- `GET /api/connectors/{source_id}`: one catalog entry.
- `GET /api/connectors/health`: `{health:[...]}` for all sources.
- `GET /api/connectors/{source_id}/health`: source health.
- `GET /api/connectors/{source_id}/snapshot`: current normalized observations, health and a cursor representing their accepted event position.
- `GET /api/observations?source_id=water&asset_id=WATER_PLANT&limit=1000`: latest observations, total count and explicit `truncated` flag. Both filters are optional; limit is 1–2000.
- `GET /api/connectors/{source_id}/events?after=<cursor>&limit=100`: accepted events after a returned cursor; limit is 1–1000. Without `after`, starts at the oldest retained event. Returns `events`, `next_cursor`, `latest_cursor`, `has_more`, and `retention_events`.
- `POST /api/connectors/{source_id}/simulation` with `{mode:"live"|"paused"|"offline"}`: control a synthetic adapter for a failure demonstration.
- `POST /api/connectors/{source_id}/ingest`: explicitly synthetic demo batch, accepted only while that connector is paused.

Legacy `/api/systems/{id}/data` retains its domain `records` and adds normalized `observations`. Its records reflect that source's own accepted values, including informational values that do not own the canonical asset property. `timestamp` and `system.last_sync` are the last accepted ingestion time, not the HTTP request time.

A normalized observation contains:

```json
{
  "schema_version": "1.0",
  "observation_id": "stable hash of source ID and event ID",
  "event_id": "operator-demo-001",
  "source_id": "water",
  "source_asset_id": "water/WATER_PLANT",
  "asset_id": "WATER_PLANT",
  "metric": "water_lpm",
  "value": 312.0,
  "unit": "L/min",
  "source_timestamp": "2026-10-15T20:00:00.123456+00:00",
  "ingested_at": "2026-10-15T20:00:00.125+00:00",
  "sequence": 25,
  "authoritative": true,
  "quality": {"status":"good", "age_seconds":0.002, "stale_after_seconds":5.0, "reasons":[]},
  "provenance": {
    "adapter":"synthetic.water.v1",
    "synthetic":true,
    "transport":"in_process_simulation",
    "source_field":"water_lpm",
    "planned_protocol":"MQTT / utility gateway"
  }
}
```

## Demonstrate failure and recovery

Pause a source, wait more than five seconds, and read its health. Its accepted timestamp remains unchanged and health becomes `stale`. Set `offline` for an immediate explicit source outage. `live` resumes polling; health recovers only after a fresh accepted sample, usually the next simulator tick.

```sh
curl -s -X POST http://127.0.0.1:8100/api/connectors/water/simulation \
  -H 'Content-Type: application/json' -d '{"mode":"paused"}'
curl -s http://127.0.0.1:8100/api/connectors/water/health
```

While paused, submit a demonstration reading with a **current timezone-qualified timestamp**:

```json
{
  "synthetic": true,
  "events": [{
    "event_id": "operator-demo-001",
    "source_asset_id": "water/WATER_PLANT",
    "metric": "water_lpm",
    "value": 312.0,
    "unit": "L/min",
    "source_timestamp": "REPLACE_WITH_CURRENT_ISO8601_TIMESTAMP"
  }]
}
```

The batch response reports `accepted`, `duplicates`, `rejected`, indexed errors, current health and `latest_cursor`. Domain validation errors are reported per event with HTTP 200 so valid events in the same batch can be accepted. Invalid HTTP request shape returns 422; unknown source/asset returns 404; ingesting into a running/offline or non-synthetic adapter returns 409. Demo controls are not physical controls, and the service remains behind the application's authenticated tunnel.

## Ordering, freshness and retention

- Duplicate event ID with identical content: count as duplicate, add no event, change no timestamp.
- Reused event ID with different content: reject `duplicate_event_conflict`.
- Older source timestamp for the same source asset/metric: reject `out_of_order`; microsecond precision is preserved. Equal timestamps with distinct event IDs are accepted in server ingestion order.
- Missing timezone, nonfinite numbers, booleans submitted as numbers, negative constrained values, undeclared mappings/dependencies, and wrong units are rejected.
- Timestamps over five seconds in the future are rejected. Accepted timestamps slightly ahead of the clock are labeled uncertain with `source_clock_ahead`.
- Freshness uses source event time. Every shipped domain currently uses a five-second demo threshold. Poll attempts and HTTP reads do not refresh accepted timestamps.
- Source health includes `healthy`, `paused`, `stale`, `degraded`, `error`, `offline` or `unknown`, along with missing/stale metric counts. Observation quality is `good`, `uncertain` or `stale`; an asset field with no accepted observation is `unknown`.
- Adapter errors retain last accepted values and mark them uncertain. Public error messages omit provider exception text, which could contain credentials.
- Store retention is **2048 accepted events per source**, plus latest values per declared metric and up to 4096 deduplication IDs. Event storage is in memory. Restart resets the store/cursor epoch and requires a new snapshot. An expired cursor returns HTTP 409 `cursor_expired`; malformed/future cursors return 422. This is not a durable event broker.

Per-asset `data_quality.fields[metric]` carries source ID, source/ingestion timestamps, unit, synthetic flag and quality. Full snapshots also contain `connector_health` and `read_model` metadata. A missing field retains its prior synthetic baseline for backwards compatibility but is explicitly marked unknown; it must not be presented as an observed value.

## Replace a synthetic source

Implement `SourceAdapter.snapshot(context) -> SourceBatch(events, cursor)` and `poll(after, context) -> SourceBatch`, with `adapter_id`, `synthetic`, and `transport` attributes. Supply that adapter in `ConnectorRuntime(..., adapters={"weather": adapter})` at application composition. Both methods return the same source event contract; they do not modify assets or the database directly. Canonical mapping ownership and projection remain unchanged, so consumers keep the same field paths.

A real connector still needs vendor authorization, credentials outside the repository, transport-specific reconnection, source timestamp semantics and conversion tests. No such connector ships in this milestone. Source selection is code composition, not an unauthenticated endpoint for arbitrary URLs. Source actions, automatic control and durable ingestion are separate future work.

Scenario comparisons remain deliberately synthetic: `baseline_source:"synthetic_simulator"` identifies their baseline. Injected connector values are not inputs to that heuristic scenario model. Current asset telemetry history also remains the simulator's SQLite history; accepted source event history is exposed by the connector event endpoints.
