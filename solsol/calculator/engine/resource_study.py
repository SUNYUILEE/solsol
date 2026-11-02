"""Resource/range experiments composed from the existing saved-run lifecycle."""
import copy,itertools,math
import numpy as np
from .store import digest,sha
from .hard_constraints import reports
from .quality_values import feasible_fg

VERSION='RESOURCE_SCARCITY_V1'
RADIUS_FIELDS={'ABC_COVERAGE_RESOURCE_V1':{'A':'A_radius','B':'B_radius','C':'C_radius'}}

def compose(cid,body):
    if not isinstance(body,dict) or set(body)!={'base_request','budgets','radius_levels_m','seeds'}:raise ValueError('RESOURCE_STUDY_FIELDS')
    if cid not in RADIUS_FIELDS:raise ValueError('RESOURCE_STUDY_MODEL_UNSUPPORTED')
    base=copy.deepcopy(body['base_request']);budgets=body['budgets'];levels=body['radius_levels_m'];seeds=body['seeds']
    if not isinstance(base,dict):raise ValueError('RESOURCE_STUDY_BASE_REQUEST')
    if not isinstance(seeds,list) or not seeds or any(type(s) is not int or not 0<=s<=2147483647 for s in seeds) or len(set(seeds))!=len(seeds):raise ValueError('RESOURCE_STUDY_SEEDS')
    if base.get('experiment_contract_id')!=cid or base.get('solver_policy')!='generic_v1':raise ValueError('RESOURCE_STUDY_GENERIC_REQUEST_REQUIRED')
    resource=base.get('resource_contract') or base.get('model_config',{}).get('_resource_contract')
    if not resource or resource.get('version')!='SHARED_RESOURCES_V1':raise ValueError('RESOURCE_STUDY_RESOURCE_CONTRACT_REQUIRED')
    if not isinstance(budgets,list) or not budgets or any(x is not None and (type(x) not in (int,float) or not math.isfinite(x) or x<0) for x in budgets) or len(set(budgets))!=len(budgets):raise ValueError('RESOURCE_STUDY_BUDGETS')
    if not isinstance(levels,dict) or set(levels)-set(RADIUS_FIELDS[cid]):raise ValueError('RESOURCE_STUDY_RADII')
    for values in levels.values():
        if not isinstance(values,list) or not values or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values) or len(set(values))!=len(values):raise ValueError('RESOURCE_STUDY_RADIUS_VALUES')
    axes=list(levels);variants=[]
    if math.prod(len(levels[k]) for k in axes)*len(budgets)*len(seeds)>64:raise ValueError('VALIDATION_CELL_LIMIT_64: 예산×반경 조합×seed를 64셀 이내로 구성하세요')
    combinations=itertools.product(*(levels[k] for k in axes))
    for radii in combinations:
        for budget in budgets:
            q=copy.deepcopy(base);q.pop('source_run_id',None);q['resource_contract']=copy.deepcopy(resource)
            q['model_config'].pop('_resource_contract',None)
            q['resource_contract']['budget']=dict(mode='OFF',limit=None) if budget is None else dict(mode='MAX',limit=budget)
            config=q['model_config'];parameters=config.get('parameters',config)
            for sensor,value in zip(axes,radii):parameters[RADIUS_FIELDS[cid][sensor]]=value/1000 if cid=='RADAR_EOIR' else value
            label='자원 구간 · B='+('OFF' if budget is None else str(budget))+' · '+','.join(k+'='+str(v)+'m' for k,v in zip(axes,radii))
            variants.append(dict(label=label,request=q))
    return dict(variants=variants,seeds=copy.deepcopy(body['seeds']),diagnostics={})

def front_metrics(rows,indices,tolerance):
    if not rows:return dict(performance_vectors=0,performance_front=0,opposing_pairs=0,total_pairs=0,opposing_pair_fraction=None,example=None,front_example=None)
    f=np.asarray([[r['F'][i] for i in indices] for r in rows],float)
    values,orig=np.unique(f,axis=0,return_index=True)
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
    ids=NonDominatedSorting().do(values,only_non_dominated_front=True)
    pairs=0;example=None
    for i in range(1,len(values)):
        diff=values[:i]-values[i]
        conflict=np.any(diff>tolerance,axis=1)&np.any(diff<-tolerance,axis=1)
        pairs+=int(conflict.sum())
        if example is None and np.any(conflict):
            j=int(np.flatnonzero(conflict)[0]);a=rows[int(orig[j])];b=rows[int(orig[i])]
            example={k:{name:r.get(name) for name in ('id','F','named_metrics','cost','sensor_counts','qualified')} for k,r in [('A',a),('B',b)]}
    total=len(values)*(len(values)-1)//2
    front_example=None
    for i,idx in enumerate(ids[1:],1):
        diff=values[ids[:i]]-values[idx]
        conflict=np.any(diff>tolerance,axis=1)&np.any(diff<-tolerance,axis=1)
        if np.any(conflict):
            other=ids[int(np.flatnonzero(conflict)[0])]
            front_example={k:{name:r.get(name) for name in ('id','F','named_metrics','cost','sensor_counts','qualified')} for k,r in [('A',rows[int(orig[other])]),('B',rows[int(orig[idx])])]} 
            break
    return dict(performance_vectors=len(values),performance_front=len(ids),opposing_pairs=pairs,total_pairs=total,opposing_pair_fraction=pairs/total if total else None,pair_population='SELECTED_ARCHIVE_UNIQUE_PERFORMANCE_VECTORS',example=example,front_example=front_example)

def fixed_conditions(cid,request):
    """Reject comparisons with hidden changes beyond the declared two factors/seed."""
    q=copy.deepcopy(request);q.pop('source_run_id',None)
    q.get('optimizer',{}).pop('seed',None)
    config=q.get('model_config',{});parameters=config.get('parameters',config)
    for field in RADIUS_FIELDS[cid].values():parameters.pop(field,None)
    resource=q.get('resource_contract') or config.pop('_resource_contract',None)
    if not resource:raise ValueError('RESOURCE_STUDY_REQUIRES_SHARED_RESOURCES')
    resource.pop('budget',None);q['resource_contract']=resource
    return digest(q)

def study_list(service,cid):
    result=service.list(cid)
    result['validations']=[v for v in result['validations'] if v.get('state')=='unavailable' or all(c['label'].startswith('자원 구간 · ') for c in service.get(cid,v['validation_id'])['cells'])]
    return result

def compare_budgets(cells,selected_rows):
    comparisons=[]
    for low in cells:
        if not low.get('run_id') or low['budget'] is None:continue
        for high in cells:
            if not high.get('run_id') or low['seed']!=high['seed'] or low['radii_m']!=high['radii_m'] or (high['budget'] is not None and high['budget']<=low['budget']):continue
            changes=[];witness=None
            for lm in low['metrics']:
                hm=next(m for m in high['metrics'] if m['metric']['id']==lm['metric']['id']);m=lm['metric']
                if m['id']=='cost':continue
                key='maximum' if m['direction']=='maximize' else 'minimum';a,b=lm[key],hm[key]
                changes.append(dict(id=m['id'],name=m['name'],direction=m['direction'],lower_best=a,higher_best=b,change=b-a if a is not None and b is not None else None))
            for row in selected_rows[high['run_id']]:
                if row['cost']<=low['budget']+low['tolerance']:continue
                improved=[m['id'] for m in changes if m['lower_best'] is not None and ((row['named_metrics'][m['id']]-m['lower_best'])*(1 if m['direction']=='maximize' else -1)>low['tolerance'])]
                if improved:
                    witness=dict(id=row['id'],cost=row['cost'],named_metrics=row['named_metrics'],improved_metrics=improved);break
            comparisons.append(dict(lower_run_id=low['run_id'],higher_run_id=high['run_id'],seed=low['seed'],radii_m=low['radii_m'],lower_budget=low['budget'],higher_budget=high['budget'],metric_changes=changes,outside_budget_better_witness=witness,status='OBSERVED_BETTER_PERFORMANCE_OUTSIDE_LOWER_BUDGET' if witness else 'NO_OBSERVED_WITNESS',meaning='고예산에서 관측한 개선 배치가 저예산을 초과합니다. 저예산의 전역 최선이 열등하다는 증명은 아닙니다.'))
    return comparisons

def report(service,cid,vid,scope):
    if scope not in ('all','targets'):raise ValueError('RESOURCE_STUDY_SCOPE')
    group=service.get(cid,vid);cells=[];selected_rows={}
    conditions={fixed_conditions(cid,c['request']) for c in group['cells']}
    if len(conditions)!=1:raise ValueError('RESOURCE_STUDY_FIXED_CONDITIONS_MISMATCH: 예산·반경·seed 외 조건이 다릅니다')
    for cell in group['cells']:
        item=dict(cell_id=cell['cell_id'],label=cell['label'],seed=cell['seed'],state=cell['state'],attempts=cell['attempts'])
        if cell['state']!='completed' or not cell['attempts']:
            cells.append(item);continue
        record=service.service.get(cell['attempts'][-1]['run_id'],cid)
        p=record.packet(include_rows=False,compact_checkpoints=True);resource=p['config'].get('_resource_contract')
        if not resource:raise ValueError('RESOURCE_STUDY_REQUIRES_SHARED_RESOURCES')
        tol=p['archive_policy']['tolerance'];audit=reports(record)
        rows=[record.rows[i] for i in record.checkpoints[-1]['archive_ids'] if audit[i]['hard_pass'] and feasible_fg(record.rows[i],tol)]
        research=p['config'].get('_research') or p['problem'].get('research_configuration',{});goals=research.get('goals')
        total=len(rows);targets=None if goals is None else sum(r.get('qualified') is True for r in rows)
        selected=[r for r in rows if r.get('qualified') is True] if scope=='targets' else rows
        selected_rows[record.id]=selected
        indices=[i for i,key in enumerate(p['registry']['objective_order']) if key!='cost']
        costs=[r['cost'] for r in selected];budget=resource['budget'];limit=budget.get('limit') if budget['mode']=='MAX' else None
        metrics=[]
        for metric in research.get('metadata',{}).get('metrics',[]):
            if metric['id'] not in p['registry']['objective_order']:continue
            values=[r['named_metrics'][metric['id']] for r in selected]
            metrics.append(dict(metric=metric,minimum=min(values) if values else None,maximum=max(values) if values else None))
        item.update(run_id=record.id,nfe=len(record.rows),raw_sha256=sha(record.folder/'raw.json'),config_sha256=p['config_sha256'],evaluator_sha256=p['evaluator_sha256'],resource=resource,radii_m=p['problem'].get('radii'),
            model_lineage={k:p['problem'].get('model_service',{}).get(k) for k in ('source_sha256','service_release_sha256')},
            geometry_sha256=digest({k:p['problem'].get(k) for k in ('sites','demand','candidate_order','geometry')}),
            archive_count=total,target_count=targets,selected_count=len(selected),tolerance=tol,scope_status='TARGETS_UNSET' if scope=='targets' and goals is None else 'OBSERVED' if selected else 'EMPTY_OBSERVED_SET',
            budget=limit,cost_min=min(costs) if costs else None,cost_max=max(costs) if costs else None,
            min_slack=limit-max(costs) if costs and limit is not None else None,
            active_budget_count=sum(abs(limit-c)<=tol for c in costs) if limit is not None else None,
            metrics=metrics,performance=front_metrics(selected,indices,tol),objective_order=p['registry']['objective_order'],initialization=p.get('initialization'),
            interpretation='예산 잔여·경계 사용과 성능 간 절충은 별개입니다. 성능만의 비지배값이 여러 개면 이 관측 집합의 최선 배치끼리도 성능이 엇갈립니다. 전체 상반 변화 쌍에는 지배되는 성능 배치도 포함될 수 있어 필연적 절충 강도가 아닙니다. 미발견은 절충 부재의 증명이 아닙니다.')
        cells.append(item)
    completed=[c for c in cells if c.get('run_id')]
    if len({c['geometry_sha256'] for c in completed})>1:raise ValueError('RESOURCE_STUDY_GEOMETRY_CHANGED')
    if len({digest(c['model_lineage']) for c in completed})>1:raise ValueError('RESOURCE_STUDY_MODEL_LINEAGE_CHANGED')
    return dict(schema=VERSION,validation_id=vid,state=group['state'],scope=scope,cells=cells,comparisons=compare_budgets(cells,selected_rows),fixed_conditions_sha256=next(iter(conditions)),global_optimality=False,
        meaning='같은 반경에서 예산을 비교하고, 같은 예산에서 반경을 비교하세요. 여러 seed의 결과는 개별 표시하며 다른 반경의 front를 합치지 않습니다. 낮은 예산에서 전부 미관측·목표미달일 수도 있습니다.')
