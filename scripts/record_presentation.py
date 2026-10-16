"""Record a ~200-second presentation of the actual GPU application.

Requires Playwright/Chromium and an already running, verified GPU release.
This changes shared synthetic scenarios, connector modes, view and camera.
No mock renderer, synthetic screenshots or fabricated UI values are used.

  env -u NODE_OPTIONS python scripts/record_presentation.py \
    --url http://127.0.0.1:18765 --output /path/to/new/capture-directory

The output directory must not already exist. The raw browser video is 1920x960;
postproduction can add a 120px caption band for a 1920x1080 presentation.
Use --plan to print the storyboard without connecting or writing files.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urlsplit


PLAN = [
    (0, "One park, one shared picture", "Actual OVRTX rendering; all source data, scenarios and operational actions are synthetic."),
    (14, "Explore the connected park", "Orbit, zoom and click scene geometry to resolve its asset identity and connected data."),
    (38, "Compare, respond and trace", "Compare a modeled ride closure, apply it, dispatch maintenance and inspect the audit trail."),
    (70, "Understand utility dependencies", "Trace logical power dependencies, shed flexible load and simulate a water-leak repair."),
    (100, "Coordinate guests and wellbeing", "Respond to show-departure demand and heatwave scenarios with rerouting and qualified staff."),
    (124, "Connect inventory to operations", "A food-rush scenario connects queues, staffing and ERP inventory to a replenishment action."),
    (140, "Inspect sources and their quality", "Explore the API architecture, then pause a source and watch accepted observations become stale."),
    (172, "Replay a recorded moment", "Review recorded state in a shared read-only view; camera navigation remains interactive."),
    (195, "Return to live operations", "One asset backbone connects operations, source provenance, recorded history and the real rendered scene."),
]
TARGET_SECONDS = 200
CURSOR_SCRIPT = r"""
(() => {
  const style=document.createElement('style');
  style.textContent=`#presentation-pointer{position:fixed;left:0;top:0;width:19px;height:19px;border:2px solid white;border-radius:50%;background:#214f40bb;box-shadow:0 1px 6px #0008;transform:translate(-50%,-50%);pointer-events:none;z-index:2147483647;transition:width .1s,height .1s}#presentation-pointer.pressed{width:32px;height:32px;background:#d1e78b99}`;
  document.head.append(style);
  const pointer=document.createElement('div');pointer.id='presentation-pointer';pointer.setAttribute('aria-hidden','true');document.body.append(pointer);
  document.addEventListener('pointermove',event=>{pointer.style.left=event.clientX+'px';pointer.style.top=event.clientY+'px';});
  document.addEventListener('pointerdown',()=>pointer.classList.add('pressed'));
  document.addEventListener('pointerup',()=>pointer.classList.remove('pressed'));
})();
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


async def finalize_capture(*, context, browser, video, api, response_tasks, post,
                           manifest, output, recording_end_seconds):
    """Finalize evidence without letting media failures skip park restoration."""
    errors = []

    def note(phase, error):
        errors.append(error)
        manifest.setdefault("finalization_errors", []).append({"phase": phase, "error": f"{type(error).__name__}: {error}"})

    async def close(phase, operation):
        try:
            await asyncio.wait_for(operation(), timeout=20)
        except Exception as error:
            note(phase, error)

    try:
        if context:
            manifest["recording_end_seconds"] = recording_end_seconds
            await close("browser_context.close", context.close)
        if browser:
            # Also attempt this if context.close failed; it can still finalize video.
            await close("browser.close", browser.close)
        if video:
            try:
                video_path = await asyncio.wait_for(video.path(), timeout=15)
                manifest["original_video_path"] = str(video_path)
                target = output / "presentation-raw.webm"
                shutil.move(str(video_path), target)
                manifest["video"] = target.name
                if shutil.which("ffprobe"):
                    try:
                        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(target)], capture_output=True, text=True, timeout=20)
                        if probe.returncode == 0:
                            manifest["video_duration_seconds"] = float(json.loads(probe.stdout)["format"]["duration"])
                            manifest["duration_seconds"] = manifest["video_duration_seconds"]
                            manifest["duration_basis"] = "Measured video container duration from ffprobe"
                        else:
                            manifest["duration_probe_error"] = probe.stderr[:1000]
                    except Exception as error:
                        # Duration probing is optional; keep the valid video and
                        # explicit monotonic fallback even if ffprobe is broken.
                        manifest["duration_probe_error"] = f"{type(error).__name__}: {error}"
            except Exception as error:
                note("video_finalization", error)
            finally:
                if "duration_seconds" not in manifest:
                    manifest["duration_seconds"] = manifest.get("recording_content_end_seconds", recording_end_seconds)
                    manifest["duration_basis"] = "Monotonic content timing; container duration not measured"
        if response_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*list(response_tasks), return_exceptions=True), timeout=5)
            except Exception as error:
                note("response_observations", error)
    finally:
        # The API context stays alive until restoration has been attempted,
        # independently of context.close, video.path, move or probe failures.
        try:
            if "preflight" in manifest:
                for path, data in [("/api/view", {"mode": "live"}), ("/api/connectors/water/simulation", {"mode": "live"}), ("/api/actions", {"action": "reset"}), ("/render/control", {"action": "home"}), ("/render/control", {"action": "layer", "layer": "operations"})]:
                    try:
                        await post(path, data)
                        manifest["cleanup"].append({"path": path, "ok": True})
                    except Exception as error:
                        manifest["cleanup"].append({"path": path, "ok": False, "error": str(error)})
        finally:
            if api:
                await close("api.dispose", api.dispose)
    return errors


async def record(args):
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    manifest = {
        "started_at": utc_now(), "url": args.url, "status": "preflight",
        "evidence_kind": "actual_browser_and_gpu_application",
        "operational_data": "All demonstrated source data, scenarios and actions are synthetic.",
        "editorial_overlay": "Visible pointer/click indicator only; no values or application graphics replaced.",
        "resolution": {"width": 1920, "height": 960},
        "target_presentation_seconds": TARGET_SECONDS,
        "timing_basis": "Monotonic since recorded page creation; first-video-frame alignment is approximate.",
        "chapters": [], "actions": [], "page_errors": [], "native_picks": [],
        "cleanup": [], "frame_samples": [],
    }
    browser = context = page = api = video = None
    recording_zero = presentation_zero = None
    frame_headers = {}
    response_tasks = set()
    closure_record = None
    failed = None

    def elapsed():
        return round(time.monotonic() - recording_zero, 3) if recording_zero else None

    def persist():
        (output / "capture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (output / "chapters.json").write_text(json.dumps(manifest["chapters"], indent=2) + "\n")

    async def get(path):
        # Read-only metadata can retry transport failures. Mutating POSTs below
        # are deliberately never retried by this recording script.
        for attempt in range(3):
            try:
                response = await api.get(args.url + path, timeout=12000)
                if not response.ok:
                    raise RuntimeError(f"GET {path}: HTTP {response.status}")
                return await response.json()
            except RuntimeError:
                raise  # Authentication, missing endpoints and HTTP errors fail fast.
            except Exception as error:
                if attempt == 2:
                    raise
                manifest.setdefault("metadata_retries", []).append({"path": path, "attempt": attempt + 1, "at_seconds": elapsed(), "error": str(error)})
                await asyncio.sleep(.5 * (attempt + 1))

    async def post(path, data):
        response = await api.post(args.url + path, data=data, timeout=15000)
        if not response.ok:
            raise RuntimeError(f"POST {path}: HTTP {response.status}: {(await response.text())[:250]}")
        return await response.json()

    async def capture_response(response):
        try:
            path = urlsplit(response.url).path
            if path == "/render/frame.jpg" and response.ok:
                headers = await response.all_headers()
                ident = headers.get("x-frame-number")
                if ident:
                    frame_headers[ident] = {key: value for key, value in headers.items() if key.startswith("x-")}
                    while len(frame_headers) > 80:
                        del frame_headers[next(iter(frame_headers))]
            elif response.request.method == "POST" and path.startswith(("/api/", "/render/pick")):
                try:
                    body = await response.json()
                except Exception:
                    body = {"message": (await response.text())[:300]}
                manifest["actions"].append({"at_seconds": elapsed(), "path": path, "status": response.status, "response": body})
        except Exception as error:
            manifest.setdefault("capture_observation_errors", []).append(str(error))

    def on_response(response):
        task = asyncio.create_task(capture_response(response))
        response_tasks.add(task)
        task.add_done_callback(response_tasks.discard)

    async def hold_until(second):
        delay = presentation_zero + second - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    async def focus(selector, margin=24):
        await page.locator(selector).first.evaluate(
            "(element,margin)=>window.scrollTo({top:Math.max(0,element.getBoundingClientRect().top+scrollY-margin),behavior:'smooth'})", margin)
        await page.wait_for_timeout(650)

    async def click(selector, pause=0.55):
        locator = page.locator(selector).first
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        if box:
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=12)
        await locator.click(timeout=12000)
        await asyncio.sleep(pause)

    async def choose_asset(asset_id):
        await page.locator("#asset-select").scroll_into_view_if_needed()
        await page.locator("#asset-select").select_option(asset_id)
        await page.wait_for_function("id=>document.querySelector('#asset-id').textContent===id", arg=asset_id)
        await page.wait_for_timeout(600)

    async def scenario(name):
        await click(f'[data-scenario="{name}"]')
        await page.wait_for_function(
            "name=>document.querySelector('[data-scenario=\"'+name+'\"]').classList.contains('active')&&!document.querySelector('[data-scenario=\"'+name+'\"]').disabled", arg=name)
        await focus(".viewport-card")
        await page.wait_for_timeout(900)

    async def chapter(index):
        nonlocal closure_record
        planned, title, caption = PLAN[index]
        await hold_until(planned)
        if manifest["chapters"]:
            manifest["chapters"][-1]["end_seconds"] = elapsed()
        item = {"start_seconds": elapsed(), "planned_presentation_second": planned, "title": title, "caption": caption}
        manifest["chapters"].append(item)
        if page:
            image_frame = await page.locator("#render-frame").get_attribute("data-frame")
            if image_frame in frame_headers:
                manifest["frame_samples"].append({"chapter": title, "at_seconds": elapsed(), "headers": frame_headers[image_frame]})
        persist()
        print(f"[{elapsed():6.1f}s] {title}", flush=True)

    async def native_pick(asset_id):
        await click('[data-layer="none"]', .2)
        await click("#camera-home", .8)
        for attempt, (dx, dy) in enumerate([(0, 0), (0, .015), (.012, .012), (-.012, .01), (0, .015), (0, 0)], 1):
            await page.wait_for_function("document.querySelector('#frame-context').hidden", timeout=8000)
            ident = await page.locator("#render-frame").get_attribute("data-frame")
            headers = frame_headers.get(ident)
            if not headers:
                await page.wait_for_timeout(180)
                continue
            image_context = json.loads(headers["x-frame-context"])
            point = next(item for item in image_context["projected_assets"] if item["id"] == asset_id and item["visible"])
            box = await page.locator("#viewport").bounding_box()
            ratio = image_context["width"] / image_context["height"]
            width = min(box["width"], box["height"] * ratio)
            height = width / ratio
            x = box["x"] + (box["width"] - width) / 2 + (point["x"] + dx) * width
            y = box["y"] + (box["height"] - height) / 2 + (point["y"] + dy) * height
            await page.mouse.move(x, y, steps=14)
            try:
                async with page.expect_response(lambda response: urlsplit(response.url).path == "/render/pick", timeout=6500) as pending:
                    await page.mouse.click(x, y)
                response = await pending.value
                result = await response.json()
                manifest["native_picks"].append({"attempt": attempt, "at_seconds": elapsed(), "target": asset_id, "status": response.status, "result": result})
                if response.ok and result.get("asset_id") == asset_id:
                    await page.wait_for_function("id=>document.querySelector('#asset-id').textContent===id", arg=asset_id)
                    return
            except PlaywrightTimeout:
                manifest["native_picks"].append({"attempt": attempt, "target": asset_id, "result": "No pick response; image/view association may have changed."})
            await page.wait_for_timeout(250)
        raise RuntimeError("Native GPU picking did not resolve the requested asset; recording is not accepted.")

    try:
        async with async_playwright() as playwright:
            api = await playwright.request.new_context()
            try:
                state, render = await asyncio.gather(get("/api/view/state"), get("/render/status"))
                identity = render.get("source_identity", {})
                if not render.get("ready") or "NVIDIA OVRTX" not in render.get("engine", ""):
                    raise RuntimeError("The actual NVIDIA OVRTX service is not ready.")
                if identity.get("disposition") != "verified_manifest" or identity.get("verified") is not True:
                    raise RuntimeError("GPU release source identity is not a verified manifest.")
                if render.get("scene_revision") != identity.get("scene_sha256"):
                    raise RuntimeError("Renderer scene revision does not match its release manifest.")
                frame = await api.get(args.url + "/render/frame.jpg", timeout=12000)
                if not frame.ok or "image/jpeg" not in frame.headers.get("content-type", "") or not (await frame.body()).startswith(b"\xff\xd8"):
                    raise RuntimeError("GPU service did not return an actual JPEG frame.")
                if not frame.headers.get("x-source-revision") or not frame.headers.get("x-frame-context"):
                    raise RuntimeError("GPU JPEG lacks exact frame provenance.")
                manifest["preflight"] = {"renderer": render, "view": state.get("view"), "frame_headers": {key: value for key, value in frame.headers.items() if key.startswith("x-")}}
                # Prepare the shared synthetic demonstration before video starts.
                await post("/api/view", {"mode": "live"})
                await post("/api/connectors/water/simulation", {"mode": "live"})
                await post("/api/actions", {"action": "reset"})
                await post("/render/control", {"action": "home"})
                await post("/render/control", {"action": "layer", "layer": "operations"})
                browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context(viewport={"width": 1920, "height": 960}, device_scale_factor=1,
                                                    record_video_dir=str(raw), record_video_size={"width": 1920, "height": 960})
                page = await context.new_page()
                recording_zero = time.monotonic()
                video = page.video
                page.on("pageerror", lambda error: manifest["page_errors"].append(str(error)))
                page.on("response", on_response)
                await page.goto(args.url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_selector("#viewport.frame-ready", timeout=20000)
                await page.wait_for_function("document.querySelector('#kpi-attendance').textContent!=='—'")
                await page.evaluate(CURSOR_SCRIPT)
                presentation_zero = time.monotonic()
                manifest["status"] = "recording"
                manifest["presentation_start_seconds"] = elapsed()

                await chapter(0)
                await page.wait_for_timeout(3500)
                await focus(".viewport-card")
                await click('[data-layer="none"]', .2)
                await page.wait_for_timeout(2000)
                await page.screenshot(path=str(output / "storyboard-overview.png"))

                await chapter(1)
                box = await page.locator("#viewport").bounding_box()
                await page.mouse.move(box["x"] + box["width"] * .5, box["y"] + box["height"] * .65)
                await page.mouse.down()
                for index in range(20):
                    await page.mouse.move(box["x"] + box["width"] * (.5 + .08 * (index + 1) / 20), box["y"] + box["height"] * .65)
                    await page.wait_for_timeout(45)
                await page.mouse.up()
                await click("#camera-zoom-in", 1)
                await native_pick("FOOD_COURT")
                await click("#focus-asset", 1.2)
                await click('[data-layer="operations"]', .5)
                await page.screenshot(path=str(output / "storyboard-inspector.png"))

                await chapter(2)
                await click("#compare-scenarios")
                await page.wait_for_selector(".comparison-table")
                await page.wait_for_timeout(4000)
                await click(".apply-comparison")
                await page.wait_for_function("document.querySelector('#asset-status').textContent.startsWith('closed')")
                await focus(".viewport-card")
                await click("#camera-home", 2)
                await click('#asset-actions [data-action="dispatch_maintenance"]')
                await page.wait_for_function("Number(document.querySelector('#asset-orders').textContent)>0")
                await page.wait_for_timeout(2500)
                await focus("#activity-section")
                await page.wait_for_timeout(2400)
                records = (await get("/api/timeline?limit=300"))["snapshots"]
                closure_record = next((item["id"] for item in reversed(records) if item["scenario"] == "ride_closure"), None)

                await chapter(3)
                await scenario("power_fault")
                await click('[data-layer="dependencies"]', 2)
                await click('#asset-actions [data-action="shed_load"]', 1)
                await focus("#dependency-card")
                await page.wait_for_timeout(1800)
                await scenario("water_leak")
                await click('[data-layer="energy"]', 1)
                await click('#asset-actions [data-action="repair_leak"]')
                await page.wait_for_function("document.querySelector('#kpi-alerts').textContent==='0'")
                await page.wait_for_timeout(1500)

                await chapter(4)
                await scenario("show_surge")
                await click('[data-layer="crowds"]', 2)
                await click('#asset-actions [data-action="add_staff"]', 1.5)
                await click('#asset-actions [data-action="reroute_guests"]', 1)
                await focus(".viewport-card")
                await page.wait_for_timeout(2000)

                await scenario("heatwave")
                await click('#asset-actions [data-action="add_staff"]', 1.5)
                await focus(".response-card")
                await page.wait_for_timeout(1200)

                await chapter(5)
                await scenario("food_rush")
                await click('[data-layer="operations"]', 1)
                await page.wait_for_timeout(1600)
                await click('#asset-actions [data-action="replenish_stock"]', 1.5)
                await focus(".inspector")
                await page.wait_for_timeout(1800)

                await chapter(6)
                await scenario("normal")
                await focus("#systems-section")
                await page.wait_for_timeout(1300)
                await click("#show-system-map", 3.5)
                await click("#close-architecture")
                await click('.system-card[data-system="water"]')
                await page.wait_for_selector(".observation-table")
                await click('[data-connector-mode="paused"]', .3)
                await page.wait_for_function("document.querySelector('#source-health-status').textContent.toLowerCase()==='stale'", timeout=15000)
                await page.wait_for_timeout(1800)
                await click('[data-connector-mode="offline"]', 1.5)
                await click('[data-connector-mode="live"]')
                await page.wait_for_function("document.querySelector('#source-health-status').textContent.toLowerCase()==='healthy'", timeout=10000)
                await click('[data-source-tab="raw"]', 1.5)
                await page.screenshot(path=str(output / "storyboard-sources.png"))
                await click(".close-system")

                await chapter(7)
                await focus(".timeline-bar")
                records = sorted((await get("/api/timeline?limit=300"))["snapshots"], key=lambda item: item["id"])
                index = next((index for index, item in enumerate(records) if item["id"] == closure_record), max(0, len(records) - 25))
                slider = page.locator("#timeline-range")
                await slider.scroll_into_view_if_needed()
                box = await slider.bounding_box()
                fraction = index / max(1, len(records) - 1)
                x, y = box["x"] + 8 + (box["width"] - 16) * fraction, box["y"] + box["height"] / 2
                await page.mouse.move(x, y, steps=15)
                await page.mouse.click(x, y)
                await page.wait_for_selector("#replay-banner:not([hidden])")
                if not await page.locator("#compare-scenarios").is_disabled():
                    raise RuntimeError("Replay comparison control is unexpectedly enabled.")
                manifest["recorded_view"] = (await get("/api/view/state"))["view"]
                await choose_asset("RIDE_COASTER")
                await focus("#replay-banner")
                await page.wait_for_timeout(3000)
                await page.screenshot(path=str(output / "storyboard-replay.png"))
                await focus(".viewport-card")
                await click("#camera-zoom-in", 1.5)
                await click("#return-live")
                await page.wait_for_function("document.querySelector('#replay-banner').hidden&&!document.querySelector('#compare-scenarios').disabled")
                await click("#camera-home", .8)
                await click('[data-layer="operations"]', .3)

                await chapter(8)
                await focus(".viewport-card")
                await hold_until(TARGET_SECONDS)
                manifest["chapters"][-1]["end_seconds"] = elapsed()
                manifest["recording_content_end_seconds"] = elapsed()
                manifest["final_renderer"] = await get("/render/status")
                if manifest["final_renderer"].get("source_identity", {}).get("commit") != identity.get("commit"):
                    raise RuntimeError("GPU release changed during recording.")
                if manifest["page_errors"]:
                    raise RuntimeError("Browser page errors occurred; inspect the manifest.")
                manifest["status"] = "captured"
            except Exception as error:
                failed = error
                manifest["status"] = "failed"
                manifest["error"] = f"{type(error).__name__}: {error}"
                if page:
                    try:
                        await page.screenshot(path=str(output / "failure.png"))
                    except Exception:
                        pass
            finally:
                finalization_errors = await finalize_capture(
                    context=context, browser=browser, video=video, api=api,
                    response_tasks=response_tasks, post=post, manifest=manifest,
                    output=output, recording_end_seconds=elapsed())
                if finalization_errors and failed is None:
                    failed = finalization_errors[0]
                    manifest["status"] = "failed"
                    manifest["error"] = f"{type(failed).__name__}: {failed}"

    finally:
        manifest["finished_at"] = utc_now()
        persist()
    if failed:
        raise failed
    print(json.dumps({"status": manifest["status"], "video": str(output / "presentation-raw.webm"), "duration_seconds": manifest.get("duration_seconds"), "chapters": len(manifest["chapters"])}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Explicit URL of the actual, verified running GPU application")
    parser.add_argument("--output", type=Path, help="New exclusive output directory; must not exist")
    parser.add_argument("--plan", action="store_true", help="Print storyboard only; do not connect or write")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps({"target_seconds": TARGET_SECONDS, "browser_resolution": [1920, 960], "chapters": [{"start_seconds": start, "title": title, "caption": caption} for start, title, caption in PLAN]}, indent=2))
        return
    if not args.url or not args.output:
        parser.error("--url and --output are required for capture")
    args.url = args.url.rstrip("/")
    if urlsplit(args.url).scheme not in {"http", "https"}:
        parser.error("--url must use http or https")
    if args.output.exists():
        parser.error("--output must name a new directory; existing captures are never overwritten")
    asyncio.run(record(args))


if __name__ == "__main__":
    main()
