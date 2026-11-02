"""Full-service integration, separate from the historical small baseline tests."""
import copy
import json
import threading
import time
import uuid
import pytest
from test_full_calculator import request
from solsol.calculator.launch import make_server
from solsol.calculator.client import EngineClient


@pytest.fixture
def api(tmp_path):
    server=make_server(0,tmp_path);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    c=EngineClient(request()['experiment_contract_id'],f'http://127.0.0.1:{server.server_port}')
    try:yield c
    finally:server.shutdown();server.server_close();thread.join()


def terminal(c,rid):
    for _ in range(120):
        p=c.wait(rid,1)
        if p['state'] in {'completed','failed','cancelled','interrupted'}:return p
    raise AssertionError('run deadline')


def test_public_client_cancel_and_same_full_service(api):
    r=request();r['optimizer']['generations']=100
    posted=api.submit(r);api.cancel(posted['run_id'])
    p=terminal(api,posted['run_id']);assert p['state'] in {'cancelled','completed'}
    assert any(x['run_id']==posted['run_id'] for x in api.list_runs()['runs'])


def test_public_validation_export_import_multiseed_resource_guided(api,tmp_path):
    from model_service_client import client
    from engine.resource_study import compose
    r=request();r['resource_contract']={'version':'SHARED_RESOURCES_V1'}
    r['resource_contract']=client().request('/configuration',dict(experiment_contract_id=api.contract_id,config=r['model_config'],resource_contract=r['resource_contract']))['config']['_resource_contract']
    body=dict(base_request=r,budgets=[30],radius_levels_m={'A':[300]},seeds=[11,12])
    plan=compose(api.contract_id,body)
    preview=api.preview_validation(plan)
    assert len(preview['cells'])==2
    posted=api.submit_validation(plan,str(uuid.uuid4()),preview['plan_sha256'])
    vid=posted['validation_id'];deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        saved=api.validation(vid)
        if saved['state'] not in {'queued','running','preparing','analyzing'}:break
        time.sleep(.05)
    assert saved['state']=='completed',saved
    assert len(saved['cells'])==2 and all(c['state']=='completed' for c in saved['cells'])
    raw=api._request('engine/validations/'+vid+'/export',binary=True)
    packet=api.read_validation_export(raw)
    assert packet
    import base64
    imported=api._request('engine/validation-export/read',{'base64':base64.b64encode(raw).decode()})
    assert imported
    guided=api._request('engine/guided-cost-budget/preview-a',dict(base_request=r,seeds=[11,12]))
    assert guided
    ids=[c['attempts'][-1]['run_id'] for c in saved['cells']]
    assert api.compare_runs(ids[0],ids[1])
    assert api.quality_research(ids[0],[ids[1]])
    assert api.empirical_reference(ids)
    rid=ids[0]
    assert api.quality_overview(rid)
    assert api._request('engine/runs/'+rid+'/quality-workflow?view=summary')
    placements=api._request('engine/runs/'+rid+'/placements?limit=5&sort=cost')
    assert placements
    job=api.quality_start(rid,dict(scope='selected',raw_id=0,method='local'))
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        state=api.quality_status(rid,job['job_id'])
        if state['status'] in {'COMPLETED','FAILED','STOPPED'}:break
        time.sleep(.02)
    assert state['status']=='COMPLETED',state
    raw=api._request('engine/runs/'+rid+'/quality-jobs/'+job['job_id']+'/export',binary=True)
    assert len(raw)>0


def test_no_relation_model_with_selected_metrics():
    from engine.configuration import compile_request
    r=request();r['model_config']['relations']=[];r['objective_ids']=['coverage','cost']
    cp,_,_=compile_request(r['experiment_contract_id'],r)
    assert cp.n_obj==2


def test_intersection_area_distance_is_not_union():
    from engine.placement_selection import distance_to_area
    g=dict(kind='overlap',centers=[[0,0],[2,0]],radius=2,semantics='intersection')
    assert distance_to_area([-.5,0],g)==pytest.approx(.5)
    assert distance_to_area([1,0],g)==0
    assert distance_to_area([1,3],g)==pytest.approx(3-3**.5)


def test_plugin_schema_api_and_full_compile(tmp_path):
    import model_service_client as m
    from engine.configuration import compile_request
    cid='NEUTRAL_EXAMPLE_V2';meta=m.model_metadata(m.CID);schema=m.model_schema(m.CID)
    meta['id']=schema['id']=cid;meta['name']='Alternative neutral research model'
    schema['defaults']['A_radius']=777
    def converter(config):return m.model_config(config,m.CID)
    m.register_model(cid,meta,schema,converter)
    try:
        server=make_server(0,tmp_path);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            c=EngineClient(cid,f'http://127.0.0.1:{server.server_port}');assert c.config()['default']['A_radius']==777
            r=request();r['experiment_contract_id']=cid;r['model_config']['A_radius']=777
            assert c.validate_configuration(r)['summary']['n_obj']==3
            p=c.submit_configuration(r);assert terminal(c,p['run_id'])['state']=='completed'
            assert c.status(p['run_id'])['experiment_contract_id']==cid
        finally:server.shutdown();server.server_close();thread.join()
    finally:m.MODELS.pop(cid,None)


def test_general_compiled_builder_identity_capabilities_run_restore(tmp_path):
    import model_service_client as m
    class OpaqueProblem:
        def __init__(self,inner):object.__setattr__(self,'inner',inner)
        def __getattr__(self,key):
            if key=='_physical':raise AttributeError(key)
            return getattr(self.inner,key)
        def __setattr__(self,key,value):setattr(self.inner,key,value)
    def builder(cid,config,enabled,objectives,diagnostics):
        return OpaqueProblem(m.CompiledProblem(cid,config,enabled,objectives,diagnostics))
    cid='COMPILED_NEUTRAL_TEST_V1';meta=m.model_metadata(m.CID);schema=m.model_schema(m.CID)
    meta['id']=schema['id']=cid;m.register_compiled_model(cid,meta,schema,builder)
    def start():
        server=make_server(0,tmp_path);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        return server,thread,EngineClient(cid,f'http://127.0.0.1:{server.server_port}')
    try:
        r=request();r['experiment_contract_id']=cid
        server,thread,c=start()
        try:
            assert c.validate_configuration(r)
            posted=c.submit_configuration(r);rid=posted['run_id'];assert terminal(c,rid)['state']=='completed'
            cp=next(v for v in m.PROBLEMS.values() if v.cid==cid)
            assert not hasattr(cp,'_physical')
            for path in ['/problems/'+cp.problem_id+'/initialization','/problems/'+cp.problem_id+'/sensor-support']:
                with pytest.raises(m.ModelServiceError,match='MODEL_CAPABILITY_UNSUPPORTED'):m.client().request(path)
        finally:server.shutdown();server.server_close();thread.join()
        server,thread,c=start()
        try:assert c.status(rid)['state']=='completed'
        finally:server.shutdown();server.server_close();thread.join()
    finally:m.MODELS.pop(cid,None)
