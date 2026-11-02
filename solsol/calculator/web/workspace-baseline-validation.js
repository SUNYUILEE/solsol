'use strict';
// Extracted unchanged from the preserved baseline live.js validateView.
function validateView(d){
 const array=Array.isArray;
 const base=d&&typeof d.id==='string'&&d.config&&Number.isInteger(d.config.generations)&&d.problem&&array(d.problem.sites)&&array(d.problem.demand)&&array(d.points)&&array(d.current_population_points)&&array(d.history);
 const s=d?.snapshot;
 const frame=s===null||(s&&Number.isInteger(s.generation)&&Number.isFinite(s.evaluations)&&array(s.front_ids)&&array(s.population_ids)&&array(s.archive_ids));
  const contract=d?.config?.objective_contract||'binary_coverage_v1';
  const v6=contract==='full_area_tradeoff_v6'||contract==='layered_mission_v7',gMinimum=v6?0:2;
  const points=base&&d.points.every(p=>p&&Number.isInteger(p.id)&&array(p.mask)&&p.mask.length===d.problem.sites.length&&p.mask.every(v=>Number.isInteger(v)&&v>=0&&v<=3)&&array(p.performance)&&p.performance.length===2&&p.performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)&&(contract==='binary_coverage_v1'||v6||(array(p.objective_performance)&&p.objective_performance.length===2&&p.objective_performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)))&&array(p.F)&&p.F.length===3&&p.F.every(Number.isFinite)&&array(p.G)&&p.G.length>=gMinimum&&p.G.every(Number.isFinite)&&Number.isFinite(p.cost)&&array(p.sensor_counts)&&p.sensor_counts.length===2);
  const pointShape=p=>p&&Number.isInteger(p.id)&&array(p.mask)&&p.mask.length===d.problem.sites.length&&p.mask.every(v=>Number.isInteger(v)&&v>=0&&v<=3)&&array(p.performance)&&p.performance.length===2&&p.performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)&&(contract==='binary_coverage_v1'||v6||(array(p.objective_performance)&&p.objective_performance.length===2&&p.objective_performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)))&&array(p.F)&&p.F.length===3&&p.F.every(Number.isFinite)&&array(p.G)&&p.G.length>=gMinimum&&p.G.every(Number.isFinite)&&Number.isFinite(p.cost)&&array(p.sensor_counts)&&p.sensor_counts.length===2;
  const currentOk=base&&d.current_population_points.every(pointShape);
  const ids=points?d.points.map(p=>p.id):[],currentIds=base?d.current_population_points.map(p=>p.id):[],uniqueIds=new Set(ids),population=new Set(s?.population_ids||[]),archive=new Set(s?.archive_ids||[]),front=new Set(s?.front_ids||[]),uniqueMasks=new Set(base?d.points.map(p=>p.mask.join(',')):[]);
  const complete=!s||(uniqueIds.size===ids.length&&uniqueMasks.size===ids.length&&ids.every(id=>archive.has(id))&&[...archive].every(id=>uniqueIds.has(id))&&currentIds.length===population.size&&new Set(currentIds).size===currentIds.length&&currentIds.every(id=>population.has(id))&&[...population].every(id=>currentIds.includes(id))&&[...front].every(id=>population.has(id))&&(v6||d.points.every(p=>p.qualified)));
  const numeric=points&&currentOk&&[...d.points,...d.current_population_points].every(p=>{const q=contract==='max_margin_quality_v3'?p.objective_performance:p.performance,targetRelation=v6?true:Math.abs(.95-p.performance[0]-p.G[0])<1e-12&&Math.abs(.90-p.performance[1]-p.G[1])<1e-12,qualification=v6?p.performance[0]>=.95-1e-10&&p.performance[1]>=.90-1e-10:p.G.every(v=>v<=1e-10);return Math.abs((1-q[0])-p.F[0])<1e-12&&Math.abs((1-q[1])-p.F[1])<1e-12&&targetRelation&&Math.abs(p.cost/800-p.F[2])<1e-12&&p.qualified===qualification;});
  if(!base||!frame||!points||!complete||!numeric)throw Error('배치 응답에 필요한 자료 또는 ID·목적값·제약·세대 연결이 완전하지 않습니다. 기존 지도와 선택을 유지합니다.');
}
if(typeof module!=='undefined')module.exports=validateView;
if(typeof window!=='undefined')window.validateBaselineView=validateView;

