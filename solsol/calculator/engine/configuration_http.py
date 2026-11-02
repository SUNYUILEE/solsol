"""Configuration routes on the existing authenticated HTTP service."""
import re
import copy
from .configuration import catalog,compile_request
from .runtime import source_snapshot,TERMINAL
from .workflow import request_body,execution_snapshot,result_contract,copy_request,compare,diff,capability,restore_copy_numbers,metadata_packet

def get(owner,h,endpoint,query):
    recovery=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/storage-recovery',endpoint)
    if recovery:
        if query:raise ValueError('STORAGE_RECOVERY_QUERY')
        from .storage_recovery import inspect_recovery,recover
        h.send_json(inspect_recovery(owner.service,h.contract,recovery[1]));return True
    controlled=re.fullmatch(r'/api/engine/guided-cost-budget/([0-9a-f-]{36})/controlled-comparison',endpoint)
    if controlled:
        from .guided_control import comparison
        from .validation_http import manager
        if set(query)-{'scope'} or any(len(v)!=1 for v in query.values()):raise ValueError('GUIDED_QUERY')
        h.send_json(comparison(manager(owner),h.contract,controlled[1],query.get('scope',['all'])[0]));return True
    progress=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/quality-jobs(?:/([0-9a-f-]{36}))?/progress',endpoint)
    if progress:
        if query:raise ValueError('QUALITY_PROGRESS_QUERY')
        from .quality_progress import snapshot,listing,find_folder
        folder=find_folder(owner.service,h.contract,progress[1])
        h.send_json(snapshot(folder,progress[2]) if progress[2] else listing(folder));return True
    seed=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/initial-seed',endpoint)
    if seed:
        from .saved_initialization import first
        if set(query)-{'sort','targets'} or any(len(v)!=1 for v in query.values()) or query.get('targets',['false'])[0] not in ('true','false'):raise ValueError('Invalid saved placement filter')
        h.send_json(first(owner.get_record(h.contract,seed[1]),query.get('sort',['cost'])[0],query.get('targets',['false'])[0]=='true'));return True
    guided=re.fullmatch(r'/api/engine/guided-cost-budget(?:/([0-9a-f-]{36})/(proposal|comparison))?',endpoint)
    if guided:
        from . import guided_cost_budget as guide
        from .validation_http import manager
        if set(query)-{'scope'} or any(len(v)!=1 for v in query.values()):raise ValueError('GUIDED_QUERY')
        service=manager(owner)
        h.send_json(guide.listed(service,h.contract) if not guided[1] else guide.proposal(service,h.contract,guided[1],query.get('scope',['all'])[0]) if guided[2]=='proposal' else guide.comparison(service,h.contract,guided[1],query.get('scope',[None])[0]));return True
    if endpoint=='/api/engine/resource-studies':
        from .resource_study import study_list
        from .validation_http import manager
        if query:raise ValueError('RESOURCE_STUDY_QUERY')
        h.send_json(study_list(manager(owner),h.contract));return True
    scarcity=re.fullmatch(r'/api/engine/resource-studies/([0-9a-f-]{36})',endpoint)
    if scarcity:
        from .resource_study import report
        from .validation_http import manager
        if set(query)-{'scope'} or any(len(v)!=1 for v in query.values()):raise ValueError('RESOURCE_STUDY_QUERY')
        h.send_json(report(manager(owner),h.contract,scarcity[1],query.get('scope',['all'])[0]));return True
    cost=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/cost-reference(?:/([0-9a-f-]{36})(/export)?)?',endpoint)
    if cost:
        from . import cost_reference as cr
        if query:raise ValueError('COST_REFERENCE_QUERY')
        record=owner.get_record(h.contract,cost[1]);h.send_json(cr.export(record,cost[2]) if cost[3] else cr.read(record,cost[2]) if cost[2] else cr.listing(record));return True
    grid=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/grid-comparison(?:/([0-9a-f-]{36}))?',endpoint)
    if grid:
        from . import grid_comparison as gc
        if query:raise ValueError('GRID_QUERY')
        record=owner.get_record(h.contract,grid[1]);h.send_json(gc.read(record,grid[2]) if grid[2] else gc.listing(record));return True
    study=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/quality-research/([0-9a-f-]{36})',endpoint)
    if study:
        from .quality_research import study_status
        if query:raise ValueError('QUALITY_QUERY')
        h.send_json(study_status(h.contract,study[1],study[2]));return True
    job=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/quality-jobs(?:/([0-9a-f-]{36})(/rows|/export|/front)?)?',endpoint)
    if job:
        from . import quality_jobs as qj
        record=owner.get_record(h.contract,job[1])
        if job[3]=='/front':
            from .frozen_refinement import front_page
            if set(query)-{'offset'} or any(len(v)!=1 for v in query.values()):raise ValueError('REFINEMENT_FRONT_QUERY')
            offset=int(query.get('offset',['0'])[0])
            if offset<0:raise ValueError('REFINEMENT_FRONT_OFFSET')
            h.send_json(front_page(record,qj.get(record,job[2]),offset))
        elif job[3]=='/rows':
            if set(query)-{'offset','witnesses'} or any(len(v)!=1 for v in query.values()) or query.get('witnesses',['false'])[0] not in ('true','false'):raise ValueError('QUALITY_PAGE_QUERY')
            h.send_json(qj.page(record,job[2],int(query.get('offset',['0'])[0]),witnesses=query.get('witnesses',['false'])[0]=='true'))
        elif job[3]=='/export':
            if query:raise ValueError('QUALITY_QUERY')
            import tempfile,zipfile,json
            from pathlib import Path
            state=qj.get(record,job[2])
            with tempfile.TemporaryDirectory(prefix='solsol-quality-') as temp:
                root=Path(temp)
                for _ in qj.stored_entries(record,state):pass
                archive=root/'quality.zip'
                with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                    for chunk in state['chunks']:z.write(qj.location(record,job[2]).parent/chunk['name'],'batches/'+chunk['name'])
                    if state.get('derived_front'):
                        from .frozen_refinement import front_page
                        front_page(record,state,0)
                        z.write(qj.location(record,job[2]).parent/'front.json','front.json')
                    for round_file in qj.location(record,job[2]).parent.glob('round-*.json'):
                        z.write(round_file,round_file.name)
                    z.writestr('status.json',qj.packed(state));z.writestr('README.txt','Frozen diagnostic evidence. SHA-bound batches contain every Model evaluation. status.json describes completion and provenance. Not optimizer raw.\n')
                h.send_response(200);h.send_header('Content-Type','application/zip');h.send_header('Content-Disposition','attachment; filename="quality-'+job[2]+'.zip"');h.send_header('Content-Length',str(archive.stat().st_size));h.end_headers()
                with archive.open('rb') as f:
                    while chunk:=f.read(1024*1024):h.wfile.write(chunk)
        else:
            if query:raise ValueError('QUALITY_QUERY')
            h.send_json(qj.get(record,job[2]) if job[2] else qj.listing(record))
        return True
    quality=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/quality-workflow(?:/([0-9a-f-]{36}))?',endpoint)
    if quality:
        from .quality_workflow import overview,read
        if query and (quality[2] or query!={'view':['summary']}):raise ValueError('QUALITY_QUERY')
        from .quality_method_display import describe
        record=owner.get_record(h.contract,quality[1]);h.send_json(read(record,quality[2]) if quality[2] else describe(overview(record,summary=bool(query))));return True
    from .research_models import get as research_get
    if research_get(owner,h,endpoint,query):return True
    from .validation_http import get as validation_get
    if validation_get(owner,h,endpoint,query):return True
    observed=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/placements',endpoint)
    if observed:
        from .placements import placements
        if set(query)-{'generation','offset','limit','sort','targets','selection','area','arrange','hamming_radius','hamming_group','representatives_only','layout_scope'} or any(len(v)!=1 for v in query.values()):
            raise ValueError('Invalid placement query')
        if query.get('targets',['false'])[0] not in ('true','false'):raise ValueError('Invalid target filter')
        if query.get('representatives_only',['false'])[0] not in ('true','false'):raise ValueError('Invalid representative filter')
        record=owner.get_record(h.contract,observed[1])
        with record.lock:
            result=placements(record,int(query['generation'][0]) if 'generation' in query else None,
                              int(query.get('offset',['0'])[0]),int(query.get('limit',['100'])[0]),
                              query.get('sort',['cost'])[0],query.get('targets',['false'])[0]=='true',
                              query.get('selection',['all'])[0],query.get('area',['all'])[0],query.get('arrange',['plain'])[0],int(query.get('hamming_radius',['2'])[0]),int(query.get('hamming_group',['0'])[0]),query.get('representatives_only',['false'])[0]=='true',query.get('layout_scope',['all'])[0])
        h.send_json(result);return True
    spatial=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/spatial/(0|[1-9][0-9]*)',endpoint)
    if spatial:
        if query:raise ValueError('Spatial query not supported')
        record=owner.get_record(h.contract,spatial[1]);index=int(spatial[2])
        if not 0<=index<len(record.rows):raise ValueError('Unknown raw row')
        row=record.spatial(record.rows[index])
        h.send_json(dict(run_id=record.id,config_sha256=record.frozen_problem['config_sha256'],row=row));return True
    diagnostic=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/diagnostics(?:/([0-9a-f-]{36})(/export)?)?',endpoint)
    if diagnostic:
        from .research_diagnostics import list_diagnostics,read_diagnostic
        r=owner.get_record(h.contract,diagnostic[1])
        data=read_diagnostic(r,diagnostic[2]) if diagnostic[2] else list_diagnostics(r)
        if diagnostic[3]:
            content=(r.folder/'diagnostics'/(diagnostic[2]+'.json')).read_bytes()
            h.send_response(200);h.send_header('Content-Type','application/json');h.send_header('Content-Disposition','attachment; filename="'+diagnostic[2]+'.json"');h.send_header('Content-Length',str(len(content)));h.end_headers();h.wfile.write(content)
        else:h.send_json(data)
        return True
    if endpoint=='/api/config' and h.contract in ('TOY_DIMENSION_V1','HMSP-EXEC-V1','HMSP-2D-V1'):
        import live_server
        defaults={} if h.contract=='HMSP-2D-V1' else dict(n_candidates=3,n_constraints=0)
        h.send_json(dict(default=defaults,token=live_server.TOKEN,state='ready'));return True
    if endpoint=='/api/engine/registry':
        h.send_json(catalog());return True
    q=re.fullmatch(r'/api/engine/requests/([A-Za-z0-9_.:-]{1,128})',endpoint)
    if q:
        try:r=owner.service.lookup_request(h.contract,q[1])
        except KeyError:
            h.send_json(dict(error='REQUEST_NOT_FOUND'),404);return True
        h.send_json(dict(run_id=r.id,state=r.state,request_id=q[1],execution_snapshot=metadata_packet(r).get('execution_snapshot')));return True
    m=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})(/export|/view|/contract|/copy|/capabilities)?',endpoint)
    if not m:return False
    record=owner.get_record(h.contract,m[1])
    if m[2]=='/export':
        if metadata_packet(record).get('schema')=='SOLSOL_ENGINE_RUN_V1':
            data=owner.service.export(record.id,h.contract);name=record.id+'.json';mime='application/json'
        else:
            data,name,mime=owner.export(record)
        h.send_response(200);h.send_header('Content-Type',mime)
        h.send_header('Content-Disposition','attachment; filename="'+name+'"')
        h.send_header('Content-Length',str(len(data)));h.end_headers();h.wfile.write(data)
    elif m[2]=='/contract':
        if metadata_packet(record).get('schema')=='SOLSOL_ENGINE_RUN_V1' and record.state in TERMINAL:owner.service.store.read(record.folder)
        h.send_json(result_contract(record))
    elif m[2]=='/capabilities':h.send_json(capability(record))
    elif m[2]=='/copy':h.send_json(dict(parent=result_contract(record),request=copy_request(record)))
    elif m[2]=='/view':
        if set(query)-{'generation','view'} or any(len(v)!=1 for v in query.values()) or query.get('view',['full'])[0] not in ('full','summary'):raise ValueError('Unknown view query')
        h.send_json(owner.management.decorate(h.contract,record.id,record.view(int(query['generation'][0]) if 'generation' in query else None,summary=query.get('view')==['summary'])))
    else:h.send_json(record.packet(include_rows=False))
    return True

def post(owner,h,endpoint,query):
    recovery=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/storage-recovery',endpoint)
    if recovery:
        if query:raise ValueError('STORAGE_RECOVERY_QUERY')
        from .storage_recovery import inspect_recovery,recover
        obj=owner.body(h)
        if set(obj)!={'expected_intent_sha256'}:raise ValueError('STORAGE_RECOVERY_FIELDS')
        result=recover(owner.service,h.contract,recovery[1],obj['expected_intent_sha256'])
        owner.unavailable.pop((h.contract,recovery[1]),None)
        h.send_json(result);return True
    if endpoint=='/api/engine/guided-cost-budget/controlled-checks':
        from .guided_control import checks
        from .validation_http import manager
        if query:raise ValueError('GUIDED_QUERY')
        h.send_json(checks(manager(owner),h.contract,owner.body(h,limit=2*1024*1024)));return True
    if endpoint=='/api/engine/guided-cost-budget/preview-controlled':
        from .guided_control import preview
        from .validation_http import manager
        if query:raise ValueError('GUIDED_QUERY')
        h.send_json(preview(manager(owner),h.contract,owner.body(h,limit=2*1024*1024)));return True
    if endpoint in ('/api/engine/guided-cost-budget/preview-a','/api/engine/guided-cost-budget/preview-b','/api/engine/guided-cost-budget/checks','/api/engine/guided-cost-budget/placement-checks'):
        from . import guided_cost_budget as guide
        from .validation_http import manager
        if query:raise ValueError('GUIDED_QUERY')
        fn={'preview-a':guide.preview_a,'preview-b':guide.preview_b,'checks':guide.checks,'placement-checks':guide.placement_checks}[endpoint.rsplit('/',1)[-1]]
        h.send_json(fn(manager(owner),h.contract,owner.body(h,limit=2*1024*1024)));return True
    if endpoint=='/api/engine/resource-studies/preview':
        from .resource_study import compose
        from .validation_http import manager
        if query:raise ValueError('RESOURCE_STUDY_QUERY')
        body=owner.body(h,limit=2*1024*1024);request=compose(h.contract,body)
        h.send_json(dict(request=request,plan=manager(owner).preview(h.contract,request)));return True
    cost=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/cost-reference(?:/([0-9a-f-]{36})/(cancel|resume))?',endpoint)
    if cost:
        from . import cost_reference as cr
        import live_server
        record=owner.get_record(h.contract,cost[1]);body=owner.body(h,limit=65536)
        with cr.LOCK:
            if query:raise ValueError('COST_REFERENCE_QUERY')
            if cost[3]!='cancel' and (live_server.MAINTENANCE or source_snapshot()!=owner.loaded_sources):raise ValueError('COST_REFERENCE_MAINTENANCE_OR_SOURCE_CHANGED')
            if cost[2]:
                if body:raise ValueError('COST_REFERENCE_ACTION_BODY')
                result=(cr.cancel if cost[3]=='cancel' else cr.resume)(record,cost[2])
            else:result=cr.submit(record,body)
        h.send_json(result);return True
    grid=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/grid-comparison',endpoint)
    if grid:
        from . import grid_comparison as gc
        import live_server
        record=owner.get_record(h.contract,grid[1]);body=owner.body(h,limit=65536)
        with gc.LOCK:
            if query or live_server.MAINTENANCE or source_snapshot()!=owner.loaded_sources:raise ValueError('GRID_MAINTENANCE_OR_QUERY')
            result=gc.submit(record,body)
        h.send_json(result);return True
    study=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/quality-research',endpoint)
    if study:
        from .quality_research import start_study
        if query:raise ValueError('QUALITY_QUERY')
        body=owner.body(h,limit=65536)
        if not isinstance(body,dict) or set(body)!={'run_ids'} or not isinstance(body['run_ids'],list):raise ValueError('QUALITY_RESEARCH_RUN_IDS')
        h.send_json(start_study(owner.get_record,h.contract,study[1],body['run_ids']));return True
    job=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/quality-jobs(?:/([0-9a-f-]{36})/(cancel|resume))?',endpoint)
    if job:
        from . import quality_jobs as qj
        if query:raise ValueError('QUALITY_QUERY')
        record=owner.get_record(h.contract,job[1]);body=owner.body(h,limit=65536)
        with qj.GUARD:
            import live_server
            if job[3]!='cancel' and (live_server.MAINTENANCE or source_snapshot()!=owner.loaded_sources):raise ValueError('QUALITY_MAINTENANCE_OR_SOURCE_CHANGED')
            if job[2]:
                if body:raise ValueError('QUALITY_JOB_ACTION_BODY')
                result=(qj.cancel if job[3]=='cancel' else qj.resume)(record,job[2])
            else:result=qj.submit(record,body)
        h.send_json(result);return True
    quality=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/quality-workflow',endpoint)
    if quality:
        from .quality_jobs import submit,GUARD
        if query:raise ValueError('QUALITY_QUERY')
        record=owner.get_record(h.contract,quality[1])
        body=owner.body(h,limit=65536)
        with GUARD:
            import live_server
            if live_server.MAINTENANCE or source_snapshot()!=owner.loaded_sources:raise ValueError('QUALITY_MAINTENANCE_OR_SOURCE_CHANGED')
            result=submit(record,body)
        h.send_json(result);return True
    from .research_models import post as research_post
    if research_post(owner,h,endpoint,query):return True
    from .validation_http import post as validation_post
    if validation_post(owner,h,endpoint,query):return True
    if endpoint=='/api/engine/quick-preset':
        from .research_diagnostics import quick_preset
        obj=owner.body(h,limit=2*1024*1024)
        if set(obj)!={'request','size'}:raise ValueError('QUICK_PRESET_FIELDS')
        h.send_json(quick_preset(h.contract,obj['request'],obj['size']));return True
    diagnostic=re.fullmatch(r'/api/engine/runs/([0-9a-f-]{36})/diagnostics',endpoint)
    if diagnostic:
        from .research_diagnostics import analyze
        h.send_json(analyze(owner.get_record(h.contract,diagnostic[1]),owner.body(h)));return True
    if endpoint=='/api/engine/compare':
        obj=owner.body(h,limit=2*1024*1024)
        if set(obj)!={'left','right'}:raise ValueError('COMPARE_FIELDS: left and right required')
        a,b=obj['left'],obj['right']
        if a.get('experiment_contract_id')!=h.contract:raise ValueError('COMPARE_CONTRACT: left must match route')
        h.send_json(compare(owner.get_record(a['experiment_contract_id'],a['run_id']),owner.get_record(b['experiment_contract_id'],b['run_id'])));return True
    if endpoint=='/api/engine/diff':
        obj=owner.body(h,limit=2*1024*1024)
        if set(obj)!={'parent_run_id','request'}:raise ValueError('DIFF_FIELDS: parent_run_id and request required')
        old=owner.get_record(h.contract,obj['parent_run_id']);req=request_body(obj['request'])
        if req.get('source_run_id'):req=restore_copy_numbers(owner.get_record(h.contract,req['source_run_id']),req)
        cp,opt,_=compile_request(h.contract,req)
        from .saved_initialization import bind
        bind(cp,opt,owner.get_record)
        h.send_json(dict(parent_run_id=old.id,changes=diff(copy_request(old),req),execution_snapshot=execution_snapshot(cp,opt,req)));return True
    if endpoint not in ('/api/engine/validate','/api/engine/runs'):return False
    if query:raise ValueError('POST query not supported')
    obj=request_body(owner.body(h,limit=2*1024*1024))
    if obj.get('source_run_id'):obj=restore_copy_numbers(owner.get_record(h.contract,obj['source_run_id']),obj)
    # A retry identifies an already accepted immutable job, not a new problem
    # under today's defaults. Resolve it before any Model compilation.
    request_id=h.headers.get('X-Request-ID');expected=h.headers.get('X-Execution-SHA256')
    if endpoint.endswith('runs'):
        if not request_id or not expected:raise ValueError('CONFIRMED_CONFIGURATION_REQUIRED: X-Request-ID and X-Execution-SHA256')
        if owner.service.request_receipt(h.contract,request_id):
            session=owner.service.lookup_request(h.contract,request_id);saved=session.packet(include_rows=False)
            if saved.get('submitted_request')!=obj or (saved.get('execution_snapshot') or {}).get('execution_sha256')!=expected:
                raise ValueError('REQUEST_CONFLICT: request ID already used for another confirmed configuration')
            h.send_json(dict(run_id=session.id,id=session.id,state=session.state,deduplicated=True,request_id=request_id,execution_snapshot=saved['execution_snapshot']),200);return True
    cp,opt,summary=compile_request(h.contract,obj)
    from .saved_initialization import bind
    bind(cp,opt,owner.get_record)
    snapshot=execution_snapshot(cp,opt,obj)
    if endpoint.endswith('validate'):
        problem=cp.view_problem()
        if h.contract!='HMSP-2D-V1':
            problem.setdefault('map_metres',cp.config.get('map_km',20)*1000)
        response=dict(valid=True,summary=summary,problem=problem,execution_snapshot=snapshot,execution_sha256=snapshot['execution_sha256'],execution_supported=True)
        if snapshot['solver']['policy']=='generic_v1':
            from .execution_resources import plan
            response['resource_plan']=plan(cp,snapshot['optimizer'],owner.service.store.root)
        if obj.get('source_run_id'):
            response['configuration_changes']=dict(parent_run_id=obj['source_run_id'],changes=diff(copy_request(owner.get_record(h.contract,obj['source_run_id'])),obj))
        h.send_json(response);return True
    if expected!=snapshot['execution_sha256']:raise ValueError('STALE_CONFIGURATION: validate and review current execution snapshot')
    if owner.busy():raise ValueError('Program research active')
    import live_server
    if live_server.MAINTENANCE:raise ValueError('Program maintenance in progress')
    if source_snapshot()!=owner.loaded_sources:raise ValueError('Shared source changed; restart server before submitting')
    session=owner.service.create(cp,opt,request_id,execution_snapshot=snapshot,submitted_request=obj)
    h.send_json(dict(run_id=session.id,id=session.id,state=session.state,summary=summary,request_id=request_id,execution_snapshot=snapshot),202);return True
