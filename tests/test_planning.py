"""Decision-quality invariants, conservation, negative controls and HTTP isolation."""
import copy
import json
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.connectors import ConnectorRuntime, ParkReadModel
from backend.planning import PlanningRequest, simulate
from backend.planning.api import install_planning_routes
from backend.simulator import ParkSimulator


@pytest.fixture
def state():
    park = ParkSimulator(":memory:")
    yield ParkReadModel(park, ConnectorRuntime(park.base)).snapshot()
    park.close()


def plan(state, scenario="food_rush", **kwargs):
    return simulate(state, PlanningRequest(scenario=scenario, **kwargs))


def action(action, asset_id, at_minute=0):
    return {"action": action, "asset_id": asset_id, "at_minute": at_minute}


def candidate(*actions):
    return [{"id": "candidate", "label": "Test candidate", "actions": list(actions)}]


@pytest.mark.parametrize("scenario", ["normal", "ride_closure", "show_surge", "heatwave", "power_fault", "water_leak", "food_rush"])
def test_deterministic_branches_conserve_service_visits_and_leave_inputs_unchanged(state, scenario):
    before = copy.deepcopy(state)
    result = plan(state, scenario)
    assert result == plan(state, scenario)
    assert state == before
    assert result["mutates_live_state"] is False
    assert result["physical_effect"] is False
    assert result["model"]["calibrated"] is False
    assert [b["id"] for b in result["branches"]] == ["baseline", "simple_rule", "coordinated"]
    for branch in result["branches"]:
        assert abs(branch["conservation"]["residual_guests"]) < 1e-6
        assert all(v >= 0 for v in branch["summary"].values())
        for name, run in branch["sensitivity"].items():
            assert abs(run["conservation"]["residual_guests"]) < 1e-6
            assert run["demand_factor"] == result["branches"][0]["sensitivity"][name]["demand_factor"]
        assert len(branch["trajectory"]) == 13


def test_identical_actual_state_has_identical_results_despite_scenario_label(state):
    left = plan(state, "heatwave")
    state["scenario"] = "heatwave"
    right = plan(state, "heatwave")
    assert left["branches"] == right["branches"]


def test_noop_candidate_matches_baseline_in_all_demand_cases(state):
    result = plan(state, candidates=candidate())
    baseline, noop = result["branches"]
    assert baseline["summary"] == noop["summary"]
    assert baseline["sensitivity"] == noop["sensitivity"]
    assert result["decision"]["shortlist"] == []


def test_routing_conserves_demand_and_zero_compliance_is_noop(state):
    result = plan(state, "ride_closure", candidates=candidate(action("reroute_guests", "RIDE_WHEEL")), assumptions={"routing_compliance_pct": 0})
    assert result["branches"][0]["summary"] == result["branches"][1]["summary"]
    active = plan(state, "ride_closure", candidates=candidate(action("reroute_guests", "RIDE_WHEEL")))
    assert active["branches"][0]["conservation"]["arrivals"] == active["branches"][1]["conservation"]["arrivals"]


def test_staff_cost_occurs_before_benefit_and_zero_pool_blocks_shortlist(state):
    result = plan(state, "food_rush", candidates=candidate(action("add_staff", "FOOD_COURT", 10)), horizon_minutes=15)
    baseline, staff = result["branches"]
    assert staff["summary"]["served_guests"] == baseline["summary"]["served_guests"]
    assert staff["summary"]["staff_cost_eur"] > 0
    assert result["decision"]["shortlist"] == []
    assert result["decision"]["outcome"] == "no_intervention_benefit"
    assert result["decision"]["preferred_policy"] == "baseline"
    no_staff = plan(state, assumptions={"available_qualified_staff": 0})
    branch = next(b for b in no_staff["branches"] if b["id"] == "coordinated")
    assert not branch["constraints"]["feasible"]
    assert "coordinated" not in no_staff["decision"]["shortlist"]


def test_heatwave_does_not_shortlist_hvac_shedding(state):
    result = plan(state, "heatwave")
    assert "coordinated" not in result["decision"]["shortlist"]
    assert result["branches"][2]["constraints"]["violations"][0]["code"] == "heatwave_cooling_conflict"


@pytest.mark.parametrize("scenario", ["normal", "power_fault"])
def test_observed_heat_blocks_shedding_independent_of_requested_scenario(state, scenario):
    for asset in state["assets"]:
        if asset["id"] in {"HOTEL", "FOOD_COURT", "FIRST_AID"}:
            asset["temperature_c"] = 38
    result = plan(state, scenario, candidates=candidate(action("shed_load", "POWER_HUB")))
    branch = result["branches"][1]
    assert not branch["constraints"]["feasible"]
    assert "candidate" not in result["decision"]["shortlist"]
    violation = next(v for v in branch["constraints"]["violations"] if v["code"] == "heatwave_cooling_conflict")
    assert len(violation["observed_hot_assets"]) == 3
    assert violation["proposed_heatwave"] is False


@pytest.mark.parametrize("quality", ["unknown", "stale", "uncertain"])
def test_bad_observation_abstains_without_hiding_diagnostic_branches(state, quality):
    state["assets"][0]["data_quality"]["status"] = quality
    result = plan(state)
    assert result["decision"]["status"] == "insufficient_data"
    assert result["decision"]["shortlist"] == []
    assert result["input"]["quality_issues"]


def test_canonical_connector_measurement_changes_plan(state):
    original = plan(state)
    food = next(a for a in state["assets"] if a["id"] == "FOOD_COURT")
    food["throughput_per_hour"] = 100
    food["queue_minutes"] = 50
    changed = plan(state)
    assert original["branches"][0]["summary"] != changed["branches"][0]["summary"]


def test_dispatch_does_not_restore_closed_ride_and_repair_honors_lead_time(state):
    result = plan(state, "ride_closure", candidates=candidate(action("dispatch_maintenance", "RIDE_COASTER")))
    assert result["branches"][0]["summary"] == result["branches"][1]["summary"]
    result = plan(state, "water_leak")
    assert result["branches"][0]["summary"]["excess_leak_liters"] == 380 * 60
    assert result["branches"][1]["summary"]["excess_leak_liters"] == 380 * 30


@pytest.mark.parametrize("payload", [
    {"scenario": "food_rush", "horizon_minutes": 121},
    {"scenario": "food_rush", "horizon_minutes": 16},
    {"scenario": "food_rush", "assumptions": {"arrival_multiplier": float("nan")}},
    {"scenario": "food_rush", "candidates": [{"id": "baseline", "label": "bad"}]},
    {"scenario": "food_rush", "candidates": candidate(action("add_staff", "FOOD_COURT", 60))},
])
def test_invalid_request_rejected(payload):
    with pytest.raises(ValueError):
        PlanningRequest.model_validate(payload)


def test_http_readonly_frozen_revision_and_unavailable_revision(tmp_path):
    app = create_app(str(tmp_path / "park.db"), run_background=False)
    if not any(r.path == "/api/planning/simulate" for r in app.routes):
        install_planning_routes(app)
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        audit = client.get("/api/audit").json()
        simulator_before = app.state.park.snapshot()
        before = app.state.park.db.total_changes
        result = client.post("/api/planning/simulate", json={"scenario": "food_rush", "expected_state_revision": state["accepted_state_revision"]})
        assert result.status_code == 200
        assert result.json()["input"]["state_revision"] == state["accepted_state_revision"]
        assert app.state.park.db.total_changes == before
        assert client.get("/api/audit").json() == audit
        after = client.get("/api/state").json()
        assert after["accepted_state_revision"] == state["accepted_state_revision"]
        assert app.state.park.snapshot() == simulator_before
        assert after["tick"] == state["tick"]
        assert client.post("/api/planning/simulate", json={"scenario": "normal", "expected_state_revision": "f" * 64}).status_code == 409
        assert client.post("/api/planning/simulate", json={"scenario": "normal", "candidates": candidate(action("repair_leak", "HOTEL"))}).status_code == 422


def test_output_is_finite_json(state):
    json.dumps(plan(state), allow_nan=False)


def test_retained_good_snapshot_abstains_when_it_ages_out(state):
    later = datetime.fromisoformat(state["timestamp"]) + timedelta(seconds=30)
    result = simulate(state, PlanningRequest(scenario="food_rush"), as_of=later)
    assert result["decision"]["status"] == "insufficient_data"
    assert result["decision"]["shortlist"] == []
    assert result["input"]["quality_check"] == "request_time"


def test_unresolved_feeder_overload_is_infeasible_and_equal_outcomes_prefer_fewer_actions(state):
    next(a for a in state["assets"] if a["id"] == "HOTEL")["power_kw"] += 100
    result = plan(state, "power_fault")
    assert result["branches"][0]["constraints"]["feasible"] is False
    assert result["branches"][1]["constraints"]["feasible"] is True
    assert result["decision"]["shortlist"] == ["simple_rule"]
    result = plan(state, "water_leak")
    assert result["decision"]["shortlist"] == ["simple_rule"]


def test_extra_staff_have_no_service_value_without_a_bottleneck(state):
    for asset in state["assets"]:
        asset["queue_minutes"] = 0
        if asset["id"] == "FIRST_AID":
            asset["occupancy"] = 0
    result = plan(state, "normal", assumptions={"arrival_multiplier": .25},
                  candidates=candidate(action("add_staff", "FOOD_COURT")))
    baseline, staffed = result["branches"]
    assert baseline["summary"]["served_guests"] == staffed["summary"]["served_guests"]
    assert baseline["summary"]["queue_guest_minutes"] == staffed["summary"]["queue_guest_minutes"] == 0
    assert staffed["summary"]["staff_cost_eur"] > 0
    assert result["decision"]["shortlist"] == []


def test_shedding_is_park_scope_and_routing_uses_actual_target(state):
    with pytest.raises(ValueError, match="Unsupported planning target"):
        plan(state, candidates=candidate(action("shed_load", "HOTEL")))
    result = plan(state, "ride_closure", candidates=candidate(action("reroute_guests", "RIDE_COASTER")))
    assert not result["branches"][1]["constraints"]["feasible"]
    assert result["branches"][0]["summary"] == result["branches"][1]["summary"]
    to_food = plan(state, "normal", candidates=candidate(action("reroute_guests", "FOOD_COURT")))
    to_wheel = plan(state, "normal", candidates=candidate(action("reroute_guests", "RIDE_WHEEL")))
    assert to_food["branches"][1]["trajectory"] != to_wheel["branches"][1]["trajectory"]


def test_already_active_staff_does_not_get_repeated_benefit_or_cost(state):
    state["recent_actions"] = [{"action": "add_staff", "asset_id": "FOOD_COURT"}, {"action": "scenario"}]
    result = plan(state, candidates=candidate(action("add_staff", "FOOD_COURT")))
    baseline, repeat = result["branches"]
    assert repeat["summary"] == baseline["summary"]
    assert repeat["action_schedule"][0]["already_active"] is True
    assert not repeat["constraints"]["feasible"]
    assert result["decision"]["shortlist"] == []
    state["recent_actions"].insert(0, {"action": "reset"})
    reset = plan(state, candidates=candidate(action("add_staff", "FOOD_COURT")))
    assert reset["branches"][1]["constraints"]["feasible"]


def test_truncated_intervention_history_abstains(state):
    state["recent_actions"] = [{"action": "dispatch_maintenance", "asset_id": "RIDE_COASTER"}] * 12
    result = plan(state)
    assert result["decision"]["status"] == "insufficient_data"
    assert result["decision"]["shortlist"] == []


def test_sensitivity_reversal_is_visible_as_paired_adverse_case(state):
    next(a for a in state["assets"] if a["id"] == "RIDE_COASTER")["queue_minutes"] = 10
    result = plan(state, "normal", candidates=candidate(action("reroute_guests", "RIDE_COASTER")),
                  assumptions={"arrival_multiplier": .25, "demand_uncertainty_pct": 50, "routing_compliance_pct": 100})
    branch = result["branches"][1]
    assert branch["sensitivity"]["central"]["deltas_vs_baseline"]["queue_guest_minutes"] < 0
    assert branch["sensitivity"]["high"]["deltas_vs_baseline"]["queue_guest_minutes"] > 0
    assert branch["robustness"]["status"] == "adverse_sensitivity_case"
    assert {"case": "high", "metrics": ["queue_guest_minutes"]} in branch["robustness"]["worse_than_baseline_cases"]
