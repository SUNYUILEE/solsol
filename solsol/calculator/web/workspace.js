'use strict';
const M=WorkspaceModel,$=id=>document.getElementById(id),EO=M.EO,RF=M.RF;
let draft,defaults,token,setting='common',dock='solutions',mode='design',preview=null,run=null,selected=null,initial=null,site=null,requestEpoch=0,previewEpoch=0,poller=null,player=null,zoom=1,compared=new Set(),filter='all',sort='cost',cluster='all',initialRows=[],qualityReport=null,creating=false;
let loadingRun=false,pendingRun=null,slideTimer=null,referenceRow=null,referenceGeneration=0,plotMode='tradeoff',plotAngle=35,panX=0,panY=0;
let workbench=null,previewTimer=null,previewPending=false,previewFailure='',baselinePreview=null,previewController=null;
function freezeConditionBaseline(){if(run&&run.experiment_contract_id===draft.sensor)baselinePreview={problem:structuredClone({...run.problem,_parameters:run.config?.parameters,_rf:run.config?.rf_config}),row:structuredClone(currentRow()||null),metadata:structuredClone(run.metadata||null),run_id:run.run_id,goals:structuredClone(savedAreaGoals()),label:'저장 실행 '+run.run_id.slice(0,8)+' · '+run.generation+'세대',cid:draft.sensor};else if(preview?.problem)baselinePreview={problem:structuredClone(preview.problem),row:null,label:'고정한 이전 조건 · 성능 미계산',cid:draft.sensor};}

const frameCache=new Map();
let bootRunRequest=null;
function cancelBootRun(){const boot=bootRunRequest;bootRunRequest=null;boot?.controller.abort();}
function settledRequest(promise){return promise.then(value=>({value}),error=>({error}));}
async function requestValue(promise){const result=await promise;if(result.error)throw result.error;return result.value;}
function startBootRun(id,cid,authority){
 if(!id||!registryData?.bundles.some(b=>b.id===cid))return;
 const controller=new AbortController(),boot={id,cid,authority,controller,ready:false,owner:null};
 bootRunRequest=boot;
 boot.promise=settledRequest(api(cid,(cid===EO?'jobs/':'runs/')+id+'?view=summary',undefined,{}, {signal:controller.signal}));
}
async function readRunPacket(cid,id,g,signal,query){
 const boot=bootRunRequest;
 if(boot&&boot.ready&&boot.owner===loadingRun&&boot.cid===cid&&boot.id===id&&g===null){
  try{
   const result=await boot.promise;
   if(boot!==bootRunRequest||signal?.aborted||previewEpoch!==boot.authority.previewEpoch)throw Object.assign(Error('요청이 바뀌었습니다.'),{superseded:true});
   if(result.error)throw result.error;
   return result.value;
  }finally{if(bootRunRequest===boot)bootRunRequest=null;}
 }
 return api(cid,(cid===EO?'jobs/':'runs/')+id+'?'+query,undefined,{}, {signal});
}
function representative(rows){const installed=rows.filter(r=>r.sensor_counts.some(n=>n>0)).slice().sort((a,b)=>a.cost-b.cost||a.id-b.id);return installed[Math.floor(installed.length/2)]||rows[0];}
function syncSelectionBar(){const rows=visibleRows();option($('solutionPicker'),rows.length?rows.map(r=>[String(r.id),`행 ${r.id} · 비용 ${r.cost} · R ${r.sensor_counts[0]} / ${draft.sensor===EO?'E':'RF'} ${r.sensor_counts[1]}`]):[['','표시할 해 없음']],selected??'');$('solutionBar').hidden=!run||mode!=='result';$('selectionPosition').textContent=rows.length?`${Math.max(0,rows.findIndex(r=>r.id===selected)+1)} / ${rows.length}개`:'0개';$('pinSolution').disabled=selected===null;}

const terminal=new Set(['completed','cancelled','time_limit','failed','interrupted']);
const states={queued:'대기',initializing:'초기 배치 준비',preparing:'준비',running:'계산 중',verifying:'검증 중',saving:'저장 중',completed:'저장 완료',cancelled:'중지됨',time_limit:'시간 제한 종료',failed:'실패',interrupted:'중단된 저장 기록'};
const formatQuality=v=>draft.sensor===RF?(v*100).toFixed(2)+'점':(v*100).toFixed(2)+'%';
function notice(text,type=''){ $('notice').textContent=text;$('notice').className='notice '+type; }
function safe(fn,copyOperation=false){return async(...args)=>{const copyOrigin=copyOperation&&typeof configurationCopyPending!=='undefined'&&configurationCopyPending?{cid:draft?.sensor,run_id:run?.run_id,generation:run?.generation}:null;try{await fn(...args);}catch(e){if(copyOrigin&&!e.requestOrigin)e.requestOrigin=copyOrigin;if(copyOperation&&typeof configurationCopyPending!=='undefined'&&configurationCopyPending)throw e;const origin=e.requestOrigin;if(origin&&(origin.cid!==draft?.sensor||origin.run_id!==run?.run_id||origin.generation!==run?.generation))return;notice(e.message,'error');if(!run)$('runtimeStatus').textContent='요청 확인 필요';}};}
function safeCopy(fn){return safe(fn,true);}
async function api(cid,path,body,extraHeaders={},requestOptions={}){
 const controller=new AbortController();
 const upstream=requestOptions.signal,abort=()=>controller?.abort();let timer;
 if(controller){if(upstream?.aborted)abort();else upstream?.addEventListener('abort',abort,{once:true});}
 const receive=async()=>{let response;try{response=await fetch('/contracts/'+cid+'/api/'+path,{method:body?'POST':'GET',headers:{'X-Experiment-Contract':cid,...(body?{'Content-Type':'application/json','X-Run-Token':token}:{}),...extraHeaders},...requestOptions,...(controller?{signal:controller.signal}:{}),...(body?{body:JSON.stringify(body)}:{})});}catch(e){e.connectionFailure=true;throw e;}if(response.headers.get('X-Experiment-Contract')!==cid)throw Error('응답 계약 불일치');const packet=await response.json();if(!response.ok){const e=Error(packet.error||'요청 실패');e.httpStatus=response.status;e.requestPath=path;throw e;}if(!Array.isArray(packet)&&packet.experiment_contract_id!==cid)throw Error('응답 계약 누락');return packet;};
 try{return await Promise.race([receive(),new Promise((resolve,reject)=>{timer=setTimeout(()=>{const error=Error('응답을 60초 동안 받지 못했습니다. 입력과 요청 ID는 보존됩니다. 다시 불러오기 또는 미확정 제출 확인으로 재시도하세요.');error.connectionFailure=true;error.timeout=true;reject(error);controller.abort();},60000);})]);}
 catch(e){if(upstream?.aborted)e.superseded=true;throw e;}
 finally{clearTimeout(timer);upstream?.removeEventListener('abort',abort);}
}
function option(select,rows,value){select.replaceChildren();for(const [v,t] of rows){const o=document.createElement('option');o.value=v;o.textContent=t;select.append(o);}if(value!==undefined)select.value=value;}
function updateDraft(){draft.name=$('projectName').value;if(!baselinePreview)freezeConditionBaseline();previewPending=true;previewFailure='';++previewEpoch;clearTimeout(previewTimer);$('saveState').textContent='입력 중 · 미리보기 자동 갱신';$('calculate').disabled=true;if(mode==='design')$('mapBadge').textContent='조건 반영 중 · 마지막 유효 지도';renderHeader();renderSettingSummaries();if(typeof renderExecutionGuide==='function')renderExecutionGuide();notice('새 조건을 확인 중입니다. 마지막 유효 지도와 왼쪽 기준은 유지됩니다.','busy');previewTimer=setTimeout(()=>{const promise=apply(),epoch=previewEpoch;promise.catch(e=>{if(epoch!==previewEpoch)return;previewPending=true;const editing=document.activeElement;if($('settingsBody').contains(editing)&&editing?.tagName==='INPUT'&&editing.type==='number'&&(editing.value===''||editing.validity.badInput)){$('saveState').textContent='입력 중 · 값을 입력하세요';notice('입력을 마치면 조건을 확인합니다.','busy');return;}previewFailure=e.message;renderSettings();renderHeader();$('calculate').disabled=true;$('saveState').textContent='조건 확인 실패 · 입력 보존 · 다시 확인';if(typeof renderExecutionGuide==='function')renderExecutionGuide();notice(e.message+' · 마지막 유효 지도를 유지합니다.','error');});},400);}

function field(parent,label,key,values,unit='',source=null){source=source||draft.sensors[draft.sensor];const wrap=document.createElement('label');wrap.className='field';const title=document.createElement('span');title.textContent=label+(unit?' ('+unit+')':'');const input=document.createElement(values?'select':typeof source[key]==='boolean'?'input':'input');input.id='field_'+key;input.dataset.field=key;if(values)option(input,values,String(source[key]));else if(typeof source[key]==='boolean'){input.type='checkbox';input.checked=source[key];wrap.classList.add('inline');}else{input.type='number';input.step='any';input.value=source[key];}const commit=()=>{const before=source[key],next=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?null:Number(input.value)):typeof before==='number'?Number(input.value):input.value;if(Object.is(before,next))return;source[key]=next;updateDraft();if(key==='objective_contract')renderSettings();};input.onchange=commit;if(!values&&input.type!=='checkbox')input.addEventListener('input',commit);wrap.append(title,input);parent.append(wrap);return input;}
function group(title){const g=document.createElement('fieldset');g.className='fieldGroup';const l=document.createElement('legend');l.textContent=title;g.append(l);$('settingsBody').append(g);return g;}
const noteText=(parent,text)=>{const p=document.createElement('p');p.className='formNote';p.textContent=text;parent.append(p);};
function quantity(parent,label,key,source,unit,step,presets=[],scale=1,min=0,max=null){
 const wrap=document.createElement('label');wrap.className='field';const title=document.createElement('span');title.textContent=label+' ('+unit+')';const input=document.createElement('input');input.type='number';input.id='field_'+key;input.dataset.field=key;input.step=step;input.min=min;if(max!==null)input.max=max;input.value=source[key]===null||source[key]===undefined?'':source[key]/scale;
 const commit=()=>{const next=input.value===''?null:Number(input.value)*scale;if(Object.is(source[key],next))return;source[key]=next;updateDraft();};input.oninput=commit;input.onchange=commit;wrap.append(title,input);
 if(presets.length){const pick=document.createElement('select');pick.className='valuePreset';pick.setAttribute('aria-label',label+' 설정 예시');option(pick,[['','설정 예시 선택'],...presets.map(v=>Array.isArray(v)?v:[v,v+' '+unit])],'');pick.onchange=()=>{if(pick.value==='')return;input.value=pick.value;commit();pick.value='';};wrap.append(pick);}parent.append(wrap);return input;
}
function renderSettings(){
 document.querySelectorAll('[data-settings]').forEach(b=>b.setAttribute('aria-selected',b.dataset.settings===setting));$('settingsBody').replaceChildren();let g;const c=draft.sensors[draft.sensor],rf=draft.sensor===RF;
 if(draft.migrationNotice)noteText($('settingsBody'),draft.migrationNotice);
 if(setting!=='optimizer'){
  const schema=typeof registryData==='undefined'?null:registryData?.ui_models?.[draft.sensor];
  if(!schema){noteText($('settingsBody'),'모델 설정 명세를 불러오는 중입니다.');return;}
  renderSchemaFields(schema,setting,c);
  renderSettingSummaries();
 }
 if(setting==='optimizer'){
  g=group('공통 계산 계획');
  renderCommonAlgorithm(g);
  renderCommonSearchQuantities(g);
  const budget=document.createElement('p');budget.id='budgetSummary';budget.className='formNote';g.append(budget);
  if(!rf&&selection().solver_policy!=='generic_v1'){g=group('EO/IR 초기화·배치 표현');field(g,'초기 배치','initializer',[['random','무작위'],['greedy','Greedy'],['milp','MILP / ε-constraint']],'',draft.optimizer);field(g,'배치 표현','design',[['A','A · 기본 표현'],['B','B · 공간 수선'],['C','C · 계층 수선']]);}
  noteText(g,'세대 수를 늘려도 최적성이 보장되지는 않습니다. 세대별 품질 변화·다중 seed·삭제/교환 검산으로 탐색 결과를 확인하세요. 초기화와 검산의 추가 평가는 별도입니다.');renderSettingSummaries();
 }
}
function renderSettingSummaries(){
 if(!draft)return;const c=draft.sensors[draft.sensor],rf=draft.sensor===RF,nr=rf?c.radar_limit:c.radar_stock,nf=rf?c.rf_limit:c.eo_stock;
 if($('limitSummary'))$('limitSummary').textContent=c.resource_mode==='off'?'수량 제한 없음 · 후보지별 각 센서 1대까지':c.resource_mode==='all'?'Radar '+nr+'대 + '+(rf?'RF':'EO/IR')+' '+nf+'대 모두 사용':'Radar 최대 '+nr+'대 + '+(rf?'RF':'EO/IR')+' 최대 '+nf+'대 · 합계 최대 '+(nr+nf)+'대';
 if($('budgetSummary'))$('budgetSummary').textContent='초기 세대 0 + 진화 '+draft.optimizer.generations+'세대 = 저장 '+(draft.optimizer.generations+1)+'개 · 예상 최적화 평가 '+(draft.optimizer.population*(draft.optimizer.generations+1)).toLocaleString()+'회'+(rf&&draft.research?.selections?.[draft.sensor]?.solver_policy!=='generic_v1'?' · 최대 100,000회':'')+' · 실제 중지·실패 사유는 실행 상태에 표시됩니다.';
 if($('costBreakdown')){const p=$('costBreakdown'),data=preview?.summary?.presentation;p.replaceChildren();if(data){evidenceTable(p,data.cost_columns,data.cost_rows);noteText(p,data.cost_note);}else noteText(p,'모델 서비스의 비용 명세를 확인 중입니다.');}
}
function renderHeader(){document.querySelectorAll('[data-sensor]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.sensor===draft.sensor));$('contextTitle').textContent=M.label(draft.sensor);$('secondLegend').textContent=draft.sensor===EO?'EO/IR':'RF Scanner';$('mapLayer').options[2].textContent=draft.sensor===EO?'EO/IR':'RF Scanner';$('calculate').title=draft.sensor===RF?'공통 후보지의 합성 RF/Radar 측정모형 실행':'';}
async function apply(){clearTimeout(previewTimer);const epoch=++previewEpoch,cid=draft.sensor;let snapshot;try{snapshot=M.validate(draft);if(!Number.isInteger(snapshot.optimizer.generations)||snapshot.optimizer.generations<1||snapshot.optimizer.generations>1000)throw Error('진화 세대 수는 1–1000 정수로 입력하세요');if(![36,92,212].includes(snapshot.optimizer.population))throw Error('개체 수를 선택하세요');if(cid===RF&&snapshot.optimizer.population*(snapshot.optimizer.generations+1)>100000)throw Error('RF 평가 예산은 최대 100,000회입니다. 개체 수 또는 세대 수를 줄이세요');if(cid===RF&&snapshot.sensors[RF].targets!==null&&snapshot.sensors[RF].targets.some(v=>typeof v!=='number'||!Number.isFinite(v)||v<0||v>1))throw Error('Radar와 RF 목표를 각각 0–100 품질점으로 입력하세요');}catch(e){previewPending=true;throw e;}previewPending=true;$('calculate').disabled=true;notice('새 조건 미리보기 갱신 중…','busy');if(cid===EO)await api(cid,'preview',M.eoirConfig(snapshot));if(epoch!==previewEpoch||cid!==draft.sensor)return;const p=await api(cid,cid===RF?'common-preview':'workspace-preview',cid===RF?M.rfPayload(snapshot):M.preview(snapshot));if(epoch!==previewEpoch||cid!==draft.sensor)return;preview=p;previewPending=false;if(!baselinePreview)freezeConditionBaseline();$('saveState').textContent='미리보기 최신 · 계산 준비';$('calculate').disabled=!p.execution_supported||snapshot.optimizer.algorithm!=='NSGA-III'||creating||!!run&&!terminal.has(run.state);notice('미리보기 최신 · 설정을 바꾸면 오른쪽 지도에 자동 반영됩니다. 계산 실행은 별도입니다.');if(mode==='design')renderMaps();renderSettingSummaries();}

function modeTo(next){mode=next;document.body.classList.toggle('design',mode==='design');site=null;syncSelectionBar();$('designMode').setAttribute('aria-pressed',mode==='design');$('resultMode').setAttribute('aria-pressed',mode==='result');renderMaps();renderInspector();}
function mapHTML(p,row){if(!p)return '<div class="empty"><b>지도를 준비하고 있습니다</b><p>유효한 설정을 입력하면 미리보기가 자동으로 표시됩니다.</p></div>';let svg=LiveCore.map(p,row,{layer:$('mapLayer').value,candidates:true,candidateLabels:$('showLabels').checked,defense:$('showArea').checked,demand:draft.sensor===EO&&$('showDemand').checked});if(draft.sensor===RF){svg=svg.replaceAll('EO/IR','RF Scanner').replaceAll('>E</text>','>F</text>').replace(' / E ',' / RF ');if($('showDemand').checked){const unit=(p.map_metres||20000)/800;const dots=p.demand.map((xy,i)=>{const status=row?.rf_status?.[i]||'미평가';const color=status==='CONDITIONAL_LOCAL_BOUND'?'#20794c':status==='DEGENERATE_GEOMETRY'?'#b07627':'#687d88';return `<circle data-rf-status="${status}" cx="${60+xy[0]/unit}" cy="${850-xy[1]/unit}" r="4" fill="${color}"><title>RF 평가점 ${i+1} · ${status}</title></circle>`;}).join('');svg=svg.replace('</svg>',dots+'</svg>');}}return svg;}
function currentRow(){return (typeof resultRows==='function'?resultRows():run?.rows||[]).find(r=>String(r.id)===String(selected));}
function mapDifference(row,base,p,host=$('mainMap')){
 const svg=host.querySelector('svg');if(!svg||!row||!base)return;
 const x=M.rowX(row),y=M.rowX(base);let same=0,added=0,removed=0,marks='';
 for(let i=0;i<x.length;i++)for(let t=0;t<2;t++){if(x[i][t]&&y[i][t])same++;if(x[i][t]===y[i][t])continue;const add=x[i][t]===1;add?added++:removed++;const unit=(p.map_metres||20000)/800,cx=60+p.sites[i][0]/unit+(t?7:-7),cy=850-p.sites[i][1]/unit;marks+=`<circle data-difference="${add?'added':'removed'}" cx="${cx}" cy="${cy}" r="17" fill="none" stroke="${add?'#128047':'#b12c62'}" stroke-width="4" ${add?'':'stroke-dasharray="5 4"'}><title>${add?'추가':'제거'} · 후보 ${i+1} · ${t?draft.sensor===EO?'EO/IR':'RF':'Radar'}</title></circle>`;}
 const g=document.createElementNS('http://www.w3.org/2000/svg','g');g.innerHTML=marks;svg.append(g);$('differenceSummary').textContent=`기준 대비: 공통 ${same}대 · 초록 실선 +${added}대 · 자주 점선 −${removed}대 · Hamming ${added+removed}`;
}
function renderMaps(){const p=mode==='result'?run?.problem:preview?.problem,row=mode==='result'?currentRow():null;$('mainMap').innerHTML=mapHTML(p,row);if($('compareMaps').matches('[aria-pressed=true]')&&mode==='result')$('initialMap').innerHTML=mapHTML(p,referenceRow||initialRows.find(r=>String(r.id)===String(initial)));if($('mapDialog').open){$('largeMap').innerHTML='<div class="largeMapCaption">'+(mode==='result'?'선택 · '+run.generation+'세대 행 '+(row?.id??'없음')+' · 비용 '+(row?.cost??'—'):'공통 기하 초안 · 성능 미계산')+'</div>'+mapHTML(p,row);$('largeInitialMap').hidden=mode!=='result'||!$('compareMaps').matches('[aria-pressed=true]');if(!$('largeInitialMap').hidden){const base=referenceRow||initialRows.find(r=>String(r.id)===String(initial));$('largeInitialMap').innerHTML='<div class="largeMapCaption">기준 · '+(referenceRow?referenceGeneration:0)+'세대 행 '+(base?.id??'없음')+' · 비용 '+(base?.cost??'—')+'</div>'+mapHTML(p,base);}}$('initialCard').hidden=!$('compareMaps').matches('[aria-pressed=true]')||mode!=='result';$('mapTitle').textContent=mode==='design'?'공통 배치 미리보기':'선택한 진화 배치';$('mapBadge').textContent=mode==='design'?'기하 초안 · 성능 미계산':selected===null?'해 미선택':'행 '+selected+' · 비용 '+row?.cost+' · '+row?.sensor_counts.join(' / ')+'대'+(row?.qualified===false?' · 목표 미달':row?.qualified===null?' · 목표 미설정':'');$('geometrySummary').textContent=p?`${p.sites.length}개 후보 · ${((p.map_metres||20000)/1000)} × ${((p.map_metres||20000)/1000)} km · 평가 ${Number.isFinite(p.geometry?.area_km2)?p.geometry.area_km2.toFixed(2):'면적 미제공'} km²`:'';$('identity').textContent=mode==='design'?M.label(draft.sensor)+' · 공통 배치 초안':M.label(draft.sensor)+' · 실행 '+run.run_id+(selected===null?' · 해 미선택':' · 행 '+selected);$('largeIdentity').textContent=$('identity').textContent;for(const parent of [$('mainMap'),$('largeMap')]){parent.querySelectorAll('svg>g').forEach(()=>{});const candidates=parent.querySelectorAll('[data-candidate], [data-site]');candidates.forEach(e=>{e.style.cursor='pointer';});parent.querySelectorAll('title').forEach(title=>{const match=title.textContent.match(/후보지\s*(\d+)/);if(match){const el=title.parentElement;el.dataset.site=match[1];el.setAttribute('tabindex','0');el.setAttribute('role','button');el.setAttribute('aria-label','후보지 '+match[1]+' 속성');el.onclick=()=>{site=+match[1]-1;renderInspector();showSelectionProperties();};el.onkeydown=e=>{if(e.key==='Enter'){site=+match[1]-1;renderInspector();}};}});}$('differenceSummary').textContent='';if(!$('initialCard').hidden){const base=referenceRow||initialRows.find(r=>String(r.id)===String(initial));mapDifference(row,base,p);if($('mapDialog').open){mapDifference(row,base,p,$('largeMap'));$('largeIdentity').textContent+=' · 기준 '+(referenceRow?referenceGeneration:0)+'세대 행 '+base?.id+' · '+$('differenceSummary').textContent;}}renderMapReadings();renderConditionComparison();applyZoom();}
function applyZoom(){for(const el of document.querySelectorAll('.svgMap > svg,#largeMap > svg,#largeInitialMap > svg')){el.dataset.baseViewBox??=el.getAttribute('viewBox');const [bx,by,bw,bh]=el.dataset.baseViewBox.split(/[ ,]+/).map(Number),w=bw/zoom,h=bh/zoom,dx=Math.max(0,(bw-w)/2),dy=Math.max(0,(bh-h)/2);panX=Math.max(-dx,Math.min(dx,panX));panY=Math.max(-dy,Math.min(dy,panY));el.setAttribute('viewBox',`${bx+(bw-w)/2+panX} ${by+(bh-h)/2+panY} ${w} ${h}`);el.style.width='100%';el.style.height='100%';} $('zoomLabel').textContent=zoom===1?'전체':Math.round(zoom*100)+'%';if(typeof syncSensorSymbols==='function')syncSensorSymbols();}
function renderInspector(){const parent=$('inspectorBody');parent.replaceChildren();const p=mode==='design'?preview?.problem:run?.problem,r=mode==='result'?currentRow():null;const h=document.createElement('h3');h.className='selectionTitle';let items=[];if(site!==null&&p?.sites[site]){h.textContent='후보지 '+(site+1);$('selectionKind').textContent='후보 위치';items=[['동–서 좌표',p.sites[site][0]+' m'],['남–북 좌표',p.sites[site][1]+' m'],['Radar 반경',p.radii[0]+' m'],[draft.sensor===EO?'EO/IR 반경':'RF 반경',p.radii[1]+' m']];noteText(parent,'범위는 현재 지도 조건입니다. 센서 속성 편집은 다음 계산의 센서망 전체에 적용됩니다.');}else if(r){h.textContent='배치 '+r.id;$('selectionKind').textContent='저장된 원시해';items=[['Radar',r.sensor_counts[0]+'대'],[draft.sensor===EO?'EO/IR':'RF Scanner',r.sensor_counts[1]+'대'],['합성비용',r.cost+'점'],[run.qualityLabels[0],formatQuality(M.quality(r)[0])],[run.qualityLabels[1],formatQuality(M.quality(r)[1])],['목표',r.qualified===null?'미설정':r.qualified?'통과':'미달'],['세대',String(run.generation)]];}else{h.textContent='선택 대기';$('selectionKind').textContent='미선택';noteText(parent,'지도에서 후보지를 선택하거나, 저장 실행의 해 탐색 표에서 배치를 선택하세요.');}parent.prepend(h);const dl=document.createElement('dl');dl.className='propertiesList';for(const [key,val] of items){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=val;dl.append(dt,dd);}parent.append(dl);if(r){const detail=analysisSection(parent,'계산값과 설치 조건');renderRowFacts(detail,run,r);}if(run){const d=analysisSection(parent,'저장 실행의 고정 조건');renderFixedConditions(d,run);const b=document.createElement('button');b.textContent='이 조건으로 새 계산 준비';b.onclick=()=>$('copyRun').click();d.append(b);}}
function visibleRows(){if(!run)return [];let rows=run.rows;if(filter==='targets')rows=rows.filter(r=>r.qualified===true);const groups=cluster==='all'?null:M.cluster(typeof resultRows==='function'?resultRows():run.rows);if(cluster!=='all')rows=rows.filter(r=>groups[+cluster]?.some(o=>o.id===r.id));rows=[...rows].sort((a,b)=>sort==='cost'?a.cost-b.cost||a.id-b.id:M.quality(b)[sort==='radar'?0:1]-M.quality(a)[sort==='radar'?0:1]||a.cost-b.cost);if(filter==='all'){const seen=new Set();rows=rows.filter(r=>{const key=JSON.stringify(r.F);if(seen.has(key))return false;seen.add(key);return true;});}return rows;}
function choose(id){selected=id;site=null;modeTo('result');document.querySelectorAll('#dockBody tr').forEach(tr=>tr.classList.toggle('selected',tr.dataset.row===String(id)));document.querySelectorAll('.plot [data-row]').forEach(el=>{el.setAttribute('r',+el.dataset.row===id?7:4);el.setAttribute('fill',+el.dataset.row===id?'#a5671d':'#23859a');});expandControlsRefresh();}
function objectivePlot(rows){
 const max=Math.max(1,...rows.map(r=>r.cost)),angle=plotAngle*Math.PI/180;
 const project=(a,b,c)=>plotMode==='tradeoff'?[185+112*((a-.5)*Math.cos(angle)-(b-.5)*Math.sin(angle)),145+46*((a-.5)*Math.sin(angle)+(b-.5)*Math.cos(angle))-95*c/max]:[35+c/max*295,168-(plotMode==='radar'?a:b)*135];
 let content='';if(plotMode==='tradeoff'){for(let x=0;x<2;x++)for(let y=0;y<2;y++)for(let z=0;z<2;z++){const a=project(x,y,z*max);for(const b of [[1-x,y,z],[x,1-y,z],[x,y,1-z]])content+=`<path d="M${a}L${project(b[0],b[1],b[2]*max)}" fill="none" stroke="#d7e1e7"/>`;}content+=`<text x="8" y="14" font-size="11">X ${run.qualityLabels[0]} · Y ${run.qualityLabels[1]}</text><text x="8" y="29" font-size="11">Z 비용 0–${max} · 품질 축 ${draft.sensor===RF?'0–100점':'0–1'}</text><text x="48" y="200" font-size="11">높이 = 비용 · 주황 = 선택한 배치</text>`;}else content=`<path d="M35 28V168H340" fill="none" stroke="#93a9b6"/><text x="8" y="15" font-size="11">${run.qualityLabels[plotMode==='radar'?0:1]} (${draft.sensor===RF?'0–100점':'0–1'})</text><text x="8" y="35" font-size="10">${draft.sensor===RF?100:1}</text><text x="8" y="170" font-size="10">0</text><text x="200" y="199" font-size="11">비용 0–${max}</text>`;
 for(const row of [...rows.filter(r=>r.id!==selected),...rows.filter(r=>r.id===selected)]){const q=M.quality(row),[x,y]=project(q[0],q[1],row.cost);content+=`<circle role="button" tabindex="0" aria-label="그래프 배치 ${row.id} 선택" data-row="${row.id}" cx="${x}" cy="${y}" r="${row.id===selected?7:4}" fill="${row.id===selected?'#a5671d':'#23859a'}" stroke="white" stroke-width=".7"><title>행 ${row.id} · ${run.qualityLabels[0]} ${formatQuality(q[0])} · ${run.qualityLabels[1]} ${formatQuality(q[1])} · 비용 ${row.cost}</title></circle>`;}
 return `<svg viewBox="0 0 360 210" role="img" aria-label="배치의 두 품질과 비용 절충">${content}</svg>`;
}
function selectControl(parent,label,rows,value,change,id){const l=document.createElement('label');l.textContent=label+' ';const s=document.createElement('select');if(id)s.id=id;option(s,rows,value);s.onchange=()=>change(s.value);l.append(s);parent.append(l);return s;}
function renderDock(){document.querySelectorAll('[data-dock]').forEach(b=>b.setAttribute('aria-selected',b.dataset.dock===dock));const body=$('dockBody');body.replaceChildren();if(!run){body.innerHTML='<div class="empty"><b>배치 조건을 준비하거나 저장 실행을 선택하세요.</b><p>저장 결과를 열면 누적 해집합·세대별 지도·배치 비교가 같은 작업공간에 표시됩니다.</p></div>';$('resultCount').textContent='결과 없음';return;}const rows=visibleRows();if(selected===null||!rows.some(r=>r.id===selected))selected=representative(rows)?.id??null;syncSelectionBar();$('resultCount').textContent=`누적 ${run.rows.length} · 목표통과 ${draft.sensor===RF&&run.config.targets===null?'미설정':run.rows.filter(r=>r.qualified).length} · Hamming ${M.cluster(typeof resultRows==='function'?resultRows():run.rows).length}군`;
if(dock==='solutions'){const tools=document.createElement('div');tools.className='dockToolbar';selectControl(tools,'집합',[['all','전체 Pareto 근사해'],['structures','동일 목적값의 다른 배치 포함'],['targets','목표통과 배치']],filter,v=>{filter=v;selected=null;renderDock();renderMaps();renderInspector();},'frontFilter');selectControl(tools,'정렬',[['cost','비용 낮은 순'],['radar',run.qualityLabels[0]],['second',run.qualityLabels[1]]],sort,v=>{sort=v;renderDock();syncSelectionBar();},'rowSort');selectControl(tools,'Hamming',[['all','전체'],...M.cluster(typeof resultRows==='function'?resultRows():run.rows).map((g,i)=>[String(i),`${i+1}군 · ${g.length}개`])],cluster,v=>{cluster=v;selected=null;renderDock();renderMaps();renderInspector();},'structureFilter');selectControl(tools,'목적공간',[['tradeoff','두 품질·비용 (3D)'],['radar',run.qualityLabels[0]+' / 비용'],['second',run.qualityLabels[1]+' / 비용']],plotMode,v=>{plotMode=v;renderDock();},'plotMode');const rotate=document.createElement('button');rotate.textContent='시점 회전';rotate.disabled=plotMode!=='tradeoff';rotate.onclick=()=>{plotAngle=(plotAngle+45)%360;renderDock();};tools.append(rotate);body.append(tools);const grid=document.createElement('div');grid.className='solutionsGrid';const plot=document.createElement('div');plot.className='plot';const max=Math.max(1,...rows.map(r=>r.cost));plot.innerHTML=objectivePlot(rows);plot.querySelectorAll('[data-row]').forEach(e=>{e.onclick=()=>selectPlotPoint(e);e.onkeydown=evt=>{if(evt.key==='Enter')selectPlotPoint(e);};});const wrap=document.createElement('div');wrap.className='tableWrap';const table=document.createElement('table');const head=table.createTHead().insertRow();for(const name of ['배치',...run.qualityLabels,'비용','R / '+(draft.sensor===EO?'E':'RF'),'비교']){const th=document.createElement('th');th.scope='col';th.textContent=name;head.append(th);}const tbody=table.createTBody();for(const r of rows){const tr=tbody.insertRow();tr.dataset.row=r.id;tr.classList.toggle('selected',r.id===selected);const b=document.createElement('button');b.textContent='행 '+r.id;b.setAttribute('aria-label','배치 '+r.id+' 선택');b.onclick=()=>choose(r.id);tr.insertCell().append(b);for(const val of [...M.quality(r).map(formatQuality),r.cost,r.sensor_counts.join(' / ')])tr.insertCell().textContent=val;const chk=document.createElement('input');chk.type='checkbox';chk.checked=compared.has(r.id);chk.setAttribute('aria-label','배치 '+r.id+' 비교');chk.onchange=()=>{if(chk.checked)compared.add(r.id);else compared.delete(r.id);};tr.insertCell().append(chk);}wrap.append(table);grid.append(plot,wrap);body.append(grid);if(!rows.length)noteText(body,'이 필터에 해당하는 해가 없습니다. 전체 Pareto 근사해로 바꾸어 확인하세요.');}
else if(dock==='comparison'){const rows=visibleRows().filter(r=>compared.has(r.id));if(!rows.length)noteText(body,'해 탐색 표에서 비교할 배치를 체크하세요. 같은 실행·세대·표시 집합의 배치를 비교합니다.');else {const table=document.createElement('table');table.innerHTML='<thead><tr><th>배치</th><th>'+run.qualityLabels.join('</th><th>')+'</th><th>비용</th><th>장비 수</th></tr></thead>';const tbody=table.createTBody();for(const r of rows){const tr=tbody.insertRow();for(const v of [r.id,...M.quality(r).map(formatQuality),r.cost,r.sensor_counts.join('/')])tr.insertCell().textContent=v;tr.onclick=()=>choose(r.id);}body.append(table);noteText(body,'Hamming 구조 군집은 센서별 설치 비트의 차이로 분류합니다. 같은 군집이라고 같은 성능이나 최적성을 뜻하지 않습니다.');}}
else {const b=document.createElement('button');b.textContent='원시 결과 내보내기';b.onclick=safe(exportRaw);body.append(b);if(draft.sensor===RF){const q=document.createElement('button');q.textContent='저장된 해의 품질·탐색 근거';q.onclick=safe(async()=>{const cid=draft.sensor,id=run.run_id,epoch=requestEpoch;q.disabled=true;try{const result=await api(cid,'runs/'+id+'/quality');if(epoch!==requestEpoch||run?.run_id!==id||result.run_id!==id||result.config_sha256!==run.config_sha256||result.evaluator_sha256!==run.evaluator_sha256)throw Error('품질 근거 실행이 변경되었습니다.');qualityReport=result;renderDock();}finally{q.disabled=false;}});body.append(q);if(run.config.evaluator_version==='rf-common-information-v2'){const local=document.createElement('button');local.textContent='선택 해 삭제·교환 검산';local.disabled=selected===null||run.generation!==run.latest;local.title='최종 세대의 누적 해집합에서 선택한 행을 검산합니다.';local.onclick=safe(async()=>{const id=run.run_id,row=selected,epoch=requestEpoch;local.disabled=true;notice('선택 해의 삭제·교환 배치를 검산 중…','busy');try{const result=await api(RF,'runs/'+id+'/quality',{experiment_contract_id:RF,raw_id:row});if(epoch!==requestEpoch||run?.run_id!==id||result.run_id!==id||result.config_sha256!==run.config_sha256||result.evaluator_sha256!==run.evaluator_sha256)throw Error('검산 중 실행 선택 또는 근거 계약이 변경되었습니다.');qualityReport=result;renderDock();notice('선택 해 국소 검산을 저장했습니다. 원시 optimizer 해는 유지됩니다.');}finally{local.disabled=false;}});body.append(local);}}noteText(body,'원시 optimizer 해와 사후 검산은 분리합니다. 누적 경험적 비지배 집합·Hamming·세대 안정은 전역 최적성의 증명이 아닙니다.');if(qualityReport){renderQuality(body,qualityReport);}else if(run.history?.length){evidenceTable(body,['세대','NFE','누적 해'],run.history.map(r=>[r.generation,r.nfe??r.evaluations,r.archive_ids?.length??'상세 근거 확인']));noteText(body,'NFE는 평가 횟수입니다. 누적 해 수는 관측된 실현가능 배치의 절충집합 크기이며, 증가 자체가 품질 향상을 보장하지 않습니다.');}}}
async function histories(){const cid=draft.sensor,epoch=requestEpoch;const result=await api(cid,cid===EO?'jobs':'runs');if(epoch!==requestEpoch||cid!==draft.sensor)return;const rows=Array.isArray(result)?result:result.runs;option($('runHistory'),[['','저장 실행 선택'],...rows.slice().reverse().map(r=>[r.run_id||r.id,`${states[r.state]||r.state} · ${r.display_name||readableRunName(r)}${r.integrity_status==='NOT_VERIFIED_UNTIL_OPEN'?' · 열 때 검증':''}`])],run?.run_id||'');}
async function loadRun(id,g=null){
 if(!id)return;
 loadingRun?.controller?.abort();++requestEpoch;pendingRun=null;
 if(bootRunRequest?.controller.signal.aborted)cancelBootRun();
 const owner={controller:new AbortController(),cid:draft.sensor};loadingRun=owner;
 const boot=bootRunRequest;
 if(boot?.ready&&!boot.controller.signal.aborted&&boot.id===id&&boot.cid===owner.cid&&g===null){boot.owner=owner;owner.controller.signal.addEventListener('abort',()=>boot.controller.abort(),{once:true});}
 try{await fetchRun(id,g);}finally{if(loadingRun===owner)loadingRun=false;}
}
async function fetchRun(id,g=null){const cid=draft.sensor,epoch=++requestEpoch,signal=loadingRun?.controller?.signal;if(!id)return;if(run?.run_id!==id)notice('실행 상태와 결과를 불러오는 중…','busy');const key=cid+':'+id+':'+g;const query=new URLSearchParams({view:'summary'});if(g!==null)query.set('generation',g);const p=frameCache.get(key)||await readRunPacket(cid,id,g,signal,query);if(epoch!==requestEpoch||cid!==draft.sensor)return;const next=M.normalize(p,cid,id),changed=run?.run_id!==id,wasTerminal=run&&terminal.has(run.state),keepEditing=workbench?.task==='settings'&&!changed;if(terminal.has(next.state)){frameCache.set(key,p);if(frameCache.size>24)frameCache.delete(frameCache.keys().next().value);}if(!changed&&!terminal.has(next.state)&&run.state===next.state&&run.generation===next.generation){run=next;$('runtimeStatus').textContent=(states[run.state]||run.state)+` · ${run.nfe} NFE · ${(run.seconds||0).toFixed(1)}초`;clearTimeout(poller);poller=setTimeout(safe(()=>loadRun(id)),1000);return;}let firstRows=changed?[]:initialRows;if(cid===RF||next.research_configuration)firstRows=next.initialRows;else if(!firstRows.length&&next.latest>=0){const first=await api(cid,'jobs/'+id+'?generation=0',undefined,{}, {signal});if(epoch!==requestEpoch||cid!==draft.sensor)return;firstRows=M.normalize(first,cid,id).rows;}if(changed){baselinePreview=null;if(analysisDialog.open)analysisDialog.close();workbench?.setTask('map');$('initialCard').querySelector('.mapCardTitle').firstChild.textContent='초기 배치 ';document.body.classList.add('settingsHidden');$('toggleSettings').textContent='설정 열기';$('toggleSettings').setAttribute('aria-expanded','false');selected=null;initial=null;referenceRow=null;zoom=1;panX=panY=0;dock='solutions';$('showLabels').checked=false;compared.clear();qualityReport=null;filter='all';sort='cost';cluster='all';}run=next;initialRows=firstRows;if(initial===null)initial=representative(initialRows)?.id??null;if(selected===null||!visibleRows().some(r=>r.id===selected))selected=representative(visibleRows())?.id??null;mode=keepEditing?'design':'result';$('resultMode').disabled=false;$('copyRun').disabled=false;$('exportRaw').disabled=!['completed','cancelled','time_limit'].includes(run.state);$('advanced').disabled=false;$('generation').disabled=run.latest<1;$('generation').max=Math.max(0,run.latest);$('generation').value=run.generation;$('play').disabled=run.latest<1;$('cancel').disabled=terminal.has(run.state);$('generationText').textContent=run.latest<0?'초기 세대 준비 · 0 NFE':`${run.generation} / ${run.latest}세대 · ${cid===RF?(run.history.find(c=>c.generation===run.generation)?.nfe??run.nfe):run.nfe} NFE`;$('runtimeStatus').textContent=(states[run.state]||run.state)+` · ${run.nfe} NFE · ${(run.seconds||0).toFixed(1)}초`;option($('initialSolution'),[['','초기 해 선택'],...initialRows.map(r=>[String(r.id),`행 ${r.id} · 비용 ${r.cost}`])],referenceRow?'':initial??'');modeTo(keepEditing?'design':'result');renderDock();if(!keepEditing)notice(terminal.has(run.state)?(run.state==='completed'?'계산 완료 · 저장된 결과입니다. 조건을 복사해 다음 실험을 구성할 수 있습니다.':(states[run.state]||run.state)+' · 종료 전까지 저장된 부분 결과입니다.'):(states[run.state]||run.state)+' · '+run.nfe+' NFE · '+(run.seconds||0).toFixed(1)+'초',terminal.has(run.state)?'':'busy');clearTimeout(poller);if(!terminal.has(run.state)){ $('calculate').disabled=true;poller=setTimeout(safe(()=>loadRun(id)),1000);if(changed)safe(histories)();}else{$('calculate').disabled=previewPending||!preview?.execution_supported||cid===EO&&draft.optimizer.algorithm!=='NSGA-III';if(changed||!wasTerminal)safe(histories)();}}
function clearRun(){cancelBootRun();loadingRun?.controller?.abort();loadingRun=false;if(analysisDialog.open)analysisDialog.close();++requestEpoch;$('initialCard').querySelector('.mapCardTitle').firstChild.textContent='초기 배치 ';pendingRun=null;clearTimeout(slideTimer);referenceRow=null;frameCache.clear();clearTimeout(poller);clearInterval(player);player=null;$('play').textContent='▶ 세대 재생';run=null;selected=null;initial=null;initialRows=[];compared.clear();qualityReport=null;filter='all';sort='cost';cluster='all';mode='design';for(const id of ['resultMode','copyRun','exportRaw','advanced','generation','play','cancel'])$(id).disabled=true;$('generationText').textContent='실행 미선택';$('runtimeStatus').textContent='준비';renderDock();}
async function switchSensor(cid){if(creating||cid===draft.sensor)return;baselinePreview=null;clearTimeout(previewTimer);clearRun();draft.sensor=cid;preview=null;site=null;renderHeader();renderSettings();modeTo('design');safe(histories)();await apply();}
async function exportRaw(){if(!run)throw Error('저장 실행을 선택하세요');const cid=draft.sensor,id=run.run_id,path=cid===EO?'jobs/'+id+'/download':'runs/'+id+'/export';const res=await fetch('/contracts/'+cid+'/api/'+path,{headers:{'X-Experiment-Contract':cid}});if(!res.ok||res.headers.get('X-Experiment-Contract')!==cid)throw Error('원시 내보내기 검증 실패');const type=res.headers.get('Content-Type')?.split(';')[0],extension=type==='application/json'?'.json':type==='application/zip'?'.zip':null;if(!extension)throw Error('지원하지 않는 원시 내보내기 형식');const blob=await res.blob(),a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=cid+'_'+id+extension;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function evidenceTable(parent,headings,rows){const wrap=document.createElement('div');wrap.className='evidenceTable';const table=document.createElement('table'),head=table.createTHead().insertRow(),body=table.createTBody();for(const text of headings){const th=document.createElement('th');th.scope='col';th.textContent=text;head.append(th);}for(const values of rows){const tr=body.insertRow();for(const value of values)tr.insertCell().textContent=value===null?'미설정':value;}wrap.append(table);parent.append(wrap);}
function renderQuality(parent,q){const h=document.createElement('h3');h.textContent='저장된 전체 실행의 탐색 기록';parent.append(h);evidenceTable(parent,['세대','NFE','실현가능','고유 배치','중복 평가','누적 해','고유 목적값','목표통과'],q.search_quality.map(r=>[r.generation,r.nfe,r.feasible,r.unique_decisions,r.repeated_evaluations,r.archive_size,r.unique_objective_vectors,r.target_count]));noteText(parent,'고유 배치는 탐색한 서로 다른 설치 구조입니다. 중복 평가는 같은 구조를 다시 평가한 횟수입니다. 누적 해는 관측된 실현가능 배치의 경험적 비지배 집합이며, 고유 목적값 수와 다를 수 있습니다.');const hamming=q.hamming;noteText(parent,`Hamming 구조 차이: ${hamming.pair_count}쌍 · 평균 ${hamming.mean===null?'해당 없음':hamming.mean.toFixed(2)} · 최소 ${hamming.minimum??'—'} · 최대 ${hamming.maximum??'—'}. 설치 비트 차이이며 목적함수나 최적성 증명이 아닙니다.`);const sub=document.createElement('h3');sub.textContent='저장된 사후 국소 검산';parent.append(sub);if(q.unchecked_archive_rows!==undefined)noteText(parent,'현재 누적 해 중 '+q.unchecked_archive_rows+'개는 국소 미검사입니다. 최종 세대에서 해를 선택하고 삭제·교환 검산을 실행하세요.');evidenceTable(parent,['원시 행','1개 제거 검사','제거 개선','1개 이동 검사','이동 개선'],q.rows.map(r=>[r.raw_id,r.one_delete_tested,r.one_delete_witness_count,r.one_swap_tested,r.one_swap_witness_count]));noteText(parent,'개선은 다른 목적값을 악화시키지 않고 하나 이상 개선하는 실현가능 배치를 찾은 횟수입니다. 0건은 이 국소 검사에서 미발견이라는 뜻이며 전역 최적성을 보장하지 않습니다. 이 검산해는 원시 optimizer 해집합에 넣지 않습니다.');noteText(parent,'원시 배열은 원시 결과 내보내기에서 보존된 파일로 받을 수 있습니다. 배치 상세·검증에서 선택한 배치의 검사 범위와 개선 배치를 확인하세요.');}
function saveScenario(){draft.name=$('projectName').value.trim()||'이름 없는 시나리오';const packet=M.validate(draft),key='solsol.workspace.scenarios.v2';const rows=JSON.parse(localStorage.getItem(key)||'[]');rows.unshift({id:crypto.randomUUID(),at:new Date().toISOString(),draft:packet,selectedRun:run?{cid:draft.sensor,id:run.run_id}:null});localStorage.setItem(key,JSON.stringify(rows.slice(0,30)));$('saveState').textContent='시나리오 저장됨';notice('공통 배치 조건과 센서별 상세 설정을 저장했습니다.');}
function openScenarios(){const rows=JSON.parse(localStorage.getItem('solsol.workspace.scenarios.v2')||'[]');$('scenarioList').replaceChildren();if(!rows.length)noteText($('scenarioList'),'저장된 시나리오가 없습니다. 먼저 배치 조건을 저장하세요.');for(const item of rows){const el=document.createElement('div');el.className='scenarioRow';const title=document.createElement('div');const b=document.createElement('b'),s=document.createElement('span');b.textContent=item.draft.name;s.textContent=' · '+M.label(item.draft.sensor)+' · '+item.at.slice(0,16).replace('T',' ');title.append(b,s);const button=document.createElement('button');button.textContent='열기';button.onclick=safe(async()=>{const restored=M.validate(item.draft);clearRun();baselinePreview=null;draft=restored;prepareResearch();preview=null;$('projectName').value=draft.name;renderHeader();renderSettings();$('scenarioDialog').close();safe(histories)();await apply();if(item.selectedRun?.cid===draft.sensor)await loadRun(item.selectedRun.id);$('saveState').textContent='저장 시나리오 복원됨';if(draft.migrationNotice)notice(draft.migrationNotice,'warning');});el.append(title,button);$('scenarioList').append(el);}$('scenarioDialog').showModal();}
function expand(){const root=$('largeTools');root.replaceChildren();if(!$('largeInitialMap')){const comparison=document.createElement('div');comparison.id='largeComparison';const first=document.createElement('div');first.id='largeInitialMap';first.setAttribute('aria-label','비교 기준 배치 지도');$('largeMap').before(comparison);comparison.append(first,$('largeMap'));}for(const [id,name] of [['mapLayer','레이어'],['showLabels','후보 번호'],['showArea','평가영역'],['showDemand','평가점']]){const base=$(id);if(!base)continue;const c=base.cloneNode(true);c.id='large_'+id;c.value=base.value;if(base.type==='checkbox')c.checked=base.checked;const label=document.createElement('label');label.textContent=name;label.append(c);c.onchange=()=>{base.value=c.value;if(base.type==='checkbox')base.checked=c.checked;base.dispatchEvent(new Event('change'));expandControlsRefresh();};root.append(label);}if(mode!=='result'||!run){const fit=document.createElement('button');fit.textContent='지도 전체 맞춤';fit.onclick=()=>{zoom=1;panX=panY=0;applyZoom();};root.append(fit);$('mapDialog').showModal();renderMaps();return;}selectControl(root,'집합',resultFilterOptions(),filter,v=>{filter=v;selected=null;renderDock();renderMaps();renderInspector();expandControlsRefresh();},'large_frontFilter');selectControl(root,'정렬',resultSortOptions(),sort,v=>{sort=v;renderDock();expandControlsRefresh();},'large_rowSort');selectControl(root,'Hamming',[['all','전체'],...M.cluster(typeof resultRows==='function'?resultRows():run.rows).map((g,i)=>[String(i),`${i+1}군 · ${g.length}개`])],cluster,v=>{cluster=v;selected=null;renderDock();renderMaps();renderInspector();expandControlsRefresh();},'large_structureFilter');const fit=document.createElement('button');fit.textContent='지도 전체 맞춤';fit.onclick=()=>{zoom=1;panX=panY=0;applyZoom();};root.append(fit);const select=selectControl(root,'배치',[['','해 선택'],...visibleRows().map(r=>[String(r.id),`행 ${r.id} · 비용 ${r.cost}`])],selected??'',v=>choose(v===''?null:+v),'largeSolution');$('mapDialog').showModal();renderMaps();}
function expandControlsRefresh(){if(!$('mapDialog').open)return;for(const [id,values,value] of [['large_frontFilter',run?resultFilterOptions():[],filter],['large_rowSort',run?resultSortOptions():[],sort]])if($(id))option($(id),values,value);if($('large_structureFilter'))$('large_structureFilter').value=cluster;const s=$('largeSolution');if(s)option(s,[['','해 선택'],...visibleRows().map(r=>[String(r.id),`행 ${r.id} · 비용 ${r.cost}`])],selected??'');}
document.querySelectorAll('[data-sensor]').forEach(b=>b.onclick=safe(()=>switchSensor(b.dataset.sensor)));document.querySelectorAll('[data-settings]').forEach(b=>b.onclick=()=>{setting=b.dataset.settings;renderSettings();});document.querySelectorAll('[data-dock]').forEach(b=>b.onclick=()=>{dock=b.dataset.dock;setAnalysis(true);renderDock();});document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
$('applyDraft').onclick=safe(apply);$('projectName').onchange=updateDraft;$('saveScenario').onclick=safe(saveScenario);$('openScenario').onclick=safe(openScenarios);$('help').onclick=()=>$('helpDialog').showModal();$('designMode').onclick=()=>modeTo('design');$('resultMode').onclick=()=>modeTo('result');$('sensorProperties').onclick=()=>{selectWorkbenchTask('settings');document.body.classList.remove('settingsHidden');$('toggleSettings').textContent='설정 접기';$('toggleSettings').setAttribute('aria-expanded','true');setting='sensors';renderSettings();$('settingsBody').scrollTop=0;$('settingsBody').querySelector('input,select')?.focus();notice('다음 계산의 센서 설정을 편집합니다. 변경은 자동 미리보기되며 계산 실행을 눌러 새 계산을 시작하세요. 저장 결과는 고정되어 있습니다.');};$('runHistory').onchange=safe(async()=>{clearRun();if($('runHistory').value)await loadRun($('runHistory').value);else modeTo('design');});
for(const id of ['mapLayer','showLabels','showArea','showDemand'])$(id).onchange=renderMaps;$('compareMaps').onclick=()=>{$('compareMaps').setAttribute('aria-pressed',!$('compareMaps').matches('[aria-pressed=true]'));zoom=1;panX=panY=0;renderMaps();};$('zoomIn').onclick=()=>{zoom=Math.min(3,zoom+.25);applyZoom();};$('zoomOut').onclick=()=>{zoom=Math.max(.75,zoom-.25);applyZoom();};$('fitMap').onclick=()=>{zoom=1;panX=panY=0;applyZoom();};$('initialSolution').onchange=()=>{referenceRow=null;$('initialCard').querySelector('.mapCardTitle').firstChild.textContent='초기 배치 ';initial=$('initialSolution').value;renderMaps();};$('expandMap').onclick=expand;$('exportRaw').onclick=safe(exportRaw);$('generation').oninput=()=>{const id=run?.run_id,g=+$('generation').value;$('generationText').textContent=`${g}세대 불러오는 중…`;clearTimeout(slideTimer);slideTimer=setTimeout(safe(()=>loadRun(id,g)),160);};$('play').onclick=()=>{if(player){clearInterval(player);player=null;$('play').textContent='▶ 세대 재생';return;}$('play').textContent='Ⅱ 재생 멈춤';player=setInterval(safe(()=>{if(!loadingRun)return loadRun(run.run_id,(run.generation+1)%(run.latest+1));}),1200);};
$('copyRun').onclick=safeCopy(async()=>{if(draft.sensor===EO){for(const k of M.commonKeys)draft.common[k]=run.config[k];draft.sensors[EO]=structuredClone(run.config);Object.assign(draft.optimizer,{generations:run.config.generations,population:({7:36,12:92,19:212})[run.config.h],seed:run.config.seed,h:run.config.h,initializer:run.config.initializer,algorithm:'NSGA-III'});}else {if(!['rf-common-information-v2','rf-common-information-v3'].includes(run.config.evaluator_version))throw Error('소형 RF v1 실행은 기존 조건 그대로 조회합니다. 공통 연구 기본값에서 새 조건을 구성하세요.');draft.migrationNotice='이전 실행 조건을 새 RF 계약으로 준비합니다. 장비별 수량과 계산 예산을 확인하세요.'+([36,92,212].includes(run.optimizer.population)?'':' 이전 개체 수 '+run.optimizer.population+'개를 공통92개로 준비했습니다.');draft.sensors[RF]={...structuredClone(defaults.r),...structuredClone(run.config),evaluator_version:'rf-common-information-v3',radar_limit:run.config.radar_limit??draft.sensors[EO].radar_stock,rf_limit:run.config.rf_limit??draft.sensors[EO].eo_stock,resource_mode:run.config.resource_mode??'partial'};draft.common=structuredClone(run.config.common);Object.assign(draft.optimizer,{generations:run.optimizer.generations??run.optimizer.checkpoints-1,population:[36,92,212].includes(run.optimizer.population)?run.optimizer.population:92,seed:run.optimizer.seed,algorithm:'NSGA-III'});}workbench?.setTask('settings');renderSettings();updateDraft();modeTo('design');await apply();});
function lockCreation(value){creating=value;document.querySelectorAll('[data-sensor],#openScenario,#runHistory,#copyRun,#applyDraft,#settingsBody input,#settingsBody select').forEach(el=>el.disabled=value);if(!value)$('copyRun').disabled=!run;}
$('calculate').onclick=safe(async()=>{if(creating)return;if(previewPending||!preview||draft.optimizer.algorithm!=='NSGA-III')throw Error('조건 반영과 실행 방법을 확인하세요');const cid=draft.sensor,cfg=cid===EO?M.eoirConfig(draft):{...M.rfPayload(draft),preview_sha256:preview.preview_sha256,optimizer:{algorithm:draft.optimizer.algorithm,seed:draft.optimizer.seed,population:draft.optimizer.population,generations:draft.optimizer.generations}};$('calculate').disabled=true;lockCreation(true);notice('로딩중… 실행 준비','busy');try{const job=await api(cid,cid===EO?'jobs':'common-runs',cfg);clearRun();safe(histories)();await loadRun(job.id||job.run_id);}finally{lockCreation(false);}});$('cancel').onclick=safe(async()=>{if(!run)return;await api(draft.sensor,(draft.sensor===EO?'jobs/':'runs/')+run.run_id+'/cancel',draft.sensor===EO?{}:{experiment_contract_id:RF});notice('중지 요청 · 현재 세대 저장을 기다립니다.');});$('advanced').textContent='배치 상세·검증';$('advanced').onclick=openPlacementAnalysis;
const solutionBar=document.createElement('div');solutionBar.id='solutionBar';solutionBar.hidden=true;solutionBar.innerHTML='<button id="previousSolution" aria-label="이전 배치">◀</button><label>배치 <select id="solutionPicker" aria-label="지도 배치 선택"></select></label><button id="nextSolution" aria-label="다음 배치">▶</button><span id="selectionPosition"></span><button id="pinSolution">이 해와 비교</button><span class="selectionHint">선택 지도는 추천·최적성 판정이 아닙니다</span><span id="differenceSummary"></span>';$('mapStage').before(solutionBar);$('solutionPicker').onchange=()=>choose(+$('solutionPicker').value);for(const [id,step] of [['previousSolution',-1],['nextSolution',1]])$(id).onclick=()=>{const rows=visibleRows(),i=rows.findIndex(r=>r.id===selected);if(rows.length)choose(rows[(i+step+rows.length)%rows.length].id);};$('pinSolution').onclick=()=>{workbench?.setTask('compare');referenceRow=currentRow();referenceGeneration=run.generation;$('initialSolution').value='';$('initialCard').querySelector('.mapCardTitle').firstChild.textContent='비교 기준 · '+referenceGeneration+'세대 행 '+selected+' ';$('compareMaps').setAttribute('aria-pressed','true');zoom=1;panX=panY=0;renderMaps();notice('왼쪽에 행 '+selected+' 고정. 오른쪽 배치를 바꾸어 위치·성능·비용을 비교하세요. 초기 해 선택으로 초기 배치 비교에 돌아갈 수 있습니다.');};
const toggleSettings=document.createElement('button');toggleSettings.id='toggleSettings';toggleSettings.textContent='설정 접기';toggleSettings.setAttribute('aria-expanded','true');document.querySelector('.viewTabs').prepend(toggleSettings);toggleSettings.onclick=()=>{const hidden=document.body.classList.toggle('settingsHidden');toggleSettings.textContent=hidden?'설정 열기':'설정 접기';toggleSettings.setAttribute('aria-expanded',!hidden);};
let mapDrag=null;
for(const host of [$('mainMap'),$('initialMap'),$('mapDialog')]){
 host.addEventListener('pointerdown',e=>{const svg=e.target.closest('svg');if(zoom<=1||!svg)return;mapDrag={host,svg,x:e.clientX,y:e.clientY,px:panX,py:panY,captured:false};});
 host.addEventListener('pointermove',e=>{if(!mapDrag||mapDrag.host!==host)return;if(!mapDrag.captured){if(Math.hypot(e.clientX-mapDrag.x,e.clientY-mapDrag.y)<3)return;host.setPointerCapture(e.pointerId);mapDrag.captured=true;}const box=mapDrag.svg.getBoundingClientRect(),scale=Math.max(930/box.width,945/box.height)/zoom;panX=mapDrag.px-(e.clientX-mapDrag.x)*scale;panY=mapDrag.py-(e.clientY-mapDrag.y)*scale;applyZoom();});
 host.addEventListener('pointerup',()=>{mapDrag=null;});host.addEventListener('pointercancel',()=>{mapDrag=null;});
}
$('mapStage').addEventListener('keydown',e=>{if(zoom<=1||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();panX+=e.key==='ArrowLeft'?-40:e.key==='ArrowRight'?40:0;panY+=e.key==='ArrowUp'?-40:e.key==='ArrowDown'?40:0;applyZoom();});
$('fitMap').title='전체 영역 맞춤 · 확대 후 드래그로 이동';
function setAnalysis(open){document.body.classList.toggle('analysisOpen',open);document.body.classList.toggle('analysisCollapsed',!open);$('toggleAnalysis').textContent=open?'분석 접기':'분석 펼치기';$('toggleAnalysis').setAttribute('aria-expanded',open);}
const toggleAnalysis=document.createElement('button');toggleAnalysis.id='toggleAnalysis';document.querySelector('.dockTabs').append(toggleAnalysis);setAnalysis(innerHeight>850);toggleAnalysis.onclick=()=>setAnalysis(!document.body.classList.contains('analysisOpen'));
$('showLabels').checked=false;
async function restoreRequestedRun(id,authority=null){
 if(authority&&(requestEpoch!==authority.requestEpoch||previewEpoch!==authority.previewEpoch)){cancelBootRun();return;}
 if(bootRunRequest){
  if(bootRunRequest.authority===authority&&bootRunRequest.id===id&&bootRunRequest.cid===draft.sensor)bootRunRequest.ready=true;
  else cancelBootRun();
 }
 const cid=draft.sensor,initialPreviewEpoch=previewEpoch;
 previewPending=true;
 $('calculate').disabled=true;
 // Open the verified saved result before preparing an unrelated new draft.
 // Existing apply wrappers may perform several validations with their own epochs.
 const loading=loadRun(id),restoringEpoch=requestEpoch;
 try{await loading;}catch(error){
  if(cid!==draft.sensor||requestEpoch!==restoringEpoch)return;
  throw error;
 }
 if(cid!==draft.sensor||requestEpoch!==restoringEpoch||previewEpoch!==initialPreviewEpoch||run?.run_id!==id)return;
 const checking=apply(),validationEpoch=previewEpoch;
 try{await checking;}catch(error){
  if(cid!==draft.sensor||requestEpoch!==restoringEpoch||previewEpoch!==validationEpoch||run?.run_id!==id)return;
  previewPending=true;previewFailure=error.message;
  $('calculate').disabled=true;
  $('saveState').textContent='새 실행 설정 미검증 · 저장 결과 열람';
  notice('저장 결과를 열었습니다. 새 실행 설정을 검증할 수 없어 계산은 비활성 상태입니다: '+error.message,'warning');
 }
}
window.addEventListener('DOMContentLoaded',()=>safe(async()=>{
 const params=new URLSearchParams(location.search),id=params.get('run'),requestedContract=params.get('contract');
 const authority={requestEpoch,previewEpoch},controller=new AbortController();
 try{
   const response=await fetch('/api/bootstrap',{signal:controller.signal});
   if(!response.ok)throw Error('계산기 연결 실패');
   const bootstrap=await response.json();token=bootstrap.token;
   registryData=await api(bootstrap.default_contract,'engine/registry');
   defaults={e:registryData.ui_models[bootstrap.default_contract].defaults,r:{}};
   draft=M.create(defaults.e,{},bootstrap.default_contract);
   if(registryData.bundles.some(b=>b.id===requestedContract))draft.sensor=requestedContract;
   prepareResearch();Object.assign(draft.optimizer,registered().default_optimizer);
   renderHeader();renderSettings();renderDock();modeTo('design');
  if(id)await restoreRequestedRun(id,authority);
  else{safe(histories)();await apply();}
 }catch(error){controller.abort();cancelBootRun();throw error;}
})());


/* Current-run analysis: immutable scope, no navigation to the legacy application. */
function analysisSection(parent,title){const d=document.createElement('details'),h=document.createElement('summary');h.textContent=title;d.append(h);parent.append(d);return d;}
function renderFixedConditions(parent,r){
 const c=r.config||{},p=c.parameters||c,g=c.common||c;
 const names={algorithm:'계산 알고리즘',population:'개체 수',checkpoints:'저장 개수 · 초기 세대 포함',radar_limit:'Radar 보유 수량',rf_limit:'RF 보유 수량',targets:'Radar / RF 품질 목표',map_km:'지도 한 변 (km)',shape:'평가영역 모양',area_factor:'평가영역 크기 계수',candidate_count:'후보지 수',site_seed:'후보지 seed',radar:'Radar 반경 (km)',eo:'EO/IR 반경 (km)',radar_stock:'Radar 재고',eo_stock:'EO/IR 재고',radar_radius_m:'Radar 반경 (m)',rf_radius_m:'RF 반경 (m)',radar_sigma_m:'Radar 거리 측정 표준편차 (m)',radar_sigma_deg:'Radar 각도 측정 표준편차 (도)',rf_sigma_ns:'RF 시간 측정 표준편차 (ns)',normalization_m:'오차 정규화 기준 (m)',hardware_limit:'장비 수 제한',radar_acquisition:'Radar 구매비',rf_acquisition:'RF 구매비',radar_annual:'Radar 연간비',rf_annual:'RF 연간비',site_cost:'설치 지점 비용',horizon_years:'운용 기간 (년)',generations:'계산 세대 수',seed:'최적화 seed',h:'참조방향 분할',initializer:'초기 배치 방법',objective_contract:'목적함수',resource_mode:'장비 사용 조건',identification_area_factor:'식별영역 크기 계수'};
 const words={circle:'원',square:'정사각형',hexagon:'육각형',overlap:'중첩 영역',random:'무작위',greedy:'탐욕적 초기화',milp:'정수계획 초기화',partial:'일부 사용 가능',all:'보유 장비 모두 사용',off:'수량 제한 해제',full_area_tradeoff_v6:'전체 영역 탐지·식별·비용',binary_coverage_v1:'목표 충족 우선',layered_mission_v7:'탐지·식별 영역 분리',max_margin_quality_v3:'거리 여유 품질',zoned_nominal_v4:'구역별 탐지·식별'};
 const merged={...g,...p,...(r.optimizer||{})};evidenceTable(parent,['조건','저장된 값'],Object.entries(names).filter(([k])=>merged[k]!==undefined).map(([k,n])=>[n,merged[k]===null?'미설정':words[merged[k]]||String(merged[k])]));
 if(p.rf_emitting!==undefined)noteText(parent,p.rf_emitting?'RF 방사 신호가 있는 조건입니다.':'RF 무방사 조건: RF로 관측할 수 없습니다. 위치추정 성능을 만들지 않습니다.');
 noteText(parent,'후보지 '+r.problem.sites.length+'개 · 평가점 '+(r.problem.demand?.length??'—')+'개. 이 조건은 저장 결과에 결속되어 있으며 왼쪽 초안 변경으로 바뀌지 않습니다.');
}
function renderRowFacts(parent,r,row){
 evidenceTable(parent,['계산 항목','저장값'],[...(row.F||[]).map((v,i)=>['목적값 '+(i+1)+(i===2?(r.experiment_contract_id===RF?' · 합성 생애비용 (점)':' · 정규화 비용 (비용 ÷ 800)'):' · '+r.qualityLabels[i]+'의 최소화 값'),Number(v).toPrecision(7)]),...(row.G||[]).map((v,i)=>['제약 '+(i+1)+' · 0 이하 허용',Number(v).toPrecision(7)])]);
 noteText(parent,'목적값은 최적화기에 전달된 수치입니다. 목표 통과 여부와 설치 제약 충족 여부는 별개입니다. 원시 배열은 내보내기로 확인할 수 있습니다.');
 const x=M.rowX(row);evidenceTable(parent,['센서','설치 후보지 번호'],[0,1].map(i=>[i===0?'Radar':r.experiment_contract_id===RF?'RF Scanner':'EO/IR',x.flatMap((v,j)=>v[i]?[j+1]:[]).join(', ')||'설치 없음']));
}
let analysisScope=null,analysisEpoch=0,analysisStop=false;
const analysisDialog=document.createElement('dialog');analysisDialog.id='placementAnalysis';
analysisDialog.innerHTML='<header><h2>배치 설명과 검증</h2><button id="analysisClose">닫기</button></header><p id="analysisIdentity"></p><p>설치 조건과 비용·측정 품질의 절충을 확인하고, 저장된 계산값을 검산합니다. 개선 배치가 발견되면 지도에서 비교할 수 있습니다.</p><div class="analysisActions"><button id="analysisSelected">선택 배치 검산</button><label>목록 검사 수 <select id="analysisCount"><option value="1">1개</option><option value="3">3개</option><option value="10">10개</option><option value="all">현재 목록 전체</option></select></label><button id="analysisBatch">목록 배치 검산</button><button id="analysisStop" disabled>검사 중지</button><button id="analysisHistory">이전 RF 반복실험 보기</button></div><p id="analysisProgress" role="status"></p><div id="analysisContent"></div>';
document.body.append(analysisDialog);
$('analysisClose').onclick=()=>analysisDialog.close();
analysisDialog.addEventListener('close',()=>{analysisStop=true;++analysisEpoch;if(workbench?.task==='verify')workbench.setTask('map');});
function openPlacementAnalysis(){
 if(analysisDialog.open&&workbench?.task==='verify')return;
 leavePresentation();
 if(!run||!currentRow()){notice('저장 결과에서 배치를 선택한 뒤 배치 검증을 열어주세요.');return;}
 clearInterval(player);player=null;$('play').textContent='▶ 세대 재생';
 analysisStop=false;++analysisEpoch;
 analysisScope={run, row:currentRow(), rows:visibleRows().slice(),cid:draft.sensor};
 $('analysisIdentity').textContent=M.label(analysisScope.cid)+' · 실행 '+run.run_id+' · '+run.generation+'세대 · 배치 '+selected;
 $('analysisProgress').textContent='검사 전입니다. 아래 설명은 현재 선택한 저장 결과입니다.';
 $('analysisSelected').disabled=$('analysisBatch').disabled=false;$('analysisStop').disabled=true;
 const p=$('analysisContent');p.replaceChildren();renderRowFacts(p,run,currentRow());renderFixedConditions(analysisSection(p,'이 실행의 조건'),run);
 noteText(p,'현재 목록 '+analysisScope.rows.length+'개를 비용 정렬·목표 필터·Hamming 필터가 적용된 순서로 검사합니다. 목록 검사는 선택한 수만큼 순차 실행합니다. 한 배치 검산이 끝나면 중지할 수 있습니다.');
 workbench?.setTask('verify');if(!analysisDialog.open)analysisDialog.show();
}
const checkNames={solution_observed_by_requested_generation:'선택 세대까지 실제 평가된 배치',binary_shape_and_candidate_subset:'설치 배열과 후보지 일치',installation_allowed:'설치 허용 조건',F_exact_replay:'목적값 재계산 일치',G_exact_replay:'제약값 재계산 일치',cost_matches_X:'설치와 비용 일치',sensor_counts_match_X:'설치와 장비 수 일치',independent_geometry_matches:'독립 기하 계산 일치',public_row_matches_raw:'화면과 원시 행 일치'};
function verdict(v){return v===true||v==='PASS'?'통과':v===false||v==='FAIL'?'불일치 / 미달':v===null||v===undefined?'미검사':String(v);}
async function auditPlacement(scope,row){
 if(scope.cid===EO){const q=await api(EO,'jobs/'+scope.run.run_id+'/quality?solution='+row.id+'&generation='+scope.run.generation);if(q.run_id!==scope.run.run_id||q.solution_id!==row.id||q.generation!==scope.run.generation||q.identity.problem_sha256!==scope.run.problem.problem_sha256||['id','F','G','mask'].some(k=>JSON.stringify(q.selected[k])!==JSON.stringify(row[k])))throw Error('검산 실행·배치·세대 불일치');return q;}
 if(!['rf-common-information-v2','rf-common-information-v3'].includes(scope.run.config?.evaluator_version)||scope.run.generation!==scope.run.latest)throw Error('RF 개별 재검산은 공통 조건 실행의 최종 세대에서 가능합니다. 해당 실행의 최종 세대를 선택하세요.');
 const q=await api(RF,'runs/'+scope.run.run_id+'/quality',{experiment_contract_id:RF,raw_id:row.id});
 if(q.run_id!==scope.run.run_id||q.config_sha256!==scope.run.config_sha256||q.evaluator_sha256!==scope.run.evaluator_sha256||!q.rows.some(v=>v.raw_id===row.id&&v.source_decision_sha256===row.decision_sha256))throw Error('RF 검산 근거 결속 불일치');return q;
}
function showAudit(parent,scope,row,q){
 const h=document.createElement('h3');h.textContent='배치 '+row.id+' 검산 결과';parent.append(h);
 if(scope.cid===EO){
 evidenceTable(parent,['검사','결과'],Object.entries(q.integrity.checks).map(([k,v])=>[checkNames[k]||k,verdict(v)]));
 noteText(parent,'설치 제약: '+verdict(q.integrity.physical_constraint_status)+' · 운용 목표: '+verdict(q.integrity.operational_target_status));
 const o=q.observed_set;noteText(parent,o.selected.selected_in_empirical_front?'선택 배치는 이 세대까지 관측된 실현가능 배치 중 비지배 집합에 포함됩니다.':o.selected.dominator_id!==null&&o.selected.dominator_id!==undefined?'선택 배치를 지배하는 관측 배치: '+o.selected.dominator_id:'선택 배치의 비지배 포함 여부를 확정하지 못했습니다.');noteText(parent,'이 세대까지 저장된 '+o.evaluations+'회 평가의 목적값·제약으로 분류한 누적 해: '+o.empirical_front_decisions+'개. 선택 배치의 수치는 위에서 재계산했지만 모든 평가행을 독립 재계산했다는 뜻은 아닙니다.');
 evidenceTable(parent,['국소 검사','검사 수','범위','개선 발견'],['one_delete','one_swap'].map(k=>{const a=q.local_search[k];return[k==='one_delete'?'센서 1개 제거':'설치 1개 변경 (종류 변경 포함)',a.checked,a.exhaustive?'해당 이웃 전체':'일부 이웃만 검사',a.witness?'발견':'미발견'];}));
 noteText(parent,'검사 수가 0이면 판단할 근거가 없습니다. 개선 미발견은 검사한 이웃 범위의 결과이며 전역 최적성이나 배치 효율 통과 판정이 아닙니다.');
 const z=q.reduced_reference;noteText(parent,'축소 참조: 후보 '+z.candidate_sites+'개에서 '+z.enumerated_states+'상태를 열거했습니다. 전체 후보지 문제의 참 Pareto 전선은 아닙니다.');
 const w=q.local_search.first_witness;if(w?.point)showWitness(parent,scope,row,w.point);
 }else{
 const a=q.rows.find(v=>v.raw_id===row.id);
 evidenceTable(parent,['국소 검사','검사 수','개선 발견 수'],[['센서 1개 제거',a.one_delete_tested,a.one_delete_witness_count],['같은 센서 종류의 설치 위치 변경',a.one_swap_tested,a.one_swap_witness_count]]);
 noteText(parent,'현재 실행·설정·평가기·원시 행과 결속된 사후 검산입니다. 개선 미발견과 검사 수 0은 효율 통과나 전역 최적성을 뜻하지 않습니다.');
 if(a.witnesses[0]){const w=a.witnesses[0];showWitness(parent,scope,row,{...w,mask:w.X.map(x=>x[0]+2*x[1]),cost:w.F[2],sensor_counts:[0,1].map(i=>w.X.reduce((n,x)=>n+x[i],0))});}
 }
}
function showWitness(parent,scope,row,w){
 const h=document.createElement('h4');h.textContent='더 나은 배치가 발견되었습니다 · 사후 검산 배치';parent.append(h);
 evidenceTable(parent,['목적값 (작을수록 좋음)','원래 배치','검산 배치'],row.F.map((f,i)=>['목적 '+(i+1),f,w.F[i]]));
 noteText(parent,'아래 배치는 검산 중 생성된 비교 근거입니다. 원시 최적화 해집합에 추가하거나 원래 계산해로 표시하지 않습니다.');
 const box=document.createElement('div');box.className='analysisWitness';box.innerHTML=mapHTML(scope.run.problem,w);parent.append(box);
}
async function executeAnalysis(batch){
 const scope=analysisScope,epoch=++analysisEpoch;analysisStop=false;
 const count=$('analysisCount').value,rows=batch?scope.rows.slice(0,count==='all'?undefined:Number(count)):[scope.row];
 $('analysisSelected').disabled=$('analysisBatch').disabled=true;$('analysisStop').disabled=false;
 const p=$('analysisContent');p.replaceChildren();let completed=0;
 try{for(const row of rows){if(analysisStop||epoch!==analysisEpoch)break;$('analysisProgress').textContent='검산 중… '+completed+' / '+rows.length+'개 완료 · 배치 '+row.id+(scope.cid===EO?' · 목적값 재생과 국소 이웃을 검사합니다.':' · 저장된 부모 목적값을 기준으로 국소 이웃을 검사합니다. 기존 검산 결과가 있으면 조회합니다.');
 const q=await auditPlacement(scope,row);if(epoch!==analysisEpoch)return;const d=batch?analysisSection(p,'배치 '+row.id+' · 검산 근거'):p;showAudit(d,scope,row,q);completed++;}
 if(epoch===analysisEpoch)$('analysisProgress').textContent=(analysisStop?'중지됨 · ':'검산 종료 · ')+completed+' / '+rows.length+'개 검사. 아래 검사 범위를 확인하세요.';
 }catch(e){if(epoch===analysisEpoch)$('analysisProgress').textContent='검산 실패 · '+e.message+' · 완료된 '+completed+'개 근거는 보존되어 있습니다.';}
 finally{if(epoch===analysisEpoch){$('analysisSelected').disabled=$('analysisBatch').disabled=false;$('analysisStop').disabled=true;}}
}
$('analysisSelected').onclick=()=>executeAnalysis(false);$('analysisBatch').onclick=()=>executeAnalysis(true);
$('analysisStop').onclick=()=>{analysisStop=true;$('analysisProgress').textContent='중지 요청 · 현재 배치 검산이 끝나면 다음 배치를 시작하지 않습니다.';};
$('analysisHistory').onclick=safe(async()=>{
 if(!$('analysisStop').disabled)return;
 const epoch=analysisEpoch,p=$('analysisContent');p.replaceChildren();noteText(p,'이전 RF 고정 조건 반복실험입니다. 현재 선택 배치나 편집 중인 조건의 검증 결과가 아닙니다.');
 const q=await api(RF,'research');if(epoch!==analysisEpoch)return;
 const study=q.studies?.slice().sort((a,b)=>b.started_at.localeCompare(a.started_at))[0]||q.study||q;noteText(p,'실행일: '+(study.started_at||'기록 없음'));if(study.verdict)noteText(p,'국소 검사 '+study.verdict.local_checked+'배치 중 '+study.verdict.local_failed+'배치 미통과. 빈 배치에서 검사 수가 0인 판정은 효율 통과 근거가 아닙니다.');noteText(p,'상태: '+(states[study.state]||study.state||'기록 없음')+' · 최적화 평가 '+(study.optimizer_nfe??0)+'회. 실행별 계산 종료와 연구 검증 통과는 별개입니다.');
 for(const e of study.errors||[])noteText(p,typeof e==='string'?e:'실험 과정에 오류가 기록되어 있습니다.');
 const rows=study.runs||[];evidenceTable(p,['조건','범위','계산 방법','seed','실행 상태','평가 수'],rows.map(r=>['조건 '+r.case,r.reduced?'축소 문제':'전체 문제',r.algorithm,r.seed,states[r.state]||r.state,r.nfe]));
 const links=analysisSection(p,'이전 실험의 저장 배치 열기');for(const item of rows){const b=document.createElement('button');b.textContent='조건 '+item.case+' · '+item.algorithm+' · seed '+item.seed+' · '+(item.reduced?'축소':'전체')+' 지도 열기';b.onclick=safe(async()=>{analysisDialog.close();await switchSensor(RF);await loadRun(item.run_id);});links.append(b);}
 noteText(p,'과거 시간 제한 종료와 개선 배치 발견은 실패 근거로 유지됩니다. 현재 조건의 계산은 설정 → 조건 반영 → 계산 실행에서 수행하세요.');
});
window.addEventListener('DOMContentLoaded',()=>{const b=$('openResearch');if(b){b.textContent='배치 검증';b.onclick=openPlacementAnalysis;}});


function selectWorkbenchTask(next){
 if(!workbench)return;
 if(!['map','compare'].includes(next))leavePresentation();
 if(next==='verify'){openPlacementAnalysis();return;}
 if(analysisDialog.open)analysisDialog.close();
 workbench.setTask(next);
 if(next==='settings'){freezeConditionBaseline();clearInterval(player);player=null;$('play').textContent='▶ 세대 재생';modeTo('design');return;}
 if(run)modeTo('result');
 if(next==='compare'){$('compareMaps').setAttribute('aria-pressed','true');zoom=1;panX=panY=0;}
 if(next==='map')$('compareMaps').setAttribute('aria-pressed','false');
 if(next==='solutions'){dock='solutions';renderDock();}
 renderMaps();renderInspector();
}
function leavePresentation(){document.body.classList.remove('presentation');const b=$('presentationMode');if(b){b.textContent='발표 보기';b.setAttribute('aria-pressed','false');}}
function showSelectionProperties(){if(!workbench)return;leavePresentation();if(innerWidth<1100)workbench.setTask('details');workbench.showSide('properties');}
import('/workbench-shell.js').then(({mountWorkbench})=>{
 workbench=mountWorkbench({selectTask:next=>selectWorkbenchTask(next)});
 $('applyDraft').hidden=true;
 const conditionTools=document.createElement('div');conditionTools.id='conditionCompareTools';conditionTools.innerHTML='<button id="pinConditionBaseline">현재 초안을 왼쪽 기준으로 고정</button><span id="conditionCompareNote"></span>';$('mapStage').before(conditionTools);$('pinConditionBaseline').onclick=()=>{if(!preview?.problem||previewPending)return;baselinePreview={problem:structuredClone(preview.problem),row:null,label:'고정한 초안 · 성능 미계산',cid:draft.sensor};renderMaps();};
 const contextInfo=document.createElement('button');contextInfo.id='contextInfo';contextInfo.textContent='지도·상태 안내';contextInfo.setAttribute('aria-expanded','false');contextInfo.onclick=()=>contextInfo.setAttribute('aria-expanded',document.body.classList.toggle('showContextInfo'));document.querySelector('.mapTop').prepend(contextInfo);
 const menu=document.createElement('button');menu.id='compactMenu';menu.textContent='프로젝트 메뉴';menu.setAttribute('aria-expanded','false');menu.onclick=()=>menu.setAttribute('aria-expanded',document.body.classList.toggle('showProjectMenu'));document.querySelector('.mapTop').prepend(menu);
 const detail=document.createElement('button');detail.id='inspectSelection';detail.textContent='선택 설명';detail.onclick=showSelectionProperties;document.querySelector('.mapTools').append(detail);const present=document.createElement('button');present.id='presentationMode';present.textContent='발표 보기';present.setAttribute('aria-pressed','false');present.onclick=()=>{if(!document.body.classList.contains('presentation')&&!['map','compare'].includes(workbench.task))selectWorkbenchTask('map');const active=document.body.classList.toggle('presentation');present.textContent=active?'작업 화면 복귀':'발표 보기';present.setAttribute('aria-pressed',active);};document.querySelector('.mapTools').append(present);
 $('toggleSettings').onclick=()=>selectWorkbenchTask(workbench.task==='settings'?'map':'settings');
 $('designMode').onclick=()=>selectWorkbenchTask('settings');$('resultMode').onclick=()=>selectWorkbenchTask('map');
 $('compareMaps').onclick=()=>selectWorkbenchTask(workbench.task==='compare'?'map':'compare');
 const originalCopy=$('copyRun').onclick;$('copyRun').onclick=async()=>{await originalCopy();workbench.setTask('settings');};
 const originalSensor=$('sensorProperties').onclick;$('sensorProperties').onclick=()=>{originalSensor();workbench.setTask('settings');};
 if(run)selectWorkbenchTask('map');else if(draft)renderMaps();
}).catch(e=>notice('작업 화면을 불러오지 못했습니다: '+e.message,'error'));


function renderMapReadings(){
 const row=mode==='result'?currentRow():null,base=referenceRow||initialRows.find(r=>String(r.id)===String(initial));
 for(const [host,item] of [[$('mainMap'),row],[$('initialMap'),base]]){
  const card=host.closest('.mapCard');let line=card.querySelector('.mapReading');
  if(!line){line=document.createElement('div');line.className='mapReading';host.before(line);}
  line.textContent=mode==='result'&&item?run.qualityLabels.map((label,i)=>label+' '+formatQuality(M.quality(item)[i])).join('  ·  ')+'  ·  비용 '+item.cost:'';
  line.hidden=!line.textContent;
 }
}
function selectPlotPoint(point){
 const x=+point.getAttribute('cx'),y=+point.getAttribute('cy'),plot=point.closest('.plot');
 const ids=[...plot.querySelectorAll('[data-row]')].filter(p=>Math.hypot(+p.getAttribute('cx')-x,+p.getAttribute('cy')-y)<=6).map(p=>+p.dataset.row);
 plot.querySelector('.pointCandidates')?.remove();
 if(ids.length===1){choose(ids[0]);return;}
 const panel=document.createElement('div');panel.className='pointCandidates';const label=document.createElement('label');label.textContent='겹친 배치 '+ids.length+'개 ';const select=document.createElement('select');select.id='overlapSolution';select.setAttribute('aria-label','겹친 점의 배치');
 option(select,ids.map(id=>{const r=resultRows().find(v=>v.id===id);return[String(id),'행 '+id+' · 비용 '+r.cost+' · '+r.sensor_counts.join(' / ')+'대'];}),String(point.dataset.row));label.append(select);
 const b=document.createElement('button');b.textContent='이 배치 선택';b.onclick=()=>{choose(+select.value);panel.remove();};panel.append(label,b);plot.append(panel);
}


function renderCommonSearchQuantities(g){
 const generic=draft.research?.selections?.[draft.sensor]?.solver_policy==='generic_v1';
 quantity(g,'진화 세대 수','generations',draft.optimizer,'세대',10,[20,50,100,150,250,500,1000,...(generic?[2000,5000]:[])],1,1,generic?null:1000);
 if(draft.research?.selections?.[draft.sensor]?.solver_policy==='generic_v1')quantity(g,'개체 수','population',draft.optimizer,'개',1,[12,36,92],1,4,256);
 else field(g,'개체 수','population',[[36,'36개 · 빠른 설정 점검'],[92,'92개 · 더 많은 참조방향'],[212,'212개 · 더 많은 참조방향']],'',draft.optimizer);
 quantity(g,'최적화 seed','seed',draft.optimizer,'정수',1,[8701,8702,8703],1,0,2147483647);
}
function footprintSummary(p){
 if(!p)return '지도 준비 중';
 const area=p.geometry?.area_km2;if(!(area>0))return '원면적 / 평가영역 · 평가영역 면적 미제공';
 const names=p.sensor_names||['Radar',draft.sensor===EO?'EO/IR':'RF'];
 return '원면적 / 평가영역 · '+p.radii.map((r,i)=>names[i]+' '+(100*Math.PI*(r/1000)**2/area).toFixed(1)+'%').join(' · ');
}
function footprintNote(p){return '원면적 비는 πr² / 평가영역 면적입니다. 실제 영역 커버율·중첩 제거·품질 점수가 아닙니다. '+(p?.geometry?.area_km2&&p.map_metres?'평가영역 / 지도 '+(100*p.geometry.area_km2/((p.map_metres/1000)**2)).toFixed(1)+'%.':'');}
function drawRadiusReference(host,p,row){
 if(!p||row)return;const svg=host.querySelector('svg');if(!svg)return;
 const center=p.geometry?.center||[(p.map_metres||20000)/2,(p.map_metres||20000)/2],unit=(p.map_metres||20000)/800;
 const group=document.createElementNS('http://www.w3.org/2000/svg','g');group.dataset.radiusReference='true';
 const ids=p._metadata?.sensors?.map(s=>s.id)||(configured()?run.metadata.sensors.map(s=>s.id):['radar',draft.sensor===EO?'eoir':'rf_scanner']);
 for(let i=0;i<p.radii.length;i++){const id=ids[i],x=60+center[0]/unit,y=850-center[1]/unit,r=p.radii[i]/unit;group.innerHTML+=sensorRange(id,x,y,r,true)+sensorRangeLabel(id,x,y,r,p.radii[i]/1000,i);}
 const caption=document.createElementNS(svg.namespaceURI,'text');caption.setAttribute('x','60');caption.setAttribute('y','935');caption.setAttribute('font-size','18');caption.setAttribute('fill','#365c71');caption.textContent='중앙 기준 반경 비교 · 센서 설치 아님';group.append(caption);svg.append(group);
}
function renderConditionComparison(){
 const editing=mode==='design'&&workbench?.task==='settings';
 $('initialSolution').hidden=editing;
 if($('conditionCompareTools'))$('conditionCompareTools').hidden=!editing;
 if(!editing)return;
 if(!baselinePreview&&preview?.problem)freezeConditionBaseline();
 const base=baselinePreview?.cid===draft.sensor?baselinePreview:null,p=preview?.problem;
 $('initialCard').hidden=false;
 $('initialCard').querySelector('.mapCardTitle').firstChild.textContent='기존 조건 · '+(base?.label||'준비 중')+' ';
 $('initialMap').innerHTML=mapHTML(base?.problem,base?.row);
 $('mapTitle').textContent='새 조건 · 자동 미리보기';
 $('mapBadge').textContent=previewPending?'갱신 대기 · 마지막 유효 조건':'현재 입력 · 성능 미계산';
 for(const [host,problem,row] of [[$('initialMap'),base?.problem,base?.row],[$('mainMap'),p,null]]){
  const card=host.closest('.mapCard'),reading=card.querySelector('.mapReading');reading.hidden=false;reading.textContent=footprintSummary(problem);
  drawRadiusReference(host,problem,row);
 }
 if($('conditionCompareNote'))$('conditionCompareNote').textContent=footprintNote(p);
 if($('pinConditionBaseline'))$('pinConditionBaseline').disabled=previewPending||!p;
}

