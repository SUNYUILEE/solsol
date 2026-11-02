"""Fresh isolated install using only declared runtime dependencies."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import shutil
from calculator_export import write,product_fingerprint

ROOT=Path(__file__).resolve().parents[1]
started_product=product_fingerprint(ROOT)
with tempfile.TemporaryDirectory(prefix='solsol-package-') as temporary:
    root=Path(temporary);venv.EnvBuilder(with_pip=True).create(root/'venv')
    python=root/'venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    stage=root/'source';stage.mkdir()
    shutil.copytree(ROOT/'solsol',stage/'solsol',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(ROOT/'pyproject.toml',stage/'pyproject.toml')
    subprocess.run([str(python),'-m','pip','install','--quiet',str(stage)],check=True)
    code='''import tempfile,threading
from solsol.calculator.launch import make_server
from solsol.calculator.client import EngineClient
with tempfile.TemporaryDirectory() as data:
 s=make_server(0,data);t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
 try:
  c=EngineClient('ABC_COVERAGE_RESOURCE_V1',f'http://127.0.0.1:{s.server_port}');r=c.registry();m=r['bundles'][0]
  q=dict(experiment_contract_id=m['id'],model_config=r['ui_models'][m['id']]['defaults'],enabled_sensor_ids=[v['id'] for v in m['sensors']],objective_ids=m['default_objective_ids'],diagnostic_ids=[],solver_policy='generic_v1',goals=None,optimizer=dict(algorithm='NSGA-II',population=8,generations=1,seed=2,initializer='random'))
  assert c.validate_configuration(q)['summary']['n_obj']==3
  posted=c.submit_configuration(q);saved=c.wait(posted['run_id'],30);assert saved['state']=='completed',saved
  assert len(saved['checkpoints'])==2
 finally:s.shutdown();s.server_close();t.join()
'''
    subprocess.run([str(python),'-I','-c',code],cwd=root,check=True)
assert product_fingerprint(ROOT)==started_product,'Product changed during isolated build; rerun with frozen sources'
write(ROOT/'docs/evidence/full/package-install.json',dict(status='PASS',checks=['fresh venv without system site packages','package installed with declared runtime dependencies only','isolated interpreter outside repository validates/submits/completes through same full HTTP service','product fingerprint frozen before source stage and unchanged after installed run'],product_sha256=started_product))
print('PASS: isolated package installation and actual full-service run')
