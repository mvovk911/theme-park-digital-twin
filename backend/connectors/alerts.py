"""Explainable operational alerts over canonical fields, distinct from model forecasts."""
from __future__ import annotations
import copy
from .catalog import get_path


def project_alerts(state, model_statuses):
    assets = {asset["id"]: asset for asset in state["assets"]}
    model_alerts = [{**copy.deepcopy(alert), "origin": "synthetic_model"} for alert in state["alerts"]]
    alerts = []

    def evidence(asset_id, metric):
        asset = assets[asset_id]
        quality = asset["data_quality"]["fields"].get(metric)
        accepted = quality is not None and quality["status"] != "unknown"
        return {"asset_id": asset_id, "metric": metric, "value": copy.deepcopy(get_path(asset, metric)),
                "origin": "accepted_observation" if accepted else "synthetic_model",
                "source_id": quality.get("source_id") if accepted else None,
                "source_timestamp": quality.get("source_timestamp") if accepted else None,
                "quality": quality.get("status") if accepted else "unobserved",
                "synthetic": quality.get("synthetic", True) if accepted else True}

    def add(ident, severity, asset_id, title, message, action, fields, origin="canonical_rule"):
        rows = [evidence(ident, field) for ident, field in fields]
        alerts.append({"id": ident, "severity": severity, "asset_id": asset_id, "title": title,
                       "message": message, "recommended_action": action, "origin": origin,
                       "evidence": rows, "synthetic": all(row["synthetic"] for row in rows)})

    for asset_id in ("RIDE_COASTER", "RIDE_WHEEL"):
        if assets[asset_id]["status"] in {"closed", "fault"}:
            add("ride_unavailable" if asset_id == "RIDE_COASTER" else "wheel_unavailable", "critical", asset_id,
                "Coaster unavailable" if asset_id == "RIDE_COASTER" else "Wheel unavailable",
                f"Canonical ride status is {assets[asset_id]['status']}; inspect the source and coordinate maintenance.",
                "dispatch_maintenance", [(asset_id, "status")])
    if assets["POWER_HUB"]["status"] in {"fault", "closed"}:
        add("feeder_fault", "critical", "POWER_HUB", "Power feeder fault",
            "Canonical energy-center status indicates a fault or closure. Capacity forecasts remain synthetic model values.",
            "shed_load", [("POWER_HUB", "status")])
    water = assets["WATER_PLANT"]
    if water["water_lpm"] > 400:
        add("water_leak", "critical" if water["status"] == "fault" else "warning", "WATER_PLANT", "Abnormal water flow",
            "Monitored flow exceeds the illustrative 400 L/min threshold. This rule flags a possible leak, not a confirmed diagnosis.",
            "repair_leak", [("WATER_PLANT", "water_lpm"), ("WATER_PLANT", "status")])
    elif water["status"] in {"fault", "closed"}:
        add("water_plant_fault", "critical", "WATER_PLANT", "Water plant unavailable",
            "Canonical plant status indicates a fault or closure; current flow does not meet the high-flow leak rule.",
            "dispatch_maintenance", [("WATER_PLANT", "status"), ("WATER_PLANT", "water_lpm")])
    food = assets["FOOD_COURT"]
    stock_low = food["erp"]["stock_units"] < food["erp"]["reorder_point"]
    if stock_low:
        add("food_stock", "warning", "FOOD_COURT", "Stock below reorder point",
            "Accepted food inventory is below its configured reorder point.", "replenish_stock",
            [("FOOD_COURT", "erp.stock_units"), ("FOOD_COURT", "erp.reorder_point")])
    if food["queue_minutes"] >= 20 and (stock_low or food["staff"]["on_duty"] < food["staff"]["required"]):
        add("food_demand", "warning", "FOOD_COURT", "Kitchen capacity constrained",
            "Current queue and staffing/inventory fields indicate a service constraint.", "add_staff",
            [("FOOD_COURT", "queue_minutes"), ("FOOD_COURT", "staff.on_duty"),
             ("FOOD_COURT", "staff.required"), ("FOOD_COURT", "erp.stock_units")])
    if assets["WEATHER_STATION"]["temperature_c"] >= 35:
        add("heat", "warning", "FIRST_AID", "Heat response needed",
            "Accepted weather temperature exceeds the illustrative 35°C response threshold.", "add_staff",
            [("WEATHER_STATION", "temperature_c")])
    if any(a["id"] == "crowd_surge" for a in model_alerts) and assets["SHOW_ARENA"]["occupancy"] >= 500:
        add("crowd_surge", "warning", "SHOW_ARENA", "Modeled show departure demand",
            "The synthetic show-departure model predicts a surge while canonical arena occupancy is at least 500. Movement is not observed.",
            "reroute_guests", [("SHOW_ARENA", "occupancy")], origin="synthetic_model")
        alerts[-1]["evidence"].append({"origin": "synthetic_model", "scenario": state["scenario"],
                                      "metric": "show_departure_forecast", "synthetic": True})

    conflicts = []
    for asset_id, model_status in model_statuses.items():
        asset = assets[asset_id]
        quality = asset["data_quality"]["fields"].get("status")
        if not quality or quality["status"] == "unknown" or model_status == asset["status"]:
            continue
        conflict = {"asset_id": asset_id, "metric": "status", "model_value": model_status,
                    "canonical_value": asset["status"], "source_id": quality["source_id"]}
        conflicts.append(conflict)
        add(f"source_conflict_{asset_id}_status", "warning", asset_id, "Source/model status conflict",
            f"Accepted {quality['source_id']} status is {asset['status']}; the synthetic scenario model reports {model_status}.",
            None, [(asset_id, "status")], origin="model_source_conflict")
        alerts[-1]["evidence"].append({"origin": "synthetic_model", "asset_id": asset_id,
                                      "metric": "status", "value": model_status, "synthetic": True})
    state["alerts"] = alerts
    state["model_alerts"] = model_alerts
    state["source_conflicts"] = conflicts
    state["kpis"]["active_alerts"] = len(alerts)
