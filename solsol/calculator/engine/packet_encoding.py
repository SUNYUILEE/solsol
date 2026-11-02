"""Exact public packet JSON, emitted without a second resident packet graph."""
import json
import numpy as np


def write_packet(session, stream, include_rows=True, compact_checkpoints=False):
    """Write bytes to a caller-owned sink; sink errors may leave partial output.

    packet_bytes publishes only a successful complete buffer. Unsupported
    Unicode retains the original full-encoder exception, including its offset.
    """
    try:
        return _write_packet(session,stream,include_rows,compact_checkpoints)
    except UnicodeEncodeError:
        json.dumps(session.packet(include_rows=include_rows,
                                  compact_checkpoints=compact_checkpoints),
                   ensure_ascii=False).encode('utf-8')
        raise


def _write_packet(session, stream, include_rows=True, compact_checkpoints=False):
    from .run_names import names
    def write(data):
        remaining=memoryview(data)
        while remaining:
            count=stream.write(remaining)
            if count is None or count<=0:raise BlockingIOError('Packet sink made no progress')
            remaining=remaining[count:]
    # Stored sessions are immutable; hold their lock for a consistent name and
    # value snapshot while writing. The ordinary packet() copy contract stays.
    with session.lock:
        result = dict(session.data) if include_rows else {
            k: v for k, v in session.data.items() if k not in ('rows', 'events')}
        if not include_rows:
            result['solver'] = {k: v for k, v in result['solver'].items()
                                if k not in ('auxiliary_evaluations', 'initial_X')}
        result['checkpoints'] = session.checkpoints
        result.update(names(result, session.folder))
        from .binary_decision import json_default
        encode = lambda value: json.dumps(value, ensure_ascii=False,default=json_default).encode('utf-8')
        write(b'{')
        for index, (key, value) in enumerate(result.items()):
            if index:
                write(b', ')
            encoded_key=encode(key) if isinstance(key,str) else json.dumps({key:None},ensure_ascii=False).rsplit(': ',1)[0][1:].encode('utf-8')
            write(encoded_key); write(b': ')
            if key == 'rows' and isinstance(value, list):
                write(b'[')
                for offset in range(0, len(value), 256):
                    if offset:
                        write(b', ')
                    write(encode(value[offset:offset + 256])[1:-1])
                write(b']')
            elif key == 'checkpoints':
                write(b'[')
                for cp_index, original in enumerate(value):
                    if cp_index:
                        write(b', ')
                    cp = {k: v for k, v in original.items()
                          if not compact_checkpoints or k not in ('population_X', 'population_ids')}
                    if isinstance(cp.get('population_X'), np.ndarray):
                        cp['population_X'] = cp['population_X'].tolist()
                    write(encode(cp))
                write(b']')
            else:
                write(encode(value))
        write(b'}')
