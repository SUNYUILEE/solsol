import json
import threading
from urllib.error import HTTPError
from urllib.request import Request,urlopen

import pytest

from solsol.server import make_server
from solsol.engine.storage import RunStore
from test_contract import tiny


def test_http_contract_validation_and_origin(tmp_path):
    server=make_server(0,tmp_path);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def post(path,value,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        return urlopen(Request(base+path,data=json.dumps(value).encode(),headers=headers))
    try:
        with post('/api/validate',dict(config=tiny())) as response:
            assert json.load(response)['status']=='PASS'
        with pytest.raises(HTTPError):post('/api/jobs',dict(config=tiny()),'https://unrelated.example')
        c=tiny();c['sensors'][0]['maximum']=.5
        with pytest.raises(HTTPError):post('/api/validate',dict(config=c))
        with urlopen(base+'/') as response:assert b'SOLSOL' in response.read()
        with pytest.raises(HTTPError):urlopen(Request(base+'/api/runs',headers={'Host':'attacker.example'}))
    finally:server.shutdown();server.server_close();thread.join()


def test_storage_path_and_immutable_run(tmp_path):
    from solsol.engine.runtime import run_experiment
    from solsol.models.coverage import CoverageModel
    store=RunStore(tmp_path)
    with pytest.raises(ValueError):store.load('../other')
    run=run_experiment(CoverageModel(tiny()),dict(population=4,generations=0))
    store.save(run);store.save(run)
    run['status']='changed'
    with pytest.raises(ValueError):store.save(run)
