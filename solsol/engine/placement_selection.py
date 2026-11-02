"""Post-hoc observed-X selection and geometry labels, never Model F/G changes."""
import math
import numpy as np

AREA_FILTERS=('all','coverage_any','coverage_all','coverage_none','range_any','range_all','range_none','site_any','site_all','site_none','empty')


def distance_to_area(point, geometry):
    """Euclidean distance to the closed public area; None for unspecified shapes."""
    if not isinstance(geometry,dict):return None
    x,y=point
    if geometry.get('kind')=='circle':
        cx,cy=geometry['center'];return max(0.,math.hypot(x-cx,y-cy)-geometry['radius'])
    if geometry.get('kind')=='overlap' and geometry.get('centers'):
        return min(max(0.,math.hypot(x-cx,y-cy)-geometry['radius']) for cx,cy in geometry['centers'])
    vertices=geometry.get('vertices')
    if not vertices:return None
    inside=False;distance=math.inf
    for a,b in zip(vertices,vertices[1:]+vertices[:1]):
        ax,ay=a;bx,by=b;dx,dy=bx-ax,by-ay;den=dx*dx+dy*dy
        t=max(0.,min(1.,((x-ax)*dx+(y-ay)*dy)/den)) if den else 0.
        distance=min(distance,math.hypot(x-ax-t*dx,y-ay-t*dy))
        if (ay>y)!=(by>y) and x < ax+(y-ay)*dx/(by-ay):inside=not inside
    return 0. if inside or distance<=1e-7 else distance


def area_masks(problem, width):
    distances=[distance_to_area(p,problem.get('geometry')) for p in problem.get('sites',[])]
    if not distances or any(d is None for d in distances):return None,None
    inside=np.array(distances)<=1e-7
    radii=problem.get('radii')
    ranges=None
    if isinstance(radii,list) and len(radii)==width and all(isinstance(r,(int,float)) and math.isfinite(r) and r>=0 for r in radii):
        ranges=np.array(distances)[:,None]<=np.array(radii)[None,:]+1e-7
    return inside,ranges


def area_relation(X,inside,ranges):
    occupied=np.asarray(X)!=0;total=int(occupied.sum())
    return dict(installed=total,site_inside=int((occupied*inside[:,None]).sum()) if inside is not None else None,
                range_intersects=int((occupied*ranges).sum()) if ranges is not None else None)


def area_matches(relation, area):
    if area=='all':return True
    if area.startswith('coverage_'):
        values=relation.get('model_coverage_values',[])
        if not values:return False
        return any(v>0 for v in values) if area=='coverage_any' else all(v>0 for v in values) if area=='coverage_all' else all(v==0 for v in values)
    n=relation['installed']
    if area=='empty':return n==0
    if not n:return False
    count=relation['range_intersects' if area.startswith('range_') else 'site_inside']
    if count is None:return False
    return count>0 if area.endswith('_any') else count==n if area.endswith('_all') else count==0


def representatives(rows,ids,archive_ids,count=100):
    """Cost ascending, then max-min bit Hamming; archive seed then lowest raw ID.

    All source IDs survive unchanged. No dominance or objective is recalculated here.
    Strict cost priority means expensive cost bands may not be sampled.
    """
    if not ids:return [],{}
    ids=sorted(ids,key=lambda i:(rows[i]['cost'],i))
    bits=np.array([rows[i]['X'] for i in ids],dtype=np.int8).reshape(len(ids),-1)
    distances=np.full(len(ids),bits.shape[1]+1,dtype=int);available=np.ones(len(ids),dtype=bool)
    costs=np.array([rows[i]['cost'] for i in ids]);chosen=[];scores={};archive=set(archive_ids)
    for _ in range(min(count,len(ids))):
        band=np.flatnonzero(available & (costs==costs[available].min()))
        if not chosen:
            k=next((int(k) for k in band if ids[k] in archive),int(band[0]));score=None
        else:
            k=int(band[np.argmax(distances[band])]);score=int(distances[k])
        chosen.append(ids[k]);scores[ids[k]]=score;available[k]=False
        distances=np.minimum(distances,np.count_nonzero(bits!=bits[k],axis=1))
    return chosen,scores


def performance_representatives(rows, ids, metric_order, count=100):
    """Lexicographic model performance, max-min Hamming only within exact ties.

    metric_order contains (named metric ID, +1 minimize / -1 maximize).
    No rounded bands, composite scores or scientific objectives are introduced.
    """
    if not metric_order:raise ValueError('No performance metrics configured')
    keys={i:tuple(sign*rows[i]['named_metrics'][name] for name,sign in metric_order) for i in ids}
    if any(not all(math.isfinite(v) for v in key) for key in keys.values()):raise ValueError('Non-finite performance metric')
    ordered=sorted(ids,key=lambda i:(keys[i],i))
    if not ordered:return [],{}
    bits=np.asarray([rows[i]['X'] for i in ordered],dtype=np.int8).reshape(len(ordered),-1)
    distances=np.full(len(ordered),bits.shape[1]+1,dtype=int)
    chosen=[];scores={};start=0
    while start<len(ordered) and len(chosen)<count:
        end=start+1
        while end<len(ordered) and keys[ordered[end]]==keys[ordered[start]]:end+=1
        band=list(range(start,end))
        while band and len(chosen)<count:
            k=max(band,key=lambda j:(int(distances[j]),-ordered[j]))
            scores[ordered[k]]=int(distances[k]) if chosen else None
            chosen.append(ordered[k]);band.remove(k)
            distances=np.minimum(distances,np.count_nonzero(bits!=bits[k],axis=1))
        start=end
    return chosen,scores


def primary_representatives(rows, ids, metric_order, count=100):
    """One representative per primary value before revisiting a value.

    Secondary objectives never break ties. Exact X duplicates are removed;
    max-min Hamming chooses within each primary band. Output is primary sorted.
    This is a display sample, not a Pareto archive or an optimizer objective.
    """
    if not metric_order:raise ValueError('No performance metrics configured')
    name,sign=metric_order[0]
    unique={}
    for i in ids:unique.setdefault(tuple(map(tuple,rows[i]['X'])),i)
    ordered=sorted(unique.values(),key=lambda i:(sign*rows[i]['named_metrics'][name],i))
    if not ordered:return [],{}
    values=[sign*rows[i]['named_metrics'][name] for i in ordered]
    if not all(math.isfinite(v) for v in values):raise ValueError('Non-finite performance metric')
    bits=np.asarray([rows[i]['X'] for i in ordered],dtype=np.int8).reshape(len(ordered),-1)
    bands={}
    for k,v in enumerate(values):bands.setdefault(v,[]).append(k)
    distances=np.full(len(ordered),bits.shape[1]+1,dtype=int);chosen=[]
    while len(chosen)<min(count,len(ordered)):
        for band in bands.values():
            if not band:continue
            k=max(band,key=lambda j:(int(distances[j]),-ordered[j]))
            band.remove(k);chosen.append(k)
            distances=np.minimum(distances,np.count_nonzero(bits!=bits[k],axis=1))
            if len(chosen)>=count:break
    chosen.sort(key=lambda k:values[k])
    scores={ordered[k]:None if j==0 else int(np.count_nonzero(bits[chosen[:j]]!=bits[k],axis=1).min()) for j,k in enumerate(chosen)}
    return [ordered[k] for k in chosen],scores
