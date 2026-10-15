"""HTTP and WebSocket API for the synthetic park twin."""
from __future__ import annotations
import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Path as PathParam, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from project_revision import source_identity
from .simulator import ActionRequestConflict, ParkSimulator
from .connectors import ConnectorRuntime, ParkReadModel
from .connectors.api import install_connector_routes


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    asset_id: str | None = None
    request_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def create_app(database_path: str | None = None, run_background: bool = True):
    @asynccontextmanager
    async def lifespan(app):
        app.state.source_identity = source_identity(Path(__file__).resolve().parents[1])
        app.state.park = ParkSimulator(database_path or os.environ.get("PARK_DB", str(Path(__file__).parent / "data" / "park.db")))
        app.state.connectors = ConnectorRuntime(app.state.park.base)
        app.state.read_model = ParkReadModel(app.state.park, app.state.connectors)
        app.state.read_model.snapshot()
        async def simulate():
            while True:
                await asyncio.sleep(1)
                await asyncio.to_thread(app.state.park.advance)
                await asyncio.to_thread(app.state.read_model.snapshot)
        task = asyncio.create_task(simulate()) if run_background else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            app.state.park.close()

    app = FastAPI(title="Park Twin — Synthetic Services", version="0.1.0", lifespan=lifespan,
                  description="All telemetry, systems, identities and actions in this proof of concept are synthetic.")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "synthetic": True, "database": "connected", "source_identity": app.state.source_identity, "tick": app.state.park.snapshot()["tick"]}

    @app.get("/api/state")
    def state():
        return app.state.read_model.snapshot()

    @app.get("/api/state/revisions/{revision}")
    def state_revision(revision: str = PathParam(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")):
        try:
            return app.state.read_model.revision_snapshot(revision)
        except KeyError:
            raise HTTPException(404, "Canonical state revision is unavailable or no longer retained")

    @app.get("/api/assets")
    def assets():
        return {"synthetic": True, "assets": app.state.read_model.snapshot()["assets"]}

    @app.get("/api/assets/{asset_id}/history")
    def history(asset_id: str, limit: int = Query(120, ge=1, le=3600)):
        try:
            return {"synthetic": True, "asset_id": asset_id, "history": app.state.park.history(asset_id, limit)}
        except KeyError:
            raise HTTPException(404, "Unknown asset")

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str):
        try:
            detail = app.state.park.asset(asset_id)
            projected = next(a for a in app.state.read_model.snapshot()["assets"] if a["id"] == asset_id)
            return {**detail, **projected}
        except KeyError:
            raise HTTPException(404, "Unknown asset")

    @app.get("/api/systems")
    def systems():
        return {"synthetic": True, "systems": app.state.read_model.snapshot()["systems"]}

    @app.get("/api/systems/{system_id}/data")
    def system_data(system_id: str):
        try:
            return app.state.read_model.system_data(system_id)
        except KeyError:
            raise HTTPException(404, "Unknown synthetic system")

    @app.get("/api/audit")
    def audit(limit: int = Query(100, ge=1, le=1000)):
        return {"synthetic": True, "events": app.state.park.audit(limit)}

    @app.get("/api/scenarios/compare")
    def compare_scenario(scenario: str = Query(...)):
        try:
            return app.state.park.compare(scenario)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/scenarios")
    def scenario(request: ScenarioRequest):
        try:
            app.state.park.set_scenario(request.scenario)
            return app.state.read_model.snapshot()
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/actions")
    def action(request: ActionRequest):
        try:
            result = app.state.park.act(request.action, request.asset_id, request.request_id)
            result["state"] = app.state.read_model.snapshot()
            return result
        except ActionRequestConflict as exc:
            raise HTTPException(409, {"code": "request_id_conflict", "message": str(exc)})
        except KeyError:
            raise HTTPException(404, "Unknown asset")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.websocket("/ws/state")
    async def websocket(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(app.state.read_model.snapshot())
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            pass

    install_connector_routes(app)
    return app


app = create_app()
