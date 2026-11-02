import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]/'solsol/calculator'
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def request():
    from model_service_client import CID,default_config
    c=default_config();c.update(candidate_count=4,point_spacing=250)
    for s in ['A','B','C']:c[s+'_stock']=2
    return dict(experiment_contract_id=CID,model_config=c,enabled_sensor_ids=['A','B','C'],
        objective_ids=['coverage','joint_coverage','cost'],diagnostic_ids=[],solver_policy='generic_v1',goals=None,
        optimizer=dict(algorithm='NSGA-II',seed=7,population=8,generations=2,
            initializer='random',initialization_evaluations=16,initialization_seconds=10,ref_partitions=1))


def test_preserved_configuration_and_model_identity():
    from engine.configuration import compile_request
    from engine.workflow import execution_snapshot
    r=request();cp,opt,summary=compile_request(r['experiment_contract_id'],r)
    snapshot=execution_snapshot(cp,opt,r)
    assert summary['n_var']==12 and snapshot['declared_nfe']==24
    assert cp.service_identity['source_sha256']==cp.evaluator_hash


def test_preserved_run_store_and_quality(tmp_path):
    from engine.configuration import compile_request
    from engine.workflow import execution_snapshot
    from engine.runtime import RunService
    import time
    r=request();cp,opt,_=compile_request(r['experiment_contract_id'],r)
    service=RunService(tmp_path);snap=execution_snapshot(cp,opt,r)
    session=service.create(cp,opt,'full-test-1',execution_snapshot=snap,submitted_request=r)
    deadline=time.monotonic()+60
    while session.state not in ('completed','failed','cancelled','time_limit') and time.monotonic()<deadline:time.sleep(.05)
    assert session.state=='completed',session.error
    assert len(session.rows)==24 and len(session.checkpoints)==3
    restored=service.store.read(session.folder)
    assert restored['run_id']==session.id
    from engine.quality_assessment import assess
    report=assess(session)
    assert report['hard_invalid']==0 and report['nfe']==24


def test_retained_uint8_hard_audit_matches_plain_lists():
    import numpy as np
    from engine.hard_constraints import _prepare,_measure_batch
    p=dict(experiment_contract_id='ABC_COVERAGE_RESOURCE_V1',compilation=dict(allowed=[[True,True]],co_location=True),problem=dict(sites=[[0,0]]))
    prepared=_prepare(p,None)
    plain=list(_measure_batch([dict(id=0,X=[[0,1]])],p,None,prepared))[0]
    retained=list(_measure_batch([dict(id=0,X=np.array([[0,1]],np.uint8))],p,None,prepared))[0]
    assert retained[4]==plain[4]==0


def test_neutral_exact_cost_formulation_matches_all_tiny_layouts():
    import itertools
    import numpy as np
    from scipy.optimize import Bounds,LinearConstraint,milp
    from engine.configuration import compile_request
    from engine.milp_initialization import fetch_formulation,arrays,checked_incumbent
    r=request();r['goals']={'coverage':20,'joint_coverage':10}
    cp,_,_=compile_request(r['experiment_contract_id'],r)
    p=fetch_formulation(cp);a=arrays(cp,p);c,A,lo,hi,_,_=a
    result=milp(c,integrality=np.ones(len(c)),bounds=Bounds(np.zeros(len(c)),np.ones(len(c))),constraints=LinearConstraint(A,lo,hi))
    assert result.success
    x,cost=checked_incumbent(cp,p,a,result.x)
    row=cp.evaluate_physical(x)[0]
    assert all(g<=0 for g in row['G']) and row['qualified']
    best=float('inf')
    for bits in itertools.product([0,1],repeat=12):
        row=cp.evaluate_physical(np.array(bits).reshape(4,3))[0]
        if all(g<=0 for g in row['G']) and row['qualified']:best=min(best,row['cost'])
    assert cost==best


def test_public_api_confirmation_idempotency_and_restore(tmp_path):
    import json,threading,time
    from urllib.request import urlopen
    from solsol.calculator.launch import make_server
    from engine_client import EngineClient
    server=make_server(0,tmp_path);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        client=EngineClient(request()['experiment_contract_id'],base)
        confirmed=client._request('engine/validate',request())
        headers={'X-Request-ID':'confirmed-full-api-1','X-Execution-SHA256':confirmed['execution_sha256']}
        run=client._request('engine/runs',request(),extra_headers=headers)
        again=client._request('engine/runs',request(),extra_headers=headers)
        assert run['run_id']==again['run_id'] and again['deduplicated']
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            state=client._request('runs/'+run['run_id']+'/progress')
            if state['state'] in ('completed','failed'):break
            time.sleep(.05)
        assert state['state']=='completed',state
        view=client._request('engine/runs/'+run['run_id']+'/view?view=summary')
        assert view['view_schema']=='SOLSOL_CONFIGURABLE_SUMMARY_V1'
        assert len(json.loads(client._request('engine/runs/'+run['run_id']+'/export',binary=True))['rows'])==24
        with urlopen(base+'/api/openapi.json') as response:assert json.load(response)['openapi']=='3.1.0'
    finally:server.shutdown();server.server_close();thread.join()


def test_shared_resource_contract_replaces_old_count_and_cost_rules():
    from engine.configuration import compile_request
    r=request();r['resource_contract']=dict(version='SHARED_RESOURCES_V1',
        sensor_counts={s:dict(mode='EXACT',value=1) for s in ['A','B','C']},
        budget=dict(mode='MAX',limit=100),cost=dict(sensor_unit_costs=dict(A=2,B=3,C=4),site_cost=5))
    cp,_,_=compile_request(r['experiment_contract_id'],r)
    row=cp.evaluate_physical([[[1,1,1],[0,0,0],[0,0,0],[0,0,0]]])[0]
    assert cp.bundle.inventory_rule['lower']==[1,1,1]
    assert cp.bundle.inventory_rule['upper']==[1,1,1]
    assert row['cost']==14 and sum(row['cost_components'].values())==14


def test_batch_empty_and_declared_geometry_are_preserved():
    import numpy as np
    from engine.configuration import compile_request
    r=request();cp,_,_=compile_request(r['experiment_contract_id'],r)
    batch=cp.batch(np.empty((0,cp.n_var),dtype=np.uint8))
    assert batch.X.shape==(0,4,3) and batch.F.shape==(0,3)
    g=cp.view_problem()['geometry']
    assert g['center']==[500,500] and g['vertices']==[[125,125],[875,125],[875,875],[125,875]]


def test_explicit_inputs_do_not_bypass_shared_resources():
    from model_service_client import CompiledProblem,CID
    from solsol.models.coverage import example_config
    c=example_config();c['_resource_contract']=dict(version='SHARED_RESOURCES_V1',
        sensor_counts={s:dict(mode='EXACT',value=1) for s in ['A','B','C']},
        budget=dict(mode='MAX',limit=100),cost=dict(sensor_unit_costs=dict(A=2,B=3,C=4),site_cost=5))
    cp=CompiledProblem(CID,c,['A','B','C'],['coverage','cost'],[])
    assert cp.bundle.inventory_rule['lower']==[1,1,1]
    x=[[1,1,1]]+[[0,0,0] for _ in range(11)]
    assert cp.evaluate_physical(x)[0]['cost']==14
    assert cp.view_problem()['geometry'] is None


def test_grid_resampling_changes_only_sample_points_and_rejects_explicit_points():
    from engine.configuration import compile_request
    from engine.grid_comparison import refine
    r=request();cp,_,_=compile_request(r['experiment_contract_id'],r)
    fine=refine(cp,cp.config,cp.cid,500)
    assert fine.view_problem()['sites']==cp.view_problem()['sites']
    assert fine.view_problem()['geometry']==cp.view_problem()['geometry']
    assert fine.view_problem()['demand']!=cp.view_problem()['demand']
    c=dict(cp.config,explicit_points=cp._physical.config['points'])
    with pytest.raises(ValueError,match='EXPLICIT_POINTS'):refine(cp,c,cp.cid,500)


@pytest.mark.parametrize('shape',['square','circle','hexagon','overlap'])
def test_all_common_region_shapes_have_truthful_points(shape):
    from model_service_client import model_config,default_config
    from neutral_geometry import contains
    c=default_config();c['shape']=shape
    physical=model_config(c)
    assert physical['evaluation_geometry']['kind']==shape
    assert physical['points'] and all(contains(physical['evaluation_geometry'],p['x'],p['y']) for p in physical['points'])


def finished_session(tmp_path,seed=7):
    import time
    from engine.configuration import compile_request
    from engine.workflow import execution_snapshot
    from engine.runtime import RunService
    r=request();r['optimizer']['seed']=seed
    cp,opt,_=compile_request(r['experiment_contract_id'],r);service=RunService(tmp_path)
    s=service.create(cp,opt,'quality-fixture-'+str(seed),execution_snapshot=execution_snapshot(cp,opt,r),submitted_request=r)
    deadline=time.monotonic()+60
    while s.state not in ('completed','failed') and time.monotonic()<deadline:time.sleep(.02)
    # Internal state can be assigned while terminal persistence owns this lock.
    # The public packet/progress API already waits for the durable publication.
    with s.lock:assert s.state=='completed',s.error
    return s,service


@pytest.mark.parametrize('method',['local','milp','exact','refine'])
def test_full_quality_jobs_preserve_raw_and_store_every_evaluation(tmp_path,method):
    import time
    from engine import quality_jobs as q
    from engine.store import sha
    s,_=finished_session(tmp_path);before=sha(s.folder/'raw.json')
    job=q.submit(s,dict(scope='selected',raw_id=0,generation=2,method=method))
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=q.get(s,job['job_id'])
        if state['status'] in q.TERMINAL:break
        time.sleep(.02)
    assert state['status']=='COMPLETED',state
    entries=list(q.stored_entries(s,state))
    assert state['evaluated']==len(entries)>0
    assert all(r['provenance']=='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER' for r in entries)
    assert sha(s.folder/'raw.json')==before and state['global_optimality'] is False


def test_quality_exact_stop_and_resume_verifies_frozen_batches(tmp_path):
    import time
    from engine import quality_jobs as q
    s,_=finished_session(tmp_path)
    job=q.submit(s,dict(scope='selected',raw_id=0,method='exact'))
    q.cancel(s,job['job_id']);deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=q.get(s,job['job_id'])
        if state['status'] in q.TERMINAL and q.identity(s,job['job_id']) not in q.ACTIVE:break
        time.sleep(.02)
    assert state['status']=='STOPPED',state
    old=state['next_eval'];q.resume(s,job['job_id'])
    while time.monotonic()<deadline:
        state=q.get(s,job['job_id'])
        if state['status'] in q.TERMINAL:break
        time.sleep(.02)
    assert state['status']=='COMPLETED' and state['next_eval']>=old
    assert len(list(q.stored_entries(s,state)))==state['next_eval']


def test_set_search_quality_and_seed_comparison_use_preserved_services(tmp_path):
    from engine.quality_research import calculate,save_study
    from engine.results import quality_summary
    s,service=finished_session(tmp_path,7)
    t,_=finished_session(tmp_path,8)
    report=calculate([s,t]);search=quality_summary(s)
    assert report and len(search['search_quality'])==3
    study=save_study(s,[t]);assert study


@pytest.mark.parametrize('algorithm',['NSGA-II','NSGA-III'])
@pytest.mark.parametrize('initializer',['random','greedy','milp'])
def test_preserved_optimizer_initializer_matrix(tmp_path,algorithm,initializer):
    import time
    from engine.configuration import compile_request
    from engine.workflow import execution_snapshot
    from engine.runtime import RunService
    from engine.common_initialization import VERSION
    r=request();r['optimizer'].update(algorithm=algorithm,initializer=initializer,initialization_version=VERSION)
    cp,opt,_=compile_request(r['experiment_contract_id'],r);service=RunService(tmp_path)
    s=service.create(cp,opt,algorithm+'-'+initializer,execution_snapshot=execution_snapshot(cp,opt,r),submitted_request=r)
    deadline=time.monotonic()+60
    while s.state not in ('completed','failed') and time.monotonic()<deadline:time.sleep(.02)
    with s.lock:
        assert s.state=='completed',s.error
        assert s.audit['raw_replay']=='PASS' and len(s.rows)==24
        assert s.initialization['method']==initializer
        assert s.counters['initial_population_evaluations']==8


def test_saved_initialization_keeps_source_evidence_and_replays(tmp_path):
    import time
    from engine.saved_initialization import first,bind
    from engine.configuration import compile_request
    from engine.workflow import execution_snapshot
    s,service=finished_session(tmp_path)
    r=request();r['optimizer'].update(initializer='saved',saved_seed=first(s)['reference'])
    cp,opt,_=compile_request(r['experiment_contract_id'],r);bind(cp,opt,lambda cid,rid:service.get(rid,cid))
    new=service.create(cp,opt,'saved-initializer',execution_snapshot=execution_snapshot(cp,opt,r),submitted_request=r)
    deadline=time.monotonic()+60
    while new.state not in ('completed','failed') and time.monotonic()<deadline:time.sleep(.02)
    with new.lock:
        assert new.state=='completed',new.error
        assert new.initialization['method']=='saved'
        assert new.solver_metadata['initial_X'][0]==s.rows[r['optimizer']['saved_seed']['row_id']]['X']
