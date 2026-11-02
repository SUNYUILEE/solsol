"""Model registration via the pinned HTTP contract; solver code stays local."""
from pathlib import Path
import sys
_ROOT=Path(__file__).resolve().parents[1]
for _path in (_ROOT,_ROOT/'implementation'):
    if str(_path) not in sys.path:sys.path.insert(0,str(_path))
from model_service_client import compile_remote,compile_remote_toy
compile_problem=compile_remote

def compile_toy(n_candidates=3,n_sensors=2,n_objectives=3,n_constraints=0,
                enabled_sensor_ids=None,objective_ids=None,diagnostic_ids=None,
                candidate_order=None,sensor_order=None,allowed=None,co_location=True):
    return compile_remote_toy(**locals())
