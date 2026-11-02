"""Saved-condition cost references, separate from optimizer and local diagnostics."""
import copy,json,os,subprocess,sys,threading,time,uuid
from pathlib import Path
import numpy as np
from .store import atomic_json,digest,sha
from .quality_workflow import binding
from .results import _compiled
from .hard_constraints import reports,audit_row,definition as hard_definition
from . import milp_initialization as formulation

LOCK=threading.RLock()
ACTIVE={}
TERMINAL={'COMPLETED','STOPPED','INTERRUPTED','ERROR','UNSUPPORTED','INFEASIBLE'}

def definition():
    return digest({name:sha(Path(__file__).with_name(name)) for name in
        ('cost_reference.py','cost_reference_solver.py','milp_initialization.py','hard_constraints.py','results.py')})

DEFINITION=definition()

def capability(record):
    goals=(record.config.get('_research') or {}).get('goals')
    reason=''
    if record.cid!='ABC_COVERAGE_RESOURCE_V1':reason='이 모델에는 저장 조건과 결속된 공개 비용 하한 정식화가 연결되지 않았습니다.'
    elif not goals:reason='이 저장 실행은 영역 목표가 OFF입니다. 현재 중립 비용 reference는 저장된 영역 목표가 있는 문제에 적용됩니다.'
    elif record.config.get('targets') is not None:reason='이 과거 실행의 모델 품질 목표는 영역 목표 비용 정식화와 다릅니다.'
    return dict(supported=not reason,reason=reason,goals=goals,scope='저장 후보·설치·재고·영역 목표의 고정 이산 비용 문제. 실제 지원 여부는 공개 Model 계약을 확인합니다.')

def location(record,key):
    if str(uuid.UUID(key))!=key:raise ValueError('COST_REFERENCE_ID')
    return record.folder/'cost_references'/key

def save(record,state):
    atomic_json(location(record,state['job_id'])/'state.json',dict(payload=state,sha256=digest(state)))

def identity(record,key):return str(record.folder.resolve()),key

def read(record,key):
    with LOCK:
        wrapper=json.loads((location(record,key)/'state.json').read_text(encoding='utf-8'));state=wrapper['payload']
        if digest(state)!=wrapper['sha256'] or state['parent']!=binding(record):raise ValueError('COST_REFERENCE_BINDING_CHANGED')
        for name,h in state['artifacts'].items():
            if Path(name).name!=name or sha(location(record,key)/name)!=h:raise ValueError('COST_REFERENCE_ARTIFACT_CHANGED')
        if state['status'] not in TERMINAL and identity(record,key) not in ACTIVE:
            state.update(status='INTERRUPTED',phase='서버 종료로 중단 · 완료 단계부터 재개 가능');save(record,state)
        return state

def listing(record):
    return dict(capability=capability(record),jobs=sorted([read(record,p.parent.name) for p in (record.folder/'cost_references').glob('*/state.json')],key=lambda s:s['created_at'],reverse=True))

def export(record,key):
    state=read(record,key)
    artifacts={name:json.loads((location(record,key)/name).read_text(encoding='utf-8')) for name in state['artifacts']}
    return dict(state=state,artifacts=artifacts,sha256=digest(dict(state=state,artifacts=artifacts)))

def submit(record,options):
    if options!={}:raise ValueError('COST_REFERENCE_OPTIONS: 저장 조건 전체를 사용하며 시간·평가 cap을 받지 않습니다')
    if record.state not in ('completed','cancelled','time_limit'):raise ValueError('COST_REFERENCE_SAVED_RUN_REQUIRED')
    if definition()!=DEFINITION:raise ValueError('COST_REFERENCE_SOURCE_CHANGED')
    with LOCK:
        if any(k[0]==str(record.folder.resolve()) for k in ACTIVE):raise ValueError('COST_REFERENCE_ACTIVE')
        cap=capability(record);key=str(uuid.uuid4())
        state=dict(schema='SOLSOL_COST_REFERENCE_V1',job_id=key,parent=binding(record),definition_sha256=DEFINITION,
            status='QUEUED' if cap['supported'] else 'UNSUPPORTED',phase='공개 비용 계약 확인' if cap['supported'] else cap['reason'],
            created_at=time.time(),elapsed_seconds=0,artifacts={},result=None,evaluations=0,evaluation_attempts=0,
            evaluation_budget=None,time_budget=None,provenance='POSTHOC_COST_REFERENCE_NOT_OPTIMIZER',pareto_optimality=False,independent_oracle=False)
        save(record,state)
        if cap['supported']:launch(record,state)
        return copy.deepcopy(state)

def launch(record,state):
    event=threading.Event();ACTIVE[identity(record,state['job_id'])]=event
    threading.Thread(target=work,args=(record,copy.deepcopy(state),event),daemon=True,name='cost-reference-'+state['job_id'][:8]).start()

def cancel(record,key):
    with LOCK:
        state=read(record,key);event=ACTIVE.get(identity(record,key))
        if event:event.set()
        return dict(state,stop_requested=bool(event))

def resume(record,key):
    with LOCK:
        state=read(record,key)
        if state['status'] not in ('STOPPED','INTERRUPTED'):raise ValueError('COST_REFERENCE_NOT_RESUMABLE')
        if state['definition_sha256']!=DEFINITION or definition()!=DEFINITION:raise ValueError('COST_REFERENCE_DEFINITION_CHANGED')
        if any(k[0]==str(record.folder.resolve()) for k in ACTIVE):raise ValueError('COST_REFERENCE_ACTIVE')
        state.update(status='QUEUED',phase='저장 완료 단계 확인 · 중단 solver 단계는 다시 계산');save(record,state);launch(record,state)
        return copy.deepcopy(state)

class Stopped(Exception):pass

def work(record,state,event):
    started=time.monotonic();prior=state['elapsed_seconds'];root=location(record,state['job_id'])
    def checkpoint(phase=None):
        if phase:state['phase']=phase
        state['elapsed_seconds']=prior+time.monotonic()-started
        with LOCK:save(record,state)
    def stop():
        if event.is_set():raise Stopped()
    def artifact(name,value):
        atomic_json(root/name,dict(payload=value,sha256=digest(value)));state['artifacts'][name]=sha(root/name);checkpoint()
    def load(name):
        wrapper=json.loads((root/name).read_text(encoding='utf-8'))
        if digest(wrapper['payload'])!=wrapper['sha256']:raise ValueError('COST_REFERENCE_ARTIFACT_INTEGRITY')
        return wrapper['payload']
    try:
        state['status']='RUNNING';checkpoint('공개 Model 비용 계약 확인');stop();cp=_compiled(record)
        try:p=formulation.fetch_formulation(cp)
        except ValueError as error:
            if 'UNSUPPORTED:' not in str(error):raise
            state.update(status='UNSUPPORTED',phase='공개 Model 비용 계약 미지원: '+str(error));return
        a=formulation.arrays(cp,p)
        if 'formulation.json' in state['artifacts']:
            if load('formulation.json')!=p:raise ValueError('COST_REFERENCE_FORMULATION_CHANGED')
        else:artifact('formulation.json',p)
        for phase in ('lp','integer'):
            stop();name=phase+'.json'
            if name in state['artifacts']:continue
            checkpoint('연속 완화 하한 계산 중' if phase=='lp' else '정수 비용 배치 계산 중')
            attempt=phase+'-'+uuid.uuid4().hex
            output=root/(attempt+'.json')
            with (root/(attempt+'.log')).open('wb') as log:
                process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('cost_reference_solver.py')),str(root/'formulation.json'),str(output),phase,str(os.getpid())],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                try:
                    while process.poll() is None:
                        if event.wait(.2):process.terminate();process.wait();raise Stopped()
                        checkpoint()
                    if process.returncode:raise ValueError('COST_REFERENCE_SOLVER_FAILED: '+str(process.returncode))
                finally:
                    if process.poll() is None:process.terminate();process.wait()
            result=json.loads(output.read_text(encoding='utf-8'));artifact(name,result)
        lp,integer=load('lp.json'),load('integer.json');stop()
        if integer['status']==2:
            state.update(status='INFEASIBLE',phase='공개 고정 비용 문제에 실현가능 배치 없음');return
        if lp['status']!=0 or integer['status']!=0:raise ValueError('COST_REFERENCE_SOLVER_NOT_OPTIMAL')
        x,cost=formulation.checked_incumbent(cp,p,a,integer['x']);checkpoint('같은 Model로 설치·목표·F/G·비용 재평가')
        if 'replay.json' not in state['artifacts']:
            state['evaluation_attempts']+=1;checkpoint()
            row=cp.evaluate_physical(x,validate_installation=True)[0];state['evaluations']+=1
            artifact('replay.json',row)
        row=load('replay.json');stop()
        snapshot,rule=hard_definition(record)
        if not audit_row(dict(row,id='reference'),snapshot,rule)['hard_pass']:raise ValueError('COST_REFERENCE_INSTALLATION_INVALID')
        if row['X']!=x.tolist() or not np.isfinite(row['F']+row['G']).all() or np.any(np.asarray(row['G'])>cp.feasibility_tolerance):raise ValueError('COST_REFERENCE_REPLAY_INVALID')
        if not all(np.isfinite(row['coverage_metrics'][t['metric_id']]) and row['coverage_metrics'][t['metric_id']]>=t['epsilon'] for t in p['targets']):raise ValueError('COST_REFERENCE_TARGET_FAILED')
        if not np.isclose(row['named_metrics']['cost'],cost,rtol=0,atol=1e-7):raise ValueError('COST_REFERENCE_COST_MISMATCH')
        bounds=[lp['fun'],integer['mip_dual_bound'],integer['fun']]
        if any(v is None or not np.isfinite(v) for v in bounds) or lp['fun']>cost+1e-7 or abs(integer['mip_dual_bound']-cost)>1e-7 or abs(integer['fun']-cost)>1e-7:raise ValueError('COST_REFERENCE_BOUND_MISMATCH')
        checkpoint('관측 배치의 설치·재고·목표 통과 비용 비교');hard=reports(record);eligible=[]
        for source in record.rows:
            stop()
            if hard[source['id']]['hard_pass'] and np.isfinite(source['F']+source['G']).all() and all(v<=cp.feasibility_tolerance for v in source['G']) and all(np.isfinite(source.get('coverage_metrics',{}).get(t['metric_id'],np.nan)) and source['coverage_metrics'][t['metric_id']]>=t['epsilon'] for t in p['targets']) and np.isfinite(source.get('named_metrics',{}).get('cost',np.nan)):eligible.append(source)
        best=min(eligible,key=lambda r:r['named_metrics']['cost']) if eligible else None
        if best is not None and best['named_metrics']['cost']<integer['mip_dual_bound']-1e-7:
            state['contradiction_raw_id']=best['id']
            raise ValueError('COST_REFERENCE_OBSERVED_BELOW_BOUND: 원시 행 '+str(best['id']))
        if binding(record)!=state['parent']:raise ValueError('COST_REFERENCE_PARENT_CHANGED')
        rid='cost-reference:'+state['job_id']
        reference=dict(row,id=rid,run_id=record.id,experiment_contract_id=record.cid,provenance=state['provenance'])
        state['result']=dict(reference_id=rid,row=reference,observed_row=best,sensor_counts=x.sum(0).astype(int).tolist(),sensor_order=list(cp.sensor_order),
            targets=p['targets'],lp_lower_bound=lp['fun'],integer_lower_bound=integer['mip_dual_bound'],feasible_upper_bound=cost,
            observed_minimum=None if best is None else best['named_metrics']['cost'],observed_qualified_count=len(eligible),
            observed_qualified_raw_ids=[v['id'] for v in eligible],
            observed_cost_difference=None if best is None else best['named_metrics']['cost']-cost,formulation_sha256=p['formulation_sha256'],bound_scope=p['bound_scope'],
            model_certificate=p.get('radar_certificate'),validate_installation=True,
            meaning='Model이 선언한 고정 이산 영역목표 비용 문제의 수치 하한·실현 상한입니다. 성능 목적 전체의 Pareto 개선이나 독립 oracle 증명이 아닙니다.')
        stop();state.update(status='COMPLETED',phase='별도 비용 reference 저장 완료')
    except Stopped:state.update(status='STOPPED',phase='사용자 중지 · 완료 단계 저장됨 · 중단 solver 단계는 재개 시 다시 계산')
    except Exception as error:state.update(status='ERROR',phase='비용 reference 실패',error=str(error),result=None)
    finally:
        with LOCK:checkpoint();ACTIVE.pop(identity(record,state['job_id']),None)
