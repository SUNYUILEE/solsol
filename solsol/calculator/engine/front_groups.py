"""Display-only performance ordering and representative-radius Hamming groups."""
import numpy as np
from .placement_selection import performance_representatives


def group_front(rows, ids, metrics, radius):
    ordered,scores=performance_representatives(rows,ids,metrics,count=len(ids))
    if not ordered:return [],{},[]
    bits=np.asarray([rows[i]['X'] for i in ordered],dtype=np.int8).reshape(len(ordered),-1)
    leaders=[];groups=[];members={}
    for k,i in enumerate(ordered):
        distances=np.count_nonzero(bits[leaders]!=bits[k],axis=1) if leaders else np.array([],dtype=int)
        eligible=np.flatnonzero(distances<=radius)
        if len(eligible):g=int(min(eligible,key=lambda j:(distances[j],j)));distance=int(distances[g])
        else:
            g=len(leaders);leaders.append(k);groups.append(dict(id=g+1,representative_id=i,size=0));distance=0
        groups[g]['size']+=1
        members[i]=dict(group_id=g+1,representative_id=groups[g]['representative_id'],distance_to_representative=distance,performance_rank=k+1,hamming_to_previous_min=scores[i])
    return ordered,members,groups
