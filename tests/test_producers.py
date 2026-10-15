"""Pure scenario compatibility and external synthetic publishers at the HTTP boundary."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.domain import SCENARIOS, registry
from backend.model_rules import evaluate
from backend.simulator import ParkSimulator
from simulators.producer import SyntheticProducer, ProducerError, main, publish_batch, require_paused_sources


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "park.db"), run_background=False)) as client:
        yield client


def test_pure_model_matches_persisted_scenarios_without_accessing_db(tmp_path):
    park = ParkSimulator(str(tmp_path / "model.db"))
    try:
        for scenario in SCENARIOS:
            park.set_scenario(scenario["id"])
            park.act("add_staff", "FOOD_COURT")
            park.act("dispatch_maintenance", "RIDE_COASTER")
            snapshot = park.snapshot()
            counts = {asset["id"]: asset["maintenance"]["open_work_orders"] for asset in snapshot["assets"]}
            park.db.set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
            try:
                actual = evaluate(park.base, park.scenario, park.mitigations, snapshot["tick"], snapshot["timestamp"], counts, snapshot["recent_actions"])
                assert actual == snapshot
                assert park.compare("normal")["mutates_live_state"] is False
            finally:
                park.db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
    finally:
        park.close()


def test_pure_model_does_not_mutate_or_expose_input_objects():
    base = {asset["id"]: asset for asset in registry()}
    mitigations = {"staff:FOOD_COURT": 2, "replenish_stock": True}
    counts = {"RIDE_COASTER": 1}
    actions = [{"action": "test"}]
    original = deepcopy((base, mitigations, counts, actions, SCENARIOS))
    result = evaluate(base, "food_rush", mitigations, 17, "2026-10-15T12:00:00+00:00", counts, actions)
    assert (base, mitigations, counts, actions, SCENARIOS) == original
    result["assets"][0]["staff"]["on_duty"] = -100
    result["recent_actions"][0]["action"] = "mutated"
    result["scenarios"][0]["label"] = "mutated"
    result["systems"][0]["asset_ids"].clear()
    assert (base, mitigations, counts, actions, SCENARIOS) == original
    assert evaluate(base, "normal", {}, 17, "time", {}, [])["systems"][0]["asset_ids"]


def test_producer_import_and_sample_without_sqlite_or_gateway():
    script = """
import sys
from simulators.producer import SyntheticProducer
producer = SyntheticProducer(['weather'], 'heatwave')
assert producer.batches(1)['weather']['events'][0]['value'] >= 38
assert 'sqlite3' not in sys.modules
assert 'backend.simulator' not in sys.modules
assert 'backend.app' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("profile", [scenario["id"] for scenario in SCENARIOS])
def test_all_ten_sources_publish_each_profile_through_http(client, profile):
    sources = [item["id"] for item in client.get("/api/connectors").json()["connectors"]]
    for source in sources:
        assert client.post(f"/api/connectors/{source}/simulation", json={"mode": "paused"}).status_code == 200
    require_paused_sources(client, sources)
    producer = SyntheticProducer(sources, profile)
    batches = producer.batches(17)
    assert len(batches) == 10
    for source, batch in batches.items():
        response = publish_batch(client, source, batch)
        assert response["accepted"] == len(batch["events"])
        assert response["rejected"] == response["duplicates"] == 0
        observations = client.get(f"/api/connectors/{source}/snapshot").json()["observations"]
        assert len(observations) == len(batch["events"])
        assert {observation["event_id"] for observation in observations} == {event["event_id"] for event in batch["events"]}
        assert all(observation["provenance"]["synthetic"] for observation in observations)
        assert all(observation["provenance"]["transport"] == "synthetic_http_ingest" for observation in observations)
        assert all(observation["source_id"] == source for observation in observations)
    # Publishing source samples never changes the gateway's scenario/workflows.
    assert client.app.state.park.snapshot()["scenario"] == "normal"


def test_external_source_projection_ownership_and_natural_staleness(client):
    for source in ("vision", "weather"):
        client.post(f"/api/connectors/{source}/simulation", json={"mode": "paused"})
    before = client.get("/api/assets/SHOW_ARENA").json()["occupancy"]
    vision = SyntheticProducer(["vision"], "show_surge").batches(1)["vision"]
    publish_batch(client, "vision", vision)
    assert client.get("/api/assets/SHOW_ARENA").json()["occupancy"] == before
    observations = client.get("/api/observations", params={"source_id": "vision", "asset_id": "SHOW_ARENA"}).json()["observations"]
    assert next(o for o in observations if o["metric"] == "occupancy")["value"] == 560
    weather = SyntheticProducer(["weather"], "heatwave").batches(1)["weather"]
    publish_batch(client, "weather", weather)
    assert client.get("/api/state").json()["weather"]["temperature_c"] >= 38
    last_ingested = client.get("/api/connectors/weather/health").json()["last_ingested_at"]
    client.app.state.connectors.clock = lambda: datetime.now(timezone.utc) + timedelta(seconds=7)
    health = client.get("/api/connectors/weather/health").json()
    assert health["status"] == "stale"
    assert health["last_ingested_at"] == last_ingested
    assert client.get("/api/assets/WEATHER_STATION").json()["data_quality"]["fields"]["temperature_c"]["status"] == "stale"


def test_source_must_be_paused_and_producer_never_changes_mode(client):
    with pytest.raises(ProducerError, match="Pause"):
        require_paused_sources(client, ["weather"])
    assert client.get("/api/connectors/weather/health").json()["mode"] == "live"
    batch = SyntheticProducer(["weather"]).batches(1)["weather"]
    with pytest.raises(ProducerError, match="HTTP 409"):
        publish_batch(client, "weather", batch)
    client.post("/api/connectors/weather/simulation", json={"mode": "paused"})
    require_paused_sources(client, ["weather"])
    client.post("/api/connectors/weather/simulation", json={"mode": "offline"})
    with pytest.raises(ProducerError, match="HTTP 409"):
        publish_batch(client, "weather", batch)


def test_retry_after_lost_response_reuses_accepted_ids(client):
    client.post("/api/connectors/weather/simulation", json={"mode": "paused"})
    producer = SyntheticProducer(["weather"])
    batch = producer.batches(1)["weather"]
    previous = client.get("/api/connectors/weather/health").json()["counters"]["accepted"]

    class LostResponse:
        calls = 0
        def post(self, url, json):
            self.calls += 1
            response = client.post(url, json=json)
            if self.calls == 1:
                assert response.json()["accepted"] == len(batch["events"])
                raise httpx.ReadTimeout("Simulated lost response after commit")
            return response

    transport = LostResponse()
    result = publish_batch(transport, "weather", batch, sleep=lambda _: None)
    assert transport.calls == 2
    assert result["accepted"] == 0 and result["duplicates"] == len(batch["events"])
    assert client.get("/api/connectors/weather/health").json()["counters"]["accepted"] == previous + len(batch["events"])
    other_process = SyntheticProducer(["weather"]).batches(1)["weather"]
    assert {e["event_id"] for e in batch["events"]}.isdisjoint(e["event_id"] for e in other_process["events"])


def test_rejected_batch_is_not_retried(client):
    client.post("/api/connectors/weather/simulation", json={"mode": "paused"})
    batch = SyntheticProducer(["weather"]).batches(1)["weather"]
    batch["events"][0]["unit"] = "wrong"
    with pytest.raises(ProducerError, match="unit_mismatch"):
        publish_batch(client, "weather", batch, sleep=lambda _: pytest.fail("rejection must not retry"))
    assert client.get("/api/connectors/weather/health").json()["counters"]["rejected"] == 1


def test_cli_defaults_to_one_sample_json_without_network(capsys, monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **_: pytest.fail("dry-run must not create an HTTP client"))
    assert main(["--source", "all", "--emit-json"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 10
    assert all(row["synthetic"] is True and row["events"] for row in rows)
    assert main(["--source", "weather"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 1


@pytest.mark.parametrize("args", [["--rate", "nan"], ["--rate", "0"], ["--rate", "inf"], ["--count", "0"], ["--count", "100001"], ["--api-url", "file:///tmp/no"], ["--api-url", "http://user:pass@localhost:8000"], ["--api-url", "http://localhost:bad"]])
def test_cli_rejects_invalid_delivery_limits_and_targets(args):
    with pytest.raises(SystemExit) as exc:
        main(["--source", "weather", *args])
    assert exc.value.code == 2


@pytest.mark.parametrize("failure", ["transport", "server"])
def test_retry_budget_is_bounded(failure):
    class FailingTransport:
        calls = 0
        def post(self, url, json):
            self.calls += 1
            if failure == "transport":
                raise httpx.ConnectError("Synthetic outage")
            return httpx.Response(503)

    transport = FailingTransport()
    sleeps = []
    batch = SyntheticProducer(["weather"]).batches(1)["weather"]
    with pytest.raises(ProducerError, match="after 3 attempts"):
        publish_batch(transport, "weather", batch, sleep=sleeps.append)
    assert transport.calls == 3
    assert sleeps == [.25, .5]
