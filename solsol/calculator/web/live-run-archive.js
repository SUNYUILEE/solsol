'use strict';
// Discovery only. Filtering never changes the open result or starts a calculation.
const LiveRunArchive=(()=>{
 const $=id=>document.getElementById(id),esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const states={queued:'대기',initializing:'준비 중',running:'계산 중',saving:'검산·저장 중',completed:'세대 종료',cancelled:'사용자 중지',time_limit:'시간 제한',failed:'실패',unavailable:'읽기 불가'};
 const init={random:'무작위',greedy:'Greedy',milp:'MILP/ε'};
 let page=1,serial=0,lastRun=null,apply=null;
 function date(row){return row.record_time&&Number.isFinite(Date.parse(row.record_time))?new Intl.DateTimeFormat('ko-KR',{dateStyle:'short',timeStyle:'medium',timeZone:'UTC'}).format(new Date(row.record_time))+' UTC':'수정시각 미기록';}
 function query(current){const q=new URLSearchParams({page:String(page),limit:$('archiveLimit').value||'20',state:$('archiveState').value,initializer:$('archiveInit').value,design:$('archiveDesign').value,q:$('archiveQuery').value.trim()});if(current)q.set('current',current);return '/api/archive?'+q.toString();}
 function rows(data){return data.current?[data.current,...data.items.filter(r=>r.id!==data.current.id)]:data.items;}
 function options(list){return list.map(r=>`<option value="${esc(r.id)}"${r.state==='unavailable'?' disabled':''}>${esc(r.id.slice(0,8))} · ${esc(states[r.state]||'상태 미기록')} · ${esc(init[r.config?.initializer||'random']||'초기화 미기록')} · ${esc(r.config?.design||'—')}/H${esc(r.config?.h??'—')} · ${esc(date(r))}</option>`).join('');}
 async function refresh(request,current,opened){
  const ticket=++serial,old=$('jobs').value,changed=lastRun!==(opened||null);$('archiveRefresh').disabled=true;$('archiveStatus').textContent='실행 목록을 불러오는 중입니다.';
  try{
   const data=await request(query(opened));if(ticket!==serial)return false;
   if(data.schema!=='run-archive-v1'||!Array.isArray(data.items))throw Error('목록 형식을 확인할 수 없습니다.');
   page=data.page;lastRun=opened||null;const all=rows(data),selectable=all.filter(r=>r.state!=='unavailable');
   $('jobs').innerHTML=selectable.length?options(selectable):'<option value="">검색에 맞는 실행 없음</option>';
   const keep=!changed&&selectable.some(r=>r.id===old)?old:selectable.some(r=>r.id===opened)?opened:selectable[0]?.id||'';$('jobs').value=keep;
   $('archivePrev').disabled=page<=1;$('archiveNext').disabled=page>=data.pages;
   $('archivePage').textContent=`${page} / ${data.pages}페이지`;
   const start=data.total?(page-1)*data.limit+1:0,end=Math.min(page*data.limit,data.total);
   $('archiveStatus').textContent=`전체 ${data.total_all}건 · 검색 결과 ${data.total}건 · ${start}–${end}건 표시${data.current&&!data.items.some(r=>r.id===data.current.id)?' · 현재 실행은 비교 기준으로 별도 표시':''}. 읽기 불가 ${data.unavailable_count}건 · 수정시각 미기록 ${data.unknown_time_count}건.`;
   if(typeof LiveRunComparison!=='undefined')LiveRunComparison.render(all,current);
   if(!all.length&&data.total_all>0)$('comparisonRows').innerHTML='<tr><td colspan="6">검색 조건에 맞는 실행이 없습니다. 검색 조건을 바꾸거나 초기화하세요.</td></tr>';
   return true;
  }catch(e){if(ticket!==serial)return false;$('archiveStatus').textContent='실행 목록을 갱신하지 못했습니다. 현재 지도와 이전 목록을 유지합니다. 다시 검색하거나 다시 연결하세요.';return false;}
  finally{if(ticket===serial)$('archiveRefresh').disabled=false;}
 }
 function bind(fn){apply=fn;const reset=()=>{page=1;return apply();};$('archiveRefresh').onclick=reset;
  ['archiveState','archiveInit','archiveDesign','archiveLimit'].forEach(id=>$(id).addEventListener('change',reset));
  $('archiveQuery').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();reset();}});
  $('archiveClear').onclick=()=>{['archiveState','archiveInit','archiveDesign','archiveQuery'].forEach(id=>$(id).value='');return reset();};
  $('archivePrev').onclick=()=>{page=Math.max(1,page-1);return apply();};$('archiveNext').onclick=()=>{page++;return apply();};
 }
 return {refresh,bind,rows,options,date,query};
})();
if(typeof module!=='undefined')module.exports=LiveRunArchive;
