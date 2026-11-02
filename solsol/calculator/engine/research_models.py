"""Draft Model contracts and inspection artifacts, never optimizer rows."""
import copy
import json
import re
import uuid
from datetime import datetime, timezone
from model_service_client import client
from .contracts import digest
from .store import atomic_json

MODEL = 'HMSP-V1'
VERSION = 'hmsp-baseline-draft-1'
OBJECTIVES = ['physical_observability', 'rf_quality', 'visual_quality', 'cost']
SENSORS = ['radar', 'rf_scanner', 'eoir']


def check(ok, reason):
    if not ok: raise ValueError('HMSP_' + reason)


def checksum(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def contract():
    api = client()
    health = api.request('/health')
    p = api.request('/research/models/' + MODEL + '/contract')
    check(all(p.get(k) == health.get(k) and checksum(p.get(k)) for k in ('service_release_sha256', 'source_sha256')), 'CONTRACT_RELEASE')
    check(p.get('model_id') == MODEL and p.get('version') == VERSION and p.get('execution_ready') is False, 'UNSUPPORTED_CONTRACT')
    b = p['baseline']
    check(b.get('model_id') == MODEL and b.get('version') == VERSION and b.get('execution_ready') is False, 'BASELINE')
    check(b.get('objective_order') == OBJECTIVES and b.get('objective_direction') == ['maximize'] * 3 + ['minimize'], 'OBJECTIVE_ORDER')
    check(b.get('objective_version') == 'HMSP-OBJECTIVES-DRAFT-1' and b['environment_contract']['environment_version'] == 'ENV-2D-V1', 'SEMANTIC_VERSION')
    check(checksum(p.get('contract_sha256')), 'CONTRACT_HASH')
    for doc in [b] + p['successors']:
        check(doc.get('model_hash') == digest({k:v for k,v in doc.items() if k != 'model_hash'}), 'DOCUMENT_HASH')
    return p


def verify_inspection(c, request, response):
    check(isinstance(response,dict) and response.get('api_version')=='SOLSOL_MODEL_API_V1' and
        response.get('status')=='DRAFT_COMPONENT_INSPECTION' and response.get('execution_ready') is False, 'RESPONSE_STATUS')
    check(all(isinstance(response.get(k),dict) for k in
        ('modeled_measurement','derived_information','aggregate','diagnostics','cost')), 'RESPONSE_BLOCKS')
    expected = dict(model_id=MODEL, version=VERSION, environment_version='ENV-2D-V1',
        objective_version='HMSP-OBJECTIVES-DRAFT-1', execution_ready=False,
        contract_sha256=c['contract_sha256'], input_sha256=digest(request),
        rf_config_sha256=digest(request['rf_config']), service_release_sha256=c['service_release_sha256'], source_sha256=c['source_sha256'])
    check(all(response.get(k) == v for k,v in expected.items()), 'INSPECTION_BINDING')
    check(not any(k in response for k in ('F','G','results')) and response.get('constraint_status') == 'FULL_HMSP_G_NOT_CONFIGURED', 'DRAFT_NOT_OPTIMIZER')
    check(response.get('X') == request['X'] and response.get('sensor_order') == SENSORS and
        response.get('candidate_order') == [str(i) for i in range(len(request['X']))], 'PLACEMENT_BINDING')
    check(checksum(response.get('rf_evaluator_sha256')), 'EVALUATOR_IDENTITY')
    check(response.get('inspection_sha256') == digest({k:v for k,v in response.items() if k not in
        ('inspection_sha256', 'api_version', 'source_sha256', 'service_release_sha256')}), 'INSPECTION_HASH')
    values = response['primary_candidates']
    check(isinstance(values,list) and len(values)==4 and all(isinstance(v,dict) and set(v)>={'id','value','status'} and
        (v['value'] is None or type(v['value']) in (int,float)) and v['status'] in ('not_configured','defined_inherited_component','defined_explicit_ledger') for v in values), 'PRIMARY_SCHEMA')
    check([v['id'] for v in values] == OBJECTIVES, 'PRIMARY_ORDER')
    check(all(values[i]['value'] is None and values[i]['status'] == 'not_configured' for i in (0,2)), 'UNRESOLVED_OBJECTIVES')
    if request['cost_ledger'] is None:
        check(values[3]['value'] is None and values[3]['status'] == 'not_configured', 'UNCONFIGURED_COST')
    else:check(type(values[3]['value']) in (int,float) and values[3]['status']=='defined_explicit_ledger', 'CONFIGURED_COST')
    check(type(values[1]['value']) in (int,float) and values[1]['status']=='defined_inherited_component','RF_COMPONENT')
    # Serializing with allow_nan=False rejects nonfinite values anywhere.
    digest(response)


def folder(owner):
    return owner.service.store.root / '_research_inspections' / MODEL


def load(owner, ident):
    check(bool(re.fullmatch('[0-9a-f-]{36}', ident)), 'INSPECTION_ID')
    p = json.loads((folder(owner) / (ident + '.json')).read_text(encoding='utf-8'))
    check(p.get('artifact_sha256') == digest({k:v for k,v in p.items() if k != 'artifact_sha256'}), 'STORED_CHECKSUM')
    check(p.get('inspection_id') == ident and p.get('model_id') == MODEL, 'STORED_ID')
    return p


def inspect(owner, body):
    check(isinstance(body, dict) and set(body) == {'expected_service_release_sha256', 'request'}, 'REQUEST_ENVELOPE')
    c = contract(); req = body['request']
    check(body['expected_service_release_sha256'] == c['service_release_sha256'], 'STALE_SERVICE_RELEASE')
    check(isinstance(req, dict) and set(req) == {'model_id','version','expected_contract_sha256','rf_config','X','cost_ledger'}, 'REQUEST_FIELDS')
    check(req['model_id'] == MODEL and req['version'] == VERSION and req['expected_contract_sha256'] == c['contract_sha256'], 'STALE_CONTRACT')
    ident = str(uuid.uuid4())
    p = dict(schema='SOLSOL_RESEARCH_INSPECTION_V1', inspection_id=ident, model_id=MODEL,
        calculator_source_sha256=digest(owner.loaded_sources),calculator_source_hashes=copy.deepcopy(owner.loaded_sources),
        created_at=datetime.now(timezone.utc).isoformat(), status='REQUESTED', contract=copy.deepcopy(c),
        request=copy.deepcopy(req), optimizer_nfe=0, requested_inspections=1, confirmed_inspections=None,
        scientific_approval='NOT_REVIEWED', execution_ready=False)
    def save():
        p['artifact_sha256'] = digest({k:v for k,v in p.items() if k != 'artifact_sha256'})
        atomic_json(folder(owner) / (ident + '.json'), p)
    save()
    try:
        result = client().request('/research/models/' + MODEL + '/inspect', req)
        verify_inspection(c, req, result)
        p.update(status='INSPECTED', confirmed_inspections=1, response=result)
    except Exception as exc:
        p.update(status='FAILED', error=str(exc), completion_status='UNCONFIRMED_OR_REJECTED')
        save()
        raise ValueError('HMSP_INSPECTION_FAILED:' + ident + ': ' + str(exc)) from exc
    save()
    return p


def get(owner, h, endpoint, query):
    base='/api/engine/research-models/' + MODEL
    if endpoint == base:
        h.send_json(dict(contract=contract(), calculator_support=dict(inspection=True, optimization=False)));return True
    if endpoint == base + '/inspections':
        rows=[load(owner,p.stem) for p in sorted(folder(owner).glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[:50]]
        h.send_json(dict(inspections=[{k:v for k,v in p.items() if k in ('inspection_id','created_at','status','artifact_sha256','error')} for p in rows]));return True
    m=re.fullmatch(re.escape(base) + r'/inspections/([0-9a-f-]{36})',endpoint)
    if m:h.send_json(dict(artifact=load(owner,m[1])));return True
    return False


def post(owner,h,endpoint,query):
    if endpoint in ('/api/engine/research-models/' + MODEL + '/prepare','/api/engine/research-models/' + MODEL + '/inspect'):
        from .runtime import source_snapshot
        check(source_snapshot()==owner.loaded_sources,'CALCULATOR_SOURCE_CHANGED: restart required')
    if endpoint == '/api/engine/research-models/' + MODEL + '/prepare':
        body=owner.body(h,limit=2*1024*1024)
        check(isinstance(body,dict) and set(body)=={'model_config'},'PREPARE_FIELDS')
        c=contract()
        config=client().request('/configuration',dict(experiment_contract_id='RADAR_RF_SCANNER',config=body['model_config']))['config']
        from model_service_client import compile_remote
        cp=compile_remote('RADAR_RF_SCANNER',config)
        native=copy.deepcopy(cp.config);native.pop('_research',None)
        h.send_json(dict(contract=c,request=dict(model_id=MODEL,version=VERSION,expected_contract_sha256=c['contract_sha256'],
            rf_config=native,X=[[0,0,0] for _ in cp.candidate_order],cost_ledger=None)));return True
    if endpoint != '/api/engine/research-models/' + MODEL + '/inspect':return False
    if query:raise ValueError('HMSP_QUERY_NOT_SUPPORTED')
    import live_server
    if live_server.MAINTENANCE or owner.busy():raise ValueError('PROGRAM_BUSY_OR_MAINTENANCE')
    h.send_json(dict(artifact=inspect(owner,owner.body(h,limit=2*1024*1024))));return True
