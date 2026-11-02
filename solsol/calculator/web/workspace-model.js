'use strict';
// Model-neutral scenario/row boundary. The workbench, lifecycle and analysis
// owners remain in their preserved common modules.
const WorkspaceModel=(()=>{
 const EO='NEUTRAL_LEGACY_A',RF='NEUTRAL_LEGACY_B';
 const commonKeys=['map_km','shape','area_factor','candidate_count','site_seed'];let schemas={};
 function label(cid){return cid;}
 function create(defaults,unused,cid='ABC_COVERAGE_RESOURCE_V1'){
  return {schema:'SOLSOL_SHARED_DRAFT_V4',name:'새 센서 배치 연구',sensor:cid,
   common:Object.fromEntries(commonKeys.map(k=>[k,defaults[k]])),sensors:{[cid]:structuredClone(defaults)},
   optimizer:{algorithm:'NSGA-III',generations:10,population:36,seed:1,h:3,initializer:'random'}};
 }
 function validate(d){if(d?.schema!=='SOLSOL_SHARED_DRAFT_V4'||!d.sensors?.[d.sensor]||!d.common||!d.optimizer)throw Error('중립 시나리오 계약을 확인하세요.');return structuredClone(d);}
 function eoirConfig(d){return {...structuredClone(d.sensors[d.sensor]),...structuredClone(d.common)};}
 function radii(d){const c=d.sensors[d.sensor];return Object.keys(c).filter(k=>k.endsWith('_radius')).map(k=>c[k]);}
 function preview(d){return {experiment_contract_id:d.sensor,common:structuredClone(d.common),radii_m:radii(d)};}
 function setModelSchemas(v){schemas=structuredClone(v);}
 function rfPayload(d){return {common:structuredClone(d.common),parameters:structuredClone(d.sensors[d.sensor])};}
 function rowX(r){if(!Array.isArray(r.X))throw Error('명시적인 후보지×센서 배치가 필요합니다.');return r.X;}
 function cluster(rows){const groups=[];for(const r of rows){const bits=rowX(r).flat(),g=groups.find(g=>g.every(q=>{const other=rowX(q).flat();return other.length===bits.length&&bits.filter((b,i)=>b!==other[i]).length<3;}));if(g)g.push(r);else groups.push([r]);}return groups;}
 function normalize(p,cid,id){if(p.experiment_contract_id!==cid||p.run_id!==id||!p.registry||!p.metadata)throw Error('실행 계약과 메타데이터가 일치하지 않습니다.');return {...p,rows:p.archive||[],initialRows:p.initial_archive||[],latest:p.checkpoints.length-1,seconds:p.elapsed_seconds,history:p.checkpoints,qualityLabels:p.registry.objective_order.slice(0,2).map(k=>p.metadata.metrics.find(m=>m.id===k).name)};}
 const quality=r=>Object.values(r.named_metrics||{}).slice(0,2);
 return {EO,RF,label,commonKeys,create,validate,eoirConfig,radii,preview,rfPayload,rowX,cluster,normalize,quality,setModelSchemas};
})();
if(typeof module!=='undefined')module.exports=WorkspaceModel;
