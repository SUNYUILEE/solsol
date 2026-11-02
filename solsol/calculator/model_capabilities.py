"""Exact finite coverage/resource cost formulation for the neutral example.

Boolean coverage relations are encoded as OR/AND constraints. This formulation
certifies only the frozen discrete example, not a continuous/physical problem.
"""
import hashlib
from pathlib import Path
import numpy as np
from engine.contracts import digest

VERSION='NEUTRAL_AREA_INITIALIZATION_V1'


def formulation(cp):
    m=cp._physical;c=m.config;n,s=cp.space.shape;points=len(c['points'])
    variables=[];objective=[];constraints=[];lower=[];upper=[];row_ids=[]
    def var(kind,**attrs):
        k=len(variables);variables.append(dict(kind=kind,**attrs));objective.append(0.);return k
    def con(coeff,lo=None,hi=None,label='constraint'):
        constraints.append({k:float(v) for k,v in coeff.items() if v});lower.append(lo);upper.append(hi);row_ids.append(label+':'+str(len(row_ids)))
    def or_variable(inputs,kind,**attrs):
        v=var(kind,**attrs)
        for x in inputs:con({v:1,x:-1},lo=0,label='or_lower')
        con(dict([(v,1)]+[(x,-1) for x in inputs]),hi=0,label='or_upper')
        return v
    installation={};mapping=[]
    for i,j in np.argwhere(cp.space.allowed):
        i=int(i);j=int(j);flat=i*s+j;k=var('installation',flat_X_index=flat,candidate_index=i,sensor_index=j)
        installation[i,j]=k;objective[k]=float(c['sensors'][j]['cost']);mapping.append(dict(variable_index=k,flat_X_index=flat))
    site_vars=[]
    for i in range(n):
        indices=[k for (site,j),k in installation.items() if site==i]
        y=or_variable(indices,'site_activation',candidate_index=i);objective[y]=float(c['sites'][i]['activation_cost']);site_vars.append(y)
        con({k:c['sensors'][j]['resource'] for (site,j),k in installation.items() if site==i},hi=float(c['sites'][i]['capacity']),label='site_capacity')
        if not cp.space.co_location:con({k:1 for k in indices},hi=1,label='co_location')
    for j in range(s):
        sensor=c['sensors'][j]
        con({k:1 for (i,t),k in installation.items() if t==j},lo=sensor['minimum'],hi=sensor['maximum'],label='inventory')
    covered={}
    for j in range(s):
        for p in range(points):
            indices=[k for (i,t),k in installation.items() if t==j and m.visibility[i,j,p]]
            covered[j,p]=or_variable(indices,'sensor_point_coverage',sensor_index=j,point_index=p)
    union=[or_variable([covered[j,p] for j in range(s)],'union_coverage',point_index=p) for p in range(points)]
    relation=[]
    for r in c['relations']:
        ids=[cp.sensor_order.index(k) for k in r['sensors']];values=[]
        for p in range(points):
            z=var('joint_coverage',relation_id=r['id'],point_index=p);values.append(z)
            for j in ids:con({z:1,covered[j,p]:-1},hi=0,label='and_upper')
            con(dict([(z,1)]+[(covered[j,p],-1) for j in ids]),lo=1-len(ids),label='and_lower')
        relation.append(values)
    if c['budget'] is not None:con({k:v for k,v in enumerate(objective)},hi=float(c['budget']),label='budget')
    if c['total_resource'] is not None:con({k:c['sensors'][j]['resource'] for (i,j),k in installation.items()},hi=float(c['total_resource']),label='total_resource')
    goals=cp.config.get('_research',{}).get('goals') or {}
    for key,goal in goals.items():
        if key=='coverage':coeff={union[p]:float(m.weights[p]*100) for p in range(points)}
        elif key=='joint_coverage' and relation:coeff={group[p]:float(m.weights[p]*100/len(relation)) for group in relation for p in range(points)}
        else:raise ValueError('No exact coverage expression for goal '+key)
        con(coeff,lo=float(goal),label='coverage_goal')
    rows=[];cols=[];data=[]
    for i,row in enumerate(constraints):
        for j,value in row.items():rows.append(i);cols.append(j);data.append(value)
    identity=dict(problem_id=cp.problem_id,input_sha256=cp.input_sha256,model_id=cp.cid,model_version=cp.model_version,
        config_sha256=cp.config_hash,evaluator_sha256=cp.evaluator_hash,service_release_sha256=cp.service_identity['service_release_sha256'],source_sha256=cp.model_source_sha256)
    order=dict(candidate_order=list(cp.candidate_order),sensor_order=list(cp.sensor_order),active_slot_order=np.flatnonzero(cp.space.allowed.ravel()).tolist(),
        full_X_shape=list(cp.space.shape),enabled_sensor_ids=list(cp.space.enabled_sensor_ids),allowed=cp.space.allowed.astype(int).tolist(),co_location=cp.space.co_location,codec_slot_order=cp.codec.slots.tolist())
    result=dict(contract_version=VERSION,status='SUPPORTED',identity=identity,order=order,installation_sha256=digest(order),installation_contract='INSTALLATION_SPACE_V1',
        target_source='research_goals',tolerance=cp.feasibility_tolerance,builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        targets=[dict(metric_id=k,epsilon=v,unit='%',value_source='coverage_metrics.'+k) for k,v in goals.items()],
        exactness='EXACT_AREA_GOAL_INTEGER_FORMULATION',variables=variables,integrality=[1]*len(variables),bounds=dict(lower=[0]*len(variables),upper=[1]*len(variables)),
        objective=dict(sense='minimize',metric_id='actual_cost',unit='synthetic_cost',constant=0,c=objective),
        constraints=dict(matrix=dict(format='coo',shape=[len(constraints),len(variables)],row=rows,col=cols,data=data),row_ids=row_ids,lower=lower,upper=upper),
        restoration=dict(default_X_value=0,variable_to_flat_X=mapping),
        acceptance=dict(endpoint='/evaluate-batch',validate_installation=True,require_integer=True,require_same_identity=True,require_G_at_most_tolerance=True,require_all_frozen_area_goals=True),
        bound_scope='EXACT_FROZEN_DISCRETE_NEUTRAL_COVERAGE_RESOURCE_CONTRACT_ONLY')
    result['formulation_sha256']=digest(result)
    return result
