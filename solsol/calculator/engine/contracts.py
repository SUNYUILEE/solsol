"""Serializable contracts for the shared calculation boundary."""
from dataclasses import dataclass, field, asdict
import hashlib
import json
import numpy as np

REGISTRY_VERSION = 'solsol-registry-v1'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class ObjectiveSpec:
    objective_id: str
    direction: str = 'minimize'
    unit: str = 'dimensionless'
    transform: str = 'identity'
    definition_version: str = 'v1'
    display_name: str = ''

@dataclass(frozen=True)
class ViewPreferences:
    layers: tuple = ()
    columns: tuple = ()

@dataclass(frozen=True)
class RegistrySnapshot:
    experiment_contract_id: str
    model_version: str
    candidate_order: tuple
    sensor_order: tuple
    objective_order: tuple
    constraint_order: tuple
    registry_version: str = REGISTRY_VERSION

    def to_dict(self):
        return asdict(self)

@dataclass(frozen=True)
class RunConfig:
    experiment_contract_id: str
    model_config: dict
    enabled_sensor_ids: tuple | None = None
    objective_ids: tuple | None = None
    diagnostic_ids: tuple = ()
    solver_config: dict = field(default_factory=dict)

@dataclass
class EvaluationBatch:
    rows: list
    X: np.ndarray
    F: np.ndarray
    G: np.ndarray

@dataclass
class RunRecord:
    run_id: str
    experiment_contract_id: str
    status: str
    metadata: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
