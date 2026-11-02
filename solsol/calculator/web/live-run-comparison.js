'use strict';
// Public saved-run summaries only; no optimization, guessed timing, or speed ranking.
const LiveRunComparison=(()=>{
 const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const number=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0?x:null;
 const states={queued:'대기',initializing:'초기 준비',running:'탐색 중',saving:'검산·저장 중',completed:'요청 세대 종료',cancelled:'사용자 중지',time_limit:'시간 제한',failed:'실패 · 결과 비교 불가',unavailable:'읽기 불가 · 기록 점검 필요'};
 const initializers={random:'무작위',greedy:'Greedy + 무작위',milp:'MILP/ε + 무작위'};
 const defaults={map_km:20,area_factor:1,resource_mode:'off',radar_stock:10,eo_stock:30,initializer:'random'};
 const labels={map_km:'지도 크기',shape:'평가영역 모양',area_factor:'평가 면적 비율',radar:'Radar 반경',eo:'EO/IR 반경',resource_mode:'자원 규칙',radar_stock:'Radar 보유량',eo_stock:'EO/IR 보유량',design:'유전·진화 설계',h:'참조방향 H',generations:'요청 세대',seed:'난수 시드',initializer:'초기화'};
 const value=(c,k)=>c?.[k]??defaults[k];
 const format=(k,v)=>k==='initializer'?(initializers[v]||'미기록'):k==='shape'?({circle:'원형',square:'사각형',hexagon:'정육각형',overlap:'겹치는 원'}[v]||v):k==='resource_mode'?({off:'제한 끔',all:'전부 사용',partial:'일부 사용'}[v]||v):k==='area_factor'?`${v*100}%`:['map_km','radar','eo'].includes(k)?`${v}km`:v??'미기록';
 const terminal=r=>['completed','cancelled','time_limit'].includes(r?.state);
 const invalid=r=>!r||['failed','unavailable'].includes(r.state)||!!r.error;
 const num=x=>number(x)===null?'미기록':x.toLocaleString('ko-KR',{maximumFractionDigits:3});
 let lastReference=null;
 function differences(a,b){
  if(!a||!b||['radar','eo','shape','design','h','generations','seed'].some(k=>a[k]===undefined||b[k]===undefined))return null;
  return Object.keys(labels).filter(k=>!(['radar_stock','eo_stock'].includes(k)&&value(a,'resource_mode')==='off'&&value(b,'resource_mode')==='off')&&value(a,k)!==value(b,k)).map(k=>({key:k,label:labels[k],reference:format(k,value(b,k)),row:format(k,value(a,k))}));
 }
 function model(row,reference){
  const bad=invalid(row),diff=differences(row?.config,reference?.config),nfe=bad?null:number(row?.evaluations),refNfe=invalid(reference)?null:number(reference?.evaluations);
  const initial=bad?null:number(row?.initial_cost),final=bad?null:number(row?.final_cost);
  return {id:row?.id||'',bad,state:states[row?.state]||'상태 미기록',terminal:terminal(row),selected:!!reference&&row.id===reference.id,diff,
   inputMatch:diff!==null&&diff.every(d=>d.key==='initializer'),nfe,refNfe,budgetMatch:nfe!==null&&refNfe!==null&&nfe===refNfe,
   initial,final,decrease:initial!==null&&final!==null?initial-final:null,
   prep:bad?null:number(row?.preparation_seconds),prepNfe:bad?null:number(row?.preparation_evaluations),search:bad?null:number(row?.search_seconds),generation:bad?null:number(row?.actual_generation)};
 }
 function rowsHtml(rows,reference){
  return rows.map(row=>{const m=model(row,reference),diff=m.diff?.filter(d=>d.key!=='initializer')||[];
   const condition=!reference?'현재 실행을 열면 비교할 수 있습니다.':m.selected?'현재 보고 있는 실행':m.diff===null?'입력 비교 자료 미기록':m.inputMatch?'초기화 제외 입력 같음':`입력 ${diff.length}항목 다름`;
   const detail=m.diff?.length?`<details><summary>설정 차이 ${m.diff.length}개</summary><ul>${m.diff.map(d=>`<li>${esc(d.label)}: ${esc(d.reference)} → ${esc(d.row)}</li>`).join('')}</ul></details>`:'';
   const budget=!reference?'평가량 비교 대기':m.bad||invalid(reference)?'검증된 평가량 비교 불가':m.budgetMatch?'진화 평가횟수 같음':m.nfe===null||m.refNfe===null?'평가횟수 미기록':`진화 평가횟수 다름 · 기준 ${num(m.refNfe)}회`;
   const cost=x=>x===null?(m.bad?'검증 자료 없음':'목표 통과값 없음'):num(x)+'점';
   const delta=m.decrease===null?'차이 계산 불가':m.decrease>0?num(m.decrease)+'점 감소':m.decrease<0?num(-m.decrease)+'점 증가':'추가 비용 감소 없음';
   const search=m.search===null?(m.bad?'검증 자료 없음':terminal(row)?'시간 미기록':'시간 미확정'):num(m.search)+'초';
   return `<tr data-run-id="${esc(m.id)}"${m.selected?' class="comparisonCurrent" aria-current="true"':''}><th scope="row"><span>${esc(row.state==='unavailable'?'메타데이터 읽기 불가':initializers[value(row.config,'initializer')]||'초기화 미기록')}</span><small>${esc(m.id.slice(0,8))} · ${esc(m.state)}</small>${typeof LiveRunArchive!=='undefined'?`<small>파일 수정 · ${esc(LiveRunArchive.date(row))}</small>`:''}${m.selected?'<strong>현재 실행</strong>':row.state==='unavailable'?'<span>실행 기록 점검 필요</span>':`<button type="button" data-open-run="${esc(m.id)}" aria-label="실행 ${esc(m.id.slice(0,8))} 열기">배치 보기</button>`}</th><td>${condition}<small>${budget}</small>${detail}</td><td>${m.generation===null?'세대 자료 없음':num(m.generation)+' / '+num(row.config?.generations)+'세대'}<small>${m.nfe===null?'평가 자료 없음':num(m.nfe)+'회 진화 평가'}</small></td><td>${cost(m.initial)} → ${cost(m.final)}<small>${delta}</small></td><td>${m.prep===null?(m.bad?'검증 자료 없음':'시간 미기록'):num(m.prep)+'초'}<small>${m.prepNfe===null?'평가 미기록':num(m.prepNfe)+'회 준비 평가'}</small></td><td>${search}<small>${m.search!==null&&m.nfe>0?'평가 1천회당 '+num(m.search/m.nfe*1000)+'초':'환산값 없음'}</small></td></tr>`;
  }).join('');
 }
 function render(rows,current){
  const host=document.getElementById('comparisonRows'),caption=document.getElementById('comparisonReference');if(!host)return;
  const ref=current?rows.find(r=>r.id===current.id):null;
  const sorted=ref?[ref,...rows.filter(r=>r.id!==ref.id)]:rows.slice();
  const wrapper=host.closest?.('.tableWrap');
  if(wrapper&&lastReference!==(ref?.id||null))wrapper.scrollTop=0;
  lastReference=ref?.id||null;
  host.innerHTML=sorted.length?rowsHtml(sorted,ref):'<tr><td colspan="6">저장된 실행이 없습니다. 계산을 시작하면 여기에 결과가 추가됩니다.</td></tr>';
  if(caption)caption.textContent=ref?`비교 기준 · 현재 실행 ${ref.id.slice(0,8)} · ${initializers[value(ref.config,'initializer')]||'초기화 미기록'} · 제공된 실행 ${rows.length}건`:`비교 기준 대기 · 결과를 열면 해당 실행을 기준으로 설정 차이를 표시합니다. 제공된 실행 ${rows.length}건`;
  // Existing load path owns race guards, map selection reset and failed-run recovery.
  host.querySelectorAll('[data-open-run]').forEach(button=>button.addEventListener('click',()=>{document.getElementById('jobs').value=button.getAttribute('data-open-run');document.getElementById('loadJob').click();}));
 }
 return {model,differences,rowsHtml,render};
})();
if(typeof module!=='undefined')module.exports=LiveRunComparison;
