"""Replay, source quality and frame-provenance acceptance checks.

Pure JavaScript checks (Node only; no browser/GPU claim):
    python tests/browser_extended.py --logic-only

Browser checks against a running POC (changes shared synthetic state):
    PARK_URL=http://127.0.0.1:8100 python tests/browser_extended.py

Add --mock-renderer to exercise frame freshness deterministically using an
explicitly labeled CPU image fixture. This never validates NVIDIA rendering.
Evidence uses a separate extended/offline folder; original GPU captures remain
untouched. Requires playwright and an installed Chromium for browser checks.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("PARK_URL", "http://127.0.0.1:8100").rstrip("/")


LOGIC_CHECKS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor() {
    this.textContent=''; this.innerHTML=''; this.hidden=false; this.disabled=false;
    this.style={}; this.dataset={}; this.attributes=new Map(); this.children=[]; this.parts=new Map();
    const classes=new Set();
    this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle:(x,on)=>{const yes=on===undefined?!classes.has(x):on;yes?classes.add(x):classes.delete(x);return yes;}};
  }
  querySelector(selector) {if(!this.parts.has(selector))this.parts.set(selector,new Element());return this.parts.get(selector);}
  querySelectorAll(){return [];}
  setAttribute(key,value){this.attributes.set(key,String(value));}
  toggleAttribute(key,on){if(on)this.attributes.set(key,'');else this.attributes.delete(key);}
  hasAttribute(key){return this.attributes.has(key);}
  append(...elements){this.children.push(...elements);}
  replaceChildren(...elements){this.children=[...elements];}
  get firstElementChild(){return this.children[0];}
  get lastElementChild(){return this.children.at(-1);}
}
const elements=new Map(), groups=new Map();
const byId=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
for(const selector of ['.scenario-chip','[data-action]','[data-connector-mode]','.actions-section > .action-note'])groups.set(selector,[new Element(),new Element()]);
const document={getElementById:byId,querySelectorAll:s=>groups.get(s)||[],createElement:()=>new Element(),body:new Element()};
const context=vm.createContext({document,Date,Map,Set,Number,String,Math,Array,JSON,Promise,setTimeout:()=>0,clearTimeout:()=>{},console});
let source=fs.readFileSync(process.argv[1],'utf8');
const marker='\n  bindEvents();\n';
assert.equal(source.split(marker).length,2,'Test entry point must be unique');
source=source.replace(marker,`\n  globalThis.testHooks={fieldNumber,fieldUnknown,fieldModeled,alertProvenance,assetStatus,observationValue,frameMatchesView,metadataFromHeaders,updateFrameContext,updateWriteControls,renderView,dependencyEdges,renderDependencyLines,
 setSnapshot(value){snapshot=value;},setRenderer(value){renderer=value;},setSelected(value){selectedId=value;},setLayer(value){currentLayer=value;},
 setFrame(value){frameMetadata=value;lastFrameReceived=Date.now();lastUniqueFrameAt=Date.now();},setPending(value){viewPending=value;}};return;\n`);
vm.runInContext(source,context,{filename:process.argv[1]});
const t=context.testHooks, checks=[];
const check=(name,fn)=>{fn();checks.push(name);};
const asset={id:'RIDE_COASTER',status:'operational',power_kw:220,queue_minutes:24,data_quality:{fields:{power_kw:{status:'unknown'},status:{status:'unknown'}}}};
check('unknown fields never appear as observed baseline values',()=>{assert.equal(t.fieldNumber(asset,'power_kw'),'—');assert.equal(t.assetStatus(asset),'unknown');assert.equal(t.fieldNumber(asset,'queue_minutes'),'24');assert.equal(t.observationValue({value:99,quality:{status:'unknown'}}),'—');assert.equal(t.observationValue({value:null}),'—');});
check('unmapped values are modeled only with explicit read-model semantics',()=>{t.setSnapshot({});assert.equal(t.fieldModeled(asset,'queue_minutes'),false);t.setSnapshot({read_model:{unmapped_fields_origin:'synthetic_model'}});assert.equal(t.fieldModeled(asset,'queue_minutes'),true);assert.equal(t.fieldModeled(asset,'power_kw'),false);assert.equal(t.fieldUnknown(asset,'power_kw'),true);});
check('alert provenance distinguishes model evidence and accepted source quality',()=>{const label=t.alertProvenance({origin:'canonical_rule',evidence:[{metric:'status',origin:'accepted_observation',source_id:'ride_scada',quality:'stale'},{metric:'capacity',origin:'synthetic_model'}]});assert.match(label,/Operational rule/);assert.match(label,/ride_scada · stale/);assert.match(label,/Capacity: modeled/);});
const live={view:{mode:'live'},assets:[]};
const replay={view:{mode:'replay',snapshot_id:17,captured_at:new Date().toISOString(),source_timestamp:new Date().toISOString(),recorded_motion:null,scene_matches_current:true},assets:[]};
check('recorded view disables all operational mutations and comparison',()=>{t.setSnapshot(replay);t.updateWriteControls();for(const selector of ['.scenario-chip','[data-action]','[data-connector-mode]'])assert.ok(groups.get(selector).every(e=>e.disabled));assert.ok(byId('compare-scenarios').disabled);assert.equal(byId('camera-home').disabled,false);});
check('live view restores mutation controls',()=>{t.setSnapshot(live);t.updateWriteControls();for(const selector of ['.scenario-chip','[data-action]','[data-connector-mode]'])assert.ok(groups.get(selector).every(e=>!e.disabled));assert.equal(byId('compare-scenarios').disabled,false);});
check('view changes lock writes before response arrives',()=>{t.setPending(true);t.updateWriteControls();assert.ok(groups.get('[data-action]').every(e=>e.disabled));t.setPending(false);});
check('uncaptured historical motion is explicitly disclosed',()=>{t.setSnapshot(replay);t.renderView();assert.equal(byId('replay-banner').hidden,false);assert.match(byId('replay-pose-note').textContent,/not historical evidence/);});
const oldTime=new Date(Date.now()-30000).toISOString(), nowTime=new Date().toISOString();
check('JPEG headers override newer renderer-status timestamps',()=>{t.setRenderer({frame:999,rendered_at:nowTime,view_mode:'live'});const meta=t.metadataFromHeaders(new Headers({'X-Frame-Number':'12','X-Frame-Rendered-At':oldTime,'X-Source-Timestamp':oldTime,'X-Source-Tick':'3','X-View-Mode':'replay','X-View-Snapshot-Id':'17','X-Pose-Source':'unrecorded'}));assert.equal(meta.frame,12);assert.equal(meta.renderedAt,oldTime);assert.equal(meta.snapshotId,'17');t.setFrame(meta);assert.ok(t.frameMatchesView());});
check('missing image identity cannot borrow a fresh status timestamp',()=>{const meta=t.metadataFromHeaders(new Headers());assert.equal(meta.frame,null);assert.equal(meta.renderedAt,null);assert.equal(meta.viewMode,null);});
check('repeated delivery of old frame remains visibly stale',()=>{t.updateFrameContext();assert.ok(byId('viewport').classList.contains('frame-stale'));assert.match(byId('frame-context').textContent,/LAST GPU IMAGE/);assert.match(byId('frame-freshness').textContent,/Frame #12/);assert.ok(byId('frame-freshness').textContent.includes(new Date(oldTime).toLocaleTimeString('en-GB',{timeZone:'UTC',hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'})));});
check('replay image identity must match selected record',()=>{t.setFrame({frame:13,renderedAt:nowTime,viewMode:'live',sourceTimestamp:nowTime});assert.equal(t.frameMatchesView(),false);t.updateFrameContext();assert.match(byId('frame-context').textContent,/VIEW SWITCH IN PROGRESS/);t.setFrame({frame:14,renderedAt:nowTime,viewMode:'replay',snapshotId:18,sourceTimestamp:nowTime});assert.equal(t.frameMatchesView(),false);});
check('fresh frames cannot hide degraded status-source quality',()=>{t.setSnapshot(live);t.setFrame({frame:15,renderedAt:nowTime,viewMode:'live',sourceTimestamp:nowTime,poseSource:'stale_frozen'});t.updateFrameContext();assert.ok(byId('viewport').classList.contains('source-stale'));assert.match(byId('frame-context').textContent,/affected ride poses frozen/);assert.equal(byId('renderer-badge').querySelector('span').textContent,'STALE SOURCE');});
const graph={view:{mode:'live'},assets:[{id:'POWER_HUB',name:'Power',status:'fault',dependencies:[]},{id:'WATER_PLANT',name:'Water',status:'operational',dependencies:['POWER_HUB']},{id:'FOOD_COURT',name:'Food',status:'warning',dependencies:['POWER_HUB','WATER_PLANT']}]};
check('dependency graph includes upstream and downstream service relations',()=>{t.setSnapshot(graph);t.setSelected('FOOD_COURT');const edges=JSON.parse(JSON.stringify(t.dependencyEdges()));assert.equal(edges.length,3);assert.ok(edges.some(e=>e.from==='WATER_PLANT'&&e.to==='FOOD_COURT'));});
check('unobserved dependency baseline is excluded',()=>{const copy=JSON.parse(JSON.stringify(graph));copy.assets[2].data_quality={fields:{dependencies:{status:'unknown'}}};t.setSnapshot(copy);assert.equal(t.dependencyEdges().length,0);});
check('dependency SVG uses the hidden attribute correctly',()=>{t.setSnapshot(graph);t.setSelected('POWER_HUB');t.setLayer('dependencies');t.setFrame({frame:16,renderedAt:nowTime,viewMode:'live',sourceTimestamp:nowTime,poseSource:'live'});t.setRenderer({ready:true,width:1280,height:720,projected_assets:[{id:'POWER_HUB',visible:true,x:.2,y:.3},{id:'WATER_PLANT',visible:true,x:.4,y:.6},{id:'FOOD_COURT',visible:true,x:.8,y:.5}]});byId('viewport').clientWidth=1280;byId('viewport').clientHeight=720;t.renderDependencyLines();assert.equal(byId('dependency-lines').hasAttribute('hidden'),false);assert.match(byId('dependency-lines').innerHTML,/dependency-edge fault/);t.setLayer('none');t.renderDependencyLines();assert.ok(byId('dependency-lines').hasAttribute('hidden'));});
console.log(JSON.stringify({kind:'javascript_logic_checks_not_browser_or_gpu',passed:checks.length,checks},null,2));
"""


def logic_checks():
    html = (ROOT / "frontend/index.html").read_text()
    javascript = (ROOT / "frontend/app.js").read_text()
    declared = set(re.findall(r'\bid="([\w-]+)"', html + javascript))
    declared.update(re.findall(r"\.id\s*=\s*['\"]([\w-]+)['\"]", javascript))
    referenced = set(re.findall(r"(?<!\$)\$\('([\w-]+)'\)", javascript))
    missing = referenced - declared
    assert not missing, f"JavaScript references undeclared UI IDs: {sorted(missing)}"
    subprocess.run(["node", "--check", str(ROOT / "frontend/app.js")], check=True)
    subprocess.run(["node", "-e", LOGIC_CHECKS, str(ROOT / "frontend/app.js")], check=True)
    print(f"DOM identifier contract: {len(referenced)} referenced IDs resolved.")


async def browser_checks(mock_renderer: bool):
    from playwright.async_api import async_playwright

    output = Path(os.environ.get("PARK_SCREENSHOTS", str(ROOT / "docs/images" / ("offline-ui" if mock_renderer else "extended-ui"))))
    output.mkdir(parents=True, exist_ok=True)
    errors, browser_requests = [], []
    fixture = {"frame": 0, "metadata": None, "freeze": False, "degraded": False, "hold_view": False}
    placeholder = '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#213b36"/><text x="640" y="340" text-anchor="middle" fill="#c7d8b4" font-family="sans-serif" font-size="30">CPU UI TEST FIXTURE</text><text x="640" y="385" text-anchor="middle" fill="#9aaf8b" font-family="sans-serif" font-size="19">No GPU image or native picking is being validated.</text></svg>'

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: browser_requests.append(request.url))

        async def get(path):
            response = await page.request.get(BASE + path)
            assert response.ok, f"GET {path}: {response.status}"
            return await response.json()

        async def post(path, body):
            response = await page.request.post(BASE + path, data=body)
            assert response.ok, f"POST {path}: {response.status}"
            return await response.json()

        async def mock_render(route):
            path = route.request.url.split("/render/", 1)[1].split("?", 1)[0]
            state = await get("/api/view/state")
            view = state.get("view", {"mode": "live"})
            now = datetime.now(timezone.utc).isoformat()
            if fixture["metadata"] is None or not fixture["freeze"] and not fixture["hold_view"]:
                fixture["frame"] += 1
                fixture["metadata"] = {
                    "frame": fixture["frame"], "rendered_at": now,
                    "source_timestamp": state["timestamp"], "source_tick": state["tick"],
                    "view_mode": view["mode"], "snapshot_id": view.get("snapshot_id"),
                    "pose_source": "unrecorded" if view["mode"] == "replay" else "stale_frozen" if fixture["degraded"] else "live",
                }
            metadata = fixture["metadata"]
            if path == "status":
                payload = {**metadata, "ready": True, "fps": 0, "width": 1280, "height": 720,
                           "engine": "CPU test fixture, not OVRTX", "phase": "test_fixture",
                           "projected_assets": [{"id": asset["id"], "visible": True, "x": .15 + (index % 4) * .21, "y": .25 + (index // 4) * .22} for index, asset in enumerate(state["assets"])]}
                await route.fulfill(json=payload)
            elif path == "frame.jpg":
                await route.fulfill(body=placeholder, content_type="image/svg+xml", headers={
                    "X-Frame-Number": str(metadata["frame"]), "X-Frame-Rendered-At": metadata["rendered_at"],
                    "X-Source-Timestamp": metadata["source_timestamp"], "X-Source-Tick": str(metadata["source_tick"]),
                    "X-View-Mode": metadata["view_mode"], "X-View-Snapshot-Id": str(metadata["snapshot_id"] or ""),
                    "X-Pose-Source": metadata["pose_source"], "Cache-Control": "no-store"})
            elif path == "control":
                await route.fulfill(json={"accepted": True, "test_fixture": True})
            else:
                await route.fulfill(status=503, json={"detail": "Native picking is not available in a CPU fixture"})

        try:
            await post("/api/view", {"mode": "live"})
            await post("/api/connectors/water/simulation", {"mode": "live"})
            await post("/api/actions", {"action": "reset"})
            if mock_renderer:
                await page.route("**/render/**", mock_render)
            await page.goto(BASE, wait_until="domcontentloaded")
            await page.wait_for_function("document.querySelector('#kpi-attendance').textContent !== '—'")
            if mock_renderer:
                await page.evaluate("document.querySelector('h1').textContent='OFFLINE UI TEST · MOCK RENDER FRAME'")
            await page.locator("#asset-select").select_option("WATER_PLANT")
            await page.locator('.system-card[data-system="water"]').click()
            await page.wait_for_selector(".observation-table")
            await page.locator('[data-connector-mode="paused"]').click()
            await page.wait_for_function("document.querySelector('#source-health-status').textContent.toLowerCase()==='stale'", timeout=18000)
            paused = await get("/api/connectors/water/health")
            frozen_source_time = paused["last_source_timestamp"]
            await page.wait_for_timeout(1200)
            assert (await get("/api/connectors/water/health"))["last_source_timestamp"] == frozen_source_time
            await page.screenshot(path=str(output / "source-stale.png"))
            await page.locator('[data-connector-mode="offline"]').click()
            await page.wait_for_function("document.querySelector('#source-health-status').textContent.toLowerCase()==='offline'")
            records = (await get("/api/timeline?limit=300"))["snapshots"]
            record_id = max(record["id"] for record in records)
            await page.locator('[data-connector-mode="live"]').click()
            await page.wait_for_function("document.querySelector('#source-health-status').textContent.toLowerCase()==='healthy'", timeout=10000)
            await page.locator(".close-system").click()
            await page.locator('[data-layer="dependencies"]').click()
            if mock_renderer:
                await page.wait_for_selector("#dependency-lines:not([hidden])")
                assert await page.locator(".dependency-edge").count() > 0
            await page.screenshot(path=str(output / "logical-dependencies.png"), full_page=True)

            # Select the captured offline record through the actual timeline UI.
            await page.wait_for_timeout(3200)
            records = sorted((await get("/api/timeline?limit=300"))["snapshots"], key=lambda record: record["id"])
            index = next(index for index, record in enumerate(records) if record["id"] == record_id)
            if mock_renderer:
                fixture["hold_view"] = True
            await page.locator("#timeline-range").evaluate("(element,index)=>{element.value=String(index);element.dispatchEvent(new Event('input',{bubbles:true}));element.dispatchEvent(new Event('change',{bubbles:true}));}", index)
            await page.wait_for_selector("#replay-banner:not([hidden])")
            assert await page.locator("#compare-scenarios").is_disabled()
            for button in await page.locator(".scenario-chip, [data-action]").all():
                assert await button.is_disabled()
            for path, payload in (("/api/actions", {"action": "reset"}), ("/api/connectors/water/simulation", {"mode": "paused"})):
                assert (await page.request.post(BASE + path, data=payload)).status == 409
            assert (await page.request.get(BASE + "/api/scenarios/compare?scenario=ride_closure")).status == 409
            if mock_renderer:
                await page.wait_for_function("document.querySelector('#frame-context').textContent.includes('VIEW SWITCH IN PROGRESS')")
                assert await page.locator(".scene-label").count() == 0
                fixture["hold_view"] = False
                await page.wait_for_function("document.querySelector('#frame-context').textContent.includes('historical ride pose unavailable')")
            boundary = len(browser_requests)
            await page.locator('.system-card[data-system="water"]').click()
            await page.wait_for_function("document.querySelector('#source-health-status').textContent.toLowerCase()==='offline'")
            assert all([await button.is_disabled() for button in await page.locator("[data-connector-mode]").all()])
            await page.wait_for_timeout(2500)
            assert not any("/api/connectors/" in url or "/api/observations" in url or "/api/systems/" in url for url in browser_requests[boundary:]), "Replay fetched a live source payload"
            await page.locator(".close-system").click()
            snapshot_before = await get("/api/view/state")
            newest_before = max(record["id"] for record in (await get("/api/timeline"))["snapshots"])
            await page.wait_for_timeout(2600)
            assert (await get("/api/view/state"))["view"]["snapshot_id"] == record_id
            assert max(record["id"] for record in (await get("/api/timeline"))["snapshots"]) > newest_before
            await page.screenshot(path=str(output / "recorded-view.png"), full_page=True)
            await page.locator("#return-live").click()
            await page.wait_for_selector("#replay-banner[hidden]", state="attached")
            assert await page.locator("#compare-scenarios").is_enabled()

            if mock_renderer:
                fixture["degraded"] = True
                await page.wait_for_function("document.querySelector('#frame-context').textContent.includes('affected ride poses frozen')")
                fixture["degraded"] = False
                await page.wait_for_timeout(1000)
                fixture["freeze"] = True
                await page.wait_for_timeout(800)
                original_caption = await page.locator("#frame-freshness").inner_text()
                await page.wait_for_function("document.querySelector('#viewport').classList.contains('frame-stale')", timeout=9000)
                assert await page.locator("#frame-freshness").inner_text() == original_caption
                await page.screenshot(path=str(output / "cached-frame-stale.png"))
                fixture["freeze"] = False
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.evaluate("scrollTo(0,0)")
            await page.wait_for_timeout(500)
            assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth")
            await page.screenshot(path=str(output / "mobile-extended.png"), full_page=True)
            assert not errors, errors
            report = {"verified_at": datetime.now(timezone.utc).isoformat(),
                      "evidence_kind": "cpu_browser_fixture_not_gpu_validation" if mock_renderer else "browser_against_running_application",
                      "page_errors": errors, "connector_pause_stale_offline_resume": True,
                      "replay_read_only": True, "replay_source_calls": 0, "recording_continues": True,
                      "frame_metadata_failure_cases": mock_renderer, "mobile_overflow": False,
                      "record_id": record_id, "recorded_source_timestamp": snapshot_before["view"]["source_timestamp"]}
            (output / "extended-browser-validation.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
        finally:
            for path, body in (("/api/view", {"mode": "live"}), ("/api/connectors/water/simulation", {"mode": "live"}), ("/api/actions", {"action": "reset"}), ("/render/control", {"action": "home"}), ("/render/control", {"action": "layer", "layer": "operations"})):
                try:
                    await page.request.post(BASE + path, data=body, timeout=6000)
                except Exception:
                    pass
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logic-only", action="store_true", help="Run pure JS logic/DOM-ID checks without a browser or GPU")
    parser.add_argument("--mock-renderer", action="store_true", help="Use an explicitly labeled CPU image/metadata fixture for browser checks")
    arguments = parser.parse_args()
    if arguments.logic_only:
        logic_checks()
    else:
        asyncio.run(browser_checks(arguments.mock_renderer))
