'use strict';
// Display selection and diagnostics only; no optimizer genome is modified.
const LiveSelection=(()=>{
const rules=[
 {key:'cost',name:'최저비용 대표',why:'두 목표를 통과한 현재 비지배 배치 중 비용이 가장 작습니다.'},
 {key:'detection',name:'탐지 우선 대표',why:'현재 비지배 배치 중 탐지율이 가장 높습니다. 동률이면 더 저렴한 배치입니다.'},
 {key:'identification',name:'식별 우선 대표',why:'현재 비지배 배치 중 식별률이 가장 높습니다. 동률이면 더 저렴한 배치입니다.'},
 {key:'margin',name:'두 목표 여유 대표',why:'min(탐지율÷0.95, 식별률÷0.90)이 가장 큽니다. 작은 쪽의 목표 달성 여유를 높이고, 동률이면 비용을 줄이는 설명용 선택입니다.'}
];
const targets=()=>ModelDisplay.call('definition').targets;
const margin=p=>Math.min(...p.performance.map((v,i)=>v/targets()[i]));
function targetQualified(p){
 const values=p?.performance;
 return Boolean(Array.isArray(values)&&values.length>=2&&Number.isFinite(values[0])&&Number.isFinite(values[1])&&values.every((v,i)=>v>=targets()[i]-1e-10));
}
function inScope(points,scope='target_front'){
 const rows=Array.isArray(points)?points:[];
 return scope==='all_front'?rows.slice():scope==='target_front'?rows.filter(targetQualified):[];
}
function costOrdered(points){
 return (Array.isArray(points)?points:[]).slice().sort((a,b)=>a.cost-b.cost||b.performance[0]-a.performance[0]||b.performance[1]-a.performance[1]||a.id-b.id);
}
function representatives(points,front){const ids=new Set(front),pool=points.filter(p=>targetQualified(p)&&ids.has(p.id));return rules.map(rule=>{const score=p=>rule.key==='cost'?-p.cost:rule.key==='detection'?p.performance[0]:rule.key==='identification'?p.performance[1]:margin(p);const sorted=pool.slice().sort((a,b)=>score(b)-score(a)||a.cost-b.cost||a.id-b.id);return {...rule,point:sorted[0]||null};});}
function zones(problem,contract){const z=ModelDisplay.call('zones',problem,contract);return {...z,detection:new Set(z.detection),identification:new Set(z.identification)};}
function contributions(problem,point,contract='binary_coverage_v1'){return ModelDisplay.call('contributions',problem,point,contract);}
function oneDeleteMinimal(problem,point,contract){return contributions(problem,point,contract).every(r=>!r.removableWithoutLoss);}
function performance(problem,mask,contract='binary_coverage_v1'){return ModelDisplay.call('performance',problem,mask,contract);}
return{representatives,contributions,oneDeleteMinimal,performance,zones,margin,targetQualified,inScope,costOrdered};})();
if(typeof module!=='undefined')module.exports=LiveSelection;
