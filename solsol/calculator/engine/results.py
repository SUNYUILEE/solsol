"""Existing UI DTOs projected from the same common run record and raw row IDs."""
import copy
import numpy as np
from .quality_values import finite_fg, feasible_fg


def _require_saved_model_identity(cp, packet):
    """Reject a different service identity before replaying modern saved runs."""
    problem = packet.get('problem') or {}
    if 'model_service' not in problem:
        return  # Legacy records need a separate historical replay policy.
    saved = problem['model_service']
    current = getattr(cp, 'service_identity', None)
    fields = ('api_version', 'problem_id', 'input_sha256',
              'source_sha256', 'service_release_sha256')
    if not isinstance(saved, dict) or not isinstance(current, dict):
        raise ValueError('SAVED_MODEL_IDENTITY_UNAVAILABLE')
    if any(not isinstance(identity.get(key), str) or not identity[key].strip()
           for identity in (saved, current) for key in fields):
        raise ValueError('SAVED_MODEL_IDENTITY_UNAVAILABLE')
    if any(saved[key] != current[key] for key in fields):
        raise ValueError('SAVED_MODEL_IDENTITY_MISMATCH')


def _compiled(session):
    from .registry import compile_problem
    from .workflow import metadata_packet
    packet=metadata_packet(session,include_solver_policy=True)
    cp=getattr(session,'problem',None)
    if cp is None:
        from contextlib import nullcontext
        from model_service_client import service_scope
        identity=(packet.get('problem') or {}).get('model_service')
        with service_scope(identity) if identity is not None else nullcontext():
            c=packet['compilation']
            if packet.get('submitted_request'):
                # Normalized Model config may reproduce F/G yet register a
                # different input/problem identity. Recreate the original
                # request on its pinned release for every installation domain.
                from .configuration import compile_request
                cp,_,_=compile_request(session.cid,copy.deepcopy(packet['submitted_request']))
            else:
                cp=compile_problem(session.cid,session.config,c['enabled_sensor_ids'],c['registry']['objective_order'],c['diagnostic_ids'])
    _require_saved_model_identity(cp, packet)
    from .installation_domain import restore_domain
    cp=restore_domain(cp,packet)
    if cp.config_hash!=packet['config_sha256'] or cp.evaluator_hash!=packet['evaluator_sha256']:raise ValueError('EVALUATOR_UNAVAILABLE')
    return cp


def quality_summary(session):
    """Read-only search diagnostics use the saved common archive membership."""
    import hashlib
    from .store import atomic_json
    p=session.packet(include_rows=False,compact_checkpoints=True);progress=[]
    from .hard_constraints import reports
    audits=reports(session);tol=p['archive_policy']['tolerance']
    valid={r['id'] for r in session.rows if audits[r['id']]['hard_pass'] and feasible_fg(r,tol)}
    unique_seen=set();cursor=0;valid_count=0;invalid_count=0
    for c in session.checkpoints:
        rows=session.rows[:c['nfe']];ids=[i for i in c['archive_ids'] if i in valid]
        for r in session.rows[cursor:c['nfe']]:
            unique_seen.add(r['placement_hash']);valid_count+=r['id'] in valid;invalid_count+=not finite_fg(r)
        cursor=c['nfe'];unique=len(unique_seen)
        research=session.config.get('_research') or p.get('problem',{}).get('research_configuration',{})
        goals=research.get('goals') if research else session.config.get('goals') if session.cid=='HMSP-EXEC-V1' else session.config.get('targets')
        progress.append(dict(generation=c['generation'],nfe=len(rows),feasible=valid_count,invalid_values=invalid_count,unique_decisions=unique,repeated_evaluations=len(rows)-unique,archive_size=len(ids),unique_objective_vectors=len({tuple(session.rows[i]['F']) for i in ids}),target_count=None if goals is None else sum(session.rows[i].get('qualified') is True for i in ids),target_unknown_count=None if goals is None else sum(not isinstance(session.rows[i].get('qualified'),bool) for i in ids)))
    ids=[i for i in session.checkpoints[-1]['archive_ids'] if i in valid] if session.checkpoints else []
    from .placement_statistics import hamming_summary
    hamming=hamming_summary([session.rows[i]['X'] for i in ids])
    result=dict(experiment_contract_id=session.cid,run_id=session.id,config_sha256=p['config_sha256'],evaluator_sha256=p['evaluator_sha256'],raw_sha256=hashlib.sha256((session.folder/'raw.json').read_bytes()).hexdigest(),provenance='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER',rows=[],search_quality=progress,hamming=hamming,claim='관측된 실행의 탐색·국소 진단입니다. 전역 최적성을 인증하지 않습니다.')
    from .store import digest
    import json
    path=session.folder/'shared_diagnostics.json'
    if path.exists():
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved['sha256']!=digest(saved['payload']) or any(saved['payload'][k]!=result[k] for k in ('run_id','config_sha256','evaluator_sha256','raw_sha256')):raise ValueError('Diagnostic identity mismatch')
        result['rows']=saved['payload']['rows']
    result['unchecked_archive_rows']=len(ids)-len(result['rows'])
    return result


def diagnostic(session,raw_id,generation=None):
    """Keep legacy module helpers on the same release as the saved problem."""
    from contextlib import nullcontext
    from model_service_client import service_scope
    if session.state not in ('completed','cancelled','time_limit'):raise ValueError('Wait for a saved run before diagnosis')
    if type(raw_id) is not int or not 0<=raw_id<len(session.rows):raise ValueError('Invalid raw row ID')
    cp=_compiled(session)
    identity=getattr(cp,'service_identity',None)
    with service_scope(identity,cp._client.endpoint) if identity is not None else nullcontext():
        return _diagnostic(session,raw_id,generation,cp)


def _diagnostic(session,raw_id,generation,cp):
    """Named legacy local policies; evaluator calls counted separately from NFE."""
    from types import SimpleNamespace
    from .store import atomic_json,digest
    if session.state not in ('completed','cancelled','time_limit'):raise ValueError('Wait for a saved run before diagnosis')
    if type(raw_id) is not int or not 0<=raw_id<len(session.rows):raise ValueError('Invalid raw row ID')
    calls=[0]
    class Model:
        def __getattr__(self,name):return getattr(cp.model,name)
        @property
        def __model_service_reference__(self):return cp.model
        def rows(self,x):
            a=np.asarray(x);a=a[None] if a.ndim==2 else a
            result=cp.evaluate_physical(a);calls[0]+=len(result)
            if any(not finite_fg(r) for r in result):raise ValueError('QUALITY_NONFINITE')
            return result
        def row(self,x):return self.rows(x)[0]
        def evaluate(self,x):
            rows=self.rows(x);values=tuple(np.asarray([r[k] for r in rows]) for k in ('F','G','counts'))
            return tuple(v[0] for v in values) if np.asarray(x).ndim==2 else values
        def metrics(self,x):
            rows=self.rows(x);values=tuple(np.asarray([r[k] for r in rows]) for k in ('performance','quality'))
            return tuple(v[0] for v in values) if np.asarray(x).ndim==2 else values
    with session.lock:
        if session.cid=='RADAR_EOIR':
            if type(generation) is not int or not 0<=generation<len(session.checkpoints):raise ValueError('Invalid diagnosis generation')
            key=('diagnosis',raw_id,generation)
            if key in session._views:return copy.deepcopy(session._views[key])
            from live_solution_quality import assess
            job=SimpleNamespace(id=session.id,config=session.config,lock=session.lock,model=Model(),X=np.asarray([r['X'] for r in session.rows],np.uint8),F=np.asarray([r['F'] for r in session.rows]),G=np.asarray([r['G'] for r in session.rows]),snapshots=session.checkpoints,point=lambda i:copy.deepcopy(session.rows[i]))
            result=assess(job,raw_id,generation)
            result.update(experiment_contract_id=session.cid,provenance='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER',diagnostic_evaluations=calls[0])
            atomic_json(session.folder/f'diagnostic-{raw_id}-{generation}.json',dict(sha256=digest(result),payload=result))
            from .store import record_derivation
            record_derivation(session,'LEGACY_LOCAL_DIAGNOSTIC',dict(raw_id=raw_id,generation=generation),calls[0],dict(source_file=f'diagnostic-{raw_id}-{generation}.json',result_sha256=digest(result)))
            session._views[key]=result
            return copy.deepcopy(result)
        result=quality_summary(session)
        if raw_id not in session.checkpoints[-1]['archive_ids']:raise ValueError('Select a current archive row')
        if any(r['raw_id']==raw_id for r in result['rows']):return result
        source=session.rows[raw_id];x=np.asarray(source['X']);f=np.asarray(source['F']);counts={'one_delete':0,'one_swap':0};witnesses=[]
        def evaluate(y,op):
            r=Model().row(y);counts[op]+=1
            if all(g<=cp.feasibility_tolerance for g in r['G']) and np.all(np.asarray(r['F'])<=f+1e-12) and np.any(np.asarray(r['F'])<f-1e-12):witnesses.append(dict(operation=op,X=r['X'],F=r['F'],G=r['G'],provenance='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER'))
        for a,t in np.argwhere(x==1):
            y=x.copy();y[a,t]=0;evaluate(y,'one_delete')
            for b in np.flatnonzero(x[:,t]==0):
                z=y.copy();z[b,t]=1;evaluate(z,'one_swap')
        result['rows'].append(dict(raw_id=raw_id,source_decision_sha256=source['decision_sha256'],one_delete_tested=counts['one_delete'],one_swap_tested=counts['one_swap'],one_delete_witness_count=sum(w['operation']=='one_delete' for w in witnesses),one_swap_witness_count=sum(w['operation']=='one_swap' for w in witnesses),witnesses=witnesses,diagnostic_evaluations=calls[0]))
        result['unchecked_archive_rows']-=1
        atomic_json(session.folder/'shared_diagnostics.json',dict(sha256=digest(result),payload=result))
        from .store import record_derivation
        record_derivation(session,'LEGACY_LOCAL_DIAGNOSTIC',dict(raw_id=raw_id),calls[0],dict(source_file='shared_diagnostics.json',result_sha256=digest(result)))
        return result

def to_view(session,generation=None,*,summary=False):
    if session.config.get('_research') or session.cid in ('HMSP-EXEC-V1','HMSP-2D-V1'):
        from .configuration_view import view
        return view(session,generation,summary=summary)
    packet=session.packet(include_rows=False,compact_checkpoints=True);checkpoints=session.checkpoints
    if generation is not None and (type(generation) is not int or not 0<=generation<len(checkpoints)):raise ValueError('Invalid generation')
    cp=checkpoints[-1] if generation is None and checkpoints else checkpoints[generation] if checkpoints else None
    ids=cp['archive_ids'] if cp else [];packet.pop('rows',None)
    # Cache per immutable checkpoint; polling the same frame does not reevaluate its map.
    def row(i):return session.spatial(session.rows[i])
    if session.cid=='RADAR_EOIR':
        return dict(packet,id=session.id,seconds=packet['elapsed_seconds'],latest_generation=len(checkpoints)-1,snapshot=copy.deepcopy(cp),points=[copy.deepcopy(session.rows[i]) for i in ids],current_population_points=[copy.deepcopy(session.rows[i]) for i in cp['population_ids']] if cp else [],representative=copy.deepcopy(session.rows[cp['representative_id']]) if cp and cp.get('representative_id') is not None else None,history=[{k:v for k,v in c.items() if k not in ('population_X','population_ids','front_ids','archive_ids')} for c in checkpoints])
    key=('hamming',cp['generation'] if cp else None)
    if key not in session._views:
        from hamming_posthoc import complete_link
        session._views[key]=[list(v) for v in complete_link(np.asarray([session.rows[i]['X'] for i in ids]),range(len(ids)),3)] if ids else []
    return dict(packet,archive=[row(i) for i in ids],initial_archive=[row(i) for i in checkpoints[0]['archive_ids']] if checkpoints else [],generation=cp['generation'] if cp else None,target_count=None if session.config.get('targets') is None else sum(bool(session.rows[i].get('qualified')) for i in ids),hamming_clusters=copy.deepcopy(session._views[key]),independent_reference_count=None,map_provenance='REPLAY_DERIVATION_FROM_EXACT_RAW_XFG')
