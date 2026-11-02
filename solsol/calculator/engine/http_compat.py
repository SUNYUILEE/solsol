"""Existing HTTP routes backed by the common service and immutable legacy reader."""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
import numpy as np
from .runtime import RunService, RunSession, ACTIVE, TERMINAL, source_snapshot
from .legacy import read_legacy, LegacyRecord


class HTTPCompat:
    def __init__(self, root, busy=lambda: False, runtime_root=None):
        self.root = Path(root)
        legacy_root=self.root/'shared_engine_v1'
        self.service = RunService(runtime_root or legacy_root,read_roots=[legacy_root] if runtime_root else [])
        self.busy = busy
        self.legacy = {}
        self.unavailable = {}
        self.loaded_sources = source_snapshot()
        from .run_management import RunManagement
        self.management=RunManagement(self)

    def folders(self, cid):
        bases = [self.root/cid] if cid == 'RADAR_RF_SCANNER' else list((self.root/cid).glob('*'))
        if cid == 'RADAR_RF_SCANNER':
            bases += [self.root/'common_v2'/cid, self.root/'common_v3'/cid]
        return [p for base in bases for p in base.glob('*') if p.is_dir() and re.fullmatch(r'[0-9a-f-]{36}', p.name)]

    def get_record(self, cid, rid):
        try:
            return self.service.get(rid, cid)
        except KeyError:
            key = (cid, rid)
            if key not in self.legacy:
                folder = next((p for p in self.folders(cid) if p.name == rid), None)
                if folder is None:
                    raise KeyError('Run not found in this contract')
                self.legacy[key] = read_legacy(folder)
            return self.legacy[key]

    def collection(self, cid, include_deleted=False):
        summaries = {r['run_id']:r for r in self.service.catalog(cid)}
        records = {}
        for folder in self.folders(cid):
            key = cid, folder.name
            try:
                records[key] = self.get_record(*key)
            except (ValueError, OSError, KeyError) as exc:
                self.unavailable[key] = str(exc)
        rows = []
        for (_, rid), r in records.items():
            p = r.packet(include_rows=False) if isinstance(r, LegacyRecord) else r.packet(include_rows=False,compact_checkpoints=True)
            cp = p.get('checkpoints', getattr(r, 'snapshots', []))
            rows.append(dict(id=rid, run_id=rid, state=r.state, config=r.config, evaluator_version=r.config.get('evaluator_version'), actual_generation=cp[-1]['generation'] if cp else None, evaluations=p.get('nfe', len(p.get('rows', []))), runtime_version=p.get('runtime_version', 'legacy')))
            from .run_names import names
            rows[-1].update(names(p,r.folder))
        rows += [r for rid,r in summaries.items() if (cid,rid) not in records]
        rows += [dict(id=rid, run_id=rid, state='unavailable', config={}, error=error) for (contract, rid), error in self.unavailable.items() if contract == cid and (contract, rid) not in records]
        rows += [dict(id=rid, run_id=rid, state='unavailable', config={}, error=error) for (contract, rid), error in getattr(self.service, 'read_errors', {}).items() if contract == cid and (contract, rid) not in records and rid not in summaries]
        return self.management.apply(cid,rows,include_deleted)

    def export(self, record):
        if isinstance(record, LegacyRecord):
            return record.export_bytes()
        if record.state not in TERMINAL:
            raise ValueError('Saving not complete')
        raw = self.service.export(record.id, record.cid)
        if record.cid != 'RADAR_EOIR' or record.config.get('_research'):
            from .run_names import names
            return raw, names(record.packet(include_rows=False,compact_checkpoints=True),record.folder)['export_name']+'.json', 'application/json'
        packet = json.loads(raw)
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
        arrays = io.BytesIO()
        rows = packet['rows']
        n = len(packet['problem']['sites'])
        k = len(rows[0]['G']) if rows else len(packet['registry']['constraint_order'])
        np.savez_compressed(arrays, X=np.asarray([r['X'] for r in rows], dtype=np.uint8).reshape(-1, n, 2), F=np.asarray([r['F'] for r in rows], dtype=float).reshape(-1, 3), G=np.asarray([r['G'] for r in rows], dtype=float).reshape(len(rows), k))
        result = dict(packet, id=record.id)
        members = {'raw.json': raw, 'raw.npz': arrays.getvalue(), 'config.json': encode(packet['config']), 'problem.json': encode(packet['problem']), 'result.json': encode(result), 'checkpoints.json': encode(packet['checkpoints'])}
        manifest = dict(schema='SOLSOL_SHARED_ENGINE_COMPAT_EXPORT_V1', id=record.id, state=record.state, source_schema=packet['schema'], files={name: hashlib.sha256(data).hexdigest() for name, data in members.items()}, publication_contract='append-only-commit-v1', provenance='DERIVED_EXPORT_OF_SHARED_RAW_NOT_LEGACY_RUN')
        members['manifest.json'] = encode(manifest)
        members['completion.json'] = encode(dict(schema=manifest['publication_contract'], run_id=record.id, result_sha256=hashlib.sha256(members['result.json']).hexdigest(), manifest_sha256=hashlib.sha256(members['manifest.json']).hexdigest()))
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, data in members.items():
                z.writestr(name, data)
        return output.getvalue(), record.id+'.zip', 'application/zip'

    @staticmethod
    def body(handler,limit=65536):
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= limit:
            raise ValueError('Request size out of range')
        obj = json.loads(handler.rfile.read(length))
        if not isinstance(obj, dict):
            raise ValueError('JSON object required')
        return obj

    def get(self, h, endpoint, query):
        if self.management.get(h,endpoint,query):return True
        from .configuration_http import get
        if get(self,h,endpoint,query):return True
        cid = h.contract
        collection = 'jobs' if cid == 'RADAR_EOIR' else 'runs'
        if cid == 'RADAR_EOIR' and endpoint == '/api/archive':
            allowed = {'page', 'limit', 'state', 'initializer', 'design', 'q', 'current'}
            if set(query)-allowed or any(len(v)!=1 for v in query.values()):
                raise ValueError('Invalid archive query')
            value = lambda k, default='': query.get(k, [default])[0]
            page, limit = int(value('page','1')), int(value('limit','20'))
            if page < 1 or limit not in (10,20,50):
                raise ValueError('Invalid archive page')
            rows = self.collection(cid)
            total_all = len(rows)
            current = next((r for r in rows if r['id']==value('current')), None)
            rows = [r for r in rows if (not value('state') or r['state']==value('state')) and (not value('initializer') or r['config'].get('initializer')==value('initializer')) and (not value('design') or r['config'].get('design')==value('design')) and (not value('q') or value('q').casefold() in (r['id']+' '+str(r['config'].get('seed',''))).casefold())]
            pages = max(1,(len(rows)+limit-1)//limit)
            page = min(page,pages)
            h.send_json(dict(schema='run-archive-v1',items=rows[(page-1)*limit:page*limit],current=current,page=page,pages=pages,limit=limit,total=len(rows),total_all=total_all,unavailable_count=sum(r['state']=='unavailable' for r in rows),unknown_time_count=len(rows),order='store_discovery',time_meaning='execution_time_not_inferred'))
            return True
        if endpoint == '/api/'+collection:
            if query:
                raise ValueError('Unknown collection query')
            rows = self.collection(cid)
            h.send_json(rows if collection == 'jobs' else dict(runs=rows))
            return True
        match = re.fullmatch('/api/'+collection+r'/([0-9a-f-]{36})(/download|/export|/progress|/quality)?', endpoint)
        if not match:
            advanced = re.fullmatch('/api/'+collection+r'/([0-9a-f-]{36})/(quality-set|multi-seed-quality|robust-cost-proof)', endpoint)
            if advanced:
                record = self.get_record(cid, advanced[1])
                if isinstance(record, LegacyRecord):
                    self.legacy_diagnostic(record)
                    return False
                h.send_json({'error': 'This advanced diagnostic is not yet connected to shared records', 'diagnostic_status': 'NOT_IMPLEMENTED'}, 409)
                return True
            return False
        try:
            record = self.get_record(cid, match[1])
        except KeyError:
            h.send_json({'error':'Run not found in this contract'},404)
            return True
        action = match[2]
        if action == '/quality':
            if isinstance(record, LegacyRecord):
                try:
                    self.legacy_diagnostic(record)
                except (ValueError, OSError, ImportError) as exc:
                    h.send_json({'error': str(exc), 'diagnostic_status': 'EVALUATOR_UNAVAILABLE'}, 409)
                    return True
                return False
            from .results import diagnostic, quality_summary
            raw_id = int(query['solution'][0]) if 'solution' in query else None
            generation = int(query['generation'][0]) if 'generation' in query else None
            h.send_json(quality_summary(record) if raw_id is None else diagnostic(record, raw_id, generation))
        elif action in ('/download', '/export'):
            if query:
                raise ValueError('Export query unsupported')
            data, name, mime = self.export(record)
            h.send_response(200)
            h.send_header('Content-Type', mime)
            h.send_header('Content-Disposition', 'attachment; filename="'+name+'"')
            h.send_header('Content-Length', str(len(data)))
            h.end_headers()
            h.wfile.write(data)
        else:
            if set(query)-{'generation','view'} or any(len(v) != 1 for v in query.values()) or query.get('view',['full'])[0] not in ('full','summary') or action=='/progress' and 'view' in query:
                raise ValueError('Invalid generation query')
            generation = int(query['generation'][0]) if 'generation' in query else None
            if generation is not None and generation < 0:
                raise ValueError('Invalid generation')
            if action == '/progress':
                if isinstance(record,RunSession):
                    progress=record.progress_snapshot()
                    h.send_json(dict(progress,id=record.id,error=record.error,config=record.config,seconds=progress['elapsed_seconds'],evaluations=progress['nfe'],latest_generation=progress['generation'] if progress['generation'] is not None else -1))
                    return True
                # Stored data is immutable. Progress needs scalars, not a deep
                # copy of every population and historical archive.
                p = record.data if hasattr(record,'data') else record.packet(include_rows=False)
                cp = getattr(record,'checkpoints',p.get('checkpoints',getattr(record,'snapshots',[])))
                h.send_json(dict(id=record.id, state=record.state, config=record.config, error=p.get('error'), seconds=p.get('elapsed_seconds', p.get('seconds')), latest_generation=len(cp)-1, generation=cp[-1]['generation'] if cp else None, evaluations=p.get('nfe', cp[-1].get('evaluations', cp[-1].get('nfe', 0)) if cp else 0), requested_generations=record.config.get('generations')))
            else:
                summary=query.get('view')==['summary'] and not isinstance(record,LegacyRecord)
                h.send_json(self.management.decorate(cid,record.id,record.view(generation,summary=True) if summary else record.view(generation)))
        return True

    def post(self, h, endpoint, query):
        if self.management.post(h,endpoint,query):return True
        from .configuration_http import post
        if post(self,h,endpoint,query):return True
        cid = h.contract
        if endpoint in ('/api/runs','/api/common-runs') and cid not in ('RADAR_EOIR','RADAR_RF_SCANNER'):
            raise ValueError('Use confirmed configuration API: /api/engine/validate then /api/engine/runs')
        collection = 'jobs' if cid == 'RADAR_EOIR' else 'runs'
        create = endpoint in ('/api/jobs',) if cid == 'RADAR_EOIR' else endpoint in ('/api/runs', '/api/common-runs')
        action = re.fullmatch('/api/'+collection+r'/([0-9a-f-]{36})/(cancel|quality)', endpoint)
        if not create and not action:
            return False
        if action and action[2] == 'quality' and isinstance(self.get_record(cid, action[1]), LegacyRecord):
            try:
                self.legacy_diagnostic(self.get_record(cid, action[1]))
            except (ValueError, OSError, ImportError) as exc:
                h.send_json({'error': str(exc), 'diagnostic_status': 'EVALUATOR_UNAVAILABLE'}, 409)
                return True
            return False
        if query:
            raise ValueError('POST query unsupported')
        obj = self.body(h)
        if obj.get('experiment_contract_id', cid) != cid or cid == 'RADAR_RF_SCANNER' and obj.get('experiment_contract_id') != cid:
            raise ValueError('Body experiment identity mismatch')
        if action:
            record = self.get_record(cid, action[1])
            if action[2] == 'cancel':
                expected = {'experiment_contract_id'} if cid == 'RADAR_RF_SCANNER' else set()
                if set(obj) != expected:
                    raise ValueError('Invalid cancel body')
                result = dict(run_id=record.id, state=record.state) if isinstance(record, LegacyRecord) else self.service.cancel(record.id, cid)
                h.send_json(dict(result, cancel_requested=True), 202)
            else:
                if set(obj) != {'experiment_contract_id', 'raw_id'}:
                    raise ValueError('Select one raw row for diagnosis')
                from .results import diagnostic
                h.send_json(diagnostic(record, obj['raw_id']))
            return True
        if self.busy():
            raise ValueError('Program research is active')
        if source_snapshot() != self.loaded_sources:
            raise ValueError('Shared engine source changed; restart server before submitting')
        if cid == 'RADAR_EOIR':
            from live_model import validate
            config = validate(obj)
            optimizer = {}
        elif endpoint == '/api/common-runs':
            from model_service_client import client
            if client().request('/models/'+cid+'/schema')['model'].get('retired_model_versions'):
                raise ValueError('RETIRED_MODEL: use the current model through /api/engine/validate and /api/engine/runs; historical results remain readable')
            from rf_common_contract import make_config as v2, PARAMETERS as p2, VERSION as version2
            from rf_common_v3_contract import make_config as v3, PARAMETERS as p3, VERSION as version3
            from rf_contract import digest
            expected = {'experiment_contract_id', 'common', 'parameters', 'evaluator_version', 'optimizer', 'preview_sha256'}
            is_v3 = obj.get('evaluator_version') == version3
            if set(obj) != expected or obj.get('evaluator_version') not in (version2, version3) or not isinstance(obj['parameters'], dict) or set(obj['parameters']) != set(p3 if is_v3 else p2):
                raise ValueError('Common RF draft fields/version mismatch')
            config = (v3 if is_v3 else v2)(obj['common'], obj['parameters'])
            if obj['preview_sha256'] != digest(config):
                raise ValueError('Apply current RF settings before calculation')
            optimizer = obj['optimizer']
        else:
            from model_service_client import client
            if client().request('/models/'+cid+'/schema')['model'].get('retired_model_versions'):
                raise ValueError('RETIRED_MODEL: use the current model through /api/engine/validate and /api/engine/runs; historical results remain readable')
            from rf_contract import fixture
            if set(obj) != {'experiment_contract_id', 'config', 'optimizer'} or not isinstance(obj['config'], dict) or any(obj['config'].get(k) != fixture()[k] for k in ('sites', 'points')):
                raise ValueError('RF fixture/config fields mismatch')
            config, optimizer = obj['config'], obj['optimizer']
        session = self.service.submit(cid, config, optimizer, request_id=h.headers.get('X-Request-ID'))
        h.send_json(dict(id=session.id, run_id=session.id, state=session.state, config=session.config, problem=session.frozen_problem), 202)
        return True
