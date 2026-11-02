"""Saved, descriptive Quick Research diagnostics. Never updates optimizer rows."""
import copy
import json
import math
import time
from pathlib import Path
import numpy as np
from .store import digest,sha,record_derivation,RunStore
from .results import _compiled

DEFINITION='SOLSOL_BASIC_DIAGNOSTICS_V1'
LOADED_DEFINITION_SHA256=sha(Path(__file__))
SCOPES=('initial_population','population','cumulative','feasible','archive','qualified')

def quick_preset(cid,request,size):
    from .configuration import compile_request
    from .workflow import execution_snapshot,diff
    if size not in ('small','medium'):raise ValueError('QUICK_PRESET_SIZE')
    q=copy.deepcopy(request);toy=cid=='TOY_DIMENSION_V1';legacy=q['solver_policy']=='legacy_eoir_v1'
    population=(12 if toy else 36) if size=='small' else (24 if toy else 92 if legacy else 72)
    generations=3 if size=='small' else 5
    if legacy:
        q['model_config'].update(h=7 if population==36 else 12,generations=generations)
        q['optimizer']['wallclock_limit_seconds']=120
    else:q['optimizer'].update(population=population,generations=generations,wallclock_limit_seconds=0 if q.get('solver_policy')=='generic_v1' else 120)
    cp,opt,summary=compile_request(cid,q)
    return dict(request=q,changes=diff(request,q),execution_snapshot=execution_snapshot(cp,opt,q),summary=summary,
        rationale='운영용 짧은 탐색 예시; 기존 소형36/1진화 및 toy12/1진화 측정에서 확장. 과학적 적정 예산 기준이 아니며 모델/후보/정확도/제약/seed/solver 정책은 유지합니다.')

def statistics(values,tolerance=0):
    a=sorted(float(v) for v in values if v is not None and math.isfinite(v))
    unique=[]
    for v in a:
        if not unique or v-unique[-1]>tolerance:unique.append(v)
    return dict(status='OBSERVED' if a else 'EMPTY',n=len(a),min=min(a) if a else None,max=max(a) if a else None,
        mean=float(np.mean(a)) if a else None,median=float(np.median(a)) if a else None,
        variance=float(np.var(a)) if a else None,variance_definition='population ddof=0; singleton=0; empty=null',
        unique_count=len(unique),unique_tolerance=tolerance,unique_definition='exact float equality' if tolerance==0 else 'sorted nonoverlapping groups anchored at first value; absolute tolerance')

def saturation(values,direction,threshold,tolerance=0,is_cost=False):
    a=[float(v) for v in values if v is not None and math.isfinite(v)]
    status='NOT_APPLICABLE_COST' if is_cost else 'NOT_CONFIGURED' if threshold is None else 'EMPTY' if not a else 'OBSERVED'
    n=sum(v>=threshold-tolerance if direction=='maximize' else v<=threshold+tolerance for v in a) if status=='OBSERVED' else None
    return dict(status=status,threshold=threshold,threshold_source='USER_ABSOLUTE_VALUE' if threshold is not None else None,
        direction=direction,tolerance=tolerance,count=n,n=len(a),ratio=n/len(a) if n is not None else None,
        definition='maximize >= threshold - tolerance; minimize <= threshold + tolerance; observed max is not a theoretical bound')

def options_checked(options):
    allowed={'scope','generation','unique_placements','unique_tolerance','thresholds','saturation_tolerance','ablation','raw_ids','representatives','correlation','correlation_sample_limit','correlation_seed'}
    if not isinstance(options,dict) or set(options)-allowed:raise ValueError('DIAGNOSTIC_OPTIONS: unknown fields')
    o=dict(scope='archive',generation=None,unique_placements=True,unique_tolerance=0.,thresholds={},saturation_tolerance=0.,ablation=False,raw_ids=[],representatives=3,correlation=False,correlation_sample_limit=300,correlation_seed=1)
    o.update(copy.deepcopy(options))
    if o['scope'] not in SCOPES:raise ValueError('DIAGNOSTIC_SCOPE')
    if o['generation'] is not None and (type(o['generation']) is not int or o['generation']<0):raise ValueError('DIAGNOSTIC_GENERATION')
    if any(type(o[k]) is not bool for k in ('unique_placements','ablation','correlation')):raise ValueError('DIAGNOSTIC_BOOLEAN')
    for k in ('unique_tolerance','saturation_tolerance'):
        if type(o[k]) not in (int,float) or not math.isfinite(o[k]) or o[k]<0:raise ValueError('DIAGNOSTIC_TOLERANCE')
    if not isinstance(o['thresholds'],dict) or any(not isinstance(k,str) or type(v) not in (int,float) or not math.isfinite(v) for k,v in o['thresholds'].items()):raise ValueError('DIAGNOSTIC_THRESHOLDS')
    if not isinstance(o['raw_ids'],list) or len(o['raw_ids'])>5 or len(set(o['raw_ids']))!=len(o['raw_ids']) or any(type(i) is not int or i<0 for i in o['raw_ids']):raise ValueError('DIAGNOSTIC_RAW_IDS')
    for k,lo,hi in [('representatives',3,5),('correlation_sample_limit',2,300),('correlation_seed',0,2147483647)]:
        if type(o[k]) is not int or not lo<=o[k]<=hi:raise ValueError('DIAGNOSTIC_'+k.upper())
    return o

def select_sample(record,options):
    o=options_checked(options);p=record.packet(include_rows=False);cps=record.checkpoints
    gen=o['generation'] if o['generation'] is not None else (cps[-1]['generation'] if cps else None)
    if gen is not None and not any(c['generation']==gen for c in cps):raise ValueError('DIAGNOSTIC_GENERATION_NOT_SAVED')
    if o['scope']=='initial_population':gen=0 if cps else None
    cp=next((c for c in cps if c['generation']==gen),None);stop=cp['nfe'] if cp else 0
    tol=p['archive_policy']['tolerance']
    if o['scope'] in ('initial_population','population'):ids=list(cp['population_ids']) if cp else []
    elif o['scope'] in ('archive','qualified'):ids=list(cp['archive_ids']) if cp else []
    else:ids=list(range(stop))
    if o['scope']=='feasible':ids=[i for i in ids if all(g<=tol for g in record.rows[i]['G'])]
    reason=None
    if o['scope']=='qualified':
        if p['config'].get('_research',{}).get('goals') is None:reason='GOALS_NOT_CONFIGURED'
        ids=[i for i in ids if record.rows[i].get('qualified') is True]
    before=list(ids)
    if o['unique_placements']:
        seen=set();ids=[i for i in ids if not (record.rows[i]['placement_hash'] in seen or seen.add(record.rows[i]['placement_hash']))]
    return [record.rows[i] for i in ids],dict(scope=o['scope'],generation=gen,nfe_boundary=stop,raw_ids=ids,source_count=len(before),sample_count=len(ids),
        duplicate_policy='first placement_hash occurrence' if o['unique_placements'] else 'include repeated X and population ID occurrences',removed_duplicates=len(before)-len(ids),
        feasibility_tolerance=tol,status=reason or ('OBSERVED' if ids else 'EMPTY'),population_semantics='saved survivor population, not offspring or cumulative rows')

def metric_definitions(record):
    p=record.packet(include_rows=False);meta=(p['config'].get('_research') or p['problem'].get('research_configuration',{})).get('metadata',{})
    specs={m['id']:m for m in meta.get('metrics',[])};defs=[]
    for j,key in enumerate(p['registry']['objective_order']):
        m=specs.get(key,{})
        defs.append(dict(id='F:'+key,source='F',index=j,name='원시 F · '+m.get('name',key),direction='minimize',unit='optimizer_scale',is_cost=key=='cost',metric_id=key))
    for key in dict.fromkeys([*p['registry']['objective_order'],*p.get('compilation',{}).get('diagnostic_ids',[]),'cost']):
        m=specs.get(key)
        if m:defs.append(dict(id=key,source='named_metrics',name=m['name'],direction=m['direction'],unit=m['unit'],display_scale=m.get('display_scale',1),is_cost=key=='cost',metric_id=key))
    for m in meta.get('coverage_metrics',[]):defs.append(dict(id=m['id'],source='coverage_metrics',name=m['name'],direction='maximize',unit='%',is_cost=False,metric_id=m['id']))
    return defs

def metric_value(row,m):
    status=row.get('metric_status',{}).get(m['metric_id'],'DEFINED') if m['source']=='named_metrics' else 'DEFINED'
    if status!='DEFINED':return None,status
    v=row['F'][m['index']] if m['source']=='F' else row.get(m['source'],{}).get(m['id'])
    if v is None:return None,'NOT_RECORDED'
    if not math.isfinite(v):return None,'NONFINITE'
    return float(v)*m.get('display_scale',1),'DEFINED'

def cost_relation(rows,definitions):
    metrics=[m for m in definitions if m['source']!='F' and not m['is_cost']];groups=[];prev={}
    for cost in sorted(set(r['cost'] for r in rows)):
        rs=[r for r in rows if r['cost']==cost];values=[]
        for m in metrics:
            a=[metric_value(r,m)[0] for r in rs];s=statistics(a);best=s['max'] if m['direction']=='maximize' else s['min'];prior=prev.get(m['id']);slope=None
            if best is not None and prior is not None:
                slope=((best-prior[1]) if m['direction']=='maximize' else (prior[1]-best))/(cost-prior[0])
            if best is not None:prev[m['id']]=(cost,best)
            values.append(dict(metric_id=m['id'],range=s,observed_best=best,benefit_change_per_cost=slope))
        groups.append(dict(cost=cost,raw_ids=[r['id'] for r in rs],placement_hashes=[r['placement_hash'] for r in rs],n=len(rs),metrics=values))
    return dict(status='OBSERVED' if groups else 'EMPTY',groups=groups,definition='exact equal-cost groups preserve all sampled raw IDs; adjacent observed best benefit / positive cost difference',recommendation=None)

def correlations(rows,definitions,o):
    from scipy.stats import rankdata
    rng=np.random.default_rng(o['correlation_seed']);sample=rows
    if len(rows)>o['correlation_sample_limit']:sample=[rows[int(i)] for i in sorted(rng.choice(len(rows),o['correlation_sample_limit'],replace=False))]
    metrics=[m for m in definitions if m['source']!='F'];result=[]
    for i,a in enumerate(metrics):
        for b in metrics[i+1:]:
            pairs=[(metric_value(r,a)[0],metric_value(r,b)[0]) for r in sample];pairs=[p for p in pairs if None not in p]
            x=np.array([p[0]*(1 if a['direction']=='maximize' else -1) for p in pairs]);y=np.array([p[1]*(1 if b['direction']=='maximize' else -1) for p in pairs])
            status='INSUFFICIENT_SAMPLE' if len(x)<2 else 'CONSTANT_OBJECTIVE' if np.ptp(x)==0 or np.ptp(y)==0 else 'OBSERVED'
            conflict=valid=ties=0
            for j in range(len(x)):
                dx=x[j]-x[:j];dy=y[j]-y[:j];active=(dx!=0)&(dy!=0);valid+=int(active.sum());ties+=int((~active).sum());conflict+=int(((dx*dy<0)&active).sum())
            result.append(dict(left=a['id'],right=b['id'],status=status,n=len(x),pearson=float(np.corrcoef(x,y)[0,1]) if status=='OBSERVED' else None,
                spearman=float(np.corrcoef(rankdata(x),rankdata(y))[0,1]) if status=='OBSERVED' else None,conflict_ratio=conflict/valid if valid else None,conflicting_pairs=conflict,comparable_pairs=valid,tied_pairs=ties))
    return dict(status='OBSERVED',rows=result,raw_ids=[r['id'] for r in sample],seed=o['correlation_seed'],limit=o['correlation_sample_limit'],sampled=len(sample)!=len(rows),
        definition='benefit oriented: maximize value, minimize negative value; Pearson; Spearman average tie ranks; conflict over pairs changing both metrics; no redundancy decision')

def ablations(record,o,counter):
    cp=_compiled(record);p=record.packet(include_rows=False);cps=record.checkpoints
    gen=o['generation'] if o['generation'] is not None else (cps[-1]['generation'] if cps else None)
    checkpoint=next((c for c in cps if c['generation']==gen),None)
    archive=[record.rows[i] for i in checkpoint['archive_ids']] if checkpoint else []
    archive=sorted(archive,key=lambda r:(r['cost'],r['placement_hash'],r['id']))
    seen=set();archive=[r for r in archive if not (r['placement_hash'] in seen or seen.add(r['placement_hash']))]
    ids=o['raw_ids'] or [archive[int(i)]['id'] for i in np.unique(np.linspace(0,len(archive)-1,min(o['representatives'],len(archive))).round().astype(int))] if archive else o['raw_ids']
    if any(i not in (checkpoint['archive_ids'] if checkpoint else []) for i in ids):raise ValueError('ABLATION_SELECT_PARETO_RAW_ID_AT_GENERATION')
    results=[];defs=[m for m in metric_definitions(record) if m['source']!='F']
    for raw_id in ids:
        source=record.rows[raw_id]
        for j,sensor in enumerate(cp.sensor_order):
            x=np.asarray(source['X'],dtype=np.uint8).copy();count=int(x[:,j].sum());x[:,j]=0
            if count:
                counter[0]+=1
                try:after=cp.evaluate_physical(x,validate_installation=False)[0]
                except Exception as exc:
                    return dict(status='ERROR',rows=results,raw_ids=ids,error=dict(type=type(exc).__name__,message=str(exc),raw_id=raw_id,sensor_type_id=sensor,attempted_X=x.tolist()),selection_rule='explicit selected IDs' if o['raw_ids'] else 'evenly spaced unique archive cost ranks',definition='Completed removal rows retained; failed evaluation is not a scientific failure')
                if len(counter)>1:counter[1]+=1
            else:after=copy.deepcopy(source)
            delta=[float(b-a) for a,b in zip(source['F'],after['F'])];loss=[]
            for m in defs:
                a,sa=metric_value(source,m);b,sb=metric_value(after,m)
                loss.append(dict(metric_id=m['id'],before=a,after=b,before_status=sa,after_status=sb,performance_loss=(a-b if m['direction']=='maximize' else b-a) if a is not None and b is not None else None,direction=m['direction']))
            results.append(dict(raw_id=raw_id,physical_placement_identity=source['placement_hash'],sensor_type_id=sensor,status='OBSERVED' if count else 'SENSOR_ABSENT',removed_count=count,
                before=dict(X=source['X'],F=source['F'],G=source['G'],cost=source['cost'],named_metrics=source.get('named_metrics'),metric_status=source.get('metric_status'),feasible=all(g<=cp.feasibility_tolerance for g in source['G'])),
                after=dict(X=x.tolist(),F=after['F'],G=after['G'],cost=after['cost'],named_metrics=after.get('named_metrics'),metric_status=after.get('metric_status'),feasible=all(g<=cp.feasibility_tolerance for g in after['G']),placement_hash=after['placement_hash']),
                raw_F_delta=delta,cost_reduction=float(source['cost']-after['cost']),metrics=loss,evaluations=1 if count else 0))
    return dict(status='OBSERVED' if results else 'EMPTY',rows=results,raw_ids=ids,selection_rule='explicit selected Pareto raw IDs' if o['raw_ids'] else 'unique placement archive sorted cost, placement_hash, raw_id; evenly spaced rank including extremes; up to '+str(o['representatives']),
        definition='whole sensor column zero; no repair/replacement/reoptimization; raw delta=after-before, performance loss=max before-after/min after-before; undefined observations give null loss')

def analyze(record,options):
    from .runtime import TERMINAL
    if record.packet(include_rows=False).get('schema')!='SOLSOL_ENGINE_RUN_V1':raise ValueError('UNSUPPORTED_DIAGNOSTIC_MODEL: legacy result lacks common sample contract')
    if record.state not in TERMINAL:raise ValueError('DIAGNOSTIC_WAIT_FOR_SAVED_RUN')
    RunStore(record.folder.parent.parent).read(record.folder)
    o=options_checked(options);start=time.perf_counter();calls=[0,0];p=record.packet(include_rows=False)
    defs=metric_definitions(record)
    if set(o['thresholds'])-{m['id'] for m in defs}:raise ValueError('UNKNOWN_DIAGNOSTIC_METRIC')
    rows,target=select_sample(record,o)
    payload=dict(definition_version=DEFINITION,definition_sha256=LOADED_DEFINITION_SHA256,options=o,target=target,search_nfe=p['nfe'],search_elapsed_seconds=p.get('elapsed_seconds'),
        identity=dict(run_id=record.id,experiment_contract_id=record.cid,config_sha256=p['config_sha256'],evaluator_sha256=p['evaluator_sha256']),
        observation='Descriptive measurements only; saturation or low contribution is not failure and does not approve objectives',status='COMPLETED')
    try:
        values=[]
        for m in defs:
            observations=[metric_value(r,m) for r in rows];v=[x[0] for x in observations];states={s:sum(t==s for _,t in observations) for _,s in observations}
            values.append(dict(metric=m,range=statistics(v,o['unique_tolerance']),observation_status_counts=states,saturation=saturation(v,m['direction'],o['thresholds'].get(m['id']),o['saturation_tolerance'],m['is_cost'])))
        payload.update(metrics=values,cost_relation=cost_relation(rows,defs))
        ablation_options=dict(o,generation=target['generation'])
        payload['ablation']=dict(status='NOT_RUN',reason='Optional fixed-evaluator operation')
        payload['correlation']=dict(status='NOT_RUN',reason='Optional pairwise analysis')
        if o['ablation']:
            payload['ablation']=dict(status='ERROR',reason='Fixed evaluator operation did not complete',generation=target['generation'])
            payload['ablation']=dict(ablations(record,ablation_options,calls),generation=target['generation'])
            if payload['ablation']['status']=='ERROR':payload.update(status='ERROR',error=payload['ablation']['error'])
        if o['correlation']:payload['correlation']=correlations(rows,defs,o)
    except Exception as exc:
        payload.update(status='ERROR',error=dict(type=type(exc).__name__,message=str(exc)))
    payload.update(additional_evaluations=calls[0],completed_evaluations=calls[1],evaluation_count_definition='attempted evaluator rows; completed_evaluations separately counts successful rows; never search NFE',elapsed_seconds=time.perf_counter()-start)
    descriptor=record_derivation(record,DEFINITION,target,calls[0],payload,status=payload['status'])
    return read_diagnostic(record,descriptor['path'][:-5])

def read_diagnostic(record,diagnostic_id):
    import uuid
    if str(uuid.UUID(diagnostic_id))!=diagnostic_id:raise ValueError('INVALID_DIAGNOSTIC_ID')
    from .workflow import sidecar_index
    entry=next((x for x in sidecar_index(record) if x['path']==diagnostic_id+'.json'),None)
    if not entry:raise KeyError('DIAGNOSTIC_NOT_FOUND')
    if entry['status'] in ('INTEGRITY_ERROR','UNSUPPORTED_SCHEMA'):raise ValueError(entry['status'])
    d=json.loads((record.folder/'diagnostics'/entry['path']).read_text(encoding='utf-8'))
    return dict(diagnostic_id=diagnostic_id,sidecar=d,file_sha256=entry['sha256'])

def list_diagnostics(record):
    from .workflow import sidecar_index
    result=[]
    for entry in sidecar_index(record):
        item=dict(entry,diagnostic_id=entry['path'][:-5])
        if entry['status'] not in ('INTEGRITY_ERROR','UNSUPPORTED_SCHEMA'):
            d=json.loads((record.folder/'diagnostics'/entry['path']).read_text(encoding='utf-8'));item.update(kind=d['kind'],definition_version=d.get('payload',{}).get('definition_version'),options=d.get('payload',{}).get('options'))
        result.append(item)
    return dict(run_id=record.id,experiment_contract_id=record.cid,diagnostics=result)
