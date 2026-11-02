"""Validation composition on the existing authenticated service and store."""
import re
import threading
from .runtime import source_snapshot

_lock=threading.Lock()
def manager(owner):
    with _lock:
        if not hasattr(owner,'validation_service'):
            from .validation_service import ValidationService
            owner.validation_service=ValidationService(owner.service)
            def analyses(record,options):
                from .research_diagnostics import analyze as basic
                from .validation_analysis import analyze as advanced
                out={}
                for key,fn in [('basic',basic),('validation',advanced)]:
                    out[key]=dict(status='NOT_RUN',reason='Not selected')
                    if options.get(key) is not None:
                        try:out[key]=fn(record,options[key])
                        except Exception as exc:out[key]=dict(status='ERROR',reason=str(exc))
                return out
            owner.validation_service.analyze=analyses
        return owner.validation_service

def get(owner,h,endpoint,query):
    if endpoint=='/api/engine/validation-export/import-options':
        from .validation_import import import_roots,MAX_ZIP_BYTES,MAX_EXPANDED_BYTES
        h.send_json(dict(local_roots=[str(p) for p in import_roots()],max_zip_bytes=MAX_ZIP_BYTES,max_expanded_bytes=MAX_EXPANDED_BYTES,requires_explicit_path=True));return True
    if endpoint=='/api/engine/validations':h.send_json(manager(owner).list(h.contract));return True
    m=re.fullmatch(r'/api/engine/validations/([0-9a-f-]{36})(/export)?',endpoint)
    if not m:return False
    service=manager(owner)
    if not m[2]:h.send_json(service.get(h.contract,m[1]));return True
    data=service.export(h.contract,m[1])
    h.send_response(200);h.send_header('Content-Type','application/zip');h.send_header('Content-Disposition','attachment; filename="'+m[1]+'.zip"');h.send_header('Content-Length',str(len(data)));h.end_headers();h.wfile.write(data);return True

def post(owner,h,endpoint,query):
    if endpoint=='/api/engine/validation-export/read':
        import base64
        from .validation_import import read_export_bytes
        body=owner.body(h,limit=32*1024*1024)
        if set(body)!={'base64'}:raise ValueError('VALIDATION_EXPORT_READ_FIELDS')
        data=read_export_bytes(base64.b64decode(body['base64'],validate=True),h.contract)
        h.send_json(data);return True
    if endpoint=='/api/engine/validation-export/read-local':
        from .validation_import import read_local_export
        body=owner.body(h,limit=8192)
        if set(body)!={'path'}:raise ValueError('VALIDATION_LOCAL_PATH_FIELDS')
        h.send_json(read_local_export(body['path'],h.contract));return True
    if endpoint=='/api/engine/reference':
        from .validation_analysis import empirical_reference
        body=owner.body(h)
        if set(body)!={'run_ids'} or not isinstance(body['run_ids'],list) or not 1<=len(body['run_ids'])<=16 or len(set(body['run_ids']))!=len(body['run_ids']):raise ValueError('REFERENCE_SELECT_1_TO_16_RUNS')
        h.send_json(dict(reference=empirical_reference([owner.get_record(h.contract,i) for i in body['run_ids']])));return True
    m=re.fullmatch(r'/api/engine/validations(?:/(preview)|/([0-9a-f-]{36})/(cancel|retry))?',endpoint)
    advanced=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/validation-diagnostics',endpoint)
    if not m and not advanced:return False
    body=owner.body(h,limit=2*1024*1024)
    if advanced:
        from .validation_analysis import analyze
        h.send_json(analyze(owner.get_record(h.contract,advanced[1]),body));return True
    service=manager(owner)
    if m[1]:h.send_json(service.preview(h.contract,body));return True
    if m[3]=='cancel':
        if body:raise ValueError('VALIDATION_CANCEL_FIELDS')
        h.send_json(service.cancel(h.contract,m[2]));return True
    if not m[3] and h.headers.get('X-Request-ID'):
        try:existing=service.lookup_request(h.contract,h.headers.get('X-Request-ID'))
        except KeyError:existing=None
        if existing:
            h.send_json(service.submit(h.contract,body,h.headers.get('X-Request-ID'),h.headers.get('X-Execution-SHA256')));return True
    import live_server
    if live_server.MAINTENANCE or owner.busy():raise ValueError('Program maintenance or research active')
    if source_snapshot()!=owner.loaded_sources:raise ValueError('Shared source changed; restart server before submitting')
    if m[3]=='retry':
        if set(body)!={'cell_ids'}:raise ValueError('VALIDATION_RETRY_FIELDS')
        h.send_json(service.retry(h.contract,m[2],body['cell_ids']),202);return True
    h.send_json(service.submit(h.contract,body,h.headers.get('X-Request-ID'),h.headers.get('X-Execution-SHA256')),202);return True
