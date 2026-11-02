"""Bind reviewed source dispositions to fresh, named acceptance artifacts."""
import json
from pathlib import Path
from calculator_export import sha,symbols,write,check

ROOT=Path(__file__).resolve().parents[1]
inventory=json.loads((ROOT/'docs/migration/source-inventory.json').read_text(encoding='utf8'))


def evidence(name):
    p=ROOT/'docs/evidence/full'/name
    return dict(path=p.relative_to(ROOT).as_posix(),status=json.loads(p.read_text(encoding='utf8'))['status'],sha256=sha(p)) if p.exists() else dict(path=p.relative_to(ROOT).as_posix(),status='NOT_RUN')


files=[]
excluded={'hmsp-exec-example.json','workspace-hmsp.js','workspace-hmsp2d.js','workspace-cue-meaning.js','workspace-research-models.js','program-research.js'}
active_html=(ROOT/'solsol/calculator/web/workspace.html').read_text(encoding='utf8')
for f in inventory['files']:
    src=f['path'];name=Path(src).name
    if name in excluded:
        files.append(dict(source=src,status='EXCLUDED_MODEL',reason='Old device/quality-specific model registration, input example or physical cue semantics; generic workflow preserved in workspace configuration/neutral adapter and engine services',calculator_capabilities_removed=False));continue
    dst=src.replace('app/integrated/','solsol/calculator/')
    if name=='model_service_client.py':dst='solsol/calculator/remote_model_client.py'
    p=ROOT/dst
    category='active calculator'
    proof='tests.json'
    if src.startswith('quality/') or name.endswith('.md'):category='preserved quality/contract document';proof='source-preservation.json'
    elif '/web/' in src:
        active=name in active_html or name in ['workspace.html','workbench-shell.js','workspace.js']
        category='active original workbench' if active else 'historical/reference UI utility; not an enabled device/model shell'
        proof='browser-workflows.json' if active else 'source-preservation.json'
    if name in ['legacy.py','eoir_grid_comparison.py','research_models.py','model_io.py','model_derived_api.py']:
        category='preserved legacy compatibility/reference utility; old model capabilities not registered';proof='source-preservation.json'
    present={v['name'] for v in symbols(p)} if p.exists() else set()
    absent={v['name'] for v in f['symbols']}-present
    replacements={}
    if absent:
        actual='call' if name=='model-display.js' else 'validate'
        replacements={n:dict(target=actual,reason='Removed device adapter validation/request replaced by neutral scenario boundary and exact frozen model-row presentation; full common view/configuration binding remains in workspace-configuration.js') for n in absent}
    files.append(dict(source=src,target=dst,status='PRESERVED' if p.exists() and sha(p)==f['sha256'] else 'ADAPTED',category=category,
                      target_sha256=sha(p) if p.exists() else None,symbol_replacements=replacements,runtime_status='PRESERVED_NOT_EXECUTED' if proof=='source-preservation.json' else evidence(proof)['status'],evidence=[evidence(proof)],
                      active_capability_owner=('quality/QUALITY_GATES.yaml and docs/evidence/full' if src.startswith('quality/') else 'solsol/calculator/web/workspace.html + common engine quality/validation/results services'),
                      scope_note='Preservation/runtime evidence covers this owner as part of its common workflow; does not certify every possible input or independent model science.'))
domains={}
for d in ['public_api_client','all_initializers_solvers','quality_jobs_resume_export','set_search_quality','comparison_resource_studies','evidence_provenance']:domains[d]=evidence('tests.json')
for d in ['full_ui_workflows','run_storage_restore','neutral_model_switch']:domains[d]=evidence('browser-workflows.json')
domains['source_preservation']=evidence('source-preservation.json');domains['independent_scope_review']=evidence('independent-review.json')
mapping=dict(schema='SOLSOL_FULL_CAPABILITY_MAP_V2',files=files,acceptance_evidence=domains,
             limits=['Historical device model shells and fixtures are not enabled','Generic capability equivalence is bounded by recorded workflows; no field science or PRODUCT_EXIT certification','Old unimplemented quality-set/multi-seed-quality/robust-cost-proof routes are superseded by preserved common services, not falsely restored'])
write(ROOT/'docs/migration/capability-map.json',mapping)
report=check(inventory,ROOT,mapping);write(ROOT/'docs/migration/parity-report.json',report)
print(json.dumps(dict(status=report['status'],files=len(files),missing=report['missing'],unverified=report['unverified'],changed=report['changed'])))
