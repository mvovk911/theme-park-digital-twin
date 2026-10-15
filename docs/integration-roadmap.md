# From park proof of concept to an operational digital twin

The starting point is the NVIDIA FOX idea: spatial context, operational data,
simulation and AI assistance meet in an application that helps people act. A park
adds unusual constraints: visitors move unpredictably, demand changes with weather
and show schedules, and ride safety remains under certified local controls.

## Three useful project directions

| Direction | First decision to improve | Pilot outcome to measure |
|---|---|---|
| Operations control room | Where to send staff after a ride closure or show release | Time to detect, understand and respond; measured queue and throughput changes |
| Utilities and maintenance | Which fault affects which attractions, and who should inspect it | Fault-to-work-order time, inspection compliance, measured energy/water usage |
| Planning and guest experience | How a new attraction, timetable or capacity plan changes demand | Forecast error against held-out real days; service level and congestion constraints |

Start with operations plus one utility dependency. These are understandable in a
small pilot and do not require a perfect whole-park model. Expand planning only
after real observations can calibrate and validate the simulation.

## Connectors and boundaries

The prototype exposes ten domain feeds as synthetic HTTP APIs. The protocols and
vendors below are **future integrations**, not installed connectors.

| System family | Candidate interfaces | Data and use |
|---|---|---|
| Ride control / SCADA | Read-only OPC UA; approved historian REST; MQTT gateway | Operating state, cycle count, vibration, temperature; asset health and downtime |
| Ticketing / access | REST, webhooks, batch exports | Admission counts, capacity and reservations; demand planning |
| Queue / guest counts | Aggregated camera analytics REST/events, counters | Zone occupancy and queue observations; dispatch and routing |
| CMMS / EAM | Vendor REST/OData, work-order events | Asset register, inspections, parts and work orders; maintenance workflow |
| ERP / POS | ERP OData/REST, sales events, inventory batches | Stock, procurement and illustrative cost context; replenishment |
| Workforce | Scheduling API, approved roster export | Coverage, skills and shift changes; staffing recommendations |
| Buildings / utilities | BACnet gateway, Modbus gateway, meters via MQTT | Electrical distribution, HVAC and water; dependency tracing and anomalies |
| Weather / environment | Forecast REST and local station MQTT | Wind, temperature, precipitation; operating context |
| GIS / BIM / engineering | GIS REST/WFS, IFC, CAD-to-USD pipeline | Coordinate reference, geometry, asset locations and revisions |
| Guest services / hotel / parking | PMS, parking and notification APIs | Arrivals, service demand, accessible routes and guest communication |

Keep personal guest identity outside the spatial model. Counts and zone aggregates
are sufficient for the pilot. Real integration needs source-specific authorization,
rate limits, retries and clear ownership; APIs alone do not create semantic agreement.

## The aggregation layer

1. **Ingest:** adapters translate source events, retaining source timestamp, ingestion
   timestamp, unit, quality and provenance. Use an event broker when volume or
   reliability needs it; do not add one solely for the demo.
2. **Identify:** an asset registry links source record IDs to a stable park asset ID
   and USD prim path. Version geometry and mappings together. Treat duplicates,
   missing units and out-of-order events explicitly.
3. **Store:** a time-series store holds telemetry; relational storage holds registry,
   workflow and audit; object storage holds geometry and model revisions. The POC
   uses SQLite for all operational data to keep the system reproducible.
4. **Contextualize:** a dependency graph relates rides, power circuits, water supply,
   teams, stock and zones. APIs provide a coherent read model for applications.
5. **Decide:** rules and later calibrated simulation create explanations, comparisons
   and proposed actions. Scenario branches must not overwrite live observations.
6. **Act:** approved commands go through source-system adapters with authorization,
   idempotency, acknowledgement and audit. This demonstration changes synthetic
   state only. Ride interlocks and safety control stay at their certified control layer.

This is a park operations orchestration layer, comparable to selected MES functions
such as dispatch, work execution and asset status. ERP remains the financial,
procurement and inventory system of record. A 3D stage is the spatial representation,
not the transactional database or time-series archive.

## Visualization and interaction

The POC uses procedural USD geometry → OVStage runtime → OVRTX on an NVIDIA GPU.
Only rendered images travel to the browser; selecting geometry uses a native RTX
pick query, resolves the prim path, then retrieves the matching database record.
Camera movement and ride animation update stage transforms. Browser overlays add
queue, energy and occupancy values at projected asset positions.

A production experience could add map and 3D views, time replay, camera bookmarks,
confidence/freshness indicators, dependency highlighting and a separate scenario
branch. Optional conversational AI should call the same permissioned APIs, cite
source timestamps and offer reviewable actions. The current POC contains no LLM
agent, calibrated crowd physics, forecast optimizer or digital safety model.

## How to start

| Phase | Work | Exit evidence |
|---|---|---|
| 1. Scope and baseline | Pick one closure-response decision and one utility fault; agree asset owners and measured baseline | Named operators, source access, metrics and acceptance scenario |
| 2. Data contracts | Map 20–50 assets; connect read-only feeds; validate timestamps, units and quality | Replayable sample, identity coverage and freshness report |
| 3. Spatial pilot | Import survey/BIM, simplify geometry, bind IDs; build operator views | Verified coordinate alignment and pick-to-record correctness |
| 4. Operational trial | Compare alerts and recommendations with actual operator responses | Measured task time, false alerts, usability feedback |
| 5. Controlled expansion | Add acknowledged workflows, calibrated scenarios and additional domains | Audit trail, recovery tests and demonstrated incremental value |

Do not claim savings from a prettier dashboard. Measure downtime, response time,
service levels and metered resource use against a comparable baseline, controlling
for attendance, weather and operating hours. The demo's queue, cost and resource
numbers illustrate workflows; they are not estimates of financial return.

Source inspiration: [NVIDIA FOX blueprint article](https://blogs.nvidia.com/blog/factory-operations-fox-blueprint-ai-brain/).
See [the illustrated deck](project-concept.pdf) and [its research sources](deck-source/sources.md).
