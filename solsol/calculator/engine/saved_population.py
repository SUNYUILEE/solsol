"""Private stored-session population projection; the full reader stays intact.

The whole original JSON is parsed with the historical float converter. Only a
population whose bytes equal the corresponding already-parsed raw row matrices
can remain deferred. Every noncanonical case uses the original full reader.
"""
import re
from typing import Any,Literal
import numpy as np
try:
    import msgspec
except ImportError:
    msgspec=None

_object=msgspec.json.Decoder(dict[str,msgspec.Raw]) if msgspec is not None else None
_array=msgspec.json.Decoder(list[msgspec.Raw]) if msgspec is not None else None
_space=re.compile(rb'[ \t\r\n]*')
_key=re.compile(rb'"(?:[^"\\]|\\.)*"')
_cp_names=('generation','nfe','evaluations','population_X','population_ids','front_ids','archive_ids','elapsed_seconds')
_cp_optional=('qualified_count','legacy_policy_qualified_count','target_archive_count')
_binary_translation=bytes.maketrans(b'01',b'\x00\x01')
_cp_type=msgspec.defstruct('PrivateCanonicalCheckpoint',[(key,msgspec.Raw if key=='population_X' else Any,msgspec.UNSET) for key in (*_cp_names,*_cp_optional)],forbid_unknown_fields=True) if msgspec is not None else None

class ProjectionFallback(Exception):
    pass

class _Checkpoint(dict):
    pass

class _Population:
    def __init__(self,raw,references):self.raw=raw;self.references=references;self.binary=None
    def __len__(self):
        if self.binary is None:raise ProjectionFallback()
        return len(self.references)
    def __eq__(self,other):
        if self.binary is None:raise ProjectionFallback()
        return self.references==other
    def __ne__(self,other):return not self==other

class _ValidationPopulation(_Population):
    def __eq__(self,other):
        # Values were certified against the freshly validated row index in
        # prepare_session_population. This comparison only binds occurrences.
        if self.binary is None or not isinstance(other,list):raise ProjectionFallback()
        if len(self.references)!=len(other):return False
        if not all(a is b for a,b in zip(self.references,other)):raise ProjectionFallback()
        return True

def _row_type(raw,json):
    import json as stdjson
    # Discover only the writer's first row shape, without decoding all X lists.
    prefix=bytes(memoryview(raw)[:65536]).decode('utf-8')
    pos=prefix.index('[')+1
    first,_=stdjson.JSONDecoder().raw_decode(prefix,pos)
    if not isinstance(first,dict) or 'X' not in first:raise ProjectionFallback()
    keys=list(first)
    # Immutable identity/specification text is decoded once by Literal's C
    # lookup. A differing or non-string value falls back to the full reader;
    # arbitrary metadata and variable status/origin/placement hashes stay Any.
    shared={'experiment_contract_id','run_id','config_sha256','evaluator_sha256',
            'config_hash','evaluator_hash','model_version','environment_version',
            'parent_model_version','resource_contract_version','quality_semantics',
            'goal_definition','provenance'}
    metadata=msgspec.defstruct('PrivateValidationRow',
        [(f'f{i}',msgspec.Raw if key=='X' else Literal[first[key]] if key in shared and type(first[key]) is str else Any,msgspec.UNSET) for i,key in enumerate(keys)],
        rename={f'f{i}':key for i,key in enumerate(keys)},forbid_unknown_fields=True)
    # All-Raw fields reference immutable byte buffers, never decoded containers.
    # This frozen, nonescaping certificate cannot participate in object cycles.
    # Any-valued metadata above retains its normal GC behavior.
    certificate=msgspec.defstruct('PrivateRawRowCertificate',
        [(f'f{i}',msgspec.Raw,msgspec.UNSET) for i in range(len(keys))],
        rename={f'f{i}':key for i,key in enumerate(keys)},
        forbid_unknown_fields=True,frozen=True,gc=False)
    return keys,metadata,msgspec.json.Decoder(certificate)

def _validation_rows(parsed,raw,keys,json,shape,certificate_decoder,compact=False):
    originals=_array.decode(raw)
    if len(originals)!=len(parsed):raise ProjectionFallback()
    if compact:
        # Exact canonical integer tokens, separators AND both dimensions. The
        # whole root JSON/UTF-8 parser and whole-row certificate still run.
        site=rb'\[[01](?:,[01]){'+str(shape[1]-1).encode()+rb'}\]'
        try:binary_matrix=re.compile(rb'\[(?:'+site+rb',){'+str(shape[0]-1).encode()+rb'}'+site+rb'\]')
        except (re.error,OverflowError):raise ProjectionFallback()
    rows=[]
    for original,typed in zip(originals,parsed):
        source=bytes(original);certificate=certificate_decoder.decode(source)
        # Raw-aware C encoding preserves every original metadata value token.
        # Exact full bytes prove key presence/order/uniqueness without Python
        # per-member wrappers or changing float/string spellings.
        if msgspec.json.encode(certificate)!=source:raise ProjectionFallback()
        row=dict(zip(keys,msgspec.structs.astuple(typed)))
        if any(value is msgspec.UNSET for value in row.values()):raise ProjectionFallback()
        raw_x=bytes(row['X'])
        # The whole root already parsed JSON grammar. This is only a candidate
        # binary buffer, never acceptance by digit extraction: the following
        # complete original-byte certificate proves every token and dimension.
        candidate=raw_x.translate(_binary_translation,b'[],')
        if compact:
            if binary_matrix.fullmatch(raw_x) is None:raise ProjectionFallback()
            from .binary_decision import BinaryDecision
            row['X']=BinaryDecision(candidate,shape)
        else:
            x=np.frombuffer(candidate,dtype=np.uint8).reshape(shape).copy()
            if raw_x!=json.dumps(x,option=json.OPT_SERIALIZE_NUMPY):raise ProjectionFallback()
            x.flags.writeable=False;row['X']=x
        rows.append(row)
    return rows

def _unique_members(data,fields,json):
    # A Raw dict keeps the last duplicate key. Require exact one-to-one original
    # members (including escaped key spellings), otherwise use the full decoder.
    pos=_space.match(data).end()
    if data[pos:pos+1]!=b'{':return False
    pos+=1
    for index,(key,value) in enumerate(fields.items()):
        pos=_space.match(data,pos).end();token=_key.match(data,pos)
        if token is None or json.loads(token.group())!=key:return False
        pos=_space.match(data,token.end()).end()
        if data[pos:pos+1]!=b':':return False
        pos=_space.match(data,pos+1).end()
        if not data.startswith(memoryview(value),pos):return False
        pos=_space.match(data,pos+len(value)).end()
        if index<len(fields)-1:
            if data[pos:pos+1]!=b',':return False
            pos+=1
    pos=_space.match(data,pos).end()
    return data[pos:pos+1]==b'}' and _space.match(data,pos+1).end()==len(data)

def decode_session_json(data,context):
    from . import store
    json=store._fast_json
    if _object is None or json is None or not hasattr(json,'Fragment') or store._raw_json_decoder is None or len(data)<1048576 or store._has_large_integer(data):
        return store.decode_saved_json(data)
    try:
        store._validate_utf8(data);fields=_object.decode(data)
        if 'checkpoints' not in fields or not _unique_members(data,fields,json):raise ProjectionFallback()
        keys=list(fields)
        row_keys,row_type,certificate_decoder=_row_type(fields['rows'],json) if context.get('validation_rows') or context.get('compact_rows') else (None,None,None)
        Root=msgspec.defstruct('PrivateRoot',[(f'f{i}',list[_cp_type] if key=='checkpoints' else list[row_type] if key=='rows' and row_type is not None else Any,msgspec.UNSET) for i,key in enumerate(keys)],rename={f'f{i}':key for i,key in enumerate(keys)},forbid_unknown_fields=True)
        # One whole document: every metadata value retains its original JSON
        # ancestors, fallback context and exact per-token float conversion.
        parsed=msgspec.json.Decoder(Root,float_hook=json.loads).decode(data)
        result={key:getattr(parsed,f'f{i}') for i,key in enumerate(keys)}
        if result.get('schema')!=store.SCHEMA or result.get('state') not in ('completed','cancelled','time_limit','failed'):raise ProjectionFallback()
        config=result.get('config',{})
        if not isinstance(config,dict):raise ProjectionFallback()
        if not (config.get('_research') or result.get('experiment_contract_id') in ('HMSP-EXEC-V1','HMSP-2D-V1')):raise ProjectionFallback()
        if row_type is not None:
            shape=(len(result['registry']['candidate_order']),len(result['registry']['sensor_order']))
            if not all(dimension>0 for dimension in shape):raise ProjectionFallback()
            result['rows']=_validation_rows(result['rows'],fields['rows'],row_keys,json,shape,certificate_decoder,compact=bool(context.get('compact_rows') and not context.get('validation_rows')))
        # The static writer shape avoids reparsing every checkpoint before the
        # whole decode. A complete byte certificate below proves original key
        # order, field presence, duplicate absence and canonical spellings.
        raw_array=memoryview(fields['checkpoints']);position=1
        if bytes(raw_array[:1])!=b'[':raise ProjectionFallback()
        checkpoints=[]
        for index,parsedcp in enumerate(result['checkpoints']):
            cp=_Checkpoint((key,getattr(parsedcp,key)) for key in _cp_names)
            if any(value is msgspec.UNSET for value in cp.values()):raise ProjectionFallback()
            for key in _cp_optional:
                value=getattr(parsedcp,key)
                if value is not msgspec.UNSET:cp[key]=value
            pop=cp['population_X']
            references=[result['rows'][i]['X'] for i in cp['population_ids']]
            cp['population_X']=json.Fragment(bytes(pop))
            certificate=json.dumps(cp)
            begin=position
            # Bound comparison copies to one checkpoint. Retain only a view of
            # the original checked document, not all encoded certificates.
            if bytes(raw_array[position:position+len(certificate)])!=certificate:raise ProjectionFallback()
            position+=len(certificate)
            delimiter=b',' if index<len(result['checkpoints'])-1 else b']'
            if bytes(raw_array[position:position+1])!=delimiter:raise ProjectionFallback()
            position+=1
            cp['population_X']=(_ValidationPopulation if row_type is not None else _Population)(pop,references);cp.raw=raw_array[begin:position-1];checkpoints.append(cp)
        if not checkpoints:
            if bytes(raw_array)!=b'[]':raise ProjectionFallback()
        elif position!=len(raw_array):raise ProjectionFallback()
        result['checkpoints']=checkpoints
        context.update(used_projection=True,certified_populations=len(checkpoints))
        if row_type is not None:
            context['validated_row_arrays']=len(result['rows'])
            context['native_row_struct_certificates']=len(result['rows'])
            if context.get('compact_rows') and not context.get('validation_rows'):context['private_binary_decisions']=len(result['rows'])
        return result
    except (ProjectionFallback,msgspec.DecodeError,UnicodeError,TypeError,ValueError,KeyError,IndexError,OverflowError,RecursionError):
        context['decode_fallback']=True
    # Release failed projected graphs AND their traceback before full fallback.
    fields=parsed=result=checkpoints=cp=parsedcp=pop=references=encoded=raw_array=certificate=None
    return store.decode_saved_json(data)

def validate_session_checkpoint(data,run_id,expected,context):
    from . import store
    if not isinstance(expected,_Checkpoint):return store.validate_terminal_checkpoint(data,run_id,expected,json_native=True)
    if not store._has_large_integer(data):
        try:
            store._validate_utf8(data);binding=store._checkpoint_binding_decoder.decode(data)
            if binding.schema==store.SCHEMA and binding.run_id==run_id and binding.checkpoint is not None and bytes(binding.checkpoint)==bytes(expected.raw):
                context['canonical_payloads']=context.get('canonical_payloads',0)+1
                return
        except (msgspec.DecodeError,UnicodeError,TypeError,ValueError,RecursionError):pass
    raise ProjectionFallback()

def finalize_session_packet(packet,decisions,context):
    from . import store
    if not context.get('used_projection'):return packet
    checkpoints=[]
    for original in packet['checkpoints']:
        cp=dict(original)
        if isinstance(original,_Checkpoint):
            x=cp['population_X'].binary
            if x is None:raise ProjectionFallback()
            cp['population_X']=x
            context['private_binary_populations']=context.get('private_binary_populations',0)+1
        checkpoints.append(cp)
    # Plain dicts and owned read-only arrays only: no Raw marker/view escapes.
    packet['checkpoints']=checkpoints
    return packet

def prepare_session_population(pop,ids,decisions,context):
    """One exact certificate from the fully validated binary row index."""
    from . import store
    if not isinstance(pop,_Population):return
    if any(type(i) is not int or i not in decisions for i in ids):raise ProjectionFallback()
    x=np.asarray([decisions[i] for i in ids],dtype=np.uint8)
    if bytes(pop.raw)!=store._fast_json.dumps(x,option=store._fast_json.OPT_SERIALIZE_NUMPY):raise ProjectionFallback()
    x.flags.writeable=False;pop.binary=x
    context['validated_population_certificates']=context.get('validated_population_certificates',0)+1
