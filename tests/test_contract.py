import copy
import itertools

import numpy as np
import pytest

from solsol.models.coverage import CoverageModel, example_config
from solsol.geometry import visible
from solsol.engine.runtime import run_experiment, replay
from solsol.engine.storage import RunStore


def tiny():
    c = example_config()
    c['sites'] = [dict(id='s0', x=0, y=0, z=0, capacity=3, activation_cost=4),
                  dict(id='s1', x=4, y=0, z=0, capacity=3, activation_cost=4)]
    c['points'] = [dict(id='p0', x=0, y=0, z=0, weight=1),
                   dict(id='p1', x=4, y=0, z=0, weight=3)]
    c['sensors'] = [dict(id=k, radius=1, height=2, cost=v, resource=1, minimum=0, maximum=2)
                    for k,v in [('A',2),('B',3)]]
    c['relations'] = [dict(id='AB', sensors=['A','B'])]
    c['obstacles'] = []
    c['budget'] = 100
    c['total_resource'] = 4
    c['goals'] = {}
    return c


def test_analytic_joint_union_and_shared_activation():
    m = CoverageModel(tiny())
    r = m.evaluate([[1,1],[0,0]])
    assert r['coverage'] == .25
    assert r['joint_coverage'] == .25
    assert r['cost'] == 9
    assert r['F'] == [-.25,-.25,9.]
    assert all(g <= 0 for g in r['G'])
    assert r['covered_points'] == [True,False]


def test_relation_requires_same_point_not_same_installation():
    c = tiny(); c['sensors'][0]['radius'] = 5
    r = CoverageModel(c).evaluate([[1,0],[0,1]])
    assert r['coverage'] == 1
    assert r['joint_coverage'] == .75
    assert r['cost'] == 13


def test_resource_budget_and_goals_are_constraints():
    c = tiny(); c['sites'][0]['capacity']=1; c['budget']=8; c['goals']={'coverage':.5}
    r = CoverageModel(c).evaluate([[1,1],[0,0]])
    assert sum(g > 0 for g in r['G']) == 3


def test_los_solid_prism_and_heights():
    box = dict(xmin=1,xmax=2,ymin=-1,ymax=1,zmin=0,zmax=3)
    assert not visible([0,0,2],[4,0,0],[box])
    assert visible([0,0,5],[4,0,5],[box])
    assert visible([0,2,2],[4,2,0],[box])
    assert not visible([1,0,1],[4,0,0],[box])
    assert not visible([0,1,1],[4,1,1],[box])


@pytest.mark.parametrize('mutation',[
    lambda c:c['sensors'][0].update(radius=-1),
    lambda c:c['sensors'][0].update(cost=float('nan')),
    lambda c:c['sensors'][0].update(maximum=1.5),
    lambda c:c['sensors'][0].update(minimum=3,maximum=2),
    lambda c:c['sensors'][0].update(id='B'),
    lambda c:c.update(points=[]),
    lambda c:c['relations'][0].update(sensors=['Z']),
    lambda c:c.update(goals={'coverage':2}),
    lambda c:c.update(los='false'),
    lambda c:c['sites'][0].update(allowed=[]),
])
def test_invalid_inputs_rejected(mutation):
    c=tiny(); mutation(c)
    with pytest.raises(ValueError):CoverageModel(c)


def test_outside_installation_and_forbidden_slots():
    c=tiny(); c['sites'][0].update(x=-.5,allowed=['A'])
    m=CoverageModel(c)
    assert m.evaluate([[1,0],[0,0]])['coverage']==.25
    with pytest.raises(ValueError):m.evaluate([[0,1],[0,0]])
    with pytest.raises(ValueError):m.evaluate([[.5,0],[0,0]])


def test_no_relations_omits_joint_objective():
    c=tiny();c['relations']=[];c['objectives']=['coverage','cost']
    assert CoverageModel(c).evaluate([[0,0],[0,0]])['F']==[0.,0.]


def test_snapshot_isolated():
    c=tiny();m=CoverageModel(c);before=m.contract_id
    c['sensors'][0]['radius']=99
    assert m.contract_id==before
    assert m.evaluate([[1,0],[0,0]])['coverage']==.25


def test_extreme_finite_weights_normalize_without_overflow():
    c=tiny()
    for p in c['points']:p['weight']=1e308
    assert CoverageModel(c).evaluate([[1,0],[1,0]])['coverage']==1


@pytest.mark.parametrize('objectives',[['cost','coverage'],['joint_coverage','coverage']])
def test_greedy_does_not_assume_cost_last(objectives):
    from solsol.engine.initializers import prepare
    from solsol.engine.runtime import options
    import threading
    c=tiny();c['objectives']=objectives;m=CoverageModel(c)
    _,ledger,_=prepare(m,options(dict(initializer='greedy',preparation_budget=32,population=4)),threading.Event())
    final=next(r['row'] for r in ledger if r['purpose']=='proposal-recheck')
    assert final['coverage']>0


@pytest.mark.parametrize('algorithm',['NSGA-II','NSGA-III'])
@pytest.mark.parametrize('initializer',['random','greedy','milp'])
def test_run_replay_seed_and_cumulative_archive(algorithm,initializer):
    opt=dict(algorithm=algorithm,initializer=initializer,seed=17,population=12,generations=3,
             preparation_budget=16,ref_partitions=2)
    a=run_experiment(CoverageModel(tiny()),opt)
    b=run_experiment(CoverageModel(tiny()),opt)
    assert [(r['X'],r['F'],r['G']) for r in a['rows']]==[(r['X'],r['F'],r['G']) for r in b['rows']]
    assert replay(a)['status']=='PASS'
    assert a['counters']['search_evaluations']==len(a['rows'])
    assert a['counters']['preparation_evaluations']==len(a['preparation'])
    assert len(a['checkpoints'])==4
    oracle=[]
    for bits in itertools.product([0,1],repeat=4):
        x=np.array(bits).reshape(2,2)
        # independent hand-derived reference, no Model calls
        union=[bool(x[i].any()) for i in range(2)]
        joint=[bool(x[i].all()) for i in range(2)]
        f=[-(union[0]+3*union[1])/4,-(joint[0]+3*joint[1])/4,
           float(2*x[:,0].sum()+3*x[:,1].sum()+4*sum(union))]
        oracle.append((x.tolist(),f))
    for row in a['rows']:
        assert row['F']==next(f for x,f in oracle if x==row['X'])
    feasible=[r for r in a['rows'] if all(g<=0 for g in r['G'])]
    expected=[];seen=set()
    for r in feasible:
        key=str(r['X'])
        if key in seen:continue
        seen.add(key)
        if not any(all(u<=v for u,v in zip(t['F'],r['F'])) and t['F']!=r['F'] for t in feasible):
            expected.append(r['id'])
    assert a['archive_ids']==expected


def test_store_checksum_contract_and_full_replay(tmp_path):
    a=run_experiment(CoverageModel(tiny()),dict(seed=4,population=8,generations=2))
    store=RunStore(tmp_path);store.save(a);b=store.load(a['run_id'])
    assert b==a
    assert replay(b)['checked_rows']==len(a['rows'])
    bad=copy.deepcopy(a);bad['rows'][0]['cost']+=1
    assert replay(bad)['status']=='FAIL'
    bad=copy.deepcopy(a);bad['config']['budget']=1
    assert replay(bad)['status']=='FAIL'
    path=tmp_path/(a['run_id']+'.json');path.write_text('{}')
    with pytest.raises(ValueError):store.load(a['run_id'])


@pytest.mark.parametrize('mutation',[
    lambda r:r['rows'][0].update(generation=100),
    lambda r:r['rows'][0].update(provenance='SEARCH_EVALUATION'),
    lambda r:r['checkpoints'][0].update(population_ids=[]),
])
def test_replay_checks_lifecycle_metadata(mutation):
    a=run_experiment(CoverageModel(tiny()),dict(population=4,generations=1))
    mutation(a)
    assert replay(a)['status']=='FAIL'


def test_zero_generation_and_pre_cancel_are_honest():
    import threading
    a=run_experiment(CoverageModel(tiny()),dict(population=4,generations=0))
    assert len(a['rows'])==4 and len(a['checkpoints'])==1
    event=threading.Event();event.set()
    b=run_experiment(CoverageModel(tiny()),dict(population=4,generations=0),cancel=event)
    assert b['status']=='stopped' and not b['rows']
    assert replay(b)['status']=='PASS'


def test_all_infeasible_has_empty_archive():
    c=tiny();c['budget']=0;c['goals']={'coverage':1}
    a=run_experiment(CoverageModel(c),dict(population=4,generations=1))
    assert a['archive_ids']==[]
    assert replay(a)['status']=='PASS'


def test_independent_exact_reference_and_separate_diagnostics():
    from solsol.engine.diagnostics import exact_reference,local_check
    m=CoverageModel(tiny());report=exact_reference(m,max_bits=4)
    assert report['evaluations']==16
    assert sorted(r['F'] for r in report['front'])==sorted([
        [0.,0.,0.],[-.75,0.,6.],[-.75,-.75,9.],[-1.,0.,12.],[-1.,-.75,15.],[-1.,-1.,18.]])
    assert all(r['provenance']=='EXACT_REFERENCE_NOT_OPTIMIZER' for r in report['front'])
    full=m.evaluate([[1,1],[1,1]])
    d=local_check(m,full['X'],budget=32)
    assert d['evaluations']>0 and d['global_optimality']=='NOT_CERTIFIED'
    with pytest.raises(ValueError):exact_reference(m,max_bits=3)


def test_diagnostics_propagate_valid_x_evaluator_failures():
    from solsol.engine.diagnostics import exact_reference,local_check
    m=CoverageModel(tiny());evaluate=m.evaluate
    def broken(x):
        if np.asarray(x).sum()==1:raise ValueError('deliberate evaluator failure')
        return evaluate(x)
    m.evaluate=broken
    with pytest.raises(ValueError,match='deliberate evaluator failure'):exact_reference(m,max_bits=4)
    with pytest.raises(ValueError,match='deliberate evaluator failure'):local_check(m,[[1,1],[0,0]],budget=10)
