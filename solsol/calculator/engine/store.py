"""Single run storage contract with immutable checkpoints and atomic commit marker."""
import hashlib,json,os,math,re,codecs,tempfile
from contextlib import contextmanager
from pathlib import Path
from .binary_decision import json_default
try:
    import orjson as _fast_json
except ImportError:
    _fast_json=None
try:
    import msgspec as _projection_json
except ImportError:
    _projection_json=None

if _projection_json is not None:
    from typing import Any
    class _CheckpointHeader(_projection_json.Struct):
        schema:Any=None
        run_id:Any=None
        checkpoint:Any=None
    _checkpoint_decoder=_projection_json.json.Decoder(_CheckpointHeader)
    class _CheckpointBinding(_projection_json.Struct):
        schema:Any=None
        run_id:Any=None
        checkpoint:_projection_json.Raw=None
    _checkpoint_binding_decoder=_projection_json.json.Decoder(_CheckpointBinding)
else:
    _checkpoint_decoder=None
    _checkpoint_binding_decoder=None

# Keep the previous parser's exact floating-point conversion for *each* token,
# including very long decimal midpoint spellings. The full object graph uses
# msgspec's smaller allocation strategy; precision is not traded for memory.
_raw_json_decoder=(_projection_json.json.Decoder(float_hook=_fast_json.loads)
                   if _projection_json is not None and _fast_json is not None else None)

_DIGIT_MASK=bytes(1 if 48<=c<=57 else 0 for c in range(256))

def _has_large_integer(data):
    # Translation and substring search run in C. A regex testing nineteen
    # digits at each byte was slower than the JSON decoder on large ledgers.
    mask=data.translate(_DIGIT_MASK);start=mask.find(b'\1'*19)
    while start>=0:
        end=mask.find(b'\0',start+19)
        if end<0:end=len(data)
        before=start-1
        if before>=0 and data[before]==45:before-=1
        while before>=0 and data[before] in b' \t\r\n':before-=1
        after=end
        while after<len(data) and data[after] in b' \t\r\n':after+=1
        if (before<0 or data[before] in b':[,') and (after==len(data) or data[after] in b',]}'):return True
        start=mask.find(b'\1'*19,end)
    return False

def decode_saved_json(data):
    """Fast UTF-8 JSON with the historical integer/exception semantics.

    Full untyped msgspec decoding uses orjson's float hook to retain the prior
    token conversion exactly. orjson rounds integers beyond 64 bits; use stdlib for any
    19+-digit integer token; decimal fractions and quoted hashes aren't tokens.
    A string resembling such a token may choose the slower path harmlessly.
    """
    if _fast_json is not None:
        if not _has_large_integer(data):
            # The full untyped decoder retains every raw field. Its allocation
            # strategy avoids orjson's large transient arena on long ledgers.
            # Compatibility extensions still use the historical stdlib path.
            if _raw_json_decoder is not None:
                try:return _raw_json_decoder.decode(data)
                except (_projection_json.DecodeError,UnicodeDecodeError):pass
            try:return _fast_json.loads(data)
            except _fast_json.JSONDecodeError:pass
    return json.loads(data.decode('utf-8'))


def decode_terminal_checkpoint(data):
    """Validate the entire document, materializing only committed bindings.

    This is used only after the member's original SHA-256 has been checked.
    Interrupted journals still need every field and use decode_saved_json.
    Unknown strings in msgspec's skip path don't validate UTF-8, so validate
    the whole byte buffer first. Large integers and compatibility extensions
    (NaN, lone surrogates, etc.) retain the historical decoder/error behavior.
    """
    if _checkpoint_decoder is not None and not _has_large_integer(data):
        data.decode('utf-8')
        try:
            p=_checkpoint_decoder.decode(data)
        except _projection_json.DecodeError:
            pass
        else:
            return dict(schema=p.schema,run_id=p.run_id,checkpoint=p.checkpoint)
    return decode_saved_json(data)

def _validate_utf8(data):
    """Strict whole-buffer check with bounded temporary Unicode storage."""
    decoder=codecs.getincrementaldecoder('utf-8')()
    view=memoryview(data)
    try:
        for start in range(0,len(data),1048576):decoder.decode(view[start:start+1048576],final=False)
        decoder.decode(b'',final=True)
    except UnicodeDecodeError:
        # Preserve the historical exception's whole-document byte offsets.
        data.decode('utf-8')


def validate_terminal_checkpoint(data,run_id,expected,*,json_native=False):
    # The caller has checked the original member SHA. Validate every byte of
    # JSON and UTF-8, but avoid rebuilding a duplicate checkpoint object graph
    # when its exact canonical bytes already prove the complete binding.
    if json_native and _fast_json is not None and _checkpoint_binding_decoder is not None and not _has_large_integer(data):
        try:
            _validate_utf8(data)
            p=_checkpoint_binding_decoder.decode(data)
            if p.schema==SCHEMA and p.run_id==run_id and p.checkpoint is not None:
                encoded=_fast_json.dumps(expected)
                # orjson maps nonfinite values to null. Conservatively retain
                # the original comparison whenever any null spelling occurs.
                if b'null' not in encoded and bytes(p.checkpoint)==encoded:return
        except (_projection_json.DecodeError,UnicodeError,ValueError,TypeError,RecursionError):pass
    # Noncanonical spellings, missing fields, unusual numbers and extensions
    # keep the existing decoded-value comparison and exact failure behavior.
    saved=decode_terminal_checkpoint(data)
    if saved.get('schema')!=SCHEMA or saved.get('run_id')!=run_id or saved.get('checkpoint')!=expected:
        raise ValueError('INTEGRITY_ERROR: checkpoint payload')


def share_row_strings(rows):
    """Share immutable text within one verified read, never mutable containers."""
    if not rows:return
    # Discover repeated text paths once. Walking every numeric field and
    # pooling every unique placement hash made this compaction itself costly.
    # Omitted paths simply retain their original strings and values.
    paths=[];pending=[((),rows[0])]
    while pending:
        prefix,current=pending.pop()
        for key,value in current.items():
            path=prefix+(key,)
            if isinstance(value,dict):pending.append((path,value))
            elif type(value) is str:
                other=rows[min(1,len(rows)-1)]
                for part in path:
                    other=other.get(part) if isinstance(other,dict) else None
                if type(other) is str and other==value:paths.append(path)
    # Flat metadata dominates the ledger. Avoid a tuple slice and empty
    # ancestor traversal for each scalar; nested paths retain original order.
    flat=[path[0] for path in paths if len(path)==1]
    nested=[]
    for path in paths:
        if len(path)==1:continue
        prefix=path[:-1]
        if not nested or nested[-1][0]!=prefix:nested.append((prefix,[]))
        nested[-1][1].append(path[-1])
    pool={}
    for row in rows:
        for key in flat:
            value=row.get(key)
            if type(value) is str:row[key]=pool.setdefault(value,value)
        for prefix,keys in nested:
            current=row
            for key in prefix:
                current=current.get(key)
                if not isinstance(current,dict):break
            else:
                for key in keys:
                    value=current.get(key)
                    if type(value) is str:current[key]=pool.setdefault(value,value)


SCHEMA='SOLSOL_ENGINE_RUN_V1'
JOURNAL_V1='SOLSOL_CHECKPOINT_DELTA_V1'
JOURNAL_V2='SOLSOL_CHECKPOINT_DELTA_V2'
CHECKPOINT_ROOT_V2='SOLSOL_ENGINE_CHECKPOINT_ROOT_V2'
COMMIT_INTENT='SOLSOL_TERMINAL_COMMIT_INTENT_V1'
_JOURNAL_RESERVED={'rows','events','checkpoints','checkpoint_storage'}

def journal_metadata_checksum(encoded):
    checksum=hashlib.sha256()
    for key in sorted(encoded):
        checksum.update(json.dumps(key,ensure_ascii=False).encode('utf-8'))
        checksum.update(b':');checksum.update(encoded[key].encode('utf-8'));checksum.update(b'\n')
    return checksum.hexdigest()

def journal_metadata_delta(metadata,previous):
    # Compare serialized values, not Python equality: 0/-0.0, bool/int and
    # arbitrarily large integers must retain their exact JSON representation.
    encoded={k:json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default) for k,v in metadata.items()}
    changed=metadata if previous is None else {k:v for k,v in metadata.items() if previous.get(k)!=encoded[k]}
    removed=[] if previous is None else [k for k in previous if k not in encoded]
    return changed,removed,encoded

def restore_journal_metadata(saved,packet,generation,encoded_cache=None):
    metadata=saved.get('metadata');removed=saved.get('metadata_removed')
    expected_mode='full' if generation==0 else 'delta'
    if (saved.get('metadata_mode')!=expected_mode or not isinstance(metadata,dict) or
        not isinstance(removed,list) or any(not isinstance(k,str) for k in removed) or
        len(set(removed))!=len(removed) or set(metadata)&set(removed) or
        (_JOURNAL_RESERVED & (set(metadata)|set(removed))) or (generation==0 and removed)):
        raise ValueError('INTEGRITY_ERROR: checkpoint metadata delta')
    result=({} if generation==0 else {k:v for k,v in packet.items() if k not in _JOURNAL_RESERVED})
    if any(k not in result for k in removed):raise ValueError('INTEGRITY_ERROR: checkpoint metadata removal')
    for key in removed:del result[key]
    result.update(metadata)
    # The reader's private cache contains encoded values from the preceding
    # verified checkpoint. Re-encode changed fields only, not multi-MB solver
    # ledgers again for every generation during interrupted recovery.
    encoded=(dict(encoded_cache) if generation>0 and encoded_cache is not None else journal_metadata_delta(result,None)[2])
    if generation>0 and encoded_cache is not None:
        for key in removed:del encoded[key]
        encoded.update(journal_metadata_delta(metadata,None)[2])
    if saved.get('metadata_sha256')!=journal_metadata_checksum(encoded):
        raise ValueError('INTEGRITY_ERROR: checkpoint metadata checksum')
    if encoded_cache is not None:encoded_cache.clear();encoded_cache.update(encoded)
    return result

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=json_default).encode()).hexdigest()

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Keep staged JSON in a separate same-volume directory. This also avoids
    # treating partially written diagnostics/checkpoints as published members.
    staging=path.parent/'.pending';staging.mkdir(exist_ok=True)
    tmp=staging/path.name
    with tmp.open('w',encoding='utf-8') as f:
        from .live_checkpoint import CheckpointJournal
        text=value.text() if isinstance(value,CheckpointJournal) else json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default)
        f.write(text);f.flush();os.fsync(f.fileno())
    tmp.replace(path)

def sha(path):
    checksum=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1048576),b''):checksum.update(block)
    return checksum.hexdigest()


def checked_checkpoint_bytes(folder,items):
    """Read every declared member with bounded IO overlap; never cache trust."""
    def read(item):
        name,expected=item
        if Path(name).name!=name:raise ValueError('INTEGRITY_ERROR: checkpoint checksum')
        data=(folder/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('INTEGRITY_ERROR: checkpoint checksum')
        return name,data
    items=list(items)
    if len(items)<16:
        yield from map(read,items)
        return
    from concurrent.futures import ThreadPoolExecutor
    from collections import deque
    # Eight pending futures plus the current decode buffer; checks stay ordered.
    with ThreadPoolExecutor(max_workers=8,thread_name_prefix='checkpoint-read') as pool:
        pending=deque();iterator=iter(items)
        for _ in range(8):pending.append(pool.submit(read,next(iterator)))
        while pending:
            result=pending.popleft().result()
            item=next(iterator,None)
            if item is not None:pending.append(pool.submit(read,item))
            yield result

@contextmanager
def terminal_commit_lock(folder):
    """Cross-process commit/recovery exclusion, released by OS on process exit."""
    path=Path(folder)/'.terminal-commit.lock'
    with path.open('a+b') as f:
        if f.seek(0,os.SEEK_END)==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

class EncodedRows:
    """Session-local certificates of the append-only ledger, never a disk cache.

    The runtime appends finalized evaluation rows and never edits them. Detect
    replacement/truncation on every publication and verify content at commit.
    """
    def __init__(self,checkpoints=False,spool=False):
        self.references=[];self.chunks=[];self.companions={};self.checkpoints=checkpoints
        self._spool_enabled=spool;self._spool_disabled=False;self._spool=None;self._positions=[];self._published_end=0
    def close(self):
        source=self._spool;self._spool=None;self._spool_disabled=True
        if source is not None:
            try:source.close()
            except OSError:pass
        for cached in self.companions.values():cached.close()
    def __del__(self):
        if getattr(self,'_spool',None) is not None:self.close()
    def _spool_chunk(self,chunk,offset):
        if not self._spool_enabled or self._spool_disabled:return None
        try:
            if self._spool is None:self._spool=tempfile.TemporaryFile(mode='w+b')
            self._spool.seek(offset);remaining=memoryview(chunk)
            while remaining:
                count=self._spool.write(remaining)
                if count is None or count<=0:raise OSError('Private encoding spool made no progress')
                remaining=remaining[count:]
            return offset,len(chunk)
        except (OSError,ValueError):
            self.close();return None
    def _text(self,rows):
        if self.checkpoints:
            from .live_checkpoint import checkpoint_text
            return '['+','.join(checkpoint_text(row) for row in rows)+']'
        from .binary_decision import BinaryDecision
        if _fast_json is not None and rows and all(type(row) is dict and
                all(type(key) is str for key in row) and type(row.get('X')) is BinaryDecision for row in rows):
            # Only immutable, constructor-certified binary decisions use native
            # encoding. Metadata keeps stdlib token, integer and error semantics.
            # Assemble Unicode for the entire original chunk before UTF-8 so
            # lone-surrogate errors keep their whole-chunk offsets.
            try:
                import numpy as np
                marker='\x00SOLSOL_PRIVATE_BINARY_X\x00'
                token=json.dumps(marker,ensure_ascii=False)
                metadata=[{key:(marker if key=='X' else value) for key,value in row.items()} for row in rows]
                text=json.dumps(metadata,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default)
                parts=text.split(token)
                # A user metadata key/value may legitimately equal our marker.
                # Such a collision always retains the original whole encoder.
                if len(parts)==len(rows)+1:
                    pieces=[parts[0]]
                    for row,part in zip(rows,parts[1:]):
                        pieces.append(_fast_json.dumps(np.asarray(row['X']),option=_fast_json.OPT_SERIALIZE_NUMPY).decode('ascii'))
                        pieces.append(part)
                    return ''.join(pieces)
            except (TypeError,ValueError,OverflowError,RecursionError,UnicodeError):
                # Re-run the whole original group to preserve error precedence,
                # cycle detection and unsupported metadata/default behavior.
                pass
        return json.dumps(rows,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default)
    def update(self,rows,verify=False):
        if len(rows)<len(self.references) or any(a is not b for a,b in zip(self.references,rows)):
            raise ValueError('INTEGRITY_ERROR: raw ledger is not append-only')
        # Keep each actual append boundary, not a re-partition of all rows.
        # Certificates retain no complete encoded ledger beside the live rows.
        # Verify before changing either list so failures leave it reusable.
        if verify:
            for start,count,certificate in self.chunks:
                chunk=self._text(rows[start:start+count])[1:-1].encode('utf-8')
                if hashlib.sha256(chunk).digest()!=certificate:raise ValueError('INTEGRITY_ERROR: previously published raw row changed')
        added=rows[len(self.references):]
        if added:
            # Terminal publication can add 100,000 rows at once. Bound temporary
            # Unicode/UTF-8 copies instead of materializing the whole raw ledger.
            new_chunks=[];positions=[];offset=self._published_end;size=1 if self.checkpoints else 256
            for start in range(0,len(added),size):
                group=added[start:start+size]
                chunk=self._text(group)[1:-1].encode('utf-8')
                new_chunks.append((len(self.references)+start,len(group),hashlib.sha256(chunk).digest()))
                positions.append(self._spool_chunk(chunk,offset));offset+=len(chunk)
            self.chunks.extend(new_chunks)
            self.references.extend(added)
            self._positions.extend(positions);self._published_end=offset
    def encoded(self,verify_current=True):
        yield b'['
        for i,(start,count,certificate) in enumerate(self.chunks):
            chunk=None
            if not verify_current and self._spool is not None and self._positions[i] is not None:
                try:
                    offset,length=self._positions[i];self._spool.seek(offset);candidate=self._spool.read(length)
                    if len(candidate)!=length or hashlib.sha256(candidate).digest()!=certificate:raise OSError('Private encoding spool checksum')
                    chunk=candidate
                except (OSError,ValueError):self.close()
            if chunk is None:
                chunk=self._text(self.references[start:start+count])[1:-1].encode('utf-8')
                if hashlib.sha256(chunk).digest()!=certificate:raise ValueError('INTEGRITY_ERROR: previously published raw row changed')
            if i:yield b','
            yield chunk
        yield b']'

def atomic_run_json(path,packet,encoded_rows,verify=False,before_publish=None,*,_verified_snapshot=False):
    """Publish the unchanged V1 JSON bytes; only encoding work is incremental."""
    encoded_rows.update(packet['rows'],verify=verify)
    sequences={'rows':encoded_rows}
    # Runtime event and checkpoint dictionaries are also finalized before append.
    # Mutable state/counters/audit and all other metadata are encoded each time.
    for key in ('events','checkpoints'):
        if key in packet:
            cached=encoded_rows.companions.setdefault(key,EncodedRows(checkpoints=key=='checkpoints',spool=encoded_rows._spool_enabled))
            cached.update(packet[key],verify=verify);sequences[key]=cached
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    staging=path.parent/'.pending';staging.mkdir(exist_ok=True);tmp=staging/path.name
    checksum=hashlib.sha256()
    with tmp.open('wb') as f:
        def write(chunk):
            f.write(chunk);checksum.update(chunk)
        write(b'{')
        for i,(key,value) in enumerate(packet.items()):
            if i:write(b',')
            write(json.dumps(key,ensure_ascii=False).encode('utf-8')+b':')
            if key in sequences:
                for chunk in sequences[key].encoded(verify_current=not(_verified_snapshot and verify)):write(chunk)
            else:write(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_default).encode('utf-8'))
        write(b'}');f.flush();os.fsync(f.fileno())
    if before_publish is not None:before_publish(checksum.hexdigest())
    tmp.replace(path)
    return checksum.hexdigest()

def record_derivation(session,kind,target,evaluations,payload,status='COMPLETED'):
    """Append-only provenance envelope for a fixed-model posthoc operation."""
    import uuid
    if type(evaluations) is not int or evaluations<0:raise ValueError('Invalid derived evaluation count')
    # Only immutable identity is needed. Copying all population checkpoints here
    # made each selected map row pay for the complete optimization history.
    p=getattr(session,'frozen_problem',None)
    if p is None:p=session.packet(include_rows=False)
    raw=session.folder/'raw.json'
    if not raw.is_file():raise ValueError('DERIVATION_PARENT_NOT_SAVED')
    parent=dict(experiment_contract_id=session.cid,run_id=session.id,config_sha256=p['config_sha256'],evaluator_sha256=p['evaluator_sha256'],raw_sha256=sha(raw))
    manifest=session.folder/'manifest.json'
    if manifest.is_file():parent['manifest_sha256']=sha(manifest)
    if status not in ('COMPLETED','ERROR'):raise ValueError('Invalid derivation status')
    d=dict(schema='SOLSOL_DIAGNOSTIC_SIDECAR_V1',parent=parent,kind=kind,target=target,evaluations=evaluations,status=status,provenance='POSTHOC_DERIVATION_NOT_OPTIMIZER',payload=payload)
    d['sha256']=digest(d)
    path=session.folder/'diagnostics'/(str(uuid.uuid4())+'.json');atomic_json(path,d)
    return dict(path=path.name,sha256=sha(path),evaluations=evaluations,parent=parent)


def validate_row_metadata(rows,index,c,p):
    """Reuse checked binary decisions in bounded batches; preserve row rules."""
    import numpy as np
    mask=None
    if rows and c.get('installation_domain'):
        mask=~np.asarray(c['allowed'],dtype=bool)
    for start in range(0,len(rows),256):
        group=rows[start:start+256]
        # Invalid ordering must hit the original identity rejection before lookup.
        ordered=all(r['id']==start+j for j,r in enumerate(group))
        if ordered:
            xbatch=np.asarray([index.decisions[start+j] for j in range(len(group))])
            counts=xbatch.sum(axis=1).astype(int).tolist()
            forbidden=np.any(xbatch*mask,axis=(1,2)) if mask is not None and mask.shape==xbatch.shape[1:] else None
        for j,r in enumerate(group):
            i=start+j
            if r['id']!=i or any(r.get(k)!=p.get(k) for k in ('run_id','experiment_contract_id','config_sha256','evaluator_sha256')):raise ValueError('INTEGRITY_ERROR: row identity')
            x=index.decisions[i]
            if mask is not None and (forbidden[j] if ordered and forbidden is not None else np.any(x*mask)):
                raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: raw installation outside allowed space')
            if type(r.get('generation')) is not int or r['generation']!=i//p['optimizer']['population']:raise ValueError('INTEGRITY_ERROR: raw generation')
            actual_counts=counts[j] if ordered else x.sum(axis=0).astype(int).tolist()
            if r.get('sensor_counts')!=actual_counts or not math.isfinite(r.get('cost',float('nan'))):raise ValueError('INTEGRITY_ERROR: counts/cost')
            components=r.get('cost_components')
            if not isinstance(components,dict) or not all(type(v) in (int,float) and math.isfinite(v) for v in components.values()) or not abs(sum(components.values())-r['cost'])<=1e-12+1e-12*abs(r['cost']):raise ValueError('INTEGRITY_ERROR: cost components')

class RunStore:
    def __init__(self,root):self.root=Path(root)
    def request_path(self,cid,request_id):
        import re
        if not re.fullmatch(r'[A-Z][A-Z0-9_-]*',cid) or not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',request_id):raise ValueError('INVALID_REQUEST_ID')
        return self.root/'_requests'/cid/(digest(request_id)+'.json')
    def request_receipt(self,cid,request_id):
        path=self.request_path(cid,request_id)
        if not path.exists():
            if path.with_suffix('.claim').exists():raise ValueError('REQUEST_RESERVED_WITHOUT_RAW: reservation interrupted before receipt')
            return None
        try:r=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):raise ValueError('INTEGRITY_ERROR: incomplete request reservation; request will not be resubmitted') from None
        if r.get('schema')!='SOLSOL_REQUEST_RECEIPT_V1':raise ValueError('UNSUPPORTED_SCHEMA: request receipt')
        if r.get('experiment_contract_id')!=cid or r.get('request_id')!=request_id or r.get('sha256')!=digest({k:v for k,v in r.items() if k!='sha256'}):raise ValueError('INTEGRITY_ERROR: request receipt')
        self.folder(cid,r['run_id'])
        return r
    def reserve_request(self,cid,request_id,run_id,fingerprint):
        path=self.request_path(cid,request_id)
        if path.exists():raise ValueError('REQUEST_ALREADY_RESERVED')
        r=dict(schema='SOLSOL_REQUEST_RECEIPT_V1',experiment_contract_id=cid,request_id=request_id,run_id=run_id,fingerprint=fingerprint)
        r['sha256']=digest(r);path.parent.mkdir(parents=True,exist_ok=True)
        try:
            path.with_suffix('.claim').mkdir(exist_ok=False)
        except FileExistsError:raise ValueError('REQUEST_ALREADY_RESERVED') from None
        atomic_json(path,r)
        return r
    def folder(self,cid,run_id):
        import re,uuid
        if not re.fullmatch(r'[A-Z][A-Z0-9_-]*',cid) or str(uuid.UUID(run_id))!=run_id:raise ValueError('Invalid run path identity')
        return self.root/cid/run_id
    def begin(self,cid,run_id):
        folder=self.folder(cid,run_id);folder.mkdir(parents=True,exist_ok=False)
        return folder
    def catalog_entry(self,folder):
        folder=Path(folder)
        manifest=folder/'manifest.json'
        # Discovery cache only. Opening/exporting still performs strict read().
        # Live/interrupted ledgers are not cached because checkpoints advance.
        if manifest.is_file():
            import copy
            committed=json.loads(manifest.read_text(encoding='utf8'))
            checkpoints=sorted(committed.get('checkpoint_files',{}),key=lambda name:(len(name),name))
            watched=[folder/'raw.json',manifest]
            if checkpoints:
                if not re.fullmatch(r'checkpoint-\d+\.json',checkpoints[-1]):raise ValueError('INTEGRITY_ERROR: checkpoint filename')
                watched.append(folder/checkpoints[-1])
            signature=tuple((p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns) for p in watched)
            cache=getattr(self,'_discovery_cache',{})
            prior=cache.get(str(folder))
            if prior is not None and prior[0]==signature:return copy.deepcopy(prior[1])
            result=self._catalog_entry_uncached(folder)
            after=tuple((p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns) for p in watched)
            if signature==after:
                cache[str(folder)]=(signature,copy.deepcopy(result));self._discovery_cache=cache
            return result
        return self._catalog_entry_uncached(folder)

    def _catalog_entry_uncached(self,folder):
        """Unverified discovery metadata only; opening/exporting still calls read.

        V1 writer puts scalar identity/config before rows. Parse complete JSON
        values, not a substring search that could match a nested/string key.
        Reordered historical JSON is decoded for discovery only. Scientific
        replay validation remains mandatory when opening/exporting a run.
        """
        folder=Path(folder);decoder=json.JSONDecoder();header={}
        # Large initializer ledgers can precede rows. Expand only the prefix,
        # instead of decoding every historical evaluation on each list request.
        with (folder/'raw.json').open('r',encoding='utf-8') as f:
            text=f.read(1024*1024)
            for _ in range(4):
                try:
                    i=0
                    while i<len(text) and text[i].isspace():i+=1
                    if text[i]!='{':break
                    i+=1
                    while True:
                        while i<len(text) and text[i].isspace():i+=1
                        key,i=decoder.raw_decode(text,i)
                        while i<len(text) and text[i].isspace():i+=1
                        if text[i]!=':':raise ValueError('Invalid catalog separator')
                        i+=1
                        while i<len(text) and text[i].isspace():i+=1
                        if key=='rows':break
                        _,i=decoder.raw_decode(text,i)
                        while i<len(text) and text[i].isspace():i+=1
                        if text[i]!=',':break
                        i+=1
                    break
                except (ValueError,IndexError):
                    extra=f.read(len(text))
                    if not extra:break
                    text+=extra
        pos=0
        def white(i):
            while i<len(text) and text[i].isspace():i+=1
            return i
        try:
            pos=white(pos)
            if text[pos]!='{':raise ValueError('Invalid raw object')
            pos+=1
            while True:
                pos=white(pos);key,pos=decoder.raw_decode(text,pos);pos=white(pos)
                if not isinstance(key,str) or text[pos]!=':' or key in header:raise ValueError('Invalid raw header')
                pos=white(pos+1)
                if key=='rows':
                    if text[pos]!='[':raise ValueError('Invalid raw rows')
                    break
                value,pos=decoder.raw_decode(text,pos);header[key]=value;pos=white(pos)
                if text[pos]!=',':raise ValueError('Incomplete raw header')
                pos+=1
        except (ValueError,IndexError):header={}
        required={'schema','run_id','experiment_contract_id','state','config','config_sha256'}
        if not required<=header.keys():
            p=decode_saved_json((folder/'raw.json').read_bytes())
            header={k:p[k] for k in required if k in p}
            header['runtime_version']=p.get('runtime_version','shared-engine-v1')
            header['optimizer']=p.get('optimizer',{})
            header['checkpoint_storage']=p.get('checkpoint_storage')
            del p
            if not required<=header.keys():raise ValueError('INTEGRITY_ERROR: missing catalog header')
        if header['schema'] not in (SCHEMA,CHECKPOINT_ROOT_V2):raise ValueError('UNSUPPORTED_SCHEMA')
        if header['run_id']!=folder.name or header['experiment_contract_id']!=folder.parent.name:raise ValueError('INTEGRITY_ERROR: path identity')
        if not isinstance(header['config'],dict):raise ValueError('INTEGRITY_ERROR: catalog config')
        state=header['state'];generation=None;nfe=None;total=None;manifest=folder/'manifest.json'
        if header['schema']==CHECKPOINT_ROOT_V2 and (header.get('checkpoint_storage')!=JOURNAL_V2 or state in ('completed','cancelled','time_limit','failed') or manifest.exists()):raise ValueError('UNSUPPORTED_SCHEMA: invalid checkpoint root')
        if manifest.is_file():
            m=json.loads(manifest.read_text(encoding='utf-8'))
            if m.get('schema')!=SCHEMA or any(m.get(k)!=header.get(k) for k in ('run_id','experiment_contract_id','state','config_sha256')):raise ValueError('INTEGRITY_ERROR: catalog manifest identity')
            names=list(m['checkpoint_files'])
            if any(not re.fullmatch(r'checkpoint-[0-9]{6,}\.json',n) or n!=f"checkpoint-{int(n[11:-5]):06d}.json" for n in names):raise ValueError('INTEGRITY_ERROR: checkpoint name')
            if names:
                name=max(names,key=lambda name:(len(name),name));data=(folder/name).read_bytes()
                if hashlib.sha256(data).hexdigest()!=m['checkpoint_files'][name]:raise ValueError('INTEGRITY_ERROR: checkpoint checksum')
                cp=json.loads(data)
                if cp.get('schema')!=SCHEMA or cp.get('run_id')!=header['run_id']:raise ValueError('INTEGRITY_ERROR: checkpoint identity')
                generation=cp['checkpoint']['generation'];nfe=cp['checkpoint']['nfe']
                if type(generation) is not int or generation<0 or type(nfe) is not int or nfe<0:raise ValueError('INTEGRITY_ERROR: checkpoint summary')
            if 'evaluations' in m:
                total=m['evaluations']
                if type(total) is not int or total<0 or (nfe is not None and total<nfe):raise ValueError('INTEGRITY_ERROR: terminal evaluation count')
            elif state=='completed':total=nfe
        elif state in ('completed','cancelled','time_limit','failed'):raise ValueError('INTEGRITY_ERROR: missing terminal manifest')
        else:
            state='interrupted'
            if header.get('checkpoint_storage') in (JOURNAL_V1,JOURNAL_V2):
                paths=sorted(folder.glob('checkpoint-*.json'),key=lambda p:(len(p.name),p.name))
                if paths:
                    cp=decode_saved_json(paths[-1].read_bytes())['checkpoint'];generation=cp['generation'];nfe=cp['nfe']
        from .run_names import names
        return dict(id=header['run_id'],run_id=header['run_id'],state=state,config=header['config'],optimizer=header.get('optimizer',{}),evaluator_version=header['config'].get('evaluator_version'),actual_generation=generation,evaluations=total if manifest.is_file() else nfe,checkpoint_evaluations=nfe,evaluation_count_scope='TOTAL_COMMITTED' if total is not None else 'CHECKPOINT_ONLY' if not manifest.is_file() else 'TOTAL_UNKNOWN',runtime_version=header.get('runtime_version','shared-engine-v1'),integrity_status='NOT_VERIFIED_UNTIL_OPEN',**names(header,folder))
    def persist(self,session,checkpoint=False,terminal=False):
        # Serialization completes under the same ledger lock; no redundant deep
        # copy of the entire growing history is required for this internal sink.
        if terminal and checkpoint:raise ValueError('Checkpoint and terminal publication must be separate')
        with session.lock:
            with terminal_commit_lock(session.folder):return self._persist_locked(session,checkpoint,terminal)
    def _persist_locked(self,session,checkpoint=False,terminal=False):
        folder=session.folder
        if (folder/'manifest.json').exists():raise ValueError('Committed run is immutable')
        packet=session._storage_packet() if hasattr(session,'_storage_packet') else session.packet(copy_values=False)
        packet['storage_complete']=bool(terminal)
        # Each checkpoint publishes its newly evaluated rows exactly once.
        # A committed run still has the original complete V1 raw/manifest.
        # An interrupted run reconstructs the same ledger from the hash chain.
        if not terminal and checkpoint:
            if getattr(session,'_journal_storage',None)!=JOURNAL_V2:
                raise ValueError('INTEGRITY_ERROR: checkpoint writer was not initialized for V2')
            cp=packet['checkpoints'][-1];p=folder/f"checkpoint-{cp['generation']:06d}.json"
            if p.exists():raise ValueError('Checkpoint already published')
            start=getattr(session,'_journal_nfe',0);event_start=getattr(session,'_journal_events',0)
            metadata={k:v for k,v in packet.items() if k not in _JOURNAL_RESERVED}
            previous_metadata=getattr(session,'_journal_metadata',None)
            changed,removed,encoded=journal_metadata_delta(metadata,previous_metadata)
            delta=dict(schema=SCHEMA,run_id=session.id,checkpoint=cp,
                journal_schema=JOURNAL_V2,
                previous_sha256=session._journal_hash if hasattr(session,'_journal_hash') else sha(folder/'raw.json'),
                start_nfe=start,rows=packet['rows'][start:],events=packet['events'][event_start:],
                metadata=changed,metadata_removed=removed,
                metadata_sha256=journal_metadata_checksum(encoded),
                metadata_mode='full' if previous_metadata is None else 'delta')
            from .live_checkpoint import CheckpointJournal
            atomic_json(p,CheckpointJournal(delta))
            session._journal_hash=sha(p);session._journal_nfe=len(packet['rows']);session._journal_events=len(packet['events'])
            session._journal_metadata=encoded
            return
        if not terminal and (folder/'raw.json').exists():return
        packet={'checkpoint_storage':JOURNAL_V2,**packet}
        if not terminal:packet['schema']=CHECKPOINT_ROOT_V2
        if not hasattr(session,'_encoded_rows'):session._encoded_rows=EncodedRows(spool=True)
        commit_manifest=None
        def prepare_commit(raw_hash):
            nonlocal commit_manifest
            commit_manifest=dict(schema=SCHEMA,run_id=session.id,experiment_contract_id=session.cid,state=session.state,raw_sha256=raw_hash,config_sha256=packet['config_sha256'],evaluations=len(packet['rows']),checkpoint_files={p.name:sha(p) for p in folder.glob('checkpoint-*.json')})
            intent=dict(schema=COMMIT_INTENT,manifest=commit_manifest)
            intent['sha256']=digest(intent)
            prior=folder/'terminal-intent.json'
            if prior.exists() and json.loads(prior.read_text(encoding='utf-8'))!=intent:raise ValueError('TERMINAL_INTENT_CONFLICT: preserve prior attempt for explicit recovery')
            atomic_json(folder/'terminal-intent.json',intent)
        raw_sha256=atomic_run_json(folder/'raw.json',packet,session._encoded_rows,verify=terminal,before_publish=prepare_commit if terminal else None,_verified_snapshot=terminal)
        session._journal_storage=JOURNAL_V2
        if checkpoint:
            cp=packet['checkpoints'][-1];p=folder/f"checkpoint-{cp['generation']:06d}.json"
            if p.exists():raise ValueError('Checkpoint already published')
            atomic_json(p,dict(schema=SCHEMA,run_id=session.id,checkpoint=cp,raw_sha256=raw_sha256))
        if terminal:
            atomic_json(folder/'manifest.json',commit_manifest)
            session._encoded_rows.close()
            del session._encoded_rows
    def read(self,folder,*,decision_sink=None):
        return self._read_verified(folder,decision_sink=decision_sink)

    def read_session(self,folder,*,decision_sink=None,projection_sink=None,_raw_sink=None,_validation_rows=False):
        """Private verified storage for a session; default full read is intact."""
        from .saved_population import ProjectionFallback,finalize_session_packet
        context={'validation_rows':True} if _validation_rows and _raw_sink is not None else {'compact_rows':True};decisions={};packet=None;captured={} if _raw_sink is not None else None
        try:
            packet=self._read_verified(folder,decision_sink=decisions,_session_projection=context,_raw_sink=captured)
            packet=finalize_session_packet(packet,decisions,context)
        except (ProjectionFallback,ValueError,TypeError,KeyError,IndexError,UnicodeError,RecursionError,OverflowError,AttributeError,OSError):
            if not context.get('used_projection'):raise
            context['whole_read_fallback']=True
        else:
            if decision_sink is not None:decision_sink.update(decisions)
            if projection_sink is not None:projection_sink.update(context)
            if _raw_sink is not None:_raw_sink.update(captured)
            return packet
        # Do not retain the failed graph/traceback while allocating a full one.
        packet=decisions=captured=None
        if _raw_sink is None:packet=self.read(folder,decision_sink=decision_sink)
        else:packet=self._read_verified(folder,decision_sink=decision_sink,_raw_sink=_raw_sink)
        if projection_sink is not None:projection_sink.update(context)
        return packet
    def read_verified_raw(self,folder,*,projection_sink=None):
        """Export exactly the original bytes that passed every fresh check.

        The session projection retains the full scientific verification while
        avoiding unused expanded populations. Nothing comes from a trust cache.
        Bytes publish only after finalization; fallback captures its own read.
        """
        captured={}
        self.read_session(folder,_raw_sink=captured,_validation_rows=True,projection_sink=projection_sink)
        return captured['raw']
    def recover_terminal(self,folder,expected_intent_sha256):
        """Explicit pinned recovery; never rewrite raw or synthesize a manifest."""
        folder=Path(folder).resolve();folder.relative_to(self.root.resolve())
        with terminal_commit_lock(folder):
            intent_path=folder/'terminal-intent.json'
            intent_bytes=intent_path.read_bytes()
            if hashlib.sha256(intent_bytes).hexdigest()!=expected_intent_sha256:raise ValueError('INTEGRITY_ERROR: recovery intent pin')
            intent=json.loads(intent_bytes.decode('utf-8'))
            if intent.get('schema')!=COMMIT_INTENT or intent.get('sha256')!=digest({k:v for k,v in intent.items() if k!='sha256'}):raise ValueError('INTEGRITY_ERROR: recovery intent')
            manifest=intent['manifest']
            if (folder/'manifest.json').exists():
                if json.loads((folder/'manifest.json').read_text(encoding='utf-8'))!=manifest:raise ValueError('INTEGRITY_ERROR: recovery commit conflict')
                self.read(folder)
                return dict(status='ALREADY_COMMITTED',raw_sha256=sha(folder/'raw.json'))
            packet=self._read_verified(folder,manifest)
            if packet['state'] not in ('completed','cancelled','time_limit','failed') or packet.get('storage_complete') is not True:raise ValueError('INTEGRITY_ERROR: recovery requires terminal raw')
            if sha(folder/'raw.json')!=manifest['raw_sha256'] or any(sha(folder/n)!=h for n,h in manifest['checkpoint_files'].items()):raise ValueError('INTEGRITY_ERROR: recovery files changed')
            atomic_json(folder/'manifest.json',manifest)
            return dict(status='RECOVERED_COMMIT',raw_sha256=manifest['raw_sha256'],evaluations=packet['nfe'])
    def _read_verified(self,folder,commit_manifest=None,*,decision_sink=None,_session_projection=None,_raw_sink=None):
        folder=Path(folder);raw=folder/'raw.json'
        data=raw.read_bytes();raw_hash=hashlib.sha256(data).hexdigest()
        captured_raw=data if _raw_sink is not None else None
        if _session_projection is None:p=decode_saved_json(data)
        else:
            from .saved_population import decode_session_json
            p=decode_session_json(data,_session_projection)
        del data
        if p.get('schema')==CHECKPOINT_ROOT_V2:
            if p.get('checkpoint_storage')!=JOURNAL_V2 or p.get('state') in ('completed','cancelled','time_limit','failed') or (folder/'manifest.json').exists() or commit_manifest is not None:raise ValueError('UNSUPPORTED_SCHEMA: invalid checkpoint root')
            p['schema']=SCHEMA
        elif p.get('schema')!=SCHEMA:raise ValueError('UNSUPPORTED_SCHEMA')
        if 'checkpoint_storage' in p and p['checkpoint_storage'] not in (JOURNAL_V1,JOURNAL_V2):
            raise ValueError('UNSUPPORTED_CHECKPOINT_STORAGE')
        if p.get('run_id')!=folder.name or p.get('experiment_contract_id')!=folder.parent.name:raise ValueError('INTEGRITY_ERROR: path identity')
        manifest=folder/'manifest.json'
        terminal=p.get('state') in ('completed','cancelled','time_limit','failed')
        verified_manifest=None
        if manifest.exists() or commit_manifest is not None:
            if commit_manifest is not None and manifest.exists():raise ValueError('INTEGRITY_ERROR: recovery manifest already exists')
            m=json.loads(manifest.read_text(encoding='utf-8')) if commit_manifest is None else commit_manifest
            verified_manifest=m
            if m.get('schema')!=SCHEMA or m.get('raw_sha256')!=raw_hash or any(m.get(k)!=p.get(k) for k in ('run_id','experiment_contract_id','state','config_sha256')):raise ValueError('INTEGRITY_ERROR: manifest')
            expected={f"checkpoint-{c['generation']:06d}.json":c for c in p['checkpoints']}
            if set(m['checkpoint_files'])!=set(expected):raise ValueError('INTEGRITY_ERROR: checkpoint manifest membership')
            for n,data in checked_checkpoint_bytes(folder,m['checkpoint_files'].items()):
                # expected is from the just-decoded original JSON, so no
                # tuple/datetime/non-string-key encoder coercion is trusted.
                if _session_projection is not None and _session_projection.get('used_projection'):
                    from .saved_population import validate_session_checkpoint
                    validate_session_checkpoint(data,p['run_id'],expected[n],_session_projection)
                else:validate_terminal_checkpoint(data,p['run_id'],expected[n],json_native=True)
        elif terminal:raise ValueError('INTEGRITY_ERROR: missing terminal manifest')
        else:
            if p.get('checkpoint_storage') in (JOURNAL_V1,JOURNAL_V2):
                journal_schema=p['checkpoint_storage']
                metadata_encoded={}
                previous_hash=raw_hash
                for gen,path in enumerate(sorted(folder.glob('checkpoint-*.json'),key=lambda p:(len(p.name),p.name))):
                    saved=decode_saved_json(path.read_bytes())
                    if (path.name!=f'checkpoint-{gen:06d}.json' or saved.get('schema')!=SCHEMA or
                        saved.get('run_id')!=p['run_id'] or saved.get('journal_schema')!=journal_schema or
                        saved.get('previous_sha256')!=previous_hash or saved.get('start_nfe')!=len(p['rows'])):
                        raise ValueError('INTEGRITY_ERROR: checkpoint journal chain')
                    cp=saved['checkpoint'];meta=(restore_journal_metadata(saved,p,gen,metadata_encoded) if journal_schema==JOURNAL_V2 else saved['metadata'])
                    if any(meta.get(k)!=p.get(k) for k in ('run_id','experiment_contract_id','config_sha256','evaluator_sha256')):
                        raise ValueError('INTEGRITY_ERROR: checkpoint journal identity')
                    p['rows'].extend(saved['rows']);p['events'].extend(saved['events']);p['checkpoints'].append(cp)
                    if journal_schema==JOURNAL_V2:
                        # Full0 may omit keys that existed only in initial raw.
                        # Replace the complete metadata namespace, not only the
                        # explicitly removed keys of later delta records.
                        for key in list(p):
                            if key not in _JOURNAL_RESERVED:del p[key]
                    p.update(meta)
                    if cp['generation']!=gen or cp['nfe']!=len(p['rows']) or p['nfe']!=len(p['rows']):
                        raise ValueError('INTEGRITY_ERROR: checkpoint journal range')
                    previous_hash=sha(path)
            p['state']='interrupted';p['termination_reason']='PROCESS_LOSS';p['storage_complete']=False
        from .archive import archive_prefix_ids
        import numpy as np
        c=p['compilation'];registry=p['registry']
        if any(p['problem'].get(key)!=p.get(key) for key in ('experiment_contract_id','config_sha256','evaluator_sha256')):raise ValueError('INTEGRITY_ERROR: frozen map identity')
        from .installation_domain import scientific_compilation as model_compilation
        scientific_compilation=model_compilation(p)
        if 'model_service' in scientific_compilation:
            service=scientific_compilation.pop('model_service')
            if service!=p['problem'].get('model_service') or set(service)!={'api_version','problem_id','input_sha256','source_sha256'} or service['api_version']!='SOLSOL_MODEL_API_V1':raise ValueError('INTEGRITY_ERROR: model service provenance')
        if digest(scientific_compilation)!=p['config_sha256'] or c['config']!=p['config'] or c['registry']!=registry:raise ValueError('INTEGRITY_ERROR: compiled configuration')
        n=len(registry['candidate_order']);s=len(registry['sensor_order']);m=len(registry['objective_order']);k=len(registry['constraint_order'])
        rows=p['rows'];previous=0
        if p['nfe']!=len(rows):raise ValueError('INTEGRITY_ERROR: NFE')
        if verified_manifest is not None and 'evaluations' in verified_manifest and (type(verified_manifest['evaluations']) is not int or verified_manifest['evaluations']!=len(rows)):raise ValueError('INTEGRITY_ERROR: manifest NFE')
        # One validation pass supplies checked binary decisions for counts and
        # checkpoint identity too; do not reconstruct each nested X repeatedly.
        archives,index=archive_prefix_ids(rows,[cp['nfe'] for cp in p['checkpoints']],tolerance=p['archive_policy']['tolerance'],sort=p['archive_policy']['sort'],return_index=True)
        if rows and index.widths!=(m,k,(n,s)):raise ValueError('INTEGRITY_ERROR: row dimensions')
        validate_row_metadata(rows,index,c,p)
        if len(rows)>=4096:share_row_strings(rows)
        for gen,cp in enumerate(p['checkpoints']):
            stop=cp['nfe']
            if cp['generation']!=gen or not previous<stop<=len(rows) or cp['evaluations']!=stop:raise ValueError('INTEGRITY_ERROR: checkpoint range')
            pop=cp['population_X'];ids=cp['population_ids']
            if _session_projection is not None and _session_projection.get('used_projection'):
                from .saved_population import prepare_session_population
                prepare_session_population(pop,ids,index.decisions,_session_projection)
            if len(pop)!=p['optimizer']['population'] or len(ids)!=len(pop) or any(type(i) is not int or not 0<=i<stop for i in ids) or pop!=[rows[i]['X'] for i in ids]:raise ValueError('INTEGRITY_ERROR: population identity')
            if cp['archive_ids']!=archives[gen]:raise ValueError('INTEGRITY_ERROR: archive')
            previous=stop
        if p.get('state')=='completed' and (previous!=len(rows) or len(p['checkpoints'])!=p['optimizer']['checkpoints'] or len(rows)!=p['optimizer']['population']*p['optimizer']['checkpoints']):raise ValueError('INTEGRITY_ERROR: incomplete completed budget')
        p['resume_available']=False
        # Publish only after every integrity check succeeded. These are the
        # already checked binary matrices, not an on-disk trust cache.
        if decision_sink is not None:decision_sink.update(index.decisions)
        if _raw_sink is not None:_raw_sink['raw']=captured_raw
        return p
