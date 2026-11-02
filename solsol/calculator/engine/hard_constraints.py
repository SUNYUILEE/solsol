"""Calculator installation audit; never changes the Model's raw F/G or IDs."""
import numpy as np
from .installation_domain import GEOMETRIC_MODELS
from .placement_selection import distance_to_area
from .quality_values import finite_vector

def definition(record):
    from .workflow import metadata_packet
    p=metadata_packet(record)
    rule=p['compilation'].get('inventory_rule')
    if rule is None:
        c=p['config'];order=p['registry']['sensor_order']
        keys={'radar':'radar_stock','eoir':'eo_stock'} if record.cid=='RADAR_EOIR' else {'radar':'radar_limit','rf_scanner':'rf_limit','eoir':'eoir_limit'}
        if c.get('resource_mode') in ('all','partial') and all(keys.get(s) in c for s in order):
            rule=dict(mode=c['resource_mode'],limits=[c[keys[s]] for s in order])
    return p,rule

def area_distances(p):
    return [distance_to_area(s,p['problem'].get('geometry')) for s in p['problem']['sites']] if p['experiment_contract_id'] in GEOMETRIC_MODELS else []


def _prepare(p,rule,distances=None):
    """Invocation-local constants, shared only across rows of this frozen packet."""
    geometric=p['experiment_contract_id'] in GEOMETRIC_MODELS
    ds=(area_distances(p) if distances is None else distances) if geometric else []
    unknown=any(d is None for d in ds)
    return dict(expected=rule['limits'] if rule and rule.get('mode')=='all' else None,
        limits=np.asarray(rule['limits']) if rule and rule.get('mode') in ('all','partial') else None,
        resource_lower=np.asarray(rule['lower']) if rule and 'lower' in rule else None,
        resource_upper=np.asarray(rule['upper']) if rule and 'upper' in rule else None,
        forbidden=~np.asarray(p['compilation']['allowed'],bool),
        outside_mask=np.asarray(ds)>1e-7 if geometric and not unknown else None,
        unknown=unknown,geometric=geometric)


_UNMEASURED=object()

def audit_row(row,p,rule,distances=None,*,_prepared=None,_measured=None,_constraint_violation=_UNMEASURED):
    prepared=_prepare(p,rule,distances) if _prepared is None else _prepared
    expected=prepared['expected']
    unknown=prepared['unknown']
    if _measured is None:
        x=np.asarray(row['X']);counts=x.sum(0).astype(int)
        stock=int(np.abs(counts-prepared['limits']).sum()) if expected is not None else int(np.maximum(counts-prepared['limits'],0).sum()) if rule and rule.get('mode')=='partial' else 0
        if prepared['resource_lower'] is not None:
            stock=int((np.maximum(prepared['resource_lower']-counts,0)+np.maximum(counts-prepared['resource_upper'],0)).sum())
        outside=0
        if prepared['outside_mask'] is not None:outside=int(x[prepared['outside_mask']].sum())
        forbidden=int((x*prepared['forbidden']).sum())
        duplicate=int(np.maximum(x-1,0).sum())
        colocation=0 if p['compilation'].get('co_location',True) else int(np.maximum(x.sum(1)-1,0).sum())
        total=int(x.sum())
    else:
        counts,stock,outside,forbidden,duplicate,colocation,total=_measured
    # Evaluation area is a performance target, not the installation domain.
    # Sensor centers outside it remain legal if the Model allows the slots.
    hard=stock+forbidden+duplicate+colocation
    goals=(p['config'].get('_research') or p['problem'].get('research_configuration',{})).get('goals')
    return dict(run_id=p['run_id'],solution_id=row['id'],selected_sensor_count=counts.tolist(),expected_sensor_count=expected,
        inside_evaluation_area_count=None if unknown else total-outside,outside_evaluation_area_count=None if unknown else outside,duplicate_count=duplicate,
        forbidden_slot_count=forbidden,co_location_violation=colocation,inventory_violation=stock,
        hard_constraint_violation=hard,constraint_violation=(float(np.maximum(row['G'],0).sum()) if finite_vector(row.get('G'),allow_empty=True) else None) if _constraint_violation is _UNMEASURED else _constraint_violation,
        objective_values=row.get('F'),quantitative_target_enabled=goals is not None,performance_constraint_values={key:float(value)-row['coverage_metrics'][key] for key,value in (goals or {}).items()} if p['experiment_contract_id'] in GEOMETRIC_MODELS else {},hard_pass=hard==0,
        duplicate_definition='same candidate/sensor pair; cross-sensor co-location follows model contract')

def _measure_batch(rows,p,rule,prepared,validated_decisions=None):
    """Bounded rectangular stored rows; preserve scalar audit arithmetic."""
    # Retained decisions are uint8: subtraction must use signed arithmetic.
    x=np.asarray([r['X'] for r in rows],dtype=int) if validated_decisions is None else np.asarray([validated_decisions[r['id']] for r in rows],dtype=int)
    counts=x.sum(axis=1).astype(int)
    zeros=np.zeros(len(rows),dtype=int)
    stock=np.abs(counts-prepared['limits']).sum(axis=1).astype(int) if prepared['expected'] is not None else np.maximum(counts-prepared['limits'],0).sum(axis=1).astype(int) if rule and rule.get('mode')=='partial' else zeros
    if prepared['resource_lower'] is not None:
        stock=(np.maximum(prepared['resource_lower']-counts,0)+np.maximum(counts-prepared['resource_upper'],0)).sum(axis=1).astype(int)
    outside=x[:,prepared['outside_mask']].sum(axis=(1,2)).astype(int) if prepared['outside_mask'] is not None else zeros
    forbidden=(x*prepared['forbidden']).sum(axis=(1,2)).astype(int)
    duplicate=np.maximum(x-1,0).sum(axis=(1,2)).astype(int)
    colocation=zeros if p['compilation'].get('co_location',True) else np.maximum(x.sum(axis=2)-1,0).sum(axis=1).astype(int)
    total=x.sum(axis=(1,2)).astype(int)
    for i in range(len(rows)):
        yield counts[i],int(stock[i]),int(outside[i]),int(forbidden[i]),int(duplicate[i]),int(colocation[i]),int(total[i])


def _constraint_batch(rows):
    # Invocation-local only: never cache facts about mutable F/G. Fast native
    # finite checks/reductions replace one ndarray and ABC check per row.
    values=[r.get('G') for r in rows]
    if not values or any(type(v) not in (list,tuple) for v in values):return None
    width=len(values[0])
    for v in values:
        if len(v)!=width:return None
        has_float=False
        for g in v:
            if type(g) is float:has_float=True
            elif type(g) is not int or not -(2**53)<=g<=2**53:return None
        # Match the original per-row NumPy float64 dtype, never coerce an
        # integer-only row (integer sum overflow/precision differs).
        if width and not has_float:return None
    matrix=np.asarray(values,dtype=float)
    if not np.isfinite(matrix).all():return None
    # Retain scalar overflow/warning/exception order on unusual magnitudes.
    if width and (np.abs(matrix)>np.finfo(float).max/(2*width)).any():return None
    return np.maximum(matrix,0).sum(axis=1).tolist()

def reports(record):
    cache=getattr(record,'_hard_reports',None)
    if cache is None:cache={};record._hard_reports=cache
    if len(cache)!=len(record.rows):
        p,rule=definition(record)
        ds=area_distances(p)
        prepared=_prepare(p,rule,ds)
        for start in range(len(cache),len(record.rows),256):
            rows=record.rows[start:start+256]
            violations=_constraint_batch(rows)
            for i,(r,measured) in enumerate(zip(rows,_measure_batch(rows,p,rule,prepared,getattr(record,'_validated_decisions',None)))):
                cache[r['id']]=audit_row(r,p,rule,ds,_prepared=prepared,_measured=measured,_constraint_violation=violations[i] if violations is not None else _UNMEASURED)
    return cache

def valid_ids(record,ids):
    checks=reports(record)
    return [i for i in ids if checks[i]['hard_pass']]

def decorated(record,i):
    import copy
    row=record.rows[i]
    # X is the validated binary candidate/sensor matrix. Its numeric cells
    # are immutable; copying the two list levels preserves independent DTOs
    # without recursively dispatching deepcopy for every cell of every map.
    result=copy.deepcopy({k:v for k,v in row.items() if k!='X'})
    result['X']=[site[:] for site in row['X']]
    result['installation_audit']=reports(record)[i]
    return result

