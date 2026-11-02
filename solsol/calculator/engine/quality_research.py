"""Budget evidence from frozen feasible archives; never a probability of optimality."""
import json
import copy
import threading
import uuid
import re
from pathlib import Path
import numpy as np
from .store import digest, sha, atomic_json
from .hard_constraints import reports
from .comparison_basis import freeze_basis
from .quality_values import finite_fg, feasible_fg, quality_definition

SOURCES = [
    dict(label='Knowles·Thiele·Zitzler (2006): 반복 실행과 품질 지표',url='https://sop.tik.ee.ethz.ch/publicationListFiles/ktz2006a.pdf'),
    dict(label='Ishibuchi 외 (2015): 지배 관계를 반영한 IGD+',url='https://doi.org/10.1145/2739480.2754792'),
    dict(label='Fonseca 외 (2011): 반복 실행의 성능 도달 빈도',url='https://lopez-ibanez.eu/doc/FonGueLopPaq2011emo.pdf')]

JOBS={}
LOCK=threading.RLock()

def study_status(cid,parent_id,key):
    with LOCK:
        value=JOBS[key]
        if value['experiment_contract_id']!=cid or value['parent_run_id']!=parent_id:raise ValueError('반복 비교 요청이 현재 실행과 다릅니다.')
        return copy.deepcopy(value)

def start_study(get_record,cid,parent_id,ids):
    if not ids or len(set(ids))!=len(ids) or parent_id in ids or any(str(uuid.UUID(i))!=i for i in ids):raise ValueError('서로 다른 반복 실행 ID를 선택하세요.')
    with LOCK:
        for j in JOBS.values():
            if j['parent_run_id']==parent_id and j['state']=='running':
                if j['run_ids']==ids:return copy.deepcopy(j)
                raise ValueError('현재 실행의 다른 비교가 진행 중입니다.')
        key=str(uuid.uuid4());job=dict(comparison_id=key,experiment_contract_id=cid,parent_run_id=parent_id,run_ids=list(ids),state='running',phase='저장 원시 자료 대조',loaded_runs=0,total_runs=len(ids)+1)
        JOBS[key]=job
    def work():
        try:
            records=[]
            for rid in [parent_id]+ids:
                records.append(get_record(cid,rid))
                with LOCK:job['loaded_runs']+=1
            with LOCK:job['phase']='같은 조건 확인·품질 지표 계산'
            result=save_study(records[0],records[1:])
            with LOCK:job.update(state='completed',phase='비교 저장 완료',result=result)
        except Exception as exc:
            with LOCK:job.update(state='failed',phase='비교 조건 또는 계산 확인 필요',error=str(exc))
    threading.Thread(target=work,daemon=True).start()
    return study_status(cid,parent_id,key)

def nondominated(f):
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
    f=np.unique(np.asarray(f,float),axis=0)
    return f[NonDominatedSorting().do(f,only_non_dominated_front=True)] if len(f) else f

def calculate(records):
    """Common fixed empirical scale for every checkpoint and run in this report.

    Single-run reference is deliberately retrospective, not independent validation.
    Repeated-run reports require callers to validate frozen problem/search identity.
    """
    from pymoo.indicators.hv import HV
    from pymoo.indicators.igd_plus import IGDPlus
    valid=[];fronts=[];basis_sources=[];eligibility=[]
    for r in records:
        audits=reports(r);packet=r.packet(include_rows=False,compact_checkpoints=True);tol=packet['archive_policy']['tolerance']
        basis_sources.append(dict(run_id=r.id,experiment_contract_id=getattr(r,'cid',None),config_sha256=packet.get('config_sha256'),
            evaluator_sha256=packet.get('evaluator_sha256'),problem_sha256=digest(packet['problem']) if 'problem' in packet else None,
            registry_sha256=digest(packet['registry']) if 'registry' in packet else None,
            objective_order=packet.get('registry',{}).get('objective_order'),tolerance=tol,checkpoints_sha256=digest(r.packet(include_rows=False,compact_checkpoints=False)['checkpoints'])))
        ids={x['id'] for x in r.rows if audits[x['id']]['hard_pass'] and feasible_fg(x,tol)}
        invalid=sum(not finite_fg(x) for x in r.rows)
        eligibility.append(dict(run_id=r.id,total=len(r.rows),accepted=len(ids),invalid_values=invalid,
            constraint_rejected=len(r.rows)-len(ids)-invalid))
        valid.append(ids)
        fronts.append([np.asarray([r.rows[i]['F'] for i in c['archive_ids'] if i in ids],float) for c in r.checkpoints])
    all_f=np.asarray([r.rows[i]['F'] for r,ids in zip(records,valid) for i in sorted(ids)],float)
    if not len(all_f):return dict(status='EMPTY',reason='품질 비교에 사용할 유효한 제약 통과 평가가 없습니다. 제외 사유를 확인하세요.',sources=SOURCES,eligibility=eligibility)
    if any(not r.checkpoints for r in records):return dict(status='INCOMPLETE_CHECKPOINTS',reason='평가행은 있지만 세대별 저장 기록이 없어 탐색 진전 비교를 계산하지 않았습니다.',sources=SOURCES,eligibility=eligibility)
    low=all_f.min(axis=0);high=all_f.max(axis=0);active=np.flatnonzero(high>low);constant=np.flatnonzero(high==low)
    if not len(active):return dict(status='CONSTANT',reason='유효하게 관측한 모든 목적값이 같습니다. 위치 변경에 대한 목적값 변화를 확인하세요.',sources=SOURCES,eligibility=eligibility)
    scale=(high-low)[active];offset=low[active];reference_point=np.full(len(active),1.1)
    transform=lambda f:(np.asarray(f,float).reshape(-1,len(low))[:,active]-offset)/scale
    finals=[transform(fs[-1]) if fs else np.empty((0,len(active))) for fs in fronts]
    union=nondominated(np.concatenate(finals));hv=HV(ref_point=reference_point)
    reference_hv=float(hv(union)) if len(union) else 0
    traces=[]
    for r,fs in zip(records,fronts):
        trace=[]
        for c,f in zip(r.checkpoints,fs):
            z=transform(f);value=float(hv(z)) if len(z) else 0
            trace.append(dict(generation=c['generation'],nfe=c['nfe'],hv=value,
                reference_percent=100*value/reference_hv if reference_hv else None,
                igd_plus=float(IGDPlus(union)(z)) if len(z) and len(union) else None,
                archive_count=len(f)))
        final=trace[-1] if trace else None
        tail=next((t for t in trace if t['nfe']>=.8*final['nfe']),final) if final else None
        traces.append(dict(run_id=r.id,trace=trace,final=final,tail_start=tail,
            last_fifth_gain_pp=final['reference_percent']-tail['reference_percent'] if final and final['reference_percent'] is not None else None,
            raw_sha256=sha(r.folder/'raw.json')))
    attainment=[sum(bool(len(f) and np.any(np.all(f<=point+1e-12,axis=1))) for f in finals) for point in union]
    normalization=dict(version='POOLED_RANGE_MINIMIZED_V1',kind='FROZEN_POOLED_FEASIBLE_OBSERVED_RANGE',offset=offset.tolist(),scale=scale.tolist(),active_indices=active.tolist(),constant_indices=constant.tolist(),reference_point=reference_point.tolist())
    reference=dict(kind='EMPIRICAL_FINAL_ARCHIVE_UNION',F=union.tolist(),sha256=digest(union.tolist()),hv=reference_hv,independent=False)
    for source,trace in zip(basis_sources,traces):source['raw_sha256']=trace['raw_sha256']
    basis=freeze_basis('BUDGET_REPORT_LOCAL',sorted(basis_sources,key=lambda s:s['run_id']),reference,normalization,
        dict(order=basis_sources[0]['objective_order'],directions='RAW_F_ALREADY_MINIMIZED'),quality_definition(__file__)) if all(all(v is not None for v in s.values()) for s in basis_sources) else None
    return dict(status='OBSERVED',schema='SOLSOL_BUDGET_QUALITY_V1',definition_sha256=quality_definition(__file__),sources=SOURCES,runs=traces,
        comparison_basis=basis,normalization=normalization,reference=reference,eligibility=eligibility,
        attainment=dict(run_count=len(records),reference_point_counts=attainment),global_optimality=False)

def save_study(parent,records):
    """Validate real frozen contracts before merging observations across seeds."""
    if not records or len({r.id for r in [parent]+records})!=len(records)+1:raise ValueError('반복 비교: 서로 다른 실행을 선택하세요.')
    p=parent.packet(include_rows=False,compact_checkpoints=True)
    if parent.state!='completed':raise ValueError('반복 비교: 완료된 원본 실행이 필요합니다.')
    baseline=copy.deepcopy(p['submitted_request'])
    if not baseline or baseline.get('solver_policy')!='generic_v1':raise ValueError('반복 비교: 공통 실행 설정이 필요합니다.')
    seed0=baseline['optimizer'].pop('seed');seeds=[seed0];identities=[]
    search_files=['engine/solver.py','engine/initialization.py','engine/common_initialization.py','engine/milp_initialization.py','engine/objective_activity.py','engine/installation_domain.py','engine/archive.py','engine/hard_constraints.py']
    for r in records:
        packet=r.packet(include_rows=False,compact_checkpoints=True);actual=copy.deepcopy(packet['submitted_request'])
        if r.cid!=parent.cid or r.state!='completed' or len(r.rows)!=len(parent.rows):raise ValueError('반복 비교: 같은 모델·완료 상태·평가 횟수가 필요합니다.')
        seed=actual['optimizer'].pop('seed');seeds.append(seed)
        if actual!=baseline:raise ValueError('반복 비교: 난수 이외의 저장 조건이 다릅니다.')
        for key in ['evaluator_sha256','registry','problem']:
            if packet[key]!=p[key]:raise ValueError('반복 비교: 저장된 평가기 또는 문제 계약이 다릅니다: '+key)
        if packet['compilation']['installation_domain']!=p['compilation']['installation_domain']:raise ValueError('반복 비교: 설치 허용 조건이 다릅니다.')
        for name in search_files:
            if any(not isinstance(v,str) or re.fullmatch('[0-9a-f]{64}',v) is None for v in (packet['source_hashes'].get(name),p['source_hashes'].get(name))):raise ValueError('반복 비교: 탐색 구현의 필수 해시가 없습니다: '+name)
            if packet['source_hashes'].get(name)!=p['source_hashes'].get(name):raise ValueError('반복 비교: 탐색 구현이 다릅니다: '+name)
        identities.append(dict(run_id=r.id,seed=seed,evaluator_sha256=packet['evaluator_sha256'],problem_sha256=digest(packet['problem']),registry_sha256=digest(packet['registry']),config_sha256=packet['config_sha256']))
    if len(set(seeds))!=len(seeds):raise ValueError('반복 비교: 중복 seed는 독립 반복으로 합산하지 않습니다.')
    report=calculate([parent]+records)
    if report['status']!='OBSERVED':raise ValueError('반복 비교: 변화가 있는 제약 통과 목적값이 필요합니다.')
    research=p['config'].get('_research') or p['problem'].get('research_configuration',{})
    metrics=[m for m in research.get('metadata',{}).get('metrics',[]) if m['id'] in baseline['objective_ids']]
    report['performance']=performance_summary([parent]+records,metrics)
    study=dict(parent_run_id=parent.id,parent_raw_sha256=sha(parent.folder/'raw.json'),seeds=seeds[1:],independent_repeat_count=len(records),original_included=True,identities=identities,report=report,policy='Identical saved request except unique seed; frozen evaluator, registry, problem, installation domain, search implementation and completed NFE checked. Pooled empirical reference includes compared runs.')
    atomic_json(parent.folder/'quality_research.json',dict(payload=study,sha256=digest(study)))
    return study


def performance_summary(records,metrics):
    performance=[]
    for r in records:
        packet=r.packet(include_rows=False,compact_checkpoints=True);audits=reports(r);tol=packet['archive_policy']['tolerance']
        ids=[i for i in r.checkpoints[-1]['archive_ids'] if audits[i]['hard_pass'] and feasible_fg(r.rows[i],tol)]
        ms=[]
        for m in metrics:
            values=[r.rows[i].get('named_metrics',{}).get(m['id']) for i in ids]
            values=[v for v in values if isinstance(v,(int,float)) and np.isfinite(v)]
            ms.append(dict(metric=m,minimum=min(values) if values else None,maximum=max(values) if values else None))
        performance.append(dict(run_id=r.id,metrics=ms,nfe=len(r.rows),elapsed_seconds=packet['elapsed_seconds'],counters=packet.get('counters',{})))
    return performance

def overview(record):
    from .quality_judgment import final_layouts,compare_fronts,checked_local_evidence
    result=calculate([record])
    result['judgment_definition_sha256']=quality_definition(Path(__file__).with_name('quality_judgment.py'))
    result['final_layouts']=final_layouts(record)
    result['checked_jobs']=checked_local_evidence(record)
    path=record.folder/'quality_research.json'
    if path.exists():
        wrapper=json.loads(path.read_text(encoding='utf-8'));study=wrapper['payload']
        if wrapper['sha256']!=digest(study) or study['parent_raw_sha256']!=sha(record.folder/'raw.json') or study['parent_run_id']!=record.id:
            raise ValueError('QUALITY_RESEARCH_BINDING')
        cache_key=digest(dict(study=wrapper['sha256'],definition=quality_definition(__file__),judgment=result['judgment_definition_sha256']))
        cached=getattr(record,'_quality_repeat_cache',None)
        cache_hit=cached is not None and cached['key']==cache_key
        # Check every referenced raw artifact before presenting repeatability evidence.
        repeat_fronts=[];repeat_records=[]
        for item in study['report']['runs']:
            raw=record.folder.parent/item['run_id']/'raw.json'
            if not raw.is_file() or sha(raw)!=item['raw_sha256']:raise ValueError('QUALITY_RESEARCH_SOURCE_CHANGED')
            if item['run_id']!=record.id and not cache_hit:
                from .runtime import StoredSession
                from .store import decode_saved_json
                child=StoredSession(decode_saved_json(raw.read_bytes()),raw.parent)
                repeat_records.append(child)
                repeat_fronts.append(dict(run_id=child.id,layouts=final_layouts(child)))
        if cache_hit:
            result.update(copy.deepcopy(cached['value']))
            return result
        if study['report'].get('definition_sha256')!=quality_definition(__file__):
            # Recalculate derived numbers from verified raw records, never overwrite the old study.
            study=copy.deepcopy(study)
            previous_definition=study['report'].get('definition_sha256')
            packet=record.packet(include_rows=False,compact_checkpoints=True)
            research=packet['config'].get('_research') or packet['problem'].get('research_configuration',{})
            metrics=[m for m in research.get('metadata',{}).get('metrics',[]) if m['id'] in (packet.get('submitted_request') or {}).get('objective_ids',[])]
            study['report']=calculate([record]+repeat_records)
            study['report']['performance']=performance_summary([record]+repeat_records,metrics)
            study['recalculated_from_saved_raw']=True;study['previous_definition_sha256']=previous_definition
        result['repeat_study']=study
        result['joint_evidence']=compare_fronts(final_layouts(record),repeat_fronts,record.packet(include_rows=False,compact_checkpoints=True)['archive_policy']['tolerance'])
        record._quality_repeat_cache=dict(key=cache_key,value=copy.deepcopy({k:result[k] for k in ('repeat_study','joint_evidence')}))
    return result
