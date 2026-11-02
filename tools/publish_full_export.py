"""Evidence-gated, selected-file, non-forced publication to the authorized repo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from calculator_export import check,product_fingerprint,write,sha

ROOT=Path(__file__).resolve().parents[1]
ENV=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never',PYTHONUTF8='1')


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,env=ENV).decode('utf8')


def retained_whitespace(source,inventory,mapping):
    """Reject new whitespace errors; prove every retained one in original bytes.

    CRLF is intentional byte-preserving provenance. Markdown two-space line
    breaks and copied source EOF whitespace are retained only with exact proof.
    """
    result=subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
    assert result.returncode in (0,2),result.stderr
    originals={f['path']:f for f in inventory['files']}
    targets={f['target']:originals[f['source']] for f in mapping['files'] if f.get('target')}
    ops=json.loads((ROOT/'docs/migration/operations-lineage.json').read_text(encoding='utf8'))
    for f in ops['checks']:targets[f['target']]=dict(path=f['source'],sha256=f['source_sha256'])
    exceptions=[];diagnostics=0
    for line in result.stdout.splitlines():
        m=re.match(r'^(.*):(\d+): (.+)\.$',line)
        if not m:
            assert not line.strip() or line.startswith('+'),'Unrecognized whitespace diagnostic: '+line
            continue
        name,n,kind=m[1],int(m[2]),m[3];original=targets.get(name)
        diagnostics+=1
        assert kind in ('trailing whitespace','new blank line at EOF'),'Unreviewed whitespace kind: '+kind
        assert original,'New whitespace error: '+line
        p=source/original['path'];assert sha(p)==original['sha256'],'Changed original whitespace evidence'
        raw=p.read_bytes();actual=(ROOT/name).read_bytes()
        if kind=='trailing whitespace':assert actual.splitlines()[n-1] in raw.splitlines(),line
        else:assert raw.replace(b'\r\n',b'\n').endswith(b'\n\n') and actual.replace(b'\r\n',b'\n').endswith(b'\n\n'),line
        exceptions.append(dict(target=name,line=n,kind=kind,source=original['path'],source_sha256=original['sha256'],reason='Retained original bytes, not newly introduced whitespace'))
    assert result.returncode==0 or diagnostics>0,'Nonzero whitespace check without validated diagnostics'
    return exceptions


def main():
    p=argparse.ArgumentParser();p.add_argument('--push',action='store_true');p.add_argument('--receipt',type=Path,required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    inv=json.loads((ROOT/'docs/migration/source-inventory.json').read_text(encoding='utf8'))
    mapping=json.loads((ROOT/'docs/migration/capability-map.json').read_text(encoding='utf8'))
    assert check(inv,ROOT,mapping)['status']=='PASS','Incomplete full-scope preservation'
    fingerprint=product_fingerprint(ROOT)
    for name in ['tests.json','browser-workflows.json','independent-review.json','package-install.json','source-preservation.json']:
        proof=json.loads((ROOT/'docs/evidence/full'/name).read_text(encoding='utf8'))
        assert proof['status']=='PASS' and proof['product_sha256']==fingerprint,name
        if name=='independent-review.json':
            for item in proof.get('reviewed_files',[]):
                assert sha(ROOT/item['path'])==item['sha256'],'Reviewed artifact changed: '+item['path']
    assert json.loads((ROOT/'docs/evidence/full/operations-bootstrap.json').read_text(encoding='utf8'))['status']=='PASS'
    tree=ET.parse(ROOT/'docs/evidence/full/operations-tests.xml')
    assert len(list(tree.iter('testcase')))>=29 and not list(tree.iter('failure')) and not list(tree.iter('error'))
    assert git('remote','get-url','origin').strip()=='https://github.com/SUNYUILEE/solsol.git'
    assert git('symbolic-ref','--short','HEAD').strip()=='main'
    subprocess.run(['git','merge-base','--is-ancestor','d27fde5dbfbfd9eb18401c0016cbd4bbc5800afc','HEAD'],cwd=ROOT,check=True)
    selected=['.agents','.github','.gitattributes','.gitignore','AGENTS.md','README.md','START.cmd','pyproject.toml','solsol','tests','tools','docs','quality','MIGRATION_MANIFEST.json','research_ops.py','research_recovery.py','project.yaml','00_research_ops','01_목표','02_상태','03_방법','04_근거','05_데이터','06_코드','06_code','07_실행','08_검증','09_실패','10_결정','11_재현','12_협업','13_설명문서']
    git('add','--',*selected)
    names=list(filter(None,git('diff','--cached','--name-only','-z').split('\0')))
    token=re.compile(rb'(?i)(?<![A-Za-z0-9_])(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    local_user=re.compile(rb'(?i)[A-Z]:[/\\]Users[/\\][A-Za-z0-9_. -]+[/\\]')
    index={}
    for item in filter(None,git('ls-files','--stage','-z').split('\0')):
        meta,name=item.split('\t',1);index[name]=meta.split()[1]
    checks=[]
    for name in names:
        assert not any(v in name.split('/') for v in ['.env','.venv','node_modules','__pycache__','data','build','dist'])
        path=ROOT/name;assert not path.is_symlink()
        blob=path.read_bytes()
        assert hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()==index[name],'Staged bytes changed: '+name
        assert len(blob)<50_000_000 and not token.search(blob),'Sensitive/oversized selected file: '+name
        if name.endswith(('.py','.js','.html','.css','.json','.md','.yaml','.yml','.txt','.xml')):
            assert not local_user.search(blob),'Nonportable user path: '+name
        checks.append(dict(path=name,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest()))
    whitespace=retained_whitespace(a.source,inv,mapping)
    if not a.push:
        write(a.receipt,dict(status='PASS',checks=checks,retained_source_whitespace=whitespace,product_sha256=fingerprint,stage='REVIEWABLE_SELECTED_FILES_NOT_YET_PUSHED'));print('PASS: publication preflight');return
    git('commit','-m','Preserve full calculator workbench, APIs and evidence with neutral model boundary')
    commit=git('rev-parse','HEAD').strip();git('push','origin','main')
    remote=git('ls-remote','--heads','origin','main').split()[0];assert remote==commit
    assert not git('status','--porcelain').strip(),'Uncommitted export files remain'
    write(a.receipt,dict(status='PASS',checks=checks,retained_source_whitespace=whitespace,repository='https://github.com/SUNYUILEE/solsol',branch='main',commit=commit,remote_commit=remote,force_push=False,product_sha256=fingerprint))
    print(json.dumps(dict(status='PASS',commit=commit,remote_commit=remote,files=len(checks))))


if __name__=='__main__':main()
