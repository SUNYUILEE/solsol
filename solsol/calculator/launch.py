"""Serve the preserved calculator UI and common API without a legacy server."""
import json
import mimetypes
from pathlib import Path
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from engine.http_compat import HTTPCompat
from model_service_client import CID,client,default_config,model_metadata,model_schema
import live_server


def make_server(port=8877,data_dir='data/full-calculator',model_plugins=()):
    import importlib
    for name in model_plugins:
        module=importlib.import_module(name)
        module.register_models(__import__('model_service_client'))
    live_server.TOKEN=secrets.token_urlsafe(32)
    owner=HTTPCompat(Path(data_dir).resolve())
    class Handler(BaseHTTPRequestHandler):
        contract=CID
        def log_message(self,*args):pass
        def local(self):
            hosts=(f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
            if self.headers.get('Host') not in hosts:raise ValueError('Local host required')
            if self.command=='POST':
                origin=self.headers.get('Origin')
                if origin and origin not in tuple('http://'+h for h in hosts):raise ValueError('Origin mismatch')
                if self.headers.get('X-Run-Token')!=live_server.TOKEN:raise ValueError('Run token required')
        def route(self):
            parsed=urlsplit(self.path);match=re.fullmatch(r'/contracts/([A-Z][A-Z0-9_-]*)(/api/.*)',parsed.path)
            if match:
                self.contract=match[1];model_metadata(self.contract)
                if self.headers.get('X-Experiment-Contract') not in (None,self.contract):raise ValueError('Contract header mismatch')
                return match[2],parse_qs(parsed.query)
            self.contract=CID;return parsed.path,parse_qs(parsed.query)
        def end_headers(self):
            self.send_header('X-Experiment-Contract',self.contract)
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            super().end_headers()
        def send_json(self,value,status=200):
            if isinstance(value,dict):value=dict(value,experiment_contract_id=self.contract)
            from engine.binary_decision import json_default
            content=json.dumps(value,ensure_ascii=False,allow_nan=False,default=json_default).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
        def do_GET(self):
            try:
                self.local();endpoint,query=self.route()
                if endpoint=='/api/config':return self.send_json(dict(default=model_schema(self.contract)['defaults'],common_default=default_config(),token=live_server.TOKEN,state='ready'))
                if endpoint=='/api/bootstrap':return self.send_json(dict(token=live_server.TOKEN,registry=client().request('/models')['registry'],default_contract=CID))
                if endpoint=='/api/openapi.json':
                    from .openapi import document
                    return self.send_json(document())
                if endpoint.startswith('/api/'):
                    if owner.get(self,endpoint,query):return
                    return self.send_json(dict(error='API route not found'),404)
                name=endpoint.lstrip('/')
                if name in ('','index.html','live.html','rf.html'):name='workspace.html'
                if name in ('demo.html','prototype.html','experiment-workbench.html'):
                    return self.send_json(dict(error='Historical model-specific shell; use /workspace.html'),410)
                file=ROOT/'web'/name
                if '/' in name or '\\' in name or not file.is_file():return self.send_json(dict(error='Not found'),404)
                content=file.read_bytes();self.send_response(200);self.send_header('Content-Type',(mimetypes.guess_type(str(file))[0] or 'application/octet-stream')+'; charset=utf-8');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
            except Exception as exc:self.send_json(dict(error=f'{type(exc).__name__}: {exc}'),400)
        def do_POST(self):
            try:
                self.local();endpoint,query=self.route()
                if self.headers.get_content_type()!='application/json':raise ValueError('JSON required')
                if endpoint=='/api/preview':
                    from model_service_client import compile_remote
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=2*1024*1024:raise ValueError('Body size')
                    body=json.loads(self.rfile.read(size));cp=compile_remote(self.contract,body.get('model_config',body))
                    return self.send_json(dict(problem=cp.view_problem()))
                if owner.post(self,endpoint,query):return
                return self.send_json(dict(error='API route not found'),404)
            except Exception as exc:
                # Preserve error truth; failed runs/quality jobs retain their own
                # immutable raw, journal, batch and failure artifacts.
                self.send_json(dict(error=f'{type(exc).__name__}: {exc}'),400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.workspace=owner
    return server


def serve(port=8877,data_dir='data/full-calculator',model_plugins=()):
    server=make_server(port,data_dir,model_plugins)
    print(f'SOLSOL workspace: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
