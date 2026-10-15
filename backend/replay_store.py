"""Bounded, durable snapshots of the accepted operational read model.

This store never evaluates a scenario or writes to the live simulator. Payloads
are JSON compressed with zlib; historical values survive rule changes/restarts.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import zlib


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ReplayStore:
    def __init__(
        self,
        path: str | Path,
        scene_revision: str,
        config_revision: str,
        retention_limit: int = 7200,
    ):
        if retention_limit < 1:
            raise ValueError("Snapshot retention must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.scene_revision = scene_revision
        self.config_revision = config_revision
        self.retention_limit = retention_limit
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest TEXT NOT NULL UNIQUE,
                captured_at TEXT NOT NULL,
                source_timestamp TEXT NOT NULL,
                tick INTEGER NOT NULL,
                scenario TEXT NOT NULL,
                scene_revision TEXT NOT NULL,
                config_revision TEXT NOT NULL,
                summary TEXT NOT NULL,
                has_recorded_motion INTEGER NOT NULL,
                payload BLOB NOT NULL
            );
        """)
        self.db.commit()
        self._selected: dict | None = None

    def close(self):
        with self.lock:
            self.db.close()

    def capture(
        self,
        snapshot: dict,
        recorded_motion: dict | None = None,
        work_orders: list[dict] | None = None,
    ) -> int:
        payload = {
            "schema_version": "1.0",
            "snapshot": snapshot,
            "recorded_motion": recorded_motion,
            "work_orders": work_orders,
        }
        raw = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        digest = hashlib.sha256(
            raw + self.scene_revision.encode() + self.config_revision.encode()
        ).hexdigest()
        with self.lock:
            existing = self.db.execute(
                "SELECT id FROM snapshots WHERE digest=?", (digest,)
            ).fetchone()
            if existing:
                return existing["id"]
            cursor = self.db.execute(
                """INSERT INTO snapshots
                (digest,captured_at,source_timestamp,tick,scenario,scene_revision,
                 config_revision,summary,has_recorded_motion,payload)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    digest,
                    utc_now(),
                    snapshot["timestamp"],
                    snapshot["tick"],
                    snapshot["scenario"],
                    self.scene_revision,
                    self.config_revision,
                    json.dumps(snapshot["kpis"]),
                    int(recorded_motion is not None),
                    zlib.compress(raw, level=3),
                ),
            )
            ident = cursor.lastrowid
            self.db.execute(
                """DELETE FROM snapshots WHERE id NOT IN
                (SELECT id FROM snapshots ORDER BY id DESC LIMIT ?)""",
                (self.retention_limit,),
            )
            self.db.commit()
            return ident

    @staticmethod
    def _metadata(row) -> dict:
        return {
            **{
                key: row[key]
                for key in (
                    "id",
                    "captured_at",
                    "source_timestamp",
                    "tick",
                    "scenario",
                    "scene_revision",
                    "config_revision",
                )
            },
            "summary": json.loads(row["summary"]),
            "has_recorded_motion": bool(row["has_recorded_motion"]),
        }

    def timeline(self, limit: int = 300) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                """SELECT id,captured_at,source_timestamp,tick,scenario,
                scene_revision,config_revision,summary,has_recorded_motion FROM snapshots
                ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [self._metadata(row) for row in reversed(rows)]

    def get(self, ident: int) -> dict:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM snapshots WHERE id=?", (ident,)
            ).fetchone()
            if row is None:
                raise KeyError(ident)
            payload = json.loads(zlib.decompress(row["payload"]))
            return {**self._metadata(row), **payload}

    def select(self, ident: int | None) -> None:
        with self.lock:
            self._selected = self.get(ident) if ident is not None else None

    @property
    def is_replay(self) -> bool:
        with self.lock:
            return self._selected is not None

    def cursor(self) -> dict:
        with self.lock:
            return {
                "mode": "replay" if self._selected else "live",
                "snapshot_id": self._selected["id"] if self._selected else None,
            }

    def view_state(self, live: dict) -> dict:
        with self.lock:
            selected = copy.deepcopy(self._selected)
        state = selected["snapshot"] if selected else copy.deepcopy(live)
        if selected and selected["work_orders"] is not None:
            for asset in state["assets"]:
                asset["work_orders"] = [
                    order
                    for order in selected["work_orders"]
                    if order["asset_id"] == asset["id"]
                ]
        state["view"] = {
            "mode": "replay" if selected else "live",
            "snapshot_id": selected["id"] if selected else None,
            "captured_at": selected["captured_at"] if selected else None,
            "source_timestamp": state["timestamp"],
            "scene_revision": (
                selected["scene_revision"] if selected else self.scene_revision
            ),
            "config_revision": (
                selected["config_revision"] if selected else self.config_revision
            ),
            "scene_matches_current": not selected
            or selected["scene_revision"] == self.scene_revision,
            "recorded_motion": selected["recorded_motion"] if selected else None,
            "live_tick": live["tick"],
            "shared_session": True,
            "read_only": bool(selected),
            "work_orders_recorded": selected is not None
            and selected["work_orders"] is not None,
        }
        return state

    def history(self, asset_id: str, limit: int = 90) -> list[dict]:
        with self.lock:
            cutoff = self._selected["id"] if self._selected else 2**63 - 1
            rows = self.db.execute(
                "SELECT * FROM snapshots WHERE id<=? ORDER BY id DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
            history = []
            for row in reversed(rows):
                record = json.loads(zlib.decompress(row["payload"]))
                asset = next(
                    (a for a in record["snapshot"]["assets"] if a["id"] == asset_id),
                    None,
                )
                if asset:
                    history.append(
                        {
                            "snapshot_id": row["id"],
                            "timestamp": row["source_timestamp"],
                            "tick": row["tick"],
                            **{
                                key: asset[key]
                                for key in (
                                    "status",
                                    "queue_minutes",
                                    "occupancy",
                                    "power_kw",
                                    "water_lpm",
                                    "temperature_c",
                                )
                            },
                        }
                    )
            return history
