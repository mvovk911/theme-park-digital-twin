#!/usr/bin/env python3
"""Offline reconciliation of fixed API and changing-release GPU observation ledgers."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import html
import io
import json
import math
import re
from pathlib import Path
import statistics

MIN_SECONDS = 28800
SCHEDULING_TOLERANCE_SECONDS = 2.0
PAUSED_HEALTH_INTERVAL_SECONDS = 10.0
CHECK_DURATION_PRECISION_SECONDS = 0.002


def utc():
    return datetime.now(timezone.utc).isoformat()


def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.timestamp() if dt.tzinfo else None
    except (TypeError, AttributeError, ValueError):
        return None


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values):
    values = sorted(x for x in values if number(x))
    def percentile(q):
        if not values: return None
        pos = (len(values)-1)*q; lo = math.floor(pos); hi = math.ceil(pos)
        return round(values[lo]+(values[hi]-values[lo])*(pos-lo), 6)
    return {'count':len(values), 'min':values[0] if values else None, 'median':percentile(.5),
            'p95':percentile(.95), 'p99':percentile(.99), 'max':values[-1] if values else None,
            'mean':round(statistics.mean(values),6) if values else None,
            'percentile_method':'linear interpolation between sorted observations'}


def read_input(path, inputs):
    path = Path(path)
    before = path.stat(); captured = utc(); data = path.read_bytes(); after = path.stat()
    inputs.append({'path':str(path.resolve()), 'captured_at':captured, 'bytes':len(data),
        'sha256':hashlib.sha256(data).hexdigest(), 'size_before':before.st_size, 'size_after':after.st_size,
        'changed_during_read':before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns})
    return data


def read_ledger(raw):
    events=[]; errors=[]; lines=raw.splitlines()
    for n,line in enumerate(lines,1):
        if not line.strip():
            errors.append({'line':n,'issue':'blank_line'});continue
        try:
            value=json.loads(line)
            if not isinstance(value,dict): raise ValueError('event must be an object')
            events.append(value)
        except (ValueError,UnicodeDecodeError) as error:
            errors.append({'line':n,'issue':'invalid_json','error':str(error),
                'tail_line':n==len(lines), 'line_sha256':hashlib.sha256(line).hexdigest()})
    if raw and not raw.endswith(b'\n'):
        errors.append({'line':len(lines),'issue':'unterminated_tail','tail_line':True})
    return events,errors


def verification_status(identity):
    """Classify retained release-manifest evidence without claiming attestation."""
    required=['verified','dirty','disposition','source','mismatches']
    if any(key not in identity for key in required):return 'unknown'
    if (identity['verified'] is True and identity['dirty'] is False and
            identity['disposition']=='verified_manifest' and identity['source']=='release_manifest' and identity['mismatches']==[]):
        return 'verified'
    return 'unverified'


def identity_records(kind, summary, events):
    records=[]
    for e in events:
        health = e.get('health') if e.get('type')=='observation' else None
        if e.get('type')=='check' and isinstance(e.get('evidence'),dict):
            ev=e['evidence'];health=ev.get('health') or (ev if 'source_identity' in ev else None)
        if isinstance(health,dict) and isinstance(health.get('source_identity'),dict):
            records.append({'utc':e.get('utc'),'identity':health['source_identity']})
    initial=(summary.get('setup') or {}).get('health',{}).get('source_identity')
    if initial and not records: records.append({'utc':summary.get('started_at'),'identity':initial})
    transitions=[]
    for r in records:
        signature=json.dumps(r['identity'],sort_keys=True)
        if not transitions or signature!=transitions[-1]['signature']:
            transitions.append({'first_observed_at':r['utc'],'last_observed_at':r['utc'],
                'observations':1,'identity':r['identity'],'signature':signature})
        else:
            transitions[-1]['last_observed_at']=r['utc'];transitions[-1]['observations']+=1
    for t in transitions:t.pop('signature')
    commits=list(dict.fromkeys(r['identity'].get('commit') for r in records if r['identity'].get('commit')))
    checked=list(dict.fromkeys(r['identity'].get('checked_at') for r in records if r['identity'].get('checked_at')))
    return {'commits':commits,'checked_at_values':checked,'transitions':transitions,
        'identity_observations':len(records),
        'coverage_note':('Fixed API startup identity is not continuous process attestation; most cycle checks do not retain health bodies.' if kind=='fixed_api' else
            'Each retained health identity names the observed deployment; checked_at changes indicate startup-verification transitions, not proven crash causes.')}


def gaps_and_failures(samples, interval, start, end):
    valid=[(stamp(e.get('utc')),e) for e in samples if stamp(e.get('utc')) is not None]
    gaps=[]
    for (a,ea),(b,eb) in zip(valid,valid[1:]):
        if b-a > interval*1.5:
            gaps.append({'after':ea['utc'],'before':eb['utc'],'seconds':round(b-a,3),
                'estimated_missing_scheduled_samples':max(0,math.floor((b-a)/interval)-1)})
    failed=[]; active=None
    for _,e in valid:
        if e.get('status')=='fail':
            if active is None:active={'first_failed_at':e['utc'],'last_failed_at':e['utc'],'failed_records':0,'errors':[]}
            active['last_failed_at']=e['utc'];active['failed_records']+=1
            if e.get('error') not in active['errors']:active['errors'].append(e.get('error'))
        elif active:
            active['next_passing_observation_at']=e['utc'];failed.append(active);active=None
    if active:active['next_passing_observation_at']=None;failed.append(active)
    first,last=(valid[0][0],valid[-1][0]) if valid else (None,None)
    return {'inter_sample_gaps_over_1_5_intervals':gaps,'failed_sample_sequences':failed,
        'leading_unobserved_seconds':round(first-start,3) if first is not None and start is not None else None,
        'trailing_unobserved_seconds':round(end-last,3) if last is not None and end is not None else None,
        'note':'Failure sequences and gaps bound sampled evidence only; they do not establish continuous outage duration or causes.'}


def coverage_analysis(kind,summary,checks,observations,cycles,start,end,interval):
    """Cadence coverage, not uptime: union of producer schedule windows.

    A CPU cycle's next due time is max(start+interval, observed cleanup finish).
    GPU lacks execution finish: only the configured interval is supportable.
    Explicit pause checks cover their actual producer's ten-second cadence.
    """
    windows=[];functional=[];pause_windows=[];startup_windows=[];issues=[];declared_pauses=[]
    for pause in summary.get('pause_events',[]):
        begin=stamp(pause.get('started_at'));finish=stamp(pause.get('ended_at'))
        if finish is None and begin is not None and number(pause.get('duration_seconds')):finish=begin+pause['duration_seconds']
        if begin is not None and finish is not None and finish>=begin:declared_pauses.append((begin,finish))
    def add(target,begin,finish):
        if begin is not None and finish is not None and finish>=begin:
            target.append((begin,finish))
    if kind=='fixed_api':
        for c in cycles:
            begin=stamp(c['first_at']);finish=c.get('execution_finished_at_epoch')
            if c['complete_check_set'] and begin is not None and finish is not None:
                add(functional,begin,max(begin+interval,finish))
        for e in checks:
            begin=stamp(e.get('utc'));duration=e.get('duration_seconds')
            if begin is None or not number(duration) or duration<0:continue
            if e.get('check')=='startup':add(startup_windows,begin,begin+duration)
            if e.get('check')=='paused_read_only_health':
                # Only explicit pause intervals may authorize health-only coverage.
                matched=False
                for pause in summary.get('pause_events',[]):
                    pstart=stamp(pause.get('started_at'));pend=stamp(pause.get('ended_at'))
                    if pend is None and pstart is not None and number(pause.get('duration_seconds')):pend=pstart+pause['duration_seconds']
                    if pstart is not None and pend is not None and pstart<=begin<=pend+SCHEDULING_TOLERANCE_SECONDS:
                        add(pause_windows,max(begin,pstart),min(max(begin+PAUSED_HEALTH_INTERVAL_SECONDS,begin+duration),pend));matched=True
                if not matched:issues.append('Paused health check has no matching explicit pause interval.')
    else:
        for e in observations:
            begin=stamp(e.get('utc'))
            if begin is not None:add(functional,begin,begin+interval)
    def merged(rows):
        clipped=sorted((max(a,start),min(b,end)) for a,b in rows if start is not None and end is not None and b>start and a<end)
        result=[]
        for a,b in clipped:
            if b<a:continue
            if result and a<=result[-1][1]:result[-1]=(result[-1][0],max(b,result[-1][1]))
            else:result.append((a,b))
        return result
    # Pause time cannot be covered by a prior cycle's otherwise valid cadence window.
    for pa,pb in declared_pauses:
        split=[]
        for a,b in functional:
            if pb<=a or pa>=b:split.append((a,b))
            else:
                if a<pa:split.append((a,pa))
                if pb<b:split.append((pb,b))
        functional=split
    all_windows=merged(functional+pause_windows+startup_windows);uncovered=[]
    def gap(a,b):
        if b>a:uncovered.append({'started_at':datetime.fromtimestamp(a,timezone.utc).isoformat(),
            'finished_at':datetime.fromtimestamp(b,timezone.utc).isoformat(),'seconds':round(b-a,6)})
    cursor=start
    if start is not None and end is not None and end>=start:
        for a,b in all_windows:gap(cursor,a);cursor=max(cursor,b)
        gap(cursor,end)
    else:issues.append('Valid run window is unavailable.')
    count=sum(c['complete_check_set'] for c in cycles) if kind=='fixed_api' else len(observations)
    if count<2:issues.append('At least two repeated functional cycles/observations are needed to establish sampling across time.')
    maxgap=max((g['seconds'] for g in uncovered),default=0)
    if maxgap>SCHEDULING_TOLERANCE_SECONDS:issues.append('An uncovered schedule interval exceeds the fixed scheduling tolerance.')
    duration=lambda rows:round(sum(b-a for a,b in merged(rows)),6)
    return {'adequate':not issues,'method':'union_of_configured_schedule_windows_with_known_CPU_execution_finish',
        'scheduling_tolerance_seconds':SCHEDULING_TOLERANCE_SECONDS,'configured_interval_seconds':interval,
        'paused_health_interval_seconds':PAUSED_HEALTH_INTERVAL_SECONDS if kind=='fixed_api' else None,
        'observed_records':count,'uncovered_intervals':uncovered,
        'unobserved_seconds':round(sum(g['seconds'] for g in uncovered),6),'max_unobserved_seconds':maxgap,
        'functional_observation_window_seconds':duration(functional),'health_only_pause_seconds':duration(pause_windows),
        'startup_check_seconds':duration(startup_windows),'issues':issues,
        'limitations':['Schedule coverage is not continuous uptime or continuous functional activity.',
            'The fixed 2-second scheduling allowance is a declared bookkeeping/poll tolerance (CPU idle polls up to 1 second); it is not fitted to observed results. All gaps, even tolerated gaps, remain reported.',
            'Failed records count as observations; success fraction is separate.',
            'GPU observation execution duration is not retained, so long gaps cannot be excused by an assumed long request.',
            'Startup checks and explicit pause health checks are separate from functional cycle windows.']}


def analyze_track(directory, kind, inputs):
    directory=Path(directory);warnings=[];errors=[];input_start=len(inputs)
    summary=json.loads(read_input(directory/'summary.json',inputs))
    events,parse_errors=read_ledger(read_input(directory/'events.jsonl',inputs))
    capture_consistent=not any(x['changed_during_read'] for x in inputs[input_start:])
    if not capture_consistent:errors.append('An input file changed during read; finalization requires a stable captured input.')
    if parse_errors:errors.append('Journal contains malformed, blank or unterminated records; see journal_parse_issues.')
    checks=[e for e in events if e.get('type')=='check']
    observations=[e for e in events if e.get('type')=='observation']
    records=checks if kind=='fixed_api' else observations
    failures=[{'utc':e.get('utc'),'check':e.get('check'),'cycle':e.get('cycle'),'index':e.get('index'),'error':e.get('error')}
              for e in records if e.get('status')=='fail']
    invalid_status=[e for e in records if e.get('status') not in ['pass','fail']]
    if any(stamp(e.get('utc')) is None for e in records):errors.append('A required check/observation has an invalid timezone-aware UTC timestamp.')
    required_times=[stamp(e.get('utc')) for e in records if stamp(e.get('utc')) is not None]
    if any(b<a for a,b in zip(required_times,required_times[1:])):errors.append('Required check/observation timestamps decrease in producer order.')
    if any(not number(e.get('duration_seconds')) or e['duration_seconds']<0 for e in checks):errors.append('A required check has an invalid or missing execution duration.')
    for before,after in zip(checks,checks[1:]):
        begin,next_begin=stamp(before.get('utc')),stamp(after.get('utc'));duration=before.get('duration_seconds')
        if begin is not None and next_begin is not None and number(duration) and begin+duration>next_begin+CHECK_DURATION_PRECISION_SECONDS:
            errors.append(f'Serial check {before.get("check")} ends after the next required check starts; execution duration is contradictory.')
    if invalid_status:errors.append(f'{len(invalid_status)} check/sample records have unsupported status.')
    summary_failures=summary.get('failures') if kind=='fixed_api' else summary.get('failed_samples')
    if summary_failures != len(failures):errors.append(f'Summary failure count {summary_failures!r} differs from journal {len(failures)}.')
    per_type=defaultdict(lambda:Counter())
    for e in records:per_type[e.get('check','observation')][e.get('status','unknown')]+=1
    cycles=None;cycle_detail=[]
    if kind=='fixed_api':
        saved_checks=summary.get('checks',[])
        if saved_checks != checks:errors.append(f'Summary check records differ from journal: summary={len(saved_checks)}, journal={len(checks)}; content/order also compared.')
        grouped=defaultdict(list)
        for e in checks:
            if isinstance(e.get('cycle'),int) and e['cycle']>0 and e.get('check') not in ['paused_read_only_health','final_cleanup']:
                grouped[e['cycle']].append(e)
        # Supported producer protocol: six regular checks, three optional planner checks, then cleanup.
        required={'compare_read_only','interventions','retries_and_errors','source_failures','source_model_conflict','replay_guards','cleanup'}
        if any(str(e.get('check','')).startswith('planning_') for e in checks):
            required.update(['planning_counterfactuals','planning_degraded_input','planning_assumption_stress'])
        complete_cycles=0
        for n,rows in sorted(grouped.items()):
            names=Counter(x.get('check') for x in rows);missing=sorted(required-set(names));duplicates={k:v for k,v in names.items() if v>1}
            finished=not missing and not duplicates and rows[-1].get('check')=='cleanup'
            complete_cycles+=int(finished)
            cycle_detail.append({'cycle':n,'checks':len(rows),'first_at':rows[0].get('utc'),'last_at':rows[-1].get('utc'),
                'complete_check_set':finished,'missing_checks':missing,'duplicate_checks':duplicates,
                'execution_finished_at_epoch':(stamp(rows[-1].get('utc'))+rows[-1]['duration_seconds']) if stamp(rows[-1].get('utc')) is not None and number(rows[-1].get('duration_seconds')) else None})
        cycles={'reported_completed_cycles':summary.get('completed_cycles'),'journal_started_cycles':len(grouped),
                'journal_full_cycles':complete_cycles,'expected_checks_per_cycle':len(required),'details':cycle_detail}
        if summary.get('completed_cycles') != complete_cycles:
            errors.append(f'Reported completed_cycles={summary.get("completed_cycles")} differs from full journal cycles={complete_cycles}; producer increments before cycle work.')
        if sorted(grouped)!=list(range(1,max(grouped,default=0)+1)):errors.append('Cycle IDs are not contiguous from one.')
        if len([e for e in checks if e.get('check')=='startup'])!=1:errors.append('Expected exactly one startup check.')
    else:
        if summary.get('samples') != len(observations):errors.append(f'Summary samples={summary.get("samples")} differs from journal={len(observations)}.')
        indexes=[e.get('index') for e in observations]
        if indexes!=list(range(len(indexes))):errors.append('GPU observation indices are not contiguous from zero (missing/duplicate/reordered records).')
        saved=[{'index':e.get('index'),'utc':e.get('utc'),'error':e.get('error')} for e in observations if e.get('status')=='fail']
        if summary.get('failures',[]) != saved:errors.append('GPU summary failure list differs from journal failures.')
    start,finish=stamp(summary.get('started_at')),stamp(summary.get('finished_at'))
    elapsed=summary.get('elapsed_seconds');span=finish-start if start is not None and finish is not None else None
    if finish is not None:
        for check in checks:
            begin=stamp(check.get('utc'));duration=check.get('duration_seconds')
            if begin is not None and number(duration) and begin+duration>finish+CHECK_DURATION_PRECISION_SECONDS:
                errors.append(f'Check {check.get("check")} execution finish extends beyond reported run finish.')
    event_times=[stamp(e.get('utc')) for e in events if stamp(e.get('utc')) is not None]
    if len(event_times)!=len(events):warnings.append('Some journal records lack a parseable timezone-aware utc timestamp.')
    if any(b<a for a,b in zip(event_times,event_times[1:])):warnings.append('Mixed journal timestamps are not monotonic: check.utc records check start, while HTTP utc records request completion. This alone does not establish clock movement or reordered observations.')
    if span is not None and number(elapsed) and abs(span-elapsed)>2:errors.append('UTC start/finish span and reported monotonic elapsed differ by more than two seconds.')
    if start is None:errors.append('Missing or invalid timezone-aware start timestamp.')
    if summary.get('complete') is True and finish is None:errors.append('Producer marked complete without a valid finish timestamp.')
    if event_times and start is not None and min(event_times)<start-1:errors.append('Journal contains records preceding reported start.')
    if event_times and finish is not None and max(event_times)>finish+1:errors.append('Journal contains records after reported finish.')
    interval=summary.get('interval_seconds')
    if not number(interval) or interval<=0:errors.append('Missing or invalid configured observation interval; diagnostic fallback is not completion evidence.')
    interval=interval if number(interval) and interval>0 else 30 if kind=='gpu_observer' else 300
    endpoint=finish if finish is not None else start+elapsed if start is not None and number(elapsed) else max(event_times,default=None)
    selected=observations if kind=='gpu_observer' else [dict(type='cycle',utc=c['first_at'],status='pass' if c['complete_check_set'] else 'fail') for c in cycle_detail]
    availability=gaps_and_failures(selected,interval,start,endpoint)
    if availability['inter_sample_gaps_over_1_5_intervals']:warnings.append('Recorded sampling gaps exceed 1.5 requested intervals; inspect unobserved spans.')
    if (availability['trailing_unobserved_seconds'] or 0)>interval*1.5:warnings.append('Trailing time without a retained cycle/sample exceeds 1.5 requested intervals; elapsed duration does not establish observations in that span.')
    if (availability['leading_unobserved_seconds'] or 0)>interval*1.5:warnings.append('Leading time without a retained cycle/sample exceeds 1.5 requested intervals.')
    identities=identity_records(kind,summary,events)
    if kind=='fixed_api' and len(identities['commits'])>1:errors.append('Fixed API track contains multiple source commits.')
    if kind=='gpu_observer' and len(identities['commits'])>1:warnings.append('GPU observer spans multiple deployments; this is not a single-release soak.')
    if not identities['commits']:errors.append('No source commit identity retained in supplied ledger.')
    if any(not re.fullmatch(r'[0-9a-f]{40}',c) or len(set(c))==1 for c in identities['commits']):errors.append('Source commit identity is not a valid full non-placeholder Git SHA.')
    if not records:errors.append('No functional checks or observation samples in journal.')
    if kind=='fixed_api' and cycles['journal_full_cycles']<1:errors.append('No full functional cycle established.')
    health=[e for e in events if e.get('type')=='http' and e.get('path')=='/api/health']
    transport=[{'utc':e.get('utc'),'path':e.get('path'),'method':e.get('method'),'error':e.get('error')} for e in events if e.get('type')=='transport_error']
    frame_ages=[e.get('frame',{}).get('age_seconds') for e in observations]
    paused=summary.get('pause_seconds',0)
    pause_events=summary.get('pause_events',[])
    if not number(paused) or paused<0:errors.append('Invalid pause_seconds.')
    durations=[]
    for pause in pause_events:
        duration=pause.get('duration_seconds');a,b=stamp(pause.get('started_at')),stamp(pause.get('ended_at'))
        if not number(duration) or duration<0 or a is None or (pause.get('ended_at') is not None and b is None):errors.append('Invalid pause timestamp/duration evidence.')
        elif b is not None and abs(b-a-duration)>SCHEDULING_TOLERANCE_SECONDS:errors.append('Pause UTC span differs from its reported duration.')
        else:durations.append(duration)
    if number(paused) and abs(sum(durations)-paused)>SCHEDULING_TOLERANCE_SECONDS:errors.append('Pause duration total differs from pause_seconds.')
    if paused:warnings.append('Elapsed wall time includes paused health-only periods; report functional cycle count separately.')
    elapsed_complete=summary.get('complete') is True and number(elapsed) and elapsed>=MIN_SECONDS and span is not None and span>=MIN_SECONDS and not errors
    coverage=coverage_analysis(kind,summary,checks,observations,cycle_detail,start,endpoint,interval)
    verification=Counter(verification_status(r['identity']) for r in identities['transitions'])
    identities['verification']={'verified_count':verification['verified'],'unverified_count':verification['unverified'],'unknown_count':verification['unknown'],
        'count_unit':'source_identity_transitions', 'all_observed_identities_verified':bool(identities['transitions']) and not verification['unverified'] and not verification['unknown']}
    complete=elapsed_complete and coverage['adequate'] and identities['verification']['all_observed_identities_verified']
    if not complete:warnings.append('Incomplete or inconsistent evidence: no verified eight-hour completion claim is permitted.')
    return {'track':kind,'producer_complete':summary.get('complete') is True,'verified_eight_hour_complete':complete,
        'elapsed_reconciled_complete':elapsed_complete,'coverage':coverage,'input_capture_consistent':capture_consistent,
        'started_at':summary.get('started_at'),'finished_at':summary.get('finished_at'),'elapsed_seconds':elapsed,
        'utc_span_seconds':round(span,6) if span is not None else None,'requested_duration_seconds':summary.get('requested_duration_seconds'),
        'pause_seconds':paused,'pause_events':summary.get('pause_events',[]),'phase':summary.get('phase'),
        'journal_records':len(events),'journal_event_types':dict(Counter(e.get('type','unknown') for e in events)),
        'checks_or_samples':len(records),'failed_checks_or_samples':len(failures),'passed_checks_or_samples':sum(e.get('status')=='pass' for e in records),
        'observed_passing_sample_fraction':round(sum(e.get('status')=='pass' for e in records)/len(records),6) if records else None,
        'availability_scope':'Fraction of recorded checks/samples; not continuous uptime, not guest outcomes.',
        'check_types':dict(per_type),'cycles':cycles,'failures':failures,'transport_errors':transport,
        'health_http_latency_ms':distribution([e.get('elapsed_ms') for e in health]),
        'health_http_status_counts':dict(Counter(str(e.get('status')) for e in health)),
        'health_latency_scope':'Recorded completed HTTP health requests, including HTTP errors. Transport failures have no elapsed_ms and are listed separately.',
        'frame_age_seconds':distribution(frame_ages),'availability_intervals':availability,'source_identity':identities,
        'journal_parse_issues':parse_errors,'reconciliation_errors':errors,'warnings':warnings}


def analyze_resources(path,inputs):
    if not path:return None
    raw=read_input(path,inputs);rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    headers=list(rows[0]) if rows else []
    time_key=next((k for k in headers if k.lower() in ['utc','timestamp','time','sampled_at','observed_at','captured_at']),None)
    naive_utc=0
    times=[]
    for r in rows:
        value=r.get(time_key) if time_key else None
        ts=stamp(value)
        if ts is None and value:
            try:
                ts=datetime.strptime(value.strip(),'%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc).timestamp();naive_utc+=1
            except ValueError:pass
        times.append(ts)
    valid=[x for x in times if x is not None];span=max(valid)-min(valid) if valid else None
    metrics={}
    for key in headers:
        vals=[]
        for i,r in enumerate(rows):
            try:v=float(r[key])
            except (ValueError,TypeError):continue
            if math.isfinite(v):vals.append((i,v))
        if not vals:continue
        first,last=vals[0],vals[-1];delta=last[1]-first[1]
        metric_span=(times[last[0]]-times[first[0]]) if times[first[0]] is not None and times[last[0]] is not None else None
        metrics[key]={**distribution([v for _,v in vals]),'first':first[1],'last':last[1],'last_minus_first':delta,
            'endpoint_change_per_hour':round(delta/metric_span*3600,6) if metric_span and metric_span>0 else None}
    return {'rows':len(rows),'columns':headers,'timestamp_column':time_key,
        'first_observed_at':rows[0].get(time_key) if rows and time_key else None,
        'last_observed_at':rows[-1].get(time_key) if rows and time_key else None,
        'observed_span_seconds':span,'numeric_columns':metrics,'naive_nvidia_timestamps_assumed_utc':naive_utc,
        'limits':['Resource sampling began later than the API/GPU experiment (reported start 20:10:39 UTC); this file does not establish full eight-hour resource coverage.',
            'NVIDIA CSV timestamps without timezone are interpreted as UTC based on this experiment context; this is an explicit assumption, not timezone evidence in the CSV.',
            'Measurements may include the static renderer and other processes. Endpoint trends are descriptive, not memory-leak certification or workload attribution.',
            'Numeric columns retain CSV units/names; numeric IDs or counters must not be interpreted as utilization. No interpolation across missing samples.']}


def validate_review_contract(data):
    """Shared fail-closed final-deck gate. Raises ValueError; no I/O or side effects."""
    def demand(condition,message):
        if not condition:raise ValueError(message)
    demand(isinstance(data,dict),'Contract must be an object')
    demand(data.get('schema_version')=='aster.review-run.v2','Expected aster.review-run.v2')
    demand(isinstance(data.get('tracks'),dict),'Tracks must be an object')
    demand(set(data.get('tracks',{}))=={'fixed_api','gpu_observer'},'Both experiment tracks are required')
    demand(data.get('input_capture_consistent') is True,'Stable exact input capture is required')
    demand(isinstance(data.get('inputs'),list) and not any(not isinstance(i,dict) or i.get('changed_during_read') is not False for i in data['inputs']),'Input manifest contains an unstable or unknown capture')
    for name,t in data['tracks'].items():
        prefix=name+': '
        demand(isinstance(t,dict),prefix+'track must be an object')
        start,finish=stamp(t.get('started_at')),stamp(t.get('finished_at'));elapsed=t.get('elapsed_seconds')
        demand(t.get('complete') is True and t.get('elapsed_reconciled_complete') is True,prefix+'reconciled completion required')
        demand(number(elapsed) and elapsed>=MIN_SECONDS and start is not None and finish is not None and finish-start>=MIN_SECONDS,prefix+'eight-hour elapsed and UTC span required')
        demand(abs(finish-start-elapsed)<=SCHEDULING_TOLERANCE_SECONDS,prefix+'elapsed/UTC mismatch')
        demand(type(t.get('cycles')) is int and t['cycles']>=2,prefix+'at least two repeated functional cycles/observations required')
        demand(type(t.get('failures')) is int and t['failures']>=0,prefix+'failure count required')
        demand(isinstance(t.get('failed_records'),list) and len(t['failed_records'])==t['failures'],prefix+'failed record ledger must match failure count')
        demand(isinstance(t.get('transport_errors'),list),prefix+'transport error ledger required')
        demand(isinstance(t.get('warnings'),list) and t.get('reconciliation_errors')==[],prefix+'warnings and empty reconciled error ledger required')
        coverage=t.get('coverage',{})
        demand(isinstance(coverage,dict),prefix+'coverage must be an object')
        demand(coverage.get('method')=='union_of_configured_schedule_windows_with_known_CPU_execution_finish',prefix+'supported coverage method required')
        demand(isinstance(coverage.get('limitations'),list) and bool(coverage['limitations']),prefix+'coverage limitations required')
        demand(coverage.get('adequate') is True,prefix+'adequate scheduled observation coverage required')
        demand(coverage.get('scheduling_tolerance_seconds')==SCHEDULING_TOLERANCE_SECONDS,prefix+'unsupported coverage tolerance')
        demand(number(coverage.get('configured_interval_seconds')) and coverage['configured_interval_seconds']>0,prefix+'configured cadence required')
        demand(type(coverage.get('observed_records')) is int and coverage['observed_records']>=2,prefix+'repeated coverage observations required')
        demand(coverage['observed_records']==t['cycles'],prefix+'coverage observation count differs from cycles/samples')
        for key in ['unobserved_seconds','max_unobserved_seconds','functional_observation_window_seconds','health_only_pause_seconds']:
            demand(number(coverage.get(key)) and coverage[key]>=0,prefix+'missing/invalid coverage '+key)
        demand(isinstance(coverage.get('uncovered_intervals'),list),prefix+'uncovered interval ledger required')
        demand(coverage['max_unobserved_seconds']<=SCHEDULING_TOLERANCE_SECONDS,prefix+'uncovered interval exceeds declared scheduling tolerance')
        demand(all(isinstance(g,dict) for g in coverage['uncovered_intervals']),prefix+'invalid uncovered interval')
        demand(all(number(g.get('seconds')) and 0<=g['seconds']<=SCHEDULING_TOLERANCE_SECONDS for g in coverage['uncovered_intervals']),prefix+'coverage gap exceeds scheduling tolerance')
        gaps=coverage['uncovered_intervals']
        demand(abs(sum(g['seconds'] for g in gaps)-coverage['unobserved_seconds'])<=0.00001,prefix+'unobserved gap total mismatch')
        demand(abs(max((g['seconds'] for g in gaps),default=0)-coverage['max_unobserved_seconds'])<=0.00001,prefix+'maximum gap mismatch')
        for g in gaps:
            ga,gb=stamp(g.get('started_at')),stamp(g.get('finished_at'))
            demand(ga is not None and gb is not None and start<=ga<=gb<=finish and abs(gb-ga-g['seconds'])<=0.00001,prefix+'invalid gap timestamps/duration')
        availability=t.get('availability_intervals',{})
        demand(isinstance(availability,dict) and isinstance(availability.get('inter_sample_gaps_over_1_5_intervals'),list) and isinstance(availability.get('failed_sample_sequences'),list) and 'leading_unobserved_seconds' in availability and 'trailing_unobserved_seconds' in availability,prefix+'availability intervals required')
        demand(number(t.get('pause_seconds')) and t['pause_seconds']>=0 and isinstance(t.get('pause_events'),list),prefix+'pause evidence required')
        identity=t.get('source_identity',{})
        demand(isinstance(identity,dict),prefix+'identity must be an object')
        verification=identity.get('verification',{})
        demand(isinstance(verification,dict),prefix+'verification must be an object')
        for key in ['verified_count','unverified_count','unknown_count']:
            demand(type(verification.get(key)) is int and verification[key]>=0,prefix+'identity verification counts required')
        demand(verification['verified_count']>0 and verification['unverified_count']==0 and verification['unknown_count']==0,prefix+'all observed source identities must be verified')
        demand(isinstance(t.get('source_transitions'),list) and bool(t['source_transitions']),prefix+'source transitions required')
        for row in t['source_transitions']:
            demand(isinstance(row,dict) and isinstance(row.get('identity'),dict),prefix+'invalid source transition')
            source=row['identity'];commit=source.get('commit','')
            demand(verification_status(source)=='verified' and isinstance(commit,str) and re.fullmatch(r'[0-9a-f]{40}',commit) and len(set(commit))>1,prefix+'unverified or invalid source transition')
        actual=Counter(verification_status(row['identity']) for row in t['source_transitions'])
        demand(all(verification[k+'_count']==actual[k] for k in ['verified','unverified','unknown']),prefix+'verification counts differ from retained transitions')
        commits=list(dict.fromkeys(row['identity']['commit'] for row in t['source_transitions']))
        demand(t.get('observed_commits')==commits and identity.get('deployment_commits')==commits,prefix+'observed commit lists must match retained transitions')
        demand(identity.get('commit')==t['source_transitions'][-1]['identity']['commit'] and verification_status(identity)=='verified',prefix+'primary identity must be verified and last observed')
        commit=identity.get('commit','')
        demand(isinstance(commit,str) and re.fullmatch(r'[0-9a-f]{40}',commit) and len(set(commit))>1,prefix+'valid primary commit required')
    return data


def final_contract(tracks,inputs=None):
    if not all(t['verified_eight_hour_complete'] for t in tracks.values()):return None
    if any(i['changed_during_read'] for i in (inputs or [])):return None
    result={'schema_version':'aster.review-run.v2','complete':True,'input_capture_consistent':True,'inputs':inputs or [],'tracks':{
        name:{'complete':True,'elapsed_reconciled_complete':t['elapsed_reconciled_complete'],
              'started_at':t['started_at'],'finished_at':t['finished_at'],'elapsed_seconds':t['elapsed_seconds'],
              'cycles':t['cycles']['journal_full_cycles'] if t['cycles'] else t['checks_or_samples'],
              'cycle_unit':'functional_cycles' if t['cycles'] else 'observation_samples',
              'failures':t['failed_checks_or_samples'],'failed_records':t['failures'],'transport_errors':t['transport_errors'],'coverage':t['coverage'],
              'pause_seconds':t['pause_seconds'],'pause_events':t['pause_events'],
              'warnings':t['warnings'],'reconciliation_errors':t['reconciliation_errors'],
              'availability_intervals':t['availability_intervals'],
              'source_identity':{**t['source_identity']['transitions'][-1]['identity'],
                  'deployment_commits':t['source_identity']['commits'],
                  'verification':t['source_identity']['verification'],
                  'primary_identity_scope':'Last observed source identity; not a claim that the entire run used this source.'},
              'observed_commits':t['source_identity']['commits'],
              'source_transitions':t['source_identity']['transitions']}
        for name,t in tracks.items()},'scope':'Reconciled elapsed experiment and adequate scheduled observations, including explicitly reported health-only pauses; not continuous uptime or eight hours of uninterrupted functional exercise. Failures remain visible.'}
    try:return validate_review_contract(result)
    except ValueError:return None


def markdown(report):
    lines=['# FOX run evidence analysis','',f'Analysis captured at {report["analyzed_at"]}.', '',
        '**Verified eight-hour completion for both tracks: '+('yes' if report['complete'] else 'no')+'.**', '',
        '| Track | Producer complete | Elapsed seconds | UTC span | Full cycles / samples | Failures |',
        '|---|---:|---:|---:|---:|---:|']
    for name,t in report['tracks'].items():
        count=t['cycles']['journal_full_cycles'] if t['cycles'] else t['checks_or_samples']
        lines.append(f'| {name} | {t["producer_complete"]} | {t["elapsed_seconds"]} | {t["utc_span_seconds"]} | {count} | {t["failed_checks_or_samples"]} |')
    lines += ['', 'These are recorded checks and observation samples, **not continuous uptime**. Expected negative-test HTTP responses are not automatically failures; recorded failed checks and transport failures remain visible. No failure is reclassified as a deployment artifact without additional evidence.']
    for name,t in report['tracks'].items():
        lines += ['',f'## {name}','',f'Source commits: {", ".join(t["source_identity"]["commits"]) or "not recorded"}.',
            f'Elapsed/reconciled complete: {t["elapsed_reconciled_complete"]}; scheduled coverage adequate: {t["coverage"]["adequate"]}. Unobserved schedule seconds: {t["coverage"]["unobserved_seconds"]}; largest uncovered interval: {t["coverage"]["max_unobserved_seconds"]} seconds.',
            f'Paused wall time: {t["pause_seconds"]} seconds. Health request latency: {json.dumps(t["health_http_latency_ms"])}.',
            f'Frame age: {json.dumps(t["frame_age_seconds"])}.',
            f'Journal records: {t["journal_records"]}; check/sample types: {json.dumps(t["check_types"])}.',
            f'Source verification transitions: {len(t["source_identity"]["transitions"])}; transport errors: {len(t["transport_errors"])}.']
        for msg in t['coverage']['issues']:lines += ['',f'- **Coverage limit:** {msg}']
        lines += ['',f'Source verification: {json.dumps(t["source_identity"]["verification"])}.']
        for msg in t['reconciliation_errors']:lines += ['',f'- **Reconciliation error:** {msg}']
        for msg in t['warnings']:lines += ['',f'- {msg}']
        for fail in t['failures']:lines += ['',f'- Failed record {fail["utc"]}, {fail.get("check") or fail.get("index")}: {fail["error"]}']
    if report['resources']:
        r=report['resources'];lines += ['', '## Resource observations','',f'{r["rows"]} rows, {r["first_observed_at"]} through {r["last_observed_at"]}; observed span {r["observed_span_seconds"]} seconds.']
        lines += ['','| CSV column | Min | Max | First | Last | Endpoint change/hour |','|---|---:|---:|---:|---:|---:|']
        for key,m in r['numeric_columns'].items():lines.append(f'| {key} | {m["min"]} | {m["max"]} | {m["first"]} | {m["last"]} | {m["endpoint_change_per_hour"]} |')
        lines += ['',*r['limits']]
    lines += ['', 'Exact input SHA256, sizes, capture times, failed-sample sequences, unobserved intervals, source identities and reconciliation details are in `analysis.json`. Files are captured individually, not as an atomic cross-file snapshot. A live writer can therefore produce a temporary count mismatch; it is reported, never silently corrected.', '',
        'The final `aster.review-run.v2` file is emitted only when both producers report completion, both monotonic elapsed and actual timezone-aware start/finish spans are at least 28,800 seconds, and the ledgers reconcile. Failed checks can remain in a completed run.']
    return '\n'.join(lines)+'\n'


def timeline(report):
    tracks=report['tracks'];starts=[stamp(t['started_at']) for t in tracks.values() if stamp(t['started_at']) is not None]
    if not starts:return '<svg xmlns="http://www.w3.org/2000/svg"><text x="10" y="20">No valid timestamps</text></svg>'
    origin=min(starts);end=max([origin+MIN_SECONDS]+[stamp(t['started_at'])+t['elapsed_seconds'] for t in tracks.values() if stamp(t['started_at']) is not None and number(t['elapsed_seconds'])])
    def x(ts):return 190+780*(ts-origin)/(end-origin)
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1020" height="280" viewBox="0 0 1020 280">',
        '<rect width="1020" height="280" fill="#101923"/>','<g fill="#e8eef3" font-family="sans-serif" font-size="14">',
        '<text x="24" y="30">Recorded experiment windows — sampled evidence, not continuous uptime</text>']
    for i,(name,t) in enumerate(tracks.items()):
        y=80+i*80;s=stamp(t['started_at']);e=s+t['elapsed_seconds'] if s is not None and number(t['elapsed_seconds']) else s
        out.append(f'<text x="24" y="{y+5}">{html.escape(name)}</text>')
        out.append(f'<line x1="190" y1="{y}" x2="970" y2="{y}" stroke="#465566" stroke-width="12"/>')
        if s is not None and e is not None:out.append(f'<line x1="{x(s):.2f}" y1="{y}" x2="{x(e):.2f}" y2="{y}" stroke="#4db7ae" stroke-width="12"/>')
        for fail in t['failures']:
            ts=stamp(fail['utc'])
            if ts is not None:out.append(f'<circle cx="{x(ts):.2f}" cy="{y}" r="5" fill="#ff796f"/>')
        for transition in t['source_identity']['transitions'][1:]:
            ts=stamp(transition['first_observed_at'])
            if ts is not None:out.append(f'<line x1="{x(ts):.2f}" y1="{y-12}" x2="{x(ts):.2f}" y2="{y+12}" stroke="#eac657" stroke-width="2"/>')
        out.append(f'<text x="190" y="{y+30}" font-size="12">{html.escape(str(t["elapsed_seconds"]))} s; complete={str(t["verified_eight_hour_complete"]).lower()}</text>')
    for hour in range(9):out.append(f'<text x="{x(origin+hour*3600):.2f}" y="228" font-size="12">{hour}h</text>')
    out += ['<text x="24" y="263" font-size="12">Teal: reported wall window. Red: failed record. Gold: changed source verification identity. Gray: planned window.</text>','</g></svg>']
    return '\n'.join(out)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-dir',required=True);parser.add_argument('--gpu-dir',required=True)
    parser.add_argument('--resource-csv');parser.add_argument('--output',required=True)
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=False);inputs=[]
    tracks={name:analyze_track(path,name,inputs) for name,path in [('fixed_api',args.api_dir),('gpu_observer',args.gpu_dir)]}
    resources=analyze_resources(args.resource_csv,inputs);contract=final_contract(tracks,inputs)
    report={'schema':'aster.run-analysis.v1','analyzed_at':utc(),'complete':contract is not None,'tracks':tracks,'resources':resources,
        'inputs':inputs,'analyzer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':['Inputs captured separately; ongoing writes can make a partial snapshot inconsistent.',
                  'No provider inventory, live HTTP, database writes or source mutations are performed.',
                  'Check success does not establish business value, model calibration or safety.']}
    (out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');(out/'analysis.md').write_text(markdown(report));(out/'timeline.svg').write_text(timeline(report))
    if contract:(out/'review-run.json').write_text(json.dumps(contract,indent=2)+'\n')
    print(json.dumps({'complete':report['complete'],'output':str(out),'reconciliation_errors':{k:len(v['reconciliation_errors']) for k,v in tracks.items()}}))

if __name__=='__main__':main()
