"""Version-pinned loopback model transport. No model-source import or fallback."""
import copy,json,math,os,threading,uuid,hashlib,re
from pathlib import Path
from types import SimpleNamespace
from http.client import HTTPConnection,HTTPException
from urllib.parse import urlsplit,quote
from contextlib import contextmanager
import numpy as np
from scipy.sparse import issparse,csc_matrix

API='SOLSOL_MODEL_API_V1'
class ModelServiceError(RuntimeError):pass
class ModelContext(dict):
    def __init__(self,key,value,owner_identity=None):
        super().__init__(value);self.context_id=key;self.owner_identity=owner_identity
def settings():
    p=Path(__file__).with_name('model_service.json')
    return json.loads(p.read_text(encoding='utf-8'))
def encode(v,rngs=None,owner_identity=None):
    # Resolve a proxy exactly once, then validate the same value we serialize.
    if not isinstance(v,ModelContext):
        sentinel=object();reference=getattr(v,'__model_service_reference__',sentinel)
        if reference is not sentinel:v=reference
    if isinstance(v,ModelContext):
        _require_reference_owner(v.owner_identity,owner_identity)
        return {'$context_ref':v.context_id}
    if issparse(v):
        v=v.tocsc();return {'$sparse':{'shape':list(v.shape),'data':encode(v.data,rngs,owner_identity),'indices':encode(v.indices,rngs,owner_identity),'indptr':encode(v.indptr,rngs,owner_identity)}}
    if isinstance(v,RemoteModel):
        _require_reference_owner((v._client.endpoint,v._source_sha256,v._release_sha256),owner_identity)
        return {'$problem_model':v._problem_id}
    if isinstance(v,np.random.Generator):
        if rngs is not None:rngs.append(v)
        return {'$rng':encode(v.bit_generator.state,owner_identity=owner_identity)}
    if isinstance(v,np.ndarray):return {'$array':{'dtype':str(v.dtype),'shape':list(v.shape),'data':encode(v.tolist(),rngs,owner_identity)}}
    if isinstance(v,np.generic):return encode(v.item(),rngs,owner_identity)
    if isinstance(v,float) and not math.isfinite(v):return {'$float':'nan' if math.isnan(v) else 'inf' if v>0 else '-inf'}
    if isinstance(v,tuple):return {'$tuple':[encode(x,rngs,owner_identity) for x in v]}
    if isinstance(v,list):return [encode(x,rngs,owner_identity) for x in v]
    if isinstance(v,dict):
        if any(not isinstance(k,str) for k in v):return {'$mapping':[[encode(k,rngs,owner_identity),encode(x,rngs,owner_identity)] for k,x in v.items()]}
        return {k:encode(x,rngs,owner_identity) for k,x in v.items()}
    return v
def decode(v,owner_identity=None):
    # JSON scalars already have their final representation. Avoid one Python
    # function call per coordinate/bit while still decoding every tagged node.
    if isinstance(v,list):return [decode(x,owner_identity) if isinstance(x,(list,dict)) else x for x in v]
    if not isinstance(v,dict):return v
    if set(v)=={'$context'}:return ModelContext(v['$context']['id'],decode(v['$context']['value'],owner_identity),owner_identity)
    if set(v)=={'$mapping'}:return {decode(k,owner_identity):decode(x,owner_identity) for k,x in v['$mapping']}
    if set(v)=={'$sparse'}:
        a=v['$sparse'];return csc_matrix((decode(a['data'],owner_identity),decode(a['indices'],owner_identity),decode(a['indptr'],owner_identity)),shape=a['shape'])
    if set(v)=={'$array'}:
        a=v['$array'];return np.asarray(decode(a['data'],owner_identity),dtype=a['dtype']).reshape(a['shape'])
    if set(v)=={'$tuple'}:return tuple(decode(x,owner_identity) for x in v['$tuple'])
    if set(v)=={'$float'}:return float(v['$float'])
    if set(v)=={'$path'}:return Path(v['$path'])
    return {k:decode(x,owner_identity) if isinstance(x,(list,dict)) else x for k,x in v.items()}

def _transport_identity(transport,identity):
    return (transport.endpoint,identity.get('source_sha256'),identity.get('service_release_sha256'))

def _require_reference_owner(reference,owner_identity):
    if owner_identity is None:return  # Standalone encoding is not a transport operation.
    if reference is None or not all(owner_identity) or reference!=owner_identity:
        raise ModelServiceError('MODEL_REFERENCE_TRANSPORT_MISMATCH')

class ModelClient:
    def __init__(self,endpoint=None,timeout=30):
        self.endpoint=endpoint or os.environ.get('SOLSOL_MODEL_ENDPOINT') or settings()['endpoint']
        u=urlsplit(self.endpoint)
        if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost') or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:raise ModelServiceError('MODEL_SERVICE_LOOPBACK_ENDPOINT_REQUIRED')
        self.endpoint=self.endpoint.rstrip('/');self.timeout=timeout;self.modules={}
        self._host=u.hostname;self._port=u.port or 80;self._transport=threading.local()
    def close(self):
        connection=getattr(self._transport,'connection',None)
        if connection is not None:connection.close();del self._transport.connection
    def _metadata_path(self,path):
        configured=os.environ.get('SOLSOL_MODEL_METADATA_CACHE') or settings().get('metadata_cache')
        if not configured:return None
        root=Path(configured)
        if not root.is_absolute():raise ModelServiceError('MODEL_METADATA_CACHE_ABSOLUTE_PATH_REQUIRED')
        key=hashlib.sha256((self.endpoint+'\n'+path).encode()).hexdigest()
        return root/(key+'.json')
    def _metadata_snapshot(self,path,result=None):
        target=self._metadata_path(path)
        if target is None:return None
        if result is not None:
            identity={k:result.get(k) for k in ('source_sha256','service_release_sha256')}
            if not all(identity.values()):
                health=self._online_request('/health')
                if result.get('source_sha256')!=health['source_sha256']:raise ModelServiceError('MODEL_METADATA_SOURCE_MISMATCH')
                identity={k:health[k] for k in identity}
            packet=dict(schema='SOLSOL_MODEL_METADATA_SNAPSHOT_V1',api_version=API,endpoint=self.endpoint,path=path,identity=identity,payload=result)
            encoded=json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False)
            packet['sha256']=hashlib.sha256(encoded.encode()).hexdigest()
            if target.exists() and target.read_text(encoding='utf-8')==json.dumps(packet,allow_nan=False):return packet
            pending=target.parent/'.pending';pending.mkdir(parents=True,exist_ok=True);temporary=pending/(str(uuid.uuid4())+'.json')
            with temporary.open('x',encoding='utf-8') as out:json.dump(packet,out,allow_nan=False);out.flush();os.fsync(out.fileno())
            os.replace(temporary,target);return packet
        if not target.is_file():return None
        try:
            packet=json.loads(target.read_text(encoding='utf-8'));checksum=packet.pop('sha256')
            if checksum!=hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest():raise ValueError('checksum')
            if packet['schema']!='SOLSOL_MODEL_METADATA_SNAPSHOT_V1' or packet['api_version']!=API or packet['endpoint']!=self.endpoint or packet['path']!=path:raise ValueError('binding')
            if any(not isinstance(packet['identity'][k],str) or not re.fullmatch('[a-f0-9]{64}',packet['identity'][k]) for k in ('source_sha256','service_release_sha256')):raise ValueError('identity')
            if packet['payload']['api_version']!=API or packet['payload']['source_sha256']!=packet['identity']['source_sha256']:raise ValueError('payload identity')
            if packet['payload'].get('service_release_sha256',packet['identity']['service_release_sha256'])!=packet['identity']['service_release_sha256']:raise ValueError('release identity')
            return packet
        except (ValueError,KeyError,TypeError) as exc:raise ModelServiceError('MODEL_METADATA_SNAPSHOT_INTEGRITY: '+str(exc)) from None
    def request(self,path,body=None):
        metadata=body is None and (path=='/models' or re.fullmatch(r'/models/[A-Z0-9_-]+/schema',path) or re.fullmatch(r'/compat/modules/[a-z0-9_]+',path))
        if os.environ.get('SOLSOL_MODEL_METADATA_ONLY')=='1' and path!='/health':
            if not metadata:raise ModelServiceError('MODEL_SERVICE_UNAVAILABLE: explicit offline read-only mode; restart calculator online to execute')
            saved=self._metadata_snapshot(path)
            if saved is None:raise ModelServiceError('MODEL_SERVICE_UNAVAILABLE: no matching metadata snapshot for offline read-only mode')
            result=copy.deepcopy(saved['payload'])
            result['model_service_metadata']=dict(status='OFFLINE_CACHED_READ_ONLY',execution_available=False,endpoint=self.endpoint,**saved['identity'])
            return result
        try:result=self._online_request(path,body)
        except ModelServiceError as exc:
            if not metadata or not str(exc).startswith('MODEL_SERVICE_UNAVAILABLE:'):raise
            saved=self._metadata_snapshot(path)
            if saved is None:raise
            result=copy.deepcopy(saved['payload'])
            result['model_service_metadata']=dict(status='OFFLINE_CACHED_READ_ONLY',execution_available=False,endpoint=self.endpoint,**saved['identity'])
            return result
        if metadata:
            try:saved=self._metadata_snapshot(path,result)
            except OSError as exc:
                result['model_service_metadata']=dict(status='LIVE_METADATA_CACHE_WRITE_ERROR',execution_available=True,error=str(exc));return result
            result=copy.deepcopy(result)
            result['model_service_metadata']=dict(status='LIVE',execution_available=True,endpoint=self.endpoint,**(saved['identity'] if saved else {}))
        return result
    def _online_request(self,path,body=None):
        if not path.startswith('/') or path.startswith('//') or '\r' in path or '\n' in path:raise ModelServiceError('MODEL_SERVICE_INVALID_PATH')
        payload=None if body is None else json.dumps(body,allow_nan=False).encode()
        connection=getattr(self._transport,'connection',None)
        if connection is None:
            connection=HTTPConnection(self._host,self._port,timeout=self.timeout);self._transport.connection=connection
        try:
            # Never replay an ambiguous request: a failed POST may already have run.
            connection.request('GET' if body is None else 'POST',path,body=payload,headers={'X-Model-API':API,'Content-Type':'application/json'})
            response=connection.getresponse();raw=response.read()
            if 300<=response.status<400:raise ModelServiceError('MODEL_SERVICE_REDIRECT_REJECTED')
            if response.headers.get('X-Model-API')!=API:raise ModelServiceError('MODEL_SERVICE_API_VERSION_MISMATCH')
        except (HTTPException,TimeoutError,OSError) as e:
            self.close();raise ModelServiceError('MODEL_SERVICE_UNAVAILABLE: '+str(e)) from None
        except ModelServiceError:self.close();raise
        if response.status>=400:
            try:value=json.loads(raw);message=value.get('message',value.get('error',''))
            except (ValueError,TypeError,AttributeError):
                self.close();raise ModelServiceError('MODEL_SERVICE_MALFORMED_ERROR_RESPONSE') from None
            if value.get('error')=='INVALID_INPUT':raise ValueError(message) from None
            raise ModelServiceError('MODEL_SERVICE_ERROR: '+str(message)) from None
        try:result=json.loads(raw)
        except (ValueError,UnicodeError) as e:
            self.close();raise ModelServiceError('MODEL_SERVICE_MALFORMED_RESPONSE: '+str(e)) from None
        if not isinstance(result,dict):raise ModelServiceError('MODEL_SERVICE_MALFORMED_RESPONSE')
        if result.get('api_version')!=API:raise ModelServiceError('MODEL_SERVICE_API_VERSION_MISMATCH')
        return result
    def register(self,definition):return self.request('/problems',definition)
    def call(self,fields,args,kwargs,expected=None):
        owner_identity=_transport_identity(self,{**fields,**(expected or {})})
        rngs=[];payload=dict(fields,args=encode(args,rngs,owner_identity),kwargs=encode(kwargs,rngs,owner_identity));result=self.request('/compat/call',payload)
        for k,v in {**fields,**(expected or {})}.items():
            if result.get(k)!=v:raise ModelServiceError('MODEL_COMPAT_IDENTITY_MISMATCH: '+k)
        states=result.get('rng_states',[])
        if len(states)!=len(rngs):raise ModelServiceError('MODEL_RNG_RESPONSE_MISMATCH')
        for r,state in zip(rngs,states):r.bit_generator.state=decode(state)
        return decode(result['value'],owner_identity)
    def module(self,name):
        if name not in self.modules:self.modules[name]=self.request('/compat/modules/'+quote(name))
        return self.modules[name]

_local=threading.local()
def client():
    if not hasattr(_local,'client'):_local.client=ModelClient()
    return _local.client

@contextmanager
def service_scope(identity, endpoint=None):
    """Compile against an explicit frozen service, without changing other threads.

    Compiled objects retain this client after the scope exits. A missing route
    never falls back to a different release: health is checked before compiling.
    """
    fields=('api_version','source_sha256','service_release_sha256')
    if not isinstance(identity,dict) or any(not isinstance(identity.get(k),str) or not identity[k] for k in fields):
        raise ModelServiceError('SAVED_MODEL_IDENTITY_INCOMPLETE')
    routes=settings().get('replay_endpoints',{})
    # Transport recovery never changes the saved scientific identity. An
    # explicit process map can route a frozen release to a replacement loopback
    # listener after a reboot while retaining all health/compiled checks below.
    override=os.environ.get('SOLSOL_MODEL_REPLAY_ENDPOINTS')
    if override is not None:
        try:
            def unique_pairs(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError()
                    result[key]=value
                return result
            overrides=json.loads(override,object_pairs_hook=unique_pairs)
            if not isinstance(overrides,dict) or any(not isinstance(k,str) or not re.fullmatch('[a-f0-9]{64}',k) or not isinstance(v,str) or not v or v!=v.strip() for k,v in overrides.items()):raise ValueError()
            for value in overrides.values():ModelClient(value).close()
        except (ValueError,TypeError,ModelServiceError):
            raise ModelServiceError('INVALID_REPLAY_TRANSPORT_OVERRIDE') from None
        routes={**routes,**overrides}
    endpoint=endpoint or routes.get(identity['service_release_sha256'])
    prior=getattr(_local,'client',None)
    transport=ModelClient(endpoint) if endpoint else client()
    try:
        health=transport.request('/health')
        if any(health.get(k)!=identity[k] for k in fields):
            raise ModelServiceError('SAVED_MODEL_SERVICE_IDENTITY_MISMATCH')
        _local.client=transport
        yield transport
    finally:
        if prior is None:
            if hasattr(_local,'client'):del _local.client
        else:_local.client=prior
        if transport is not prior:transport.close()
def module_attribute(module,name):
    transport=client();metadata=transport.module(module);spec=metadata['exports'].get(name)
    if spec is None:raise AttributeError(name)
    if spec['kind']=='value':return decode(copy.deepcopy(spec['value']),_transport_identity(transport,metadata))
    if spec['kind']=='factory':
        def factory(*args,**kwargs):
            transport=client()
            owner_identity=_transport_identity(transport,transport.module(module))
            return RemoteModel(transport.register(dict(kind='legacy',module=module,factory=name,args=encode(args,owner_identity=owner_identity),kwargs=encode(kwargs,owner_identity=owner_identity))),model_client=transport)
        return factory
    def invoke(*args,**kwargs):
        transport=client()
        return transport.call(dict(module=module,function=name),args,kwargs,{k:transport.module(module)[k] for k in ('source_sha256','service_release_sha256')})
    return invoke

class RemoteModel:
    def __init__(self,descriptor,model_client=None):
        self._client=model_client if model_client is not None else client()
        self._release_sha256=descriptor['service_release_sha256']
        self._problem_id=descriptor['problem_id'];self._definition=descriptor['definition'];self._attrs=decode(descriptor['model_attributes'],_transport_identity(self._client,descriptor));self._methods=set(descriptor['model_methods']);self._source_sha256=descriptor['source_sha256'];self._input_sha256=descriptor['input_sha256']
    def __getattr__(self,name):
        if name in self._attrs:return self._attrs[name]
        if name in self._methods:
            def invoke(*args,**kwargs):return self._client.call(dict(problem_id=self._problem_id,method=name),args,kwargs,dict(input_sha256=self._input_sha256,source_sha256=self._source_sha256,service_release_sha256=self._release_sha256))
            return invoke
        raise AttributeError(name)

class RemoteCompiledProblem:
    def __init__(self,descriptor,model_client=None):
        # Keep registration and later worker-thread evaluations on one service.
        self._client=model_client if model_client is not None else client()
        from engine.contracts import ObjectiveSpec,RegistrySnapshot
        from engine.placement import PlacementSpace,PlacementCodec
        self._descriptor=descriptor;self.problem_id=descriptor['problem_id'];self.api_version=descriptor['api_version'];self.input_sha256=descriptor['input_sha256'];self.model_source_sha256=descriptor['source_sha256']
        self.service_identity={k:descriptor[k] for k in ('api_version','problem_id','input_sha256','source_sha256','service_release_sha256')}
        self.presentation=copy.deepcopy(descriptor.get('presentation',{}))
        c=decode(descriptor['compiled'],_transport_identity(self._client,descriptor))
        for k,v in c.items():
            if k not in ('registry_snapshot','objective_specs','space','bundle','view_problem'):setattr(self,k,v)
        self.experiment_contract_id=self.cid
        for k in ('sensor_order','objective_order','diagnostic_order','constraint_order','candidate_order'):setattr(self,k,tuple(getattr(self,k)))
        s=c['space'];self.space=PlacementSpace(self.candidate_order,self.sensor_order,s['dataset_id'],s['allowed'],s['enabled_sensor_ids'],s['co_location']);self.codec=PlacementCodec(self.space,s['legacy_full'])
        rs=c['registry_snapshot'];self.registry_snapshot=RegistrySnapshot(**{k:tuple(v) if k.endswith('_order') else v for k,v in rs.items()})
        self.objective_specs=tuple(ObjectiveSpec(**v) for v in c['objective_specs']);self.model=RemoteModel(descriptor,model_client=self._client)
        b=c['bundle'];self.bundle=SimpleNamespace(**b);self.bundle.objective_order=tuple(b['objective_order']);self.bundle.sensor_order=tuple(b['sensor_order']);self.bundle.model=self.model;self.bundle.objective_specs=self.objective_specs
        self._view_problem=c['view_problem']
    def evaluate_physical(self,X,spatial=False,validate_installation=False):
        a=self.space.validate(X,installation=validate_installation)
        if a.ndim==2:a=a[None]
        rows=[]
        for start in range(0,len(a),512):
            chunk=a[start:start+512];bid=str(uuid.uuid4());ids=[str(start+i) for i in range(len(chunk))]
            result=self._client.request('/visualize' if spatial else '/evaluate-batch',dict(problem_id=self.problem_id,batch_id=bid,placements=[dict(id=i,X=x.tolist()) for i,x in zip(ids,chunk)],spatial=spatial,validate_installation=validate_installation))
            if any(result.get(k)!=v for k,v in dict(problem_id=self.problem_id,batch_id=bid,input_sha256=self.input_sha256,model_version=self.model_version,evaluator_sha256=self.evaluator_hash,service_release_sha256=self.service_identity['service_release_sha256']).items()):raise ModelServiceError('MODEL_BATCH_IDENTITY_MISMATCH')
            returned=result.get('results',[])
            if len(returned)!=len(ids) or len({r['id'] for r in returned})!=len(ids) or {r['id'] for r in returned}!=set(ids):raise ModelServiceError('MODEL_PLACEMENT_IDS_MISMATCH')
            mapping={r['id']:decode(r['row']) for r in returned}
            for i,x in zip(ids,chunk):
                row=mapping[i]
                if not np.array_equal(np.asarray(row['X']),x) or row['config_hash']!=self.config_hash or row['evaluator_hash']!=self.evaluator_hash:raise ModelServiceError('MODEL_RESULT_BINDING_MISMATCH')
                if len(row['F'])!=self.n_obj or len(row['G'])!=self.n_constr or not np.isfinite(row['F']+row['G']).all():raise ModelServiceError('MODEL_RESULT_DIMENSION_OR_NONFINITE')
                rows.append(row)
        return rows
    def evaluate(self,z_batch,spatial=False):return self.evaluate_physical(self.codec.decode(z_batch),spatial,True)
    def batch(self,z_batch,spatial=False):
        from engine.contracts import EvaluationBatch
        r=self.evaluate(z_batch,spatial)
        return EvaluationBatch(r,np.asarray([v['X'] for v in r],np.uint8).reshape((-1,)+self.space.shape),np.asarray([v['F'] for v in r]).reshape(len(r),self.n_obj),np.asarray([v['G'] for v in r]).reshape(len(r),self.n_constr))
    def encode(self,X):return self.codec.encode(X)
    def decode(self,z):return self.codec.decode(z)
    def view_problem(self):return copy.deepcopy(self._view_problem)

def compile_remote(cid,config,enabled_sensor_ids=None,objective_ids=None,diagnostic_ids=None):
    transport=client()
    return RemoteCompiledProblem(transport.register(dict(kind='compiled',experiment_contract_id=cid,config=config,enabled_sensor_ids=enabled_sensor_ids,objective_ids=objective_ids,diagnostic_ids=diagnostic_ids)),model_client=transport)
def compile_remote_toy(**kwargs):
    transport=client()
    # Toy definitions contain values, never remote object handles.
    return RemoteCompiledProblem(transport.register(dict(kind='toy',arguments=encode(kwargs,owner_identity=(transport.endpoint,None,None)))),model_client=transport)
