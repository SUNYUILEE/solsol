"""A/B research derived from immutable validation plans and saved Model rows.

No separate solver or mutable study state: B's frozen labels bind its A plan,
selected scope and proposal digest. Existing validation/check lifecycles own work.
"""
import copy, math, re
import numpy as np
from .store import digest, sha
from .hard_constraints import reports
from .quality_values import feasible_fg
from .resource_study import front_metrics

A_LABEL='비용 연구 A · 성능과 비용'
B_PREFIX='비용 연구 B|'

def group(service,cid,vid,kind):
    g=service.get(cid,vid)
    if not g['cells'] or any(not c['label'].startswith(A_LABEL if kind=='A' else B_PREFIX) for c in g['cells']):
        raise ValueError('GUIDED_STUDY_KIND_MISMATCH')
    if kind=='A':
        identities=[]
        for c in g['cells']:
            q=copy.deepcopy(c['request']);q.get('optimizer',{}).pop('seed',None)
            identities.append(digest(q))
            if c['label']!=A_LABEL:raise ValueError('GUIDED_A_LABEL')
        if len(set(identities))!=1:raise ValueError('GUIDED_A_SEED_ONLY_VARIATION')
    else:
        for c in g['cells']:
            parts=c['label'].split('|')
            if len(parts)!=5 or not re.fullmatch('[0-9a-f-]{36}',parts[1]) or parts[2] not in ('all','targets') or not re.fullmatch('[0-9a-f]{64}',parts[3]):raise ValueError('GUIDED_B_LABEL')
            budget=c['request'].get('resource_contract',{}).get('budget',{})
            if budget.get('mode')!='MAX' or float(parts[4])!=budget.get('limit'):raise ValueError('GUIDED_B_BUDGET_BINDING')
    return g

def listed(service,cid):
    studies=[];unavailable=[]
    for item in service.list(cid)['validations']:
        if item.get('state')=='unavailable':continue
        g=service.get(cid,item['validation_id']);labels=[c['label'] for c in g['cells']]
        if labels and all(s.startswith(A_LABEL) for s in labels):studies.append(dict(item,kind='A'))
        elif labels and all(s.startswith('비용 대조 V1|') for s in labels):
            from .guided_control import identity
            try:
                ids=[identity(c) for c in g['cells']]
                if len({v[:3] for v in ids})!=1:raise ValueError('CONTROL_MIXED_PARENT')
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                unavailable.append(dict(validation_id=item['validation_id'],reason=str(exc)));continue
            studies.append(dict(item,kind='B',design='BUDGET_MATCHED_COST_ROLE_V1',a_id=ids[0][0],scope=ids[0][1]))
        elif labels and all(s.startswith(B_PREFIX) for s in labels):
            try:group(service,cid,item['validation_id'],'B')
            except (ValueError,IndexError,TypeError) as exc:
                unavailable.append(dict(validation_id=item['validation_id'],reason=str(exc)));continue
            studies.append(dict(item,kind='B',a_id=labels[0].split('|')[1],scope=labels[0].split('|')[2]))
    return dict(studies=studies,unavailable=unavailable,designs=['LEGACY_AB','BUDGET_MATCHED_COST_ROLE_V1'])

def preview_a(service,cid,body):
    if set(body)!={'base_request','seeds'}:raise ValueError('GUIDED_A_FIELDS')
    q=copy.deepcopy(body['base_request']);q.pop('source_run_id',None)
    if cid!='ABC_COVERAGE_RESOURCE_V1':raise ValueError('GUIDED_MODEL_UNSUPPORTED')
    ids=[v for v in q['objective_ids'] if v!='cost']
    if len(ids)<2:raise ValueError('성능 목적을 두 개 이상 선택하세요. 비용을 제외한 다음 실험에도 필요합니다.')
    q['objective_ids']=ids+['cost'];q['diagnostic_ids']=[v for v in q.get('diagnostic_ids',[]) if v!='cost']
    q['solver_policy']='generic_v1'
    resource=q.get('resource_contract') or q['model_config'].pop('_resource_contract',None)
    if not resource:raise ValueError('먼저 조건 설정에서 공통 예산·수량과 센서 단가를 설정하세요.')
    q['resource_contract']=copy.deepcopy(resource);q['model_config'].pop('_resource_contract',None)
    q['resource_contract']['budget']={'mode':'OFF','limit':None}
    request=dict(variants=[dict(label=A_LABEL,request=q)],seeds=body['seeds'],diagnostics={})
    return dict(request=request,plan=service.preview(cid,request))

def saved(service,cid,cell):
    if cell['state']!='completed':raise ValueError('계산·재평가·저장이 모두 완료된 뒤 다음 단계를 여세요.')
    r=service.service.get(cell['attempts'][-1]['run_id'],cid)
    p=r.packet(include_rows=False,compact_checkpoints=True);audit=reports(r);tol=p['archive_policy']['tolerance']
    feasible=[row for row in r.rows if audit[row['id']]['hard_pass'] and feasible_fg(row,tol)]
    archive=set(r.checkpoints[-1]['archive_ids'])
    return r,p,feasible,[row for row in feasible if row['id'] in archive],tol

def scoped(rows,scope):
    if scope not in ('all','targets'):raise ValueError('GUIDED_SCOPE')
    return [r for r in rows if scope=='all' or r.get('qualified') is True]

def proposal(service,cid,vid,scope):
    g=group(service,cid,vid,'A');samples=[];pins=[];target_costs=[]
    for cell in g['cells']:
        r,p,raw,archive,tol=saved(service,cid,cell)
        resource=p['config'].get('_resource_contract')
        if 'cost' not in p['registry']['objective_order'] or resource['budget']['mode']!='OFF':raise ValueError('GUIDED_A_REQUIRES_COST_OBJECTIVE_BUDGET_OFF')
        for row in scoped(archive,scope):samples.append(dict(cost=row['cost'],run_id=r.id,raw_id=row['id'],seed=cell['seed']))
        target_costs.extend(row['cost'] for row in archive if row.get('qualified') is True)
        pins.append(dict(run_id=r.id,raw_sha256=sha(r.folder/'raw.json'),config_sha256=p['config_sha256'],evaluator_sha256=p['evaluator_sha256']))
    costs=sorted(set(s['cost'] for s in samples));candidates=[]
    for q in (0,.25,.5,.75,1):
        if not costs:break
        value=costs[math.ceil(q*(len(costs)-1))]
        if not any(c['budget']==value for c in candidates):candidates.append(dict(budget=value,reason='관측 고유 비용 분위 '+str(q),source=next(s for s in samples if s['cost']==value)))
    target=min(target_costs) if target_costs else None
    if target is not None and any(s['cost']==target for s in samples) and not any(c['budget']==target for c in candidates):
        candidates.append(dict(budget=target,reason='관측 목표 통과 최소 비용',source=next(s for s in samples if s['cost']==target)))
    out=dict(a_id=vid,scope=scope,pins=pins,candidates=sorted(candidates,key=lambda c:c['budget']),observed_unique_costs=len(costs),observed_target_minimum=target,
        meaning='실제로 관측한 비용에서 다음 실험의 예산 후보를 골랐습니다. 필요한 최소 예산이나 성능 절충 발생을 보장하지 않습니다. 목표 미설정·미통과 집합은 빈 집합으로 유지합니다.')
    out['proposal_sha256']=digest(out);return out

def preview_b(service,cid,body):
    if set(body)!={'a_id','scope','proposal_sha256','budgets'}:raise ValueError('GUIDED_B_FIELDS')
    prop=proposal(service,cid,body['a_id'],body['scope'])
    if prop['proposal_sha256']!=body['proposal_sha256']:raise ValueError('GUIDED_PROPOSAL_CHANGED')
    budgets=body['budgets']
    if not prop['candidates']:raise ValueError('선택한 집합에 관측 비용이 없습니다. 집합 선택을 확인하세요.')
    if not isinstance(budgets,list) or not budgets or any(type(b) not in (int,float) or not math.isfinite(b) or b<0 for b in budgets) or len(set(budgets))!=len(budgets):raise ValueError('유한한 0 이상 예산을 중복 없이 입력하세요.')
    g=group(service,cid,body['a_id'],'A');variants=[]
    # All A seeds share exactly one request except the seed field.
    for budget in budgets:
        q=copy.deepcopy(g['cells'][0]['request']);q['objective_ids']=[v for v in q['objective_ids'] if v!='cost']
        q['resource_contract']['budget']=dict(mode='MAX',limit=budget)
        variants.append(dict(label=B_PREFIX+body['a_id']+'|'+body['scope']+'|'+prop['proposal_sha256']+'|'+str(budget),request=q))
    request=dict(variants=variants,seeds=[c['seed'] for c in g['cells']],diagnostics={})
    return dict(request=request,plan=service.preview(cid,request),proposal=prop)

def fixed(q):
    q=copy.deepcopy(q);q.pop('source_run_id',None);q['objective_ids']=[i for i in q['objective_ids'] if i!='cost'];q['optimizer'].pop('seed',None)
    q['resource_contract'].pop('budget',None);return digest(q)

def compact(row,indices):
    return dict(raw_id=row['id'],X=row['X'],cost=row['cost'],performance_F=[row['F'][i] for i in indices],named_metrics=row.get('named_metrics'),sensor_counts=row.get('sensor_counts'),qualified=row.get('qualified'))

def front(rows,indices):
    if not rows:return []
    rows=sorted(rows,key=lambda r:(r['cost'],r['id']))
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
    f=np.array([[r['F'][i] for i in indices] for r in rows]);values,original=np.unique(f,axis=0,return_index=True)
    return [rows[int(original[i])] for i in NonDominatedSorting().do(values,only_non_dominated_front=True)]

def comparison(service,cid,vid,scope=None):
    g=group(service,cid,vid,'B');labels=[c['label'].split('|') for c in g['cells']]
    if len({tuple(s[1:4]) for s in labels})!=1:raise ValueError('GUIDED_PARENT_MISMATCH')
    a_id,proposal_scope,ph=labels[0][1:4];prop=proposal(service,cid,a_id,proposal_scope)
    scope=proposal_scope if scope is None else scope
    scoped([],scope)
    if ph!=prop['proposal_sha256']:raise ValueError('GUIDED_PROPOSAL_CHANGED')
    ag=group(service,cid,a_id,'A');acells={c['seed']:c for c in ag['cells']};cells=[];acache={}
    target_witnesses=[]
    for ac in ag['cells']:
        acache[ac['seed']]=saved(service,cid,ac)
        ar,ap,araw,aarchive,at=acache[ac['seed']]
        ai=[i for i,v in enumerate(ap['registry']['objective_order']) if v!='cost']
        target_witnesses.extend(dict(compact(row,ai),run_id=ar.id,seed=ac['seed']) for row in aarchive if row.get('qualified') is True)
    target_witnesses.sort(key=lambda x:(x['cost'],x['seed'],x['raw_id']))
    for c in g['cells']:
        if c['state']!='completed':cells.append(dict(cell_id=c['cell_id'],state=c['state'],seed=c['seed']));continue
        ac=acells[c['seed']]
        if fixed(ac['request'])!=fixed(c['request']):raise ValueError('GUIDED_FIXED_CONDITIONS_CHANGED')
        if c['seed'] not in acache:acache[c['seed']]=saved(service,cid,ac)
        ar,ap,araw,aarchive,at=acache[c['seed']];br,bp,braw,barchive,bt=saved(service,cid,c)
        ai=[i for i,v in enumerate(ap['registry']['objective_order']) if v!='cost'];bi=list(range(len(bp['registry']['objective_order'])))
        if [ap['registry']['objective_order'][i] for i in ai]!=list(bp['registry']['objective_order']) or 'cost' in bp['registry']['objective_order']:raise ValueError('GUIDED_PERFORMANCE_AXES_CHANGED')
        lineage=lambda p:{k:p['problem'].get('model_service',{}).get(k) for k in ('source_sha256','service_release_sha256')}
        if lineage(ap)!=lineage(bp):raise ValueError('GUIDED_MODEL_CHANGED')
        if any(ap['registry'][key]!=bp['registry'][key] for key in ('candidate_order','sensor_order')):
            raise ValueError('GUIDED_PHYSICAL_ORDER_CHANGED')
        if any(digest(ap['problem'].get(key))!=digest(bp['problem'].get(key)) for key in ('sites','demand','geometry')):
            raise ValueError('GUIDED_MAP_GEOMETRY_CHANGED')
        budget=c['request']['resource_contract']['budget']['limit'];tol=max(at,bt)
        raw=[r for r in scoped(araw,scope) if r['cost']<=budget+tol];arch=[r for r in scoped(aarchive,scope) if r['cost']<=budget+tol];bs=scoped(barchive,scope)
        af=front(raw,ai);aof=front(arch,ai);bf=front(bs,bi)
        # Choose a displayed example only; never imply every archive row was checked.
        pick=lambda rows,idx:compact(sorted(rows,key=lambda r:(tuple(r['F'][i] for i in idx),r['cost'],r['id']))[0],idx) if rows else None
        metrics=[]
        research=lambda p:p['config'].get('_research') or p['problem'].get('research_configuration',{})
        metadata=research(ap).get('metadata',{}).get('metrics',[])
        for i,key in enumerate(bp['registry']['objective_order']):
            m=next((m for m in metadata if m['id']==key),{'name':key})
            vals=lambda rows:[r['named_metrics'][key] for r in rows]
            av,bv=vals(af),vals(bf)
            metrics.append(dict(id=key,name=m['name'],unit=m.get('unit'),direction=m.get('direction'),a_range=[min(av),max(av)] if av else None,b_range=[min(bv),max(bv)] if bv else None))
        cells.append(dict(cell_id=c['cell_id'],state=c['state'],seed=c['seed'],budget=budget,a_run_id=ar.id,b_run_id=br.id,
            a_raw_sha256=sha(ar.folder/'raw.json'),b_raw_sha256=sha(br.folder/'raw.json'),axes=bp['registry']['objective_order'],metrics=metrics,
            sensor_labels=[next((s['name'] for s in research(bp).get('metadata',{}).get('sensors',[]) if s['id']==key),key) for key in bp['registry']['sensor_order']],
            a_original_archive_eligible=len(arch),a_raw_eligible=len(raw),a_archive_performance_front=len(aof),a_raw_performance_front=len(af),b_archive_count=len(bs),b_performance_front=len(bf),
            b_all_archive_count=len(barchive),b_target_count=sum(r.get('qualified') is True for r in barchive),
            goals_configured=research(bp).get('goals') is not None,
            accounting={side:dict(search_nfe=p.get('nfe'),counters=p.get('counters'),initialization=p.get('initialization'),attempts=cc['attempts']) for side,p,cc in [('a',ap,ac),('b',bp,c)]},
            a_target_witness=next((r for r in target_witnesses if r['cost']<=budget+tol),None),
            a_example=pick(af,ai),b_example=pick(bf,bi),b_conflict=front_metrics(bf,bi,tol)['front_example'],
            min_budget_slack=min((budget-r['cost'] for r in bs),default=None)))
    from .research_explanation import explain
    for cell in cells:
        cell['explanation']=explain(cell,scope)
        if cell.get('b_conflict'):
            record=service.service.get(cell['b_run_id'],cid)
            for witness in cell['b_conflict'].values():witness['X']=record.rows[witness['id']]['X']
    return dict(a_id=a_id,b_id=vid,scope=scope,proposal_scope=proposal_scope,state=g['state'],proposal=prop,cells=cells,global_optimality=False,
        meaning='A는 같은 예산 이하의 관측 원시·원래 archive를 각각 공통 성능 축으로 다시 비교합니다. B는 비용을 목적에서 제외한 새 탐색입니다. 예산을 고른 집합과 현재 표시 집합은 별개이며 서로 다른 차원의 HV는 비교하지 않습니다.')

def classify_performance(base,row,indices):
    """Exact stored-value dominance, distinct from tolerant G feasibility."""
    f=np.array([row['F'][i] for i in indices]);b=np.array([base['F'][i] for i in indices])
    strict=bool(np.all(f<=b) and np.any(f<b))
    equal_saving=bool(np.array_equal(f,b) and row['cost']<base['cost'])
    return strict,equal_saving,f.tolist()

def check_result(record,key,raw_id,budget,scope):
    from . import quality_jobs as qj
    state=qj.get(record,key)
    if state['source_ids']!=[raw_id] or state['method']!='local':raise ValueError('GUIDED_CHECK_SOURCE_MISMATCH')
    base=record.rows[raw_id];order=record.packet(include_rows=False)['registry']['objective_order'];indices=[i for i,k in enumerate(order) if k!='cost'];tol=state.get('tolerance',1e-9)
    strict=[];saving=[]
    if state['status']=='COMPLETED' and state.get('scope_complete'):
        for item in qj.stored_entries(record,state):
            row=item.get('row',item);seq=item.get('sequence')
            if not row.get('feasible') or row['cost']>budget+tol or (scope=='targets' and row.get('qualified') is not True):continue
            improves,equal_saving,f=classify_performance(base,row,indices)
            evidence=dict(sequence=seq,cost=row['cost'],performance_F=f,operation=row.get('operation'),source_raw_id=raw_id,provenance='POSTHOC_CHECK_NOT_OPTIMIZER')
            if improves:strict.append(evidence)
            if equal_saving:saving.append(evidence)
    return dict(job_id=key,run_id=record.id,raw_id=raw_id,status=state['status'],phase=state['phase'],evaluated=state['evaluated'],total=state['total'],scope_complete=state.get('scope_complete',False),strict_performance_improvements=strict,equal_performance_cost_savings=saving,performance_comparison='EXACT_STORED_VALUES',feasibility_tolerance=tol,
        meaning='이 원시 행 하나의 설치 마스크 안에서 전체 1회 삭제·추가·동일 센서 이동을 확인합니다. 비용 절감과 엄격한 성능 개선을 분리합니다. 전체 해집합·전역 검증이 아닙니다.')

def checks(service,cid,body):
    if set(body)-{'b_id','cell_id','a_job','b_job','scope'} or not {'b_id','cell_id','a_job','b_job'}<=set(body):raise ValueError('GUIDED_CHECK_FIELDS')
    report=comparison(service,cid,body['b_id'],body.get('scope'));cell=next(c for c in report['cells'] if c['cell_id']==body['cell_id']);results=[]
    for side in ('a','b'):
        example=cell[side+'_example']
        if not example:raise ValueError('비교할 관측 배치가 없습니다.')
        results.append(check_result(service.service.get(cell[side+'_run_id'],cid),body[side+'_job'],example['raw_id'],cell['budget'],report['scope']))
    return dict(results=results,complete=all(r['status']=='COMPLETED' and r['scope_complete'] for r in results),comparison=cell)

def placement_checks(service,cid,body):
    """Read complete stored single-delete evidence for the displayed B witnesses."""
    from . import quality_jobs as qj
    from .placement_selection import distance_to_area
    if set(body)!={'b_id','cell_id','scope'}:raise ValueError('GUIDED_PLACEMENT_CHECK_FIELDS')
    report=comparison(service,cid,body['b_id'],body['scope']);cell=next(c for c in report['cells'] if c['cell_id']==body['cell_id'])
    if not cell.get('b_conflict'):return dict(results=[],meaning='선택 집합에서 성능 교차 배치 쌍이 관측되지 않았습니다.')
    record=service.service.get(cell['b_run_id'],cid);p=record.packet(include_rows=False);listing=qj.listing(record);results=[]
    for example in cell['b_conflict'].values():
        matches=[j for j in listing['jobs'] if j.get('definition_sha256')==listing['definition_sha256'] and j.get('method')=='local' and j.get('source_ids')==[example['id']]]
        state=next((j for j in matches if j['status']=='COMPLETED' and j.get('scope_complete')),matches[0] if matches else None)
        if not state:results.append(dict(raw_id=example['id'],status='NOT_RUN',deletions=[]));continue
        result=check_result(record,state['job_id'],example['id'],cell['budget'],report['scope']);deletions=[]
        if result['status']=='COMPLETED' and result['scope_complete']:
            for entry in qj.stored_entries(record,state):
                row=entry.get('row',entry)
                if row.get('operation')!='one_delete':continue
                delta=np.asarray(example['X'],int)-np.asarray(row['X'],int);slots=np.argwhere(delta==1)
                if len(slots)!=1 or np.count_nonzero(delta)!=1:raise ValueError('GUIDED_DELETE_NOT_ONE_SLOT')
                site,sensor=map(int,slots[0]);distance=distance_to_area(p['problem']['sites'][site],p['problem'].get('geometry'))
                same=np.array_equal(row['F'],example['F']);admissible=bool(row.get('feasible')) and (report['scope']=='all' or row.get('qualified') is True)
                deletions.append(dict(sequence=entry.get('sequence'),candidate_index=site,sensor_index=sensor,sensor=cell['sensor_labels'][sensor],outside_evaluation_area=None if distance is None else distance>1e-7,cost=row['cost'],cost_change=row['cost']-example['cost'],same_performance=bool(same),feasible=row.get('feasible'),qualified=row.get('qualified'),admissible=admissible,
                    meaning='선택 성능 동일·비용 절감·현재 표시 조건 유지' if same and row['cost']<example['cost'] and admissible else '제약 또는 현재 표시 조건 미달' if not admissible else '선택 성능 변화 있음' if not same else '선택 성능 동일·비용 절감 없음',
                    performance_changes={key:row['named_metrics'][key]-example['named_metrics'][key] for key in cell['axes']}))
        result['deletions']=deletions;results.append(result)
    return dict(run_id=record.id,results=results,meaning='각 원시 배치에서 센서 하나를 삭제한 실제 공개 Model 재평가입니다. 같은 성능·비용 절감은 표시한 목적과 목표 범위의 판정이며 전체 실용성·전역 최적 판정이 아닙니다. 수량 제약 미달 삭제는 대체 가능한 배치가 아닙니다.')
