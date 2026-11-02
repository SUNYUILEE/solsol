"""Stable physical identity and explicit full/active-slot binary codecs."""
import numpy as np
from .contracts import digest

def _ids(values, label):
    values = tuple(values)
    if not values or any(not isinstance(v, str) or not v for v in values) or len(set(values)) != len(values):
        raise ValueError('Invalid or duplicate ' + label)
    return values

class PlacementSpace:
    def __init__(self, candidate_order, sensor_order, dataset_id='explicit-v1', allowed=None,
                 enabled_sensor_ids=None, co_location=True):
        self.candidate_order = _ids(candidate_order, 'candidate IDs')
        self.sensor_order = _ids(sensor_order, 'sensor IDs')
        self.dataset_id = dataset_id
        self.shape = (len(self.candidate_order), len(self.sensor_order))
        self.co_location = bool(co_location)
        enabled = self.sensor_order if enabled_sensor_ids is None else tuple(enabled_sensor_ids)
        if len(set(enabled)) != len(enabled) or set(enabled) - set(self.sensor_order):
            raise ValueError('Unknown or duplicate enabled sensor IDs')
        self.enabled_sensor_ids = enabled
        a = np.ones(self.shape, bool) if allowed is None else np.asarray(allowed)
        if a.shape != self.shape or np.any((a != 0) & (a != 1)):
            raise ValueError('Invalid allowed installation slots')
        self.allowed = a.astype(bool).copy()
        self.allowed &= np.array([s in enabled for s in self.sensor_order])[None, :]
        self.allowed.setflags(write=False)

    def validate(self, X, installation=True):
        a = np.asarray(X)
        if a.shape[-2:] != self.shape or a.ndim not in (2, 3) or np.any((a != 0) & (a != 1)):
            raise ValueError('Expected binary candidate-by-sensor placement')
        if installation and np.any(a * ~self.allowed):
            raise ValueError('Disabled or forbidden installation slot')
        if installation and not self.co_location and np.any(a.sum(axis=-1) > 1):
            raise ValueError('Co-location forbidden')
        return a.astype(np.uint8)

    def from_pairs(self, pairs):
        pairs = [tuple(p) for p in pairs]
        if any(len(p) != 2 for p in pairs) or len(set(pairs)) != len(pairs):
            raise ValueError('Duplicate or invalid physical installation')
        a = np.zeros(self.shape, np.uint8)
        for c, s in pairs:
            if c not in self.candidate_order or s not in self.sensor_order:
                raise ValueError('Unknown installation ID')
            a[self.candidate_order.index(c), self.sensor_order.index(s)] = 1
        return self.validate(a)

    def to_pairs(self, X):
        a = self.validate(X, installation=False)
        if a.ndim != 2:
            raise ValueError('Physical identity requires one placement')
        return sorted((self.candidate_order[i], self.sensor_order[j]) for i, j in np.argwhere(a))

    def placement_hash(self, X):
        return digest(dict(dataset_id=self.dataset_id, installations=self.to_pairs(X)))

    def reorder(self, candidate_order=None, sensor_order=None):
        cs = self.candidate_order if candidate_order is None else tuple(candidate_order)
        ss = self.sensor_order if sensor_order is None else tuple(sensor_order)
        if set(cs) - set(self.candidate_order) or set(ss) - set(self.sensor_order):
            raise ValueError('Unknown reorder/subset ID')
        a = self.allowed[np.ix_([self.candidate_order.index(c) for c in cs], [self.sensor_order.index(s) for s in ss])]
        return PlacementSpace(cs, ss, self.dataset_id, a, [s for s in self.enabled_sensor_ids if s in ss], self.co_location)

class PlacementCodec:
    def __init__(self, space, legacy_full=False):
        self.space = space
        self.legacy_full = bool(legacy_full)
        self.slots = np.arange(np.prod(space.shape)) if legacy_full else np.flatnonzero(space.allowed.ravel())
        self.n_var = len(self.slots)
        self.version = 'legacy-row-major-v1' if legacy_full else 'active-slots-v1'

    def encode(self, X, validate_installation=True):
        a = self.space.validate(X, installation=validate_installation)
        return a.reshape(a.shape[:-2] + (int(np.prod(self.space.shape)),))[..., self.slots]

    def decode(self, z, validate_installation=True):
        z = np.asarray(z)
        if z.ndim not in (1, 2) or z.shape[-1] != self.n_var or np.any((z != 0) & (z != 1)):
            raise ValueError('Invalid binary encoding or dimension')
        a = np.zeros(z.shape[:-1] + (int(np.prod(self.space.shape)),), np.uint8)
        a[..., self.slots] = z
        return self.space.validate(a.reshape(z.shape[:-1] + self.space.shape), installation=validate_installation)

    def raw_encoding_hash(self, z):
        return digest(dict(codec=self.version, candidate_order=self.space.candidate_order,
                           sensor_order=self.space.sensor_order, z=np.asarray(z).tolist()))

def encode(placement, space):
    return PlacementCodec(space).encode(placement)

def decode(z, space):
    return PlacementCodec(space).decode(z)
