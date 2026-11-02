"""Content-addressed report-local basis, not an independent Pareto reference."""
import copy
from .store import digest

SCHEMA='SOLSOL_COMPARISON_BASIS_V1'

def freeze_basis(kind, source, reference, normalization, objectives, definition):
    value=copy.deepcopy(dict(schema=SCHEMA,kind=kind,source=source,reference=reference,
        normalization=normalization,objectives=objectives,definition_sha256=definition))
    return dict(value,sha256=digest(value))

def compare_basis(left,right):
    """Validate exported descriptors before comparing any report-local scores."""
    for value in (left,right):
        if not isinstance(value,dict) or value.get('schema')!=SCHEMA:
            return 'MISSING_BASIS'
        content={k:v for k,v in value.items() if k!='sha256'}
        if value.get('sha256')!=digest(content):return 'INVALID_BASIS'
        if not value.get('source'):return 'UNBOUND_SOURCE'
    return 'SAME_BASIS' if left['sha256']==right['sha256'] else 'DIFFERENT_BASIS'
