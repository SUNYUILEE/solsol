"""Common, bounded posthoc checks of frozen calculator runs."""
import copy,itertools,json,threading,time,uuid
from types import SimpleNamespace
from pathlib import Path
import numpy as np
from .store import digest,sha,atomic_json,record_derivation
from .results import _compiled,quality_summary
from .quality_values import quality_definition

VERSION='SOLSOL_COMMON_QUALITY_V1'
DEFINITION_SHA256=quality_definition(__file__)
def binding(record):
    p=record.packet(include_rows=False,compact_checkpoints=True)
    return dict(run_id=record.id,experiment_contract_id=record.cid,config_sha256=p['config_sha256'],evaluator_sha256=p['evaluator_sha256'],raw_sha256=sha(record.folder/'raw.json'),installation_domain=p['compilation'].get('installation_domain'))
def read(record,key):
    if str(uuid.UUID(key))!=key:raise ValueError('QUALITY_CHECK_ID')
    saved=json.loads((record.folder/'quality_checks'/(key+'.json')).read_text(encoding='utf-8'))
    if saved['sha256']!=digest(saved['payload']) or saved['payload']['parent']!=binding(record):raise ValueError('QUALITY_CHECK_INTEGRITY')
    return saved['payload']
def overview(record,summary=False):
    from .quality_assessment import assess
    from .quality_research import overview as budget_quality
    p=record.packet(include_rows=False,compact_checkpoints=True);history=[]
    for path in sorted((record.folder/'quality_checks').glob('*.json'),reverse=True):
        result=read(record,path.stem);history.append({k:result.get(k) for k in ('check_id','status','scope','method','tested','total','next_offset','improvement_count','source_count')})
    if summary:
        from .quality_judgment import final_layouts,checked_local_evidence
        budget=dict(status='DEFERRED',reason='세대별 HV·IGD+는 별도로 조회합니다. 저장 배치와 검산 결과를 먼저 확인할 수 있습니다.',final_layouts=final_layouts(record),checked_jobs=checked_local_evidence(record))
        budget['judgment_definition_sha256']=quality_definition(Path(__file__).with_name('quality_judgment.py'))
    else:budget=budget_quality(record)
    return dict(parent=binding(record),definition_sha256=DEFINITION_SHA256,assessment=assess(record),budget_quality=budget,search=quality_summary(record),initialization=p.get('initialization'),initialization_trace=p.get('solver',{}).get('initializer_trace',[]),replay=p.get('audit'),history=history,
        methods=dict(local='단일 센서 삭제·동일 종류 위치 이동 및 원시 재평가',milp='공통 국소 선형 MILP 후보를 원래 F/G로 재평가; 원문제 최적성 증명 아님',exact='허용 설치 비트 9개 이하의 전체 조합 검산; 큰 문제는 미지원'),
        preservation='원시 optimizer 해집합과 검산 개선 후보를 별도 보존합니다.')
def targets(record,options):
    generation=options.get('generation',len(record.checkpoints)-1)
    if type(generation) is not int or not 0<=generation<len(record.checkpoints):raise ValueError('QUALITY_GENERATION')
    checkpoint=record.checkpoints[generation];scope=options.get('scope','selected')
    if scope=='selected':
        rid=options.get('raw_id')
        if type(rid) is not int or not 0<=rid<checkpoint['nfe']:raise ValueError('QUALITY_RAW_ID')
        ids=[rid]
    elif scope in ('archive','qualified'):
        ids=checkpoint['archive_ids']
        if scope=='qualified':
            p=record.packet(include_rows=False);goals=p['config'].get('_research',{}).get('goals',p['config'].get('goals'))
            if goals is None:raise ValueError('QUALITY_GOALS_UNSET: 저장 실행에 정량 목표가 없습니다')
            ids=[i for i in ids if record.rows[i].get('qualified') is True]
    else:raise ValueError('QUALITY_SCOPE')
    return generation,scope,[record.rows[i] for i in ids]
def neighbors(cp,sources):
    for source in sources:
        x=np.asarray(source['X'],dtype=np.uint8)
        yield source,'replay',x
        for a,t in np.argwhere(x):
            y=x.copy();y[a,t]=0;yield source,'one_delete',y
            for b in np.flatnonzero(cp.space.allowed[:,t] & (x[:,t]==0)):
                z=y.copy();z[b,t]=1
                if cp.space.co_location or np.all(z.sum(1)<=1):yield source,'one_swap',z
def analyze(record,options):
    if not isinstance(options,dict) or set(options)-{'generation','scope','raw_id','method','budget','offset','previous_check_id'}:raise ValueError('QUALITY_OPTIONS')
    if record.state not in ('completed','cancelled','time_limit'):raise ValueError('QUALITY_SAVED_RESULT_REQUIRED')
    budget=options.get('budget',128);offset=options.get('offset',0);method=options.get('method','local')
    if type(budget) is not int or not 1<=budget<=512 or type(offset) is not int or offset<0:raise ValueError('QUALITY_BUDGET')
    if method not in ('local','milp','exact'):raise ValueError('QUALITY_METHOD')
    generation,scope,sources=targets(record,options);cp=_compiled(record);started=time.monotonic()
    previous=None
    if offset:
        if method!='local' or not options.get('previous_check_id'):raise ValueError('QUALITY_CONTINUATION_REQUIRED')
        previous=read(record,options['previous_check_id'])
        if previous.get('definition_sha256')!=DEFINITION_SHA256:raise ValueError('QUALITY_DEFINITION_CHANGED: 검산 코드가 변경되었습니다. 새 검산으로 시작하세요')
        if previous['next_offset']!=offset or any(previous.get(k)!=v for k,v in [('generation',generation),('scope',scope),('method',method)]) or previous['options'].get('raw_id')!=options.get('raw_id'):
            raise ValueError('QUALITY_CONTINUATION_MISMATCH')
    result=dict(schema=VERSION,check_id=str(uuid.uuid4()),parent=binding(record),generation=generation,scope=scope,method=method,options=copy.deepcopy(options),source_count=len(sources),tested=0,attempted=0,total=0,next_offset=None,status='COMPLETED',rows=[],witnesses=[],improvement_count=0,provenance='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER',global_optimality=False)
    result['definition_sha256']=DEFINITION_SHA256
    tol=cp.feasibility_tolerance
    def consume(source,operation,row):
        from .quality_values import finite_fg
        if not finite_fg(row) or not finite_fg(source):raise ValueError('QUALITY_NONFINITE: 유효하지 않은 목적·제약값으로 개선을 판정할 수 없습니다')
        feasible=all(g<=tol for g in row['G']);qualified=row.get('qualified')
        source_f=np.asarray(source['F']);f=np.asarray(row['F'])
        improved=feasible and (scope!='qualified' or qualified is True) and bool(np.all(f<=source_f+tol) and np.any(f<source_f-tol))
        item=dict(raw_id=source['id'],operation=operation,feasible=feasible,qualified=qualified,cost=row['cost'],F=row['F'],G=row['G'],improved=improved)
        if operation=='replay':item['replay_match']=np.allclose(f,source_f,rtol=0,atol=tol) and np.allclose(row['G'],source['G'],rtol=0,atol=tol) and row['cost']==source['cost']
        result['rows'].append(item)
        if operation=='replay' and not item['replay_match']:raise ValueError('QUALITY_REPLAY_MISMATCH: 원시 재평가 불일치. 개선 판단을 중단했습니다')
        if improved:result['witnesses'].append(dict(item,X=row['X'],sensor_counts=row['sensor_counts'],named_metrics=row.get('named_metrics',{}),coverage_metrics=row.get('coverage_metrics',{}),provenance=result['provenance']))
    try:
        if not sources:result['status']='EMPTY'
        elif method=='local':
            # Count candidates without evaluating them; the offset is stable for this frozen input.
            result['total']=sum(1 for _ in neighbors(cp,sources))
            if offset>result['total']:raise ValueError('QUALITY_OFFSET')
            selected=itertools.islice(neighbors(cp,sources),offset,offset+budget)
            while True:
                batch=list(itertools.islice(selected,32))
                if not batch:break
                result['attempted']+=len(batch)
                evaluated=cp.evaluate_physical([x for _,_,x in batch],validate_installation=True)
                result['tested']+=len(evaluated)
                for (source,op,_),row in zip(batch,evaluated):consume(source,op,row)
            end=offset+result['tested'];result['next_offset']=end if end<result['total'] else None
            if result['next_offset'] is not None:result['status']='PARTIAL'
        elif method=='exact':
            if cp.n_var>9 or 2**cp.n_var>budget:raise ValueError('QUALITY_EXACT_LIMIT: 전체 조합이 512개 이하이고 예산 안인 축소 문제만 지원합니다')
            result['enumerated_binary_states']=2**cp.n_var;result['total']=0
            vectors=itertools.product((0,1),repeat=cp.n_var)
            while True:
                z=list(itertools.islice(vectors,32))
                if not z:break
                X=cp.codec.decode(np.asarray(z),validate_installation=False);X=[x for x in X if cp.space.co_location or np.all(x.sum(1)<=1)]
                if not X:continue
                result['total']+=len(X)
                result['attempted']+=len(X);evaluated=cp.evaluate_physical(X,validate_installation=True);result['tested']+=len(evaluated)
                for row in evaluated:
                    for source in sources:consume(source,'exact_reference',row)
            result['reference_scope']='EXHAUSTIVE_FROZEN_DISCRETE_INSTALLATION_SPACE';result['epsilon_goals']='Frozen Model G and saved quantitative goal qualification; no threshold invented'
        else:
            from .common_initialization import prepare
            session=SimpleNamespace(problem=cp,optimizer=dict(population=4,seed=record.packet(include_rows=False)['optimizer']['seed'],initializer='milp',initialization_evaluations=budget),initialization=None,solver_metadata={},counters={'preparation_evaluations':0},cancel=threading.Event())
            prepare(session,time.monotonic()+20)
            result['initialization']=session.initialization;result['milp_trace']=session.solver_metadata.get('initializer_trace',[])
            ledger=session.solver_metadata.get('auxiliary_evaluations',[]);result['tested']=len(ledger);result['attempted']=session.initialization['preparation_evaluation_attempts'];result['total']=budget
            for entry in ledger:
                for source in sources:consume(source,'milp_'+entry['purpose'],entry['row'])
            result['status']='BOUNDED';result['reference_scope']='LOCAL_LINEAR_PROPOSAL_NOT_EXACT_MODEL'
        if previous:result['witnesses']=previous['witnesses']+result['witnesses']
        result['improvement_count']=len(result['witnesses'])
    except Exception as exc:
        result['status']='ERROR';result['error']=str(exc);result['quarantined_witnesses']=len(result['witnesses']);result['witnesses']=[];result['improvement_count']=0
    result['elapsed_seconds']=time.monotonic()-started
    result['cumulative_tested']=(previous.get('cumulative_tested',previous['tested']) if previous else 0)+result['tested']
    result['untested']=max(0,result['total']-offset-result['tested'])
    result['claim']='검사한 이웃/후보의 결과입니다. 미발견은 전역 최적성 증명이 아닙니다. 삭제로 전량 조건을 위반한 해는 개선해에서 제외합니다.'
    atomic_json(record.folder/'quality_checks'/(result['check_id']+'.json'),dict(sha256=digest(result),payload=result))
    record_derivation(record,VERSION,dict(check_id=result['check_id'],scope=scope,generation=generation),result['attempted'],dict(check_id=result['check_id'],tested=result['tested']),status='ERROR' if result['status']=='ERROR' else 'COMPLETED')
    return result
