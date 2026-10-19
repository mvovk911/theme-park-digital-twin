"""Read-only planning HTTP routes; live mutations stay behind their own API."""
from fastapi import HTTPException
from .contracts import PlanningRequest
from .engine import capabilities, simulate


def install_planning_routes(app):
    @app.get("/api/planning/capabilities")
    def planning_capabilities():
        return capabilities()

    @app.post("/api/planning/simulate")
    async def planning_simulate(request: PlanningRequest):
        def run():
            replay = getattr(app.state, "replay", None)
            if replay and replay.is_replay:
                raise HTTPException(409, {"code": "recorded_view", "message": "Return to live before starting a prospective plan."})
            try:
                if request.expected_state_revision:
                    snapshot = app.state.read_model.revision_snapshot(request.expected_state_revision)["state"]
                else:
                    snapshot = app.state.read_model.snapshot()
                return simulate(snapshot, request, as_of=app.state.connectors.clock())
            except KeyError:
                raise HTTPException(409, {"code": "planning_revision_unavailable", "message": "The requested canonical state is no longer retained; fetch a new snapshot."})
            except ValueError as exc:
                raise HTTPException(422, {"code": "invalid_planning_input", "message": str(exc)})
        lock = getattr(app.state, "view_write_lock", None)
        if lock:
            async with lock:
                return run()
        return run()
