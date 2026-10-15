"""Synthetic park definitions, independent of storage and application services."""
from __future__ import annotations

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
    ("ride_scada", "Simulated Ride SCADA", "Synthetic HTTP · planned OPC UA", ["RIDE_COASTER", "RIDE_WHEEL"]),
    ("ticketing", "Simulated Ticketing & Reservations", "Synthetic HTTP · planned REST", ["ENTRY_GATE", "RIDE_COASTER", "RIDE_WHEEL", "SHOW_ARENA"]),
    ("vision", "Simulated People Counters", "Synthetic HTTP · planned MQTT", ["ENTRY_GATE", "SHOW_ARENA", "FOOD_COURT", "PARKING"]),
    ("cmms", "Simulated Maintenance CMMS", "Synthetic HTTP · planned vendor REST", ["RIDE_COASTER", "RIDE_WHEEL", "POWER_HUB", "WATER_PLANT"]),
    ("erp", "Simulated ERP & POS", "Synthetic HTTP · planned vendor REST", ["FOOD_COURT", "HOTEL"]),
    ("workforce", "Simulated Workforce", "Synthetic HTTP · planned REST", ["ENTRY_GATE", "FOOD_COURT", "RIDE_COASTER", "FIRST_AID"]),
    ("bms", "Simulated Building & Energy", "Synthetic HTTP · planned BACnet", ["POWER_HUB", "HOTEL", "FOOD_COURT", "PARKING"]),
    ("water", "Simulated Water Management", "Synthetic HTTP · planned MQTT", ["WATER_PLANT", "RESTROOMS"]),
    ("weather", "Simulated Local Weather", "Synthetic HTTP · planned REST", ["WEATHER_STATION"]),
    ("gis", "Park Asset Registry / OpenUSD", "Synthetic HTTP · OpenUSD paths", [a["id"] for a in registry()]),
]

