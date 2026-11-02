"""Atomic, checksummed whole-run storage. No historical source data is loaded."""
import json
import os
import re
import tempfile
from pathlib import Path

from .contracts import canonical,digest


class RunStore:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)

    def path(self,run_id):
        if not isinstance(run_id,str) or re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',run_id) is None:
            raise ValueError('Invalid run ID')
        path=self.root/(run_id+'.json')
        if path.is_symlink():raise ValueError('Symlink run paths forbidden')
        return path

    def save(self,run):
        target=self.path(run['run_id'])
        payload=canonical(dict(schema='SOLSOL_STORED_V1',sha256=digest(run),run=run))
        if target.exists():
            if target.read_bytes()==payload:return
            raise ValueError('Run identity already stored with different bytes')
        fd,name=tempfile.mkstemp(prefix='pending-',suffix='.tmp',dir=self.root)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
            # Exclusive destination creation prevents replacing a concurrent run.
            os.link(name,target)
        finally:
            if os.path.exists(name):os.unlink(name)

    def load(self,run_id):
        try:
            envelope=json.loads(self.path(run_id).read_text(encoding='utf-8'))
            run=envelope['run']
            if (envelope['schema']!='SOLSOL_STORED_V1' or run['run_id']!=run_id or envelope['sha256']!=digest(run)):
                raise ValueError('Run checksum or identity mismatch')
            return run
        except (KeyError,TypeError,json.JSONDecodeError) as exc:raise ValueError('Invalid stored run') from exc

    def list(self):
        result=[]
        for path in sorted(self.root.glob('*.json')):
            try:
                r=self.load(path.stem)
                result.append(dict(run_id=r['run_id'],status=r['status'],nfe=len(r['rows']),
                    experiment_contract_id=r['experiment_contract_id'],archive_count=len(r['archive_ids'])))
            except (ValueError,OSError):
                result.append(dict(run_id=path.stem,status='corrupt'))
        return result
