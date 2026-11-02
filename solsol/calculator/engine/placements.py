"""Read-only, globally sorted pages of observed feasible unique placements.

This collection includes dominated rows; it never replaces the Pareto archive.
"""
import copy
from .store import digest
from .configuration_view import physical_key
from .subset_fidelity import evaluate_subset, finite_evaluation
from .placement_selection import AREA_FILTERS,area_masks,area_relation,area_matches,representatives,performance_representatives,primary_representatives


def collection_counts(record,cp,tolerance):
    """Unfiltered, exact-X unique collection sizes at the selected checkpoint."""
    from .hard_constraints import reports
    key=(cp['generation'],cp['nfe'],tolerance)
    cache=getattr(record,'_collection_counts',{})
    if key in cache:return copy.deepcopy(cache[key])
    hard=reports(record)
    def unique(ids):
        rows={}
        for i in sorted(ids):
            if hard[i]['hard_pass'] and finite_evaluation(record.rows[i],tolerance):
                rows.setdefault(physical_key(record,record.rows[i]),record.rows[i])
        return rows
    observed=unique(range(cp['nfe']))
    archive=unique(cp['archive_ids'])
    history=unique({i for c in record.checkpoints if c['generation']<=cp['generation'] for i in c['archive_ids']})
    value={name:dict(all=len(rows),qualified=sum(r.get('qualified') is True for r in rows.values())) for name,rows in [('archive',archive),('history',history),('observed',observed)]}
    value.update(generation=cp['generation'],last_generation=record.checkpoints[-1]['generation'])
    cache[key]=value
    if len(cache)>8:cache.pop(next(iter(cache)))
    record._collection_counts=cache
    return copy.deepcopy(value)


def placements(record, generation=None, offset=0, limit=100, sort='cost', targets=False, selection='all', area='all', arrange='plain', hamming_radius=2, hamming_group=0, representatives_only=False, layout_scope='all'):
    if not isinstance(layout_scope,str):raise ValueError('Invalid layout scope')
    if selection not in ('all','diverse100','performance100','primary100','front100','history','archive') or area not in AREA_FILTERS:raise ValueError('Invalid placement selection or area filter')
    if arrange not in ('plain','performance') or type(hamming_radius) is not int or not 0<=hamming_radius<=100000 or type(hamming_group) is not int or hamming_group<0 or type(representatives_only) is not bool:raise ValueError('Invalid front grouping')
    grouped=selection in ('history','archive') and arrange=='performance'
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('Invalid placement page')
    if type(targets) is not bool:raise ValueError('Invalid target filter')
    cps=record.checkpoints
    if generation is not None and (type(generation) is not int or not 0 <= generation < len(cps)):
        raise ValueError('Invalid generation')
    cp=cps[generation] if generation is not None else cps[-1] if cps else None
    stop=cp['nfe'] if cp else 0
    history={}
    if selection=='history':
        for checkpoint in cps:
            if checkpoint['nfe']>stop or checkpoint['generation']>cp['generation']:break
            for i in checkpoint['archive_ids']:
                entry=history.setdefault(i,dict(first_generation=checkpoint['generation'],last_generation=checkpoint['generation']))
                entry['last_generation']=checkpoint['generation']
    research=record.config.get('_research') or record.frozen_problem.get('research_configuration')
    if not research:raise ValueError('Observed placement browser requires configurable run')
    metadata=research['metadata'];metrics={m['id']:m for m in metadata['metrics']}
    active=set(research.get('objective_ids',[])+research.get('diagnostic_ids',[]))
    performance_ids=[i for i in research.get('objective_ids',[]) if i!='cost']
    performance_order=[]
    if selection in ('performance100','primary100','front100') or grouped:
        if not performance_ids:raise ValueError('No active performance objective')
        if sort in ('cost','raw'):sort=performance_ids[0]
        if sort not in performance_ids:raise ValueError('Performance priority must be an active performance objective')
        performance_order=[sort]+[i for i in performance_ids if i!=sort]
    if sort not in ('cost','raw') and (sort not in metrics or (active and sort not in active)):raise ValueError('Invalid placement sort')
    if targets and (research['goals'] is None or not metadata['coverage_metrics']):
        raise ValueError('Area targets not configured')
    from .workflow import metadata_packet
    packet=metadata_packet(record)
    tolerance=packet['archive_policy']['tolerance']
    cache=getattr(record,'_placement_pages',None)
    if cache is None:cache={};record._placement_pages=cache
    sensor_order=packet['registry']['sensor_order']
    if layout_scope!='all' and layout_scope not in sensor_order:raise ValueError('Layout scope requires a registered sensor')
    key=(stop,cp['generation'] if cp else None,sort,targets,tolerance,selection,area,arrange,hamming_radius,layout_scope)
    if key not in cache:
        from .hard_constraints import reports
        hard=reports(record)
        first={}
        source=[record.rows[i] for i in sorted(history)] if selection=='history' else [record.rows[i] for i in cp['archive_ids']] if selection=='archive' and cp else [] if selection=='archive' else record.rows[:stop]
        for row in source:
            if hard[row['id']]['hard_pass'] and finite_evaluation(row,tolerance):
                first.setdefault(physical_key(record,row),row['id'])
        ids=list(first.values());unique=len(ids)
        if selection=='history':
            for row in source:
                i=first.get(physical_key(record,row))
                if i is not None:
                    history[i]['first_generation']=min(history[i]['first_generation'],history[row['id']]['first_generation'])
                    history[i]['last_generation']=max(history[i]['last_generation'],history[row['id']]['last_generation'])
        if targets:ids=[i for i in ids if record.rows[i]['qualified'] is True]
        width=len(record.rows[0]['X'][0]) if record.rows and record.rows[0]['X'] else len(record.frozen_problem.get('radii') or [])
        inside,ranges=area_masks(record.frozen_problem,width)
        if area.startswith('site_') and inside is None:raise ValueError('Saved model has no explicit evaluation-area boundary')
        if area.startswith('range_') and ranges is None:raise ValueError('Saved model has no explicit evaluation-area boundary and sensor radii')
        relations={i:area_relation(record.rows[i]['X'],inside,ranges) for i in ids}
        for i in ids:relations[i]['model_coverage_values']=list(record.rows[i].get('coverage_metrics',{}).values())
        ids=[i for i in ids if area_matches(relations[i],area)]
        eligible=len(ids);reference_ids=list(ids);scores={}
        direction=-1 if metrics.get(sort,{}).get('direction')=='maximize' else 1
        def order(i):
            r=record.rows[i]
            value=i if sort=='raw' else r['cost'] if sort=='cost' else r['named_metrics'][sort]
            return (direction*value,i)
        members={};groups=[];preservation=None
        selection_rows=record.rows;sensor_groups=[]
        if layout_scope!='all':
            sensor_index=sensor_order.index(layout_scope)
            def priority(i):
                return tuple((-1 if metrics[m]['direction']=='maximize' else 1)*record.rows[i]['named_metrics'][m] for m in performance_order)+(i,) if performance_order else order(i)
            distinct={}
            for i in sorted(ids,key=priority):distinct.setdefault(tuple(x[sensor_index] for x in record.rows[i]['X']),[]).append(i)
            sensor_groups=[dict(representative_id=members[0],member_ids=members) for members in distinct.values()]
            ids=[g['representative_id'] for g in sensor_groups]
            selection_rows={i:dict(record.rows[i],X=[[x[sensor_index]] for x in record.rows[i]['X']]) for i in ids}
        if grouped:
            from .front_groups import group_front
            ids,members,groups=group_front(selection_rows,ids,[(i,-1 if metrics[i]['direction']=='maximize' else 1) for i in performance_order],hamming_radius)
        elif selection=='front100':
            from .front_representatives import front_representatives
            ids,scores,preservation=front_representatives(selection_rows,ids,[metrics[i] for i in research['objective_ids']],[(i,-1 if metrics[i]['direction']=='maximize' else 1) for i in performance_order])
            if layout_scope!='all':preservation=None
        elif selection in ('performance100','primary100'):
            selector=primary_representatives if selection=='primary100' else performance_representatives
            ids,scores=selector(selection_rows,ids,[(i,-1 if metrics[i]['direction']=='maximize' else 1) for i in performance_order])
        elif selection=='diverse100':ids,scores=representatives(selection_rows,ids,cp['archive_ids'] if cp else [])
        else:ids.sort(key=order)
        cache[key]=(ids,unique,eligible,relations,scores,inside is not None,ranges is not None,copy.deepcopy(history),members,groups,preservation,reference_ids,sensor_groups)
        if len(cache)>8:cache.pop(next(iter(cache)))
    ids,unique,eligible,relations,scores,site_available,range_available,history,members,groups,preservation,reference_ids,sensor_groups=cache[key]
    before_group=len(ids)
    if grouped:
        if hamming_group and hamming_group not in {g['id'] for g in groups}:raise ValueError('Unknown Hamming group')
        ids=[i for i in ids if (not hamming_group or members[i]['group_id']==hamming_group) and (not representatives_only or members[i]['representative_id']==i)]
    total=len(ids)
    fidelity_cache=getattr(record,'_subset_fidelity',{})
    fidelity_key=(key,hamming_group,representatives_only)
    if fidelity_key not in fidelity_cache:
        basis_source=dict(run_id=record.id,experiment_contract_id=record.cid,config_sha256=record.frozen_problem['config_sha256'],
            evaluator_sha256=packet['evaluator_sha256'],problem_sha256=digest(record.frozen_problem),registry_sha256=digest(packet['registry']),
            generation=cp['generation'] if cp else 0,nfe_boundary=stop,collection=selection if selection in ('archive','history') else 'observed',
            targets=targets,goals=research.get('goals'),area=area,tolerance=tolerance,identity_policy='FIRST_FEASIBLE_RAW_ID_PER_EXACT_X_THROUGH_GENERATION')
        fidelity_cache[fidelity_key]=evaluate_subset(record.rows,reference_ids,ids,[metrics[i] for i in research.get('objective_ids',[])],source=basis_source)
        if len(fidelity_cache)>8:fidelity_cache.pop(next(iter(fidelity_cache)))
        record._subset_fidelity=fidelity_cache
    fidelity=copy.deepcopy(fidelity_cache[fidelity_key])
    # Clamp a previously valid page after a generation/filter change.
    offset=min(offset,((total-1)//limit)*limit) if total else 0
    from .hard_constraints import valid_ids,reports
    archive=set(valid_ids(record,cp['archive_ids'] if cp else []))
    rows=[dict(copy.deepcopy(record.rows[i]),observed_is_nondominated=i in archive,
               installation_audit=reports(record)[i],
               area_relation=relations[i],representative_rank=ids.index(i)+1 if selection in ('diverse100','performance100','primary100','front100') else None,
               hamming_to_selected_min=scores.get(i)) for i in ids[offset:offset+limit]]
    if selection=='history':
        archive_x={tuple(map(tuple,record.rows[i]['X'])) for i in archive}
        for row in rows:
            row['nondominance_history']=history[row['id']]
            row['observed_is_nondominated']=tuple(map(tuple,row['X'])) in archive_x
    if grouped:
        for row in rows:
            row['hamming']=members[row['id']]
            row['representative_rank']=members[row['id']]['performance_rank']
            row['hamming_to_selected_min']=members[row['id']]['hamming_to_previous_min']
    return dict(schema='SOLSOL_OBSERVED_PLACEMENTS_V1',run_id=record.id,experiment_contract_id=record.cid,
                config_sha256=record.frozen_problem['config_sha256'],generation=cp['generation'] if cp else 0,
                nfe_boundary=stop,total=total,unique_feasible=unique,archive_count=len(archive),
                collection_counts=collection_counts(record,cp,tolerance) if cp else None,
                offset=offset,limit=limit,sort=sort,targets=targets,rows=rows,subset_fidelity=fidelity,front_preservation=preservation,
                selection=selection,area=area,eligible=eligible,area_capabilities=dict(site=site_available,range=range_available,coverage=bool(metadata['coverage_metrics'])),
                performance_order=performance_order,
                layout_scope=layout_scope,layout_scope_source_count=eligible,sensor_layouts=sensor_groups,
                radar_layouts=sensor_groups if layout_scope=='radar' else [],
                arrangement=arrange,grouping=dict(radius=hamming_radius,selected_group=hamming_group,representatives_only=representatives_only,total_before_group=before_group,groups=groups,policy='PERFORMANCE_ORDERED_LEADER_RADIUS_'+(layout_scope.upper()+'_BITS' if layout_scope!='all' else 'ALL_SENSOR_BITS')+'_BEFORE_PAGING') if grouped else None,
                selection_policy='FULL_PERFORMANCE_THEN_GLOBAL_HAMMING_GROUPS' if grouped else 'EXTREMES_NONDOMINATED_F_THEN_X_THEN_PRIMARY_V1' if selection=='front100' else 'PRIMARY_VALUE_ROUND_ROBIN_MAX_MIN_HAMMING_V1' if selection=='primary100' else 'PERFORMANCE_LEXICOGRAPHIC_THEN_MAX_MIN_HAMMING_EXACT_TIES_V1' if selection=='performance100' else 'COST_ASC_THEN_MAX_MIN_BIT_HAMMING_ARCHIVE_SEED_RAW_ID_TIES_V1' if selection=='diverse100' else 'ALL_SORTED',
                area_policy='CLOSED_GEOMETRIC_REGION_AND_NOMINAL_CIRCULAR_RANGE_NOT_MODEL_QUALITY_V1',
                scope='CURRENT_NONDOMINATED_UNIQUE_X' if selection=='archive' else 'HISTORICAL_NONDOMINATED_UNION_CURRENTLY_DOMINATED_INCLUDED' if selection=='history' else 'OBSERVED_FEASIBLE_UNIQUE_X_INCLUDING_DOMINATED',
                identity_policy='FIRST_FEASIBLE_RAW_ID_PER_EXACT_X_THROUGH_GENERATION')
