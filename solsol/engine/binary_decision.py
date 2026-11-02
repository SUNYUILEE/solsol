"""Private immutable binary decisions; public values remain ordinary lists."""
import json
import operator


class BinaryDecision:
    __slots__ = ('_data', '_rows', '_columns')
    __hash__ = None

    def __init__(self, data, shape):
        if type(data) is not bytes:
            raise TypeError('owned immutable bytes required')
        if (type(shape) is not tuple or len(shape) != 2 or
                any(type(size) is not int or size < 0 for size in shape)):
            raise ValueError('two exact nonnegative integer dimensions required')
        rows, columns = shape
        if len(data) != rows * columns or data.count(b'\x00') + data.count(b'\x01') != len(data):
            raise ValueError('invalid binary matrix bytes')
        object.__setattr__(self, '_data', data)
        object.__setattr__(self, '_rows', rows)
        object.__setattr__(self, '_columns', columns)

    def __setattr__(self, name, value):raise AttributeError('immutable BinaryDecision')
    def __delattr__(self, name):raise AttributeError('immutable BinaryDecision')
    def __len__(self):return self._rows
    def _row(self, index):
        start=index*self._columns
        return list(self._data[start:start+self._columns])
    def __iter__(self):
        for index in range(self._rows):yield self._row(index)
    def __getitem__(self, index):
        if isinstance(index,slice):return [self._row(i) for i in range(*index.indices(self._rows))]
        index=operator.index(index)
        if index<0:index+=self._rows
        if not 0<=index<self._rows:raise IndexError('BinaryDecision row index out of range')
        return self._row(index)
    def tolist(self):return self.__array__().tolist()
    def __deepcopy__(self,memo):
        if id(self) not in memo:memo[id(self)]=self.tolist()
        return memo[id(self)]
    def __array__(self,dtype=None,copy=None):
        import numpy as np
        result=np.frombuffer(self._data,dtype=np.uint8).reshape((self._rows,self._columns))
        target=result.dtype if dtype is None else np.dtype(dtype)
        if target!=result.dtype:
            if copy is False:raise ValueError('dtype conversion requires a copy')
            return result.astype(target,copy=True)
        return result.copy() if copy is True else result
    def __eq__(self,other):
        if isinstance(other,BinaryDecision):return (self._rows,self._columns,self._data)==(other._rows,other._columns,other._data)
        if type(other) is list:return self.tolist()==other
        return NotImplemented
    def __ne__(self,other):
        value=self.__eq__(other)
        return NotImplemented if value is NotImplemented else not value


def json_default(value):
    if isinstance(value,BinaryDecision):return value.tolist()
    # Preserve stdlib rejection for every unknown type; no ndarray coercion.
    return json.JSONEncoder().default(value)


def public_rows(rows):
    if not any(isinstance(row.get('X'),BinaryDecision) for row in rows):return rows
    return [dict(row,X=row['X'].tolist()) if isinstance(row.get('X'),BinaryDecision) else row for row in rows]


def retain_decision(value):
    """Only the exact canonical integer JSON matrix receives private storage."""
    import numpy as np
    try:
        import orjson
        if type(value) is not list or not value or any(type(site) is not list for site in value):return value
        x=np.asarray(value)
        if x.ndim!=2 or x.dtype.kind not in 'iu' or np.any((x!=0)&(x!=1)):return value
        x=np.asarray(x,dtype=np.uint8,order='C')
        if orjson.dumps(value)!=orjson.dumps(x,option=orjson.OPT_SERIALIZE_NUMPY):return value
        return BinaryDecision(x.tobytes(),x.shape)
    except (ImportError,TypeError,ValueError,OverflowError):return value
