"""Machine-discoverable common calculator API; detailed original client retained."""
def document():
    operations={
        '/config':['get'],'/engine/registry':['get'],'/engine/validate':['post'],'/engine/runs':['post'],
        '/engine/requests/{request_id}':['get'],'/runs':['get'],'/runs/{run_id}':['get'],
        '/runs/{run_id}/progress':['get'],'/engine/runs/{run_id}':['get'],
        '/engine/runs/{run_id}/view':['get'],'/engine/runs/{run_id}/export':['get'],
        '/engine/runs/{run_id}/copy':['get'],'/engine/runs/{run_id}/contract':['get'],
        '/engine/runs/{run_id}/capabilities':['get'],'/engine/runs/{run_id}/placements':['get'],
        '/engine/runs/{run_id}/spatial/{raw_id}':['get'],'/runs/{run_id}/cancel':['post'],
        '/engine/runs/{run_id}/quality-workflow':['get','post'],
        '/engine/runs/{run_id}/quality-jobs':['get','post'],
        '/engine/runs/{run_id}/quality-jobs/{job_id}/cancel':['post'],
        '/engine/runs/{run_id}/quality-jobs/{job_id}/resume':['post'],
        '/engine/runs/{run_id}/quality-jobs/{job_id}/rows':['get'],
        '/engine/runs/{run_id}/quality-jobs/{job_id}/export':['get'],
        '/engine/runs/{run_id}/quality-research':['get','post'],
        '/engine/runs/{run_id}/diagnostics':['get','post'],
        '/engine/compare':['post'],'/engine/diff':['post'],
        '/engine/validations/preview':['post'],'/engine/validations':['get','post'],
        '/engine/validations/{validation_id}':['get'],
        '/engine/validations/{validation_id}/cancel':['post'],
        '/engine/validations/{validation_id}/retry':['post'],
        '/engine/validations/{validation_id}/export':['get'],
        '/engine/resource-studies':['get'],'/engine/resource-studies/preview':['post'],
        '/engine/resource-studies/{study_id}':['get'],
        '/engine/guided-cost-budget/preview-a':['post'],'/engine/guided-cost-budget/preview-b':['post'],
        '/engine/runs/{run_id}/grid-comparison':['get','post'],
        '/engine/runs/{run_id}/cost-reference':['get','post'],
        '/engine/runs/{run_id}/storage-recovery':['get','post']}
    paths={}
    for path,methods in operations.items():
        params=[dict(name='cid',**{'in':'path'},required=True,schema={'type':'string'})]
        import re
        params += [dict(name=n,**{'in':'path'},required=True,schema={'type':'string'}) for n in re.findall(r'\{([^}]+)\}',path)]
        paths['/contracts/{cid}/api'+path]={m:dict(operationId=m+'_'+path.replace('/','_'),parameters=params,
            responses={'200':{'description':'Provenance-bound calculator response'},'400':{'description':'Contract, input or integrity failure'}},
            description='See engine_client.py for exact payload helpers. POST requires X-Run-Token; submit also requires X-Request-ID and X-Execution-SHA256.') for m in methods}
    return dict(openapi='3.1.0',info=dict(title='SOLSOL full calculator API',version='0.2.0'),paths=paths,
        **{'x-evidence-contract':'Immutable config/evaluator/registry identity; raw optimizer, diagnostics and references remain separate.'})
