"""One lifecycle and evaluation/checkpoint sinks for every solver policy."""
import copy,hashlib,json,threading,time,uuid
import platform
from importlib.metadata import version
from pathlib import Path
import numpy as np
from .registry import compile_problem
from .archive import archive_ids,AppendOnlyArchive
from .store import RunStore,SCHEMA,digest
from model_service_client import ModelServiceError

ACTIVE={'queued','preparing','running','verifying','saving'}
TERMINAL={'completed','cancelled','time_limit','failed','interrupted'}

def source_snapshot():
    root=Path(__file__).resolve().parents[1]
    paths=list((root/'engine').rglob('*.py'))+list((root/'implementation').rglob('*.py'))+list(root.glob('*.py'))
    result={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return result

LOADED_SOURCE_HASHES=source_snapshot()
ENVIRONMENT=dict(python=platform.python_version(),**{name:version(name) for name in ('numpy','scipy','pymoo')})

def optimizer_config(problem,opt):
    opt=copy.deepcopy(opt)
    explicit=opt.pop('policy',None)
    if problem.config.get('_resource_contract') and explicit!='generic_v1':
        raise ValueError('RESOURCE_POLICY: shared resource contracts require generic_v1')
    if explicit is not None and explicit not in ('generic_v1','legacy_eoir_v1','legacy_rf_v1','legacy_rf_v2','legacy_rf_v3'):raise ValueError('Unknown solver policy')
    if problem.cid=='RADAR_EOIR' and explicit!='generic_v1':
        from live_model import PRESETS
        c=problem.config
        if problem.objective_order!=problem.bundle.objective_order:raise ValueError('UNSUPPORTED_INPUT: legacy EOIR solver requires original objective order; generic objective selection is not this policy')
        if opt and set(opt)-{'wallclock_limit_seconds'}:raise ValueError('EOIR optimizer settings belong to frozen config')
        seconds=opt.get('wallclock_limit_seconds',300)
        if type(seconds) not in (int,float) or not np.isfinite(seconds) or not 0<=seconds<=1800:raise ValueError('Invalid wallclock limit')
        return dict(algorithm='NSGA-III',seed=c['seed'],population=PRESETS[c['h']],generations=c['generations'],checkpoints=c['generations']+1,wallclock_limit_seconds=opt.get('wallclock_limit_seconds',300)), 'legacy_eoir_v1'
    version=problem.config.get('evaluator_version')
    policy=explicit or {'rf-information-candidate-1':'legacy_rf_v1','rf-common-information-v2':'legacy_rf_v2','rf-common-information-v3':'legacy_rf_v3'}.get(version,'generic_v1')
    expected={'algorithm','seed','population', 'generations' if policy in ('legacy_rf_v3','generic_v1') else 'checkpoints'}
    extras={'wallclock_limit_seconds'}|({'ref_partitions','initializer','initialization_version','initialization_evaluations','initialization_seconds','saved_seed'} if policy=='generic_v1' else set())
    if not expected<=set(opt) or set(opt)-expected-extras:raise ValueError('Unknown/missing optimizer fields')
    if opt['algorithm'] not in ('random','NSGA-II','NSGA-III'):raise ValueError('Unknown optimizer')
    ints=['seed','population','generations' if 'generations' in expected else 'checkpoints']
    if any(type(opt[k]) is not int for k in ints) or not 0<=opt['seed']<=2147483647:raise ValueError('Invalid optimizer integers')
    lo,hi=(4,64) if policy=='legacy_rf_v1' else (36,64) if policy=='legacy_rf_v2' else (36,212) if policy=='legacy_rf_v3' else (4,256)
    if not lo<=opt['population']<=hi:raise ValueError('Invalid population')
    count=opt['generations']+1 if 'generations' in opt else opt['checkpoints']
    if policy=='generic_v1':
        # Preserve exact JSON/JavaScript counters, not a fixed research budget.
        if count<2 or count*opt['population']>9007199254740991:
            raise ValueError('진화 세대 수는 1 이상의 정수이며 총 평가 수는 JSON 안전 정수 범위여야 합니다.')
    elif not 2<=count<=(1001 if policy=='legacy_rf_v3' else 30) or count*opt['population']>100000:
        raise ValueError('Optimizer budget exceeded')
    opt['checkpoints']=count
    opt.setdefault('wallclock_limit_seconds',0 if policy=='generic_v1' else 180 if policy=='legacy_rf_v2' else 1800)
    if type(opt['wallclock_limit_seconds']) not in (int,float) or not np.isfinite(opt['wallclock_limit_seconds']) or not 0<=opt['wallclock_limit_seconds']<=(86400 if policy=='generic_v1' else 1800):raise ValueError('Invalid wallclock limit')
    if 'ref_partitions' in opt and (type(opt['ref_partitions']) is not int or not 1<=opt['ref_partitions']<=255):raise ValueError('Invalid reference partitions')
    if policy=='generic_v1':
        from .initialization import validate_resources
        from .common_initialization import METHODS, LEGACY_VERSION, VERSIONS
        # Missing version means the historical API policy, never implicit migration.
        opt.setdefault('initialization_version',LEGACY_VERSION)
        if opt['initialization_version'] not in VERSIONS:raise ValueError('Unknown initialization version')
        if opt.get('initializer','random') not in METHODS:raise ValueError('Unknown initializer')
        if opt.get('initializer')=='saved':
            from .saved_initialization import validate_reference
            validate_reference(opt.get('saved_seed'))
        elif 'saved_seed' in opt:raise ValueError('저장 초기 배치를 사용하지 않을 때는 원본 선택을 해제하세요.')
        opt.setdefault('initialization_evaluations',128)
        opt.setdefault('initialization_seconds',30)
        if type(opt['initialization_evaluations']) is not int or not 1<=opt['initialization_evaluations']<=512:raise ValueError('Invalid initialization evaluation budget')
        if type(opt['initialization_seconds']) not in (int,float) or not np.isfinite(opt['initialization_seconds']) or not 0<opt['initialization_seconds']<=120:raise ValueError('Invalid initialization time budget')
        validate_resources(problem.space,getattr(problem.bundle,'inventory_rule',None))
    return opt,policy

class RunSession:
    def __init__(self,problem,optimizer,store,run_id=None):
        self.problem=problem;self.model=problem.model;self.cid=problem.cid;self.config=copy.deepcopy(problem.config)
        self.optimizer,self.policy=optimizer_config(problem,optimizer)
        from .installation_domain import ensure_domain
        ensure_domain(problem,self.policy)
        self.id=run_id or str(uuid.uuid4());self.store=store;self.folder=store.folder(self.cid,self.id)
        self.rows=[];self.checkpoints=[];self.events=[];self.initialization=None;self.solver_trace=[];self.audit=None
        self.cancel=threading.Event();self.lock=threading.RLock();self.state='queued';self.error=None;self.termination_reason=None
        self._progress_lock=threading.Lock();self._terminal_progress=None
        self.started=time.monotonic();self.elapsed=0.;self.wallclock_limit=self.optimizer['wallclock_limit_seconds']
        if self.policy=='generic_v1' and self.wallclock_limit==0:self.wallclock_limit=float('inf')
        self.counters=dict(preparation_evaluations=0,initial_population_evaluations=0,offspring_evaluations=0,refinement_evaluations=0,replay_evaluations=0,diagnostic_evaluations=0)
        self.source_hashes=copy.deepcopy(LOADED_SOURCE_HASHES);self.environment=copy.deepcopy(ENVIRONMENT);self.runtime_hash=digest(dict(sources=self.source_hashes,environment=self.environment))
        self.solver_metadata=dict(policy=self.policy);self.archive_policy=dict(tolerance=problem.feasibility_tolerance,sort='cost' if self.cid=='RADAR_EOIR' else 'raw')
        self._spatial={};self._views={};self._begun=False
        self._archive_index=AppendOnlyArchive(**self.archive_policy);self._archive_stop=0;self._observed_placements={}
        self.view_diagnostics=dict(map_evaluations=0)
        self.compilation=dict(config=self.config,registry=problem.registry_snapshot.to_dict(),enabled_sensor_ids=problem.space.enabled_sensor_ids,allowed=problem.space.allowed.tolist(),diagnostic_ids=problem.diagnostic_order,codec=problem.codec.version,co_location=problem.space.co_location)
        self.compilation['installation_domain']=copy.deepcopy(getattr(problem,'installation_domain',None))
        self.compilation['inventory_rule']=copy.deepcopy(getattr(problem.bundle,'inventory_rule',None))
        if hasattr(problem,'model_allowed'):self.compilation['model_allowed']=copy.deepcopy(problem.model_allowed)
        self.frozen_problem=copy.deepcopy(problem.view_problem())
        if self.cid=='RADAR_EOIR' and 'upper_bound' in self.frozen_problem:
            self.counters['diagnostic_evaluations']+=1
            self.solver_metadata['setup_diagnostics']=[dict(phase='FROZEN_PROBLEM_UPPER_BOUND',provenance='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER',X=np.ones(problem.space.shape,dtype=int).tolist(),row=copy.deepcopy(self.frozen_problem['upper_bound']),evaluations=1)]
        self.frozen_problem.update(experiment_contract_id=self.cid,config_sha256=problem.config_hash,evaluator_sha256=problem.evaluator_hash)
        self.frozen_problem['model_service']=copy.deepcopy(problem.service_identity)
        if hasattr(problem,'calculator_configuration'):
            self.frozen_problem['research_configuration']=copy.deepcopy(problem.calculator_configuration)
        if '_research' in self.config:
            self.frozen_problem['research_configuration']=copy.deepcopy(self.config['_research'])
            self.frozen_problem.setdefault('map_metres',self.config.get('map_km',20)*1000)
        self._discovery_snapshot=_discovery_entry_locked(self)
    def set_phase(self,state):
        with self.lock:
            self.state=state;self._discovery_snapshot=_discovery_entry_locked(self)
        self._record_runtime_status()
    def _record_runtime_status(self):
        """Small sidecar for crash diagnosis; never rewrites scientific results."""
        from datetime import datetime,timezone
        from .store import atomic_json
        try:
            if not self.folder.exists():return
            cp=self.checkpoints[-1] if self.checkpoints else {}
            atomic_json(self.folder/'runtime-status.json',dict(schema='SOLSOL_RUNTIME_STATUS_V1',
                run_id=self.id,experiment_contract_id=self.cid,state=self.state,
                updated_at=datetime.now(timezone.utc).isoformat(),pid=__import__('os').getpid(),
                generation=cp.get('generation'),nfe=len(self.rows),counters=dict(self.counters),
                elapsed_seconds=time.monotonic()-self.started,error=self.error,
                termination_reason=self.termination_reason))
        except Exception:
            # Diagnostic IO failure must not cancel or disguise the original run.
            import logging
            logging.getLogger(__name__).exception('Runtime status recording failed for %s',self.id)
    def evaluate(self,X,generation,origin):
        if self.problem.config!=self.config:raise ValueError('Configuration changed after submit')
        rows=self.problem.evaluate_physical(X,validate_installation=True)
        with self.lock:
            for row in rows:
                for key in ('candidate_order','sensor_order','objective_order','constraint_order'):row.pop(key,None)
                row.update(id=len(self.rows),run_id=self.id,experiment_contract_id=self.cid,config_sha256=self.problem.config_hash,evaluator_sha256=self.problem.evaluator_hash,generation=generation,origin=origin,provenance='RAW_OPTIMIZER_EVALUATIONS')
                from .hard_constraints import audit_row,area_distances
                audit_context=dict(run_id=self.id,experiment_contract_id=self.cid,config=self.config,problem=self.frozen_problem,compilation=self.compilation)
                if not hasattr(self,'_audit_distances'):self._audit_distances=area_distances(audit_context)
                check=audit_row(row,audit_context,self.compilation['inventory_rule'],self._audit_distances)
                if not check['hard_pass']:raise ValueError('HARD_CONSTRAINT_VIOLATION: '+str(check))
                row['installation_audit']=check
                if self.policy=='generic_v1' and self.config.get('_research'):
                    from .binary_decision import retain_decision
                    row['X']=retain_decision(row['X'])
                self.rows.append(row)
            self.counters['initial_population_evaluations' if generation==0 else 'offspring_evaluations']+=len(rows)
        return rows
    def checkpoint(self,pop_X,generation,extra=None):
        with self.lock:
            if generation!=len(self.checkpoints):raise ValueError('Non-sequential checkpoint')
            pop_X=np.asarray(pop_X)
            new=self.rows[self._archive_stop:];self._archive_index.extend(new)
            for r in new:self._observed_placements[np.asarray(r['X'],np.uint8).tobytes()]=r['id']
            self._archive_stop=len(self.rows)
            ids=[self._observed_placements[np.asarray(x,np.uint8).tobytes()] for x in pop_X]
            from .live_checkpoint import retain_population
            population=retain_population(pop_X) if self.policy=='generic_v1' and self.config.get('_research') and not extra else pop_X.astype(int).tolist()
            cp=dict(generation=generation,nfe=len(self.rows),evaluations=len(self.rows),population_X=population,population_ids=ids,front_ids=[],archive_ids=self._archive_index.selected(),elapsed_seconds=time.monotonic()-self.started)
            if extra:cp.update(extra)
            if self.config.get('_research'):
                if 'qualified_count' in cp:cp['legacy_policy_qualified_count']=cp['qualified_count']
                cp['qualified_count']=None if self.config['_research']['goals'] is None else sum(self.rows[i]['qualified'] is True for i in ids)
                cp['target_archive_count']=None if self.config['_research']['goals'] is None else sum(self.rows[i]['qualified'] is True for i in cp['archive_ids'])
            self.checkpoints.append(cp)
            self._discovery_snapshot=_discovery_entry_locked(self)
            self.store.persist(self,checkpoint=True)
    def progress_snapshot(self):
        """Bounded monitoring data: never copy populations or archive history."""
        while True:
            with self._progress_lock:
                published=copy.deepcopy(self._terminal_progress)
                if published is not None:
                    if published['state']=='saving':
                        now=time.monotonic()
                        published['elapsed_seconds']=now-self.started
                        published['terminal_storage_seconds']=now-self._terminal_storage_started
                    published['cancel_requested']=self.cancel.is_set()
                    return published
            # A reader may arrive just before saving publishes its snapshot.
            # Retry the small publication instead of waiting behind terminal IO.
            if self.lock.acquire(timeout=0.05):
                try:
                    with self._progress_lock:
                        if self._terminal_progress is not None:continue
                    return self._progress_snapshot_locked()
                finally:self.lock.release()
    def _progress_snapshot_locked(self):
        cp=self.checkpoints[-1] if self.checkpoints else {}
        return dict(state=self.state,nfe=len(self.rows),elapsed_seconds=self.elapsed if self.state in TERMINAL else time.monotonic()-self.started,
                    generation=cp.get('generation'),declared_nfe=self.optimizer['population']*self.optimizer['checkpoints'],
                    requested_generations=self.optimizer['checkpoints']-1,counters=dict(self.counters),
                    archive_count=len(cp.get('archive_ids',[])),target_archive_count=cp.get('target_archive_count'),
                    checkpoint_elapsed_seconds=cp.get('elapsed_seconds'),cancel_requested=self.cancel.is_set())
    def _publish_terminal_progress(self,finished=False):
        # Called with the ledger lock held. Only scalar progress is published;
        # raw rows/checkpoints remain protected through atomic storage.
        with self._progress_lock:
            now=time.monotonic()
            if not finished:self._terminal_storage_started=now
            snapshot=self._progress_snapshot_locked()
            snapshot['terminal_storage_seconds']=now-self._terminal_storage_started
            if finished:
                # Live observation is separate from historical raw duration.
                snapshot['observed_completion_elapsed_seconds']=now-self.started
                snapshot['pre_completion_elapsed_seconds']=snapshot['elapsed_seconds']
                snapshot['elapsed_seconds']=snapshot['observed_completion_elapsed_seconds']
                snapshot['elapsed_scope']='LIVE_OBSERVED_THROUGH_TERMINAL_STORAGE'
            self._terminal_progress=snapshot
            self._discovery_snapshot=_discovery_entry_locked(self)
    def packet(self,include_rows=True,compact_checkpoints=False,copy_values=True,*,_native_checkpoint_buffers=False):
        with self.lock:
            solver=self.solver_metadata if include_rows else {k:v for k,v in self.solver_metadata.items() if k not in ('auxiliary_evaluations','initial_X','initialization_formulation')}
            packet=dict(schema=SCHEMA,runtime_version='shared-engine-v1',experiment_contract_id=self.cid,run_id=self.id,config=self.config,compilation=self.compilation,config_sha256=self.problem.config_hash,evaluator_sha256=self.problem.evaluator_hash,optimizer_code_sha256=self.runtime_hash,source_hashes=self.source_hashes,environment=self.environment,optimizer=self.optimizer,solver=solver,state=self.state,error=self.error,termination_reason=self.termination_reason,storage_complete=self.state in TERMINAL and (self.folder/'manifest.json').exists(),rows=self.rows if include_rows else [],checkpoints=([{k:v for k,v in cp.items() if k not in ('population_X','population_ids')} for cp in self.checkpoints] if compact_checkpoints else self.checkpoints),events=self.events if include_rows else [],nfe=len(self.rows),declared_nfe=self.optimizer['population']*self.optimizer['checkpoints'],counters=self.counters,elapsed_seconds=self.elapsed if self.state in TERMINAL else time.monotonic()-self.started,problem=self.frozen_problem,registry=self.problem.registry_snapshot.to_dict(),archive_policy=self.archive_policy,initialization=self.initialization,audit=self.audit,provenance='RAW_OPTIMIZER_EVALUATIONS',scientific_approval='NOT_PROMOTED',resume_available=False,submission=getattr(self,'submission',None),execution_snapshot=getattr(self,'execution_snapshot',None),submitted_request=getattr(self,'submitted_request',None),cancel_requested=self.cancel.is_set(),engine_components=['RunService','RunSession','CompiledProblem','archive_ids','RunStore'])
            if self.folder.exists():
                from .run_names import names
                packet.update(names(packet,self.folder))
            if not _native_checkpoint_buffers and not compact_checkpoints:
                from .live_checkpoint import public_checkpoint
                if any(isinstance(c.get('population_X'),np.ndarray) for c in packet['checkpoints']):
                    packet['checkpoints']=[public_checkpoint(c) for c in packet['checkpoints']]
            if include_rows and not _native_checkpoint_buffers:
                from .binary_decision import public_rows
                packet['rows']=public_rows(packet['rows'])
            return copy.deepcopy(packet) if copy_values else packet
    def _storage_packet(self):
        return self.packet(copy_values=False,_native_checkpoint_buffers=True)
    def spatial(self,row):
        # Model IO must never hold the optimizer's append/checkpoint lock.
        # A separate lock coalesces map requests without serializing evolution.
        with self.lock:
            if not hasattr(self,'_map_lock'):self._map_lock=threading.Lock()
            map_lock=self._map_lock
        with map_lock:
            if row['id'] not in self._spatial:
                fresh=self.problem.evaluate_physical(np.asarray([row['X']]),spatial=True)[0]
                if fresh['F']!=row['F'] or fresh['G']!=row['G'] or fresh['cost']!=row['cost']:raise ValueError('INTEGRITY_ERROR: map replay')
                if self.state in TERMINAL:
                    from .store import record_derivation
                    record_derivation(self,'MAP_REPLAY',dict(raw_id=row['id']),1,dict(placement_hash=row.get('placement_hash'),status='EXACT_FROZEN_MODEL_XFG_MATCH'))
                with self.lock:
                    self._spatial[row['id']]={**row,**{k:v for k,v in fresh.items() if k not in ('config_sha256','evaluator_sha256','id','run_id')}}
                    self.view_diagnostics['map_evaluations']+=1
                # View derivations have separate counters and never change committed raw.
            return copy.deepcopy(self._spatial[row['id']])
    def view(self,generation=None,*,summary=False):
        from .results import to_view
        with self.lock:
            # Preparation and legacy producers have different publication
            # rules. Keep their established path; generic search publishes
            # immutable preparation metadata before entering running.
            if self.policy!='generic_v1' or self.state in ('queued','preparing'):
                return to_view(self,generation,summary=summary)
            if not hasattr(self,'_view_lock'):self._view_lock=threading.Lock()
            if not hasattr(self,'_map_lock'):self._map_lock=threading.Lock()
            view_lock=self._view_lock
        # Slow display aggregation and map IO must not own the optimizer ledger
        # lock. Rows/checkpoints are append-only; freeze membership and mutable
        # headers briefly, then serialize concurrent displays separately.
        with view_lock:
            with self.lock:
                if self.policy!='generic_v1' or self.state in ('queued','preparing'):
                    return to_view(self,generation,summary=summary)
                snapshot=copy.copy(self);snapshot.lock=threading.RLock()
                snapshot.rows=list(self.rows);snapshot.checkpoints=list(self.checkpoints)
                snapshot.counters=dict(self.counters);snapshot.audit=copy.deepcopy(self.audit)
                snapshot.initialization=copy.deepcopy(self.initialization)
                if hasattr(self,'_hard_reports'):snapshot._hard_reports={k:v for k,v in self._hard_reports.copy().items() if k<len(snapshot.rows)}
                snapshot.solver_metadata=copy.deepcopy({k:v for k,v in self.solver_metadata.items() if k not in ('auxiliary_evaluations','initial_X','initialization_formulation')})
            result=to_view(snapshot,generation,summary=summary)
            for key in ('_views','_hard_reports','_history_count_cache','_evaluation_summaries','_evaluation_prefixes'):
                if hasattr(snapshot,key):
                    value=getattr(snapshot,key)
                    if key=='_hard_reports' and len(getattr(self,key,{}))>len(value):continue
                    setattr(self,key,value)
            return result
    status=view
    def run(self):
        from .solver import solve
        with self.lock:
            if self._begun:raise ValueError('Run already started')
            self._begun=True;self.started=time.monotonic()
        reason='failed'
        try:
            if not getattr(self,'_reserved',False):self.folder=self.store.begin(self.cid,self.id)
            self._record_runtime_status()
            self.store.persist(self)
            reason='cancelled' if self.cancel.is_set() else solve(self)
            self.set_phase('verifying')
            for start in range(0,len(self.rows),256):
                if self.cancel.is_set():
                    reason='cancelled'
                    break
                old=self.rows[start:start+256];fresh=self.problem.evaluate_physical(np.asarray([r['X'] for r in old]))
                for a,b in zip(old,fresh):
                    if any(a[k]!=b[k] for k in ('F','G','cost','placement_hash','sensor_counts')):raise ValueError('INTEGRITY_ERROR: fixed-X replay')
                self.counters['replay_evaluations']+=len(fresh)
                if start==0 or time.monotonic()-last_status>=10:
                    self._record_runtime_status();last_status=time.monotonic()
            if self.cancel.is_set():reason='cancelled'
            if reason=='completed' and (len(self.checkpoints)!=self.optimizer['checkpoints'] or len(self.rows)!=self.optimizer['population']*len(self.checkpoints)):raise ValueError('Incomplete declared optimizer budget')
            replayed=self.counters['replay_evaluations']
            self.audit=dict(raw_replay='PASS' if replayed==len(self.rows) else 'PARTIAL_USER_STOP' if replayed else 'NOT_RUN_USER_STOP',evaluations=replayed,unchecked_evaluations=len(self.rows)-replayed,search_evaluations=len(self.rows),preparation_evaluations=self.counters['preparation_evaluations'],preparation_seconds=(self.initialization or {}).get('seconds',0),posthoc_diagnostic_evaluations=replayed,scope='fixed-X adapter replay; independent oracle is separate development evidence')
        except TimeoutError as exc:reason='time_limit';self.error=str(exc)
        except Exception as exc:
            reason='failed';self.error=type(exc).__name__+': '+str(exc)
            import logging
            logging.getLogger(__name__).exception('Run %s computation failed',self.id)
        with self.lock:
            try:
                self.state='saving';self._record_runtime_status();self._publish_terminal_progress();self.store.persist(self)
                if reason=='completed' and self.cancel.is_set():reason='cancelled'
                self.state=reason;self.termination_reason={'completed':'GENERATION_BUDGET','cancelled':'USER_STOP','time_limit':'WALLCLOCK_BUDGET','failed':'COMPUTATION_ERROR'}[reason];self.elapsed=time.monotonic()-self.started
                self.store.persist(self,terminal=True)
            except Exception as exc:
                self.state='failed';self.termination_reason='STORAGE_ERROR';self.error=type(exc).__name__+': '+str(exc);self.elapsed=time.monotonic()-self.started
                import logging
                logging.getLogger(__name__).exception('Run %s storage failed',self.id)
            finally:
                try:self._publish_terminal_progress(finished=True);self._record_runtime_status()
                finally:
                    cache=getattr(self,'_encoded_rows',None)
                    if cache is not None:cache.close()
        return self

def stored_runtime_diagnostic(folder,packet):
    """Optional crash explanation, never evidence of a scientific commit.

    The immutable raw/journal is already verified. This separate diagnostic
    cannot change state, error, counters, audit, or storage_complete in it.
    """
    if packet.get('state')!='interrupted':return None
    path=Path(folder)/'runtime-status.json'
    try:
        if path.stat().st_size>65536:return None
        import json
        data=json.loads(path.read_text(encoding='utf8'))
        if (data.get('schema')!='SOLSOL_RUNTIME_STATUS_V1' or data.get('run_id')!=packet['run_id'] or
            data.get('experiment_contract_id')!=packet['experiment_contract_id'] or
            type(data.get('nfe')) is not int or data['nfe']!=len(packet['rows']) or
            (data.get('generation') is not None and type(data['generation']) is not int) or
            data.get('generation')!=(packet['checkpoints'][-1]['generation'] if packet['checkpoints'] else None) or
            data.get('state')!='failed' or not isinstance(data.get('error'),str) or
            not data['error'] or len(data['error'])>4096):return None
        return dict(source='runtime-status.json',evidence_status='DIAGNOSTIC_ONLY_NOT_COMMITTED',
                    state=data['state'],error=data['error'],termination_reason=data.get('termination_reason'))
    except (OSError,ValueError,TypeError,AttributeError):return None

class StoredSession:
    def __init__(self,packet,folder,validated_decisions=None):
        if (validated_decisions is not None and len(packet['rows'])>=4096 and
            (packet['config'].get('_research') or packet['experiment_contract_id'] in ('HMSP-EXEC-V1','HMSP-2D-V1'))):
            from .store import _fast_json
            if _fast_json is not None:
                # The caller's full verified packet stays unchanged. Only this
                # stored session owns a compact copy of population history;
                # every noncompact public packet reconstructs independent lists.
                checkpoints=[]
                for original in packet['checkpoints']:
                    cp=dict(original);pop=cp['population_X']
                    if (type(pop) is list and pop and
                        all(type(matrix) is list and all(type(site) is list for site in matrix) for matrix in pop)):
                        x=np.asarray([validated_decisions[i] for i in cp['population_ids']],dtype=np.uint8)
                        # JSON equality here is deliberately stronger than
                        # Python 0==False==0.0. Preserve unusual numeric types.
                        # Encode the uint8 buffer directly; rebuilding millions
                        # of temporary Python lists defeats the private buffer.
                        if _fast_json.dumps(pop)==_fast_json.dumps(x,option=_fast_json.OPT_SERIALIZE_NUMPY):
                            x.flags.writeable=False;cp['population_X']=x
                    checkpoints.append(cp)
                packet=dict(packet,checkpoints=checkpoints)
        self.data=packet;self.folder=Path(folder);self.id=packet['run_id'];self.cid=packet['experiment_contract_id'];self.config=packet['config'];self.state=packet['state'];self.rows=packet['rows'];self.checkpoints=packet['checkpoints'];self.frozen_problem=packet['problem'];self.lock=threading.RLock();self._spatial={};self._views={};self.problem=None
        self._validated_decisions=validated_decisions
        self.runtime_diagnostic=stored_runtime_diagnostic(folder,packet)
        self._discovery_snapshot=_discovery_entry_locked(self)
    def packet(self,include_rows=True,compact_checkpoints=False):
        result=dict(self.data) if include_rows else {k:v for k,v in self.data.items() if k not in ('rows','events')}
        if not include_rows:result['solver']={k:v for k,v in result['solver'].items() if k not in ('auxiliary_evaluations','initial_X')}
        if compact_checkpoints:result['checkpoints']=[{k:v for k,v in cp.items() if k not in ('population_X','population_ids')} for cp in self.checkpoints]
        else:result['checkpoints']=[dict(cp) for cp in self.checkpoints]
        from .run_names import names
        result.update(names(result,self.folder))
        # Copy the original public values once, before expanding private buffers.
        # Each occurrence still receives its own list, with no session aliases.
        result=copy.deepcopy(result)
        if not compact_checkpoints:
            for cp in result['checkpoints']:
                if isinstance(cp.get('population_X'),np.ndarray):cp['population_X']=cp['population_X'].tolist()
        return result
    def packet_bytes(self,include_rows=True,compact_checkpoints=False):
        import io
        output=io.BytesIO()
        self.write_packet(output,include_rows=include_rows,compact_checkpoints=compact_checkpoints)
        return output.getvalue()
    def write_packet(self,stream,include_rows=True,compact_checkpoints=False):
        from .packet_encoding import write_packet
        return write_packet(self,stream,include_rows,compact_checkpoints)
    def spatial(self,row):
        if row['id'] not in self._spatial:
            c=self.data['compilation']
            def unavailable(status,reason):
                size=len(self.frozen_problem.get('demand',[]))
                return dict(copy.deepcopy(row),spatial_status=status,spatial_reason=reason,neutral_spatial=dict(status=status,point_count=size,values_available=False))
            try:
                from .results import _compiled
                cp=_compiled(self)
                available=cp.evaluator_hash==self.data['evaluator_sha256'] and cp.config_hash==self.data['config_sha256']
            except ModelServiceError as exc:
                return unavailable('UNAVAILABLE_MODEL_SERVICE',str(exc))
            except ValueError as exc:
                if str(exc)=='SAVED_MODEL_IDENTITY_MISMATCH':
                    return unavailable('UNAVAILABLE_MODEL_IDENTITY_MISMATCH','저장 당시 Model 버전과 현재 재평가 Model이 달라 지도 재평가를 중단했습니다. 저장 원시의 배치·성능·비용은 보존됩니다. 당시 Model 연결을 복원한 뒤 다시 조회하세요.')
                if str(exc)=='SAVED_MODEL_IDENTITY_UNAVAILABLE':
                    return unavailable('UNAVAILABLE_MODEL_IDENTITY_INCOMPLETE','저장 당시 또는 현재 Model의 식별 정보가 불완전하여 지도 재평가를 중단했습니다. 저장 원시의 배치·성능·비용은 보존됩니다. 원래 계약 정보를 확인해야 합니다.')
                available=False
            except (ImportError,OSError):available=False
            if not available:
                return unavailable('UNAVAILABLE_EVALUATOR_SOURCE','Frozen evaluator or input is unavailable or incompatible')
            self.problem=cp
            try:fresh=cp.evaluate_physical(np.asarray([row['X']]),spatial=True)[0]
            except ModelServiceError as exc:
                return unavailable('UNAVAILABLE_MODEL_SERVICE',str(exc))
            if fresh['F']!=row['F'] or fresh['G']!=row['G'] or fresh['cost']!=row['cost']:raise ValueError('INTEGRITY_ERROR: stored map replay')
            from .store import record_derivation
            record_derivation(self,'MAP_REPLAY',dict(raw_id=row['id']),1,dict(placement_hash=row.get('placement_hash'),status='EXACT_FROZEN_MODEL_XFG_MATCH'))
            self._spatial[row['id']]={**row,**{k:v for k,v in fresh.items() if k not in ('config_sha256','evaluator_sha256')}}
        return copy.deepcopy(self._spatial[row['id']])
    def view(self,generation=None,*,summary=False):
        from .results import to_view
        with self.lock:return to_view(self,generation,summary=summary)

class RunService:
    def __init__(self,root,read_roots=()):
        self.store=RunStore(root);self.sessions={};self.requests={};self.read_errors={};self.lock=threading.RLock();self._loading_locks={}
        seen={self.store.root.resolve()};self.read_stores=[self.store]
        for root in read_roots:
            path=Path(root).resolve()
            if path not in seen:self.read_stores.append(RunStore(path));seen.add(path)
    def request_receipt(self,cid,request_id):
        receipts=[r for store in self.read_stores if (r:=store.request_receipt(cid,request_id)) is not None]
        if any(r!=receipts[0] for r in receipts[1:]):raise ValueError('INTEGRITY_ERROR: conflicting request receipts across run roots')
        return receipts[0] if receipts else None
    def _saved_folder(self,cid,run_id):
        folders=[p for store in self.read_stores if (p:=store.folder(cid,run_id)).is_dir()]
        if not folders:return None
        if len(folders)>1:
            from .store import sha
            signatures=[]
            for folder in folders:
                # Identical copies may be listed once; divergent histories must
                # never be silently selected based on root order.
                signatures.append((sha(folder/'raw.json'),sha(folder/'manifest.json') if (folder/'manifest.json').is_file() else None))
            if any(value!=signatures[0] for value in signatures[1:]):raise ValueError('INTEGRITY_ERROR: conflicting run copies across run roots')
        return folders[0]
    def submit(self,cid,config,optimizer=None,request_id=None,start=True,installation_domain=None):
        problem=compile_problem(cid,config)
        if installation_domain is not None:
            from .installation_domain import apply_domain
            apply_domain(problem,installation_domain,optimizer_config(problem,optimizer or {})[1])
        return self.create(problem,optimizer or {},request_id,start)
    def lookup_request(self,cid,request_id):
        receipt=self.request_receipt(cid,request_id)
        if receipt is None:raise KeyError('REQUEST_NOT_FOUND')
        folder=self._saved_folder(cid,receipt['run_id'])
        if receipt['run_id'] not in self.sessions and (folder is None or not (folder/'raw.json').is_file()):raise ValueError('REQUEST_RESERVED_WITHOUT_RAW: process interrupted; request will not be resubmitted')
        try:session=self.get(receipt['run_id'],cid)
        except KeyError:raise ValueError('REQUEST_RESERVED_WITHOUT_RAW: process interrupted; request will not be resubmitted') from None
        from .workflow import metadata_packet
        if metadata_packet(session).get('submission')!=receipt:raise ValueError('INTEGRITY_ERROR: request binding')
        return session
    request_lookup=lookup_request
    def release_saved_cache(self):
        """Drop only reloadable committed saved sessions, never a live producer.

        Existing readers keep their own reference; original files are untouched
        and every later open still passes the complete original verification.
        Caller holds the service lock. No session lock or Model IO is acquired.
        """
        ids=[rid for rid,s in self.sessions.items() if isinstance(s,StoredSession)
             and s.state in TERMINAL and (s.folder/'manifest.json').is_file()]
        for rid in ids:del self.sessions[rid]
        return ids
    def create(self,problem,optimizer,request_id=None,start=True,execution_snapshot=None,submitted_request=None):
        # Bind saved input before the global lock: cold loads and source locks
        # must never wait while holding the service lock.
        normalized,policy=optimizer_config(problem,optimizer)
        from .saved_initialization import bind
        bind(problem,normalized,lambda cid,rid:self.get(rid,cid))
        from .installation_domain import ensure_domain
        domain=ensure_domain(problem,policy)
        if execution_snapshot is not None and execution_snapshot.get('installation_domain')!=domain:
            raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: submitted snapshot differs from execution')
        fingerprint=digest(dict(problem=problem.config_hash,optimizer=normalized,policy=policy,installation_domain=domain['sha256'],
            evaluator=problem.evaluator_hash,objectives=list(problem.objective_order),diagnostics=list(problem.diagnostic_order)))
        with self.lock:
            receipt=self.request_receipt(problem.cid,request_id) if request_id else None
            if receipt:
                if receipt['fingerprint']!=fingerprint:raise ValueError('REQUEST_CONFLICT: same request ID with different configuration')
            else:
                if start and any(s.state in ACTIVE for s in self.sessions.values()):raise ValueError('A shared engine run is active')
                session=RunSession(problem,optimizer,self.store)
                session.execution_snapshot=copy.deepcopy(execution_snapshot);session.submitted_request=copy.deepcopy(submitted_request)
                if start and policy=='generic_v1':
                    released=self.release_saved_cache()
                    session.solver_metadata['resource_management']=dict(policy='RELEASE_COMMITTED_SAVED_CACHE_BEFORE_SEARCH_V1',released_run_ids=released,files_unchanged=True)
                if request_id:
                    session.submission=self.store.reserve_request(problem.cid,request_id,session.id,fingerprint)
                    session.folder=self.store.begin(session.cid,session.id);session._reserved=True
                    self.store.persist(session)
                self.sessions[session.id]=session
                if start:threading.Thread(target=session.run,daemon=True).start()
                return session
        # Waiting for an existing cold load cannot retain the global lock.
        return self.lookup_request(problem.cid,request_id)
    def get(self,run_id,cid=None):
        with self.lock:
            s=self.sessions.get(run_id)
            if s is not None:
                if cid and s.cid!=cid:raise KeyError('Run not found in contract')
                return s
            if not cid:raise KeyError('Run not found in contract')
            loading=self._loading_locks.setdefault((cid,run_id),threading.Lock())
        # A cold read must not hold the service-wide lock and block unrelated
        # status/cancel requests. Concurrent readers of one run share one load.
        with loading:
            with self.lock:s=self.sessions.get(run_id)
            if s is None:
                folder=self._saved_folder(cid,run_id)
                if folder is None:raise KeyError('Run not found in contract')
                decisions={}
                s=StoredSession(self.store.read_session(folder,decision_sink=decisions),folder,decisions)
                with self.lock:
                    s=self.sessions.setdefault(run_id,s)
            if s.cid!=cid:raise KeyError('Run not found in contract')
            return s
    def status(self,run_id,cid=None,generation=None):return self.get(run_id,cid).view(generation)
    def cancel(self,run_id,cid=None):
        s=self.get(run_id,cid)
        if hasattr(s,'cancel'):s.cancel.set()
        return dict(run_id=run_id,state='stop_requested' if s.state in ACTIVE else s.state)
    def read(self,run_id,cid):return self.get(run_id,cid).packet()
    def export(self,run_id,cid):
        s=self.get(run_id,cid)
        if s.state not in TERMINAL:raise ValueError('Saving not complete')
        return self.store.read_verified_raw(s.folder)
    def list(self,cid):
        found={k:s for k,s in self.sessions.items() if s.cid==cid}
        for store in self.read_stores:
            for p in (store.root/cid).glob('*/raw.json'):
                if p.parent.name not in found:
                    try:found[p.parent.name]=self.get(p.parent.name,cid)
                    except (ValueError,OSError,KeyError) as exc:self.read_errors[(cid,p.parent.name)]=str(exc)
        return list(found.values())
    def catalog(self,cid):
        """List discovery summaries without loading every historical raw ledger."""
        with self.lock:loaded={k:s for k,s in self.sessions.items() if s.cid==cid}
        result={}
        for rid,s in loaded.items():
            result[rid]=discovery_entry(s)
        for store in self.read_stores:
            for raw in (store.root/cid).glob('*/raw.json'):
                rid=raw.parent.name
                if rid in result:continue
                try:
                    folder=self._saved_folder(cid,rid)
                    result[rid]=store.catalog_entry(folder)
                except (ValueError,OSError,KeyError,TypeError) as exc:
                    self.read_errors[(cid,rid)]=str(exc)
                    result[rid]=dict(id=rid,run_id=rid,state='unavailable',config={},error=str(exc),integrity_status='ERROR')
        return list(result.values())


def discovery_entry(session):
    """Only copy fields needed by the picker, never full checkpoint history."""
    if not session.lock.acquire(blocking=False):
        published=getattr(session,'_discovery_snapshot',None)
        if published is not None:
            return dict(copy.deepcopy(published),discovery_status='LAST_PUBLISHED_WHILE_BUSY')
        # Stored sessions do not have a writer; only their first view may hold
        # this lock. Live sessions always publish at construction.
        session.lock.acquire()
    try:
        row=_discovery_entry_locked(session)
        session._discovery_snapshot=row
        return copy.deepcopy(row)
    finally:session.lock.release()


def _discovery_entry_locked(session):
    from .run_names import names
    cp=session.checkpoints[-1] if session.checkpoints else {}
    saved=getattr(session,'data',{})
    config=copy.deepcopy(session.config)
    optimizer=copy.deepcopy(getattr(session,'optimizer',saved.get('optimizer',{})))
    row=dict(id=session.id,run_id=session.id,state=session.state,config=config,
             evaluator_version=config.get('evaluator_version'),actual_generation=cp.get('generation'),
             evaluations=len(session.rows),checkpoint_evaluations=cp.get('nfe'),
             evaluation_count_scope='TOTAL_LOADED' if session.state in TERMINAL else 'LIVE_OBSERVED',
             runtime_version=saved.get('runtime_version','shared-engine-v1'),
             integrity_status='LIVE_RECORD' if session.state in ACTIVE else 'VERIFIED_ON_LOAD' if isinstance(session,StoredSession) else 'COMMITTED_LIVE_RECORD')
    if session.folder.exists():row.update(names(dict(row,experiment_contract_id=session.cid,optimizer=optimizer),session.folder))
    return row
