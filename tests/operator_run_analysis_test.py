"""Boundary tests for evidence reconciliation; no live services or backend imports."""
import importlib.util
import json
from pathlib import Path
import sys

SPEC=importlib.util.spec_from_file_location('run_analysis',Path(__file__).parents[1]/'operators/analyze_fox_run.py')
a=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(a)
COMMIT='d3dca3d20612d3d09ed1acb680683a990cbd51ba'
SECOND='afa84a1'+COMMIT[7:]


def fixture(tmp_path, *, seconds=28800, complete=True, commits=None):
    commits=commits or [COMMIT]
    events=[]
    for i,c in enumerate(commits):
        events.append({'type':'observation','index':i,'utc':f'2026-10-19T00:00:{i*30:02d}+00:00','status':'pass',
            'health':{'source_identity':{'commit':c,'checked_at':f'start-{i}'}}})
    summary={'complete':complete,'started_at':'2026-10-19T00:00:00+00:00',
        'finished_at':'2026-10-19T08:00:00+00:00' if seconds==28800 else '2026-10-19T00:00:30+00:00',
        'elapsed_seconds':seconds,'samples':len(events),'failed_samples':0,'failures':[],'interval_seconds':30}
    (tmp_path/'summary.json').write_text(json.dumps(summary));(tmp_path/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    return summary,events


def test_short_producer_complete_is_not_eight_hours(tmp_path):
    fixture(tmp_path,seconds=30)
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['producer_complete'] and not result['verified_eight_hour_complete']
    assert a.final_contract({'fixed_api':result,'gpu_observer':result}) is None


def test_truncated_tail_blocks_completion_and_preserves_prefix(tmp_path):
    fixture(tmp_path)
    with (tmp_path/'events.jsonl').open('a') as stream:stream.write('{"type":')
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['checks_or_samples']==1
    assert not result['verified_eight_hour_complete']
    assert {x['issue'] for x in result['journal_parse_issues']}=={'invalid_json','unterminated_tail'}


def test_count_mismatch_cannot_be_silently_repaired(tmp_path):
    s,_=fixture(tmp_path);s['samples']=10;(tmp_path/'summary.json').write_text(json.dumps(s))
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert not result['verified_eight_hour_complete']
    assert any('samples=10' in e for e in result['reconciliation_errors'])


def test_multirevision_and_failed_record_remain_visible(tmp_path):
    s,events=fixture(tmp_path,commits=[COMMIT,SECOND])
    events[1].update(status='fail',error='Connection refused')
    s['failed_samples']=1;s['failures']=[{'index':1,'utc':events[1]['utc'],'error':'Connection refused'}]
    (tmp_path/'summary.json').write_text(json.dumps(s));(tmp_path/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    result=a.analyze_track(tmp_path,'gpu_observer',[])
    assert result['verified_eight_hour_complete']
    assert result['failed_checks_or_samples']==1 and len(result['source_identity']['transitions'])==2
    assert result['source_identity']['commits']==[COMMIT,SECOND]
    final=a.final_contract({'fixed_api':result,'gpu_observer':result})
    assert final['schema_version']=='aster.review-run.v1'
    assert final['tracks']['gpu_observer']['source_identity']['commit']==SECOND
    assert final['tracks']['gpu_observer']['failures']==1


def test_completed_cycle_requires_all_checks_not_counter(tmp_path):
    s,_=fixture(tmp_path)
    identity={'commit':COMMIT,'checked_at':'2026-10-19T00:00:00Z'}
    events=[{'type':'check','cycle':0,'check':'startup','status':'pass','utc':s['started_at'],'evidence':{'health':{'source_identity':identity}}},
            {'type':'check','cycle':1,'check':'cleanup','status':'pass','utc':'2026-10-19T00:00:30Z'}]
    s.update(checks=events,completed_cycles=1,failures=0,setup={'health':{'source_identity':identity}})
    (tmp_path/'summary.json').write_text(json.dumps(s));(tmp_path/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    result=a.analyze_track(tmp_path,'fixed_api',[])
    assert result['cycles']['journal_full_cycles']==0 and not result['verified_eight_hour_complete']


def test_resource_interval_and_explicit_timezone_assumption(tmp_path):
    p=tmp_path/'resource.csv';p.write_text('timestamp,memory.used [MiB]\n2026/10/19 20:10:40.015,100\n2026/10/19 20:11:40.015,130\n')
    result=a.analyze_resources(p,[])
    assert result['observed_span_seconds']==60
    assert result['numeric_columns']['memory.used [MiB]']['endpoint_change_per_hour']==1800
    assert result['naive_nvidia_timestamps_assumed_utc']==2
