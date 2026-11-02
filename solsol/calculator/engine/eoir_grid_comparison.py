"""Pinned public EOIR grid extension; never changes the original run evaluator."""
import copy
import uuid
from pathlib import Path
import numpy as np
from model_service_client import ModelClient,decode
from .store import digest,sha

ENDPOINT='http://127.0.0.1:8894'
RELEASE='755df5188ae1bda109e721d3cb0f5434bda3cc9fea3bed8ebe73872e6e038103'
WRAPPER='1e50917f900bdd62fa34466a6ba5e5a3c0066d1e1e35374665f2e6e4c5717b23'
CONTRACT='EOIR_GRID_REEVALUATION_V1'
VERSION='full_area_tradeoff_v6-grid-reevaluation-v1'
IMPLEMENTATION_SHA256=sha(Path(__file__))


def require(ok,message):
    if not ok:raise ValueError('EOIR_GRID_'+message)


def validate_derived_binding(response,request,row,source,tolerance):
    require(response['input_sha256']==digest(request),'REQUEST_HASH')
    require(response['contract_version']==CONTRACT and response['evaluation_version']==VERSION,'EVALUATION_VERSION')
    require(response['evaluation_kind']=='FIXED_PLACEMENT_GRID_REEVALUATION','EVALUATION_KIND')
    for key,top in (('config_hash','config_sha256'),('evaluator_hash','evaluator_sha256'),('grid_sha256','grid_sha256'),('evaluation_version','evaluation_version'),('evaluation_kind','evaluation_kind')):
        require(row[key]==response[top],'ROW_BINDING_'+key)
    require(len(row['G'])==len(source['G']) and np.isfinite(row['G']).all() and np.allclose(row['G'],source['G'],rtol=0,atol=tolerance),'UNCHANGED_G')


def compare(record,rid,step,cp):
    """Require exact parent replay before making separately identified grid rows."""
    p=record.packet(include_rows=False);source=record.rows[rid]
    old=cp._descriptor;frozen=p['problem']['model_service']
    require(all(old.get(k)==v for k,v in frozen.items()),'ORIGINAL_IDENTITY_CHANGED')
    require(cp.config_hash==p['config_sha256'] and cp.evaluator_hash==p['evaluator_sha256'],'ORIGINAL_EVALUATOR_CHANGED')
    x=cp.space.validate(np.asarray(source['X']),installation=True).tolist()
    client=ModelClient(ENDPOINT)
    try:
        parent=client.register(copy.deepcopy(old['definition']))
        require(parent['service_release_sha256']==RELEASE,'RELEASE_CHANGED')
        require(all(parent[k]==old[k] for k in ('api_version','problem_id','input_sha256','source_sha256','definition')),'PARENT_IDENTITY_CHANGED')
        require(parent['compiled']==old['compiled'],'PARENT_COMPILATION_CHANGED')
        capability=client.request('/problems/'+parent['problem_id']+'/grid-evaluation')
        require(capability.get('status')=='SUPPORTED' and capability.get('contract_version')==CONTRACT,'UNSUPPORTED_OBJECTIVE')
        identity=capability['identity']
        expected=dict(problem_id=parent['problem_id'],input_sha256=parent['input_sha256'],model_id=record.cid,model_version=cp.model_version,config_sha256=cp.config_hash,evaluator_sha256=cp.evaluator_hash,source_sha256=parent['source_sha256'],service_release_sha256=RELEASE)
        require(identity==expected,'CAPABILITY_IDENTITY_CHANGED')
        goals=(old['definition']['config'].get('_research') or {}).get('goals')
        from .grid_comparison import target_context,qualify
        require(target_context(p)['values']==goals and capability['targets']==goals,'SAVED_TARGET_SOURCE_MISMATCH')
        bid=str(uuid.uuid4());placements=[dict(id=str(rid),X=x)]
        request=dict(problem_id=parent['problem_id'],batch_id=bid,placements=placements,spatial=False,validate_installation=True)
        replay=client.request('/evaluate-batch',request)
        for key,val in dict(problem_id=parent['problem_id'],batch_id=bid,input_sha256=parent['input_sha256'],model_version=cp.model_version,evaluator_sha256=cp.evaluator_hash,service_release_sha256=RELEASE).items():require(replay.get(key)==val,'REPLAY_IDENTITY_'+key)
        require(len(replay['results'])==1 and replay['results'][0]['id']==str(rid),'REPLAY_ROWS')
        base=decode(replay['results'][0]['row']);tolerance=max(p['archive_policy']['tolerance'],1e-10)
        def parity(row,original):
            require(row['X']==x and row['placement_hash']==source['placement_hash'],'PLACEMENT_CHANGED')
            for key in ('F','G'):
                require(len(row[key])==len(original[key]) and np.isfinite(row[key]).all() and np.allclose(row[key],original[key],rtol=0,atol=tolerance),'PARITY_'+key)
            require(np.isfinite(row['cost']) and np.isclose(row['cost'],source['cost'],rtol=0,atol=tolerance),'COST_CHANGED')
        parity(base,source)
        require(base['config_hash']==cp.config_hash and base['evaluator_hash']==cp.evaluator_hash,'REPLAY_ROW_IDENTITY')
        evidence=[]
        def evaluate(spacing):
            req=dict(contract_version=CONTRACT,problem_id=parent['problem_id'],expected_identity=identity,batch_id=str(uuid.uuid4()),grid_metres=spacing,validate_installation=True,placements=placements)
            response=client.request('/evaluations/grid',req)
            require(response.get('status')=='EVALUATED','NOT_EVALUATED')
            require(digest({k:v for k,v in response.items() if k not in ('api_version','response_sha256')})==response['response_sha256'],'RESPONSE_HASH')
            require(response['base_identity']==identity and response['batch_id']==req['batch_id'],'RESPONSE_IDENTITY')
            require(response['service_release_sha256']==RELEASE and response['wrapper_source_sha256']==WRAPPER,'WRAPPER_CHANGED')
            require(response['optimizer_nfe_delta']==0 and response['evaluations']==1 and not response['search_executed'] and not response['original_results_mutated'] and not response['source_problem_mutated'],'PROVENANCE')
            preserved=response['preserved'];compiled=decode(parent['compiled'])
            require(digest(preserved)==response['preserved_sha256'],'PRESERVED_HASH')
            for key,val in dict(config=old['definition']['config'],sites=cp.view_problem()['sites'],candidate_order=list(cp.candidate_order),sensor_order=list(cp.sensor_order),objective_order=list(cp.objective_order),diagnostic_order=list(cp.diagnostic_order),constraint_order=list(cp.constraint_order),allowed=np.asarray(compiled['space']['allowed']).astype(int).tolist()).items():
                require(preserved[key]==val,'PRESERVED_'+key)
            grid=response['evaluation_grid']
            require(grid['grid_metres']==spacing and digest(grid)==response['grid_sha256'],'GRID_HASH')
            require(response['targets']==goals and len(response['results'])==1 and response['results'][0]['id']==str(rid),'RESULT_BINDING')
            row=decode(response['results'][0]['row'])
            validate_derived_binding(response,req,row,source,tolerance)
            require(row['X']==x and row['original_placement_hash']==source['placement_hash'] and row['installation_validated'],'RESULT_PLACEMENT')
            require(row['sensor_counts']==np.asarray(x).sum(0).tolist(),'SENSOR_COUNTS')
            require(np.isfinite(row['F']+row['G']).all() and len(row['F'])==len(source['F']) and len(row['G'])==len(source['G']),'RESULT_DIMENSION')
            require(np.isclose(row['cost'],source['cost'],rtol=0,atol=tolerance),'RESULT_COST')
            evidence.append(dict(request=req,response=response))
            return dict(step=spacing,point_count=grid['point_count'],F=row['F'],G=row['G'],named_metrics=row['named_metrics'],coverage_metrics=row['coverage_metrics'],target_pass=qualify(row,goals),provenance='DERIVED_FIXED_PLACEMENT_REEVALUATION',model=dict(parent_identity=identity,evaluation_version=response['evaluation_version'],evaluation_kind=response['evaluation_kind'],evaluator_sha256=response['evaluator_sha256'],config_sha256=response['config_sha256'],grid_sha256=response['grid_sha256'],service_release_sha256=RELEASE)),row
        baseline,baseline_row=evaluate(500);parity(baseline_row,source)
        comparison=baseline if step==500 else evaluate(step)[0]
        original=dict(step=500,point_count=len(cp.view_problem()['demand']),F=source['F'],G=source['G'],named_metrics=source.get('named_metrics',{}),coverage_metrics=source.get('coverage_metrics',{}),target_pass=qualify(source,goals),provenance='SAVED_OPTIMIZER_ROW',model=frozen)
        research=old['definition']['config'].get('_research') or {}
        return dict(raw_id=rid,X=x,sensor_counts=np.asarray(x).sum(0).tolist(),sensor_order=list(cp.sensor_order),goals=goals,goal_kind='AREA_PERCENT',installation_domain=p['compilation'].get('installation_domain'),metadata=research.get('metadata',{}),original=original,baseline_reassessment=baseline,comparison=comparison,cost_unchanged=True,candidate_sha256=digest(list(cp.candidate_order)),sites_sha256=digest(cp.view_problem()['sites']),evaluations=1+len(evidence),optimizer_nfe_delta=0,original_model=frozen,registered_model=identity,effective_allowed=p['compilation']['allowed'],original_replay=dict(request=request,response=replay,tolerance=tolerance),grid_evidence=evidence,meaning='원래 수치는 저장된 탐색 배치의 결과입니다. 새 500m 재평가가 원래 목적값·제약값·비용과 같은지 확인한 뒤 센서 위치·수량·비용을 유지하고 성능 확인 지점의 간격만 바꿨습니다. 새 평가 버전의 별도 비교 결과이며, 더 촘촘한 간격이 참값이나 전역 최적성을 보증하지 않습니다.')
    finally:client.close()
