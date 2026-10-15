"""Durable action receipts share the transaction with all simulated side effects."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.simulator import ActionRequestConflict, ParkSimulator


@pytest.fixture
def park(tmp_path):
    park = ParkSimulator(str(tmp_path / "park.db"))
    yield park
    park.close()


def database_image(park):
    return "\n".join(park.db.iterdump())


def test_normalized_default_target_retry_returns_immutable_ack_without_effects(park):
    first = park.act("add_staff", request_id="staff-1")
    original = deepcopy(first["result"])
    assert original["target"] == {"scope": "asset", "asset_id": "FOOD_COURT"}
    assert original["acknowledgement"] == "accepted"
    assert original["lifecycle"] == "simulation_applied"
    assert original["synthetic"] and original["physical_effect"] is False
    first["result"]["message"] = "caller changed this"
    park.act("reset")
    before, database = park.snapshot(), database_image(park)
    second = park.act("add_staff", "FOOD_COURT", request_id="staff-1")
    assert second["result"] == original
    assert second["idempotency"] == {"request_id": "staff-1", "replayed": True}
    assert second["state"] == before
    assert database_image(park) == database
    assert park.mitigations == {}  # Retrying an old acknowledgement does not reapply a reset effect.


def test_same_id_different_normalized_payload_conflicts_without_changes(park):
    park.act("add_staff", request_id="collision")
    before, database = park.snapshot(), database_image(park)
    for action, asset in (("add_staff", "FIRST_AID"), ("replenish_stock", "FOOD_COURT")):
        with pytest.raises(ActionRequestConflict):
            park.act(action, asset, request_id="collision")
        assert park.snapshot() == before
        assert database_image(park) == database
        assert park.db.in_transaction is False


def test_dispatch_ack_is_open_work_order_and_survives_reset_without_reopening(park):
    park.set_scenario("ride_closure")
    first = park.act("dispatch_maintenance", request_id="dispatch-1")
    assert first["result"]["lifecycle"] == "work_order_open"
    assert first["result"]["work_order_id"] == park.asset("RIDE_COASTER")["work_orders"][0]["id"]
    assert park.asset("RIDE_COASTER")["status"] == "closed"
    park.act("reset")
    before = database_image(park)
    retry = park.act("dispatch_maintenance", "RIDE_COASTER", request_id="dispatch-1")
    assert retry["result"] == first["result"]
    assert database_image(park) == before
    assert park.asset("RIDE_COASTER")["work_orders"][0]["status"] == "closed_by_reset"


@pytest.mark.parametrize("action,asset", [("dispatch_maintenance", "RIDE_COASTER"), ("add_staff", "FIRST_AID"), ("reset", None), ("repair_leak", "WATER_PLANT")])
def test_receipt_storage_failure_rolls_back_every_effect_and_can_retry(park, action, asset):
    park.set_scenario("water_leak")
    park.act("dispatch_maintenance", "WATER_PLANT")
    park.act("add_staff", "FOOD_COURT")
    park.db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON action_receipts BEGIN SELECT RAISE(ABORT, 'injected receipt failure'); END")
    park.db.commit()
    before, database = park.snapshot(), database_image(park)
    mitigations = deepcopy(park.mitigations)
    with pytest.raises(sqlite3.IntegrityError, match="injected receipt failure"):
        park.act(action, asset, request_id="retry-failed-transaction")
    assert park.snapshot() == before
    assert park.scenario == before["scenario"] and park.tick == before["tick"]
    assert park.mitigations == mitigations
    assert database_image(park) == database
    assert park.db.in_transaction is False
    park.db.execute("DROP TRIGGER fail_receipt")
    park.db.commit()
    result = park.act(action, asset, request_id="retry-failed-transaction")
    assert result["idempotency"]["replayed"] is False
    assert park.act(action, asset, request_id="retry-failed-transaction")["idempotency"]["replayed"] is True


def test_legacy_action_failure_also_rolls_back_without_request_id(park, monkeypatch):
    before, database = park.snapshot(), database_image(park)
    original = park._advance_uncommitted
    def fail_after_advance():
        original()
        raise RuntimeError("failed before commit")
    monkeypatch.setattr(park, "_advance_uncommitted", fail_after_advance)
    with pytest.raises(RuntimeError, match="before commit"):
        park.act("dispatch_maintenance")
    assert park.snapshot() == before
    assert database_image(park) == database
    assert park.db.in_transaction is False


def test_http_concurrent_same_id_requests_apply_dispatch_once(tmp_path):
    with TestClient(create_app(str(tmp_path / "concurrent.db"), run_background=False)) as client:
        payload = {"action": "dispatch_maintenance", "request_id": "concurrent-dispatch"}
        before = client.app.state.park.tick
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: client.post("/api/actions", json=payload), range(8)))
        assert all(response.status_code == 200 for response in responses)
        replies = [response.json() for response in responses]
        assert all(reply["result"] == replies[0]["result"] for reply in replies)
        assert sum(not reply["idempotency"]["replayed"] for reply in replies) == 1
        assert client.app.state.park.tick == before + 1
        assert len(client.get("/api/audit").json()["events"]) == 1
        assert len(client.get("/api/assets/RIDE_COASTER").json()["work_orders"]) == 1


def test_http_retry_after_restart_and_lost_response(tmp_path, monkeypatch):
    path = str(tmp_path / "restart.db")
    payload = {"action": "dispatch_maintenance", "request_id": "restart-dispatch"}
    with TestClient(create_app(path, run_background=False), raise_server_exceptions=False) as client:
        # The action transaction commits; assembling its HTTP state response fails.
        reader = client.app.state.read_model
        original = reader.snapshot
        monkeypatch.setattr(reader, "snapshot", lambda: (_ for _ in ()).throw(RuntimeError("lost response")))
        assert client.post("/api/actions", json=payload).status_code == 500
        monkeypatch.setattr(reader, "snapshot", original)
        first_retry = client.post("/api/actions", json=payload).json()
        assert first_retry["idempotency"]["replayed"] is True
        acknowledged = first_retry["result"]
    with TestClient(create_app(path, run_background=False)) as client:
        before = client.app.state.park.snapshot()
        database = database_image(client.app.state.park)
        response = client.post("/api/actions", json={**payload, "asset_id": "RIDE_COASTER"})
        assert response.status_code == 200
        retry = response.json()
        assert retry["result"] == acknowledged
        assert retry["idempotency"]["replayed"] is True
        assert retry["state"]["tick"] == before["tick"]
        assert database_image(client.app.state.park) == database
        collision = client.post("/api/actions", json={**payload, "asset_id": "RIDE_WHEEL"})
        assert collision.status_code == 409
        assert collision.json()["detail"]["code"] == "request_id_conflict"


def test_http_request_id_validation_and_legacy_compatibility(tmp_path):
    with TestClient(create_app(str(tmp_path / "legacy.db"), run_background=False)) as client:
        for invalid in ("", " ", "a" * 129, "has spaces", "line\nbreak", 123, "a\n"):
            assert client.post("/api/actions", json={"action": "add_staff", "request_id": invalid}).status_code == 422
        for _ in range(2):
            response = client.post("/api/actions", json={"action": "add_staff"})
            assert response.status_code == 200
            assert response.json()["idempotency"] == {"request_id": None, "replayed": False}
        assert len(client.get("/api/audit").json()["events"]) == 2
        assert client.app.state.park.db.execute("SELECT COUNT(*) FROM action_receipts").fetchone()[0] == 0
        # Failed applicability checks do not consume an otherwise valid request ID.
        invalid = client.post("/api/actions", json={"action": "repair_leak", "asset_id": "HOTEL", "request_id": "correctable"})
        assert invalid.status_code == 422
        assert client.post("/api/actions", json={"action": "repair_leak", "request_id": "correctable"}).status_code == 200
