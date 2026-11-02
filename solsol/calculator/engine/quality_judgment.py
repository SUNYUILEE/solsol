"""Run-specific empirical evidence; never a probability of global optimality."""
import math
from .hard_constraints import definition, audit_row, reports
from .quality_values import feasible_fg


def final_layouts(record):
    packet, rule = definition(record)
    tolerance = packet['archive_policy']['tolerance']
    audits = reports(record)
    rows = []
    for i in record.checkpoints[-1]['archive_ids'] if record.checkpoints else []:
        row = record.rows[i]
        if (audits[i]['hard_pass'] and
                feasible_fg(row,tolerance)):
            rows.append({key: row[key] for key in
                         ('id', 'X', 'F', 'named_metrics', 'coverage_metrics', 'cost', 'sensor_counts')
                         if key in row})
            rows[-1]['sensor_counts']=[sum(column) for column in zip(*row['X'])]
    return rows


def compare_fronts(original, repeats, tolerance):
    """Count runs, not individual layouts. A witness must jointly dominate."""
    outcomes = []
    for item in repeats:
        attained, improved, witnesses = [], [], []
        for base in original:
            matches = [r for r in item['layouts'] if len(r['F']) == len(base['F']) and
                       all(a <= b + tolerance for a, b in zip(r['F'], base['F']))]
            better = [r for r in matches if any(a < b - tolerance for a, b in zip(r['F'], base['F']))]
            if matches:
                attained.append(base['id'])
            if better:
                improved.append(base['id'])
                # Deterministic evidence example, not a new preference/objective.
                witness = min(better, key=lambda r: r['id'])
                witnesses.append(dict(original_id=base['id'],candidate=witness))
        outcomes.append(dict(run_id=item['run_id'],attained_ids=attained,
                             improved_ids=improved,witnesses=witnesses))
    n = len(original)
    return dict(schema='SOLSOL_JOINT_REPEAT_EVIDENCE_V1', original_layouts=original,
                original_count=n, repeat_count=len(outcomes), runs=outcomes,
                runs_attaining_entire_original=sum(n > 0 and len(r['attained_ids']) == n for r in outcomes),
                runs_improving_any=sum(bool(r['improved_ids']) for r in outcomes),
                runs_improving_entire_original=sum(n > 0 and len(r['improved_ids']) == n for r in outcomes),
                tolerance=tolerance, parent_excluded_from_frequency=True,
                global_optimality_probability=None)


def checked_local_evidence(record):
    # Verify persisted batches, not only the displayed job-state counters.
    from .quality_jobs import listing, stored_entries
    originals = final_layouts(record)
    ids = {r['id'] for r in originals}
    result = []
    for job in listing(record)['jobs']:
        if job['status'] != 'COMPLETED' or not ids.intersection(job['source_ids']):
            continue
        entries = list(stored_entries(record, job))
        witnesses = [r for r in entries if ids.intersection(r['improved_for'])]
        packet,_=definition(record)
        goals=(packet['config'].get('_research') or packet['problem'].get('research_configuration',{})).get('goals')
        counts = improvement_counts(witnesses, ids, targets_configured=goals is not None)
        result.append(dict(job_id=job['job_id'],method=job['method'],evaluated=len(entries),
                           replayed=sum(r['operation']=='replay' for r in entries),
                           covers_entire_final=bool(ids) and ids.issubset(job['source_ids']) and job.get('scope_complete') is True,
                           final_source_count=len(ids.intersection(job['source_ids'])),
                           improvement_count=len(witnesses),
                           **counts,
                           witnesses=witnesses[:3]))
    return result


def improvement_counts(entries, source_ids, *, targets_configured=None):
    """Evaluation rows, distinct decisions, and affected sources are not interchangeable."""
    relevant = [r for r in entries if set(source_ids).intersection(r.get('improved_for', []))]
    key = lambda r: tuple(tuple(c) for c in r['X'])
    unique = {key(r) for r in relevant}
    qualified = {key(r) for r in relevant if r.get('qualified') is True}
    if targets_configured is None:
        targets_configured = True if any(isinstance(r.get('qualified'),bool) for r in relevant) else None
    qualification_known = all(isinstance(r.get('qualified'),bool) for r in relevant)
    return dict(improvement_evaluation_rows=len(relevant), improvement_unique_X=len(unique),
                improved_source_count=len(set(source_ids).intersection({i for r in relevant for i in r['improved_for']})),
                qualified_improvement_unique_X=len(qualified) if targets_configured is True and qualification_known else None,
                qualification_status='NOT_CONFIGURED' if targets_configured is False else 'COUNTED' if targets_configured is True and qualification_known else 'UNRECORDED')
