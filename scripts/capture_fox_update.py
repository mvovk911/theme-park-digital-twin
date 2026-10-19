"""Record an 88-second update from the actual, revision-verified GPU application.

Uses only real UI interactions and real service responses. It changes the shared
synthetic scenario/view/camera and creates one synthetic work order. Run only in a
reserved demo window. --plan is offline; --preflight-only reads without mutation.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlsplit
from uuid import uuid4

TARGET_SECONDS = 88
RESOLUTION = {"width": 1920, "height": 960}
PLAN = [
    (0, "An actual incident in the live twin", "Actual RTX frames. The coaster closure, source data and operator actions are synthetic."),
    (9, "Start with the current incident", "Prepare the selected asset. No forecast or saved comparison is required."),
    (18, "Review the frozen observations", "Status, inspection and open orders retain their source quality and timestamps at proposal creation."),
    (29, "Execute a separate, explicit request", "A synthetic work order is acknowledged and read back. Dispatch does not repair or reopen the ride."),
    (42, "The ride remains closed", "The live asset still reports closed, with one open work order. Acceptance is not physical completion."),
    (49, "Compare an authored design", "Baseline access is unreachable. The separate dining design gives a 40.852 m route at assumed walking speed."),
    (57, "Inspect the native before and after", "Matched static native closeups show the added connection. These images are not the live camera."),
    (65, "Close the connection in the query", "Closing the authored connection removes the route. The query does not change the park or its scene."),
    (74, "Test the unresolved entrance barrier", "The step-free filter still finds no route from the entrance. Authored labels are not certification."),
    (82, "Keep the evidence and the limits", "Export the exact queries, responses and identities. This design query is independent of the forecast."),
]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def vtt_time(seconds):
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def verify_identity(value, expected, label):
    identity = value.get("source_identity", {})
    if (identity.get("commit") != expected or identity.get("verified") is not True
            or identity.get("disposition") != "verified_manifest"):
        raise RuntimeError(f"{label} is not the expected verified-manifest release {expected}")
    return identity


async def get_json(api, base, path):
    response = await api.get(base + path, timeout=12000)
    if not response.ok:
        raise RuntimeError(f"GET {path} returned HTTP {response.status}")
    try:
        return await response.json()
    except Exception as error:
        raise RuntimeError(f"GET {path} did not return readable JSON") from error


async def preflight(api, base, expected):
    health, render, workflow, spatial = await asyncio.gather(*[
        get_json(api, base, path) for path in
        ("/api/health", "/render/status", "/api/workflows/capabilities", "/api/spatial/capabilities")
    ])
    backend_identity = verify_identity(health, expected, "Gateway")
    render_identity = verify_identity(render, expected, "Renderer")
    if health.get("status") != "ok" or health.get("synthetic") is not True:
        raise RuntimeError("Expected a healthy synthetic gateway")
    if not render.get("ready") or "NVIDIA OVRTX" not in render.get("engine", ""):
        raise RuntimeError("The actual NVIDIA OVRTX renderer is unavailable")
    if (render.get("scene_revision") != render_identity.get("scene_sha256")
            or backend_identity.get("scene_sha256") != render_identity.get("scene_sha256")):
        raise RuntimeError("Gateway and rendered scene identities differ")
    if (workflow.get("synthetic") is not True or workflow.get("physical_control") is not False
            or not workflow.get("proposal_origins", {}).get("current_incident")):
        raise RuntimeError("The bounded current-incident workflow is unavailable")
    if spatial.get("mutates_live_state") is not False or spatial.get("forecast_coupled") is not False:
        raise RuntimeError("The independent read-only design capability is unavailable")
    previews = {}
    for variant in ("baseline", "dining_connection"):
        metadata = await get_json(api, base, f"/api/spatial/previews/{variant}/metadata")
        response = await api.get(base + f"/api/spatial/previews/{variant}", timeout=12000)
        body = await response.body()
        identity = next(row["identity"] for row in spatial["variants"] if row["variant"] == variant)
        headers = response.headers
        if (not response.ok or not body.startswith(b"\x89PNG\r\n\x1a\n")
                or headers.get("x-spatial-preview-mode") != "static_native"
                or sha256(body) != headers.get("x-spatial-preview-image-sha256")
                or headers.get("x-spatial-graph-sha256") != identity["graph_sha256"]
                or headers.get("x-spatial-scene-sha256") != identity["baseline_scene_sha256"]
                or (headers.get("x-spatial-variant-layer-sha256") or "") != (identity["variant_layer_sha256"] or "")):
            raise RuntimeError(f"Native {variant} preview bytes/source identity could not be verified")
        previews[variant] = {"metadata": metadata, "image_sha256": sha256(body),
                             "headers": {key: value for key, value in headers.items() if key.startswith("x-spatial-")}}
    frame = await api.get(base + "/render/frame.jpg", timeout=12000)
    body = await frame.body()
    headers = frame.headers
    if (not frame.ok or not body.startswith(b"\xff\xd8") or not headers.get("x-source-revision")
            or not headers.get("x-frame-context") or not headers.get("x-frame-number")):
        raise RuntimeError("Actual GPU JPEG with exact frame/source provenance is unavailable")
    json.loads(headers["x-frame-context"])
    return {"health": health, "renderer": render, "workflow": workflow, "spatial": spatial,
            "previews": previews, "frame": {"sha256": sha256(body),
            "headers": {key: value for key, value in headers.items() if key.startswith("x-")}}}


async def record(args):
    from playwright.async_api import async_playwright

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    manifest = {
        "schema_version": "aster.fox-feature-update.v1", "started_at": utc_now(),
        "url": args.url, "expected_commit": args.expected_commit, "status": "preflight",
        "target_content_seconds": TARGET_SECONDS, "resolution": RESOLUTION,
        "recorder_script_sha256": sha256(Path(__file__).read_bytes()),
        "native_resolution_note": "Browser recording resolution is not native GPU resolution or frame rate; see preflight renderer evidence.",
        "scope": "Actual browser/GPU application; all operational sources and actions are synthetic; design previews are static native captures.",
        "timing_basis": "Monotonic since page creation; approximate relative to first encoded frame. No speed-up or application-value replacement.",
        "chapters": [], "screenshots": [], "requests": [], "responses": [], "page_errors": [],
        "request_failures": [], "cleanup": [], "finalization_errors": [], "observation_errors": [],
    }
    browser = context = page = api = video = None
    recording_zero = content_zero = None
    mutations_started = False
    failed = None
    tasks = set()
    frames = {}

    def elapsed():
        return round(time.monotonic() - recording_zero, 3) if recording_zero else None

    def persist():
        (output / "capture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        captions = ["WEBVTT", ""]
        for index, chapter in enumerate(manifest["chapters"], 1):
            end = chapter.get("end_seconds")
            if end is not None and end > chapter["start_seconds"]:
                captions += [str(index), f'{vtt_time(chapter["start_seconds"])} --> {vtt_time(end)}',
                             chapter["caption"], ""]
        (output / "captions.vtt").write_text("\n".join(captions) + "\n")

    async def post(path, payload):
        # No retries for writes. The UI retains its own workflow identities;
        # recorder setup/cleanup resets have distinct explicit request IDs.
        response = await api.post(args.url + path, data=payload, timeout=10000)
        if not response.ok:
            raise RuntimeError(f"POST {path} returned HTTP {response.status}: {(await response.text())[:300]}")
        return await response.json()

    async def observe(response):
        try:
            path = urlsplit(response.url).path
            if path == "/render/frame.jpg" and response.ok:
                headers = await response.all_headers()
                body = await response.body()
                number = headers.get("x-frame-number")
                if number:
                    frames[number] = {"sha256": sha256(body), "headers": {
                        key: value for key, value in headers.items() if key.startswith("x-")}}
                    while len(frames) > 40:
                        del frames[next(iter(frames))]
            elif response.request.method == "POST":
                try:
                    body = await response.json()
                except Exception:
                    body = {"unreadable_response": True}
                manifest["responses"].append({"at_seconds": elapsed(), "path": path,
                                               "status": response.status, "body": body})
        except Exception as error:
            manifest["observation_errors"].append(str(error))

    def on_response(response):
        task = asyncio.create_task(observe(response))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    def on_request(request):
        if request.method == "POST":
            manifest["requests"].append({"at_seconds": elapsed(), "path": urlsplit(request.url).path,
                                          "payload": request.post_data_json})

    async def focus(selector):
        await page.locator(selector).first.evaluate(
            "e=>window.scrollTo({top:Math.max(0,e.getBoundingClientRect().top+scrollY-24),behavior:'smooth'})")
        await page.wait_for_timeout(550)

    async def await_live_annotations():
        await page.wait_for_function("""() => {
            const viewport=document.getElementById('viewport');
            const label=document.querySelector('#scene-labels [data-label-asset="RIDE_COASTER"]');
            return viewport.classList.contains('frame-ready') &&
                !viewport.classList.contains('frame-stale') &&
                document.getElementById('frame-context').hidden &&
                document.querySelectorAll('#scene-labels .scene-label').length>0 &&
                label && label.textContent.includes('Closed');
        }""",timeout=12000)

    async def click(selector):
        locator = page.locator(selector).first
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        if box:
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=12)
        await locator.click()
        await page.wait_for_timeout(250)

    async def chapter(index):
        planned, title, caption = PLAN[index]
        delay = content_zero + planned - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        if elapsed() >= 97:
            raise RuntimeError("Capture exceeded its short-update timing budget; preserve this failed take")
        if manifest["chapters"]:
            manifest["chapters"][-1]["end_seconds"] = elapsed()
        manifest["chapters"].append({"start_seconds": elapsed(), "title": title, "caption": caption,
                                      "planned_content_second": planned})
        persist()
        print(f"[{elapsed():5.1f}s] {title}", flush=True)

    async def screenshot(name, selector=None):
        before_frame = await page.locator("#render-frame").get_attribute("data-frame")
        data = await (page.locator(selector).screenshot(path=str(output / name)) if selector
                      else page.screenshot(path=str(output / name)))
        frame_number = await page.locator("#render-frame").get_attribute("data-frame")
        visible = await page.locator("#render-frame").evaluate(
            "e=>{let r=e.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth&&!e.hidden;}")
        frame = frames.get(frame_number)
        if visible and not frame:
            await page.wait_for_timeout(200)
            frame = frames.get(frame_number)
        manifest["screenshots"].append({"file": name, "sha256": sha256(data), "at_seconds": elapsed(),
                                        "frame_before_screenshot": before_frame, "frame_after_screenshot": frame_number, "live_frame_in_viewport": visible,
                                        "frame_context_before": frames.get(before_frame), "frame_context_after": frame,
                                        "frame_association": "DOM frame ID stable across screenshot; no pixel-level certification" if frame and frame_number == before_frame else "Frame changed or context unavailable; no exact screenshot/frame association claimed"})
        persist()

    async def close_phase(label, operation, timeout=20):
        try:
            await asyncio.wait_for(operation(), timeout)
        except Exception as error:
            manifest["finalization_errors"].append({"phase": label, "error": str(error)})

    try:
        async with async_playwright() as playwright:
            api = await playwright.request.new_context()
            try:
                manifest["preflight"] = await preflight(api, args.url, args.expected_commit)
                persist()
                mutations_started = True
                await post("/api/view", {"mode": "live"})
                await post("/api/actions", {"action": "reset", "request_id": "fox-video-setup:" + uuid4().hex})
                await post("/render/control", {"action": "home"})
                await post("/render/control", {"action": "layer", "layer": "operations"})
                browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context(viewport=RESOLUTION, device_scale_factor=1,
                    accept_downloads=True, record_video_dir=str(raw), record_video_size=RESOLUTION)
                recording_zero = time.monotonic()
                page = await context.new_page()
                video = page.video
                page.set_default_timeout(8000)
                page.on("pageerror", lambda error: manifest["page_errors"].append(str(error)))
                page.on("requestfailed", lambda request: manifest["request_failures"].append({
                    "path": urlsplit(request.url).path, "failure": request.failure, "at_seconds": elapsed()}))
                page.on("request", on_request)
                page.on("response", on_response)
                await page.goto(args.url, wait_until="domcontentloaded", timeout=12000)
                await page.wait_for_selector("#viewport.frame-ready", timeout=12000)
                await page.wait_for_function("!document.getElementById('spatial-export').disabled")
                await page.wait_for_function("!document.getElementById('spatial-preview-baseline').hidden&&!document.getElementById('spatial-preview-dining_connection').hidden")
                await click('[data-scenario="ride_closure"]')
                await page.wait_for_function("document.querySelector('[data-scenario=ride_closure]').classList.contains('active')&&!document.querySelector('[data-scenario=ride_closure]').disabled")
                await page.select_option("#asset-select", "RIDE_COASTER")
                await page.wait_for_function("document.getElementById('asset-status').textContent.startsWith('closed')")
                await focus(".viewport-card")
                await await_live_annotations()
                content_zero = time.monotonic()
                manifest["presentation_start_seconds"] = elapsed()
                manifest["status"] = "recording"

                await chapter(0)
                first_frame = await page.locator("#render-frame").get_attribute("data-frame")
                await page.wait_for_timeout(1500)
                second_frame = await page.locator("#render-frame").get_attribute("data-frame")
                if first_frame == second_frame:
                    raise RuntimeError("Displayed GPU frame did not advance")
                manifest["advancing_frames"] = [first_frame, second_frame]
                await await_live_annotations()
                await screenshot("01-live-closure.png")

                await chapter(1)
                before = len([row for row in manifest["requests"] if row["path"].startswith('/api/workflows/')])
                await click("#prepare-maintenance")
                await focus("#workflow-panel")
                if len([row for row in manifest["requests"] if row["path"].startswith('/api/workflows/')]) != before:
                    raise RuntimeError("Preparing an incident unexpectedly issued a workflow request")
                async with page.expect_response(lambda response: urlsplit(response.url).path == "/api/workflows/incidents") as pending:
                    await click("#workflow-create")
                response = await pending.value
                if not response.ok:
                    raise RuntimeError(f"Incident proposal rejected: {await response.text()}")
                proposal = (await response.json())["proposal"]
                if proposal.get("origin") != "current_incident" or proposal.get("precondition_scope") != "target":
                    raise RuntimeError("Unexpected incident proposal scope")
                if len(proposal.get("creation_observation", {}).get("fields", {})) != 3:
                    raise RuntimeError("The three frozen source observations are missing")
                manifest["proposal"] = proposal

                await chapter(2)
                await focus("#workflow-proposal")
                await screenshot("02-frozen-observations.png")

                await chapter(3)
                async with page.expect_response(lambda response: urlsplit(response.url).path.endswith("/execute")) as pending:
                    await click("#workflow-execute")
                response = await pending.value
                if not response.ok:
                    raise RuntimeError(f"Execution rejected: {await response.text()}")
                accepted = await response.json()
                receipt = accepted["proposal"]
                if (accepted.get("outcome") != "accepted_workflow_not_repair"
                        or receipt.get("readback", {}).get("physical_completion") is not False
                        or receipt["readback"].get("asset_status_evidence", {}).get("value") != "closed"
                        or receipt["readback"]["asset_status_evidence"].get("quality") != "good"
                        or receipt["receipt"]["work_order_id"] != receipt["readback"]["work_order"]["id"]):
                    raise RuntimeError("Accepted work order and independently observed closed status do not agree")
                manifest["accepted_workflow"] = accepted
                await page.wait_for_function("document.getElementById('workflow-proposal').textContent.includes('Work order accepted')")
                await focus(".workflow-result")
                await screenshot("03-receipt-still-closed.png")

                await chapter(4)
                await focus(".viewport-card")
                await page.wait_for_function("document.getElementById('asset-status').textContent.startsWith('closed')&&Number(document.getElementById('asset-orders').textContent)===1")
                manifest["asset_after_dispatch"] = await get_json(api,args.url,"/api/assets/RIDE_COASTER")
                await await_live_annotations()
                await screenshot("04-live-work-order.png")

                await chapter(5)
                await focus("#spatial-panel")
                if "40.852" not in await page.locator("#spatial-result-dining_connection").inner_text():
                    raise RuntimeError("Expected dining route distance is absent")
                if "No route" not in await page.locator("#spatial-result-baseline").inner_text():
                    raise RuntimeError("Baseline unexpectedly has a dining route")
                await screenshot("05-design-comparison.png")

                await chapter(6)
                await focus(".spatial-preview")
                await screenshot("06-static-native-closeups.png")

                await chapter(7)
                await focus(".spatial-controls")
                await page.check("#spatial-closed")
                await click("#spatial-compare")
                await page.wait_for_function("!document.getElementById('spatial-export').disabled")
                if "No route" not in await page.locator("#spatial-result-dining_connection").inner_text():
                    raise RuntimeError("Closing the authored connection did not remove the route")
                await screenshot("07-query-closure.png")

                await chapter(8)
                await page.uncheck("#spatial-closed")
                await page.check("#spatial-accessible")
                await click("#spatial-compare")
                await page.wait_for_function("!document.getElementById('spatial-export').disabled")
                if ("No route" not in await page.locator("#spatial-result-dining_connection").inner_text()
                        or "entry threshold" not in await page.locator("#spatial-note-dining_connection").inner_text()):
                    raise RuntimeError("The remaining entrance barrier is not explicitly reported")
                await screenshot("08-step-free-negative.png")

                await chapter(9)
                await focus(".spatial-footer")
                async with page.expect_download() as pending:
                    await click("#spatial-export")
                download = await pending.value
                await download.save_as(str(output / "spatial-query-evidence.json"))
                manifest["spatial_export_sha256"] = sha256((output / "spatial-query-evidence.json").read_bytes())
                await screenshot("09-export-limits.png")
                await asyncio.sleep(max(0,content_zero + TARGET_SECONDS - time.monotonic()))
                manifest["recording_content_end_seconds"] = elapsed()
                manifest["chapters"][-1]["end_seconds"] = elapsed()
                if elapsed() >= 100:
                    raise RuntimeError("Raw-content timeline exceeded 100 seconds; this take is not accepted")
                health, render = await asyncio.gather(get_json(api,args.url,"/api/health"),get_json(api,args.url,"/render/status"))
                verify_identity(health,args.expected_commit,"Final gateway")
                verify_identity(render,args.expected_commit,"Final renderer")
                manifest["final_health"] = health
                manifest["final_renderer"] = render
                if manifest["page_errors"]:
                    raise RuntimeError("Browser errors were observed; inspect the evidence before recording another take")
                manifest["status"] = "captured"
            except Exception as error:
                failed = error
                manifest["status"] = "failed"
                manifest["error"] = f"{type(error).__name__}: {error}"
                if page:
                    try:
                        await screenshot("failure.png")
                    except Exception as secondary:
                        manifest["finalization_errors"].append({"phase":"failure_screenshot","error":str(secondary)})
            finally:
                # Close the recorded browser before restoration, so cleanup is
                # not misrepresented as part of the feature demonstration.
                try:
                    if page:
                        try:
                            manifest["retained_workflow_retry_record"] = await page.evaluate("localStorage.getItem('aster.maintenance.retry.v1')")
                        except Exception as error:
                            manifest["finalization_errors"].append({"phase":"retry_identity_read","error":str(error)})
                    if tasks:
                        await close_phase("response_observations",lambda:asyncio.gather(*list(tasks),return_exceptions=True),5)
                    if context:
                        manifest["browser_close_requested_seconds"] = elapsed()
                        await close_phase("context.close",context.close)
                    if browser:
                        await close_phase("browser.close",browser.close)
                    if video:
                        try:
                            path = await asyncio.wait_for(video.path(),15)
                            manifest["original_video_path"] = str(path)
                            target = output / "fox-feature-update-raw.webm"
                            shutil.move(str(path),target)
                            manifest["video"] = target.name
                            manifest["video_sha256"] = sha256(target.read_bytes())
                            manifest["duration_seconds"] = manifest.get("recording_content_end_seconds",elapsed())
                            manifest["duration_basis"] = "Monotonic content end; encoded container duration has not been measured"
                        except Exception as error:
                            manifest["finalization_errors"].append({"phase":"video_finalize","error":str(error)})
                finally:
                    # Media finalization failures never bypass cleanup or API disposal.
                    try:
                        if mutations_started:
                            for path,payload in [
                                ("/api/view",{"mode":"live"}),
                                ("/api/actions",{"action":"reset","request_id":"fox-video-cleanup:"+uuid4().hex}),
                                ("/render/control",{"action":"home"}),
                                ("/render/control",{"action":"layer","layer":"operations"}),
                            ]:
                                try:
                                    await post(path,payload)
                                    manifest["cleanup"].append({"path":path,"ok":True})
                                except Exception as error:
                                    manifest["cleanup"].append({"path":path,"ok":False,"error":str(error)})
                            try:
                                state = await get_json(api,args.url,"/api/view/state")
                                manifest["cleanup_view"] = state.get("view")
                                manifest["cleanup_scenario"] = state.get("scenario")
                                if state.get("scenario") != "normal" or state.get("view",{}).get("mode") != "live":
                                    raise RuntimeError("Cleanup did not restore live/normal")
                            except Exception as error:
                                manifest["cleanup"].append({"path":"readback","ok":False,"error":str(error)})
                    finally:
                        if api:
                            await close_phase("api.dispose",api.dispose)
    except Exception as error:
        # Also preserve failures while starting/stopping the Playwright manager,
        # outside the browser/API inner finalizers.
        if failed is None:
            failed = error
            manifest["status"] = "failed"
            manifest["error"] = f"{type(error).__name__}: {error}"
    finally:
        if manifest["chapters"] and "end_seconds" not in manifest["chapters"][-1]:
            manifest["chapters"][-1]["end_seconds"] = manifest.get("browser_close_requested_seconds") or elapsed()
        if manifest["finalization_errors"] or any(not row["ok"] for row in manifest["cleanup"]):
            if failed is None:
                failed = RuntimeError("Capture finalization or cleanup failed; inspect manifest")
                manifest["status"] = "failed"
                manifest["error"] = str(failed)
        manifest["finished_at"] = utc_now()
        try:
            persist()
        except Exception as error:
            # A failed final evidence write must not replace the original error.
            print(f"Final manifest write failed: {error}",flush=True)
            if failed is None:
                failed = error
    if failed:
        raise failed
    print(json.dumps({"status":manifest["status"],"video":manifest.get("video"),
                      "content_end_seconds":manifest.get("recording_content_end_seconds"),"manifest":str(output/'capture-manifest.json')},indent=2))


async def preflight_only(args):
    from playwright.async_api import async_playwright
    async with async_playwright() as playwright:
        api = await playwright.request.new_context()
        try:
            result = await preflight(api,args.url,args.expected_commit)
            print(json.dumps({"status":"preflight_passed","commit":args.expected_commit,
                              "scene_sha256":result["renderer"]["scene_revision"],"mutations":0},indent=2))
        finally:
            await api.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',help='Explicit running GPU application origin, e.g. http://127.0.0.1:8100')
    parser.add_argument('--output',type=Path,help='New exclusive directory; never overwritten')
    parser.add_argument('--expected-commit',help='Exact deployed 40-character Git commit required by both services')
    parser.add_argument('--plan',action='store_true',help='Print storyboard offline; no connection or files')
    parser.add_argument('--preflight-only',action='store_true',help='Read release/GPU/preview evidence only; no mutations or files')
    args = parser.parse_args()
    if args.plan:
        print(json.dumps({'target_content_seconds':TARGET_SECONDS,'resolution':RESOLUTION,
                          'chapters':[{'start_seconds':s,'title':t,'caption':c} for s,t,c in PLAN]},indent=2))
        return
    if not args.url or not args.expected_commit:
        parser.error('--url and --expected-commit are required')
    parsed = urlsplit(args.url)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'}:
        parser.error('--url must be an http(s) origin without credentials, path, query or fragment')
    args.url = args.url.rstrip('/')
    if not re.fullmatch(r'[a-f0-9]{40}',args.expected_commit):
        parser.error('--expected-commit must be the full lowercase 40-character Git commit')
    if args.preflight_only:
        asyncio.run(preflight_only(args))
        return
    if not args.output:
        parser.error('--output is required for capture')
    if args.output.exists():
        parser.error('--output already exists; choose a new take directory')
    asyncio.run(record(args))


if __name__ == '__main__':
    main()
