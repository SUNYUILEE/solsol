"""Explicit posthoc front-preserving heuristic. Does not replace the archive."""
import numpy as np
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
from .placement_selection import primary_representatives


def front_representatives(rows, ids, objectives, performance_order, count=100):
    if type(count) is not int or count < 1:raise ValueError('Positive representative capacity required')
    first={}
    for i in sorted(ids):first.setdefault(tuple(map(tuple,rows[i]['X'])),i)
    ids=sorted(first.values())
    if not ids:return [],{},dict(front_vectors=0,selected_front_vectors=0,front_layouts=0,selected_front_layouts=0,extremes=[],all_front_vectors_preserved=True,all_front_layouts_preserved=True)
    if not objectives or not performance_order:raise ValueError('Active objectives required')
    values=np.asarray([[rows[i]['named_metrics'][m['id']] for m in objectives] for i in ids],float)
    if not np.isfinite(values).all():raise ValueError('Nonfinite objective value')
    signs=np.asarray([-1 if m['direction']=='maximize' else 1 for m in objectives])
    f=values*signs
    unique,inverse=np.unique(f,axis=0,return_inverse=True)
    front=sorted(map(int,NonDominatedSorting().do(unique,only_non_dominated_front=True)))
    low=f.min(axis=0);span=f.max(axis=0)-low;active=np.flatnonzero(span>0)
    normalized=(unique[:,active]-low[active])/span[active]
    members={j:[] for j in front}
    for k,j in enumerate(inverse):
        if int(j) in members:members[int(j)].append(k)
    # Extrema are selected from the nondominated set, including tied extremes.
    extrema={int(j):min(front,key=lambda k:(unique[k,j],tuple(unique[k]),k)) for j in active}
    chosen_f=[]
    for j in active:
        k=extrema[int(j)]
        if k not in chosen_f and len(chosen_f)<count:chosen_f.append(k)
    if not chosen_f:chosen_f=[front[0]]
    remaining_f=set(front)-set(chosen_f)
    distances=np.full(len(unique),np.inf)
    for k in chosen_f:distances=np.minimum(distances,np.linalg.norm(normalized-normalized[k],axis=1))
    while remaining_f and len(chosen_f)<count:
        k=max(remaining_f,key=lambda k:(float(distances[k]),-k));chosen_f.append(k);remaining_f.remove(k)
        distances=np.minimum(distances,np.linalg.norm(normalized-normalized[k],axis=1))
    bits=np.asarray([rows[i]['X'] for i in ids],dtype=np.int8).reshape(len(ids),-1)
    hamming=np.full(len(ids),bits.shape[1]+1,dtype=int);chosen=[]
    def add(k):
        chosen.append(k)
        np.minimum(hamming,np.count_nonzero(bits!=bits[k],axis=1),out=hamming)
    for j in chosen_f:add(max(members[j],key=lambda k:(int(hamming[k]),-ids[k])))
    front_members={k for group in members.values() for k in group}
    remaining_x=front_members-set(chosen)
    while remaining_x and len(chosen)<min(count,len(ids)):
        k=max(remaining_x,key=lambda k:(int(hamming[k]),-ids[k]));add(k);remaining_x.remove(k)
    if len(chosen)<min(count,len(ids)):
        used={ids[k] for k in chosen}
        extra,_=primary_representatives(rows,[i for i in ids if i not in used],performance_order,count-len(chosen))
        positions={i:k for k,i in enumerate(ids)}
        for i in extra:add(positions[i])
    chosen.sort(key=lambda k:(tuple(sign*rows[ids[k]]['named_metrics'][name] for name,sign in performance_order),ids[k]))
    selected_f={int(inverse[k]) for k in chosen}
    scores={ids[k]:None if j==0 else int(np.count_nonzero(bits[chosen[:j]]!=bits[k],axis=1).min()) for j,k in enumerate(chosen)}
    meta=dict(front_vectors=len(front),selected_front_vectors=len(set(front)&selected_f),
        front_layouts=len(front_members),selected_front_layouts=len(front_members&set(chosen)),
        all_front_vectors_preserved=set(front)<=selected_f,all_front_layouts_preserved=front_members<=set(chosen),
        extremes=[dict(objective_id=m['id'],value=float(values[:,j].max() if signs[j]<0 else values[:,j].min()),
                       preserved=any(f[k,j]==low[j] for k in chosen)) for j,m in enumerate(objectives)],
        capacity=count,dominance='EXACT_ACTIVE_OBJECTIVES_WITHIN_FILTERED_OBSERVATIONS',
        constant_objectives=[m['id'] for j,m in enumerate(objectives) if span[j]==0])
    return [ids[k] for k in chosen],scores,meta
