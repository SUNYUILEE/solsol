'use strict';
// Saved-row inspection only. Explicit navigation delegates the main view; no optimizer call.
const LiveInspector=(()=>{
 let current=null,shown=null,start=null,pair=null,opener=null,navBusy=false,navEpoch=0,navMessage='';
 const el=id=>document.getElementById(id);
 function navigation(){
  if(!el('inspectGeneration'))return;
  const b=pair?.current,a=pair?.start,h=b?.job?.history||[],g=b?.generation;
  const disabled=navBusy||!b?.job||b.job.id!==current?.job?.id;
  el('inspectGeneration').innerHTML=h.map(s=>`<option value="${s.generation}">${s.generation}세대 · ${s.evaluations.toLocaleString()}회 평가</option>`).join('');
  el('inspectGeneration').value=String(g??'');el('inspectGeneration').disabled=disabled||!h.length;
  const i=h.findIndex(s=>s.generation===g);
  el('inspectPrevious').disabled=disabled||i<=0;el('inspectNext').disabled=disabled||i<0||i>=h.length-1;
  const diagnostic=document.getElementById('diagnostics')?.checked,scope=document.getElementById('solutionScope')?.value||'target_front',allRows=b?.job?.points||[],minimal=document.getElementById('localMinimal')?.checked,scoped=(diagnostic?allRows:LiveSelection.inScope(allRows,scope)).filter(p=>diagnostic||!minimal||LiveSelection.oneDeleteMinimal(b.job.problem,p,b.job.config?.objective_contract)),rows=LiveSelection.costOrdered(typeof LiveFrontInsight==='undefined'?scoped:LiveFrontInsight.uniquePoints(scoped)),archive=new Set(b?.job?.snapshot?.archive_ids||[]),front=new Set(b?.job?.snapshot?.front_ids||[]);
  const label=p=>`#${p.id} · ${p.cost}점 · 탐지 ${LiveCore.pct(p.performance[0])} / 식별 ${LiveCore.pct(p.performance[1])} · ${LiveSelection.targetQualified(p)?'목표 통과':'목표 미달 · 진단'}${archive.has(p.id)?' · 누적 비지배':front.has(p.id)?' · 현재 세대 비지배':''}`;
  const target=rows.filter(LiveSelection.targetQualified),other=rows.filter(p=>!LiveSelection.targetQualified(p)),options=(group,title)=>group.length?`<optgroup label="${title} · ${group.length}개 · 비용 낮은 순">${group.map((p,i)=>`<option value="${p.id}">비용순 ${i+1}/${group.length} · ${label(p)}</option>`).join('')}</optgroup>`:'';
  el('inspectSolution').innerHTML='<option value="">배치 선택</option>'+options(target,'목표통과 누적 비지배')+options(other,'목표 미달 절충·진단');
  const staleGeneration=b?.generation!==current?.generation;
  el('inspectSolution').value=b?.point?String(b.point.id):'';el('inspectSolution').disabled=disabled||staleGeneration||!rows.length;
  el('inspectInitialSolution').innerHTML='<option value="">시작 배치 선택</option>'+(a?.job?.points||[]).slice().sort((x,y)=>x.id-y.id).map(p=>`<option value="${p.id}">#${p.id} · ${p.cost}점 · R${p.sensor_counts[0]} / E${p.sensor_counts[1]}</option>`).join('');
  el('inspectInitialSolution').value=a?.point?String(a.point.id):'';el('inspectInitialSolution').disabled=disabled||staleGeneration||!a?.job?.points?.length;
  const staleRun=b?.job?.id!==current?.job?.id;
  el('inspectNavigationStatus').textContent=navBusy?navMessage:staleRun?'실행이 바뀌었습니다. 닫고 현재 실행의 지도를 다시 여세요.':staleGeneration?'본 화면의 세대가 바뀌었습니다. 지도는 직전 선택 배치입니다. 세대를 먼저 선택한 다음 배치를 고르세요.':navMessage||`목표통과 누적 비지배 ${target.length}개 · 전체 표시 ${rows.length}개 · 비용 낮은 순${diagnostic?' · 진단 포함':''}`;
  el('inspectNavigation').setAttribute('aria-busy',String(navBusy));
 }
 function sync(which,run){
  if(current?.job?.id!==run)throw Error('실행이 바뀌었습니다. 닫고 현재 실행의 지도를 다시 여세요.');
  pair=structuredClone({start,current});shown=pair[which];
 }
 async function moveGeneration(value){
  if(navBusy||!pair)return;
  const g=Number(value),run=pair.current?.job?.id;
  if(value===''||!Number.isInteger(g)||!pair.current?.job?.history?.some(s=>s.generation===g))return;
  const ticket=++navEpoch;navBusy=true;navMessage=`${g}세대 자료를 불러오는 중입니다. 지도는 직전 선택 배치입니다.`;navigation();
  try{
   if(run!==current?.job?.id)throw Error('실행이 바뀌었습니다. 닫고 현재 실행의 지도를 다시 여세요.');
   await LiveReplay.seek(g);
   if(ticket!==navEpoch||!el('mapInspector').open)return;
   if(!el('error').hidden||current?.generation!==g)throw Error('요청한 세대 자료를 확인하지 못했습니다. 지도는 직전 선택 배치입니다. 다시 연결 후 시도하세요.');
   sync('current',run);navMessage=`${g}세대로 이동했습니다. 가장 나중에 평가된 생존 배치를 표시하며, 최적해나 같은 개체의 후손을 뜻하지 않습니다.`;
  }catch(e){navMessage=e.message;}finally{if(ticket===navEpoch){navBusy=false;render();}}
 }
 function pick(which){
  if(navBusy||!pair)return;
  const control=el(which==='start'?'inspectInitialSolution':'inspectSolution'),value=control.value,run=pair.current?.job?.id;
  if(value===''||!pair[which]?.job?.points?.some(p=>p.id===Number(value))){navigation();return;}
  try{
   if(run!==current?.job?.id)throw Error('실행이 바뀌었습니다. 닫고 현재 실행의 지도를 다시 여세요.');
   if(pair.current?.generation!==current?.generation)throw Error('본 화면의 세대가 바뀌었습니다. 세대를 먼저 선택한 다음 배치를 고르세요.');
   if(which==='start'){el('initialSolution').value=value;el('initialSolution').onchange();}
   else{selectFrom('inspectSolution');}
   if((which==='start'?start:current)?.point?.id!==Number(value))throw Error('선택 배치를 확인하지 못했습니다. 세대를 다시 선택하세요.');
   sync(which,run);navMessage=`${which==='start'?'시작':'현재 세대'} 배치 #${value} 선택 · 본 화면의 지도·수치와 연결됩니다.`;
  }catch(e){navMessage=e.message;}render();
 }
 function inventoryText(c,counts){
  if(c.resource_mode==='all')return counts.some((v,i)=>v!==[c.radar_stock,c.eo_stock][i])?'보유량 전부 사용 조건을 위반한 배치입니다. 목표·자원 표를 확인하세요.':'보유량 전부 사용: 대수가 같으면 비용은 고정됩니다. 위치와 모델 성능을 비교하세요.';
  if(c.resource_mode==='partial'){const delta=[c.radar_stock-counts[0],c.eo_stock-counts[1]];return delta.some(v=>v<0)?`보유량 초과: Radar ${Math.max(0,-delta[0])}대 / EO/IR ${Math.max(0,-delta[1])}대. 사용 가능한 배치가 아닙니다.`:`미사용: Radar ${delta[0]}대 / EO/IR ${delta[1]}대.`;}
  return '금액이 아닌 합성 비용점수입니다.';
 }
 function metrics(problem,point){
  if(!point)return null;
  if(!point.identity?.decision_sha256)throw Error('선택 배치의 결정벡터 계보가 없습니다. 지도를 표시할 수 없습니다.');
  LiveQualityLineage.validateSetPoint({mask:point.mask,decision_sha256:point.identity.decision_sha256},problem.sites.length);
  return ModelDisplay.call('inspect_metrics',problem,point,problem.objective_contract||current?.job?.config?.objective_contract);
 }
 function renderContent(){
  const dialog=el('mapInspector');if(!dialog.open)return;
  navigation();
  if(!shown?.point){el('inspectMap').innerHTML='';el('inspectMetrics').innerHTML='';el('inspectIdentity').textContent='선택한 배치가 없습니다. 닫은 뒤 목록에서 배치를 선택하세요.';return;}
  const {problem,point,job,generation}=shown,m=metrics(problem,point),c=job.config;
  el('inspectIdentity').textContent=`${generation}세대 · 배치 #${point.id} · 선택 시점 고정 · 실행 ${job.id}`;
  el('inspectTitle').textContent=shown===pair?.start?'시작 배치 상세':'선택 세대 배치 상세';
  el('inspectSource').textContent=shown===pair?.start?shown.source:'목록·그래프 또는 세대 관찰에서 선택한 배치입니다. 초기 배치의 후손이라는 뜻은 아닙니다.';
  for(const [id,key] of [['inspectStart','start'],['inspectCurrent','current']]){el(id).disabled=!pair?.[key]?.point;el(id).setAttribute('aria-pressed',String(shown===pair?.[key]));}
  const a=pair?.start,b=pair?.current;
  if(a?.point)metrics(a.problem,a.point);
  if(b?.point)metrics(b.problem,b.point);
  el('inspectPair').textContent=a?.point&&b?.point?`선택한 두 배치 비교 · 0세대 #${a.point.id} → ${b.generation}세대 #${b.point.id}\n탐지 ${(100*(b.point.performance[0]-a.point.performance[0])).toFixed(2)}%p · 식별 ${(100*(b.point.performance[1]-a.point.performance[1])).toFixed(2)}%p · 비용 ${a.point.cost} → ${b.point.cost}점 (${b.point.cost-a.point.cost>=0?'+':''}${b.point.cost-a.point.cost}점)\n집단 전체의 개선량이나 최적해 대비 격차가 아닙니다.`:'두 배치를 모두 선택하면 같은 실행의 시작·현재 배치 차이를 표시합니다.';
  el('inspectHeadline').textContent=`탐지 ${m.missions[0].percent.toFixed(2)}% · 식별 ${m.missions[1].percent.toFixed(2)}% · 비용 ${m.cost}점 · Radar ${m.counts[0]}대 / EO/IR ${m.counts[1]}대`;
  el('inspectCandidates').parentElement.lastChild.textContent=` 후보지 ${problem.sites.length}곳`;
  el('inspectMap').innerHTML=LiveCore.map(problem,point,{layer:el('inspectLayer').value,candidates:el('inspectCandidates').checked,candidateLabels:el('inspectCandidateLabels').checked,demand:el('inspectDemand').checked,defense:el('inspectDefense').checked});
  const zoom=Number(el('inspectZoom').value),view=el('inspectViewport');
  el('inspectMap').style.width=zoom?(100*zoom)+'%':Math.min(view.clientWidth,view.clientHeight*930/945)+'px';
   el('inspectMetrics').innerHTML=m.missions.map((v,i)=>`<section class="inspectMission ${v.missing?'isShort':''}"><h3>${i?'식별':'탐지'} <span>목표 ${i?'90':'95'}%</span></h3><strong>${v.percent.toFixed(2)}%</strong><p>${v.hit} / ${m.den[i]} 평가점</p><p class="inspectTarget">${v.missing?`목표까지 ${v.missing}개 부족 (${v.deficit.toFixed(2)}%p)`:'목표 도달'}</p><small>목표에 필요한 평가점 ${v.required}개 · ${i?'식별':'탐지'}되지 않은 점 ${v.uncovered}개</small></section>`).join('')+
   `<section class="inspectMission"><h3>설치 비용</h3><strong>${m.cost}점</strong><p>Radar ${m.counts[0]}대 × 6점<br>EO/IR ${m.counts[1]}대 × 2점</p><p>${LiveCore.resourceLabel(c)}</p><small>${inventoryText(c,m.counts)}</small></section>`;
  const areaContext=problem.objective_contract==='layered_mission_v7'&&problem.mission_zones?`탐지 면적 ${problem.geometry.area_km2.toFixed(2)} km² · 식별 면적 ${problem.mission_zones.identification_geometry.area_km2.toFixed(2)} km²`:`평가 면적 ${problem.geometry.area_km2.toFixed(2)} km²`;
  el('inspectContext').textContent=`${problem.map_metres/1000||20} × ${problem.map_metres/1000||20} km 지도 · ${areaContext} · Radar 반경 ${problem.radii[0]/1000} km · EO/IR 반경 ${problem.radii[1]/1000} km`;
 }
 function render(){try{renderContent();}catch(e){el('inspectMap').innerHTML='';el('inspectMetrics').innerHTML='';el('inspectHeadline').textContent='';el('inspectPair').textContent='수치 검증 실패 · 두 배치 비교를 표시할 수 없습니다.';el('inspectSource').textContent='';el('inspectIdentity').textContent=e.message;}}
 function update(problem,point,job,generation){current=job?{problem,point,job,generation}:null;start=job&&typeof LiveReplay.inspectionStart==='function'?LiveReplay.inspectionStart(job):null;el('inspectOpen').disabled=!point;el('inspectInitialOpen').disabled=!start?.point;render();}
 function center(){const view=el('inspectViewport'),map=el('inspectMap');view.scrollTop=Math.max(0,(map.scrollHeight-view.clientHeight)/2);view.scrollLeft=Math.max(0,(map.scrollWidth-view.clientWidth)/2);}
 function fitViewport(){
  if(!el('mapInspector').open||Number(el('inspectZoom').value)!==0)return;
  const view=el('inspectViewport');
  el('inspectMap').style.width=Math.max(0,Math.min(view.clientWidth,view.clientHeight*930/945))+'px';
 }
 function mapKey(event){
  const view=el('inspectViewport');
  if(!el('mapInspector').open||document.activeElement!==view||event.target!==view||event.altKey||event.ctrlKey||event.metaKey)return;
  const moves={ArrowLeft:[-80,0],ArrowRight:[80,0],ArrowUp:[0,-80],ArrowDown:[0,80]};
  if(moves[event.key]){event.preventDefault();const [x,y]=moves[event.key];view.scrollLeft=Math.max(0,Math.min(view.scrollWidth-view.clientWidth,view.scrollLeft+x));view.scrollTop=Math.max(0,Math.min(view.scrollHeight-view.clientHeight,view.scrollTop+y));}
  else if(event.key==='Home'){event.preventDefault();center();}
  else if(['+','=','-'].includes(event.key)){event.preventDefault();const options=[0,1,1.5,2],control=el('inspectZoom'),index=options.indexOf(Number(control.value));control.value=String(options[Math.max(0,Math.min(options.length-1,index+(event.key==='-'?-1:1)))]);render();center();}
 }
 function init(){
  const open=(which,button)=>{const selected=which==='start'?start:current;if(!selected?.point)return;LiveReplay.stop();pair=structuredClone({start,current});shown=pair[which];navMessage='';navBusy=false;++navEpoch;opener=button;el('inspectLayer').value=el('layer').value;el('inspectCandidates').checked=el('candidates').checked;el('inspectCandidateLabels').checked=el('candidateLabels').checked;el('inspectDefense').checked=el('defense').checked;el('inspectDemand').checked=el('demand').checked;el('mapInspector').showModal();render();center();el('inspectClose').focus();};
  el('inspectOpen').onclick=()=>open('current',el('inspectOpen'));
  el('inspectInitialOpen').onclick=()=>open('start',el('inspectInitialOpen'));
  for(const [id,key] of [['inspectStart','start'],['inspectCurrent','current']])el(id).onclick=()=>{if(!pair?.[key]?.point)return;shown=pair[key];render();};
  el('inspectClose').onclick=()=>el('mapInspector').close();
  el('mapInspector').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();el('mapInspector').close();}});
  el('mapInspector').addEventListener('close',()=>{++navEpoch;navBusy=false;shown=null;pair=null;const target=opener&&!opener.disabled?opener:el('mapSection');if(target.id==='mapSection')target.setAttribute('tabindex','-1');target.focus();opener=null;});
  el('inspectGeneration').onchange=()=>moveGeneration(el('inspectGeneration').value);
  for(const [id,step] of [['inspectPrevious',-1],['inspectNext',1]])el(id).onclick=()=>{const h=pair?.current?.job?.history||[],i=h.findIndex(s=>s.generation===pair?.current?.generation);if(h[i+step])return moveGeneration(String(h[i+step].generation));};
  el('inspectSolution').onchange=()=>pick('current');el('inspectInitialSolution').onchange=()=>pick('start');
  for(const id of ['inspectLayer','inspectCandidates','inspectCandidateLabels','inspectDefense','inspectDemand'])el(id).addEventListener('change',render);
  el('inspectZoom').addEventListener('change',()=>{render();center();});
  el('inspectCenter').onclick=center;
  el('inspectViewport').addEventListener('keydown',mapKey);
  if(typeof ResizeObserver!=='undefined')new ResizeObserver(fitViewport).observe(el('inspectViewport'));
 }
 return{metrics,inventoryText,update,init};
})();
if(typeof module!=='undefined')module.exports=LiveInspector;
