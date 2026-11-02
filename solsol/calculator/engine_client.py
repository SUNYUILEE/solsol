"""Client of the existing local program. No evaluator or optimizer runs here.

All numerical requests go through the same server routes used by the UI.
An uncertain POST is never automatically retried.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import time
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


CONTRACTS = {'ABC_COVERAGE_RESOURCE_V1': {'collection':'runs','create':'engine/runs','preview':'engine/validate','export':'export','page':'live.html','format':'json'}}

TERMINAL = {'completed', 'cancelled', 'failed', 'time_limit', 'interrupted'}


class EngineError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EngineError('Unexpected redirect; request was not forwarded')


class EngineClient:
    def __init__(self, contract_id: str, base_url: str = 'http://127.0.0.1:8877', timeout: float = 30):
        if not isinstance(contract_id,str) or not contract_id or not all(c.isalnum() or c in '_-' for c in contract_id):
            raise EngineError('Explicit model contract ID required')
        if contract_id not in CONTRACTS:
            CONTRACTS[contract_id]={'collection':'runs','create':'engine/runs','preview':'engine/validate','export':'export','page':'live.html','format':'json'}
        url = urlsplit(base_url)
        try:
            port = url.port
        except ValueError:
            raise EngineError('Invalid local program port') from None
        if port is not None and not 1 <= port <= 65535:
            raise EngineError('Invalid local program port')
        if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
            raise EngineError('Use the existing loopback program URL')
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise EngineError('HTTP timeout must be in (0, 60] seconds')
        self.base_url = base_url.rstrip('/')
        self.contract_id = contract_id
        self.routes = CONTRACTS[contract_id]
        self.timeout = timeout
        self._token = None
        self._opener = build_opener(NoRedirect())

    @staticmethod
    def _id(run_id):
        try:
            if str(uuid.UUID(run_id)) != run_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise EngineError('Canonical run UUID required') from None
        return run_id

    def _request(self, endpoint, body=None, binary=False, timeout=None, extra_headers=None):
        headers = {'X-Experiment-Contract': self.contract_id}
        if body is not None:
            if self._token is None:
                self.config()
            headers.update({'Origin': self.base_url, 'X-Run-Token': self._token, 'Content-Type': 'application/json'})
        headers.update(extra_headers or {})
        request = Request(f'{self.base_url}/contracts/{self.contract_id}/api/{endpoint}',
                          data=None if body is None else json.dumps(body, allow_nan=False).encode(), headers=headers)
        try:
            with self._opener.open(request, timeout=self.timeout if timeout is None else min(self.timeout, timeout)) as response:
                if response.headers.get('X-Experiment-Contract') != self.contract_id:
                    raise EngineError('Response contract mismatch')
                raw = response.read()
        except HTTPError as exc:
            raise EngineError(f'Program HTTP {exc.code}: {exc.read().decode("utf-8", errors="replace")[:1000]}') from None
        except (URLError, TimeoutError, OSError) as exc:
            suffix = '; submission outcome may be unknown: inspect run history before retrying' if body is not None else ''
            raise EngineError(f'Program connection failed: {exc}{suffix}') from None
        if binary:
            return raw
        packet = json.loads(raw)
        if isinstance(packet, dict) and packet.get('experiment_contract_id') != self.contract_id:
            raise EngineError('JSON contract mismatch')
        if not isinstance(packet, dict) and not (isinstance(packet, list) and endpoint == 'jobs' and self.contract_id == 'RADAR_EOIR'):
            raise EngineError('Invalid program response')
        return packet

    def config(self):
        packet = self._request('config')
        self._token = packet.get('token')
        if not isinstance(self._token, str) or not self._token:
            raise EngineError('Program connection token unavailable')
        return {key: value for key, value in packet.items() if key != 'token'}

    def list_runs(self):
        return self._request(self.routes['collection'])

    def registry(self):
        return self._request('engine/registry')

    def quick_preset(self,payload,size='small'):
        return self._request('engine/quick-preset',dict(request=payload,size=size))

    def preview_validation(self,plan):return self._request('engine/validations/preview',plan)
    def empirical_reference(self,run_ids):return self._request('engine/reference',dict(run_ids=[self._id(i) for i in run_ids]))
    def submit_validation(self,plan,request_id,plan_sha256):
        return self._request('engine/validations',plan,extra_headers={'X-Request-ID':request_id,'X-Execution-SHA256':plan_sha256})
    def validations(self):return self._request('engine/validations')
    def validation(self,validation_id):return self._request('engine/validations/'+self._id(validation_id))
    def cancel_validation(self,validation_id):return self._request('engine/validations/'+self._id(validation_id)+'/cancel',{})
    def retry_validation(self,validation_id,cell_ids):return self._request('engine/validations/'+self._id(validation_id)+'/retry',dict(cell_ids=cell_ids))
    def validation_diagnostics(self,run_id,options):return self._request('engine/runs/'+self._id(run_id)+'/validation-diagnostics',options)
    def export_validation(self,validation_id,path):
        raw=self._request('engine/validations/'+self._id(validation_id)+'/export',binary=True)
        target=Path(path)
        if target.exists():raise EngineError('Validation export path already exists')
        self.read_validation_export(raw)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        return dict(validation_id=validation_id,path=str(target),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),calculation_performed_by_client=False)

    @staticmethod
    def read_validation_export(source):
        """Reopen and verify a portable export in memory; no extraction or compute."""
        raw=source if isinstance(source,bytes) else Path(source).read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist()
            if len(names)!=len(set(names)):raise EngineError('Duplicate validation ZIP members')
            manifest=json.loads(z.read('export_manifest.json'))
            if manifest.get('schema')!='SOLSOL_VALIDATION_EXPORT_V1':raise EngineError('Unsupported validation export schema')
            if set(names)!=set(manifest['files'])|{'export_manifest.json'}:raise EngineError('Validation export member mismatch')
            for name,entry in manifest['files'].items():
                value=z.read(name)
                if len(value)!=entry['bytes'] or hashlib.sha256(value).hexdigest()!=entry['sha256']:raise EngineError('Validation export integrity error: '+name)
            plan=json.loads(z.read('plan.json'));summary=json.loads(z.read('summary.json'))
            if plan['plan_sha256']!=manifest['plan_sha256'] or summary['validation_id']!=manifest['validation_id']:raise EngineError('Validation export identity mismatch')
            return dict(manifest=manifest,plan=plan,summary=summary,calculation_performed_by_client=False)

    def read_local_validation_export(self,path):
        """Explicit loopback Desktop/Downloads ZIP selection; server validates."""
        return self._request('engine/validation-export/read-local',dict(path=str(path)))

    def diagnose(self,run_id,options=None):
        return self._request('engine/runs/'+self._id(run_id)+'/diagnostics',options or {},timeout=180)

    def diagnostics(self,run_id):
        return self._request('engine/runs/'+self._id(run_id)+'/diagnostics')

    def diagnostic(self,run_id,diagnostic_id):
        return self._request('engine/runs/'+self._id(run_id)+'/diagnostics/'+self._id(diagnostic_id))

    def export_diagnostic(self,run_id,diagnostic_id,path):
        raw=self._request('engine/runs/'+self._id(run_id)+'/diagnostics/'+self._id(diagnostic_id)+'/export',binary=True)
        saved=self.diagnostic(run_id,diagnostic_id)
        if hashlib.sha256(raw).hexdigest()!=saved['file_sha256'] or json.loads(raw)!=saved['sidecar']:raise EngineError('Diagnostic export mismatch')
        target=Path(path)
        if target.exists():raise EngineError('Diagnostic export path already exists')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        return dict(run_id=run_id,diagnostic_id=diagnostic_id,path=str(target),sha256=saved['file_sha256'],bytes=len(raw),calculation_performed_by_client=False)

    def validate_configuration(self,payload):
        self._body_identity(payload)
        return self._request('engine/validate',payload)

    def submit_configuration(self,payload,request_id=None,execution_sha256=None):
        self._body_identity(payload)
        request_id=request_id or str(uuid.uuid4());self.last_request_id=request_id
        if execution_sha256 is None:
            try:old=self.request_status(request_id)
            except EngineError as exc:
                if 'HTTP 404' not in str(exc):raise
                old=None
            if old:
                snapshot=old.get('execution_snapshot') or {}
                if snapshot.get('submitted_request')!={k:v for k,v in payload.items() if k!='schema'}:raise EngineError('REQUEST_CONFLICT: existing request has different submitted values')
                execution_sha256=snapshot['execution_sha256']
            else:execution_sha256=self.validate_configuration(payload)['execution_sha256']
        try:packet=self._request('engine/runs',payload,extra_headers={'X-Request-ID':request_id,'X-Execution-SHA256':execution_sha256})
        except EngineError as exc:raise EngineError(str(exc)+'; request_id='+request_id+'; recover with request_status using this same ID') from None
        return dict(packet,ui_url=self.ui_url(packet['run_id']))

    def request_status(self,request_id):
        import re
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',request_id):raise EngineError('Invalid request ID')
        return self._request('engine/requests/'+request_id)

    def quality_overview(self,run_id):return self._request('engine/runs/'+self._id(run_id)+'/quality-workflow')
    def quality_research(self,run_id,run_ids):return self._request('engine/runs/'+self._id(run_id)+'/quality-research',dict(run_ids=[self._id(i) for i in run_ids]),timeout=180)
    def quality_research_status(self,run_id,comparison_id):return self._request('engine/runs/'+self._id(run_id)+'/quality-research/'+self._id(comparison_id))
    def quality_jobs(self,run_id):return self._request('engine/runs/'+self._id(run_id)+'/quality-jobs')
    def quality_start(self,run_id,options):return self._request('engine/runs/'+self._id(run_id)+'/quality-jobs',options)
    def quality_status(self,run_id,job_id):return self._request('engine/runs/'+self._id(run_id)+'/quality-jobs/'+self._id(job_id))
    def quality_cancel(self,run_id,job_id):return self._request('engine/runs/'+self._id(run_id)+'/quality-jobs/'+self._id(job_id)+'/cancel',{})
    def quality_resume(self,run_id,job_id):return self._request('engine/runs/'+self._id(run_id)+'/quality-jobs/'+self._id(job_id)+'/resume',{})
    def quality_check(self,run_id,options):return self._request('engine/runs/'+self._id(run_id)+'/quality-workflow',options)
    def quality_check_result(self,run_id,check_id):return self._request('engine/runs/'+self._id(run_id)+'/quality-workflow/'+self._id(check_id))
    def result_contract(self,run_id):return self._request('engine/runs/'+self._id(run_id)+'/contract')
    def copy_configuration(self,run_id):return self._request('engine/runs/'+self._id(run_id)+'/copy')
    def configuration_diff(self,run_id,payload):return self._request('engine/diff',dict(parent_run_id=self._id(run_id),request=payload))
    def compare_runs(self,left_id,right_id,right_contract=None):
        return self._request('engine/compare',dict(left=dict(experiment_contract_id=self.contract_id,run_id=self._id(left_id)),right=dict(experiment_contract_id=right_contract or self.contract_id,run_id=self._id(right_id))))

    def preview(self, payload):
        """Accept the exact existing UI request, without changing model values."""
        self._body_identity(payload)
        return self._request(self.routes['preview'], payload)

    def _body_identity(self, payload):
        if not isinstance(payload, dict):
            raise EngineError('Request must be a JSON object')
        if 'experiment_contract_id' in payload and payload['experiment_contract_id'] != self.contract_id:
            raise EngineError('Request contract mismatch')
        if self.contract_id == 'RADAR_RF_SCANNER' and payload.get('experiment_contract_id') != self.contract_id:
            raise EngineError('Explicit RF request contract required')

    def submit(self, payload):
        """Exactly one POST. Validation, budgets and concurrency stay in the server."""
        self._body_identity(payload)
        packet = self.submit_configuration(payload)
        run_id = self._id(packet.get('run_id', packet.get('id')))
        return {'experiment_contract_id': self.contract_id, 'run_id': run_id,
                'ui_url': self.ui_url(run_id), 'server_response': packet}

    def ui_url(self, run_id):
        return f'{self.base_url}/{self.routes["page"]}?{urlencode({"run": self._id(run_id),"contract":self.contract_id})}'

    def status(self, run_id, generation=None, *, _timeout=None):
        endpoint = self.routes['collection'] + '/' + self._id(run_id)
        if generation is not None:
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
                raise EngineError('Generation must be a nonnegative integer')
            endpoint += '?' + urlencode({'generation': generation})
        packet = self._request(endpoint, timeout=_timeout)
        if packet.get('run_id', packet.get('id')) != run_id:
            raise EngineError('Response run identity mismatch')
        return packet

    def wait(self, run_id, seconds=30):
        if not math.isfinite(seconds) or not 0 <= seconds <= 60:
            raise EngineError('Wait bound must be 0–60 seconds; poll again explicitly')
        deadline = time.monotonic() + seconds
        if seconds == 0:
            return self.status(run_id)  # One snapshot, subject to the configured HTTP timeout.
        packet = None
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                if packet is None:
                    raise EngineError('Wait deadline elapsed before the first response')
                return packet
            packet = self.status(run_id, _timeout=remaining)
            if packet['state'] in TERMINAL or time.monotonic() >= deadline:
                return packet
            time.sleep(min(1, max(0, deadline-time.monotonic())))

    def cancel(self, run_id):
        body = {'experiment_contract_id': self.contract_id} if self.contract_id == 'RADAR_RF_SCANNER' else {}
        return self._request(self.routes['collection'] + '/' + self._id(run_id) + '/cancel', body)

    def export(self, run_id, directory):
        status = self.status(run_id)
        if status['state'] not in TERMINAL:
            raise EngineError('Run is not saved; no export requested')
        endpoint = self.routes['collection'] + '/' + self._id(run_id) + '/' + self.routes['export']
        raw = self._request(endpoint, binary=True)
        self._validate_export(raw, status, run_id)
        # Preserve the server artifact byte-for-byte. Never extract or re-evaluate it.
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=False)
        artifact = target / ('server_export.' + ('json' if status['config'].get('_research') else self.routes['format']))
        artifact.write_bytes(raw)
        receipt = {'schema': 'SOLSOL_ENGINE_EXPORT_RECEIPT_V1', 'experiment_contract_id': self.contract_id,
                   'run_id': run_id, 'ui_url': self.ui_url(run_id), 'state': status['state'],
                   'source_endpoint': self.base_url + '/contracts/' + self.contract_id + '/api/' + endpoint,
                   'artifact': {'path': artifact.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()},
                   'calculation_performed_by_client': False}
        (target / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        return receipt

    def _validate_export(self, raw, status, run_id):
        """Check identity inside the original artifact; never extract ZIP paths."""
        try:
            if self.routes['format'] == 'json' or status['config'].get('_research'):
                packet = json.loads(raw)
                for key in ('experiment_contract_id', 'run_id', 'config', 'config_sha256', 'evaluator_sha256', 'state'):
                    if key=='state' and status['state']=='interrupted' and packet.get('state') in ('queued','preparing','running','verifying','saving') and not packet.get('storage_complete'):continue
                    if key not in packet or packet[key] != status[key]:
                        raise EngineError('Export identity/config mismatch: ' + key)
                return
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise EngineError('Duplicate export ZIP members')
                manifest = json.loads(archive.read('manifest.json'))
                result = json.loads(archive.read('result.json'))
                config = json.loads(archive.read('config.json'))
                if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict) or not isinstance(result, dict):
                    raise EngineError('Invalid export manifest/result shape')
                if manifest['id'] != run_id or result['id'] != run_id or config != status['config']:
                    raise EngineError('Export run/config mismatch')
                if manifest['state'] != status['state'] or result['state'] != status['state']:
                    raise EngineError('Export state mismatch')
                for name, digest in manifest['files'].items():
                    if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                        raise EngineError('Export member checksum mismatch: ' + name)
                if manifest.get('publication_contract') is not None:
                    marker = json.loads(archive.read('completion.json'))
                    if marker['run_id'] != run_id or marker['schema'] != manifest['publication_contract']:
                        raise EngineError('Export completion identity mismatch')
                    for name in ('result', 'manifest'):
                        if marker[name + '_sha256'] != hashlib.sha256(archive.read(name + '.json')).hexdigest():
                            raise EngineError('Export completion checksum mismatch')
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            raise EngineError('Invalid program export: ' + str(exc)) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8877')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('config', 'list', 'registry'):
        sub.add_parser(command)
    for command in ('preview', 'submit', 'validate-configuration', 'submit-configuration'):
        child=sub.add_parser(command);child.add_argument('--request', required=True, type=Path)
        if command=='submit-configuration':
            child.add_argument('--request-id');child.add_argument('--execution-sha256')
    sub.add_parser('request-status').add_argument('--request-id',required=True)
    sub.add_parser('validations')
    for command in ('preview-validation','submit-validation'):
        child=sub.add_parser(command);child.add_argument('--plan',type=Path,required=True)
        if command=='submit-validation':child.add_argument('--request-id',required=True);child.add_argument('--plan-sha256',required=True)
    for command in ('validation','cancel-validation','retry-validation','export-validation'):
        child=sub.add_parser(command);child.add_argument('--validation-id',required=True)
        if command=='retry-validation':child.add_argument('--cell-ids',nargs='+',required=True)
        if command=='export-validation':child.add_argument('--output',type=Path,required=True)
    child=sub.add_parser('validation-diagnostics');child.add_argument('--run',required=True);child.add_argument('--options',type=Path,required=True)
    child=sub.add_parser('quick-preset');child.add_argument('--request',type=Path,required=True);child.add_argument('--size',choices=['small','medium'],default='small')
    child=sub.add_parser('diagnose');child.add_argument('--run',required=True);child.add_argument('--options',type=Path)
    child=sub.add_parser('diagnostics');child.add_argument('--run',required=True)
    for command in ('diagnostic','export-diagnostic'):
        child=sub.add_parser(command);child.add_argument('--run',required=True);child.add_argument('--diagnostic-id',required=True)
        if command=='export-diagnostic':child.add_argument('--output',type=Path,required=True)
    child=sub.add_parser('compare');child.add_argument('--left',required=True);child.add_argument('--right',required=True);child.add_argument('--right-contract')
    child=sub.add_parser('diff');child.add_argument('--run',required=True);child.add_argument('--request',type=Path,required=True)
    for command in ('status', 'wait', 'cancel', 'export', 'ui-url','result-contract','copy-configuration'):
        child = sub.add_parser(command)
        child.add_argument('--run', required=True)
        if command == 'status': child.add_argument('--generation', type=int)
        if command == 'wait': child.add_argument('--seconds', type=float, default=30)
        if command == 'export': child.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        client = EngineClient(args.contract, args.url)
        if args.command == 'config': result = client.config()
        elif args.command == 'list': result = client.list_runs()
        elif args.command == 'registry': result = client.registry()
        elif args.command == 'validations':result=client.validations()
        elif args.command == 'preview-validation':result=client.preview_validation(json.loads(args.plan.read_text(encoding='utf-8-sig')))
        elif args.command == 'submit-validation':result=client.submit_validation(json.loads(args.plan.read_text(encoding='utf-8-sig')),args.request_id,args.plan_sha256)
        elif args.command == 'validation':result=client.validation(args.validation_id)
        elif args.command == 'cancel-validation':result=client.cancel_validation(args.validation_id)
        elif args.command == 'retry-validation':result=client.retry_validation(args.validation_id,args.cell_ids)
        elif args.command == 'export-validation':result=client.export_validation(args.validation_id,args.output)
        elif args.command == 'validation-diagnostics':result=client.validation_diagnostics(args.run,json.loads(args.options.read_text(encoding='utf-8-sig')))
        elif args.command == 'quick-preset':result=client.quick_preset(json.loads(args.request.read_text(encoding='utf-8-sig')),args.size)
        elif args.command == 'diagnose':result=client.diagnose(args.run,json.loads(args.options.read_text(encoding='utf-8-sig')) if args.options else {})
        elif args.command == 'diagnostics':result=client.diagnostics(args.run)
        elif args.command == 'diagnostic':result=client.diagnostic(args.run,args.diagnostic_id)
        elif args.command == 'export-diagnostic':result=client.export_diagnostic(args.run,args.diagnostic_id,args.output)
        elif args.command == 'request-status':result=client.request_status(args.request_id)
        elif args.command == 'compare':result=client.compare_runs(args.left,args.right,args.right_contract)
        elif args.command == 'diff':result=client.configuration_diff(args.run,json.loads(args.request.read_text(encoding='utf-8-sig')))
        elif args.command == 'result-contract':result=client.result_contract(args.run)
        elif args.command == 'copy-configuration':result=client.copy_configuration(args.run)
        elif args.command == 'submit-configuration':result=client.submit_configuration(json.loads(args.request.read_text(encoding='utf-8-sig')),args.request_id,args.execution_sha256)
        elif args.command in ('preview', 'submit','validate-configuration','submit-configuration'):
            result = getattr(client, args.command.replace('-','_'))(json.loads(args.request.read_text(encoding='utf-8-sig')))
        elif args.command == 'status': result = client.status(args.run, args.generation)
        elif args.command == 'wait': result = client.wait(args.run, args.seconds)
        elif args.command == 'cancel': result = client.cancel(args.run)
        elif args.command == 'export': result = client.export(args.run, args.output)
        else: result = {'ui_url': client.ui_url(args.run)}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (EngineError, ValueError, OSError) as exc:
        print(json.dumps({'status': 'ERROR', 'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
