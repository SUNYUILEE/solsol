"""Proven fixed-cost projection for search, preserving every raw Model value."""
def projection(cp):
    ids=list(cp.objective_order);active=list(range(len(ids)));excluded=[]
    rule=getattr(cp.bundle,'inventory_rule',None)
    # This published EOIR contract has site-independent unit costs 6 and 2.
    # RF and HMSP have occupied-site accounting: exact stock is insufficient.
    if not cp.config.get('_resource_contract') and cp.cid=='RADAR_EOIR' and cp.config.get('objective_contract')=='full_area_tradeoff_v6' and rule and rule['mode']=='all' and 'cost' in ids:
        index=ids.index('cost');active.remove(index)
        excluded=[dict(objective_id='cost',index=index,reason='FIXED_INVENTORY_FIXED_UNIT_COST',cost=sum(n*{'radar':6,'eoir':2}[s] for s,n in zip(cp.sensor_order,rule['limits'])),evaluator_sha256=cp.evaluator_hash)]
    if len(active)<2:raise ValueError('OBJECTIVE_ACTIVITY: 상수 비용을 제외하면 유효 목적이 2개 미만입니다. 기존 성능 목적을 추가하세요.')
    return dict(version='CALCULATOR_EFFECTIVE_OBJECTIVES_V1',raw_objective_ids=ids,effective_indices=active,effective_objective_ids=[ids[i] for i in active],excluded=excluded,raw_values_preserved=True)
