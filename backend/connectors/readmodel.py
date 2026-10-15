"""Canonical asset projection. The UI and replay consume this stable interface."""
from __future__ import annotations
import copy
from collections import OrderedDict
import hashlib
import json
from .catalog import LEGACY_FIELDS, set_path
from .alerts import project_alerts


class ParkReadModel:
    def __init__(self, park, connectors, revision_capacity=64, revision_max_bytes=4 * 1024 * 1024):
        if (type(revision_capacity) is not int or type(revision_max_bytes) is not int or
                not 1 <= revision_capacity <= 64 or not 1 <= revision_max_bytes <= 4 * 1024 * 1024):
            raise ValueError("Revision retention must fit 1–64 entries and 1 byte–4 MiB")
        self.park = park
        self.connectors = connectors
        self._revision_capacity = revision_capacity
        self._revision_max_bytes = revision_max_bytes
        self._revisions = OrderedDict()
        self._revision_bytes = 0

    def _retain_revision(self, state):
        """Freeze the first capture; duplicate reads neither refresh nor reorder it."""
        revision = state["accepted_state_revision"]
        with self.connectors.lock:
            if revision in self._revisions:
                return
            envelope = {"revision": revision,
                        "captured_at": self.connectors.clock().isoformat(timespec="microseconds"),
                        "state": state, "scope": "retained canonical state; not durable replay"}
            payload = json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            # An oversized single snapshot is unavailable; it must not flush the
            # useful bounded window or silently exceed its byte limit.
            if len(payload) > self._revision_max_bytes:
                return
            while self._revisions and (len(self._revisions) >= self._revision_capacity or
                                       self._revision_bytes + len(payload) > self._revision_max_bytes):
                _, oldest = self._revisions.popitem(last=False)
                self._revision_bytes -= len(oldest)
            self._revisions[revision] = payload
            self._revision_bytes += len(payload)

    def revision_snapshot(self, revision):
        """Read a retained capture without polling sources or changing the cache."""
        with self.connectors.lock:
            payload = self._revisions[revision.lower()]
        # Every caller receives a new object; the cache stores immutable bytes.
        return json.loads(payload)

    def snapshot(self):
        with self.connectors.lock:
            state = self.park.snapshot()
            model_statuses = {asset["id"]: asset["status"] for asset in state["assets"]}
            self.connectors.refresh(state)
            records = self.connectors.observations()["observations"]
            assets = {asset["id"]: asset for asset in state["assets"]}
            for asset in assets.values():
                asset["data_quality"] = {"status": "good", "fields": {}, "source_ids": []}
            for observation in records:
                if not observation["authoritative"]:
                    continue
                asset = assets[observation["asset_id"]]
                set_path(asset, observation["metric"], copy.deepcopy(observation["value"]))
                quality = {**observation["quality"], "source_id": observation["source_id"],
                           "source_timestamp": observation["source_timestamp"], "ingested_at": observation["ingested_at"],
                           "unit": observation["unit"], "synthetic": observation["provenance"]["synthetic"]}
                asset["data_quality"]["fields"][observation["metric"]] = quality
                if observation["source_id"] not in asset["data_quality"]["source_ids"]:
                    asset["data_quality"]["source_ids"].append(observation["source_id"])
                severity = {"good": 0, "uncertain": 1, "stale": 2, "unknown": 3}
                if severity[quality["status"]] > severity[asset["data_quality"]["status"]]:
                    asset["data_quality"]["status"] = quality["status"]
            # Missing source samples remain explicitly unknown. Existing baseline
            # values are kept only for compatibility; they are not claimed as observed.
            for source_id, spec in self.connectors.specs.items():
                store = self.connectors.stores[source_id]
                for mapping in spec.mappings:
                    if mapping.authoritative and (mapping.source_asset_id, mapping.metric) not in store.latest:
                        quality = assets[mapping.asset_id]["data_quality"]
                        quality["status"] = "unknown"
                        quality["fields"][mapping.metric] = {"status": "unknown", "source_id": source_id,
                                                             "unit": mapping.unit, "reasons": ["no_accepted_observation"]}
            state["connector_health"] = [self.connectors.health(source_id) for source_id in self.connectors.specs]
            health = {item["source_id"]: item for item in state["connector_health"]}
            for system in state["systems"]:
                source_id = system["id"]
                item = health[source_id]
                system.update(status="connected" if item["status"] == "healthy" else item["status"],
                              last_sync=item["last_ingested_at"], health=item,
                              source_timestamp=item["last_source_timestamp"],
                              protocol=f"Synthetic HTTP · planned {self.connectors.specs[source_id].planned_protocol}",
                              synthetic=self.connectors.adapters[source_id].synthetic)
        queue_assets = [a for a in assets.values() if a["queue_minutes"] > 0 and a["status"] not in {"closed", "fault"}]
        state["kpis"].update(
            average_wait_minutes=round(sum(a["queue_minutes"] for a in queue_assets) / max(1, len(queue_assets)), 1),
            queue_asset_count=len(queue_assets), excluded_closed_count=sum(a["status"] == "closed" for a in assets.values()),
            power_kw=round(sum(a["power_kw"] for a in assets.values()), 1),
            water_lpm=round(sum(a["water_lpm"] for a in assets.values()), 1),
            open_rides=sum(a["type"] == "ride" and a["status"] in {"operational", "warning"} for a in assets.values()),
            estimated_operating_cost_eur_per_hour=round(sum(a["erp"]["operating_cost_eur_per_hour"] for a in assets.values()), 2))
        state["weather"]["temperature_c"] = assets["WEATHER_STATION"]["temperature_c"]
        project_alerts(state, model_statuses)
        state["read_model"] = {"schema_version": "1.0", "source": "accepted_connector_observations",
                               "unmapped_fields_origin": "synthetic_model",
                               "quality_status": "good" if all(h["status"] == "healthy" for h in state["connector_health"]) else "degraded"}
        # Identity includes accepted values, their provenance and quality transitions.
        # Continuously increasing age is presentation data, not a new observation.
        def stable(value):
            if isinstance(value, dict):
                return {k: stable(v) for k, v in value.items() if k not in {"age_seconds", "max_age_seconds"}}
            if isinstance(value, list):
                return [stable(v) for v in value]
            return value
        content = {"tick": state["tick"], "timestamp": state["timestamp"],
                   "scenario": state["scenario"], "assets": state["assets"],
                   "sources": [{"source_id": h["source_id"], "status": h["status"], "mode": h["mode"]}
                               for h in state["connector_health"]]}
        state["accepted_state_revision"] = hashlib.sha256(json.dumps(stable(content), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self._retain_revision(state)
        return state

    def system_data(self, source_id):
        with self.connectors.lock:
            self.connectors.require_source(source_id)
            state = self.snapshot()
            system = next(s for s in state["systems"] if s["id"] == source_id)
            records = [{"asset_id": a["id"], **{k: a[k] for k in LEGACY_FIELDS[source_id]},
                        "synthetic": system["synthetic"]}
                       for a in state["assets"] if a["id"] in system["asset_ids"]]
            observations = self.connectors.observations(source_id=source_id)["observations"]
            by_asset = {record["asset_id"]: record for record in records}
            for observation in observations:
                # Source records retain that source's value even when a different
                # authoritative connector owns the canonical asset property.
                set_path(by_asset[observation["asset_id"]], observation["metric"], copy.deepcopy(observation["value"]))
            return {"synthetic": system["synthetic"], "timestamp": system["last_sync"], "system": system,
                    "records": records, "observations": observations}
