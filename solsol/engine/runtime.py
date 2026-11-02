"""Generic MOEA lifecycle, raw observation ledger, checkpoints and full replay."""
import copy
import hashlib
import importlib.metadata
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.core.problem import Problem
from pymoo.core.repair import Repair
from pymoo.operators.crossover.ux import UniformCrossover
from pymoo.operators.mutation.bitflip import BitflipMutation
from pymoo.util.ref_dirs import get_reference_directions

from .archive import archive_ids
from .contracts import digest
from .initializers import prepare
from .inventory import randomized_resource_repair
from .placement import PlacementCodec
from .placement_statistics import hamming_summary


def implementation_fingerprint():
    root=Path(__file__).resolve().parents[1]
    return digest({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.rglob('*.py'))})


def options(value=None):
    value={} if value is None else value
    if not isinstance(value,dict):raise ValueError('Optimizer must be an object')
    result=dict(algorithm='NSGA-II',initializer='random',seed=1,population=48,generations=30,
                preparation_budget=128,ref_partitions=4,wallclock_seconds=1200)
    if set(value)-set(result):raise ValueError('Unknown optimizer option')
    result.update(value)
    for key,lo,hi in [('seed',0,2**32-1),('population',4,2000),('generations',0,100000),
                       ('preparation_budget',0,10000),('ref_partitions',1,40),('wallclock_seconds',1,43200)]:
        v=result[key]
        if type(v) is not int or not lo<=v<=hi:raise ValueError('Invalid '+key)
    if result['population']*(result['generations']+1)>2000000:raise ValueError('Search row budget exceeds 2000000')
    if result['algorithm'] not in ('NSGA-II','NSGA-III'):raise ValueError('Unsupported algorithm')
    if result['initializer'] not in ('random','greedy','milp'):raise ValueError('Unsupported initializer')
    return result


def run_experiment(model,optimizer=None,progress=None,cancel=None):
    opt=options(optimizer);cancel=threading.Event() if cancel is None else cancel
    started=time.monotonic();rows=[];checkpoints=[];latest={};codec=PlacementCodec(model.space)
    if not codec.n_var:raise ValueError('No active installation slots')
    code_sha=implementation_fingerprint()
    run=dict(schema='SOLSOL_RUN_V1',run_id=str(uuid.uuid4()),model_id=model.model_id,
        evaluator_version=model.evaluator_version,experiment_contract_id=model.contract_id,
        implementation_sha256=code_sha,config=model.config,optimizer=opt,
        candidate_order=list(model.space.candidate_order),sensor_order=list(model.space.sensor_order),
        objective_ids=list(model.objective_ids),constraint_ids=list(model.constraint_ids),
        environment={k:importlib.metadata.version(k) for k in ['numpy','scipy','pymoo']},
        rows=rows,checkpoints=checkpoints,archive_ids=[],preparation=[],initialization={},
        counters=dict(preparation_evaluations=0,search_evaluations=0,replay_evaluations=0),
        status='preparing',elapsed_seconds=0.,scientific_optimum_certified=False)
    def publish(phase):
        run['status']=phase;run['elapsed_seconds']=time.monotonic()-started
        if progress:progress(dict(status=phase,generation=max(0,len(checkpoints)-1),
            nfe=len(rows),preparation_evaluations=len(run['preparation']),elapsed_seconds=run['elapsed_seconds']))
    publish('preparing')
    initial,ledger,info=prepare(model,opt,cancel)
    run['preparation']=ledger;run['initialization']=info
    run['counters']['preparation_evaluations']=len(ledger)
    if cancel.is_set():
        publish('stopped');return run
    rng=np.random.default_rng(np.random.SeedSequence([opt['seed'],91541]))
    class InstallationRepair(Repair):
        def _do(self,problem,z,**unused):
            return np.array([codec.encode(randomized_resource_repair(model.space,model.inventory_rule,
                codec.decode(v,validate_installation=False),rng)) for v in z],bool)
    class Objective(Problem):
        def __init__(self):
            super().__init__(n_var=codec.n_var,n_obj=len(model.objective_ids),n_ieq_constr=len(model.constraint_ids),xl=0,xu=1,vtype=bool)
        def _evaluate(self,z,out,*args,**kwargs):
            evaluated=[]
            for v in z:
                r=model.evaluate(codec.decode(v));r.update(id=len(rows),generation=len(checkpoints),
                    provenance='INITIAL_POPULATION' if not checkpoints else 'SEARCH_EVALUATION')
                if not np.isfinite(r['F']+r['G']).all():raise ValueError('Nonfinite model row')
                if len(r['F'])!=len(model.objective_ids) or len(r['G'])!=len(model.constraint_ids):raise ValueError('Model dimension mismatch')
                rows.append(r);latest[r['placement_hash']]=r['id'];evaluated.append(r)
            out['F']=np.array([r['F'] for r in evaluated]);out['G']=np.array([r['G'] for r in evaluated])
    args=dict(pop_size=opt['population'],sampling=np.array([codec.encode(x) for x in initial],bool),
        crossover=UniformCrossover(),mutation=BitflipMutation(),repair=InstallationRepair(),eliminate_duplicates=False)
    directions=None
    if opt['algorithm']=='NSGA-III':
        directions=get_reference_directions('das-dennis',len(model.objective_ids),n_partitions=opt['ref_partitions'])
        if len(directions)>opt['population']:raise ValueError('Reference directions exceed population; reduce partitions or increase population')
        algorithm=NSGA3(ref_dirs=directions,**args)
    else:algorithm=NSGA2(**args)
    run['solver_metadata']=dict(policy='generic-neutral-v1',repair_rng=[opt['seed'],91541],
        reference_directions=None if directions is None else directions.tolist(),
        initialization_rng=[opt['seed'],91401],raw_F_preserved=True)
    algorithm.setup(Objective(),seed=opt['seed'],termination=('n_gen',opt['generations']+1),verbose=False)
    publish('running')
    while algorithm.has_next():
        if cancel.is_set() or time.monotonic()-started>=opt['wallclock_seconds']:break
        algorithm.next()
        ids=[latest[model.space.placement_hash(codec.decode(z))] for z in algorithm.pop.get('X')]
        cp=dict(generation=len(checkpoints),row_stop=len(rows),population_ids=ids,
                archive_ids=archive_ids(rows,model.contract_id),nfe=len(rows))
        checkpoints.append(cp);run['archive_ids']=cp['archive_ids']
        run['counters']['search_evaluations']=len(rows);publish('running')
    run['archive_ids']=archive_ids(rows,model.contract_id)
    selected=[rows[i] for i in run['archive_ids']]
    run['quality']=dict(archive_layouts=len(selected),hamming=hamming_summary([r['X'] for r in selected]),
        objective_ranges={k:([min(r['named_metrics'][k] for r in rows),max(r['named_metrics'][k] for r in rows)] if rows else None)
                          for k in model.objective_ids},
        scope='observed optimizer evaluations only',global_optimality='NOT_CERTIFIED',
        human_understanding='NOT_MEASURED',field_validity='NOT_MEASURED')
    publish('stopped' if cancel.is_set() else 'time_limit' if algorithm.has_next() else 'completed')
    return run


def replay(run,model_factory=None):
    """Reevaluate every search/preparation X; no mutation of stored evidence."""
    try:
        if run['schema']!='SOLSOL_RUN_V1':raise ValueError('Unknown run schema')
        if run['implementation_sha256']!=implementation_fingerprint():raise ValueError('Implementation fingerprint mismatch')
        if model_factory is None:
            from solsol.models.coverage import CoverageModel
            model_factory=CoverageModel
        model=model_factory(run['config'])
        if (run['experiment_contract_id']!=model.contract_id or run['model_id']!=model.model_id or
            run['evaluator_version']!=model.evaluator_version):raise ValueError('Model contract mismatch')
        if (run['candidate_order']!=list(model.space.candidate_order) or run['sensor_order']!=list(model.space.sensor_order) or
            run['objective_ids']!=list(model.objective_ids) or run['constraint_ids']!=list(model.constraint_ids)):
            raise ValueError('Input/axis order mismatch')
        opt=options(run['optimizer'])
        if run['status'] not in ('completed','stopped','time_limit'):raise ValueError('Nonterminal run')
        if run['status']=='completed' and len(run['checkpoints'])!=opt['generations']+1:raise ValueError('Incomplete completed run')
        for i,row in enumerate(run['rows']):
            actual=model.evaluate(row['X'])
            if row['id']!=i or any(actual[k]!=row[k] for k in actual):raise ValueError('Raw row replay mismatch: '+str(i))
        for row in run['preparation']:
            actual=model.evaluate(row['row']['X'])
            if actual!=row['row']:raise ValueError('Preparation row replay mismatch')
        if run['counters']['search_evaluations']!=len(run['rows']) or run['counters']['preparation_evaluations']!=len(run['preparation']):
            raise ValueError('Evaluation counter mismatch')
        if archive_ids(run['rows'],model.contract_id)!=run['archive_ids']:raise ValueError('Cumulative archive mismatch')
        previous=0
        for gen,cp in enumerate(run['checkpoints']):
            stop=cp['row_stop']
            if cp['generation']!=gen or not previous<stop<=len(run['rows']) or cp['nfe']!=stop:raise ValueError('Checkpoint range mismatch')
            if cp['archive_ids']!=archive_ids(run['rows'][:stop],model.contract_id):raise ValueError('Checkpoint archive mismatch')
            if stop-previous!=opt['population'] or len(cp['population_ids'])!=opt['population']:raise ValueError('Checkpoint population size mismatch')
            for r in run['rows'][previous:stop]:
                if r['generation']!=gen or r['provenance']!=('INITIAL_POPULATION' if gen==0 else 'SEARCH_EVALUATION'):
                    raise ValueError('Row generation/provenance mismatch')
            if any(type(i) is not int or not 0<=i<stop for i in cp['population_ids']):raise ValueError('Checkpoint population mismatch')
            previous=stop
        if run['rows'] and previous!=len(run['rows']):raise ValueError('Uncheckpointed rows')
        return dict(status='PASS',checked_rows=len(run['rows']),checked_preparation_rows=len(run['preparation']),
                    experiment_contract_id=model.contract_id,global_optimality='NOT_CERTIFIED')
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        return dict(status='FAIL',error=str(exc),checked_rows=0)
