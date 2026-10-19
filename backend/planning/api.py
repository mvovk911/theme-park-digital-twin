"""Read-only planning HTTP routes; live mutations stay behind their own API."""
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from fastapi import HTTPException, Path as PathParam, Query, Request
from .contracts import PlanningRequest
from .engine import capabilities, simulate
from .evidence import EvidenceError, EvidenceStore, MAX_BUNDLE_BYTES, make_bundle, verify_bundle


def install_planning_routes(app):
    if getattr(app.state, "planning_installed", False):
        raise ValueError("Planning has already been installed")
    app.state.planning_installed = True
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            with application.state.park.lock:
                park_path = application.state.park.db.execute("PRAGMA database_list").fetchone()[2]
            default_path = str(Path(park_path).with_name("planning.db")) if park_path else ":memory:"
            path = os.environ.get("PARK_PLANNING_DB", default_path)
            if path != ":memory:" and park_path and Path(path).resolve() == Path(park_path).resolve():
                raise ValueError("Planning evidence must use a database separate from live park state")
            replay_path = os.environ.get("PARK_REPLAY_DB")
            if path != ":memory:" and replay_path and Path(path).resolve() == Path(replay_path).resolve():
                raise ValueError("Planning evidence must use a database separate from replay state")
            application.state.planning_evidence = EvidenceStore(path)
            try:
                yield
            finally:
                application.state.planning_evidence.close()

    app.router.lifespan_context = lifespan

    def evidence_call(operation):
        try:
            return operation()
        except EvidenceError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})

    async def read_bundle(request):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BUNDLE_BYTES:
                raise HTTPException(413, {"code": "evidence_too_large", "message": "Evidence input exceeds 1 MiB"})
            raw.extend(chunk)
        def unique_object(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("Duplicate JSON keys are not accepted")
                obj[key] = value
            return obj
        def invalid_constant(value):
            raise ValueError(f"Nonfinite JSON constant {value} is not accepted")
        try:
            return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise HTTPException(422, {"code": "invalid_evidence_json", "message": str(exc)})

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
                as_of = app.state.connectors.clock()
                result = simulate(snapshot, request, as_of=as_of)
                result["evidence_bundle"] = make_bundle(snapshot, request, result, as_of)
                return result
            except EvidenceError as exc:
                raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})
            except KeyError:
                raise HTTPException(409, {"code": "planning_revision_unavailable", "message": "The requested canonical state is no longer retained; fetch a new snapshot."})
            except ValueError as exc:
                raise HTTPException(422, {"code": "invalid_planning_input", "message": str(exc)})
        lock = getattr(app.state, "view_write_lock", None)
        if lock:
            async with lock:
                return run()
        return run()

    @app.get("/api/planning/evidence")
    def evidence_list(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0, le=256)):
        return app.state.planning_evidence.list(limit, offset)

    @app.post("/api/planning/evidence/verify")
    async def evidence_verify(request: Request):
        bundle = await read_bundle(request)
        return evidence_call(lambda: verify_bundle(bundle))

    @app.post("/api/planning/evidence")
    async def evidence_save(request: Request):
        bundle = await read_bundle(request)
        return evidence_call(lambda: app.state.planning_evidence.save(bundle))

    @app.get("/api/planning/evidence/{bundle_id}")
    def evidence_get(bundle_id: str = PathParam(pattern=r"^[0-9a-f]{64}$")):
        return evidence_call(lambda: app.state.planning_evidence.get(bundle_id))
