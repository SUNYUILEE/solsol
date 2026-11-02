"""Exact immutable-prefix dominance lifetimes with optional compiled queries.

Uses the V2 tree construction and unchanged AppendOnlyArchive.extend validation.
No native pretrim, float rounding, fastmath, parallelism, or
trusted result cache. Numba's cache stores compiled machine code only.
"""
import math
import numpy as np
from .archive import AppendOnlyArchive, _archive_prefix_ids_reference as _baseline_prefix_ids
class _Node:
    __slots__ = ('low', 'high', 'earliest', 'left', 'right', 'indices')


class _EarliestDominator:
    def __init__(self, values, arrivals, missing, leaf_size=48):
        self.values = values
        self.arrivals = arrivals
        self.missing = missing
        self.leaf_size = leaf_size
        self.root = self._build(np.arange(len(values), dtype=np.intp), 0) if len(values) else None

    def _build(self, indices, depth):
        node = _Node()
        values = self.values[indices]
        node.low = tuple(values.min(axis=0))
        node.high = tuple(values.max(axis=0))
        node.earliest = int(self.arrivals[indices].min())
        node.left = node.right = None
        node.indices = None
        if len(indices) <= self.leaf_size:
            node.indices = indices
            return node
        # Cycling dimensions avoids overflow in a floating-point span estimate.
        axis = depth % self.values.shape[1]
        middle = len(indices) // 2
        order = np.argpartition(values[:, axis], middle)
        node.left = self._build(indices[order[:middle]], depth + 1)
        node.right = self._build(indices[order[middle:]], depth + 1)
        return node



try:
    from numba import njit
except (ImportError, OSError, RuntimeError):
    njit = None


def _flatten(tree):
    nodes = []
    stack = [tree.root]
    while stack:
        node = stack.pop()
        nodes.append(node)
        if node.indices is None:
            stack.extend((node.right, node.left))
    lookup = {id(node): i for i, node in enumerate(nodes)}
    low = np.asarray([node.low for node in nodes], dtype=np.float64)
    high = np.asarray([node.high for node in nodes], dtype=np.float64)
    earliest = np.asarray([node.earliest for node in nodes], dtype=np.int64)
    left = np.full(len(nodes), -1, dtype=np.int64)
    right = left.copy()
    offsets = np.zeros(len(nodes), dtype=np.int64)
    counts = offsets.copy()
    leaves = []
    for i, node in enumerate(nodes):
        if node.indices is None:
            left[i] = lookup[id(node.left)]
            right[i] = lookup[id(node.right)]
        else:
            offsets[i] = len(leaves)
            counts[i] = len(node.indices)
            leaves.extend(node.indices)
    return (low, high, earliest, left, right, offsets, counts,
            np.asarray(leaves, dtype=np.int64))


def _deaths_kernel(values, arrivals, missing, low, high, earliest,
                   left, right, offsets, counts, leaves):
    result = np.full(len(values), missing, dtype=np.int64)
    stack = np.empty(len(earliest), dtype=np.int64)
    for q in range(len(values)):
        best = missing
        birth = arrivals[q]
        size = 1
        stack[0] = 0
        while size:
            size -= 1
            node = stack[size]
            if earliest[node] >= best:
                continue
            outside = False
            inside = True
            strict_box = False
            equal_box = True
            for axis in range(values.shape[1]):
                x = values[q, axis]
                if low[node, axis] > x:
                    outside = True
                    break
                if high[node, axis] > x:
                    inside = False
                if high[node, axis] < x:
                    strict_box = True
                if low[node, axis] != x:
                    equal_box = False
            if outside:
                continue
            if inside:
                if strict_box:
                    best = earliest[node]
                    if best <= birth:
                        break
                    continue
                if equal_box:
                    continue
            if left[node] < 0:
                for offset in range(offsets[node], offsets[node] + counts[node]):
                    p = leaves[offset]
                    if arrivals[p] >= best:
                        continue
                    dominates = True
                    strict = False
                    for axis in range(values.shape[1]):
                        if values[p, axis] > values[q, axis]:
                            dominates = False
                            break
                        if values[p, axis] < values[q, axis]:
                            strict = True
                    if dominates and strict:
                        best = arrivals[p]
                        if best <= birth:
                            break
                if best <= birth:
                    break
            else:
                first = left[node]
                second = right[node]
                if earliest[second] < earliest[first]:
                    first, second = second, first
                stack[size] = second
                stack[size + 1] = first
                size += 2
        result[q] = best
    return result


try:
    _compiled_deaths = (njit(cache=True, fastmath=False)(_deaths_kernel)
                        if njit is not None else None)
except Exception:
    _compiled_deaths = None


def archive_prefix_ids(rows, stops, tolerance=0.0, sort='raw', return_index=False, *, stats=None):
    """Immutable cold records only; live append remains in archive.py.

    Input positions, not possibly noncontiguous raw IDs, determine time. Every
    admitted equal-F physical row remains separately visible once it arrives.
    The returned index preserves last-checkpoint front / unselected-tail state.
    """
    if stats is not None:
        stats.clear()
    if _compiled_deaths is None or len(rows) >= np.iinfo(np.int64).max:
        return _baseline_prefix_ids(rows, stops, tolerance, sort, return_index)
    index = AppendOnlyArchive(tolerance, sort)
    previous = 0
    checked_stops = []
    for stop in stops:
        if type(stop) is not int or not previous < stop <= len(rows):
            raise ValueError('Invalid archive prefix range')
        index.extend(rows[previous:stop])
        checked_stops.append(stop)
        previous = stop
    # Includes malformed rows after the last checkpoint, exactly as baseline.
    index.extend(rows[previous:])

    admitted = list(index._pending)
    if not admitted or not checked_stops:
        result = [[] for _ in checked_stops]
        return (result, index) if return_index else result

    position = {row['id']: offset for offset, row in enumerate(rows)}
    groups = {}
    group_values = []
    group_arrivals = []
    row_groups = []
    row_arrivals = []
    for row in admitted:
        # Same float64 conversion as the baseline cross-front comparison kernel.
        key = tuple(np.asarray(row['F'], dtype=float))
        group = groups.get(key)
        arrival = position[row['id']]
        if group is None:
            group = len(group_values)
            groups[key] = group
            group_values.append(key)
            group_arrivals.append(arrival)
        else:
            group_arrivals[group] = min(group_arrivals[group], arrival)
        row_groups.append(group)
        row_arrivals.append(arrival)

    values = np.asarray(group_values, dtype=float)
    arrivals = np.asarray(group_arrivals, dtype=np.int64)
    missing = len(rows) + 1
    tree = _EarliestDominator(values, arrivals, missing)
    flat = _flatten(tree)
    try:
        deaths = _compiled_deaths(values, arrivals, missing, *flat)
    except Exception as exc:
        # Optional compiler/cache/platform failures preserve the original path.
        # This catch does not wrap input validation or subsequent cost sorting.
        if stats is not None:
            stats.update(mode='baseline_fallback', reason=type(exc).__name__)
        return _baseline_prefix_ids(rows, checked_stops, tolerance, sort, return_index)

    # Raw IDs are all validated. Cost is accessed by the baseline only for
    # selected prefix rows, so dominated/trailing cost must not be read early.
    order = sorted(range(len(admitted)), key=lambda i: admitted[i]['id'])
    ordered_rows = [admitted[i] for i in order]
    born = np.asarray([row_arrivals[i] for i in order], dtype=np.int64)
    dead = np.asarray([deaths[row_groups[i]] for i in order], dtype=np.int64)
    ids = [row['id'] for row in ordered_rows]
    result = []
    sort_keys = {}
    last_selected = np.empty(0, dtype=np.intp)
    for stop in checked_stops:
        last_selected = np.flatnonzero((born < stop) & (dead >= stop))
        if sort == 'cost':
            for selected in last_selected:
                i = int(selected)
                if i in sort_keys:
                    continue
                row = ordered_rows[i]
                try:
                    key = (row['cost'], *row['F'][:2], row['id'])
                    # Nonfinite/incomparable keys can make stable-sort output
                    # depend on the baseline's preceding merge order. Preserve
                    # that behavior instead of inventing an order from raw IDs.
                    finite = all(type(value) is int or
                                 (type(value) is float and math.isfinite(value))
                                 for value in key)
                except (KeyError, TypeError, ValueError):
                    finite = False
                if not finite:
                    return _baseline_prefix_ids(rows, checked_stops, tolerance,
                                                sort, return_index)
                sort_keys[i] = key
            last_selected = sorted(last_selected, key=lambda i: sort_keys[int(i)])
        result.append([ids[int(i)] for i in last_selected])

    # Publish only after validation, tree queries and ordering all succeed.
    index._front = [ordered_rows[int(i)] for i in last_selected]
    index._pending = [row for row in admitted if position[row['id']] >= previous]
    if stats is not None:
        stats.update(mode='numba', groups=len(values), nodes=len(flat[2]),
                     queried_groups=len(values))
    return (result, index) if return_index else result
