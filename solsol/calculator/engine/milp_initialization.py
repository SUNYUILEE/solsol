"""Consume Model-owned integer matrices; never reconstruct sensor formulas."""
import copy
import math
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix
from model_service_client import client
from .contracts import digest
from .initialization import assign, resource_counts

VERSION = 'NEUTRAL_AREA_INITIALIZATION_V1'


def require(condition, reason):
    if not condition:
        raise ValueError('MODEL_INITIALIZATION_' + reason)


def binding(cp, packet):
    expected = dict(problem_id=cp.problem_id, input_sha256=cp.input_sha256,
        model_id=cp.cid, model_version=cp.model_version, config_sha256=cp.config_hash,
        evaluator_sha256=cp.evaluator_hash, service_release_sha256=cp.service_identity['service_release_sha256'],
        source_sha256=cp.model_source_sha256)
    order = dict(candidate_order=list(cp.candidate_order), sensor_order=list(cp.sensor_order),
        active_slot_order=np.flatnonzero(cp.space.allowed.ravel()).tolist(),
        full_X_shape=list(cp.space.shape), enabled_sensor_ids=list(cp.space.enabled_sensor_ids),
        allowed=cp.space.allowed.astype(int).tolist(), co_location=cp.space.co_location,
        codec_slot_order=cp.codec.slots.tolist())
    require(packet.get('contract_version') == VERSION, 'VERSION')
    require(packet.get('identity') == expected, 'IDENTITY')
    require(packet.get('order') == order and packet.get('installation_sha256') == digest(order), 'ORDER')
    require(packet.get('installation_contract') == 'INSTALLATION_SPACE_V1', 'INSTALLATION_VERSION')
    require(packet.get('target_source') == 'research_goals', 'TARGET_SOURCE')
    require(packet.get('tolerance') == cp.feasibility_tolerance, 'TOLERANCE')
    for key in ('builder_sha256', 'formulation_sha256'):
        value = packet.get(key)
        require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'HASH_FORMAT')
    require(packet.get('status') == 'SUPPORTED', 'UNSUPPORTED:' + str(packet.get('reason', 'unknown')))
    targets = packet.get('targets', [])
    require(len({t['metric_id'] for t in targets}) == len(targets), 'DUPLICATE_TARGET')
    require({t['metric_id']: t['epsilon'] for t in targets} == cp.config['_research']['goals'], 'TARGETS')
    require(all(t['unit'] == '%' and t['value_source'] == 'coverage_metrics.' + t['metric_id'] for t in targets), 'TARGET_UNITS')


def capability(cp):
    if not hasattr(cp, '_initialization_capability'):
        p = client().request('/problems/' + cp.problem_id + '/initialization')
        binding(cp, p)
        cp._initialization_capability = copy.deepcopy(p)
    return copy.deepcopy(cp._initialization_capability)


def fetch_formulation(cp):
    cap = capability(cp)
    p = client().request('/initialization/formulation', dict(problem_id=cp.problem_id,
        contract_version=VERSION, expected_identity=cap['identity'], method='milp_epsilon', target_source='research_goals'))
    binding(cp, p)
    require(p['formulation_sha256'] == cap['formulation_sha256'] and
        digest({k: v for k, v in p.items() if k not in ('api_version', 'formulation_sha256')}) == p['formulation_sha256'], 'FORMULATION_HASH')
    require(p['builder_sha256'] == cap['builder_sha256'], 'BUILDER_HASH')
    return p


def arrays(cp, p):
    """Strict wire validation before allocating solver matrices."""
    require(p.get('exactness') == 'EXACT_AREA_GOAL_INTEGER_FORMULATION', 'EXACTNESS')
    objective = p['objective']
    require(objective['sense'] == 'minimize' and objective['metric_id'] == 'actual_cost' and
        objective['unit'] == 'synthetic_cost' and objective['constant'] == 0, 'OBJECTIVE')
    n = len(p['variables']); require(0 < n <= 100000, 'VARIABLE_LIMIT')
    c = np.asarray(objective['c'], float)
    require(c.shape == (n,) and np.isfinite(c).all(), 'OBJECTIVE_ARRAY')
    require(p['integrality'] == [1] * n and p['bounds'] == dict(lower=[0] * n, upper=[1] * n), 'BINARY_BOUNDS')
    cons = p['constraints']; mat = cons['matrix']; shape = mat['shape']
    require(mat['format'] == 'coo' and len(shape) == 2 and all(type(v) is int and v >= 0 for v in shape) and shape[1] == n, 'MATRIX_SHAPE')
    m = shape[0]
    require(len(cons['row_ids']) == m and len(set(cons['row_ids'])) == m, 'ROW_IDS')
    require(len(mat['row']) == len(mat['col']) == len(mat['data']) <= 2000000, 'NONZERO_LIMIT')
    require(all(type(v) is int and 0 <= v < m for v in mat['row']) and
        all(type(v) is int and 0 <= v < n for v in mat['col']) and np.isfinite(mat['data']).all(), 'COO_DATA')
    require(len(cons['lower']) == len(cons['upper']) == m and
        all(v is None or (type(v) in (int, float) and math.isfinite(v)) for v in cons['lower'] + cons['upper']), 'CONSTRAINT_BOUNDS')
    lo = np.asarray([-np.inf if v is None else v for v in cons['lower']])
    hi = np.asarray([np.inf if v is None else v for v in cons['upper']])
    require(np.all(lo <= hi), 'CONSTRAINT_INTERVAL')
    A = coo_matrix((mat['data'], (mat['row'], mat['col'])), shape=tuple(shape)).tocsc()
    restore = p['restoration']; mapping = restore['variable_to_flat_X']
    require(restore['default_X_value'] == 0, 'RESTORE_DEFAULT')
    indices = [v['variable_index'] for v in mapping]; flats = [v['flat_X_index'] for v in mapping]
    require(all(type(v) is int and 0 <= v < n for v in indices) and len(set(indices)) == len(indices), 'RESTORE_VARIABLES')
    require(all(type(v) is int for v in flats) and sorted(flats) == np.flatnonzero(cp.space.allowed.ravel()).tolist(), 'RESTORE_SLOTS')
    require(set(indices) == {i for i, v in enumerate(p['variables']) if v['kind'] == 'installation'}, 'RESTORE_COMPLETE')
    for index, flat in zip(indices, flats):
        v = p['variables'][index]
        require(v['flat_X_index'] == flat and v['candidate_index'] == flat // cp.space.shape[1] and
            v['sensor_index'] == flat % cp.space.shape[1], 'RESTORE_ORDER')
    require(p['acceptance'] == dict(endpoint='/evaluate-batch', validate_installation=True, require_integer=True,
        require_same_identity=True, require_G_at_most_tolerance=True, require_all_frozen_area_goals=True), 'ACCEPTANCE')
    return c, A, lo, hi, indices, flats


def checked_incumbent(cp, p, a, vector):
    c, A, lo, hi, indices, flats = a
    v = np.asarray(vector, float)
    require(v.shape == c.shape and np.isfinite(v).all(), 'INCUMBENT_SHAPE')
    require(np.all(np.abs(v - np.rint(v)) <= 1e-6), 'FRACTIONAL_INCUMBENT')
    v = np.rint(v)
    require(np.all((v >= 0) & (v <= 1)), 'INCUMBENT_BOUNDS')
    av = A @ v
    require(np.all(av >= lo - 1e-7) and np.all(av <= hi + 1e-7), 'INCUMBENT_CONSTRAINTS')
    x = np.zeros(cp.space.shape, np.uint8); x.flat[flats] = v[indices].astype(np.uint8)
    return cp.space.validate(x), float(c @ v)


def prepare_milp(session, deadline):
    started = time.monotonic(); cp = session.problem
    info = session.initialization
    info.update(version=VERSION, seed_count=0, targets=cp.config['_research']['goals'],
        target_semantics='MODEL_COVERAGE_METRICS_PERCENT_NOT_MEAN_QUALITY', preparation_budget=1,
        pareto_front_certified=False, scientific_optimum_certified=False, sources=[])
    trace = session.solver_metadata.setdefault('initializer_trace', [])
    best = None
    try:
        p = fetch_formulation(cp)
        session.solver_metadata['initialization_formulation'] = p
        info.update(formulation_sha256=p['formulation_sha256'], builder_sha256=p['builder_sha256'], bound_scope=p['bound_scope'])
        a = arrays(cp, p)
        if session.cancel.is_set():
            info['outcome'] = 'CANCELLED_BEFORE_SOLVE'
        elif time.monotonic() >= deadline:
            info['outcome'] = 'NO_INCUMBENT_PREPARATION_DEADLINE'
        else:
            limit = max(.001, deadline - time.monotonic())
            entry = dict(method='milp', phase='SOLVING', time_limit_seconds=limit, mip_rel_gap=0.)
            trace.append(entry)
            result = milp(a[0], integrality=np.ones(len(a[0])), bounds=Bounds(0, 1),
                constraints=LinearConstraint(a[1], a[2], a[3]), options=dict(time_limit=limit, mip_rel_gap=0.))
            entry.update(phase='SOLVED', status=int(result.status), message=str(result.message))
            for key in ('mip_dual_bound', 'mip_gap', 'mip_node_count', 'fun'):
                v = getattr(result, key, None)
                entry[key] = float(v) if v is not None and math.isfinite(v) else None
            require(result.status in (0, 1, 2), 'SOLVER_FAILURE:' + str(result.status))
            if session.cancel.is_set():
                info['outcome'] = 'CANCELLED_AFTER_SOLVE'
            elif result.x is None:
                require(result.status in (1, 2), 'MISSING_OPTIMAL_INCUMBENT')
                info['outcome'] = 'INFEASIBLE' if result.status == 2 else 'NO_INCUMBENT_WITHIN_BUDGET'
            else:
                require(result.status in (0, 1), 'UNEXPECTED_INCUMBENT')
                entry['integer_candidate'] = [float(v) if math.isfinite(v) else None for v in np.asarray(result.x).ravel()]
                x, objective = checked_incumbent(cp, p, a, result.x)
                reevaluation = dict(requested_evaluations=1, confirmed_evaluations=None, outcome='REQUESTED')
                entry['reevaluation'] = reevaluation
                info['preparation_evaluation_attempts'] = 1
                info['preparation_evaluations_uncertain'] = True
                try:
                    row = cp.evaluate_physical([x], validate_installation=True)[0]
                except Exception as exc:
                    reevaluation.update(outcome='ERROR_COMPLETION_UNKNOWN', error=str(exc))
                    raise
                reevaluation.update(confirmed_evaluations=1, outcome='RESPONSE_VALIDATED')
                info['preparation_evaluations_uncertain'] = False
                ledger = session.solver_metadata.setdefault('auxiliary_evaluations', [])
                auxiliary_id = len(ledger); ledger.append(dict(auxiliary_id=auxiliary_id, phase='preparation', row=row))
                session.counters['preparation_evaluations'] += 1
                require(np.isfinite(row['F'] + row['G']).all() and np.all(np.asarray(row['G']) <= cp.feasibility_tolerance), 'REEVALUATED_G')
                require(all(math.isfinite(row['coverage_metrics'][t['metric_id']]) and row['coverage_metrics'][t['metric_id']] >= t['epsilon'] for t in p['targets']), 'REEVALUATED_GOALS')
                require(math.isfinite(row['cost']) and math.isclose(row['cost'], objective, rel_tol=1e-10, abs_tol=1e-10), 'REEVALUATED_COST')
                require(result.fun is not None and math.isclose(float(result.fun), objective, rel_tol=1e-10, abs_tol=1e-10), 'SOLVER_COST')
                best = x
                info.update(seed_count=1, outcome='QUALIFIED_INTEGER_INCUMBENT',
                    sources=[dict(index=0, method='milp', auxiliary_id=auxiliary_id)], actual_cost_upper_bound=row['cost'])
        rng = np.random.default_rng(np.random.SeedSequence([session.optimizer['seed'], 91401]))
        limits, exact = resource_counts(cp.space, getattr(cp.bundle, 'inventory_rule', None))
        base = []
        for _ in range(session.optimizer['population']):
            counts = limits if exact else np.asarray([rng.integers(0, v + 1) for v in limits])
            orders = [rng.permutation(np.flatnonzero(cp.space.allowed[:, j])) for j in range(cp.space.shape[1])]
            base.append(assign(cp.space, counts, orders, exact=exact))
        if best is not None: base[0] = best
        X = np.asarray(base)
        info.update(status='PREPARED', population=len(X), initial_X_sha256=digest(X.astype(int).tolist()),
            fallback_population='seeded resource-feasible random', deadline_semantics='solver limit; HTTP and reevaluation may finish afterwards')
        return cp.codec.encode(X), info
    except Exception as exc:
        info.update(status='FAILED', outcome='REJECTED', error=str(exc))
        raise
    finally:
        info.update(seconds=time.monotonic() - started, preparation_evaluations=session.counters['preparation_evaluations'])
