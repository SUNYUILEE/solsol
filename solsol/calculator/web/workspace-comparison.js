'use strict';
// Common A/B comparison: existing map renderer and immutable saved rows remain the source.
let comparisonRunKey='',comparisonReferenceKey='';
const comparisonSourceGenerations=new Map();
const comparisonKey=()=>run?draft.sensor+':'+run.run_id:'';
const comparisonBase=()=>referenceRow||initialRows.find(r=>String(r.id)===String(initial));
const comparisonUnit=m=>m.unit==='dimensionless'?'무차원':m.unit==='synthetic_cost'?'합성 비용':m.unit||'';
const comparisonNumber=v=>Number.isFinite(v)?v.toFixed(2):'미기록';
function comparisonRows(){return dock==='comparison'?resultRows():visibleRows();}
function comparisonLabel(r){return '배치 '+r.id+' · '+run.metadata.sensors.map((s,i)=>s.name+' '+r.sensor_counts[i]).join(' / ');}
function comparisonGuide(){
 let d=$('comparisonHelp');if(!d){d=document.createElement('dialog');d.id='comparisonHelp';d.innerHTML='<div class="dialogHead"><h2>두 배치를 비교하는 방법</h2><button id="comparisonHelpClose">닫기</button></div><ol><li><b>기준 A</b>에서 남겨 둘 배치를 고릅니다. 왼쪽 지도는 A로 고정됩니다.</li><li><b>대안 B</b>를 고르거나 이전·다음 버튼을 누릅니다. 오른쪽 지도만 바뀝니다.</li><li>지도 아래 <b>A에서 B로 바꾸면</b>을 읽습니다. 성능과 비용이 각각 좋아지는지, 나빠지는지 확인합니다.</li><li>더 많은 배치는 <b>비교 대상 목록·필터</b>에서 최종 해·이력·관측 배치와 목표 조건을 고릅니다. 목록에서 배치를 누르면 B가 됩니다. A는 그대로입니다.</li><li><b>확대 비교</b>에서도 같은 A/B와 레이어를 확인할 수 있습니다.</li></ol><p>두 지도는 같은 저장 실행·후보 좌표를 사용합니다. 센서 기호는 설치 위치, 둘레 선은 명목 범위입니다. 영역 밖에 있는 센서도 평가영역을 관측할 수 있습니다.</p><p>Hamming은 설치 여부가 다른 비트 수입니다. 한 센서를 옮기면 보통 2가 늘며, 성능 점수나 우열이 아닙니다. 모든 성능이 좋아지는 변화와, 어떤 성능을 얻고 다른 성능을 잃는 절충을 구분하세요.</p><p><a href="/quality-guide.html#compare" target="_blank" rel="noopener">전체 사용 시나리오 읽기 ↗</a></p>';document.body.append(d);$('comparisonHelpClose').onclick=()=>d.close();}d.showModal();
}
function openComparisonCollection(){
 let d=$('comparisonCollection');if(!d){d=document.createElement('dialog');d.id='comparisonCollection';d.innerHTML='<div class="dialogHead"><h2>비교 대상 목록·필터</h2><button id="comparisonCollectionClose">지도 비교로 돌아가기</button></div><p>이 창은 B로 고를 배치의 목록을 바꿉니다. 기준 A와 저장 계산 조건은 바꾸지 않습니다.</p><div id="comparisonCollectionBody"></div>';document.body.append(d);$('comparisonCollectionClose').onclick=()=>{d.close();renderMaps();};}d.dataset.runKey=comparisonKey();renderComparisonCollection();d.showModal();
}
function renderComparisonCollection(){const d=$('comparisonCollection');if(!d)return;if(d.dataset.runKey!==comparisonKey()){d.close();return;}const body=$('comparisonCollectionBody');body.replaceChildren();renderPlacementControls(body,'compareList_');}
function renderLargeComparisonTools(host,prefix){const group=document.createElement('div');group.id=prefix+'placementControls';group.className='largePairControls';host.append(group);const a=comparisonBase();noteText(group,`기준 A: 배치 ${a?.id??'없음'} · 대안 B: 배치 ${currentRow()?.id??'없음'} · 실행 ${run.run_id.slice(0,8)}. 두 지도는 같은 레이어와 확대 배율입니다.`);selectControl(group,'대안 B',comparisonRows().map(r=>[String(r.id),comparisonLabel(r)]),String(currentRow()?.id??''),v=>{choose(+v);expandControlsRefresh();},'largeComparisonB');}
function openPlacementComparison(pin=false){
 if(!run){notice('먼저 저장 실행을 선택하세요.');return;}
 if(comparisonRunKey!==comparisonKey())comparisonSourceGenerations.clear();
 dock='solutions';
 if(comparisonReferenceKey!==comparisonKey()||pin||!comparisonBase()){
  const row=currentRow()||comparisonRows()[0];referenceRow=row?structuredClone(row):null;referenceGeneration=run.generation;comparisonReferenceKey=comparisonKey();if(row)comparisonSourceGenerations.set(row.id,referenceGeneration);
 }
 comparisonRunKey=comparisonKey();
 selectWorkbenchTask('compare');
 const rows=comparisonRows(),base=comparisonBase(),other=rows.find(r=>r.id!==base?.id);
 if(other&&currentRow()?.id===base?.id)choose(other.id);else renderMaps();
}
function renderCompactPlacementTools(host){
 host.replaceChildren();
 if(workbench?.task!=='compare'){const b=document.createElement('button');b.textContent='해 목록·표시 조건';b.onclick=openComparisonCollection;host.append(b);return;}
 if(comparisonRunKey!==comparisonKey()){comparisonSourceGenerations.clear();comparisonRunKey=comparisonKey();comparisonReferenceKey='';referenceRow=null;}
 if(!comparisonBase()||comparisonReferenceKey!==comparisonKey()){const row=currentRow()||comparisonRows()[0];referenceRow=row?structuredClone(row):null;referenceGeneration=run.generation;comparisonReferenceKey=comparisonKey();}
 const base=comparisonBase(),rows=comparisonRows(),choices=[...new Map([base,...rows].filter(Boolean).map(r=>[String(r.id),r])).values()];
 if(base&&!comparisonSourceGenerations.has(base.id))comparisonSourceGenerations.set(base.id,referenceRow?referenceGeneration:0);
 const line=document.createElement('div');line.className='comparisonSelectors';host.append(line);
 selectControl(line,'기준 A · 왼쪽',choices.map(r=>[String(r.id),comparisonLabel(r)]),String(base?.id??''),v=>{const row=choices.find(r=>String(r.id)===v);if(row){referenceRow=structuredClone(row);referenceGeneration=comparisonSourceGenerations.get(row.id)??(row===base?referenceGeneration:run.generation);comparisonSourceGenerations.set(row.id,referenceGeneration);comparisonReferenceKey=comparisonKey();renderMaps();}},'comparisonA');
 selectControl(line,'대안 B · 오른쪽',rows.length?rows.map(r=>[String(r.id),comparisonLabel(r)]):[['','조건에 맞는 배치 없음']],String(currentRow()?.id??''),v=>{if(v!=='')choose(+v);},'comparisonB');
 const actions=document.createElement('div');actions.className='comparisonActions';line.append(actions);
 for(const [id,label,step] of [['comparisonPrevious','이전 B',-1],['comparisonNext','다음 B',1]]){const b=document.createElement('button');b.id=id;b.textContent=label;b.disabled=rows.length<2;b.onclick=()=>{const i=rows.findIndex(r=>r.id===selected);choose(rows[(i+step+rows.length)%rows.length].id);};actions.append(b);}
 const hint=document.createElement('div');hint.className='comparisonHint';host.append(hint);const text=document.createElement('span');text.textContent='A를 고정하고 B를 바꾸세요. 아래 표는 A → B의 성능·비용 변화입니다.';hint.append(text);
 for(const [id,label,fn] of [['comparisonBrowse','비교 대상 목록·필터',openComparisonCollection],['comparisonHow','사용 방법',comparisonGuide],['comparisonExpand','확대 비교',expand]]){const b=document.createElement('button');b.id=id;b.textContent=label;b.onclick=fn;hint.append(b);}
}
function renderComparisonReadout(){
 let panel=$('comparisonReadout');if(!panel){panel=document.createElement('section');panel.id='comparisonReadout';panel.setAttribute('aria-label','기준과 대안의 실제 수치 비교');$('mapStage').after(panel);}panel.hidden=workbench?.task!=='compare'||!run||mode!=='result';if(panel.hidden)return;panel.replaceChildren();
 const a=comparisonBase(),b=currentRow();
 $('initialSolution').hidden=true;$('initialCard').querySelector('.mapCardTitle').firstChild.textContent='A · 기준 배치 '+(a?.id??'없음')+' · '+(referenceRow?referenceGeneration:0)+'세대';
 $('mapTitle').textContent='B · 대안 배치 '+(b?.id??'없음');$('mapBadge').textContent='실행 '+run.run_id.slice(0,8)+' · '+run.generation+'세대';
 $('initialMap').dataset.comparisonRow=a?.id??'';$('mainMap').dataset.comparisonRow=b?.id??'';
 const title=document.createElement('strong');title.textContent='A에서 B로 바꾸면';panel.append(title);
 if(!a||!b){noteText(panel,'비교할 배치가 없습니다. 비교 대상 목록·필터에서 표시 조건을 바꾸세요. 원래 해집합이 0개라는 뜻은 아닙니다.');return;}
 const metrics=(run.research_configuration?.objective_ids||run.registry?.objective_order||[]).map(id=>run.metadata.metrics.find(m=>m.id===id)).filter(Boolean);
 const delta=tradeoffDelta(a,b,metrics),hamming=a.X.flat().reduce((n,v,i)=>n+(v!==b.X.flat()[i]),0),g=delta.filter(d=>d.better>1e-12).length,l=delta.filter(d=>d.better< -1e-12).length;
 const summary=document.createElement('span');summary.className='comparisonVerdict';summary.textContent=hamming===0?'같은 설치 배치입니다.':`설치 차이 ${hamming}비트 · ${g}개 목적 개선 / ${l}개 저하`+(g&&l?' · 성능·비용의 절충':g?' · 관측 목적에서 B 개선':l?' · 관측 목적에서 A 우세':' · 목적값은 같고 위치는 다릅니다');panel.append(summary);
 const wrap=document.createElement('div');wrap.className='comparisonMetricScroll';panel.append(wrap);const table=document.createElement('table');table.innerHTML='<thead><tr><th>비교 항목</th><th>기준 A</th><th>대안 B</th><th>B − A · 변화</th></tr></thead>';wrap.append(table);const body=table.createTBody();
 metrics.forEach((m,i)=>{const d=delta[i],s=m.display_scale||1,unit=m.unit==='%'?'%p':comparisonUnit(m),tr=body.insertRow();tr.dataset.metric=m.id;for(const text of [m.name+' · '+(tradeoffMin(m)?'낮을수록 좋음':'높을수록 좋음'),(a.named_metrics[m.id]*s).toFixed(2)+' '+comparisonUnit(m),(b.named_metrics[m.id]*s).toFixed(2)+' '+(m.unit||''),(d.display>0?'+':'')+d.display.toFixed(4)+' '+unit+' · '+(d.better>1e-12?'개선':d.better< -1e-12?'저하':'같음')])tr.insertCell().textContent=text;});
 const details=document.createElement('details');details.className='comparisonCoverage';panel.append(details);const sum=document.createElement('summary');sum.textContent='영역 커버율·저장 목표·출처';details.append(sum);
 const goals=savedAreaGoals();noteText(details,goalSummary(goals,run.metadata));evidenceTable(details,['영역 지표','기준 A (%)','대안 B (%)','차이 (%p)'],(run.metadata.coverage_metrics||[]).map(m=>[m.name,comparisonNumber(a.coverage_metrics?.[m.id]),comparisonNumber(b.coverage_metrics?.[m.id]),comparisonNumber(Number.isFinite(b.coverage_metrics?.[m.id])&&Number.isFinite(a.coverage_metrics?.[m.id])?b.coverage_metrics[m.id]-a.coverage_metrics[m.id]:null)]));noteText(details,`같은 실행 ${run.run_id} · A 원시 행 ${a.id} (${referenceRow?referenceGeneration:0}세대) · B 원시 행 ${b.id} (${run.generation}세대). 목표 통과는 ${a.qualified===null?'A 미설정':a.qualified?'A 통과':'A 미달'} / ${b.qualified===null?'B 미설정':b.qualified?'B 통과':'B 미달'}. Hamming은 성능 목적이 아닙니다.`);
}
const comparisonOldMaps=renderMaps;renderMaps=function(){comparisonOldMaps();renderComparisonReadout();if($('comparisonCollection')?.open)renderComparisonCollection();if(workbench?.task!=='compare')$('initialSolution').hidden=mode==='design';};
const comparisonOldTask=selectWorkbenchTask;selectWorkbenchTask=function(next){if(next==='compare'){dock='solutions';if(comparisonReferenceKey!==comparisonKey()){const r=currentRow()||comparisonRows()[0];referenceRow=r?structuredClone(r):null;referenceGeneration=run?.generation??0;comparisonReferenceKey=comparisonKey();comparisonRunKey=comparisonKey();}}comparisonOldTask(next);if(next==='compare')renderDock();};
const comparisonOldDock=renderDock;renderDock=function(){comparisonOldDock();const tab=document.querySelector('[data-dock=solutions]');if(tab)tab.setAttribute('aria-selected',dock!=='evidence');if(!configured()||dock==='evidence')return;const toolbar=document.createElement('div');toolbar.className='checkedSubset';const b=document.createElement('button');b.id='checkedSubset';b.textContent=dock==='comparison'?'전체 목록으로 돌아가기':'체크한 배치만 보기 ('+compared.size+'개)';b.textContent=dock==='comparison'?'전체 목록으로 돌아가기':b.textContent;b.onclick=()=>{dock=dock==='comparison'?'solutions':'comparison';renderDock();renderMaps();};toolbar.append(b);if(dock==='comparison')noteText(toolbar,compared.size?'체크한 배치의 표입니다. 두 지도를 비교하려면 왼쪽 배치 비교를 여세요.':'체크한 배치가 없습니다. 전체 목록으로 돌아가 표의 체크칸을 선택하세요.');$('dockBody').prepend(toolbar);};
const comparisonOldClear=clearRun;clearRun=function(){comparisonSourceGenerations.clear();comparisonRunKey='';comparisonReferenceKey='';$('comparisonCollection')?.close();comparisonOldClear();};
window.addEventListener('DOMContentLoaded',()=>{$('pinSolution').textContent='이 배치를 기준 A로 비교';$('pinSolution').onclick=()=>openPlacementComparison(true);document.querySelector('[data-dock=comparison]')?.remove();$('dockBody').addEventListener('change',e=>{if(e.target.matches('input[type=checkbox]')&&$('checkedSubset')&&dock!=='comparison')$('checkedSubset').textContent='체크한 배치만 보기 ('+compared.size+'개)';});const help=$('helpDialog'),p=document.createElement('p'),b=document.createElement('button');b.textContent='두 배치 비교 사용법';b.onclick=()=>{help.close();comparisonGuide();};const a=document.createElement('a');a.href='/quality-guide.html#compare';a.target='_blank';a.rel='noopener';a.textContent='전체 사용 시나리오 읽기 ↗';p.append(b,document.createTextNode(' '),a);help.append(p);});
