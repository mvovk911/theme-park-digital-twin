"""Pure, uncalibrated scenario rules shared by the gateway and demo producers.

All inputs (including time and work-order counts) are explicit. No I/O, wall
clock, randomness or application state is accessed, and inputs remain unchanged.
"""
from __future__ import annotations
import copy
import math
from .domain import ACTIONS, SCENARIOS, SYSTEM_DEFS


def evaluate(base, scenario, mitigations, tick, now, work_order_counts, recent_actions):
    """Evaluate demo rules without changing simulator state or touching storage."""
    assets = copy.deepcopy(base)
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
                "asset_ids": list(ids), "synthetic": True} for ident, name, protocol, ids in SYSTEM_DEFS]
    queue_assets = [a for a in assets.values() if a["queue_minutes"] > 0]
    return {"synthetic": True, "timestamp": now, "tick": tick, "scenario": scenario,
                  "assets": list(assets.values()), "weather": {"temperature_c": round(temp, 1), "wind_kph": round(9 + wave * 2, 1), "condition": "heat advisory" if scenario == "heatwave" else "partly cloudy"},
                  "systems": systems, "alerts": alerts, "scenarios": copy.deepcopy(SCENARIOS), "actions": copy.deepcopy(ACTIONS),
                  "recent_actions": copy.deepcopy(recent_actions),
                  "kpis": {"attendance": 3420 + round(wave * 35), "total_capacity": 6200,
                           "average_wait_minutes": round(sum(a["queue_minutes"] for a in queue_assets) / max(1, len(queue_assets)), 1),
                           "queue_asset_count": len(queue_assets),
                           "excluded_closed_count": sum(a["status"] == "closed" for a in assets.values()),
                           "power_kw": round(sum(a["power_kw"] for a in assets.values()), 1),
                           "power_capacity_kw": assets["POWER_HUB"]["capacity"],
                           "water_lpm": round(sum(a["water_lpm"] for a in assets.values()), 1),
                           "open_rides": sum(a["type"] == "ride" and a["status"] != "closed" for a in assets.values()),
                           "active_alerts": len(alerts),
                           "estimated_operating_cost_eur_per_hour": round(sum(a["erp"]["operating_cost_eur_per_hour"] for a in assets.values()), 2)}}

