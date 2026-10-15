"""HTTP/lifespan adapter for recorded park inspection; live state stays separate."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
import hashlib
import math
import os
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .replay_store import ReplayStore

ROOT = Path(__file__).resolve().parents[1]


class ViewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["live", "replay"]
    snapshot_id: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def require_cursor(self):
        if self.mode == "replay" and self.snapshot_id is None:
            raise ValueError("Replay requires a recorded snapshot ID")
        if self.mode == "live" and self.snapshot_id is not None:
            raise ValueError("Live view does not accept a snapshot ID")
        return self


def current_revisions() -> tuple[str, str]:
    scene = hashlib.sha256((ROOT / "assets/park.usdc").read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for path in sorted((ROOT / "backend").rglob("*.py")):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    digest.update((ROOT / "assets/asset_registry.json").read_bytes())
    return scene, digest.hexdigest()


def _live_state(app):
    reader = getattr(app.state, "read_model", app.state.park)
    return reader.snapshot()


def install_replay(
    app,
    database_path: str | None = None,
    interval: float = 2.0,
    retention_limit: int = 7200,
    record_background: bool = True,
    probe_renderer: bool = True,
):
    """Install once before serving; wrap the existing application lifespan."""
    if getattr(app.state, "replay_installed", False):
        raise ValueError("Replay has already been installed")
    app.state.replay_installed = True
    previous_lifespan = app.router.lifespan_context

    async def capture():
        snapshot = _live_state(app)
        orders = None
        workflows = getattr(app.state.park, "workflow_snapshot", None)
        if workflows:
            workflow = workflows()
            if workflow["tick"] == snapshot["tick"]:
                orders = workflow["work_orders"]
        motion = None
        if probe_renderer:
            try:
                async with httpx.AsyncClient(timeout=0.35, trust_env=False) as client:
                    response = await client.get("http://127.0.0.1:8091/status")
                    response.raise_for_status()
                    render = response.json()
                candidate = render.get("ride_motion", {})
                if (
                    render.get("ready")
                    and render.get("view_mode", "live") == "live"
                    and render.get("scene_revision") == app.state.replay.scene_revision
                    and render.get("source_tick") == snapshot["tick"]
                    and bool(snapshot.get("accepted_state_revision"))
                    and render.get("accepted_state_revision") == snapshot["accepted_state_revision"]
                    and all(
                        isinstance(candidate.get(k), (int, float))
                        and math.isfinite(candidate[k])
                        for k in ("coaster_phase", "wheel_angle")
                    )
                ):
                    motion = {
                        key: float(candidate[key])
                        for key in ("coaster_phase", "wheel_angle")
                    }
            except (httpx.HTTPError, ValueError, TypeError):
                pass  # Data recording works even with no GPU; no pose is invented.
        return app.state.replay.capture(snapshot, motion, orders)

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            scene, config = current_revisions()
            path = database_path or os.environ.get(
                "PARK_REPLAY_DB", str(ROOT / "backend/data/replay.db")
            )
            application.state.replay = ReplayStore(path, scene, config, retention_limit)
            application.state.capture_replay = capture
            application.state.replay_recording_error = None
            application.state.view_write_lock = asyncio.Lock()
            await capture()

            async def recorder():
                while True:
                    await asyncio.sleep(interval)
                    try:
                        await capture()
                        application.state.replay_recording_error = None
                    except Exception as error:
                        application.state.replay_recording_error = str(error)

            task = asyncio.create_task(recorder()) if record_background else None
            try:
                yield
            finally:
                if task:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                application.state.replay.close()

    app.router.lifespan_context = lifespan

    @app.middleware("http")
    async def protect_recorded_view(request: Request, call_next):
        store = getattr(app.state, "replay", None)
        mutating = request.method in {"POST", "PUT", "PATCH", "DELETE"} and (
            request.url.path in {"/api/actions", "/api/scenarios"}
            or request.url.path.startswith("/api/connectors/")
        )
        comparing = (
            request.method == "GET" and request.url.path == "/api/scenarios/compare"
        )

        async def dispatch():
            if store and store.is_replay and (mutating or comparing):
                return JSONResponse(
                    {
                        "detail": "Recorded view is read-only. Return to live before changing the park or comparing scenarios."
                    },
                    status_code=409,
                )
            response = await call_next(request)
            if store and mutating and response.status_code < 400:
                try:
                    await capture()
                except Exception as error:
                    app.state.replay_recording_error = str(error)
            return response

        changing_view = request.method == "POST" and request.url.path == "/api/view"
        if store and (mutating or comparing or changing_view):
            async with app.state.view_write_lock:
                return await dispatch()
        return await dispatch()

    @app.get("/api/timeline")
    async def timeline(limit: int = Query(300, ge=1, le=2000)):
        store = app.state.replay
        return {
            "snapshots": store.timeline(limit),
            "view": store.cursor(),
            "retention_limit": store.retention_limit,
            "recording_interval_seconds": interval,
            "shared_session": True,
            "recording_error": app.state.replay_recording_error,
        }

    @app.get("/api/view/state")
    async def view_state():
        return app.state.replay.view_state(_live_state(app))

    @app.post("/api/view")
    async def change_view(data: ViewRequest):
        try:
            app.state.replay.select(data.snapshot_id if data.mode == "replay" else None)
        except KeyError:
            raise HTTPException(
                404, "Recorded snapshot is unavailable or outside retention"
            )
        return app.state.replay.view_state(_live_state(app))

    @app.get("/api/view/assets/{asset_id}/history")
    async def asset_history(asset_id: str, limit: int = Query(90, ge=1, le=1000)):
        display = app.state.replay.view_state(_live_state(app))
        if not any(a["id"] == asset_id for a in display["assets"]):
            raise HTTPException(404, "Unknown asset")
        return {
            "synthetic": True,
            "asset_id": asset_id,
            "history": app.state.replay.history(asset_id, limit),
            "view": display["view"],
        }

    @app.get("/api/view/assets/{asset_id}")
    async def asset(asset_id: str):
        display = app.state.replay.view_state(_live_state(app))
        selected = next((a for a in display["assets"] if a["id"] == asset_id), None)
        if selected is None:
            raise HTTPException(404, "Unknown asset")
        if display["view"]["mode"] == "live":
            detail = app.state.park.asset(asset_id)
            selected = {**detail, **selected}
        else:
            selected = {
                **selected,
                "work_orders": selected.get("work_orders", []),
                "audit": [
                    a
                    for a in display.get("recent_actions", [])
                    if a.get("asset_id") == asset_id
                ],
            }
        return {**selected, "view": display["view"]}
