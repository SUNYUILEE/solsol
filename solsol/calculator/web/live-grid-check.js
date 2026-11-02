'use strict';
// Separate fixed-placement sampling check; never an optimizer input or replacement.
const LiveGridCheck=(()=>{
 let current=null,key=null,serial=0,result=null,qualityGate={integrity:'PENDING'};
 const el=id=>document.getElementById(id);
 function contains(...a){return ModelDisplay.call('contains',...a);}
 function grid(...a){return ModelDisplay.call('grid',...a);}
 function evaluate(...a){return ModelDisplay.call('grid_evaluate',...a);}
 function inspect(...a){return ModelDisplay.call('grid_inspect',...a);}
 function renderMap(){
  const box=el('gridCheckMap');box.innerHTML=result&&el('gridCheckMapDetails').open?LiveCore.map({...current.problem,demand:result.points},current.point,{layer:el('gridCheckLayer').value,candidates:false,defense:true,demand:true}):'';
  if(typeof LiveGridView!=='undefined')LiveGridView.refresh();
 }
 function render(){
  const r=result;el('gridCheckStatus').textContent=`${current.generation}세대 · 배치 #${current.point.id} · ${r.changed?'평가 간격에 따라 성능 기준 판정이 달라졌습니다.':r.fine.pass.every(Boolean)?'두 간격에서 성능 기준을 충족했습니다.':'250m 검산에서 성능 기준에 미달합니다.'} · 실행 ${current.job.id}`;
  el('gridCheckStatus').className=r.changed||!r.fine.pass.every(Boolean)?'gridCheckStatus gridCheckWarning':'gridCheckStatus';
  el('gridCheckRows').innerHTML=r.base.performance.map((_,i)=>`<tr><th scope="row">${i?'식별':'탐지'} · 목표 ${i?'90':'95'}%</th><td>${(r.base.performance[i]*100).toFixed(2)}%<small>${r.base.hit[i]} / ${r.base.n}점 · ${r.base.pass[i]?'도달':'미달'}</small></td><td>${(r.fine.performance[i]*100).toFixed(2)}%<small>${r.fine.hit[i]} / ${r.fine.n}점 · ${r.fine.pass[i]?'도달':'미달'}</small></td><td>${r.delta[i]>=0?'+':''}${r.delta[i].toFixed(2)}%p</td><td>${Math.max(0,r.fine.required[i]-r.fine.hit[i])}점<small>목표 필요 ${r.fine.required[i]}점</small></td></tr>`).join('');
  el('gridCheckCost').textContent=`같은 설치 위치 · Radar ${r.counts[0]}대 / EO/IR ${r.counts[1]}대 · 비용 ${r.cost}점으로 동일`;
  el('gridCheckOutput').hidden=false;el('gridCheckMapDetails').hidden=false;if(typeof LiveGridView!=='undefined')LiveGridView.ready(current,r);renderMap();
 }
 function update(problem,point,job,generation){
  const next=point?JSON.stringify([job.id,generation,problem.problem_sha256,point.id,point.mask,point.performance,point.cost,point.sensor_counts]):null;
  current=point?{problem,point,job,generation}:null;
  if(next===key)return;key=next;serial++;result=null;qualityGate={integrity:'PENDING'};el('gridCheckButton').disabled=true;el('gridCheckOutput').hidden=true;el('gridCheckMapDetails').hidden=true;el('gridCheckMap').innerHTML='';el('gridCheckRows').innerHTML='';
  if(typeof LiveGridView!=='undefined')LiveGridView.clear();
  el('gridCheckStatus').className='gridCheckStatus';el('gridCheckStatus').textContent=point?`배치 #${point.id} · 계산 일치 확인 후 250m 표본 검산을 사용할 수 있습니다.`:'목록이나 그래프에서 배치를 선택하세요.';
 }
 function applies(gate){return !!current&&(!gate.run_id||gate.run_id===current.job.id)&&(!Number.isInteger(gate.generation)||gate.generation===current.generation)&&(!Number.isInteger(gate.solution_id)||gate.solution_id===current.point.id);}
 function setQualityGate(gate){
  qualityGate=gate||{integrity:'PENDING'};const allowed=applies(qualityGate)&&qualityGate.integrity==='PASS';
  el('gridCheckButton').disabled=!allowed;
  if(!allowed){serial++;result=null;el('gridCheckOutput').hidden=true;el('gridCheckMapDetails').hidden=true;el('gridCheckMap').innerHTML='';el('gridCheckRows').innerHTML='';if(typeof LiveGridView!=='undefined')LiveGridView.clear();}
  if(current)el('gridCheckStatus').textContent=qualityGate.integrity==='PASS'?`배치 #${current.point.id} · 500m 계산 결과를 250m 표본으로 확인할 수 있습니다.`:qualityGate.integrity==='FAIL'?'계산 일치 실패로 추가 검산을 중단했습니다. 먼저 해품질 진단에서 불일치를 확인하세요.':'계산 일치 검사를 기다리고 있습니다.';
 }
 function init(){
  if(typeof LiveGridView!=='undefined')LiveGridView.init();
  el('gridCheckButton').onclick=()=>{if(!current)return;LiveReplay.stop();const ticket=++serial,snapshot=structuredClone(current);el('gridCheckButton').disabled=true;el('gridCheckStatus').textContent=`배치 #${snapshot.point.id} · 평가 간격 검산 중…`;
   setTimeout(()=>{try{const checked=inspect(snapshot.problem,snapshot.point);if(ticket!==serial)return;current=snapshot;result=checked;render();}catch(e){if(ticket!==serial)return;result=null;el('gridCheckOutput').hidden=true;el('gridCheckMapDetails').hidden=true;el('gridCheckMap').innerHTML='';if(typeof LiveGridView!=='undefined')LiveGridView.clear();el('gridCheckStatus').textContent='검산 실패: '+e.message;}finally{if(ticket===serial)el('gridCheckButton').disabled=false;}},0);
  };
  el('gridCheckMapDetails').addEventListener('toggle',renderMap);el('gridCheckLayer').addEventListener('change',renderMap);
 }
 return{contains,grid,evaluate,inspect,update,init,setQualityGate};
})();
if(typeof module!=='undefined')module.exports=LiveGridCheck;
