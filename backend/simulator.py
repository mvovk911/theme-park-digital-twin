"""Deterministic, synthetic park digital shadow backed by SQLite."""
from __future__ import annotations
import copy
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

# Compatibility exports retained for existing callers.
from .domain import ACTIONS, SCENARIOS, SYSTEM_DEFS, registry
from .model_rules import evaluate


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ActionRequestConflict(ValueError):
    """A durable request ID was already used for another normalized action."""


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
            CREATE TABLE IF NOT EXISTS action_receipts(request_id TEXT PRIMARY KEY, payload TEXT NOT NULL, acknowledgement TEXT NOT NULL);
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

    def workflow_snapshot(self):
        """Bounded workflow context for replay, read atomically with its tick."""
        with self.lock:
            rows = self.db.execute("SELECT * FROM work_orders ORDER BY id DESC LIMIT 300")
            return {"tick": self.tick, "work_orders": [dict(row) for row in rows]}

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

    def act(self, action, asset_id=None, request_id=None):
        if action not in {a["id"] for a in ACTIONS}:
            raise ValueError("Unknown action")
        if asset_id is not None and asset_id not in self.base:
            raise KeyError(asset_id)
        if request_id is not None and (not isinstance(request_id, str) or
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id) is None):
            raise ValueError("request_id must be 1–128 letters, digits, dots, underscores, colons or hyphens, starting with a letter or digit")
        defaults = {"dispatch_maintenance": "RIDE_COASTER", "reroute_guests": "RIDE_WHEEL", "add_staff": "FOOD_COURT", "shed_load": "POWER_HUB", "repair_leak": "WATER_PLANT", "replenish_stock": "FOOD_COURT"}
        target = asset_id or defaults.get(action)
        payload = json.dumps({"action": action, "asset_id": target}, sort_keys=True, separators=(",", ":"))
        with self.lock:
            previous = (self.scenario, copy.deepcopy(self.mitigations), self.tick, copy.deepcopy(self.state))
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if request_id is not None:
                    receipt = self.db.execute("SELECT payload, acknowledgement FROM action_receipts WHERE request_id=?", (request_id,)).fetchone()
                    if receipt:
                        if receipt["payload"] != payload:
                            raise ActionRequestConflict("request_id already acknowledged a different action or target")
                        self.db.rollback()  # Read-only retry: release the transaction without advancing.
                        return {"synthetic": True, "result": json.loads(receipt["acknowledgement"]),
                                "idempotency": {"request_id": request_id, "replayed": True}, "state": self.snapshot()}
                result = self._apply_action(action, target)
                result["request_id"] = request_id
                self._advance_uncommitted()
                if request_id is not None:
                    self.db.execute("INSERT INTO action_receipts VALUES (?,?,?)",
                                    (request_id, payload, json.dumps(result, sort_keys=True, allow_nan=False)))
                self.db.commit()
            except BaseException:
                try:
                    self.db.rollback()
                finally:
                    self.scenario, self.mitigations, self.tick, self.state = previous
                raise
            return {"synthetic": True, "result": result,
                    "idempotency": {"request_id": request_id, "replayed": False}, "state": self.snapshot()}

    def _apply_action(self, action, target):
        """Apply simulated effects and audit inside the caller's transaction/lock."""
        work_order_id = None
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
                work_order_id = existing[0]
                message = f"Existing synthetic work order #{existing[0]} remains assigned."
            else:
                cursor = self.db.execute("INSERT INTO work_orders(asset_id,status,created_at,title) VALUES (?,'open',?,?)", (target, utc_now(), "Inspect synthetic operational fault"))
                work_order_id = cursor.lastrowid
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
        result.update(synthetic=True, acknowledgement="accepted",
                      target={"scope": "park" if action == "reset" else "asset",
                              "asset_id": None if action == "reset" else target},
                      lifecycle="work_order_open" if action == "dispatch_maintenance" else "simulation_applied",
                      physical_effect=False)
        if work_order_id is not None:
            result["work_order_id"] = work_order_id
        return result

    def _evaluate(self, scenario, mitigations, tick, now, work_order_counts, recent_actions):
        """Compatibility wrapper around the storage-independent scenario model."""
        return evaluate(self.base, scenario, mitigations, tick, now, work_order_counts, recent_actions)

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
                "baseline_source": "synthetic_simulator",
                "mutates_live_state": False, "baseline_tick": before["tick"],
                "timestamp": before["timestamp"],
                "before": {key: before[key] for key in summary_keys},
                "after": {key: after[key] for key in summary_keys},
                "deltas": deltas, "asset_changes": changes,
                "assumptions": [
                    "Illustrative synthetic rules, not a calibrated forecast or a claim of real-world savings.",
                    "Both cases use the same simulation tick, attendance and base assets; no future time horizon is modeled.",
                    "The baseline is the synthetic simulator; injected connector observations are not inputs to this scenario model.",
                    "Before retains current mitigations. After applies the selected scenario with mitigations cleared, matching scenario activation.",
                    "Mean queue wait is unweighted across active queues; a closed ride is excluded and can make this average misleading.",
                    "Total monitored water flow sums synthetic asset readings, including circulation; it is not net utility consumption.",
                    "Operating cost uses illustrative baseline staffing and energy assumptions, with added staff at 28 EUR/h; it is not a financial model.",
                ],
            }

    def advance(self):
        with self.lock:
            self._advance_uncommitted()
            self.db.commit()

    def _advance_uncommitted(self):
        """Persist a model step; the caller owns the lock and commit boundary."""
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
