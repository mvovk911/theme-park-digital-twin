"""Decision Lab browser semantics with real engine results and mocked HTTP transport.

No renderer is mocked or claimed: app.js is excluded to isolate this read-only UI.
Install Playwright + Chromium alongside project dependencies, then:
  python -m pytest tests/test_planning_browser.py
The module skips when Playwright is absent. No shared park service is contacted.
"""
from pathlib import Path
import copy
import json
from datetime import datetime

import pytest

playwright = pytest.importorskip('playwright.sync_api')
from backend.connectors import ConnectorRuntime, ParkReadModel
from backend.planning import PlanningRequest, simulate
from backend.planning.evidence import EvidenceStore, EvidenceError, digest, make_bundle, verify_bundle
from backend.planning.engine import capabilities
from backend.simulator import ParkSimulator

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch(args=['--no-sandbox'])
        yield instance
        instance.close()


@pytest.fixture
def ui(browser):
    park = ParkSimulator(':memory:')
    state = ParkReadModel(park, ConnectorRuntime(park.base)).snapshot()
    page = browser.new_page(viewport={'width':1440, 'height':1000})
    page.set_default_timeout(5000)
    store = EvidenceStore(':memory:')
    settings = {'store':store, 'response':None, 'status':200, 'calls':[], 'errors':[]}
    page.on('pageerror', lambda error: settings['errors'].append(str(error)))

    def route(request):
        path = request.request.url.removeprefix('http://planning.test')
        if path == '/api/planning/capabilities':
            return request.fulfill(json=capabilities())
        if path == '/api/planning/simulate':
            payload = request.request.post_data_json
            settings['calls'].append(payload)
            result = settings['response']
            if result is None:
                parsed=PlanningRequest(**payload); as_of=datetime.fromisoformat(state['timestamp'])
                result=simulate(state,parsed,as_of=as_of)
                result['evidence_bundle']=make_bundle(state,parsed,result,as_of)
            if settings.get('hold_response'):
                settings['pending_response']=(request,result)
                return
            return request.fulfill(status=settings['status'], json=result)
        if path.startswith('/api/planning/evidence'):
            try:
                if path == '/api/planning/evidence/verify':
                    data=verify_bundle(request.request.post_data_json)
                elif path == '/api/planning/evidence' and request.request.method=='POST':
                    data=store.save(request.request.post_data_json)
                elif path.startswith('/api/planning/evidence?'):
                    data=store.list()
                else:
                    data=store.get(path.rsplit('/',1)[-1])
                return request.fulfill(json=data)
            except EvidenceError as error:
                return request.fulfill(status=error.status,json={'detail':{'code':error.code,'message':error.message}})
        if path == '/':
            html = (ROOT/'frontend/index.html').read_text().replace('<script defer src="/app.js"></script>', '')
            return request.fulfill(content_type='text/html', body=html)
        if path in ['/styles.css', '/planning.css', '/planning.js']:
            return request.fulfill(content_type='text/javascript' if path.endswith('.js') else 'text/css', body=(ROOT/'frontend'/path[1:]).read_text())
        return request.abort()

    page.route('**/*', route)
    page.goto('http://planning.test')
    observation = {'revision':state['accepted_state_revision'], 'timestamp':state['timestamp'], 'tick':state['tick'], 'scenario':'normal', 'mode':'live', 'quality':'good'}

    def emit():
        page.evaluate('(state)=>document.dispatchEvent(new CustomEvent("park:state",{detail:state}))', observation)

    emit()
    page.wait_for_function('!document.getElementById("planning-run").disabled')
    settings.update(page=page, state=state, observation=observation, emit=emit)
    try:
        yield settings
    finally:
        try:
            page.close()
        finally:
            park.close()
            store.close()
        assert settings['errors'] == []


def compare(ui, scenario='food_rush'):
    page = ui['page']
    page.select_option('#planning-scenario', scenario)
    with page.expect_response(lambda response: response.url.endswith('/api/planning/simulate')):
        page.click('#planning-run')
    page.wait_for_function('!document.getElementById("planning-run").disabled')


def test_full_tradeoff_and_charts_preserve_request_provenance(ui):
    compare(ui)
    page=ui['page']
    assert page.locator('.planning-branch').count()==3
    assert page.locator('#planning-comparison tbody tr').count()==8
    assert ui['calls'][0]['expected_state_revision']==ui['state']['accepted_state_revision']
    assert 'central case' in page.locator('.planning-branch').first.inner_text()
    for metric in ['queue','served','power','stock','leak']:
        page.select_option('#planning-chart-metric',metric)
        assert page.locator('#planning-chart polyline').count()==(4 if metric=='power' else 3)
    assert not page.locator('#planning-section button').filter(has_text='Execute').count()


def test_do_nothing_is_explicit_when_intervention_has_no_benefit(ui):
    ui['response']=simulate(ui['state'],PlanningRequest(scenario='normal',candidates=[{'id':'noop','label':'No extra intervention','actions':[]}]))
    compare(ui,'normal')
    assert 'model prefers no additional intervention' in ui['page'].locator('#planning-outcome').inner_text()
    assert 'model-preferred reference' in ui['page'].locator('.planning-branch').first.inner_text().lower()


def test_real_routing_reversal_is_visible_with_paired_high_demand_delta(ui):
    next(asset for asset in ui['state']['assets'] if asset['id']=='RIDE_COASTER')['queue_minutes']=10
    response=simulate(ui['state'],PlanningRequest(scenario='normal',candidates=[{'id':'routing','label':'Routing response','actions':[{'action':'reroute_guests','asset_id':'RIDE_COASTER'}]}],assumptions={'arrival_multiplier':.25,'demand_uncertainty_pct':50,'routing_compliance_pct':100}))
    branch=response['branches'][1]
    assert branch['deltas_vs_baseline']['queue_guest_minutes']<0
    assert branch['sensitivity']['high']['deltas_vs_baseline']['queue_guest_minutes']>0
    ui['response']=response
    compare(ui,'normal')
    warning=ui['page'].locator('.planning-adverse').inner_text()
    assert 'High demand (1.5× central)' in warning
    assert 'guest-min accumulated waiting' in warning
    assert 'same demand' in warning
    assert ui['page'].locator('.planning-adverse').is_visible()


def test_source_quality_blocks_shortlist_and_warning_survives_poll(ui):
    state=copy.deepcopy(ui['state']);state['assets'][0]['data_quality']['status']='stale'
    ui['response']=simulate(state,PlanningRequest(scenario='food_rush'))
    compare(ui);ui['emit']()
    assert 'insufficient' in ui['page'].locator('#planning-status').inner_text()
    assert 'Insufficient evidence' in ui['page'].locator('#planning-outcome').inner_text()
    assert 'stale' in ui['page'].locator('#planning-quality').inner_text()


def test_expired_revision_error_preserves_previous_results_and_stays_visible(ui):
    compare(ui)
    previous=ui['page'].locator('#planning-frozen').inner_text()
    ui['status']=409;ui['response']={'detail':{'message':'Requested observation expired'}}
    compare(ui);ui['emit']()
    assert 'expired' in ui['page'].locator('#planning-status').inner_text()
    assert ui['page'].locator('#planning-frozen').inner_text()==previous


def test_mismatched_response_rejected_and_replay_disables_requests(ui):
    response=simulate(ui['state'],PlanningRequest(scenario='food_rush'));response['input']['state_revision']='f'*64;ui['response']=response
    compare(ui)
    assert 'could not be associated' in ui['page'].locator('#planning-status').inner_text()
    assert ui['page'].locator('#planning-results').is_hidden()
    ui['observation']['mode']='replay';ui['emit']()
    assert ui['page'].locator('#planning-run').is_disabled()
    assert 'Recorded view' in ui['page'].locator('#planning-status').inner_text()


def test_unavailable_staff_visible_and_mobile_does_not_overflow(ui):
    ui['page'].fill('#planning-staff','0');compare(ui)
    branch=ui['page'].locator('.planning-branch.infeasible')
    assert branch.count()==1
    assert '2 qualified staff requested; 0 assumed available' in branch.inner_text()
    ui['page'].set_viewport_size({'width':390,'height':844})
    assert ui['page'].evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert ui['page'].locator('#planning-section').evaluate('(e)=>e.scrollWidth<=e.clientWidth')


def test_save_download_and_reopen_reproduce_exact_frozen_evidence(ui, tmp_path):
    compare(ui)
    page=ui['page']; original=page.locator('#planning-frozen').inner_text()
    with page.expect_response(lambda response:response.url.endswith('/api/planning/evidence')) as saved_response:
        page.click('#planning-save')
    assert saved_response.value.status==200, saved_response.value.text()
    page.wait_for_function('document.getElementById("planning-save").textContent.includes("Saved comparison")')
    saved=ui['store'].list()['items'];assert len(saved)==1
    with page.expect_download() as pending:page.click('#planning-export')
    path=tmp_path/'comparison.json';pending.value.save_as(path)
    bundle=json.loads(path.read_text());assert bundle['bundle_id']==saved[0]['bundle_id']
    assert verify_bundle(bundle)['verified']
    compare(ui,'water_leak');assert page.locator('#planning-result-title').inner_text().startswith('Water leak')
    page.click('#planning-library-toggle');page.wait_for_selector('[data-evidence-open]');page.click('[data-evidence-open]')
    page.wait_for_function('document.getElementById("planning-evidence-context").textContent.includes("Reopened historical")')
    assert page.locator('#planning-frozen').inner_text()==original
    assert 'observation origin not authenticated' in page.locator('#planning-evidence-context').inner_text()
    assert page.locator('#planning-scenario').input_value()=='food_rush'


def test_import_tampering_and_model_mismatch_preserve_current_result(ui, tmp_path):
    compare(ui);page=ui['page'];page.click('#planning-save')
    page.wait_for_function('document.getElementById("planning-save").textContent.includes("Saved comparison")')
    bundle=ui['store'].get(ui['store'].list()['items'][0]['bundle_id'])
    before=page.locator('#planning-frozen').inner_text()
    bundle['payload']['result']['branches'][0]['summary']['served_guests']+=1
    path=tmp_path/'tampered.json';path.write_text(json.dumps(bundle));page.set_input_files('#planning-import-file',str(path))
    page.wait_for_function('document.getElementById("planning-evidence-notice").textContent.includes("SHA256")')
    assert page.locator('#planning-frozen').inner_text()==before
    assert page.locator('#planning-evidence-notice').get_attribute('class').endswith('error')
    mismatch=ui['store'].get(ui['store'].list()['items'][0]['bundle_id'])
    mismatch['payload']['model_source_sha256']='f'*64
    mismatch['bundle_id']=digest(mismatch['payload'])
    path.write_text(json.dumps(mismatch));page.set_input_files('#planning-import-file',str(path))
    page.wait_for_function('document.getElementById("planning-evidence-notice").textContent.includes("another model source")')
    assert page.locator('#planning-frozen').inner_text()==before


def test_historical_open_allowed_during_replay_without_changing_cursor(ui):
    compare(ui);page=ui['page'];page.click('#planning-save')
    page.wait_for_function('document.getElementById("planning-save").textContent.includes("Saved comparison")')
    ui['observation']['mode']='replay';ui['emit']();assert page.locator('#planning-run').is_disabled()
    page.click('#planning-library-toggle');page.wait_for_selector('[data-evidence-open]');page.click('[data-evidence-open]')
    page.wait_for_function('document.getElementById("planning-evidence-context").textContent.includes("Reopened historical")')
    assert page.locator('#planning-run').is_disabled()
    assert 'Recorded view' in page.locator('#planning-status').inner_text()
    assert len(ui['calls'])==1


def test_view_transition_rejects_inflight_prospective_result(ui):
    ui['hold_response']=True
    page=ui['page'];page.click('#planning-run')
    page.wait_for_function('document.getElementById("planning-run").textContent.includes("Comparing")')
    ui['observation']['mode']='replay';ui['emit']()
    route,result=ui['pending_response'];route.fulfill(json=result)
    page.wait_for_function('!document.getElementById("planning-scenario").disabled')
    assert page.locator('#planning-results').is_hidden()
    assert page.locator('#planning-run').is_disabled()
    assert 'Recorded view' in page.locator('#planning-status').inner_text()
