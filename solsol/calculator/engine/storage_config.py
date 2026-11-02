"""Production run-data location; explicit RunService roots remain unchanged."""
import os,json
from pathlib import Path


def production_run_root(config_path=None):
    configured=os.environ.get('SOLSOL_RUN_ROOT')
    config_path=Path(config_path) if config_path is not None else Path(__file__).resolve().parents[1]/'runtime_storage.json'
    if not configured and config_path.is_file():
        config=json.loads(config_path.read_text(encoding='utf8'))
        if not isinstance(config,dict) or set(config)!={'schema','run_root'} or config['schema']!='SOLSOL_RUNTIME_STORAGE_V1' or not isinstance(config['run_root'],str) or not config['run_root']:
            raise ValueError('UNSUPPORTED_RUNTIME_STORAGE_CONFIGURATION')
        configured=config['run_root']
    if configured:
        root=Path(os.path.expandvars(configured)).expanduser()
    else:
        local=os.environ.get('LOCALAPPDATA')
        if not local:raise ValueError('RUN_STORAGE_UNCONFIGURED: set SOLSOL_RUN_ROOT or LOCALAPPDATA')
        root=Path(local)/'SOLSOL'/'engine-runs-v1'
    if not root.is_absolute():raise ValueError('RUN_STORAGE_ABSOLUTE_PATH_REQUIRED')
    return root.resolve()
