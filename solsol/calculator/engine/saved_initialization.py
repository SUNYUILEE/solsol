"""Resolve a saved, ranked placement. Never accept a client-supplied X or F/G."""
import copy
import re
import numpy as np
from .store import digest, sha


def validate_reference(value):
    if not isinstance(value,dict) or set(value)!={'run_id','row_id','raw_sha256','X_sha256','sort','targets'}:
        raise ValueError('저장 초기 배치를 다시 선택하세요.')
    if not isinstance(value['run_id'],str) or not re.fullmatch(r'[0-9a-f-]{36}',value['run_id']):
        raise ValueError('저장 실행 번호가 올바르지 않습니다.')
    if type(value['row_id']) is not int or value['row_id']<0 or type(value['targets']) is not bool or not isinstance(value['sort'],str):
        raise ValueError('저장 초기 배치의 순위 조건이 올바르지 않습니다.')
    for key in ('raw_sha256','X_sha256'):
        if not isinstance(value[key],str) or not re.fullmatch(r'[0-9a-f]{64}',value[key]):raise ValueError('저장 배치 근거가 없습니다. 다시 선택하세요.')


def first(record, priority='cost', targets=False):
    from .runtime import TERMINAL
    from .hard_constraints import reports
    from .subset_fidelity import finite_evaluation
    if record.state not in TERMINAL or not (record.folder/'raw.json').is_file():
        raise ValueError('저장이 끝난 실행에서 초기 배치를 선택하세요.')
    with record.lock:
        # First rank is lexicographic, with lowest raw ID breaking the first
        # exact tie. Hamming groups and subset fidelity cannot change this rank.
        # Avoid constructing all groups and quality matrices for one seed.
        research=record.config.get('_research') or record.frozen_problem.get('research_configuration')
        if not research:raise ValueError('Observed placement browser requires configurable run')
        metrics={m['id']:m for m in research['metadata']['metrics']}
        performance=[i for i in research['objective_ids'] if i!='cost']
        if not performance:raise ValueError('No active performance objective')
        if priority in ('cost','raw'):priority=performance[0]
        if priority not in performance:raise ValueError('Performance priority must be an active performance objective')
        if targets and (research['goals'] is None or not research['metadata']['coverage_metrics']):raise ValueError('Area targets not configured')
        order=[priority]+[i for i in performance if i!=priority]
        checks=reports(record);tolerance=record.archive_policy['tolerance'] if hasattr(record,'archive_policy') else record.data['archive_policy']['tolerance']
        unique={}
        for i in sorted(record.checkpoints[-1]['archive_ids']):
            r=record.rows[i]
            if checks[i]['hard_pass'] and finite_evaluation(r,tolerance):unique.setdefault(tuple(map(tuple,r['X'])),i)
        ids=[i for i in unique.values() if not targets or record.rows[i]['qualified'] is True]
        if not ids:raise ValueError('선택한 조건의 저장 비지배 배치가 없습니다. 목표 통과 필터를 확인하세요.')
        def key(i):return tuple((-1 if metrics[m]['direction']=='maximize' else 1)*record.rows[i]['named_metrics'][m] for m in order)+(i,)
        if any(not np.isfinite(key(i)).all() for i in ids):raise ValueError('Non-finite performance metric')
        row=record.rows[min(ids,key=key)]
        ref=dict(run_id=record.id,row_id=row['id'],raw_sha256=sha(record.folder/'raw.json'),
                 X_sha256=digest(row['X']),sort=order[0],targets=targets)
        return dict(reference=ref,performance_order=order,cost=row['cost'],
                    sensor_counts=row['sensor_counts'],generation=record.checkpoints[-1]['generation'])


def bind(cp, optimizer, get_record):
    if optimizer.get('initializer')!='saved':return
    ref=optimizer.get('saved_seed');validate_reference(ref)
    record=get_record(cp.cid,ref['run_id'])
    selected=first(record,ref['sort'],ref['targets'])
    if selected['reference']!=ref:raise ValueError('저장 초기 배치의 근거 또는 순위가 달라졌습니다. 다시 선택하세요.')
    # Identity is immutable in a terminal run; no population/history copy.
    registry=record.compilation['registry'] if hasattr(record,'compilation') else record.data['registry']
    # Geometry and sensor identity must match, even when dimensions coincide.
    if (list(cp.candidate_order)!=list(registry['candidate_order']) or list(cp.sensor_order)!=list(registry['sensor_order'])
            or not np.array_equal(np.asarray(cp.bundle.sites),np.asarray(record.frozen_problem['sites']))):
        raise ValueError('저장 배치를 사용하려면 후보지 좌표·순서와 센서 종류를 유지하세요.')
    x=np.asarray(record.rows[ref['row_id']]['X'])
    cp.space.validate(x,installation=True)
    from .initialization import resource_bounds
    lower,upper=resource_bounds(cp.space,getattr(cp.bundle,'inventory_rule',None))
    if np.any(x.sum(axis=0)<lower) or np.any(x.sum(axis=0)>upper):
        raise ValueError('저장 배치가 새 센서 수량 조건과 맞지 않습니다. 수량 조건을 유지하거나 다른 초기화 방법을 선택하세요.')
    cp.saved_initialization=dict(**copy.deepcopy(selected),X=x.astype(int).tolist())
