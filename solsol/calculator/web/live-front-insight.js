'use strict';
const LiveFrontInsight=(()=>{
 const maskKey=p=>Array.isArray(p?.mask)?p.mask.join(','):`id:${p?.id}`;
 const objectiveKey=p=>`${p.performance[0].toFixed(12)}|${p.performance[1].toFixed(12)}|${p.cost}`;
 function uniquePoints(points){
  const groups=new Map();
  for(const point of points||[]){const key=maskKey(point);if(!groups.has(key))groups.set(key,{point,ids:[]});groups.get(key).ids.push(point.id);}
  return [...groups.values()].map(group=>({...group.point,duplicateIds:group.ids.slice().sort((a,b)=>a-b),occurrences:group.ids.length})).sort((a,b)=>a.cost-b.cost||b.performance[0]-a.performance[0]||b.performance[1]-a.performance[1]||a.id-b.id);
 }
 function uniqueObjectives(points){return new Set((points||[]).map(p=>p.F?.join('|')||JSON.stringify([p.objective_performance||p.performance,p.cost]))).size;}
 function bands(points){
  const bins=[['95–96%',.95,.96],['96–97%',.96,.97],['97–98%',.97,.98],['98–99%',.98,.99],['99–100%',.99,1.0000001]];
  return bins.map(([label,lo,hi])=>({label,count:(points||[]).filter(p=>p.performance[0]>=lo&&p.performance[0]<hi).length}));
 }
 function objectiveDisplayGroups(points,selectedId,targetPredicate=p=>LiveSelection.targetQualified(p)){
  const groups=new Map();
  for(const point of points||[]){const key=objectiveKey(point);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(point);}
  return [...groups.values()].map(group=>{
   group.sort((a,b)=>a.id-b.id);
   const targetQualified=group.every(targetPredicate),expand=targetQualified&&group.length>1;
   if(expand||group.length===1)return {points:group,targetQualified,expand,collapsedCount:0};
   const selected=group.find(point=>point.id===selectedId||point.duplicateIds?.includes(selectedId))||group[0];
   return {points:[selected],targetQualified:false,expand:false,collapsedCount:group.length-1};
  });
 }
 function render(run,selectedId){
  const host=document.getElementById('frontInsight');if(!host)return;
  if(!run?.snapshot||!Array.isArray(run.points)){host.innerHTML='<div class="insightEmpty">계산 결과를 불러오면 해집합의 변별력과 고유 배치를 검사합니다.</div>';return;}
  const points=displayPoints(),unique=uniquePoints(points),diagnostic=document.getElementById('diagnostics')?.checked,scope=document.getElementById('solutionScope')?.value||'target_front',targetMode=!diagnostic&&scope==='target_front',front=new Set(displayFrontIds()),frontPoints=points.filter(p=>front.has(p.id)),archiveUnique=uniquePoints(run.points||[]),unionUnique=uniquePoints([...(run.points||[]),...(run.current_population_points||[])]),archiveTarget=archiveUnique.filter(LiveSelection.targetQualified),detectionOnly=unionUnique.filter(p=>p.performance[0]>=.95-1e-10&&p.performance[1]<.90-1e-10),jointTargetUnion=unionUnique.filter(LiveSelection.targetQualified),rawCounts=run.audit?.population_counts||null,minimalFilter=!diagnostic&&Boolean(document.getElementById('localMinimal')?.checked),seedKnown=Number.isInteger(run.initialization?.seed_count),seedCount=seedKnown?run.initialization.seed_count:null;
  if(!points.length){host.innerHTML=`<div class="insightEmpty"><b>${diagnostic?'이 세대에 표시할 진단 배치가 없습니다.':targetMode?'선택 세대까지 정량목표(탐지 95%·식별 90%)와 자원 조건을 모두 통과한 누적 비지배 배치가 없습니다.':'선택 세대까지 표시할 물리 비지배 절충해가 없습니다.'}</b><br>빈 목록을 0% 성능이나 0점 비용으로 해석하지 않습니다.${targetMode?' 전체 물리 Pareto 목록이나 원시 진단 보기에서 미달 절충해를 확인할 수 있습니다.':''}</div>`;return;}
  const ds=points.map(p=>p.performance[0]),min=Math.min(...ds),max=Math.max(...ds),near=points.filter(p=>p.performance[0]>=.99).length,ratio=points.length?near/points.length:0;
  const saturated=points.length>1&&(ratio>=.8||max-min<.02),rawReplay=run.audit?.raw_replay==='PASS';
  const bins=bands(points),peak=Math.max(1,...bins.map(b=>b.count));
  const displayGroups=objectiveDisplayGroups(unique,selectedId),sameFGroups=displayGroups.filter(group=>group.expand);
  const option=(point,extra='')=>`<option value="${point.id}" ${point.duplicateIds.includes(selectedId)?'selected':''}>#${point.id} · R${point.sensor_counts?.[0]??'?'} / E${point.sensor_counts?.[1]??'?'} · ${point.cost}점 · 탐지 ${(point.performance[0]*100).toFixed(2)}% · 식별 ${(point.performance[1]*100).toFixed(2)}%${extra}${diagnostic&&!LiveSelection.targetQualified(point)?' · 목표 미달 진단':''}${point.occurrences>1?' · 동일 X '+point.occurrences+'회':''}</option>`;
  const groupedOptions=displayGroups.map(group=>{if(!group.expand){const collapsed=group.collapsedCount?` · 같은 성능·비용 목표 미달 배치 ${group.collapsedCount}개 접음`:'';return option(group.points[0],collapsed);}const reference=LiveHamming.medoid(group.points);return `<optgroup label="목표통과 · 동일 성능·비용 · 서로 다른 배치 ${group.points.length}개">${group.points.map((point,index)=>option(point,` · 구조 ${index+1}/${group.points.length} · 기준 #${reference.id}와 dH ${LiveHamming.distance(point.mask,reference.mask)}`)).join('')}</optgroup>`;}).join('');
  const selectableCount=displayGroups.reduce((sum,group)=>sum+group.points.length,0),collapsedUnqualified=displayGroups.reduce((sum,group)=>sum+group.collapsedCount,0);
  host.innerHTML=`<div class="insightHead"><div><span class="insightEyebrow">${diagnostic?'원시 탐색 진단':targetMode?'성능 기준 충족 배치':'전체 물리 절충 배치'}</span><h3>${diagnostic?'누적 절충해 + '+run.snapshot.generation+'세대 전체 · 기준 미달 포함':targetMode?'0–'+run.snapshot.generation+'세대 누적 기준충족 비지배 해':'0–'+run.snapshot.generation+'세대 누적 전체 물리 비지배 해 · 기준 미달 포함'}</h3></div><div class="insightActions"><span class="insightState ${saturated?'warning':'supported'}">${saturated?'탐지 목적 변별력 경고':'목적 분포 확인'}</span><label class="insightDiagnosticToggle"><input id="frontDiagnosticsMirror" type="checkbox"${diagnostic?' checked':''}>${diagnostic?'Pareto 목록으로 돌아가기':'원시 진단 보기'}</label></div></div>
  <div class="insightMetrics"><article><span>${diagnostic?'진단 합집합 고유 X':'누적 원시 비지배 X'}</span><strong>${diagnostic?unionUnique.length:archiveUnique.length}</strong><small>${diagnostic?'누적 비지배와 현재 생존집단 통합':'0세대부터 선택 세대까지·동일 X 통합'}</small></article><article><span>${minimalFilter?(targetMode?'목표통과·삭제최소 X':'전체절충·삭제최소 X'):'현재 표시 고유 X'}</span><strong>${unique.length}</strong><small>${minimalFilter?(targetMode?`누적 목표통과 ${archiveTarget.length}개 중 단일삭제 검사 통과`:`전체 물리 비지배 ${archiveUnique.length}개 중 단일삭제 검사 통과`):'필터 미적용'}</small></article><article><span>현재 표시 고유 F</span><strong>${uniqueObjectives(points)}</strong><small>탐지·식별·비용 조합</small></article><article><span>현재 표시 탐지 범위</span><strong>${(min*100).toFixed(2)}–${(max*100).toFixed(2)}%</strong><small>${near}/${points.length}개가 99% 이상</small></article></div>
  <div class="admissionFunnel" aria-label="모집단별 해 수 비교"><article><span>원시 평가 중 물리 실현가능</span><b>${rawCounts?rawCounts.physical_feasible_rows.toLocaleString():'미계산'}</b><small>G≤0 · 목표 통과와 다른 판정</small></article><article><span>원시 평가 중 탐지만 통과</span><b>${rawCounts?(rawCounts.detection_target_rows-rawCounts.joint_target_rows).toLocaleString():detectionOnly.length}</b><small>D≥95%, I&lt;90%</small></article><article><span>원시 평가 중 두 목표 통과</span><b>${rawCounts?rawCounts.joint_target_rows.toLocaleString():jointTargetUnion.length}</b><small>D≥95%, I≥90% · 중복 행 포함</small></article><article><span>누적 비지배 두 목표 통과</span><b>${archiveTarget.length}</b><small>목표 통과 원시행 중 비지배 archive</small></article><article><span>현재 설명 목록</span><b>${diagnostic?'진단':unique.length}</b><small>${minimalFilter?'archive 목표통과 후 단일삭제 최소성 적용':'추가 숨김 없음'}</small></article></div>
  <p class="insightPopulationNote"><b>물리 실현가능</b>은 설치·보유량 제약 G≤0, <b>성능 기준 충족</b>은 탐지 95%와 식별 90%의 동시 달성입니다. 원시 기준충족 수가 누적 archive보다 큰 것은 계산 누락이 아니라, 지배되거나 같은 목적·배치가 반복된 행을 archive가 보존하지 않기 때문입니다. 탐지 분포 막대는 <b>${diagnostic?'진단 합집합':'현재 설명 목록'}</b>의 탐지율만 표시하므로 막대 개수만으로 식별 90% 충족을 판단할 수 없습니다. 이 실행의 초기화는 <b>${run.initialization?.method||run.config?.initializer||'미확인'}</b>, 실제 준비해 주입 <b>${seedKnown?seedCount+'개':'미확인'}</b>입니다.${run.config?.initializer!=='random'&&seedKnown&&seedCount===0?' 이름은 seeded 방식이지만 실제 시작집단은 무작위와 동일합니다.':run.config?.initializer!=='random'&&!seedKnown?' 초기화 계보에 준비해 수가 없어 seeded 여부를 확인할 수 없습니다.':''}</p>
  <div class="insightBody"><div><h4>탐지 분포</h4><div class="bandChart">${bins.map(b=>`<div><span>${b.label}</span><i style="--bar:${100*b.count/peak}%"></i><b>${b.count}</b></div>`).join('')}</div><p class="insightNote">${saturated?'이 세대에서는 탐지축이 거의 상수라 3목적 문제가 실질적으로 식별–비용 절충에 가까워졌습니다. 원시 평가 전체나 참 Pareto 전선이 같다는 뜻은 아닙니다.':'탐지축에 서로 다른 절충값이 남아 있습니다.'}</p></div>
  <div class="solutionExplorer"><h4>${diagnostic?'진단 배치 탐색':targetMode?'목표통과 고유 배치 탐색':'전체 절충 고유 배치 탐색'}</h4><label for="frontSolutionExplorer">지도에서 분석할 배치</label><select id="frontSolutionExplorer"><option value="">지도 선택 항목 ${selectableCount}개 중 선택</option>${groupedOptions}</select><p>${diagnostic?'이 목록은 현재 세대 원시 진단행이며 목표 미달이 포함될 수 있습니다. 목표 미달 상태에서 성능·비용까지 같은 다른 배치는 펼치지 않고 대표 진단 1개만 남깁니다. ':targetMode?'이 목록의 모든 배치는 탐지 95%와 식별 90%를 동시에 통과합니다. ':'이 목록은 목표 미달을 포함한 전체 물리 비지배 절충해입니다. '}완전히 같은 설치벡터 X 반복 ${points.length-unique.length}개는 하나로 묶였습니다. 탐지 95%·식별 90%를 통과하면서 동일한 탐지·식별·비용을 내는 서로 다른 배치 그룹만 ${sameFGroups.length}개 표시합니다.${collapsedUnqualified?` 목표 미달 동일 성능·비용 중복 ${collapsedUnqualified}개는 접었습니다.`:''}</p></div></div>
  <div id="hammingInsight">${LiveHamming.panel(run,problem,selectedId)}</div>
  <div class="lineageStrip"><span><b>${rawReplay?'저장값 재계산 일치':'저장값 재계산 미확인'}</b></span><span>실행 <b>${run.id.slice(0,8)}</b></span><span>세대 <b>${run.snapshot.generation}</b></span><span>${diagnostic?'현재 비지배':'누적 경험적 비지배'} <b>${frontPoints.length}</b></span><span>진단 범위 <b>${diagnostic?'현재 생존집단':'0세대부터 선택 세대까지'}</b></span></div>`;
  const explorer=document.getElementById('frontSolutionExplorer');explorer.onchange=()=>{if(explorer.value==='')return;const control=document.getElementById('solution');if(control){control.value=explorer.value;control.onchange();}};
  const mirror=document.getElementById('frontDiagnosticsMirror');if(mirror)mirror.onchange=()=>{const control=document.getElementById('diagnostics');if(!control)return;control.checked=mirror.checked;control.onchange();};
  const rerender=threshold=>{const target=document.getElementById('hammingInsight');if(!target)return;target.innerHTML=LiveHamming.panel(run,problem,selectedId,threshold);LiveHamming.bind(run,problem,selectedId,rerender);};LiveHamming.bind(run,problem,selectedId,rerender);
 }
 return {maskKey,uniquePoints,uniqueObjectives,bands,objectiveDisplayGroups,render};
})();
if(typeof module!=='undefined')module.exports=LiveFrontInsight;
