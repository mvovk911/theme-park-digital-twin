"""Conserved fluid-queue branches, not a calibrated park or safety simulation.

No database, clock, random generator, network client or simulator reference is
accepted here. The input is one frozen canonical observation snapshot.
"""
from __future__ import annotations
import copy
import hashlib
import json
from datetime import datetime
from .contracts import Candidate, PlanningRequest, ScheduledAction

MODEL = {"id": "aster-fluid-planner", "version": "1.0.0", "calibrated": False,
         "method": "five_minute_fluid_queues_and_resource_balances"}
QUEUE_IDS = ("RIDE_COASTER", "RIDE_WHEEL", "FOOD_COURT", "FIRST_AID")
DELAYS = {"reroute_guests": 5, "add_staff": 10, "shed_load": 5,
          "repair_leak": 30, "replenish_stock": 20, "dispatch_maintenance": 0}
TARGETS = {"reroute_guests": list(QUEUE_IDS[:3]), "add_staff": list(QUEUE_IDS),
           "shed_load": ["POWER_HUB"], "repair_leak": ["WATER_PLANT"], "replenish_stock": ["FOOD_COURT"],
           "dispatch_maintenance": ["RIDE_COASTER", "RIDE_WHEEL", "POWER_HUB", "WATER_PLANT", "RESTROOMS"]}
METRICS = {
    "queue_guest_minutes": {"unit": "guest-min", "direction": "lower", "meaning": "Integral of backlog in four modeled service queues; service visits, not unique park guests."},
    "served_guests": {"unit": "service-visits", "direction": "higher", "meaning": "Completed service visits during the horizon."},
    "unserved_guests": {"unit": "service-visits", "direction": "lower", "meaning": "Backlog remaining at horizon; no abandonment or disappearance is assumed."},
    "staff_cost_eur": {"unit": "EUR", "direction": "lower", "meaning": "Incremental illustrative staffing cost at EUR28/person/hour from action request time."},
    "energy_kwh": {"unit": "kWh", "direction": "lower", "meaning": "Integral of modeled aggregate power; no electrical network solution."},
    "feeder_exceedance_minutes": {"unit": "min", "direction": "lower", "meaning": "Time modeled aggregate demand exceeds observed/proposed feeder capacity."},
    "excess_leak_liters": {"unit": "L", "direction": "lower", "meaning": "Incremental scenario leak only; does not add nested flow meters or circulation."},
    "food_stockout_minutes": {"unit": "min", "direction": "lower", "meaning": "Five-minute periods in which food demand remains after stock is exhausted."},
}
ASSUMPTIONS = [
    "Uncalibrated synthetic planning exercise; output is not a real-world forecast, savings claim or safety approval.",
    "Frozen canonical observations initialize each branch; scenario shocks add to existing conditions and never reopen an already closed ride.",
    "Four fluid queues represent service visits, not unique people: coaster, wheel, food and guest care. Initial backlog is posted wait times observed service rate; care uses observed occupancy.",
    "Demand starts at 90% of observed service capacity (closed coaster uses an explicit 840/hour synthetic fallback); equal low/central/high demand factors are used for every branch.",
    "Sensitivity ranges are three assumed demand cases, not probabilities, confidence intervals or calibrated uncertainty.",
    "Each five-minute interval uses arrivals and available capacity; queue guest-minutes use trapezoidal integration, so short transients are approximate.",
    "Guests remain in queue until served. Routing moves the assumed compliance fraction (default 25%) of arrivals from the most backlogged other open attraction/food queue to the explicit target, only when that target has a shorter current modeled wait. It never deletes demand. Guest preference and walking time are not modeled.",
    "Two extra staff increase modeled service capacity by 15% after 10 minutes; qualification and availability are asserted synthetic reserve-pool assumptions, not verified employee records. No donor team is depleted. Real roster transfer and donor minimum coverage are unsupported. Cost starts on assignment at EUR28/person/hour.",
    "Food consumes one stock unit per service visit. A replenishment delivers 300 units after 20 minutes, bounded by observed stock capacity; supply-chain purchasing cost is not modeled.",
    "Load shedding reduces observed hotel load 25%, parking load 65% and food load 8% after 5 minutes, without thermal comfort or charging-service simulation.",
    "Leak repair completes after an assumed 30 minutes; no physical work, repair reliability or water-network hydraulics are simulated. Maintenance dispatch opens only a hypothetical work order and never restores ride availability.",
    "Existing observed mitigations are carried in input measurements. Repeating an action found active in canonical recent-action evidence receives no extra effect and makes that candidate infeasible. A full 12-event history without a reset/scenario boundary causes abstention because earlier active actions may be missing.",
]
UNSUPPORTED = ["ride dynamics or restraint/PLC safety logic", "crowd collision, evacuation certification or accessibility routing", "electrical protection/load flow", "water pressure/quality/hydraulics", "thermal comfort/CFD", "weather prediction", "maintenance failure probability", "revenue, satisfaction or causal ROI", "real command execution"]


def capabilities():
    return {"synthetic": True, "model": MODEL, "mutates_live_state": False,
            "scenarios": ["normal", "ride_closure", "show_surge", "heatwave", "power_fault", "water_leak", "food_rush"],
            "limits": {"horizon_minutes": [15, 120], "step_minutes": 5, "candidates": 6, "actions_per_candidate": 6},
            "actions": [{"action": k, "lead_minutes": v, "physical_effect": False, "allowed_asset_ids": TARGETS[k],
                         "target_semantics": "park flexible-load group" if k == "shed_load" else "routing destination" if k == "reroute_guests" else "asset"}
                        for k, v in DELAYS.items()],
            "metrics": METRICS, "uncertainty": "shared deterministic low/central/high demand sensitivity; not confidence intervals",
            "baselines": ["baseline (do nothing)", "simple_rule (scenario-specific operational rule, when candidates omitted)"],
            "assumptions": ASSUMPTIONS, "unsupported": UNSUPPORTED}


def _action(action, asset):
    return ScheduledAction(action=action, asset_id=asset)


def default_candidates(scenario):
    rules = {
        "normal": [], "ride_closure": [_action("dispatch_maintenance", "RIDE_COASTER")],
        "show_surge": [_action("reroute_guests", "RIDE_WHEEL")],
        "heatwave": [_action("add_staff", "FIRST_AID")],
        "power_fault": [_action("shed_load", "POWER_HUB")],
        "water_leak": [_action("repair_leak", "WATER_PLANT")],
        "food_rush": [_action("replenish_stock", "FOOD_COURT")],
    }
    simple = rules[scenario]
    combined = list(simple)
    if scenario in {"ride_closure", "show_surge"}:
        if not any(a.action == "reroute_guests" for a in combined):
            combined.append(_action("reroute_guests", "RIDE_WHEEL"))
        combined.append(_action("add_staff", "RIDE_WHEEL"))
    elif scenario == "food_rush":
        combined.append(_action("add_staff", "FOOD_COURT"))
    elif scenario == "power_fault":
        combined.append(_action("dispatch_maintenance", "POWER_HUB"))
    elif scenario == "heatwave":
        combined.append(_action("shed_load", "POWER_HUB"))
    elif scenario == "water_leak":
        combined.append(_action("dispatch_maintenance", "WATER_PLANT"))
    else:
        combined.append(_action("add_staff", "FOOD_COURT"))
    return [Candidate(id="simple_rule", label="Simple operating rule", actions=simple),
            Candidate(id="coordinated", label="Coordinated response", actions=combined)]


def _validate_targets(candidate, assets):
    for a in candidate.actions:
        if a.asset_id not in assets:
            raise ValueError(f"Unknown planning asset: {a.asset_id}")
        kind = assets[a.asset_id]["type"]
        valid = {
            "dispatch_maintenance": kind in {"ride", "utility", "facility"},
            "reroute_guests": a.asset_id in {"RIDE_COASTER", "RIDE_WHEEL", "FOOD_COURT"},
            "add_staff": a.asset_id in QUEUE_IDS,
            "shed_load": a.asset_id == "POWER_HUB",
            "repair_leak": a.asset_id == "WATER_PLANT",
            "replenish_stock": a.asset_id == "FOOD_COURT",
        }
        if not valid[a.action]:
            raise ValueError(f"Unsupported planning target for {a.action}: {a.asset_id}")


def _quality(snapshot, as_of=None):
    issues = []
    # The model uses every asset's power and four queues; broad abstention is
    # intentional until a calibrated per-decision dependency graph exists.
    for asset in snapshot["assets"]:
        quality = asset.get("data_quality", {})
        if quality.get("status") != "good":
            issues.append({"asset_id": asset["id"], "quality": quality.get("status", "unknown"),
                           "reason": "Planning input is missing, stale, uncertain or conflicting"})
        elif as_of is not None:
            expired = []
            for metric, field in quality.get("fields", {}).items():
                try:
                    sample_time = datetime.fromisoformat(field["source_timestamp"].replace("Z", "+00:00"))
                    age = (as_of - sample_time).total_seconds()
                    if age > field["stale_after_seconds"] or age < -5:
                        expired.append(metric)
                except (KeyError, TypeError, ValueError):
                    expired.append(metric)
            if expired or not quality.get("fields"):
                issues.append({"asset_id": asset["id"], "quality": "stale" if expired else "unknown",
                               "reason": "Frozen observations no longer satisfy freshness at planning request time",
                               "fields": sorted(expired)})
    if not snapshot.get("accepted_state_revision"):
        issues.append({"reason": "Canonical accepted-state provenance is missing", "quality": "unknown"})
    history = snapshot.get("recent_actions", [])
    if len(history) >= 12 and not any(a.get("action") in {"reset", "scenario"} for a in history):
        issues.append({"reason": "Recent action history is bounded and may omit still-active interventions", "quality": "unknown"})
    return issues


def _active_action_keys(snapshot):
    active = set()
    for event in snapshot.get("recent_actions", []):
        kind = event.get("action")
        if kind in {"reset", "scenario"}:
            break
        active.add((kind, event.get("asset_id") if kind in {"add_staff", "dispatch_maintenance"} else "park"))
    return active


def _run(snapshot, request, candidate, demand_factor):
    assets = {a["id"]: a for a in snapshot["assets"]}
    scenario = request.scenario
    rates = {k: float(assets[k]["throughput_per_hour"]) / 60 for k in QUEUE_IDS}
    queues = {k: max(0., float(assets[k]["queue_minutes"]) * rates[k]) for k in QUEUE_IDS}
    queues["FIRST_AID"] = float(assets["FIRST_AID"]["occupancy"])
    initial = sum(queues.values())
    closed = {k for k in QUEUE_IDS if assets[k]["status"] in {"closed", "fault"}}
    if scenario in {"ride_closure", "power_fault"}:
        closed.add("RIDE_COASTER")
    if "RIDE_COASTER" in closed:
        queues["RIDE_WHEEL"] += queues["RIDE_COASTER"] * .6
        queues["FOOD_COURT"] += queues["RIDE_COASTER"] * .4
        queues["RIDE_COASTER"] = 0.
    arrivals_rate = {k: (.9 * rates[k]) for k in QUEUE_IDS}
    if "RIDE_COASTER" in closed and rates["RIDE_COASTER"] == 0:
        arrivals_rate["RIDE_COASTER"] = .9 * 840 / 60
    stock = float(assets["FOOD_COURT"]["erp"]["stock_units"])
    if scenario == "food_rush":
        stock = min(stock, 60.)
    stock_capacity = float(assets["FOOD_COURT"]["erp"]["stock_capacity"])
    power = sum(float(a["power_kw"]) for a in assets.values())
    if scenario in {"ride_closure", "power_fault"} and assets["RIDE_COASTER"]["status"] not in {"closed", "fault"}:
        power += 18 - float(assets["RIDE_COASTER"]["power_kw"])
    if scenario == "heatwave" and float(assets["FIRST_AID"]["temperature_c"]) < 35:
        power += .3 * sum(float(assets[k]["power_kw"]) for k in ("HOTEL", "FOOD_COURT", "FIRST_AID"))
    capacity = float(assets["POWER_HUB"]["capacity"])
    if scenario == "power_fault":
        capacity = min(capacity, 540.)
    observed_leak = max(0., float(assets["WATER_PLANT"]["water_lpm"]) - 180.) if assets["WATER_PLANT"]["status"] == "fault" else 0.
    leak = max(380., observed_leak) if scenario == "water_leak" else observed_leak
    existing_actions = _active_action_keys(snapshot)
    schedule = [{**a.model_dump(), "effective_at_minute": a.at_minute + DELAYS[a.action],
                 "already_active": (a.action, a.asset_id if a.action in {"add_staff", "dispatch_maintenance"} else "park") in existing_actions}
                for a in candidate.actions]
    assigned = sum(2 for a in schedule if a["action"] == "add_staff" and not a["already_active"])
    violations = []
    for a in schedule:
        if a["already_active"]:
            violations.append({"code": "already_active_action", "action": a["action"], "asset_id": a["asset_id"],
                               "reason": "Canonical action evidence already includes this intervention; no repeated benefit or cost is modeled."})
        if a["action"] == "reroute_guests" and a["asset_id"] in closed:
            violations.append({"code": "routing_target_unavailable", "asset_id": a["asset_id"]})
    if assigned > request.assumptions.available_qualified_staff:
        violations.append({"code": "staff_budget_exceeded", "requested": assigned,
                           "available": request.assumptions.available_qualified_staff})
    hot_assets = [{"asset_id": k, "temperature_c": float(assets[k]["temperature_c"])}
                  for k in ("HOTEL", "FOOD_COURT", "FIRST_AID")
                  if float(assets[k]["temperature_c"]) >= 35]
    if (scenario == "heatwave" or hot_assets) and any(a.action == "shed_load" for a in candidate.actions):
        violations.append({"code": "heatwave_cooling_conflict", "reason": "The modeled shedding includes HVAC under observed or proposed hot conditions; comfort/heat safety is not modeled.",
                           "observed_hot_assets": hot_assets, "assumed_threshold_c": 35,
                           "proposed_heatwave": scenario == "heatwave"})
    summary = {k: 0. for k in METRICS}
    total_arrivals = 0.
    replenished = False
    trajectory = [{"minute": 0, "queue_guests": {k: round(v, 3) for k, v in queues.items()},
                   "food_stock_units": stock, "power_kw": round(power, 3), "feeder_capacity_kw": capacity,
                   "excess_leak_lpm": round(leak, 3), "cumulative_served_guests": 0.}]
    for minute in range(0, request.horizon_minutes, 5):
        effective = [a for a in schedule if a["effective_at_minute"] <= minute and not a["already_active"]]
        active = {a["action"] for a in effective}
        staffed = {a["asset_id"] for a in effective if a["action"] == "add_staff"}
        before = sum(queues.values())
        incoming = {k: v * 5 * demand_factor * request.assumptions.arrival_multiplier for k, v in arrivals_rate.items()}
        if scenario == "show_surge" and minute < 20:
            incoming["RIDE_COASTER"] += 560 * .4 / 4 * demand_factor
            incoming["RIDE_WHEEL"] += 560 * .3 / 4 * demand_factor
            incoming["FOOD_COURT"] += 560 * .3 / 4 * demand_factor
        if scenario == "food_rush":
            incoming["FOOD_COURT"] *= 1.5 if minute < 45 else 1.1
        if scenario == "heatwave":
            incoming["FIRST_AID"] *= 2.5
        if "RIDE_COASTER" in closed:
            displaced = incoming["RIDE_COASTER"]
            incoming["RIDE_COASTER"] = 0.
            incoming["RIDE_WHEEL"] += displaced * .6
            incoming["FOOD_COURT"] += displaced * .4
        if "reroute_guests" in active:
            open_queues = [k for k in QUEUE_IDS[:3] if k not in closed and rates[k] > 0]
            target = next(a["asset_id"] for a in effective if a["action"] == "reroute_guests")
            others = [k for k in open_queues if k != target]
            source = max(others, key=lambda k: queues[k] / rates[k]) if others else None
            if target in open_queues and source and queues[source] / rates[source] > queues[target] / rates[target]:
                moved = incoming[source] * request.assumptions.routing_compliance_pct / 100
                incoming[source] -= moved
                incoming[target] += moved
        total_arrivals += sum(incoming.values())
        if "replenish_stock" in active and not replenished:
            stock = min(stock_capacity, stock + 300)
            replenished = True
        for k in QUEUE_IDS:
            queues[k] += incoming[k]
            capacity_step = 0. if k in closed else rates[k] * 5 * (1.15 if k in staffed else 1)
            served = min(queues[k], capacity_step, stock if k == "FOOD_COURT" else float("inf"))
            queues[k] -= served
            summary["served_guests"] += served
            if k == "FOOD_COURT":
                stock -= served
        summary["queue_guest_minutes"] += (before + sum(queues.values())) / 2 * 5
        summary["food_stockout_minutes"] += 5 if stock <= 1e-9 and queues["FOOD_COURT"] > 1e-9 else 0
        step_power = power
        if "shed_load" in active:
            step_power -= sum(float(assets[k]["power_kw"]) * factor for k, factor in (("HOTEL", .25), ("PARKING", .65), ("FOOD_COURT", .08)))
        step_power = max(0., step_power)
        summary["energy_kwh"] += step_power * 5 / 60
        summary["feeder_exceedance_minutes"] += 5 if step_power > capacity else 0
        step_leak = 0. if "repair_leak" in active else leak
        summary["excess_leak_liters"] += step_leak * 5
        summary["staff_cost_eur"] += sum(2 * 28 * 5 / 60 for a in schedule if a["action"] == "add_staff" and a["at_minute"] <= minute and not a["already_active"])
        trajectory.append({"minute": minute + 5, "queue_guests": {k: round(v, 3) for k, v in queues.items()},
                           "food_stock_units": round(stock, 3), "power_kw": round(step_power, 3),
                           "feeder_capacity_kw": capacity, "excess_leak_lpm": round(step_leak, 3),
                           "cumulative_served_guests": round(summary["served_guests"], 3)})
    summary["unserved_guests"] = sum(queues.values())
    if trajectory[-1]["power_kw"] > capacity:
        violations.append({"code": "residual_feeder_exceedance", "reason": "Modeled demand still exceeds feeder capacity at the end of the horizon."})
    conservation_error = initial + total_arrivals - summary["served_guests"] - summary["unserved_guests"]
    return {"summary": {k: round(v, 3) for k, v in summary.items()}, "trajectory": trajectory,
            "conservation": {"initial_queue_guests": round(initial, 6), "arrivals": round(total_arrivals, 6),
                             "residual_guests": round(conservation_error, 8)},
            "action_schedule": schedule, "constraints": {"feasible": not violations, "violations": violations,
            "qualified_staff_requested": assigned, "qualified_staff_available": request.assumptions.available_qualified_staff}}


def simulate(snapshot, request: PlanningRequest, *, as_of=None):
    """Return comparable independent branches without changing snapshot or live state."""
    snapshot = copy.deepcopy(snapshot)
    json.dumps(snapshot, allow_nan=False)  # Nonfinite input is never a forecast.
    assets = {a["id"]: a for a in snapshot["assets"]}
    required = set(QUEUE_IDS) | {"POWER_HUB", "WATER_PLANT", "HOTEL", "PARKING"}
    if not required <= assets.keys():
        raise ValueError("Planning snapshot is missing required canonical assets")
    candidates = [Candidate(id="baseline", label="Do nothing", actions=[])]
    candidates += default_candidates(request.scenario) if request.candidates is None else request.candidates
    spread = request.assumptions.demand_uncertainty_pct / 100
    factors = {"low": 1 - spread, "central": 1., "high": 1 + spread}
    branches = []
    for candidate in candidates:
        _validate_targets(candidate, assets)
        runs = {name: _run(snapshot, request, candidate, factor) for name, factor in factors.items()}
        central = runs["central"]
        branches.append({"id": candidate.id, "label": candidate.label, **central,
                         "sensitivity": {name: {"demand_factor": factors[name], "summary": run["summary"], "conservation": run["conservation"]} for name, run in runs.items()},
                         "ranges": {metric: {"min": min(r["summary"][metric] for r in runs.values()), "max": max(r["summary"][metric] for r in runs.values())} for metric in METRICS},
                         "tradeoffs": []})
    baseline = branches[0]["summary"]
    for branch in branches:
        branch["deltas_vs_baseline"] = {key: round(value - baseline[key], 3) for key, value in branch["summary"].items()}
        adverse_cases = []
        for name, case in branch["sensitivity"].items():
            case_baseline = branches[0]["sensitivity"][name]["summary"]
            case["deltas_vs_baseline"] = {metric: round(value - case_baseline[metric], 3) for metric, value in case["summary"].items()}
            # Labor is an explicit cost tradeoff, not a hidden adverse service
            # effect. Other outcome deterioration remains visible case by case.
            worse = [metric for metric, delta in case["deltas_vs_baseline"].items()
                     if metric != "staff_cost_eur" and (delta > 0 if METRICS[metric]["direction"] == "lower" else delta < 0)]
            if worse:
                adverse_cases.append({"case": name, "metrics": worse})
        branch["robustness"] = {"status": "adverse_sensitivity_case" if adverse_cases else "no_adverse_case_in_tested_set",
                                "worse_than_baseline_cases": adverse_cases,
                                "scope": "Paired low/central/high comparisons; excludes explicit labor-cost tradeoff, not a guarantee outside tested cases."}
        if branch["summary"]["staff_cost_eur"]:
            branch["tradeoffs"].append("Uses scarce qualified staff and incurs incremental labor cost.")
        if any(a["action"] == "shed_load" for a in branch["action_schedule"]):
            branch["tradeoffs"].append("Reduced HVAC/EV service is not quantified; energy reduction alone does not establish net value.")
        if any(a["action"] == "replenish_stock" for a in branch["action_schedule"]):
            branch["tradeoffs"].append("Consumes 300 stock units from an assumed available supply; procurement cost and waste are not modeled.")
        if any(a["action"] == "dispatch_maintenance" for a in branch["action_schedule"]):
            branch["tradeoffs"].append("Dispatch creates a hypothetical work order only; no modeled restoration benefit.")
    issues = _quality(snapshot, as_of)
    # Pareto screening across all displayed metrics avoids hiding cost behind a
    # made-up weighted score. A dominated no-op/dispatch tie is not an improvement.
    def dominates(left, right):
        comparisons = [(left[m] <= right[m] if spec["direction"] == "lower" else left[m] >= right[m]) for m, spec in METRICS.items()]
        return all(comparisons) and any(left[m] != right[m] for m in METRICS)
    feasible = [b for b in branches if b["constraints"]["feasible"]]
    shortlist = [] if issues else [b["id"] for b in feasible if b["id"] != "baseline"
                    and b["summary"] != baseline
                    and not any(dominates(other["summary"], b["summary"])
                                or (other["summary"] == b["summary"] and len(other["action_schedule"]) < len(b["action_schedule"]))
                                for other in feasible if other is not b)]
    baseline_nondominated = branches[0]["constraints"]["feasible"] and not any(dominates(b["summary"], baseline) for b in feasible)
    outcome = "insufficient_data" if issues else "tradeoffs_require_review" if shortlist else "no_intervention_benefit" if baseline_nondominated else "no_feasible_response"
    identity = {"snapshot_revision": snapshot.get("accepted_state_revision"), "request": request.model_dump(), "model": MODEL, "quality_issues": issues}
    return {"synthetic": True, "mutates_live_state": False, "physical_effect": False, "model": MODEL,
            "plan_id": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
            "input": {"state_revision": snapshot.get("accepted_state_revision"), "tick": snapshot["tick"],
                      "timestamp": snapshot["timestamp"], "source": "frozen_canonical_observations",
                      "current_scenario": snapshot["scenario"], "requested_scenario": request.scenario,
                      "quality_check": "request_time" if as_of is not None else "snapshot_capture",
                      "read_model": snapshot.get("read_model"), "quality_issues": issues},
            "horizon_minutes": request.horizon_minutes, "step_minutes": 5, "branches": branches,
            "decision": {"status": "insufficient_data" if issues else "review_required", "shortlist": shortlist,
                         "outcome": outcome, "preferred_policy": "baseline" if outcome == "no_intervention_benefit" else None,
                         "baseline_is_nondominated": baseline_nondominated if not issues else None,
                         "auto_execute": False, "rationale": ["Shortlist screens central-case feasible nondominated interventions; equal outcomes prefer fewer actions. Paired sensitivity flags can still show worse outcomes than do nothing.",
                         "Do nothing is the explicit preferred policy when no candidate demonstrates an undominated modeled benefit; this is not authority for real action or inaction.",
                         "Do-nothing and simple-rule baselines remain visible. Review uncertainty, omitted costs and operational constraints before any separate synthetic action."]},
            "parameters": request.assumptions.model_dump(), "metric_definitions": METRICS,
            "assumptions": ASSUMPTIONS, "unsupported": UNSUPPORTED}
