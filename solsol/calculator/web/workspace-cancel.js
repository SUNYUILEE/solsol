'use strict';
// Every model uses its own run identity and the established cancel contract.
$('cancel').onclick=safe(async()=>{
 if(!run)return;
 const cid=run.experiment_contract_id,id=run.run_id;
 if(cid!==draft.sensor)throw Error('선택한 실행과 모델이 다릅니다. 실행을 다시 선택하세요.');
 $('cancel').disabled=true;
 notice('중지 요청을 보내고 있습니다…','busy');
 try{
  const reply=await api(cid,(cid===EO?'jobs/':'runs/')+id+'/cancel',cid===RF?{experiment_contract_id:cid}:{});
  if(run?.run_id!==id||draft.sensor!==cid)return;
  run.cancel_requested=reply.cancel_requested===true;
  $('runtimeStatus').textContent='중지 요청 · 진행 중인 평가와 저장을 마치는 중';
  notice('중지 요청이 접수됐습니다. 진행 중인 평가가 끝나면 계산을 멈추고 결과를 저장합니다.','busy');
 }catch(e){if(run?.run_id===id&&draft.sensor===cid)$('cancel').disabled=terminal.has(run.state);throw e;}
});
