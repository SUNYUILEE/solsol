"""Owned live binary populations with exact historical public JSON tokens."""
import json
import numpy as np
from .binary_decision import json_default
try:
    import orjson
except ImportError:
    orjson=None

def retain_population(value):
    # Only canonical binary integer producers use private compact storage.
    # All other inputs keep the historical astype(int)/list behavior/errors.
    if value.dtype.kind in 'biu' and np.all((value==0)|(value==1)):
        result=np.array(value,dtype=np.uint8,copy=True,order='C')
        result.flags.writeable=False
        return result
    return value.astype(int).tolist()

def public_checkpoint(value):
    if isinstance(value.get('population_X'),np.ndarray):
        return {k:(v.tolist() if k=='population_X' else v) for k,v in value.items()}
    return value

def checkpoint_text(value):
    pop=value.get('population_X')
    if not isinstance(pop,np.ndarray):
        return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default)
    if (orjson is None or pop.dtype!=np.uint8 or not pop.flags.c_contiguous
            or any(not isinstance(k,str) for k in value)):
        return json.dumps(public_checkpoint(value),ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default)
    binary=orjson.dumps(pop,option=orjson.OPT_SERIALIZE_NUMPY).decode('ascii')
    encode=lambda v:json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default)
    return '{'+','.join(encode(k)+':'+(binary if k=='population_X' else encode(v)) for k,v in value.items())+'}'

class CheckpointJournal(dict):
    """Private writer value; every other field uses the original JSON encoder."""
    def text(self):
        from .binary_decision import json_default
        encode=lambda v:json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default)
        return '{'+','.join(encode(k)+':'+(checkpoint_text(v) if k=='checkpoint' else encode(v)) for k,v in self.items())+'}'
