"""Calculator-owned binary initializers. The public Model is the only F/G oracle.

MILP solves a bounded local linear proposal, NOT the original nonlinear model.
Its solver bound/gap refers only to the recorded approximation. Every seed is
checked by the original Model and reevaluated as an initial-population row.
"""
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from .initialization import METHODS as BASE_METHODS, assign, resource_bounds
from .store import digest

LEGACY_VERSION = 'calculator-common-initialization-v1'
VERSION = 'calculator-common-initialization-v2'
VERSIONS = (LEGACY_VERSION, VERSION)
DEFAULT_BUDGET = 128
METHODS = (*BASE_METHODS, 'saved')


def seed_admission(method, version):
    if method=='saved':return 'SAVED_EXPLICIT_LAYOUT; MODEL_G_AND_GOALS_REPORTED_NOT_ADMISSION'
    if method=='random':return 'NO_PROPOSAL_SEEDS'
    return ('MODEL_G_AND_INSTALLATION; AREA_GOALS_ARE_NOT_SEED_ADMISSION' if version==VERSION
            else 'HISTORICAL_MODEL_G_AND_COVERAGE_GOALS')


def random_population(cp, population, seed):
    rng = np.random.default_rng(np.random.SeedSequence([seed, 91401]))
    lower, limits = resource_bounds(cp.space, getattr(cp.bundle, 'inventory_rule', None))
    exact = bool(np.all(lower == limits))
    result = []
    for _ in range(population):
        counts = limits if exact else np.asarray([rng.integers(lo, v + 1) for lo,v in zip(lower,limits)])
        orders = [rng.permutation(np.flatnonzero(cp.space.allowed[:, j])) for j in range(cp.space.shape[1])]
        result.append(assign(cp.space, counts, orders, exact=exact,minimum=lower))
    return np.asarray(result)


def prepare(session, deadline):
    cp = session.problem; opt = session.optimizer; method = opt.get('initializer', 'random')
    if method not in METHODS: raise ValueError('Unknown initializer')
    # Unversioned historical requests retain their original admission policy.
    version = opt.get('initialization_version', LEGACY_VERSION)
    if version not in VERSIONS: raise ValueError('Unknown initialization version')
    model_g_admission = version == VERSION
    started = time.monotonic(); budget = opt.get('initialization_evaluations', DEFAULT_BUDGET)
    base = random_population(cp, opt['population'], opt['seed'])
    info = dict(method=method, version=version, owner='CALCULATOR', status='PREPARING',
        population=len(base), preparation_budget=budget, preparation_evaluations=0,
        preparation_evaluation_attempts=0, preparation_evaluations_uncertain=False,
        seed_count=0, sources=[], pareto_front_certified=False, scientific_optimum_certified=False,
        approximation='LOCAL_LINEAR_F_G_PROPOSAL_NOT_EXACT_MODEL' if method=='milp' else None,
        deadline_semantics='cooperative between Model batches; MILP solver time bounded; HTTP may finish later',
        fallback_population='shared seeded resource-feasible random; not necessarily Model-G feasible')
    session.initialization = info
    trace = session.solver_metadata.setdefault('initializer_trace', [])
    ledger = session.solver_metadata.setdefault('auxiliary_evaluations', [])
    cache = {}; accepted = []; calls = 0
    count_lower, limits = resource_bounds(cp.space, getattr(cp.bundle, 'inventory_rule', None))
    exact = bool(np.all(count_lower == limits))
    rng = np.random.default_rng(np.random.SeedSequence([opt['seed'], 91402]))
    research = getattr(cp, 'calculator_configuration', cp.config.get('_research', {}))
    coverage_goals = research.get('goals') if research.get('goal_definition') == 'EVALUATION_POINT_COVERAGE_V1' else None
    tolerance = cp.feasibility_tolerance

    def remaining(): return not session.cancel.is_set() and time.monotonic() < deadline and calls < budget
    def values(row):
        f = np.asarray(row['F'], float); g = list(row['G'])
        for key, goal in (coverage_goals or {}).items():
            g.append((goal - row['coverage_metrics'][key]) / 100.)
        g = np.asarray(g, float)
        if f.shape != (cp.n_obj,) or not np.isfinite(f).all() or not np.isfinite(g).all():
            raise ValueError('INITIALIZER_NONFINITE_OR_WRONG_MODEL_ROW')
        return f, g
    def evaluate(xs, phase):
        nonlocal calls
        unique = []
        for x in xs:
            key = digest(np.asarray(x).astype(int).tolist())
            if key not in cache and not any(k == key for k, _ in unique): unique.append((key, x))
        unique = unique[:max(0, budget-calls)] if remaining() else []
        if unique:
            info['preparation_evaluation_attempts'] += len(unique)
            info['preparation_evaluations_uncertain'] = True
            rows = cp.evaluate_physical([x for _, x in unique], validate_installation=True)
            if len(rows) != len(unique): raise ValueError('INITIALIZER_BATCH_LENGTH')
            for (key, x), row in zip(unique, rows):
                if not np.array_equal(np.asarray(row['X']), x): raise ValueError('INITIALIZER_X_BINDING')
                values(row)
                aid = len(ledger); ledger.append(dict(auxiliary_id=aid, phase='preparation', purpose=phase, row=row))
                cache[key] = (row, aid)
            calls += len(rows); session.counters['preparation_evaluations'] += len(rows)
            info.update(preparation_evaluations=calls, preparation_evaluations_uncertain=False)
        return [cache.get(digest(np.asarray(x).astype(int).tolist())) for x in xs]
    def feasible(row): return bool(np.all(values(row)[1] <= tolerance))
    def model_feasible(row):
        g=np.asarray(row['G'],float)
        if g.shape!=(cp.n_constr,) or not np.isfinite(g).all():
            raise ValueError('INITIALIZER_NONFINITE_OR_WRONG_MODEL_G')
        return bool(np.all(g<=tolerance))
    def resource_ok(x):
        counts=x.sum(axis=0)
        return bool(np.all((counts>=count_lower)&(counts<=limits)))
    def remember(pair):
        if pair and (model_feasible(pair[0]) if model_g_admission else feasible(pair[0])) and resource_ok(np.asarray(pair[0]['X'])) and pair[1] not in [v[1] for v in accepted]: accepted.append(pair)
    def score(row, weight, scale):
        f, g = values(row)
        return (float(np.maximum(g-tolerance, 0).sum()), float(np.dot(weight, f/scale)))
    def neighbors(x, slots):
        result=[]
        for flat in slots:
            y=x.copy();y.flat[flat]=1-y.flat[flat]
            # Installation validation is stricter than inventory G validation.
            if cp.space.co_location or np.all(y.sum(axis=1)<=1): result.append((int(flat), y))
        return result

    try:
        if method == 'saved':
            source=getattr(cp,'saved_initialization',None)
            if source is None:raise ValueError('저장 초기 배치의 원본 확인이 필요합니다.')
            pair=evaluate([np.asarray(source['X'],np.uint8)],'saved_layout_reevaluation')[0]
            if pair is None:raise ValueError('저장 초기 배치를 재평가하지 못했습니다. 준비 시간을 늘려 다시 실행하세요.')
            row,aid=pair
            base[0]=np.asarray(row['X'],np.uint8)
            info['sources'].append(dict(index=0,method=method,auxiliary_id=aid,**{k:v for k,v in source.items() if k!='X'},
                new_model_feasible=bool(np.all(np.asarray(row['G'])<=tolerance)),new_goal_qualified=feasible(row),new_cost=row['cost']))
        elif method != 'random':
            center = base[0].copy() if np.any(count_lower) else np.zeros(cp.space.shape, np.uint8)
            current = evaluate([center], 'anchor')[0]
            for step in range(16):
                if current is None or not remaining(): break
                weight = np.ones(cp.n_obj)/cp.n_obj if step == 0 else np.eye(cp.n_obj)[(step-1)%cp.n_obj]
                slots = np.flatnonzero(cp.space.allowed.ravel())
                if len(slots)>32: slots=np.sort(rng.choice(slots,32,replace=False))
                candidates = neighbors(center, slots)
                pairs = evaluate([x for _,x in candidates], 'local_calibration')
                known = [(flat,x,pair) for (flat,x),pair in zip(candidates,pairs) if pair]
                if not known: break
                f0,g0=values(current[0]); fs=np.asarray([values(v[2][0])[0] for v in known])
                scale=np.maximum(np.ptp(np.vstack([f0,fs]),axis=0),1e-9)
                if method == 'greedy':
                    options=[v for v in known if resource_ok(v[1])]
                    # Exact inventory requires exchanges, not infeasible single additions.
                    if np.any(count_lower):
                        exchanges=[]
                        for j in range(cp.space.shape[1]):
                            for old in np.flatnonzero(center[:,j]):
                                for new in np.flatnonzero(cp.space.allowed[:,j] & (center[:,j]==0)):
                                    y=center.copy();y[old,j]=0;y[new,j]=1
                                    if cp.space.co_location or np.all(y.sum(axis=1)<=1): exchanges.append(y)
                                    if len(exchanges)>=32: break
                                if len(exchanges)>=32: break
                            if len(exchanges)>=32: break
                        options += [(None,np.asarray(p[0]['X'],np.uint8),p) for p in evaluate(exchanges,'greedy_exchange') if p and resource_ok(np.asarray(p[0]['X']))]
                    if not options: break
                    _,proposal,pair=min(options,key=lambda v:score(v[2][0],weight,scale))
                    improved=score(pair[0],weight,scale)<score(current[0],weight,scale)
                    trace.append(dict(method=method,step=step,weight=weight.tolist(),scale=scale.tolist(),
                        selected_auxiliary_id=pair[1],improved=improved))
                    remember(pair)
                    if improved: center=proposal;current=pair
                    else:
                        # Change scalarization and anchor deterministically on a stall.
                        center=base[(step+1)%len(base)].copy();current=evaluate([center],'restart_anchor')[0]
                else:
                    if not remaining(): break
                    k=len(known); q=len(g0)
                    df=np.column_stack([values(v[2][0])[0]-f0 for v in known])
                    dg=np.column_stack([values(v[2][0])[1]-g0 for v in known])
                    slots=np.asarray([v[0] for v in known]); signs=1-2*center.ravel()[slots].astype(int)
                    # d=1 flips an installation. Continuous slacks allow a local
                    # proposal even when nonlinear quality goals are unattainable.
                    c=np.r_[weight @ (df/scale[:,None]), np.full(q,1e4)]
                    rows=[]; lower=[]; upper=[]
                    for j in range(cp.space.shape[1]):
                        a=np.zeros(k+q);a[:k]=signs*(slots%cp.space.shape[1]==j)
                        rows.append(a);upper.append(float(limits[j]-center[:,j].sum()))
                        lower.append(float(count_lower[j]-center[:,j].sum()))
                    if not cp.space.co_location:
                        for i in range(cp.space.shape[0]):
                            a=np.zeros(k+q);a[:k]=signs*(slots//cp.space.shape[1]==i)
                            rows.append(a);lower.append(-np.inf);upper.append(float(1-center[i].sum()))
                    a=np.zeros(k+q);a[:k]=1;rows.append(a);lower.append(1);upper.append(min(4,k))
                    for j in range(q):
                        a=np.r_[dg[j],np.zeros(q)];a[k+j]=-1
                        rows.append(a);lower.append(-np.inf);upper.append(float(tolerance-g0[j]))
                    matrix=np.asarray(rows); ub=np.r_[np.ones(k),np.full(q,np.inf)]
                    limit=max(.001,min(2.,deadline-time.monotonic()))
                    result=milp(c,integrality=np.r_[np.ones(k),np.zeros(q)],bounds=Bounds(np.zeros(k+q),ub),
                        constraints=LinearConstraint(matrix,lower,upper),options={'time_limit':limit,'mip_rel_gap':0.})
                    entry=dict(method=method,step=step,approximation=info['approximation'],anchor_auxiliary_id=current[1],
                        calibration_auxiliary_ids=[v[2][1] for v in known],slots=slots.tolist(),weight=weight.tolist(),scale=scale.tolist(),
                        objective=c.tolist(),matrix=matrix.tolist(),lower=[None if not np.isfinite(v) else v for v in lower],
                        upper=upper,status=int(result.status),message=str(result.message),bound_scope='LOCAL_LINEAR_APPROXIMATION_ONLY',
                        incumbent=None if result.x is None else result.x.tolist())
                    trace.append(entry)
                    if result.status not in (0,1,2): raise ValueError('INITIALIZER_MILP_SOLVER_ERROR:'+str(result.status))
                    if result.x is None:
                        center=base[(step+1)%len(base)].copy();current=evaluate([center],'restart_anchor')[0];continue
                    v=np.asarray(result.x);rounded=v.copy();rounded[:k]=np.rint(v[:k])
                    if not np.isfinite(v).all() or np.max(np.abs(v[:k]-rounded[:k]))>1e-6 or np.any(rounded< -1e-7) or np.any(rounded>ub+1e-7): raise ValueError('INITIALIZER_MILP_INVALID_INCUMBENT')
                    av=matrix@rounded
                    if np.any(av<np.asarray(lower)-1e-7) or np.any(av>np.asarray(upper)+1e-7): raise ValueError('INITIALIZER_MILP_CONSTRAINT_VIOLATION')
                    proposal=center.copy();chosen=slots[rounded[:k]>0.5];proposal.flat[chosen]=1-proposal.flat[chosen]
                    cp.space.validate(proposal)
                    if not resource_ok(proposal): raise ValueError('INITIALIZER_MILP_RESOURCE_VIOLATION')
                    pair=evaluate([proposal],'milp_proposal')[0]
                    entry['reevaluated_auxiliary_id']=pair[1] if pair else None
                    entry['accepted_by_original_model']=bool(pair and (model_feasible(pair[0]) if model_g_admission else feasible(pair[0])))
                    if model_g_admission:
                        entry['goal_qualified']=bool(pair and feasible(pair[0]))
                        entry['seed_admission_version']=version
                    remember(pair)
                    if pair and score(pair[0],weight,scale)<score(current[0],weight,scale): center=proposal;current=pair
                    else: center=base[(step+1)%len(base)].copy();current=evaluate([center],'restart_anchor')[0]
            for index,(row,aid) in enumerate(accepted[:max(1,len(base)//2)]):
                base[index]=np.asarray(row['X'],np.uint8)
                info['sources'].append(dict(index=index,method=method,auxiliary_id=aid))
                if model_g_admission:
                    info['sources'][-1].update(model_feasible=model_feasible(row),goal_qualified=feasible(row),cost=row['cost'])
        info.update(status='PREPARED',seed_count=len(info['sources']),
            outcome='RANDOM_POPULATION' if method=='random' else 'MODEL_VALIDATED_SEEDS' if info['sources'] else 'NO_MODEL_FEASIBLE_SEED_WITHIN_BUDGET',
            initial_X_sha256=digest(base.astype(int).tolist()))
        if model_g_admission:
            prepared=[row for row,_ in cache.values()]
            info.update(seed_admission=seed_admission(method,version),
                proposal_guidance='UNCHANGED_MODEL_G_PLUS_COVERAGE_DEFICITS',
                prepared_model_feasible_count=sum(model_feasible(row) for row in prepared),
                prepared_goal_qualified_count=sum(feasible(row) for row in prepared),
                admitted_goal_qualified_count=sum(feasible(ledger[s['auxiliary_id']]['row']) for s in info['sources']),
                seed_candidate_scope='SAVED_EXPLICIT_LAYOUT' if method=='saved' else 'NO_PREPARATION' if method=='random' else 'SELECTED_GREEDY_OR_MILP_PROPOSALS_ONLY; CALIBRATION_ROWS_NOT_INJECTED',
                source_accounting='PREPARATION_LEDGER; SELECTED_X_REEVALUATED_AS_INITIAL_POPULATION')
            if method in ('greedy','milp'):
                info['outcome']='MODEL_G_VALIDATED_SEEDS' if info['sources'] else 'NO_MODEL_G_FEASIBLE_PROPOSAL_SEED'
        return cp.codec.encode(base),info
    except Exception as exc:
        info.update(status='FAILED',outcome='REJECTED',error=str(exc));raise
    finally:
        info.update(seconds=time.monotonic()-started,preparation_evaluations=calls,
            stopped_by='cancel' if session.cancel.is_set() else 'deadline' if time.monotonic()>=deadline else 'evaluation_budget' if calls>=budget else 'method_complete')
