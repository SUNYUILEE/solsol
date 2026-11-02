"""Independent-of-search evaluations; never merged into optimizer evidence."""
import itertools
import numpy as np
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting

from .placement import PlacementCodec


def dominates(a,b):
    return all(u<=v for u,v in zip(a['F'],b['F'])) and any(u<v for u,v in zip(a['F'],b['F']))


def local_check(model,x,budget=512):
    if type(budget) is not int or not 1<=budget<=10000:raise ValueError('Local diagnostic budget must be 1..10000')
    x=model.space.validate(x);baseline=model.evaluate(x);rows=[];attempts=0;seen=set()
    selected=np.argwhere(x);free=np.argwhere(model.space.allowed & (x==0))
    def candidates():
        for i,j in selected:
            y=x.copy();y[i,j]=0;yield 'one-delete',y
        for i,j in selected:
            for a,b in free:
                y=x.copy();y[i,j]=0;y[a,b]=1;yield 'one-swap',y
    exhausted=True
    for kind,y in candidates():
        if len(rows)>=budget:exhausted=False;break
        attempts+=1;key=y.tobytes()
        if key in seen:continue
        seen.add(key)
        try:model.space.validate(y)
        except ValueError:continue
        row=model.evaluate(y)
        row.update(diagnostic_id=len(rows),kind=kind,provenance='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER')
        row['dominates_baseline']=row['feasible'] and dominates(row,baseline)
        row['same_performance_cheaper']=(row['feasible'] and row['cost']<baseline['cost'] and
            all(row['named_metrics'][k]==v for k,v in baseline['named_metrics'].items() if k!='cost'))
        rows.append(row)
    return dict(schema='SOLSOL_LOCAL_CHECK_V1',experiment_contract_id=model.contract_id,baseline=baseline,
        rows=rows,evaluations=1+len(rows),attempts=attempts,neighborhood_exhausted=exhausted,
        dominating_witnesses=[r['diagnostic_id'] for r in rows if r['dominates_baseline']],
        global_optimality='NOT_CERTIFIED')


def exact_reference(model,max_bits=16):
    codec=PlacementCodec(model.space)
    if type(max_bits) is not int or not 0<=max_bits<=20 or codec.n_var>max_bits:
        raise ValueError('Exact reference is bounded to explicitly approved <=20 active bits')
    rows=[];evaluations=0
    for bits in itertools.product([0,1],repeat=codec.n_var):
        try:x=codec.decode(bits)
        except ValueError:continue
        row=model.evaluate(x)
        evaluations+=1
        if row['feasible']:
            row.update(reference_id=len(rows),provenance='EXACT_REFERENCE_NOT_OPTIMIZER');rows.append(row)
    indices=NonDominatedSorting().do(np.asarray([r['F'] for r in rows]),only_non_dominated_front=True) if rows else []
    return dict(schema='SOLSOL_EXACT_REFERENCE_V1',experiment_contract_id=model.contract_id,
        active_bits=codec.n_var,encoded_layouts=2**codec.n_var,evaluations=evaluations,
        feasible_layouts=len(rows),front=[rows[int(i)] for i in indices],
        scope='Exact only for this finite, frozen model and candidate/point discretization',
        larger_problem_global_optimality='NOT_CERTIFIED')
