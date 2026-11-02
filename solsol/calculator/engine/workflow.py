"""Frozen execution and read-only result use, on the existing run/store contract."""
import copy,json
from dataclasses import asdict
from .store import digest,sha
from .runtime import optimizer_config,LOADED_SOURCE_HASHES,ENVIRONMENT,TERMINAL

REQUEST_SCHEMA='SOLSOL_CONFIGURATION_REQUEST_V1'

def metadata_packet(record, *, include_solver_policy=False):
    """Copy configuration/provenance without walking the population history.

    Stored records have already passed RunStore.read. This is not a new or
    weaker restore path: exclude unused large fields before defensive copying.
    """
    from .runtime import RunSession,StoredSession
    if isinstance(record,(RunSession,StoredSession)):
        with record.lock:
            source=record.data if isinstance(record,StoredSession) else record.packet(include_rows=False,compact_checkpoints=True,copy_values=False)
            metadata={k:v for k,v in source.items() if k not in ('rows','events','checkpoints','solver')}
            if include_solver_policy:metadata['solver']={'policy':source['solver']['policy']}
            return copy.deepcopy(metadata)
    return record.packet(include_rows=False)

def restore_copy_numbers(record, request):
    """Preserve unchanged saved JSON number spelling across a browser roundtrip.

    Changed values remain new inputs. This does not relax Model hash equality.
    """
    from .configuration import same_json_numbers
    def merge(value, original):
        if type(value) in (int,float) and type(original) in (int,float) and same_json_numbers(value,original):return original
        if isinstance(value,dict) and isinstance(original,dict):return {k:merge(v,original[k]) if k in original else v for k,v in value.items()}
        if isinstance(value,list) and isinstance(original,list) and len(value)==len(original):return [merge(v,o) for v,o in zip(value,original)]
        return value
    p=metadata_packet(record);result=copy.deepcopy(request)
    original=(p.get('submitted_request') or {}).get('model_config',{})
    result['model_config']=merge(merge(result.get('model_config',{}),original),p['config'])
    if 'resource_contract' in result:result['resource_contract']=merge(result['resource_contract'],p['config'].get('_resource_contract'))
    return result
def request_body(obj):
    if not isinstance(obj,dict):raise ValueError('INVALID_CONFIGURATION: object required')
    if obj.get('schema',REQUEST_SCHEMA)!=REQUEST_SCHEMA:raise ValueError('UNSUPPORTED_SCHEMA: configuration request')
    return {k:v for k,v in obj.items() if k!='schema'}

def execution_snapshot(cp,opt,request):
    optimizer,policy=optimizer_config(cp,opt)
    from .installation_domain import ensure_domain
    ensure_domain(cp,policy)
    registry=cp.registry_snapshot.to_dict()
    meta=cp.config.get('_research',getattr(cp,'calculator_configuration',{})).get('metadata',{})
    snapshot=dict(schema='SOLSOL_EXECUTION_SNAPSHOT_V1',experiment_contract_id=cp.cid,
        config_sha256=cp.config_hash,registry=registry,model_config=copy.deepcopy(cp.config),model_service=copy.deepcopy(cp.service_identity),
        candidates=dict(order=list(registry['candidate_order']),sites=copy.deepcopy(cp.bundle.sites),sha256=digest(dict(order=registry['candidate_order'],sites=cp.bundle.sites))),
        enabled_sensor_ids=list(cp.space.enabled_sensor_ids),diagnostic_ids=list(cp.diagnostic_order),
        objectives=[asdict(next(x for x in cp.objective_specs if x.objective_id==key)) for key in cp.objective_order],constraint_order=list(registry['constraint_order']),
        feasibility_tolerance=cp.feasibility_tolerance,cost_definition=next((m for m in meta.get('metrics',[]) if m['id']=='cost'),None),
        solver=dict(policy=policy,algorithm=optimizer['algorithm'],initialization=cp.config.get('initializer','binary_random') if policy=='legacy_eoir_v1' else 'legacy constrained sample / CountRepair' if policy in ('legacy_rf_v2','legacy_rf_v3') else optimizer.get('initializer','random'),
            operators=cp.config.get('design') if policy=='legacy_eoir_v1' else 'two_point_or_short_uniform / bitflip / registered inventory repair',
            reference_directions='legacy policy population-derived partitions' if policy!='generic_v1' else dict(method='das-dennis',partitions=optimizer.get('ref_partitions',1))),
        optimizer=optimizer,declared_nfe=optimizer['population']*optimizer['checkpoints'],
        initialization_preparation=dict(max_model_evaluations=optimizer['initialization_evaluations'],max_seconds=optimizer['initialization_seconds'],target_semantics='original Model G and optional public coverage goals; F minimization',search_nfe_excludes_preparation=True,actual_random_preparation_evaluations=0) if policy=='generic_v1' else None,
        termination=dict(generation_budget=optimizer['checkpoints']-1,wallclock_limit_seconds=optimizer['wallclock_limit_seconds'],user_cancel=True),
        evaluator_sha256=cp.evaluator_hash,optimizer_code_sha256=digest(dict(sources=LOADED_SOURCE_HASHES,environment=ENVIRONMENT)),environment=ENVIRONMENT,
        submitted_request=copy.deepcopy(request),normalization_note='정규화된 모델·정책·예산 전체가 이 snapshot에 고정됩니다. 기본값과 변환도 제출 전에 확인할 수 있습니다.')
    if policy=='generic_v1':
        from .objective_activity import projection
        snapshot['solver']['objective_projection']=projection(cp)
        from .common_initialization import VERSION, LEGACY_VERSION, VERSIONS, seed_admission
        actual_version=optimizer.get('initialization_version',LEGACY_VERSION)
        snapshot['solver']['initialization_version']=actual_version
        snapshot['initialization_capability']=dict(owner='CALCULATOR',version=actual_version,default_for_new_ui=VERSION,supported_versions=list(VERSIONS),methods=['random','greedy','milp','saved'],milp_semantics='LOCAL_LINEAR_F_G_PROPOSAL_NOT_EXACT_MODEL')
        snapshot['initialization_preparation']['seed_admission_version']=actual_version
        snapshot['initialization_preparation']['seed_admission']=seed_admission(optimizer.get('initializer','random'),actual_version)
    snapshot['installation_domain']=copy.deepcopy(getattr(cp,'installation_domain',None))
    snapshot['execution_sha256']=digest(snapshot)
    return snapshot

def diff(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        result=[]
        for k in sorted(a.keys()|b.keys()):
            p=path+'/'+k
            if k not in a:result.append(dict(path=p,before_present=False,after=copy.deepcopy(b[k])))
            elif k not in b:result.append(dict(path=p,before=copy.deepcopy(a[k]),after_present=False))
            else:result+=diff(a[k],b[k],p)
        return result
    return [] if a==b else [dict(path=path,before=copy.deepcopy(a),after=copy.deepcopy(b))]

def copy_request(record):
    p=metadata_packet(record)
    from .installation_domain import default_domain
    domain=(p.get('compilation',{}).get('installation_domain') or {}).get('mode') or default_domain(record.cid)
    if p.get('submitted_request'):
        request=copy.deepcopy(p['submitted_request'])
        request['installation_domain']=domain
        return request
    r=p['config'].get('_research')
    if not r:raise ValueError('UNSUPPORTED_COPY: historical configuration has no selected configuration snapshot; use historical UI copy and review')
    c=copy.deepcopy(p['config']);c.pop('_research',None)
    opt=copy.deepcopy(p['optimizer']);opt.pop('checkpoints',None)
    if r['solver_policy']=='legacy_eoir_v1':opt={'wallclock_limit_seconds':opt['wallclock_limit_seconds']}
    return dict(experiment_contract_id=p['experiment_contract_id'],model_config=c,
        enabled_sensor_ids=r['enabled_sensor_ids'],objective_ids=r['objective_ids'],diagnostic_ids=r['diagnostic_ids'],solver_policy=r['solver_policy'],optimizer=opt,goals=r['goals'],installation_domain=domain)

def capability(record):
    p=metadata_packet(record);shared=p.get('schema')=='SOLSOL_ENGINE_RUN_V1'
    return dict(read=True,export=p['state'] in TERMINAL,copy_configuration=bool(p.get('submitted_request') or p['config'].get('_research')),
        compare=True,solver_resume=False,solver_resume_reason='저장된 결과 복원만 지원하며 solver 상태를 이어서 계산하지 않습니다.',
        validation=dict(group_runs=bool(p['config'].get('_research')),fixed_reference_indicators=shared,substitution=shared,fixed_placement_robustness=shared,solver_resume=False,field_model_approval=False),
        diagnostics=dict(status='AVAILABLE' if shared and p['state'] in TERMINAL else 'NOT_AVAILABLE',reason='저장된 공통 실행은 기본 진단·센서 제거·고정 reference 지표·선택형 대체와 조건별 재평가를 지원합니다. IGD+는 같은 문제의 reference가 필요합니다.' if shared else '과거 실행은 공통 표본 계약이 없어 기본 진단을 지원하지 않습니다.',
            sidecar_contract='SOLSOL_DIAGNOSTIC_SIDECAR_V1' if shared else None),raw_replay_status=p.get('audit'))

class _RequestFileDigests:
    """Request-local digests, rechecked before returning; never a disk cache."""
    def __init__(self):self.values={}
    def get(self,path):
        if path not in self.values:self.values[path]=sha(path) if path.is_file() else None
        return self.values[path]
    def verify(self):
        for path,expected in self.values.items():
            actual=sha(path) if path.is_file() else None
            if actual!=expected:raise ValueError('INTEGRITY_ERROR: source changed during diagnostic lookup')


def sidecar_index(record):
    sources=_RequestFileDigests()
    entries=_sidecar_index(record,sources)
    sources.verify()
    return entries


def _sidecar_index(record,sources):
    p=metadata_packet(record);raw=record.folder/'raw.json';entries=[]
    for path in sorted((record.folder/'diagnostics').glob('*.json')):
        try:d=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):
            entries.append(dict(path=path.name,status='INTEGRITY_ERROR',reason='malformed sidecar'));continue
        if not isinstance(d,dict):
            entries.append(dict(path=path.name,status='INTEGRITY_ERROR',reason='sidecar fields'));continue
        if d.get('schema')!='SOLSOL_DIAGNOSTIC_SIDECAR_V1':
            entries.append(dict(path=path.name,status='UNSUPPORTED_SCHEMA'));continue
        if not isinstance(d.get('parent'),dict) or type(d.get('evaluations')) is not int or d.get('evaluations')<0:
            entries.append(dict(path=path.name,status='INTEGRITY_ERROR',reason='sidecar fields'));continue
        parent=d.get('parent',{})
        ok=parent.get('run_id')==record.id and parent.get('experiment_contract_id')==record.cid and parent.get('config_sha256')==p['config_sha256'] and sources.get(raw) is not None and parent.get('raw_sha256')==sources.get(raw)
        ok=ok and parent.get('evaluator_sha256')==p.get('evaluator_sha256') and d.get('sha256')==digest({k:v for k,v in d.items() if k!='sha256'})
        if 'manifest_sha256' in parent:ok=ok and sources.get(record.folder/'manifest.json') is not None and parent['manifest_sha256']==sources.get(record.folder/'manifest.json')
        entries.append(dict(path=path.name,status=d.get('status','NOT_RUN') if ok else 'INTEGRITY_ERROR',sha256=sha(path),parent=parent,target=d.get('target'),evaluations=d.get('evaluations')))
    return entries

def result_contract(record):
    p=metadata_packet(record);raw=record.folder/'raw.json';manifest=record.folder/'manifest.json'
    sources=_RequestFileDigests();diagnostics=_sidecar_index(record,sources)
    raw_hash=sources.get(raw);manifest_hash=sources.get(manifest)
    result=dict(schema='SOLSOL_RESULT_USE_V1',experiment_contract_id=record.cid,run_id=record.id,config_sha256=p['config_sha256'],
        state=p['state'],termination_reason=p.get('termination_reason'),storage_complete=p.get('storage_complete'),
        execution_snapshot=p.get('execution_snapshot'),registry=p.get('registry'),evaluator_sha256=p.get('evaluator_sha256'),
        optimizer_code_sha256=p.get('optimizer_code_sha256'),environment=p.get('environment'),nfe=p.get('nfe'),counters=p.get('counters'),
        raw_source=dict(path=raw.name,sha256=raw_hash) if raw_hash is not None else dict(status='LEGACY_ORIGINAL_FORMAT'),
        manifest_source=dict(path=manifest.name,sha256=manifest_hash) if manifest_hash is not None else None,
        map_provenance=dict(source='frozen problem geometry and raw X',evaluations=0,meaning='placement overlay; scientific map replay, when requested, is separate'),
        capabilities=capability(record),diagnostics=diagnostics,derived_evaluations=sum(d.get('evaluations',0) for d in diagnostics if d['status'] in ('COMPLETED','ERROR') and type(d.get('evaluations')) is int),restore_semantics='STORED_RESULT_ONLY_NOT_SOLVER_RESUME')
    sources.verify()
    return result

def compare(left,right):
    a=left.packet(include_rows=False);b=right.packet(include_rows=False)
    def semantics(p):
        r=p.get('registry',{});research=p['config'].get('_research') or p['problem'].get('research_configuration',{});meta=research.get('metadata',{})
        return dict(cid=p['experiment_contract_id'],model=r.get('model_version',p['config'].get('objective_contract',p['config'].get('evaluator_version'))),
            installation_domain=(p.get('compilation',{}).get('installation_domain') or {}).get('sha256','historical_model_space'),
            evaluator=p.get('evaluator_sha256'),metrics=meta.get('metrics'),order=r.get('objective_order'),goal_definition=research.get('goal_definition'),
            metric_context={k:p['config'].get(k) for k in ('normalization_m','horizon_years','common','objective_contract','geometry_contract','area_factor','identification_area_factor','map_km','shape')})
    reasons=diff(semantics(a),semantics(b))
    if any(not (p['config'].get('_research') or p['problem'].get('research_configuration')) for p in (a,b)):reasons.append(dict(path='/metadata',reason='LEGACY_METRIC_DEFINITION_NOT_FROZEN'))
    if a['experiment_contract_id']=='HMSP-EXEC-V1' and b['experiment_contract_id']=='HMSP-EXEC-V1' and a['config']!=b['config']:
        reasons.append(dict(path='/config',reason='HMSP_EXPLICIT_CUE_WEIGHT_COST_OR_CONSTRAINT_INPUT_DIFFERS'))
    compatible=not reasons
    return dict(schema='SOLSOL_RUN_COMPARISON_V1',left=dict(run_id=left.id,experiment_contract_id=left.cid,config_sha256=a['config_sha256']),
        right=dict(run_id=right.id,experiment_contract_id=right.cid,config_sha256=b['config_sha256']),
        comparable=compatible,classification='SAME_MODEL_DEFINITION' if compatible else 'DIFFERENT_METRIC_OR_MODEL_DEFINITION',
        reasons=reasons,changes=diff(dict(config=a['config'],optimizer=a.get('optimizer')),dict(config=b['config'],optimizer=b.get('optimizer'))),
        combined_axes_allowed=compatible,raw_read_allowed=True,
        explanation='동일 모델·정의입니다. 설정 차이와 각각의 원시 결과를 확인하세요.' if compatible else '모델·정의·목적 순서 또는 지표 단위/집계가 달라 같은 축으로 합치지 않습니다. 각각의 원시는 열람할 수 있습니다.')
