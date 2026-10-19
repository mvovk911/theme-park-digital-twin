"""Explicit synthetic workflow HTTP boundary, serialized with recorded view."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import HTTPException, Path as PathParam, Query
from backend.planning.evidence import EvidenceError
from .contracts import CreateProposal, ExecuteProposal, WorkflowError
from .service import WorkflowService, capabilities
from .store import WorkflowStore


def install_workflow_routes(app):
    if getattr(app.state, "workflows_installed", False):
        raise ValueError("Workflows have already been installed")
    app.state.workflows_installed = True
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            with application.state.park.lock:
                park_path = application.state.park.db.execute("PRAGMA database_list").fetchone()[2]
            with application.state.planning_evidence.lock:
                evidence_path = application.state.planning_evidence.db.execute("PRAGMA database_list").fetchone()[2]
            default = str(Path(park_path).with_name("workflows.db")) if park_path else ":memory:"
            path = os.environ.get("PARK_WORKFLOWS_DB", default)
            conflicts = [p for p in [park_path, evidence_path, os.environ.get("PARK_REPLAY_DB")] if p]
            if path != ":memory:" and any(Path(path).resolve() == Path(p).resolve() for p in conflicts):
                raise ValueError("Workflows need a database separate from park, planning evidence and replay")
            store = WorkflowStore(path)
            application.state.workflow_store = store
            application.state.workflow_view_lock = asyncio.Lock()
            application.state.workflows = WorkflowService(application.state.park, application.state.read_model,
                                                         application.state.connectors, application.state.planning_evidence, store)
            try:
                yield
            finally:
                store.close()

    app.router.lifespan_context = lifespan

    def call(operation):
        try:
            return operation()
        except (WorkflowError, EvidenceError) as exc:
            detail = {"code": exc.code, "message": exc.message}
            if getattr(exc, "context", None) is not None:
                detail["context"] = exc.context
            raise HTTPException(exc.status, detail)

    async def mutate(operation):
        lock = getattr(app.state, "view_write_lock", app.state.workflow_view_lock)
        async with lock:
            replay = getattr(app.state, "replay", None)
            if replay and replay.is_replay:
                raise HTTPException(409, {"code": "recorded_view", "message": "Return to live before creating or executing workflow proposals"})
            # Same ordering as ParkReadModel.snapshot: connectors before park.
            with app.state.connectors.lock:
                with app.state.park.lock:
                    return call(operation)

    @app.get("/api/workflows/capabilities")
    def workflow_capabilities():
        return capabilities()

    @app.post("/api/workflows/proposals")
    async def proposal_create(request: CreateProposal):
        return await mutate(lambda: app.state.workflows.create(request))

    @app.post("/api/workflows/proposals/{proposal_id}/execute")
    async def proposal_execute(request: ExecuteProposal, proposal_id: str = PathParam(pattern=r"^[0-9a-f]{32}$")):
        return await mutate(lambda: app.state.workflows.execute(proposal_id, request))

    @app.get("/api/workflows/proposals")
    def proposals(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0, le=256)):
        return app.state.workflow_store.list(limit, offset)

    @app.get("/api/workflows/proposals/{proposal_id}")
    def proposal_get(proposal_id: str = PathParam(pattern=r"^[0-9a-f]{32}$")):
        return call(lambda: {"proposal": app.state.workflow_store.get(proposal_id)})
