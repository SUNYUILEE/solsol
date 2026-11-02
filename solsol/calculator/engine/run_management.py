"""User labels and recoverable list deletion, outside scientific run files."""
import copy,json,re,threading,uuid
from datetime import datetime,timezone
from .runtime import ACTIVE,TERMINAL,RunSession
from .store import atomic_json

class RunManagement:
    def __init__(self,owner):
        self.owner=owner;self.root=owner.service.store.root/'_run_management';self.lock=threading.RLock()

    def path(self,cid,rid):
        if not isinstance(cid,str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]*',cid):raise ValueError('잘못된 실험 종류입니다.')
        try:valid=str(uuid.UUID(rid))==rid
        except (ValueError,TypeError,AttributeError):valid=False
        if not valid:raise ValueError('잘못된 실행 ID입니다.')
        return self.root/cid/(rid+'.json')

    def metadata(self,cid,rid):
        path=self.path(cid,rid)
        if not path.exists():return dict(revision=0,name=None,deleted=False,history=[])
        p=json.loads(path.read_text(encoding='utf8'))
        if (p.get('schema')!='SOLSOL_RUN_MANAGEMENT_V1' or p.get('experiment_contract_id')!=cid or p.get('run_id')!=rid or
            type(p.get('revision')) is not int or p['revision']<1 or type(p.get('deleted')) is not bool or
            p.get('name') is not None and not isinstance(p['name'],str)):
            raise ValueError('실행 관리 기록의 식별 정보가 맞지 않습니다.')
        return p

    def decorate(self,cid,rid,packet):
        p=dict(packet);m=self.metadata(cid,rid)
        p['automatic_name']=p.get('display_name',rid);p['custom_name']=m['name']
        if m['name']:p['display_name']=m['name']
        p['management_revision']=m['revision'];p['deleted']=m['deleted']
        return p

    def apply(self,cid,rows,include_deleted=False):
        result=[]
        for row in rows:
            value=self.decorate(cid,row.get('run_id',row.get('id')),row)
            if include_deleted or not value['deleted']:result.append(value)
        return result

    def rows(self,cid,deleted=False):
        rows=self.owner.collection(cid,include_deleted=True)
        result=[]
        for row in rows:
            if row['deleted']!=deleted:continue
            rid=row['run_id'];loaded=self.owner.service.sessions.get(rid)
            editable=row['state'] in TERMINAL
            if isinstance(loaded,RunSession):
                # Terminal state is assigned before final IO; the publication
                # becomes terminal only after the writer has returned.
                published=getattr(loaded,'_terminal_progress',None)
                editable=editable and bool(published and published['state'] not in ACTIVE)
            result.append({k:copy.deepcopy(row.get(k)) for k in ('run_id','state','display_name','automatic_name','custom_name','management_revision','deleted','actual_generation','evaluations')})
            result[-1]['editable']=bool(editable)
        return result

    def update(self,cid,rid,body):
        self.path(cid,rid)
        if not isinstance(body,dict) or set(body)-{'action','name','expected_revision'}:raise ValueError('잘못된 관리 요청입니다.')
        action=body.get('action');expected=body.get('expected_revision')
        if action not in ('rename','trash','restore') or type(expected) is not int or expected<0:raise ValueError('관리 동작과 목록 버전을 확인하세요.')
        name=body.get('name')
        if action=='rename':
            if not isinstance(name,str) or len(name)>120 or any(ord(c)<32 or ord(c)==127 for c in name):raise ValueError('이름은 줄바꿈 없이 120자 이내로 입력하세요.')
            name=name.strip() or None
        elif 'name' in body:raise ValueError('이 동작은 이름을 받지 않습니다.')
        with self.lock:
            loaded=self.owner.service.sessions.get(rid)
            if loaded is not None and loaded.cid!=cid:raise KeyError('다른 실험의 실행입니다.')
            guard=getattr(loaded,'lock',None)
            if guard is not None and not guard.acquire(blocking=False):raise ValueError('계산·저장·조회 처리 중입니다. 끝난 뒤 다시 시도하세요.')
            try:
                candidates=self.rows(cid,deleted=action=='restore')
                row=next((r for r in candidates if r['run_id']==rid),None)
                if row is None:raise KeyError('이 목록에서 실행을 찾을 수 없습니다. 목록을 새로고침하세요.')
                if not row['editable']:raise ValueError('계산이나 저장이 끝난 항목만 편집할 수 있습니다.')
                prior=self.metadata(cid,rid)
                if prior['revision']!=expected:raise ValueError('다른 창에서 변경됐습니다. 목록을 새로고침하세요.')
                p=dict(prior,schema='SOLSOL_RUN_MANAGEMENT_V1',experiment_contract_id=cid,run_id=rid,revision=expected+1)
                if action=='rename':p['name']=name
                else:p['deleted']=action=='trash'
                p['updated_at']=datetime.now(timezone.utc).isoformat()
                p['history']=prior.get('history',[])+[dict(action=action,name=p['name'],deleted=p['deleted'],at=p['updated_at'])]
                path=self.path(cid,rid);path.parent.mkdir(parents=True,exist_ok=True);atomic_json(path,p)
                return dict(run_id=rid,revision=p['revision'],custom_name=p['name'],deleted=p['deleted'])
            finally:
                if guard is not None:guard.release()

    def get(self,h,endpoint,query):
        if endpoint!='/api/engine/run-management':return False
        if query=={'capabilities':['true']}:
            h.send_json(dict(schema='SOLSOL_RUN_MANAGEMENT_V1',rename=True,recoverable_delete=True));return True
        if set(query)-{'deleted'} or query.get('deleted',['false']) not in (['true'],['false']):raise ValueError('잘못된 목록 필터입니다.')
        h.send_json(dict(schema='SOLSOL_RUN_MANAGEMENT_V1',runs=self.rows(h.contract,query.get('deleted')==['true'])));return True

    def post(self,h,endpoint,query):
        match=re.fullmatch(r'/api/engine/run-management/([0-9a-f-]{36})',endpoint)
        if not match:return False
        if query:raise ValueError('관리 요청에는 query를 사용할 수 없습니다.')
        try:h.send_json(self.update(h.contract,match[1],self.owner.body(h)))
        except KeyError as exc:h.send_json({'error':str(exc)},404)
        except ValueError as exc:h.send_json({'error':str(exc)},409)
        return True
