/* Names and recoverable deletion live outside immutable scientific results. */
window.addEventListener('DOMContentLoaded',()=>{
 const button=document.createElement('button');button.id='manageRuns';button.textContent='실행 목록 편집';button.hidden=true;$('runHistory').after(button);
 const dialog=document.createElement('dialog');dialog.id='runManagementDialog';dialog.className='runManagement';
 dialog.innerHTML=`<div class="runManagementHead"><div><h2>저장 실행 관리</h2><p id="managedContract"></p></div><button id="managedClose" aria-label="실행 관리 닫기">닫기</button></div>
 <p>이름을 바꿔 실험을 구분하세요. 삭제한 항목은 휴지통에서 복원할 수 있습니다.</p>
 <div class="runManagementTools"><label>목록 <select id="managedView"><option value="saved">저장 실행</option><option value="trash">휴지통</option></select></label><label>검색 <input id="managedSearch" type="search" placeholder="이름 또는 실행 ID" autocomplete="off"></label><button id="managedRefresh">새로고침</button></div>
 <div class="runManagementGrid"><div><p id="managedCount"></p><select id="managedList" size="10" aria-label="편집할 저장 실행"></select></div><section aria-label="선택한 실행 편집"><h3 id="managedTitle">실행을 선택하세요</h3><p id="managedDetails"></p><p id="managedAutomatic"></p><label>이름 <input id="managedName" maxlength="120" autocomplete="off"></label><div class="runManagementActions"><button id="managedRename">이름 저장</button><button id="managedReset">자동 이름 사용</button><button id="managedTrash">삭제…</button><button id="managedRestore">복원</button></div><p id="managedGuard"></p><div id="managedConfirm" hidden><p id="managedConfirmText"></p><button id="managedConfirmTrash">휴지통으로 이동</button><button id="managedKeep">취소</button></div></section></div>
 <p id="managedStatus" role="status" aria-live="polite"></p>`;
 document.body.append(dialog);
 let cid=null,rows=[],busy=false;
 const selected=()=>rows.find(r=>r.run_id===$('managedList').value);
 const lock=value=>{busy=value;for(const el of dialog.querySelectorAll('input,select,button'))el.disabled=value;renderSelection();};
 function renderSelection(){
  const r=selected(),trash=$('managedView').value==='trash';$('managedConfirm').hidden=true;
  $('managedTitle').textContent=r?.display_name||'실행을 선택하세요';
  $('managedDetails').textContent=r?`${states[r.state]||r.state} · ${r.actual_generation??'—'}세대 · ${(r.evaluations??0).toLocaleString()} NFE · ID ${r.run_id}`:'';
  $('managedAutomatic').textContent=r?'자동 이름: '+r.automatic_name:'';
  $('managedName').value=r?.custom_name||'';$('managedName').placeholder=r?'이름을 입력하거나 자동 이름을 사용하세요':'';
  $('managedGuard').textContent=r&&!r.editable?'계산·검증·저장 중이거나 상태 확인이 필요한 항목은 편집할 수 없습니다.':trash?'복원하면 저장 실행 목록에 다시 나타납니다.':'삭제는 목록에서 숨기는 기능이며, 원시 계산 파일은 보존됩니다.';
  for(const id of ['managedName','managedRename','managedReset','managedTrash'])$(id).disabled=busy||!r?.editable||trash;
  $('managedRestore').hidden=!trash;$('managedRestore').disabled=busy||!r?.editable||!trash;$('managedTrash').hidden=trash;
 }
 function renderList(preferred){
  const q=$('managedSearch').value.trim().toLocaleLowerCase(),visible=rows.filter(r=>`${r.display_name} ${r.automatic_name} ${r.run_id}`.toLocaleLowerCase().includes(q));
  option($('managedList'),visible.map(r=>[r.run_id,`${r.display_name} · ${states[r.state]||r.state} · ${r.actual_generation??'—'}세대 · ${r.run_id.slice(0,8)}`]),visible.some(r=>r.run_id===preferred)?preferred:(visible[0]?.run_id||''));
  $('managedCount').textContent=`${visible.length}개 표시 / 전체 ${rows.length}개`;renderSelection();
 }
 async function refresh(preferred){
  lock(true);$('managedStatus').textContent='저장 실행 목록을 불러오는 중입니다.';
  try{const p=await api(cid,'engine/run-management?deleted='+($('managedView').value==='trash'));rows=p.runs;renderList(preferred);$('managedStatus').textContent=rows.length?'편집할 실행을 선택하세요.':'이 목록에 실행이 없습니다.';}
  catch(e){rows=[];renderList();$('managedStatus').textContent='목록을 불러오지 못했습니다: '+e.message;return false;}
  finally{lock(false);}
  return true;
 }
 async function change(action,name){
  const r=selected();if(busy||!r?.editable)return;const id=r.run_id;lock(true);$('managedStatus').textContent='변경 내용을 저장 중입니다.';
  try{
   const body={action,expected_revision:r.management_revision};if(action==='rename')body.name=name;
   const saved=await api(cid,'engine/run-management/'+id,body);
   r.management_revision=saved.revision;
   if(run?.run_id===id&&draft.sensor===cid){
    if(action==='trash'){clearRun();modeTo('design');}
    else if(action==='rename')run.display_name=name.trim()||r.automatic_name;
   }
   const message=action==='rename'?'이름을 저장했습니다.':action==='trash'?'휴지통으로 이동했습니다. 휴지통에서 복원할 수 있습니다.':'실행 목록으로 복원했습니다.';
   let historyOK=true;try{await histories();}catch(e){historyOK=false;}
   const refreshed=await refresh(action==='rename'?id:null);
   $('managedStatus').textContent=message+(!refreshed||!historyOK?' 목록 갱신에 실패했습니다. 새로고침하세요.':'');
  }catch(e){$('managedStatus').textContent=e.connectionFailure?'응답을 받지 못해 반영 여부를 확인해야 합니다. 새로고침한 뒤 이름과 목록을 확인하세요.':'변경하지 못했습니다: '+e.message;}
  finally{lock(false);}
 }
 button.onclick=()=>{cid=draft.sensor;$('managedContract').textContent='현재 실험: '+cid;$('managedView').value='saved';$('managedSearch').value='';dialog.showModal();refresh(run?.run_id||$('runHistory').value);};
 $('managedClose').onclick=()=>dialog.close();dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
 $('managedList').onchange=renderSelection;$('managedSearch').oninput=()=>renderList($('managedList').value);
 $('managedView').onchange=()=>refresh();$('managedRefresh').onclick=()=>refresh($('managedList').value);
 $('managedRename').onclick=()=>change('rename',$('managedName').value);$('managedReset').onclick=()=>change('rename','');
 $('managedTrash').onclick=()=>{const r=selected();if(!r?.editable)return;$('managedConfirmText').textContent=`“${r.display_name}”을(를) 저장 목록에서 삭제할까요? 휴지통에서 복원할 수 있습니다.`;$('managedConfirm').hidden=false;};
 $('managedKeep').onclick=()=>{$('managedConfirm').hidden=true;};$('managedConfirmTrash').onclick=()=>change('trash');$('managedRestore').onclick=()=>change('restore');
 // Old running servers keep their ongoing calculation; expose only when the
 // loaded backend supports this feature, not just because static files changed.
 const capabilityContract=new URLSearchParams(location.search).get('contract')||'ABC_COVERAGE_RESOURCE_V1';
 api(capabilityContract,'engine/run-management?capabilities=true').then(p=>{
  if(!(p.rename&&p.recoverable_delete))return;
  const reveal=()=>{if(draft&&token&&typeof registryData!=='undefined'&&registryData?.bundles){button.hidden=false;return true;}return false;};
  if(!reveal()){const timer=setInterval(()=>{if(reveal())clearInterval(timer);},100);}
 }).catch(()=>{});
});
