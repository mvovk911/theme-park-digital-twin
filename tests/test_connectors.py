"""Connector boundary contracts independent of network access or worker threads."""
from dataclasses import replace
from datetime import timedelta
import copy
import pytest
from backend.simulator import ParkSimulator
from backend.connectors import ConnectorRuntime, ParkReadModel
from backend.connectors.adapters import SourceBatch
from backend.connectors.catalog import default_catalog, validate_catalog
from backend.connectors.validation import EventError, parse_timestamp


@pytest.fixture
def system(tmp_path):
    park = ParkSimulator(str(tmp_path / "park.db"))
    moment = [parse_timestamp(park.snapshot()["timestamp"])]
    connectors = ConnectorRuntime(park.base, clock=lambda: moment[0])
    read_model = ParkReadModel(park, connectors)
    read_model.snapshot()
    yield park, connectors, read_model, moment
    park.close()


def event(connectors, source="water", value=123.0, metric="water_lpm", asset="WATER_PLANT", event_id="manual-1", timestamp=None):
    mapping = connectors.mapping_indexes[source][(f"{source}/{asset}", metric)]
    return {"event_id": event_id, "source_asset_id": mapping.source_asset_id, "metric": metric,
            "value": value, "unit": mapping.unit,
            "source_timestamp": timestamp or connectors.clock().isoformat()}


def test_all_ten_adapters_have_valid_accepted_observations(system):
    park, connectors, read_model, _ = system
    catalog = connectors.catalog()["connectors"]
    assert {item["id"] for item in catalog} == {"ride_scada", "ticketing", "vision", "cmms", "erp", "workforce", "bms", "water", "weather", "gis"}
    assert len(connectors.observations()["observations"]) == sum(len(item["mappings"]) for item in catalog)
    for item in catalog:
        assert item["synthetic"]
        assert item["transport"] == "in_process_simulation"
        assert item["health"]["status"] == "healthy"
        assert item["health"]["counters"]["rejected"] == 0
        assert item["capabilities"]["physical_control"] is False
        assert item["capabilities"]["snapshot"] and item["capabilities"]["event_poll"]
    for observation in connectors.observations()["observations"]:
        assert observation["asset_id"] in park.base
        assert observation["unit"]
        assert observation["source_timestamp"]
        assert observation["ingested_at"]
        assert observation["quality"]["status"] == "good"
        assert observation["provenance"]["synthetic"]
        assert observation["authoritative"] in (True, False)
    state = read_model.snapshot()
    assert all("planned" in source["protocol"] and "emulator" not in source["protocol"] for source in state["systems"])
    assert state["kpis"]["queue_asset_count"] > 2  # Includes food, admission and facilities.


def test_mapping_catalog_rejects_unknown_assets_and_conflicting_owners(system):
    park, _, _, _ = system
    specs = default_catalog()
    bad_mapping = replace(specs[0].mappings[0], asset_id="UNKNOWN")
    with pytest.raises(ValueError, match="Unknown asset"):
        validate_catalog([replace(specs[0], mappings=(bad_mapping,))], set(park.base))
    with pytest.raises(ValueError, match="Duplicate connector"):
        validate_catalog([specs[0], specs[0]], set(park.base))
    conflicting = replace(specs[0], id="another", mappings=(specs[0].mappings[0],))
    with pytest.raises(ValueError, match="Multiple authoritative"):
        validate_catalog([specs[0], conflicting], set(park.base))


@pytest.mark.parametrize("change,code", [
    ({"unit": "gallons/min"}, "unit_mismatch"),
    ({"value": "123"}, "invalid_type"),
    ({"value": True}, "invalid_type"),
    ({"value": float("nan")}, "invalid_type"),
    ({"value": float("inf")}, "invalid_type"),
    ({"value": 10 ** 400}, "invalid_type"),
    ({"value": -1}, "out_of_range"),
    ({"source_asset_id": "water/UNKNOWN"}, "unknown_mapping"),
    ({"metric": "password"}, "unknown_mapping"),
    ({"source_timestamp": "2026-10-15 10:00:00"}, "invalid_timestamp"),
    ({"source_timestamp": "invalid"}, "invalid_timestamp"),
    ({"extra": 123}, "invalid_event_shape"),
    ({"event_id": ""}, "invalid_event_id"),
])
def test_rejected_events_do_not_change_latest_values(system, change, code):
    _, connectors, _, _ = system
    connectors.set_simulation_mode("water", "paused")
    before = copy.deepcopy(connectors.stores["water"].latest)
    bad = {**event(connectors), **change}
    result = connectors.ingest_demo("water", [bad])
    assert result["accepted"] == 0
    assert result["rejected"] == 1
    assert result["errors"][0]["code"] == code
    assert connectors.stores["water"].latest == before
    assert connectors.health("water")["status"] == "degraded"


def test_future_timestamp_and_unknown_dependency_are_rejected(system):
    _, connectors, _, moment = system
    connectors.set_simulation_mode("water", "paused")
    future = event(connectors, timestamp=(moment[0] + timedelta(seconds=6)).isoformat())
    assert connectors.ingest_demo("water", [future])["errors"][0]["code"] == "future_timestamp"
    connectors.set_simulation_mode("gis", "paused")
    unknown = event(connectors, "gis", ["UNKNOWN"], "dependencies", "WATER_PLANT")
    assert connectors.ingest_demo("gis", [unknown])["errors"][0]["code"] == "unknown_dependency"


def test_accepted_ingestion_updates_projection_and_keeps_simulator_separate(system):
    park, connectors, read_model, moment = system
    before = park.snapshot()
    connectors.set_simulation_mode("water", "paused")
    moment[0] += timedelta(seconds=1)
    result = connectors.ingest_demo("water", [event(connectors, value=321.5)])
    assert result["accepted"] == 1
    state = read_model.snapshot()
    asset = next(a for a in state["assets"] if a["id"] == "WATER_PLANT")
    assert asset["water_lpm"] == 321.5
    assert asset["data_quality"]["fields"]["water_lpm"]["source_id"] == "water"
    assert asset["data_quality"]["fields"]["water_lpm"]["unit"] == "L/min"
    assert park.snapshot() == before


def test_duplicate_conflict_and_out_of_order_semantics(system):
    _, connectors, _, moment = system
    connectors.set_simulation_mode("water", "paused")
    moment[0] += timedelta(seconds=2)
    first = event(connectors, value=111.0)
    assert connectors.ingest_demo("water", [first])["accepted"] == 1
    count = len(connectors.stores["water"].events)
    assert connectors.ingest_demo("water", [first])["duplicates"] == 1
    assert len(connectors.stores["water"].events) == count
    conflict = {**first, "value": 222.0}
    assert connectors.ingest_demo("water", [conflict])["errors"][0]["code"] == "duplicate_event_conflict"
    late = event(connectors, event_id="late", timestamp=(moment[0] - timedelta(seconds=1)).isoformat())
    assert connectors.ingest_demo("water", [late])["errors"][0]["code"] == "out_of_order"
    # Equal source timestamps with distinct event IDs are accepted in ingest order.
    same_time = event(connectors, value=333.0, event_id="same-time")
    assert connectors.ingest_demo("water", [same_time])["accepted"] == 1
    assert connectors.stores["water"].latest[("water/WATER_PLANT", "water_lpm")]["value"] == 333.0


def test_pause_stale_offline_resume_health_uses_accepted_timestamp(system):
    park, connectors, read_model, moment = system
    initial = connectors.health("weather")
    connectors.set_simulation_mode("weather", "paused")
    assert connectors.health("weather")["status"] == "paused"
    moment[0] += timedelta(seconds=6)
    stale = connectors.health("weather")
    assert stale["status"] == "stale"
    assert stale["last_ingested_at"] == initial["last_ingested_at"]
    read_model.snapshot()
    assert connectors.health("weather")["last_ingested_at"] == initial["last_ingested_at"]
    connectors.set_simulation_mode("weather", "offline")
    assert connectors.health("weather")["status"] == "offline"
    assert connectors.observations("weather")["observations"][0]["quality"]["reasons"] == ["source_timestamp_stale", "source_offline"]
    connectors.set_simulation_mode("weather", "live")
    context = park.snapshot()
    context.update(tick=context["tick"] + 1, timestamp=moment[0].isoformat())
    connectors.refresh(context)
    assert connectors.health("weather")["status"] == "healthy"
    assert connectors.health("weather")["last_ingested_at"] != initial["last_ingested_at"]


def test_cursor_poll_and_bounded_retention(system):
    park, _, _, moment = system
    connectors = ConnectorRuntime(park.base, clock=lambda: moment[0], capacity=3)
    connectors.refresh(park.snapshot())
    initial = connectors.events("weather", limit=1)
    cursor = initial["next_cursor"]
    assert len(initial["events"]) == 1
    assert not connectors.events("weather", cursor)["events"]
    for index in range(2, 6):
        moment[0] += timedelta(seconds=1)
        context = park.snapshot()
        context.update(tick=index, timestamp=moment[0].isoformat())
        connectors.refresh(context)
    assert len(connectors.stores["weather"].events) == 3
    assert len(connectors.stores["weather"].dedup) <= 6
    with pytest.raises(EventError) as exc:
        connectors.events("weather", cursor)
    assert exc.value.code == "cursor_expired"
    page = connectors.events("weather", limit=2)
    assert len(page["events"]) == 2 and page["has_more"]
    assert len(connectors.events("weather", page["next_cursor"])["events"]) == 1
    with pytest.raises(EventError) as exc:
        connectors.events("weather", "old-epoch:1")
    assert exc.value.code == "cursor_expired"


def test_replacement_adapter_uses_same_contract_and_read_model(system):
    park, _, _, moment = system
    class ReplacementWeather:
        adapter_id = "example.weather.v1"
        transport = "fixture_transport"
        synthetic = False
        def snapshot(self, context):
            return SourceBatch([{"event_id": "replacement-1", "source_asset_id": "weather/WEATHER_STATION",
                                 "metric": "temperature_c", "value": 31.0, "unit": "Cel",
                                 "source_timestamp": moment[0].isoformat()}], "replacement-1")
        def poll(self, after, context):
            return SourceBatch([], after) if after else self.snapshot(context)
    connectors = ConnectorRuntime(park.base, adapters={"weather": ReplacementWeather()}, clock=lambda: moment[0])
    state = ParkReadModel(park, connectors).snapshot()
    station = next(a for a in state["assets"] if a["id"] == "WEATHER_STATION")
    assert station["temperature_c"] == 31.0
    assert station["data_quality"]["fields"]["temperature_c"]["synthetic"] is False
    with pytest.raises(EventError) as exc:
        connectors.set_simulation_mode("weather", "offline")
    assert exc.value.code == "not_synthetic"
    with pytest.raises(EventError):
        connectors.ingest_demo("weather", [])


def test_poll_failure_is_isolated_and_does_not_expose_exception_text(system):
    park, connectors, _, _ = system
    class FailedAdapter:
        adapter_id = "synthetic.failure.v1"
        synthetic = True
        transport = "in_process_simulation"
        def poll(self, after, context):
            raise RuntimeError("credential=must-not-appear")
    connectors.adapters["water"] = FailedAdapter()
    connectors.refresh(park.snapshot())
    health = connectors.health("water")
    assert health["status"] == "error"
    assert "must-not-appear" not in str(health)
    assert connectors.health("weather")["status"] == "healthy"
    observation = connectors.observations("water")["observations"][0]
    assert observation["quality"]["status"] == "uncertain"
    assert observation["value"] is not None  # Last accepted value retained, labeled uncertain.


def test_legacy_records_retained_with_observation_provenance(system):
    _, connectors, read_model, _ = system
    for source_id in connectors.specs:
        result = read_model.system_data(source_id)
        assert result["records"] and result["observations"]
        assert result["timestamp"] == result["system"]["health"]["last_ingested_at"]
    assert "erp" in read_model.system_data("erp")["records"][0]


def test_informational_source_value_does_not_override_canonical_owner(system):
    _, connectors, read_model, moment = system
    baseline = read_model.snapshot()
    entry_before = next(a for a in baseline["assets"] if a["id"] == "ENTRY_GATE")
    connectors.set_simulation_mode("vision", "paused")
    moment[0] += timedelta(seconds=1)
    injected = event(connectors, "vision", 999, "occupancy", "ENTRY_GATE")
    assert connectors.ingest_demo("vision", [injected])["accepted"] == 1
    canonical = next(a for a in read_model.snapshot()["assets"] if a["id"] == "ENTRY_GATE")
    assert canonical["occupancy"] == entry_before["occupancy"]  # Ticketing owns this field.
    source = next(a for a in read_model.system_data("vision")["records"] if a["asset_id"] == "ENTRY_GATE")
    assert source["occupancy"] == 999  # Raw source payload remains inspectable.


def test_timestamp_order_preserves_microsecond_precision(system):
    _, connectors, _, moment = system
    connectors.set_simulation_mode("water", "paused")
    moment[0] += timedelta(seconds=1)
    accepted_time = moment[0] + timedelta(microseconds=200)
    first = event(connectors, timestamp=accepted_time.isoformat())
    assert connectors.ingest_demo("water", [first])["accepted"] == 1
    earlier = event(connectors, event_id="slightly-earlier", timestamp=(accepted_time - timedelta(microseconds=1)).isoformat())
    assert connectors.ingest_demo("water", [earlier])["errors"][0]["code"] == "out_of_order"


def test_old_simulator_context_does_not_rewind_or_degrade_sources(system):
    park, connectors, _, moment = system
    old = park.snapshot()
    new = copy.deepcopy(old)
    moment[0] += timedelta(seconds=1)
    new.update(tick=old["tick"] + 1, timestamp=moment[0].isoformat())
    connectors.refresh(new)
    latest = connectors.stores["weather"].latest.copy()
    connectors.refresh(old)
    assert connectors.stores["weather"].latest == latest
    assert connectors.health("weather")["status"] == "healthy"


def test_workflow_snapshot_is_bounded_and_matches_tick(system):
    park, _, _, _ = system
    park.act("dispatch_maintenance", "RIDE_COASTER")
    snapshot = park.workflow_snapshot()
    assert snapshot["tick"] == park.snapshot()["tick"]
    assert snapshot["work_orders"][0]["asset_id"] == "RIDE_COASTER"
    assert "history" not in snapshot
    park.db.executemany("INSERT INTO work_orders(asset_id,status,created_at,title) VALUES ('WATER_PLANT','completed',?,'fixture')",
                       [(park.snapshot()["timestamp"],)] * 301)
    park.db.commit()
    assert len(park.workflow_snapshot()["work_orders"]) == 300


def test_injected_ride_fault_is_not_open_or_in_active_queue_average(system):
    _, connectors, read_model, moment = system
    baseline = read_model.snapshot()
    assert baseline["kpis"]["open_rides"] == 2
    connectors.set_simulation_mode("ride_scada", "paused")
    moment[0] += timedelta(seconds=1)
    fault = event(connectors, "ride_scada", "fault", "status", "RIDE_COASTER")
    assert connectors.ingest_demo("ride_scada", [fault])["accepted"] == 1
    state = read_model.snapshot()
    coaster = next(a for a in state["assets"] if a["id"] == "RIDE_COASTER")
    assert coaster["status"] == "fault"
    assert coaster["queue_minutes"] > 0  # Ticketing retains its own last observation.
    assert state["kpis"]["open_rides"] == 1
    assert state["kpis"]["queue_asset_count"] == baseline["kpis"]["queue_asset_count"] - 1
    active = [a for a in state["assets"] if a["queue_minutes"] > 0 and a["status"] not in {"closed", "fault"}]
    assert state["kpis"]["average_wait_minutes"] == round(sum(a["queue_minutes"] for a in active) / len(active), 1)
    warning = event(connectors, "ride_scada", "warning", "status", "RIDE_COASTER", event_id="warning-2")
    assert connectors.ingest_demo("ride_scada", [warning])["accepted"] == 1
    assert read_model.snapshot()["kpis"]["open_rides"] == 2


def test_canonical_ride_fault_alert_and_model_source_conflict(system):
    _, connectors, read_model, moment = system
    connectors.set_simulation_mode("ride_scada", "paused")
    moment[0] += timedelta(seconds=1)
    assert connectors.ingest_demo("ride_scada", [event(connectors, "ride_scada", "fault", "status", "RIDE_COASTER")])["accepted"] == 1
    state = read_model.snapshot()
    unavailable = next(a for a in state["alerts"] if a["id"] == "ride_unavailable")
    assert unavailable["origin"] == "canonical_rule"
    assert unavailable["evidence"][0]["origin"] == "accepted_observation"
    assert unavailable["evidence"][0]["source_id"] == "ride_scada"
    assert unavailable["evidence"][0]["value"] == "fault"
    assert state["kpis"]["open_rides"] == 1
    assert state["source_conflicts"][0]["model_value"] == "operational"
    assert state["kpis"]["active_alerts"] == len(state["alerts"])


def test_paused_operational_scada_does_not_claim_model_closure_is_observed(system):
    park, connectors, read_model, moment = system
    connectors.set_simulation_mode("ride_scada", "paused")
    park.set_scenario("power_fault")
    moment[0] = parse_timestamp(park.snapshot()["timestamp"])
    state = read_model.snapshot()
    coaster = next(a for a in state["assets"] if a["id"] == "RIDE_COASTER")
    assert coaster["status"] == "operational"
    assert state["kpis"]["open_rides"] == 2
    assert not any(a["id"] == "ride_unavailable" for a in state["alerts"])
    conflict = next(a for a in state["alerts"] if a["id"] == "source_conflict_RIDE_COASTER_status")
    assert conflict["origin"] == "model_source_conflict"
    assert {e["origin"] for e in conflict["evidence"]} == {"synthetic_model", "accepted_observation"}
    assert any(a["id"] == "ride_unavailable" and a["origin"] == "synthetic_model" for a in state["model_alerts"])
    feeder = next(a for a in state["alerts"] if a["id"] == "feeder_fault")
    assert feeder["evidence"][0]["source_id"] == "bms"
    assert state["kpis"]["active_alerts"] == len(state["alerts"])


def test_stock_and_water_alerts_follow_injected_canonical_values(system):
    _, connectors, read_model, moment = system
    moment[0] += timedelta(seconds=1)
    connectors.set_simulation_mode("erp", "paused")
    assert connectors.ingest_demo("erp", [event(connectors, "erp", 5, "erp.stock_units", "FOOD_COURT")])["accepted"] == 1
    connectors.set_simulation_mode("water", "paused")
    assert connectors.ingest_demo("water", [event(connectors, value=500.0)])["accepted"] == 1
    state = read_model.snapshot()
    assert state["scenario"] == "normal"
    stock = next(a for a in state["alerts"] if a["id"] == "food_stock")
    water = next(a for a in state["alerts"] if a["id"] == "water_leak")
    assert stock["evidence"][0]["source_id"] == "erp"
    assert water["evidence"][0]["source_id"] == "water"
    assert water["severity"] == "warning"  # High flow alone is not a confirmed leak.


def test_model_crowd_alert_is_labeled_and_checked_against_canonical_occupancy(system):
    park, connectors, read_model, moment = system
    park.set_scenario("show_surge")
    moment[0] = parse_timestamp(park.snapshot()["timestamp"])
    state = read_model.snapshot()
    crowd = next(a for a in state["alerts"] if a["id"] == "crowd_surge")
    assert crowd["origin"] == "synthetic_model"
    assert any(e["origin"] == "synthetic_model" for e in crowd["evidence"])
    connectors.set_simulation_mode("ticketing", "paused")
    moment[0] += timedelta(seconds=1)
    assert connectors.ingest_demo("ticketing", [event(connectors, "ticketing", 10, "occupancy", "SHOW_ARENA")])["accepted"] == 1
    assert not any(a["id"] == "crowd_surge" for a in read_model.snapshot()["alerts"])


def test_source_snapshot_cursor_cannot_skip_concurrent_acceptance(system, monkeypatch):
    import threading
    _, connectors, _, moment = system
    connectors.set_simulation_mode("weather", "paused")
    moment[0] += timedelta(seconds=1)
    old = connectors.source_snapshot("weather")
    copied, attempted, finished = threading.Event(), threading.Event(), threading.Event()
    original = connectors.observations
    def intercepted(*args, **kwargs):
        result = original(*args, **kwargs)
        copied.set()
        assert attempted.wait(2)
        assert not finished.wait(.03), "Writer escaped the source snapshot lock"
        return result
    monkeypatch.setattr(connectors, "observations", intercepted)
    def writer():
        assert copied.wait(2)
        attempted.set()
        connectors.ingest_demo("weather", [event(connectors, "weather", 31.0, "temperature_c", "WEATHER_STATION")])
        finished.set()
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        snapshot = connectors.source_snapshot("weather")
    finally:
        thread.join(2)
    assert not thread.is_alive()
    assert snapshot["cursor"] == old["cursor"]
    assert snapshot["observations"][0]["value"] == old["observations"][0]["value"]
    following = connectors.events("weather", snapshot["cursor"])
    assert len(following["events"]) == 1
    assert following["events"][0]["value"] == 31.0


def test_late_valid_events_retained_without_advancing_accepted_cursor(system):
    _, connectors, _, moment = system
    connectors.set_simulation_mode("weather", "paused")
    moment[0] += timedelta(seconds=2)
    newest = event(connectors, "weather", 30.0, "temperature_c", "WEATHER_STATION")
    accepted = connectors.ingest_demo("weather", [newest])
    late = event(connectors, "weather", 20.0, "temperature_c", "WEATHER_STATION", "late-valid",
                 (moment[0] - timedelta(seconds=1)).isoformat())
    result = connectors.ingest_demo("weather", [late])
    assert result["rejected"] == 1 and result["errors"][0]["code"] == "out_of_order"
    assert result["latest_cursor"] == accepted["latest_cursor"]
    assert result["latest_decision_cursor"] != accepted["latest_decision_cursor"]
    assert connectors.events("weather", accepted["latest_cursor"])["events"] == []
    decisions = connectors.decisions("weather", accepted["latest_decision_cursor"])["decisions"]
    assert len(decisions) == 1
    assert decisions[0]["applied"] is False and decisions[0]["reason"] == "out_of_order"
    assert decisions[0]["observation"]["value"] == 20.0
    assert decisions[0]["observation"]["sequence"] is None
    assert connectors.source_snapshot("weather")["observations"][0]["value"] == 30.0
    with pytest.raises(EventError) as exc:
        connectors.decisions("weather", accepted["latest_cursor"])
    assert exc.value.code == "invalid_cursor"


def test_decision_retention_is_bounded_and_independent_of_accepted_events(system):
    park, _, _, moment = system
    connectors = ConnectorRuntime(park.base, clock=lambda: moment[0], capacity=3)
    connectors.refresh(park.snapshot())
    connectors.set_simulation_mode("weather", "paused")
    moment[0] += timedelta(seconds=1)
    reading = event(connectors, "weather", 30.0, "temperature_c", "WEATHER_STATION")
    accepted = connectors.ingest_demo("weather", [reading])
    for _ in range(4):
        connectors.ingest_demo("weather", [reading])
    assert len(connectors.stores["weather"].decisions) == 3
    assert len(connectors.stores["weather"].events) == 2
    assert connectors.events("weather", accepted["latest_cursor"])["events"] == []
    with pytest.raises(EventError) as exc:
        connectors.decisions("weather", accepted["latest_decision_cursor"])
    assert exc.value.code == "cursor_expired"
