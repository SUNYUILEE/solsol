"""Export generic operations/record harnesses into an empty neutral project.

Never copies tasks, approvals, failures, historical runs or recovered sessions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from calculator_export import write,sha

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);a=parser.parse_args();source=a.source.resolve()
    if source==ROOT or source in ROOT.parents:raise ValueError('Separate export required')
    lineage=[]
    def copy(relative):
        src=source/relative;dst=ROOT/relative
        if dst.exists() and sha(src)!=sha(dst):raise ValueError('Refuse replacing existing operations source: '+relative)
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        lineage.append(dict(source=relative,target=relative,source_sha256=sha(src),target_sha256=sha(dst)))
    for name in ['research_ops.py','research_recovery.py','00_research_ops/RESEARCH_SYSTEM_ARCHITECTURE.md',
                 '00_research_ops/contracts/GATE_CATALOG_V7.json','00_research_ops/contracts/RECORD_STRUCTURE_BINDING_V2.json',
                 '00_research_ops/contracts/PROMOTION_STATE_MACHINE_V1.json','00_research_ops/contracts/GIT_PROMOTION_RECEIPT_V1.schema.json',
                 '00_research_ops/policies/GIT_PROMOTION_POLICY_V1.json',
                 '.agents/skills/research-operations-continuity/SKILL.md','.agents/skills/연구기록_전체복구/SKILL.md']:
        copy(name)
    for relative in ['06_code/harnesses/research_operations/src','06_code/harnesses/research_operations/tests',
                     '06_코드/harnesses/연구기록_전체복구기/src','06_코드/harnesses/연구기록_전체복구기/schemas']:
        for p in (source/relative).rglob('*'):
            if p.is_file() and p.suffix in ('.py','.json','.md') and '__pycache__' not in p.parts:copy(p.relative_to(source).as_posix())
    subprocess.run([sys.executable,'-B',str(ROOT/'research_ops.py'),'--project-root',str(ROOT),'init'],check=True)
    profile=json.loads((ROOT/'00_research_ops/PROJECT_PROFILE.json').read_text(encoding='utf8'))
    profile.update(project_id='SOLSOL-NEUTRAL-CALCULATOR',research_domain='Model-neutral sensor placement, MOEA, shared resources, LOS and reproducible evidence',
                   record_system_mode='NEW_PROJECT_EMPTY_V3',source_import_mode='MIGRATED_SOURCES_READ_ONLY_V1',
                   mandatory_project_instructions=['AGENTS.md','00_research_ops/START_HERE.md','00_research_ops/RESEARCH_SYSTEM_ARCHITECTURE.md','00_research_ops/contracts/GATE_CATALOG_V7.json','00_research_ops/contracts/RECORD_STRUCTURE_BINDING_V2.json','00_research_ops/policies/GIT_PROMOTION_POLICY_V1.json'],
                   new_project_initialization_evidence='00_research_ops/evidence/NEW_PROJECT_INITIALIZATION.json',
                   portable_package_lineage_evidence='00_research_ops/evidence/PORTABLE_PACKAGE_LINEAGE.json')
    write(ROOT/'00_research_ops/PROJECT_PROFILE.json',profile)
    binding=json.loads((ROOT/'00_research_ops/contracts/RECORD_STRUCTURE_BINDING_V2.json').read_text(encoding='utf8'))
    for row in binding['required_record_paths']:
        p=ROOT/row['path']
        if row['kind']=='directory':
            p.mkdir(parents=True,exist_ok=True)
            marker=p/'README.md'
            if not marker.exists():marker.write_text('# '+p.name+'\n\nNew neutral research record directory. No historical run or scientific approval is inherited.\n',encoding='utf8')
    (ROOT/'project.yaml').write_text('project_id: SOLSOL-NEUTRAL-CALCULATOR\nrecord_system_mode: NEW_PROJECT_EMPTY_V3\nresearch_domain: Model-neutral placement and reproducible evidence\n',encoding='utf8')
    (ROOT/'12_협업/역할목록.yaml').write_text('roles: [R00, R01, R02, R03, R04, R05, R06]\nself_approval_forbidden: true\n',encoding='utf8')
    if not (ROOT/'12_협업/역할간_인계기록.jsonl').exists():(ROOT/'12_협업/역할간_인계기록.jsonl').write_bytes(b'')
    for name in ['approved_artifacts.jsonl','failures/failure_registry.jsonl']:
        p=ROOT/'00_research_ops'/name;p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():p.write_bytes(b'')
    write(ROOT/'00_research_ops/evidence/NEW_PROJECT_INITIALIZATION.json',dict(schema='RESEARCH_NEW_PROJECT_INITIALIZATION_V1',status='PASS',record_system_mode='NEW_PROJECT_EMPTY_V3',historical_recovery_claimed=False,scientific_validation_claimed=False,record_store_initialized=True))
    write(ROOT/'00_research_ops/evidence/PORTABLE_PACKAGE_LINEAGE.json',dict(schema='RESEARCH_PORTABLE_PACKAGE_LINEAGE_V1',status='PASS',package_id='solsol-neutral-operations-export-20261102',project_specific_data_included=False,historical_run_data_included=False,files=lineage))
    write(ROOT/'docs/migration/operations-lineage.json',dict(status='PASS',checks=lineage,historical_results_included=False))
    checks=[]
    for action in ['doctor','system-audit']:
        result=subprocess.run([sys.executable,'-B',str(ROOT/'research_ops.py'),'--project-root',str(ROOT),action],capture_output=True,text=True,encoding='utf8')
        payload=json.loads(result.stdout);checks.append(dict(action=action,result=payload));assert result.returncode==0 and payload['status']=='PASS',payload
    write(ROOT/'docs/evidence/full/operations-bootstrap.json',dict(status='PASS',checks=checks,scope='new empty neutral record system; operational structure is not scientific validation'))


if __name__=='__main__':main()
