"""Accepted-state identities distinguish ingestion from simulator time."""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.replay import install_replay
from backend.connectors import ConnectorRuntime, ParkReadModel
from backend.simulator import ParkSimulator
from renderer.frame_cache import FrameCache, response_headers
import backend.replay as replay
import json


def test_revision_ignores_age_but_tracks_quality_transition(tmp_path):
    park = ParkSimulator(str(tmp_path / "park.db"))
    now = [datetime.now(timezone.utc)]
    connectors = ConnectorRuntime(park.base, clock=lambda: now[0])
    reader = ParkReadModel(park, connectors)
    first = reader.snapshot()
    for source in connectors.specs:
        connectors.set_simulation_mode(source, "paused")
    paused = reader.snapshot()
    assert paused["accepted_state_revision"] != first["accepted_state_revision"]
    now[0] += timedelta(seconds=0.05)
    assert (
        reader.snapshot()["accepted_state_revision"]
        == paused["accepted_state_revision"]
    )
    now[0] += timedelta(hours=1)
    assert (
        reader.snapshot()["accepted_state_revision"]
        != paused["accepted_state_revision"]
    )
    park.close()


@pytest.mark.parametrize(
    "matching,frame_age", [(False, 0), (True, 0), (True, 60), (True, -10), (True, None)]
)
def test_replay_pose_requires_accepted_revision_not_only_tick(
    tmp_path, monkeypatch, matching, frame_age
):
    app = create_app(str(tmp_path / "park.db"), run_background=False)
    install_replay(
        app, str(tmp_path / "history.db"), record_background=False, probe_renderer=True
    )
    status = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return status

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return Response()

    monkeypatch.setattr(replay.httpx, "AsyncClient", Client)
    with TestClient(app) as client:
        client.post(
            "/api/connectors/ride_scada/simulation", json={"mode": "paused"}
        ).raise_for_status()
        old = client.get("/api/view/state").json()
        status.update(
            ready=True,
            view_mode="live",
            scene_revision=app.state.replay.scene_revision,
            source_tick=old["tick"],
            accepted_state_revision=old["accepted_state_revision"],
            ride_motion={"coaster_phase": 0.123, "wheel_angle": 0.456},
            frame=1,
            rendered_at=(
                (datetime.now(timezone.utc) - timedelta(seconds=frame_age)).isoformat()
                if frame_age is not None
                else None
            ),
        )
        if matching:
            # Preview the exact accepted state after this injection without advancing time.
            # Renderer fixture acknowledges the current revision when queried.
            async def get(self, url):
                status["accepted_state_revision"] = app.state.read_model.snapshot()[
                    "accepted_state_revision"
                ]
                return Response()

            monkeypatch.setattr(Client, "get", get)
        event = dict(
            event_id="fault-now",
            source_asset_id="ride_scada/RIDE_COASTER",
            metric="status",
            value="fault",
            unit="state",
            source_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        result = client.post(
            "/api/connectors/ride_scada/ingest",
            json={"synthetic": True, "events": [event]},
        )
        assert result.json()["accepted"] == 1
        new = client.get("/api/view/state").json()
        assert new["tick"] == old["tick"]
        assert new["accepted_state_revision"] != old["accepted_state_revision"]
        latest = app.state.replay.get(
            client.get("/api/timeline").json()["snapshots"][-1]["id"]
        )
        expected = matching and frame_age == 0
        assert latest["has_recorded_motion"] is expected
        if expected:
            assert latest["recorded_motion"]["provenance"]["frame"] == 1
            assert (
                latest["recorded_motion"]["provenance"]["rendered_at"]
                == status["rendered_at"]
            )


def test_frame_context_is_immutable_and_travels_with_bytes():
    cache = FrameCache()
    metadata = dict(
        frame=1,
        accepted_state_revision="revision-a",
        camera={"yaw": 0},
        projected_assets=[{"id": "HOTEL", "x": 0.25, "y": 0.3}],
        width=1280,
        height=720,
    )
    cache.publish(b"frame-a", metadata)
    metadata["camera"]["yaw"] = 1
    _, captured = cache.read()
    headers = response_headers(captured, True)
    assert headers["X-Source-Revision"] == "revision-a"
    context = json.loads(headers["X-Frame-Context"])
    assert context["camera"]["yaw"] == 0
    assert context["projected_assets"][0]["x"] == 0.25


def test_versioned_pick_rejects_changed_camera_source_and_view():
    from renderer.frame_cache import camera_token, pick_context_matches

    token = camera_token({"yaw": 0, "radius": 50})
    current = dict(
        camera_token=token,
        accepted_state_revision="a",
        view_mode="live",
        snapshot_id=None,
    )
    request = dict(
        expected_camera_token=token,
        expected_source_revision="a",
        expected_view_mode="live",
        expected_snapshot_id=None,
    )
    assert pick_context_matches(request, current)
    for field, value in (
        ("camera_token", "changed"),
        ("accepted_state_revision", "b"),
        ("view_mode", "replay"),
        ("snapshot_id", 2),
    ):
        assert not pick_context_matches(request, {**current, field: value})
    assert not pick_context_matches({}, current)
