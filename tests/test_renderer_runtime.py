"""CPU invariants for command lifetime and truthful frame publication.

These tests do not claim GPU renderer execution or native resource destruction.
"""

from datetime import datetime, timedelta, timezone
import queue
import pytest
from renderer.commands import CommandMailbox, MailboxClosed
from renderer.frame_cache import FrameCache, response_headers, timestamp_age


def test_cancelled_queued_pick_is_never_delivered_to_native_owner():
    clock = [10.0]
    mailbox = CommandMailbox(clock=lambda: clock[0])
    old = mailbox.submit("pick", {"x": 0.4, "y": 0.5})
    mailbox.cancel(old, "HTTP caller timed out")
    current = mailbox.submit("control", {"action": "home"})
    assert mailbox.take() is current
    assert mailbox.take() is None
    assert old.done.is_set() and old.cancelled
    assert old.result["error"] == "HTTP caller timed out"
    assert mailbox.finish(current)
    assert mailbox.outstanding == 0


def test_expired_inflight_pick_cannot_complete_as_a_valid_selection():
    clock = [10.0]
    mailbox = CommandMailbox(clock=lambda: clock[0])
    command = mailbox.submit("pick", {}, ttl=1)
    assert mailbox.take() is command
    clock[0] = 12.0
    assert not mailbox.active(command)
    assert not mailbox.finish(command, {"asset_id": "HOTEL"})
    assert command.result["cancelled"]
    assert "asset_id" not in command.result


def test_failure_completes_all_pending_callers_and_rejects_new_work():
    mailbox = CommandMailbox()
    inflight = mailbox.submit("pick", {})
    queued = mailbox.submit("control", {"action": "home"})
    assert mailbox.take() is inflight
    mailbox.close("Native initialization failed")
    for command in (inflight, queued):
        assert command.done.is_set() and command.cancelled
        assert command.result["error"] == "Native initialization failed"
    assert mailbox.outstanding == 0 and mailbox.take() is None
    with pytest.raises(MailboxClosed):
        mailbox.submit("pick", {})


def test_mailbox_has_real_backpressure():
    mailbox = CommandMailbox(capacity=1)
    command = mailbox.submit("control", {})
    with pytest.raises(queue.Full):
        mailbox.submit("control", {})
    assert mailbox.outstanding == 1
    mailbox.close()
    assert command.done.is_set()


def test_cached_frame_keeps_original_identity_time_and_records_its_age():
    clock = [100.0]
    cache = FrameCache(clock=lambda: clock[0])
    stamp = "2026-10-15T20:00:00+00:00"
    metadata = {
        "frame": 4,
        "rendered_at": stamp,
        "source_tick": 32,
        "view_mode": "live",
        "source_timestamp": stamp,
        "scene_revision": "scene-a",
        "projected_assets": [{"id": "HOTEL"}],
    }
    cache.publish(b"actual-image-bytes", metadata)
    metadata["projected_assets"].clear()
    clock[0] = 118.0
    image, served = cache.read()
    assert image == b"actual-image-bytes"
    assert served["frame"] == 4 and served["rendered_at"] == stamp
    assert served["frame_age_seconds"] == 18
    assert len(served["projected_assets"]) == 1
    served["projected_assets"].clear()
    assert len(cache.read()[1]["projected_assets"]) == 1
    headers = response_headers(served, ready=False)
    assert headers["X-Frame-Rendered-At"] == stamp
    assert headers["X-Renderer-Ready"] == "false"
    assert headers["X-Frame-Number"] == "4"
    assert headers["X-Source-Tick"] == "32"


def test_frame_data_and_snapshot_provenance_move_together():
    cache = FrameCache()
    cache.publish(b"live", {"frame": 1, "view_mode": "live", "source_tick": 100})
    cache.publish(
        b"historical",
        {"frame": 2, "view_mode": "replay", "snapshot_id": 7, "source_tick": 15},
    )
    image, meta = cache.read()
    assert image == b"historical"
    headers = response_headers(meta, ready=True)
    assert headers["X-View-Mode"] == "replay"
    assert headers["X-View-Snapshot-Id"] == "7"
    assert headers["X-Source-Tick"] == "15"
    with pytest.raises(ValueError):
        cache.publish(b"old", {"frame": 1})


def test_unknown_or_naive_source_time_is_not_treated_as_fresh():
    assert timestamp_age(None) is None
    assert timestamp_age("malformed") is None
    assert timestamp_age("2026-10-15T20:00:00") is None
    old = (datetime.now(timezone.utc) - timedelta(seconds=12)).isoformat()
    assert timestamp_age(old) >= 12


def test_failed_renderer_rejects_controls_instead_of_enqueuing_them(monkeypatch):
    from renderer import service
    from fastapi import HTTPException

    monkeypatch.setitem(service.state, "ready", False)
    with pytest.raises(HTTPException) as failure:
        service.control(service.Control(action="home"))
    assert failure.value.status_code == 503
    assert service.commands.outstanding == 0


def test_initialization_failure_reaches_resource_cleanup_before_diagnostics(
    monkeypatch,
):
    import sys
    from types import SimpleNamespace
    from renderer import service

    calls = []

    class FakeRenderer:
        def __init__(self, config):
            pass

        def attach_ovstage(self, stage):
            calls.append("attach")

        def detach_ovstage(self):
            calls.append("detach")

        def destroy(self):
            calls.append("renderer.destroy")

    class FakeStage:
        def __init__(self, name):
            pass

        def destroy(self):
            calls.append("stage.destroy")

    def fail_population(*args, **kwargs):
        raise ValueError("Invalid scene fixture")

    monkeypatch.setitem(
        sys.modules,
        "ovrtx",
        SimpleNamespace(Renderer=FakeRenderer, RendererConfig=lambda **kw: kw),
    )
    monkeypatch.setitem(
        sys.modules,
        "ovstage",
        SimpleNamespace(
            Stage=FakeStage,
            population=SimpleNamespace(open_usd_from_string=fail_population),
        ),
    )
    mailbox = CommandMailbox()
    request = mailbox.submit("pick", {})
    monkeypatch.setattr(service, "commands", mailbox)
    monkeypatch.setattr(service, "state", dict(service.state))
    service.render_loop()
    assert calls == ["attach", "detach", "stage.destroy", "renderer.destroy"]
    assert service.state["phase"] == "failed" and not service.state["ready"]
    assert service.state["error"] == "Invalid scene fixture"
    assert service.state["cleanup_errors"] == []
    assert request.done.is_set() and request.cancelled


def test_only_the_ride_with_a_current_authoritative_status_advances():
    from renderer.source_state import ride_motion_policy

    assets = {
        "RIDE_COASTER": {
            "status": "operational",
            "data_quality": {"fields": {"status": {"status": "stale"}}},
        },
        "RIDE_WHEEL": {
            "status": "warning",
            "data_quality": {"fields": {"status": {"status": "good"}}},
        },
    }
    result = ride_motion_policy(assets, snapshot_fresh=True)
    assert not result["RIDE_COASTER"]["advance"]
    assert result["RIDE_COASTER"]["reason"] == "status_source_stale"
    assert result["RIDE_WHEEL"]["advance"]
    assert not any(
        rule["advance"] for rule in ride_motion_policy(assets, False).values()
    )
    assert not any(
        rule["advance"]
        for rule in ride_motion_policy(assets, True, replay=True).values()
    )
    assets["RIDE_WHEEL"]["status"] = "closed"
    assert not ride_motion_policy(assets, True)["RIDE_WHEEL"]["advance"]
    assert not any(rule["advance"] for rule in ride_motion_policy({}, True).values())
