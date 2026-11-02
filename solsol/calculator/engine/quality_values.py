"""Eligibility of stored numerical evidence, independent of optional goals."""
import math
from numbers import Real


def finite_vector(values, *, allow_empty=False):
    return isinstance(values, (list, tuple)) and (allow_empty or bool(values)) and all(
        isinstance(v, Real) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def finite_fg(row):
    return finite_vector(row.get('F')) and finite_vector(row.get('G'), allow_empty=True)


def feasible_fg(row, tolerance):
    return finite_fg(row) and all(g <= tolerance for g in row['G'])


def quality_definition(path):
    from pathlib import Path
    from .store import digest, sha
    paths={Path(path),Path(__file__),Path(__file__).with_name('hard_constraints.py'),Path(__file__).with_name('results.py')}
    paths.add(Path(__file__).with_name('placement_statistics.py'))
    return digest({p.name:sha(p) for p in paths})
