"""Explicit local model adapter with pinned source identity, not legacy physics.

This implements the public calculator model boundary in-process. The external
calculator HTTP API remains the only UI/application/AI execution path.
"""
import copy
from contextlib import contextmanager
import hashlib
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np

from engine.contracts import digest,ObjectiveSpec,RegistrySnapshot
from engine.placement import PlacementSpace,PlacementCodec
from solsol.models.coverage import CoverageModel,example_config

API='SOLSOL_MODEL_API_V1'
CID='ABC_COVERAGE_RESOURCE_V1'
MODELS={}
PROBLEMS={}
class ModelServiceError(RuntimeError):pass


def source_identity():
    root=Path(__file__).resolve().parents[1]
    files=[Path(__file__),Path(__file__).with_name('neutral_geometry.py'),Path(__file__).with_name('model_capabilities.py'),root/'models/coverage.py',root/'geometry.py',
           root/'engine/placement.py',root/'engine/inventory.py',root/'engine/contracts.py']
    definitions={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for cid,spec in MODELS.items():
        import inspect
        factory=spec.get('compiled_builder') or spec['converter']
        path=Path(inspect.getfile(factory));definitions['plugin:'+cid]=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metadata=spec['metadata'],schema=spec['schema'])
    return digest(definitions)


def default_config():
    c=dict(map_km=1.,shape='square',area_factor=.75,candidate_count=12,site_seed=1,
        point_spacing=100.,inventory_mode='partial',budget=70.,total_resource=16.,
        activation_cost=2.,site_capacity=4.,los_enabled=True,
        obstacles=[dict(xmin=450,xmax=520,ymin=300,ymax=700,zmin=0,zmax=25)],
        relations=[dict(id='AB',sensors=['A','B']),dict(id='AC',sensors=['A','C'])])
    for s,r,cost,load in [('A',300.,8.,2.),('B',220.,5.,1.),('C',160.,3.,1.)]:
        c.update({s+'_radius':r,s+'_height':5.,s+'_cost':cost,s+'_resource':load,s+'_stock':4,s+'_minimum':0})
    return c


def field(key,label,unit='',kind='quantity',**extra):
    return dict(key=key,label=label,unit=unit,kind=kind,step=extra.pop('step',1),
                presets=extra.pop('presets',[]),scale=1,minimum=0,maximum=extra.pop('maximum',1000000),**extra)


def model_metadata(cid=CID):
    if cid in MODELS:return copy.deepcopy(MODELS[cid]['metadata'])
    if cid!=CID:raise ModelServiceError('Unknown neutral model: '+cid)
    metrics=[dict(id=k,name=n,unit=u,direction=d,display_scale=1,
        definition=definition,computation='Explicit neutral model evaluation, frozen Cartesian input') for k,n,u,d,definition in [
        ('coverage','전체 커버리지','%', 'maximize','가중 평가 지점 중 한 종류 이상이 커버하는 비율'),
        ('joint_coverage','공동 커버리지','%', 'maximize','선택한 센서 관계별 동시 커버 비율의 평균'),
        ('cost','설치·장비 비용','비용 단위','minimize','장비별 비용과 후보지별 공유 설치비의 합')]]
    return dict(id=cid,name='A/B/C · 범위·관계·공유 자원',version='neutral-coverage-v2',
        sensors=[dict(id=s,name='Sensor '+s,short=s) for s in ['A','B','C']],metrics=metrics,
        coverage_metrics=copy.deepcopy(metrics[:2]),default_objective_ids=['coverage','joint_coverage','cost'],
        policies=['generic_v1'],default_policy='generic_v1',
        default_optimizer=dict(algorithm='NSGA-III',seed=1,population=36,generations=10,ref_partitions=3,
            initializer='random',initialization_evaluations=128,initialization_seconds=30),
        shared_resources=dict(version='SHARED_RESOURCES_V1'),sensor_support=dict(status='SUPPORTED',version='SENSOR_SUPPORT_V1',radius_fields=[dict(sensor_id=s,canonical_config_path=[s+'_radius'],compact_config_path=[s+'_radius'],unit='m') for s in ['A','B','C']]),
        capabilities=dict(advanced_diagnostics_reason='공통 품질·검산·근거 센터에서 같은 원시 실행을 분석합니다.',geometry=True,coverage=True,shared_resources=True,spatial=True,
            quality_methods=['refine','local','milp','exact'],sensor_support=True,
            independent_oracle='external reference remains separately owned',physical_sensor_validation=False))


def model_schema(cid=CID):
    if cid in MODELS:return copy.deepcopy(MODELS[cid]['schema'])
    meta=model_metadata(cid)
    common=[field('map_km','지도 한 변','km',step=.1,maximum=100),field('area_factor','평가영역 비율','',step=.05,maximum=1),
        field('candidate_count','후보지 수','개',maximum=1000),field('site_seed','후보 위치 seed','',maximum=2147483647),
        field('point_spacing','평가 지점 간격','m',maximum=100000)]
    groups={'common':[dict(title='공통 영역·후보지',fields=common,notes=['설치 후보지와 평가 영역은 별개입니다. 영역 밖 후보지도 사용할 수 있습니다.'])],
        'sensors':[],'objectives':[dict(title='공유 설치·예산',fields=[field('budget','예산','비용 단위'),field('total_resource','전체 자원','자원 단위'),
            field('activation_cost','후보지 공유 설치비','비용 단위'),field('site_capacity','후보지 용량','자원 단위')],notes=['목적·진단 선택과 목표 설정은 계산기 공통 기능입니다.'])]}
    for s in ['A','B','C']:
        groups['sensors'].append(dict(title='Sensor '+s,fields=[field(s+'_radius','수평 범위','m'),field(s+'_height','설치 높이','m'),
            field(s+'_cost','장비 비용','비용 단위'),field(s+'_resource','장비 자원','자원 단위'),field(s+'_stock','보유 상한','대'),field(s+'_minimum','최소 수량','대')],
            notes=['특정 장비의 오차·각도·조향 수식을 포함하지 않는 중립 자원입니다.']))
    groups['common'][0]['fields'].append(dict(key='shape',label='평가영역 모양',kind='choice',source='common',unit='',choices=[['square','정사각형'],['circle','원'],['hexagon','육각형'],['overlap','두 원의 교집합']]))
    groups['sensors'][0]['fields'].append(dict(key='inventory_mode',label='기존 수량 사용 방식',kind='choice',unit='',choices=[['partial','최대 수량 내 일부 사용'],['all','보유 수량 전부 사용']]))
    for f in common:
        if f['key'] in ('map_km','shape','area_factor','candidate_count','site_seed'):f['source']='common'
    return dict(id=cid,defaults=default_config(),groups=groups,
        field_schema={f['key']:f for sections in groups.values() for section in sections for f in section['fields']},
        capabilities=meta['capabilities'])


def register_model(cid,metadata,schema,converter):
    """Explicit Python plugin boundary. No imported device definitions required."""
    if not isinstance(cid,str) or not cid or cid in (CID,*MODELS):raise ValueError('Unique model ID required')
    if metadata.get('id')!=cid or schema.get('id')!=cid or not callable(converter):raise ValueError('Model registration identity')
    MODELS[cid]=dict(metadata=copy.deepcopy(metadata),schema=copy.deepcopy(schema),converter=converter)


def register_compiled_model(cid,metadata,schema,builder):
    """Register any scientific model through the preserved full CP protocol.

    Builder receives cid/config/ordered sensor/objective/diagnostic selections;
    it returns a compiled problem satisfying the original public contract. Its
    source, metadata and schema are pinned by source_identity, not copied here.
    """
    if not isinstance(cid,str) or not cid or cid in (CID,*MODELS) or not callable(builder):raise ValueError('Unique explicit compiled model registration required')
    if metadata.get('id')!=cid or schema.get('id')!=cid:raise ValueError('Plugin model identity')
    MODELS[cid]=dict(metadata=copy.deepcopy(metadata),schema=copy.deepcopy(schema),compiled_builder=builder)


def model_config(config,cid=CID):
    from neutral_geometry import region,contains,apply_resources
    if cid in MODELS and 'converter' in MODELS[cid]:return MODELS[cid]['converter'](copy.deepcopy(config))
    c=copy.deepcopy(config)
    if 'sensors' in c and 'points' in c and 'sites' in c:
        result={k:v for k,v in c.items() if not k.startswith('_')};result['goals']={};return apply_resources(result,c.get('_resource_contract'))
    base=default_config();base.update({k:v for k,v in c.items() if not k.startswith('_')})
    if isinstance(base.get('common'),dict):base.update(base['common'])
    width=float(base['map_km'])*1000;n=base['candidate_count'];spacing=float(base['point_spacing'])
    if type(n) is not int or not 1<=n<=1000 or not 0<width<=100000 or not spacing>0:raise ValueError('Invalid common geometry')
    if (width/spacing)**2>10000:raise ValueError('Evaluation grid exceeds 10000 points')
    rng=np.random.default_rng(base['site_seed'])
    sites=base.get('explicit_sites') or [dict(id='S'+str(i+1),x=float(x),y=float(y),z=0.,capacity=base['site_capacity'],activation_cost=base['activation_cost']) for i,(x,y) in enumerate(rng.uniform(0,width,size=(n,2)))]
    factor=float(base['area_factor'])
    if not 0<factor<=1:raise ValueError('Evaluation area factor must be (0,1]')
    lo=width*(1-factor)/2;hi=width-lo
    geometry=region(width,factor,base['shape'])
    points=base.get('explicit_points') or [dict(id='P'+str(i+1),x=float(x),y=float(y),z=1.,weight=1.)
        for i,(x,y) in enumerate(( (x,y) for y in np.arange(lo+spacing/2,hi,spacing) for x in np.arange(lo+spacing/2,hi,spacing) if contains(geometry,float(x),float(y))))]
    sensors=[]
    for s in [v['id'] for v in model_metadata(cid)['sensors']]:
        stock=base[s+'_stock'];minimum=stock if base['inventory_mode']=='all' else base[s+'_minimum']
        sensors.append(dict(id=s,radius=base[s+'_radius'],height=base[s+'_height'],cost=base[s+'_cost'],resource=base[s+'_resource'],minimum=minimum,maximum=stock))
    result=dict(model_id=CID,units='metres',los=base['los_enabled'],co_location=True,sensors=sensors,sites=sites,points=points,
        relations=base['relations'],obstacles=base['obstacles'],budget=base['budget'],total_resource=base['total_resource'],goals={},
        objectives=['coverage',*(['joint_coverage'] if base['relations'] else []),'cost'],evaluation_geometry=geometry)
    return apply_resources(result,c.get('_resource_contract'))


class CompiledProblem:
    def __init__(self,cid,config,enabled_sensor_ids=None,objective_ids=None,diagnostic_ids=None):
        self.cid=cid;self.experiment_contract_id=cid;self.config=copy.deepcopy(config)
        self._physical=CoverageModel(model_config(config,cid));m=self._physical
        self.candidate_order=m.space.candidate_order;self.sensor_order=m.space.sensor_order
        self.objective_order=tuple(objective_ids or m.objective_ids);self.diagnostic_order=tuple(diagnostic_ids or [])
        allowed_ids={x['id'] for x in model_metadata(cid)['metrics']}
        if len(set(self.objective_order))!=len(self.objective_order) or set(self.objective_order+self.diagnostic_order)-allowed_ids:raise ValueError('Unknown metric selection')
        self.constraint_order=tuple(m.constraint_ids);self.model_version=model_metadata(cid)['version'];self.feasibility_tolerance=0.
        self.space=PlacementSpace(self.candidate_order,self.sensor_order,m.space.dataset_id,m.space.allowed,enabled_sensor_ids,m.space.co_location)
        self.codec=PlacementCodec(self.space);self.n_var=self.codec.n_var;self.n_obj=len(self.objective_order);self.n_constr=len(self.constraint_order)
        self.config_hash=digest(self.config);self.evaluator_hash=source_identity();self.model_source_sha256=self.evaluator_hash;self.input_sha256=digest(dict(cid=cid,config=self.config,enabled=list(self.space.enabled_sensor_ids),objectives=self.objective_order,diagnostics=self.diagnostic_order))
        self.problem_id=self.input_sha256
        self.service_identity=dict(api_version=API,problem_id=self.problem_id,input_sha256=self.input_sha256,source_sha256=self.evaluator_hash,service_release_sha256=self.evaluator_hash)
        self._client=client();self.model=SimpleNamespace(n=len(self.candidate_order),installation_allowed=self.space.allowed)
        self.objective_specs=tuple(ObjectiveSpec(objective_id=k,direction='minimize',transform='negative' if k!='cost' else 'identity',display_name=next(v['name'] for v in model_metadata(cid)['metrics'] if v['id']==k)) for k in self.objective_order)
        self.registry_snapshot=RegistrySnapshot(cid,self.model_version,self.candidate_order,self.sensor_order,self.objective_order,self.constraint_order)
        self.config_hash=digest(dict(config=self.config,registry=self.registry_snapshot.to_dict(),
            enabled_sensor_ids=self.space.enabled_sensor_ids,allowed=self.space.allowed.tolist(),
            diagnostic_ids=self.diagnostic_order,codec=self.codec.version,co_location=self.space.co_location))
        self.bundle=SimpleNamespace(sites=[[s['x'],s['y']] for s in m.config['sites']],sensor_order=self.sensor_order,objective_order=self.objective_order,inventory_rule=dict(copy.deepcopy(m.inventory_rule),limits=[s['maximum'] for s in m.config['sensors']]),model=self.model,objective_specs=self.objective_specs)
        self.presentation=dict(kind='NEUTRAL_COVERAGE_RESOURCE',scope='Explicit synthetic or user supplied geometry; no device physics')
        c=m.config;allxy=self.bundle.sites+[[p['x'],p['y']] for p in c['points']];width=max(1.,max(max(p) for p in allxy))
        geometry=c.get('evaluation_geometry') or config.get('evaluation_geometry')
        self._view_problem=dict(experiment_contract_id=cid,sites=self.bundle.sites,demand=[[p['x'],p['y']] for p in c['points']],geometry=geometry,
            radii=[s['radius'] for s in c['sensors']],map_metres=float(config.get('map_km',width/1000))*1000,
            config_sha256=self.config_hash,evaluator_sha256=self.evaluator_hash,model_service=self.service_identity,
            model_version=self.model_version,sensor_order=list(self.sensor_order),sensor_names=[s['id'] for s in c['sensors']],obstacles=c['obstacles'],point_weights=[p['weight'] for p in c['points']],
            evaluator_version=self.model_version,grid_metres=float(config.get('point_spacing',100)))
        PROBLEMS[self.problem_id]=self

    def evaluate_physical(self,X,spatial=False,validate_installation=False):
        a=self.space.validate(X,installation=validate_installation)
        if a.ndim==2:a=a[None]
        result=[];c=self._physical.config
        for x in a:
            r=self._physical.evaluate(x);metrics={k:(v*100 if k!='cost' else v) for k,v in r['named_metrics'].items()}
            coverage={k:v for k,v in metrics.items() if k!='cost'}
            components={s['id']:float(x[:,j].sum()*s['cost']) for j,s in enumerate(c['sensors'])}
            components['shared_installation']=float(sum(site['activation_cost'] for i,site in enumerate(c['sites']) if x[i].any()))
            goals=self.config.get('_research',{}).get('goals')
            out=dict(X=x.astype(int).tolist(),F=[metrics[k] if k=='cost' else -metrics[k] for k in self.objective_order],G=r['G'],cost=r['cost'],
                sensor_counts=r['counts'],counts=r['counts'],cost_components=components,named_metrics=metrics,coverage_metrics=coverage,
                qualified=None if goals is None else all(coverage[k]>=v for k,v in goals.items()),
                placement_hash=self.space.placement_hash(x),decision_sha256=digest(x.astype(int).tolist()),config_hash=self.config_hash,evaluator_hash=self.evaluator_hash,
                covered_points=r['covered_points'],covered_by_sensor=r['covered_by_sensor'],joint_points=r['joint_points'],site_loads=r['site_loads'],blocked_links=r['blocked_links'])
            if spatial:out.update(spatial_status='AVAILABLE',neutral_spatial=dict(covered_points=r['covered_points'],by_sensor=r['covered_by_sensor'],relations=r['joint_points'],blocked_links=r['blocked_links']))
            result.append(out)
        return result
    def evaluate(self,z_batch,spatial=False):return self.evaluate_physical(self.codec.decode(z_batch),spatial,True)
    def batch(self,z_batch,spatial=False):
        from engine.contracts import EvaluationBatch
        rows=self.evaluate(z_batch,spatial)
        return EvaluationBatch(rows,np.asarray([r['X'] for r in rows],np.uint8).reshape((-1,)+self.space.shape),np.asarray([r['F'] for r in rows]).reshape(len(rows),self.n_obj),np.asarray([r['G'] for r in rows]).reshape(len(rows),self.n_constr))
    def encode(self,x):return self.codec.encode(x)
    def decode(self,z):return self.codec.decode(z)
    def view_problem(self):return copy.deepcopy(self._view_problem)


class LocalModelClient:
    endpoint='local://neutral-model-adapter'
    def close(self):pass
    def request(self,path,body=None):
        if path=='/models':
            ids=[CID,*MODELS];return dict(registry=dict(bundles=[model_metadata(i) for i in ids],ui_models={i:model_schema(i) for i in ids}))
        if path=='/health':return dict(status='ready',api_version=API,source_sha256=source_identity(),service_release_sha256=source_identity())
        if path.startswith('/models/') and path.endswith('/schema'):
            cid=path.split('/')[2];return dict(model=model_metadata(cid),schema=model_schema(cid))
        if path=='/configuration':
            cid=body['experiment_contract_id'];c=copy.deepcopy(body['config'])
            if body.get('resource_contract') is not None:
                r=copy.deepcopy(body['resource_contract'])
                if r.get('version')!='SHARED_RESOURCES_V1':raise ValueError('Resource contract version')
                r.setdefault('sensor_counts',{s['id']:dict(mode='MAX',max=c.get(s['id']+'_stock',4)) for s in model_metadata(cid)['sensors']})
                r.setdefault('cost',dict(sensor_unit_costs={s['id']:c.get(s['id']+'_cost',1) for s in model_metadata(cid)['sensors']},site_cost=c.get('activation_cost',0)))
                r.setdefault('budget',dict(mode='OFF',limit=None));c['_resource_contract']=r
            if not MODELS.get(cid,{}).get('compiled_builder'):
                CoverageModel(model_config(c,cid))
            return dict(config=c,metadata=model_metadata(cid))
        if path.startswith('/problems/') and path.endswith('/initialization'):
            from model_capabilities import formulation
            if not hasattr(PROBLEMS[path.split('/')[2]],'_physical'):raise ModelServiceError('MODEL_CAPABILITY_UNSUPPORTED: exact neutral formulation')
            return formulation(PROBLEMS[path.split('/')[2]])
        if path=='/initialization/formulation':
            from model_capabilities import formulation
            if not hasattr(PROBLEMS[body['problem_id']],'_physical'):raise ModelServiceError('MODEL_CAPABILITY_UNSUPPORTED: exact neutral formulation')
            p=formulation(PROBLEMS[body['problem_id']])
            if body['expected_identity']!=p['identity']:raise ModelServiceError('Formulation identity mismatch')
            return p
        if path.startswith('/problems/') and path.endswith('/sensor-support'):
            cp=PROBLEMS[path.split('/')[2]]
            if not hasattr(cp,'_physical'):raise ModelServiceError('MODEL_CAPABILITY_UNSUPPORTED: neutral sensor support')
            allowed=cp.space.allowed;zero=~cp._physical.visibility.any(2);safe=allowed & zero
            lower=cp.bundle.inventory_rule.get('lower',[0]*len(cp.sensor_order))
            for j,v in enumerate(lower):
                if v>0:safe[:,j]=False
            c=dict(status='SUPPORTED',contract_version='SENSOR_SUPPORT_V1',identity=dict({k:v for k,v in cp.service_identity.items() if k!='api_version'},model_id=cp.cid,config_sha256=cp.config_hash,evaluator_sha256=cp.evaluator_hash,model_version=cp.model_version),candidate_order=list(cp.candidate_order),sensor_order=list(cp.sensor_order),original_allowed=allowed.astype(int).tolist(),safe_search_allowed=(allowed & ~safe).astype(int).tolist(),safe_prune_mask=safe.astype(int).tolist(),zero_support_mask=zero.astype(int).tolist(),full_X_shape=list(allowed.shape),active_slot_order=cp.codec.slots.tolist(),search_integration=dict(policy='OPT_IN_CLIENT_MASK_ORIGINAL_CODEC_V1'))
            c['support_sha256']=digest(c);return c
        raise ModelServiceError('MODEL_CAPABILITY_UNSUPPORTED: '+path)


_CLIENT=LocalModelClient()
def client():return _CLIENT
def settings():return dict(endpoint=_CLIENT.endpoint,api_version=API)
def compile_remote(cid,config,enabled_sensor_ids=None,objective_ids=None,diagnostic_ids=None):
    builder=MODELS.get(cid,{}).get('compiled_builder')
    if builder:
        cp=builder(cid,copy.deepcopy(config),enabled_sensor_ids,objective_ids,diagnostic_ids)
        if cp.cid!=cid or cp.evaluator_hash!=source_identity() or cp.service_identity.get('source_sha256')!=cp.evaluator_hash:
            raise ModelServiceError('PLUGIN_MODEL_IDENTITY_UNPINNED')
        if cp.service_identity.get('problem_id')!=cp.problem_id or cp.service_identity.get('input_sha256')!=cp.input_sha256:
            raise ModelServiceError('PLUGIN_PROBLEM_IDENTITY_MISMATCH')
        PROBLEMS[cp.problem_id]=cp
        return cp
    return CompiledProblem(cid,config,enabled_sensor_ids,objective_ids,diagnostic_ids)
def compile_remote_toy(**kwargs):raise ModelServiceError('Old structural toy is not an active sensor model')
@contextmanager
def service_scope(identity,endpoint=None):
    if identity is not None:
        if identity.get('source_sha256')!=source_identity() or identity.get('service_release_sha256')!=source_identity():raise ModelServiceError('SAVED_MODEL_SERVICE_IDENTITY_MISMATCH')
        if endpoint is not None and endpoint!=_CLIENT.endpoint:raise ModelServiceError('SAVED_MODEL_ENDPOINT_MISMATCH')
    yield _CLIENT
def module_attribute(module,name):raise ModelServiceError('DEVICE_SPECIFIC_MODULE_EXCLUDED: '+module+'.'+name)
