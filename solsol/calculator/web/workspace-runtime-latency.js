/* Lightweight progress between map snapshots; retain full terminal results. */
function runtimeProgressText(p){
 const n=p.nfe??p.evaluations,total=Number.isFinite(n)?n:'미기록',replay=p.counters?.replay_evaluations;
 const observed=Number.isFinite(p.observed_completion_elapsed_seconds)&&p.observed_completion_elapsed_seconds>=0;
 const elapsed=observed?p.observed_completion_elapsed_seconds:[p.elapsed_seconds,p.seconds].find(v=>Number.isFinite(v)&&v>=0);
 const ended=terminal.has(p.state),time=elapsed===undefined?'시간 미기록':`${ended?(observed?'완료 관측 ':'기록 경과 '):''}${elapsed.toFixed(1)}초`;
 const detail=p.state==='verifying'?` · 저장 전 재평가 ${Number.isFinite(replay)?replay.toLocaleString():'진행량 미기록'} / ${Number.isFinite(n)?n.toLocaleString():'전체 미기록'}회 · 완료 후 저장합니다`:p.state==='saving'?' · 검산 결과와 원시 배치를 저장하고 있습니다':observed&&Number.isFinite(p.terminal_storage_seconds)&&p.terminal_storage_seconds>=0?` · 최종 저장 단계 ${p.terminal_storage_seconds.toFixed(1)}초 포함`:ended&&!observed?' · 저장 완료까지의 총시간은 미확인':'';
 const failure=p.error||p.runtime_diagnostic?.error;
 return (p.cancel_requested?'중지 요청 · ':'')+(states[p.state]||p.state)+` · ${p.generation??0}세대 · ${total} NFE · ${time}`+detail+(failure?' · 사유: '+failure:'');
}
(()=>{
 const priorFetch=fetchRun,priorSettings=renderSettings,priorRequest=requestConfiguration;
 let snapshotAt=0,progressInFlight=false;
 const completionObservations=new Map();
 function missingProgress(e,cid,id){
  if(e.httpStatus!==404||e.requestPath!==(cid===EO?'jobs/':'runs/')+id+'/progress'||cid!==draft.sensor||run?.run_id!==id)return;
  clearRun();renderHeader();renderSettings();
  $('calculate').disabled=previewPending||!confirmedExecution||JSON.stringify(requestConfiguration())!==JSON.stringify(confirmedRequest);
  e.message+=' · 서버에 실행이 없어 편집 잠금을 해제했습니다. 조건을 확인한 뒤 다시 계산할 수 있습니다.';
 }
 function showTerminal(cid,id){
  if(cid===draft.sensor&&run?.run_id===id&&terminal.has(run.state))$('runtimeStatus').textContent=runtimeProgressText({...run,...completionObservations.get(cid+':'+id)});
 }
 fetchRun=async function(id,g=null){
  const cid=draft.sensor,owner=loadingRun,stillCurrent=()=>cid===draft.sensor&&owner===loadingRun&&run?.run_id===id;
  if(id&&g===null&&run?.run_id===id&&!terminal.has(run.state)&&run.research_configuration){
   const progressOwner={};progressInFlight=progressOwner;
   try{
    const p=await api(cid,(cid===EO?'jobs/':'runs/')+id+'/progress',undefined,{}, {signal:loadingRun?.controller?.signal});
    if(!stillCurrent())return;
    if(terminal.has(p.state)){
     if(Number.isFinite(p.observed_completion_elapsed_seconds)&&p.observed_completion_elapsed_seconds>=0)completionObservations.set(cid+':'+id,{observed_completion_elapsed_seconds:p.observed_completion_elapsed_seconds,terminal_storage_seconds:p.terminal_storage_seconds});
     snapshotAt=0;const result=await priorFetch(id,g);
     showTerminal(cid,id);
     return result;
    }
    if(!['verifying','saving'].includes(p.state)&&Date.now()-snapshotAt>=10000){const result=await priorFetch(id,g);snapshotAt=Date.now();showTerminal(cid,id);return result;}
    run.cancel_requested=p.cancel_requested===true;
    $('runtimeStatus').textContent=runtimeProgressText(p);
    if(['verifying','saving'].includes(p.state)){const message=$('executionGuide')?.querySelector('span');if(message)message.textContent=runtimeProgressText(p);}
    clearTimeout(poller);poller=setTimeout(safe(()=>loadRun(id)),1000);
    return;
   }catch(e){if(e.superseded||!stillCurrent())return;if(e.connectionFailure&&stillCurrent()){snapshotAt=0;clearTimeout(poller);poller=setTimeout(safe(()=>loadRun(id)),2000);notice(e.message+' · 진행 조회 재시도 중 · 마지막 서버 상태 유지','error');return;}missingProgress(e,cid,id);throw e;}
   finally{if(progressInFlight===progressOwner)progressInFlight=false;}
  }
  try{await priorFetch(id,g);snapshotAt=Date.now();if(cid===draft.sensor&&run?.run_id===id&&['verifying','saving'].includes(run.state))$('runtimeStatus').textContent=runtimeProgressText(run);showTerminal(cid,id);}
  catch(e){if(e.superseded||owner!==loadingRun||cid!==draft.sensor)return;if(e.connectionFailure&&stillCurrent()&&!terminal.has(run.state)){snapshotAt=0;clearTimeout(poller);poller=setTimeout(safe(()=>loadRun(id)),2000);notice(e.message+' · 진행 조회 재시도 중 · 마지막 서버 상태 유지','error');return;}throw e;}
 };
 renderSettings=function(){
  priorSettings();if(!configured()||setting!=='optimizer'||selection()?.solver_policy!=='generic_v1')return;
  const old=$('field_wallclock_limit_seconds');if(old)old.closest('.field').remove();
  $('runtimeTerminationSettings')?.remove();
  const g=group('계산 종료 조건');
  g.id='runtimeTerminationSettings';$('settingsBody').prepend(g);
  renderExecutionResources(g);
  draft.optimizer.wallclock_limit_seconds=0;
  noteText(g,'시간 제한 없음 · 요청한 세대까지 계산합니다. 중지 버튼을 누르면 진행 중인 평가가 끝난 뒤 계산을 멈추고 결과를 저장합니다.');
  noteText(g,'화면 진행은 매초, 배치 지도는 약 10초 간격으로 갱신합니다. 저장 조건을 복사해도 다음 계산에는 시간 제한을 적용하지 않습니다.');
 };
 requestConfiguration=function(){const q=priorRequest();if(q.solver_policy==='generic_v1'){draft.optimizer.wallclock_limit_seconds=0;q.optimizer.wallclock_limit_seconds=0;}return q;};
})();
