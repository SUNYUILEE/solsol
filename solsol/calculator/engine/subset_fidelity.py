"""Read-only fidelity of a selected subset, not unknown-front optimality."""
import math
import hashlib
from pathlib import Path
import numpy as np
from .store import digest, sha
from .comparison_basis import freeze_basis


def finite_evaluation(row, tolerance):
    return all(math.isfinite(v) for v in row['F']) and all(math.isfinite(g) and g <= tolerance for g in row['G'])


def evaluate_subset(rows, reference_ids, selected_ids, objectives, *, source=None):
    rids = sorted(set(reference_ids)); sids = sorted(set(selected_ids))
    if not objectives or len({m['id'] for m in objectives})!=len(objectives) or any(m['direction'] not in ('maximize','minimize') for m in objectives):
        raise ValueError('Subset fidelity requires distinct ordered objectives with explicit directions')
    if not set(sids).issubset(rids):
        raise ValueError('Selected subset is outside its reference')
    if any(not all(math.isfinite(v) for v in rows[i]['F']+rows[i]['G']) for i in rids):
        raise ValueError('Nonfinite evaluation in subset reference')
    out = dict(schema='SOLSOL_SUBSET_FIDELITY_V1', reference_count=len(rids), selected_count=len(sids),
               reference_ids_sha256=digest(rids), selected_ids_sha256=digest(sids),
               reference_kind='FILTERED_UNIQUE_X_BEFORE_SELECTION_AND_PAGING', independent=False,
               source='https://arxiv.org/abs/2006.08156', definition_sha256=sha(Path(__file__)), objective_ids=[m['id'] for m in objectives])
    if not rids or not sids:
        return dict(out, status='EMPTY_REFERENCE' if not rids else 'EMPTY_SELECTION', performance=None, structure=None)
    f = np.asarray([[rows[i]['named_metrics'][m['id']] for m in objectives] for i in rids], float)
    x = np.asarray([rows[i]['X'] for i in rids])
    if not np.isfinite(f).all() or x.ndim != 3 or not np.isin(x, [0, 1]).all():
        raise ValueError('Subset fidelity requires finite metrics and binary candidate/sensor matrices')
    out['reference_values_sha256']=hashlib.sha256(f.astype('<f8').tobytes()+x.astype('uint8').tobytes()).hexdigest()
    directions = np.asarray([-1 if m['direction']=='maximize' else 1 for m in objectives])
    z = f * directions; low = z.min(axis=0); span = z.max(axis=0)-low; active = span > 0
    normalization=dict(version='OBSERVED_RANGE_MINIMIZED_V1',kind='THIS_REFERENCE_OBSERVED_RANGE',minimized_offset=low.tolist(),span=span.tolist(),
        directions=directions.tolist(),active_objective_ids=[m['id'] for m,a in zip(objectives,active) if a],
        constant_objective_ids=[m['id'] for m,a in zip(objectives,active) if not a])
    out['comparison_basis']=freeze_basis('SUBSET_FILTERED_REFERENCE',source,
        dict(ids_sha256=out['reference_ids_sha256'],values_sha256=out['reference_values_sha256'],count=len(rids),
             raw_evaluations_sha256=digest([dict(id=i,F=rows[i]['F'],G=rows[i]['G']) for i in rids]),
             matrix_shape=list(x.shape[1:]),performance_weighting='UNIQUE_OBJECTIVE_VECTORS',structure_weighting='UNIQUE_X'),
        normalization,[{k:m.get(k) for k in ('id','direction','unit')} for m in objectives],out['definition_sha256'])
    z = (z[:,active]-low[active])/span[active]
    indices = {i:k for k,i in enumerate(rids)}; si = [indices[i] for i in sids]
    unique, first = np.unique(z, axis=0, return_index=True)
    selected = z[si]
    nearest = np.zeros(len(unique)); nearest_si = np.zeros(len(unique), dtype=int)
    if rids != sids and active.any():
        for start in range(0, len(unique), 128):
            block = unique[start:start+128]
            best = np.full(len(block), np.inf); at = np.zeros(len(block), dtype=int)
            for j in range(0, len(selected), 128):
                dist = np.linalg.norm(np.maximum(selected[j:j+128][None,:,:]-block[:,None,:], 0), axis=2)
                ix = dist.argmin(axis=1); value = dist[np.arange(len(block)), ix]; improve = value < best
                best[improve] = value[improve]; at[improve] = j+ix[improve]
            nearest[start:start+128] = best; nearest_si[start:start+128] = at
    elif rids == sids:
        nearest_si = first
    worst = int(nearest.argmax()); ri = int(first[worst]); sj = int(nearest_si[worst])
    structure_dist = np.zeros(len(rids), dtype=int)
    packed = np.packbits(x.reshape(len(x),-1).astype(np.uint8),axis=1)
    pop = np.asarray([i.bit_count() for i in range(256)], dtype=np.uint8)
    selected_id_set = set(sids)
    remaining = [k for k,i in enumerate(rids) if i not in selected_id_set]
    for start in range(0,len(remaining),128):
        ix = remaining[start:start+128]; best = np.full(len(ix), x.shape[1]*x.shape[2]+1)
        for j in range(0,len(si),128):
            distances = pop[np.bitwise_xor(packed[ix,None,:], packed[si[j:j+128]][None,:,:])].sum(axis=2)
            best = np.minimum(best, distances.min(axis=1))
        structure_dist[ix] = best
    return dict(out, status='CALCULATED',
        normalization=normalization,
        performance=dict(igd_plus=float(nearest.mean()), worst_distance=float(nearest[worst]),
                         distinct_reference_vectors=len(unique),
                         witness=dict(reference_solution_id=rids[ri], selected_solution_id=sids[sj],
                                      reference_values=f[ri].tolist(), selected_values=f[si[sj]].tolist())),
        structure=dict(exact_included=len(sids), mean_nearest_hamming=float(structure_dist.mean()),
                       max_nearest_hamming=int(structure_dist.max()),
                       worst_reference_solution_id=rids[int(structure_dist.argmax())], bit_count=int(x.shape[1]*x.shape[2])))
