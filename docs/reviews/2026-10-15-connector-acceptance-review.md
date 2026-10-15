# Connector milestone acceptance review

Reviewed commit: `cf4d621cee0b15279db5edcb21269bc0d9ebb56d` (2026-10-15 UTC). Includes the preceding asset checkpoint `de28d1a`. This is the first recurring implementation review after the [initial architecture review](2026-10-15-architecture-review.md); the [public-example benchmark](2026-10-15-digital-twin-benchmark.md) supplies the product acceptance direction.

**Verdict: keep the implementation, fix the projection and snapshot-boundary bugs, and continue incremental integration.** Accepted observations now have a meaningful boundary and declared ownership. The project has not become an uncontrollable blob. A full rewrite would discard useful behavior without resolving the specific defects identified here.

The original P1 finding about competing simulator/connector truth is **partially resolved**. Independently ingested values survive unrelated simulator ticks and do not mutate the source simulator. Canonical assets and several KPIs use accepted observations. Alerts, scenario comparison and telemetry history still follow a different state path. Connector snapshots also have a reproducible cursor consistency race. Those are contract issues to resolve before calling the operational story complete.

## Review method and verified evidence

The review used a clean `git archive cf4d621` extracted to `/tmp/park-connector-review-cf4d621`, rather than relying on concurrently changing root replay/renderer/frontend work. No application files, database, GPU process or commits were modified.

The committed backend/connector suite passed:

```text
51 passed in 9.58s
```

Command, from the isolated archive, using the project's recovered Python environment:

```sh
PYTHONPATH=/tmp:$PWD /path/to/park-twin/.venv/bin/python \
  -m pytest -q -p park_sandbox_testloop \
  tests/test_backend.py tests/test_connectors.py tests/test_connectors_http.py
```

`park_sandbox_testloop` is a test-process-only sandbox wakeup workaround supplied by the integrator; it was not added to the repository or used to alter application behavior. Additional direct Python probes used a temporary database and injected clock. A deterministic HTTP interleaving probe exercised the snapshot/cursor race. Static OpenUSD checks opened the committed `assets/park.usdc` using the separate modeling environment.

**No new GPU or browser verification is claimed.** Current uncommitted renderer/replay/frontend improvements are outside this reviewed revision. Passing the 51 checks establishes their covered behaviors, not the missing acceptance gates below.

## Acceptance summary

| Requirement | Evidence at `cf4d621` | Result |
|---|---|---|
| Ten domain contracts and discoverable mappings | Catalog and legacy domain feed tests; 137 declared source mappings, 115 authoritative mappings | Implemented |
| Strict type/unit/identity/time validation | Parameterized invalid-value/unit/mapping/dependency/time cases; HTTP request validation | Implemented for declared metrics |
| Accepted source owns projection across unrelated ticks | Injected `WATER_PLANT.water_lpm=321.5`; advanced simulator three ticks; public projection remained 321.5 while simulator reading was 174.4 | Verified |
| Informational source does not overwrite owner | Existing vision/ticketing test keeps canonical ticketing occupancy and exposes different vision source value separately | Verified |
| Pause and age source independently | Existing tests preserve last accepted ingestion time and mark paused weather stale after six seconds; independent probe verified stale field/source | Verified |
| No false healthy status after error/offline/clock skew | Existing adapter-failure/offline tests; four-second-ahead weather event accepted with `uncertain` quality, `source_clock_ahead`, degraded source | Verified |
| Duplicate and conflict handling | Identical retry counted once without sequence advance; changed content for same ID rejected | Verified within bounded dedup lifetime |
| Late events retained without replacing newer current value | Older source timestamp rejected `out_of_order`; no receipt retained | **Benchmark P0 gap** |
| Snapshot/cursor represents one acceptance position | HTTP interleaving produces old value with cursor already including a new event; catch-up skips that event | **Bug** |
| Canonical status/KPIs/alerts agree | Status/open-rides KPI change after injected fault; alerts remain simulator-derived | **Bug** |
| Restart/cursor semantics explicit | New store epoch rejects old cursor; counters/mode/latest observations reset | Documented prototype limitation, not durable ingestion |
| Canonical current/history/comparison consistent | Current uses accepted observations; history/comparison use simulator, explicitly documented/labeled in response | Deliberate split needing visible consumer semantics |
| Cross-system identity resolves into current USD | All 12 IDs/root paths match; all connector assets exist; 18 camera/ride/car/gondola paths exist | Static checks pass |
| End-to-end actual GPU experience at this revision | Not exercised by this reviewer | Pending integrated validation |

The catalog currently defines gauges/state/list fields, not cumulative energy/volume/cycle-counter semantics. Do not infer production counter-reset support from the source cursor or accepted-event sequence implementation.

## P1: alerts are not derived from the canonical operational state

**Locations:** `backend/connectors/readmodel.py:ParkReadModel.snapshot`, `backend/simulator.py:ParkSimulator._evaluate`.

The read model overlays authoritative observations and recomputes queue, power, water, open rides and cost. It preserves the simulator's alert list and active-alert count. Consequently valid injected observations can describe an incident that the incident panel does not know about, or contradict an incident generated by scenario rules.

Verified examples:

1. Normal simulator; pause `ride_scada`; ingest canonical coaster `status="fault"`. Result: coaster fault, `open_rides=1`, `alerts=[]`, `active_alerts=0`.
2. Same paused SCADA; ingest coaster `status="operational"`; activate synthetic `power_fault` scenario. Result: canonical coaster operational, `open_rides=2`, plus critical alert **“Coaster unavailable”** and feeder-fault alert.

The source is paused, so its observation may age. That is legitimate last-known data, but any contradictory scenario alert must be explicitly identified as scenario/expected impact rather than silently presented as a current observed incident. At injection time the first example is already inconsistent without waiting for staleness.

**Fix direction:** evaluate operational alerts and their count from one completed canonical snapshot. Preserve scenario expectations as separately labeled hypotheses if needed. Include source receipt/quality and affected dependencies in diagnosis. Do not mutate source simulator state to force agreement.

**Acceptance:** external ride fault and water anomaly produce suitable canonical incidents; restoration resolves the corresponding incident; a stale observation is labeled last known; scenario expectations cannot contradict observed state without explaining the conflict. `active_alerts == len(alerts)` and displayed incidents reference the same snapshot as asset values/KPIs. Add both reproduced cases as regression checks.

## P1: connector snapshot and cursor are not atomic

**Location:** `backend/connectors/api.py:install_connector_routes.snapshot.operation`.

`runtime()` refreshes the read model, then the endpoint calls `connectors.observations(...)`, `connectors.health(...)` and `connectors.health(...)` again for the cursor. Each method holds the runtime lock individually; the whole returned object does not. Another ingestion/poll can run between them.

A deterministic interleaving accepted water flow 456.7 immediately after the observation copy but before cursor capture. The HTTP response contained:

```text
snapshot water flow: 174.1
latest accepted flow: 456.7
snapshot cursor: <epoch>:7 (already includes the new event)
GET events?after=<epoch>:7: []
```

A snapshot-followed-by-poll client permanently misses the new value until some later update happens. This is a real catch-up contract violation, not merely differently aged health display.

**Fix direction:** provide one runtime `source_snapshot()` method that holds the lock while copying observations, health and acceptance position, or hold the same runtime lock across the endpoint operation. Use one captured health result.

**Acceptance:** inject concurrently between observation copy and cursor capture. The response must either include the new value with its position or retain the previous cursor so `/events?after=cursor` delivers the event. Add a deterministic regression test; random load alone is insufficient evidence.

## P1 against benchmark P0: late/rejected receipts disappear

**Locations:** `backend/connectors/store.py:EventStore.accept`, `backend/connectors/runtime.py:ConnectorRuntime._ingest`.

Out-of-order events correctly do not overwrite the latest value and do not increment accepted sequence. However, they are rejected before entering the store. Only aggregate rejection counters, last error and the immediate batch response remain. A probe using an event timestamp one millisecond older than the accepted value returned `out_of_order`; its event ID was absent from retained events.

This behavior is candidly documented and the existing test asserts it. It does not meet the benchmark's P0 requirement to retain late receipts while preserving fresher current state. It also prevents later incident/replay review from explaining which delayed observations arrived and why they were excluded.

**Fix direction:** retain a bounded receipt/audit stream with acceptance disposition, server receipt time, source time, source/event identity and a safe rejection reason. Keep accepted projection sequence/cursor semantics distinct if needed. Apply bounded retention/redaction; do not retain arbitrary provider secrets or unbounded payloads.

**Acceptance:** a valid late event is inspectable with its receipt and `applied_to_latest=false`, while the fresh current value remains unchanged. Malformed/invalid receipts have safe structured reasons. Retrying identical rejected/late receipts has defined semantics. No heavyweight broker is required.

## P2: explicitly separate source truth from synthetic history/comparison

**Locations:** `backend/app.py:asset`, `history`, `compare_scenario`; `backend/simulator.py:history`, `compare`; `docs/connectors.md` final paragraph.

The documented split is real: public current `water_lpm=321.5`, while the latest `/history` sample remains simulator flow 174.6. A comparison reports public current `open_rides=2` while `before.kpis.open_rides=1`, with `baseline_source="synthetic_simulator"` correctly identifying the model baseline.

This is not evidence that the accepted observation was lost: it survives current projection. It is evidence that consumers must distinguish datasets. Without visible labeling, the inspector sparkline, comparison “current” column or future replay could imply that they describe the same state.

**Acceptance:** expose provenance on the history response and clearly label simulator history/model baseline in consumers, or persist canonical snapshots and deliberately migrate those views. A comparison based on the simulator must not call its baseline current accepted-source truth. An injected value must appear in its declared observation/history dataset with its event identity. Do not quietly feed injected operational values into an uncalibrated scenario model as though its rules were validated for them.

## P2: in-memory reset and bounded ordering are correct only within their declared scope

**Locations:** `backend/connectors/store.py:EventStore`, `runtime.py:ConnectorRuntime.__init__`, `docs/connectors.md`.

Verified: process restart changes epoch, returns `cursor_expired` for a previous cursor, resets counters/modes, and regenerates current readings from the simulator. The injected 321.5 value became the simulator's 174.6 on the new runtime. This is an explicit in-memory prototype limitation, not an undisclosed persistence bug.

The default store retains 2,048 accepted events **per source**, not 2,048 ticks. GIS emits 36 events per tick, giving roughly 57 seconds of accepted-event retention at one tick per second. Dedup remembers up to 4,096 event IDs per source and also resets on restart. Equal source timestamps with distinct event IDs are deliberately applied in ingestion order, not a domain sequence order.

**Acceptance before stronger claims:** documentation/UI expose source epoch and event-count retention; replay is based on an identified durable snapshot store rather than treating this stream as durable history. If supporting real counters or durable exactly-once actions later, define producer boot identity, domain sequence/reset rules and persisted request IDs. Those features are not required to keep this synthetic milestone useful.

## Static asset identity review at the same committed revision

The committed USD and registry passed direct inspection:

- Exactly 12 unique scene IDs, equal to the operational registry IDs; no duplicate IDs.
- Each operational USD root exists and agrees with both its `assetId` custom data and `park:assetId` attribute and backend `scene_path`.
- All connector mapping asset IDs resolve into that scene.
- Eighteen declared camera, train, articulated car, rotor and gondola paths exist.
- Units are meters, up axis is Z, and all inspected geometry under operational roots has bound material.

These checks **do not prove renderer writes all new car transforms or that native picks pass**; that needs the integrated GPU run.

Remaining metadata drift: 11 of 12 scene display names differ from operational names (for example “Comet Run Coaster” vs “Skyline Coaster”). Scene `systems` labels include conceptual names such as `energy`, `maintenance`, `queues`, `shows`, `incidents`, while actual connector IDs are `bms`, `cmms`, `ticketing`/`vision`, etc. Those labels are not necessarily wrong as taxonomy, but they are not resolvable connector references.

**Acceptance:** one canonical display name or explicit authored/operational alias relationship; label conceptual tags separately from actual connector IDs and validate true connector references. Keep the stable IDs/hierarchy already working. A wholesale asset rewrite is unnecessary.

## Complexity and recommendation

The milestone adds focused modules for catalog, adapter protocol, validation, bounded store, runtime, read model and HTTP routes. This is a reasonable separation of concerns for ten domains, not gratuitous enterprise infrastructure. The tests cover meaningful validation, ownership and failure semantics. Keep those boundaries.

The risk has moved from “accepted data gets overwritten by the simulator” toward “several derived views represent different truths.” Resolve that explicitly with a canonical projection/incident evaluator and snapshot/time contracts. Avoid replacing the implementation with a broker, a graph database, a new web framework or a generic plugin framework to address these few defects.

Next integrated review should verify these gates:

1. Atomic source snapshot plus cursor with deterministic interleaving coverage.
2. Canonical fault/restoration incidents and quality-aware diagnosis; no status/alert contradiction.
3. Late receipt retention with fresh-value preservation and safe audit reasons.
4. Clear dataset origins for current, history, comparison and replay.
5. One deployed revision manifest; actual GPU car animation, native picks and source-failure story captured at that revision.

Until then this is a strong connector foundation with specific incomplete acceptance gates, not a completed production integration platform.
