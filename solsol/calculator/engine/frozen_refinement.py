"""Iterative placement improvement inside the calculator's persistent quality jobs.

Every source is visited. Accepted placements become the next search centre;
all evaluations stay diagnostic evidence, never overwritten optimizer rows.
"""
import itertools
import time
import numpy as np

BATCH_SIZE = 256  # Transport/checkpoint batch; never a search budget.


def collect_front(record, state, sources, event):
    """Separate derived archive of all feasible observed rows, with native refs."""
    from .quality_jobs import stored_entries, location
    from .archive import _select_validated
    from .store import atomic_json, digest, sha
    front, pending, seen = [], [], {}
    serial = 0
    def append(row, reference):
        nonlocal serial
        key = np.asarray(row['X'], np.uint8).tobytes()
        if key in seen:
            if seen[key] != (row['F'], row['G'], row['cost']):
                raise ValueError('REFINEMENT_CONFLICTING_EVALUATION')
            return
        seen[key] = (row['F'], row['G'], row['cost'])
        pending.append(dict(row, id=serial, reference=reference))
        serial += 1
    def flush():
        nonlocal front
        candidates = front + pending
        keep = set(_select_validated(candidates, 'cost', 'general', nds_method='efficient_non_dominated_sort'))
        front = [r for r in candidates if r['id'] in keep]
        pending.clear()
    for source in sources:
        if not all(g <= state['tolerance'] for g in source['G']):
            raise ValueError('REFINEMENT_INFEASIBLE_SOURCE')
        append(source, dict(kind='raw', run_id=record.id, raw_id=source['id']))
    flush()
    for row in stored_entries(record, state):
        if event.is_set():
            state.update(status='STOPPED', phase='누적 개선집합 정리 중지 · 재개 가능', scope_complete=False)
            return
        if row['feasible'] and (state['scope'] != 'qualified' or row.get('qualified') is True):
            append(row, dict(kind='diagnostic', job_id=state['job_id'], sequence=row['sequence']))
        if len(pending) >= 256:
            flush()
    flush()
    front.sort(key=lambda r: (r['cost'], *r['F'], r['id']))
    for row in front:
        row.pop('id', None)
    payload = dict(schema='SOLSOL_FROZEN_DERIVED_FRONT_V1', parent=state['parent'],
        job_id=state['job_id'], evaluated=state['evaluated'], source_count=len(sources),
        unique_observed_X=len(seen), rows=front,
        provenance='DERIVED_OBSERVED_FRONT_WITH_SOURCE_REFERENCES')
    path = location(record, state['job_id']).parent / 'front.json'
    atomic_json(path, dict(payload=payload, sha256=digest(payload)))
    state['derived_front'] = dict(count=len(front), sha256=sha(path),
        unique_observed_X=len(seen), path='front.json')
    return front


def run(record, state, event, cp, originals, checkpoint):
    from .quality_jobs import location, unpacked
    from .store import digest, atomic_json, sha
    root = location(record, state['job_id']).parent
    state.setdefault('refinement_round', 0)
    state.setdefault('settled_X', [])
    while not event.is_set():
        round_number = state['refinement_round']
        sources = originals
        if round_number:
            path = root / ('round-' + str(round_number) + '.json')
            if sha(path) != state['round_sources_sha256']:
                raise ValueError('REFINEMENT_ROUND_INTEGRITY')
            sources = unpacked(path.read_text(encoding='utf8'))
        execute(record, state, event, cp, sources, checkpoint)
        if state['status'] != 'COMPLETED':
            return
        state.update(status='RUNNING', phase='전체 관측 개선집합 정리', scope_complete=False)
        checkpoint()
        front = collect_front(record, state, originals, event)
        if front is None:
            return
        settled = set(state['settled_X'])
        pending = [r for r in front if digest(r['X']) not in settled]
        state['front_unchecked_count'] = len(pending)
        if not pending:
            state.update(status='COMPLETED', phase='전체 개선 해집합의 단일 변경 탐색 완료',
                         scope_complete=True, total=state['evaluated'])
            return
        # Include every newly surviving alternative. A population-size selection
        # is never used to substitute for full derived-front coverage.
        for row in pending:
            row['id'] = row['reference'].get('raw_id', row.get('source_id'))
            if row['id'] not in state['source_ids']:
                raise ValueError('REFINEMENT_ROUND_SOURCE_BINDING')
        round_number += 1
        path = root / ('round-' + str(round_number) + '.json')
        atomic_json(path, dict(payload=pending, sha256=digest(pending)))
        state.setdefault('completed_rounds', []).append(dict(
            round=state['refinement_round'], source_count=len(sources),
            accepted_steps=state['refinement']['accepted_steps'], front_count=len(front),
            next_source_count=len(pending)))
        state.update(refinement_round=round_number, round_sources_sha256=sha(path))
        state.pop('refinement', None)
        checkpoint()
    state.update(status='STOPPED', phase='반복 개선 저장 · 이어서 가능', scope_complete=False)


def front_page(record, state, offset):
    from .quality_jobs import location, unpacked
    from .store import sha
    if state['status'] != 'COMPLETED' or not state.get('derived_front'):
        raise ValueError('REFINEMENT_FRONT_NOT_READY')
    path = location(record, state['job_id']).parent / 'front.json'
    if sha(path) != state['derived_front']['sha256']:
        raise ValueError('REFINEMENT_FRONT_INTEGRITY')
    payload = unpacked(path.read_text(encoding='utf8'))
    if payload['parent'] != state['parent'] or payload['job_id'] != state['job_id']:
        raise ValueError('REFINEMENT_FRONT_BINDING')
    return dict(job_id=state['job_id'], total=len(payload['rows']), offset=offset,
                rows=payload['rows'][offset:offset + 100])


def dominates(candidate, source, tolerance):
    # No accumulation of tolerance-sized regressions along a long chain.
    a, b = np.asarray(candidate['F']), np.asarray(source['F'])
    return bool(np.all(a <= b) and np.any(a < b - tolerance))


def vectors(cp, row, phase):
    from .quality_jobs import local_vectors
    if phase == 'delete':
        x = np.asarray(row['X'], np.uint8)
        for site, sensor in np.argwhere(x):
            y = x.copy()
            y[site, sensor] = 0
            yield row, 'one_delete', y
    else:
        yield from local_vectors(cp, row)


def execute(record, state, event, cp, sources, checkpoint):
    from .quality_jobs import save, stored_entries, resource_feasible
    from .quality_values import finite_fg
    tol = state['tolerance']
    cursor = state.setdefault('refinement', dict(
        phase='replay', source_index=0, offset=0, accepted_steps=0,
        current_source_count=len(sources),
        delete_completed=0, local_completed=0, leaves={}, improved_source_ids=[],
        selection='first improving batch, minimum cost then lexicographic F; all alternatives retained',
        method='iterated strict Pareto descent: delete sweep, then delete/add/same-type relocation'))
    # Only accepted centres are needed to resume. Their sequence references are
    # checked against immutable evidence, not trusted as arbitrary input X.
    selected = set(cursor['leaves'].values())
    if cursor.get('centre_sequence') is not None:
        selected.add(cursor['centre_sequence'])
    known = {}
    for row in stored_entries(record, state):
        if row['sequence'] in selected:
            if not row['feasible']:
                raise ValueError('REFINEMENT_INVALID_CENTRE')
            known[row['sequence']] = row
    if selected - known.keys():
        raise ValueError('REFINEMENT_MISSING_CENTRE')
    for index, sequence in cursor['leaves'].items():
        if known[sequence]['source_id'] != sources[int(index)]['id']:
            raise ValueError('REFINEMENT_CENTRE_LINEAGE')
    if cursor.get('centre_sequence') is not None:
        if known[cursor['centre_sequence']]['source_id'] != sources[cursor['source_index']]['id']:
            raise ValueError('REFINEMENT_CURRENT_LINEAGE')

    def evaluate(batch, root, centre):
        state['attempted'] += len(batch)
        checkpoint()
        evaluated = cp.evaluate_physical([x for _, _, x in batch], validate_installation=True)
        if len(evaluated) != len(batch):
            raise ValueError('REFINEMENT_BATCH_LENGTH')
        entries = []
        for (source, operation, x), row in zip(batch, evaluated):
            if not finite_fg(row) or not np.array_equal(np.asarray(row['X']), x):
                raise ValueError('REFINEMENT_EVALUATION_BINDING')
            feasible = all(g <= tol for g in row['G']) and resource_feasible(cp, x)
            if operation == 'replay':
                if not (np.allclose(row['F'], source['F'], rtol=0, atol=tol)
                        and np.allclose(row['G'], source['G'], rtol=0, atol=tol)
                        and row['cost'] == source['cost']):
                    raise ValueError('REFINEMENT_REPLAY_MISMATCH')
                improved = []
            else:
                original = record.rows[root['id']]
                improved = [root['id']] if (feasible and
                    (state['scope'] != 'qualified' or row.get('qualified') is True)
                    and dominates(row, original, tol)) else []
            item = dict(row, source_id=source['id'] if operation == 'replay' else root['id'],
                operation=operation, feasible=bool(feasible), improved_for=improved,
                parent_sequence=cursor.get('centre_sequence'),
                provenance=state['provenance'], sequence=state['next_eval'] + len(entries))
            entries.append(item)
        return entries

    def commit(entries):
        state['next_eval'] += len(entries)
        state['evaluated'] += len(entries)
        state['witness_count'] += sum(bool(r['improved_for']) for r in entries)
        save(record, state, [(r['sequence'], r) for r in entries])

    while not event.is_set():
        if cursor['phase'] == 'replay':
            start = cursor['source_index']
            batch_sources = sources[start:start + BATCH_SIZE]
            if not batch_sources:
                cursor.update(phase='delete', source_index=0, offset=0)
                checkpoint()
                continue
            entries = evaluate([(s, 'replay', np.asarray(s['X'], np.uint8)) for s in batch_sources], None, None)
            if any(not r['feasible'] for r in entries):
                raise ValueError('REFINEMENT_INFEASIBLE_SOURCE')
            cursor['source_index'] += len(batch_sources)
            commit(entries)
            continue
        index = cursor['source_index']
        if index == len(sources):
            if cursor['phase'] == 'delete':
                cursor.update(phase='local', source_index=0, offset=0)
                checkpoint()
                continue
            state.update(status='COMPLETED', phase='전체 배치 반복 개선 완료',
                         scope_complete=True, total=state['evaluated'])
            return
        root = sources[index]
        seq = cursor.get('centre_sequence', cursor['leaves'].get(str(index)))
        centre = known[seq] if seq is not None else root
        cursor['centre_sequence'] = seq
        state['phase'] = ('전체 해 비용 절감' if cursor['phase'] == 'delete' else '개선 배치에서 삭제·추가·이동 탐색')
        batch = list(itertools.islice(vectors(cp, centre, cursor['phase']), cursor['offset'], cursor['offset'] + BATCH_SIZE))
        if not batch:
            if cursor['phase'] == 'local':
                from .store import digest
                key = digest(centre['X'])
                if key not in state['settled_X']:
                    state['settled_X'].append(key)
            cursor[cursor['phase'] + '_completed'] += 1
            cursor.update(source_index=index + 1, offset=0)
            cursor.pop('centre_sequence', None)
            checkpoint()
            continue
        entries = evaluate(batch, root, centre)
        improvements = [r for r in entries if r['feasible'] and
            (state['scope'] != 'qualified' or r.get('qualified') is True) and dominates(r, centre, tol)]
        if improvements:
            winner = min(improvements, key=lambda r: (r['cost'], *r['F'], r['sequence']))
            seq = winner['sequence']
            known[seq] = winner
            cursor['leaves'][str(index)] = seq
            cursor.update(centre_sequence=seq, offset=0, accepted_steps=cursor['accepted_steps'] + 1)
            if root['id'] not in cursor['improved_source_ids']:
                cursor['improved_source_ids'].append(root['id'])
        else:
            cursor['offset'] += len(batch)
        commit(entries)
    state.update(status='STOPPED', phase='반복 개선 저장 · 이어서 가능', scope_complete=False)
