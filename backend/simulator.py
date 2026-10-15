"""Deterministic, synthetic park digital shadow backed by SQLite."""
from __future__ import annotations
import copy
import json
import math
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCENARIOS = [
    {"id": "normal", "label": "Normal operations", "description": "A typical synthetic operating day."},
    {"id": "ride_closure", "label": "Ride closure", "description": "Coaster fault displaces guests into nearby queues."},
    {"id": "show_surge", "label": "Show departure surge", "description": "An audience leaves the arena and increases food and ride demand."},
    {"id": "heatwave", "label": "Heatwave", "description": "High temperature raises cooling, water and first-aid demand."},
    {"id": "power_fault", "label": "Power feeder fault", "description": "A feeder fault closes the coaster and reduces usable power capacity."},
    {"id": "water_leak", "label": "Water leak", "description": "A leak increases plant flow and affects nearby facilities."},
    {"id": "food_rush", "label": "Lunch rush", "description": "Food queues grow while inventory and staffing become constrained."},
]
ACTIONS = [
    {"id": "dispatch_maintenance", "label": "Dispatch maintenance"},
    {"id": "reroute_guests", "label": "Reroute guests"},
    {"id": "add_staff", "label": "Add qualified staff"},
    {"id": "shed_load", "label": "Shed flexible load"},
    {"id": "repair_leak", "label": "Simulate leak repair"},
    {"id": "replenish_stock", "label": "Replenish food stock"},
    {"id": "reset", "label": "Reset simulation"},
]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def registry():
    # id, name, type, cap, occupancy, wait, throughput, kW, lpm, staff, qualification
    rows = [
        ("RIDE_COASTER", "Skyline Coaster", "ride", 48, 35, 24, 840, 220, 2, 6, "ride_operator_coaster"),
        ("RIDE_WHEEL", "Panorama Wheel", "ride", 96, 68, 12, 320, 42, 0, 3, "ride_operator_wheel"),
        ("SHOW_ARENA", "Lakeside Arena", "entertainment", 600, 310, 4, 600, 65, 4, 5, "crowd_steward"),
        ("FOOD_COURT", "Garden Food Court", "food", 240, 145, 8, 290, 85, 38, 12, "food_hygiene"),
        ("POWER_HUB", "Energy Center", "utility", 900, 0, 0, 0, 15, 0, 2, "electrical_authorized"),
        ("WATER_PLANT", "Water & Lake Plant", "utility", 650, 0, 0, 0, 28, 180, 2, "water_treatment"),
        ("ENTRY_GATE", "Welcome Plaza", "admission", 350, 85, 3, 1800, 12, 2, 8, "guest_services"),
        ("PARKING", "Arrival & EV Parking", "transport", 600, 355, 0, 300, 55, 0, 4, "traffic_steward"),
        ("HOTEL", "Parkside Lodge", "hospitality", 180, 125, 0, 25, 130, 62, 18, "hospitality"),
        ("FIRST_AID", "Guest Care", "care", 18, 3, 0, 24, 8, 5, 3, "first_aid_certified"),
        ("RESTROOMS", "Central Restrooms", "facility", 36, 12, 2, 200, 7, 28, 3, "facilities_service"),
        ("WEATHER_STATION", "Weather Mast", "sensor", 1, 0, 0, 0, 0.3, 0, 0, "instrumentation"),
    ]
    descriptions = {
        "RIDE_COASTER": "Coaster telemetry, ride availability, queue demand and certified staffing.",
        "RIDE_WHEEL": "Wheel operations and reserve attraction capacity for diverted guests.",
        "SHOW_ARENA": "Show schedule, audience capacity and predicted departure surge.",
        "FOOD_COURT": "Restaurant demand, kitchen staffing, ERP inventory and service cost.",
        "POWER_HUB": "Electrical feeder dependencies, flexible demand and consumption.",
        "WATER_PLANT": "Water supply, lake circulation, leak detection and treatment.",
        "ENTRY_GATE": "Ticket admission, reservations and occupancy estimation.",
        "PARKING": "Arrival demand, car occupancy, EV charging and transport connections.",
        "HOTEL": "Resort occupancy, cooling demand and hospitality services.",
        "FIRST_AID": "Guest care readiness, occupancy and certified responders.",
        "RESTROOMS": "Water use, facility occupancy, cleaning and service readiness.",
        "WEATHER_STATION": "Synthetic local weather driving operational forecasts.",
    }
    out = []
    for ident, name, kind, cap, occ, wait, throughput, power, water, staff, qual in rows:
        dependencies = [] if ident in {"POWER_HUB", "WEATHER_STATION"} else ["POWER_HUB"]
        if ident in {"FOOD_COURT", "HOTEL", "RESTROOMS", "FIRST_AID"}:
            dependencies.append("WATER_PLANT")
        out.append({"id": ident, "name": name, "type": kind, "scene_path": f"/World/Park/{ident}",
                    "description": descriptions[ident], "capacity": cap, "occupancy": occ,
                    "queue_minutes": wait, "throughput_per_hour": throughput, "power_kw": power,
                    "water_lpm": water, "temperature_c": 24.0,
                    "staff": {"on_duty": staff, "required": staff, "qualifications": [qual]},
                    "reservations": {"booked": int(cap * .35), "next_window_minutes": 15},
                    "erp": {"stock_units": 420 if ident == "FOOD_COURT" else 80,
                            "stock_capacity": 600 if ident == "FOOD_COURT" else 100,
                            "reorder_point": 120 if ident == "FOOD_COURT" else 20,
                            "operating_cost_eur_per_hour": round(staff * 28 + power * .22, 2)},
                    "dependencies": dependencies,
                    "maintenance": {"inspection_status": "passed", "health_pct": 98, "open_work_orders": 0},
                    "metadata": {"source": "Synthetic park simulator", "baseline_power_kw": power,
                                 "accessibility": "Accessible guest route; attraction-specific boarding requirements apply"},
                    "synthetic": True})
    return out


SYSTEM_DEFS = [
    ("ride_scada", "Simulated Ride SCADA", "OPC UA emulator", ["RIDE_COASTER", "RIDE_WHEEL"]),
    ("ticketing", "Simulated Ticketing & Reservations", "REST emulator", ["ENTRY_GATE", "RIDE_COASTER", "RIDE_WHEEL", "SHOW_ARENA"]),
    ("vision", "Simulated People Counters", "MQTT emulator", ["ENTRY_GATE", "SHOW_ARENA", "FOOD_COURT", "PARKING"]),
    ("cmms", "Simulated Maintenance CMMS", "REST / SQLite", ["RIDE_COASTER", "RIDE_WHEEL", "POWER_HUB", "WATER_PLANT"]),
    ("erp", "Simulated ERP & POS", "REST / SQLite", ["FOOD_COURT", "HOTEL"]),
    ("workforce", "Simulated Workforce", "REST emulator", ["ENTRY_GATE", "FOOD_COURT", "RIDE_COASTER", "FIRST_AID"]),
    ("bms", "Simulated Building & Energy", "BACnet emulator", ["POWER_HUB", "HOTEL", "FOOD_COURT", "PARKING"]),
    ("water", "Simulated Water Management", "MQTT emulator", ["WATER_PLANT", "RESTROOMS"]),
    ("weather", "Simulated Local Weather", "REST emulator", ["WEATHER_STATION"]),
    ("gis", "Park Asset Registry / OpenUSD", "USD paths / SQLite", [a["id"] for a in registry()]),
]


class ParkSimulator:
    def __init__(self, database_path: str):
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS telemetry(asset_id TEXT, tick INTEGER, timestamp TEXT, data TEXT, PRIMARY KEY(asset_id,tick));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, action TEXT, asset_id TEXT, message TEXT);
            CREATE TABLE IF NOT EXISTS work_orders(id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT, status TEXT, created_at TEXT, title TEXT);
        """)
        for asset in registry():
            self.db.execute("INSERT OR IGNORE INTO assets VALUES (?,?)", (asset["id"], json.dumps(asset)))
        self.db.commit()
        self.base = {row["id"]: json.loads(row["data"]) for row in self.db.execute("SELECT * FROM assets")}
        self.scenario = self._setting("scenario", "normal")
        self.mitigations = self._setting("mitigations", {})
        self.tick = self._setting("tick", 0)
        self.state = {}
        self.advance()

    def _setting(self, key, default):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _save(self):
        for key, value in (("scenario", self.scenario), ("mitigations", self.mitigations), ("tick", self.tick)):
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def close(self):
        with self.lock:
            self.db.close()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def _audit(self, action, asset_id, message):
        timestamp = utc_now()
        cursor = self.db.execute("INSERT INTO audit(timestamp,action,asset_id,message) VALUES (?,?,?,?)", (timestamp, action, asset_id, message))
        return {"id": cursor.lastrowid, "timestamp": timestamp, "action": action, "asset_id": asset_id, "message": message}

    def audit(self, limit=100, asset_id=None):
        with self.lock:
            if asset_id:
                rows = self.db.execute("SELECT * FROM audit WHERE asset_id=? ORDER BY id DESC LIMIT ?", (asset_id, limit))
            else:
                rows = self.db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in rows]

    def history(self, asset_id, limit=120):
        with self.lock:
            if asset_id not in self.base:
                raise KeyError(asset_id)
            rows = list(self.db.execute("SELECT data FROM telemetry WHERE asset_id=? ORDER BY tick DESC LIMIT ?", (asset_id, limit)))
            return [json.loads(row[0]) for row in reversed(rows)]

    def asset(self, asset_id):
        with self.lock:
            if asset_id not in self.base:
                raise KeyError(asset_id)
            asset = copy.deepcopy(next(a for a in self.state["assets"] if a["id"] == asset_id))
            asset["history"] = self.history(asset_id)
            asset["work_orders"] = [dict(r) for r in self.db.execute("SELECT * FROM work_orders WHERE asset_id=? ORDER BY id DESC LIMIT 50", (asset_id,))]
            asset["audit"] = self.audit(30, asset_id)
            return asset

    def set_scenario(self, scenario):
        if scenario not in {s["id"] for s in SCENARIOS}:
            raise ValueError("Unknown scenario")
        with self.lock:
            self.scenario = scenario
            self.mitigations = {}
            self._audit("scenario", None, f"Synthetic scenario set to {scenario}")
            self.advance()
            return self.snapshot()

    def act(self, action, asset_id=None):
        if action not in {a["id"] for a in ACTIONS}:
            raise ValueError("Unknown action")
        if asset_id is not None and asset_id not in self.base:
            raise KeyError(asset_id)
        with self.lock:
            defaults = {"dispatch_maintenance": "RIDE_COASTER", "reroute_guests": "RIDE_WHEEL", "add_staff": "FOOD_COURT", "shed_load": "POWER_HUB", "repair_leak": "WATER_PLANT", "replenish_stock": "FOOD_COURT"}
            target = asset_id or defaults.get(action)
            if action == "reset":
                self.scenario = "normal"
                self.mitigations = {}
                self.db.execute("UPDATE work_orders SET status='closed_by_reset' WHERE status='open'")
                message = "Synthetic park restored to normal operations; audit retained."
            elif action == "dispatch_maintenance":
                if self.base[target]["type"] not in {"ride", "utility", "facility"}:
                    raise ValueError("Maintenance dispatch requires a ride, utility or facility")
                existing = self.db.execute("SELECT id FROM work_orders WHERE asset_id=? AND status='open'", (target,)).fetchone()
                if existing:
                    message = f"Existing synthetic work order #{existing[0]} remains assigned."
                else:
                    cursor = self.db.execute("INSERT INTO work_orders(asset_id,status,created_at,title) VALUES (?,'open',?,?)", (target, utc_now(), "Inspect synthetic operational fault"))
                    message = f"Synthetic work order #{cursor.lastrowid} created and qualified maintenance assigned."
            elif action == "reroute_guests":
                if self.base[target]["type"] not in {"ride", "entertainment", "admission", "food"}:
                    raise ValueError("Guest routing requires a ride, entertainment, admission or food asset")
                self.mitigations["reroute_guests"] = True
                message = "Synthetic guest guidance activated: spread excess demand across available attractions."
            elif action == "add_staff":
                if self.base[target]["staff"]["required"] == 0:
                    raise ValueError("Asset has no operational staffing demand")
                self.mitigations[f"staff:{target}"] = 2
                message = f"Two simulated staff with {self.base[target]['staff']['qualifications'][0]} qualification assigned."
            elif action == "shed_load":
                if target not in {"POWER_HUB", "HOTEL", "PARKING", "FOOD_COURT"}:
                    raise ValueError("Flexible load shedding applies to energy, hotel, parking or food assets")
                self.mitigations["shed_load"] = True
                message = "Synthetic flexible load reduced: EV charging and noncritical HVAC. Ride safety power unchanged."
            elif action == "repair_leak":
                if target != "WATER_PLANT":
                    raise ValueError("Leak repair requires WATER_PLANT")
                self.mitigations["repair_leak"] = True
                self.db.execute("UPDATE work_orders SET status='completed' WHERE asset_id='WATER_PLANT' AND status='open'")
                message = "Synthetic leak isolated and repaired; plant flow restored."
            elif action == "replenish_stock":
                if target != "FOOD_COURT":
                    raise ValueError("Food replenishment requires FOOD_COURT")
                self.mitigations["replenish_stock"] = True
                message = "Synthetic ERP replenishment received: food inventory restored to 600 units."
            result = self._audit(action, target, message)
            self.advance()
            return {"synthetic": True, "result": result, "state": self.snapshot()}

    def _evaluate(self, scenario, mitigations, tick, now, work_order_counts, recent_actions):
        """Evaluate demo rules without changing simulator state or touching storage."""
        assets = copy.deepcopy(self.base)
        wave = math.sin(tick / 25)
        temp = (38 if scenario == "heatwave" else 24) + wave * .5
        for i, a in enumerate(assets.values()):
            variation = math.sin(tick / 20 + i) * .035
            a["status"] = "operational"
            a["occupancy"] = max(0, min(a["capacity"], round(a["occupancy"] * (1 + variation))))
            a["queue_minutes"] = max(0, round(a["queue_minutes"] * (1 + variation), 1))
            a["power_kw"] *= 1 + variation
            a["water_lpm"] *= 1 + variation
            a["temperature_c"] = round(temp, 1)
            extra_staff = mitigations.get(f"staff:{a['id']}", 0)
            a["staff"]["on_duty"] += extra_staff
            a["erp"]["operating_cost_eur_per_hour"] += extra_staff * 28
            a["maintenance"]["open_work_orders"] = work_order_counts.get(a["id"], 0)
            a["timestamp"] = now
        coaster, wheel, food = assets["RIDE_COASTER"], assets["RIDE_WHEEL"], assets["FOOD_COURT"]
        alerts = []
        def alert(ident, severity, target, title, message, action):
            alerts.append({"id": ident, "severity": severity, "asset_id": target, "title": title, "message": message, "recommended_action": action})
        if scenario in {"ride_closure", "power_fault"}:
            coaster.update(status="closed", occupancy=0, throughput_per_hour=0, queue_minutes=0, power_kw=18)
            coaster["maintenance"].update(health_pct=42, inspection_status="review_required")
            wheel.update(status="warning", queue_minutes=32 + wave)
            food["queue_minutes"] += 10
            alert("ride_unavailable", "critical", "RIDE_COASTER", "Coaster unavailable", "Synthetic fault: dispatch maintenance; displaced guests increase nearby queues.", "dispatch_maintenance")
        if scenario == "power_fault":
            assets["POWER_HUB"].update(status="fault", capacity=540)
            assets["HOTEL"]["status"] = "warning"
            alert("feeder_fault", "critical", "POWER_HUB", "Feeder capacity reduced", "Synthetic power capacity is limited to 540 kW. Flexible load shedding reduces demand; feeder repair is still required.", "shed_load")
        if scenario == "show_surge":
            assets["SHOW_ARENA"].update(status="warning", occupancy=560)
            food.update(queue_minutes=29, occupancy=228, status="warning")
            wheel["queue_minutes"] += 18
            coaster["queue_minutes"] += 15
            alert("crowd_surge", "warning", "SHOW_ARENA", "Show departure demand", "560 synthetic guests are entering the plaza and nearby queues.", "reroute_guests")
        if scenario == "heatwave":
            for ident in ("HOTEL", "FOOD_COURT", "FIRST_AID"):
                assets[ident]["power_kw"] *= 1.3
                assets[ident]["water_lpm"] *= 1.4
            assets["FIRST_AID"].update(occupancy=13, status="warning")
            assets["WATER_PLANT"]["water_lpm"] *= 1.4
            alert("heat", "warning", "FIRST_AID", "Heat response needed", "Synthetic 38°C conditions increase cooling, hydration and guest-care demand.", "add_staff")
        if scenario == "water_leak" and not mitigations.get("repair_leak"):
            assets["WATER_PLANT"].update(water_lpm=560 + wave * 6, status="fault")
            assets["WATER_PLANT"]["maintenance"]["health_pct"] = 55
            assets["RESTROOMS"].update(status="warning", queue_minutes=9)
            alert("water_leak", "critical", "WATER_PLANT", "Abnormal water flow", "Synthetic leak adds approximately 380 L/min; dependent facilities need attention.", "repair_leak")
        if scenario == "food_rush":
            food.update(status="warning", queue_minutes=34, occupancy=235)
            food["staff"]["required"] = 14
            food["erp"]["stock_units"] = 60
            alert("food_demand", "warning", "FOOD_COURT", "Kitchen capacity constrained", "Synthetic lunch demand raises waits; add qualified staff and replenish stock.", "add_staff")
        if mitigations.get("reroute_guests"):
            for ident in ("RIDE_COASTER", "RIDE_WHEEL", "FOOD_COURT"):
                assets[ident]["queue_minutes"] *= .65
            assets["SHOW_ARENA"]["occupancy"] = round(assets["SHOW_ARENA"]["occupancy"] * .8)
        if mitigations.get("shed_load"):
            assets["HOTEL"]["power_kw"] *= .75
            assets["PARKING"]["power_kw"] *= .35
            assets["FOOD_COURT"]["power_kw"] *= .92
        if mitigations.get("replenish_stock"):
            food["erp"]["stock_units"] = 600
        if scenario == "food_rush" and mitigations.get("staff:FOOD_COURT") and mitigations.get("replenish_stock"):
            food["status"] = "operational"
            alerts = [a for a in alerts if a["id"] != "food_demand"]
        for a in assets.values():
            if mitigations.get(f"staff:{a['id']}"):
                a["queue_minutes"] *= .7
                if a["status"] != "closed":
                    a["throughput_per_hour"] = round(a["throughput_per_hour"] * 1.15)
            for metric in ("queue_minutes", "power_kw", "water_lpm"):
                a[metric] = round(a[metric], 1)
        if food["erp"]["stock_units"] < food["erp"]["reorder_point"]:
            alert("food_stock", "warning", "FOOD_COURT", "Stock below reorder point", "Synthetic ERP food stock is below 120 units.", "replenish_stock")
        systems = [{"id": ident, "name": name, "protocol": protocol, "status": "connected", "last_sync": now,
                    "asset_ids": ids, "synthetic": True} for ident, name, protocol, ids in SYSTEM_DEFS]
        queue_assets = [a for a in assets.values() if a["queue_minutes"] > 0]
        return {"synthetic": True, "timestamp": now, "tick": tick, "scenario": scenario,
                      "assets": list(assets.values()), "weather": {"temperature_c": round(temp, 1), "wind_kph": round(9 + wave * 2, 1), "condition": "heat advisory" if scenario == "heatwave" else "partly cloudy"},
                      "systems": systems, "alerts": alerts, "scenarios": SCENARIOS, "actions": ACTIONS,
                      "recent_actions": recent_actions,
                      "kpis": {"attendance": 3420 + round(wave * 35), "total_capacity": 6200,
                               "average_wait_minutes": round(sum(a["queue_minutes"] for a in queue_assets) / max(1, len(queue_assets)), 1),
                               "power_kw": round(sum(a["power_kw"] for a in assets.values()), 1),
                               "power_capacity_kw": assets["POWER_HUB"]["capacity"],
                               "water_lpm": round(sum(a["water_lpm"] for a in assets.values()), 1),
                               "open_rides": sum(a["type"] == "ride" and a["status"] != "closed" for a in assets.values()),
                               "active_alerts": len(alerts),
                               "estimated_operating_cost_eur_per_hour": round(sum(a["erp"]["operating_cost_eur_per_hour"] for a in assets.values()), 2)}}

    def compare(self, scenario):
        """Same-tick hypothetical comparison; no database reads or writes."""
        if scenario not in {s["id"] for s in SCENARIOS}:
            raise ValueError("Unknown scenario")
        with self.lock:
            before = self.snapshot()
            counts = {a["id"]: a["maintenance"]["open_work_orders"] for a in before["assets"]}
            after = self._evaluate(scenario, {}, before["tick"], before["timestamp"], counts, before["recent_actions"])
            metrics = [
                ("average_wait_minutes", "Mean active queue wait", "min"),
                ("open_rides", "Open rides", "rides"),
                ("power_kw", "Reported power load", "kW"),
                ("power_capacity_kw", "Available feeder capacity", "kW"),
                ("water_lpm", "Total monitored water flow", "L/min"),
                ("active_alerts", "Active alerts", "alerts"),
                ("estimated_operating_cost_eur_per_hour", "Illustrative operating cost", "EUR/h"),
            ]
            deltas = [{"metric": key, "label": label, "unit": unit,
                       "before": before["kpis"][key], "after": after["kpis"][key],
                       "delta": round(after["kpis"][key] - before["kpis"][key], 2)}
                      for key, label, unit in metrics]
            before_assets = {a["id"]: a for a in before["assets"]}
            changes = []
            fields = ("status", "queue_minutes", "power_kw", "water_lpm", "occupancy", "temperature_c")
            for asset in after["assets"]:
                previous = before_assets[asset["id"]]
                if any(previous[key] != asset[key] for key in fields):
                    change = {"asset_id": asset["id"], "name": asset["name"]}
                    for key in fields:
                        change[f"before_{key}"] = previous[key]
                        change[f"after_{key}"] = asset[key]
                    changes.append(change)
            summary_keys = ("scenario", "kpis", "weather", "alerts")
            return {
                "synthetic": True, "method": "heuristic_same_tick_comparison",
                "mutates_live_state": False, "baseline_tick": before["tick"],
                "timestamp": before["timestamp"],
                "before": {key: before[key] for key in summary_keys},
                "after": {key: after[key] for key in summary_keys},
                "deltas": deltas, "asset_changes": changes,
                "assumptions": [
                    "Illustrative synthetic rules, not a calibrated forecast or a claim of real-world savings.",
                    "Both cases use the same simulation tick, attendance and base assets; no future time horizon is modeled.",
                    "Before retains current mitigations. After applies the selected scenario with mitigations cleared, matching scenario activation.",
                    "Mean queue wait is unweighted across active queues; a closed ride is excluded and can make this average misleading.",
                    "Total monitored water flow sums synthetic asset readings, including circulation; it is not net utility consumption.",
                    "Operating cost uses illustrative baseline staffing and energy assumptions, with added staff at 28 EUR/h; it is not a financial model.",
                ],
            }

    def advance(self):
        with self.lock:
            self.tick += 1
            now = utc_now()
            counts = {row["asset_id"]: row["total"] for row in self.db.execute(
                "SELECT asset_id, COUNT(*) AS total FROM work_orders WHERE status='open' GROUP BY asset_id")}
            self.state = self._evaluate(self.scenario, self.mitigations, self.tick, now, counts, self.audit(12))
            for asset in self.state["assets"]:
                sample = {"timestamp": now, "tick": self.tick,
                          **{k: asset[k] for k in ("status", "queue_minutes", "occupancy", "power_kw", "water_lpm", "temperature_c")}}
                self.db.execute("INSERT OR REPLACE INTO telemetry VALUES (?,?,?,?)",
                                (asset["id"], self.tick, now, json.dumps(sample)))
            self.db.execute("DELETE FROM telemetry WHERE tick <= ?", (self.tick - 3600,))
            self._save()
            self.db.commit()
