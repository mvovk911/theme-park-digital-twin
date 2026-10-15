# Standalone synthetic HTTP producers

The park's ten source feeds can run as separate Python processes outside the gateway. Each process generates illustrative scenario samples and sends normalized events to the existing ingestion API. No physical devices, MQTT brokers, OPC UA servers, ERP instances or other vendor systems are contacted.

The producer uses the same asset definitions, pure scenario rules and typed connector mappings as the gateway. It does not open SQLite or import the gateway application. `backend/domain.py` owns definitions; `backend/model_rules.py` owns pure scenario evaluation; `ParkSimulator` retains persistence, workflows and orchestration. Existing imports from `backend.simulator` remain compatible.

## Inspect a sample without networking

From the repository root, use the project's environment with `requirements-backend.txt` installed:

```bash
.venv/bin/python -m simulators.producer --source weather --profile heatwave
.venv/bin/python -m simulators.producer --source all --emit-json
```

The default is one sample per selected source, printed as JSON lines. Each line contains `source_id`, `synthetic: true` and an `events` array. Only an explicit `--api-url` enables publishing. `--emit-json` and `--api-url` cannot be combined.

The source choices come directly from the catalog: `ride_scada`, `ticketing`, `vision`, `cmms`, `erp`, `workforce`, `bms`, `water`, `weather`, `gis`. Repeat `--source` to select several; `--source all` selects all ten. `--profile` accepts the seven existing scenarios: `normal`, `ride_closure`, `show_surge`, `heatwave`, `power_fault`, `water_leak`, `food_rush`.

## Publish through the gateway

Start the gateway normally, then pause the in-process adapter for each selected source in the Sources dialog or API. Paused means the gateway stops generating samples for that source; external synthetic HTTP ingestion remains enabled.

```bash
curl -X POST http://127.0.0.1:8100/api/connectors/weather/simulation \
  -H 'Content-Type: application/json' -d '{"mode":"paused"}'

.venv/bin/python -m simulators.producer --source weather --profile heatwave \
  --api-url http://127.0.0.1:8100 --rate 1 --count 60
```

The CLI checks that each source is synthetic, permits demo ingestion and is paused. It never changes source mode. A source that is live or offline rejects publishing. If someone changes its mode while a producer runs, the next batch fails and the producer stops.

For independent processes, pause `water` and `weather`, then run one command in each terminal:

```bash
.venv/bin/python -m simulators.producer --source water --profile water_leak \
  --api-url http://127.0.0.1:8100 --rate 1 --count 120

.venv/bin/python -m simulators.producer --source weather --profile heatwave \
  --api-url http://127.0.0.1:8100 --rate 1 --count 120
```

`--rate` is the requested sample frequency per selected source (0.1–20 Hz, default 1). `--count` is a finite sample limit per source (1–100000, default 1). HTTP delivery is sequential, so slow responses reduce the achieved frequency. Missed intervals do not trigger a catch-up burst. Each sample advances the synthetic model by one tick; this is a demonstration waveform, not a calibrated time or capacity model.

Stop with Ctrl+C or let the sample count finish. The source remains paused; its accepted values age and eventually become stale according to that source's catalog threshold. No final heartbeat pretends it is still fresh. Resume the source in the UI or with `{"mode":"live"}` to return to in-process generation on subsequent simulator ticks.

## Data and delivery contract

The producer sends `POST /api/connectors/{source_id}/ingest` with exactly:

```json
{
  "synthetic": true,
  "events": [{
    "event_id": "producer:<unique-session>:<tick>:weather/WEATHER_STATION:temperature_c",
    "source_asset_id": "weather/WEATHER_STATION",
    "metric": "temperature_c",
    "value": 38.0,
    "unit": "Cel",
    "source_timestamp": "2026-10-15T20:00:00.123456+00:00"
  }]
}
```

Every process gets a UUID session ID. Event IDs include its session, sample tick, source asset and metric. A batch shares a UTC source timestamp taken at generation. Values and units come from the shared mappings and pure model; the gateway still validates every event independently. HTTP-ingested observations record `provenance.transport: synthetic_http_ingest`; in-process samples retain `in_process_simulation`. The event ID identifies a demo producer session, not an authenticated device identity.

A connection error, lost response or HTTP 5xx triggers at most two retries of the identical batch with bounded backoff. Accepted event IDs deduplicate within the gateway's bounded retention window. HTTP 4xx or any per-event rejection stops delivery without retry. A batch can be partially accepted; failure output explicitly says so. There is no durable spool, broker, process lease or exactly-once guarantee. The two retries do not extend the event timestamp; a delayed sample can become stale. Run one producer per source to avoid competing writers; the gateway does not lease the source to a process. Newer timestamps win per metric, valid late events remain in the decision journal without replacing current values.

## What changes in the park

A selected source can change only the fields assigned to it by the connector catalog. For example, the weather producer updates the canonical station temperature, whereas a people-counter observation of arena occupancy stays informational because ticketing owns that canonical field. The canonical read model, alerts, source quality and renderer consume the accepted observations through their existing paths.

A producer profile does **not** change the gateway's scenario, actions, work orders or comparison baseline. Selecting a heatwave profile only for `weather` changes the temperature observation; it does not invent concurrent HVAC, staffing or water responses. To generate all ten feeds from the same synthetic profile, pause all ten sources and publish `--source all --profile heatwave`. Fields without an authoritative connector mapping still come from the gateway model; publishing all sources does not replace that model. Separate processes or profiles can deliberately produce source/model conflicts; those conflicts remain visible. Simulator history and what-if comparison remain based on the gateway's own model, as described in [the connector contract](connectors.md).

## Verification

`tests/test_producers.py` checks database-free model/producer imports, persisted scenario equivalence, input isolation, all ten sources in every profile through the real FastAPI routes using an in-process ASGI test transport, field ownership, natural staleness, pause enforcement and safe retry after a lost success response. These checks do not require a TCP listener or GPU.

```bash
.venv/bin/python -m pytest -q tests/test_producers.py tests/test_backend.py \
  tests/test_connectors.py tests/test_connectors_http.py
```

In the restricted development sandbox, the test runner uses a temporary asyncio heartbeat plugin because cross-thread event-loop wakeups are unavailable. This is a local test-environment workaround; it changes no production module and is not required on a normal host.

Historical inspection does not stop acquisition. A producer whose source was paused
before entering replay can continue publishing; new events update live state and
new recordings while the selected historical snapshot remains unchanged. Operator
actions and source-mode changes remain locked until returning Live.
