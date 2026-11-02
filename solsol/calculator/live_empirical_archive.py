"""Derived cumulative empirical nondominated view over immutable MOEA rows.

This module never changes raw X/F/G or the saved current-generation front.
"""
from __future__ import annotations

import numpy as np
from search import NDS

TOL = 1e-12


def _unique_decision_ids(ids, X):
    first = {}
    for raw_id in map(int, ids):
        key = np.ascontiguousarray(X[raw_id]).tobytes()
        first.setdefault(key, raw_id)
    return np.asarray(list(first.values()), dtype=int)


def cumulative_archive_ids(X, F, G, evaluations=None):
    """Return first-observed unique feasible X that are nondominated in observed F."""
    X = np.asarray(X, dtype=np.uint8)
    F = np.asarray(F, dtype=float)
    G = np.asarray(G, dtype=float)
    stop = len(X) if evaluations is None else max(0, min(int(evaluations), len(X)))
    feasible = np.flatnonzero(np.all(G[:stop] <= TOL, axis=1))
    unique = _unique_decision_ids(feasible, X) if len(feasible) else np.array([], dtype=int)
    if not len(unique):
        return []
    # The live view can contain tens of thousands of rows. Calling pymoo's
    # quadratic sorter on every status request made a completed 500-generation
    # run appear to hang while it was being published. For exactly three
    # minimisation objectives, use an O(n log n) sweep over f1.
    values = F[unique]
    order = np.lexsort((values[:, 2], values[:, 1], values[:, 0]))
    sorted_values = values[order]
    f1_levels = np.unique(sorted_values[:, 1])
    tree = np.full(len(f1_levels) + 1, np.inf, dtype=float)

    def prefix_min(index):
        result = np.inf
        while index:
            result = min(result, tree[index]); index -= index & -index
        return result

    def update(index, value):
        while index < len(tree):
            if value < tree[index]: tree[index] = value
            index += index & -index

    keep = np.ones(len(order), dtype=bool)
    start = 0
    while start < len(order):
        end = start + 1
        # Identical objective vectors do not strictly dominate one another.
        while end < len(order) and np.array_equal(sorted_values[end], sorted_values[start]):
            end += 1
        for pos in range(start, end):
            rank = int(np.searchsorted(f1_levels, sorted_values[pos, 1], side='right'))
            keep[pos] = not (prefix_min(rank) <= sorted_values[pos, 2])
        for pos in range(start, end):
            rank = int(np.searchsorted(f1_levels, sorted_values[pos, 1], side='left')) + 1
            update(rank, sorted_values[pos, 2])
        start = end
    ids = unique[order[keep]].tolist()
    return sorted(map(int, ids), key=lambda i: (F[i, 2], F[i, 0], F[i, 1], i))


def derived_snapshot(snapshot, X, F, G):
    view = dict(snapshot)
    view['archive_ids'] = cumulative_archive_ids(X, F, G, snapshot['evaluations'])
    view['archive_scope'] = 'observed_feasible_unique_x_empirically_nondominated_through_generation'
    return view
