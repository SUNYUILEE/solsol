'use strict';
// Read-only explanations share the existing whole-population cost model.
const LiveInitialContext=(()=>{
 const same=(a,b)=>Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>v===b[i]);
 const number=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
 function sourceIssue(zero,point){
  const info=zero?.initialization;if(!point||!info)return '';
  const rows=(info.sources||[]).filter(s=>s.index===point.id);
  if(rows.length>1)return '초기 배치 출처가 중복되어 생성 방법을 확정할 수 없습니다.';
  if(rows.length===1&&(!['milp','greedy'].includes(rows[0].method)||!['original','perturbed'].includes(rows[0].kind)))return '초기 배치의 생성 방법 또는 원본·변형 구분이 올바르게 기록되지 않았습니다.';
  if(!rows.length&&info.method!=='random'&&(!Number.isInteger(info.seed_count)||point.id<info.seed_count))return '준비 배치의 생성 출처가 누락되었거나 확인되지 않습니다. 무작위 배치로 단정하지 않습니다.';
  return '';
 }
 function provenance(zero,point){
  if(!point)return '초기 배치를 선택하면 생성 방법을 표시합니다.';
  const issue=sourceIssue(zero,point);if(issue)return issue;
  const info=zero?.initialization,s=info?.sources?.find(s=>s.index===point.id);
  if(!s)return info&&(info.method==='random'||Array.isArray(info.sources))?'무작위로 만든 초기 배치입니다. MILP·Greedy 준비 원본이 아닙니다.':'이 배치의 생성 출처는 저장되어 있지 않습니다.';
  const name=s.method==='milp'?'MILP':s.method==='greedy'?'Greedy':'준비';
  if(s.kind!=='original')return `${name} 원본을 변형한 배치입니다. 원본의 최소비용 판정을 이 배치에 적용하지 않습니다.`;
  const rows=(info.targets||[]).filter(r=>same(r.targets,s.targets)&&same(r.seed?.mask,point.mask)&&r.seed?.cost===point.cost&&r.upper_bound===point.cost);
  if(rows.length!==1)return `${name} 준비 원본 · 이 배치와 일치하는 계산 근거를 확인할 수 없습니다.`;
  const r=rows[0],target=Array.isArray(s.targets)&&s.targets.every(number)?s.targets.map(v=>(v*100).toFixed(0)+'%').join(' / '):'미기록';
  const prefix=`${name} 준비 목표: 탐지 / 식별 ${target}. `;
  if(s.method!=='milp')return prefix+'Greedy로 찾은 배치이며, 최저비용이 보장되지는 않습니다.';
  if(r.milp_status===0&&r.cost_optimal_certified===true&&number(r.lower_bound)&&r.lower_bound===point.cost)return prefix+`이 준비 목표에서 하한과 배치 비용이 ${point.cost}점으로 일치했습니다. 전체 파레토 해집합의 정답이라는 뜻은 아닙니다.`;
  if(r.milp_status===1)return prefix+`계산 제한에 도달했습니다. 확보한 배치 ${point.cost}점${number(r.lower_bound)?', 수학적 하한 '+r.lower_bound+'점':''}이며 최소비용 확정은 아닙니다.`;
  return prefix+'제한된 계산에서 확보한 배치입니다. 최소비용 확정 근거는 없습니다.';
 }
 function model(zero,run,initialId,currentId){
  const m=LiveProgress.model(zero,run);if(!m)return null;
  return {...m,initialPoint:m.start?zero.points.find(p=>p.id===initialId)||null:null,currentPoint:run.points?.find(p=>p.id===currentId)||null,
   origin:m.start?provenance(zero,zero.points.find(p=>p.id===initialId)): '같은 실행의 초기 집단 자료를 확인할 수 없습니다.'};
 }
 function clear(){for(const id of ['initialContext','currentContext','initialCostSummary','currentCostSummary']){const h=document.getElementById(id);if(h)h.replaceChildren();}}
 function panel(label,pop,point,note){
  return `<div class="contextCosts"><div><span>이 지도에서 선택한 배치</span><strong>${point&&number(point.cost)?point.cost+'점':'미선택'}</strong></div><div><span>${label} · 목표 통과 최저비용</span><strong>${pop?(pop.cost===null?'통과 배치 없음':pop.cost+'점'):'자료 없음'}</strong></div></div><p>${pop?'목표 통과 '+pop.qualified+' / 전체 '+pop.total+'개 · 최저비용 고유 X '+pop.ties.length+'개'+(pop.rawTieRows>pop.ties.length?' (원시 '+pop.rawTieRows+'행)':''):'집단 비교 자료 없음'}</p><p class="contextNote">${note}</p>`;
 }
 function render(zero,run,initialId,currentId){
  const left=document.getElementById('initialContext'),right=document.getElementById('currentContext');if(!left||!right)return;
  const m=model(zero,run,initialId,currentId);if(!m){clear();return;}
  for(const [id,p,s] of [['initialCostSummary',m.initialPoint,m.start],['currentCostSummary',m.currentPoint,m.current]]){const h=document.getElementById(id);if(h)h.textContent=`이 지도 ${p&&number(p.cost)?p.cost+'점':'미선택'} · 집단 내 목표 통과 최저 ${s?(s.cost===null?'없음':s.cost+'점'):'자료 없음'}`;}
  left.innerHTML=panel('0세대 전체',m.start,m.initialPoint,m.origin);
  right.innerHTML=panel(m.generation+'세대 전체',m.current,m.currentPoint,LiveProgress.story(m)+(m.fixedCost?' 보유 장비 전부 사용 조건에서는 비용이 고정됩니다.':'')+' 배치 선택은 위 고유 배치 해 탐색에서 수행합니다.');
 }
 return {model,provenance,sourceIssue,render,clear};
})();
