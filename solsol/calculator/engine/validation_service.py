"""Persisted validation plans orchestrate children of the existing RunService.

Restoration never launches a child. Checksums detect corruption; they are not
authentication signatures or scientific approval.
"""
import copy
import json
import re
import threading
import time
import uuid
import io
import zipfile
import hashlib
import statistics
from pathlib import Path
from .configuration import compile_request
from .workflow import execution_snapshot, request_body
from .runtime import ACTIVE
from .store import atomic_json, digest, sha

SCHEMA = 'SOLSOL_VALIDATION_V1'
RETRYABLE = {'failed', 'cancelled', 'time_limit', 'interrupted'}
PENDING = {'queued', 'preparing', 'running', 'verifying', 'saving', 'analyzing'}


class ValidationService:
    def __init__(self, service):
        self.service = service
        self.root = Path(service.store.root)/'_validation'
        self.read_roots=[Path(store.root)/'_validation' for store in service.read_stores]
        self.lock = threading.RLock()
        self.records = {}
        self.stops = {}
        self.workers = {}
        self.analyze = None

    def _folder(self, cid, vid):
        if not isinstance(cid, str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]*', cid):
            raise ValueError('INVALID_VALIDATION_CONTRACT')
        if str(uuid.UUID(vid)) != vid:
            raise ValueError('INVALID_VALIDATION_ID')
        return self.root/cid/vid

    def _read_folder(self,cid,vid):
        active=self._folder(cid,vid)
        candidates=[root/cid/vid for root in self.read_roots if (root/cid/vid/'plan.json').is_file()]
        if not candidates:return active
        # An explicit retry may have a newer state in the writable root; its
        # immutable plan must still be the same as every historical copy.
        plans=[json.loads((p/'plan.json').read_text(encoding='utf8')) for p in candidates]
        if any(p!=plans[0] for p in plans[1:]):raise ValueError('INTEGRITY_ERROR: conflicting validation plans across roots')
        if len(candidates)>1:
            states=[sha(p/'state.json') for p in candidates]
            if any(value!=states[0] for value in states[1:]):
                current=json.loads((candidates[0]/'state.json').read_text(encoding='utf8'))
                parent=current.get('storage_parent')
                if candidates[0].resolve()!=active.resolve() or not isinstance(parent,dict) or set(parent)!={'root','state_sha256'}:
                    raise ValueError('INTEGRITY_ERROR: conflicting validation states across roots')
                for folder,state_hash in zip(candidates[1:],states[1:]):
                    if Path(parent['root']).resolve()!=folder.resolve() or parent['state_sha256']!=state_hash:
                        raise ValueError('INTEGRITY_ERROR: validation storage parent mismatch')
        return candidates[0]

    def _receipt(self,cid,request_id):
        receipts=[]
        for root in self.read_roots:
            claim=root/'_requests'/cid/digest(request_id)
            if not claim.exists():continue
            if not (claim/'receipt.json').is_file():raise ValueError('VALIDATION_REQUEST_RESERVED_WITHOUT_RECEIPT: no automatic retry')
            receipt=json.loads((claim/'receipt.json').read_text(encoding='utf8'));checksum=receipt.pop('sha256',None)
            if checksum!=digest(receipt) or receipt.get('request_id')!=request_id or receipt.get('experiment_contract_id')!=cid:raise ValueError('INTEGRITY_ERROR: validation request receipt')
            receipts.append(receipt)
        if any(r!=receipts[0] for r in receipts[1:]):raise ValueError('INTEGRITY_ERROR: conflicting validation receipts across roots')
        return receipts[0] if receipts else None

    def preview(self, cid, body):
        if isinstance(body,dict) and 'schema' in body:
            if body['schema']!=SCHEMA:raise ValueError('UNSUPPORTED_SCHEMA: validation request')
            body={k:v for k,v in body.items() if k!='schema'}
        if not isinstance(body, dict) or set(body)-{'variants', 'seeds', 'diagnostics'}:
            raise ValueError('INVALID_VALIDATION_PLAN_FIELDS')
        variants, seeds = body.get('variants'), body.get('seeds')
        if not isinstance(variants, list) or not variants or not isinstance(seeds, list) or not seeds:
            raise ValueError('NONEMPTY_VARIANTS_AND_SEEDS_REQUIRED')
        if any(type(seed) is not int or not 0 <= seed <= 2147483647 for seed in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError('INVALID_OR_DUPLICATE_SEED: no seed is skipped')
        if len(variants)*len(seeds) > 64:
            raise ValueError('VALIDATION_CELL_LIMIT_64')
        diagnostics = copy.deepcopy(body.get('diagnostics', {}))
        if not isinstance(diagnostics, dict) or set(diagnostics)-{'basic','validation'} or any(v is not None and not isinstance(v,dict) for v in diagnostics.values()):
            raise ValueError('INVALID_DIAGNOSTICS_OPTIONS')
        if diagnostics.get('validation') is not None and set(diagnostics['validation'])-{'indicators','substitution','robustness'}:
            raise ValueError('INVALID_VALIDATION_DIAGNOSTICS_OPTIONS')
        # Fail invalid JSON (NaN included) before reserving any directories.
        digest(diagnostics)
        cells = []
        for index, variant in enumerate(variants):
            if not isinstance(variant, dict) or set(variant) != {'label', 'request'} or not isinstance(variant['label'], str) or not 1 <= len(variant['label']) <= 200:
                raise ValueError('INVALID_VARIANT')
            for seed in seeds:
                request = request_body(copy.deepcopy(variant['request']))
                if request.get('solver_policy') == 'legacy_eoir_v1':
                    request.setdefault('model_config', {})['seed'] = seed
                else:
                    request.setdefault('optimizer', {})['seed'] = seed
                cp, opt, _ = compile_request(cid, request)
                snapshot = execution_snapshot(cp, opt, request)
                from .validation_analysis import problem_identity, indicator_options, substitution_options
                selected = diagnostics.get('validation') or {}
                additional=0
                from .research_diagnostics import options_checked
                if diagnostics.get('basic') is not None:
                    basic=options_checked(diagnostics['basic'])
                    if basic['generation'] is not None and basic['generation']>=snapshot['optimizer']['checkpoints']:raise ValueError('DIAGNOSTIC_GENERATION_OUTSIDE_PLAN')
                    if basic['ablation']:additional+=(len(basic['raw_ids']) or basic['representatives'])*len(cp.sensor_order)
                if selected.get('indicators') is not None:indicator_options(cp, selected['indicators'])
                def raw_ids_checked(option):
                    ids=option.get('raw_ids')
                    if not isinstance(ids,list) or not 1<=len(ids)<=5 or any(type(i) is not int or i<0 for i in ids) or len(set(ids))!=len(ids):raise ValueError('VALIDATION_SELECT_1_TO_5_RAW_IDS')
                    return ids
                if selected.get('substitution') is not None:
                    option=substitution_options(cp, selected['substitution']);ids=raw_ids_checked(option)
                    additional+=len(ids)*(1+option['budget'])
                if selected.get('robustness') is not None:
                    option=selected['robustness']
                    if not isinstance(option,dict) or set(option)!={'raw_ids','variants'} or not isinstance(option['variants'],list) or not 1<=len(option['variants'])<=8:raise ValueError('ROBUSTNESS_FIELDS')
                    ids=raw_ids_checked(option)
                    for variant_condition in option['variants']:
                        if not isinstance(variant_condition,dict) or set(variant_condition)!={'label','request'} or not isinstance(variant_condition['label'],str):raise ValueError('ROBUSTNESS_VARIANT')
                        other,_,_=compile_request(cid,variant_condition['request'])
                        if other.candidate_order!=cp.candidate_order or other.sensor_order!=cp.sensor_order or other.objective_order!=cp.objective_order:raise ValueError('ROBUSTNESS_PHYSICAL_OR_OBJECTIVE_ORDER_MISMATCH')
                    additional+=len(ids)*len(option['variants'])
                cells.append(dict(cell_id=f'cell-{len(cells):03d}', variant_index=index, label=variant['label'], seed=seed, request=request, execution_snapshot=snapshot, problem_sha256=digest(problem_identity(cp)), expected_nfe=snapshot['declared_nfe'],additional_diagnostic_evaluation_budget=additional))
        expected = sum(c['expected_nfe'] for c in cells)
        if expected > 200000:
            raise ValueError('VALIDATION_NFE_LIMIT_200000')
        plan = dict(schema=SCHEMA, experiment_contract_id=cid, variants=copy.deepcopy(variants), seeds=copy.deepcopy(seeds), diagnostics=diagnostics, cells=cells, total_cells=len(cells), expected_nfe=expected, limits=dict(cells=64, expected_nfe=200000), budget_note='GENERATION_NFE_WITH_TIME_SAFETY_LIMIT: declared NFE = population × (generations + 1). Arbitrary exact NFE termination mid-population is unsupported; choose population/generations explicitly. Time-limit attempts are retained but excluded from completed convergence statistics.', claim='OPERATIONAL_VALIDATION_PLAN_NOT_SCIENTIFIC_APPROVAL')
        plan.update(total_search_evaluations=expected,additional_diagnostic_evaluation_budget=sum(c['additional_diagnostic_evaluation_budget'] for c in cells),diagnostic_budget_note='Worst-case additional evaluator rows: ablation selected/representative rows × registered sensor types; substitution selected rows × (1 + candidate budget); fixed-X robustness selected rows × variants. Indicators/correlation use stored rows. Raw ID existence and Pareto membership are checked after each child; unavailable selections are errors, never skipped. Actual derived attempted/completed counts are stored separately. This total excludes automatic raw replay and view/preview work.')
        plan['total_combined_evaluation_budget']=expected+plan['additional_diagnostic_evaluation_budget']
        plan['initialization_preparation_evaluation_budget']=sum((c['execution_snapshot'].get('initialization_preparation') or {}).get('max_model_evaluations',0) for c in cells)
        plan['total_combined_evaluation_budget']+=plan['initialization_preparation_evaluation_budget']
        plan['initialization_comparison_note']='Equal search NFE is not equal total Model effort. Preparation cap and actual preparation/search/replay counts are separate. MILP uses a calculator local approximation with original Model acceptance.'
        plan['plan_sha256']=digest(plan)
        return plan

    def _save(self, record):
        folder=self._folder(record['experiment_contract_id'],record['validation_id'])
        if not (folder/'plan.json').is_file():
            original=self._read_folder(record['experiment_contract_id'],record['validation_id'])
            if original!=folder:
                atomic_json(folder/'plan.json',json.loads((original/'plan.json').read_text(encoding='utf8')))
                record.setdefault('storage_parent',dict(root=str(original),state_sha256=sha(original/'state.json')))
        record['updated_at'] = time.time()
        value = copy.deepcopy(record)
        value['state_sha256'] = digest(value)
        atomic_json(self._folder(record['experiment_contract_id'], record['validation_id'])/'state.json', value)

    def _load(self, cid, vid):
        key = cid, vid
        if key in self.records:
            return self.records[key]
        folder = self._read_folder(cid, vid)
        if not (folder/'plan.json').is_file():
            raise KeyError('VALIDATION_NOT_FOUND: no saved plan for this contract and ID')
        if not (folder/'state.json').is_file():
            raise ValueError('INTEGRITY_ERROR: validation state missing')
        plan = json.loads((folder/'plan.json').read_text(encoding='utf-8'))
        if plan.get('schema')!=SCHEMA:raise ValueError('UNSUPPORTED_SCHEMA: validation plan')
        if plan.get('plan_sha256') != digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) or plan.get('experiment_contract_id') != cid:
            raise ValueError('INTEGRITY_ERROR: validation plan')
        record = json.loads((folder/'state.json').read_text(encoding='utf-8'))
        if record.get('schema')!=SCHEMA:raise ValueError('UNSUPPORTED_SCHEMA: validation state')
        checksum = record.pop('state_sha256', None)
        if checksum != digest(record) or record.get('plan_sha256') != plan['plan_sha256'] or record.get('validation_id') != vid or record.get('experiment_contract_id') != cid:
            raise ValueError('INTEGRITY_ERROR: validation state')
        if [c['cell_id'] for c in record['cells']] != [c['cell_id'] for c in plan['cells']]:
            raise ValueError('INTEGRITY_ERROR: validation cell ordering')
        changed = record['state'] in PENDING or record['state'] == 'stop_requested'
        was_active=changed
        for cell, frozen in zip(record['cells'], plan['cells']):
            if any(cell.get(k) != v for k, v in frozen.items()):
                raise ValueError('INTEGRITY_ERROR: frozen validation cell')
            for attempt in cell['attempts']:
                if attempt.get('run_id'):
                    child_folder = self.service._saved_folder(cid, attempt['run_id'])
                    if child_folder is not None and (child_folder/'raw.json').is_file():
                        child = self.service.store.read(child_folder)
                        if child['experiment_contract_id'] != cid or child['run_id'] != attempt['run_id'] or child['config_sha256'] != attempt['config_sha256'] or (child.get('execution_snapshot') or {}).get('execution_sha256') != attempt['execution_sha256']:
                            raise ValueError('INTEGRITY_ERROR: validation child identity')
                        for name, checksum in attempt.get('artifact_sha256',{}).items():
                            if sha(child_folder/name) != checksum:raise ValueError('INTEGRITY_ERROR: validation child bytes')
                        if child['state'] not in PENDING and ('elapsed_seconds' not in attempt or 'artifact_sha256' not in attempt):
                            attempt.update(elapsed_seconds=child.get('elapsed_seconds',0),artifact_sha256={p.name:sha(p) for p in [child_folder/'raw.json',child_folder/'manifest.json'] if p.is_file()});changed=True
                        if attempt['state'] in PENDING and child['state'] not in PENDING:
                            attempt.update(state=child['state'],nfe=child.get('nfe',0),elapsed_seconds=child.get('elapsed_seconds',0),error=child.get('error'),artifact_sha256={p.name:sha(p) for p in [child_folder/'raw.json',child_folder/'manifest.json'] if p.is_file()})
                            if attempt is cell['attempts'][-1]:cell['state']=child['state']
                            changed=True
                    elif attempt['state'] not in PENDING:
                        raise ValueError('INTEGRITY_ERROR: validation child raw missing')
            if cell['state'] in PENDING:
                cell['state'] = 'interrupted'
                if cell['attempts']:
                    cell['attempts'][-1].update(state='interrupted', error='Process restarted; child is not automatically resumed')
                changed = True
                was_active=True
        if changed:
            if was_active:record['state'] = 'completed' if all(c['state']=='completed' for c in record['cells']) else 'interrupted'
            record['restore_semantics'] = 'EXPLICIT_RETRY_REQUIRED_NO_SOLVER_RESUME'
            self._save(record)
        self.records[key] = record
        return record

    def submit(self, cid, body, request_id, expected_hash):
        if isinstance(body,dict) and 'schema' in body:
            if body['schema']!=SCHEMA:raise ValueError('UNSUPPORTED_SCHEMA: validation request')
            body={k:v for k,v in body.items() if k!='schema'}
        self._folder(cid,'00000000-0000-0000-0000-000000000000')
        if not isinstance(body,dict) or set(body)-{'variants','seeds','diagnostics'}:raise ValueError('INVALID_VALIDATION_PLAN_FIELDS')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', request_id):
            raise ValueError('INVALID_VALIDATION_REQUEST_ID')
        receipt=self._receipt(cid,request_id)
        if receipt is not None:
            if receipt['plan_sha256']!=expected_hash:raise ValueError('VALIDATION_REQUEST_CONFLICT')
            stored=json.loads((self._read_folder(cid,receipt['validation_id'])/'plan.json').read_text(encoding='utf-8'))
            if any(body.get(k,{} if k=='diagnostics' else None)!=stored[k] for k in ('variants','seeds','diagnostics')):raise ValueError('VALIDATION_REQUEST_CONFLICT')
            return self.get(cid,receipt['validation_id'])
        plan = self.preview(cid, body)
        if plan['plan_sha256'] != expected_hash:
            raise ValueError('VALIDATION_PLAN_CHANGED: preview again')
        with self.lock:
            claim = self.root/'_requests'/cid/digest(request_id)
            claim.parent.mkdir(parents=True, exist_ok=True)
            try:
                claim.mkdir()
            except FileExistsError:
                receipt_path = claim/'receipt.json'
                if not receipt_path.is_file():
                    raise ValueError('VALIDATION_REQUEST_RESERVED_WITHOUT_RECEIPT: no automatic retry')
                receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                checksum = receipt.pop('sha256', None)
                if checksum != digest(receipt) or receipt.get('request_id') != request_id or receipt.get('experiment_contract_id') != cid:
                    raise ValueError('INTEGRITY_ERROR: validation request receipt')
                if receipt['plan_sha256'] != expected_hash:
                    raise ValueError('VALIDATION_REQUEST_CONFLICT')
                return self.get(cid, receipt['validation_id'])
            vid = str(uuid.uuid4())
            folder = self._folder(cid, vid)
            folder.mkdir(parents=True, exist_ok=False)
            atomic_json(folder/'plan.json', plan)
            record = dict(schema=SCHEMA, experiment_contract_id=cid, validation_id=vid, request_id=request_id, plan_sha256=expected_hash, state='queued', created_at=time.time(), total_cells=plan['total_cells'], expected_nfe=plan['expected_nfe'], diagnostics=plan['diagnostics'], cells=[dict(c, state='queued', attempts=[], diagnostics={'status': 'NOT_RUN'}) for c in plan['cells']], errors=[], restore_semantics='STORED_VALIDATION_ONLY_NOT_SOLVER_RESUME')
            self.records[cid, vid] = record
            self._save(record)
            receipt = dict(experiment_contract_id=cid, request_id=request_id, validation_id=vid, plan_sha256=expected_hash)
            receipt['sha256'] = digest(receipt)
            atomic_json(claim/'receipt.json', receipt)
            self._start(record)
            return self.get(cid, vid)

    def lookup_request(self,cid,request_id):
        self._folder(cid,'00000000-0000-0000-0000-000000000000')
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',request_id):raise ValueError('INVALID_VALIDATION_REQUEST_ID')
        receipt=self._receipt(cid,request_id)
        if receipt is None:raise KeyError('VALIDATION_REQUEST_NOT_FOUND')
        record=self.get(cid,receipt['validation_id'])
        if record['plan_sha256']!=receipt['plan_sha256']:raise ValueError('INTEGRITY_ERROR: validation receipt plan')
        return record

    def _start(self, record):
        key = record['experiment_contract_id'], record['validation_id']
        stop = threading.Event()
        self.stops[key] = stop
        worker = threading.Thread(target=self._run, args=(record, stop), daemon=True)
        self.workers[key] = worker
        worker.start()

    def _run(self, record, stop):
        cid, vid = record['experiment_contract_id'], record['validation_id']
        with self.lock:
            record['state'] = 'running'
            self._save(record)
        for cell in record['cells']:
            if cell['state'] != 'queued':
                continue
            child = None
            attempt = None
            request_id = f'validation:{vid}:{cell["cell_id"]}:{len(cell["attempts"])+1}'
            try:
                while not stop.is_set():
                    with self.service.lock:
                        if not any(s.state in ACTIVE for s in self.service.sessions.values()):
                            cp, opt, _ = compile_request(cid, cell['request'])
                            snapshot = execution_snapshot(cp, opt, cell['request'])
                            if snapshot != cell['execution_snapshot']:
                                raise ValueError('VALIDATION_EXECUTION_SNAPSHOT_CHANGED')
                            attempt_id = len(cell['attempts'])+1
                            request_id = f'validation:{vid}:{cell["cell_id"]}:{attempt_id}'
                            child = self.service.create(cp, opt, request_id=request_id, start=False, execution_snapshot=snapshot, submitted_request=cell['request'])
                            break
                    stop.wait(.1)
                if stop.is_set() and child is None:
                    with self.lock:
                        cell['state'] = 'cancelled'
                        cell['cancellation'] = 'NOT_STARTED_BY_USER_STOP'
                        self._save(record)
                    continue
                with self.lock:
                    attempt = dict(attempt=len(cell['attempts'])+1, run_id=child.id, request_id=request_id, retry_of=cell['attempts'][-1]['run_id'] if cell['attempts'] else None, original_run_id=cell['attempts'][0]['run_id'] if cell['attempts'] else child.id, config_sha256=cp.config_hash, execution_sha256=snapshot['execution_sha256'], state='running', nfe=0, diagnostics={'status': 'NOT_RUN'})
                    cell['attempts'].append(attempt)
                    cell['state'] = 'running'
                    self._save(record)
                if stop.is_set():
                    child.cancel.set()
                child.run()
                with self.lock:
                    p = child.packet(include_rows=False,compact_checkpoints=True)
                    attempt.update(state=child.state, nfe=p.get('nfe', 0), elapsed_seconds=p.get('elapsed_seconds',0), error=p.get('error'), termination_reason=p.get('termination_reason'),artifact_sha256={path.name:sha(path) for path in [child.folder/'raw.json',child.folder/'manifest.json'] if path.is_file()},preparation_evaluations=p.get('counters',{}).get('preparation_evaluations'),preparation_seconds=(p.get('initialization') or {}).get('seconds'),initialization=p.get('initialization'),initial_archive_count=len(p.get('checkpoints',[{}])[0].get('archive_ids',[])) if p.get('checkpoints') else None,archive_count=len(p.get('checkpoints',[{}])[-1].get('archive_ids',[])) if p.get('checkpoints') else None)
                    cell['state'] = child.state
                    self._save(record)
                if child.state == 'completed' and record['diagnostics'] and not stop.is_set():
                    if self.analyze is None:
                        attempt['diagnostics'] = dict(status='NOT_RUN', reason='Analysis callback not configured')
                    else:
                        try:
                            result = self.analyze(child, copy.deepcopy(record['diagnostics']))
                            def error_status(value):
                                return isinstance(value,dict) and (value.get('status') in ('ERROR','FAILED') or any(error_status(v) for v in value.values())) or isinstance(value,list) and any(error_status(v) for v in value)
                            attempt['diagnostics'] = dict(status='ERROR' if error_status(result) else 'COMPLETED', result=result)
                        except Exception as exc:
                            attempt['diagnostics'] = dict(status='ERROR', error=type(exc).__name__+': '+str(exc))
                    cell['diagnostics'] = copy.deepcopy(attempt['diagnostics'])
            except Exception as exc:
                with self.lock:
                    cell['state'] = 'failed'
                    error = type(exc).__name__+': '+str(exc)
                    if attempt is not None:
                        attempt.update(state='failed', error=error)
                    else:
                        cell['attempts'].append(dict(attempt=len(cell['attempts'])+1, run_id=None if child is None else child.id, request_id=request_id, retry_of=cell['attempts'][-1]['run_id'] if cell['attempts'] else None, original_run_id=cell['attempts'][0]['run_id'] if cell['attempts'] else None, config_sha256=cell['execution_snapshot']['config_sha256'], execution_sha256=cell['execution_snapshot']['execution_sha256'], state='failed', nfe=0, error=error, diagnostics={'status':'NOT_RUN'}))
                    record['errors'].append(dict(cell_id=cell['cell_id'], run_id=None if child is None else child.id, error=error))
            finally:
                with self.lock:
                    self._save(record)
        with self.lock:
            record['state'] = 'cancelled' if stop.is_set() else 'completed' if all(c['state']=='completed' for c in record['cells']) else 'completed_with_failures'
            self._save(record)

    def _stored_indicators(self,cid,attempt):
        from .workflow import sidecar_index
        reference=(attempt.get('diagnostics',{}).get('result') or {}).get('validation')
        if not isinstance(reference,dict) or not reference.get('diagnostic_id'):return {}
        diagnostic_id=reference['diagnostic_id']
        if str(uuid.UUID(diagnostic_id))!=diagnostic_id:raise ValueError('INTEGRITY_ERROR: validation diagnostic reference')
        child=self.service.get(attempt['run_id'],cid)
        entry=next((e for e in sidecar_index(child) if e['path']==diagnostic_id+'.json'),None)
        if entry is None or entry['status'] not in ('COMPLETED','ERROR') or entry['sha256']!=reference.get('file_sha256'):raise ValueError('INTEGRITY_ERROR: pinned validation diagnostic')
        data=json.loads((child.folder/'diagnostics'/entry['path']).read_text(encoding='utf-8'))
        if data!=reference.get('sidecar'):raise ValueError('INTEGRITY_ERROR: validation diagnostic payload')
        payload=data.get('payload',{});indicators=payload.get('indicators',{})
        if not indicators.get('trace'):return {}
        key=digest(indicators.get('options',{}));trace=indicators['trace'][-1]
        return {key:dict(options=indicators.get('options'),generation=trace['generation'],nfe=trace['nfe'],diagnostic_id=diagnostic_id,definition_version=payload.get('definition_version'),definition_sha256=payload.get('definition_sha256'),**{metric:trace[metric] for metric in ('hv','igd_plus')})}

    def get(self, cid, vid):
        with self.lock:
            record = copy.deepcopy(self._load(cid, vid))
            counts = {}
            for cell in record['cells']:
                if cell['attempts'] and cell['state'] in PENDING:
                    run_id = cell['attempts'][-1]['run_id']
                    child = self.service.sessions.get(run_id)
                    if child is not None:
                        p = child.progress_snapshot() if hasattr(child,'progress_snapshot') else child.packet(include_rows=False)
                        cell['attempts'][-1].update(state=child.state, nfe=p.get('nfe',0),elapsed_seconds=p.get('elapsed_seconds',0))
                        cell['progress']={k:p.get(k) for k in ('generation','declared_nfe','requested_generations','counters','archive_count','target_archive_count','checkpoint_elapsed_seconds','cancel_requested')}
                        cell['phase']=child.state
                counts[cell['state']] = counts.get(cell['state'],0)+1
            record['counts'] = counts
            record['total_attempts'] = sum(len(c['attempts']) for c in record['cells'])
            record['observed_nfe_all_attempts'] = sum(a.get('nfe',0) for c in record['cells'] for a in c['attempts'])
            groups={}
            for cell in record['cells']:
                group=groups.setdefault(cell['problem_sha256'],dict(problem_sha256=cell['problem_sha256'],total_cells=0,seeds=[],counts={},successful_nfe=[],successful_elapsed_seconds=[],indicator_groups={}))
                group['total_cells']+=1;group['seeds'].append(cell['seed']);group['counts'][cell['state']]=group['counts'].get(cell['state'],0)+1
                if cell['state']=='completed' and cell['attempts']:
                    attempt=cell['attempts'][-1]
                    group['successful_nfe'].append(attempt.get('nfe',0));group['successful_elapsed_seconds'].append(attempt.get('elapsed_seconds',0))
                    if attempt['diagnostics'].get('status') in ('COMPLETED','ERROR'):
                        reference=(attempt['diagnostics'].get('result') or {}).get('validation') or {}
                        cell['indicator_source']=dict(diagnostic_id=reference.get('diagnostic_id'),status=reference.get('sidecar',{}).get('payload',{}).get('indicators',{}).get('status','NOT_RUN'),reason=reference.get('sidecar',{}).get('payload',{}).get('indicators',{}).get('reason'))
                        for indicator_key,value in self._stored_indicators(cid,attempt).items():
                            snap=cell['execution_snapshot'];comparison=dict(declared_nfe=snap['declared_nfe'],wallclock_limit_seconds=snap['termination']['wallclock_limit_seconds'],solver=snap['solver'],generation=value['generation'],nfe=value['nfe'])
                            definition=dict(version=value['definition_version'],sha256=value['definition_sha256'])
                            grouped_key=digest(dict(options=indicator_key,comparison=comparison,definition=definition))
                            indicator=group['indicator_groups'].setdefault(grouped_key,dict(options_sha256=indicator_key,options=value['options'],comparison=comparison,definition=definition,hv=[],igd_plus=[],metric_statuses={'hv':[],'igd_plus':[]}))
                            for metric in ('hv','igd_plus'):
                                indicator['metric_statuses'][metric].append(dict(cell_id=cell['cell_id'],**value[metric]))
                                if value[metric].get('status')=='OBSERVED' and value[metric].get('value') is not None:indicator[metric].append(value[metric]['value'])
            for group in groups.values():
                for key in ('successful_nfe','successful_elapsed_seconds'):
                    values=group.pop(key);group[key]=dict(samples=len(values),mean=statistics.mean(values) if values else None,variance=statistics.variance(values) if len(values)>1 else None)
                group['denominator_definition']='all planned variant-seed cells; statistics use latest completed attempts only; failures retained in counts'
                for indicator in group['indicator_groups'].values():
                    comparison=indicator['comparison'];eligible=[]
                    for cell in record['cells']:
                        snap=cell['execution_snapshot']
                        if cell['problem_sha256']!=group['problem_sha256'] or snap['declared_nfe']!=comparison['declared_nfe'] or snap['termination']['wallclock_limit_seconds']!=comparison['wallclock_limit_seconds'] or snap['solver']!=comparison['solver']:continue
                        requested=(record.get('diagnostics',{}).get('validation') or {}).get('indicators')
                        if requested is None or digest(requested)!=indicator['options_sha256']:continue
                        generations=requested.get('checkpoints')
                        planned_generation=max(generations) if generations else snap['optimizer']['checkpoints']-1
                        if planned_generation==comparison['generation']:eligible.append(cell['cell_id'])
                    indicator['eligible_cell_ids']=eligible
                    for metric in ('hv','igd_plus'):
                        values=indicator[metric];indicator[metric]=dict(total_cells=len(eligible),observed_samples=len(values),missing_or_not_run=len(eligible)-len(values),mean=statistics.mean(values) if values else None,variance=statistics.variance(values) if len(values)>1 else None)
                group['indicator_groups']=list(group['indicator_groups'].values())
            record['problem_groups']=list(groups.values())
            comparisons={}
            for cell in record['cells']:
                snap=cell['execution_snapshot']
                budget=dict(problem_sha256=cell['problem_sha256'],declared_nfe=snap['declared_nfe'],wallclock_limit_seconds=snap['termination']['wallclock_limit_seconds'],solver=snap['solver'],initialization_preparation=snap.get('initialization_preparation'),policy='GENERATION_NFE_WITH_TIME_SAFETY_LIMIT')
                key=digest(budget)
                group=comparisons.setdefault(key,dict(comparison_sha256=key,contract=budget,cell_ids=[],counts={},completed_nfe=[],completed_elapsed_seconds=[],preparation_evaluations=[],preparation_seconds=[],initial_archive_count=[],archive_count=[]))
                group['cell_ids'].append(cell['cell_id']);group['counts'][cell['state']]=group['counts'].get(cell['state'],0)+1
                if cell['state']=='completed' and cell['attempts']:
                    a=cell['attempts'][-1];group['completed_nfe'].append(a.get('nfe',0));group['completed_elapsed_seconds'].append(a.get('elapsed_seconds',0))
                    for metric in ('preparation_evaluations','preparation_seconds','initial_archive_count','archive_count'):
                        if a.get(metric) is not None:group[metric].append(a[metric])
            for group in comparisons.values():
                same_problem=[c for c in record['cells'] if c['problem_sha256']==group['contract']['problem_sha256']]
                group['budget_comparability']='EQUAL_DECLARED_NFE_AND_TIME_LIMIT' if len({(c['execution_snapshot']['declared_nfe'],c['execution_snapshot']['termination']['wallclock_limit_seconds']) for c in same_problem})==1 else 'SAME_PROBLEM_UNEQUAL_BUDGETS_SEPARATE_GROUPS'
                for metric in ('completed_nfe','completed_elapsed_seconds','preparation_evaluations','preparation_seconds','initial_archive_count','archive_count'):
                    values=group[metric];group[metric]=dict(total_cells=len(group['cell_ids']),completed_samples=len(values),mean=statistics.mean(values) if values else None,variance=statistics.variance(values) if len(values)>1 else None)
            record['comparison_groups']=list(comparisons.values())
            return record

    def list(self, cid):
        if not re.fullmatch(r'[A-Z][A-Z0-9_-]*', cid):
            raise ValueError('INVALID_VALIDATION_CONTRACT')
        result = []
        folders={p.name:p for root in reversed(self.read_roots) for p in (root/cid).glob('*')}
        for folder in sorted(folders.values()):
            if not folder.is_dir():
                continue
            try:
                record = self.get(cid, folder.name)
                result.append({k:record[k] for k in ('validation_id','plan_sha256','state','created_at','total_cells','expected_nfe','counts','total_attempts','observed_nfe_all_attempts')})
            except (ValueError, OSError, KeyError) as exc:
                result.append(dict(validation_id=folder.name,state='unavailable',error=str(exc)))
        return dict(experiment_contract_id=cid, validations=result)

    def cancel(self, cid, vid):
        with self.lock:
            record = self._load(cid, vid)
            key = cid, vid
            if key in self.stops and self.workers[key].is_alive():
                self.stops[key].set()
                record['state'] = 'stop_requested'
                for cell in record['cells']:
                    if cell['state'] in PENDING and cell['attempts']:
                        self.service.cancel(cell['attempts'][-1]['run_id'], cid)
                self._save(record)
            return self.get(cid, vid)

    def retry(self, cid, vid, cell_ids):
        with self.lock:
            record = self._load(cid, vid)
            key = cid, vid
            if key in self.workers and self.workers[key].is_alive():
                raise ValueError('VALIDATION_STILL_ACTIVE')
            if not isinstance(cell_ids, list) or not cell_ids or any(not isinstance(i,str) for i in cell_ids) or len(set(cell_ids))!=len(cell_ids):
                raise ValueError('INVALID_RETRY_CELLS')
            cells = {c['cell_id']:c for c in record['cells']}
            if any(i not in cells or cells[i]['state'] not in RETRYABLE for i in cell_ids):
                raise ValueError('ONLY_EXPLICIT_FAILED_TERMINAL_CELLS_CAN_RETRY')
            for i in cell_ids:
                cp,opt,_=compile_request(cid,cells[i]['request'])
                if execution_snapshot(cp,opt,cells[i]['request'])!=cells[i]['execution_snapshot']:raise ValueError('VALIDATION_EXECUTION_SNAPSHOT_CHANGED')
            for i in cell_ids:
                cells[i]['state'] = 'queued'
                cells[i]['diagnostics'] = {'status':'NOT_RUN'}
            record['state'] = 'queued'
            self._save(record)
            self._start(record)
            return self.get(cid, vid)

    def export(self, cid, vid):
        record = self.get(cid, vid)
        plan = json.loads((self._read_folder(cid, vid)/'plan.json').read_text(encoding='utf-8'))
        if plan.get('plan_sha256') != record['plan_sha256'] or plan.get('plan_sha256') != digest({k:v for k,v in plan.items() if k!='plan_sha256'}):
            raise ValueError('INTEGRITY_ERROR: validation export plan')
        from .workflow import sidecar_index
        folder=self._read_folder(cid,vid)
        members={name:(folder/name).read_bytes() for name in ('plan.json','state.json')}
        state=json.loads(members['state.json']);state_sha=state.pop('state_sha256',None)
        if state_sha!=digest(state):raise ValueError('INTEGRITY_ERROR: validation export state')
        for cell in record['cells']:
            for attempt in cell['attempts']:
                if not attempt.get('run_id'):continue
                child_folder=self.service._saved_folder(cid,attempt['run_id'])
                if child_folder is None:raise ValueError('INTEGRITY_ERROR: validation child raw missing')
                self.service.store.read(child_folder)
                child=self.service.get(attempt['run_id'],cid)
                if any(s['status'] in ('INTEGRITY_ERROR','UNSUPPORTED_SCHEMA') for s in sidecar_index(child)):raise ValueError('INTEGRITY_ERROR: validation diagnostic sidecar')
                for path in sorted(child_folder.rglob('*')):
                    if path.is_file() and path.suffix in ('.json','.npz'):
                        members['children/'+child.id+'/'+path.relative_to(child_folder).as_posix()]=path.read_bytes()
        members['summary.json']=json.dumps(record,ensure_ascii=False,allow_nan=False).encode()
        manifest=dict(schema='SOLSOL_VALIDATION_EXPORT_V1',experiment_contract_id=cid,validation_id=vid,plan_sha256=record['plan_sha256'],files={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in members.items()},read_only_export=True)
        members['export_manifest.json']=json.dumps(manifest,ensure_ascii=False,allow_nan=False).encode()
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in members.items():z.writestr(name,data)
        return output.getvalue()
