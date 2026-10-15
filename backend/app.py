"""HTTP and WebSocket API for the synthetic park twin."""
from __future__ import annotations
import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from .simulator import ParkSimulator


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    asset_id: str | None = None


def create_app(database_path: str | None = None, run_background: bool = True):
    @asynccontextmanager
    async def lifespan(app):
        app.state.park = ParkSimulator(database_path or os.environ.get("PARK_DB", str(Path(__file__).parent / "data" / "park.db")))
        async def simulate():
            while True:
                await asyncio.sleep(1)
                await asyncio.to_thread(app.state.park.advance)
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
        return {"status": "ok", "synthetic": True, "database": "connected", "tick": app.state.park.snapshot()["tick"]}

    @app.get("/api/state")
    def state():
        return app.state.park.snapshot()

    @app.get("/api/assets")
    def assets():
        return {"synthetic": True, "assets": app.state.park.snapshot()["assets"]}

    @app.get("/api/assets/{asset_id}/history")
    def history(asset_id: str, limit: int = Query(120, ge=1, le=3600)):
        try:
            return {"synthetic": True, "asset_id": asset_id, "history": app.state.park.history(asset_id, limit)}
        except KeyError:
            raise HTTPException(404, "Unknown asset")

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str):
        try:
            return app.state.park.asset(asset_id)
        except KeyError:
            raise HTTPException(404, "Unknown asset")

    @app.get("/api/systems")
    def systems():
        return {"synthetic": True, "systems": app.state.park.snapshot()["systems"]}

    @app.get("/api/systems/{system_id}/data")
    def system_data(system_id: str):
        state = app.state.park.snapshot()
        system = next((s for s in state["systems"] if s["id"] == system_id), None)
        if system is None:
            raise HTTPException(404, "Unknown synthetic system")
        fields = {
            "ride_scada": ["status", "throughput_per_hour", "power_kw", "maintenance"],
            "ticketing": ["occupancy", "capacity", "reservations", "queue_minutes"],
            "vision": ["occupancy", "capacity", "queue_minutes"],
            "cmms": ["maintenance", "dependencies"],
            "erp": ["erp", "throughput_per_hour"],
            "workforce": ["staff"],
            "bms": ["power_kw", "temperature_c", "dependencies"],
            "water": ["water_lpm", "status", "dependencies"],
            "weather": ["temperature_c"],
            "gis": ["scene_path", "metadata", "dependencies"],
        }[system_id]
        records = [{"asset_id": a["id"], **{k: a[k] for k in fields}, "synthetic": True}
                   for a in state["assets"] if a["id"] in system["asset_ids"]]
        return {"synthetic": True, "timestamp": state["timestamp"], "system": system, "records": records}

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
            return app.state.park.set_scenario(request.scenario)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/actions")
    def action(request: ActionRequest):
        try:
            return app.state.park.act(request.action, request.asset_id)
        except KeyError:
            raise HTTPException(404, "Unknown asset")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.websocket("/ws/state")
    async def websocket(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(app.state.park.snapshot())
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            pass

    return app


app = create_app()
