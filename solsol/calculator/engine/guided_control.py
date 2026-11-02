"""Budget-matched cost-role controls, separate from historical A/B plans.

Uses the existing validation lifecycle. No solver, Model formula or raw rewrite.
"""
import copy
import math
import uuid
from . import guided_cost_budget as guide
from .store import digest, sha

PREFIX = '비용 대조 V1|'


def label(a_id, scope, proposal_hash, budget, cost_role):
    return PREFIX + '|'.join((a_id, scope, proposal_hash, str(budget), cost_role))


def identity(cell):
    parts = cell['label'].split('|')
    if len(parts) != 6 or parts[0] != PREFIX[:-1]:
        raise ValueError('CONTROL_LABEL')
    _, a_id, scope, ph, budget, role = parts
    if str(uuid.UUID(a_id)) != a_id or scope not in ('all', 'targets'):
        raise ValueError('CONTROL_PARENT')
    if len(ph) != 64 or any(c not in '0123456789abcdef' for c in ph):
        raise ValueError('CONTROL_PROPOSAL_HASH')
    budget = float(budget)
    if not math.isfinite(budget) or budget < 0 or role not in ('ON', 'OFF'):
        raise ValueError('CONTROL_ROLE_OR_BUDGET')
    q = cell['request']
    actual = q['resource_contract']['budget']
    if actual != dict(mode='MAX', limit=budget):
        raise ValueError('CONTROL_BUDGET_BINDING')
    if ('cost' in q['objective_ids']) != (role == 'ON'):
        raise ValueError('CONTROL_OBJECTIVE_BINDING')
    return a_id, scope, ph, budget, role


def preview(service, cid, body):
    # Reuse scope, frozen raw/proposal, finite-budget and seed validation.
    old = guide.preview_b(service, cid, body)
    a = guide.group(service, cid, body['a_id'], 'A')
    variants = []
    for variant in old['request']['variants']:
        budget = variant['request']['resource_contract']['budget']['limit']
        for role in ('ON', 'OFF'):
            q = copy.deepcopy(variant['request'])
            if role == 'ON':
                q['objective_ids'] = copy.deepcopy(a['cells'][0]['request']['objective_ids'])
            variants.append(dict(label=label(body['a_id'], body['scope'], body['proposal_sha256'], budget, role), request=q))
    request = dict(variants=variants, seeds=old['request']['seeds'], diagnostics={})
    return dict(request=request, plan=service.preview(cid, request), proposal=old['proposal'],
        design='BUDGET_MATCHED_COST_ROLE_V1',
        meaning='기준 A와 예산·비용 목적 유지군을 비교하여 예산 효과를, 같은 예산의 비용 목적 유지·제외군을 비교하여 목적 역할 효과를 관측합니다. 반복 탐색의 차이를 함께 확인해야 하며 절충 발생을 보장하지 않습니다.')


def bound_group(service, cid, vid):
    """Fail closed before reading results: complete ON/OFF pairs per budget/seed."""
    g = service.get(cid, vid)
    if not g['cells']:
        raise ValueError('CONTROL_EMPTY')
    parsed = [identity(c) for c in g['cells']]
    parents = {p[:3] for p in parsed}
    if len(parents) != 1:
        raise ValueError('CONTROL_MIXED_PARENT')
    a_id, scope, ph = next(iter(parents))
    prop = guide.proposal(service, cid, a_id, scope)
    if prop['proposal_sha256'] != ph:
        raise ValueError('GUIDED_PROPOSAL_CHANGED')
    a = guide.group(service, cid, a_id, 'A')
    sources = {c['seed']: c for c in a['cells']}
    seen = set()
    for c, p in zip(g['cells'], parsed):
        key = (p[3], c['seed'], p[4])
        if key in seen or c['seed'] not in sources:
            raise ValueError('CONTROL_PAIR_DUPLICATE_OR_SEED')
        seen.add(key)
        base = copy.deepcopy(sources[c['seed']]['request'])
        # identity() checked numeric equality; JSON 20 and 20.0 are equivalent budgets.
        base['resource_contract']['budget'] = copy.deepcopy(c['request']['resource_contract']['budget'])
        if p[4] == 'OFF':
            base['objective_ids'] = [i for i in base['objective_ids'] if i != 'cost']
        if digest(base) != digest(c['request']):
            raise ValueError('CONTROL_FIXED_CONDITIONS_CHANGED')
    expected = {(p[3], seed, role) for p in parsed for seed in sources for role in ('ON', 'OFF')}
    if seen != expected:
        raise ValueError('CONTROL_MISSING_PAIR')
    return dict(group=g, baseline=a, proposal=prop)


def comparison(service, cid, vid, scope='all'):
    guide.scoped([], scope)
    bound = bound_group(service, cid, vid)
    baseline = {c['seed']: c for c in bound['baseline']['cells']}
    pairs = {}
    for c in bound['group']['cells']:
        _, _, _, budget, role = identity(c)
        pairs.setdefault((budget, c['seed']), {})[role] = c
    results, cache = [], {}

    def loaded(c):
        # IDs are local to each validation; the immutable request and attempts distinguish A.
        key = digest(dict(request=c['request'], attempts=c.get('attempts')))
        if key not in cache:
            cache[key] = guide.saved(service, cid, c)
        return cache[key]

    for (budget, seed), pair in sorted(pairs.items()):
        cells = dict(BASELINE=baseline[seed], ON=pair['ON'], OFF=pair['OFF'])
        states = {role: c['state'] for role, c in cells.items()}
        result = dict(budget=budget, seed=seed, states=states, arms={}, complete=all(s == 'completed' for s in states.values()))
        results.append(result)
        if not result['complete']:
            continue
        packets = {role: loaded(c) for role, c in cells.items()}
        bp = packets['BASELINE'][1]
        axes = [k for k in bp['registry']['objective_order'] if k != 'cost']
        for role, (record, p, raw, archive, tol) in packets.items():
            order = p['registry']['objective_order']
            if [k for k in order if k != 'cost'] != axes:
                raise ValueError('CONTROL_PERFORMANCE_AXES_CHANGED')
            if ('cost' in order) != (role != 'OFF'):
                raise ValueError('CONTROL_SAVED_OBJECTIVE_ROLE')
            for key in ('candidate_order', 'sensor_order'):
                if p['registry'][key] != bp['registry'][key]:
                    raise ValueError('CONTROL_PHYSICAL_ORDER_CHANGED')
            for key in ('sites', 'demand', 'geometry'):
                if digest(p['problem'].get(key)) != digest(bp['problem'].get(key)):
                    raise ValueError('CONTROL_MAP_GEOMETRY_CHANGED')
            for key in ('source_sha256', 'service_release_sha256'):
                origin = bp['problem'].get('model_service', {}).get(key)
                actual = p['problem'].get('model_service', {}).get(key)
                if not origin or actual != origin:
                    raise ValueError('CONTROL_MODEL_RELEASE_UNVERIFIED')
            indices = [order.index(k) for k in axes]
            selected = guide.scoped(archive, scope)
            performance = guide.front(selected, indices)
            eligible = [r for r in selected if r['cost'] <= budget + tol]
            stats = guide.front_metrics(performance, indices, tol)
            conflict = stats['front_example']
            if conflict:
                by_id = {r['id']: r for r in performance}
                for witness in conflict.values():
                    witness['X'] = by_id[witness['id']]['X']
            result['arms'][role] = dict(run_id=record.id, raw_sha256=sha(record.folder/'raw.json'),
                config_sha256=p['config_sha256'], evaluator_sha256=p['evaluator_sha256'],
                axes=axes, objective_order=order, archive_count=len(selected), performance_front_count=len(performance),
                budget_eligible_archive_count=len(eligible),
                performance_ranges={k: [min(r['named_metrics'][k] for r in performance), max(r['named_metrics'][k] for r in performance)] if performance else None for k in axes},
                cost_range=[min(r['cost'] for r in selected), max(r['cost'] for r in selected)] if selected else None,
                min_budget_slack=min((budget-r['cost'] for r in selected), default=None),
                example=guide.compact(performance[0], indices) if performance else None,
                conflict=conflict, search_nfe=p.get('nfe'), counters=p.get('counters'),
                initialization=p.get('initialization'), attempts=cells[role]['attempts'])
        nfes = [a['search_nfe'] for a in result['arms'].values()]
        known = all(type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in nfes)
        result['matched_search_nfe'] = len(set(nfes)) == 1 if known else None
    return dict(design='BUDGET_MATCHED_COST_ROLE_V1', study_id=vid, scope=scope,
        proposal_scope=bound['proposal']['scope'], proposal=bound['proposal'], pairs=results,
        complete=bool(results) and all(r['complete'] for r in results), global_optimality=False,
        meaning='기준과 비용 목적 유지군은 예산 제한 효과, 같은 예산의 유지·제외군은 목적 역할 효과를 비교합니다. 기준 전체 성능과 예산 이하 관측 수를 구분합니다. 공통 성능 축의 관측 결과이며 다른 차원의 HV나 전역 인과 증명이 아닙니다.')


def checks(service, cid, body):
    if set(body) != {'study_id', 'budget', 'seed', 'scope', 'a_job', 'b_job'}:
        raise ValueError('CONTROL_CHECK_FIELDS')
    if type(body['budget']) not in (int,float) or not math.isfinite(body['budget']) or body['budget']<0 or type(body['seed']) is not int:
        raise ValueError('CONTROL_CHECK_PAIR_IDENTITY')
    report = comparison(service, cid, body['study_id'], body['scope'])
    pair = next((p for p in report['pairs'] if p['budget'] == body['budget'] and p['seed'] == body['seed']), None)
    if pair is None or not pair['complete']:
        raise ValueError('CONTROL_CHECK_PAIR_NOT_COMPLETE')
    results = []
    for role, job in [('ON', body['a_job']), ('OFF', body['b_job'])]:
        arm = pair['arms'][role]
        if not arm['example']:
            raise ValueError('CONTROL_CHECK_NO_EXAMPLE')
        result = guide.check_result(service.service.get(arm['run_id'], cid), job,
                                    arm['example']['raw_id'], pair['budget'], report['scope'])
        result['cost_role'] = role
        results.append(result)
    return dict(results=results, complete=all(r['status']=='COMPLETED' and r['scope_complete'] for r in results),
                comparison=pair, scope=report['scope'], provenance='POSTHOC_CHECK_NOT_OPTIMIZER')
