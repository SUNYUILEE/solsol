'use strict';
// Posthoc analysis only. Never changes objective order, F/G, constraints or solver.
function tradeoffMin(m){return m.direction==='min'||m.direction==='minimize';}
function tradeoffData(source,computePairs=true){
 const finite=r=>Array.isArray(r.F)&&r.F.length>0&&r.F.every(Number.isFinite)&&Array.isArray(r.G)&&r.G.every(Number.isFinite);
 const invalidCount=(source.rows||[]).filter(r=>!finite(r)).length;
 const seen=new Set(),rows=(source.rows||[]).filter(r=>{const k=JSON.stringify(r.X);if(!finite(r)||seen.has(k)||r.installation_audit?.hard_pass===false||r.G.some(g=>g>(source.archive_policy?.tolerance??1e-9)))return false;seen.add(k);return true;});
 const metrics=(source.research_configuration?.objective_ids||[]).map(id=>source.metadata.metrics.find(m=>m.id===id)).filter(Boolean);
 const axes=metrics.map(m=>{const values=rows.map(r=>r.named_metrics?.[m.id]);if(values.some(v=>!Number.isFinite(v)))return {...m,missing:true};const min=Math.min(...values),max=Math.max(...values);return {...m,min,max,constant:min===max};});
 const vectors=[],vseen=new Set();for(const r of rows){const v=metrics.map(m=>r.named_metrics?.[m.id]),k=JSON.stringify(v);if(v.every(Number.isFinite)&&!vseen.has(k)){vseen.add(k);vectors.push(v);}}
 const pairs=[];if(computePairs)for(let i=0;i<axes.length;i++)for(let j=i+1;j<axes.length;j++){let opposing=0,together=0,tied=0;for(let a=0;a<vectors.length;a++)for(let b=0;b<a;b++){const di=(vectors[a][i]-vectors[b][i])*(tradeoffMin(axes[i])?-1:1),dj=(vectors[a][j]-vectors[b][j])*(tradeoffMin(axes[j])?-1:1);if(!di||!dj)tied++;else if(di*dj<0)opposing++;else together++;}pairs.push({i,j,opposing,together,tied});}
 return {rows,axes,vectors:vectors.length,pairs,invalidCount};
}
function tradeoffDelta(a,b,axes){return axes.map(m=>{const raw=b.named_metrics[m.id]-a.named_metrics[m.id];return {id:m.id,raw,display:raw*(m.display_scale||1),better:raw*(tradeoffMin(m)?-1:1)};});}
// Exact saved values, before display rounding. A mode or observed best is not a theoretical bound.
function tradeoffConcentration(data){
 return data.axes.filter(m=>m.id!=='cost').map(m=>{
  const counts=new Map();let n=0,best=null;
  for(const r of data.rows){const v=r.named_metrics?.[m.id];if(!Number.isFinite(v)||(r.metric_status?.[m.id]&&r.metric_status[m.id]!=='DEFINED'))continue;n++;counts.set(v,(counts.get(v)||0)+1);if(best===null||(tradeoffMin(m)?v<best:v>best))best=v;}
  let modalCount=0;for(const count of counts.values())modalCount=Math.max(modalCount,count);
  return {id:m.id,name:m.name,n,excluded:data.rows.length-n,distinct_values:counts.size,modal_count:modalCount,modal_fraction:n?modalCount/n:null,observed_best:best,best_count:n?counts.get(best):0,status:n<2?'INSUFFICIENT_OBSERVATIONS':counts.size===1?'OBSERVED_CONSTANT':'OBSERVED_VARIATION',cause:'NOT_ESTABLISHED'};
 });
}
function tradeoffResearchMethod(){
 return {version:'SOLSOL_SATURATION_METHOD_V1',cause_status:'NOT_ESTABLISHED',
  question:'예산·설치 후보지·목적 구조·탐색 중 무엇이 해의 집중에 기여하는가?',
  branches:[
   {id:'resource',name:'공유 예산',test:'센서 범위·후보지·단가·수량 조건을 고정하고 세 조건을 여러 예산에서 반복',evidence:'같은 예산에서 성능의 손익이 교차하는 원시 배치 쌍·잔여예산·반복 차이',limit:'예산 소진만으로 경쟁을 증명하지 않음',availability:'기존 순서대로 연구에서 실행'},
   {id:'candidate',name:'설치 후보지·경계',test:'물리적으로 허용된 같은 설치 영역에서 후보 표본을 바꾸거나 보강하여 별도 비교',evidence:'같은 평가점에서 재평가한 성능·배치 지도·후보 seed 및 좌표 결속',limit:'후보 변경은 이산 문제 변경; 평가영역 밖 센서를 자동 제외하지 않음',availability:'별도 실험 설계 필요 · 자동 후보 재생성 미연결'},
   {id:'objective',name:'목적의 포화·중복',test:'공개 지표 정의와 상한·이산성을 확인하고 전체/목표 통과 집합을 비교',evidence:'목적별 값 분포·공통 성능 축·공개 상한 근거; 관측 최고와 이론 상한 구별',limit:'동일값 집중은 낮은 차원 Pareto 전선이나 물리적 포화의 증명이 아님',availability:'현재 저장값 진단; 상한·원인 판정은 추가 근거 필요'},
   {id:'search',name:'탐색·참조방향',test:'문제·후보지·평가기를 고정하고 seed·NFE 또는 탐색 방법을 대조',evidence:'같은 실제 평가량의 반복 결과·별도 reference·센서별 배치 다양성',limit:'빈 참조방향이나 지표 정체만으로 탐색 실패를 확정하지 않음',availability:'탐색 민감도는 별도 실험 · 자동 참조벡터 적응 미연결'}],
  verification:'가설 → 한 요인씩 대조 → 같은 공통 성능·비용·G 재평가 → 지도·삭제/이동 근거 → 가설 유지·반박·미확정. 원해와 검산 대안을 분리한다.',
  comparison_rules:['세 군의 공유 자원 계약·단가·설치 조건을 동일하게 명시; 계약 생략을 예산 OFF로 취급하지 않음','같은 seed는 같은 탐색 경로를 보장하지 않음; 실제 초기 X·준비/탐색/재평가/총 평가량·population·참조방향 기록','예산 후보 선택용 관측과 확인용 반복을 분리; 미달·빈 결과·실패도 보존','목적 수가 다른 HV를 직접 비교하지 않고 공통 성능 축과 실제 비용을 비교','단순 양의 배율·정규화는 정확한 Pareto 지배관계를 바꾸지 않음; 선택 연산에 미치는 영향은 별도 검사'],
  execution_design:{status:'DRAFT_NOT_RUN',seeds:null,repetitions:null,search_nfe:null,total_evaluations:null,stop_policy:null,practical_difference_delta:null,tie_tolerance:null,near_bound_tolerance:null,initialization_comparison:null,unresolved_reason:'새 확인 실험의 수치 조건은 아직 확정하지 않았습니다. 기존 실행 화면에서 확인하며 임의 상한을 추가하지 않습니다.',initialization_options:['공통 실현가능 초기 X를 고정한 대조','같은 초기화 정책을 사용하는 전체 과정 비교; 초기화 차이도 효과에 포함'],contrasts:['A↔B: 비용 목적이 있는 조건의 예산 효과','B↔C: 같은 예산의 비용 목적 제거 효과'],limits:['A↔C만으로 두 효과를 분리하지 않음','비용×예산 전체 상호작용 추정은 이 세 군만으로 하지 않음','저장 동일 X를 필터·투영한 대조와 각 군 재최적화의 총 효과를 분리'],budget_binding:['실제 비용 단위와 budget G 방향·허용오차 기록','실현가능 증거 배치·경계/여유 분포 보존','미발견을 불가능 증명으로 쓰지 않음'],outcome_rules:['원래 성능+비용 벡터와 공통 G·목표를 비교; 비용 제외 군도 비용 보존','목표통과와 평균 품질·전체 평가행과 누적 비지배 집합을 구분','seed별 차이·실패율·불확실성 보고; 유리한 예산/지표만 선택하지 않음','strict dominance와 허용 손실 이내 개선을 분리; 분산 증가만으로 개선 판정하지 않음','집중·높은 상관만으로 목적 삭제하지 않음; 제한된 삭제/교환 무개선은 전역 포화 증명 아님']},
  sources:[
   {id:'US20260002919A1',kind:'공개 특허',url:'https://patents.google.com/patent/US20260002919A1/en',locator:'Description: geometric design / FIGS. 4A–4B; claim 1',finding:'가스 센서 배치의 센서 수·관측률 포화·설치 경계 형상',limit:'SOLSOL의 포화 원인이나 자동 적응 효과를 증명하지 않음'},
   {id:'LC-MaOEA (2020)',kind:'논문',url:'https://link.springer.com/article/10.1007/s40747-020-00136-5',locator:'Introduction; Proposed algorithm; Empirical results',finding:'낮은 차원 Pareto 전선에서 참조벡터 생성·탐색 방법 연구',limit:'제한된 문제군의 결과; SOLSOL의 전선 차원·알고리즘 우수성은 별도 검증'},
   {id:'Mavrotas (2009)',kind:'논문',url:'https://doi.org/10.1016/j.amc.2009.03.037',locator:'The epsilon-constraint method',finding:'목적을 제약으로 옮기고 한계를 변화시키는 방법론',limit:'현재 성능 다목적+비용 상한 실험은 이 발상을 활용; AUGMECON 구현·정확 Pareto 증명은 아님'}],
  claim_limit:'기술적 참고자료이며 특허 신규성·권리범위·SOLSOL 원인 판정을 하지 않음'};
}
function tradeoffResearchPlan(f,scope,data){
 const costs=[...new Set(data.rows.map(r=>r.cost).filter(Number.isFinite))].sort((a,b)=>a-b);
 const levels=[...new Set([0,.25,.5,.75,1].map(q=>costs.length?costs[Math.floor(q*(costs.length-1))]:null).filter(v=>v!==null))];
 return {schema:'SOLSOL_CONCENTRATION_STUDY_PLAN_V1',status:'PLAN_ONLY_NOT_EXECUTED',source:{run_id:f.run_id,experiment_contract_id:f.experiment_contract_id,config_sha256:f.config_sha256,evaluator_sha256:f.evaluator_sha256??null,model_service:f.problem?.model_service??null,raw_sha256:f.result_contract?.raw_source?.sha256??null,raw_identity_status:f.result_contract?.raw_source?.sha256?'RECORDED':'NOT_PROVIDED_IN_VIEW',scope,row_ids:data.rows.map(r=>r.id),metrics:data.axes.map(m=>({id:m.id,unit:m.unit??null,direction:m.direction}))},
  hypothesis:'쉬운 목적의 조기 포화가 해 집중에 기여하는가? 원인 미확정.',observations:tradeoffConcentration(data),method:tradeoffResearchMethod(),
  budget_candidates:{values:levels,basis:'선택 집합의 서로 다른 관측 비용 수준을 정렬한 0/25/50/75/100% 순위값; 배치 빈도 가중 없음; 최적 예산이나 절충 발생 경계가 아님',requires_user_confirmation:true},
  arms:[{id:'A',cost_objective:true,budget:null},{id:'B',cost_objective:true,budget:'각 확정 B'},{id:'C',cost_objective:false,budget:'B군과 동일 B'}],
  comparisons:[{arms:['A','B'],question:'예산 제한 효과'},{arms:['B','C'],question:'같은 예산에서 비용 목적 포함 효과'}],
  frozen_source:{config:f.config,research_configuration:f.research_configuration,solver:f.solver},
  controls:['같은 Model 계약·후보지·평가영역·평가점·반경·단가·수량 조건·영역 목표','각 반복의 같은 seed·초기화 정책·탐색 평가량; 달라진 항목은 비교에서 명시','예산 선정용 실행과 확인용 반복을 구분; 반경 변경은 별도 실험'],
  outcomes:['공통 성능 축의 비지배 관계와 목적별 집중도','예산 사용·잔여량과 목표 통과 여부','지도에서 설치 위치·센서별 다른 배치·삭제/이동 대안','미달·빈 집합·실패를 포함한 반복 간 차이'],
  interpretation:'문제 난이도와 optimizer behavior를 진단하는 통제 실험. 절충 증가 자체가 성공 기준은 아니며 이 계획은 실행 요청이 아닙니다.'};
}
function tradeoffBindPlan(plan,receipt){
 if(receipt.run_id!==plan.source.run_id||receipt.experiment_contract_id!==plan.source.experiment_contract_id||receipt.config_sha256!==plan.source.config_sha256||(plan.source.evaluator_sha256&&receipt.evaluator_sha256!==plan.source.evaluator_sha256))throw Error('연구 계획과 저장 원시 출처가 일치하지 않습니다.');
 if(!/^[a-f0-9]{64}$/i.test(receipt.raw_source?.sha256||''))throw Error('저장 원시 해시를 확인할 수 없어 결속된 계획을 저장하지 않았습니다.');
 if(plan.source.raw_sha256&&plan.source.raw_sha256!==receipt.raw_source.sha256)throw Error('연구 계획에 결속된 원시 해시가 변경됐습니다. 계획을 다시 확인하세요.');
 return {...plan,source:{...plan.source,raw_sha256:receipt.raw_source.sha256,raw_identity_status:'VERIFIED_BY_RESULT_CONTRACT'},source_receipt:receipt};
}
function renderTradeoffResearch(host,f,data,scope){
 const details=document.createElement('details'),summary=document.createElement('summary');details.id='tradeoffResearchProcedure';summary.textContent='목적값이 몰리는 이유 연구 · 진단 → 같은 예산 비교 → 지도 확인';details.append(summary);host.append(details);
 noteText(details,'문제 난이도를 조절해 탐색기가 어떤 해와 배치를 찾는지 진단합니다. 한 목적이 쉽게 포화됐다는 설명은 가설입니다. 아래 수치는 현재 선택 집합의 저장값이며 원인을 확정하지 않습니다.');
 evidenceTable(details,['성능 목적','유효 배치','서로 다른 값','가장 많은 동일값 비율','관측 최선값 동률','제외'],tradeoffConcentration(data).map(m=>[m.name,m.n,m.distinct_values,m.n<2?'비교 자료 부족':`${m.modal_count}/${m.n} (${(100*m.modal_fraction).toFixed(1)}%)`,`${m.best_count}/${m.n}`,m.excluded]));
 noteText(details,'반올림 전 값이 정확히 같은 배치를 셉니다. 표시상 같은 수치가 실제로 다를 수 있습니다. 관측 최선값은 모델의 이론 상한이 아닙니다. 목표 통과만 고르면 필터 자체로 값 범위가 좁아질 수 있으므로 전체 집합도 함께 보세요.');
 evidenceTable(details,['단계','비교할 내용','알 수 있는 범위'],[
  ['1. 집중 확인','전체/목표 통과를 바꾸어 목적값과 A/B 지도를 확인','성능의 집중과 설치 위치의 중복을 구분'],
  ['2. 비용 역할 분리','A: 비용 목적 ON·예산 OFF / B: 비용 목적 ON·예산 B / C: 비용 목적 OFF·같은 예산 B','A↔B는 예산 효과, B↔C는 비용 목적 효과'],
  ['3. 난이도 변화','예산별 동일 seed·탐색량으로 반복; 반경 변경은 별도 실험','공유 자원 부족·목적 포화·탐색 부족 가설을 구분'],
  ['4. 지도와 검산','같은 성능 축으로 비교하고 설치 영역·수량·삭제/이동 대안 확인','합리적인 배치인지 확인; 전역 최적성 증명은 아님']]);
 const plan=tradeoffResearchPlan(f,scope,data);noteText(details,`다음 예산 후보: ${plan.budget_candidates.values.join(', ')||'비용 근거 없음'}. 서로 다른 관측 비용 수준을 정렬한 0/25/50/75/100% 순위값이며 배치 빈도로 가중하지 않습니다. 실행 전 조건과 구간을 확정해야 하며, 절충이 반드시 생기는 값은 아닙니다.`);
 const save=document.createElement('button'),saveStatus=document.createElement('p');save.id='tradeoffResearchExport';save.textContent='이 집합의 진단·비교 계획 저장';saveStatus.id='tradeoffResearchSaveStatus';saveStatus.setAttribute('role','status');save.onclick=safe(async()=>{save.disabled=true;saveStatus.textContent='저장 원시 출처를 확인 중입니다. 완료되면 계획 파일을 내려받습니다.';try{const receipt=await api(f.experiment_contract_id,'engine/runs/'+f.run_id+'/contract');if(!details.isConnected||run?.run_id!==f.run_id||run?.config_sha256!==f.config_sha256||draft.sensor!==f.experiment_contract_id)return;qualityDownload(tradeoffBindPlan(plan,receipt),`research-plan-${f.run_id}-${scope}.json`);saveStatus.textContent='원시 출처에 결속한 계획 파일을 저장했습니다. 새 계산은 시작하지 않았습니다.';}catch(e){saveStatus.textContent='계획 저장 실패: '+e.message;throw e;}finally{save.disabled=false;}});details.append(save,saveStatus);
 const execute=document.createElement('button');execute.id='tradeoffResearchOpen';execute.textContent='이 저장 조건으로 순서대로 연구 열기';execute.disabled=typeof openGuidedCostBudget!=='function';execute.onclick=safe(async()=>{if(run?.run_id!==f.run_id||run?.config_sha256!==f.config_sha256||draft.sensor!==f.experiment_contract_id)throw Error('분석한 저장 실행이 바뀌었습니다. 절충 분석을 다시 여세요.');const dialog=host.closest('dialog');if(dialog){dialog.close();dialog.remove();}await openGuidedCostBudget();});details.append(execute);
 noteText(details,'계획 저장과 연구 화면 열기는 계산을 시작하지 않습니다. 연구 화면에서 예산 산출 집합·예산 후보를 다시 선택하고 세 조건 비교를 확인하세요. 이 화면의 분석 필터를 실행 조건으로 자동 적용하지 않습니다. 기존 2군 결과만으로 비용 역할과 예산 효과를 각각 증명했다고 해석하지 않습니다.');
 noteText(details,'값 몰림의 다른 원인은 지표의 상한 처리, 목적 간 중복, 이산적인 설치 조건, 부족한 탐색입니다. 비용을 제한해도 성능 간 경쟁은 보장되지 않습니다. 실제 조건에서 나타나는 구조를 설명하는 것이 연구의 목적입니다.');
 const method=plan.method,more=document.createElement('details'),label=document.createElement('summary');more.id='tradeoffMethodEvidence';label.textContent='특허·논문에서 무엇을 적용하나요? · 원인별 대조 방법';more.append(label);details.append(more);
 noteText(more,'비용·예산 비교는 자원 조건의 영향부터 확인하는 실험입니다. 설치 후보지의 한계나 참조방향의 문제까지 해결했다는 뜻은 아닙니다.');
 evidenceTable(more,['확인할 원인 가설','대조 방법','필요한 근거·판정 한계','현재 기능'],method.branches.map(x=>[x.name,x.test,x.evidence+' · '+x.limit,x.availability]));
 noteText(more,method.verification);for(const rule of method.comparison_rules)noteText(more,rule);
 noteText(more,'내보내는 계획은 아직 실행 전입니다. 반복 seed·평가량·실질 차이 기준·동률 허용오차는 미확정으로 저장합니다. 같은 초기 배치를 쓰는 대조와 같은 초기화 정책의 전체 과정 비교를 구분해야 합니다. 세 군만으로 비용×예산의 전체 상호작용을 추정하지 않습니다.');
 for(const source of method.sources){const a=document.createElement('a');a.href=source.url;a.target='_blank';a.rel='noopener';a.textContent=source.kind+' · '+source.id;more.append(a);noteText(more,source.finding+' — '+source.limit);}
 noteText(more,method.claim_limit);
}
// Descriptive saved-set checks. Exact equality does not infer physical saturation.
function tradeoffDiagnosis(f,data){
 const performance=data.axes.filter(m=>m.id!=='cost'),groups=new Map(),witnesses=[];
 let missingPerformance=0,missingCost=0;
 for(const r of data.rows){
  if(!performance.length||performance.some(m=>!Number.isFinite(r.named_metrics?.[m.id])||(r.metric_status?.[m.id]&&r.metric_status[m.id]!=='DEFINED'))){missingPerformance++;continue;}
  if(!Number.isFinite(r.cost)){missingCost++;continue;}
  const key=JSON.stringify(performance.map(m=>r.named_metrics[m.id]));
  if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);
 }
 for(const group of groups.values()){
  const best=group.reduce((a,b)=>b.cost<a.cost?b:a);
  for(const r of group)if(r.cost>best.cost)witnesses.push({raw_id:r.id,cheaper_raw_id:best.id,cost:r.cost,cheaper_cost:best.cost,saving:r.cost-best.cost});
 }
 const costs=data.rows.map(r=>r.cost).filter(Number.isFinite),budget=f.config?._resource_contract?.budget;
 const performanceRanges=performance.map(m=>{const v=data.rows.filter(r=>!r.metric_status?.[m.id]||r.metric_status[m.id]==='DEFINED').map(r=>r.named_metrics?.[m.id]).filter(Number.isFinite);return {...m,n:v.length,excluded:data.rows.length-v.length,min:v.length?Math.min(...v):null,max:v.length?Math.max(...v):null};});
 const coverage=(f.metadata?.coverage_metrics||[]).map(m=>{const v=data.rows.map(r=>r.coverage_metrics?.[m.id]).filter(Number.isFinite);return {...m,n:v.length,missing:data.rows.length-v.length,min:v.length?Math.min(...v):null,max:v.length?Math.max(...v):null,at100:v.filter(x=>x===100).length};});
 return {costObjective:data.axes.some(m=>m.id==='cost'),costExcluded:f.solver?.objective_projection?.excluded?.some(m=>m.objective_id==='cost')===true,
  budget:budget?.mode==='MAX'&&Number.isFinite(budget.limit)?budget.limit:null,costMin:costs.length?Math.min(...costs):null,costMax:costs.length?Math.max(...costs):null,
  atBudget:budget?.mode==='MAX'?costs.filter(c=>c===budget.limit).length:null,coverage,performanceRanges,witnesses,missingPerformance,missingCost};
}
function renderTradeoffDiagnosis(host,f,data){
 const q=tradeoffDiagnosis(f,data),section=document.createElement('details'),heading=document.createElement('summary');
 section.id='tradeoffDiagnosis';heading.textContent='현재 해집합 진단 · 비용 역할·포화·과배치';section.append(heading);host.append(section);
 const role=q.costExcluded?'비용을 선택했지만 고정비용 근거로 탐색 축에서 제외했습니다.':q.costObjective?'비용 최소화가 목적함수에 포함된 실행입니다.':'비용 최소화가 목적함수에 없는 실행입니다. 같은 성능의 더 비싼 배치도 남을 수 있습니다.';
 noteText(section,role+(q.budget!==null?` 동시에 예산 ${q.budget} 이하로 제한했습니다. 예산 상한은 최저 비용을 뜻하지 않습니다.`:' 공통 예산 상한은 기록되지 않았습니다.'));
 noteText(section,`분석 집합의 비용 ${q.costMin??'미기록'}–${q.costMax??'미기록'}`+(q.budget!==null?` · 상한과 정확히 같은 배치 ${q.atBudget}개`:'')+' · 예산을 채웠다는 사실만으로 절충·최적성을 판정하지 않습니다.');
 evidenceTable(section,['실제 성능 목적','관측 최저','관측 최고','관측 상태','미관측·결측 제외'],q.performanceRanges.map(m=>[m.name,m.n?valueText(m,m.min):'미기록',m.n?valueText(m,m.max):'미기록',!m.n?'판정 불가':m.min===m.max?'이 집합에서 동일':'차이 있음',m.excluded]));
 if(q.coverage.length)evidenceTable(section,['영역 지표 · 목적과 구분','관측 범위 (%)','정확히 100%인 배치','결측'],q.coverage.map(m=>[m.name,m.n?`${m.min.toFixed(4)}–${m.max.toFixed(4)}`:'미기록',`${m.at100} / ${m.n}`,m.missing]));
 noteText(section,'영역 100%와 품질 목적의 포화는 다릅니다. 관측값이 같거나 상한에 몰린 것만으로 물리적 포화·지표 손실·탐색 실패를 구분할 수 없습니다.');
 noteText(section,`기록된 모든 성능 목적이 정확히 같은데 더 저렴한 관측 대안이 있는 배치: ${q.witnesses.length}개. 성능 결측 ${q.missingPerformance}개, 그 밖의 비용 결측 ${q.missingCost}개는 이 검사에서 제외합니다. 센서 삭제 검산과 별개이며 원시 해를 제거하지 않습니다.`);
 if(q.witnesses.length)evidenceTable(section,['배치','더 저렴한 배치','비용 변화','절감'],q.witnesses.slice(0,10).map(w=>['행 '+w.raw_id,'행 '+w.cheaper_raw_id,`${w.cost} → ${w.cheaper_cost}`,w.saving]));
 noteText(section,'과배치 여부는 해품질·검산에서 센서 1개 삭제 후 같은 평가기로 성능·설치 제약·비용을 확인하세요. 정확 수량 제약에서는 삭제가 불가능할 수 있으므로 이동·교환을 검사합니다.');
 noteText(section,'다음 연구: 같은 후보지·평가점·모델·단가를 고정 → 비용 목적 포함/제외를 같은 예산에서 비교 → 예산 구간별 반복 → 후보 seed와 탐색 seed를 분리하고 같은 NFE로 비교 → 원래 모든 목적과 비용으로 다시 비지배 판정. 낮은 성능 구간에서 대안을 못 찾았다는 사실은 그 대안이 없다는 증명이 아닙니다.');
 noteText(section,'현재 진단은 저장된 관측 집합의 설명입니다. 250세대, Hamming 다양성, 자체 archive 대비 HV/IGD만으로 해집합 전체의 충분한 탐색이나 전역 최적성을 인증하지 않습니다.');
}
function tradeoffSvg(parent,tag,attrs={},text){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;parent.append(e);return e;}
async function tradeoffPairsAsync(data,current){const seen=new Set(),vectors=data.rows.map(r=>data.axes.map(m=>r.named_metrics[m.id])).filter(v=>{const k=JSON.stringify(v);if(seen.has(k))return false;seen.add(k);return true;}),pairs=[];for(let i=0;i<data.axes.length;i++)for(let j=i+1;j<data.axes.length;j++){let opposing=0,together=0,tied=0;for(let a=0;a<vectors.length;a++){if(a%64===0){await new Promise(resolve=>setTimeout(resolve,0));if(!current())return null;}for(let b=0;b<a;b++){const di=(vectors[a][i]-vectors[b][i])*(tradeoffMin(data.axes[i])?-1:1),dj=(vectors[a][j]-vectors[b][j])*(tradeoffMin(data.axes[j])?-1:1);if(!di||!dj)tied++;else if(di*dj<0)opposing++;else together++;}}pairs.push({i,j,opposing,together,tied});}return pairs;}
async function openTradeoff(){
 if(!configured()||!terminal.has(run.state))return;
 const cid=run.experiment_contract_id,rid=run.run_id,hash=run.config_sha256;
 $('tradeoffDialog')?.remove();const originQuality=$('qualityDialog')?.open;const d=document.createElement('dialog');d.id='tradeoffDialog';d.className='tradeoffDialog';const head=document.createElement('div');head.className='dialogHead';const title=document.createElement('h2');title.textContent='배치를 바꾸면 무엇을 얻고 잃나요?';const close=document.createElement('button');close.textContent=originQuality?'품질 질문으로 돌아가기':'닫기';close.onclick=()=>{d.close();d.remove();if(originQuality)$('qualityDialog')?.querySelector('[data-quality-target="tradeoff"]')?.focus({preventScroll:true});};head.append(title,close);d.append(head);const body=document.createElement('div');d.append(body);document.body.append(d);d.showModal();noteText(body,'최종 해집합의 실제 목적값을 읽는 중… 추가 최적화는 실행하지 않습니다.');
 try{const p=await api(cid,(cid===EO?'jobs/':'runs/')+rid),f=M.normalize(p,cid,rid);if(!d.isConnected)return;if(run?.run_id!==rid||draft.sensor!==cid){d.remove();return;}if(f.run_id!==rid||f.config_sha256!==hash)throw Error('실행·조건 결속 불일치');body.replaceChildren();renderTradeoff(body,f);}catch(e){if(d.isConnected){body.replaceChildren();noteText(body,'절충 분석을 불러오지 못했습니다: '+e.message);}}
}
function tradeoffScopeData(f,scope='all'){
 if(!['all','targets'].includes(scope))throw Error('지원하지 않는 절충 분석 집합');
 const all=tradeoffData(f,false),goals=f.research_configuration?.goals,hasGoals=goals&&Object.keys(goals).length>0;
 if(scope==='targets'&&!hasGoals)throw Error('저장 목표가 없어 목표 통과 집합을 선택할 수 없습니다.');
 const qualified=all.rows.filter(r=>r.qualified===true),unknown=all.rows.filter(r=>typeof r.qualified!=='boolean');
 return {data:scope==='targets'?tradeoffData({...f,rows:qualified},false):all,allCount:all.rows.length,qualifiedCount:qualified.length,unknownCount:unknown.length,hasGoals};
}
function renderTradeoff(host,f,scope='all'){
 const scoped=tradeoffScopeData(f,scope),data=scoped.data,{rows,axes}=data;host.replaceChildren();host.dataset.runId=f.run_id;host.dataset.scope=scope;
 const scopeControls=document.createElement('div');scopeControls.className='tradeoffSelectors';host.append(scopeControls);
 selectControl(scopeControls,'분석할 해집합',[['all',`전체 누적 비지배해 · ${scoped.allCount}개`],...(scoped.hasGoals?[['targets',`저장 목표 통과 누적 비지배해 · ${scoped.qualifiedCount}개`]]:[])],scope,v=>renderTradeoff(host,f,v),'tradeoffScope');
 noteText(host,`실행 ${f.run_id.slice(0,8)} · ${scope==='targets'?'저장 목표 통과':'전체'} 누적 비지배 ${rows.length}배치 · 서로 다른 목적값 ${data.vectors}종. 마지막 저장 세대까지 누적 평가한 비지배 집합이며 지도 페이지·센서별 중복 제거와 별도로 분석합니다.`);
 noteText(host,'그래프·A/B·목표/비용 표는 위에서 선택한 같은 집합을 사용합니다. 축 범위는 현재 분석 집합에 맞추므로 다른 집합의 그림 높이만으로 성능을 비교하지 마세요.');
 if(rows.length)renderTradeoffDiagnosis(host,f,data);
 renderTradeoffResearch(host,f,data,scope);
 if(!scoped.hasGoals)noteText(host,'저장된 영역 목표가 없어 목표 통과 집합을 제공하지 않습니다.');
 else if(scoped.unknownCount)noteText(host,`전체 집합 중 목표 판정 미기록 ${scoped.unknownCount}개는 통과 집합에 넣지 않습니다.`);
 if(data.invalidCount)noteText(host,`평가 수치 오류·미기록 ${data.invalidCount}배치는 절충 비교에서 제외했습니다. 성능 0이나 제약 충족으로 해석하지 않습니다.`);
 if(!rows.length){noteText(host,data.invalidCount?'평가 수치 오류·미기록으로 제외된 배치가 있어 절충 비교를 구성할 수 없습니다. 이 상태만으로 모든 배치가 제약 미달이라고 판단하지 않습니다.':scope==='targets'?'저장 목표 통과가 확인된 누적 비지배 배치가 없습니다. 전체 집합으로 바꾸어 목표 미달과 성능 절충을 확인하세요.':'비교 가능한 누적 비지배 배치가 없습니다. 탐색 기록의 평가 수와 제약 판정을 확인하세요.');return;}
 const nav=document.createElement('div');nav.className='qualityNavigation';host.append(nav);const chartPanel=document.createElement('section'),goalPanel=document.createElement('section');host.append(chartPanel,goalPanel);
 for(const [label,p] of [['1. 목적 간 성능 교환',chartPanel],['2. 목표 달성과 비용',goalPanel]]){const b=document.createElement('button');b.textContent=label;b.onclick=()=>{chartPanel.hidden=p!==chartPanel;goalPanel.hidden=p!==goalPanel;for(const x of nav.children)x.setAttribute('aria-pressed',String(x===b));};nav.append(b);}nav.firstChild.click();
 noteText(chartPanel,'한 배치의 탐지 성능을 높일 때 식별·RF 품질 또는 비용에서 어떤 손해가 생기는지 비교합니다. 모든 목적이 좋아지는 경우는 절충이 아니라 개선입니다.');
 if(axes.some(m=>m.missing)){noteText(chartPanel,'일부 목적값이 누락되어 성능 교환 그래프는 미계산입니다. 목표 달성과 비용 탭에서 남아 있는 근거를 확인할 수 있습니다. 누락을 0으로 표시하지 않습니다.');}else{
 for(const m of axes.filter(m=>m.constant))noteText(chartPanel,`${m.name}: 모든 최종 배치에서 ${valueText(m,m.min)}로 같습니다. 이 집합에서는 절충을 구분하지 않는 축입니다.`);
 const controls=document.createElement('div');controls.className='tradeoffSelectors';chartPanel.append(controls);const primary=axes.find(m=>!m.constant)||axes[0],ordered=[...rows].sort((a,b)=>(a.named_metrics[primary.id]-b.named_metrics[primary.id])*(tradeoffMin(primary)?1:-1));let aid=ordered[0].id,bid=ordered.at(-1).id;
 const opts=ordered.map(r=>[String(r.id),`행 ${r.id} · ${valueText(primary,r.named_metrics[primary.id])}`]);
 selectControl(controls,'기준 A',opts,String(aid),v=>{aid=+v;draw();},'tradeoffA');selectControl(controls,'대안 B',opts,String(bid),v=>{bid=+v;draw();},'tradeoffB');
 const plot=document.createElement('div');plot.className='tradeoffPlot';chartPanel.append(plot);const comparison=document.createElement('div');comparison.id='tradeoffComparison';chartPanel.append(comparison);
 function draw(){plot.replaceChildren();comparison.replaceChildren();const a=rows.find(r=>r.id===aid),b=rows.find(r=>r.id===bid),w=Math.max(680,axes.length*170),svg=tradeoffSvg(plot,'svg',{viewBox:`0 0 ${w} 330`,role:'img','aria-label':'최종 목적값 평행좌표: 회색 전체 배치, 파랑 기준 A, 주황 대안 B'}),x=j=>75+j*(w-150)/Math.max(1,axes.length-1),y=(r,m)=>m.constant?155:260-210*(tradeoffMin(m)?(m.max-r.named_metrics[m.id])/(m.max-m.min):(r.named_metrics[m.id]-m.min)/(m.max-m.min));
 axes.forEach((m,j)=>{tradeoffSvg(svg,'line',{x1:x(j),x2:x(j),y1:50,y2:260,stroke:'#afbbc2'});tradeoffSvg(svg,'text',{x:x(j),y:22,'text-anchor':'middle','font-size':11},m.name);tradeoffSvg(svg,'text',{x:x(j),y:40,'text-anchor':'middle','font-size':11},valueText(m,tradeoffMin(m)?m.min:m.max));tradeoffSvg(svg,'text',{x:x(j),y:280,'text-anchor':'middle','font-size':11},valueText(m,tradeoffMin(m)?m.max:m.min));});
 function line(r,color,width){const path=tradeoffSvg(svg,'polyline',{points:axes.map((m,j)=>`${x(j)},${y(r,m)}`).join(' '),fill:'none',stroke:color,'stroke-width':width,'stroke-opacity':width===1?.25:1,'data-row-id':r.id});tradeoffSvg(path,'title',{},`행 ${r.id}: `+axes.map(m=>m.name+' '+valueText(m,r.named_metrics[m.id])).join(' / '));if(width===1)path.onclick=()=>{bid=r.id;$('tradeoffB').value=String(bid);draw();};}
 const shown=rows.length>1000?Array.from({length:1000},(_,i)=>rows[Math.floor(i*(rows.length-1)/999)]):rows;shown.forEach(r=>line(r,'#526d7b',1));line(a,'#007ca3',4);line(b,'#bc6200',3);tradeoffSvg(svg,'text',{x:75,y:314,'font-size':12},`파랑 A ${a.id} / 주황 B ${b.id} · 위쪽일수록 좋음 · 같은 축 안에서 비교`);
 const delta=tradeoffDelta(a,b,axes),g=delta.filter(x=>x.better>0),loss=delta.filter(x=>x.better<0),verdict=document.createElement('p');verdict.className='qualityVerdict';verdict.textContent=aid===bid?'같은 배치를 선택했습니다. 다른 대안 B를 골라 비교하세요.':g.length&&loss.length?`A → B: ${g.length}개 목적은 좋아지고 ${loss.length}개 목적은 나빠집니다. 어느 성능을 더 중시하는지 판단하는 절충입니다.`:g.length?'B가 비교한 모든 목적에서 나쁘지 않고 하나 이상 좋습니다.':loss.length?'A가 비교한 모든 목적에서 나쁘지 않고 하나 이상 좋습니다.':'설치가 달라도 목적값은 모두 같습니다. 성능 절충 없이 위치 대안을 비교할 수 있습니다.';comparison.append(verdict);
 evidenceTable(comparison,['목적','기준 A','대안 B','B로 바꿀 때'],axes.map((m,i)=>[m.name,valueText(m,a.named_metrics[m.id]),valueText(m,b.named_metrics[m.id]),`${delta[i].display>0?'+':''}${delta[i].display.toFixed(4)} ${m.unit==='%'?'%p':m.unit||''} · ${delta[i].better>0?'개선':delta[i].better<0?'저하':'동일'}`]));
 let h=0;for(let i=0;i<a.X.length;i++)for(let j=0;j<a.X[i].length;j++)h+=a.X[i][j]!==b.X[i][j];noteText(comparison,`설치 선택 ${h}비트 차이(Hamming). 센서 한 대 이동은 보통 2비트이며 성능 점수가 아닙니다.`);
 const maps=document.createElement('details'),s=document.createElement('summary');s.textContent='A와 B 설치 지도 비교';maps.append(s);maps.ontoggle=()=>{if(run?.run_id!==f.run_id||draft.sensor!==f.experiment_contract_id){maps.replaceChildren();noteText(maps,'실행이 바뀌었습니다. 현재 실행에서 절충 비교를 다시 여세요.');return;}if(maps.open&&maps.children.length===1){const box=document.createElement('div');box.className='qualityCompareMaps';for(const [label,r] of [['기준 A',a],['대안 B',b]]){const panel=document.createElement('div');noteText(panel,label+' · 행 '+r.id);panel.insertAdjacentHTML('beforeend',qualityGeometryMap(f.problem,r));box.append(panel);}maps.append(box);}};comparison.append(maps);
 }
 draw();noteText(chartPanel,'평행좌표는 각 목적의 관측 최저–최고 범위를 같은 높이에 맞춥니다. 선의 교차는 인접 목적의 순위 교환을 보여주며, 축 간 높이 차이를 물리적 성능 차이로 읽지 않습니다. 회색 선을 누르거나 대안 B에서 배치를 고르세요. 1,000개 초과 집합은 배경선만 균등 간격 1,000개를 표시하며 모든 배치는 선택 목록에서 고를 수 있습니다.');
 const details=document.createElement('details'),sum=document.createElement('summary');sum.textContent='목적 두 개씩 경쟁 관계 확인 · 계산 방법과 논문';details.append(sum);chartPanel.append(details);let pairStarted=false;details.ontoggle=async()=>{if(!details.open||pairStarted)return;pairStarted=true;const status=document.createElement('p');status.textContent='모든 목적값 쌍의 관계를 계산 중… 창을 닫으면 중단합니다.';details.append(status);const pairs=await tradeoffPairsAsync(data,()=>chartPanel.isConnected&&details.isConnected&&run?.run_id===f.run_id&&draft.sensor===f.experiment_contract_id);if(!pairs)return;status.textContent=`서로 다른 목적값 ${data.vectors}종의 모든 쌍. 관측 집합의 관계이며 모델 전체의 인과관계가 아닙니다.`;evidenceTable(details,['목적 쌍','서로 반대 방향 변화','함께 좋아짐/나빠짐','한 축 이상 동률'],pairs.map(p=>[axes[p.i].name+' / '+axes[p.j].name,p.opposing,p.together,p.tied]));};const link=document.createElement('a');link.href='https://arxiv.org/abs/1705.00368';link.target='_blank';link.rel='noopener';link.textContent='Li·Zhen·Yao: 다목적 해집합의 평행좌표 해석';details.append(link);
 }
 const goals=f.research_configuration.goals,qualified=goals?rows.filter(r=>r.qualified===true):[],unknown=goals?rows.filter(r=>typeof r.qualified!=='boolean').length:0,costs=rows.map(r=>r.cost).filter(Number.isFinite),missingCosts=rows.length-costs.length,costMin=Math.min(...costs),costMax=Math.max(...costs);noteText(goalPanel,'여기서는 선택한 영역 커버율 목표와 비용을 비교합니다. 모델의 품질·재고·설치 제약은 별도로 유지됩니다. 목적값과 영역 커버율은 정의가 다를 수 있어 아래에 따로 표시합니다.');
 const message=document.createElement('p');message.className='qualityVerdict';message.textContent=costMin===costMax?(f.solver?.objective_projection?.excluded?.some(m=>m.objective_id==='cost')?`고정비용 근거가 있는 실행입니다. 선택한 모든 배치의 비용은 ${costMin}이며 목표를 낮추어도 같은 고정 수량·단가 조건의 비용은 같습니다.`:`이번 선택 집합에서는 비용이 모두 ${costMin}로 같습니다. 관측한 값이 같다는 뜻이며 다른 배치의 저비용 가능성까지 배제하지 않습니다.`):goals?qualified.length?`선택 집합의 관측 최저 비용 ${costMin} → 저장 목표 통과가 확인된 배치의 관측 최저 비용 ${Math.min(...qualified.map(r=>r.cost))}. 이 실행에서 찾은 대안끼리 비교한 값입니다.`:unknown?'목표 통과가 확인된 배치는 0개이며 판정 미기록 배치가 있습니다. 전부 목표 미달이라고 판단할 수 없습니다.':'현재 선택 집합에 저장 영역 목표를 모두 만족하는 배치가 없습니다.':'영역 커버율 목표를 설정하지 않았습니다. 모델 제약은 유지되며 성능과 비용의 교환은 첫 화면에서 비교합니다.';goalPanel.append(message);
 if(goals)noteText(goalPanel,`저장 영역 목표 통과 확인 ${qualified.length} / ${rows.length}배치 · 판정 미기록 ${unknown}개. 미기록을 미달로 간주하지 않습니다. 이는 관측 구성 비율이며 성공 확률이 아닙니다.`);
 if(missingCosts)message.textContent=`비용 기록 ${costs.length}개 · 미기록 ${missingCosts}개. ${costs.length?'기록된 배치 중 관측 최저 비용은 '+costMin+'입니다.':'비용을 비교할 기록이 없습니다.'} 전체 집합의 최저 비용이나 고정비용을 단정하지 않습니다.`;
 const gs=f.metadata.coverage_metrics||[],table=document.createElement('div');table.className='tradeoffTable';goalPanel.append(table);evidenceTable(table,['배치','비용',...gs.map(m=>m.name+(goals?.[m.id]!=null?' (목표 '+goals[m.id]+')':'')),'영역 목표 판정'],[...rows].sort((a,b)=>(Number.isFinite(a.cost)?a.cost:Infinity)-(Number.isFinite(b.cost)?b.cost:Infinity)||a.id-b.id).slice(0,100).map(r=>['행 '+r.id,Number.isFinite(r.cost)?r.cost:'미기록',...gs.map(m=>Number.isFinite(r.coverage_metrics?.[m.id])?r.coverage_metrics[m.id].toFixed(2):'미기록'),qualityQualification(r,goals)]));
 noteText(goalPanel,'위 표는 비용순 첫 100개까지 표시합니다. 전체 배치의 목적과 지도는 첫 탭의 선택 목록에서 확인할 수 있습니다. 다른 수량·비용 조건을 시험하려면 설정을 복사하여 별도 실행하세요. 여기서 목표 필터를 바꾸거나 그래프를 읽는 것은 재최적화가 아닙니다.');
}

function renderExecutionGuide(){
 let bar=$('executionGuide');if(!bar){bar=document.createElement('nav');bar.id='executionGuide';bar.setAttribute('aria-label','계산과 검산 진행 순서');$('notice').after(bar);}
const restriction=typeof savedRunCopyRestriction==='function'?savedRunCopyRestriction():null,copyButton=$('copyRun');
 if(restriction){copyButton.disabled=true;copyButton.textContent='이전 조건 복사 미지원';copyButton.dataset.readOnlyCopy='true';}else if(copyButton.dataset.readOnlyCopy){delete copyButton.dataset.readOnlyCopy;copyButton.disabled=creating||!run;copyButton.textContent='현재 결과 조건을 초안으로 복사';}
const active=run&&!terminal.has(run.state),copying=typeof configurationCopyPending!=='undefined'&&configurationCopyPending,editing=mode==='design',ready=!active&&!copying&&!previewPending&&!previewFailure&&!$('calculate').disabled,hasResult=run&&terminal.has(run.state),failed=!!draft&&((typeof configurationCopyError!=='undefined'&&configurationCopyError?.cid===draft.sensor&&configurationCopyError?.run_id===run?.run_id&&configurationCopyError?.message)||(typeof selection==='function'&&selection()?.saved_seed_error)),key=[active,ready,hasResult,run?.run_id,run?.state,mode,copying,previewPending,previewFailure,failed,restriction?.message,run?.error,run?.runtime_diagnostic?.error,run?.storage_complete].join('|');if(bar.dataset.key===key)return;bar.dataset.key=key;bar.replaceChildren();
 const message=document.createElement('span');message.textContent=copying?'저장 조건 복사 중 · 완료 후 새 조건을 확인합니다':active?(typeof runtimeProgressText==='function'&&['verifying','saving'].includes(run.state)?runtimeProgressText(run):'계산 중 · 세대 결과는 자동 갱신됩니다'):editing?(previewFailure?'새 조건 확인 실패 · 입력은 유지됩니다. 1. 조건 확인을 눌러 다시 시도하세요.':ready?'새 조건 확인 완료 · 다음: 계산 시작':failed?'불러오기 실패 · 입력은 유지됩니다. 다시 불러오기 버튼을 눌러주세요.':'새 조건 확인 대기 · 확인이 끝나면 계산 시작 버튼이 활성화됩니다'):hasResult?'저장 결과 · 다음: 해를 비교하고 품질을 확인하세요':ready?'설정 확인 완료 · 계산 시작 가능':'먼저 공통 영역·센서·목적·계산 조건을 확인하세요';bar.append(message);
 if(hasResult&&(run.error||run.runtime_diagnostic?.error)){const reason=document.createElement('span');reason.id='runFailureReason';reason.setAttribute('role','alert');reason.textContent=(run.termination_reason==='STORAGE_ERROR'||run.storage_complete===false?'최종 저장 미완료 · ':'실행 실패 · ')+(run.error||run.runtime_diagnostic.error)+(run.runtime_diagnostic?' · 종료 진단 기록이며 최종 저장을 증명하지 않습니다.':'')+' · 저장된 원시·중간 결과를 유지합니다. 조건을 복사해 확인 후 다시 계산할 수 있습니다.';bar.append(reason);}
 if(restriction&&!active&&!copying){message.textContent=restriction.message;const fresh=document.createElement('a');fresh.href='live.html?contract='+encodeURIComponent(draft.sensor);fresh.target='_blank';fresh.rel='noopener';fresh.textContent='현재 RF 모델 새 설정 열기';fresh.className='button';bar.append(fresh);}
 const actions=[['1. 조건 확인',safe(async()=>{workbench?.setTask('settings');if(editing&&(previewPending||previewFailure))await apply();}),false],['2. 계산 시작',()=>$('calculate').click(),!ready],['3. 절충 비교',()=>openTradeoff(),!hasResult||!configured()],['4. 품질·검산',()=>openQualityCenter(),!hasResult]];
 actions.forEach(([text,fn,disabled],i)=>{const b=document.createElement('button');b.textContent=text;b.disabled=disabled;b.dataset.flowStep=i+1;b.onclick=fn;if(!disabled&&((editing&&ready&&i===1)||(!editing&&hasResult&&i===2)))b.className='nextAction';bar.append(b);});
 $('calculate').classList.toggle('nextAction',ready&&editing);
 if($('qualityCenter'))$('qualityCenter').disabled=!!active;
}
const guideFetch=fetchRun;fetchRun=async function(...args){await guideFetch(...args);renderExecutionGuide();};
const guideSettings=renderSettings;renderSettings=function(){guideSettings();renderExecutionGuide();};
const guideClear=clearRun;clearRun=function(){guideClear();renderExecutionGuide();};
window.addEventListener('DOMContentLoaded',renderExecutionGuide);
