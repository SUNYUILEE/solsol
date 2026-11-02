"""Full calculator entrypoint. Run commands use the UI's HTTP service."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    web=sub.add_parser('serve');web.add_argument('--port',type=int,default=8877);web.add_argument('--data-dir',default='data/full-calculator');web.add_argument('--model-plugin',action='append',default=[])
    for name in ['example','run','list','replay','audit']:
        q=sub.add_parser(name);q.add_argument('--url',default='http://127.0.0.1:8877');q.add_argument('--contract',default='ABC_COVERAGE_RESOURCE_V1')
        if name=='example':q.add_argument('--output',type=Path)
        if name=='run':q.add_argument('--config',type=Path,required=True);q.add_argument('--request-id')
        if name in ['replay','audit']:q.add_argument('run_id')
        if name=='audit':q.add_argument('--options',type=Path)
    args=p.parse_args()
    try:
        if args.command=='serve':
            from .calculator.launch import serve
            return serve(args.port,args.data_dir,args.model_plugin)
        from .calculator.client import EngineClient
        client=EngineClient(args.contract,args.url)
        if args.command=='example':
            registry=client.registry();meta=next(b for b in registry['bundles'] if b['id']==args.contract)
            result=dict(experiment_contract_id=args.contract,model_config=registry['ui_models'][args.contract]['defaults'],enabled_sensor_ids=[s['id'] for s in meta['sensors']],objective_ids=meta['default_objective_ids'],diagnostic_ids=[],solver_policy='generic_v1',goals=None,optimizer=dict(algorithm='NSGA-II',population=8,generations=2,seed=1,initializer='random'))
        elif args.command=='run':result=client.submit_configuration(json.loads(args.config.read_text(encoding='utf-8-sig')),args.request_id)
        elif args.command=='list':result=client.list_runs()
        elif args.command=='replay':result=client.status(args.run_id)
        else:result=client.diagnose(args.run_id,json.loads(args.options.read_text(encoding='utf-8-sig')) if args.options else {})
        text=json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)
        if args.command=='example' and args.output:args.output.write_text(text+'\n',encoding='utf-8')
        else:print(text)
    except (ValueError,OSError,RuntimeError,KeyError) as exc:p.exit(2,str(exc)+'\n')
