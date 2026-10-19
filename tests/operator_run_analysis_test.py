"""Boundary tests for evidence reconciliation; no live services or backend imports."""
import copy
from datetime import datetime,timedelta,timezone
import importlib.util
import json
from pathlib import Path
import pytest

SPEC=importlib.util.spec_from_file_location('run_analysis',Path(__file__).parents[1]/'operators/analyze_fox_run.py')
a=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(a)
COMMIT='d3dca3d20612d3d09ed1acb680683a990cbd51ba'
SECOND='afa84a1'+COMMIT[7:]
START=datetime(2026,10,19,tzinfo=timezone.utc)


def write(tmp_path,summary,events):
    (tmp_path/'summary.json').write_text(json.dumps(summary))
    (tmp_path/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))


def fixture(tmp_path, *, seconds=28800, complete=True, commits=None, dense=False):
    commits=commits or [COMMIT];events=[]
    n=max(1,int(seconds/30)) if dense else len(commits)
    for i in range(n):
        c=commits[min(len(commits)-1,i*len(commits)//n)]
        events.append({'type':'observation','index':i,'utc':(START+timedelta(seconds=i*30)).isoformat(),'status':'pass',
            'health':{'source_identity':{'commit':c,'checked_at':c,'verified':True,'dirty':False,'disposition':'verified_manifest','source':'release_manifest','mismatches':[]}}})
    summary={'complete':complete,'started_at':START.isoformat(),'finished_at':(START+timedelta(seconds=seconds)).isoformat(),
        'elapsed_seconds':seconds,'samples':len(events),'failed_samples':0,'failures':[],'interval_seconds':30}
    write(tmp_path,summary,events);return summary,events


def test_short_producer_complete_is_not_eight_hours(tmp_path):
    fixture(tmp_path,seconds=30)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['producer_complete'] and not result['verified_eight_hour_complete']
    assert a.final_contract({'fixed_api':result,'gpu_observer':result}) is None


def test_one_sample_and_eight_hour_clock_is_not_observed_completion(tmp_path):
    fixture(tmp_path)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['elapsed_reconciled_complete']
    assert not result['coverage']['adequate'] and not result['verified_eight_hour_complete']
    assert result['coverage']['unobserved_seconds']==28770
    assert a.final_contract({'fixed_api':result,'gpu_observer':result}) is None


def test_invalid_required_timestamp_blocks_reconciliation(tmp_path):
    s,e=fixture(tmp_path);e[0]['utc']='not-a-time';write(tmp_path,s,e)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert not result['elapsed_reconciled_complete']
    assert any('required check/observation' in x for x in result['reconciliation_errors'])


def test_changed_during_read_blocks_finalization(tmp_path,monkeypatch):
    fixture(tmp_path,dense=True)
    original=a.read_input
    def unstable(path,inputs):
        data=original(path,inputs);inputs[-1]['changed_during_read']=True;return data
    monkeypatch.setattr(a,'read_input',unstable)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert not result['input_capture_consistent'] and not result['elapsed_reconciled_complete']


def test_truncated_tail_blocks_completion_and_preserves_prefix(tmp_path):
    fixture(tmp_path)
    with (tmp_path/'events.jsonl').open('a') as stream:stream.write('{"type":')
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['checks_or_samples']==1 and not result['verified_eight_hour_complete']
    assert {x['issue'] for x in result['journal_parse_issues']}=={'invalid_json','unterminated_tail'}


def test_count_mismatch_cannot_be_silently_repaired(tmp_path):
    s,e=fixture(tmp_path);s['samples']=10;write(tmp_path,s,e)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert not result['verified_eight_hour_complete']
    assert any('samples=10' in e for e in result['reconciliation_errors'])


def test_multirevision_failure_and_coverage_survive_final_contract(tmp_path):
    s,events=fixture(tmp_path,commits=[COMMIT,SECOND],dense=True)
    events[1].update(status='fail',error='Connection refused')
    s['failed_samples']=1;s['failures']=[{'index':1,'utc':events[1]['utc'],'error':'Connection refused'}];write(tmp_path,s,events)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['verified_eight_hour_complete'] and result['elapsed_reconciled_complete']
    assert result['failed_checks_or_samples']==1 and len(result['source_identity']['transitions'])==2
    # Only exercising output-shape validation here; both synthetic tracks share a fixture.
    final=a.final_contract({'fixed_api':result,'gpu_observer':result})
    assert final['schema_version']=='aster.review-run.v2'
    gpu=final['tracks']['gpu_observer']
    assert gpu['source_identity']['commit']==SECOND and gpu['failures']==1
    assert gpu['coverage']['adequate'] and gpu['coverage']['unobserved_seconds']==0
    assert gpu['source_identity']['verification']['verified_count']==2
    assert gpu['pause_seconds']==0 and gpu['pause_events']==[]
    assert a.validate_review_contract(final)==final
    broken=copy.deepcopy(final);broken['tracks']['gpu_observer'].pop('coverage')
    with pytest.raises(ValueError,match='coverage'):a.validate_review_contract(broken)
    broken=copy.deepcopy(final);broken['tracks']['gpu_observer']['source_identity'].pop('verification')
    with pytest.raises(ValueError,match='verification'):a.validate_review_contract(broken)


def test_unverified_intermediate_identity_blocks_final(tmp_path):
    s,e=fixture(tmp_path,commits=[COMMIT,SECOND],dense=True)
    e[0]['health']['source_identity']['verified']=False;write(tmp_path,s,e)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['elapsed_reconciled_complete'] and result['coverage']['adequate']
    assert not result['verified_eight_hour_complete']
    assert result['source_identity']['verification']['unverified_count']==1


def test_completed_cycle_requires_all_checks_not_counter(tmp_path):
    s,_=fixture(tmp_path)
    identity={'commit':COMMIT,'checked_at':START.isoformat(),'verified':True,'dirty':False,'disposition':'verified_manifest','source':'release_manifest','mismatches':[]}
    events=[{'type':'check','cycle':0,'check':'startup','status':'pass','utc':s['started_at'],'duration_seconds':.1,'evidence':{'health':{'source_identity':identity}}},
            {'type':'check','cycle':1,'check':'cleanup','status':'pass','utc':(START+timedelta(seconds=30)).isoformat(),'duration_seconds':1}]
    s.update(checks=events,completed_cycles=1,failures=0,setup={'health':{'source_identity':identity}});write(tmp_path,s,events)
    result=a.analyze_track(tmp_path,'fixed_api',[])
    assert result['cycles']['journal_full_cycles']==0 and not result['verified_eight_hour_complete']


def test_cpu_slow_cycle_execution_and_explicit_pause_are_separate():
    start=START.timestamp();end=start+60
    cycles=[{'first_at':START.isoformat(),'complete_check_set':True,'execution_finished_at_epoch':start+20},
            {'first_at':(START+timedelta(seconds=40)).isoformat(),'complete_check_set':True,'execution_finished_at_epoch':start+60}]
    summary={'pause_events':[{'started_at':(START+timedelta(seconds=20)).isoformat(),'ended_at':(START+timedelta(seconds=40)).isoformat(),'duration_seconds':20}]}
    checks=[{'check':'paused_read_only_health','utc':(START+timedelta(seconds=n)).isoformat(),'duration_seconds':.1} for n in [20,30]]
    result=a.coverage_analysis('fixed_api',summary,checks,[],cycles,start,end,10)
    assert result['adequate'] and result['unobserved_seconds']==0
    assert result['functional_observation_window_seconds']==40 and result['health_only_pause_seconds']==20
    without=a.coverage_analysis('fixed_api',summary,[],[],cycles,start,end,10)
    assert not without['adequate'] and without['unobserved_seconds']==20


def test_resource_interval_and_explicit_timezone_assumption(tmp_path):
    p=tmp_path/'resource.csv';p.write_text('timestamp,memory.used [MiB]\n2026/10/19 20:10:40.015,100\n2026/10/19 20:11:40.015,130\n')
    result=a.analyze_resources(p,[])
    assert result['observed_span_seconds']==60
    assert result['numeric_columns']['memory.used [MiB]']['endpoint_change_per_hour']==1800
    assert result['naive_nvidia_timestamps_assumed_utc']==2


def test_prior_cycle_window_cannot_hide_missing_pause_observations():
    start=START.timestamp()
    cycles=[{'first_at':START.isoformat(),'complete_check_set':True,'execution_finished_at_epoch':start+1},
            {'first_at':(START+timedelta(seconds=60)).isoformat(),'complete_check_set':True,'execution_finished_at_epoch':start+61}]
    summary={'pause_events':[{'started_at':(START+timedelta(seconds=20)).isoformat(),'ended_at':(START+timedelta(seconds=40)).isoformat(),'duration_seconds':20}]}
    result=a.coverage_analysis('fixed_api',summary,[],[],cycles,start,start+120,60)
    assert not result['adequate'] and result['unobserved_seconds']==20
    assert result['functional_observation_window_seconds']==100


@pytest.mark.parametrize('changed', [{'dirty':True},{'disposition':'dirty_git'},{'mismatches':['backend/app.py']}])
def test_verified_boolean_cannot_override_contradictory_manifest(tmp_path,changed):
    s,e=fixture(tmp_path,dense=True)
    e[0]['health']['source_identity'].update(changed);write(tmp_path,s,e)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['elapsed_reconciled_complete'] and result['coverage']['adequate']
    assert not result['verified_eight_hour_complete']
    assert result['source_identity']['verification']['unverified_count']==1


def test_cpu_duration_cannot_manufacture_coverage_beyond_finish(tmp_path):
    summary,_=fixture(tmp_path)
    identity={'commit':COMMIT,'verified':True,'dirty':False,'source':'release_manifest','disposition':'verified_manifest','mismatches':[]}
    events=[{'type':'check','cycle':0,'check':'startup','status':'pass','utc':START.isoformat(),'duration_seconds':.1,'evidence':{'health':{'source_identity':identity}}}]
    names=['compare_read_only','interventions','retries_and_errors','source_failures','source_model_conflict','replay_guards','cleanup']
    for cycle,offset in [(1,1),(2,100)]:
        for i,name in enumerate(names):
            events.append({'type':'check','cycle':cycle,'check':name,'status':'pass','utc':(START+timedelta(seconds=offset+i)).isoformat(),
                'duration_seconds':999999 if name=='cleanup' else .1})
    summary.update(completed_cycles=2,checks=events,failures=0,interval_seconds=300);write(tmp_path,summary,events)
    result=a.analyze_track(tmp_path,'fixed_api',[])
    assert not result['elapsed_reconciled_complete'] and not result['verified_eight_hour_complete']
    assert any('beyond reported run finish' in x for x in result['reconciliation_errors'])
    assert any('ends after the next' in x for x in result['reconciliation_errors'])

    # Genuine slow checks remain valid if they finish before the next serial check.
    for row in events:
        if row['check']=='cleanup':row['duration_seconds']=90
    summary['checks']=events;write(tmp_path,summary,events)
    valid_slow=a.analyze_track(tmp_path,'fixed_api',[])
    assert valid_slow['elapsed_reconciled_complete']
    assert not valid_slow['coverage']['adequate']  # Two short observation windows still do not cover eight hours.
