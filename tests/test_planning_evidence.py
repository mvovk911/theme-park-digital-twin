"""Historical bundles survive cache expiry and cannot become execution authority."""
import copy
from datetime import datetime, timedelta
import json
import sqlite3
import shutil
import subprocess
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.connectors import ConnectorRuntime, ParkReadModel
from backend.planning import PlanningRequest, simulate
from backend.planning.evidence import (EvidenceError, EvidenceStore, MAX_BUNDLE_BYTES,
                                       MAX_SAFE_INTEGER, canonical_bytes, digest, make_bundle, verify_bundle)
from backend.simulator import ParkSimulator
from backend.replay import install_replay


@pytest.fixture
def bundle():
    park = ParkSimulator(":memory:")
    state = ParkReadModel(park, ConnectorRuntime(park.base)).snapshot()
    as_of = datetime.fromisoformat(state["timestamp"])
    request = PlanningRequest(scenario="food_rush", expected_state_revision=state["accepted_state_revision"])
    result = simulate(state, request, as_of=as_of)
    value = make_bundle(state, request, result, as_of)
    park.close()
    return value


def test_bundle_reproduces_and_does_not_alias_response(bundle):
    verified = verify_bundle(bundle)
    assert verified["verified"] is True
    assert verified["execution_authority"] is False
    assert verified["origin_authenticated"] is False
    assert verified["scope"] == "historical_reproduction"
    assert len(canonical_bytes(bundle)) < MAX_BUNDLE_BYTES


def test_changed_result_rejected_even_when_attacker_rehashes(bundle):
    changed = copy.deepcopy(bundle)
    changed["payload"]["result"]["branches"][0]["summary"]["served_guests"] += 1
    with pytest.raises(EvidenceError, match="SHA256"):
        verify_bundle(changed)
    changed["bundle_id"] = digest(changed["payload"])
    with pytest.raises(EvidenceError) as failure:
        verify_bundle(changed)
    assert failure.value.code == "evidence_reproduction_mismatch"


@pytest.mark.parametrize("field,value,code", [
    ("model_source_sha256", "a" * 64, "evidence_model_mismatch"),
    ("schema_version", "unknown", "unsupported_evidence_schema"),
    ("evaluation_as_of", "2026-10-19T10:00:00", "invalid_evidence"),
])
def test_unsupported_or_ambiguous_evidence_rejected(bundle, field, value, code):
    bundle["payload"][field] = value
    bundle["bundle_id"] = digest(bundle["payload"])
    with pytest.raises(EvidenceError) as failure:
        verify_bundle(bundle)
    assert failure.value.code == code


def test_durable_save_dedup_restart_and_caps_preserve_existing(bundle, tmp_path):
    path = str(tmp_path / "evidence.db")
    store = EvidenceStore(path, max_bundles=1)
    assert store.save(bundle)["already_saved"] is False
    assert store.save(bundle)["already_saved"] is True
    modified = copy.deepcopy(bundle)
    # Same historical inputs/result can have a different valid explicit as-of
    # time while remaining inside the sample freshness window.
    modified["payload"]["evaluation_as_of"] = (datetime.fromisoformat(bundle["payload"]["evaluation_as_of"]) + timedelta(milliseconds=1)).isoformat()
    modified["bundle_id"] = digest(modified["payload"])
    with pytest.raises(EvidenceError) as failure:
        store.save(modified)
    assert failure.value.code == "evidence_store_full"
    assert store.list()["total"] == 1
    store.close()
    reopened = EvidenceStore(path)
    assert reopened.get(bundle["bundle_id"]) == bundle
    assert verify_bundle(reopened.get(bundle["bundle_id"]))["verified"]
    reopened.close()


def test_byte_cap_and_foreign_database_are_not_silently_overwritten(bundle, tmp_path):
    store = EvidenceStore(":memory:", max_bytes=1)
    with pytest.raises(EvidenceError) as failure:
        store.save(bundle)
    assert failure.value.code == "evidence_store_full"
    assert store.list()["total"] == 0
    store.close()
    path = str(tmp_path / "foreign.db")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE live_secret(value TEXT)")
    with pytest.raises(ValueError, match="other application tables"):
        EvidenceStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("live_secret",)]


def test_http_explicit_save_survives_revision_cache_clear_and_process_restart(tmp_path, monkeypatch):
    park_path = str(tmp_path / "park.db")
    evidence_path = str(tmp_path / "separate-evidence.db")
    monkeypatch.setenv("PARK_PLANNING_DB", evidence_path)
    with TestClient(create_app(park_path, run_background=False)) as client:
        before = client.get("/api/state").json()
        reply = client.post("/api/planning/simulate", json={"scenario": "food_rush"})
        assert reply.status_code == 200
        bundle = reply.json()["evidence_bundle"]
        assert client.get("/api/planning/evidence").json()["total"] == 0
        client.app.state.read_model._revisions.clear()
        assert client.post("/api/planning/evidence/verify", json=bundle).json()["verified"] is True
        saved = client.post("/api/planning/evidence", json=bundle)
        assert saved.status_code == 200
        assert saved.json()["execution_authority"] is False
        assert client.post("/api/planning/evidence", json=bundle).json()["already_saved"] is True
        assert client.get("/api/state").json()["accepted_state_revision"] == before["accepted_state_revision"]
        assert client.get("/api/audit").json()["events"] == []
    with TestClient(create_app(park_path, run_background=False)) as restarted:
        exported = restarted.get("/api/planning/evidence/" + bundle["bundle_id"])
        assert exported.json() == bundle
        assert restarted.post("/api/planning/evidence/verify", json=exported.json()).json()["verified"] is True
        assert restarted.get("/api/planning/evidence").json()["total"] == 1


def test_http_untrusted_input_bounds_and_duplicate_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("PARK_PLANNING_DB", str(tmp_path / "evidence.db"))
    with TestClient(create_app(str(tmp_path / "park.db"), run_background=False)) as client:
        assert client.post("/api/planning/evidence", content=b"x" * (MAX_BUNDLE_BYTES + 1)).status_code == 413
        for payload in [b'{"payload":{},"payload":{}}', b'{"x":NaN}', b'[]', b'{"bad":true}', b'{"unsafe":9007199254740992}']:
            assert client.post("/api/planning/evidence", content=payload).status_code == 422
        assert client.get("/api/planning/evidence/" + "0" * 64).status_code == 404
        assert client.get("/api/planning/evidence?limit=101").status_code == 422
        assert client.get("/api/planning/evidence").json()["total"] == 0


def test_replay_lifespan_keeps_three_databases_separate_and_evidence_does_not_move_cursor(tmp_path, monkeypatch):
    monkeypatch.delenv("PARK_PLANNING_DB", raising=False)
    monkeypatch.delenv("PARK_REPLAY_DB", raising=False)
    app = create_app(str(tmp_path / "park.db"), run_background=False)
    install_replay(app, str(tmp_path / "replay.db"), record_background=False, probe_renderer=False)
    with TestClient(app) as client:
        connections = [app.state.park.db, app.state.replay.db, app.state.planning_evidence.db]
        paths = [connection.execute("PRAGMA database_list").fetchone()[2] for connection in connections]
        assert len(set(paths)) == 3
        assert all(str(tmp_path) in path for path in paths)
        bundle = client.post("/api/planning/simulate", json={"scenario": "food_rush"}).json()["evidence_bundle"]
        sid = client.get("/api/timeline").json()["snapshots"][0]["id"]
        assert client.post("/api/view", json={"mode": "replay", "snapshot_id": sid}).status_code == 200
        cursor = copy.deepcopy(app.state.replay.cursor())
        live_state = app.state.park.snapshot()
        assert client.post("/api/planning/simulate", json={"scenario": "food_rush"}).status_code == 409
        assert client.post("/api/planning/evidence", json=bundle).status_code == 200
        assert client.post("/api/planning/evidence/verify", json=bundle).json()["verified"] is True
        assert client.get("/api/planning/evidence/" + bundle["bundle_id"]).json() == bundle
        assert app.state.replay.cursor() == cursor
        assert app.state.park.snapshot() == live_state
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")


def test_actual_javascript_json_roundtrip_preserves_bundle_hash_and_reproduction(bundle):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the actual JavaScript serialization regression")
    script = "let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s))));"
    transported = subprocess.run([node, "-e", script], input=json.dumps(bundle), text=True,
                                 capture_output=True, check=True, timeout=10)
    browser_bundle = json.loads(transported.stdout)
    assert verify_bundle(browser_bundle)["verified"] is True
    assert digest(browser_bundle["payload"]) == bundle["bundle_id"]
    assert canonical_bytes({"value": 1.0, "zero": -0.0}) == canonical_bytes({"value": 1, "zero": 0})
    values = [1.0000000000000002, .000001, 1e-7, MAX_SAFE_INTEGER, -MAX_SAFE_INTEGER, -0.0]
    numeric_transport = subprocess.run([node, "-e", script], input=json.dumps(values), text=True,
                                      capture_output=True, check=True, timeout=10)
    assert canonical_bytes(values) == canonical_bytes(json.loads(numeric_transport.stdout))


@pytest.mark.parametrize("number", [MAX_SAFE_INTEGER + 1, -(MAX_SAFE_INTEGER + 1), float(MAX_SAFE_INTEGER + 1), 1e20, float("nan"), float("inf")])
def test_unsafe_or_nonfinite_numbers_cannot_enter_hashed_evidence(number):
    with pytest.raises(ValueError):
        canonical_bytes({"number": number})
