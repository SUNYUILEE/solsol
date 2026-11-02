'use strict';
// Derived, post-hoc layout analysis. This module never changes F/G or the MOEA archive.
const LiveHamming=(()=>{
 let activeThreshold=6;
 const distance=(a,b)=>a.reduce((sum,v,i)=>sum+(((v^b[i])&1)?1:0)+(((v^b[i])&2)?1:0),0);
 const signature=c=>c.map(p=>p.id).sort((a,b)=>a-b).join(',');
 function diameter(a,b){let d=0;for(const x of a)for(const y of b)d=Math.max(d,distance(x.mask,y.mask));return d;}
 function cluster(points,threshold=6){
  let groups=points.map(p=>[p]);
  while(true){
   let best=null;
   for(let i=0;i<groups.length;i++)for(let j=i+1;j<groups.length;j++){
    const d=diameter(groups[i],groups[j]);if(d>=threshold)continue;
    const key=[d,signature(groups[i])+'|'+signature(groups[j])];
    if(!best||key[0]<best.key[0]||(key[0]===best.key[0]&&key[1]<best.key[1]))best={i,j,key};
   }
   if(!best)break;
   groups[best.i]=groups[best.i].concat(groups[best.j]).sort((a,b)=>a.id-b.id);groups.splice(best.j,1);
  }
  return groups.sort((a,b)=>Math.min(...a.map(x=>x.cost))-Math.min(...b.map(x=>x.cost))||signature(a).localeCompare(signature(b)));
 }
 function medoid(group){return group.slice().sort((a,b)=>{
  const da=group.reduce((s,x)=>s+distance(a.mask,x.mask),0),db=group.reduce((s,x)=>s+distance(b.mask,x.mask),0);
  return da-db||a.id-b.id;
 })[0];}
 function representative(group){
  const central=p=>group.reduce((s,x)=>s+distance(p.mask,x.mask),0);
  return group.slice().sort((a,b)=>a.cost-b.cost||LiveSelection.margin(b)-LiveSelection.margin(a)||central(a)-central(b)||a.id-b.id)[0]||medoid(group);
 }
 function qualifiedPool(run,problem){
  const unique=LiveFrontInsight.uniquePoints(run?.points||[]),contract=run?.config?.objective_contract||'binary_coverage_v1';
  return unique.filter(p=>p.qualified&&LiveSelection.oneDeleteMinimal(problem,p,contract));
 }
 function panel(run,problem,selectedId,threshold=activeThreshold){
  activeThreshold=threshold;
  if(run?.config?.objective_contract==='layered_mission_v7')return '<div class="hammingEmpty">V7 배치군은 아래 <b>신뢰성 근거 계산</b>에서 누적 해집합·one-delete·250m 재검산을 먼저 마친 뒤 Hamming 거리로 표시합니다.</div>';
  if(run?.config?.objective_contract!=='full_area_tradeoff_v6')return '<div class="hammingEmpty">이 목적함수 계약에는 배치구조 사후 분류가 연결되지 않았습니다.</div>';
  const archiveUnique=LiveFrontInsight.uniquePoints(run?.points||[]),qualified=archiveUnique.filter(p=>p.qualified),pool=qualifiedPool(run,problem),groups=cluster(pool,threshold);
  if(!pool.length)return `<div class="hammingPanel"><div class="hammingHead"><div><span>배치구조 사후 분석</span><h4>해밍거리 군집</h4></div><b>적용 대기</b></div><p>누적 경험적 비지배 해 중 탐지 95%·식별 90%와 one-delete 최소성을 함께 만족한 배치가 없습니다. 현재 세대의 목표통과 해를 억지로 대표안으로 승격하지 않습니다.</p><small>누적 고유 X ${archiveUnique.length}개 · 목표통과 ${qualified.length}개 · one-delete 통과 ${pool.length}개</small></div>`;
  const cards=groups.map((g,i)=>{const rep=representative(g),dia=diameter(g,g);return `<button type="button" class="hammingCard${g.some(p=>p.duplicateIds?.includes(selectedId)||p.id===selectedId)?' selected':''}" data-solution="${rep.id}"><span>배치군 ${i+1} · ${g.length}개 해</span><strong>#${rep.id} · ${rep.cost}점</strong><small>탐지 ${(rep.performance[0]*100).toFixed(1)}% · 식별 ${(rep.performance[1]*100).toFixed(1)}% · 군집 직경 ${dia}</small></button>`;}).join('');
  return `<div class="hammingPanel"><div class="hammingHead"><div><span>배치구조 사후 분석</span><h4>해밍거리 군집과 실제 대표 배치</h4></div><label>유사 기준<select id="hammingThreshold"><option value="4"${threshold===4?' selected':''}>dH &lt; 4</option><option value="6"${threshold===6?' selected':''}>dH &lt; 6</option><option value="8"${threshold===8?' selected':''}>dH &lt; 8</option></select></label></div><p>목적함수나 NSGA-III 생존선택에 해밍거리를 넣지 않습니다. 누적 비지배·목표통과·one-delete 최소성 검사를 마친 배치만 구조가 비슷한 군으로 묶고, 각 군의 실제 원시 배치 중 저비용 우선 대표를 지도에서 선택합니다.</p><div class="hammingMetrics"><span>누적 고유 X <b>${archiveUnique.length}</b></span><span>목표통과 <b>${qualified.length}</b></span><span>one-delete 통과 <b>${pool.length}</b></span><span>구조 군집 <b>${groups.length}</b></span></div><div class="hammingCards">${cards}</div><small>dH=2는 같은 센서 한 대의 위치 이동 또는 한 후보지의 Radar↔EO/IR 교체에 해당합니다. 이 결과는 사후 해석이며 참 Pareto 전선이나 전역 최적성을 인증하지 않습니다.</small></div>`;
 }
 function bind(run,problem,selectedId,rerender){
  const select=document.getElementById('hammingThreshold');if(select)select.onchange=()=>{activeThreshold=+select.value;rerender(activeThreshold);};
  document.querySelectorAll('.hammingCard[data-solution]').forEach(button=>button.onclick=()=>{const control=document.getElementById('solution');if(control){control.value=button.dataset.solution;control.onchange();}});
 }
 return{distance,cluster,medoid,representative,qualifiedPool,panel,bind,threshold:()=>activeThreshold};
})();
if(typeof module!=='undefined')module.exports=LiveHamming;
