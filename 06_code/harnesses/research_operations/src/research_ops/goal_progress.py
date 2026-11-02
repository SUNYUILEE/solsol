"""Evidence-bound goal checkpoints inside the existing research harness.

This is a progress ledger, never an executor or a scientific approval shortcut.
"""
from pathlib import Path
from . import core

def descriptor(root,path):
    target=core.resolve_workspace_path(root,path)
    data=core.read_ordinary_bytes(target,label=path)
    return dict(path=path,bytes=len(data),sha256=core.sha256_bytes(data))

def load_plan(root,path):
    plan=core.load_json(core.resolve_workspace_path(root,path))
    if plan.get('schema')!='RESEARCH_GOAL_PLAN_V1' or not isinstance(plan.get('milestones'),list) or not plan['milestones']:
        raise core.OpsError('Invalid goal plan')
    if not isinstance(plan.get('frozen_inputs'),list) or not plan['frozen_inputs']:
        raise core.OpsError('Goal domain plan and policies must be frozen by exact descriptors')
    for item in plan['frozen_inputs']:
        if not isinstance(item,dict) or descriptor(root,item.get('path'))!=item:raise core.OpsError('Changed goal input; register reviewed successor plan')
    known=set()
    for item in plan['milestones']:
        if not isinstance(item.get('id'),str) or item['id'] in known or not isinstance(item.get('acceptance'),str) or not item['acceptance']:
            raise core.OpsError('Invalid milestone identity/acceptance')
        if not isinstance(item.get('dependencies'),list) or any(d not in known for d in item['dependencies']):
            raise core.OpsError('Dependencies must refer to earlier milestones')
        known.add(item['id'])
    return plan

def inspect_report(root,path,role,task_id,milestone,plan_sha):
    report=core.load_json(core.resolve_workspace_path(root,path))
    if report.get('task_id')!=task_id or report.get('milestone')!=milestone or report.get('role_id')!=role or report.get('plan_sha256')!=plan_sha:
        raise core.OpsError('Report task/milestone/role/plan mismatch')
    if report.get('status') not in ('PASS','FAIL') or not isinstance(report.get('agent_id'),str) or not report['agent_id'].strip():
        raise core.OpsError('Report decision or author missing')
    evidence=report.get('evidence')
    if not isinstance(evidence,list) or not evidence:raise core.OpsError('Evidence required')
    for item in evidence:
        if not isinstance(item,dict) or descriptor(root,item.get('path'))!=item:raise core.OpsError('Stale or malformed report evidence')
    return report

def inspect_decision(root,event,plan_sha):
    for key in ('verification','review'):
        if descriptor(root,event[key]['path'])!=event[key]:raise core.OpsError('Changed checkpoint report')
    v=inspect_report(root,event['verification']['path'],'R04',event['task_id'],event['milestone'],plan_sha)
    r=inspect_report(root,event['review']['path'],'R06',event['task_id'],event['milestone'],plan_sha)
    if v['agent_id']==r['agent_id'] or r.get('reviewed_verification_sha256')!=event['verification']['sha256']:
        raise core.OpsError('Independent exact verification review required')
    if 'correction' in event:
        if descriptor(root,event['correction']['path'])!=event['correction']:raise core.OpsError('Changed correction decision')
        c=core.load_json(core.resolve_workspace_path(root,event['correction']['path']))
        if c.get('previous_verification_sha256')!=event.get('previous_verification_sha256') or not c.get('material_change') or not c.get('negative_test_evidence'):
            raise core.OpsError('Invalid correction binding')
        for item in c['negative_test_evidence']:
            if descriptor(root,item['path'])!=item:raise core.OpsError('Changed correction negative evidence')
    return 'PASS' if v['status']==r['status']=='PASS' else 'FAIL'

def ledger_path(root,plan):
    goal_id=plan.get('goal_id')
    import re
    if not isinstance(goal_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',goal_id):raise core.OpsError('Unsafe goal ID')
    return root/core.OPS_DIR/'goals'/(goal_id+'.jsonl')

def status(root,plan_path):
    plan=load_plan(root,plan_path);pin=descriptor(root,plan_path)
    events=core.read_jsonl(ledger_path(root,plan));states={};notes={}
    for event in events:
        if event.get('plan')!=pin:raise core.OpsError('Goal plan changed; use a versioned successor goal')
        try:states[event['milestone']]=inspect_decision(root,event,pin['sha256'])
        except core.OpsError as exc:states[event['milestone']]='STALE';notes[event['milestone']]=str(exc)
    items=[]
    for item in plan['milestones']:
        state=states.get(item['id'],'PENDING')
        unmet=[d for d in item['dependencies'] if states.get(d)!='PASS']
        # A descendant cannot remain passed if upstream evidence has gone stale.
        if unmet and state=='PASS':state='STALE';states[item['id']]=state
        if state=='PENDING' and not unmet:state='READY'
        items.append(dict(id=item['id'],status=state,unmet_dependencies=unmet,note=notes.get(item['id'],''),acceptance=item['acceptance']))
    return dict(schema='RESEARCH_GOAL_PROGRESS_V1',goal_id=plan['goal_id'],plan=pin,status='COMPLETE' if all(i['status']=='PASS' for i in items) else 'ACTIVE',milestones=items,next_safe_actions=[i['id'] for i in items if i['status']=='READY'],correction_required=[i['id'] for i in items if i['status'] in ('FAIL','STALE')],scientific_approval=False)

def checkpoint(root,plan_path,task_id,milestone,verification,review,correction=None):
    if core.preflight(root,task_id,persist=False)['status']!='PASS':raise core.OpsError('Task preflight required')
    progress=status(root,plan_path);plan=load_plan(root,plan_path)
    item=next((i for i in progress['milestones'] if i['id']==milestone),None)
    if item is None or item['unmet_dependencies']:raise core.OpsError('Unknown milestone or unmet dependency')
    event=dict(schema='RESEARCH_GOAL_CHECKPOINT_V1',task_id=task_id,milestone=milestone,plan=progress['plan'],verification=descriptor(root,verification),review=descriptor(root,review),created_at=core.utc_now())
    outcome=inspect_decision(root,event,progress['plan']['sha256']);event['outcome']=outcome
    previous_events=core.read_jsonl(ledger_path(root,plan))
    prior=[e for e in previous_events if e['milestone']==milestone]
    if prior:
        last=prior[-1]
        if last['verification']==event['verification'] and last['review']==event['review']:raise core.OpsError('Identical checkpoint repetition forbidden')
        if not correction:raise core.OpsError('Changed attempt requires recorded correction')
        event['correction']=descriptor(root,correction)
        event['previous_verification_sha256']=last['verification']['sha256']
        c=core.load_json(core.resolve_workspace_path(root,correction))
        if c.get('previous_verification_sha256')!=last['verification']['sha256'] or not c.get('material_change') or not c.get('negative_test_evidence'):
            raise core.OpsError('Correction must bind prior failure, material change and negative test')
        for evidence in c['negative_test_evidence']:
            if descriptor(root,evidence['path'])!=evidence:raise core.OpsError('Correction evidence stale')
    path=ledger_path(root,plan);path.parent.mkdir(parents=True,exist_ok=True)
    import json
    # Call serially through the harness; exclusive lock fails rather than races.
    lock=path.with_suffix('.lock')
    acquired=False
    try:
        with lock.open('x'):
            acquired=True
            if core.read_jsonl(path)!=previous_events:raise core.OpsError('Ledger changed')
            with path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(event,ensure_ascii=False)+'\n');stream.flush()
                import os
                os.fsync(stream.fileno())
    except FileExistsError:raise core.OpsError('Goal ledger locked; inspect owner before retry')
    finally:
        if acquired:lock.unlink(missing_ok=True)
    core.record_event(root,task_id,'RESULT','GOAL_CHECKPOINT',[plan_path,verification,review],milestone+': '+outcome+'; no automatic scientific promotion')
    return status(root,plan_path)
