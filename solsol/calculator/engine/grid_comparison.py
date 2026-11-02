"""Separate fixed-X sampling study through the public Model API."""
import copy,json,threading,time,uuid
from pathlib import Path
import numpy as np
from .store import digest,sha,atomic_json
from .quality_workflow import binding
from .results import _compiled
from .hard_constraints import reports

LOCK=threading.RLock()
ACTIVE=set()
STEPS=(250,500,1000)
IMPLEMENTATION_SHA256=sha(Path(__file__))

def capability(record):
    supported=record.cid=='ABC_COVERAGE_RESOURCE_V1' and 'point_spacing' in record.config and not any(k in record.config for k in ('explicit_points','points'))
    if record.cid=='RADAR_EOIR':
        supported=record.config.get('objective_contract')=='full_area_tradeoff_v6'
        return dict(supported=supported,steps=list(STEPS),reason='' if supported else '이 EO/IR 목적함수는 평가 지점 간격 비교를 아직 지원하지 않습니다. full_area_tradeoff_v6 저장 실행에서 사용할 수 있습니다.',scope='저장 조건 재현 확인 후 별도 평가 버전으로 비교합니다. 서비스 연결·조건 일치 실패 시 결과를 생성하지 않습니다.')
    return dict(supported=supported,steps=list(STEPS),reason='' if supported else '이 모델의 저장 조건을 유지하는 평가 격자 변경 계약이 아직 연결되지 않았습니다. 원래 배치의 검산은 위에서 사용할 수 있습니다.')

def location(record,key):
    if str(uuid.UUID(key))!=key:raise ValueError('GRID_JOB_ID')
    return record.folder/'grid_comparisons'/(key+'.json')

def save(record,value):
    atomic_json(location(record,value['job_id']),dict(payload=value,sha256=digest(value)))

def read(record,key):
    with LOCK:
        wrapper=json.loads(location(record,key).read_text(encoding='utf-8'));value=wrapper['payload']
        if digest(value)!=wrapper['sha256'] or value['parent']!=binding(record):raise ValueError('GRID_EVIDENCE_CHANGED')
        if value['status'] in ('QUEUED','RUNNING') and (str(record.folder),key) not in ACTIVE:
            value=copy.deepcopy(value);value.update(status='INTERRUPTED',message='서버 종료로 중단됐습니다. 같은 배치로 새 비교를 시작하세요.')
        return value

def listing(record):
    return dict(capability=capability(record),jobs=sorted([read(record,p.stem) for p in (record.folder/'grid_comparisons').glob('*.json')],key=lambda r:r['created_at'],reverse=True))

def qualify(row,goals):
    if goals is None:return None
    values=row.get('coverage_metrics',{})
    if any(k not in values or not np.isfinite(values[k]) for k in goals):raise ValueError('GRID_TARGET_METRIC_MISSING')
    return all(values[k]>=threshold for k,threshold in goals.items())

def target_context(packet):
    config=packet['config']
    research=config.get('_research') or packet.get('problem',{}).get('research_configuration',{})
    if 'goals' in research:return dict(kind='AREA_PERCENT',values=research['goals'])
    if packet['experiment_contract_id']=='RADAR_RF_SCANNER':return dict(kind='MODEL_QUALITY_0_1',values=config.get('targets'))
    return dict(kind='AREA_PERCENT',values=config.get('goals'))

def refine(cp,config,cid,step):
    from model_service_client import client,compile_remote
    c=client()
    if cid=='ABC_COVERAGE_RESOURCE_V1':
        if any(k in config for k in ('explicit_points','points')):raise ValueError('GRID_EXPLICIT_POINTS_RESAMPLING_UNDECLARED')
        result=copy.deepcopy(config);result['point_spacing']=step
        new=compile_remote(cid,result,list(cp.space.enabled_sensor_ids),list(cp.objective_order),list(cp.diagnostic_order))
        if new.candidate_order!=cp.candidate_order or new.view_problem()['sites']!=cp.view_problem()['sites']:raise ValueError('GRID_CANDIDATES_CHANGED')
        return new
    if cid=='RADAR_RF_SCANNER':
        keys=c.request('/models/'+cid+'/schema')['model']['defaults'].keys()
        mod=c.module('rf_aoa_v1')
        result=c.call(dict(module='rf_aoa_v1',function='make_config'),[],dict(common=config['common'],parameters={k:config[k] for k in keys},selected_indices=config['selected_indices'],grid_metres=step),{k:mod[k] for k in ('source_sha256','service_release_sha256')})
        if '_research' in config:result['_research']=copy.deepcopy(config['_research'])
    else:
        request={k:copy.deepcopy(config[k]) for k in ('common','parameters','selected_indices','allowed','goals')}
        request.update(grid_metres=step,_research=copy.deepcopy(config.get('client_research')))
        result=c.request('/configuration',dict(experiment_contract_id=cid,config=request))['config']
    new=compile_remote(cid,result,list(cp.space.enabled_sensor_ids),list(cp.objective_order),list(cp.diagnostic_order))
    strip=lambda c:{k:v for k,v in c.items() if k not in ('geometry_payload','geometry_sha256','_research','client_research')}
    if strip(config)!=strip(result):raise ValueError('GRID_NON_GEOMETRY_INPUT_CHANGED')
    if new.service_identity['source_sha256']!=cp.service_identity['source_sha256'] or new.service_identity['service_release_sha256']!=cp.service_identity['service_release_sha256']:raise ValueError('GRID_MODEL_VERSION_CHANGED')
    if new.candidate_order!=cp.candidate_order or new.sensor_order!=cp.sensor_order or new.view_problem()['sites']!=cp.view_problem()['sites']:raise ValueError('GRID_CANDIDATES_CHANGED')
    return new

def calculate(record,rid,step):
    p=record.packet(include_rows=False);source=record.rows[rid];cp=_compiled(record)
    if not reports(record)[rid]['hard_pass']:raise ValueError('GRID_SOURCE_HARD_CONSTRAINT_FAILED')
    if record.cid=='RADAR_EOIR':
        from .eoir_grid_comparison import compare
        return compare(record,rid,step,cp)
    x=np.asarray(source['X'],dtype=np.uint8);base=cp.evaluate_physical(x)[0]
    tolerance=max(p['archive_policy']['tolerance'],1e-10)
    if any(not np.allclose(base[k],source[k],rtol=0,atol=tolerance) for k in ('F','G')):raise ValueError('GRID_ORIGINAL_REPLAY_MISMATCH')
    other=refine(cp,record.config,record.cid,step)
    from .installation_domain import restore_domain
    other=restore_domain(other,p)
    if not np.array_equal(cp.space.allowed,other.space.allowed):raise ValueError('GRID_ALLOWED_CHANGED')
    fine=other.evaluate_physical(x)[0]
    if base['X']!=fine['X']:raise ValueError('GRID_X_CHANGED')
    costs=[r.get('named_metrics',{}).get('cost') for r in (base,fine)]
    if None not in costs and not np.isclose(*costs,rtol=0,atol=tolerance):raise ValueError('GRID_COST_CHANGED')
    research=p['config'].get('_research') or p['problem'].get('research_configuration',{})
    target=target_context(p);goals=target['values']
    metadata=research.get('metadata') or {}
    def point(compiled,row):
        passed=None if goals is None else row.get('qualified') if target['kind']=='MODEL_QUALITY_0_1' else qualify(row,goals)
        if goals is not None and type(passed) is not bool:raise ValueError('GRID_TARGET_RESULT_MISSING')
        return dict(step=compiled.view_problem().get('grid_metres',compiled.config.get('geometry_payload',{}).get('grid_metres')),point_count=len(compiled.view_problem()['demand']),F=row['F'],G=row['G'],named_metrics=row.get('named_metrics',{}),coverage_metrics=row.get('coverage_metrics',{}),target_pass=passed,model=compiled.service_identity)
    return dict(raw_id=rid,X=source['X'],sensor_counts=x.sum(0).astype(int).tolist(),sensor_order=list(cp.sensor_order),goals=goals,goal_kind=target['kind'],installation_domain=p['compilation'].get('installation_domain'),metadata=metadata,original=point(cp,base),comparison=point(other,fine),cost_unchanged=None if None in costs else True,
        candidate_sha256=digest(list(cp.candidate_order)),sites_sha256=digest(cp.view_problem()['sites']),evaluations=2,
        meaning='같은 배치의 표본 간격 민감도입니다. 더 촘촘한 격자를 참값이나 전역 최적으로 간주하지 않습니다.')

def submit(record,options):
    if not isinstance(options,dict) or set(options)!={'raw_id','step'}:raise ValueError('GRID_OPTIONS')
    rid,step=options['raw_id'],options['step']
    if type(rid) is not int or not 0<=rid<len(record.rows) or type(step) is not int or step not in STEPS:raise ValueError('GRID_SELECTION')
    if record.state not in ('completed','cancelled','time_limit'):raise ValueError('GRID_SAVED_RUN_REQUIRED')
    if not capability(record)['supported']:raise ValueError('GRID_MODEL_NOT_SUPPORTED')
    with LOCK:
        if any(folder==str(record.folder) for folder,_ in ACTIVE):raise ValueError('GRID_COMPARISON_ALREADY_RUNNING')
        implementation={'grid_comparison':IMPLEMENTATION_SHA256}
        if record.cid=='RADAR_EOIR':
            from .eoir_grid_comparison import IMPLEMENTATION_SHA256 as adapter_sha
            implementation['eoir_grid_comparison']=adapter_sha
        key=str(uuid.uuid4());value=dict(schema='SOLSOL_GRID_COMPARISON_V1',job_id=key,parent=binding(record),options=copy.deepcopy(options),definition_sha256=IMPLEMENTATION_SHA256,implementation_sha256=implementation,status='QUEUED',created_at=time.time(),provenance='POSTHOC_GRID_SENSITIVITY_NOT_OPTIMIZER',result=None)
        save(record,value);ACTIVE.add((str(record.folder),key))
        def work():
            try:
                with LOCK:value['status']='RUNNING';save(record,value)
                result=calculate(record,rid,step)
                if value['parent']!=binding(record):raise ValueError('GRID_PARENT_CHANGED')
                with LOCK:value.update(status='COMPLETED',result=result);save(record,value)
            except Exception as error:
                with LOCK:value.update(status='ERROR',message=str(error));save(record,value)
            finally:
                with LOCK:ACTIVE.discard((str(record.folder),key))
        threading.Thread(target=work,daemon=True).start()
        return copy.deepcopy(value)
