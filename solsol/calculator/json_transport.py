"""Lossless compression for large JSON responses, negotiated per request."""
import gzip
import json


class NotAcceptableEncoding(ValueError):
    pass


def encode_response(obj,accept_encoding=''):
    data=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode('utf-8')
    qualities={}
    for item in accept_encoding.split(','):
        parts=[p.strip().lower() for p in item.split(';')]
        quality=1.0
        for parameter in parts[1:]:
            if parameter.startswith('q='):
                try:quality=float(parameter[2:])
                except ValueError:quality=0.0
        qualities.setdefault(parts[0],quality if 0<=quality<=1 else 0.0)
    gzip_ok=qualities.get('gzip',qualities.get('*',0))>0
    identity_ok=qualities.get('identity',0 if qualities.get('*')==0 else 1)>0
    if not gzip_ok and not identity_ok:raise NotAcceptableEncoding('No acceptable response encoding')
    if gzip_ok and (len(data)>=65536 or not identity_ok):
        packed=gzip.compress(data,compresslevel=1,mtime=0)
        if len(packed)<len(data) or not identity_ok:return packed,'gzip'
    return data,None
