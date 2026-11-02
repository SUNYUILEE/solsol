'use strict';
// Read-only view of recorded timers. Never infer checkpoint timing or solver NFE.
const LiveTiming=(()=>{
 const number=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0?v:null;
 const count=v=>Number.isInteger(v)&&v>=0?v:null;
 const seconds=v=>v===null?'미기록':v.toLocaleString('ko-KR',{maximumFractionDigits:4})+'초';
 const evaluations=v=>v===null?'미기록':v.toLocaleString('ko-KR')+'회';
 function model(run){
  const failed=!!run&&(run.state==='failed'||!!run.error);
  const terminal=!!run&&['completed','cancelled','time_limit'].includes(run.state)&&!failed;
  const init=run?.initialization,audit=terminal?run.audit:null;
  // Initializing/queued seconds=0 is a default, not an elapsed-time measurement.
  const sampled=!!run?.snapshot&&!failed&&!['queued','initializing'].includes(run.state);
  return {failed,terminal,hasRun:!!run,
   preparation:failed?null:number(init?.seconds),preparationNFE:failed?null:count(init?.preparation_evaluations),
   search:number(audit?.search_seconds),searchNFE:count(audit?.search_evaluations),
   replayNFE:count(audit?.posthoc_diagnostic_evaluations),
   replay:number(audit?.timing?.schema==='LIVE_TIMING_V1'?audit.timing.posthoc_seconds:null),
   artifacts:number(audit?.timing?.schema==='LIVE_TIMING_V1'?audit.timing.artifact_seconds:null),
   solverSeconds:failed?null:number(init?.solver_seconds),
   lpCalls:failed?null:count(init?.solver_call_counts?.LP),milpCalls:failed?null:count(init?.solver_call_counts?.MILP),
   refinementContract:audit?.offspring_refinement_effort?.contract||'off',
   refinementChecks:count(audit?.offspring_refinement_effort?.candidate_checks),
   refinementAccepted:count(audit?.offspring_refinement_effort?.accepted),
   refinementSeconds:number(audit?.offspring_refinement_effort?.seconds),
   worker:sampled?number(run.seconds):null,
   generation:failed?null:count(run?.snapshot?.generation),
   checkpointNFE:failed?null:count(run?.snapshot?.evaluations)};
 }
 function render(run){
  const host=document.getElementById('executionTiming');if(!host)return;
  const m=model(run);host.hidden=!m.hasRun;
  if(!m.hasRun){host.textContent='';return;}
  if(m.failed){host.innerHTML='<h3 id="executionTimingTitle">계산 시간·평가 횟수</h3><p>실행 실패 · 검증된 시간 비교 자료를 표시할 수 없습니다. 이전 실행의 시간은 사용하지 않습니다.</p>';return;}
  host.innerHTML=`<h3 id="executionTimingTitle">계산 시간·평가 횟수</h3><p>표시 중인 ${m.generation===null?'세대 자료 대기':m.generation+'세대'} · 이 시점까지 진화 평가 ${evaluations(m.checkpointNFE)}. 아래 시간은 세대별 시간이 아니라 실행 전체의 기록입니다.</p><div class="tableWrap" tabindex="0" role="region" aria-label="계산 단계별 시간과 평가 횟수"><table><thead><tr><th scope="col">계산 단계</th><th scope="col">기록된 시간</th><th scope="col">목적값 평가</th><th scope="col">포함하는 작업</th></tr></thead><tbody><tr><th scope="row">초기 배치 준비</th><td>${seconds(m.preparation)}</td><td>${evaluations(m.preparationNFE)}</td><td>LP/MILP·Greedy와 초기 집단 준비. 솔버 내부 반복과 Greedy 후보 점수 검사는 이 평가 횟수에 포함하지 않습니다.</td></tr><tr><th scope="row">진화 탐색</th><td>${seconds(m.search)}</td><td>${evaluations(m.searchNFE)}</td><td>0세대 평가부터 자식 생성·평가·NSGA-III 생존 선택·세대 기록까지. 탐색이 끝나면 시간이 확정됩니다.</td></tr><tr><th scope="row">목표유지 비용 정련</th><td>${seconds(m.refinementSeconds)}</td><td>공식 NFE 외 후보검사 ${evaluations(m.refinementChecks)}</td><td>${m.refinementContract==='target_delete_v1'?`정식 자식 중 ${evaluations(m.refinementAccepted)}에서 목표를 유지하는 장비 한 대를 제거했습니다. 최종 자식만 공식 평가됩니다.`:'사용하지 않았습니다.'}</td></tr><tr><th scope="row">저장 전 재검산</th><td>${m.replay===null?'별도 시간 미기록':seconds(m.replay)}</td><td>${evaluations(m.replayNFE)}</td><td>저장할 배치의 목적값 재계산. 탐색 평가 횟수와 별도로 집계하며 해집합을 바꾸지 않습니다.</td></tr><tr><th scope="row">배치·세대 파일 저장</th><td>${seconds(m.artifacts)}</td><td>목적값 평가 없음</td><td>배치 원시값·교차/변이 이력·세대 파일 쓰기만 측정합니다. 최종 공개 파일 쓰기는 제외합니다.</td></tr></tbody></table></div><p><strong>준비 시간 안의 수학적 풀이</strong> · LP ${evaluations(m.lpCalls)} · MILP ${evaluations(m.milpCalls)} · 솔버 호출 시간 ${seconds(m.solverSeconds)}. 호출 수는 내부 반복 횟수가 아니며, 제한시간 종료와 예외도 호출 시도로 셉니다. 이 시간은 초기 배치 준비에 포함되어 있으므로 다시 더하지 않습니다. 무작위 초기화도 비교용 LP 하한을 계산할 수 있습니다.</p><p class="timingTotal"><strong>작업 경과 · 마지막 기록 ${seconds(m.worker)}</strong></p><p>작업 경과에는 초기 준비·진화·기록·검산의 여러 구간이 들어갑니다. 지도 모델 구성, 최종 결과 공개 파일 쓰기, 통신과 화면 표시 시간은 제외됩니다. 실시간 초시계나 사용자 체감 총시간이 아닙니다. 과거 세대로 이동해도 실행 전체 시간은 그대로입니다.</p><p class="muted">빠르기를 비교하려면 같은 지도·목적함수·설계·실제 평가 예산·실행 환경을 맞추고 준비 시간과 비용 정련 후보검사도 함께 비교하세요. 초기화에서 이미 좋은 배치를 얻은 경우와 진화가 추가로 개선한 경우는 구분해야 합니다.</p>`;
 }
 return {model,render};
})();
