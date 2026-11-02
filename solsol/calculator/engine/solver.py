"""Solver policies own variation, never run identity, archive, or result storage."""
import time
import numpy as np
from pymoo.core.population import Population
from pymoo.core.problem import Problem,ElementwiseProblem
from pymoo.core.callback import Callback
from pymoo.core.repair import Repair
from pymoo.algorithms.moo.nsga3 import NSGA3,ReferenceDirectionSurvival
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.crossover.pntx import TwoPointCrossover
from pymoo.operators.crossover.ux import UniformCrossover
from pymoo.operators.mutation.bitflip import BitflipMutation
from pymoo.operators.sampling.rnd import BinaryRandomSampling
from pymoo.operators.selection.tournament import TournamentSelection
from pymoo.util.ref_dirs import get_reference_directions
from pymoo.optimize import minimize
from .store import digest


def reference_directions(session,partitions,objectives=None):
    m=session.problem.n_obj if objectives is None else objectives
    if m<2:raise ValueError('UNSUPPORTED_INPUT: MOO policy requires at least two objectives')
    vectors=get_reference_directions('das-dennis',m,n_partitions=partitions)
    session.solver_metadata['reference_directions']=dict(method='das-dennis',objectives=m,partitions=partitions,count=len(vectors),vectors=vectors.tolist(),sha256=digest(vectors.tolist()))
    return vectors


class EOIRModelProxy:
    """Record auxiliary scientific evaluations without perturbing model or RNG."""
    def __init__(self,session,phase):
        self.session=session;self.phase=phase;self.calls=0
    def __getattr__(self,name):return getattr(self.session.problem.model,name)
    @property
    def __model_service_reference__(self):return self.session.problem.model
    def _rows(self,x):
        if time.monotonic()-self.session.started>=self.session.wallclock_limit:raise TimeoutError('WALLCLOCK_BUDGET')
        a=np.asarray(x);batch=a[None] if a.ndim==2 else a
        rows=self.session.problem.evaluate_physical(batch)
        ledger=self.session.solver_metadata.setdefault('auxiliary_evaluations',[])
        for row in rows:
            ledger.append(dict(auxiliary_id=len(ledger),phase=self.phase,row=row))
        self.calls+=len(rows)
        self.session.counters[self.phase+'_evaluations']+=len(rows)
        return rows
    def point(self,x):return self._rows(x)[0]
    def metrics(self,x):
        rows=self._rows(x)
        nominal=np.asarray([r['performance'] for r in rows]);quality=np.asarray([r['quality'] for r in rows])
        return (nominal[0],quality[0]) if np.asarray(x).ndim==2 else (nominal,quality)
    def evaluate(self,x):
        rows=self._rows(x)
        values=tuple(np.asarray([r[k] for r in rows]) for k in ('legacy_F','G','counts'))
        return tuple(v[0] for v in values) if np.asarray(x).ndim==2 else values


def solve_eoir(session):
    """Extracted EOIR legacy policy: unchanged RNG streams and operator ordering."""
    from live_model import PRESETS,FULL_AREA_TRADEOFF_CONTRACT,LAYERED_CONTRACT
    from live_seeding import prepare
    from search import parent,ranks,cross,mutate,NDS
    from live_engine import local_mutate
    from live_target_delete import refine
    from model import mask
    from model_derived_api import TARGETS
    b=session.problem.model;cfg=session.config;p=PRESETS[cfg['h']]
    if time.monotonic()-session.started>=session.wallclock_limit:return 'time_limit'
    rng=np.random.default_rng(cfg['seed']+100000);refine_rng=np.random.default_rng(cfg['seed']+700000)
    session.set_phase('preparing')
    prep_model=EOIRModelProxy(session,'preparation');refine_model=EOIRModelProxy(session,'refinement')
    initial,session.initialization=prepare(prep_model,cfg,p,session.cancel,solver_trace=session.solver_trace)
    if session.cancel.is_set():return 'cancelled'
    if time.monotonic()-session.started>=session.wallclock_limit:return 'time_limit'
    if prep_model.calls!=session.initialization['preparation_evaluations']:
        raise ValueError('Preparation evaluator ledger mismatch')
    session.solver_metadata.update(policy='legacy_eoir_v1',initial_X=initial.astype(int).tolist(),initial_X_sha256=digest(initial.astype(int).tolist()),rng_streams=[cfg['seed']+100000,cfg['seed']+700000])
    survival=ReferenceDirectionSurvival(reference_directions(session,cfg['h']))
    problem=Problem(n_var=session.problem.n_var,n_obj=session.problem.n_obj,n_ieq_constr=session.problem.n_constr)
    session.set_phase('running')
    def evaluate(xs,gen):
        rows=session.evaluate(xs,gen,'INITIAL_POPULATION' if gen==0 else 'SEARCH_EVALUATION')
        return Population.new(X=np.asarray(xs).reshape(len(xs),session.problem.n_var),F=np.array([r['F'] for r in rows]),G=np.array([r['G'] for r in rows]),eid=np.array([r['id'] for r in rows]))
    pop=evaluate(initial,0);pop=survival.do(problem,pop,n_survive=p,random_state=rng);best=None
    def checkpoint(gen):
        nonlocal best
        ids=pop.get('eid').astype(int);f=pop.get('F');g=pop.get('G')
        feasible=np.flatnonzero(np.all(g<=0,axis=1));front=feasible[NDS.do(f[feasible],only_non_dominated_front=True)] if len(feasible) else np.array([],int)
        nominal=np.asarray([session.rows[int(i)]['performance'] for i in ids])
        good=np.flatnonzero(np.all(nominal>=TARGETS,axis=1)&np.all(g<=0,axis=1)) if cfg['objective_contract'] in (FULL_AREA_TRADEOFF_CONTRACT,LAYERED_CONTRACT) else feasible
        qualified=np.intersect1d(front,good)
        if len(qualified):rep=int(min(qualified,key=lambda j:(f[j,2],f[j,0]+f[j,1])));cost=round(session.rows[int(ids[rep])]['cost']);best=cost if best is None else min(best,cost)
        elif len(front):rep=int(min(front,key=lambda j:(f[j,0]+f[j,1],f[j,2])));cost=None
        else:rep=int(min(range(len(ids)),key=lambda j:(np.maximum(g[j],0).sum(),f[j,2])));cost=None
        nominal,quality=session.rows[int(ids[rep])]['performance'],session.rows[int(ids[rep])]['quality']
        session.checkpoint(pop.get('X').reshape(-1,b.n,2),gen,dict(population_ids=ids.tolist(),front_ids=ids[front].tolist(),representative_id=int(ids[rep]),qualified_count=len(good),current_cost=cost,best_cost=best,performance=np.asarray(nominal).tolist(),objective_performance=np.asarray(quality).tolist(),cost=round(session.rows[int(ids[rep])]['cost'])))
    checkpoint(0)
    for gen in range(1,cfg['generations']+1):
        if session.cancel.is_set():return 'cancelled'
        if time.monotonic()-session.started>=session.wallclock_limit:return 'time_limit'
        rank=ranks(pop);children=[]
        for j in range(p):
            ia=parent(pop,rank,rng);ib=parent(pop,rank,rng);a=pop[ia].X.reshape(b.n,2).astype(np.uint8);bb=pop[ib].X.reshape(b.n,2).astype(np.uint8)
            if cfg['design'] in ('A','B'):
                crossed=cross(a,bb,rng,'switch' if cfg['design']=='A' else 'site');x,flips=mutate(crossed,rng,1.5);action='bit_flip';edits=[]
            else:
                crossed=np.where(rng.random((b.n,1))<.5,a,bb).astype(np.uint8) if rng.random()<.2 else a.copy()
                x,action,edits=local_mutate(crossed,b.installation_allowed,rng);flips=[]
            before=x.copy();cleared=np.flatnonzero((x*(1-b.installation_allowed)).ravel()).tolist();x=b.repair(x,rng)
            resource_edits=[[int(k),int(x.flat[k])] for k in np.flatnonzero((before!=x).ravel())]
            refinement=None
            if cfg.get('refinement','off')=='target_delete_v1':
                before_calls=refine_model.calls
                x,refinement=refine(x,refine_model,refine_rng)
                refinement['actual_evaluations']=refine_model.calls-before_calls
                if refinement['actual_evaluations']!=1+refinement['candidate_checks']:
                    raise ValueError('Refinement evaluator ledger mismatch')
            session.events.append(dict(generation=gen,parent_ids=[int(pop[ia].get('eid')),int(pop[ib].get('eid'))],crossed_mask=mask(crossed).tolist(),flips=flips,action=action,edits=edits,repair_cleared=cleared,resource_repair_edits=resource_edits,refinement=refinement,child_id=len(session.rows)+j))
            children.append(x)
        offspring=evaluate(np.asarray(children),gen)
        pop=survival.do(problem,Population.merge(pop,offspring),n_survive=p,random_state=rng);checkpoint(gen)
    return 'cancelled' if session.cancel.is_set() else 'completed'


def solve_pymoo(session):
    """Generic dimensional solver with named legacy sampling/repair policies."""
    cp=session.problem;opt=session.optimizer;n=cp.model.n;s=len(cp.sensor_order);p=opt['population'];policy=session.policy
    algorithm=opt['algorithm'];seed=opt['seed'];count=opt.get('checkpoints',opt.get('generations',1)+1)
    from .objective_activity import projection
    axes=projection(cp) if policy=='generic_v1' else dict(effective_indices=list(range(cp.n_obj)),excluded=[])
    active=axes['effective_indices'];session.solver_metadata['objective_projection']=axes
    goals=cp.config.get('_research',{}).get('goals') or {}
    session.solver_metadata['constraint_layers']=dict(hard='inventory / active-slot domain / Model G',performance_thresholds=goals,objectives_independent_of_thresholds=True)
    repair_rng=np.random.default_rng(np.random.SeedSequence([seed,91541]))
    session.set_phase('preparing');repair=None;sample=None;initial=None;kwargs={}
    if policy in ('legacy_rf_v2','legacy_rf_v3'):
        if policy=='legacy_rf_v3':
            from rf_common_v3_runtime import sample as sample_fn,CountRepair,reference_partitions,SAMPLER,VARIATION
            sample=lambda rng:sample_fn(rng,p,n,session.config);repair=CountRepair(session.config);h=reference_partitions(p)
        else:
            from rf_common_runtime import sample as sample_fn,CountRepair,SAMPLER,VARIATION
            sample=lambda rng:sample_fn(rng,p,n,session.config['hardware_limit']);repair=CountRepair(session.config['hardware_limit']);h=7
        initial=sample(np.random.default_rng(seed));kwargs=dict(crossover=TwoPointCrossover(prob=.9),mutation=BitflipMutation(prob=1.,prob_var=1/cp.n_var),repair=repair)
        session.solver_metadata.update(sampling=SAMPLER,variation=VARIATION,initial_X=initial.astype(int).tolist(),initial_X_sha256=digest(initial.astype(int).tolist()))
    else:
        h=5 if policy=='legacy_rf_v1' else opt.get('ref_partitions',1)
        kwargs=dict(crossover=UniformCrossover() if policy=='generic_v1' and cp.n_var<3 else TwoPointCrossover(),mutation=BitflipMutation())
        if policy=='generic_v1':
            if cp.n_var==0:
                raise ValueError('UNSUPPORTED_INPUT: generic search requires at least one enabled installation slot')
            class InstallationRepair(Repair):
                def _do(self,problem,Z,**unused):
                    return np.asarray([cp.codec.encode(generic_physical(z,repair_rng)) for z in Z],dtype=bool)
            kwargs['repair']=InstallationRepair()
            session.solver_metadata['installation_repair']=dict(version='seeded-resource-repair-v2',
                co_location=cp.space.co_location,rule='random tie breaking among selected and free allowed slots; valid placements unchanged',
                disabled_slots='excluded by active-slot codec',rng_stream=[seed,91541],rng_consumption='invalid offspring only; evaluation and checkpoint decode consume none')
    dirs=reference_directions(session,h,len(active)) if algorithm=='NSGA-III' else None
    if policy=='generic_v1' and dirs is not None and len(dirs)>p:raise ValueError('Reference directions exceed declared population')
    def generic_physical(z,rng=None):
        x=cp.codec.decode(z,validate_installation=False)
        x=x*cp.space.allowed
        if rng is not None:
            from .initialization import randomized_resource_repair
            return randomized_resource_repair(cp.space,getattr(cp.bundle,'inventory_rule',None),x,rng)
        if not cp.space.co_location:
            for site in np.flatnonzero(x.sum(axis=1)>1):
                installed=np.flatnonzero(x[site]);x[site,installed[1:]]=0
        # Bundle declares counts; generic policy does not name sensor combinations.
        rule=getattr(cp.bundle,'inventory_rule',None)
        if rule and ('lower' in rule or 'upper' in rule):
            from .initialization import resource_bounds
            lower,upper=resource_bounds(cp.space,rule);counts=x.sum(0)
            if not np.all((counts>=lower)&(counts<=upper)):
                raise ValueError('RESOURCE_REPAIR_REQUIRED_BEFORE_EVALUATION')
            return cp.space.validate(x)
        if rule and rule['mode']!='off':
            counts=x.sum(0);limits=np.asarray(rule['limits'])
            if np.all(counts==limits if rule['mode']=='all' else counts<=limits):return cp.space.validate(x)
            if rule['mode']=='all' and not cp.space.co_location:
                from .initialization import repair_all
                return repair_all(cp.space,rule,x)
            for j,limit in enumerate(rule['limits']):
                active=np.flatnonzero(x[:,j])
                x[active[int(limit):],j]=0
                if rule['mode']=='all':
                    free=np.flatnonzero(cp.space.allowed[:,j] & (x[:,j]==0))
                    need=int(limit)-int(x[:,j].sum())
                    x[free[:need],j]=1
        return cp.space.validate(x)
    def physical(z):
        # Existing bundles use exactly their original full row-major representation.
        if policy!='generic_v1':return np.asarray(z).reshape(n,s)
        return generic_physical(z)
    if policy=='generic_v1':
        method=opt.get('initializer','random')
        from .common_initialization import prepare
        initial,session.initialization=prepare(session,min(session.started+session.wallclock_limit,time.monotonic()+opt['initialization_seconds']))
        if session.cancel.is_set():return 'cancelled'
        actual=np.asarray([physical(z) for z in initial]).astype(int).tolist()
        if digest(actual)!=session.initialization['initial_X_sha256']:raise ValueError('INITIALIZER_REPAIR_CHANGED_SEEDS')
        session.solver_metadata.update(initial_X=actual,initial_X_sha256=digest(actual))
        session.solver_metadata['installation_repair']['all_no_colocation']='augmenting-assignment-v1'
    class Objective(Problem):
        def __init__(self):super().__init__(n_var=cp.n_var,n_obj=len(active),n_ieq_constr=cp.n_constr+len(goals),xl=0,xu=1,vtype=bool)
        def _evaluate(self,x,out,*args,**kwargs):
            if time.monotonic()-session.started>session.wallclock_limit:raise TimeoutError('WALLCLOCK_BUDGET')
            gen=len(session.checkpoints)
            origin='INITIAL_POPULATION' if gen==0 else 'SEARCH_EVALUATION'
            # Evaluation has no solver RNG side effects. Preserve population order
            # while crossing the model API once per batch, not once per individual.
            rows=session.evaluate(np.asarray([physical(z) for z in x]),gen,origin)
            for excluded in axes['excluded']:
                if any(r['cost']!=excluded['cost'] for r in rows):raise ValueError('CONSTANT_COST_CONTRACT_MISMATCH')
            out['F']=np.asarray([r['F'] for r in rows])[:,active]
            out['G']=np.asarray([r['G']+[float(target)-r['coverage_metrics'][key] for key,target in goals.items()] for r in rows]).reshape(len(rows),cp.n_constr+len(goals))
    class Progress(Callback):
        def notify(self,a):
            session.checkpoint(np.asarray([physical(z) for z in a.pop.get('X')]),len(session.checkpoints))
            if session.cancel.is_set():a.termination.force_termination=True
    session.set_phase('running')
    if algorithm=='random':
        rng=np.random.default_rng(np.random.SeedSequence([seed,1])) if sample else np.random.default_rng(seed)
        for gen in range(count):
            if time.monotonic()-session.started>session.wallclock_limit:return 'time_limit'
            if sample:z=initial if gen==0 else sample(rng)
            elif gen==0 and initial is not None:z=initial
            else:z=rng.integers(0,2,(p,cp.n_var))
            x=np.asarray([generic_physical(v,repair_rng) if policy=='generic_v1' else physical(v) for v in z]);session.evaluate(x,gen,'INITIAL_POPULATION' if gen==0 else 'RANDOM_SEARCH');session.checkpoint(x,gen)
            if session.cancel.is_set():break
    else:
        from seeded_selection import seeded_cv_tournament
        kw=dict(pop_size=p,sampling=initial.copy() if initial is not None else BinaryRandomSampling(),eliminate_duplicates=False,**kwargs)
        a=NSGA2(**kw) if algorithm=='NSGA-II' else NSGA3(ref_dirs=dirs,selection=TournamentSelection(func_comp=seeded_cv_tournament),**kw)
        minimize(Objective(),a,('n_gen',count),seed=seed,callback=Progress(),verbose=False)
    return 'cancelled' if session.cancel.is_set() else 'completed'


POLICIES={'legacy_eoir_v1':solve_eoir,'legacy_rf_v1':solve_pymoo,'legacy_rf_v2':solve_pymoo,'legacy_rf_v3':solve_pymoo,'generic_v1':solve_pymoo}

def solve(session):
    if session.policy.startswith('legacy_') and set(session.problem.space.enabled_sensor_ids)!=set(session.problem.sensor_order):
        raise ValueError('UNSUPPORTED_INPUT: legacy solver policy requires all registered sensor types enabled; selected-type solver policy is not exposed in stage2')
    return POLICIES[session.policy](session)
