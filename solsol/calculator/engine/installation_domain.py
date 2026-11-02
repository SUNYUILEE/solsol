"""Calculator-owned search domain, independent of Model objectives and goals."""
import copy
import numpy as np
from .contracts import digest
from .placement import PlacementSpace,PlacementCodec
from .placement_selection import distance_to_area
from .initialization import validate_resources

GEOMETRIC_MODELS={'ABC_COVERAGE_RESOURCE_V1'}

def support_allowed(certificate,original,candidates,sensors,identity,rule):
    """Validate a Model certificate without reproducing its scientific tensors."""
    c=certificate
    if (not isinstance(c,dict) or c.get('status')!='SUPPORTED' or c.get('contract_version')!='SENSOR_SUPPORT_V1'
            or c.get('support_sha256')!=digest({k:v for k,v in c.items() if k not in ('support_sha256','api_version')})
            or any(c.get('identity',{}).get(k)!=v for k,v in identity.items())
            or c.get('candidate_order')!=list(candidates) or c.get('sensor_order')!=list(sensors)
            or c.get('search_integration',{}).get('policy')!='OPT_IN_CLIENT_MASK_ORIGINAL_CODEC_V1'):
        raise ValueError('SENSOR_SUPPORT_INTEGRITY: certificate identity/checksum')
    original=np.asarray(original,bool);masks={}
    for key in ('original_allowed','safe_search_allowed','safe_prune_mask','zero_support_mask'):
        a=np.asarray(c.get(key))
        if a.shape!=original.shape or np.any((a!=0)&(a!=1)):
            raise ValueError('SENSOR_SUPPORT_INTEGRITY: mask shape/binary')
        masks[key]=a.astype(bool)
    if (not np.array_equal(masks['original_allowed'],original)
            or np.any(masks['safe_prune_mask'] & ~(original & masks['zero_support_mask']))
            or not np.array_equal(masks['safe_search_allowed'],original & ~masks['safe_prune_mask'])
            or c.get('full_X_shape')!=list(original.shape)
            or c.get('active_slot_order')!=np.flatnonzero(original.ravel()).tolist()):
        raise ValueError('SENSOR_SUPPORT_INTEGRITY: original domain/codec')
    lower=(rule or {}).get('lower',(rule or {}).get('limits') if (rule or {}).get('mode')=='all' else [0]*len(sensors))
    if len(lower)!=len(sensors) or any(v>0 and masks['safe_prune_mask'][:,j].any() for j,v in enumerate(lower)):
        raise ValueError('SENSOR_SUPPORT_INTEGRITY: positive count minimum pruned')
    return masks['safe_search_allowed']

def _support_identity(cp):
    return dict({k:v for k,v in cp.service_identity.items() if k!='api_version'},model_id=cp.cid,
                config_sha256=cp.config_hash,evaluator_sha256=cp.evaluator_hash,model_version=cp.model_version)

def default_domain(cid):
    return 'model'

def ensure_domain(cp,policy):
    """Guard every new execution, including callers below configuration HTTP."""
    packet=getattr(cp,'installation_domain',None)
    if packet is None:
        return apply_domain(cp,default_domain(cp.cid),policy)
    if (packet.get('sha256')!=digest({k:v for k,v in packet.items() if k!='sha256'})
            or packet.get('allowed')!=cp.space.allowed.astype(int).tolist()
            or cp.view_problem().get('calculator_installation_domain')!=packet):
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: execution space does not match declared domain')
    if packet['mode'] in ('inside_area','model_supported') and policy!='generic_v1':
        raise ValueError('INSTALLATION_DOMAIN: 영역 안 배치는 일반 계산 정책을 선택하세요')
    if packet['mode']=='model_supported':
        allowed=support_allowed(packet.get('support_certificate'),cp.model_allowed,cp.candidate_order,cp.sensor_order,_support_identity(cp),getattr(cp.bundle,'inventory_rule',None))
        if not np.array_equal(allowed,cp.space.allowed) or packet.get('original_codec_slots')!=cp.codec.slots.tolist():
            raise ValueError('SENSOR_SUPPORT_INTEGRITY: execution mask/codec')
    return packet


def apply_domain(cp,mode,policy,*,support_certificate=None):
    if mode not in ('model','inside_area','model_supported'):raise ValueError('INSTALLATION_DOMAIN: unknown policy')
    original=cp.space
    if not hasattr(cp,'model_allowed'):cp.model_allowed=original.allowed.astype(int).tolist()
    certificate=None
    if mode=='model_supported':
        if policy!='generic_v1':raise ValueError('INSTALLATION_DOMAIN: model_supported requires generic_v1')
        if support_certificate is None:
            from model_service_client import client
            support_certificate=client().request('/problems/'+cp.problem_id+'/sensor-support')
        certificate=copy.deepcopy(support_certificate)
        allowed=support_allowed(certificate,cp.model_allowed,cp.candidate_order,cp.sensor_order,_support_identity(cp),getattr(cp.bundle,'inventory_rule',None))
        # Keep the original codec object and active slot order. The search space
        # validates the narrower mask while variation repair clears pruned bits.
        cp.space=PlacementSpace(original.candidate_order,original.sensor_order,original.dataset_id,allowed,original.enabled_sensor_ids,original.co_location)
        validate_resources(cp.space,getattr(cp.bundle,'inventory_rule',None))
    if mode=='inside_area':
        if policy!='generic_v1':raise ValueError('INSTALLATION_DOMAIN: 영역 안 배치는 일반 계산 정책을 선택하세요')
        p=cp.view_problem();distances=[distance_to_area(site,p.get('geometry')) for site in p.get('sites',[])]
        if len(distances)!=original.shape[0] or any(d is None for d in distances):
            raise ValueError('INSTALLATION_DOMAIN: 모델의 명시 평가영역 경계가 필요합니다')
        mask=np.array(distances)<=1e-7
        allowed=original.allowed & mask[:,None]
        cp.space=PlacementSpace(original.candidate_order,original.sensor_order,original.dataset_id,allowed,original.enabled_sensor_ids,original.co_location)
        cp.codec=PlacementCodec(cp.space);cp.n_var=cp.codec.n_var
        if not cp.n_var:raise ValueError('INSTALLATION_DOMAIN: 평가영역 안에 설치 가능한 후보지가 없습니다')
        try:validate_resources(cp.space,getattr(cp.bundle,'inventory_rule',None))
        except ValueError as e:raise ValueError('INSTALLATION_DOMAIN: 영역 안 후보지로 보유 수량을 모두 설치할 수 없습니다 · '+str(e)) from None
    packet=dict(version='CALCULATOR_INSTALLATION_DOMAIN_V1',mode=mode,
                candidate_order=list(cp.candidate_order),sensor_order=list(cp.sensor_order),
                allowed=cp.space.allowed.astype(int).tolist(),eligible_sites=int(np.any(cp.space.allowed,axis=1).sum()),
                candidate_count=cp.space.shape[0],active_slots=int(cp.space.allowed.sum()),
                boundary_rule='INSTALLATION_CENTER_INSIDE_CLOSED_REGION' if mode=='inside_area' else 'ORIGINAL_MODEL_INSTALLATION_SPACE',
                quantitative_goals_independent=True)
    if certificate is not None:
        packet.update(boundary_rule='MODEL_CERTIFIED_ZERO_SUPPORT_PRUNING',support_certificate=certificate,
                      original_codec_slots=cp.codec.slots.tolist(),original_codec_n_var=cp.n_var)
    packet['sha256']=digest(packet);cp.installation_domain=packet
    cp._view_problem['calculator_installation_domain']=copy.deepcopy(packet)
    return packet


def scientific_compilation(packet):
    """Validate the calculator mask separately from the original Model digest."""
    c=copy.deepcopy(packet['compilation']);domain=c.pop('installation_domain',None)
    c.pop('inventory_rule',None)
    original=c.pop('model_allowed',None)
    if domain is None:
        if packet['problem'].get('calculator_installation_domain') is not None:
            raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: missing saved domain')
        return c
    if original is None:
        # Read-only migration of the early domain format. Never rewrite raw.
        # New records carry original allowed and can be checked offline.
        from .registry import compile_problem
        cp=compile_problem(packet['experiment_contract_id'],c['config'],c['enabled_sensor_ids'],c['registry']['objective_order'],c['diagnostic_ids'])
        if cp.config_hash!=packet['config_sha256'] or cp.evaluator_hash!=packet['evaluator_sha256']:
            raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: original Model identity unavailable')
        original=cp.space.allowed.astype(int).tolist()
    if (domain.get('sha256')!=digest({k:v for k,v in domain.items() if k!='sha256'})
            or domain!=packet['problem'].get('calculator_installation_domain')
            or domain.get('allowed')!=np.asarray(c['allowed'],dtype=int).tolist()
            or (packet.get('execution_snapshot') and packet['execution_snapshot'].get('installation_domain')!=domain)):
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: saved mask binding')
    allowed=np.asarray(original)
    if allowed.shape!=np.asarray(c['allowed']).shape or np.any((allowed!=0)&(allowed!=1)):
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: original mask')
    expected=allowed.astype(bool)
    if domain['mode']=='inside_area':
        distances=[distance_to_area(site,packet['problem'].get('geometry')) for site in packet['problem']['sites']]
        if len(distances)!=len(expected) or any(d is None for d in distances):
            raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: missing geometry')
        expected=expected & (np.asarray(distances)<=1e-7)[:,None]
    elif domain['mode']=='model_supported':
        if (domain.get('candidate_order')!=list(c['registry']['candidate_order'])
                or domain.get('sensor_order')!=list(c['registry']['sensor_order'])):
            raise ValueError('SENSOR_SUPPORT_INTEGRITY: saved physical order')
        identity=dict({k:v for k,v in packet['problem'].get('model_service',{}).items() if k!='api_version'},
                      model_id=packet['experiment_contract_id'],config_sha256=packet['config_sha256'],evaluator_sha256=packet['evaluator_sha256'])
        expected=support_allowed(domain.get('support_certificate'),expected,domain.get('candidate_order'),domain.get('sensor_order'),identity,packet['compilation'].get('inventory_rule'))
        slots=np.flatnonzero(allowed.ravel()).tolist() if c['codec']=='active-slots-v1' else list(range(allowed.size))
        if domain.get('original_codec_slots')!=slots or domain.get('original_codec_n_var')!=len(slots):
            raise ValueError('SENSOR_SUPPORT_INTEGRITY: frozen codec')
    elif domain['mode']!='model':raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: mode')
    if not np.array_equal(expected,c['allowed']):
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: geometry intersection')
    c['allowed']=np.asarray(original,dtype=bool).tolist()
    return c


def restore_domain(cp,packet):
    expected=packet.get('compilation',{}).get('installation_domain')
    if expected is None:
        if packet.get('problem',{}).get('calculator_installation_domain') is not None or (packet.get('execution_snapshot') or {}).get('installation_domain') is not None:
            raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: missing compilation domain')
        return cp
    if not isinstance(expected,dict) or expected.get('sha256')!=digest({k:v for k,v in expected.items() if k!='sha256'}):
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: checksum')
    if packet['problem'].get('calculator_installation_domain')!=expected:
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: frozen problem')
    snapshot=packet.get('execution_snapshot')
    if snapshot and snapshot.get('installation_domain')!=expected:
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: execution snapshot')
    actual=apply_domain(cp,expected['mode'],packet['solver']['policy'],support_certificate=expected.get('support_certificate'))
    if actual!=expected or packet['compilation']['allowed']!=actual['allowed']:
        raise ValueError('INSTALLATION_DOMAIN_INTEGRITY: recompiled allowed slots')
    return cp
