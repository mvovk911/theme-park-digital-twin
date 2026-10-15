"""Live browser / synthetic API / native OVRTX integration smoke test.

Requires the running GPU POC. Changes shared synthetic scenarios and camera,
then restores normal operations. All operational actions remain in the audit.

Install: pip install playwright && python -m playwright install chromium
Run: PARK_URL=http://127.0.0.1:8100 python tests/browser_smoke.py
Optional PARK_SCREENSHOTS changes the default docs/images evidence directory.
"""

import asyncio, json, pathlib, os
from datetime import datetime, timezone
from playwright.async_api import async_playwright

BASE = os.environ.get("PARK_URL", "http://127.0.0.1:8100").rstrip("/")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(os.environ.get("PARK_SCREENSHOTS", str(ROOT / "docs/images")))
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(
            viewport={"width": 1600, "height": 1150}, device_scale_factor=1
        )
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            await page.request.post(BASE + "/api/view", data={"mode": "live"})
            await page.goto(BASE, wait_until="domcontentloaded")
            await page.wait_for_function(
                "document.querySelector('#kpi-attendance').textContent !== '—'"
            )
            print("Operational data loaded. Waiting for GPU frame.", flush=True)
            await page.wait_for_selector("#viewport.frame-ready", timeout=240000)
            assert await page.locator(".system-card").count() == 10
            assert await page.locator("#asset-select option").count() == 12
            await page.wait_for_timeout(1500)
            status = await (await page.request.get(BASE + "/render/status")).json()
            assert status["ready"] and status["frame"] > 0
            print(
                "GPU ready: "
                + json.dumps(
                    {
                        k: status.get(k)
                        for k in ["fps", "frame", "ovrtx_version", "ovstage_version"]
                    }
                ),
                flush=True,
            )
            await page.request.post(BASE + "/api/actions", data={"action": "reset"})
            await page.locator("#camera-home").click()
            await page.wait_for_timeout(1500)
            before = await (await page.request.get(BASE + "/render/status")).json()
            box = await page.locator("#viewport").bounding_box()
            await page.mouse.move(
                box["x"] + box["width"] * 0.52, box["y"] + box["height"] * 0.65
            )
            await page.mouse.down()
            await page.mouse.move(
                box["x"] + box["width"] * 0.62, box["y"] + box["height"] * 0.67, steps=8
            )
            await page.mouse.up()
            await page.wait_for_timeout(1200)
            after = await (await page.request.get(BASE + "/render/status")).json()
            assert abs(after["camera"]["yaw"] - before["camera"]["yaw"]) > 0.05
            await page.locator("#camera-zoom-in").click()
            await page.wait_for_timeout(1000)
            zoomed = await (await page.request.get(BASE + "/render/status")).json()
            assert zoomed["camera"]["radius"] < after["camera"]["radius"]
            await page.locator("#camera-home").click()
            await page.locator('[data-layer="none"]').click()
            await page.wait_for_timeout(1200)
            status = await (await page.request.get(BASE + "/render/status")).json()
            picked = []
            for aid in ["FOOD_COURT", "HOTEL", "POWER_HUB"]:
                point = next(x for x in status["projected_assets"] if x["id"] == aid)
                for dx, dy in [(0, 0), (0, 0.015), (0.012, 0.012), (-0.012, 0.01)]:
                    # Fail-closed association intentionally hides overlays/picks between
                    # source revisions. Wait for an image/data pair before clicking.
                    await page.wait_for_function("document.querySelector('#frame-context').hidden")
                    box = await page.locator("#viewport").bounding_box()
                    async with page.expect_response(
                        lambda r: "/render/pick" in r.url, timeout=22000
                    ) as response:
                        await page.mouse.click(
                            box["x"] + (point["x"] + dx) * box["width"],
                            box["y"] + (point["y"] + dy) * box["height"],
                        )
                    resp = await response.value
                    result = await resp.json()
                    picked.append(
                        {"target": aid, "status": resp.status, "result": result}
                    )
                    if result.get("asset_id") == aid:
                        await page.wait_for_function(
                            '(id)=>document.querySelector("#asset-id").textContent===id',
                            arg=result["asset_id"],
                        )
                        break
            print("Native picks: " + json.dumps(picked), flush=True)
            assert all(
                any(
                    x["target"] == aid and x["result"].get("asset_id") == aid
                    for x in picked
                )
                for aid in ["FOOD_COURT", "HOTEL", "POWER_HUB"]
            ), "Native picks did not identify every target asset"
            await page.locator("#focus-asset").click()
            await page.wait_for_timeout(1200)
            focused = await (await page.request.get(BASE + "/render/status")).json()
            assert focused["camera"]["radius"] == 83
            await page.locator('[data-layer="energy"]').click()
            await page.wait_for_timeout(500)
            await page.wait_for_function("document.querySelectorAll('.scene-label').length > 0")
            await page.locator('[data-scenario="ride_closure"]').click()
            await page.wait_for_function(
                "document.querySelector('#asset-status').textContent==='closed'"
            )
            await page.wait_for_timeout(1800)
            motion_before = await (
                await page.request.get(BASE + "/render/status")
            ).json()
            await page.wait_for_timeout(1300)
            motion_after = await (
                await page.request.get(BASE + "/render/status")
            ).json()
            assert (
                motion_before["ride_motion"]["coaster_phase"]
                == motion_after["ride_motion"]["coaster_phase"]
            ), "Closed coaster still moving"
            assert (
                motion_before["ride_motion"]["wheel_angle"]
                != motion_after["ride_motion"]["wheel_angle"]
            ), "Open wheel stopped"
            await page.locator(
                '#asset-actions [data-action="dispatch_maintenance"]'
            ).click()
            await page.wait_for_function(
                "Number(document.querySelector('#asset-orders').textContent)>0"
            )
            await page.locator("#camera-home").click()
            await page.locator('[data-layer="operations"]').click()
            await page.wait_for_timeout(1800)
            await page.evaluate("scrollTo(0,0)")
            await page.screenshot(
                path=str(OUT / "operations-ride-closure.png"), full_page=True
            )
            await page.locator('[data-scenario="water_leak"]').click()
            await page.wait_for_function(
                "document.querySelector('#asset-id').textContent==='WATER_PLANT'"
            )
            await page.locator('#asset-actions [data-action="repair_leak"]').click()
            await page.wait_for_function(
                "document.querySelector('#kpi-alerts').textContent==='0'"
            )
            await page.request.post(BASE + "/api/actions", data={"action": "reset"})
            await page.locator("#asset-select").select_option("RIDE_COASTER")
            await page.locator("#camera-home").click()
            await page.wait_for_timeout(6200)
            resumed = await (await page.request.get(BASE + "/render/status")).json()
            assert (
                resumed["ride_motion"]["coaster_phase"]
                != motion_after["ride_motion"]["coaster_phase"]
            ), "Normal coaster did not resume"
            await page.evaluate("scrollTo(0,0)")
            await page.screenshot(path=str(OUT / "operations-live.png"), full_page=True)
            await page.locator("#viewport").screenshot(
                path=str(OUT / "ovrtx-viewport.png")
            )
            await page.locator("#compare-scenarios").click()
            await page.wait_for_selector(".comparison-table")
            assert await page.locator(".comparison-table tbody tr").count() == 7
            assert (await (await page.request.get(BASE + "/api/state")).json())[
                "scenario"
            ] == "normal"
            await page.screenshot(path=str(OUT / "scenario-comparison.png"))
            await page.locator(".close-comparison").click()
            await page.locator('.system-card[data-system="erp"]').click()
            await page.locator('[data-source-tab="raw"]').click()
            await page.wait_for_selector("#source-feed pre")
            assert "stock_units" in await page.locator("#source-feed").inner_text()
            await page.locator(".close-system").click()
            await page.locator("#show-system-map").click()
            await page.screenshot(path=str(OUT / "connected-architecture.png"))
            await page.locator("#close-architecture").click()
            assert not await page.evaluate(
                "document.documentElement.scrollWidth>innerWidth"
            )
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.evaluate("scrollTo(0,0)")
            await page.wait_for_timeout(500)
            assert not await page.evaluate(
                "document.documentElement.scrollWidth>innerWidth"
            )
            await page.screenshot(path=str(OUT / "mobile-live.png"), full_page=True)
            report = {
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "comparison_read_only": True,
                "source_payload": True,
                "desktop_overflow": False,
                "page_errors": errors,
                "renderer": {
                    k: status.get(k)
                    for k in [
                        "engine",
                        "fps",
                        "frame",
                        "ovrtx_version",
                        "ovstage_version",
                        "source_identity",
                        "scene_revision",
                        "accepted_state_revision",
                        "camera_token",
                        "rendered_at",
                        "source_timestamp",
                        "source_tick",
                    ]
                },
                "native_picks": picked,
                "camera_orbit": True,
                "camera_zoom": True,
                "camera_focus": True,
                "overlay": True,
                "closure_dispatch": True,
                "motion_closure": {
                    "before": motion_before["ride_motion"],
                    "after": motion_after["ride_motion"],
                    "resumed": resumed["ride_motion"],
                },
                "leak_repair": True,
                "mobile_overflow": False,
            }
            (OUT / "browser-validation.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2), flush=True)
            assert not errors
        finally:
            # Shared POC: restore normal state even after a failed check; preserve audit.
            for path, payload in [
                ("/api/view", {"mode": "live"}),
                ("/api/actions", {"action": "reset"}),
                ("/render/control", {"action": "home"}),
                ("/render/control", {"action": "layer", "layer": "operations"}),
            ]:
                try:
                    await page.request.post(BASE + path, data=payload, timeout=6000)
                except Exception:
                    pass
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
