"""All-observation empirical archive; exact dominance, distinct physical layouts."""
import numpy as np
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting

from .contracts import digest


def archive_ids(rows,contract_id=None):
    unique={};seen_ids=set();width=None
    for r in rows:
        if type(r['id']) is not int or r['id']<0 or r['id'] in seen_ids:raise ValueError('Duplicate raw ID')
        seen_ids.add(r['id'])
        if contract_id is not None and r['experiment_contract_id']!=contract_id:raise ValueError('Mixed contract archive')
        if r['provenance'] not in ('INITIAL_POPULATION','SEARCH_EVALUATION'):raise ValueError('Diagnostics cannot enter optimizer archive')
        f=np.asarray(r['F'],float);g=np.asarray(r['G'],float);x=np.asarray(r['X'])
        if f.ndim!=1 or g.ndim!=1 or len(f)<2 or not np.isfinite(f).all() or not np.isfinite(g).all():
            raise ValueError('Invalid F/G')
        if x.ndim!=2 or np.any((x!=0)&(x!=1)):raise ValueError('Invalid decision')
        shape=(f.shape,g.shape,x.shape)
        if width is not None and shape!=width:raise ValueError('Mixed archive shape')
        width=shape
        key=digest(r['X'])
        if key in unique:
            old=unique[key]
            if old['F']!=r['F'] or old['G']!=r['G']:raise ValueError('Inconsistent same-X evaluations')
        else:unique[key]=r
    feasible=[r for r in unique.values() if all(v<=0 for v in r['G'])]
    if not feasible:return []
    keep=NonDominatedSorting().do(np.array([r['F'] for r in feasible]),only_non_dominated_front=True)
    return sorted(feasible[int(i)]['id'] for i in keep)
