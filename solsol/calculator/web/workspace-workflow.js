'use strict';
// One server-confirmed request and one saved run, shared with EngineClient.
let confirmedRequest=null,confirmedExecution=null,copyParent=null,configurationChanges=null,configurationCopyPending=false,configurationCopyError='';
function savedRunCopyRestriction(){
 if(!run||draft?.sensor!==RF||run.experiment_contract_id!==RF)return null;
 // Explicit-coordinate copies use the existing server copy adapter in resources.
 if(!run.config?.common&&run.config?.geometry_payload)return null;
 const versions=registryData?.ui_models?.[RF]?.parameter_keys_by_version;
 if(!versions||versions[run.config?.evaluator_version])return null;
 const version=registryData?.bundles.find(b=>b.id===RF)?.version;
 return {code:'LEGACY_RF_READ_ONLY',message:'이전 RF 계약 · 저장 결과 열람 전용입니다. 조건 복사는 지원하지 않습니다. '+(version?'현재 모델 '+version:'현재 모델')+'의 새 설정을 별도 창에서 열 수 있습니다. 기존 결과와 입력은 유지됩니다.'};
}
const configurationCopy=$('copyRun').onclick;
$('copyRun').onclick=async function(){await configurationCopy();if(configured()){selection().initializer=run.optimizer.initializer||'random';selection().initialization_evaluations=run.optimizer.initialization_evaluations??128;selection().initialization_seconds=run.optimizer.initialization_seconds??30;await apply();}};
const inspectorBeforeAccounting=renderInspector;
function savedInitializationReading(parent){
 const source=run?.initialization?.sources?.find(s=>s.method==='saved'),ref=source?.reference;
 if(ref)noteText(parent,`초기 배치 원본 · 저장 실행 ${ref.run_id.slice(0,8)} · 행 ${ref.row_id} · 초기 개체 1번. 새 조건 재평가 비용 ${source.new_cost} · ${source.new_model_feasible?'모델 제약 충족':'모델 제약 미충족'} · 원본 배치를 그대로 사용했습니다.`);
}
function initializationAdmissionReading(host){
 const info=run?.initialization;if(!info)return;
 if(info.version==='calculator-common-initialization-v2'){
  noteText(host,`초기 후보 준비: 모델 제약 통과 ${info.prepared_model_feasible_count??'미기록'}개 · 영역 목표까지 통과 ${info.prepared_goal_qualified_count??'미기록'}개 · 실제 초기 모집단에 전달 ${info.seed_count??'미기록'}개. 준비 후보 전체를 탐색 해집합에 넣지 않으며, 전달한 배치는 첫 세대에서 다시 평가합니다.`);
  if(['greedy','milp'].includes(info.method))noteText(host,'새 초기 후보 규칙: 영역 목표 미달만으로 시작 후보를 버리지 않습니다. 제안·탐색의 목적과 목표, Model 제약은 그대로입니다.');
 }else if(info.version==='calculator-common-initialization-v1'&&['greedy','milp'].includes(info.method))noteText(host,`기존 초기 후보 규칙: 모델 제약과 영역 목표를 모두 통과한 제안만 수용했습니다. 초기 모집단에 전달 ${info.seed_count??'미기록'}개. 0개라도 모델 제약을 만족한 준비 후보가 없었다는 뜻은 아닙니다.`);
}
function renderEvaluationAccounting(){inspectorBeforeAccounting();savedInitializationReading($('inspectorBody'));initializationAdmissionReading($('inspectorBody'));if(!run?.counters)return;const c=run.counters,prep=c.preparation_evaluations||0,search=(c.initial_population_evaluations||0)+(c.offspring_evaluations||0),replay=c.replay_evaluations||0,refine=c.refinement_evaluations||0,diagnostic=c.diagnostic_evaluations||0;noteText($('inspectorBody'),`확인된 모델 평가: 준비 ${prep} · 탐색 ${search} · 재생 ${replay} · 정련 ${refine} · 진단 ${diagnostic} · 총 ${prep+search+replay+refine+diagnostic}회`);if(run.initialization?.preparation_evaluations_uncertain)noteText($('inspectorBody'),'준비 평가 응답이 확인되지 않아 실제 총 평가 횟수는 미확정입니다. 요청 시도는 원시 실행 기록에 보존됩니다.');}
const workflowPrior={apply,settings:renderSettings,inspector:renderEvaluationAccounting,fetch:fetchRun,copy:$('copyRun').onclick};
function syncLoadedRunChoice(){
 if(!run?.run_id||run.experiment_contract_id!==draft.sensor)return;
 const picker=$('runHistory');let item=[...picker.options].find(o=>o.value===run.run_id);
 if(!item){item=document.createElement('option');item.value=run.run_id;picker.append(item);}
 item.textContent=(states[run.state]||'실행 상태 확인 중')+' · '+(run.display_name||readableRunName(run));picker.value=run.run_id;
}
function readableRunName(r){
 const opt=r.optimizer||{},b=r.config?._resource_contract?.budget;
 const gen=opt.generations??(opt.checkpoints?opt.checkpoints-1:r.actual_generation??r.generation??'미기록');
 return `${r.experiment_contract_id||draft.sensor} · ${gen}세대 · 예산 ${b?.mode==='MAX'?b.limit:'제한 없음'} · seed ${opt.seed??r.config?.seed??'미기록'}`;
}
const workflowHistories=histories;
histories=async function(){await workflowHistories();syncLoadedRunChoice();};
const clearBeforeWorkflow=clearRun;
clearRun=function(){copyParent=null;configurationChanges=null;confirmedRequest=null;confirmedExecution=null;clearBeforeWorkflow();};
const pendingKey=cid=>'solsol.pendingRequest.v1.'+cid;
function connectionState(text){let el=$('connectionState');if(!el){el=document.createElement('span');el.id='connectionState';el.setAttribute('role','status');$('runtimeStatus').after(el);}el.textContent=' · 연결: '+text;}
function jsonDetails(parent,title,data,id){
 const record=JSON.stringify(data,null,2);
 const d=document.createElement('details'),s=document.createElement('summary');if(id)d.id=id;s.textContent=title;d.append(s);
 noteText(d,'원본 연구 기록은 파일로 내려받아 확인할 수 있습니다.');
 const button=document.createElement('button');button.type='button';button.textContent='연구 기록 파일 내려받기';
 button.onclick=()=>{const url=URL.createObjectURL(new Blob([record],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='solsol-research-record.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 d.append(button);parent.append(d);return d;
}
// Presentation only: never normalize or mutate the request used for calculation.
function readableConfigurationChanges(changes,registry,cid,savedConfig={},savedRun=null){
 const meta=registry.bundles.find(b=>b.id===cid),schema=registry.ui_models?.[cid],fields=[];
 for(const sections of Object.values(schema?.groups||{}))for(const section of sections)fields.push(...(section.fields||[]));
 const sensor=id=>meta?.sensors.find(s=>s.id===id)?.name||'센서',metric=id=>meta?.metrics.find(m=>m.id===id)?.name||'평가 항목';
 const simple=v=>v===undefined?'저장값 없음':v===null?'미지정':typeof v==='boolean'?(v?'사용':'사용 안 함'):typeof v==='number'?String(v):'설정 변경';
 const limit=v=>v===undefined?'저장값 없음':!v?'미지정':v.mode==='OFF'?'제한 없음':v.mode==='MAX'?'최대 '+simple(v.limit??v.max):v.mode==='EXACT'?'정확히 '+simple(v.value):v.mode==='RANGE'?simple(v.min)+' ~ '+simple(v.max):'제한 설정 변경';
 const resource=v=>v===undefined?'저장값 없음':!v?'미지정':[
  v.budget?'공통 예산 '+limit(v.budget):'',
  ...Object.entries(v.sensor_counts||{}).map(([id,n])=>sensor(id)+' 수량 '+limit(n)),
  ...Object.entries(v.cost?.sensor_unit_costs||{}).map(([id,n])=>sensor(id)+' 장비당 비용 '+simple(n)),
  v.cost?.site_cost!==undefined?'설치 지점당 비용 '+simple(v.cost.site_cost):''
 ].filter(Boolean).join(' · ')||'공통 비용·재고 설정 변경';
 const names={generations:'진화 세대 수',population:'개체 수',seed:'난수 시드',ref_partitions:'참조방향 분할 수',algorithm:'최적화 알고리즘',initializer:'초기 배치 방법',initialization_version:'초기 후보 수용 규칙',initialization_evaluations:'초기 배치 준비 평가 수',initialization_seconds:'초기 배치 준비 시간',wallclock_limit_seconds:'계산 시간 제한',grid_metres:'평가점 간격'};
 const choices={random:'무작위',greedy:'Greedy',milp:'MILP',saved:'저장 결과의 성능 1순위 배치',OFF:'제한 없음',MAX:'상한 제한',EXACT:'정확 수량',RANGE:'범위 제한',inside_area:'평가영역 내부',model_default:'모델 기본 영역','calculator-common-initialization-v1':'기존 규칙 · 영역 목표까지 통과한 후보','calculator-common-initialization-v2':'새 규칙 · 모델 제약을 통과한 후보'};
 return changes.flatMap(original=>{
  if(original.path==='/source_run_id')return [];
  if(original.path.startsWith('/optimizer/saved_seed'))return original.path==='/optimizer/saved_seed'?[{label:'초기 배치 원본',before:original.before?'저장 실행 '+original.before.run_id.slice(0,8)+' · 행 '+original.before.row_id:'사용 안 함',after:original.after?'저장 실행 '+original.after.run_id.slice(0,8)+' · 행 '+original.after.row_id:'사용 안 함',beforeKnown:true}]:[];
  // The request may omit a default that the saved evaluator actually used.
  // Only a saved effective value can establish that this is unchanged.
  const change={...original};
  if(change.path==='/optimizer/initialization_version'&&change.before===undefined&&savedRun?.research_configuration?.solver_policy==='generic_v1'){
   change.before=savedRun.optimizer?.initialization_version??savedRun.initialization?.version??'calculator-common-initialization-v1';
  }
  if(change.path==='/model_config/grid_metres'&&change.before===undefined){
   const saved=savedConfig.grid_metres??savedConfig.geometry_payload?.grid_metres;
   if(saved!==undefined)change.before=saved;
  }
  if(change.before!==undefined&&JSON.stringify(change.before)===JSON.stringify(change.after))return [];
  const parts=change.path.split('/').filter(Boolean),key=parts.at(-1),field=parts[0]==='model_config'?fields.find(f=>f.key===key&&(f.source==='common')===parts.includes('common')):null;
  let label=field?.label||names[key]||'추가 설정',format=v=>{
   if(v===undefined||v===null)return simple(v);
   if(key==='wallclock_limit_seconds')return v===0?'시간 제한 없음':v+'초';
   const choice=field?.choices?.find(x=>x[0]===v);if(choice)return choice[1];
   if(typeof v==='number')return String(Number((v/(field?.scale||1)).toFixed(6)))+(field?.unit?' '+field.unit:key==='grid_metres'?' m':key==='generations'?'세대':key==='population'?'개':'');
   if(typeof v==='boolean')return simple(v);
   if(choices[v])return choices[v];
   if(key==='algorithm'&&['NSGA-III','NSGA-II','MOEA/D','RVEA'].includes(v))return v;
   return '설정 변경';
  };
  if(parts[0]==='source_run_id'){
   label='저장 실행 연결';format=v=>v?'복사한 저장 실행과 연결':'연결 없음';
  }else if(parts[0]==='resource_contract'){
   const scalarFormat=format;
   label='공통 비용·재고';format=resource;
   const suffix={mode:'방식',limit:'상한',min:'최소',max:'최대',value:'정확 수량'};
   if(parts[1]==='budget'){label='공통 예산'+(parts.length>2?' '+(suffix[key]||'설정'):'');format=parts.length===2?limit:scalarFormat;}
   if(parts[1]==='sensor_counts'){label=(parts[2]?sensor(parts[2])+' ':'')+'수량 제한'+(parts.length>3?' '+(suffix[key]||'설정'):'');format=parts.length===2?v=>v===undefined?simple(v):resource({sensor_counts:v}):parts.length===3?limit:scalarFormat;}
   if(parts[1]==='cost'){label=parts[2]==='site_cost'?'설치 지점당 비용':parts[3]?sensor(parts[3])+' 장비당 비용':'장비 비용';format=v=>typeof v==='object'&&v!==null?'비용 설정 변경':simple(v);}
  }else if(['enabled_sensor_ids','objectives','objective_ids','diagnostic_ids'].includes(parts[0])){
   label=({enabled_sensor_ids:'사용 센서',objectives:'최적화 목적',objective_ids:'최적화 목적',diagnostic_ids:'진단 항목'})[parts[0]];
   format=v=>Array.isArray(v)?v.map(parts[0]==='enabled_sensor_ids'?sensor:metric).join(', ')||'없음':simple(v);
  }
  return [{label,before:format(change.before),after:format(change.after),beforeKnown:change.before!==undefined}];
 });
}
function executionConstraintLabel(id,index){
 const names={budget:'공통 예산',budget_excess:'공통 예산 상한',shared_budget:'공통 예산 상한',resource_budget:'공통 예산 상한',radar_inventory:'Radar 수량',rf_inventory:'RF 수량',rf_scanner_inventory:'RF 수량',eoir_inventory:'EO/IR 수량',radar_shortfall:'Radar 관측 목표',joint_shortfall:'공동 관측 목표',total_excess:'전체 설치 수량'};
 if(names[id])return names[id];
 const sensor=id.includes('radar')?'Radar':id.includes('eoir')?'EO/IR':id.includes('rf')?'RF':null;
 if(id.includes('budget'))return '공통 예산 상한';
 if(sensor&&/inventory|count|stock/.test(id))return sensor+' 수량 제한';
 return '추가 설치 제약 '+(index+1);
}
function replacedResourceField(key,cid){
 return ['resource_mode','radar_stock','eo_stock','radar_limit','rf_limit','eoir_limit'].includes(key)||cid==='HMSP-2D-V1'&&['radar_acquisition','rf_acquisition','eoir_acquisition','radar_annual','rf_annual','eoir_annual','site_cost','horizon_years'].includes(key);
}
function renderExecutionDetails(parent,p){
 const meta=registryData.bundles.find(b=>b.id===p.experiment_contract_id),metric=id=>meta?.metrics.find(m=>m.id===id),sensor=id=>meta?.sensors.find(s=>s.id===id)?.name||'센서 이름 미제공';
 const root=document.createElement('div');root.className='executionReadable';root.dataset.executionSha=p.execution_sha256;parent.append(root);
 const section=(title,rows)=>{const h=document.createElement('h3');h.textContent=title;root.append(h);evidenceTable(root,['항목','확정 값'],rows);};
 const m=p.solver.objective_projection?.effective_indices.length??p.objectives.length,part=p.optimizer.ref_partitions??p.solver.reference_directions?.partitions;
 section('계산 계획',[['모델',meta?.name||p.experiment_contract_id],['알고리즘',p.optimizer.algorithm],['개체 / 세대',p.optimizer.population+'개 / '+p.termination.generation_budget+'세대'],['탐색 평가 예산',p.declared_nfe+'회'],['seed',p.optimizer.seed],['참조방향',p.optimizer.algorithm!=='NSGA-III'?'미사용':part?directionCount(m,part)+'개 · 목적 '+m+'개 · h='+part:'기존 정책에 따름'],['종료',p.termination.generation_budget+'세대'+(p.solver.policy==='generic_v1'&&p.termination.wallclock_limit_seconds===0?' · 시간 제한 없음':' 또는 '+p.termination.wallclock_limit_seconds+'초')+' · 사용자 중지 가능']]);
 const unit=u=>({dimensionless:'무차원',synthetic_cost:'합성 비용 점수'})[u]||u||'';
 section('센서와 목적 순서',[['센서 순서',p.registry.sensor_order.map((id,i)=>(i+1)+'. '+sensor(id)+(p.enabled_sensor_ids.includes(id)?'':' (비활성)')).join(' → ')],...p.registry.objective_order.map((id,i)=>['목적 '+(i+1),(metric(id)?.name||'평가 항목 이름 미제공')+' · '+(metric(id)?.direction==='maximize'?'최대화':metric(id)?.direction==='minimize'?'최소화':'방향 미제공')+' · '+unit(metric(id)?.unit)]),['진단만 계산',p.diagnostic_ids.map(id=>metric(id)?.name||'진단 항목 이름 미제공').join(', ')||'없음']]);
 const resources=p.model_config?._resource_contract;
 const limits=resources?[
  resources.budget?.mode==='MAX'?'공통 예산 '+resources.budget.limit+' 이하':'예산 제한 없음',
  ...Object.entries(resources.sensor_counts||{}).map(([id,c])=>sensor(id)+' '+(c.mode==='OFF'?'수량 제한 없음':c.mode==='MAX'?c.max+'대 이하':c.mode==='EXACT'?c.value+'대 고정':c.min+'–'+c.max+'대'))
 ].join(' · '):p.constraint_order.map(executionConstraintLabel).join(' · ')||'제약 없음';
 section('비용과 제약',[['비용 정의',metric('cost')?.definition||p.cost_definition?.name||'모델의 비용 정의 참조'],['적용 중인 제한',limits],['제약 허용오차',String(p.feasibility_tolerance)]]);
 if(p.solver.objective_projection?.excluded.length)noteText(root,'고정 수량의 비용은 상수입니다. 비용값은 보존하며, 성능 목적 '+m+'개로 탐색·참조방향을 구성합니다.');
 if(p.installation_domain)section('설치 가능 영역',[['설치 위치',p.installation_domain.mode==='inside_area'?'평가영역 안에만 설치':p.installation_domain.mode==='model_supported'?'모델이 확인한 무기여 위치 제외 · 영역 밖도 기여하면 허용':'모델 기본 후보지 · 영역 밖 포함 가능'],['설치 가능 후보',p.installation_domain.eligible_sites+' / '+p.installation_domain.candidate_count+'곳'],['탐색 센서 슬롯',p.installation_domain.active_slots+'개'],['영역 조건과 정량 목표','설치 영역은 탐색 공간 제한이며 성능 목표 선택과 독립']]);
 const schema=registryData.ui_models?.[p.experiment_contract_id],values=p.model_config.parameters||p.model_config.rf_config||p.model_config;
 if(schema){const rows=[],seen=new Set();for(const sections of Object.values(schema.groups||{}))for(const part of sections)for(const field of part.fields||[]){if(seen.has(field.key)||resources&&replacedResourceField(field.key,p.experiment_contract_id))continue;seen.add(field.key);const source=field.source==='common'?p.model_config.common:values,value=source?.[field.key];if(value===undefined||value===null||typeof value==='object')continue;const choice=field.choices?.find(x=>x[0]===value);rows.push([(part.title?part.title+' · ':'')+field.label,choice?choice[1]:typeof value==='boolean'?(value?'사용':'사용 안 함'):String(typeof value==='number'?Number((value/(field.scale||1)).toFixed(6)):value)+(field.unit?' '+field.unit:'')]);}if(rows.length)section('이번 계산에 적용되는 센서·영역 입력',rows);}
 section('초기화',[['초기 배치',({random:'무작위',binary_random:'무작위',greedy:'Greedy',milp:'MILP · 국소 선형 근사',saved:'저장 결과의 성능 1순위 배치','legacy constrained sample / CountRepair':'무작위 · 센서 수량 조건 반영'})[p.solver.initialization]||'저장된 초기 배치 방식'],['준비 예산',p.initialization_preparation?p.initialization_preparation.max_model_evaluations+'회 / '+p.initialization_preparation.max_seconds+'초 · 탐색 평가와 별도':'저장된 실행의 준비 조건 사용']]);
 if(p.optimizer?.saved_seed){const ref=p.optimizer.saved_seed;section('초기 배치 원본',[['저장 실행',ref.run_id.slice(0,8)],['배치 번호',ref.row_id],['선택 기준',(metric(ref.sort)?.name||'성능')+' 우선 · '+(ref.targets?'저장 목표 통과':'전체 누적 비지배')+' 배치의 1순위'],['탐색 방식','원본 배치를 새 조건으로 재평가 · 첫 개체에 삽입 · 나머지는 무작위']]);}
 const d=document.createElement('details'),sum=document.createElement('summary');sum.textContent='후보 순서와 좌표 · '+p.candidates.sites.length+'곳';d.append(sum);evidenceTable(d,['후보 순서','동쪽 x (m)','북쪽 y (m)'],p.candidates.sites.map((xy,i)=>[i+1,...xy]));root.append(d);
}
function showConfirmed(){
 if(setting!=='optimizer'||!preview?.execution_snapshot)return;const p=preview.execution_snapshot,g=group('확정 실행 설정');g.id='confirmedExecution';if(previewPending)noteText(g,'아래는 마지막 유효 설정입니다. 현재 입력을 확인하기 전에는 계산할 수 없습니다.');
 noteText(g,`${p.optimizer.algorithm} · 개체 ${p.optimizer.population} · ${p.termination.generation_budget}세대 · 탐색 ${p.declared_nfe}회`);
 const d=document.createElement('details'),summary=document.createElement('summary');d.id='executionSnapshotDetails';summary.textContent='확정 조건 상세';d.append(summary);renderExecutionDetails(d,p);g.append(d);
 const button=document.createElement('button');button.id='expandExecutionDetails';button.textContent='확정 조건 크게 보기';button.onclick=()=>{let dialog=$('executionDetailsDialog');if(dialog)dialog.remove();dialog=document.createElement('dialog');dialog.id='executionDetailsDialog';const head=document.createElement('div');head.className='dialogHead';const title=document.createElement('h2');title.textContent='확정 실행 조건';const close=document.createElement('button');close.textContent='닫기';close.onclick=()=>dialog.close();head.append(title,close);dialog.append(head);renderExecutionDetails(dialog,p);document.body.append(dialog);dialog.showModal();};g.append(button);
 if(copyParent)noteText(g,'복사한 저장 실행 · '+copyParent.slice(0,8));
}
const detailedConfirmed=showConfirmed;
showConfirmed=function(){detailedConfirmed();const g=$('confirmedExecution');if(!g)return;g.style.overflowWrap='anywhere';if(copyParent){const summary=document.createElement('div');summary.id='copyChangeSummary';summary.className='formNote';summary.setAttribute('aria-live','polite');if(previewPending||configurationChanges===null)noteText(summary,'변경 내용을 확인하고 있습니다…');else{const saved=run?.run_id===copyParent?run:null,rows=readableConfigurationChanges(configurationChanges,registryData,draft.sensor,saved?.config||{},saved);if(rows.length){noteText(summary,'저장 조건에서 바꾼 항목');for(const row of rows)noteText(summary,row.beforeKnown?`${row.label}: ${row.before} → ${row.after}`:`${row.label}: 현재 ${row.after} · 이전 실행과의 값 비교는 확인되지 않았습니다.`);}else noteText(summary,'저장 조건에서 바꾼 항목이 없습니다.');}g.append(summary);}};
renderSettings=function(){workflowPrior.settings();showConfirmed();};
apply=async function(){const cid=draft.sensor,before=JSON.stringify(requestConfiguration());await workflowPrior.apply();if(previewPending||cid!==draft.sensor||before!==JSON.stringify(requestConfiguration()))return;confirmedRequest=JSON.parse(before);confirmedExecution=preview.execution_snapshot;configurationChanges=null;if(copyParent){const parent=copyParent;const value=preview.configuration_changes?.parent_run_id===parent?preview.configuration_changes:await api(cid,'engine/diff',{parent_run_id:parent,request:confirmedRequest});if(cid!==draft.sensor||parent!==copyParent||before!==JSON.stringify(requestConfiguration()))return;configurationChanges=value.changes;}renderSettings();};
$('applyDraft').onclick=safe(()=>apply());
async function recoverPending(cid,pending){try{const value=await api(cid,'engine/requests/'+encodeURIComponent(pending.request_id));localStorage.removeItem(pendingKey(cid));clearRun();safe(histories)();await loadRun(value.run_id);notice('접수된 동일 요청의 저장 실행을 복원했습니다. 새 계산은 만들지 않았습니다.');return true;}catch(e){if(e.httpStatus===404)return false;throw e;}}
$('calculate').onclick=safe(async()=>{if(creating)return;if(previewPending||!confirmedExecution||JSON.stringify(requestConfiguration())!==JSON.stringify(confirmedRequest))throw Error('현재 조건의 확정 설정을 먼저 확인하세요.');const cid=draft.sensor,request=structuredClone(confirmedRequest),execution=structuredClone(confirmedExecution);lockCreation(true);try{let pending=JSON.parse(localStorage.getItem(pendingKey(cid))||'null');if(pending){if(await recoverPending(cid,pending))return;if(JSON.stringify(pending.request)!==JSON.stringify(request))throw Error('이전 요청의 접수 여부가 확인되지 않았습니다. 이전 조건을 복원하여 같은 요청 ID로 확인하세요.');}else{pending={request_id:crypto.randomUUID(),execution_sha256:execution.execution_sha256,request};localStorage.setItem(pendingKey(cid),JSON.stringify(pending));}notice('로딩중… 확정 설정 제출','busy');const job=await api(cid,'engine/runs',pending.request,{'X-Request-ID':pending.request_id,'X-Execution-SHA256':pending.execution_sha256});localStorage.removeItem(pendingKey(cid));copyParent=null;clearRun();safe(histories)();await loadRun(job.run_id);connectionState('연결됨');}catch(e){if(e.httpStatus&&e.httpStatus<500&&!String(e.message).includes('RESERVED'))localStorage.removeItem(pendingKey(cid));if(e.connectionFailure)connectionState('끊김 · 요청 ID 보존됨');throw e;}finally{lockCreation(false);}});
$('copyRun').onclick=safeCopy(async()=>{const restriction=savedRunCopyRestriction();if(restriction)throw Object.assign(Error(restriction.message),{code:restriction.code});if(draft.sensor===RF&&!registryData?.ui_models?.[RF]?.parameter_keys_by_version?.[run.config?.evaluator_version])throw Error('RF 모델 정보를 확인하지 못했습니다. 모델 연결을 확인한 뒤 다시 불러오세요.');if(!configured())return workflowPrior.copy();const parent=run.run_id;await workflowPrior.copy();copyParent=parent;await apply();setting='optimizer';renderSettings();notice('저장 실행을 새 초안으로 복사했습니다. 계산 탭에서 변경 항목과 확정 설정을 확인하세요.');});
fetchRun=async function(id,g=null){const cid=draft.sensor,owner=loadingRun;try{await workflowPrior.fetch(id,g);if(cid!==draft.sensor)return;syncLoadedRunChoice();connectionState('연결됨');if(run?.run_id===id){$('exportRaw').disabled=!terminal.has(run.state);if(run.cancel_requested&&!terminal.has(run.state))$('runtimeStatus').textContent='중지 요청 · '+$('runtimeStatus').textContent;}}catch(e){if(e.superseded||owner!==loadingRun||cid!==draft.sensor)return;if(e.connectionFailure&&cid===draft.sensor){connectionState('끊김 · 재연결 중');clearTimeout(poller);poller=setTimeout(safe(()=>loadRun(id,g)),2000);notice(e.message+' · 연결을 다시 확인합니다. 마지막 계산 상태는 유지합니다.','error');return;}throw e;}};
renderInspector=function(){workflowPrior.inspector();if(!run)return;const parent=$('inspectorBody');noteText(parent,`실행 ${run.run_id} · ${run.termination_reason||states[run.state]||run.state} · ${run.storage_complete?'저장 완결':'진행 중 또는 부분 저장'}`);noteText(parent,'결과 복원은 저장 자료 열람입니다. 중단된 solver의 계산 재개는 지원하지 않습니다.');jsonDetails(parent,'고정 설정과 평가 횟수',{config_sha256:run.config_sha256,execution_snapshot:run.execution_snapshot,registry:run.registry,counters:run.counters,optimizer:run.optimizer,environment:run.environment,source:run.optimizer_code_sha256});const compareButton=document.createElement('button');compareButton.id='compareRuns';compareButton.textContent='다른 저장 실행과 조건 비교';compareButton.onclick=safe(openRunComparison);parent.append(compareButton);const contract=document.createElement('button');contract.textContent='원시·지도·진단 출처 확인';contract.id='resultContract';contract.onclick=safe(async()=>{const cid=draft.sensor,id=run.run_id,v=await api(cid,'engine/runs/'+id+'/contract');if(run?.run_id!==id||draft.sensor!==cid)return;jsonDetails(parent,'동일 원시 결과 계약',v,'resultContractDetails').open=true;});parent.append(contract);};
async function openRunComparison(){const left={experiment_contract_id:draft.sensor,run_id:run.run_id};const dialog=document.createElement('dialog');dialog.id='runComparison';const title=document.createElement('h2');title.textContent='저장 실행의 조건·지표 정의 비교';const model=document.createElement('select');model.id='comparisonModel';option(model,registryData.bundles.map(b=>[b.id,b.name]),left.experiment_contract_id);const chooser=document.createElement('select');chooser.id='comparisonRun';const result=document.createElement('div'),close=document.createElement('button'),compareButton=document.createElement('button');close.textContent='닫기';close.onclick=()=>{dialog.close();dialog.remove();};compareButton.textContent='차이 확인';compareButton.id='compareRunApply';const fill=async()=>{const cid=model.value,p=await api(cid,cid===EO?'jobs':'runs');if(model.value!==cid)return;const rows=Array.isArray(p)?p:p.runs;option(chooser,rows.map(r=>[r.run_id||r.id,(r.run_id||r.id)+' · '+(states[r.state]||r.state)]));};model.onchange=safe(fill);compareButton.onclick=safe(async()=>{const v=await api(left.experiment_contract_id,'engine/compare',{left,right:{experiment_contract_id:model.value,run_id:chooser.value}});result.replaceChildren();noteText(result,v.explanation);jsonDetails(result,'정의·단위 비교와 구조화된 설정 차이',v,'runComparisonResult').open=true;const a=document.createElement('a');a.textContent='비교 대상의 원시 결과 화면 열기';a.href='/live.html?contract='+encodeURIComponent(model.value)+'&run='+encodeURIComponent(chooser.value);a.target='_blank';a.rel='noopener';result.append(a);});dialog.append(title,model,chooser,compareButton,close,result);document.body.append(dialog);dialog.showModal();await fill();}
window.addEventListener('DOMContentLoaded',()=>{connectionState('확인 중');const button=document.createElement('button');button.id='recoverSubmission';button.textContent='미확정 제출 확인';button.onclick=safe(async()=>{const pending=JSON.parse(localStorage.getItem(pendingKey(draft.sensor))||'null');if(!pending){notice('확인할 미확정 제출이 없습니다.');return;}if(!await recoverPending(draft.sensor,pending))notice('서버에 접수 기록이 없습니다. 같은 조건에서 계산을 누르면 보존한 요청 ID로 제출합니다.');});$('runHistory').after(button);});
