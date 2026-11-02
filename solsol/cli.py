import argparse
import json
from pathlib import Path

from .models.coverage import CoverageModel,example_config
from .engine.runtime import run_experiment,replay
from .engine.storage import RunStore


def main():
    p=argparse.ArgumentParser(description='SOLSOL abstract sensor placement calculator')
    sub=p.add_subparsers(dest='command',required=True)
    demo=sub.add_parser('example');demo.add_argument('--output',type=Path)
    run=sub.add_parser('run');run.add_argument('--config',type=Path)
    run.add_argument('--data-dir',default='data/runs');run.add_argument('--seed',type=int,default=1)
    run.add_argument('--population',type=int,default=48);run.add_argument('--generations',type=int,default=30)
    run.add_argument('--algorithm',choices=['NSGA-II','NSGA-III'],default='NSGA-II')
    run.add_argument('--initializer',choices=['random','greedy','milp'],default='random')
    verify=sub.add_parser('replay');verify.add_argument('run_id');verify.add_argument('--data-dir',default='data/runs')
    ls=sub.add_parser('list');ls.add_argument('--data-dir',default='data/runs')
    audit=sub.add_parser('audit');audit.add_argument('run_id');audit.add_argument('--data-dir',default='data/runs')
    audit.add_argument('--row',type=int);audit.add_argument('--exact',action='store_true')
    audit.add_argument('--budget',type=int,default=512);audit.add_argument('--output',type=Path,required=True)
    web=sub.add_parser('serve');web.add_argument('--port',type=int,default=8877);web.add_argument('--data-dir',default='data/runs')
    args=p.parse_args()
    try:
        if args.command=='serve':
            from .server import serve
            serve(args.port,args.data_dir);return
        if args.command=='example':
            value=json.dumps(example_config(),ensure_ascii=False,indent=2)
            if args.output:args.output.write_text(value+'\n',encoding='utf-8')
            else:print(value)
            return
        if args.command=='run':
            config=json.loads(args.config.read_text(encoding='utf-8')) if args.config else example_config()
            opt={k:getattr(args,k) for k in ['seed','population','generations','algorithm','initializer']}
            result=run_experiment(CoverageModel(config),opt);report=replay(result)
            if report['status']!='PASS':raise ValueError(report['error'])
            result['verification']=report;RunStore(args.data_dir).save(result)
            print(json.dumps(dict(run_id=result['run_id'],status=result['status'],nfe=len(result['rows']),
                                  archive_count=len(result['archive_ids']),verification=report),indent=2));return
        if args.command=='replay':
            report=replay(RunStore(args.data_dir).load(args.run_id));print(json.dumps(report,indent=2))
            if report['status']!='PASS':raise SystemExit(1)
        if args.command=='list':print(json.dumps(RunStore(args.data_dir).list(),indent=2))
        if args.command=='audit':
            from .engine.diagnostics import exact_reference,local_check
            stored=RunStore(args.data_dir).load(args.run_id)
            report=replay(stored)
            if report['status']!='PASS':raise ValueError(report['error'])
            model=CoverageModel(stored['config'])
            if args.exact:result=exact_reference(model)
            else:
                row=args.row if args.row is not None else next(iter(stored['archive_ids']),None)
                if row is None or not 0<=row<len(stored['rows']):raise ValueError('Choose an existing raw row')
                result=local_check(model,stored['rows'][row]['X'],args.budget)
                result['source_row_id']=row
            result['source_run_id']=stored['run_id']
            with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
            print(json.dumps(dict(output=str(args.output),evaluations=result['evaluations']),indent=2))
    except (ValueError,OSError,KeyError) as exc:p.exit(2,f'{exc}\n')
