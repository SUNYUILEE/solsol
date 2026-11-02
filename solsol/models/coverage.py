"""New abstract coverage/shared-resource model. No inherited device physics."""
import copy
import math

import numpy as np

from solsol.engine.contracts import digest
from solsol.engine.placement import PlacementSpace
from solsol.engine.inventory import validate_resources
from solsol.geometry import visible

MODEL_ID='ABC_COVERAGE_RESOURCE_V1'
VERSION='1.0.0'


def number(value,label,minimum=None,maximum=None,integer=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(label+' must be finite numeric')
    if integer and (type(value) is not int):raise ValueError(label+' must be integer')
    if minimum is not None and value<minimum:raise ValueError(label+' below minimum')
    if maximum is not None and value>maximum:raise ValueError(label+' above maximum')
    return value


def records(value,label,allow_empty=False):
    if not isinstance(value,list) or (not value and not allow_empty):raise ValueError(label+' requires a list')
    ids=[]
    for row in value:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'].strip():
            raise ValueError(label+' requires nonempty string IDs')
        ids.append(row['id'])
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate '+label+' ID')
    return ids


class CoverageModel:
    model_id=MODEL_ID
    evaluator_version=VERSION

    def __init__(self,config):
        try:self._build(copy.deepcopy(config))
        except (KeyError,TypeError,OverflowError) as exc:raise ValueError('Malformed coverage configuration: '+str(exc)) from exc

    @property
    def config(self):return copy.deepcopy(self._config)

    def _build(self,c):
        if not isinstance(c,dict) or c.get('model_id')!=MODEL_ID:raise ValueError('Unsupported model_id')
        if c.get('units')!='metres':raise ValueError('Cartesian metres required')
        if type(c.get('los')) is not bool or type(c.get('co_location')) is not bool:
            raise ValueError('LOS and co_location require booleans')
        sensors=c['sensors'];sites=c['sites'];points=c['points']
        ss=records(sensors,'sensor');cs=records(sites,'site');ps=records(points,'point')
        if len(ss)*len(cs)>5000 or len(ss)*len(cs)*len(ps)>10000000:
            raise ValueError('Example model geometry budget exceeded')
        for sensor in sensors:
            for k in ['radius','height','cost','resource']:number(sensor[k],k,0)
            for k in ['minimum','maximum']:number(sensor[k],k,0,integer=True)
            if sensor['minimum']>sensor['maximum']:raise ValueError('Inventory minimum exceeds maximum')
        for site in sites:
            for k in ['x','y','z']:number(site[k],k)
            for k in ['capacity','activation_cost']:number(site[k],k,0)
            allowed=site.get('allowed',ss)
            if not isinstance(allowed,list) or not allowed or len(set(allowed))!=len(allowed) or set(allowed)-set(ss):
                raise ValueError('Invalid site allowed sensors')
        for point in points:
            for k in ['x','y','z']:number(point[k],k)
            number(point['weight'],'point weight',0)
        if max(p['weight'] for p in points)<=0:raise ValueError('Positive total point weight required')
        relations=c['relations'];records(relations,'relation',allow_empty=True)
        for r in relations:
            ids=r['sensors']
            if not isinstance(ids,list) or len(ids)<2 or len(set(ids))!=len(ids) or set(ids)-set(ss):
                raise ValueError('Relation needs at least two distinct known sensor IDs')
        obstacles=c['obstacles']
        if not isinstance(obstacles,list):raise ValueError('Obstacles require a list')
        for b in obstacles:
            for axis in 'xyz':
                number(b[axis+'min'],axis+'min');number(b[axis+'max'],axis+'max')
                if b[axis+'min']>=b[axis+'max']:raise ValueError('Invalid prism extents')
        for k in ['budget','total_resource']:
            if c[k] is not None:number(c[k],k,0)
        goals=c['goals']
        if not isinstance(goals,dict) or set(goals)-{'coverage','joint_coverage'}:raise ValueError('Unknown goals')
        for k,v in goals.items():number(v,k,0,1)
        if not relations and 'joint_coverage' in goals:raise ValueError('Joint goal requires relations')
        objectives=c['objectives']
        available={'coverage','joint_coverage','cost'} if relations else {'coverage','cost'}
        if not isinstance(objectives,list) or len(objectives)<2 or len(set(objectives))!=len(objectives) or set(objectives)-available:
            raise ValueError('Choose two or more available distinct objectives')
        self.objective_ids=objectives.copy()
        self.space=PlacementSpace(cs,ss,dataset_id=digest(dict(sites=sites,points=points)),
            allowed=[[s in site.get('allowed',ss) for s in ss] for site in sites],co_location=c['co_location'])
        self.inventory_rule=dict(mode='partial',lower=[s['minimum'] for s in sensors],upper=[s['maximum'] for s in sensors])
        validate_resources(self.space,self.inventory_rule)
        self.constraint_ids=([f'inventory_min:{s}' for s in ss]+[f'inventory_max:{s}' for s in ss]+
            [f'site_capacity:{i}' for i in cs]+(['budget'] if c['budget'] is not None else [])+
            (['total_resource'] if c['total_resource'] is not None else [])+[f'goal:{k}' for k in goals])
        self._config=c
        self.contract_id=digest(dict(model_id=MODEL_ID,evaluator_version=VERSION,config=c))
        self.weights=np.array([p['weight'] for p in points],float)
        self.weights/=self.weights.max()
        self.weights/=self.weights.sum()
        self.visibility=np.zeros((len(sites),len(sensors),len(points)),bool)
        self.in_range=np.zeros_like(self.visibility)
        for i,site in enumerate(sites):
            for j,sensor in enumerate(sensors):
                if not self.space.allowed[i,j]:continue
                start=[site['x'],site['y'],site['z']+sensor['height']]
                for k,p in enumerate(points):
                    within=math.hypot(site['x']-p['x'],site['y']-p['y'])<=sensor['radius']
                    self.in_range[i,j,k]=within
                    self.visibility[i,j,k]=within and (not c['los'] or visible(start,[p['x'],p['y'],p['z']],obstacles))

    def evaluate(self,x):
        x=self.space.validate(x)
        if x.ndim!=2:raise ValueError('One physical placement per evaluation')
        c=self._config;sensors=c['sensors'];sites=c['sites'];counts=x.sum(0).astype(int)
        by_type=(self.visibility & x[:,:,None].astype(bool)).any(0)
        union=by_type.any(0)
        relation_masks={r['id']:by_type[[self.space.sensor_order.index(s) for s in r['sensors']]].all(0) for r in c['relations']}
        relation_values={k:float(mask@self.weights) for k,mask in relation_masks.items()}
        joint=float(np.mean(list(relation_values.values()))) if relation_values else None
        coverage=float(union@self.weights)
        occupied=x.any(1)
        cost=float(counts@np.array([s['cost'] for s in sensors])+occupied@np.array([s['activation_cost'] for s in sites]))
        loads=x@np.array([s['resource'] for s in sensors],float)
        g=([s['minimum']-int(v) for s,v in zip(sensors,counts)]+[int(v)-s['maximum'] for s,v in zip(sensors,counts)]+
           (loads-np.array([s['capacity'] for s in sites])).tolist())
        if c['budget'] is not None:g.append(cost-c['budget'])
        if c['total_resource'] is not None:g.append(float(loads.sum())-c['total_resource'])
        metrics=dict(coverage=coverage,cost=cost)
        if joint is not None:metrics['joint_coverage']=joint
        g.extend(value-metrics[key] for key,value in c['goals'].items())
        f=[metrics[k] if k=='cost' else -metrics[k] for k in self.objective_ids]
        if not np.isfinite(f+g+[cost,float(loads.sum())]).all():
            raise ValueError('Nonfinite derived model values; rescale costs/resources/coordinates')
        blocked=(self.in_range & ~self.visibility & x[:,:,None].astype(bool)).sum()
        return dict(X=x.astype(int).tolist(),F=f,G=[float(v) for v in g],cost=cost,counts=counts.tolist(),
            coverage=coverage,joint_coverage=joint,named_metrics=metrics,relation_coverage=relation_values,
            covered_points=union.tolist(),covered_by_sensor=by_type.tolist(),
            joint_points={k:v.tolist() for k,v in relation_masks.items()},site_loads=loads.tolist(),
            blocked_links=int(blocked),placement_hash=self.space.placement_hash(x),experiment_contract_id=self.contract_id,
            feasible=all(v<=0 for v in g))


def example_config():
    """Synthetic demonstration values; replace for research. No old defaults."""
    return dict(model_id=MODEL_ID,units='metres',los=True,co_location=True,
        sensors=[dict(id=k,radius=r,height=5,cost=cost,resource=load,minimum=0,maximum=4)
                 for k,r,cost,load in [('A',240,8,2),('B',170,5,1),('C',110,3,1)]],
        sites=[dict(id=f'S{i+1}',x=x,y=y,z=0,capacity=4,activation_cost=2)
               for i,(x,y) in enumerate(( (x,y) for y in [100,300,500] for x in [100,300,500,700]))],
        points=[dict(id=f'P{i+1}',x=x,y=y,z=1,weight=1)
                for i,(x,y) in enumerate(( (x,y) for y in range(25,601,50) for x in range(25,801,50)))],
        relations=[dict(id='AB',sensors=['A','B']),dict(id='AC',sensors=['A','C'])],
        obstacles=[dict(xmin=370,xmax=430,ymin=170,ymax=430,zmin=0,zmax=25)],
        budget=70,total_resource=16,goals={},objectives=['coverage','joint_coverage','cost'])
