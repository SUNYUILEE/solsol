"""Read-only persisted progress. Never certifies raw results or worker liveness."""
import hashlib
import json
import time
import uuid
from pathlib import Path

FIELDS=('job_id','status','phase','method','scope','source_count','evaluated',
        'attempted','elapsed_seconds','total','total_upper_bound','witness_count',
        'scope_complete','refinement_round','error')

def find_folder(service,cid,run_id):
    if str(uuid.UUID(run_id))!=run_id:raise ValueError('QUALITY_RUN_ID')
    folders={p.resolve() for store in service.read_stores if (p:=store.folder(cid,run_id)).is_dir()}
    if not folders:raise KeyError('Run not found in contract')
    if len(folders)!=1:raise ValueError('QUALITY_PROGRESS_AMBIGUOUS_ROOT: use full integrity-checked lookup')
    return folders.pop()

def snapshot(folder,job_id):
    folder=Path(folder)
    if str(uuid.UUID(job_id))!=job_id:raise ValueError('QUALITY_JOB_ID')
    path=folder/'quality_jobs'/job_id/'state.json'
    # Atomic publication makes this a single version; no shared writer lock.
    with path.open('rb') as handle:
        data=handle.read()
    envelope=json.loads(data)
    state=envelope['payload']
    actual=hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if envelope['sha256']!=actual:raise ValueError('QUALITY_JOB_INTEGRITY')
    parent=state['parent']
    if state['job_id']!=job_id or parent['run_id']!=folder.name or parent['experiment_contract_id']!=folder.parent.name:
        raise ValueError('QUALITY_PROGRESS_IDENTITY')
    result={key:state[key] for key in FIELDS if key in state}
    refinement=state.get('refinement',{})
    result['refinement']={key:refinement[key] for key in ('current_source_count','delete_completed','local_completed','accepted_steps') if key in refinement}
    result.update(schema='SOLSOL_PERSISTED_QUALITY_PROGRESS_V1',parent=parent,
        observation=dict(kind='PERSISTED_SNAPSHOT',observed_at=time.time(),
                         state_sha256=actual,state_bytes=len(data),
                         raw_integrity='NOT_RECHECKED',worker_liveness='UNKNOWN',
                         results_certified=False),
        meaning='저장된 진행 기록입니다. 현재 worker 실행 여부와 원시 결과 무결성은 이 조회로 확인하지 않습니다.')
    return result

def listing(folder):
    return dict(schema='SOLSOL_PERSISTED_QUALITY_PROGRESS_LIST_V1',
                jobs=[snapshot(folder,p.parent.name) for p in sorted((Path(folder)/'quality_jobs').glob('*/state.json'))],
                results_certified=False)
