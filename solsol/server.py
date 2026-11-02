"""Loopback research workspace; asynchronous run, stop, save and restoration."""
import copy
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .engine.runtime import run_experiment,replay,options
from .engine.storage import RunStore
from .models.coverage import CoverageModel,example_config


class Workspace:
    def __init__(self,data_dir):
        self.store=RunStore(data_dir);self.jobs={};self.lock=threading.Lock()

    def start(self,body):
        model=CoverageModel(body['config']);opt=options(body.get('optimizer'))
        with self.lock:
            if any(j['status'] not in ('completed','stopped','time_limit','failed') for j in self.jobs.values()):
                raise ValueError('A run is already active')
            job_id=str(uuid.uuid4());event=threading.Event()
            job=dict(job_id=job_id,status='waiting',generation=0,nfe=0,elapsed_seconds=0.,cancel=event)
            self.jobs[job_id]=job
        def progress(value):
            with self.lock:job.update(value)
        def work():
            try:
                run=run_experiment(model,opt,progress,event)
                terminal=run['status'];progress(dict(status='verifying'))
                verification=replay(run)
                if verification['status']!='PASS':raise ValueError(verification['error'])
                run['verification']=verification;progress(dict(status='saving'))
                self.store.save(run)
                with self.lock:job.update(status=terminal,run_id=run['run_id'],archive_count=len(run['archive_ids']))
            except Exception as exc:
                with self.lock:job.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        threading.Thread(target=work,daemon=True).start()
        return dict(job_id=job_id)


def make_server(port=8877,data_dir='data/runs'):
    workspace=Workspace(data_dir);web=Path(__file__).parent/'web'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,data,status=200,ctype='application/json; charset=utf-8'):
            payload=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(payload)
        def do_GET(self):
            path=urlsplit(self.path).path
            try:
                if self.headers.get('Host','') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
                    raise ValueError('Local host required')
                if path=='/api/example':return self.send(dict(config=example_config()))
                if path=='/api/runs':return self.send(workspace.store.list())
                if path.startswith('/api/runs/'):
                    return self.send(workspace.store.load(path.removeprefix('/api/runs/')))
                if path.startswith('/api/jobs/'):
                    with workspace.lock:
                        j=workspace.jobs[path.removeprefix('/api/jobs/')]
                        value={k:v for k,v in j.items() if k!='cancel'}
                    return self.send(value)
                files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),
                       '/style.css':('style.css','text/css; charset=utf-8')}
                if path in files:
                    name,ctype=files[path];return self.send((web/name).read_bytes(),ctype=ctype)
                return self.send(dict(error='Not found'),404)
            except (ValueError,KeyError,OSError) as exc:return self.send(dict(error=str(exc)),400)
        def do_POST(self):
            try:
                expected=f'127.0.0.1:{self.server.server_port}'
                host=self.headers.get('Host','')
                if host not in (expected,f'localhost:{self.server.server_port}'):raise ValueError('Local host required')
                origin=self.headers.get('Origin')
                if origin is not None and origin not in (f'http://{expected}',f'http://localhost:{self.server.server_port}'):
                    raise ValueError('Cross-origin writes forbidden')
                if self.headers.get_content_type()!='application/json':raise ValueError('JSON request required')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16000000:raise ValueError('Invalid body size')
                body=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
                if path=='/api/validate':
                    m=CoverageModel(body['config']);opt=options(body.get('optimizer'))
                    return self.send(dict(status='PASS',experiment_contract_id=m.contract_id,
                        objective_ids=m.objective_ids,constraint_ids=m.constraint_ids,optimizer=opt,
                        candidate_count=m.space.shape[0],point_count=len(m.config['points'])))
                if path=='/api/jobs':return self.send(workspace.start(body),202)
                if path.startswith('/api/jobs/') and path.endswith('/stop'):
                    job_id=path.split('/')[3]
                    with workspace.lock:
                        workspace.jobs[job_id]['cancel'].set()
                        if workspace.jobs[job_id]['status'] in ('waiting','preparing','running'):
                            workspace.jobs[job_id]['status']='stop_requested'
                    return self.send(dict(status='stop_requested'))
                if path=='/api/replay':
                    return self.send(replay(workspace.store.load(body['run_id'])))
                return self.send(dict(error='Not found'),404)
            except (ValueError,KeyError,TypeError,OSError) as exc:return self.send(dict(error=str(exc)),400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.workspace=workspace
    return server


def serve(port=8877,data_dir='data/runs'):
    server=make_server(port,data_dir)
    print(f'SOLSOL workspace: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
