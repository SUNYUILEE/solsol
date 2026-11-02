"""Run all actual tests and produce a provenance-bound full-calculator report."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from calculator_export import write,product_fingerprint,sha

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);a=p.parse_args()
    out=ROOT/'docs/evidence/full';out.mkdir(parents=True,exist_ok=True)
    xml=out/'pytest.xml'
    args=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider','--junitxml='+str(xml)]
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    (out/'pytest-output.txt').write_text((result.stdout+'\n'+result.stderr).replace(str(ROOT),'<repository>').rstrip()+'\n',encoding='utf8')
    cases=list(ET.parse(xml).iter('testcase')) if xml.exists() else []
    names=[c.attrib['classname']+'.'+c.attrib['name'] for c in cases]
    passed=result.returncode==0 and len(cases)>60 and not any(list(c) for c in cases)
    report=dict(status='PASS' if passed else 'FAIL',checks=names,tests=len(cases),command=[s.replace(str(ROOT),'<repository>') for s in args[2:]],returncode=result.returncode,public_paths_normalized=True,
                domains=['public_api_client','all_initializers_solvers','quality_jobs_resume_export','set_search_quality','comparison_resource_studies','evidence_provenance'],
                product_sha256=product_fingerprint(ROOT),junit_sha256=sha(xml),scientific_field_validity='NOT_MEASURED',human_usability='NOT_MEASURED',global_optimality='NOT_CERTIFIED')
    write(out/'tests.json',report)
    if a.source:
        inventory=json.loads((ROOT/'docs/migration/source-inventory.json').read_text(encoding='utf8'))
        checks=[dict(path=f['path'],unchanged=(a.source/f['path']).is_file() and sha(a.source/f['path'])==f['sha256']) for f in inventory['files']]
        write(out/'source-preservation.json',dict(status='PASS' if all(c['unchanged'] for c in checks) else 'FAIL',checks=checks,read_only=True,domains=['source_preservation'],product_sha256=product_fingerprint(ROOT)))
    print(json.dumps(dict(status=report['status'],tests=len(cases),returncode=result.returncode)))
    if not passed:print(result.stdout[-14000:]);raise SystemExit(1)


if __name__=='__main__':main()
