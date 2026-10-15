"""Canonical asset projection. The UI and replay consume this stable interface."""
from __future__ import annotations
import copy
from .catalog import LEGACY_FIELDS, set_path


class ParkReadModel:
    def __init__(self, park, connectors):
        self.park = park
        self.connectors = connectors

    def snapshot(self):
        with self.connectors.lock:
            state = self.park.snapshot()
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
        state["read_model"] = {"schema_version": "1.0", "source": "accepted_connector_observations",
                               "quality_status": "good" if all(h["status"] == "healthy" for h in state["connector_health"]) else "degraded"}
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
