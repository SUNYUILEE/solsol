'use strict';
let qualityJourneyInstance=0;
function qualityTargetMeaning(a){if(a.goals===null)return '목표를 설정하지 않아 합격·불합격 대신 성능의 절충을 비교합니다.';const unknown=a.target_unknown_count??null;return `저장 목표 통과가 확인된 배치 ${a.target_count??'미집계'}개. `+(unknown===null?'나머지 배치의 판정 기록을 확인하세요.':`목표 미달 ${a.target_failed_count}개 · 판정 미기록 ${unknown}개입니다.`)+(unknown>0?' 미기록 배치를 목표 미달이나 통과로 간주하지 않습니다.':'');}
function qualityCheckEvidenceUnchanged(loaded,job){
 const cached=loaded?.budget_quality?.checked_jobs?.find(c=>c.job_id===job.job_id);
 return job.status==='COMPLETED'&&!!cached&&cached.evaluated===job.evaluated;
}
// Read-only claim model. All observations retain the saved run's population and identity.
function qualityDecision(loaded){
 const a=loaded.assessment,q=loaded.budget_quality||{},j=q.joint_evidence,checks=q.checked_jobs||[];
 const whole=checks.filter(c=>c.covers_entire_final),improved=checks.filter(c=>c.improvement_count>0);
 const last=q.runs?.[0],repeat=j?.repeat_count||0;
 const count=v=>Number.isFinite(v)?v.toLocaleString():'미기록';
 const claims=[
  {id:'set',question:'어떤 대안을 얻었나요?',answer:`조건을 충족한 서로 다른 ${count(a.unique_feasible)}배치 중 최종 비지배 ${count(a.archive_unique_X)}배치입니다.`,meaning:qualityTargetMeaning(a),action:'최종 해의 성능·목표 비교',target:'tradeoff'},
  {id:'search',question:'쓴 계산량으로 얼마나 개선했나요?',answer:last?.final?`평가 ${count(last.trace[0]?.nfe)}→${count(last.final.nfe)}회. 자기 최종 결과를 기준으로 마지막 구간의 성능 공간 증가 ${Number.isFinite(last.last_fifth_gain_pp)?last.last_fifth_gain_pp.toFixed(3)+'%p':'미계산'}.`:(q.reason||'탐색 곡선 근거가 없습니다.'),meaning:`총 ${count(a.nfe)}회 중 서로 다른 배치 ${count(a.unique_all)}개, 반복 평가 ${count(a.repeated_evaluations)}회입니다. 자기 최종 집합과 비교하므로 마지막 100%·거리 0은 기준점에 도달했다는 뜻이며 최적성 점수가 아닙니다.`,action:'탐색 곡선·계산 기준 보기',target:'search'},
  {id:'repeat',question:'다시 계산하면 더 좋은 해가 나오나요?',answer:repeat?`동일 조건 반복 ${repeat}회 중 일부 원해를 개선한 실행 ${count(j.runs_improving_any)}회, 모든 원해를 개선한 실행 ${count(j.runs_improving_entire_original)}회입니다.`:q.status==='DEFERRED'?'저장된 반복 연구 근거는 아직 조회하지 않았습니다.':'이 실행에 연결된 동일 조건 반복은 없습니다.',meaning:repeat?'일부 개선과 전체 개선은 다른 판단입니다. 각 원래 배치에 실제로 대응하는 더 좋은 배치를 비교합니다. 전체 개선이 0회여도 모든 배치가 안정적이라는 뜻은 아닙니다.':'현재 실행의 성능과 검산 결과는 판단할 수 있습니다. seed에 따른 변동을 알려면 반복 결과를 비교해야 합니다.',action:q.status==='DEFERRED'?'저장 반복·탐색 근거 조회':repeat?'반복별 수치·개선 사례 보기':'같은 조건 반복 연구 열기',target:q.status==='DEFERRED'?'search':repeat?'repeat':'repeatSetup'},
  {id:'check',question:'직접 위치를 바꾸면 더 좋아지나요?',answer:improved.length?`최종 해를 개선한 완료 검산 기록 ${improved.length}건이 있습니다.`:whole.length?`최종 해 전체를 대상으로 완료한 검사 ${whole.length}건에서 지배 개선을 발견하지 못했습니다.`:checks.length?`완료 검산 ${checks.length}건은 최종 해집합 일부만 검사했습니다.`:'최종 해집합에 연결된 완료 검산은 없습니다.',meaning:improved.length?'원래 배치와 개선 배치의 위치·성능 차이를 확인하세요. 같은 배치를 반복 발견할 수 있어 검사 기록 수를 개선 배치 수로 읽으면 안 됩니다.':whole.length?'선택한 변경 방법을 모두 검사한 결과입니다. 다른 변경 방법이나 전체 설치 조합까지 확인했다는 뜻은 아닙니다.':'검산 대상과 방법을 선택하면 원해 재평가부터 개선 후보 확인까지 진행합니다.',action:checks.length?'저장 검산 결과·개선 지도 열기':'최종 해집합 검산 준비',target:checks.length?'checkEvidence:'+((improved[0]||whole[0]||checks[0]).job_id):'checks'},
  {id:'replay',question:'같은 입력으로 수치가 재현되나요?',answer:loaded.replay?.raw_replay==='PASS'?'저장된 원시 재생 검사가 PASS입니다.':`원시 재생 상태: ${loaded.replay?.raw_replay||'미기록'}.`,meaning:'같은 모델로 수치를 재현한 근거입니다. 독립 수식 검증이나 격자·파라미터 변화에 대한 강건성과는 구분합니다.',action:'재현·기존 연구 적용 범위 보기',target:'provenance'}
 ];
 return {schema:'SOLSOL_QUALITY_DECISION_V1',run_id:a.run_id,parent:loaded.parent,method_hashes:{assessment:a.definition_sha256||null,budget:q.definition_sha256||null,judgment:q.judgment_definition_sha256||null},claims,counts:{feasible:a.unique_feasible,front:a.archive_unique_X,objective_vectors:a.archive_unique_F,targets:a.target_count},checks,verdict:!a.archive_unique_X?'조건을 만족하는 최종 대안이 없습니다.':(improved.length||j?.runs_improving_any)?'개선 가능성이 실제로 확인된 해집합입니다.':whole.length?'완료한 검사 범위에서 개선을 찾지 못한 해집합입니다.':'조건을 만족하는 관측 해집합입니다. 아래 근거별로 판단하세요.',global_optimality_probability:null};
}
function qualityNavigate(target){
 if(target.startsWith('checkEvidence:')){openQualityCenter(target.slice('checkEvidence:'.length));return;}
 const dialog=$('qualityDialog');if(dialog){dialog.dispatchEvent(new CustomEvent('quality-navigate',{detail:target}));return;}
 openQualityCenter(null,target);
}
function qualityCostDecision(data,frozen,parent){
 const claim={id:'cost',question:'목표를 지키면서 비용을 줄일 수 있나요?',answer:'',meaning:'',action:'비용 검산의 적용 범위·준비 보기',target:'cost',status:'NOT_RUN'};
 const latest=data.jobs?.[0],job=data.jobs?.find(j=>j.status==='COMPLETED')||latest;
 if(!job){claim.status=data.capability.supported?'NOT_RUN':'UNSUPPORTED';claim.answer=data.capability.supported?'아직 저장된 비용 reference가 없습니다.':'이 저장 조건에서는 비용 하한을 아직 계산할 수 없습니다.';claim.meaning=data.capability.supported?'비용 하한 계산은 미실행입니다. 센서 변경으로 찾은 비용 절감은 별도 저장 검산에서 확인하세요.':data.capability.reason+' 비용 하한 미지원은 저장 검산 미지원을 뜻하지 않습니다. 저장 검산의 검사 범위와 개선 배치를 별도로 확인할 수 있습니다.';return claim;}
 for(const key of ['run_id','experiment_contract_id','config_sha256','evaluator_sha256','raw_sha256'])if(job.parent?.[key]!==parent[key])throw Error('비용 근거와 저장 실행의 결속 불일치');
 claim.status=job.status;claim.job_id=job.job_id;claim.target='costEvidence:'+job.job_id;
 claim.action='이 저장 검사의 진행·결과 보기';
 if(job.status!=='COMPLETED'){
  const states={QUEUED:'비용 계산 준비 중',RUNNING:'비용 계산 중',STOPPED:'사용자가 중지한 비용 계산',INTERRUPTED:'서버 종료로 중단된 비용 계산',ERROR:'실패한 비용 계산',UNSUPPORTED:'공개 비용 계약 미지원',INFEASIBLE:'공개 비용 문제에서 실현가능 배치를 찾지 못함'};
  claim.answer=(states[job.status]||'상태 확인 필요')+'입니다.';claim.meaning=(job.error||job.phase||'')+' 완료한 별도 배치와 재평가가 확인되기 전에는 비용 절감을 판정하지 않습니다.';return claim;
 }
 const r=job.result,fmt=v=>Number.isFinite(v)?Number(v.toFixed(4)).toLocaleString():'미기록';
 if(!r||![r.feasible_upper_bound,r.integer_lower_bound,r.lp_lower_bound].every(Number.isFinite)||r.validate_installation!==true||r.reference_id!==r.row?.id||r.row?.run_id!==frozen.run_id)throw Error('비용 근거의 재평가·배치 식별값이 불완전합니다');
 const old=r.observed_minimum,delta=r.observed_cost_difference;
 if(old!==null&&(!Number.isFinite(old)||!Number.isFinite(delta)))throw Error('관측 비용 비교값이 불완전합니다');
 claim.answer=old===null?`목표를 만족하는 별도 배치 비용은 ${fmt(r.feasible_upper_bound)}입니다. 비교할 목표 통과 관측 배치는 없습니다.`:delta>1e-7?`관측 최소 ${fmt(old)}보다 ${fmt(delta)} 낮은 비용 ${fmt(r.feasible_upper_bound)}의 별도 배치를 찾았습니다.`:`관측 최소 ${fmt(old)}와 별도 비용 ${fmt(r.feasible_upper_bound)}의 차이는 ${fmt(delta)}입니다.`;
 const metrics=(frozen.metadata.metrics||[]).filter(m=>m.id!=='cost'&&frozen.registry.objective_order.includes(m.id));
 const changes=metrics.map(m=>{const a=r.observed_row?.named_metrics?.[m.id],b=r.row.named_metrics?.[m.id];if(!Number.isFinite(a)||!Number.isFinite(b))return m.name+' 비교값 미기록';const gain=(m.direction==='maximize'?b-a:a-b);return `${m.name} ${fmt(a*(m.display_scale||1))}→${fmt(b*(m.display_scale||1))} (${Math.abs(gain)<=1e-10?'유지':gain>0?'향상':'저하'})`;});
 claim.meaning=`${changes.join(' · ')}. 수량 ${r.sensor_counts.join('/')}대와 저장 영역 목표 ${r.targets.map(t=>t.epsilon+'%').join('/')}를 지켰습니다. 비교 모집단은 최종 해집합에 한정하지 않은 전체 저장 관측 중 설치·목표를 통과한 ${r.observed_qualified_count}행입니다. 하한 ${fmt(r.integer_lower_bound)}와 실현 비용이 일치하는 고정 비용 문제의 근거이며, 모든 성능이 함께 좋아졌다는 뜻은 아닙니다.`;
 if(latest.job_id!==job.job_id){claim.latest_attempt={job_id:latest.job_id,status:latest.status};claim.meaning+=` 최근 시도 상태는 ${latest.status}입니다. 위 판단은 이전 완료 기록 ${job.job_id}에 근거합니다.`;}
 claim.action='원시 배치와 별도 배치의 절충·지도 비교';claim.reference_id=r.reference_id;claim.observed_raw_id=r.observed_row?.id??null;claim.evidence_scope=r.bound_scope;
 return claim;
}
function renderQualityJourney(parent,loaded,frozen){
 const model=qualityDecision(loaded),a=loaded.assessment;
 const instance='qualityAnswer-'+(++qualityJourneyInstance)+'-';
 const s=qualitySection(parent,'현재 결과의 판단과 다음 확인');s.classList.add('qualityJourney','qualityDecision');s.dataset.runId=a.run_id;
 const verdict=document.createElement('p');verdict.className='qualityVerdict';verdict.textContent=model.verdict;s.append(verdict);
 noteText(s,`${a.generation}세대 · ${a.nfe.toLocaleString()}회 평가 · 최종 해집합 전체를 판단합니다.`);
 const flow=document.createElement('div');flow.className='qualitySetFlow';s.append(flow);
 for(const [label,n,explain] of [['조건 충족 관측',a.unique_feasible,'서로 다른 설치 배치'],['최종 비지배',a.archive_unique_X,`목적값 조합 ${a.archive_unique_F}종`],['목표 통과',a.goals===null?null:a.target_count,a.goals===null?'목표 미설정':`최종 ${a.archive_unique_X}개 중 부분집합`]]){const cell=document.createElement('div'),b=document.createElement('b'),v=document.createElement('strong'),small=document.createElement('span');b.textContent=label;v.textContent=n===null?'판정 안 함':n.toLocaleString()+'개';small.textContent=explain;cell.append(b,v,small);flow.append(cell);}
 noteText(s,'알고 싶은 질문을 고르세요. 근거 보기는 저장 결과를 읽고, 새 반복·검산은 준비 화면에서 따로 시작합니다.');
 const tabs=document.createElement('div');tabs.className='qualityQuestions';tabs.setAttribute('role','group');tabs.setAttribute('aria-label','판단할 질문 선택');s.append(tabs);
 const ledger=document.createElement('div');ledger.className='qualityClaimList qualityAnswerLedger qualityFocusedAnswer';s.append(ledger);
 const labels={set:'1. 얻은 해집합',search:'2. 탐색의 진전',repeat:'3. 반복 결과',check:'4. 위치 변경 검산',replay:'5. 수치 재현'};
 function choose(id,reveal=false){for(const el of ledger.children)el.hidden=el.dataset.claim!==id;for(const b of tabs.children)b.setAttribute('aria-pressed',String(b.dataset.question===id));if(reveal)requestAnimationFrame(()=>ledger.querySelector('[data-claim="'+id+'"]').scrollIntoView({block:'start',behavior:'instant'}));}
 for(const c of model.claims){
  const tab=document.createElement('button');tab.type='button';tab.dataset.question=c.id;tab.textContent=labels[c.id];tab.setAttribute('aria-controls',instance+c.id);tab.onclick=()=>choose(c.id,true);tabs.append(tab);
  const row=document.createElement('article');row.id=instance+c.id;row.dataset.claim=c.id;const h=document.createElement('h4'),answer=document.createElement('p'),meaning=document.createElement('p'),button=document.createElement('button');h.textContent=c.question;answer.textContent=c.answer;answer.className='claimAnswer';meaning.textContent=c.meaning;button.textContent=c.action;button.dataset.qualityTarget=c.target;button.onclick=()=>qualityNavigate(c.target);row.append(h,answer,meaning);
  if(c.id==='search'&&a.metrics?.length){
   const chart=document.createElement('div');chart.className='qualityMetricProgress';row.append(chart);
   for(const x of a.metrics){const m=x.metric,cell=document.createElement('div'),label=document.createElement('strong'),values=document.createElement('span'),interpret=document.createElement('small');label.textContent=m.name;values.textContent=x.constant_observed?qualityValue(m,x.observed_best)+' · 동일':qualityValue(m,x.initial_best)+' → '+qualityValue(m,x.observed_best);interpret.textContent=x.constant_observed?'관측값이 일정합니다':(m.direction==='maximize'?'높을수록 좋음':'낮을수록 좋음');cell.append(label,values,interpret);chart.append(cell);}
   noteText(row,'초기 관측 최선 → 전체 관측 최선입니다. 목적마다 최선 배치가 다를 수 있어 위 값들을 한 배치의 성능으로 합치지 않습니다.');
  }
  row.append(button);const back=document.createElement('button');back.textContent='다른 질문 선택';back.dataset.questionBack=c.id;back.onclick=()=>{tabs.scrollIntoView({block:'center',behavior:'instant'});tab.focus({preventScroll:true});};row.append(back);ledger.append(row);
 }
 const costTab=document.createElement('button');costTab.type='button';costTab.dataset.question='cost';costTab.textContent='6. 비용과 성능 절충';costTab.onclick=()=>choose('cost',true);costTab.setAttribute('aria-controls',instance+'cost');tabs.append(costTab);
 const costRow=document.createElement('article');costRow.id=instance+'cost';costRow.dataset.claim='cost';costRow.hidden=true;ledger.append(costRow);
 choose('set');
 const renderCost=c=>{costRow.replaceChildren();const title=document.createElement('h4'),answer=document.createElement('p'),meaning=document.createElement('p');title.textContent=c.question;answer.className='claimAnswer';answer.textContent=c.answer;meaning.textContent=c.meaning;costRow.append(title,answer,meaning);const b=document.createElement('button');b.textContent=c.action;b.dataset.qualityTarget=c.target;b.onclick=()=>qualityNavigate(c.target);costRow.append(b);model.cost_reference=c;};
 renderCost({question:'목표를 지키면서 비용을 줄일 수 있나요?',answer:'저장된 비용 근거를 확인하는 중…',meaning:'이 조회는 새로운 계산을 시작하지 않습니다.',action:'비용 검사 준비·저장 기록 보기',target:'cost',status:'LOADING'});
 api(frozen.experiment_contract_id,'engine/runs/'+frozen.run_id+'/cost-reference').then(data=>{if(!s.isConnected||run?.run_id!==frozen.run_id)return;renderCost(qualityCostDecision(data,frozen,loaded.parent));}).catch(error=>{if(s.isConnected&&run?.run_id===frozen.run_id)renderCost({question:'비용 판단 근거를 읽을 수 있나요?',answer:'조회 실패로 비용 개선을 판정할 수 없습니다.',meaning:error.message,action:'저장 기록 다시 조회하기',target:'cost',status:'ERROR'});});
 const download=document.createElement('button');download.textContent='이 판단과 실행 근거 내려받기';download.onclick=()=>qualityDownload(model,'quality-judgment-'+a.run_id+'.json');s.append(download);
 return s;
}
function renderQualityProvenance(parent,loaded,frozen){
 const s=qualitySection(parent,'이론·재현·기존 연구 적용 범위');s.dataset.evidence='provenance';
 noteText(s,'이 실행에서 계산한 증거와 과거 연구의 방법을 구분합니다. 지원되는 방법도 실제 실행하지 않았다면 해당 주장을 뒷받침하지 않습니다.');
 evidenceTable(s,['확인하려는 주장','현재 계산기에서 연결된 근거','적용 범위'],[
  ['현재 예산의 탐색 성과','동일 실행 HV·IGD+ 곡선, 목적별 범위','참조는 관측 최종 집합. 100%는 참 Pareto front 달성률이 아님'],
  ['seed 변화의 반복성','같은 설정·NFE 반복 결과와 실제 지배 개선 사례','연결된 반복 수에 한정. 알고리즘 우월성 실험과 별개'],
  ['배치 변경에 대한 개선 여지','원해 재평가, 삭제·추가·이동, 이웃 MILP·ε, 전체 조합','완료한 방법·대상·고정 설치 공간에 한정'],
  ['격자를 바꿔도 목표를 유지하는가','RF/HMSP의 저장 배치 고정 평가점 간격 비교','저장 X와 수량을 유지한 민감도 검사. 실제 실행 기록을 확인하며 EOIR 공개 격자 계약은 미지원'],
  ['모델 수식 자체가 맞는가','독립 Validator의 oracle·수식 검증은 별도 연구','계산기 동일 모델 재생 PASS가 독립 검증을 대신하지 않음'],
  ['목표를 만족하는 비용 하한','RF 영역 목표 ON의 공개 정식화·별도 배치 재평가','하한·실현 상한·관측 최소를 구분. Model 선언 고정 이산 비용 문제이며 독립 oracle·전체 Pareto 증명이 아님']]);
 const cost=document.createElement('button');cost.textContent='이 실행의 비용 검사·별도 배치 근거 보기';cost.onclick=()=>qualityNavigate('cost');s.append(cost);
 const grid=document.createElement('button');grid.textContent='선택 배치의 평가점 간격 비교·저장 기록 보기';grid.onclick=()=>qualityNavigate('grid');s.append(grid);
 const refs=[['반복 해집합 평가 · Knowles 외 (2006)','https://sop.tik.ee.ethz.ch/publicationListFiles/ktz2006a.pdf'],['IGD+ 지배방향 거리 · Ishibuchi 외 (2015)','https://doi.org/10.1145/2739480.2754792'],['평가 방법 선택 지침 · Li 외','https://arxiv.org/abs/2002.09040'],['관심영역과 참조점에 따른 평가','https://arxiv.org/abs/2301.12148']];
 for(const [label,url] of refs){const p=document.createElement('p'),link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener';link.textContent=label;p.append(link);s.append(p);}
 noteText(s,'논문은 평가 방법의 근거입니다. 이 센서 모델의 물리적 타당성이나 이 실행의 우수성을 저자가 검증했다는 뜻은 아닙니다.');
 const p=loaded.parent;evidenceTable(s,['결속 대상','저장 식별값'],[['실행',p.run_id],['설정 SHA256',p.config_sha256],['평가기 SHA256',p.evaluator_sha256],['원시 SHA256',p.raw_sha256]]);
 const b=document.createElement('button');b.textContent='현재 계산 근거 JSON 내려받기';b.onclick=()=>qualityDownload(loaded,'quality-evidence-'+p.run_id+'.json');s.append(b);
 return s;
}
