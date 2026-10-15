"""Historical inspection preserves accepted values and never rewrites live state."""

import copy
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.replay import install_replay
from backend.replay_store import ReplayStore
from backend.simulator import ParkSimulator


@pytest.fixture
def snapshot(tmp_path):
    simulator = ParkSimulator(str(tmp_path / "source.db"))
    value = simulator.snapshot()
    simulator.close()
    return value


def test_recorded_snapshot_survives_restart_and_different_configuration(
    tmp_path, snapshot
):
    path = tmp_path / "replay.db"
    store = ReplayStore(path, "scene-a", "config-a")
    ident = store.capture(snapshot, {"coaster_phase": 0.25, "wheel_angle": 1.2})
    expected = copy.deepcopy(snapshot)
    snapshot["assets"][0]["power_kw"] = 99999
    store.close()
    reopened = ReplayStore(path, "scene-b", "config-b")
    reopened.select(ident)
    display = reopened.view_state(snapshot)
    assert display["assets"] == expected["assets"]
    assert display["kpis"] == expected["kpis"]
    assert display["view"]["scene_revision"] == "scene-a"
    assert display["view"]["config_revision"] == "config-a"
    assert not display["view"]["scene_matches_current"]
    assert display["view"]["recorded_motion"]["coaster_phase"] == 0.25
    reopened.close()


def test_retention_is_bounded_and_selected_view_remains_immutable(tmp_path, snapshot):
    store = ReplayStore(tmp_path / "replay.db", "a", "b", retention_limit=3)
    first = store.capture(snapshot)
    store.select(first)
    expected = store.view_state(snapshot)
    for tick in range(10, 20):
        snapshot["tick"] = tick
        snapshot["kpis"]["power_kw"] = tick
        store.capture(snapshot)
    assert len(store.timeline()) == 3
    with pytest.raises(KeyError):
        store.get(first)
    frozen = store.view_state(snapshot)
    assert frozen["kpis"] == expected["kpis"]
    assert frozen["view"]["live_tick"] == 19
    frozen["assets"].clear()
    assert store.view_state(snapshot)["assets"]
    store.select(None)
    assert store.view_state(snapshot)["kpis"]["power_kw"] == 19
    store.close()


def test_duplicate_capture_does_not_grow_history(tmp_path, snapshot):
    store = ReplayStore(tmp_path / "replay.db", "a", "b")
    first = store.capture(snapshot)
    assert store.capture(copy.deepcopy(snapshot)) == first
    assert len(store.timeline()) == 1
    store.close()


def test_historical_asset_history_excludes_future_values(tmp_path, snapshot):
    store = ReplayStore(tmp_path / "replay.db", "a", "b")
    ids = []
    for tick, queue in enumerate([10, 20, 300], 1):
        snapshot["tick"] = tick
        snapshot["assets"][0]["queue_minutes"] = queue
        ids.append(store.capture(snapshot))
    store.select(ids[1])
    history = store.history(snapshot["assets"][0]["id"])
    assert [row["queue_minutes"] for row in history] == [10, 20]
    assert all(row["snapshot_id"] <= ids[1] for row in history)
    store.close()


def test_historical_work_orders_do_not_read_current_transaction_state(
    tmp_path, snapshot
):
    store = ReplayStore(tmp_path / "replay.db", "a", "b")
    ident = store.capture(
        snapshot, work_orders=[{"id": 1, "asset_id": "RIDE_COASTER", "status": "open"}]
    )
    store.select(ident)
    asset = next(
        a for a in store.view_state(snapshot)["assets"] if a["id"] == "RIDE_COASTER"
    )
    assert asset["work_orders"] == [
        {"id": 1, "asset_id": "RIDE_COASTER", "status": "open"}
    ]
    store.close()


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "park.db"), run_background=False)
    install_replay(
        app, str(tmp_path / "replay.db"), record_background=False, probe_renderer=False
    )
    with TestClient(app) as result:
        yield result


def test_replay_api_locks_writes_while_live_simulation_keeps_advancing(client):
    before = client.get("/api/view/state").json()
    ident = client.get("/api/timeline").json()["snapshots"][0]["id"]
    recorded = client.post(
        "/api/view", json={"mode": "replay", "snapshot_id": ident}
    ).json()
    assert recorded["view"]["read_only"]
    for route, payload in [
        ("/api/scenarios", {"scenario": "ride_closure"}),
        ("/api/actions", {"action": "reset"}),
        ("/api/connectors/bms/simulation", {"mode": "offline"}),
    ]:
        assert client.post(route, json=payload).status_code == 409
    assert client.get("/api/scenarios/compare?scenario=ride_closure").status_code == 409
    client.app.state.park.advance()  # The real 1Hz producer remains independent of the cursor.
    live = client.get("/api/state").json()
    assert live["tick"] > before["tick"]
    still = client.get("/api/view/state").json()
    assert still["tick"] == recorded["tick"]
    assert still["assets"] == recorded["assets"]
    resumed = client.post("/api/view", json={"mode": "live"}).json()
    assert resumed["tick"] == live["tick"] and not resumed["view"]["read_only"]
    assert (
        client.post("/api/scenarios", json={"scenario": "ride_closure"}).status_code
        == 200
    )


def test_replay_asset_detail_and_history_use_the_same_record(client):
    client.post("/api/scenarios", json={"scenario": "ride_closure"})
    client.post(
        "/api/actions",
        json={"action": "dispatch_maintenance", "asset_id": "RIDE_COASTER"},
    )
    ident = client.get("/api/timeline").json()["snapshots"][-1]["id"]
    client.post("/api/actions", json={"action": "reset"})
    client.post("/api/view", json={"mode": "replay", "snapshot_id": ident})
    detail = client.get("/api/view/assets/RIDE_COASTER").json()
    assert detail["status"] == "closed"
    assert detail["work_orders"][0]["status"] == "open"
    history = client.get("/api/view/assets/RIDE_COASTER/history").json()
    assert history["history"][-1]["status"] == "closed"
    assert history["view"]["snapshot_id"] == ident
    assert client.get("/api/view/assets/missing").status_code == 404
    assert client.get("/api/view/assets/missing/history").status_code == 404


def test_cursor_validation_and_no_invented_pose(client):
    initial = client.get("/api/timeline").json()["snapshots"][0]
    assert initial["has_recorded_motion"] is False
    for payload in [
        {"mode": "replay"},
        {"mode": "live", "snapshot_id": 1},
        {"mode": "other"},
    ]:
        assert client.post("/api/view", json=payload).status_code == 422
    assert (
        client.post(
            "/api/view", json={"mode": "replay", "snapshot_id": 99999}
        ).status_code
        == 404
    )
    assert client.get("/api/timeline?limit=0").status_code == 422
    display = client.post(
        "/api/view", json={"mode": "replay", "snapshot_id": initial["id"]}
    ).json()
    assert display["view"]["recorded_motion"] is None
    assert display["view"]["work_orders_recorded"]


def test_background_recording_and_live_ticks_continue_while_viewing_history(tmp_path):
    import time

    app = create_app(str(tmp_path / "background.db"), run_background=True)
    install_replay(
        app, str(tmp_path / "replay.db"), interval=0.15, probe_renderer=False
    )
    with TestClient(app) as client:
        ident = client.get("/api/timeline").json()["snapshots"][0]["id"]
        first = client.post(
            "/api/view", json={"mode": "replay", "snapshot_id": ident}
        ).json()
        time.sleep(1.3)
        assert client.get("/api/state").json()["tick"] > first["tick"]
        assert len(client.get("/api/timeline").json()["snapshots"]) > 1
        still = client.get("/api/view/state").json()
        assert still["assets"] == first["assets"] and still["kpis"] == first["kpis"]


def test_api_can_reopen_a_historical_record_after_service_restart(tmp_path):
    path = str(tmp_path / "park.db")
    history = str(tmp_path / "replay.db")

    def application():
        app = create_app(path, run_background=False)
        install_replay(app, history, record_background=False, probe_renderer=False)
        return app

    with TestClient(application()) as first:
        old = first.post("/api/scenarios", json={"scenario": "power_fault"}).json()
        ident = first.get("/api/timeline").json()["snapshots"][-1]["id"]
        first.post("/api/actions", json={"action": "reset"})
    with TestClient(application()) as second:
        restored = second.post(
            "/api/view", json={"mode": "replay", "snapshot_id": ident}
        ).json()
        assert restored["kpis"] == old["kpis"]
        assert restored["scenario"] == "power_fault"
        assert restored["tick"] == old["tick"]
        assert second.get("/api/state").json()["scenario"] == "normal"
