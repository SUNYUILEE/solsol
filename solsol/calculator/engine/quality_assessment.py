"""Read-only interpretation of frozen observations, not an optimality certificate."""
import math
import numpy as np
from pathlib import Path
from .store import sha
from .hard_constraints import reports, definition
from .quality_values import finite_fg, finite_vector, feasible_fg, quality_definition

def assess(record):
    p,rule=definition(record)
    research=p['config'].get('_research') or p['problem'].get('research_configuration',{})
    metadata=research.get('metadata',{})
    tol=p['archive_policy']['tolerance'];checks=reports(record)
    rows=record.rows
    valid=lambda r: feasible_fg(r,tol)
    feasible=[r for r in rows if checks[r['id']]['hard_pass'] and valid(r)]
    unique={}
    for r in feasible:unique.setdefault(tuple(map(tuple,r['X'])),r)
    feasible=list(unique.values())
    last=record.checkpoints[-1] if record.checkpoints else {}
    ids=[i for i in last.get('archive_ids',[]) if checks[i]['hard_pass'] and valid(rows[i])]
    archive=[rows[i] for i in ids]
    initial_stop=record.checkpoints[0]['nfe'] if record.checkpoints else 0
    initial=[r for r in feasible if r['id']<initial_stop]
    metrics=[]
    for m in metadata.get('metrics',[]):
        if m['id'] not in research.get('objective_ids',[]) and m['id']!='cost':continue
        def values(source):
            return [float(r['named_metrics'][m['id']]) for r in source if isinstance(r.get('named_metrics',{}).get(m['id']),(int,float)) and math.isfinite(r['named_metrics'][m['id']])]
        vs=values(feasible);av=values(archive);iv=values(initial)
        best=max if m['direction']=='maximize' else min
        metrics.append(dict(metric=m,observed_min=min(vs) if vs else None,observed_max=max(vs) if vs else None,observed_best=best(vs) if vs else None,initial_best=best(iv) if iv else None,archive_min=min(av) if av else None,archive_max=max(av) if av else None,unique_values=len(set(vs)),constant_observed=len(set(vs))==1,sample_count=len(vs)))
    unique_all=len({tuple(map(tuple,r['X'])) for r in rows})
    from .placement_statistics import hamming_summary
    hamming=hamming_summary([r['X'] for r in archive])
    return dict(schema='SOLSOL_QUALITY_ASSESSMENT_V1',definition_sha256=quality_definition(__file__),run_id=record.id,config_sha256=p['config_sha256'],evaluator_sha256=p['evaluator_sha256'],generation=last.get('generation'),nfe=len(rows),goals=research.get('goals'),inventory_rule=rule,
        hard_invalid=sum(not c['hard_pass'] for c in checks.values()),model_invalid=sum(not finite_vector(r.get('G'),allow_empty=True) or any(g>tol for g in r['G']) for r in rows),
        nonfinite_rows=sum(not finite_fg(r) for r in rows),
        unique_feasible=len(feasible),unique_all=unique_all,repeated_evaluations=len(rows)-unique_all,
        archive_ids=ids,archive_unique_X=len({tuple(map(tuple,r['X'])) for r in archive}),archive_unique_F=len({tuple(r['F']) for r in archive}),
        target_count=None if research.get('goals') is None else sum(r.get('qualified') is True for r in archive),
        target_failed_count=None if research.get('goals') is None else sum(r.get('qualified') is False for r in archive),
        target_unknown_count=None if research.get('goals') is None else sum(not isinstance(r.get('qualified'),bool) for r in archive),
        hamming=hamming,
        metrics=metrics,archive_audits=[checks[i] for i in ids],
        scope='FINAL_SAVED_RUN_ALL_OBSERVED_UNIQUE_HARD_AND_MODEL_FEASIBLE',global_optimality=False)
