"""Integration checks for synthetic scenario, mitigation, lookup and persistence."""
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "park.db"), run_background=False)) as client:
        yield client


def by_id(state, asset_id):
    return next(a for a in state["assets"] if a["id"] == asset_id)


def test_asset_registry_identifies_scene_objects(client):
    state = client.get("/api/state").json()
    assert state["synthetic"]
    assert len(state["assets"]) == 12
    assert len({a["id"] for a in state["assets"]}) == 12
    for asset in state["assets"]:
        assert asset["scene_path"] == f"/World/Park/{asset['id']}"
        assert asset["synthetic"]
        assert "Synthetic" in asset["metadata"]["source"]
        assert set(asset["dependencies"]) <= {a["id"] for a in state["assets"]}
    detail = client.get("/api/assets/RIDE_COASTER").json()
    assert detail["history"]
    assert detail["staff"]["qualifications"] == ["ride_operator_coaster"]
    assert client.get("/api/assets/unknown").status_code == 404
    assert client.get("/api/assets/unknown/history").status_code == 404


def test_closure_routing_and_maintenance(client):
    normal = client.get("/api/state").json()
    closed = client.post("/api/scenarios", json={"scenario": "ride_closure"}).json()
    assert closed["kpis"]["open_rides"] == 1
    assert by_id(closed, "RIDE_COASTER")["status"] == "closed"
    assert by_id(closed, "RIDE_WHEEL")["queue_minutes"] > by_id(normal, "RIDE_WHEEL")["queue_minutes"]
    diverted = client.post("/api/actions", json={"action": "reroute_guests"}).json()["state"]
    assert by_id(diverted, "RIDE_WHEEL")["queue_minutes"] < by_id(closed, "RIDE_WHEEL")["queue_minutes"]
    for _ in range(2):
        assert client.post("/api/actions", json={"action": "dispatch_maintenance", "asset_id": "RIDE_COASTER"}).status_code == 200
    detail = client.get("/api/assets/RIDE_COASTER").json()
    assert len(detail["work_orders"]) == 1
    assert detail["maintenance"]["open_work_orders"] == 1
    assert detail["status"] == "closed"  # A work order is not a repair.


def test_water_leak_repair_resolves_fault_and_reduces_flow(client):
    leaking = client.post("/api/scenarios", json={"scenario": "water_leak"}).json()
    assert any(a["id"] == "water_leak" for a in leaking["alerts"])
    repaired = client.post("/api/actions", json={"action": "repair_leak", "asset_id": "WATER_PLANT"}).json()["state"]
    assert by_id(repaired, "WATER_PLANT")["water_lpm"] < by_id(leaking, "WATER_PLANT")["water_lpm"] * .5
    assert by_id(repaired, "WATER_PLANT")["status"] == "operational"
    assert not any(a["id"] == "water_leak" for a in repaired["alerts"])


def test_food_inventory_staffing_and_cost(client):
    rush = client.post("/api/scenarios", json={"scenario": "food_rush"}).json()
    initial = by_id(rush, "FOOD_COURT")
    assert initial["erp"]["stock_units"] < initial["erp"]["reorder_point"]
    staffed = client.post("/api/actions", json={"action": "add_staff", "asset_id": "FOOD_COURT"}).json()["state"]
    assert by_id(staffed, "FOOD_COURT")["queue_minutes"] < initial["queue_minutes"]
    assert staffed["kpis"]["estimated_operating_cost_eur_per_hour"] > rush["kpis"]["estimated_operating_cost_eur_per_hour"]
    replenished = client.post("/api/actions", json={"action": "replenish_stock"}).json()["state"]
    final = by_id(replenished, "FOOD_COURT")
    assert final["erp"]["stock_units"] == 600
    assert final["staff"]["on_duty"] == final["staff"]["required"]
    assert final["status"] == "operational"
    assert not replenished["alerts"]


def test_power_shedding_reduces_load_without_reopening_ride(client):
    fault = client.post("/api/scenarios", json={"scenario": "power_fault"}).json()
    shed = client.post("/api/actions", json={"action": "shed_load"}).json()["state"]
    assert shed["kpis"]["power_kw"] < fault["kpis"]["power_kw"] - 40
    assert by_id(shed, "RIDE_COASTER")["status"] == "closed"
    assert by_id(shed, "POWER_HUB")["status"] == "fault"


def test_validates_commands_and_history_limits(client):
    assert client.post("/api/scenarios", json={"scenario": "bogus"}).status_code == 422
    assert client.post("/api/actions", json={"action": "bogus"}).status_code == 422
    assert client.post("/api/actions", json={"action": "repair_leak", "asset_id": "HOTEL"}).status_code == 422
    assert client.post("/api/actions", json={"action": "add_staff", "asset_id": "missing"}).status_code == 404
    assert client.get("/api/assets/RIDE_COASTER/history?limit=0").status_code == 422
    assert client.get("/api/assets/RIDE_COASTER/history?limit=4000").status_code == 422
    client.post("/api/scenarios", json={"scenario": "heatwave"})
    history = client.get("/api/assets/WEATHER_STATION/history?limit=2").json()["history"]
    assert len(history) == 2
    assert history[-1]["temperature_c"] > history[0]["temperature_c"] + 10
    assert history[0]["tick"] < history[-1]["tick"]


def test_persistence_and_reset_preserve_audit(tmp_path):
    path = str(tmp_path / "persistent.db")
    with TestClient(create_app(path, run_background=False)) as c:
        c.post("/api/scenarios", json={"scenario": "water_leak"})
        c.post("/api/actions", json={"action": "dispatch_maintenance", "asset_id": "WATER_PLANT"})
        c.post("/api/actions", json={"action": "repair_leak"})
        tick = c.get("/api/state").json()["tick"]
    with TestClient(create_app(path, run_background=False)) as c:
        state = c.get("/api/state").json()
        assert state["scenario"] == "water_leak"
        assert state["tick"] > tick
        assert by_id(state, "WATER_PLANT")["status"] == "operational"
        assert c.get("/api/assets/WATER_PLANT").json()["work_orders"][0]["status"] == "completed"
        reset = c.post("/api/actions", json={"action": "reset"}).json()["state"]
        assert reset["scenario"] == "normal"
        assert len(c.get("/api/audit").json()["events"]) == 4


def test_websocket_matches_http_snapshot(client):
    with client.websocket_connect("/ws/state") as websocket:
        state = websocket.receive_json()
        assert state["tick"] == client.get("/api/state").json()["tick"]
        assert state["synthetic"]


def test_history_prunes_old_samples(client):
    sim = client.app.state.park
    sim.tick += 3601
    sim.advance()
    history = client.get("/api/assets/RIDE_COASTER/history").json()["history"]
    assert len(history) == 1
    assert history[0]["tick"] == sim.tick


def test_synthetic_system_domain_feeds(client):
    assert client.get("/api/health").json()["status"] == "ok"
    systems = client.get("/api/systems").json()["systems"]
    for system in systems:
        response = client.get(f"/api/systems/{system['id']}/data")
        assert response.status_code == 200
        feed = response.json()
        assert feed["synthetic"]
        assert feed["records"]
        assert all(r["synthetic"] for r in feed["records"])
    erp = client.get("/api/systems/erp/data").json()
    assert "erp" in erp["records"][0]
    assert client.get("/api/systems/unknown/data").status_code == 404


@pytest.mark.parametrize("scenario", ["normal", "ride_closure", "show_surge", "heatwave", "power_fault", "water_leak", "food_rush"])
def test_comparison_is_deterministic_and_isolated(client, scenario):
    import sqlite3
    sim = client.app.state.park
    client.post("/api/scenarios", json={"scenario": "food_rush"})
    client.post("/api/actions", json={"action": "add_staff", "asset_id": "FOOD_COURT"})
    # Freshness ages are intentionally wall-clock derived. Freeze only that
    # clock while asserting comparison leaves the complete read model unchanged.
    from datetime import datetime, timezone
    fixed_now = datetime.now(timezone.utc)
    client.app.state.connectors.clock = lambda: fixed_now
    before = client.get("/api/state").json()
    original_dump = list(sim.db.iterdump())
    # A comparison must not read or write any database table.
    sim.db.set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
    try:
        response = client.get(f"/api/scenarios/compare?scenario={scenario}")
        assert response.status_code == 200
        result = response.json()
        assert client.get(f"/api/scenarios/compare?scenario={scenario}").json() == result
    finally:
        # Passing None is supported only from Python 3.11; allow all operations
        # explicitly so this isolation test also runs on Horde Python 3.10.
        sim.db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
    assert result["synthetic"]
    assert result["mutates_live_state"] is False
    assert result["method"] == "heuristic_same_tick_comparison"
    assert result["baseline_tick"] == before["tick"]
    assert result["before"]["scenario"] == "food_rush"
    assert result["after"]["scenario"] == scenario
    assert result["before"]["kpis"]["attendance"] == result["after"]["kpis"]["attendance"]
    assert result["assumptions"]
    for item in result["deltas"]:
        assert item["delta"] == round(item["after"] - item["before"], 2)
    assert client.get("/api/state").json() == before
    assert list(sim.db.iterdump()) == original_dump


def test_comparison_effects_and_unknown_scenario(client):
    baseline = client.get("/api/state").json()
    normal = client.get("/api/scenarios/compare?scenario=normal").json()
    assert normal["asset_changes"] == []
    assert all(d["delta"] == 0 for d in normal["deltas"])
    closed = client.get("/api/scenarios/compare?scenario=ride_closure").json()
    coaster = next(c for c in closed["asset_changes"] if c["asset_id"] == "RIDE_COASTER")
    assert coaster["before_status"] == "operational"
    assert coaster["after_status"] == "closed"
    assert closed["after"]["kpis"]["open_rides"] == baseline["kpis"]["open_rides"] - 1
    hot = client.get("/api/scenarios/compare?scenario=heatwave").json()
    assert hot["after"]["weather"]["temperature_c"] > hot["before"]["weather"]["temperature_c"] + 10
    assert client.get("/api/scenarios/compare?scenario=unknown").status_code == 422
    assert client.get("/api/scenarios/compare").status_code == 422


def test_bounded_history_survives_restart_and_query_limit(tmp_path):
    import json
    path = str(tmp_path / "history.db")
    with TestClient(create_app(path, run_background=False)) as c:
        sim = c.app.state.park
        source = sim.history("RIDE_COASTER", 1)[0]
        # Seed more than the retention horizon, then exercise the real pruning path.
        samples = [("RIDE_COASTER", tick, source["timestamp"], json.dumps({**source, "tick": tick}))
                   for tick in range(1, 3602)]
        sim.db.executemany("INSERT OR REPLACE INTO telemetry VALUES (?,?,?,?)", samples)
        sim.tick = 3601
        sim.advance()
        history = c.get("/api/assets/RIDE_COASTER/history?limit=3600").json()["history"]
        assert len(history) == 3600
        assert history[0]["tick"] == 3
        assert history[-1]["tick"] == 3602
        last_two = c.get("/api/assets/RIDE_COASTER/history?limit=2").json()["history"]
        assert last_two == history[-2:]
    with TestClient(create_app(path, run_background=False)) as c:
        history = c.get("/api/assets/RIDE_COASTER/history?limit=3600").json()["history"]
        assert len(history) == 3600
        assert history[0]["tick"] == 4
        assert history[-1]["tick"] == 3603
        assert history[-2]["tick"] == last_two[-1]["tick"]
