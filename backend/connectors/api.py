"""HTTP routes for connector discovery, observations and synthetic fault exercises."""
from typing import Any, Literal
from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from .validation import EventError


class DemoBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    synthetic: Literal[True]
    events: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["live", "paused", "offline"]


def install_connector_routes(app):
    def call(operation):
        try:
            return operation()
        except KeyError:
            raise HTTPException(404, "Unknown connector or asset")
        except EventError as exc:
            status = 409 if exc.code in {"cursor_expired", "source_not_paused", "not_synthetic"} else 422
            raise HTTPException(status, {"code": exc.code, "message": exc.message})

    def runtime():
        # Poll the source snapshot before serving the connector view. Freshness is
        # still based only on accepted event timestamps, never request time.
        app.state.read_model.snapshot()
        return app.state.connectors

    @app.get("/api/connectors")
    def catalog():
        return runtime().catalog()

    @app.get("/api/connectors/health")
    def health_all():
        connectors = runtime()
        return {"health": [connectors.health(ident) for ident in connectors.specs]}

    @app.get("/api/connectors/{source_id}")
    def connector(source_id: str):
        return call(lambda: runtime().catalog(source_id))

    @app.get("/api/connectors/{source_id}/health")
    def health(source_id: str):
        return call(lambda: runtime().health(source_id))

    @app.get("/api/connectors/{source_id}/snapshot")
    def snapshot(source_id: str):
        return call(lambda: runtime().source_snapshot(source_id))

    @app.get("/api/connectors/{source_id}/events")
    def events(source_id: str, after: str | None = None, limit: int = Query(100, ge=1, le=1000)):
        return call(lambda: runtime().events(source_id, after, limit))

    @app.get("/api/connectors/{source_id}/decisions")
    def decisions(source_id: str, after: str | None = None, limit: int = Query(100, ge=1, le=1000)):
        return call(lambda: runtime().decisions(source_id, after, limit))

    @app.get("/api/observations")
    def observations(source_id: str | None = None, asset_id: str | None = None,
                     limit: int = Query(1000, ge=1, le=2000)):
        return call(lambda: runtime().observations(source_id, asset_id, limit))

    @app.post("/api/connectors/{source_id}/ingest")
    def ingest(source_id: str, request: DemoBatch):
        def operation():
            connectors = runtime()
            result = connectors.ingest_demo(source_id, request.events)
            return {"synthetic": True, **result, "health": connectors.health(source_id)}
        return call(operation)

    @app.post("/api/connectors/{source_id}/simulation")
    def simulation(source_id: str, request: SimulationRequest):
        return call(lambda: runtime().set_simulation_mode(source_id, request.mode))
