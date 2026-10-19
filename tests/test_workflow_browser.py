"""Explicit workflow UI acceptance with real services over mocked HTTP transport.

Uses isolated SQLite stores and synthetic state. No GPU or external server is used.
Run with Playwright/Chromium installed: python -m pytest tests/test_workflow_browser.py
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import pytest

playwright=pytest.importorskip('playwright.sync_api')
from backend.connectors import ConnectorRuntime, ParkReadModel
from backend.planning import PlanningRequest, simulate
from backend.planning.evidence import EvidenceStore, make_bundle
from backend.simulator import ParkSimulator
from backend.workflows.contracts import CreateProposal, ExecuteProposal, WorkflowError
from backend.workflows.service import WorkflowService, capabilities
from backend.workflows.store import WorkflowStore

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as driver:
        browser=driver.chromium.launch(args=['--no-sandbox'])
        yield browser
        browser.close()

@pytest.fixture
def ui(browser,tmp_path):
    park=ParkSimulator(str(tmp_path/'park.db'));park.set_scenario('ride_closure')
    config={'offset':0,'drop_create':False,'drop_execute':False,'mode':'live','calls':[],'errors':[]}
    clock=lambda:datetime.now(timezone.utc)+timedelta(seconds=config['offset'])
    connectors=ConnectorRuntime(park.base,clock=clock);model=ParkReadModel(park,connectors)
    evidence=EvidenceStore(str(tmp_path/'planning.db'));store=WorkflowStore(str(tmp_path/'workflow.db'))
    service=WorkflowService(park,model,connectors,evidence,store)
    state=model.snapshot();request=PlanningRequest(scenario='ride_closure');now=clock();result=simulate(state,request,as_of=now)
    bundle=make_bundle(state,request,result,now);evidence.save(bundle)
    page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(5000)
    page.on('pageerror',lambda error:config['errors'].append(str(error)))
    context={'bundle_id':bundle['bundle_id'],'saved':True,'scenario':'ride_closure','branches':result['branches']}
    observation={'mode':'live','scenario':'ride_closure'}
    def route(route):
        path=route.request.url.removeprefix('http://workflow.test')
        try:
            if path=='/api/workflows/capabilities':return route.fulfill(json=capabilities())
            if path.startswith('/api/workflows/proposals'):
                if route.request.method=='POST':
                    payload=route.request.post_data_json;config['calls'].append((path,payload))
                    if config['mode']=='replay':raise WorkflowError('recorded_view','Return to live before creating or executing workflow proposals')
                    if path.endswith('/execute'):
                        value=service.execute(path.split('/')[-2],ExecuteProposal(**payload))
                        if config['drop_execute']:config['drop_execute']=False;return route.abort()
                    else:
                        value=service.create(CreateProposal(**payload))
                        if config['drop_create']:config['drop_create']=False;return route.abort()
                elif '?' in path:value=store.list()
                else:value={'proposal':store.get(path.rsplit('/',1)[-1])}
                return route.fulfill(json=value)
            if path=='/':
                html=(ROOT/'frontend/index.html').read_text().replace('<script defer src="/app.js"></script>','').replace('<script defer src="/planning.js"></script>','')
                return route.fulfill(content_type='text/html',body=html)
            if path in ['/styles.css','/planning.css','/workflow.css','/workflow.js']:
                return route.fulfill(content_type='text/javascript' if path.endswith('.js') else 'text/css',body=(ROOT/'frontend'/path[1:]).read_text())
            route.abort()
        except WorkflowError as error:
            route.fulfill(status=error.status,json={'detail':{'code':error.code,'message':error.message,'context':error.context}})
    page.route('**/*',route)
    def emit():
        page.evaluate('(value)=>document.dispatchEvent(new CustomEvent("park:state",{detail:value}))',observation)
        page.evaluate('(value)=>document.dispatchEvent(new CustomEvent("park:planning-evidence",{detail:value}))',context)
    page.goto('http://workflow.test');emit();page.wait_for_function('!document.getElementById("workflow-create").disabled')
    config.update(page=page,park=park,store=store,observation=observation,context=context,emit=emit,connectors=connectors,model=model)
    try:yield config
    finally:
        try:page.close()
        finally:park.close();evidence.close();store.close()
        assert not config['errors']


def create(ui):
    ui['page'].click('#workflow-create')
    ui['page'].wait_for_function('!document.getElementById("workflow-proposal").hidden')


def count_orders(ui):return ui['park'].db.execute('SELECT COUNT(*) FROM work_orders').fetchone()[0]


def test_create_is_not_execution_and_explicit_dispatch_keeps_ride_closed(ui):
    create(ui);assert count_orders(ui)==0
    page=ui['page'];assert '120s' in page.locator('.workflow-expiry').inner_text() or '119s' in page.locator('.workflow-expiry').inner_text()
    assert 'Closed' in page.locator('.workflow-checks').inner_text()
    page.click('#workflow-execute');page.wait_for_function('document.getElementById("workflow-proposal").textContent.includes("Work order accepted")')
    assert count_orders(ui)==1
    assert 'Observed Closed · quality good' in page.locator('.workflow-asset-evidence').inner_text()
    assert 'physical completion: false' in page.locator('.workflow-result').inner_text()
    assert 'not a repair' in page.locator('.workflow-not-repair').inner_text()
    original=ui['calls'][-1][1]['request_id']
    page.click('#workflow-execute');page.wait_for_function('document.getElementById("workflow-message").textContent.includes("no duplicate")')
    assert ui['calls'][-1][1]['request_id']==original
    assert count_orders(ui)==1


def test_lost_create_response_retries_same_payload_after_reload(ui):
    ui['drop_create']=True;page=ui['page'];page.click('#workflow-create')
    page.wait_for_function('document.getElementById("workflow-message").textContent.includes("Acceptance unknown")')
    first=ui['calls'][0][1];assert ui['store'].list()['total']==1
    page.reload();ui['emit']();page.wait_for_function('!document.getElementById("workflow-create").disabled');create(ui)
    assert ui['calls'][1][1]==first
    assert ui['store'].list()['total']==1 and count_orders(ui)==0


def test_lost_execute_response_recovers_get_after_reload_then_same_retry(ui):
    create(ui);ui['drop_execute']=True;page=ui['page'];page.click('#workflow-execute')
    page.wait_for_function('document.getElementById("workflow-message").textContent.includes("Acceptance unknown")')
    execution=ui['calls'][-1][1]['request_id'];assert count_orders(ui)==1
    assert page.locator('#workflow-new').is_disabled()
    count_before=len(ui['calls']);page.reload();ui['emit']()
    page.wait_for_function('document.getElementById("workflow-proposal").textContent.includes("Work order accepted")')
    assert len(ui['calls'])==count_before,'GET recovery must not issue a POST'
    page.click('#workflow-execute');page.wait_for_function('document.getElementById("workflow-message").textContent.includes("no duplicate")')
    assert ui['calls'][-1][1]['request_id']==execution
    assert count_orders(ui)==1


def test_changed_conditions_block_execution_and_require_new_proposal(ui):
    create(ui);ui['park'].set_scenario('normal');page=ui['page'];page.click('#workflow-execute')
    page.wait_for_function('document.getElementById("workflow-message").textContent.includes("changed")')
    assert page.locator('#workflow-execute').is_disabled()
    assert page.locator('#workflow-new').is_enabled()
    assert count_orders(ui)==0


def test_server_expiry_blocks_dispatch_even_if_browser_clock_has_not_advanced(ui):
    create(ui);ui['offset']=121;page=ui['page'];page.click('#workflow-execute')
    page.wait_for_function('document.getElementById("workflow-message").textContent.includes("expired")')
    assert count_orders(ui)==0
    assert page.locator('#workflow-new').is_enabled()


def test_replay_disables_writes_but_proposal_get_stays_available(ui):
    create(ui);ui['mode']='replay';ui['observation']['mode']='replay';ui['emit']();page=ui['page']
    assert page.locator('#workflow-execute').is_disabled()
    before=len(ui['calls']);page.click('#workflow-recover');page.wait_for_function('document.getElementById("workflow-message").textContent.includes("reopened")')
    assert len(ui['calls'])==before and count_orders(ui)==0


def test_unsupported_actions_have_no_create_executor(ui):
    ui['context']['branches']=[{'id':'staff','label':'Staffing','action_schedule':[{'action':'add_staff','asset_id':'RIDE_WHEEL','at_minute':0}]}];ui['emit']()
    assert ui['page'].locator('#workflow-create').is_disabled()
    assert 'No supported action' in ui['page'].locator('#workflow-action').inner_text()


def test_stale_observations_block_dispatch_then_retry_retains_execution_identity(ui):
    create(ui)
    state=ui['model'].snapshot()
    source=next(a for a in state['assets'] if a['id']=='RIDE_COASTER')['data_quality']['fields']['status']['source_id']
    ui['connectors'].set_simulation_mode(source,'paused');ui['offset']=6
    page=ui['page'];page.click('#workflow-execute')
    page.wait_for_function('document.getElementById("workflow-message").textContent.includes("Fresh authoritative")')
    original=ui['calls'][-1][1]['request_id'];assert count_orders(ui)==0
    ui['offset']=0;ui['connectors'].set_simulation_mode(source,'live');ui['park'].advance();ui['emit']()
    page.click('#workflow-execute');page.wait_for_function('document.getElementById("workflow-proposal").textContent.includes("Work order accepted")')
    assert ui['calls'][-1][1]['request_id']==original and count_orders(ui)==1


def test_intervening_order_displays_existing_id_and_inspection_path(ui):
    create(ui)
    accepted=ui['park'].act('dispatch_maintenance','RIDE_COASTER',request_id='other-operator')
    ident=accepted['result']['work_order_id']
    page=ui['page'];page.click('#workflow-execute')
    page.wait_for_function('!document.getElementById("workflow-conflict").hidden')
    context=page.locator('#workflow-conflict').inner_text()
    assert f'#{ident}' in context
    assert 'Inspect the existing work order' in context
    assert page.locator('#workflow-conflict a').get_attribute('href')=='/api/assets/RIDE_COASTER'
    assert page.locator('[data-workflow-inspect]').get_attribute('data-asset')=='RIDE_COASTER'
    assert count_orders(ui)==1


def test_recovered_receipt_does_not_refresh_stale_asset_observation(ui):
    create(ui);page=ui['page'];page.click('#workflow-execute')
    page.wait_for_function('document.getElementById("workflow-proposal").textContent.includes("Work order accepted")')
    first=ui['store'].list()['items'][0]['readback']['asset_status_evidence']
    ui['connectors'].set_simulation_mode(first['source_id'],'paused');ui['offset']=10
    page.click('#workflow-execute')
    page.wait_for_function('document.querySelector(".workflow-asset-evidence").textContent.includes("Last observed Closed · stale")')
    latest=ui['store'].list()['items'][0]['readback']
    assert latest['asset_status_evidence']['source_timestamp']==first['source_timestamp']
    assert latest['asset_status_evidence']['quality']=='stale'
    assert latest['observed_at']>first['source_timestamp']
    assert 'quality good' not in page.locator('.workflow-asset-evidence').inner_text()
    assert 'does not refresh' in page.locator('.workflow-asset-evidence').inner_text()
    assert count_orders(ui)==1
