"""Synthetic dispatch is bounded by fresh state, durable intent and readback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import copy
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.planning import PlanningRequest, simulate
from backend.planning.evidence import make_bundle
from backend.replay import install_replay
from backend.workflows.api import install_workflow_routes
from backend.workflows.contracts import WorkflowError
from backend.workflows.store import WorkflowStore


def application(path, replay=False):
    app = create_app(str(path / "park.db"), run_background=False)
    if not getattr(app.state, "workflows_installed", False):
        install_workflow_routes(app)
    if replay:
        install_replay(app, str(path / "replay.db"), record_background=False, probe_renderer=False)
    return app


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PARK_PLANNING_DB", str(tmp_path / "planning.db"))
    monkeypatch.setenv("PARK_WORKFLOWS_DB", str(tmp_path / "workflows.db"))
    monkeypatch.setenv("PARK_REPLAY_DB", str(tmp_path / "replay.db"))
    return tmp_path


@pytest.fixture
def client(environment):
    with TestClient(application(environment), raise_server_exceptions=False) as c:
        yield c


def save_plan(client, scenario="ride_closure", activate=True, candidates=None):
    if activate:
        assert client.post("/api/scenarios", json={"scenario": scenario}).status_code == 200
    payload = {"scenario": scenario}
    if candidates is not None:
        payload["candidates"] = candidates
    reply = client.post("/api/planning/simulate", json=payload)
    assert reply.status_code == 200, reply.text
    bundle = reply.json()["evidence_bundle"]
    assert client.post("/api/planning/evidence", json=bundle).status_code == 200
    return bundle


def create(client, bundle, request_id="create1", **overrides):
    return client.post("/api/workflows/proposals", json={"bundle_id": bundle["bundle_id"], "branch_id": "simple_rule", "action_index": 0, "request_id": request_id, **overrides})


def execute(client, proposal, request_id="execute1"):
    return client.post(f"/api/workflows/proposals/{proposal['id']}/execute", json={"request_id": request_id})


def counts(client):
    db = client.app.state.park.db
    return (db.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0],
            db.execute("SELECT COUNT(*) FROM audit WHERE action='dispatch_maintenance'").fetchone()[0],
            db.execute("SELECT COUNT(*) FROM action_receipts").fetchone()[0])


def test_dispatch_has_receipt_verified_work_order_and_does_not_reopen_ride(client):
    bundle = save_plan(client)
    proposed = create(client, bundle)
    assert proposed.status_code == 200
    p = proposed.json()["proposal"]
    before_tick = client.get("/api/state").json()["tick"]
    accepted = execute(client, p)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["outcome"] == "accepted_workflow_not_repair"
    assert body["physical_effect"] is False
    assert body["proposal"]["readback"]["work_order"]["status"] == "open"
    assert body["proposal"]["readback"]["asset_status"] == "closed"
    assert body["proposal"]["readback"]["physical_completion"] is False
    assert body["proposal"]["receipt"]["work_order_id"] == body["proposal"]["readback"]["work_order"]["id"]
    assert counts(client) == (1, 1, 1)
    assert client.get("/api/state").json()["tick"] == before_tick + 1
    retry = execute(client, p).json()
    assert retry["idempotency"]["replayed"] is True
    assert retry["proposal"]["receipt"] == body["proposal"]["receipt"]
    assert counts(client) == (1, 1, 1)
    assert execute(client, p, "different").status_code == 409


def test_create_idempotency_preserves_original_proposal_and_conflicts(client):
    bundle = save_plan(client)
    first = create(client, bundle).json()["proposal"]
    second = create(client, bundle).json()
    assert second["proposal"] == first
    assert second["idempotency"]["replayed"] is True
    conflict = create(client, bundle, ttl_seconds=121)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "proposal_request_conflict"
    assert counts(client) == (0, 0, 0)


def test_tick_revision_changes_do_not_invalidate_relevant_unchanged_conditions(client):
    p = create(client, save_plan(client)).json()["proposal"]
    client.app.state.park.advance()
    state = client.get("/api/state").json()
    assert state["accepted_state_revision"] != p["creation_state_revision"]
    assert execute(client, p).status_code == 200


@pytest.mark.parametrize("elapsed,code", [(10, "workflow_input_not_fresh"), (301, "proposal_expired")])
def test_stale_or_expired_proposal_cannot_dispatch(client, elapsed, code):
    p = create(client, save_plan(client)).json()["proposal"]
    original_clock = client.app.state.connectors.clock
    client.app.state.connectors.clock = lambda: original_clock() + timedelta(seconds=elapsed)
    response = execute(client, p)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == code
    assert counts(client) == (0, 0, 0)


def test_scenario_change_and_new_work_order_invalidate_proposal(client):
    p = create(client, save_plan(client)).json()["proposal"]
    client.post("/api/scenarios", json={"scenario": "normal"})
    response = execute(client, p)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "proposal_preconditions_changed"
    bundle = save_plan(client)
    p = create(client, bundle, request_id="create2").json()["proposal"]
    client.post("/api/actions", json={"action": "dispatch_maintenance", "request_id": "other-operator"})
    assert execute(client, p).json()["detail"]["code"] == "proposal_preconditions_changed"
    assert counts(client) == (1, 1, 1)
    assert create(client, bundle, request_id="create3").json()["detail"]["code"] == "work_order_already_open"


@pytest.mark.parametrize("source,metric,value", [("ride_scada", "status", "warning"), ("cmms", "maintenance.inspection_status", "passed")])
def test_current_canonical_status_or_inspection_change_blocks_execution(client, source, metric, value):
    p = create(client, save_plan(client)).json()["proposal"]
    client.post(f"/api/connectors/{source}/simulation", json={"mode": "paused"})
    event = {"event_id": "changed-input", "source_asset_id": source + "/RIDE_COASTER", "metric": metric,
             "value": value, "unit": "state", "source_timestamp": client.app.state.connectors.clock().isoformat()}
    injected = client.post(f"/api/connectors/{source}/ingest", json={"synthetic": True, "events": [event]})
    assert injected.status_code == 200
    assert injected.json()["accepted"] == 1
    response = execute(client, p)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "proposal_preconditions_changed"
    assert counts(client) == (0, 0, 0)


def test_concurrent_identical_requests_acknowledge_one_dispatch(client):
    p = create(client, save_plan(client)).json()["proposal"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: execute(client, p), range(6)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(not r.json()["idempotency"]["replayed"] for r in responses) == 1
    assert len({r.json()["proposal"]["receipt"]["id"] for r in responses}) == 1
    assert counts(client) == (1, 1, 1)


def test_crash_after_command_commit_recovers_without_reexecution_even_after_expiry(client, monkeypatch):
    p = create(client, save_plan(client)).json()["proposal"]
    store = client.app.state.workflow_store
    update = store.update
    fired = False
    def fail_completion(proposal):
        nonlocal fired
        if proposal["status"] == "accepted_workflow_not_repair" and not fired:
            fired = True
            raise RuntimeError("simulated crash after park transaction committed")
        return update(proposal)
    monkeypatch.setattr(store, "update", fail_completion)
    assert execute(client, p).status_code == 500
    assert counts(client) == (1, 1, 1)
    assert store.get(p["id"])["status"] == "execution_intent_recorded"
    client.post("/api/actions", json={"action": "reset"})
    original_clock = client.app.state.connectors.clock
    client.app.state.connectors.clock = lambda: original_clock() + timedelta(seconds=301)
    response = execute(client, p)
    assert response.status_code == 200
    assert response.json()["idempotency"]["replayed"] is True
    assert response.json()["proposal"]["readback"]["work_order"]["status"] == "closed_by_reset"
    assert counts(client) == (1, 1, 1)


def test_restart_retains_proposal_and_original_receipt(environment):
    with TestClient(application(environment)) as first:
        p = create(first, save_plan(first)).json()["proposal"]
        receipt = execute(first, p).json()["proposal"]["receipt"]
    with TestClient(application(environment)) as second:
        before = second.get("/api/state").json()["tick"]
        response = execute(second, p)
        assert response.status_code == 200
        assert response.json()["proposal"]["receipt"] == receipt
        assert response.json()["idempotency"]["replayed"] is True
        assert second.get("/api/state").json()["tick"] == before
        assert counts(second) == (1, 1, 1)


def test_unaccepted_proposal_survives_restart_with_changed_revision(environment):
    with TestClient(application(environment)) as first:
        p = create(first, save_plan(first)).json()["proposal"]
    with TestClient(application(environment)) as second:
        assert second.get("/api/state").json()["accepted_state_revision"] != p["creation_state_revision"]
        assert execute(second, p).status_code == 200


def test_restart_recovers_committed_receipt_after_incomplete_workflow(environment, monkeypatch):
    with TestClient(application(environment), raise_server_exceptions=False) as first:
        p = create(first, save_plan(first)).json()["proposal"]
        update = first.app.state.workflow_store.update
        def fail_completion(proposal):
            if proposal["status"] == "accepted_workflow_not_repair":
                raise RuntimeError("process interrupted before workflow completion")
            return update(proposal)
        monkeypatch.setattr(first.app.state.workflow_store, "update", fail_completion)
        assert execute(first, p).status_code == 500
        assert counts(first) == (1, 1, 1)
    with TestClient(application(environment)) as restarted:
        response = execute(restarted, p)
        assert response.status_code == 200
        assert response.json()["idempotency"]["replayed"] is True
        assert counts(restarted) == (1, 1, 1)


def test_execution_key_cannot_be_reused_for_another_proposal(client):
    candidates = [{"id": "inspect", "label": "Inspect faults", "actions": [
        {"action": "dispatch_maintenance", "asset_id": "RIDE_COASTER"},
        {"action": "dispatch_maintenance", "asset_id": "POWER_HUB"}]}]
    # The planner treats duplicate park dispatch effects as unsupported in a
    # single candidate, so store two independently evaluated action branches.
    candidates = [{"id": "coaster", "label": "Coaster inspection", "actions": [candidates[0]["actions"][0]]},
                  {"id": "power", "label": "Feeder inspection", "actions": [candidates[0]["actions"][1]]}]
    bundle = save_plan(client, "power_fault", candidates=candidates)
    first = create(client, bundle, branch_id="coaster").json()["proposal"]
    second = create(client, bundle, request_id="create2", branch_id="power").json()["proposal"]
    assert execute(client, first, request_id="shared").status_code == 200
    conflict = execute(client, second, request_id="shared")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "execution_request_conflict"
    assert counts(client) == (1, 1, 1)


def test_historical_or_forged_bundle_never_overrides_current_state(client):
    hypothetical = save_plan(client, activate=False)
    response = create(client, hypothetical)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "hypothetical_scenario_not_active"
    snapshot = client.get("/api/state").json()
    target = next(a for a in snapshot["assets"] if a["id"] == "RIDE_COASTER")
    target["status"] = "closed"
    target["maintenance"]["inspection_status"] = "review_required"
    request = PlanningRequest(scenario="normal", candidates=[{"id": "fabricated", "label": "Fabricated historical fault", "actions": [{"action": "dispatch_maintenance", "asset_id": "RIDE_COASTER"}]}])
    as_of = client.app.state.connectors.clock()
    forged = make_bundle(snapshot, request, simulate(snapshot, request, as_of=as_of), as_of)
    saved = client.post("/api/planning/evidence", json=forged)
    assert saved.status_code == 200  # Internally consistent historical data, not authenticated origin.
    assert saved.json()["origin_authenticated"] is False
    response = create(client, forged, request_id="forged", branch_id="fabricated")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_current_maintenance_need"
    assert counts(client) == (0, 0, 0)


def test_replay_blocks_creation_and_execution_and_all_four_stores_close(environment):
    app = application(environment, replay=True)
    with TestClient(app) as client:
        bundle = save_plan(client)
        p = create(client, bundle).json()["proposal"]
        sid = client.get("/api/timeline").json()["snapshots"][0]["id"]
        client.post("/api/view", json={"mode": "replay", "snapshot_id": sid})
        assert execute(client, p).json()["detail"]["code"] == "recorded_view"
        assert create(client, bundle, request_id="create2").json()["detail"]["code"] == "recorded_view"
        assert client.get("/api/workflows/proposals/" + p["id"]).status_code == 200
        assert counts(client) == (0, 0, 0)
        connections = [app.state.park.db, app.state.replay.db, app.state.planning_evidence.db, app.state.workflow_store.db]
        assert len({db.execute("PRAGMA database_list").fetchone()[2] for db in connections}) == 4
    for db in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")


def test_unsupported_action_and_invalid_ttl_are_rejected(client):
    bundle = save_plan(client, scenario="food_rush")
    assert create(client, bundle).status_code == 422
    assert create(client, bundle, ttl_seconds=29).status_code == 422
    assert create(client, bundle, ttl_seconds=301).status_code == 422
    assert client.get("/api/workflows/capabilities").json()["physical_control"] is False
    assert counts(client) == (0, 0, 0)


def test_retention_preserves_existing_and_refuses_foreign_database(environment):
    store = WorkflowStore(str(environment / "tiny.db"), max_proposals=1)
    store.create({"id": "first"}, "request1", {})
    with pytest.raises(WorkflowError) as failure:
        store.create({"id": "second"}, "request2", {})
    assert failure.value.code == "workflow_store_full"
    assert store.get("first") == {"id": "first"}
    store.close()
    foreign_path = str(environment / "foreign.db")
    with sqlite3.connect(foreign_path) as db:
        db.execute("CREATE TABLE other_application(value TEXT)")
    with pytest.raises(ValueError, match="foreign tables"):
        WorkflowStore(foreign_path)


def test_conflict_response_explains_existing_order_and_changed_conditions(client):
    bundle = save_plan(client)
    proposal = create(client, bundle).json()["proposal"]
    accepted = client.post("/api/actions", json={"action": "dispatch_maintenance", "asset_id": "RIDE_COASTER", "request_id": "another-operator"}).json()
    order_id = accepted["result"]["work_order_id"]
    conflict = execute(client, proposal)
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    context = detail["context"]
    assert context["next_step"] == "inspect_existing_work_order"
    assert context["current_work_order_ids"] == [order_id]
    assert context["asset_detail_url"] == "/api/assets/RIDE_COASTER"
    assert context["changed_fields"]["open_work_order_ids"] == {"proposed": [], "current": [order_id]}
    assert context["changed_fields"]["observed_open_work_orders"] == {"proposed": 0, "current": 1}
    existing = create(client, bundle, request_id="fresh-proposal").json()["detail"]["context"]
    assert existing["next_step"] == "inspect_existing_work_order"
    assert existing["current_work_order_ids"] == [order_id]
    assert any(order["id"] == order_id for order in client.get(existing["asset_detail_url"]).json()["work_orders"])
    assert counts(client) == (1, 1, 1)


def test_receipt_recovery_does_not_refresh_stale_asset_status_provenance(client):
    proposal = create(client, save_plan(client)).json()["proposal"]
    first = execute(client, proposal).json()["proposal"]
    assert first["readback"]["asset_status_evidence"]["quality"] == "good"
    client.post("/api/connectors/ride_scada/simulation", json={"mode": "paused"})
    prior_clock = client.app.state.connectors.clock
    client.app.state.connectors.clock = lambda: prior_clock() + timedelta(seconds=10)
    recovered = execute(client, proposal).json()["proposal"]
    assert recovered["receipt"] == first["receipt"]
    evidence = recovered["readback"]["asset_status_evidence"]
    assert evidence["quality"] == "stale"
    assert evidence["source_id"] == "ride_scada"
    assert evidence["source_timestamp"] == first["readback"]["asset_status_evidence"]["source_timestamp"]
    assert evidence["source_timestamp"] != recovered["readback"]["observed_at"]
    assert recovered["readback"]["work_order"]["id"] == first["readback"]["work_order"]["id"]
    assert counts(client) == (1, 1, 1)
