"""Calculator initialization using public constraints and actual Model rows.

Greedy uses epsilon coverage and cost; no RF physics is reimplemented. Every
injected layout is evaluated again as an INITIAL_POPULATION row.
"""
import time
import numpy as np
from .store import digest

METHODS = ('random', 'greedy', 'milp')


def resource_bounds(space, rule):
    """Use Model-published count bounds; budget feasibility remains Model G."""
    if rule and ('lower' in rule or 'upper' in rule):
        lower, upper = rule.get('lower'), rule.get('upper')
        n = space.shape[1]
        if not isinstance(lower,list) or not isinstance(upper,list) or len(lower)!=n or len(upper)!=n or any(type(v) is not int or v<0 for v in lower+upper):
            raise ValueError('INITIALIZER_INVALID_RESOURCE_BOUNDS')
        lower=np.asarray(lower);upper=np.minimum(upper,space.allowed.sum(0))
        if np.any(lower>upper):raise ValueError('INITIALIZER_INFEASIBLE_RESOURCE_BOUNDS')
        return lower,upper
    upper,exact=resource_counts(space,rule)
    return upper.copy() if exact else np.zeros_like(upper),upper


def resource_counts(space, rule):
    capacity = space.allowed.sum(axis=0).astype(int)
    if not rule or rule['mode'] == 'off':
        return capacity, False
    if rule['mode'] not in ('partial', 'all'):
        raise ValueError('INITIALIZER_UNKNOWN_RESOURCE_MODE')
    limits = rule['limits']
    if len(limits) != space.shape[1] or any(type(v) is not int or v < 0 for v in limits):
        raise ValueError('INITIALIZER_INVALID_RESOURCE_LIMITS')
    exact = rule['mode'] == 'all'
    if exact and np.any(np.asarray(limits) > capacity):
        raise ValueError('INITIALIZER_INFEASIBLE_ALL_RESOURCE')
    return np.minimum(limits, capacity), exact


def assign(space, counts, orders, exact=True, minimum=None):
    """Bipartite augmenting paths avoid greedy starvation of restricted sensors."""
    x = np.zeros(space.shape, np.uint8)
    if space.co_location:
        for j, count in enumerate(counts):
            x[np.asarray(orders[j][:int(count)], dtype=int), j] = 1
        return space.validate(x)
    owner = {}
    def place(sensor, seen):
        for site in orders[sensor]:
            site = int(site)
            if site in seen:
                continue
            seen.add(site)
            if site not in owner or place(owner[site], seen):
                owner[site] = sensor
                return True
        return False
    required = np.zeros_like(counts) if minimum is None else np.asarray(minimum)
    for j, count in enumerate(required):
        for _ in range(int(count)):
            if not place(j,set()):raise ValueError('INITIALIZER_INFEASIBLE_RESOURCE_BOUNDS')
    for j, count in enumerate(np.asarray(counts)-required):
        for _ in range(int(count)):
            if not place(j, set()) and exact:
                raise ValueError('INITIALIZER_INFEASIBLE_ALL_RESOURCE')
    for site, sensor in owner.items():
        x[site, sensor] = 1
    return space.validate(x)


def validate_resources(space, rule):
    if rule and ('lower' in rule or 'upper' in rule):
        lower,_=resource_bounds(space,rule)
        assign(space,lower,[np.flatnonzero(space.allowed[:,j]) for j in range(space.shape[1])])
        return
    counts, exact = resource_counts(space, rule)
    if exact:
        assign(space, counts, [np.flatnonzero(space.allowed[:, j]) for j in range(space.shape[1])])


def repair_all(space, rule, x):
    counts, exact = resource_counts(space, rule)
    assert exact
    orders = [sorted(np.flatnonzero(space.allowed[:, j]), key=lambda i: (-int(x[i, j]), int(i)))
              for j in range(space.shape[1])]
    return assign(space, counts, orders)


def randomized_resource_repair(space, rule, x, rng):
    """Repair invalid offspring once; valid placements consume no RNG."""
    x=np.asarray(x,np.uint8).copy()*space.allowed
    if not space.co_location:
        for i in np.flatnonzero(x.sum(1)>1):
            keep=int(rng.choice(np.flatnonzero(x[i])));x[i]=0;x[i,keep]=1
    lower,limits=resource_bounds(space,rule)
    exact=bool(np.all(lower==limits))
    counts=x.sum(0)
    if np.all((counts>=lower)&(counts<=limits)):return space.validate(x)
    orders=[]
    for j in range(space.shape[1]):
        selected=rng.permutation(np.flatnonzero(x[:,j]))
        free=rng.permutation(np.flatnonzero(space.allowed[:,j] & (x[:,j]==0)))
        orders.append(np.concatenate([selected,free]))
    return assign(space,np.clip(counts,lower,limits),orders,exact=exact,minimum=lower)


def prepare_greedy(session, deadline):
    """Bounded epsilon coverage/cost greedy; all scores come from Model rows."""
    started=time.monotonic()
    cp=session.problem; p=session.optimizer['population']
    goals=cp.config['_research']['goals']
    keys=list(goals); target=np.asarray([goals[k] for k in keys],float)
    rng=np.random.default_rng(np.random.SeedSequence([session.optimizer['seed'],91401]))
    rule=getattr(cp.bundle,'inventory_rule',None)
    limits,exact=resource_counts(cp.space,rule)
    trace=session.solver_metadata.setdefault('initializer_trace',[])
    ledger=session.solver_metadata.setdefault('auxiliary_evaluations',[])
    calls=0; best=None; current=None
    def evaluate(X):
        nonlocal calls
        if session.cancel.is_set():return []
        if time.monotonic()>=deadline or calls+len(X)>512:return []
        result=cp.evaluate_physical(np.asarray(X),validate_installation=True)
        for row in result:ledger.append(dict(auxiliary_id=len(ledger),phase='preparation',row=row))
        calls+=len(result);session.counters['preparation_evaluations']+=len(result)
        return result
    def shortfall(row):
        return float(np.maximum(target-np.asarray([row['coverage_metrics'][k] for k in keys]),0).sum())
    def meets(row):
        return shortfall(row)<=1e-10 and np.all(np.asarray(row['G'])<=getattr(cp,'feasibility_tolerance',0))
    x=np.zeros(cp.space.shape,np.uint8)
    rows=evaluate([x])
    if rows:current=rows[0]
    while current is not None:
        if meets(current):best=current;break
        candidates=[]
        for i,j in np.argwhere(cp.space.allowed & (x==0)):
            if x[:,j].sum()>=limits[j] or (not cp.space.co_location and x[i].any()):continue
            y=x.copy();y[i,j]=1;candidates.append(y)
        if not candidates:break
        remaining=512-calls
        if len(candidates)>remaining:
            candidates=[candidates[i] for i in rng.choice(len(candidates),remaining,replace=False)]
        if not candidates:break
        rows=evaluate(candidates)
        if not rows:break
        before=shortfall(current)
        ranked=sorted(enumerate(rows),key=lambda pair: (
            -(before-shortfall(pair[1]))/max(float(pair[1]['cost'])-float(current['cost']),1e-12),
            shortfall(pair[1]),float(pair[1]['cost']),pair[0]))
        index,row=ranked[0]
        trace.append(dict(method='greedy',candidates_evaluated=len(rows),selected_auxiliary_id=len(ledger)-len(rows)+index,
                          shortfall_before=before,shortfall_after=shortfall(row)))
        x=np.asarray(row['X'],np.uint8);current=row
    if current is not None and exact and not meets(current):
        x=repair_all(cp.space,rule,x)
        rows=evaluate([x])
        if rows:current=rows[0]
        if current is not None and meets(current):best=current
    if best is not None:
        x=np.asarray(best['X'],np.uint8)
        for flat in np.flatnonzero(x.ravel()):
            y=x.copy();y.flat[flat]=0
            rows=evaluate([y])
            if not rows:break
            if meets(rows[0]) and rows[0]['cost']<best['cost']:
                best=rows[0];x=y
    base=[]
    for _ in range(p):
        counts=limits if exact else np.asarray([rng.integers(0,v+1) for v in limits])
        orders=[rng.permutation(np.flatnonzero(cp.space.allowed[:,j])) for j in range(cp.space.shape[1])]
        base.append(assign(cp.space,counts,orders,exact=exact))
    if best is not None:base[0]=np.asarray(best['X'],np.uint8)
    X=np.asarray(base)
    info=dict(method='greedy',version='model-oracle-epsilon-greedy-v1',population=p,seed_count=int(best is not None),
              targets=goals,target_semantics='MODEL_COVERAGE_METRICS_PERCENT_NOT_MEAN_QUALITY',
              preparation_evaluations=calls,preparation_budget=512,seconds=time.monotonic()-started,
              deadline_seconds=max(0,deadline-started),deadline_semantics='cooperative between Model HTTP batches',
              outcome='QUALIFIED_SEED' if best is not None else 'NO_QUALIFIED_SEED_WITHIN_BUDGET',
              fallback_population='seeded resource-feasible random',sources=[dict(index=0,method='greedy',auxiliary_id=next(v['auxiliary_id'] for v in ledger if v['row']==best))] if best is not None else [],
              pareto_front_certified=False,scientific_optimum_certified=False,
              initial_X_sha256=digest(X.astype(int).tolist()))
    return cp.codec.encode(X),info
