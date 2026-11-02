"""Calculator-owned inventory assignment and repair, extracted independently of models."""
import numpy as np

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
