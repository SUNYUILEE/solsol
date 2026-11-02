"""Optional posthoc validation; fixed references and physical, unrepaired X.

Indicator implementations reuse pymoo HV/IGDPlus, as program_research does.
All generated rows belong to a diagnostic sidecar, never the optimizer archive.
"""
import copy
import time
from dataclasses import asdict
from pathlib import Path
import numpy as np
from .store import digest,sha,RunStore,record_derivation
from .results import _compiled
from .research_diagnostics import read_diagnostic,metric_definitions,metric_value

DEFINITION='SOLSOL_VALIDATION_DIAGNOSTICS_V1'
DEFINITION_SHA256=sha(Path(__file__))

def problem_identity(cp):
    config=copy.deepcopy(cp.config)
    # These existing model fields configure only search; actual geometry is bound below.
    for k in ('seed','generations','h','initializer','design'):config.pop(k,None)
    config.pop('_research',None)
    return dict(schema='SOLSOL_SCIENTIFIC_PROBLEM_V1',experiment_contract_id=cp.cid,
        model_version=cp.model_version,evaluator_sha256=cp.evaluator_hash,model_config=config,
        candidate_order=list(cp.candidate_order),sites=copy.deepcopy(cp.bundle.sites),sensor_order=list(cp.sensor_order),
        enabled_sensor_ids=list(cp.space.enabled_sensor_ids),allowed=cp.space.allowed.tolist(),co_location=cp.space.co_location,
        objectives=[asdict(next(s for s in cp.objective_specs if s.objective_id==o)) for o in cp.objective_order],
        constraint_order=list(cp.constraint_order),feasibility_tolerance=cp.feasibility_tolerance)

def empirical_reference(records):
    """Explicit union of compatible saved runs, no evaluation and no truth claim."""
    from .runtime import TERMINAL
    if not records:raise ValueError('REFERENCE_RUNS_REQUIRED')
    identities=[];origins=[];points=[]
    for record in records:
        if record.state not in TERMINAL:raise ValueError('REFERENCE_REQUIRES_SAVED_RUN')
        RunStore(record.folder.parent.parent).read(record.folder)
        identities.append(digest(problem_identity(_compiled(record))))
        origins.append(dict(run_id=record.id,experiment_contract_id=record.cid,raw_sha256=sha(record.folder/'raw.json'),state=record.state))
        if record.checkpoints:points.extend(record.rows[i]['F'] for i in record.checkpoints[-1]['archive_ids'])
    if len(set(identities))!=1:raise ValueError('REFERENCE_PROBLEM_MISMATCH')
    if not points:raise ValueError('REFERENCE_EMPTY_FEASIBLE_UNION')
    unique=np.unique(np.asarray(points,float),axis=0)
    keep=[i for i,p in enumerate(unique) if not np.any(np.all(unique<=p,axis=1)&np.any(unique<p,axis=1))]
    out=dict(schema='SOLSOL_REFERENCE_V1',kind='EMPIRICAL',origin=dict(runs=origins,definition='nondominated union of explicitly selected saved cumulative feasible archives; unique exact F; not true front'),problem_sha256=identities[0],F=unique[keep].tolist())
    out['sha256']=digest(out)
    return out

def vector(x,m,label,positive=False):
    a=np.asarray(x,dtype=float)
    if a.shape!=(m,) or not np.isfinite(a).all() or (positive and np.any(a<=0)):raise ValueError('VALIDATION_'+label)
    return a

def indicator_options(cp,o):
    if not isinstance(o,dict) or set(o)-{'hv','igd_plus','normalization','reference_point','reference','checkpoints'}:raise ValueError('INDICATOR_FIELDS')
    if any(type(o.get(k,False)) is not bool for k in ('hv','igd_plus')):raise ValueError('INDICATOR_BOOLEAN')
    n=o.get('normalization')
    if not isinstance(n,dict) or set(n)!={'version','offset','scale'} or not isinstance(n['version'],str) or not n['version']:raise ValueError('FIXED_NORMALIZATION_REQUIRED')
    vector(n['offset'],cp.n_obj,'OFFSET');vector(n['scale'],cp.n_obj,'SCALE',True)
    if o.get('hv'):vector(o.get('reference_point'),cp.n_obj,'HV_REFERENCE')
    checkpoints=o.get('checkpoints')
    if checkpoints is not None and (not isinstance(checkpoints,list) or any(type(g) is not int or g<0 for g in checkpoints) or len(set(checkpoints))!=len(checkpoints)):raise ValueError('INDICATOR_CHECKPOINTS')
    ref=o.get('reference')
    if ref is not None:
        if not isinstance(ref,dict) or set(ref)!={'schema','kind','origin','problem_sha256','F','sha256'} or ref['schema']!='SOLSOL_REFERENCE_V1':raise ValueError('UNSUPPORTED_REFERENCE_SCHEMA')
        if ref['kind'] not in ('EXACT','EMPIRICAL') or not ref['origin']:raise ValueError('REFERENCE_PROVENANCE')
        if ref['sha256']!=digest({k:v for k,v in ref.items() if k!='sha256'}):raise ValueError('REFERENCE_INTEGRITY_ERROR')
        if ref['problem_sha256']!=digest(problem_identity(cp)):raise ValueError('REFERENCE_PROBLEM_MISMATCH')
        a=np.asarray(ref['F'],dtype=float)
        if a.ndim!=2 or a.shape[1]!=cp.n_obj or not len(a) or not np.isfinite(a).all():raise ValueError('REFERENCE_F')
    return copy.deepcopy(o)

def indicators(record,cp,o):
    from pymoo.indicators.hv import HV
    from pymoo.indicators.igd_plus import IGDPlus
    o=indicator_options(cp,o);norm=o['normalization'];offset=np.array(norm['offset']);scale=np.array(norm['scale'])
    ref=o.get('reference');reference=(np.asarray(ref['F'])-offset)/scale if ref else None
    wanted=o.get('checkpoints');saved={c['generation'] for c in record.checkpoints}
    if wanted is not None and set(wanted)-saved:raise ValueError('CHECKPOINT_NOT_SAVED')
    trace=[]
    for c in record.checkpoints:
        if wanted is not None and c['generation'] not in wanted:continue
        f=np.array([record.rows[i]['F'] for i in c['archive_ids']],float).reshape(-1,cp.n_obj);z=(f-offset)/scale
        hv=dict(status='NOT_RUN',reason='Not selected');igd=dict(status='NOT_RUN',reason='Not selected')
        if o.get('hv'):
            point=np.array(o['reference_point']);inside=np.all(z<=point,axis=1);a=z[inside]
            hv=dict(status='OBSERVED',value=float(HV(ref_point=point)(a)) if len(a) else 0.,excluded_outside=int((~inside).sum()),n=len(a))
        if o.get('igd_plus'):
            igd=dict(status='NOT_RUN',reason='REFERENCE_NOT_PROVIDED') if reference is None else dict(status='UNDEFINED_EMPTY_APPROXIMATION',value=None,n=0) if not len(z) else dict(status='OBSERVED',value=float(IGDPlus(reference)(z)),n=len(z))
        trace.append(dict(generation=c['generation'],nfe=c['nfe'],elapsed_seconds=c.get('elapsed_seconds'),archive_raw_ids=c['archive_ids'],hv=hv,igd_plus=igd))
    return dict(status='OBSERVED' if trace else 'EMPTY',options=o,trace=trace,directions=['minimize']*cp.n_obj,
        definition='raw F minimization; z=(F-fixed offset)/positive fixed scale; no per-run fitting; duplicate objective vectors do not affect indicators',
        hv_policy='normalized reference point; exclude any coordinate above reference and count; empty feasible HV=0; points below offset remain unchanged',
        igd_policy='reference raw F transformed with same normalization; empty approximation undefined; missing reference NOT_RUN',
        reference_verification='Declared exact provenance retained; exactness is not automatically certified' if ref and ref['kind']=='EXACT' else 'Empirical reference is not the true front' if ref else 'NOT_PROVIDED',
        interpretation='Archive or HV stability is not proof of global optimality')

def selected_rows(record,raw_ids):
    if not isinstance(raw_ids,list) or not 1<=len(raw_ids)<=5 or any(type(i) is not int for i in raw_ids) or len(set(raw_ids))!=len(raw_ids):raise ValueError('VALIDATION_SELECT_1_TO_5_RAW_IDS')
    archive=record.checkpoints[-1]['archive_ids'] if record.checkpoints else []
    if any(i not in archive for i in raw_ids):raise ValueError('VALIDATION_SELECT_PARETO_RAW_ID')
    return [record.rows[i] for i in raw_ids]

def compact(row,cp):
    return {**{k:copy.deepcopy(row.get(k)) for k in ('X','F','G','cost','cost_components','sensor_counts','named_metrics','metric_status','placement_hash')},
        'feasible':all(g<=cp.feasibility_tolerance for g in row['G'])}

def substitution_options(cp,o):
    if not isinstance(o,dict) or set(o)!={'raw_ids','remove_sensor_id','replacement_sensor_ids','candidate_indices','cost_tolerance','budget','seed'}:raise ValueError('SUBSTITUTION_FIELDS')
    remove=o['remove_sensor_id'];replace=o['replacement_sensor_ids'];indices=o['candidate_indices']
    if remove not in cp.sensor_order or not isinstance(replace,list) or not replace or len(set(replace))!=len(replace) or remove in replace or set(replace)-set(cp.space.enabled_sensor_ids):raise ValueError('SUBSTITUTION_SENSOR_IDS')
    if not isinstance(indices,list) or len(set(indices))!=len(indices) or any(type(i) is not int or not 0<=i<len(cp.candidate_order) for i in indices):raise ValueError('SUBSTITUTION_CANDIDATES')
    if type(o['budget']) is not int or not 1<=o['budget']<=200 or type(o['seed']) is not int or not 0<=o['seed']<=2147483647:raise ValueError('SUBSTITUTION_BUDGET_SEED')
    t=o['cost_tolerance']
    if type(t) not in (int,float) or not np.isfinite(t) or t<0:raise ValueError('SUBSTITUTION_COST_TOLERANCE')
    return copy.deepcopy(o)

def substitutions(record,cp,o,counter,progress=None):
    o=substitution_options(cp,o);sources=selected_rows(record,o['raw_ids']);results=[];rng=np.random.default_rng(o['seed'])
    if progress is not None:progress.update(rows=results,options=o)
    defs=[m for m in metric_definitions(record) if m['source']!='F'];j=cp.sensor_order.index(o['remove_sensor_id'])
    for source in sources:
        x=np.asarray(source['X'],np.uint8).copy();count=int(x[:,j].sum());x[:,j]=0
        item=dict(raw_id=source['id'],physical_placement_identity=source['placement_hash'],before=compact(source,cp),removed_count=count,candidates=[])
        results.append(item)
        if not count:item.update(status='SENSOR_ABSENT',removed=compact(source,cp),evaluations=0);continue
        counter[0]+=1;removed=cp.evaluate_physical(x,validate_installation=False)[0];counter[1]+=1
        item['removed']=compact(removed,cp)
        slots=[(i,cp.sensor_order.index(s)) for i in o['candidate_indices'] for s in o['replacement_sensor_ids'] if cp.space.allowed[i,cp.sensor_order.index(s)] and not x[i,cp.sensor_order.index(s)]]
        seen=set();attempts=0;install_rejected=0
        # Seeded random nonempty subsets; bounded generation attempts, not an exhaustive proof.
        while len(item['candidates'])<o['budget'] and attempts<max(20,o['budget']*20) and slots:
            attempts+=1;n=int(rng.integers(1,len(slots)+1));chosen=tuple(sorted(int(k) for k in rng.choice(len(slots),n,replace=False)))
            if chosen in seen:continue
            seen.add(chosen);candidate=x.copy()
            for k in chosen:candidate[slots[k]]=1
            try:cp.space.validate(candidate,installation=True)
            except ValueError:install_rejected+=1;continue
            counter[0]+=1;after=cp.evaluate_physical(candidate,validate_installation=True)[0];counter[1]+=1
            delta=float(after['cost']-source['cost']);metrics=[]
            for m in defs:
                a,sa=metric_value(source,m);b,sb=metric_value(removed,m);c,sc=metric_value(after,m)
                loss=(a-b if m['direction']=='maximize' else b-a) if None not in (a,b) else None
                recovery=(c-b if m['direction']=='maximize' else b-c) if None not in (b,c) else None
                metrics.append(dict(metric_id=m['id'],before=a,removed=b,replaced=c,statuses=[sa,sb,sc],original_loss=loss,recovery=recovery,recovery_ratio=recovery/loss if loss not in (None,0) and recovery is not None else None,ratio_reason='ZERO_OR_UNOBSERVABLE_LOSS' if loss in (None,0) else None))
            item['candidates'].append(dict(after=compact(after,cp),cost_difference=delta,cost_equivalent=abs(delta)<=o['cost_tolerance'],raw_F_delta_from_original=(np.array(after['F'])-source['F']).tolist(),metrics=metrics))
        matches=sum(c['cost_equivalent'] and c['after']['feasible'] for c in item['candidates'])
        item.update(status='OBSERVED_MATCHES' if matches else 'NOT_FOUND_WITHIN_BUDGET',matching_feasible_count=matches,generation_attempts=attempts,installation_rejections=install_rejected,evaluations=1+len(item['candidates']))
    return dict(status='OBSERVED' if results else 'EMPTY',rows=results,options=o,
        search='seeded random distinct nonempty subsets of allowed unoccupied replacement slots; at most budget evaluator rows per placement plus one removal baseline',
        cost_policy='same frozen evaluator including shared installation cost; abs(replacement cost-original cost)<=user tolerance; retain all actual differences',
        constraints='installation restrictions checked, inventory and model G reported; infeasible candidates retained but not matches; no repair',
        interpretation='No candidate found is not an impossibility proof; no automatic replacement; zero/unobservable loss gives null recovery ratio')

def robustness(record,cp,o,counter,progress=None):
    from .configuration import compile_request
    from .workflow import execution_snapshot,copy_request,diff
    if not isinstance(o,dict) or set(o)!={'raw_ids','variants'} or not isinstance(o['variants'],list) or not 1<=len(o['variants'])<=8:raise ValueError('ROBUSTNESS_FIELDS')
    sources=selected_rows(record,o['raw_ids']);rows=[]
    if progress is not None:progress.update(variants=rows,mode='FIXED_X_CHANGED_CONDITIONS_NOT_REOPTIMIZATION')
    for v in o['variants']:
        if not isinstance(v,dict) or set(v)!={'label','request'} or not isinstance(v['label'],str):raise ValueError('ROBUSTNESS_VARIANT')
        other,opt,_=compile_request(cp.cid,v['request'])
        if other.candidate_order!=cp.candidate_order or other.sensor_order!=cp.sensor_order or other.objective_order!=cp.objective_order:raise ValueError('ROBUSTNESS_PHYSICAL_OR_OBJECTIVE_ORDER_MISMATCH')
        variant=dict(label=v['label'],changes=diff(copy_request(record),v['request']),execution_snapshot=execution_snapshot(other,opt,v['request']),problem_sha256=digest(problem_identity(other)),rows=[]);rows.append(variant)
        for source in sources:
            counter[0]+=1;after=other.evaluate_physical(source['X'],validate_installation=False)[0];counter[1]+=1
            try:other.space.validate(source['X'],installation=True);installation=True
            except ValueError:installation=False
            variant['rows'].append(dict(raw_id=source['id'],physical_placement_identity=source['placement_hash'],before=compact(source,cp),after=compact(after,other),installation_allowed=installation,raw_F_delta=(np.array(after['F'])-source['F']).tolist()))
    return dict(status='OBSERVED',mode='FIXED_X_CHANGED_CONDITIONS_NOT_REOPTIMIZATION',variants=rows,
        interpretation='User-defined conditions; changed evaluator context and original identity both saved. Raw deltas alone do not establish equal metric semantics.')

def analyze(record,options):
    from .runtime import TERMINAL
    if not isinstance(options,dict) or set(options)-{'indicators','substitution','robustness'}:raise ValueError('VALIDATION_DIAGNOSTIC_FIELDS')
    if record.state not in TERMINAL or record.packet(include_rows=False).get('schema')!='SOLSOL_ENGINE_RUN_V1':raise ValueError('VALIDATION_REQUIRES_SAVED_COMMON_RUN')
    RunStore(record.folder.parent.parent).read(record.folder);cp=_compiled(record);start=time.perf_counter();calls=[0,0]
    payload=dict(definition_version=DEFINITION,definition_sha256=DEFINITION_SHA256,options=copy.deepcopy(options),problem_identity=problem_identity(cp),problem_sha256=digest(problem_identity(cp)),search_nfe=record.packet(include_rows=False)['nfe'],status='COMPLETED')
    for key,fn in [('indicators',lambda o,progress:indicators(record,cp,o)),('substitution',lambda o,progress:substitutions(record,cp,o,calls,progress)),('robustness',lambda o,progress:robustness(record,cp,o,calls,progress))]:
        payload[key]=dict(status='NOT_RUN',reason='Not selected')
        if options.get(key) is not None:
            progress={}
            try:payload[key]=fn(options[key],progress)
            except Exception as exc:payload[key]=dict(progress,status='ERROR',error=dict(type=type(exc).__name__,message=str(exc)));payload['status']='ERROR'
    payload.update(additional_evaluations=calls[0],completed_evaluations=calls[1],elapsed_seconds=time.perf_counter()-start,evaluation_count_definition='attempted posthoc rows, successful rows separately; search NFE unchanged')
    ids=[]
    for key in ('substitution','robustness'):
        option=options.get(key)
        if isinstance(option,dict) and isinstance(option.get('raw_ids'),list):ids.extend(i for i in option['raw_ids'] if type(i) is int)
    target=dict(scope='selected saved Pareto rows and/or cumulative checkpoint archives',raw_ids=sorted(set(ids)))
    descriptor=record_derivation(record,DEFINITION,target,calls[0],payload,status=payload['status'])
    return read_diagnostic(record,descriptor['path'][:-5])
