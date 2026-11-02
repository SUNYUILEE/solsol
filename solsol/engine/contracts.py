"""Canonical identities and the calculator's public evaluation boundary."""
import hashlib
import json
from typing import Protocol


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class EvaluationModel(Protocol):
    """No calculator imports of model-specific physics or initialization."""
    contract_id: str
    model_id: str
    evaluator_version: str
    space: object
    inventory_rule: dict
    objective_ids: list
    constraint_ids: list

    @property
    def config(self) -> dict: ...

    def evaluate(self, x) -> dict:
        """Return X, F (minimize), G (<=0), cost, named_metrics and map evidence."""
        ...
