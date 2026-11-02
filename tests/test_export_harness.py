import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location('export_harness',Path(__file__).resolve().parents[1]/'tools/calculator_export.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


def fixture(tmp_path):
    target=tmp_path/'target';target.mkdir()
    p=target/'quality_jobs.py';p.write_text('def resume():\n    return True\n',encoding='utf-8')
    proof=target/'proof.json'
    inventory=dict(files=[dict(path='engine/quality_jobs.py',symbols=[dict(name='resume')])])
    domains=['full_ui_workflows','public_api_client','run_storage_restore','all_initializers_solvers',
             'quality_jobs_resume_export','set_search_quality','comparison_resource_studies','evidence_provenance',
             'neutral_model_switch','source_preservation','independent_scope_review']
    proof.write_text(json.dumps(dict(status='PASS',checks=['owned runtime witness'],domains=domains)),encoding='utf8')
    mapping=dict(files=[dict(source='engine/quality_jobs.py',target='quality_jobs.py',status='PRESERVED',target_sha256=h.sha(p),runtime_status='PASS',evidence=[dict(path='proof.json',sha256=h.sha(proof),status='PASS')])],
        acceptance_evidence={d:dict(path='proof.json',sha256=h.sha(proof),status='PASS') for d in domains})
    return target,inventory,mapping


def test_missing_preserved_quality_module_blocks_publication(tmp_path):
    target,inventory,mapping=fixture(tmp_path)
    assert h.check(inventory,target,mapping)['status']=='PASS'
    (target/'quality_jobs.py').unlink()
    result=h.check(inventory,target,mapping)
    assert result['status']=='FAIL' and not result['complete_claim_allowed'] and result['missing']


def test_hash_changes_missing_symbols_and_missing_runtime_proof_block(tmp_path):
    target,inventory,mapping=fixture(tmp_path)
    (target/'quality_jobs.py').write_text('def renamed():\n    return True\n')
    result=h.check(inventory,target,mapping)
    assert result['changed'] and result['missing']
    mapping['acceptance_evidence']['public_api_client']['status']='NOT_RUN'
    assert 'public_api_client' in h.check(inventory,target,mapping)['unverified']


def test_forged_or_stale_evidence_status_does_not_close_scope(tmp_path):
    target,inventory,mapping=fixture(tmp_path)
    (target/'proof.json').write_text(json.dumps(dict(status='FAIL',checks=['actual failure'])))
    assert h.check(inventory,target,mapping)['status']=='FAIL'


def test_model_exclusion_cannot_silently_remove_calculator_functionality(tmp_path):
    target,inventory,mapping=fixture(tmp_path)
    mapping['files'][0]=dict(source='engine/quality_jobs.py',status='EXCLUDED_MODEL',reason='Old sensor coupling',calculator_capabilities_removed=False)
    assert h.check(inventory,target,mapping)['status']=='FAIL'


def test_missing_control_and_fictitious_replacement_block(tmp_path):
    target,inventory,mapping=fixture(tmp_path)
    p=target/'workspace.html';p.write_text('<button id="calculate"></button>')
    item=dict(path='app/integrated/web/workspace.html',symbols=[dict(name='calculate')]);inventory['files'].append(item)
    entry=dict(source=item['path'],target='workspace.html',status='PRESERVED',target_sha256=h.sha(p),runtime_status='PASS',evidence=mapping['files'][0]['evidence']);mapping['files'].append(entry)
    p.write_text('<p>removed</p>');entry['target_sha256']=h.sha(p)
    entry['symbol_replacements']={'calculate':{'target':'imaginary','reason':'neutral adapter'}}
    assert h.check(inventory,target,mapping)['status']=='FAIL'


def test_api_proof_requires_domain_and_live_file(tmp_path):
    target,inventory,mapping=fixture(tmp_path)
    p=target/'proof.json';p.write_text(json.dumps(dict(status='PASS',checks=['smoke only'],domains=['full_ui_workflows'])))
    for e in mapping['acceptance_evidence'].values():e['sha256']=h.sha(p)
    result=h.check(inventory,target,mapping)
    assert 'public_api_client' in result['unverified']
    p.unlink();assert h.check(inventory,target,mapping)['status']=='FAIL'
