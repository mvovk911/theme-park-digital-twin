"""A real OVRTX renderer with OVStage scene ownership and a small HTTP control API.

The render loop alone touches native SDK objects. HTTP handlers submit commands
through a queue; JPEG output is an actual GPU render, never a substitute scene.
"""

import io
import copy
import hashlib
import signal
import json
import math
import os
from pathlib import Path
import queue
import threading
import time
import traceback
import sys

import numpy as np
from PIL import Image
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
import uvicorn
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modeling.animate import wheel_transforms, CoasterRoute, train_transforms
from renderer.commands import CommandMailbox, MailboxClosed
from renderer.frame_cache import (
    FrameCache,
    response_headers,
    timestamp_age,
    camera_token,
    pick_context_matches,
)
from renderer.source_state import ride_motion_policy
from project_revision import source_identity

RUNTIME = ROOT / "runtime"
RUNTIME.mkdir(exist_ok=True)
WIDTH, HEIGHT = 1280, 720
FOCAL, APERTURE = 32.0, 36.0
PRODUCT = "/Render/Camera"
COLOR = PRODUCT + "/LdrColor"
app = FastAPI(title="Aster Park OVRTX render service")
commands = CommandMailbox(capacity=128)
frames_cache = FrameCache()
stop_event = threading.Event()
lock = threading.Lock()
state = dict(
    source_identity=source_identity(ROOT),
    ready=False,
    fps=0,
    frame=0,
    width=WIDTH,
    height=HEIGHT,
    selected_asset=None,
    camera={},
    error=None,
    projected_assets=[],
    engine="NVIDIA OVRTX + OVStage",
    phase="initializing",
    layer="operations",
)
registry = {}
SCENE_REVISION = hashlib.sha256((ROOT / "assets/park.usdc").read_bytes()).hexdigest()


def is_ready():
    with lock:
        return bool(state["ready"])


class Control(BaseModel):
    action: str
    dx: float = Field(0, ge=-2, le=2)
    dy: float = Field(0, ge=-2, le=2)
    delta: float = Field(0, ge=-2000, le=2000)
    asset_id: str | None = None
    layer: str = "operations"


class Pick(BaseModel):
    expected_camera_token: str | None = None
    expected_source_revision: str | None = None
    expected_view_mode: str | None = None
    expected_snapshot_id: int | None = None
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


@app.get("/status")
def status():
    with lock:
        result = copy.deepcopy(state)
        _, metadata = frames_cache.read()
    return {**result, **metadata}


@app.get("/frame.jpg")
def frame():
    data, metadata = frames_cache.read()
    if not data:
        raise HTTPException(503, "RTX renderer is warming up")
    return Response(
        data, media_type="image/jpeg", headers=response_headers(metadata, is_ready())
    )


@app.post("/control")
def control(data: Control):
    if not is_ready():
        raise HTTPException(503, "Renderer is not ready")
    if data.action not in {"orbit", "zoom", "home", "focus", "select", "layer"}:
        raise HTTPException(400, "Unknown control")
    if data.asset_id and data.asset_id not in registry:
        raise HTTPException(404, "Unknown scene asset")
    try:
        command = commands.submit("control", data.model_dump(), ttl=10.0)
    except queue.Full:
        raise HTTPException(429, "Renderer control queue is full")
    except MailboxClosed as error:
        raise HTTPException(503, str(error)) from error
    return {"accepted": True, "command_id": command.id}


@app.post("/pick")
def pick(data: Pick):
    if not is_ready():
        raise HTTPException(503, "Renderer not ready")
    try:
        completion = commands.submit("pick", data.model_dump(), ttl=14.0)
    except queue.Full:
        raise HTTPException(429, "Renderer control queue is full")
    except MailboxClosed as error:
        raise HTTPException(503, str(error)) from error
    if not completion.done.wait(15):
        commands.cancel(completion, "Renderer pick timed out")
        raise HTTPException(504, "Renderer pick timed out")
    if "error" in completion.result:
        raise HTTPException(
            completion.result.get("status_code", 503 if completion.cancelled else 500),
            completion.result["error"],
        )
    return completion.result


def unit(x):
    x = np.asarray(x, dtype=np.float64)
    return x / max(np.linalg.norm(x), 1e-9)


def camera_matrix(target, radius, yaw, pitch):
    eye = np.array(target) + radius * np.array(
        [
            math.cos(pitch) * math.cos(yaw),
            math.cos(pitch) * math.sin(yaw),
            math.sin(pitch),
        ]
    )
    back = unit(eye - target)
    right = unit(np.cross([0, 0, 1], back))
    up = np.cross(back, right)
    mat = np.eye(4, dtype=np.float64)
    mat[0, :3], mat[1, :3], mat[2, :3], mat[3, :3] = right, up, back, eye
    return mat


def project_assets(mat):
    out = []
    for aid, a in registry.items():
        p = np.array(a["position"], dtype=float) + [0, 0, 3]
        rel = p - mat[3, :3]
        depth = -np.dot(rel, mat[2, :3])
        if depth <= 0:
            continue
        xx = 0.5 + np.dot(rel, mat[0, :3]) * FOCAL / (depth * APERTURE)
        yy = 0.5 - np.dot(rel, mat[1, :3]) * FOCAL / (depth * APERTURE * HEIGHT / WIDTH)
        out.append(
            {
                "id": aid,
                "x": float(xx),
                "y": float(yy),
                "visible": bool(0 < xx < 1 and 0 < yy < 1),
            }
        )
    return out


def render_loop():
    global registry
    # Import SDKs only in the process owning the GPU. Do not import pxr here.
    renderer = stage = paths = None
    queries = {}
    client = None
    attached = False
    pending = None
    try:
        import ovrtx
        import ovstage

        registry = {
            a["asset_id"]: a
            for a in json.loads((ROOT / "assets/asset_registry.json").read_text())[
                "assets"
            ]
        }
        ride = json.loads((ROOT / "assets/ride_paths.json").read_text())
        route = CoasterRoute(ride["coaster"]["points"])
        with lock:
            state["phase"] = "compiling GPU shaders"
        renderer = ovrtx.Renderer(
            config=ovrtx.RendererConfig(
                log_file_path=str(RUNTIME / "ovrtx.log"), selection_outline_width=3
            )
        )
        stage = ovstage.Stage("aster.park.live")
        renderer.attach_ovstage(stage)
        attached = True
        source = f"""#usda 1.0
        (subLayers = [@{ROOT / 'assets/park.usdc'}@]
         metersPerUnit = 1
         upAxis = "Z")
        over "World"
        {{
          over "Camera"
          {{
          float focalLength = {FOCAL}
          float horizontalAperture = {APERTURE}
          float verticalAperture = {APERTURE*HEIGHT/WIDTH}
          }}
        }}
        def Scope "Render" {{
          def RenderProduct "Camera" {{
            rel camera = </World/Camera>
            uint[] deviceIds = [0]
            int2 resolution = ({WIDTH}, {HEIGHT})
            token omni:rtx:rendermode = "RealTimePathTracing"
            rel orderedVars = [<LdrColor>]
            def RenderVar "LdrColor"
            {{
              string sourceName = "LdrColor"
            }}
          }}
        }}"""
        ovstage.population.open_usd_from_string(stage, source, ordinal=1)
        stage.advance_write_floor(1, ovstage.Scope.ALL).wait()
        paths = ovstage.PathDictionary(stage)
        attr = paths.intern_token("omni:xform")
        moving = ["/World/Camera", *train_transforms(route, 0), *wheel_transforms(0)]
        for p in moving:
            pl = paths.create_path_list_from_strings([p])
            try:
                query = stage.query_from_path_list(pl)
            except Exception:
                paths.destroy_path_list(pl)
                raise
            queries[p] = (pl, query)
        dtype = ovstage.numpy_to_dldatatype(np.dtype(np.float64), lanes=16)

        def write_transform(path, mat, ordinal):
            a = np.ascontiguousarray(mat, dtype=np.float64).reshape(1, 4, 4)
            t = ovstage.make_dltensor(a, dtype=dtype, shape=[1], ndim=1)
            stage.write_attribute(
                queries[path][1], attr, ordinal=ordinal, tensors=t, is_array=False
            ).wait()

        target = np.array([0.0, 0.0, 3.0])
        radius = 285.0
        yaw = math.radians(-54)
        pitch = math.radians(40)
        ordinal = 1
        last = time.monotonic()
        wheel_angle = 0.0
        train_phase = 0.0
        last_api = 0.0
        last_receipt = 0.0
        assets = {}
        selection = []
        step_count = 0
        snapshot = {}
        view = {}
        source_timestamp = None
        source_tick = None
        accepted_state_revision = None
        client = httpx.Client(timeout=0.25, trust_env=False)
        with lock:
            state["phase"] = "rendering first frame"
        while not stop_event.is_set():
            begin = time.monotonic()
            interval = begin - last
            dt = min(interval, 0.25)
            last = begin
            if begin - last_api > 1.0:
                try:
                    response = client.get(
                        os.environ.get("PARK_API_URL", "http://127.0.0.1:8100")
                        + "/api/view/state"
                    )
                    response.raise_for_status()
                    snapshot = response.json()
                    assets = {a["id"]: a for a in snapshot["assets"]}
                    last_receipt = begin
                    source_timestamp = snapshot.get("timestamp")
                    source_tick = snapshot.get("tick")
                    accepted_state_revision = snapshot.get("accepted_state_revision")
                    view = snapshot.get("view", {})
                    with lock:
                        state["api_connected"] = True
                except Exception:
                    with lock:
                        state["api_connected"] = False
                last_api = begin
            for _ in range(40):
                if pending:
                    break
                command = commands.take()
                if command is None:
                    break
                data = command.payload
                if command.kind == "pick":
                    pending = command
                    break
                a = data["action"]
                if a == "orbit":
                    yaw -= data["dx"] * 4.0
                    pitch = np.clip(pitch + data["dy"] * 3.0, 0.12, 1.45)
                elif a == "zoom":
                    radius = float(
                        np.clip(radius * math.exp(data["delta"] * 0.001), 18, 470)
                    )
                elif a == "home":
                    target = np.array([0.0, 0.0, 3.0])
                    radius = 285.0
                    yaw = math.radians(-54)
                    pitch = math.radians(40)
                elif a in {"focus", "select"} and data["asset_id"]:
                    aid = data["asset_id"]
                    with lock:
                        state["selected_asset"] = aid
                    if a == "focus":
                        target = np.array(registry[aid]["position"], dtype=float)
                        radius = 83.0
                    if selection:
                        renderer.set_selection_outline_group_strings(selection, 0)
                    selection = [registry[aid]["prim_path"]]
                    renderer.set_selection_outline_group_strings(selection, 1)
                elif a == "layer":
                    with lock:
                        state["layer"] = data["layer"]
                commands.finish(command)
            current_camera = {
                "target": target.tolist(),
                "radius": radius,
                "yaw": float(yaw),
                "pitch": float(pitch),
            }
            current_context = {
                "camera_token": camera_token(current_camera),
                "accepted_state_revision": accepted_state_revision,
                "view_mode": view.get("mode", "live"),
                "snapshot_id": view.get("snapshot_id"),
            }
            if (
                pending
                and pending.payload.get("expected_camera_token") is not None
                and not pick_context_matches(pending.payload, current_context)
            ):
                commands.finish(
                    pending,
                    {
                        "error": "Displayed camera or data view changed; retry on the current image",
                        "status_code": 409,
                    },
                )
                pending = None
            mat = camera_matrix(target, radius, yaw, pitch)
            ordinal += 1
            write_transform("/World/Camera", mat, ordinal)
            replay = view.get("mode") == "replay"
            source_age = timestamp_age(source_timestamp)
            fresh = bool(
                last_receipt
                and begin - last_receipt <= 3.0
                and source_age is not None
                and source_age <= 5.0
            )
            motion = (
                view.get("recorded_motion")
                if replay and view.get("scene_matches_current", True)
                else None
            )
            motion_policy = ride_motion_policy(assets, fresh, replay)
            source_stale = any(
                rule["reason"].startswith(("status_source_", "snapshot_stale"))
                for rule in motion_policy.values()
            )
            pose_source = (
                "recorded"
                if motion
                else (
                    "unrecorded"
                    if replay
                    else "stale_frozen" if source_stale else "live"
                )
            )
            if motion:
                wheel_angle = float(motion["wheel_angle"])
                train_phase = float(motion["coaster_phase"])
            if motion_policy["RIDE_WHEEL"]["advance"]:
                wheel_angle += dt * 0.16
            for path, transform in wheel_transforms(wheel_angle).items():
                write_transform(path, transform, ordinal)
            if motion_policy["RIDE_COASTER"]["advance"]:
                train_phase = (train_phase + dt / 42) % 1
            for path, transform in train_transforms(route, train_phase).items():
                write_transform(path, transform, ordinal)
            stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()
            if pending and not commands.active(pending):
                commands.cancel(pending)
                pending = None
            if pending:
                p = pending.payload
                x = min(p["x"], 1 - 1 / WIDTH)
                y = min(p["y"], 1 - 1 / HEIGHT)
                renderer.enqueue_pick_query(
                    render_product_path=PRODUCT,
                    left_ndc=x,
                    top_ndc=y,
                    right_ndc=min(1, x + 1 / WIDTH),
                    bottom_ndc=min(1, y + 1 / HEIGHT),
                    flags=ovrtx.OVRTX_PICK_FLAG_INCLUDE_TRACKED_INFO,
                )
            products = renderer.step(
                render_products={PRODUCT}, delta_time=max(dt, 0.001), ordinal=ordinal
            )
            frames = products[PRODUCT].frames
            for frame in frames:
                mapping = frame.render_vars[COLOR].map(device=ovrtx.Device.CPU)
                pixels = np.from_dlpack(mapping).copy()
                mapping.unmap()
                del mapping
                if pending and not commands.active(pending):
                    commands.cancel(pending)
                    pending = None
                if pending:
                    completion = pending
                    try:
                        rv = frame.render_vars[ovrtx.OVRTX_RENDER_VAR_PICK_HIT]
                        mp = rv.map(device=ovrtx.Device.CPU)
                        magic = int(np.from_dlpack(mp.params["magic"]).reshape(-1)[0])
                        version = int(
                            np.from_dlpack(mp.params["version"]).reshape(-1)[0]
                        )
                        count = int(
                            np.from_dlpack(mp.params["hitCount"]).reshape(-1)[0]
                        )
                        hitids = np.from_dlpack(mp["primPath"]).copy().reshape(-1)
                        mp.unmap()
                        if (
                            magic != ovrtx.OVRTX_PICK_HIT_MAGIC
                            or version != ovrtx.OVRTX_PICK_HIT_VERSION
                        ):
                            raise RuntimeError("Unexpected pick schema")
                        hit = None
                        if count:
                            value = hitids[0]
                            if isinstance(value, (str, np.str_)):
                                hit = str(value)
                            elif isinstance(value, (bytes, np.bytes_)):
                                hit = value.decode()
                            else:
                                hit = renderer.resolve_prim_path_id(int(value))
                        aid = next(
                            (
                                k
                                for k, v in registry.items()
                                if hit
                                and (
                                    hit == v["prim_path"]
                                    or hit.startswith(v["prim_path"] + "/")
                                )
                            ),
                            None,
                        )
                        if not commands.active(completion):
                            raise TimeoutError("Renderer pick expired before selection")
                        if selection:
                            renderer.set_selection_outline_group_strings(selection, 0)
                        selection = [hit] if aid else []
                        if selection:
                            renderer.set_selection_outline_group_strings(selection, 1)
                        with lock:
                            state["selected_asset"] = aid
                        commands.finish(
                            completion,
                            {
                                "asset_id": aid,
                                "prim_path": hit,
                                "engine": "ovrtx_pick_hit",
                            },
                        )
                    except Exception as e:
                        commands.finish(completion, {"error": str(e)})
                    pending = None
                buf = io.BytesIO()
                Image.fromarray(pixels).convert("RGB").save(
                    buf, format="JPEG", quality=87
                )
                step_count += 1
                elapsed = max(time.monotonic() - begin, 0.001)
                with lock:
                    frames_cache.publish(
                        buf.getvalue(),
                        {
                            "frame": step_count,
                            "source_timestamp": source_timestamp,
                            "source_tick": source_tick,
                            "ride_motion": {
                                "coaster_phase": train_phase,
                                "wheel_angle": wheel_angle,
                            },
                            "ride_status": {
                                k: assets.get(k, {}).get("status")
                                for k in ("RIDE_COASTER", "RIDE_WHEEL")
                            },
                            "motion_policy": motion_policy,
                            "accepted_state_revision": accepted_state_revision,
                            "camera": current_camera,
                            "camera_token": current_context["camera_token"],
                            "projected_assets": project_assets(mat),
                            "width": WIDTH,
                            "height": HEIGHT,
                            "view_mode": view.get("mode", "live"),
                            "snapshot_id": view.get("snapshot_id"),
                            "scene_revision": SCENE_REVISION,
                            "pose_source": pose_source,
                        },
                    )
                    state.update(
                        ready=True,
                        phase="rendering",
                        frame=step_count,
                        fps=round(1 / max(interval, 0.001), 1),
                        camera={
                            "target": target.tolist(),
                            "radius": radius,
                            "yaw": float(yaw),
                            "pitch": float(pitch),
                        },
                        projected_assets=project_assets(mat),
                        error=None,
                        ovrtx_version=ovrtx.__version__,
                        ovstage_version=ovstage.__version__,
                        ride_motion={
                            "coaster_phase": train_phase,
                            "wheel_angle": wheel_angle,
                        },
                        motion_policy=motion_policy,
                        ride_status={
                            k: assets.get(k, {}).get("status")
                            for k in ("RIDE_COASTER", "RIDE_WHEEL")
                        },
                    )
                if step_count == 20:
                    Image.fromarray(pixels).save(RUNTIME / "first-render.png")
                del frame
            del frames, products
            stop_event.wait(max(0, 0.08 - (time.monotonic() - begin)))
    except Exception as e:
        traceback.print_exc()
        with lock:
            state.update(ready=False, error=str(e), phase="failed")
    finally:
        commands.close("Renderer failed or stopped")
        with lock:
            state["ready"] = False
            if state["phase"] != "failed":
                state["phase"] = "stopped"
        # Native objects remain on this one owner thread, including cleanup.
        cleanup = []
        for pl, q in queries.values():
            cleanup.extend(
                [
                    lambda q=q: q.release().wait(),
                    lambda pl=pl: paths.destroy_path_list(pl),
                ]
            )
        if paths:
            cleanup.append(paths.destroy)
        if renderer and attached:
            cleanup.append(renderer.detach_ovstage)
        if stage:
            cleanup.append(stage.destroy)
        if renderer:
            cleanup.append(renderer.destroy)
        if client:
            cleanup.append(client.close)
        errors = []
        for release in cleanup:
            try:
                release()
            except Exception as error:
                errors.append(str(error))
        with lock:
            state["cleanup_errors"] = errors


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8091, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise SystemExit("Render HTTP service failed to start; check port 8091")
        time.sleep(0.05)
    try:
        render_loop()
        # Diagnostics can outlive a failed native renderer, after resources release.
        while not stop_event.wait(0.5):
            if not thread.is_alive():
                break
    finally:
        server.should_exit = True
        thread.join(timeout=5)
