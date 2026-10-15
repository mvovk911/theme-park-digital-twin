"""HTTP compatibility and command validation for the connector boundary."""
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "park.db"), run_background=False)) as client:
        yield client


def test_catalog_health_observations_and_legacy_contract(client):
    catalog = client.get("/api/connectors").json()
    assert len(catalog["connectors"]) == 10
    assert len(client.get("/api/connectors/health").json()["health"]) == 10
    for connector in catalog["connectors"]:
        source_id = connector["id"]
        assert client.get(f"/api/connectors/{source_id}").json()["mappings"]
        snapshot = client.get(f"/api/connectors/{source_id}/snapshot").json()
        assert snapshot["observations"] and snapshot["cursor"]
        assert client.get(f"/api/connectors/{source_id}/health").json()["last_ingested_at"]
        assert client.get(f"/api/systems/{source_id}/data").json()["records"]
    observations = client.get("/api/observations?source_id=water&asset_id=WATER_PLANT&limit=1").json()
    assert len(observations["observations"]) == 1
    assert observations["truncated"]
    assert observations["observations"][0]["asset_id"] == "WATER_PLANT"
    assert client.get("/api/observations?source_id=unknown").status_code == 404
    assert client.get("/api/observations?asset_id=unknown").status_code == 404
    assert client.get("/api/observations?limit=0").status_code == 422


def test_paused_demo_ingestion_validation_projection_and_dedup(client):
    event = {"event_id": "operator-demo", "source_asset_id": "water/WATER_PLANT", "metric": "water_lpm",
             "value": 312.0, "unit": "L/min", "source_timestamp": datetime.now(timezone.utc).isoformat()}
    body = {"synthetic": True, "events": [event]}
    assert client.post("/api/connectors/water/ingest", json=body).status_code == 409
    assert client.post("/api/connectors/water/simulation", json={"mode": "paused"}).json()["mode"] == "paused"
    first = client.post("/api/connectors/water/ingest", json=body).json()
    assert first["accepted"] == 1 and first["rejected"] == 0
    asset = client.get("/api/assets/WATER_PLANT").json()
    assert asset["water_lpm"] == 312.0
    assert asset["data_quality"]["fields"]["water_lpm"]["source_id"] == "water"
    assert client.post("/api/connectors/water/ingest", json=body).json()["duplicates"] == 1
    bad = {"synthetic": True, "events": [{**event, "event_id": "bad", "unit": "wrong"}]}
    rejected = client.post("/api/connectors/water/ingest", json=bad).json()
    assert rejected["rejected"] == 1
    assert rejected["errors"][0]["code"] == "unit_mismatch"
    assert client.post("/api/connectors/water/ingest", json={"synthetic": False, "events": [event]}).status_code == 422
    assert client.post("/api/connectors/water/ingest", json={"synthetic": True, "events": []}).status_code == 422
    assert client.post("/api/connectors/unknown/ingest", json=body).status_code == 404
    assert client.post("/api/connectors/water/simulation", json={"mode": "invalid"}).status_code == 422


def test_stale_and_offline_provenance_in_full_snapshot(client):
    initial = client.get("/api/connectors/weather/health").json()
    client.post("/api/connectors/weather/simulation", json={"mode": "paused"})
    future = datetime.now(timezone.utc) + timedelta(seconds=7)
    client.app.state.connectors.clock = lambda: future
    assert client.get("/api/connectors/weather/health").json()["status"] == "stale"
    client.post("/api/connectors/weather/simulation", json={"mode": "offline"})
    state = client.get("/api/state").json()
    system = next(s for s in state["systems"] if s["id"] == "weather")
    assert system["status"] == "offline"
    assert system["last_sync"] == initial["last_ingested_at"]
    station = next(a for a in state["assets"] if a["id"] == "WEATHER_STATION")
    quality = station["data_quality"]["fields"]["temperature_c"]
    assert quality["status"] == "stale"
    assert "source_offline" in quality["reasons"]
    assert state["read_model"]["quality_status"] == "degraded"


def test_event_poll_cursor_and_errors(client):
    first = client.get("/api/connectors/weather/events?limit=1").json()
    assert len(first["events"]) == 1
    cursor = first["next_cursor"]
    assert client.get("/api/connectors/weather/events", params={"after": cursor}).json()["events"] == []
    assert client.get("/api/connectors/weather/events?after=bad").status_code == 422
    expired = client.get("/api/connectors/weather/events?after=old:0")
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "cursor_expired"
    assert client.get("/api/connectors/weather/events?limit=1001").status_code == 422
    assert client.get("/api/connectors/unknown/events").status_code == 404
