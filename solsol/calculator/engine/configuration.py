"""Shared workflow validation; the model service owns the registry."""
import copy
import math
from .contracts import digest
from model_service_client import client
TOY = "TOY_DIMENSION_V1"

def same_json_numbers(left, right):
    """Allow int/float JSON roundtrips without accepting booleans as numbers."""
    if type(left) in (int,float) and type(right) in (int,float):
        return math.isfinite(left) and math.isfinite(right) and left==right
    if type(left) is not type(right):return False
    if isinstance(left,dict):
        return left.keys()==right.keys() and all(same_json_numbers(left[k],right[k]) for k in left)
    if isinstance(left,list):
        return len(left)==len(right) and all(same_json_numbers(a,b) for a,b in zip(left,right))
    return left==right
def catalog():
    registry=copy.deepcopy(client().request("/models")["registry"])
    order=['RADAR_EOIR','RADAR_RF_SCANNER','HMSP-2D-V1','HMSP-EXEC-V1']
    registry['bundles'].sort(key=lambda b:order.index(b['id']) if b['id'] in order else len(order))
    from .common_initialization import VERSION, VERSIONS
    registry['calculator_capabilities']={'shared_resources':'SHARED_RESOURCES_V1','generic_initializers':['random','greedy','milp','saved'],
        'unavailable_initializers_by_contract':{},'initialization_version':VERSION,'initialization_versions':list(VERSIONS),'initialization_owner':'CALCULATOR',
        'milp_semantics':'LOCAL_LINEAR_F_G_PROPOSAL_NOT_EXACT_MODEL'}
    return registry
def metadata(cid):return copy.deepcopy(next(b for b in catalog()["bundles"] if b["id"]==cid))

def compile_request(cid, obj):
    from .registry import compile_problem
    from .runtime import optimizer_config
    allowed={'experiment_contract_id','model_config','enabled_sensor_ids','objective_ids','diagnostic_ids','solver_policy','optimizer','goals','installation_domain','resource_contract','source_run_id'}
    if not isinstance(obj,dict) or set(obj)-allowed or obj.get('experiment_contract_id')!=cid:
        raise ValueError('configuration: fields or experiment identity mismatch')
    meta=metadata(cid)
    for field in ('enabled_sensor_ids','objective_ids','diagnostic_ids'):
        if not isinstance(obj.get(field),list):raise ValueError(field+': ordered ID list required')
    if set(obj['objective_ids'])&set(obj['diagnostic_ids']):raise ValueError('diagnostic_ids: a metric cannot have two modes')
    if len(obj['objective_ids'])<2:raise ValueError('objective_ids: 현재 정책은 최적화 목적 2개 이상을 요구합니다')
    if not obj['enabled_sensor_ids']:raise ValueError('enabled_sensor_ids: 센서 한 종 이상을 선택하세요')
    policy=obj.get('solver_policy')
    if policy not in meta['policies']:raise ValueError('solver_policy: 지원하지 않는 정책')
    if policy!='generic_v1' and (obj['enabled_sensor_ids']!=[s['id'] for s in meta['sensors']] or obj['objective_ids']!=meta['default_objective_ids']):
        raise ValueError('solver_policy: 센서·목적 변경에는 일반 구성을 명시적으로 선택하세요')
    goals=obj.get('goals')
    hmsp=cid=='HMSP-EXEC-V1'
    if hmsp and goals is not None:raise ValueError('HMSP_GOALS: 품질 목표는 model_config.goals에 명시하세요. 영역 목표 변환은 지원하지 않습니다.')
    if goals is not None:
        keys={g['id'] for g in meta['coverage_metrics']}
        if not isinstance(goals,dict) or not goals or set(goals)-keys or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100 for v in goals.values()):
            raise ValueError('goals: 등록된 영역 커버율에 0–100% 목표를 입력하세요')
    supplied=copy.deepcopy(obj.get('model_config',{}))
    if hmsp and isinstance(supplied,dict):
        rf=supplied.get('rf_config',{})
        if isinstance(rf,dict) and rf.get('common') is not None and rf.get('selected_indices') is None:
            # Browser JSON collapses 500.0 to 500. Recover the Model's own
            # canonical representation, never recompute or relax its digest.
            keys=catalog()['ui_models']['RADAR_RF_SCANNER']['parameter_keys_by_version']['rf-aoa-v1']
            canonical=client().request('/configuration',dict(experiment_contract_id='RADAR_RF_SCANNER',
                config=dict(common=rf['common'],parameters={k:rf[k] for k in keys})))['config']
            if not same_json_numbers(rf.get('geometry_payload'),canonical['geometry_payload']) or rf.get('geometry_sha256')!=canonical['geometry_sha256']:
                raise ValueError('HMSP_COMMON_GEOMETRY_CHANGED: regenerate common geometry before submitting')
            # Only number serialization is normalized. Other supplied fields
            # retain their original meaning and are checked by the Model.
            rf['geometry_payload']=canonical['geometry_payload']
    preparation=dict(experiment_contract_id=cid,config=supplied)
    if 'resource_contract' in obj:preparation['resource_contract']=copy.deepcopy(obj['resource_contract'])
    if (obj.get('resource_contract') is not None or supplied.get('_resource_contract') is not None) and policy!='generic_v1':
        raise ValueError('RESOURCE_POLICY: 공통 자원 제약에는 일반 계산 정책을 선택하세요')
    prepared=client().request('/configuration',preparation)
    config=prepared['config'];meta=prepared['metadata']
    research=dict(schema='SOLSOL_RESEARCH_CONFIGURATION_V1',metadata=meta,goals=goals,goal_definition='EVALUATION_POINT_COVERAGE_V1',solver_policy=policy,
        enabled_sensor_ids=obj['enabled_sensor_ids'],objective_ids=obj['objective_ids'],diagnostic_ids=obj['diagnostic_ids'])
    if not hmsp:config['_research']=research
    else:
        research.update(goals=copy.deepcopy(config['goals']),goal_definition='HMSP_QUALITY_THRESHOLDS_0_1_V1_NOT_AREA_PERCENT')
    cp=compile_problem(cid,config,obj['enabled_sensor_ids'],obj['objective_ids'],obj['diagnostic_ids'])
    from .installation_domain import apply_domain,default_domain
    domain=apply_domain(cp,obj.get('installation_domain',default_domain(cid)),policy)
    cp.calculator_configuration=research
    opt=copy.deepcopy(obj.get('optimizer',{}));opt['policy']=policy
    actual,policy=optimizer_config(cp,opt)
    if hmsp:goals=copy.deepcopy(research['goals'])
    from .objective_activity import projection
    activity=projection(cp) if policy=='generic_v1' else None
    if actual['algorithm']=='NSGA-III' and policy=='generic_v1':
        m=len(activity['effective_indices']);count=math.comb(actual.get('ref_partitions',1)+m-1,m-1)
        if count>actual['population']:raise ValueError('optimizer.ref_partitions: 참조방향 수가 개체 수보다 큽니다')
    return cp,opt,dict(config_sha256=cp.config_hash,sensor_order=list(cp.sensor_order),enabled_sensor_ids=list(cp.space.enabled_sensor_ids),
        objective_ids=list(cp.objective_order),diagnostic_ids=list(cp.diagnostic_order),n_var=cp.n_var,n_obj=cp.n_obj,n_constr=cp.n_constr,objective_projection=activity,
        solver_policy=policy,optimizer=actual,declared_nfe=actual['population']*actual['checkpoints'],metadata=meta,goals=goals,presentation=cp.presentation,installation_domain=domain,
        resource_contract=copy.deepcopy(config.get('_resource_contract')),
        policy_difference=('계산기 공통 초기화: 무작위 / Greedy / MILP 국소근사. 실제 Model F/G로 평가하며 근사 MILP의 최적성은 원래 모델의 최적성이 아닙니다. '+('HMSP 품질 목표 0~1은 모델 G<=0 제약입니다.' if hmsp else '영역 목표는 공개 coverage_metrics로 별도 확인합니다.')) if policy=='generic_v1' else '과거 계산 재현 정책입니다. 새 공통 초기화 비교는 일반 구성을 선택하세요.')
