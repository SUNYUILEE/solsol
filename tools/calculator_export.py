"""Source-backed calculator migration inventory and fail-closed publication gate."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def product_fingerprint(target):
    root=Path(target)
    paths=[root/'pyproject.toml',*[p for p in (root/'solsol').rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css','.json') and '__pycache__' not in p.parts]]
    return hashlib.sha256(json.dumps({p.relative_to(root).as_posix():sha(p) for p in sorted(paths)},sort_keys=True).encode()).hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def symbols(path):
    text=path.read_text(encoding='utf-8')
    if path.suffix=='.py':
        tree=ast.parse(text)
        return [dict(kind=type(n).__name__,name=n.name,line=n.lineno)
                for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
    if path.suffix=='.js':
        return [dict(kind='javascript',name=m.group(1),line=text[:m.start()].count('\n')+1)
                for m in re.finditer(r'\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(',text)]
    if path.suffix=='.html':
        return [dict(kind='control',name=m.group(1),line=text[:m.start()].count('\n')+1)
                for m in re.finditer(r'\bid="([^"]+)"',text)]
    return []


def inventory(source):
    source=Path(source).resolve();files=[]
    for folder in ['app/integrated/engine','app/integrated/web','quality']:
        for p in sorted((source/folder).rglob('*')):
            if p.is_file() and p.suffix in ('.py','.js','.html','.css','.json','.yaml','.md') and '__pycache__' not in p.parts:
                files.append(dict(path=p.relative_to(source).as_posix(),bytes=p.stat().st_size,sha256=sha(p),symbols=symbols(p)))
    for name in ['engine_client.py','json_transport.py','background_process.py','model_service_client.py','model_io.py','model_derived_api.py','COMMON_UI_CONTRACT.md','ENGINE_ACCESS.md']:
        p=source/'app/integrated'/name
        files.append(dict(path=p.relative_to(source).as_posix(),bytes=p.stat().st_size,sha256=sha(p),symbols=symbols(p)))
    gates=(source/'quality/QUALITY_GATES.yaml').read_text(encoding='utf-8')
    return dict(schema='SOLSOL_FULL_CALCULATOR_INVENTORY_V1',files=files,
        gate_ids=sorted(set(re.findall(r'QG-\d+(?:-\d+)*',gates))),
        symbol_count=sum(len(f['symbols']) for f in files),historical_results_included=False)


def check(source_inventory,target,mapping):
    target=Path(target).resolve();dispositions={x['source']:x for x in mapping['files']};missing=[];unverified=[];changed=[]
    model_only={'app/integrated/web/'+n for n in ['hmsp-exec-example.json','workspace-hmsp.js','workspace-hmsp2d.js','workspace-cue-meaning.js','workspace-research-models.js','program-research.js']}
    adapter_files={'app/integrated/web/workspace-model.js','app/integrated/web/model-display.js'}
    def proof_valid(e,domain=None):
        if not isinstance(e,dict):return False
        p=target/e.get('path','__missing__')
        if e.get('status')!='PASS' or not p.is_file() or e.get('sha256')!=sha(p):return False
        try:proof=json.loads(p.read_text(encoding='utf8'))
        except (ValueError,OSError):return False
        return (proof.get('status')=='PASS' and bool(proof.get('checks'))
                and (domain is None or domain in proof.get('domains',[]))
                and (not proof.get('product_sha256') or proof['product_sha256']==product_fingerprint(target)))
    for item in source_inventory['files']:
        entry=dispositions.get(item['path'])
        if not entry:missing.append(dict(source=item['path'],reason='no disposition'));continue
        if entry['status']=='EXCLUDED_MODEL':
            if item['path'] not in model_only or not entry.get('reason') or entry.get('calculator_capabilities_removed') is not False:
                missing.append(dict(source=item['path'],reason='unjustified model exclusion'))
            continue
        p=target/entry['target']
        if not p.is_file():missing.append(dict(source=item['path'],reason='target missing'));continue
        if entry.get('target_sha256')!=sha(p):changed.append(entry['target'])
        required={s['name'] for s in item['symbols']};present={s['name'] for s in symbols(p)}
        replacements=entry.get('symbol_replacements',{})
        excluded=entry.get('excluded_model_symbols',{})
        for name,value in replacements.items():
            if not isinstance(value,dict) or value.get('target') not in present or not value.get('reason'):
                missing.append(dict(source=item['path'],reason='invalid replacement',symbol=name))
        if excluded and (item['path'] not in adapter_files or not all(isinstance(v,str) and v.strip() for v in excluded.values())):
            missing.append(dict(source=item['path'],reason='invalid model symbol exclusion'))
        absent=required-present-set(replacements)-set(excluded)
        if absent:missing.append(dict(source=item['path'],symbols=sorted(absent)))
        static=entry.get('runtime_status')=='PRESERVED_NOT_EXECUTED' and entry.get('active_capability_owner') and entry.get('category') in ('preserved quality/contract document','historical/reference UI utility; not an enabled device/model shell','preserved legacy compatibility/reference utility; old model capabilities not registered')
        if (entry.get('runtime_status')!='PASS' and not static) or not entry.get('evidence') or not all(proof_valid(e) for e in entry['evidence']):unverified.append(item['path'])
    evidence=mapping.get('acceptance_evidence',{})
    domains=['full_ui_workflows','public_api_client','run_storage_restore','all_initializers_solvers',
             'quality_jobs_resume_export','set_search_quality','comparison_resource_studies',
             'evidence_provenance','neutral_model_switch','source_preservation','independent_scope_review']
    for domain in domains:
        if not proof_valid(evidence.get(domain,{}),domain):unverified.append(domain)
    if source_inventory.get('gate_ids'):
        gate_file=target/'quality/QUALITY_GATES.yaml'
        gates=set(re.findall(r'QG-\d+(?:-\d+)*',gate_file.read_text(encoding='utf8'))) if gate_file.is_file() else set()
        if set(source_inventory['gate_ids'])-gates:missing.append(dict(source='quality/QUALITY_GATES.yaml',reason='detailed gate IDs removed'))
    return dict(status='PASS' if not (missing or unverified or changed) else 'FAIL',
                missing=missing,unverified=unverified,changed=changed,
                inherited_scientific_pass=False,complete_claim_allowed=not (missing or unverified or changed))


def copy_common(source,target):
    source=Path(source).resolve();target=Path(target).resolve()
    if source==target or source in target.parents:raise ValueError('Export must be outside source workspace')
    # Copy common calculator sources as the starting point. Model adapters are
    # replaced explicitly after this stage; imported models/results never enter.
    pairs=[('app/integrated/engine','solsol/calculator/engine'),('app/integrated/web','solsol/calculator/web'),('quality','quality')]
    # Validate the complete plan before copying anything. An already adapted
    # target must never be silently reset by repeating an extraction command.
    for src,dst in pairs:
        for p in (source/src).rglob('*'):
            if p.is_file() and p.suffix in ('.py','.js','.html','.css','.json','.yaml','.md') and '__pycache__' not in p.parts:
                out=target/dst/p.relative_to(source/src)
                if out.exists() and sha(out)!=sha(p):raise ValueError('Refusing to overwrite adapted export: '+str(out.relative_to(target)))
    for src,dst in pairs:
        for p in (source/src).rglob('*'):
            if p.is_file() and p.suffix in ('.py','.js','.html','.css','.json','.yaml','.md') and '__pycache__' not in p.parts:
                out=target/dst/p.relative_to(source/src);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
    for name in ['engine_client.py','json_transport.py','background_process.py','COMMON_UI_CONTRACT.md','ENGINE_ACCESS.md']:
        out=target/'solsol/calculator'/name;out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/'app/integrated'/name,out)
    for name in ['live_empirical_archive.py','search.py']:
        out=target/'solsol/calculator'/name
        shutil.copy2(source/'app/integrated/implementation'/name,out)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('inventory');i.add_argument('--source',required=True);i.add_argument('--output',required=True)
    c=sub.add_parser('copy-common');c.add_argument('--source',required=True);c.add_argument('--target',required=True)
    v=sub.add_parser('check');v.add_argument('--inventory',required=True);v.add_argument('--mapping',required=True);v.add_argument('--target',required=True);v.add_argument('--output',required=True)
    a=p.parse_args()
    if a.command=='inventory':write(a.output,inventory(a.source))
    if a.command=='copy-common':copy_common(a.source,a.target)
    if a.command=='check':
        result=check(json.loads(Path(a.inventory).read_text(encoding='utf8')),a.target,json.loads(Path(a.mapping).read_text(encoding='utf8')))
        write(a.output,result);print(json.dumps(dict(status=result['status'],missing=len(result['missing']),unverified=len(result['unverified']),changed=len(result['changed']))))
        if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
