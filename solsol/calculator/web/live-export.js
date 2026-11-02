'use strict';
// Derived selection receipt. The server's original run archive is retained separately.
const LiveExport=(()=>{
 const clone=v=>JSON.parse(JSON.stringify(v));
 function payload(problem,run,point,view={}){
  if(!run?.id||!run.snapshot||run.state==='failed'||run.error||!point)throw Error('정상 실행에서 배치를 먼저 선택하세요.');
  if(view.selection_mode!=='manual')throw Error('사용자가 직접 선택한 배치만 저장할 수 있습니다.');
  const original=run.points?.find(p=>p.id===point.id),archive=new Set(run.snapshot.archive_ids||[]),population=new Set(run.snapshot.population_ids||[]);
  if(!Number.isInteger(point.id)||(!archive.has(point.id)&&!population.has(point.id))||!original||JSON.stringify(original)!==JSON.stringify(point))throw Error('선택한 배치와 이 실행의 표시 자료가 일치하지 않습니다.');
  if(JSON.stringify(problem)!==JSON.stringify(run.problem))throw Error('배치 지도와 실행의 문제 조건이 다릅니다.');
  if(point.mask.length!==problem.sites.length||point.mask.some(m=>!Number.isInteger(m)||m<0||m>3))throw Error('설치 구성을 확인할 수 없습니다.');
  const installations=[];point.mask.forEach((m,i)=>[1,2].forEach((bit,t)=>{if(m&bit)installations.push({candidate_id:i+1,sensor:t?'EO/IR':'Radar',xy_metres:problem.sites[i],radius_metres:problem.radii[t]});}));
  const q=view.quality_gate;
  return clone({schema:'CUAS_SELECTED_PLACEMENT_V1',created_at:new Date().toISOString(),run_id:run.id,generation:run.snapshot.generation,evolution_nfe:run.snapshot.evaluations,solution_id:point.id,run_state:run.state,persistence:run.persistence,
   source:{snapshot_url:'/api/jobs/'+run.id+'?generation='+run.snapshot.generation,raw_run_url:'/api/jobs/'+run.id+'/download',problem_sha256:problem.problem_sha256,audit:run.audit,scope:archive.has(point.id)?'Selected cumulative feasible empirical-nondominated observation through this generation; derived view, not the raw final population or a global optimum certificate.':'Selected current-generation survivor; derived export, not a global optimum certificate.'},
   config:run.config,problem,point,installations,view:{chart_type:view.chart_type,metric:view.metric,angle:view.angle,layer:view.layer,selection_mode:view.selection_mode},
   quality_evidence:q?{integrity:q.integrity,constraint:q.constraint,search:q.search,message:q.message,checked_run_id:q.run_id,checked_generation:q.generation,checked_solution_id:q.solution_id}:undefined,
   certification:{global_optimality:'NOT_CERTIFIED',search_completion:'NOT_CERTIFIED',exact_full_front:'NOT_COMPUTED',product_release:'NOT_CERTIFIED'},
   interpretation:ModelDisplay.call('export_interpretation',problem,run.config?.objective_contract||'binary_coverage_v1')});
 }
 async function envelope(data){
  const text=JSON.stringify(data),hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return {schema:'CUAS_SELECTION_DOWNLOAD_V1',payload:data,integrity:{algorithm:'SHA-256',sha256:Array.from(new Uint8Array(hash),x=>x.toString(16).padStart(2,'0')).join(''),serialized_payload:text,instructions:'Hash UTF-8 serialized_payload and require its parsed JSON to equal payload. Export integrity only; not scientific optimality.'}};
 }
 let current=null,key='',revision=0,qualityGate={integrity:'PENDING',constraint:'PENDING',search:'NOT_CHECKED'};
 function applies(gate){
  if(!current)return false;
  return (!gate.run_id||gate.run_id===current.run.id)&&(!Number.isInteger(gate.generation)||gate.generation===current.run.snapshot.generation)&&(!Number.isInteger(gate.solution_id)||gate.solution_id===current.point.id);
 }
 function usable(){return !!current&&applies(qualityGate)&&qualityGate.integrity==='PASS'&&qualityGate.constraint==='PASS';}
 function refresh(){
  const b=document.getElementById('exportSelection');if(b)b.disabled=!usable();
  const label=document.getElementById('selectionExportInfo');
  if(label)label.textContent=!current?'배치를 선택하면 해당 위치·성능·비용과 실행 조건을 저장할 수 있습니다.':qualityGate.integrity==='PENDING'?'선택 배치의 계산 일치를 확인한 뒤 저장할 수 있습니다.':qualityGate.integrity!=='PASS'?'계산 일치 검사를 통과하지 못해 이 배치는 저장할 수 없습니다.':qualityGate.constraint!=='PASS'?'목표·자원 제약 미달 배치는 진단만 가능하며 결과 배치로 저장하지 않습니다.':`메인 지도 선택 · ${current.run.snapshot.generation}세대 · 배치 #${current.point.id} · 실행 ${current.run.id}`;
 }
 function revoke(){const link=document.getElementById('selectionDownload');if(link){link.hidden=true;link.removeAttribute?.('href');}const status=document.getElementById('selectionExportStatus');if(status)status.textContent='';}
 function setQualityGate(gate){qualityGate=gate||{integrity:'PENDING',constraint:'PENDING',search:'NOT_CHECKED'};if(!usable())revoke();refresh();}
 function update(problem,run,point,view){
  const manual=view?.selection_mode==='manual';
  const next=manual&&run&&point&&run.snapshot&&run.state!=='failed'&&!run.error?run.id+':'+run.snapshot.generation+':'+point.id:'';
  if(next!==key){key=next;++revision;qualityGate={integrity:'PENDING',constraint:'PENDING',search:'NOT_CHECKED'};revoke();}
  current=next?{problem,run,point,view}:null;
  refresh();
 }
 function bind(){
  document.getElementById('exportSelection').onclick=async()=>{
   const button=document.getElementById('exportSelection'),status=document.getElementById('selectionExportStatus'),link=document.getElementById('selectionDownload'),ticket=revision;
   try{
    if(!usable())throw Error('계산 일치와 제약 통과를 확인한 배치를 선택하세요.');
    const data=payload(current.problem,current.run,current.point,{...current.view,quality_gate:qualityGate});button.disabled=true;
    const file=await envelope(data);if(ticket!==revision){status.textContent='선택이 바뀌어 저장 준비를 취소했습니다. 현재 배치에서 다시 저장하세요.';return null;}
    link.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(file,null,2));link.download=`cuas-${data.run_id}-g${data.generation}-p${data.solution_id}.json`;link.hidden=false;
    status.textContent=`저장 준비됨 · ${data.generation}세대 · 배치 #${data.solution_id} · 비용 ${data.point.cost}점. JSON 파일을 내려받으세요.`;return file;
   }catch(e){status.textContent=e.message;link.hidden=true;link.removeAttribute?.('href');return null;}
   finally{button.disabled=!usable();}
  };
 }
 return {payload,envelope,update,bind,setQualityGate};
})();
if(typeof module!=='undefined')module.exports=LiveExport;
