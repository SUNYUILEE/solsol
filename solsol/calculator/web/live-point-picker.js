'use strict';
// Screen-space picking only: never modify objectives, placements or projections.
const LivePointPicker=(()=>{
 const el=id=>document.getElementById(id);
 const key=run=>run?.snapshot&&!run.error&&run.state!=='failed'?run.id+':'+run.snapshot.generation:'';
 function nearby(nodes,x,y){return nodes.filter(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)&&Math.hypot(n.x-x,n.y-y)<=Math.max(12,n.radius+6)).sort((a,b)=>a.id-b.id);}
 let pending=null,revision=0,origin=null;
 function close(restore=true,resume=true){const d=el('pointPicker'),continueView=pending?.resume;pending=null;if(d?.open)d.close();if(restore&&origin?.isConnected)origin.focus({preventScroll:true});origin=null;if(resume)continueView?.();}
 function invalidate(){++revision;close(false,false);}
 function pick(id){
  const p=pending;
  const visible=new Set((p?.getRun()?.points||[]).map(x=>x.id));
  if(!p||p.revision!==revision||key(p.getRun())!==p.key||!p.ids.includes(id)||!visible.has(id)){close(false);return false;}
  close(false);p.select(id);return true;
 }
 function handle(event,getRun,select,pause){
  const target=event.target.closest?.('[data-id]'),run=getRun();if(!target||!key(run))return;
  const points=new Map(run.points.map(p=>[p.id,p]));
  const nodes=Array.from(el('scatter').querySelectorAll('[data-id]')).map(n=>{const r=n.getBoundingClientRect();return{id:+n.dataset.id,x:r.x+r.width/2,y:r.y+r.height/2,radius:Math.max(r.width,r.height)/2};}).filter(n=>points.has(n.id));
  const hits=nearby(nodes,event.clientX,event.clientY);
  if(hits.length<2){if(points.has(+target.dataset.id))select(+target.dataset.id);return;}
  close(false,false);const resume=pause();origin=target;
  pending={revision,key:key(run),getRun,select,resume,ids:hits.map(n=>n.id)};
  el('pointPickerContext').textContent=`${run.snapshot.generation}세대 · 실행 ${run.id}`;
  el('pointPickerDescription').textContent=`클릭한 화면 위치 주변에 ${hits.length}개 배치가 있습니다. 화면에서 가까워도 목적값이나 설치 위치는 다를 수 있습니다. 배치 ID를 골라 지도와 비용을 확인하세요. 선택 중에는 세대 표시를 고정하며 진행 중인 계산은 계속됩니다.`;
  el('pointPickerRows').innerHTML=hits.map(n=>{const p=points.get(n.id);return `<tr><td><button type="button" data-pick-id="${p.id}">배치 #${p.id} 선택</button></td><td>${(p.performance[0]*100).toFixed(3)}%</td><td>${(p.performance[1]*100).toFixed(3)}%</td><td>${p.cost}점</td><td>${p.sensor_counts[0]}대 / ${p.sensor_counts[1]}대</td><td>${p.qualified?'목표 통과':'목표 미달'}</td></tr>`;}).join('');
  el('pointPicker').showModal();el('pointPickerClose').focus();
 }
 function bind(){
  el('pointPickerClose').onclick=()=>close();
  el('pointPicker').addEventListener('cancel',e=>{e.preventDefault();close();});
  el('pointPickerRows').addEventListener('click',e=>{const b=e.target.closest?.('[data-pick-id]');if(b)pick(+b.dataset.pickId);});
 }
 return {nearby,handle,pick,invalidate,bind};
})();
if(typeof module!=='undefined')module.exports=LivePointPicker;
