"""Dimension-aware cumulative archive; physical identity and raw observations differ."""
import numpy as np
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting


def archive_ids(rows, identity=None, tolerance=0.0, sort='raw', method='auto'):
    if not rows:
        return []
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError('Invalid feasibility tolerance')
    if method not in ('auto', 'general', 'sweep') or sort not in ('raw', 'cost'):
        raise ValueError('Unknown archive policy')
    keys=('experiment_contract_id','run_id','config_sha256','evaluator_sha256','config_hash','evaluator_hash','objective_order')
    expected={k:rows[0].get(k) for k in keys}
    if identity is not None:
        expected.update(identity)
    first={}; ids=set(); widths=None
    for r in rows:
        if any(r.get(k)!=v for k,v in expected.items()):
            raise ValueError('Mixed archive identity')
        if r.get('provenance')=='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER':
            raise ValueError('Diagnostic row in optimizer archive')
        f=np.asarray(r['F'],float);g=np.asarray(r['G'],float);x=np.asarray(r['X'])
        if f.ndim!=1 or not len(f) or g.ndim!=1 or not np.isfinite(f).all() or not np.isfinite(g).all():
            raise ValueError('Invalid archive objective/constraint vector')
        if x.ndim!=2 or np.any((x!=0)&(x!=1)):
            raise ValueError('Invalid physical decision')
        shape=(len(f),len(g),x.shape)
        if widths is None:widths=shape
        if widths!=shape:raise ValueError('Mixed archive dimensions')
        raw_id=r['id']
        if type(raw_id) is not int or raw_id<0 or raw_id in ids:raise ValueError('Duplicate/invalid raw ID')
        ids.add(raw_id)
        if np.all(g<=tolerance):
            key=r.get('placement_hash') or r.get('decision_sha256') or x.astype(np.uint8).tobytes()
            if key in first:
                old=first[key]
                if old['F']!=r['F'] or old['G']!=r['G'] or not np.array_equal(old['X'],x):
                    raise ValueError('Same placement has inconsistent evaluation')
            else:first[key]=r
    unique=list(first.values())
    return _select_validated(unique, sort, method)


def _select_validated(unique, sort, method, decisions=None, nds_method='fast_non_dominated_sort'):
    """Select only; callers must validate identities and deduplicate placements."""
    if not unique:return []
    f=np.asarray([r['F'] for r in unique])
    if method=='sweep' and f.shape[1]!=3:raise ValueError('Sweep requires three objectives')
    if f.shape[1]==3 and method!='general':
        from live_empirical_archive import cumulative_archive_ids
        keep=cumulative_archive_ids(np.asarray([r['X'] if decisions is None else decisions[r['id']] for r in unique]),f,np.zeros((len(f),0)))
    else:
        keep=NonDominatedSorting(method=nds_method).do(f,only_non_dominated_front=True).tolist()
    selected=[unique[int(i)] for i in keep]
    if sort=='cost':selected.sort(key=lambda r:(r['cost'],*r['F'][:2],r['id']))
    else:selected.sort(key=lambda r:r['id'])
    return [r['id'] for r in selected]


def archive_prefix_ids(rows, stops, tolerance=0.0, sort='raw', return_index=False):
    # Keep small records lightweight; the optional compiler only accelerates
    # immutable large-record prefix selection, never scientific evaluation.
    if len(rows) >= 4096:
        import os,time
        started=time.perf_counter()
        from .archive_lifetimes import archive_prefix_ids as compiled_prefixes
        imported=time.perf_counter()
        if os.environ.get('SOLSOL_COLD_DIAGNOSTICS') == '1':
            import json,sys
            stats={}
            result=compiled_prefixes(rows, stops, tolerance, sort, return_index, stats=stats)
            try:
                event=json.dumps(dict(pid=os.getpid(),rows=len(rows),seconds=time.perf_counter()-started,import_seconds=imported-started,**stats))
                from pathlib import Path
                trace=Path(__file__).resolve().parents[3]/'07_실행/integrated_service/cold_archive.jsonl'
                with trace.open('a',encoding='utf8') as stream:stream.write(event+'\n')
                print('SOLSOL_COLD_ARCHIVE '+event,file=sys.stderr,flush=True)
            except (OSError,ValueError):
                pass  # Diagnostic output cannot invalidate a verified result.
            return result
        return compiled_prefixes(rows, stops, tolerance, sort, return_index)
    return _archive_prefix_ids_reference(rows, stops, tolerance, sort, return_index)


def _archive_prefix_ids_reference(rows, stops, tolerance=0.0, sort='raw', return_index=False):
    """Validate all raw rows once, then independently select each saved prefix.

    This is for immutable stored records: no cross-read cache and no trusted
    manifest shortcut. Duplicate/conflicting rows anywhere still fail validation.
    """
    index=AppendOnlyArchive(tolerance,sort);previous=0;result=[]
    for stop in stops:
        if type(stop) is not int or not previous < stop <= len(rows):
            raise ValueError('Invalid archive prefix range')
        index.extend(rows[previous:stop])
        result.append(index.selected())
        previous=stop
    # Partial final generations are still validated even without a checkpoint.
    index.extend(rows[previous:])
    return (result,index) if return_index else result


class AppendOnlyArchive:
    """Live append-only ledger index; every new row is checked exactly once.

    All feasible placements, including dominated ones, remain in the validation
    map so a later inconsistent repetition can never escape validation.
    """
    def __init__(self,tolerance=0.0,sort='raw'):
        if not np.isfinite(tolerance) or tolerance<0 or sort not in ('raw','cost'):
            raise ValueError('Invalid archive policy')
        self.tolerance=tolerance;self.sort=sort;self.first={};self.ids=set();self.widths=None;self.expected=None;self.decisions={}
        self._front=[];self._pending=[];self._seen_physical=set()

    def extend(self,rows):
        if not rows:return
        # Validate one rectangular batch before narrowing binary decisions.
        # Per-row conversion repeatedly walks the same nested Python lists.
        f=np.asarray([r['F'] for r in rows],float)
        g=np.asarray([r['G'] for r in rows],float)
        x=np.asarray([r['X'] for r in rows])
        if f.ndim!=2 or not f.shape[1] or g.ndim!=2 or not np.isfinite(f).all() or not np.isfinite(g).all():raise ValueError('Invalid archive objective/constraint vector')
        if x.ndim!=3 or np.any((x!=0)&(x!=1)):raise ValueError('Invalid physical decision')
        shape=(f.shape[1],g.shape[1],x.shape[1:])
        if self.widths is None:self.widths=shape
        if self.widths!=shape:raise ValueError('Mixed archive dimensions')
        binary=x.astype(np.uint8)
        feasible=np.all(g<=self.tolerance,axis=1)
        keys=('experiment_contract_id','run_id','config_sha256','evaluator_sha256','config_hash','evaluator_hash','objective_order')
        for offset,r in enumerate(rows):
            if self.expected is None:self.expected={k:r.get(k) for k in keys}
            if any(r.get(k)!=v for k,v in self.expected.items()):raise ValueError('Mixed archive identity')
            if r.get('provenance')=='POSTHOC_DIAGNOSTIC_NOT_OPTIMIZER':raise ValueError('Diagnostic row in optimizer archive')
            raw_id=r['id']
            if type(raw_id) is not int or raw_id<0 or raw_id in self.ids:raise ValueError('Duplicate/invalid raw ID')
            self.ids.add(raw_id)
            self.decisions[raw_id]=binary[offset]
            if feasible[offset]:
                key=r.get('placement_hash') or r.get('decision_sha256') or binary[offset].tobytes()
                if key in self.first:
                    old=self.first[key]
                    if old['F']!=r['F'] or old['G']!=r['G'] or not np.array_equal(self.decisions[old['id']],binary[offset]):raise ValueError('Same placement has inconsistent evaluation')
                else:
                    self.first[key]=r
                    # The original three-objective sweep additionally retains
                    # first physical X, even if supplied hash keys differ. Its
                    # general dimensional counterpart deduplicates hash keys only.
                    physical=self.decisions[raw_id].tobytes()
                    if f.shape[1]!=3 or physical not in self._seen_physical:self._pending.append(r)
                    self._seen_physical.add(physical)

    def selected(self):
        if self._pending:
            self._front=_merge_front(self._front,self._pending,self.sort)
            self._pending=[]
        return [r['id'] for r in self._front]


def _merge_front(front,pending,sort):
    """Exact minimization: an existing front needs only cross-batch comparisons.

    Equal objective vectors share comparisons, never physical row identity.
    All rows in a surviving equality group remain available to map/Hamming UI.
    Strict dominance requires at least one smaller objective; no epsilon added.
    """
    new_values,new_inverse=np.unique(np.asarray([r['F'] for r in pending],float),axis=0,return_inverse=True)
    new_keep=np.zeros(len(new_values),dtype=bool)
    new_keep[NonDominatedSorting(method='efficient_non_dominated_sort').do(new_values,only_non_dominated_front=True)]=True
    new_ids=np.flatnonzero(new_keep);new_front=new_values[new_ids]
    if front:
        old_values,old_inverse=np.unique(np.asarray([r['F'] for r in front],float),axis=0,return_inverse=True)
        old_keep=np.ones(len(old_values),dtype=bool)
        # Bound temporary comparison memory even for large batches/fronts.
        for begin in range(0,len(old_values),512):
            old=old_values[begin:begin+512]
            for start in range(0,len(new_front),64):
                new=new_front[start:start+64]
                le=np.ones((len(old),len(new)),dtype=bool)
                ge=np.ones_like(le)
                for axis in range(old.shape[1]):
                    le &= old[:,axis,None]<=new[None,:,axis]
                    ge &= old[:,axis,None]>=new[None,:,axis]
                new_keep[new_ids[start:start+64]] &= ~np.any(le & ~ge,axis=0)
                old_keep[begin:begin+512] &= ~np.any(ge & ~le,axis=1)
        result=[r for i,r in enumerate(front) if old_keep[old_inverse[i]]]
    else:result=[]
    result.extend(r for i,r in enumerate(pending) if new_keep[new_inverse[i]])
    if sort=='cost':result.sort(key=lambda r:(r['cost'],*r['F'][:2],r['id']))
    else:result.sort(key=lambda r:r['id'])
    return result
