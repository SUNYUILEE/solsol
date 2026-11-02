"""Persistent complete-scope diagnostics. Batches/pages are not execution budgets."""
import copy,itertools,json,math,threading,time,uuid
from pathlib import Path
import numpy as np
from .store import digest,sha,record_derivation,atomic_json
from .results import _compiled
from .quality_workflow import binding,targets,neighbors
from .quality_values import finite_fg

VERSION='SOLSOL_COMPLETE_QUALITY_V2'
def current_definition():return digest({p.name:sha(p) for p in (Path(__file__),Path(__file__).with_name('quality_workflow.py'),Path(__file__).with_name('initialization.py'),Path(__file__).with_name('quality_values.py'),Path(__file__).with_name('results.py'),Path(__file__).with_name('hard_constraints.py'),Path(__file__).with_name('frozen_refinement.py'))})
DEFINITION_SHA256=current_definition()
def require_current():
    if current_definition()!=DEFINITION_SHA256:raise ValueError('QUALITY_SOURCE_CHANGED: 서버를 다시 시작하세요')
METHODS={
 'refine':dict(label='고정 문제 · 전체 배치 반복 개선',scope='ITERATED_PARETO_DELETE_ADD_RELOCATE'),
 'local':dict(label='전체 삭제·추가·위치 이동 검산',scope='ALL_ONE_CHANGE_NEIGHBORS'),
 'milp':dict(label='전체 이웃 MILP·ε-constraint 검산',scope='COMPLETE_NEIGHBORHOOD_SELECTION_MILP'),
 'exact':dict(label='전체 설치 조합·ε-constraint 검산',scope='EXHAUSTIVE_FROZEN_RESOURCE_FEASIBLE_SPACE'),
}
ACTIVE={};GUARD=threading.RLock()
TERMINAL={'COMPLETED','EMPTY','STOPPED','INTERRUPTED','ERROR'}

def location(record,key):
    if str(uuid.UUID(key))!=key:raise ValueError('QUALITY_JOB_ID')
    return record.folder/'quality_jobs'/key/'state.json'

def packed(value):return json.dumps(dict(payload=value,sha256=digest(value)),ensure_ascii=False,separators=(',',':'))

def unpacked(value):
    p=json.loads(value)
    if p['sha256']!=digest(p['payload']):raise ValueError('QUALITY_JOB_INTEGRITY')
    return p['payload']

def save(record,state,entries=()):
    with GUARD:_save(record,state,entries)

def _save(record,state,entries=()):
    path=location(record,state['job_id']);state.setdefault('chunks',[])
    if entries:
        rows=[dict(item,sequence=index) for index,item in entries];name='batch-'+str(rows[0]['sequence'])+'.json'
        atomic_json(path.parent/name,dict(payload=rows,sha256=digest(rows)))
        state['chunks'].append(dict(name=name,sha256=sha(path.parent/name),first=rows[0]['sequence'],count=len(rows),witness_count=sum(bool(r['improved_for']) for r in rows)))
    atomic_json(path,dict(payload=state,sha256=digest(state)))

def identity(record,key):return (str(record.folder.resolve()),key)

def get(record,key):
    with GUARD:
        state=unpacked(location(record,key).read_text(encoding='utf-8'))
        if state['parent']!=binding(record):raise ValueError('QUALITY_JOB_PARENT_CHANGED')
        if state['status'] not in TERMINAL and identity(record,key) not in ACTIVE:
            state.update(status='INTERRUPTED',phase='서버 종료로 중단됨 · 이어서 검사 가능');save(record,state)
    return state

def stored_entries(record,state):
    expected=0;root=location(record,state['job_id']).parent
    for chunk in state['chunks']:
        if chunk['name']!='batch-'+str(expected)+'.json' or chunk['first']!=expected:raise ValueError('QUALITY_CHUNK_SEQUENCE_INTEGRITY')
        path=root/chunk['name']
        if sha(path)!=chunk['sha256']:raise ValueError('QUALITY_CHUNK_INTEGRITY')
        rows=unpacked(path.read_text(encoding='utf-8'))
        if len(rows)!=chunk['count'] or sum(bool(r['improved_for']) for r in rows)!=chunk['witness_count']:raise ValueError('QUALITY_CHUNK_COUNT_INTEGRITY')
        for row in rows:
            if row['sequence']!=expected:raise ValueError('QUALITY_ENTRY_SEQUENCE_INTEGRITY')
            expected+=1;yield row
    if expected!=state['next_eval']:raise ValueError('QUALITY_JOB_CURSOR_INTEGRITY')

def listing(record):
    jobs=[get(record,p.parent.name) for p in (record.folder/'quality_jobs').glob('*/state.json')]
    return dict(methods=METHODS,definition_sha256=DEFINITION_SHA256,jobs=sorted(jobs,key=lambda p:p['created_at'],reverse=True),evaluation_budget=None,time_budget=None)

def page(record,key,offset=0,limit=100,witnesses=False):
    state=get(record,key)
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise ValueError('QUALITY_PAGE')
    if witnesses and state['status']=='ERROR':return dict(job=state,rows=[],total=0,offset=offset)
    total=sum(c['witness_count'] if witnesses else c['count'] for c in state['chunks']);rows=[];seen=0
    for item in stored_entries(record,state):
        if witnesses and not item['improved_for']:continue
        if offset<=seen<offset+limit:rows.append(item)
        seen+=1
        if seen>=offset+limit:break
    return dict(job=state,rows=rows,total=total,offset=offset)

def submit(record,options):
    require_current()
    if not isinstance(options,dict) or set(options)-{'scope','raw_id','generation','method'}:raise ValueError('QUALITY_JOB_OPTIONS: 평가 예산은 사용하지 않습니다')
    if record.state not in ('completed','cancelled','time_limit'):raise ValueError('QUALITY_SAVED_RESULT_REQUIRED')
    if options.get('method','local') not in METHODS:raise ValueError('QUALITY_METHOD')
    generation,scope,sources=targets(record,options)
    with GUARD:
        for (folder,key),_ in ACTIVE.items():
            if folder==str(record.folder.resolve()):raise ValueError('QUALITY_JOB_ACTIVE: 현재 검산을 먼저 중지하거나 완료하세요')
        key=str(uuid.uuid4());path=location(record,key);path.parent.mkdir(parents=True)
        state=dict(schema=VERSION,job_id=key,parent=binding(record),definition_sha256=DEFINITION_SHA256,options=copy.deepcopy(options),generation=generation,scope=scope,method=options.get('method','local'),source_ids=[s['id'] for s in sources],source_count=len(sources),status='QUEUED',phase='검산 준비',created_at=time.time(),elapsed_seconds=0,evaluated=0,attempted=0,total=None,total_upper_bound=None,witness_count=0,next_eval=0,certificates=[],evaluation_budget=None,time_budget=None,provenance='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER',global_optimality=False)
        save(record,state);launch(record,state)
    return state

def launch(record,state):
    event=threading.Event();key=identity(record,state['job_id']);ACTIVE[key]=event
    threading.Thread(target=work,args=(record,copy.deepcopy(state),event),daemon=True,name='quality-'+state['job_id'][:8]).start()

def cancel(record,key):
    with GUARD:
        state=get(record,key);event=ACTIVE.get(identity(record,key))
        if event:event.set()
    # Worker owns persisted progress. Do not overwrite a freshly completed batch.
    return dict(state,stop_requested=bool(event))

def resume(record,key):
    with GUARD:
        require_current()
        state=get(record,key)
        if state['status'] not in ('STOPPED','INTERRUPTED'):raise ValueError('QUALITY_JOB_NOT_RESUMABLE')
        if state['definition_sha256']!=DEFINITION_SHA256:raise ValueError('QUALITY_DEFINITION_CHANGED')
        if any(folder==str(record.folder.resolve()) for folder,_ in ACTIVE):raise ValueError('QUALITY_JOB_ACTIVE')
        state.update(status='QUEUED',phase='저장 근거 검증 준비',scope_complete=False);save(record,state);launch(record,state)
    return state

def resource_feasible(cp,x):
    from .initialization import resource_bounds
    lower,limits=resource_bounds(cp.space,getattr(cp.bundle,'inventory_rule',None));counts=np.asarray(x).sum(0)
    return bool(np.all((counts>=lower)&(counts<=limits)))

def local_vectors(cp,source):
    # Original replay is a separate mandatory prefix, once for every source.
    for _,operation,x in itertools.islice(neighbors(cp,[source]),1,None):yield source,operation,x
    x=np.asarray(source['X'],np.uint8)
    for a,t in np.argwhere(cp.space.allowed & (x==0)):
        y=x.copy();y[a,t]=1
        if cp.space.co_location or np.all(y.sum(1)<=1):yield source,'one_add',y

def full_vectors(cp):
    from .initialization import resource_bounds
    lower,limits=resource_bounds(cp.space,getattr(cp.bundle,'inventory_rule',None))
    x=np.zeros(cp.space.shape,np.uint8)
    def choose(t):
        if t==cp.space.shape[1]:yield x.copy();return
        sites=np.flatnonzero(cp.space.allowed[:,t] & (True if cp.space.co_location else x.sum(1)==0))
        counts=range(int(lower[t]),min(int(limits[t]),len(sites))+1)
        for n in counts:
            for selection in itertools.combinations(sites,n):
                index=list(selection);x[index,t]=1
                yield from choose(t+1)
                x[index,t]=0
    yield from choose(0)

def upper_count(cp):
    from .initialization import resource_bounds
    lower,limits=resource_bounds(cp.space,getattr(cp.bundle,'inventory_rule',None));answer=1
    for capacity,lo,k in zip(cp.space.allowed.sum(0),lower,limits):
        answer*=sum(math.comb(int(capacity),j) for j in range(int(lo),int(k)+1))
    return answer

def stream(cp,sources,method):
    for source in sources:yield source,'replay',np.asarray(source['X'],np.uint8)
    if method=='exact':
        for x in full_vectors(cp):yield None,'exact_reference',x
    else:
        for source in sources:yield from local_vectors(cp,source)

def certify(record,state,sources,event):
    """Epsilon bounds are source F, not invented physical quality goals."""
    from scipy.optimize import Bounds,LinearConstraint,milp
    tol=state['tolerance'];is_milp=state['method']=='milp';state['certificates']=[]
    for source in sources:
        for objective in range(len(source['F'])):
            if event.is_set():return False
            candidates=[];best=None;eligible=0
            for row in stored_entries(record,state):
                    if event.is_set():return False
                    seq=row['sequence']
                    if is_milp and row['source_id']!=source['id']:continue
                    if not row['feasible'] or (state['scope']=='qualified' and row['qualified'] is not True):continue
                    if any(v>source['F'][j]+tol for j,v in enumerate(row['F']) if j!=objective):continue
                    eligible+=1
                    if is_milp:candidates.append((seq,row['F'][objective]))
                    if best is None or row['F'][objective]<best[1]:best=(seq,row['F'][objective])
            proof=dict(raw_id=source['id'],objective=objective,epsilon_other_F=source['F'],eligible=eligible,selected_seq=None,best_F=None,scope=METHODS[state['method']]['scope'])
            if is_milp and candidates:
                # One-hot MILP over all evaluated eligible alternatives; no time/node/gap budget.
                costs=np.asarray([v for _,v in candidates]);n=len(costs)
                result=milp(costs,integrality=np.ones(n),bounds=Bounds(np.zeros(n),np.ones(n)),constraints=LinearConstraint(np.ones((1,n)),1,1),options={'mip_rel_gap':0.})
                if result.status!=0 or result.x is None:raise ValueError('QUALITY_MILP_NOT_OPTIMAL:'+str(result.message))
                z=np.rint(result.x)
                if not np.isfinite(result.x).all() or np.max(np.abs(result.x-z))>1e-6 or z.sum()!=1 or np.any((z<0)|(z>1)):raise ValueError('QUALITY_MILP_INVALID_SOLUTION')
                picked=candidates[int(np.argmax(z))]
                if abs(picked[1]-best[1])>tol:raise ValueError('QUALITY_MILP_ENUMERATION_DISAGREEMENT')
                proof.update(selected_seq=picked[0],best_F=picked[1],solver_status=int(result.status),solver_message=str(result.message),certificate='OPTIMAL_OVER_COMPLETE_EVALUATED_NEIGHBORHOOD')
            elif best:proof.update(selected_seq=best[0],best_F=best[1],certificate='MINIMUM_OVER_EXHAUSTIVE_FROZEN_SPACE')
            else:proof.update(certificate='NO_ELIGIBLE_CANDIDATE')
            state['certificates'].append(proof);save(record,state)
    return True

def work(record,state,event):
    started=time.monotonic();prior_elapsed=state['elapsed_seconds'];key=state['job_id']
    def checkpoint():
        state['elapsed_seconds']=prior_elapsed+time.monotonic()-started;save(record,state)
    try:
        if state['next_eval']:
            state.update(status='RUNNING',phase='저장 근거 무결성 검증');checkpoint()
            for _ in stored_entries(record,state):
                if event.is_set():state.update(status='STOPPED',phase='근거 검증 중 사용자 중지');return
        cp=_compiled(record);tol=cp.feasibility_tolerance;state['tolerance']=tol
        generation,scope,sources=targets(record,state['options'])
        if any(not finite_fg(s) for s in sources):raise ValueError('QUALITY_NONFINITE_SOURCE')
        if [s['id'] for s in sources]!=state['source_ids'] or generation!=state['generation']:raise ValueError('QUALITY_SOURCE_CHANGED')
        state.update(status='RUNNING',phase='전체 검사 범위 준비');checkpoint()
        if not sources:state.update(status='EMPTY',total=0);return
        if state['method']=='refine':
            from .frozen_refinement import run
            run(record,state,event,cp,sources,checkpoint)
            if state['parent']!=binding(record):raise ValueError('QUALITY_PARENT_CHANGED')
            return
        if state['method']=='exact':state['total_upper_bound']=str(len(sources)+upper_count(cp))
        else:
            total=len(sources)
            for s in sources:
                for _ in local_vectors(cp,s):
                    if event.is_set():state['status']='STOPPED';return
                    total+=1
            state['total']=total
        state['phase']='원시 재평가·전체 배치 검산';checkpoint()
        vectors=stream(cp,sources,state['method'])
        if state['next_eval']:
            state['phase']='저장된 열거 지점 복원';checkpoint()
            for _ in range(state['next_eval']):
                if event.is_set():state['status']='STOPPED';return
                next(vectors)
            state['phase']='남은 범위 검산';checkpoint()
        while not event.is_set():
            batch=list(itertools.islice(vectors,32))
            if not batch:break
            state['attempted']+=len(batch);checkpoint()
            evaluated=cp.evaluate_physical([x for _,_,x in batch],validate_installation=True)
            if len(evaluated)!=len(batch):raise ValueError('QUALITY_BATCH_LENGTH')
            entries=[]
            for (source,op,x),row in zip(batch,evaluated):
                if not np.array_equal(np.asarray(row['X']),x):raise ValueError('QUALITY_X_BINDING')
                if not finite_fg(row):raise ValueError('QUALITY_NONFINITE')
                if op=='replay' and not (np.allclose(row['F'],source['F'],rtol=0,atol=tol) and np.allclose(row['G'],source['G'],rtol=0,atol=tol) and row['cost']==source['cost']):raise ValueError('QUALITY_REPLAY_MISMATCH')
                feasible=bool(all(g<=tol for g in row['G']) and resource_feasible(cp,x));improved=[]
                for base in ([source] if source is not None else sources):
                    if feasible and (scope!='qualified' or row.get('qualified') is True) and np.all(np.asarray(row['F'])<=np.asarray(base['F'])+tol) and np.any(np.asarray(row['F'])<np.asarray(base['F'])-tol):improved.append(base['id'])
                item=dict(row,source_id=source['id'] if source else None,operation=op,feasible=feasible,qualified=row.get('qualified'),improved_for=improved,provenance=state['provenance'])
                entries.append((state['next_eval']+len(entries),item))
            state['next_eval']+=len(entries);state['evaluated']+=len(entries);state['witness_count']+=sum(bool(v['improved_for']) for _,v in entries)
            state['elapsed_seconds']=prior_elapsed+time.monotonic()-started;save(record,state,entries)
        if event.is_set():state.update(status='STOPPED',phase='사용자 요청으로 중지됨');return
        state['total']=state['evaluated'];state['phase']='ε 제약별 최선 후보 대조';checkpoint()
        if state['method'] in ('milp','exact') and not certify(record,state,sources,event):state['status']='STOPPED';return
        if state['parent']!=binding(record):raise ValueError('QUALITY_PARENT_CHANGED')
        state.update(status='COMPLETED',phase='선택 범위 전체 검사 완료',scope_complete=True)
        state['global_optimality']=False # No universal physical/global Model claim.
    except Exception as exc:
        state.update(status='ERROR',phase='검산 실패 · 개선 증거 사용 금지',error=str(exc),scope_complete=False,quarantined_witnesses=state['witness_count'],witness_count=0,certificates=[])
    finally:
        try:
            checkpoint()
            record_derivation(record,VERSION,dict(job_id=key,scope=state['scope']),state['attempted'],dict(job_id=key,evaluated=state['evaluated'],status=state['status']),status='ERROR' if state['status']=='ERROR' else 'COMPLETED')
        finally:
            with GUARD:ACTIVE.pop(identity(record,key),None)
