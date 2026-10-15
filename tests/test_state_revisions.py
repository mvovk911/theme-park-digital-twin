"""Bounded exact-frame state retention, separate from durable replay."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.connectors import ConnectorRuntime, ParkReadModel
from backend.connectors.validation import parse_timestamp
from backend.simulator import ParkSimulator


@pytest.fixture
def system(tmp_path):
    park = ParkSimulator(str(tmp_path / "park.db"))
    moment = [parse_timestamp(park.snapshot()["timestamp"])]
    connectors = ConnectorRuntime(park.base, clock=lambda: moment[0])
    reader = ParkReadModel(park, connectors)
    yield park, connectors, reader, moment
    park.close()


def test_retained_snapshot_is_immutable_and_first_capture_wins(system):
    _, connectors, reader, moment = system
    initial = reader.snapshot()
    revision = initial["accepted_state_revision"]
    first = reader.revision_snapshot(revision)
    assert first["state"] == initial
    assert first["scope"] == "retained canonical state; not durable replay"
    original = deepcopy(first)
    initial["assets"][0]["status"] = "caller mutation"
    first["state"]["assets"].clear()
    first["captured_at"] = "caller mutation"
    moment[0] += timedelta(seconds=.5)
    later = reader.snapshot()
    assert later["accepted_state_revision"] == revision
    assert later["assets"][0]["data_quality"] != original["state"]["assets"][0]["data_quality"]
    assert reader.revision_snapshot(revision) == original
    assert len(reader._revisions) == 1


def test_same_tick_ingestion_new_revision_and_duplicate_counter_not_recaptured(system):
    park, connectors, reader, moment = system
    reader.snapshot()
    connectors.set_simulation_mode("weather", "paused")
    paused = reader.snapshot()
    reading = {"event_id": "revision-test", "source_asset_id": "weather/WEATHER_STATION", "metric": "temperature_c",
               "value": 38.0, "unit": "Cel", "source_timestamp": moment[0].isoformat()}
    connectors.ingest_demo("weather", [reading])
    accepted = reader.snapshot()
    assert paused["tick"] == accepted["tick"] == park.tick
    assert paused["accepted_state_revision"] != accepted["accepted_state_revision"]
    captured = reader.revision_snapshot(accepted["accepted_state_revision"])
    assert captured["state"]["weather"]["temperature_c"] == 38.0
    retained_bytes = reader._revision_bytes
    connectors.ingest_demo("weather", [reading])
    latest = reader.snapshot()
    assert latest["accepted_state_revision"] == accepted["accepted_state_revision"]
    assert reader._revision_bytes == retained_bytes
    assert reader.revision_snapshot(latest["accepted_state_revision"]) == captured
    assert next(h for h in latest["connector_health"] if h["source_id"] == "weather")["counters"]["duplicates"] == 1
    assert next(h for h in captured["state"]["connector_health"] if h["source_id"] == "weather")["counters"]["duplicates"] == 0


def test_entry_eviction_is_fifo_and_lookup_does_not_extend_retention(system):
    park, connectors, _, _ = system
    reader = ParkReadModel(park, connectors, revision_capacity=3)
    revisions = []
    for _ in range(3):
        revisions.append(reader.snapshot()["accepted_state_revision"])
        park.advance()
    reader.revision_snapshot(revisions[0])
    newest = reader.snapshot()["accepted_state_revision"]
    with pytest.raises(KeyError):
        reader.revision_snapshot(revisions[0])
    assert len(reader._revisions) == 3
    assert reader.revision_snapshot(revisions[1])["revision"] == revisions[1]
    assert reader.revision_snapshot(newest)["revision"] == newest


def test_byte_budget_and_oversized_snapshot_preserve_existing_window(system):
    park, connectors, probe, _ = system
    state = probe.snapshot()
    sample_bytes = probe._revision_bytes
    reader = ParkReadModel(park, connectors, revision_max_bytes=sample_bytes * 2 + 100)
    revisions = []
    for _ in range(4):
        revisions.append(reader.snapshot()["accepted_state_revision"])
        park.advance()
    assert 1 <= len(reader._revisions) <= 2
    assert reader._revision_bytes <= sample_bytes * 2 + 100
    assert reader._revision_bytes == sum(len(payload) for payload in reader._revisions.values())
    with pytest.raises(KeyError):
        reader.revision_snapshot(revisions[0])
    before = dict(reader._revisions)
    oversized = deepcopy(state)
    oversized["accepted_state_revision"] = "f" * 64
    oversized["large_synthetic_description"] = "a" * (sample_bytes * 3)
    reader._retain_revision(oversized)
    assert dict(reader._revisions) == before
    with pytest.raises(KeyError):
        reader.revision_snapshot("f" * 64)


def test_concurrent_duplicate_captures_have_one_immutable_entry(system):
    _, _, reader, _ = system
    state = reader.snapshot()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: reader._retain_revision(state), range(32)))
    assert len(reader._revisions) == 1
    assert reader._revision_bytes == len(next(iter(reader._revisions.values())))
    assert reader.revision_snapshot(state["accepted_state_revision"])["state"] == state


@pytest.mark.parametrize("limits", [{"revision_capacity": 65}, {"revision_capacity": 0}, {"revision_max_bytes": 4 * 1024 * 1024 + 1}, {"revision_max_bytes": 0}])
def test_retention_cannot_exceed_configured_hard_limits(system, limits):
    park, connectors, _, _ = system
    with pytest.raises(ValueError):
        ParkReadModel(park, connectors, **limits)


def test_http_envelope_validation_missing_and_lookup_has_no_side_effects(tmp_path, monkeypatch):
    with TestClient(create_app(str(tmp_path / "http.db"), run_background=False)) as client:
        current = client.get("/api/state").json()
        revision = current["accepted_state_revision"]
        url = f"/api/state/revisions/{revision}"
        response = client.get(url)
        assert response.status_code == 200
        retained = response.json()
        assert set(retained) == {"revision", "captured_at", "state", "scope"}
        assert retained["revision"] == retained["state"]["accepted_state_revision"] == revision
        assert parse_timestamp(retained["captured_at"]).utcoffset().total_seconds() == 0
        assert client.get(f"/api/state/revisions/{revision.upper()}").json() == retained
        assert client.get("/api/state/revisions/" + "0" * 64).status_code == 404
        for malformed in ("bad", "g" * 64, "a" * 63, "a" * 65):
            assert client.get(f"/api/state/revisions/{malformed}").status_code == 422
        reader = client.app.state.read_model
        before_bytes = reader._revision_bytes
        monkeypatch.setattr(reader, "snapshot", lambda: pytest.fail("retained lookup must not refresh"))
        monkeypatch.setattr(client.app.state.connectors, "refresh", lambda *_: pytest.fail("retained lookup must not poll"))
        client.app.state.park.db.set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
        try:
            assert client.get(url).json() == retained
            assert reader._revision_bytes == before_bytes
        finally:
            client.app.state.park.db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)


def test_http_evicted_revision_is_404_and_latest_remains_current(tmp_path):
    with TestClient(create_app(str(tmp_path / "evict.db"), run_background=False)) as client:
        client.app.state.read_model = ParkReadModel(client.app.state.park, client.app.state.connectors, revision_capacity=1)
        before = client.get("/api/state").json()
        client.app.state.park.advance()
        after = client.get("/api/state").json()
        assert before["accepted_state_revision"] != after["accepted_state_revision"]
        assert client.get(f"/api/state/revisions/{before['accepted_state_revision']}").status_code == 404
        retained = client.get(f"/api/state/revisions/{after['accepted_state_revision']}").json()
        assert retained["state"]["tick"] == after["tick"]
        assert client.get("/api/state").json()["tick"] == after["tick"]
