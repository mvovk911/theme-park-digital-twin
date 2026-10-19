"""Authored-design UI with real graph queries over mocked HTTP transport.

No GPU images or real native-capture evidence are created by these tests.
"""
import json
import base64
import hashlib
from pathlib import Path
import pytest

playwright = pytest.importorskip('playwright.sync_api')
from backend.spatial.service import SpatialService
from backend.spatial.contracts import RouteRequest
ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(args=['--no-sandbox'])
        yield browser
        browser.close()

@pytest.fixture
def ui(browser):
    service = SpatialService()
    config = {'fail_graph':None,'fail_route':None,'mismatch_route':False,'fail_capability':False,'calls':[],'errors':[],'preview_bad_identity':False,'preview_valid':False,'preview_bad_bytes':False}
    page = browser.new_page(viewport={'width':1440,'height':1100}, accept_downloads=True)
    page.set_default_timeout(5000)
    page.on('pageerror',lambda error:config['errors'].append(str(error)))
    def route(route):
        request = route.request
        path = request.url.removeprefix('http://localhost:51888')
        if path.startswith('/api/'):
            config['calls'].append((request.method,path,request.post_data_json if request.method=='POST' else None))
        if path == '/':
            return route.fulfill(content_type='text/html',body='<html><head><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/spatial.css"><script defer src="/spatial.js"></script></head><body><main><section id="spatial-panel" class="spatial-panel"></section></main></body></html>')
        if path in ['/styles.css','/spatial.css','/spatial.js']:
            return route.fulfill(content_type='text/javascript' if path.endswith('.js') else 'text/css',body=(ROOT/'frontend'/path[1:]).read_text())
        if path == '/api/spatial/capabilities':
            if config['fail_capability']:return route.fulfill(status=503,json={'detail':{'message':'Design capability unavailable'}})
            return route.fulfill(json=service.capabilities())
        if path.startswith('/api/spatial/graphs/'):
            variant=path.rsplit('/',1)[-1]
            if config['fail_graph']==variant:return route.fulfill(status=503,json={'detail':{'message':'Graph unavailable'}})
            return route.fulfill(json=service.graph(variant))
        if path=='/api/spatial/route':
            query=RouteRequest(**request.post_data_json)
            if config['fail_route']==query.variant:return route.fulfill(status=503,json={'detail':{'message':'Query temporarily unavailable'}})
            result=service.route(query)
            if config['mismatch_route'] and query.variant=='dining_connection':result['identity']['graph_sha256']='0'*64
            return route.fulfill(json=result)
        if path.startswith('/api/spatial/previews/'):
            if config['preview_valid'] or config['preview_bad_bytes']:
                # Tiny fixture tests transport/hash behavior only; it is not a
                # native GPU capture and never enters project evidence artifacts.
                png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3e0AAAAASUVORK5CYII=')
                identity=service.graph(path.rsplit('/',1)[-1])['identity']
                return route.fulfill(status=200,content_type='image/png',body=png+(b'changed' if config['preview_bad_bytes'] else b''),headers={
                    'X-Spatial-Graph-Sha256':identity['graph_sha256'],
                    'X-Spatial-Scene-Sha256':identity['baseline_scene_sha256'],
                    'X-Spatial-Variant-Layer-Sha256':identity['variant_layer_sha256'] or '',
                    'X-Spatial-Preview-Image-Sha256':hashlib.sha256(png).hexdigest(),
                    'X-Spatial-Preview-Report-Sha256':'1'*64,
                    'X-Spatial-Preview-Mode':'static_native'})
            if config['preview_bad_identity']:
                return route.fulfill(status=200,content_type='image/png',headers={'X-Spatial-Graph-Sha256':'0'*64},body=b'not a verified image')
            return route.fulfill(status=503,json={'detail':{'message':'Native image unavailable'}})
        route.abort()
    page.route('**/*',route)
    def open():
        page.goto('http://localhost:51888')
        page.wait_for_function('!document.getElementById("spatial-reload").disabled')
    config.update(page=page,open=open)
    try:yield config
    finally:
        page.close()
        assert not config['errors']
        assert all(method=='GET' or path=='/api/spatial/route' for method,path,_ in config['calls'])
        assert all(path.startswith('/api/spatial/') for _,path,_ in config['calls'])

def compare(ui):
    page=ui['page'];page.click('#spatial-compare')
    page.wait_for_function('!document.getElementById("spatial-compare").disabled')

def test_before_after_graph_route_and_explicit_scope(ui):
    ui['open']();page=ui['page']
    assert 'No route' in page.locator('#spatial-result-baseline').inner_text()
    text=page.locator('#spatial-result-dining_connection').inner_text()
    assert '40.852' in text and '34.04' in text
    assert page.locator('#spatial-graph-dining_connection .route').count()==4
    assert page.locator('#spatial-graph-baseline [data-edge-id="food_missing_link"]').get_attribute('class')=='spatial-edge excluded'
    assert 'does not feed' in page.locator('.spatial-limits').inner_text()
    assert 'No percentage time saving' in page.locator('#spatial-summary').inner_text()
    assert 'unavailable' in page.locator('#spatial-preview-note-baseline').inner_text()
    assert page.locator('#spatial-preview-baseline').is_hidden()

def test_input_change_clears_old_metrics_before_closure_query(ui):
    ui['open']();page=ui['page'];before=len(ui['calls']);page.check('#spatial-closed')
    assert '40.852' not in page.locator('#spatial-result-dining_connection').inner_text()
    assert page.locator('#spatial-export').is_disabled() and len(ui['calls'])==before
    compare(ui)
    assert 'No route' in page.locator('#spatial-result-dining_connection').inner_text()
    queries=[data for method,path,data in ui['calls'] if path=='/api/spatial/route'][-2:]
    assert next(q for q in queries if q['variant']=='baseline')['blocked_edges']==[]
    assert next(q for q in queries if q['variant']=='dining_connection')['blocked_edges']==['dining_connector_link']

def test_accessibility_filter_keeps_entrance_barrier_visible(ui):
    ui['open']();page=ui['page'];page.check('#spatial-accessible');compare(ui)
    assert 'No route' in page.locator('#spatial-result-dining_connection').inner_text()
    assert 'entry threshold' in page.locator('#spatial-note-dining_connection').inner_text()
    assert 'excluded' in page.locator('#spatial-graph-dining_connection [data-edge-id="entry_main"]').get_attribute('class')

def test_partial_graph_failure_does_not_infer_other_design(ui):
    ui['fail_graph']='baseline';ui['open']();page=ui['page']
    assert 'unavailable' in page.locator('#spatial-result-baseline').inner_text()
    assert '40.852' in page.locator('#spatial-result-dining_connection').inner_text()
    assert page.locator('#spatial-export').is_disabled()
    assert 'incomplete' in page.locator('#spatial-summary').inner_text()
    assert not any(data and data.get('variant')=='baseline' for method,path,data in ui['calls'] if path=='/api/spatial/route')

def test_partial_route_failure_and_hash_mismatch_fail_closed(ui):
    ui['fail_route']='dining_connection';ui['open']();page=ui['page']
    assert 'unavailable' in page.locator('#spatial-result-dining_connection').inner_text()
    ui['fail_route']=None;ui['mismatch_route']=True;compare(ui)
    assert 'identity' in page.locator('#spatial-result-dining_connection').inner_text()
    assert page.locator('#spatial-graph-dining_connection .route').count()==0
    assert page.locator('#spatial-export').is_disabled()

def test_replay_query_is_available_without_live_actions(ui):
    ui['open']();page=ui['page'];page.evaluate('()=>document.dispatchEvent(new CustomEvent("park:state",{detail:{mode:"replay"}}))')
    assert 'separately authored design' in page.locator('#spatial-context').inner_text()
    page.check('#spatial-closed');compare(ui)
    assert 'No route' in page.locator('#spatial-result-dining_connection').inner_text()
    assert page.locator('#spatial-export').is_enabled()

def test_unavailable_capability_has_manual_retry_without_polling(ui):
    ui['fail_capability']=True;ui['open']();page=ui['page'];count=len(ui['calls']);page.wait_for_timeout(1100)
    assert len(ui['calls'])==count==1
    assert page.locator('#spatial-compare').is_disabled()
    ui['fail_capability']=False;page.click('#spatial-reload');page.wait_for_function('!document.getElementById("spatial-export").disabled')
    assert '40.852' in page.locator('#spatial-result-dining_connection').inner_text()

def test_export_keeps_exact_queries_responses_identities(ui,tmp_path):
    ui['open']();page=ui['page']
    with page.expect_download() as pending:page.click('#spatial-export')
    path=tmp_path/'comparison.json';pending.value.save_as(path);data=json.loads(path.read_text())
    assert data['scope']=='authored_design_not_live_guidance'
    assert data['forecast_coupled'] is False and data['mutates_live_state'] is False
    assert len(data['comparisons'])==2
    for row in data['comparisons']:
        assert row['query']==row['response']['query']
        assert len(row['response']['identity']['graph_sha256'])==64

def test_preview_identity_failure_does_not_display_image(ui):
    ui['preview_bad_identity']=True;ui['open']();page=ui['page']
    page.wait_for_function('document.getElementById("spatial-preview-note-baseline").textContent.includes("identity")')
    assert page.locator('#spatial-preview-baseline').is_hidden()
    assert '40.852' in page.locator('#spatial-result-dining_connection').inner_text()

def test_mobile_layout_no_overflow(ui):
    ui['open']();page=ui['page'];page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('#spatial-compare').is_visible()


def test_declared_preview_hash_must_match_actual_image_bytes(ui):
    ui['preview_bad_bytes']=True;ui['open']();page=ui['page']
    assert page.evaluate('!!crypto.subtle')
    page.wait_for_function('document.getElementById("spatial-preview-note-baseline").textContent.includes("image bytes do not match")')
    assert page.locator('#spatial-preview-baseline').is_hidden()
    assert '40.852' in page.locator('#spatial-result-dining_connection').inner_text()


def test_verified_preview_transport_displays_explicit_static_scope(ui):
    ui['preview_valid']=True;ui['open']();page=ui['page']
    page.wait_for_function('!document.getElementById("spatial-preview-baseline").hidden')
    assert 'image bytes checked in browser' in page.locator('#spatial-preview-note-baseline').inner_text()
    assert 'does not depict query closures' in page.locator('#spatial-preview-note-baseline').inner_text()
