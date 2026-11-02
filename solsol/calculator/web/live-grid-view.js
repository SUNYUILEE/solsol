'use strict';
// Presentation-only viewport. The original evaluator and selected point stay untouched.
const LiveGridView=(()=>{
 const el=id=>document.getElementById(id),modes=['fit','width','1.5','2'];let available=false,returnTarget='map';
 function size(width,height,mode){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)return{width:0,height:0};
  const w=mode==='width'?width:mode==='1.5'||mode==='2'?width*Number(mode):Math.min(width,height*930/945);
  return{width:w,height:w*945/930};
 }
 function refresh(center=false){
  const box=el('gridCheckMap'),viewport=el('gridMapViewport');if(!available||!box.querySelector('svg'))return;
  const s=size(viewport.clientWidth,viewport.clientHeight,el('gridMapZoom').value);if(!s.width)return;
  box.style.width=s.width+'px';box.style.height=s.height+'px';
  if(center){viewport.scrollLeft=Math.max(0,(s.width-viewport.clientWidth)/2);viewport.scrollTop=Math.max(0,(s.height-viewport.clientHeight)/2);}
 }
 function close(){if(el('gridMapDialog').open)el('gridMapDialog').close();}
 function focusTable(){el('gridCheckTitle').tabIndex=-1;el('gridCheckTitle').focus();el('gridCheckTitle').scrollIntoView({block:'start',behavior:'instant'});}
 function restore(){if(el('gridMapDialog').open)return;el('gridCheckMapDetails').appendChild(el('gridMapWorkspace'));el('gridMapOpen').hidden=false;el('gridMapZoom').value='fit';refresh(true);if(returnTarget==='table'||!available)focusTable();else el('gridMapOpen').focus();}
 function clear(){available=false;close();el('gridMapIdentity').textContent='';el('gridMapOpen').disabled=true;el('gridMapZoom').value='fit';el('gridCheckMap').style.width='';el('gridCheckMap').style.height='';}
 function ready(current,r){
  available=true;el('gridMapOpen').disabled=false;
  el('gridMapIdentity').textContent=`${current.generation}세대 · 배치 #${current.point.id} · 비용 ${r.cost}점 · 250m 탐지 ${(100*r.fine.performance[0]).toFixed(2)}% / 식별 ${(100*r.fine.performance[1]).toFixed(2)}% · ${r.fine.pass.every(Boolean)?'성능 기준 충족':'성능 기준 미달'} · 실행 ${current.job.id}`;
 }
 function open(){if(!available||el('gridMapDialog').open)return;returnTarget='map';LiveReplay.stop();el('gridMapHost').appendChild(el('gridMapWorkspace'));el('gridMapOpen').hidden=true;el('gridMapZoom').value='fit';el('gridMapDialog').showModal();refresh(true);el('gridMapViewport').focus();}
 function toTable(){returnTarget='table';if(el('gridMapDialog').open)close();else focusTable();}
 function keydown(e){
  const v=el('gridMapViewport');if(e.target!==v||document.activeElement!==v||!available||e.altKey||e.ctrlKey||e.metaKey)return;
  const arrows={ArrowLeft:[-80,0],ArrowRight:[80,0],ArrowUp:[0,-80],ArrowDown:[0,80]};
  if(arrows[e.key]){e.preventDefault();v.scrollLeft=Math.max(0,Math.min(v.scrollWidth-v.clientWidth,v.scrollLeft+arrows[e.key][0]));v.scrollTop=Math.max(0,Math.min(v.scrollHeight-v.clientHeight,v.scrollTop+arrows[e.key][1]));return;}
  if(['+','=','-','Home'].includes(e.key)){e.preventDefault();const i=Math.max(0,modes.indexOf(el('gridMapZoom').value));el('gridMapZoom').value=e.key==='Home'?'fit':modes[Math.max(0,Math.min(modes.length-1,i+(e.key==='-'?-1:1)))];refresh(true);}
 }
 function init(){
  el('gridMapOpen').onclick=open;el('gridMapClose').onclick=close;el('gridMapTable').onclick=toTable;
  el('gridMapZoom').addEventListener('change',()=>refresh(true));el('gridMapViewport').addEventListener('keydown',keydown);
  el('gridMapDialog').addEventListener('close',restore);
  el('gridMapDialog').addEventListener('cancel',e=>{e.preventDefault();close();});
  el('gridMapDialog').addEventListener('keydown',e=>{if(e.key==='Escape'&&el('gridMapDialog').open){e.preventDefault();close();}});
  if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>refresh()).observe(el('gridMapViewport'));
  clear();
 }
 return{size,init,ready,clear,refresh,open,close,keydown};
})();
if(typeof module!=='undefined')module.exports=LiveGridView;
