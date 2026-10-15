"""Declarative domain mappings shared by simulated and future source adapters."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from backend.domain import SYSTEM_DEFS, registry


@dataclass(frozen=True)
class Metric:
    path: str
    unit: str
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()


METRICS = {
    "status": Metric("status", "state", "string", choices=("operational", "warning", "closed", "fault")),
    "throughput_per_hour": Metric("throughput_per_hour", "people/h", "number", 0),
    "power_kw": Metric("power_kw", "kW", "number", 0),
    "water_lpm": Metric("water_lpm", "L/min", "number", 0),
    "temperature_c": Metric("temperature_c", "Cel", "number", -60, 80),
    "occupancy": Metric("occupancy", "people", "integer", 0),
    "capacity": Metric("capacity", "people", "integer", 0),
    "queue_minutes": Metric("queue_minutes", "min", "number", 0),
    "reservations.booked": Metric("reservations.booked", "reservations", "integer", 0),
    "reservations.next_window_minutes": Metric("reservations.next_window_minutes", "min", "number", 0),
    "maintenance.inspection_status": Metric("maintenance.inspection_status", "state", "string", choices=("passed", "review_required", "pending", "failed")),
    "maintenance.health_pct": Metric("maintenance.health_pct", "%", "number", 0, 100),
    "maintenance.open_work_orders": Metric("maintenance.open_work_orders", "work_orders", "integer", 0),
    "erp.stock_units": Metric("erp.stock_units", "items", "integer", 0),
    "erp.stock_capacity": Metric("erp.stock_capacity", "items", "integer", 0),
    "erp.reorder_point": Metric("erp.reorder_point", "items", "integer", 0),
    "erp.operating_cost_eur_per_hour": Metric("erp.operating_cost_eur_per_hour", "EUR/h", "number", 0),
    "staff.on_duty": Metric("staff.on_duty", "people", "integer", 0),
    "staff.required": Metric("staff.required", "people", "integer", 0),
    "staff.qualifications": Metric("staff.qualifications", "qualification_id[]", "strings"),
    "dependencies": Metric("dependencies", "asset_id[]", "assets"),
    "scene_path": Metric("scene_path", "USD prim path", "scene_path"),
    "metadata.accessibility": Metric("metadata.accessibility", "text", "string"),
}
DOMAIN_FIELDS = {
    "ride_scada": ("status", "throughput_per_hour", "power_kw", "maintenance.inspection_status", "maintenance.health_pct", "maintenance.open_work_orders"),
    "ticketing": ("occupancy", "capacity", "reservations.booked", "reservations.next_window_minutes", "queue_minutes"),
    "vision": ("occupancy", "capacity", "queue_minutes"),
    "cmms": ("maintenance.inspection_status", "maintenance.health_pct", "maintenance.open_work_orders", "dependencies"),
    "erp": ("erp.stock_units", "erp.stock_capacity", "erp.reorder_point", "erp.operating_cost_eur_per_hour", "throughput_per_hour"),
    "workforce": ("staff.on_duty", "staff.required", "staff.qualifications"),
    "bms": ("power_kw", "temperature_c", "dependencies"),
    "water": ("water_lpm", "status", "dependencies"),
    "weather": ("temperature_c",),
    "gis": ("scene_path", "metadata.accessibility", "dependencies"),
}
LEGACY_FIELDS = {
    "ride_scada": ["status", "throughput_per_hour", "power_kw", "maintenance"],
    "ticketing": ["occupancy", "capacity", "reservations", "queue_minutes"],
    "vision": ["occupancy", "capacity", "queue_minutes"],
    "cmms": ["maintenance", "dependencies"], "erp": ["erp", "throughput_per_hour"],
    "workforce": ["staff"], "bms": ["power_kw", "temperature_c", "dependencies"],
    "water": ["water_lpm", "status", "dependencies"], "weather": ["temperature_c"],
    "gis": ["scene_path", "metadata", "dependencies"],
}
PLANNED_PROTOCOLS = {"ride_scada": "OPC UA", "ticketing": "vendor REST", "vision": "MQTT / ONVIF metadata",
                     "cmms": "CMMS REST", "erp": "ERP / POS REST", "workforce": "workforce REST",
                     "bms": "BACnet gateway", "water": "MQTT / utility gateway", "weather": "weather REST", "gis": "OpenUSD / GIS"}


@dataclass(frozen=True)
class Mapping:
    source_asset_id: str
    asset_id: str
    metric: str
    unit: str
    authoritative: bool

    def as_dict(self):
        definition = METRICS[self.metric]
        return {"source_asset_id": self.source_asset_id, "asset_id": self.asset_id, "metric": self.metric,
                "destination": definition.path, "unit": self.unit, "value_type": definition.kind,
                "authoritative": self.authoritative, "minimum": definition.minimum,
                "maximum": definition.maximum, "choices": list(definition.choices)}


@dataclass(frozen=True)
class ConnectorSpec:
    id: str
    name: str
    planned_protocol: str
    asset_ids: tuple[str, ...]
    mappings: tuple[Mapping, ...]
    stale_after_seconds: float = 5.0


def get_path(record: dict, path: str) -> Any:
    value = record
    for key in path.split("."):
        value = value[key]
    return value


def set_path(record: dict, path: str, value: Any):
    keys = path.split(".")
    for key in keys[:-1]:
        record = record.setdefault(key, {})
    record[keys[-1]] = value


def default_catalog():
    specs = []
    ticketing_assets = {"ENTRY_GATE", "RIDE_COASTER", "RIDE_WHEEL", "SHOW_ARENA"}
    for source_id, name, _, asset_ids in SYSTEM_DEFS:
        mappings = []
        for asset_id in asset_ids:
            fields = DOMAIN_FIELDS[source_id]
            if source_id == "bms" and asset_id == "POWER_HUB":
                fields = (*fields, "status")
            for metric in fields:
                authoritative = True
                if metric == "dependencies":
                    authoritative = source_id == "gis"
                elif metric.startswith("maintenance."):
                    authoritative = source_id == "cmms"
                elif source_id == "vision" and asset_id in ticketing_assets:
                    authoritative = False
                unit = METRICS[metric].unit
                if asset_id == "PARKING" and metric in {"capacity", "occupancy"}:
                    unit = "vehicles"
                mappings.append(Mapping(f"{source_id}/{asset_id}", asset_id, metric, unit, authoritative))
        specs.append(ConnectorSpec(source_id, name, PLANNED_PROTOCOLS[source_id], tuple(asset_ids), tuple(mappings)))
    validate_catalog(specs, {a["id"] for a in registry()})
    return specs


def validate_catalog(specs, known_assets):
    source_ids, owners = set(), {}
    for spec in specs:
        if spec.id in source_ids:
            raise ValueError(f"Duplicate connector ID: {spec.id}")
        source_ids.add(spec.id)
        if spec.stale_after_seconds <= 0:
            raise ValueError("Freshness threshold must be positive")
        keys = set()
        for mapping in spec.mappings:
            if mapping.asset_id not in known_assets or mapping.asset_id not in spec.asset_ids:
                raise ValueError(f"Unknown asset mapping: {mapping.asset_id}")
            if mapping.metric not in METRICS:
                raise ValueError(f"Unknown metric: {mapping.metric}")
            key = (mapping.source_asset_id, mapping.metric)
            if key in keys:
                raise ValueError(f"Duplicate source mapping: {key}")
            keys.add(key)
            if mapping.authoritative:
                owner_key = (mapping.asset_id, mapping.metric)
                if owner_key in owners:
                    raise ValueError(f"Multiple authoritative sources for {owner_key}")
                owners[owner_key] = spec.id
