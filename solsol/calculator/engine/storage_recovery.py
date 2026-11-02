"""Explicit calculator-owned recovery of a pinned terminal commit; no optimizer replay."""
import contextlib,hashlib,json,re,threading
from .runtime import RunSession,StoredSession,ACTIVE
from .store import COMMIT_INTENT,digest

def _folder(service,cid,rid):
    target=service.store.folder(cid,rid).resolve();target.relative_to(service.store.root.resolve())
    actual=service._saved_folder(cid,rid)
    if actual is None:raise KeyError('STORAGE_RUN_NOT_FOUND')
    if actual.resolve()!=target:raise ValueError('STORAGE_RECOVERY_READ_ONLY_ROOT')
    if not (target/'manifest.json').exists():
        copies=[s.folder(cid,rid).resolve() for s in service.read_stores if s.folder(cid,rid).is_dir()]
        if any(p!=target for p in copies):raise ValueError('STORAGE_RECOVERY_MULTIPLE_ROOTS: 동일 미완료 기록이 여러 저장 경로에 있습니다. 원본 경로를 먼저 구분하세요.')
    return target

def _intent(folder,cid,rid):
    data=(folder/'terminal-intent.json').read_bytes();p=json.loads(data.decode('utf8'));m=p.get('manifest',{})
    if p.get('schema')!=COMMIT_INTENT or p.get('sha256')!=digest({k:v for k,v in p.items() if k!='sha256'}):raise ValueError('STORAGE_RECOVERY_INTENT_INTEGRITY')
    if m.get('experiment_contract_id')!=cid or m.get('run_id')!=rid:raise ValueError('STORAGE_RECOVERY_IDENTITY')
    return p,hashlib.sha256(data).hexdigest()

def inspect_recovery(service,cid,rid):
    base=dict(run_id=rid,experiment_contract_id=cid,automatic_recovery=False)
    with service.lock:session=service.sessions.get(rid)
    if session is not None and session.cid!=cid:raise KeyError('Run not found in contract')
    if session is not None and session.state in ACTIVE:return dict(base,status='ACTIVE',can_recover=False,reason='계산·재평가·저장 중입니다. 종료될 때까지 기다리세요.')
    folder=_folder(service,cid,rid)
    if (folder/'manifest.json').exists():return dict(base,status='COMMIT_PRESENT',can_recover=False,reason='저장 완료 표식이 있습니다. 결과를 열 때 원시와 표식을 검증합니다.')
    if not (folder/'terminal-intent.json').exists():return dict(base,status='NO_COMMIT_INTENT',can_recover=False,reason='복구에 필요한 저장 의도 기록이 없습니다. 기존 기록은 보존하며 자동 복구하지 않습니다.')
    _,pin=_intent(folder,cid,rid)
    return dict(base,status='PINNED_INTENT_AVAILABLE',can_recover=True,expected_intent_sha256=pin,reason='저장 의도 기록을 찾았습니다. 원시와 checkpoint를 검증한 뒤 저장 완료 표식만 복원할 수 있습니다. 검사 실패 시 원시는 유지됩니다.',integrity_status='RAW_NOT_YET_VERIFIED')

def recover(service,cid,rid,expected_intent_sha256):
    if not isinstance(expected_intent_sha256,str) or not re.fullmatch('[0-9a-f]{64}',expected_intent_sha256):raise ValueError('STORAGE_RECOVERY_PIN_REQUIRED')
    folder=_folder(service,cid,rid)
    with service.lock:
        session=service.sessions.get(rid)
        if session is not None and session.cid!=cid:raise KeyError('Run not found in contract')
        if session is not None and session.state in ACTIVE:raise ValueError('STORAGE_RECOVERY_ACTIVE_RUN')
        loading=service._loading_locks.setdefault((cid,rid),threading.Lock())
    with loading:
        with service.lock:session=service.sessions.get(rid)
        if session is not None and session.cid!=cid:raise KeyError('Run not found in contract')
        # Same ordering as get(): per-run load lock before the short service lock.
        with session.lock if session is not None else contextlib.nullcontext():
            if session is not None and session.state in ACTIVE:raise ValueError('STORAGE_RECOVERY_ACTIVE_RUN')
            _,actual_pin=_intent(folder,cid,rid)
            if actual_pin!=expected_intent_sha256:raise ValueError('STORAGE_RECOVERY_STALE_INTENT')
            result=service.store.recover_terminal(folder,expected_intent_sha256)
            packet=service.store.read(folder)
            if packet['run_id']!=rid or packet['experiment_contract_id']!=cid:raise ValueError('STORAGE_RECOVERY_IDENTITY')
            restored=StoredSession(packet,folder)
            with service.lock:
                service.sessions[rid]=restored;service.read_errors.pop((cid,rid),None)
    return dict(result,run_id=rid,experiment_contract_id=cid,state=restored.state,evaluations=len(restored.rows),checkpoint_evaluations=restored.checkpoints[-1]['nfe'] if restored.checkpoints else None,raw_unchanged=True,optimizer_restarted=False)
