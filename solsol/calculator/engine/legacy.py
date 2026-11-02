"""Versioned, read-only historical records. Reading never constructs a solver.

Stored evidence remains usable if its evaluator is no longer installed. Optional
RF spatial replay is lazy, exact-hash gated, and compared to the stored row.
"""
from __future__ import annotations
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
import zipfile
import numpy as np


class UnsupportedLegacySchema(ValueError):
    pass


class LegacyIntegrityError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _json(path):
    try:
        return json.loads(path.read_bytes())
    except (ValueError, OSError) as exc:
        raise LegacyIntegrityError(f'Cannot read {path.name}: {exc}') from exc


def _verify_files(folder, files):
    for name, sha in files.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            raise LegacyIntegrityError('Missing or unsafe artifact: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise LegacyIntegrityError('Artifact checksum mismatch: ' + name)


class LegacyRecord:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.id = self.folder.name
        self._views = {}
        self._spatial = {}
        self._model = None
        self._replay_attempted = False
        self.replay_status = 'NOT_REQUESTED'
        self.integrity_status = 'CHECKSUM_VERIFIED'
        if (self.folder / 'raw.json').is_file():
            self._read_rf()
        elif (self.folder / 'raw.npz').is_file():
            self._read_eoir()
        else:
            raise UnsupportedLegacySchema('No supported legacy raw artifact')

    def _read_rf(self):
        self._raw_bytes = (self.folder / 'raw.json').read_bytes()
        self.base = _json(self.folder / 'raw.json')
        p = self.base
        self.config = p.get('config', {})
        version = self.config.get('evaluator_version')
        expected = {'rf-information-candidate-1': None, 'rf-common-information-v2': 'rf-common-runtime-v1', 'rf-common-information-v3': 'rf-common-runtime-v3'}
        if version not in expected or p.get('runtime_version') != expected[version]:
            raise UnsupportedLegacySchema('Unsupported RF evaluator/runtime schema')
        self.cid = 'RADAR_RF_SCANNER'
        self.schema = version
        if p.get('experiment_contract_id') != self.cid or p.get('run_id') != self.id or _digest(self.config) != p.get('config_sha256'):
            raise LegacyIntegrityError('RF identity/config mismatch')
        self.state = p['state']
        manifest = self.folder / 'manifest.json'
        if manifest.exists():
            m = _json(manifest)
            if m.get('raw_sha256') != hashlib.sha256(self._raw_bytes).hexdigest() or any(m.get(k) != p.get(k) for k in ('run_id', 'experiment_contract_id', 'state', 'config_sha256')):
                raise LegacyIntegrityError('RF manifest mismatch')
        elif self.state in ('completed', 'cancelled'):
            raise LegacyIntegrityError('Terminal RF manifest missing')
        else:
            self.integrity_status = 'UNSEALED_NONTERMINAL_RAW'
        self.rows = p['rows']
        self.snapshots = p['checkpoints']
        self.problem = p['problem']
        n = len(self.problem['sites'])
        k = 3 if version.endswith('v3') else 1
        for i, row in enumerate(self.rows):
            x = np.asarray(row['X'])
            if row.get('id') != i or row.get('run_id') != self.id or x.shape != (n, 2) or np.any((x != 0) & (x != 1)):
                raise LegacyIntegrityError('RF raw row identity/shape mismatch')
            if len(row['F']) != 3 or len(row['G']) != k or not np.isfinite(row['F'] + row['G']).all():
                raise LegacyIntegrityError('RF raw F/G malformed')
            if any(row.get(key) != p.get(key) for key in ('experiment_contract_id', 'config_sha256', 'evaluator_sha256')) or row.get('decision_sha256') != _digest(row['X']):
                raise LegacyIntegrityError('RF raw row binding mismatch')
        previous = 0
        for cp in self.snapshots:
            if not previous <= cp['nfe'] <= len(self.rows) or any(type(i) is not int or not 0 <= i < cp['nfe'] for i in cp['archive_ids']):
                raise LegacyIntegrityError('RF checkpoint index mismatch')
            previous = cp['nfe']

    def _read_eoir(self):
        self.cid = 'RADAR_EOIR'
        self.manifest = m = _json(self.folder / 'manifest.json')
        publication = m.get('publication_contract')
        if publication not in (None, 'append-only-commit-v1'):
            raise UnsupportedLegacySchema('Unsupported EOIR publication schema')
        _verify_files(self.folder, m['files'])
        self.config = _json(self.folder / 'config.json')
        self.schema = self.config.get('objective_contract', 'binary_coverage_v1')
        if self.schema not in ('binary_coverage_v1', 'max_margin_quality_v3', 'zoned_nominal_v4', 'full_area_tradeoff_v6', 'layered_mission_v7'):
            raise UnsupportedLegacySchema('Unsupported EOIR objective schema')
        binding_path = self.folder / 'experiment_binding.json'
        if binding_path.exists():
            b = _json(binding_path)
            if b.get('experiment_contract_id') != self.cid or b.get('run_id') != self.id or b.get('config') != self.config:
                raise LegacyIntegrityError('EOIR experiment binding mismatch')
            _verify_files(self.folder, b['files'])
        self.base = _json(self.folder / 'result.json')
        self.problem = _json(self.folder / 'problem.json')
        self.snapshots = _json(self.folder / 'checkpoints.json')
        self.state = m['state']
        if m.get('id') != self.id or self.base.get('id') != self.id or self.base.get('state') != self.state:
            raise LegacyIntegrityError('EOIR result identity mismatch')
        if publication:
            marker = _json(self.folder / 'completion.json')
            if marker.get('schema') != publication or marker.get('run_id') != self.id:
                raise LegacyIntegrityError('EOIR completion identity mismatch')
            _verify_files(self.folder, {'manifest.json': marker['manifest_sha256'], 'result.json': marker['result_sha256']})
        elif (self.folder / 'completion.json').exists() or 'live_publication.py' in m.get('code_sha256', {}):
            raise LegacyIntegrityError('EOIR publication downgrade')
        with np.load(self.folder / 'raw.npz', allow_pickle=False) as raw:
            self.X, self.F, self.G = (raw[k] for k in ('X', 'F', 'G'))
        count = len(self.X)
        if self.X.shape != (count, len(self.problem['sites']), 2) or self.F.shape != (count, 3) or self.G.ndim != 2 or len(self.G) != count or not np.isfinite(self.F).all() or not np.isfinite(self.G).all() or np.any((self.X != 0) & (self.X != 1)):
            raise LegacyIntegrityError('EOIR raw shape/value mismatch')
        for cp in self.snapshots:
            if not 0 <= cp['evaluations'] <= count or any(not 0 <= i < cp['evaluations'] for key in ('population_ids', 'front_ids', 'archive_ids') for i in cp.get(key, [])):
                raise LegacyIntegrityError('EOIR checkpoint mismatch')
        self.replay_status = 'STORED_METRICS_NO_EVALUATOR_REQUIRED'

    def packet(self, include_rows=True):
        base=self.base if include_rows else {k:v for k,v in self.base.items() if k!='rows'}
        return copy.deepcopy(dict(base, experiment_contract_id=self.cid, run_id=self.id, legacy_schema=self.schema, integrity_status=self.integrity_status, replay_status=self.replay_status))

    def _rf_spatial(self, row):
        if 'radar_point_quality' in row or self.schema == 'rf-information-candidate-1':
            return copy.deepcopy(row)
        if row['id'] in self._spatial:
            return copy.deepcopy(self._spatial[row['id']])
        if not self._replay_attempted:
            self._replay_attempted = True
            module = 'rf_common_v3_contract' if self.schema.endswith('v3') else 'rf_common_contract'
            try:
                candidate = importlib.import_module(module).CommonRFModel(copy.deepcopy(self.config))
                if candidate.evaluator_hash == self.base['evaluator_sha256'] and candidate.config_hash == self.base['config_sha256'] and candidate.problem() == self.problem:
                    self._model = candidate
                    self.replay_status = 'EXACT_EVALUATOR_AVAILABLE'
                else:
                    self.replay_status = 'EVALUATOR_SOURCE_UNAVAILABLE'
            except (ImportError, ValueError, OSError):
                self.replay_status = 'EVALUATOR_SOURCE_UNAVAILABLE'
        if self._model is not None:
            fresh = self._model.row(row['X'], spatial=True)
            if any(fresh[k] != row[k] for k in ('F', 'G', 'decision_sha256')):
                raise LegacyIntegrityError('Exact RF spatial replay differs from raw F/G')
            value = dict(row, **fresh)
            from .store import record_derivation
            record_derivation(self,'LEGACY_MAP_REPLAY',dict(raw_id=row['id']),1,dict(status='EXACT_STORED_MODEL_XFG_MATCH'))
        else:
            size = len(self.problem['demand'])
            value = dict(row, spatial_status='UNAVAILABLE_EVALUATOR_SOURCE', rf_status=['UNAVAILABLE_EVALUATOR_SOURCE'] * size, **{k: [None] * size for k in ('radar_rmse_lower_bound_m', 'rf_rmse_lower_bound_m', 'radar_point_quality', 'rf_point_quality')})
        self._spatial[row['id']] = value
        return copy.deepcopy(value)

    def point(self, i, generation=None):
        self._prime_points([i])
        return copy.deepcopy(self._decoded_rows[int(i)])

    def _prime_points(self,ids):
        from model_derived_api import call
        if not hasattr(self,'_decoded_rows'):self._decoded_rows={}
        missing=sorted({int(i) for i in ids}-set(self._decoded_rows))
        for start in range(0,len(missing),512):
            batch=missing[start:start+512]
            rows=call('legacy_eoir_rows',self.schema,[dict(id=i,X=self.X[i],F=self.F[i],G=self.G[i]) for i in batch])
            if len(rows)!=len(batch) or {r['id'] for r in rows}!=set(batch):raise LegacyIntegrityError('Legacy model decode row IDs')
            for r in rows:
                i=r['id']
                if not np.array_equal(r['F'],self.F[i]) or not np.array_equal(r['G'],self.G[i]) or not np.array_equal(r['mask'],self.X[i]@[1,2]):raise LegacyIntegrityError('Legacy model decode changed raw values')
                self._decoded_rows[i]=r

    def view(self, generation=None):
        key = None if generation is None else int(generation)
        if key in self._views:
            return copy.deepcopy(self._views[key])
        p = self.packet(include_rows=False)
        if self.cid == 'RADAR_RF_SCANNER':
            cp = self.snapshots[-1 if key is None else key] if self.snapshots else None
            p.pop('rows', None)
            p.update(generation=None if cp is None else cp['generation'], nfe=len(self.rows), archive=[] if cp is None else [self._rf_spatial(self.rows[i]) for i in cp['archive_ids']], initial_archive=[] if not self.snapshots else [self._rf_spatial(self.rows[i]) for i in self.snapshots[0]['archive_ids']], hamming_clusters=[], independent_reference_count=None)
            p['target_count'] = None if self.config.get('targets') is None else sum(bool(r['qualified']) for r in p['archive'])
            if p['archive']:
                from hamming_posthoc import complete_link
                p['hamming_clusters'] = [list(v) for v in complete_link(np.asarray([r['X'] for r in p['archive']]), range(len(p['archive'])), 3)]
        else:
            cp = copy.deepcopy(self.snapshots[-1 if key is None else min(max(0, key), len(self.snapshots)-1)]) if self.snapshots else None
            if cp is not None:
                from live_empirical_archive import cumulative_archive_ids
                stop = cp['evaluations']
                # Already schema/checksum validated arrays. Preserve rejection of
                # inconsistent repeated feasible X without per-row Python objects.
                eligible=np.flatnonzero(np.all(self.G[:stop]<=1e-12,axis=1))
                if len(eligible):
                    packed=np.packbits(self.X[eligible].reshape(len(eligible),-1),axis=1)
                    _,first,inverse=np.unique(packed,axis=0,return_index=True,return_inverse=True)
                    representatives=eligible[first[inverse]]
                    if not np.array_equal(self.F[eligible],self.F[representatives]) or not np.array_equal(self.G[eligible],self.G[representatives]):
                        raise LegacyIntegrityError('Same physical placement has inconsistent F/G')
                cp['archive_ids'] = list(map(int,cumulative_archive_ids(self.X,self.F,self.G,stop)))
                cp['archive_ids'].sort(key=lambda i: (self.F[i, 2], self.F[i, 0], self.F[i, 1], i))
                cp['archive_scope'] = 'observed_feasible_unique_x_empirically_nondominated_through_generation'
                self._prime_points(cp['archive_ids']+cp['population_ids']+([] if cp.get('representative_id') is None else [cp['representative_id']]))
            p.update(problem=copy.deepcopy(self.problem), snapshot=cp, points=[] if cp is None else [self.point(i) for i in cp['archive_ids']], current_population_points=[] if cp is None else [self.point(i) for i in cp['population_ids']], representative=None if cp is None or cp.get('representative_id') is None else self.point(cp['representative_id']), latest_generation=len(self.snapshots)-1)
        p['replay_status'] = self.replay_status
        self._views[key] = copy.deepcopy(p)
        return p

    status = view

    def export_bytes(self):
        """Original RF bytes or a ZIP of original EOIR member bytes."""
        if self.cid == 'RADAR_RF_SCANNER':
            return self._raw_bytes, self.id + '.json', 'application/json'
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.folder.iterdir()):
                if path.is_file():
                    archive.writestr(path.name, path.read_bytes())
        return data.getvalue(), self.id + '.zip', 'application/zip'


def read_legacy(folder):
    return LegacyRecord(folder)
