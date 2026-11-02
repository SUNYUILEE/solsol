'use strict';
window.LiveSolutionQuality=(()=>{
 const qualitySetStyles=document.createElement('link');qualitySetStyles.rel='stylesheet';qualitySetStyles.href='live-solution-quality-v73.css';document.head.appendChild(qualitySetStyles);
 let serial=0,key='',cache=new Map(),setContext=null,setResult=null,setSelected=null,setRequestSerial=0,robustProof=null,robustProofSerial=0,robustProofAvailable=false,multiSeedData=null,multiSeedSerial=0,multiSeedActiveJobId=null;
 const $=id=>document.getElementById(id),pct=v=>(100*v).toFixed(1)+'%';
 const names={EMPIRICALLY_NONDOMINATED:'관측 집합에서 비지배',WARNING_DOMINANCE_WITNESS:'지배 반례 발견',BOUNDED_INCONCLUSIVE:'범위 내 결론 유보',NOT_CHECKED:'검사하지 않음',NOT_ASSESSED:'평가하지 않음'};
 function setRobustProofControl(supported,available=false){
  robustProofAvailable=supported&&available;
  const button=$('robustCostProof'),status=$('robustCostProofStatus');
  if(button){
   button.disabled=!robustProofAvailable;
   button.textContent=supported?'최소비용 정밀검산':'현재 목적함수에서는 정밀검산 미지원';
   button.title=supported?'500m·250m 두 격자 비용 범위를 비용별로 검산합니다.':'현재 목적함수에는 외곽 탐지·내부 식별 구역이 없어 V7용 두 격자 비용 검산을 적용하지 않습니다.';
  }
  if(!supported&&status)status.textContent='고장이 아닙니다. 현재 목적함수 계약에는 외곽 탐지·내부 식별 구역이 없으므로 V7 전용 500m·250m 동시통과 최소비용 검산을 실행하지 않습니다.';
  else if(!available&&status)status.textContent='신뢰성 근거 계산 후, 지원되는 목적함수 계약에서 비용별 가능성을 검사합니다.';
 }
 async function pointDigest(point){const bits=point.mask.flatMap(state=>[(state===1||state===3)?1:0,(state===2||state===3)?1:0]),bytes=new Uint8Array(bits);return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');}
 function ensureMultiSeedControls(){
  if($('multiSeedProgressWrap'))return;
  const button=$('multiSeedCalculate');if(!button)return;
  const actions=document.createElement('span');actions.className='multiSeedActions';button.before(actions);actions.append(button);
  const cancel=document.createElement('button');cancel.type='button';cancel.id='multiSeedCancel';cancel.className='ghost';cancel.hidden=true;cancel.textContent='계산 중단';actions.append(cancel);
  const progress=document.createElement('div');progress.id='multiSeedProgressWrap';progress.className='multiSeedProgress';progress.hidden=true;progress.innerHTML='<progress id="multiSeedProgress" max="100" value="0"></progress><span id="multiSeedProgressText">0%</span>';
  button.closest('.sectionHead')?.after(progress);
 }
 function cls(node,value){node.classList.remove('pass','warn','fail');node.classList.add(value);}
 const blockedIds=['currentMap','currentCostSummary','currentContext','deploymentDelta','resultTable'];
 function gate(state){
  LiveExport?.setQualityGate?.(state);LiveGridCheck?.setQualityGate?.(state);
  const hard=state.integrity==='FAIL';blockedIds.forEach(id=>{const node=$(id);if(!node)return;node.classList.toggle('qualityDataBlocked',hard);if(node.style){node.style.filter=hard?'grayscale(1)':'';node.style.opacity=hard?'.36':'';node.style.pointerEvents=hard?'none':'';node.style.userSelect=hard?'none':'';}});
  const notice=$('selectedTrustNotice');if(notice){notice.hidden=!hard;notice.textContent=hard?'계산 일치 검사에 실패하여 선택 배치의 지도·목표표·저장·추가 검산을 격리했습니다. 아래 해품질 카드에서 불일치 항목을 확인하세요.':'';}
 }
 function clear(message='배치 목록이나 그래프에서 배치를 선택하면 진단을 계산합니다.'){
  serial++;key='';$('qualityContent').hidden=true;$('qualityLoading').hidden=false;$('qualityLoading').textContent=message;
  $('qualityDecision').textContent='배치를 선택하세요';$('qualityDecision').className='qualityDecision neutral';$('currentMap')?.classList.remove('integrityBlocked');gate({integrity:'PENDING',constraint:'PENDING',search:'NOT_CHECKED'});
 }
 function localText(d,label){
  if(d.status==='NOT_CHECKED')return `${label}은 계산 진실성과 제약 통과 후 실행합니다.`;
  if(d.witness)return `${d.checked.toLocaleString()}개를 검사해 선택 배치를 지배하는 반례를 찾았습니다. 아래 지도는 MOEA 원시해가 아니라 진단용 편집 배치입니다.`;
  return `${d.checked.toLocaleString()}개${d.possible!==undefined?' / 가능한 '+d.possible.toLocaleString()+'개':''}를 검사했습니다. 반례를 찾지 못했지만 전체 해공간의 최적성을 인증하지 않습니다. ${d.exhaustive?'이 국소 이웃은 전수 검사했습니다.':'검사 상한에서 멈췄습니다.'}`;
 }
 function render(q,problem){
  const hard=q.integrity.status!=='PASS',feasible=q.integrity.constraint_status==='PASS',v6=['full_area_tradeoff_v6','layered_mission_v7'].includes(q.objective_contract?.id),local=q.local_search.overall;
  $('qualityLoading').hidden=true;$('qualityContent').hidden=false;
  const decision=hard?'계산 불일치 · 사용 차단':!feasible?'목표·자원 미달 · 승격 불가':local==='WARNING_DOMINANCE_WITNESS'||q.observed_set.status==='WARNING_DOMINANCE_WITNESS'?'탐색 개선 여지 · 경고':'설명 가능 · 전역 최적 미인증';
  $('qualityDecision').textContent=decision;$('qualityDecision').className='qualityDecision '+(hard?'fail':!feasible||decision.includes('경고')?'warn':'pass');
  $('currentMap')?.classList.toggle('integrityBlocked',hard);
  gate({integrity:q.integrity.status,constraint:q.integrity.constraint_status,search:local==='WARNING_DOMINANCE_WITNESS'||q.observed_set.status==='WARNING_DOMINANCE_WITNESS'?'WARNING_DOMINANCE_WITNESS':local,message:decision,run_id:q.run_id,generation:q.generation,solution_id:q.solution_id});
  $('integrityStatus').textContent=hard?'계산 결속 실패':feasible?'계산·사용조건 일치':v6?'계산 일치 · 성능 기준 미달':'계산 일치 · 제약 미달';
  $('integrityText').textContent=hard?q.integrity.meaning:`원시 X/F/G, 비용, 장비 수, 후보지, 독립 기하와 ${q.generation}세대 행 결속이 일치합니다. ${feasible?(v6?'물리 제약과 탐지95%·식별90% 운용판정선을 통과했습니다.':'모든 제약의 CV가 0입니다.'):(v6&&q.integrity.physical_constraint_status==='PASS'?'물리적으로는 실현가능하지만 탐지95%·식별90% 운용판정선에 미달해 결과 배치로 승격하지 않습니다.':'계산 오류는 아니지만 CV가 '+q.integrity.CV.toFixed(6)+'이므로 설명용 최종 배치로 승격하지 않습니다.')}`;
  cls($('integrityCard'),hard?'fail':feasible?'pass':'warn');
  $('setQualityStatus').textContent=names[q.observed_set.status]||q.observed_set.status;
  $('setQualityText').textContent=q.observed_set.selected.reason+' '+q.observed_set.scope;
  cls($('setQualityCard'),q.observed_set.status==='EMPIRICALLY_NONDOMINATED'?'pass':q.observed_set.status==='WARNING_DOMINANCE_WITNESS'?'fail':'warn');
  $('searchQualityStatus').textContent=names[local]||local;
  $('searchQualityText').textContent=local==='WARNING_DOMINANCE_WITNESS'?'한 대 삭제 또는 한 위치 교환에서 더 나은 배치를 찾았습니다. 원시해를 바꾸지 않고 경고로 표시합니다.':local==='NOT_CHECKED'?'목표·자원 제약 또는 계산 진실성 통과 전이므로 국소 검사를 사용하지 않습니다.':'검사한 국소 범위에서는 지배 반례가 없었습니다. 탐색 완료나 전역 최적을 뜻하지 않습니다.';
  cls($('searchQualityCard'),local==='WARNING_DOMINANCE_WITNESS'?'fail':local==='BOUNDED_INCONCLUSIVE'?'warn':'warn');
  const s=q.observed_set,r=q.reduced_reference;
  const rows=[['실제 목적함수 평가',s.evaluations.toLocaleString()+'회','요청 예산을 실제로 사용한 양입니다. 수렴 인증이 아닙니다.'],[v6?'물리적으로 실현가능한 평가 행':'실현가능 평가 행',s.feasible_count.toLocaleString()+'개',v6?'설치·자원 제약을 만족한 관측 행입니다. 95%·90% 기준충족 수와 같은 뜻이 아닙니다.':'탐지·식별·자원 제약을 모두 만족한 관측 행입니다.'],['서로 다른 물리 배치',s.unique_decisions.toLocaleString()+'개','같은 목적값이어도 설치 위치가 다르면 별도로 셉니다.'],['서로 다른 목적벡터',s.unique_objective_vectors.toLocaleString()+'개','탐지·식별·비용이 완전히 같은 반복을 합친 수입니다.'],[v6?'통합 물리 비지배 배치':'통합 경험적 비지배 배치',s.empirical_front_decisions.toLocaleString()+'개',v6?'전체 실행의 물리 실현가능 해를 비교한 값이며 95%·90% 미달 절충도 포함합니다.':'전체 실행에서 관측한 실현가능 해를 다시 비교한 값입니다.'],['통합 비지배 목적벡터',s.empirical_front_objectives.toLocaleString()+'개','동일 목적값의 다른 배치를 합친 절충점 수입니다.'],['선택 배치의 제약 위반 합',q.integrity.CV.toFixed(6),q.integrity.CV===0?(v6?'물리·선택 자원 제약 위반은 없습니다. 성능 기준은 별도 판정합니다.':'현행 제약을 모두 만족합니다.'):'0보다 크므로 설명용 최종 배치로 승격하지 않습니다.'],['축소 정확 검산',`${r.candidate_sites}후보 · ${r.enumerated_states.toLocaleString()}상태 · 기준 충족 ${r.operational_qualified_states.toLocaleString()}개 · 물리 실현가능 ${r.physical_feasible_states.toLocaleString()}개 · 비지배 목적벡터 ${r.nondominated_objective_vectors}개`,r.scope+(r.operational_qualified_states===0?' 이 실행 조건에서는 정량 기준을 충족한 축소 배치가 없으므로, 기준충족 참조 전선으로 사용하지 않습니다.':'')]];
  $('qualityMetricRows').innerHTML=rows.map(x=>`<tr><th>${x[0]}</th><td>${x[1]}</td><td>${x[2]}</td></tr>`).join('');
  $('deleteDiagnostic').textContent=localText(q.local_search.one_delete,'한 대 삭제 검사');
  $('swapDiagnostic').textContent=localText(q.local_search.one_swap,'한 위치 교환 검사');
  const witness=q.local_search.first_witness;
  $('qualityWitness').hidden=!witness;
  if(witness){const p=witness.point,e=witness.edit,sensor=t=>t?'EO/IR':'Radar';$('qualityWitnessTitle').textContent='국소 지배 반례 · 진단용 배치';$('qualityWitnessText').textContent=e.kind==='delete'?`후보지 ${e.site}의 ${sensor(e.sensor)} 한 대를 제거한 배치입니다. 탐지 ${pct(p.performance[0])}, 식별 ${pct(p.performance[1])}, 비용 ${p.cost}점입니다. 이 배치는 MOEA가 평가한 원시행이 아니며 현재 배치를 대체하지 않습니다.`:`후보지 ${e.from_site}의 ${sensor(e.from_sensor)}를 후보지 ${e.to_site}의 ${sensor(e.to_sensor)}로 바꾼 배치입니다. 탐지 ${pct(p.performance[0])}, 식별 ${pct(p.performance[1])}, 비용 ${p.cost}점입니다. 이 배치는 MOEA 원시행이 아닙니다.`;$('qualityWitnessMap').innerHTML=LiveCore.map(problem,p,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false});}
  $('qualityLimit').textContent=`선택 배치 #${q.solution_id}, 실행 ${q.run_id}, ${q.generation}세대에만 적용됩니다. 같은 seed 재실행과 다중 seed 비교는 아직 평가하지 않았습니다. 전체 정확 Pareto 전선·탐색 완료·전역 최적·제품 출시는 인증하지 않습니다.`;
 }
 function setMetrics(result){
  const n=result.neighbourhood,c=result.corrected_set,s=result.source,a=result.audited_explanation_set||{},sw=result.strict_one_swap||{};
  const scope=n.exhaustive?'삭제·교환 전수 검사':'삭제 전수 · 교환 결정론적 제한 검사';
  $('qualitySetMetrics').innerHTML=`<span>원시 누적 비지배 배치 <b>${s.raw_empirical_front_unique_layouts.toLocaleString()}개</b></span><span>검사한 고유 이웃 <b>${n.evaluated_unique.toLocaleString()}개</b></span><span>물리 실현가능 파생 후보 <b>${n.feasible_derived.toLocaleString()}개</b></span><span>교정 비지배 집합 <b>${c.total.toLocaleString()}개</b></span><span>원시 생존 <b>${c.raw_survivors.toLocaleString()}개</b></span><span>교정 파생 생존 <b>${c.derived_audit_survivors.toLocaleString()}개</b></span><span>500m 목표 통과 <b>${c.operational_qualified_before_delete_screen.toLocaleString()}개</b></span><span>원시·250m 유지 설명 후보 <b>${(c.raw_stable_explanation_candidate_count||0).toLocaleString()}개</b></span><span>dH=2 전수검사 전 원시 후보 <b>${(sw.preliminary_candidate_count||0).toLocaleString()}개</b></span><span>모든 엄격검사 통과 원시 후보 <b>${(c.promotion_candidate_count||0).toLocaleString()}개</b></span><span>감사 개선·국소폐쇄 설명 후보 <b>${(a.count||0).toLocaleString()}개</b></span>`;
  $('qualitySetStatus').innerHTML=`<strong>${scope}</strong> · 가능한 한 단계 이웃 ${n.possible_total.toLocaleString()}개 중 고유 ${n.evaluated_unique.toLocaleString()}개를 현행 평가기로 계산했습니다.`;
 }
 function showSetPoint(point){
  if(!point||!setContext)return;
  LiveQualityLineage.validateSetPoint(point,setContext.problem.sites.length);
  setSelected=point.id;
  document.querySelectorAll('.qualitySetGroup').forEach(node=>node.classList.toggle('selected',node.dataset.point===String(point.id)));
  const derived=point.provenance==='DERIVED_AUDIT_NOT_MOEA',raw=point.provenance==='RAW_MOEA_OBSERVED';
  if(!derived&&!raw)throw new Error('원시·감사 배치 선택기에 허용되지 않은 계보입니다.');
  $('qualitySetPointBadge').textContent=derived?'감사 교정 파생 후보 · MOEA 원시 아님':'실제 MOEA 원시 관측 해';
  $('qualitySetPointBadge').className=derived?'derived':'raw';
  $('qualitySetPointTitle').textContent=`배치 ${point.id}`;
  $('qualitySetPointMetric').textContent=`탐지 ${pct(point.performance[0])} · 식별 ${pct(point.performance[1])} · 비용 ${point.cost}점`;
  $('qualitySetPointLineage').textContent=LiveQualityLineage.admissionText(point);
  $('qualitySetMap').innerHTML=LiveCore.map(setContext.problem,point,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false});
 }
 function renderConfidence(result){
  const section=$('confidenceEvidence'),o=result.objective_evidence||{},r=result.mathematical_reference||{},rr=result.robust_reference_500m_250m||{},p=result.archive_progression||{},g=result.grid_sensitivity_250m||{};
  if(!section)return;section.hidden=false;
  const ranges=new Map((o.ranges||[]).map(x=>[x.objective,x]));
  const d=ranges.get('detection'),i=ranges.get('identification'),c=ranges.get('cost'),tr=o.pairwise_tradeoff||{};
  $('objectiveEvidenceStatus').textContent=o.status==='MEASURED_ON_CUMULATIVE_EMPIRICAL_FRONT'?'누적 비지배 해에서 실측':'계산 근거 없음';
  const rangeText=(x,kind)=>!x?'자료 없음':kind==='cost'?`${x.minimum.toFixed(0)}–${x.maximum.toFixed(0)}점 · 고유 ${x.unique_values}단계`:`${pct(x.minimum)}–${pct(x.maximum)} · 고유 ${x.unique_values}단계 · 100% 포화 ${pct(x.saturation_100_rate||0)}`;
  const trade=(x)=>x&&x.tradeoff_rate!==null?`${x.tradeoff_pairs.toLocaleString()} / ${x.informative_pairs.toLocaleString()}쌍 (${pct(x.tradeoff_rate)})`:'비교 가능한 쌍 없음';
  const op=o.operational_subset||{},opRanges=new Map((op.ranges||[]).map(x=>[x.objective,x])),opTrade=op.pairwise_tradeoff||{},db=op.bands?.detection||{},ib=op.bands?.identification||{};
  const band=(value)=>Number(value||0).toLocaleString()+'개';
  $('objectiveEvidenceBody').innerHTML=`<dl><dt>전체 누적 비지배 · 탐지</dt><dd>${rangeText(d,'performance')}</dd><dt>전체 누적 비지배 · 식별</dt><dd>${rangeText(i,'performance')}</dd><dt>전체 누적 비지배 · 비용</dt><dd>${rangeText(c,'cost')}</dd><dt>탐지↔식별 반대 이동</dt><dd>${trade(tr.detection_identification)}</dd><dt>탐지↔비용 절충</dt><dd>${trade(tr.detection_cost)}</dd><dt>식별↔비용 절충</dt><dd>${trade(tr.identification_cost)}</dd></dl><h4>95%·90%를 통과한 누적 비지배 부분집합 ${Number(op.count||0).toLocaleString()}개</h4><dl><dt>통과해 탐지 범위</dt><dd>${rangeText(opRanges.get('detection'),'performance')}</dd><dt>통과해 식별 범위</dt><dd>${rangeText(opRanges.get('identification'),'performance')}</dd><dt>통과해 비용 범위</dt><dd>${rangeText(opRanges.get('cost'),'cost')}</dd><dt>통과해 탐지 분포</dt><dd>95–97% ${band(db['95_to_below_97'])} · 97–99% ${band(db['97_to_below_99'])} · 99–100% ${band(db['99_to_below_100'])} · 100% ${band(db['100'])}</dd><dt>통과해 식별 분포</dt><dd>90–92% ${band(ib['90_to_below_92'])} · 92–95% ${band(ib['92_to_below_95'])} · 95–100% ${band(ib['95_to_below_100'])} · 100% ${band(ib['100'])}</dd><dt>통과해 탐지↔식별 반대 이동</dt><dd>${trade(opTrade.detection_identification)}</dd><dt>통과해 탐지↔비용 절충</dt><dd>${trade(opTrade.detection_cost)}</dd><dt>통과해 식별↔비용 절충</dt><dd>${trade(opTrade.identification_cost)}</dd></dl><p>${o.meaning||''}</p>`;
  const refNames={EXACT_TARGET_COST_REFERENCE_COMPUTED:'정량목표 최소비용 증명',BOUNDED_TARGET_COST_REFERENCE_COMPUTED:'시간제한 상·하한 계산',TARGETS_PROVEN_INFEASIBLE_FOR_CURRENT_CONTRACT:'현재 자원에서 목표 불가능 증명',REFERENCE_NOT_RESOLVED_WITHIN_TIME_LIMIT:'시간 안에 기준 미확정',NOT_COMPUTED_CONTRACT_OUT_OF_SCOPE:'이 계약에는 미적용'};
  $('referenceEvidenceStatus').textContent=refNames[r.status]||r.status||'계산 근거 없음';
  const val=x=>x===null||x===undefined?'없음':Number(x).toFixed(2)+'점';
  let comparison='목표통과 교정 해가 없어 비용 격차를 계산하지 못했습니다.';
  if(r.observed_cost_gap_to_exact!==null&&r.observed_cost_gap_to_exact!==undefined)comparison=r.observed_matches_exact_target_cost?'누적·교정 해집합의 최저비용이 증명된 최소비용과 같습니다.':`누적·교정 해집합 최저비용은 증명된 최소보다 ${r.observed_cost_gap_to_exact.toFixed(0)}점 높습니다.`;
  else if(r.observed_certified_absolute_gap!==null&&r.observed_certified_absolute_gap!==undefined)comparison=`500m 동일계약의 최적비용은 ${r.proved_cost_lower_bound.toFixed(0)}또는 ${r.best_corrected_qualified_cost.toFixed(0)}점으로 미확정입니다. 하한 분모 최악 격차는 ${r.observed_certified_absolute_gap.toFixed(0)}점(${pct(r.observed_certified_relative_gap)}), 실현비용 분모는 ${pct(r.observed_relative_gap_to_feasible_cost)}입니다.`;
  const init=result.source?.initialization_evidence||{},seedPreserved=(init.seed_decision_lineage||[]).some(x=>x.present_in_cumulative_raw_front&&x.first_observed_generation===0);
  const initText=seedPreserved?`초기 원본 결정벡터 해시가 0세대 원시행과 일치해 초기해 보존이 확인됩니다. 누적 원시 목표통과 최저비용 ${val(init.best_cumulative_raw_target_cost)}을 진화의 독립 발견으로 재표기하지 않습니다.`:`원본 seed 결정벡터의 0세대 보존을 확인하지 못했습니다. 같은 비용만으로 초기해 보존이나 진화 발견을 단정하지 않습니다.`;
  const robustExact=rr.exact_minimum_robust_target_cost,robustLower=rr.proved_integer_cost_lower_bound,robustObserved=rr.best_observed_robust_target_cost;
  const robustInterval=robustExact!==null&&robustExact!==undefined?`${val(robustExact)} · 최소비용 증명`:(robustLower!==null&&robustLower!==undefined&&robustObserved!==null&&robustObserved!==undefined?`${val(robustLower)} ≤ 최소비용 ≤ ${val(robustObserved)}`:'계산 근거 없음');
  const correctedPoints=result.corrected_set?.points||[],stableIds=new Set((result.hamming_raw_stable?.clusters||[]).flatMap(cluster=>cluster.member_ids||[]).map(String));
  const rawRobustCosts=correctedPoints.filter(point=>point.provenance==='RAW_MOEA_OBSERVED'&&stableIds.has(String(point.id))).map(point=>point.cost);
  const auditRobustCosts=correctedPoints.filter(point=>point.provenance==='DERIVED_AUDIT_NOT_MOEA'&&point.quality_admission?.target_qualified&&point.quality_admission?.grid_250_target_retained).map(point=>point.cost);
  const rawRobust=rawRobustCosts.length?Math.min(...rawRobustCosts):null,auditRobust=auditRobustCosts.length?Math.min(...auditRobustCosts):null;
  $('referenceEvidenceBody').innerHTML=`<dl><dt>500m 단일격자 증명 하한</dt><dd>${val(r.proved_cost_lower_bound)}</dd><dt>증명된 500m 목표통과 최소비용</dt><dd>${val(r.exact_minimum_target_cost)}</dd><dt>500m·250m 동시통과 비용 범위</dt><dd><strong>${robustInterval}</strong></dd><dt>원시 NSGA-III 두 격자 통과 최저비용</dt><dd>${val(rawRobust)}</dd><dt>감사 파생 두 격자 통과 최저비용</dt><dd>${val(auditRobust)} · MOEA 원시 아님</dd><dt>원시+감사 결합 관측 최저비용</dt><dd>${val(robustObserved)} · 계보별 값은 위 두 행 참조</dd><dt>두 격자 MILP 상태</dt><dd>${rr.status||'미계산'} · gap ${rr.milp_gap===null||rr.milp_gap===undefined?'없음':pct(rr.milp_gap)}</dd><dt>누적·교정 목표통과 최저비용</dt><dd>${val(r.best_corrected_qualified_cost)}</dd><dt>초기화와 진화 구분</dt><dd>${initText}</dd><dt>초기 준비 목적평가</dt><dd>${(init.preparation_evaluations||0).toLocaleString()}회 · LP ${(init.lp_solver_calls||0).toLocaleString()}회 · MILP ${(init.milp_solver_calls||0).toLocaleString()}회 · ${Number(init.preparation_seconds||0).toFixed(3)}초</dd><dt>NSGA-III 탐색 평가</dt><dd>${(init.search_evaluations||0).toLocaleString()} NFE · 초기 준비비용과 별도</dd><dt>500m 비교 판정</dt><dd>${comparison}</dd></dl><p>${r.scope||r.meaning||''}</p><p><b>두 격자 비용 기준:</b> ${rr.scope||'미계산'} ${rr.claim_boundary||''}</p>`;
  const proofSupported=rr.status!=='NOT_COMPUTED_CONTRACT_OUT_OF_SCOPE';
  setRobustProofControl(proofSupported,proofSupported);
  const refMap=$('referenceEvidenceMap');let refCaption=$('referenceEvidenceMapCaption');
  if(!refCaption&&refMap){refCaption=document.createElement('p');refCaption.id='referenceEvidenceMapCaption';refCaption.className='qualitySetHint';refMap.before(refCaption);}
  const robustLayout=rr.reference_layout||null,shownReference=robustLayout||r.reference_layout||null;
  if(shownReference&&setContext?.problem){
   let referenceVerified=false,referenceError='';
   try{LiveQualityLineage.validateSetPoint(shownReference,setContext.problem.sites.length);referenceVerified=true;}catch(error){referenceError=error.message;}
   if(referenceVerified){refMap.hidden=false;refCaption.hidden=false;refCaption.textContent=robustLayout?'아래 지도는 500m와 250m 목표를 동시에 만족한 MILP 실현배치입니다. 비용 하한 자체의 지도가 아니며 MOEA 원시해도 아닙니다.':'아래 지도는 500m 단일격자 수학 참조 배치입니다. 250m 동시통과 기준이나 MOEA 원시해가 아닙니다.';refMap.dataset.referenceKind=robustLayout?'robust-500m-250m':'single-grid-500m';refMap.innerHTML=LiveCore.map(setContext.problem,shownReference,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false});}
   else{refMap.hidden=true;refMap.innerHTML='';refCaption.hidden=false;refCaption.textContent=Array.isArray(shownReference.mask)?`수학 참조 지도 결속 검증 실패: ${referenceError} 집계 비용·상하한만 표시합니다.`:'수학 참조 응답에 배치벡터가 없어 지도는 표시하지 않습니다. 집계 비용·상하한만 표시합니다.';}
  }else{refMap.hidden=true;refMap.innerHTML='';if(refCaption)refCaption.hidden=true;}
  const gridStatus=$('gridSetEvidenceStatus'),gridBody=$('gridSetEvidenceBody');
  if(gridStatus&&gridBody){
   if(g.status==='INDEPENDENT_250M_REPLAY_COMPLETE'){
    gridStatus.textContent=`${g.layout_count.toLocaleString()}개 배치 재평가 완료`;
    const delta=g.maximum_absolute_delta_percentage_points||[0,0],cc=g.classification_confusion||{},rawDelta=g.raw_maximum_absolute_delta_percentage_points||[0,0],rc=g.raw_classification_confusion||{},ref250=g.reference_layout;
    gridBody.innerHTML=`<dl><dt>250m 평가점</dt><dd>탐지 ${g.detection_points.toLocaleString()}개 · 식별 ${g.identification_points.toLocaleString()}개</dd><dt>교정 전체 양방향 판정</dt><dd>유지통과 ${cc.pass_pass||0} · 통과→미달 ${cc.pass_fail||0} · 미달→통과 ${cc.fail_pass||0} · 유지미달 ${cc.fail_fail||0} · 전체 일치 ${cc.bidirectional_agreement_rate==null?'자료 없음':pct(cc.bidirectional_agreement_rate)}</dd><dt>교정 500m 통과 유지율</dt><dd>${cc.pass_to_pass_retention_rate==null?'자료 없음':pct(cc.pass_to_pass_retention_rate)}</dd><dt>교정 최대 변화</dt><dd>탐지 ${Number(delta[0]).toFixed(2)}%p · 식별 ${Number(delta[1]).toFixed(2)}%p</dd><dt>원시 누적 비지배 양방향 판정</dt><dd>유지통과 ${rc.pass_pass||0} · 통과→미달 ${rc.pass_fail||0} · 미달→통과 ${rc.fail_pass||0} · 유지미달 ${rc.fail_fail||0} · 전체 일치 ${rc.bidirectional_agreement_rate==null?'자료 없음':pct(rc.bidirectional_agreement_rate)}</dd><dt>원시 최대 변화</dt><dd>탐지 ${Number(rawDelta[0]).toFixed(2)}%p · 식별 ${Number(rawDelta[1]).toFixed(2)}%p</dd><dt>500m 단일격자 ${r.exact_minimum_target_cost??'미확정'}점 기준의 250m 재검산</dt><dd>${!ref250?'자료 없음':ref250.qualified_250m?'250m에서도 95%·90% 유지':'250m에서는 목표 미달'}</dd></dl><p>${g.meaning||''}</p>`;
   }else{gridStatus.textContent='재평가 근거 없음';gridBody.textContent='현재 목적함수 계약에서는 해집합 전체 250m 재평가를 수행하지 않았습니다.';}
  }
  $('archiveProgressRows').innerHTML=(p.checkpoints||[]).map(x=>`<tr><th>${x.generation}</th><td>${x.evaluations.toLocaleString()}</td><td>${x.physical_feasible_rows.toLocaleString()}</td><td>${x.operational_qualified_rows.toLocaleString()}</td><td>${x.cumulative_empirical_front_unique_layouts.toLocaleString()}</td><td>${x.qualified_empirical_front_unique_layouts.toLocaleString()}</td><td>${x.best_qualified_cost===null?'목표 통과 없음':x.best_qualified_cost+'점'}</td></tr>`).join('');
  $('archiveProgressMeaning').textContent=p.meaning||'';
 }
 function renderSet(result){
  LiveQualityLineage.validateSet(result,{run_id:setContext.last.id,generation:setContext.generation,problem_sha256:setContext.problem.problem_sha256,candidate_count:setContext.problem.sites.length});
  setResult=result;setMetrics(result);renderConfidence(result);$('qualitySetResult').hidden=false;
  const audited=result.audited_explanation_set||{points:[],hamming:{clusters:[]}};
  const points=new Map([...result.corrected_set.points,...(audited.points||[])].map(p=>[String(p.id),p]));
  const clusterHtml=(clusters,prefix)=>clusters.map((g,i)=>{const p=points.get(String(g.representative_id));if(!p)throw new Error('배치군 대표해가 해집합에 없습니다.');const derived=p.provenance==='DERIVED_AUDIT_NOT_MOEA';const options=g.member_ids.map(id=>{const q=points.get(String(id));if(!q)throw new Error('배치군 구성해가 해집합에 없습니다.');const provenance=q.provenance==='DERIVED_AUDIT_NOT_MOEA'?'[감사 파생]':'[원시 MOEA]';return `<option value="${q.id}">${provenance} ${q.id} · ${q.cost}점 · 탐지 ${pct(q.performance[0])} · 식별 ${pct(q.performance[1])}</option>`;}).join('');const role=derived?'비용 우선 감사 파생 대표 배치':'비용 우선 원시 관측 배치';return `<article class="qualitySetCluster"><button type="button" class="qualitySetGroup" data-point="${p.id}"><span>${prefix} ${i+1} · ${g.member_ids.length}개 · 직경 ${g.diameter}</span><strong>${derived?'감사 파생 ':''}${p.id} · ${p.cost}점</strong><small>${role} · 탐지 ${pct(p.performance[0])} · 식별 ${pct(p.performance[1])}</small></button><label>이 배치군의 모든 해<select class="qualitySetMemberSelect" aria-label="${prefix} ${i+1} 해 선택"><option value="">지도에서 볼 배치를 직접 선택</option>${options}</select></label><small>Medoid ${g.medoid_member_id} · 비용 우선 ${g.cost_priority_member_id}</small></article>`;}).join('');
  const stable=result.hamming_raw_stable?.clusters||[],promoted=result.hamming_promotion?.clusters||[],auditedClusters=audited.hamming?.clusters||[],diagnostic=result.hamming?.clusters||[],sw=result.strict_one_swap||{};
  const swapRows=(sw.rows||[]).map(row=>`<li>원시 #${row.candidate_id}: 가능한 dH=2 교환 ${row.possible.toLocaleString()}개 전수 · 500m 지배반례 ${row.objective_500m_dominance_witness_count}개 · 두 격자 모두 목표통과 ${row.target_pass_both_grids}개 · 더 싼 두 격자 통과 ${row.lower_cost_both_grid_witness_count}개</li>`).join('');
  $('qualitySetGroups').innerHTML=`<h4>원시 안정 설명 후보 · 500m/250m 목표 유지</h4><p>실제 NSGA-III 평가행만 표시합니다. Hamming 군집은 성능을 바꾸지 않고 설치구조가 비슷한 해만 묶습니다.</p>${clusterHtml(stable,'원시 안정 배치군')||'<p class="qualitySetEmpty">현재 실행에는 500m와 250m에서 모두 목표를 유지한 원시 설명 후보가 없습니다.</p>'}<details open><summary>감사 개선 후 dH=2 국소폐쇄 설명 후보 ${auditedClusters.length}개 배치군 · 원시 MOEA 아님</summary><p>${audited.meaning||''}</p>${clusterHtml(auditedClusters,'감사 개선 배치군')||'<p class="qualitySetEmpty">삭제·교환 전수검사를 모두 통과한 감사 개선 설명 후보가 없습니다.</p>'}</details><details><summary>모든 엄격검사를 통과한 원시 후보 ${promoted.length}개 배치군</summary>${clusterHtml(promoted,'엄격 원시 배치군')||'<p class="qualitySetEmpty">원시 후보에서 국소 개선 반례가 발견되어 엄격 원시 승격 후보는 없습니다. 아래 전수검사 수치와 감사 개선 배치를 함께 보세요.</p>'}${swapRows?`<ul>${swapRows}</ul>`:''}</details><details><summary>1차 감사 파생 후보까지 포함한 진단 배치군 보기 · MOEA 원시 결과 아님</summary>${clusterHtml(diagnostic,'진단 배치군')||'<p class="qualitySetEmpty">진단 배치군이 없습니다.</p>'}</details>`;
  document.querySelectorAll('.qualitySetGroup').forEach(node=>node.onclick=()=>showSetPoint(points.get(node.dataset.point)));
  document.querySelectorAll('.qualitySetMemberSelect').forEach(node=>node.onchange=()=>{if(node.value)showSetPoint(points.get(String(node.value)));});
  const ref=result.mathematical_reference||{},rr=result.robust_reference_500m_250m||{};let evidence='';
  if(ref.status==='EXACT_TARGET_COST_REFERENCE_COMPUTED')evidence=ref.observed_matches_exact_target_cost?' 500m 단일격자 목표통과 최소비용과 일치합니다.':` 500m 단일격자 목표통과 최소비용과의 격차는 ${ref.observed_cost_gap_to_exact??'미계산'}점입니다.`;
  else if(ref.observed_certified_absolute_gap!==null&&ref.observed_certified_absolute_gap!==undefined)evidence=` 동일계약 증명 하한 대비 비용 격차는 최대 ${ref.observed_certified_absolute_gap.toFixed(0)}점입니다.`;
  else if(ref.status==='TARGETS_PROVEN_INFEASIBLE_FOR_CURRENT_CONTRACT')evidence=' 현재 보유수량·설치계약에서는 95%·90% 동시 달성이 불가능하다고 MILP가 판정했습니다.';
  const robust=(rr.proved_integer_cost_lower_bound!==null&&rr.proved_integer_cost_lower_bound!==undefined&&rr.best_observed_robust_target_cost!==null&&rr.best_observed_robust_target_cost!==undefined)?` 500m·250m 동시통과 최소비용은 현재 ${rr.proved_integer_cost_lower_bound.toFixed(0)}–${rr.best_observed_robust_target_cost.toFixed(0)}점 범위로 좁혔습니다.`:'';
  $('qualitySetBoundary').textContent=`원시 해집합은 변경하지 않았습니다. 이 화면은 ${result.neighbourhood.exhaustive?'모든 한 단계 삭제·교환':'모든 삭제와 제한된 교환'} 이웃을 추가로 평가한 범위의 교정 집합입니다.${evidence}${robust} 감사 개선 배치는 원시 MOEA 해가 아니며, 수학 기준 배치도 원시해와 분리합니다.`;
  setSelected=null;$('qualitySetPointBadge').textContent='자동 선택 없음';$('qualitySetPointBadge').className='';$('qualitySetPointTitle').textContent='지도에서 볼 배치를 직접 선택하세요';$('qualitySetPointMetric').textContent='배치군 카드나 목록을 선택하면 같은 실행·세대·문제 해시의 배치만 표시합니다.';$('qualitySetPointLineage').textContent='비용 우선 대표는 배치군 설명용 기준일 뿐 사용자 선택·추천·최적해가 아닙니다.';$('qualitySetMap').innerHTML='<p class="qualitySetEmpty">선택 전에는 어떤 배치도 자동으로 지도에 올리지 않습니다.</p>';
 }
 async function correctionRequest(path){
  // This read intentionally performs thousands of evaluator calls.  The normal
  // 5 s read-retry transport would abort and duplicate the same calculation.
  // Keep one request alive and bound it explicitly instead.
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),75000);
  try{
   const response=await fetch(path,{method:'GET',signal:controller.signal,cache:'no-store'});
   const text=await response.text();let data;
   try{data=JSON.parse(text);}catch{throw new Error('교정 계산 응답 형식을 확인할 수 없습니다.');}
   if(!response.ok)throw new Error(data?.error||`교정 계산 오류 (HTTP ${response.status})`);
   return data;
  }catch(e){
    if(e.name==='AbortError')throw new Error('신뢰성 계산이 75초 제한을 넘었습니다. 원시 결과는 변경되지 않았습니다.');
   throw e;
  }finally{clearTimeout(timer);}
 }
 async function robustProofRequest(path){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),150000);
  try{
   const response=await fetch(path,{method:'GET',signal:controller.signal,cache:'no-store'});
   const text=await response.text();let data;
   try{data=JSON.parse(text);}catch{throw new Error('비용 검산 응답 형식을 확인할 수 없습니다.');}
   if(!response.ok)throw new Error(data?.error||`비용 검산 오류 (HTTP ${response.status})`);
   return data;
  }catch(e){if(e.name==='AbortError')throw new Error('비용별 MILP 검산이 150초 제한을 넘었습니다. 시간초과를 불가능 증명으로 처리하지 않았습니다.');throw e;}
  finally{clearTimeout(timer);}
 }
 function renderRobustProof(proof){
  robustProof=proof;const status=$('robustCostProofStatus'),table=$('robustCostProofTable');
  if(!status||!table)return;
  table.closest('article')?.classList.add('robustProofExpanded');
  const labels={PROVEN_INFEASIBLE_AT_FIXED_COST:'불가능 증명',PROVEN_FEASIBLE_AT_FIXED_COST:'가능·재평가 통과',ALGEBRAICALLY_INFEASIBLE_COST_LATTICE:'비용식상 불가능',FEASIBLE_WITNESS_WITHOUT_COMPLETED_PROOF:'가능 배치 발견·증명 미완료',UNRESOLVED_WITHIN_TIME_LIMIT:'시간 안에 미확정'};
  const exact=proof.exact_minimum_robust_target_cost;
  status.innerHTML=exact!==null&&exact!==undefined?`<strong>${exact}점</strong>이 같은 배치로 500m·250m 탐지 95%·식별 90%를 모두 만족하는 최소 합성비용입니다. 하한 ${proof.proved_cost_lower_bound}점부터 비용 격자를 빠짐없이 검사했습니다.`:'비용별 검산 범위에 미확정 수준이 남아 최소비용을 확정하지 않았습니다.';
  if(exact!==null&&exact!==undefined&&$('qualitySetBoundary'))$('qualitySetBoundary').textContent=`원시 해집합은 변경하지 않았습니다. 500m·250m 동시통과 최소비용은 ${exact}점으로 증명되었습니다. 아래 원시 NSGA-III 최선, 감사 파생 최선, 수학 비용 기준은 서로 다른 계보이며 수학 배치는 원시 해집합이나 Hamming 배치군에 편입하지 않습니다.`;
  const lineage=proof.lineage_comparison||{},raw=lineage.best_raw_moea,audit=lineage.best_audit_derived,relation=lineage.raw_empirical_front_relation||{},distance=lineage.stable_raw_distance_to_this_reference_witness||{};
  const witnessHash=(lineage.mathematical_reference?.decision_sha256||'').slice(0,12);
  const lineageTable=lineage.status==='LINEAGE_SEPARATED'?`<h4>수학 기준·원시 탐색·감사 파생 결과를 분리한 비교</h4><table><thead><tr><th>구분</th><th>배치·비용</th><th>이 결과가 증명하는 범위</th></tr></thead><tbody><tr><th>수학 비용 기준</th><td>${lineage.mathematical_reference.id} · ${lineage.mathematical_reference.cost}점${witnessHash?` · 배치 ${witnessHash}`:''}</td><td>두 격자 정량목표 최소 합성비용. 같은 비용의 가능한 배치 중 이번 응답의 한 증인으로, NSGA-III 원시해가 아닙니다.</td></tr><tr><th>원시 NSGA-III 최선</th><td>${raw?`#${raw.id} · ${raw.cost}점`:'해당 없음'}</td><td>${raw?`정확 비용차 +${lineage.raw_gap_to_exact_cost}점 · 비용격자 ${lineage.raw_gap_cost_lattice_steps}단계 · ${pct(lineage.raw_relative_gap_to_exact)}`:'두 격자 목표통과 원시해 없음'}</td></tr><tr><th>감사 파생 최선</th><td>${audit?`${audit.id} · ${audit.cost}점`:'해당 없음'}</td><td>삭제·교환 진단에서 만든 배치. NSGA-III 발견으로 계산하지 않음</td></tr></tbody></table><dl><dt>500m 원래 3목적 기준 · 이 수학 배치가 지배한 원시 누적해</dt><dd>${relation.reference_dominates_raw||0} / ${relation.total||0}개 · 원시해가 이 배치를 지배 ${relation.raw_dominates_reference||0}개 · 목적벡터 동일 ${relation.equal_objective_vector||0}개 · 서로 절충 ${relation.incomparable||0}개</dd><dt>원시 안정 배치와 이 수학 배치의 Hamming 거리</dt><dd>${distance.count||0}개 · 동일배치 ${distance.exact_matches||0}개 · 최소 ${distance.minimum??'없음'} · 최대 ${distance.maximum??'없음'}</dd></dl><p class="qualitySetHint">${lineage.meaning||''}</p>`:'';
  table.hidden=false;table.innerHTML=`<h4>비용 수준별 가능성 검사</h4><table><thead><tr><th>합성비용</th><th>판정</th><th>solver·재평가 근거</th></tr></thead><tbody>${(proof.rows||[]).map(row=>`<tr><th>${row.cost}점</th><td>${labels[row.status]||row.status}</td><td>${row.status==='ALGEBRAICALLY_INFEASIBLE_COST_LATTICE'?'6×Radar+2×EO/IR은 짝수만 가능합니다.':row.replay_valid?'정수해를 현행 평가기로 500m·250m 재계산해 목표와 비용이 일치했습니다.':row.status==='PROVEN_INFEASIBLE_AT_FIXED_COST'?'HiGHS가 시간초과가 아닌 infeasible 상태로 종료했습니다.':'불가능으로 간주하지 않습니다.'}</td></tr>`).join('')}</tbody></table><p class="qualitySetHint">${proof.scope||''} ${proof.claim_boundary||''} 이 수학 배치는 NSGA-III 원시 해집합과 Hamming 배치군에 편입하지 않습니다.</p>${lineageTable}`;
  const witness=(proof.rows||[]).find(row=>row.cost===exact)?.reference_layout;
  const refMap=$('referenceEvidenceMap'),caption=$('referenceEvidenceMapCaption');
  if(witness&&setContext?.problem){
   let verified=false,errorText='';
   try{LiveQualityLineage.validateSetPoint(witness,setContext.problem.sites.length);verified=true;}catch(error){errorText=error.message;}
   if(verified){refMap.hidden=false;refMap.dataset.referenceKind='fixed-cost-two-grid-proof';refMap.innerHTML=LiveCore.map(setContext.problem,witness,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false});if(caption){caption.hidden=false;caption.textContent=`수학적 비용 증명 배치 · ${exact}점 · MOEA 원시해 아님 · 500m 탐지 ${pct(witness.performance_500m[0])}/식별 ${pct(witness.performance_500m[1])} · 250m 탐지 ${pct(witness.performance_250m[0])}/식별 ${pct(witness.performance_250m[1])}`;}}
   else{refMap.hidden=true;refMap.innerHTML='';if(caption){caption.hidden=false;caption.textContent=Array.isArray(witness.mask)?`수학 비용 증명 지도 결속 검증 실패: ${errorText} 집계 최소비용만 표시합니다.`:'수학 비용 증명 응답에 배치벡터가 없어 지도는 표시하지 않습니다. 집계 최소비용만 표시합니다.';}}
  }else if(exact!==null&&exact!==undefined&&refMap){refMap.hidden=true;refMap.innerHTML='';if(caption){caption.hidden=false;caption.textContent='수학 비용 증명 응답에 지도용 배치가 없어 집계 최소비용만 표시합니다.';}}
 }
 async function calculateRobustProof(){
  if(!setContext?.last||setContext.generation===undefined||!setResult||!robustProofAvailable){
   const status=$('robustCostProofStatus');if(status&&!robustProofAvailable)status.textContent='현재 목적함수 계약에서는 V7 전용 두 격자 최소비용 검산을 실행할 수 없습니다.';
   return;
  }
  const button=$('robustCostProof'),status=$('robustCostProofStatus'),mine=++robustProofSerial;
  button.disabled=true;status.textContent='증명 하한부터 관측 상한까지 비용별 MILP 가능성과 두 격자 재평가를 계산하고 있습니다…';
  try{const threshold=+$('qualitySetThreshold').value,requestKey=LiveQualityLineage.robustProofKey(setContext,threshold),proof=await robustProofRequest(`/api/jobs/${setContext.last.id}/robust-cost-proof?generation=${setContext.generation}&threshold=${threshold}&seconds=60`);const liveThreshold=+$('qualitySetThreshold').value;if(LiveQualityLineage.robustProofResponseIsCurrent(requestKey,mine,setContext,liveThreshold,robustProofSerial)){LiveQualityLineage.validateRobustProof(proof,{run_id:setContext.last.id,generation:setContext.generation,problem_sha256:setContext.problem.problem_sha256,threshold:liveThreshold});renderRobustProof(proof);}}
  catch(e){if(mine===robustProofSerial)status.textContent='최소비용 정밀검산을 완료하지 못했습니다. '+e.message;}
  finally{if(mine===robustProofSerial)button.disabled=false;}
 }
 async function calculateSet(){
  if(!setContext?.last||setContext.generation===undefined)return;
  const button=$('qualitySetCalculate'),threshold=+$('qualitySetThreshold').value;
  const requestKey=`${setContext.last.id}:${setContext.generation}`;
  const requestSerial=++setRequestSerial;
  button.disabled=true;$('qualitySetStatus').textContent='원시 누적 비지배 집합의 삭제·교환 이웃을 계산하고 있습니다…';
  try{const result=await correctionRequest(`/api/jobs/${setContext.last.id}/quality-set?generation=${setContext.generation}&threshold=${threshold}&mode=auto`);const liveKey=setContext?.last&&setContext.generation!==undefined?`${setContext.last.id}:${setContext.generation}`:'';if(requestSerial!==setRequestSerial||requestKey!==liveKey)return;LiveQualityLineage.validateSet(result,{run_id:setContext.last.id,generation:setContext.generation,problem_sha256:setContext.problem.problem_sha256,candidate_count:setContext.problem.sites.length});renderSet(result);}
  catch(e){if(requestSerial===setRequestSerial)$('qualitySetStatus').textContent='해집합 교정 계산을 완료하지 못했습니다. 원시 결과는 변경되지 않았습니다. '+e.message;}
  finally{if(requestSerial===setRequestSerial)button.disabled=false;}
 }
 $('qualitySetCalculate')?.addEventListener('click',calculateSet);
 if($('qualitySetTitle')){
  $('qualitySetTitle').textContent='세대 누적 해집합·수학 기준·배치구조 비교';
  const head=$('qualitySetTitle').closest('.qualitySetHead');
  const step=head?.querySelector('span');if(step)step.textContent='4 · 누적 해집합 신뢰성 계산';
  const description=$('qualitySetTitle').parentElement?.querySelector('p');
  if(description)description.textContent='마지막 세대만 보지 않고 선택 세대까지 관측한 해를 누적합니다. 원시 MOEA 결과와 감사 파생 후보를 구분하고, 동일계약 수학 기준과 비용 격차를 계산한 뒤 정량목표 통과 해만 Hamming 거리로 배치군을 나눕니다.';
  $('qualitySetCalculate').textContent='신뢰성 근거 계산';
  const evidence=$('confidenceEvidence'),multiSeed=$('multiSeedEvidence'),qualitySection=$('solutionQualitySection');
  if(multiSeed&&qualitySection)qualitySection.insertAdjacentElement('beforebegin',multiSeed);
  const referenceBody=$('referenceEvidenceBody');
  if(referenceBody&&!$('robustCostProof'))referenceBody.insertAdjacentHTML('afterend','<button type="button" id="robustCostProof" class="secondary" disabled>최소비용 정밀검산</button><p id="robustCostProofStatus" class="qualitySetHint">신뢰성 근거 계산 후, 지원되는 목적함수 계약에서 비용별 가능성을 검사합니다.</p><div id="robustCostProofTable" class="tableWrap" hidden></div>');
 }
 $('robustCostProof')?.addEventListener('click',calculateRobustProof);
 $('qualitySetThreshold')?.addEventListener('change',()=>{
  robustProofSerial++;multiSeedSerial++;robustProof=null;multiSeedData=null;multiSeedActiveJobId=null;if($('multiSeedResult'))$('multiSeedResult').hidden=true;if($('multiSeedProgressWrap'))$('multiSeedProgressWrap').hidden=true;if($('multiSeedCancel'))$('multiSeedCancel').hidden=true;
  if($('robustCostProof'))$('robustCostProof').disabled=!setResult||!robustProofAvailable;
  if($('robustCostProofStatus'))$('robustCostProofStatus').textContent='Hamming 기준이 변경되어 이전 최소비용 검산을 지웠습니다. 신뢰성 근거 계산 후 다시 검산하세요.';
  if($('robustCostProofTable')){$('robustCostProofTable').hidden=true;$('robustCostProofTable').innerHTML='';$('robustCostProofTable').closest('article')?.classList.remove('robustProofExpanded');}
  if(setResult)calculateSet();
 });
 async function prepareExactPair(result){
  const pooled=result.pooled_layouts||{},points=new Map((pooled.points||[]).map(point=>[point.decision_sha256,point])),pair=pooled.exact_cost_pair;
  if(!pair)return null;
  const left=points.get(pair.left_decision_sha256),right=points.get(pair.right_decision_sha256);
  if(!left||!right)throw new Error('비교 지도 결속 실패: 정확비용 배치쌍이 통합 원시해 목록에 없습니다.');
  const [leftDigest,rightDigest]=await Promise.all([pointDigest(left),pointDigest(right)]);
  if(leftDigest!==pair.left_decision_sha256||rightDigest!==pair.right_decision_sha256)throw new Error('비교 지도 결속 실패: 정확비용 배치쌍의 결정벡터 해시가 응답과 다릅니다.');
  const leftBits=left.mask.flatMap(state=>[(state===1||state===3)?1:0,(state===2||state===3)?1:0]),rightBits=right.mask.flatMap(state=>[(state===1||state===3)?1:0,(state===2||state===3)?1:0]);
  const diff=leftBits.map((value,index)=>value===rightBits[index]?null:{candidate_index:Math.floor(index/2)+1,sensor:index%2===0?'Radar':'EO/IR',left_installed:!!value,right_installed:!!rightBits[index]}).filter(Boolean),declared=pair.changed_bits||[];
  if(diff.length!==pair.hamming_distance||JSON.stringify(diff)!==JSON.stringify(declared))throw new Error('비교 지도 결속 실패: 정확비용 배치쌍의 dH 또는 변경 비트가 원시 mask와 다릅니다.');
  return {pair,left,right,declared};
 }
 async function renderMultiSeed(result,guard){
  const current=()=>!guard||(guard.serial===multiSeedSerial&&setContext?.last?.id===guard.runId&&setContext?.generation===guard.generation&&setContext?.problem?.problem_sha256===guard.problemSha&&+$('qualitySetThreshold').value===guard.threshold);
  if(!current())return false;
  const verifiedPair=await prepareExactPair(result);
  if(!current())return false;
  multiSeedData=result;
  const exact=result.exact_two_grid_target_cost,rows=result.runs||[],aggregate=result.aggregate||{},gate=result.integrity_gate||{};
  const ci=aggregate.wilson_95_interval||[],rate=aggregate.exact_raw_hit_rate;
  let summary=$('multiSeedSummary');if(!summary){summary=document.createElement('section');summary.id='multiSeedSummary';summary.className='multiSeedSummary';$('multiSeedRows').closest('.tableWrap').before(summary);}
  summary.innerHTML=`<article><span>반복 계산 무결성</span><strong class="${gate.status==='PASS'?'passText':'failText'}">${gate.status||'미확인'}</strong><small>고유 seed ${gate.unique_seed_count??0} · 고유 실행 ${gate.unique_run_id_count??0} · 완료 ${gate.completed_run_count??0}</small></article><article><span>정확비용 원시해 도달</span><strong>${aggregate.exact_raw_hit_count??0} / ${aggregate.run_count??rows.length}</strong><small>관측률 ${rate==null?'미계산':pct(rate)} · Wilson 95% ${ci.length?`${pct(ci[0])}–${pct(ci[1])}`:'미계산'}</small></article><article><span>도달 기원</span><strong>${aggregate.hit_origin_counts?.EVOLUTION_DISCOVERED??0}개 진화 발견</strong><small>초기화 보존 ${aggregate.hit_origin_counts?.INITIALIZER_PRESERVED??0} · 0세대 비seed ${aggregate.hit_origin_counts?.GENERATION0_NON_SEEDED??0}</small></article><article><span>first-hit 탐색비용</span><strong>${aggregate.first_hit_nfe?.budget_median_reached?`${Number(aggregate.first_hit_nfe.median_success_only).toLocaleString()} NFE`:'예산 내 중앙값 미도달'}</strong><small>성공만 범위 ${aggregate.first_hit_nfe?.minimum??'–'}–${aggregate.first_hit_nfe?.maximum??'–'} · 우측검열 ${aggregate.first_hit_nfe?.right_censored_runs??0}</small></article><article><span>최선 원시 비용</span><strong>${aggregate.best_raw_cost?.minimum??'–'}–${aggregate.best_raw_cost?.maximum??'–'}점</strong><small>중앙값 ${aggregate.best_raw_cost?.median??'–'} · 정확 기준 ${exact??'–'}점</small></article><article><span>엄격 국소검사 통과</span><strong>${aggregate.strict_raw_promotion_total??0}개</strong><small>비용 도달과 별개인 삭제·dH=2 반례 검사</small></article>`;
  $('multiSeedRows').innerHTML=rows.map(row=>{const best=row.best_raw,firstExact=row.first_exact_raw_observed,gap=best?.gap_to_exact_cost,sensitivity=(row.hamming_sensitivity||[]).map(item=>`dH&lt;${item.threshold} ${item.cluster_count}군`).join('<br>');const ranges=row.objective_evidence?.ranges||[],dr=ranges.find(item=>item.objective==='detection'),ir=ranges.find(item=>item.objective==='identification'),cr=ranges.find(item=>item.objective==='cost');return `<tr><th>seed ${row.seed}<br><small>${row.run_id.slice(0,8)} · ${row.terminal_state}</small></th><td>${row.search_nfe.toLocaleString()}</td><td>${row.cumulative_raw_front_layouts.toLocaleString()}개<br><small>D ${dr?`${pct(dr.minimum)}–${pct(dr.maximum)} · 100% ${pct(dr.saturation_100_rate)}`:'–'}<br>I ${ir?`${pct(ir.minimum)}–${pct(ir.maximum)} · 100% ${pct(ir.saturation_100_rate)}`:'–'}<br>비용 ${cr?`${cr.minimum}–${cr.maximum} · ${cr.unique_values}단계`:'–'}</small></td><td>${row.two_grid_raw_layouts.toLocaleString()}개</td><td>${best?`#${best.id} · ${best.cost}점<br><small>${gap===0?'정확비용 도달':`정확 ${exact}점보다 +${gap}점 · ${best.gap_lattice_steps}단계`}</small>`:'해당 없음'}</td><td>${firstExact?`${firstExact.generation}세대 · NFE ${firstExact.nfe.toLocaleString()}<br><small>${firstExact.origin}</small>`:'예산 내 정확비용 미관측'}</td><td>${sensitivity||`${row.hamming_cluster_count}군`}</td><td>${row.strict_raw_promotion_count}개</td><td><button type="button" class="multiSeedOpen" data-run="${row.run_id}" data-id="${best?.id??''}">지도 보기</button></td></tr>`;}).join('');
  $('multiSeedStatus').innerHTML=`<strong>동일 문제·설정·NFE ${rows.length}개 실행 · 무결성 ${gate.status||'미확인'}</strong> · 500m·250m 동시통과 정확 최소비용 ${exact??'미확정'}점`;
  $('multiSeedMeaning').textContent=`${result.meaning||''} ${result.hamming_scope||''} ${result.claim_boundary||''} 엄격 승격 0개는 비용 정답 도달 실패가 아니라, 모든 허용 dH=2 교환에서까지 개선 반례가 없음을 증명하지 못했다는 별도 판정입니다.`;
  $('multiSeedResult').hidden=false;
  let progression=$('multiSeedProgression');if(!progression){progression=document.createElement('section');progression.id='multiSeedProgression';progression.className='multiSeedProgression';$('multiSeedMeaning').before(progression);}
  const maxGeneration=Math.max(1,...rows.flatMap(row=>(row.approach_progression||[]).map(point=>point.generation))),rawMaxGap=Math.max(2,...rows.flatMap(row=>(row.approach_progression||[]).map(point=>point.gap_to_exact_cost??0))),gapCeiling=Math.ceil(rawMaxGap/2)*2,chartWidth=900,chartHeight=300,pad=48,palette=['#087ea4','#b45309','#7c3aed','#15803d','#be123c','#0369a1','#a16207','#6d28d9','#0f766e','#c2410c'];
  const line=(row,index)=>{const points=(row.approach_progression||[]).filter(point=>point.gap_to_exact_cost!==null);return `<polyline class="gapSeed" style="stroke:${palette[index%palette.length]}" points="${points.map(point=>`${pad+(chartWidth-2*pad)*point.generation/maxGeneration},${chartHeight-pad-(chartHeight-2*pad)*point.gap_to_exact_cost/gapCeiling}`).join(' ')}"/>`;};
  progression.innerHTML=`<div class="sectionHead"><div><h4>세대별 정확비용 접근</h4><p>${result.approach_scope||''}</p></div></div><div class="gapLegend">${rows.map((row,index)=>`<span><i style="background:${palette[index%palette.length]}"></i>seed ${row.seed}</span>`).join('')}</div><svg class="multiSeedGapChart" viewBox="0 0 ${chartWidth} ${chartHeight}" role="img" aria-label="세대별 이중격자 통과 원시해의 정확비용 격차"><line x1="${pad}" y1="${chartHeight-pad}" x2="${chartWidth-pad}" y2="${chartHeight-pad}"/><line x1="${pad}" y1="${pad}" x2="${pad}" y2="${chartHeight-pad}"/><text x="${pad}" y="${chartHeight-12}">0세대</text><text x="${chartWidth-pad-55}" y="${chartHeight-12}">${maxGeneration}세대</text><text x="8" y="${chartHeight-pad+4}">0점</text><text x="8" y="${pad+4}">+${gapCeiling}점</text>${rows.map(line).join('')}</svg><div class="multiSeedProgressTables">${rows.map(row=>`<details><summary>seed ${row.seed} · 11개 checkpoint 펼치기</summary><div class="tableWrap"><table><thead><tr><th>세대</th><th>NFE</th><th>발견된 최종 안정 원시해</th><th>최저비용</th><th>정확 격차</th></tr></thead><tbody>${(row.approach_progression||[]).map(point=>`<tr><td>${point.generation}</td><td>${point.nfe.toLocaleString()}</td><td>${point.observed_final_stable_raw_layouts}</td><td>${point.best_cost??'아직 없음'}</td><td>${point.gap_to_exact_cost===null?'계산 전':point.gap_to_exact_cost===0?'0 · 도달':`+${point.gap_to_exact_cost}`}</td></tr>`).join('')}</tbody></table></div></details>`).join('')}</div>`;
  const pooled=result.pooled_layouts||{},active=pooled.active_clusters||{},pooledPoints=new Map((pooled.points||[]).map(point=>[point.decision_sha256,point]));
  let pooledPanel=$('multiSeedPooled');if(!pooledPanel){pooledPanel=document.createElement('section');pooledPanel.id='multiSeedPooled';pooledPanel.className='multiSeedPooled';$('multiSeedMeaning').before(pooledPanel);}
  const roleLabel={MEDOID:'군집 중심',LOW_COST:'군집 최저비용',TARGET_MARGIN:'목표 여유'};
  const pe=pooled.objective_evidence||{},pr=new Map((pe.ranges||[]).map(row=>[row.objective,row])),pd=pe.bands?.detection||{},pi=pe.bands?.identification||{};
  const pooledRange=(name,performance)=>{const row=pr.get(name);if(!row)return '자료 없음';return performance?`${pct(row.minimum)}–${pct(row.maximum)} · 고유 ${row.unique_values}단계 · 100% ${pct(row.saturation_100_rate||0)}`:`${row.minimum}–${row.maximum}점 · 고유 ${row.unique_values}단계`;};
  pooledPanel.innerHTML=`<div class="sectionHead"><div><h4>10개 실행을 합친 배치구조 대안</h4><p>${pooled.meaning||''}</p></div></div><div class="pooledSummary"><article><span>안정 원시 관측</span><strong>${pooled.stable_occurrence_count??0}개</strong><small>동일 물리배치 통합 전</small></article><article><span>고유 물리배치</span><strong>${pooled.unique_physical_layout_count??0}개</strong><small>중복 관측 ${pooled.duplicate_occurrence_count??0}개 통합</small></article><article><span>통합 경험적 비지배</span><strong>${pooled.pooled_empirical_nondominated_layout_count??0}개</strong><small>교차 seed 지배 ${pooled.cross_seed_dominated_layouts_removed??0}개 제외</small></article><article><span>고유 목적벡터</span><strong>${pooled.unique_objective_vector_count??0}개</strong><small>같은 목적값의 다른 배치 ${pooled.layouts_in_objective_ties??0}개</small></article><article><span>dH&lt;${pooled.active_threshold??'–'} 구조군</span><strong>${active.summary?.cluster_count??0}군</strong><small>${(pooled.hamming_sensitivity||[]).map(item=>`dH&lt;${item.threshold} ${item.cluster_count}군`).join(' · ')}</small></article><article><span>두 격자 최소비용 도달</span><strong>${pooled.exact_cost_layout_count??0}개</strong><small>500m·250m 목표를 만족한 ${exact??'–'}점 원시배치</small></article><article><span>500m 3목적 국소검사 통과</span><strong>${pooled.strict_raw_promotion_count??0}개</strong><small>두 격자 최소비용 도달과 다른 판정</small></article></div><div class="pooledObjectiveEvidence"><strong>통합 비지배 ${pe.layout_count??0}개 배치의 500m 목적축 분포</strong><dl><dt>탐지</dt><dd>${pooledRange('detection',true)} · 95–97% ${pd['95_to_below_97']||0} · 97–99% ${pd['97_to_below_99']||0} · 99–100% ${pd['99_to_below_100']||0} · 100% ${pd['100']||0}</dd><dt>식별</dt><dd>${pooledRange('identification',true)} · 90–92% ${pi['90_to_below_92']||0} · 92–95% ${pi['92_to_below_95']||0} · 95–100% ${pi['95_to_below_100']||0} · 100% ${pi['100']||0}</dd><dt>비용</dt><dd>${pooledRange('cost',false)}</dd></dl><p>이 전선은 500m·250m 정량목표를 모두 유지한 원시배치를 먼저 고른 뒤, 최적화에 사용한 500m 탐지·식별·비용으로 다시 비지배 판정한 결과입니다. 250m 성능은 강건성 통과열이며 네 번째 목적함수가 아닙니다.</p></div><div class="pooledClusters">${(active.clusters||[]).map((cluster,index)=>`<article class="pooledCluster"><header><span>배치구조군 ${index+1}</span><strong>${cluster.member_count}개 배치 · 직경 ${cluster.diameter}</strong><small>${cluster.seed_support_count}개 seed 지지 · ${cluster.seed_support.join(', ')}</small></header><div class="pooledRepresentatives">${cluster.representatives.map(rep=>`<button type="button" class="pooledOpen" data-sha="${rep.decision_sha256}"><span>${rep.roles.map(role=>roleLabel[role]||role).join(' · ')}</span><strong>${rep.global_id} · ${rep.cost}점</strong><small>탐지 ${pct(rep.performance[0])} · 식별 ${pct(rep.performance[1])} · R ${rep.sensor_counts?.[0]??'–'} / E ${rep.sensor_counts?.[1]??'–'}</small></button>`).join('')}</div><label>이 구조군의 실제 배치<select class="pooledMemberSelect"><option value="">지도에서 볼 배치 선택</option>${cluster.member_decision_sha256.map(sha=>{const point=pooledPoints.get(sha);return point?`<option value="${sha}">${point.global_id} · ${point.cost}점 · seed ${point.supporting_seeds.join(',')}</option>`:'';}).join('')}</select></label></article>`).join('')}</div><p class="qualitySetHint">${pooled.claim_boundary||''}</p>`;
  const pair=pooled.exact_cost_pair,left=pair&&pooledPoints.get(pair.left_decision_sha256),right=pair&&pooledPoints.get(pair.right_decision_sha256);
  let pairPanel=$('multiSeedExactPair');if(!pairPanel){pairPanel=document.createElement('section');pairPanel.id='multiSeedExactPair';pairPanel.className='multiSeedExactPair';$('multiSeedMeaning').before(pairPanel);}
  if(pair&&left&&right&&verifiedPair){const declared=verifiedPair.declared,changes=declared.map(change=>`후보 ${change.candidate_index} · ${change.sensor}: ${change.left_installed?'설치':'미설치'} → ${change.right_installed?'설치':'미설치'}`).join(' · ');pairPanel.hidden=false;pairPanel.innerHTML=`<div class="sectionHead"><div><h4>같은 ${pair.cost}점, 다른 물리배치</h4><p>두 지도는 같은 축척·같은 후보지·같은 평가영역입니다. 목적값이 같아도 설치구조가 다를 수 있음을 직접 비교합니다.</p></div><strong>dH=${pair.hamming_distance}</strong></div><div class="exactPairGrid"><article><h5>${pair.left_global_id}</h5><p>탐지 ${pct(left.performance[0])} · 식별 ${pct(left.performance[1])} · ${left.cost}점</p><div class="map">${LiveCore.map(setContext.problem,left,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false})}</div></article><article><h5>${pair.right_global_id}</h5><p>탐지 ${pct(right.performance[0])} · 식별 ${pct(right.performance[1])} · ${right.cost}점</p><div class="map">${LiveCore.map(setContext.problem,right,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false})}</div></article></div><p class="exactPairChanges"><strong>달라진 설치 비트 ${declared.length}개</strong> · ${changes}</p><p>${pair.meaning}</p>`;}else pairPanel.hidden=true;
  let mapCard=$('multiSeedMapCard');if(!mapCard){mapCard=document.createElement('article');mapCard.id='multiSeedMapCard';mapCard.className='multiSeedMapCard';mapCard.hidden=true;mapCard.innerHTML='<div><span id="multiSeedMapBadge"></span><h4 id="multiSeedMapTitle"></h4><p id="multiSeedMapMetrics"></p><p id="multiSeedMapLineage"></p><dl id="multiSeedMapAudit" class="pooledAudit"></dl></div><div id="multiSeedMap" class="map"></div><p><a id="multiSeedRunLink">이 실행의 전체 해집합 열기</a></p>';$('multiSeedMeaning').before(mapCard);}
  const openMap=async(point,badge)=>{if(!point)return;const physicalBits=point.mask.flatMap(state=>[(state===1||state===3)?1:0,(state===2||state===3)?1:0]),bytes=new Uint8Array(physicalBits),digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');if(digest!==point.decision_sha256){$('multiSeedStatus').textContent='지도 결속 실패: 선택 배치의 결정벡터 해시가 응답과 다릅니다.';return;}const audit=point.local_diagnostics||{},swapLabels={COMPLETE_NO_WITNESS:'허용 교환 전수 · 개선 반례 없음',COMPLETE_WITNESS_FOUND:'허용 교환에서 개선 반례 발견',NOT_ELIGIBLE_AFTER_DELETE_OR_GRID_SCREEN:'500m 삭제·250m 유지 선행검사에서 탈락해 교환 미실행'};mapCard.hidden=false;$('multiSeedMapBadge').textContent=badge;$('multiSeedMapTitle').textContent=`${point.global_id||'#'+point.id} · ${point.cost}점`;$('multiSeedMapMetrics').textContent=`탐지 ${pct(point.performance[0])} · 식별 ${pct(point.performance[1])} · 두 격자 정량목표 최소비용 격차 ${point.exact_cost_gap===0?'없음':`+${point.exact_cost_gap??point.gap_to_exact_cost}점`}`;$('multiSeedMapLineage').textContent=`seed ${point.seed} · 실행 ${point.run_id.slice(0,8)} · 원시 #${point.raw_id??point.id} · ${point.first_observed?.generation??'–'}세대/NFE ${point.first_observed?.nfe?.toLocaleString()??'–'} · ${(point.decision_sha256||'').slice(0,12)}. 동일배치 관측 ${point.occurrence_count??1}회.`;if($('multiSeedMapAudit'))$('multiSeedMapAudit').innerHTML=`<dt>500m 한 대 삭제</dt><dd>${audit.one_delete_exhaustive?`${audit.one_delete_tested}/${audit.one_delete_possible} 전수 · ${audit.one_delete_minimal?'3목적 지배 반례 없음':'3목적 지배 반례 발견'} · ${audit.target_resource_minimal?'500m 목표유지 삭제 없음':'500m 목표유지 삭제 가능'}`:'검사 미완료'}</dd><dt>500m dH=2 교환</dt><dd>${swapLabels[audit.one_swap_status]||audit.one_swap_status||'해당 없음'}${audit.one_swap_exhaustive?` · ${audit.one_swap_tested}/${audit.one_swap_possible} 전수`:''}</dd><dt>500m 3목적 국소검사</dt><dd>${audit.promotion_candidate?'통과':'불통과'} · 두 격자 44점 최소비용 판정과 별개</dd>`;$('multiSeedMap').innerHTML=LiveCore.map(setContext.problem,point,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false});const target=new URL(location.href);target.searchParams.set('run',point.run_id);target.searchParams.delete('solution');target.hash='solutionQualitySection';$('multiSeedRunLink').href=target.toString();mapCard.scrollIntoView({block:'start',behavior:'instant'});};
  document.querySelectorAll('.pooledOpen').forEach(button=>button.onclick=()=>openMap(pooledPoints.get(button.dataset.sha),'10-seed 통합 구조군 · 실제 NSGA-III 원시해'));
  document.querySelectorAll('.pooledMemberSelect').forEach(select=>select.onchange=()=>{if(select.value)openMap(pooledPoints.get(select.value),'10-seed 통합 구조군 · 직접 선택 원시해');});
  document.querySelectorAll('.multiSeedOpen').forEach(button=>button.onclick=async()=>{const row=(multiSeedData?.runs||[]).find(item=>item.run_id===button.dataset.run),point=row?.best_raw;if(!row||!point||String(point.id)!==button.dataset.id)return;const physicalBits=point.mask.flatMap(state=>[(state===1||state===3)?1:0,(state===2||state===3)?1:0]),bytes=new Uint8Array(physicalBits),digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');if(digest!==point.decision_sha256){$('multiSeedStatus').textContent='지도 결속 실패: 선택 배치의 결정벡터 해시가 응답과 다릅니다.';return;}mapCard.hidden=false;$('multiSeedMapBadge').textContent=`seed ${row.seed} · 실제 NSGA-III 원시 관측해`;$('multiSeedMapTitle').textContent=`#${point.id} · ${point.cost}점`;$('multiSeedMapMetrics').textContent=`탐지 ${pct(point.performance[0])} · 식별 ${pct(point.performance[1])} · 정확비용 격차 ${point.gap_to_exact_cost===0?'없음':`+${point.gap_to_exact_cost}점`}`;$('multiSeedMapLineage').textContent=`${point.first_observed.generation}세대 · NFE ${point.first_observed.nfe.toLocaleString()}에 첫 관측 · 결정벡터 ${(point.decision_sha256||'').slice(0,12)}. 수학 참조해나 감사 파생해가 아닙니다.`;$('multiSeedMap').innerHTML=LiveCore.map(setContext.problem,point,{layer:'all',candidates:true,demand:true,defense:true,candidateLabels:false});const target=new URL(location.href);target.searchParams.set('run',row.run_id);target.searchParams.delete('solution');target.hash='solutionQualitySection';$('multiSeedRunLink').href=target.toString();mapCard.scrollIntoView({block:'start',behavior:'instant'});});
  return true;
 }
 async function multiSeedRequest(path){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try{const response=await fetch(path,{method:'GET',signal:controller.signal,cache:'no-store'});const text=await response.text();let data;try{data=JSON.parse(text);}catch{throw new Error('다중 seed 응답 형식을 확인할 수 없습니다.');}if(!response.ok)throw new Error(data?.error||data?.message||`다중 seed 계산 오류 (HTTP ${response.status})`);return data;}
  catch(e){if(e.name==='AbortError')throw new Error('통합 계산 상태 요청이 20초 안에 응답하지 않았습니다. 백그라운드 작업은 별도로 계속될 수 있습니다.');throw e;}
  finally{clearTimeout(timer);}
 }
 function updateMultiSeedProgress(job){ensureMultiSeedControls();const wrap=$('multiSeedProgressWrap'),bar=$('multiSeedProgress'),text=$('multiSeedProgressText'),cancel=$('multiSeedCancel');wrap.hidden=false;bar.value=job.progress_percent||0;text.textContent=`${job.progress_percent||0}% · ${job.message||job.phase||''}`;cancel.hidden=!['queued','running'].includes(job.state);multiSeedActiveJobId=job.job_id||null;}
 async function waitForEvidenceJob(job,request){
  for(let poll=0;poll<1200;poll++){
   if(request!==multiSeedSerial)return null;updateMultiSeedProgress(job);
   if(job.state==='completed'){if(!job.result)throw new Error('완료 작업에 통합 결과가 없습니다.');return job.result;}
   if(job.state==='failed'||job.state==='interrupted')throw new Error(job.message||'백그라운드 통합 계산에 실패했습니다. 계산 버튼으로 다시 시도하세요.');
   if(job.state==='cancelled')throw new Error('통합 계산이 중단되었습니다. 다시 계산할 수 있습니다.');
   await new Promise(resolve=>setTimeout(resolve,750));job=await multiSeedRequest(job.poll_url);
  }
  throw new Error('통합 계산 상태를 15분 동안 확인했지만 완료되지 않았습니다. 작업 ID를 유지하고 다시 연결하세요.');
 }
 async function cancelMultiSeed(){if(!multiSeedActiveJobId)return;try{const cfg=await multiSeedRequest('/api/config'),response=await fetch(`/api/evidence-jobs/${multiSeedActiveJobId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json','X-Run-Token':cfg.token},body:'{}'});if(!response.ok)throw new Error('중단 요청이 거부되었습니다.');$('multiSeedStatus').textContent='통합 계산 중단을 요청했습니다.';}catch(e){$('multiSeedStatus').textContent='통합 계산을 중단하지 못했습니다. '+e.message;}}
 async function calculateMultiSeed(){
  if(!setContext?.last||setContext.generation===undefined)return;
  const button=$('multiSeedCalculate'),status=$('multiSeedStatus'),threshold=+$('qualitySetThreshold').value,request=++multiSeedSerial,runId=setContext.last.id,generation=setContext.generation,problemSha=setContext.problem.problem_sha256;
  button.disabled=true;ensureMultiSeedControls();status.textContent='백그라운드 통합 계산을 시작하고 있습니다. 화면을 떠나도 저장 실행은 변경되지 않습니다.';
  try{let job=await multiSeedRequest(`/api/jobs/${runId}/multi-seed-quality?generation=${generation}&threshold=${threshold}&seconds=60&expected_seed_count=10&async=1`);if(request!==multiSeedSerial)return;const result=job.schema==='LIVE_MULTI_SEED_APPROACH_V4'?job:await waitForEvidenceJob(job,request);if(!result||request!==multiSeedSerial)return;if(result.schema!=='LIVE_MULTI_SEED_APPROACH_V4'||result.baseline_run_id!==runId||result.generation!==generation||result.problem_sha256!==problemSha||result.objective_contract!=='layered_mission_v7'||result.hamming_threshold!==threshold||result.integrity_gate?.status!=='PASS'||result.integrity_gate?.expected_seed_count!==10||result.integrity_gate?.unique_seed_count!==10||result.integrity_gate?.unique_run_id_count!==10||result.integrity_gate?.raw_replay_pass_count!==10||result.pooled_layouts?.status!=='PASS'||result.pooled_layouts?.source_seed_count!==10||result.pooled_layouts?.source_run_count!==10||(result.runs||[]).some(row=>(row.best_raw&&row.best_raw.provenance!=='RAW_MOEA_OBSERVED')||row.raw_replay_status!=='PASS_FULL_PREFIX_EXACT'||row.raw_replay_max_error!==0)||(result.pooled_layouts?.points||[]).some(point=>point.provenance!=='RAW_MOEA_OBSERVED'))throw new Error('다중 seed 응답의 스키마·실행·세대·문제·목적함수·Hamming 기준·원시계보 무결성이 현재 화면과 다릅니다.');const rendered=await renderMultiSeed(result,{serial:request,runId,generation,problemSha,threshold});if(!rendered)return;$('multiSeedProgress').value=100;$('multiSeedProgressText').textContent='100% · 계산 완료';}
  catch(e){status.textContent='다중 seed 비교를 완료하지 못했습니다. '+e.message;}
  finally{button.disabled=false;if($('multiSeedCancel'))$('multiSeedCancel').hidden=true;multiSeedActiveJobId=null;}
 }
 ensureMultiSeedControls();$('multiSeedCancel')?.addEventListener('click',cancelMultiSeed);
 $('multiSeedCalculate')?.addEventListener('click',calculateMultiSeed);
 async function update(request,last,point,problem,generation){
  const setKey=last&&generation!==undefined?`${last.id}:${generation}`:'';
  const oldSetKey=setContext?.last&&setContext.generation!==undefined?`${setContext.last.id}:${setContext.generation}`:'';
  if(setKey!==oldSetKey){multiSeedActiveJobId=null;if($('multiSeedProgressWrap'))$('multiSeedProgressWrap').hidden=true;if($('multiSeedCancel'))$('multiSeedCancel').hidden=true;}
  if(setKey!==oldSetKey){setRequestSerial++;robustProofSerial++;multiSeedSerial++;const contract=last?.config?.objective_contract||problem?.objective_contract;setRobustProofControl(contract?contract==='layered_mission_v7':true,false);if($('qualitySetCalculate'))$('qualitySetCalculate').disabled=false;setResult=null;setSelected=null;robustProof=null;multiSeedData=null;$('qualitySetResult').hidden=true;$('qualitySetStatus').textContent='계산 전입니다. 선택한 세대까지 실제로 관측된 원시 해집합을 사용합니다.';if($('multiSeedResult'))$('multiSeedResult').hidden=true;if($('multiSeedMapCard'))$('multiSeedMapCard').hidden=true;if($('multiSeedStatus'))$('multiSeedStatus').textContent='현재 실행과 동일한 저장 실행을 찾아 계산합니다.';if($('robustCostProofTable')){$('robustCostProofTable').hidden=true;$('robustCostProofTable').closest('article')?.classList.remove('robustProofExpanded');}}
  setContext={request,last,problem,generation};
  if($('multiSeedCalculate'))$('multiSeedCalculate').disabled=!last||generation===undefined;
  if(!last||!point||generation===undefined){clear();return;}
  const next=`${last.id}:${generation}:${point.id}`;if(next===key)return;key=next;const mine=++serial;
  $('qualityContent').hidden=true;$('qualityLoading').hidden=false;$('qualityLoading').textContent=`배치 #${point.id}의 원시 재평가와 탐색 진단을 계산하고 있습니다.`;$('currentMap')?.classList.remove('integrityBlocked');gate({integrity:'PENDING',constraint:'PENDING',search:'NOT_CHECKED',run_id:last.id,generation,solution_id:point.id});
  try{let q=cache.get(next);if(!q){q=await request(`/api/jobs/${last.id}/quality?solution=${point.id}&generation=${generation}`);cache.set(next,q);}if(mine!==serial||next!==key)return;LiveQualityLineage.validateQuality(q,{run_id:last.id,generation,solution_id:point.id,problem_sha256:problem.problem_sha256,mask:point.mask,decision_sha256:point.identity?.decision_sha256,row_binding_sha256:point.identity?.row_binding_sha256});render(q,problem);}catch(e){if(mine!==serial)return;gate({integrity:'UNAVAILABLE',constraint:'UNKNOWN',search:'NOT_CHECKED',run_id:last.id,generation,solution_id:point.id});$('qualityContent').hidden=true;$('qualityLoading').hidden=false;$('qualityLoading').textContent='해품질 진단을 불러오지 못했습니다. 기존 배치를 최적·추천 해로 해석하지 마세요. '+e.message;$('qualityDecision').textContent='진단 미완료';$('qualityDecision').className='qualityDecision warn';}
 }
 return{update,clear,applyGate:gate};
})();
