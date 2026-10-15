# Synthetic park services

All values and workflows are simulated. FastAPI runs at port 8000 with a persistent SQLite registry, bounded telemetry, and action audit in `backend/data/park.db` (`PARK_DB` overrides). A 1 Hz simulator publishes state. Start: `python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000`.

## Contract

- `GET /api/state`: `{synthetic:true, timestamp, tick, scenario, assets:[...], kpis:{attendance,total_capacity,average_wait_minutes,power_kw,water_lpm,open_rides,active_alerts,estimated_operating_cost_eur_per_hour}, weather:{temperature_c,wind_kph,condition}, systems:[...], alerts:[...], scenarios:[{id,label,description}], actions:[{id,label}], recent_actions:[...]}`.
- `GET /api/assets`: `{synthetic:true,assets:[...]}`.
- `GET /api/assets/{id}`: one asset including `history`, `work_orders`, `audit`.
- `GET /api/assets/{id}/history?limit=120`: `{asset_id,synthetic:true,history:[{timestamp,tick,status,queue_minutes,occupancy,power_kw,water_lpm,temperature_c}]}` (oldest first).
- `GET /api/systems/{system_id}/data`: `{synthetic:true,timestamp,system,records:[{asset_id,...domain_fields,synthetic:true}]}` domain feeds for `ride_scada`, `ticketing`, `vision`, `cmms`, `erp`, `workforce`, `bms`, `water`, `weather`, `gis`. Protocol labels describe the intended integration; this POC serves synthetic domain data through HTTP and does not run OPC UA/MQTT/BACnet servers.
- `GET /api/systems`: `{synthetic:true,systems:[...]}`.
- `POST /api/scenarios` body `{scenario:"normal"|"ride_closure"|"show_surge"|"heatwave"|"power_fault"|"water_leak"|"food_rush"}`: resulting complete state. Sets scenario and resets mitigations.
- `POST /api/actions` body `{action:"dispatch_maintenance"|"reroute_guests"|"add_staff"|"shed_load"|"repair_leak"|"replenish_stock"|"reset",asset_id?:string}`: `{synthetic:true,result:{id,action,asset_id,timestamp,message},state:{...}}`.
- `GET /api/audit?limit=100`: `{synthetic:true,events:[...]}`.
- `GET /api/health`: healthy, synthetic, DB and simulator tick.
- `WS /ws/state`: full state once per second. Polling `/api/state` once per second is equally supported.

Asset schema: `{id,name,type,scene_path,status,description,capacity,occupancy,queue_minutes,throughput_per_hour,power_kw,water_lpm,temperature_c,staff:{on_duty,required,qualifications},reservations:{booked,next_window_minutes},erp:{stock_units,stock_capacity,reorder_point,operating_cost_eur_per_hour},dependencies:[asset_id],maintenance:{inspection_status,health_pct,open_work_orders},metadata:{...},synthetic:true}`. Scene paths are `/World/Park/{id}`. Status values: `operational`, `warning`, `closed`, `fault`. IDs: `RIDE_COASTER`, `RIDE_WHEEL`, `SHOW_ARENA`, `FOOD_COURT`, `POWER_HUB`, `WATER_PLANT`, `ENTRY_GATE`, `PARKING`, `HOTEL`, `FIRST_AID`, `RESTROOMS`, `WEATHER_STATION`.

Alerts: `{id,severity,asset_id,title,message,recommended_action}`. Systems: `{id,name,protocol,status,last_sync,asset_ids,synthetic:true}`. Every source label explicitly identifies simulation. No external systems or physical controls are connected. Scene author can add spatial metadata later.

Actions are audited, validated for applicable assets, and affect subsequent telemetry. Duplicate dispatch does not create duplicate open work orders. Reset restores normal scenario, closes simulation work orders and clears mitigation state while preserving audit history. `dispatch_maintenance` records a work order; it deliberately does not claim a closed ride has been physically repaired. `repair_leak` is a simulated repair which resolves the water leak. History retains 3600 samples per asset. Browser static files and `/render/*` are reserved for the application integration.

## Install and test

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r requirements-backend.txt
backend/.venv/bin/python -m pytest -q tests/test_backend.py
backend/.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## Read-only scenario comparison

`GET /api/scenarios/compare?scenario=ride_closure` evaluates any scenario ID at the current tick without changing live scenario, mitigation state, audit, telemetry, registry, or work orders. It does not access the database: the comparison reads a consistent in-memory snapshot and invokes the same pure rules used by live simulation. The target scenario starts with mitigations cleared, matching activation behavior; the current baseline retains existing mitigations.

Response:

```json
{
  "synthetic": true,
  "method": "heuristic_same_tick_comparison",
  "mutates_live_state": false,
  "baseline_tick": 42,
  "timestamp": "...",
  "before": {"scenario": "normal", "kpis": {}, "weather": {}, "alerts": []},
  "after": {"scenario": "ride_closure", "kpis": {}, "weather": {}, "alerts": []},
  "deltas": [{"metric": "open_rides", "label": "Open rides", "unit": "rides", "before": 2, "after": 1, "delta": -1}],
  "asset_changes": [{"asset_id": "RIDE_COASTER", "name": "Skyline Coaster", "before_status": "operational", "after_status": "closed", "before_queue_minutes": 24, "after_queue_minutes": 0, "before_power_kw": 220, "after_power_kw": 18, "before_water_lpm": 2, "after_water_lpm": 2, "before_occupancy": 35, "after_occupancy": 0, "before_temperature_c": 24, "after_temperature_c": 24}],
  "assumptions": ["Illustrative synthetic rules, not a calibrated forecast or a claim of real-world savings."]
}
```

Missing/unknown scenario returns HTTP 422. `deltas` includes wait, open rides, power load/capacity, monitored water flow, alerts and illustrative operating cost. Negative delta is simply arithmetic, not necessarily a benefit: closing a ride reduces power but also removes capacity.

### Audit of model limits

- Mean queue wait is an **unweighted mean across active queues**; a closed attraction is excluded. A lower mean is not proof of an improved guest experience.
- Water KPI sums synthetic monitored flows, including circulation. It is **not net water consumption**.
- Operating costs use illustrative baseline staffing/power and 28 EUR/h per additional staff member; there is no calibrated financial or energy-price model.
- Comparisons hold time and attendance fixed; they do not predict pedestrian motion or a future time horizon.
- Ride maintenance dispatch creates an idempotent work order but never reopens a ride. Synthetic repair is implemented only for the water-leak demonstration.
- Frontend should display the returned assumptions or a visible synthetic-estimate label alongside comparisons.
