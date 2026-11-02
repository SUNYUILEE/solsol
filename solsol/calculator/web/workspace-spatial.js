'use strict';
function renderDraftGoalState(){
 if(!registryData||!draft?.research)return;
 let el=$('draftGoalState');if(!el){el=document.createElement('div');el.id='draftGoalState';el.className='draftGoalState';($('settingsExplanationBody')||document.querySelector('.settingFoot')).prepend(el);}
 const q=requestConfiguration(),explicit=draft.sensor==='HMSP-EXEC-V1';el.replaceChildren();
const title=document.createElement('b');title.textContent='다음 계산 · '+(explicit?'모델 품질 목표':goalSummary(q.goals,registered()))+' · '+resourceSummary({...q.model_config,_resource_contract:q.resource_contract||q.model_config._resource_contract});el.append(title);
 const bound=!previewPending&&confirmedRequest&&JSON.stringify(q)===JSON.stringify(confirmedRequest)&&preview?.execution_snapshot?.experiment_contract_id===draft.sensor;
 const constraints=bound?preview.execution_snapshot.registry.constraint_order:[];
 if(constraints.some(k=>/shortfall/.test(k)))noteText(el,'이 모델의 필수 제약: '+constraints.filter(k=>/shortfall/.test(k)).map(constraintName).join(' · ')+' · 영역 목표를 꺼도 유지됩니다.');
 if(explicit)noteText(el,q.model_config?.goals?'품질 목표는 모델 제약 G에 반영됩니다.':'품질 목표 미설정');
 const cost=bound?configurationSummary?.objective_projection?.excluded.find(v=>v.objective_id==='cost'):null;
 if(cost)noteText(el,`전량 사용 비용 ${cost.cost} 고정 · 목표 커버율을 낮춰도 비용은 같습니다. 같은 수량·비용에서 성능이 다른 배치를 비교합니다.`);
 if(run&&run.experiment_contract_id===draft.sensor){el.dataset.savedRunId=run.run_id;noteText(el,'현재 저장 결과 '+run.run_id.slice(0,8)+' · '+goalSummary(savedAreaGoals(),run.metadata)+' · '+resourceSummary(run.config)+' · 초안 변경은 저장 결과에 적용되지 않습니다.');}else delete el.dataset.savedRunId;
}
// Spatial inspection is a separate, raw-bound request; it never delays run progress.
(()=>{
 const render=renderMaps,cache=new Map(),pending=new Map(),errors=new Map();
 const settingsBeforeGoalState=renderSettings;
 renderSettings=function(){settingsBeforeGoalState();renderDraftGoalState();};
 const fetchBeforeGoalState=fetchRun;
 fetchRun=async function(id,g=null){await fetchBeforeGoalState(id,g);renderDraftGoalState();};
 const clearBeforeGoalState=clearRun;
 clearRun=function(){clearBeforeGoalState();renderDraftGoalState();};
 const request=requestConfiguration;
 requestConfiguration=function(){const q=request();if(q.solver_policy==='generic_v1'&&q.optimizer.algorithm==='NSGA-III')q.optimizer.ref_partitions=effectivePartitions(selection(),searchObjectiveCount(),q.optimizer.population);if(draft.optimizer.wallclock_limit_seconds!==undefined)q.optimizer.wallclock_limit_seconds=draft.optimizer.wallclock_limit_seconds;return q;};
 function ensure(row){if(!row||!run||run.spatial_loading!=='ON_DEMAND_RAW_ROW')return;const cid=draft.sensor,rid=run.run_id,hash=run.config_sha256,key=cid+':'+rid+':'+hash+':'+row.id;
  if(cache.has(key)){Object.assign(row,cache.get(key));return;}
  if(pending.has(key)||errors.has(key))return;
  pending.set(key,api(cid,'engine/runs/'+rid+'/spatial/'+row.id).then(p=>{
   if(p.run_id!==rid||p.config_sha256!==hash||p.row.id!==row.id||p.row.run_id!==rid||p.row.config_sha256!==hash||p.row.evaluator_sha256!==row.evaluator_sha256||JSON.stringify(p.row.X)!==JSON.stringify(row.X)||JSON.stringify(p.row.F)!==JSON.stringify(row.F)||JSON.stringify(p.row.G)!==JSON.stringify(row.G)||p.row.cost!==row.cost)throw Error('무결성 오류: 지도와 원시 X/F/G·평가기 결속 불일치');
   if(p.row.spatial_status?.startsWith('UNAVAILABLE'))throw Error('공간 자료 조회 불가: '+p.row.spatial_reason);
   cache.set(key,p.row);if(cache.size>256)cache.delete(cache.keys().next().value);Object.assign(row,p.row);
  }).catch(e=>{errors.set(key,e.message);if(errors.size>256)errors.delete(errors.keys().next().value);}).finally(()=>{pending.delete(key);if(draft.sensor===cid&&run?.run_id===rid){for(const r of [...run.rows,...initialRows])if(r.id===row.id&&cache.has(key))Object.assign(r,cache.get(key));renderMaps();}}));
 }
 function rowKey(row){return draft.sensor+':'+run.run_id+':'+run.config_sha256+':'+row.id;}
 function annotate(host,row){if(!host||!row)return;const key=rowKey(row);if(!errors.has(key)&&!pending.has(key))return;for(const e of host.querySelectorAll('[data-evaluation-point]'))e.style.opacity='.25';}
 // Status is outside every SVG flex container and occupies a fixed slot.
 function requestStatus(rows,deferred=false,selectionError=''){
  const states=rows.filter(Boolean).map(row=>({key:rowKey(row),id:row.id})).filter(v=>errors.has(v.key)||pending.has(v.key));
  for(const [id,parent] of [['mapRequestStatus',document.querySelector('body>footer')],['largeMapRequestStatus',$('mapDialog').querySelector('.dialogHead')]]){
   let host=$(id);if(!host){host=document.createElement('div');host.id=id;host.className='mapRequestStatus';const text=document.createElement('span');text.setAttribute('role','status');text.setAttribute('aria-live','polite');const retry=document.createElement('button');retry.textContent='다시 조회';retry.setAttribute('aria-label','지도 자료 다시 조회');host.append(text,retry);if(id==='largeMapRequestStatus')parent.insertBefore(host,parent.lastElementChild);else parent.append(host);}
   const message=(selectionError?'배치 목록 조회 실패: '+selectionError+' · 해 목록에서 다시 조회하세요. ':deferred?'표시할 배치 선택을 확인 중입니다. ':'')+states.map(v=>'행 '+v.id+' · '+(errors.get(v.key)||'지도 자료 조회 중…')).join(' / '),failed=states.filter(v=>errors.has(v.key));
   host.firstChild.textContent=message;host.firstChild.title=message;host.dataset.state=selectionError||failed.length?'error':deferred||states.length?'loading':'ready';
   const retry=host.lastChild;retry.style.visibility=failed.length?'visible':'hidden';retry.disabled=!failed.length;retry.onclick=()=>{for(const v of failed)errors.delete(v.key);renderMaps();};
  }
 }
 renderMaps=function(){const on=mode==='result'&&run?.spatial_loading==='ON_DEMAND_RAW_ROW',row=on?currentRow():null,compare=on&&$('compareMaps').matches('[aria-pressed=true]'),base=compare?(referenceRow||initialRows.find(r=>String(r.id)===String(initial))):null,deferred=on&&typeof placementDefersMainSpatial==='function'&&(placementDefersMainSpatial()||placementPending&&!placementLive()),selectionError=on&&typeof placementError==='string'?placementError:'';if(on){if(!deferred&&!selectionError)ensure(row);ensure(base);}render();syncSensorSymbols();requestStatus(on?[row,base]:[],deferred,selectionError);if(on){annotate($('mainMap'),row);if(compare)annotate($('initialMap'),base);if($('mapDialog').open){annotate($('largeMap'),row);if(compare)annotate($('largeInitialMap'),base);}}
 };
})();
