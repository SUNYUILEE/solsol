'use strict';
// One common result collection across models, normal maps and enlarged maps.
let placementScope='archive',placementPage=null,placementPending=false,placementError='',placementEpoch=0;
let placementSpatialEpoch=0,placementSpatialSequence=0;
const placementSpatialHolds=new Set();
function placementDefersMainSpatial(){
 if(!configured()||!run||placementLive())return false;
 const holds=[...placementSpatialHolds].filter(t=>t.sequence===placementSpatialSequence&&t.epoch===placementSpatialEpoch&&t.cid===draft.sensor&&t.id===run.run_id);
 for(const hold of holds)hold.deferred=true;
 return holds.length>0;
}
let placementSelection='primary100',placementArea='all';
let subsetComparison=null;
const subsetComparisonKey=p=>p.subset_fidelity?.comparison_basis?.sha256||null;
const subsetComparisonStatus=p=>!subsetComparison?'NONE':!subsetComparison.key||!subsetComparisonKey(p)?'MISSING_BASIS':subsetComparison.key===subsetComparisonKey(p)?'SAME_BASIS':'DIFFERENT_BASIS';
const representativeSelection=v=>['primary100','performance100','front100'].includes(v);
let frontRadius=2,frontGroup=0,frontRepresentatives=false,frontQuery='';
let placementLayoutScope='all';
function layoutSensorName(id){const idx=run?.registry?.sensor_order.indexOf(id)??-1;return run?.problem?.sensor_names?.[idx]||({radar:'Radar',rf:'RF',rf_scanner:'RF',eoir:'EO/IR'})[id]||id;}
function layoutScopeOptions(){return [['all','전체 센서 배치 보기'],...(run?.registry?.sensor_order||[]).map(id=>[id,layoutSensorName(id)+' 독립 배치만 보기'])];}
function layoutHammingPrefix(){return placementPage?.layout_scope&&placementPage.layout_scope!=='all'?layoutSensorName(placementPage.layout_scope)+' ':'';}
const frontCollection=()=>placementScope==='observed'&&['history','archive'].includes(placementSelection);
function placementLive(){return configured()&&(!terminal.has(run.state)||placementScope==='generation');}
function placementPerformanceMetrics(){return configured()?run.research_configuration.objective_ids.filter(id=>id!=='cost').map(id=>run.metadata.metrics.find(m=>m.id===id)).filter(Boolean):[];}
function placementMetricText(id,value){const m=run.metadata.metrics.find(m=>m.id===id);return m?valueText(m,value):String(value);}
const placementComparisons=new Map();
const placementKey=()=>run?run.experiment_contract_id+':'+run.run_id+':'+run.generation:'';
function placementAreaMatches(row){
 if(placementArea==='all')return true;
 const r=row.area_relation;if(!r)return false;
 if(placementArea.startsWith('coverage_')){const v=r.model_coverage_values||[];return !!v.length&&(placementArea==='coverage_any'?v.some(x=>x>0):placementArea==='coverage_all'?v.every(x=>x>0):v.every(x=>x===0));}
 if(placementArea==='empty')return r.installed===0;
 if(!r.installed)return false;
 const n=placementArea.startsWith('range_')?r.range_intersects:r.site_inside;
 return n!==null&&(placementArea.endsWith('_any')?n>0:placementArea.endsWith('_all')?n===r.installed:n===0);
}
function observedResultRows(){
 if(placementLive())return (run.generation_population||[]).filter(r=>r.installation_audit?.hard_pass);
 if(placementScope!=='observed')return run?.rows||[];
 if(placementPending||placementError)return [];
 if(!placementPage||placementPage.key!==placementKey())return [];
 return dock==='comparison'?[...placementComparisons.values()].filter(r=>compared.has(r.id)&&placementAreaMatches(r)):placementPage.rows;
}
function placementRefresh(){renderDock();renderMaps();renderInspector();expandControlsRefresh();}
function renderSubsetFidelity(host,p){
 const q=p.subset_fidelity;if(!q)return;
 const section=document.createElement('details');section.className='subsetFidelity';
 const title=document.createElement('summary');title.textContent=`추려 본 배치가 놓치는 것은? · ${q.reference_count.toLocaleString()}개 중 ${q.selected_count.toLocaleString()}개`;section.append(title);host.append(section);
 if(q.status!=='CALCULATED'){noteText(section,q.status==='EMPTY_REFERENCE'?'현재 조건을 통과한 기준 배치가 없어 비교할 수 없습니다.':'선택된 배치가 없어 축약 손실을 계산하지 않았습니다.');return;}
 const perf=q.performance,structure=q.structure,short=v=>Number(v).toLocaleString(undefined,{maximumFractionDigits:5});
 if(p.front_preservation){const f=p.front_preservation;noteText(section,`현재 필터 안의 비지배 성능 ${f.selected_front_vectors}/${f.front_vectors}종류 · 비지배 설치 배치 ${f.selected_front_layouts}/${f.front_layouts}개 보존. ${f.all_front_vectors_preserved?'관측된 비지배 성능을 모두 포함합니다.':'100개 제한으로 비지배 성능 일부를 생략했습니다. 아래 손실을 확인하세요.'}`);noteText(section,'목적별 최상 배치 → 비지배 성능 대표 → 비지배 위치 다양성 → 남은 자리에 성능값별 관측 대안 순으로 고릅니다. 성능이 같은 다른 위치는 별개입니다. 원래 최종 해집합을 바꾸지 않습니다.');}
 noteText(section,`같은 실행·세대·목표·영역 필터를 적용한 추출 전 ${q.reference_count.toLocaleString()}배치와 비교합니다. 페이지를 넘겨도 기준과 선택 집합은 바뀌지 않습니다.`);
 const list=document.createElement('dl');list.className='subsetNumbers';section.append(list);
 for(const [label,value] of [['성능상 평균 손실',short(perf.igd_plus)],['가장 큰 성능 손실',short(perf.worst_distance)],['가까운 대표까지 위치 차이 · 전체 평균',short(structure.mean_nearest_hamming)+'비트'],['가장 먼 위치 차이',structure.max_nearest_hamming+'비트']]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;list.append(dt,dd);}
 noteText(section,perf.igd_plus===0?'이 기준 집합의 성능을 같은 값 또는 더 좋은 값으로 대신하는 선택 배치가 있습니다. 성능 손실 0이어도 서로 다른 설치 위치를 모두 표시한다는 뜻은 아닙니다.':'대표만 보면 놓치는 성능 절충이 있습니다. 손실은 작을수록 기준 집합의 성능을 더 잘 대신합니다. 아래 전체 보기로 생략된 대안도 확인하세요.');
 noteText(section,`설치 위치는 ${structure.exact_included.toLocaleString()}/${q.reference_count.toLocaleString()}배치를 그대로 포함합니다. 위치 차이는 후보·센서 설치 비트의 차이이며, 같은 종류 한 대 이동은 보통 2비트입니다. 거리가 크다고 성능이 나쁜 것은 아닙니다.`);
 const comparisonStatus=subsetComparisonStatus(p);
 if(comparisonStatus==='SAME_BASIS'&&subsetComparison.selection!==p.selection){const old=subsetComparison.q;noteText(section,`방금 본 추출 → 현재: 평균 성능 손실 ${short(old.performance.igd_plus)} → ${short(perf.igd_plus)}, 최대 손실 ${short(old.performance.worst_distance)} → ${short(perf.worst_distance)}, 평균 위치 차이 ${short(old.structure.mean_nearest_hamming)} → ${short(structure.mean_nearest_hamming)} 비트. 기준 배치와 계산 척도가 모두 같은 비교입니다.`);}
 else if(['MISSING_BASIS','DIFFERENT_BASIS'].includes(comparisonStatus)){noteText(section,comparisonStatus==='MISSING_BASIS'?'이전 결과의 비교 기준 정보가 없어 전후 개선량을 표시하지 않습니다. 현재 조건에서 비교 버튼을 다시 누르세요.':`비교 대상이 바뀌었습니다. 이전 기준 ${subsetComparison.q.reference_count.toLocaleString()}개 → 현재 기준 ${q.reference_count.toLocaleString()}개. 아래 수치는 현재 집합의 설명이며 이전 추출보다 좋아졌다는 비교가 아닙니다.`);}
 if(['primary100','performance100'].includes(p.selection)){const compare=document.createElement('button');compare.textContent='비지배 성능 우선 100개와 비교';compare.onclick=safe(async()=>{subsetComparison={key:subsetComparisonKey(p),selection:p.selection,q:structuredClone(q)};placementSelection='front100';await loadPlacementPage(0);document.querySelectorAll('.subsetFidelity').forEach(e=>e.open=true);});section.append(compare);}
 const more=document.createElement('details'),label=document.createElement('summary');label.textContent='계산 기준과 실제 비교 배치';more.append(label);section.append(more);
 if(q.comparison_basis){const b=q.comparison_basis,src=b.source;noteText(more,`기준 고정: ${src.collection==='archive'?'현재 비지배':src.collection==='history'?'세대별 비지배 이력':'전체 관측'} · ${src.generation}세대 · ${src.targets?'저장 목표 통과만':'목표 통과·미달 모두'} · ${q.reference_count.toLocaleString()}배치. 추출 방식이나 페이지를 바꿔도 이 기준으로 계산합니다.`);noteText(more,`기준 번호 ${b.sha256.slice(0,12)}. 실행·필터·목적·원시값·계산 척도가 바뀌면 다른 번호가 됩니다. 전체 기준과 계산식 버전은 아래 근거 파일에 저장됩니다.`);}
 noteText(more,'성능 손실은 각 목적의 관측 범위를 0~1로 맞춘 뒤, 선택 배치가 기준 배치보다 나빠지는 방향의 거리를 계산한 IGD+입니다. 백분율이나 최적성 확률이 아닙니다. 동일 목적값은 한 번씩 평균하고, 위치 차이는 서로 다른 설치 배치 모두로 평균합니다. 필터가 바뀌면 기준 범위도 바뀌므로 다른 조건의 점수를 직접 비교하지 마세요.');
 const constants=q.normalization.constant_objective_ids;if(constants.length)noteText(more,'이 집합에서 값이 같아 성능 거리에서 제외: '+constants.map(id=>run.metadata.metrics.find(m=>m.id===id)?.name||id).join(', '));
 const w=perf.witness;noteText(more,`가장 큰 성능 손실의 근거: 기준 행 ${w.reference_solution_id} ↔ 선택 행 ${w.selected_solution_id}`);
 q.objective_ids.forEach((id,i)=>noteText(more,`${run.metadata.metrics.find(m=>m.id===id)?.name||id}: 기준 ${placementMetricText(id,w.reference_values[i])} → 선택 ${placementMetricText(id,w.selected_values[i])}`));
 const source=document.createElement('a');source.href=q.source;source.target='_blank';source.rel='noopener';source.textContent='부분집합 선택과 IGD+의 논문 근거';more.append(source);
 const exportButton=document.createElement('button');exportButton.textContent='이 비교의 수치·실행 근거 저장';exportButton.onclick=()=>{const blob=new Blob([JSON.stringify({run_id:p.run_id,experiment_contract_id:p.experiment_contract_id,config_sha256:p.config_sha256,generation:p.generation,nfe_boundary:p.nfe_boundary,selection:p.selection,sort:p.sort,performance_order:p.performance_order,selection_policy:p.selection_policy,front_preservation:p.front_preservation,comparison_status:subsetComparisonStatus(p),comparison:subsetComparisonStatus(p)==='SAME_BASIS'?subsetComparison:null,arrangement:p.arrangement,scope:p.scope,identity_policy:p.identity_policy,targets:p.targets,area:p.area,grouping:p.grouping,subset_fidelity:q},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='subset-'+p.run_id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};more.append(exportButton);
 if(q.selected_count<q.reference_count){const b=document.createElement('button');b.textContent='추출 전 전체 배치 보기';b.onclick=safe(async()=>{if(frontCollection()){frontGroup=0;frontRepresentatives=false;}else placementSelection='all';await loadPlacementPage(0);});section.append(b);}
}
function renderFrontGroups(host,p,prefix){
 const grouping=p.grouping;if(!grouping)return;
 const originalHost=host,options=document.createElement('details'),title=document.createElement('summary');title.textContent='비슷한 배치 묶기 · Hamming 설정';options.append(title);host.append(options);host=options;
 selectControl(host,'Hamming 묶음 기준',[0,2,4,8,16].map(n=>[String(n),n===0?'0 · 같은 배치만 합침':`대표와 ${n}비트 이내`]),String(frontRadius),v=>safe(async()=>{frontRadius=+v;frontGroup=0;await loadPlacementPage(0);})(),prefix+'frontRadius');
 selectControl(host,'배치 표시',[['all','서로 다른 배치 전체'],['representatives','그룹별 최고 성능 대표만']],frontRepresentatives?'representatives':'all',v=>safe(async()=>{frontRepresentatives=v==='representatives';placementComparisons.clear();compared.clear();await loadPlacementPage(0);})(),prefix+'frontRepresentatives');
 selectControl(host,'전체 집합의 Hamming 그룹',[['0',`전체 ${grouping.groups.length}군 · ${grouping.total_before_group}배치`],...grouping.groups.map(g=>[String(g.id),`${g.id}군 · ${g.size}배치 · 대표 행 ${g.representative_id}`])],String(frontGroup),v=>safe(async()=>{frontGroup=+v;placementComparisons.clear();compared.clear();await loadPlacementPage(0);})(),prefix+'frontGroup');
 noteText(host,'전체 성능 순서 → 같은 성능은 Hamming 다양성 순으로 정렬합니다. 가장 좋은 미분류 배치를 대표로 고릅니다. 그룹은 대표와의 거리 기준이며 구성원끼리 모두 같은 거리라는 뜻은 아닙니다. 센서 한 대 이동은 보통 2비트 차이입니다.');
 noteText(host,`페이지를 나누기 전 ${grouping.total_before_group}배치를 분류했습니다. 현재 조건 ${p.total}배치 · 표시 ${p.rows.length}배치. 반경·성능 우선순위·목표·세대를 바꾸면 그룹을 다시 만듭니다.`);
 host=originalHost;const frame=document.createElement('div');frame.style.cssText='max-height:240px;overflow:auto';const table=document.createElement('table');table.className='frontGroupTable';const head=table.createTHead().insertRow();
 for(const label of ['성능 순위','Hamming 군','대표와 거리',...p.performance_order.map(id=>run.metadata.metrics.find(m=>m.id===id)?.name||id)]){const th=document.createElement('th');th.textContent=label;head.append(th);}
 for(const r of p.rows){const tr=table.createTBody().insertRow();const b=document.createElement('button');b.textContent=`${r.hamming.performance_rank}위 · 행 ${r.id}`;b.onclick=()=>choose(r.id);tr.insertCell().append(b);tr.insertCell().textContent=`${r.hamming.group_id}군${r.id===r.hamming.representative_id?' 대표':''}`;tr.insertCell().textContent=r.hamming.distance_to_representative;for(const id of p.performance_order)tr.insertCell().textContent=placementMetricText(id,r.named_metrics[id]);}
 frame.append(table);host.append(frame);
}
async function loadPlacementPage(offset=0){
 if(placementLive()){placementPending=false;placementRefresh();return;}
 if(!configured()||placementScope!=='observed')return;
 if((representativeSelection(placementSelection)||frontCollection())&&!placementPerformanceMetrics().some(m=>m.id===sort))sort=placementPerformanceMetrics()[0]?.id||'cost';
 const context=[placementKey(),placementSelection,sort,filter,placementArea,frontRadius,placementLayoutScope].join('|');if(context!==frontQuery){frontGroup=0;frontQuery=context;placementComparisons.clear();compared.clear();}
 const key=placementKey(),cid=run.experiment_contract_id,id=run.run_id,hash=run.config_sha256,gen=run.generation,epoch=++placementEpoch;
 placementPending=true;placementError='';placementPage=null;selected=null;cluster='all';placementRefresh();
 try{
  if(!run.registry.sensor_order.includes(placementLayoutScope))placementLayoutScope='all';
  const q=new URLSearchParams({generation:String(gen),offset:String(offset),limit:'100',sort,targets:String(filter==='targets'),selection:placementSelection,area:placementArea,layout_scope:placementLayoutScope,...(frontCollection()?{arrange:'performance',hamming_radius:String(frontRadius),hamming_group:String(frontGroup),representatives_only:String(frontRepresentatives)}:{})});
  const p=await api(cid,'engine/runs/'+id+'/placements?'+q);
  if(epoch!==placementEpoch||key!==placementKey()||placementScope!=='observed')return;
  if(p.run_id!==id||p.experiment_contract_id!==cid||p.config_sha256!==hash||p.generation!==gen)throw Error('배치 목록의 실행·조건 결속 불일치');
  for(const r of p.rows)if(r.run_id!==id||r.experiment_contract_id!==cid||r.config_sha256!==hash||r.evaluator_sha256!==run.evaluator_sha256||r.F.length!==run.registry.objective_order.length||r.X.length!==run.problem.sites.length||r.X.some(x=>x.length!==run.registry.sensor_order.length))throw Error('배치 원시 행 결속 불일치');
  placementPage={...p,key};selected=p.rows[0]?.id??null;
 }catch(e){if(epoch===placementEpoch&&key===placementKey())placementError=e.message;}
 finally{if(epoch===placementEpoch&&key===placementKey()){placementPending=false;placementRefresh();}}
}
async function changePlacementScope(value){
 if(['history','archive'].includes(value)){placementSelection=value;value='observed';filter='all';placementArea='all';frontGroup=0;}
 else if(value==='observed'&&['history','archive'].includes(placementSelection))placementSelection='primary100';
 if(!configured())return;++placementEpoch;placementScope=value;placementPage=null;placementError='';placementPending=false;cluster='all';selected=null;
 localStorage.setItem('solsol.resultScope.'+run.run_id,['history','archive'].includes(placementSelection)&&value==='observed'?placementSelection:value);
 if(value==='observed')await loadPlacementPage(0);else placementRefresh();
}
async function chooseResultCollection(kind){
 if(kind==='checks'){openQualityCenter('improvements');return;}
 if(!configured())return;
 placementScope='observed';placementSelection=kind==='history'?'history':kind==='observed'?'primary100':'archive';
 filter=kind==='qualified'&&savedAreaGoals()?'targets':'all';placementArea='all';frontGroup=0;frontRepresentatives=false;cluster='all';
 placementComparisons.clear();compared.clear();placementPage=null;selected=null;
 localStorage.setItem('solsol.collection.v2.'+run.run_id,kind);
 ++placementEpoch;placementPending=true;placementError='';placementRefresh();
 try{await fetchRun(run.run_id);}catch(e){placementPending=false;placementError=e.message;placementRefresh();}
}
function qualifiedCollectionMeaning(count){
 if(count===0)return {title:'저장 목표를 통과한 배치가 0개입니다',text:'이번 실행에서 저장 목표를 모두 만족하는 비지배 배치를 찾지 못했습니다. 목표 달성이 불가능하다는 증명은 아닙니다. 아래 ‘최종 해 전체’를 눌러 미달한 목표와 성능을 비교하세요.'};
 if(!Number.isFinite(count))return {title:'목표 통과 배치 수를 확인 중입니다',text:'저장된 목표와 해집합을 확인한 뒤 통과한 배치 수를 표시합니다. 아직 목표 달성 여부를 판정하지 않았습니다.'};
 return {title:`목표를 만족한 최종 대안 ${count.toLocaleString()}개입니다`,text:'저장된 목표를 모두 통과하고, 관측한 다른 배치에 모든 목적에서 밀리지 않는 해만 봅니다. 이 안에서 지도와 성능을 비교해 선택하세요.'};
}
function emptyFeasibleCollectionMeaning(){
 if(!configured()||placementLive()||placementPending||placementError||placementPage?.key!==placementKey())return null;
 const c=placementPage?.collection_counts;
 if(!c||c.generation!==run.generation||c.archive?.all!==0||c.observed?.all!==0)return null;
 const e=run.evaluation_summary;
 const counts=e&&[e.evaluated,e.feasible,e.infeasible].every(Number.isFinite)?`원시 평가 ${e.evaluated.toLocaleString()}회 중 모델 제약 통과 ${e.feasible.toLocaleString()}회, 미달 ${e.infeasible.toLocaleString()}회입니다. `:'';
 return {title:'조건을 통과한 관측 배치가 없습니다',text:counts+'현재 세대까지 설치 조건과 모델 제약을 모두 통과한 배치를 찾지 못했습니다. 목표 필터를 해제해도 해가 생기지 않습니다. 아래 근거에서 미달 이유를 확인하세요. 불가능하다는 증명은 아닙니다.'};
}
function appendEmptyCollectionEvidence(host){
 const b=document.createElement('button');
 if(run.evaluation_summary?.infeasible_examples?.length&&typeof openInfeasibleCandidates==='function'){b.textContent='제약 미달 후보·이유 보기';b.onclick=openInfeasibleCandidates;}
 else{b.textContent='이 실행의 품질 판단·검산 근거';b.onclick=()=>openQualityCenter();}
 host.append(b);
}
function selectedAreaGoalMeaning(checks,goals){
 if(!goals||!Object.keys(goals).length)return '영역 커버율 목표를 설정하지 않은 실행입니다. 성능과 비용의 절충을 비교합니다.';
 if(checks.some(c=>c.gap!==null&&c.gap<0))return '저장 영역 목표에 미달한 지표가 있습니다. 아래 부족분을 확인하세요.';
 if(checks.length!==Object.keys(goals).length||checks.some(c=>c.gap===null))return '영역 성능이나 목표의 기록이 부족해 영역 목표 충족 여부를 판정할 수 없습니다.';
 return '저장 영역 목표를 모두 만족합니다. 모델 제약 판정은 별도로 확인하세요.';
}
function selectedModelConstraintMeaning(row,tolerance,order){
 if(!Array.isArray(row.G)||!row.G.every(Number.isFinite)||!Number.isFinite(tolerance)||!Array.isArray(order)||row.G.length!==order.length)return '모델 제약 수치·허용오차·순서 기록이 부족해 충족 여부를 판정할 수 없습니다.';
 const failed=row.G.filter(g=>g>tolerance).length;
 return failed?`모델 제약 ${row.G.length}개 중 ${failed}개를 충족하지 못했습니다. 영역 목표 통과와 별개로 이 배치는 제약 미달입니다.`:`모델 제약 ${row.G.length}개를 모두 충족합니다. 저장된 제약 허용오차를 적용한 판정입니다.`;
}
function renderCollectionChoices(group,prefix){
 const current=placementPage?.collection_counts,isFinal=current?.generation===current?.last_generation&&!!current,counts=isFinal?current:null,nav=document.createElement('div');nav.className='collectionChoices';nav.setAttribute('aria-label','보고 싶은 해집합');group.append(nav);
 const value=placementSelection==='archive'?(filter==='targets'?'qualified':'final'):placementSelection==='history'?'history':'observed';
 const choices=[...(savedAreaGoals()?[['qualified','목표 통과 최종 해',counts?.archive.qualified]]:[]),['final','최종 해 전체',counts?.archive.all],['history','세대별 비지배 이력',counts?.history.all],['observed','다른 관측 배치 비교',counts?.observed.all]];
 for(const [id,label,n] of choices){const b=document.createElement('button');b.id=prefix+'collection_'+id;b.textContent=label+(n==null?'':` · ${n.toLocaleString()}개`);b.setAttribute('aria-pressed',isFinal&&!placementLive()&&value===id?'true':'false');b.onclick=safe(()=>chooseResultCollection(id));nav.append(b);}
 if(current&&!isFinal)noteText(group,`지금 ${current.generation}세대 시점의 결과입니다. 위 버튼은 계산 완료 시점의 집합을 엽니다.`);
 const check=document.createElement('button');check.id=prefix+'collection_checks';check.textContent='검산 개선 배치 · 별도 결과';check.onclick=()=>chooseResultCollection('checks');nav.append(check);
 const meaning=document.createElement('section');meaning.className='collectionMeaning';meaning.id=prefix+'collectionMeaning';group.prepend(meaning);
 const qualified=qualifiedCollectionMeaning(current?.archive?.qualified);
 const title=document.createElement('h3');title.textContent=placementLive()?'지금 보는 것은 탐색 중 배치입니다':value==='qualified'?qualified.title:value==='final'?'성능과 비용의 최종 절충 대안입니다':value==='history'?'좋은 배치가 발견된 과정을 봅니다':'다른 위치·성능의 대안을 비교합니다';meaning.append(title);
 noteText(meaning,placementLive()?'세대마다 시도한 배치입니다. 아직 목표나 제약을 만족하지 못한 배치도 포함될 수 있습니다.':value==='qualified'?qualified.text:value==='final'?'어떤 목적을 더 높이면 다른 목적이나 비용에서 손해가 생길 수 있는 비지배 배치입니다. 정량 목표 미달도 포함하므로 목표 판정을 함께 보세요.':value==='history'?'각 세대에서 비지배였던 서로 다른 배치를 모았습니다. 지금은 더 좋은 배치가 발견되어 지배된 과거 해도 남아 있습니다. 최종 선택은 최종 해집합에서 확인하세요.':'탐색 중 계산한 제약 통과 배치에서 대안을 봅니다. 이미 더 좋은 해에 지배된 배치도 포함하므로 최종 추천 순위와는 다릅니다.');
 if(current&&!isFinal&&!placementLive()){title.textContent=`${current.generation}세대까지의 ${placementSelection==='archive'?'비지배 배치':placementSelection==='history'?'비지배 이력':'관측 배치'}입니다`;meaning.querySelector('p').textContent='과거 세대 시점의 결과입니다. 이후 세대에서 더 좋은 배치로 대체되었을 수 있습니다. 최종 결과는 아래 다른 해집합 선택에서 엽니다.';}
 else if(value==='final'&&!placementLive()){title.textContent='사용한 목적을 비교한 최종 대안입니다';meaning.querySelector('p').textContent='관측한 배치끼리 목적값을 비교해 남은 비지배 해입니다. 성능의 절충과 목표 달성 여부를 함께 보세요. 목표를 통과하지 못한 해도 포함합니다.';}
 const fixedCost=run.solver?.objective_projection?.excluded?.find(x=>x.objective_id==='cost');if(fixedCost)noteText(meaning,`이 실행의 비용은 ${fixedCost.cost}로 고정되어 배치의 우열을 가르지 않습니다. 나머지 성능 목적으로 위치를 비교합니다.`);
 if(current&&!placementPending&&!placementError){const base=placementSelection==='history'?current.history:placementSelection==='archive'?current.archive:current.observed;noteText(meaning,`기준 집합 ${base.all.toLocaleString()}개${savedAreaGoals()?` 중 저장 목표 통과 ${base.qualified.toLocaleString()}개`:''} → 현재 표시 조건 ${placementPage.total.toLocaleString()}개. 같은 설치 배치는 한 번만 셉니다.`);}
 const empty=emptyFeasibleCollectionMeaning();if(empty){title.textContent=empty.title;meaning.querySelector('p').textContent=empty.text;appendEmptyCollectionEvidence(meaning);}
 const other=document.createElement('details'),otherTitle=document.createElement('summary');otherTitle.textContent='다른 해집합 선택 · 최종 / 이력 / 관측 / 검산';other.append(otherTitle,nav);group.append(other);
 renderSelectedMeaning(meaning,currentRow(),false);
}
function renderSelectedMeaning(host,row,full=false){
 if(!row||placementPending||placementError)return;
 const section=document.createElement('section');section.className='selectedMeaning';section.dataset.rowId=String(row.id);host.append(section);
 const h=document.createElement('h4');h.textContent=`선택 배치 ${row.id} · ${row.sensor_counts.join(' / ')}대 · 비용 ${row.cost}`;section.append(h);
 const goals=savedAreaGoals(),coverage=run.metadata.coverage_metrics||[],checks=coverage.filter(m=>goals?.[m.id]!=null).map(m=>{const v=row.coverage_metrics?.[m.id],t=goals[m.id];return {m,v,t,gap:Number.isFinite(v)&&Number.isFinite(t)?v-t:null};});
 noteText(section,selectedAreaGoalMeaning(checks,goals));
 noteText(section,selectedModelConstraintMeaning(row,run.archive_policy?.tolerance,run.registry?.constraint_order));
 if(checks.length)evidenceTable(section,['영역 성능','현재 / 목표','판정'],checks.map(({m,v,t,gap})=>[m.name,Number.isFinite(v)?`${v.toFixed(2)} / ${t} %`:'미기록',gap==null?'판정 불가':`${Math.abs(gap).toFixed(2)} %p ${gap>=0?'여유':'부족'}`]));
 const priority=run.metadata.metrics.find(m=>m.id===sort);noteText(section,row.hamming?`현재 ${priority?.name||'선택 성능'} 우선 순서에서 ${row.hamming.performance_rank}위입니다. 모든 목적에서 가장 좋다는 뜻은 아닙니다.`:row.observed_is_nondominated===false?'이 배치보다 모든 목적이 같거나 더 좋은 관측 배치가 있습니다. 위치 차이를 비교하기 위한 대안입니다.':'저장된 목적값으로 다른 배치와 비교합니다. 하나의 성능만으로 전체 우열을 판단하지 않습니다.');
 if(full){noteText(section,row.installation_audit?.hard_pass?'저장된 수량·설치 허용 조건을 통과했습니다.':'설치·수량 검사 상태는 아래 원시 근거에서 확인하세요.');if(row.hamming)noteText(section,`대표 배치 ${row.hamming.representative_id}와 설치 선택 ${row.hamming.distance_to_representative}비트가 다릅니다. 한 센서를 다른 후보로 옮기면 보통 2비트 차이입니다. 거리가 크다고 성능이 더 좋다는 뜻은 아닙니다.`);noteText(section,`출처: 저장 실행 ${run.run_id.slice(0,8)} · 원시 행 ${row.id} · ${run.generation}세대 조회. 지도·성능표는 이 행을 함께 사용합니다.`);}
}
function renderCollectionStatus(){
 let node=$('collectionState');if(!node){node=document.createElement('div');node.id='collectionState';node.setAttribute('role','status');$('solutionBar').after(node);}
 node.hidden=mode!=='result'||!configured();if(node.hidden)return;node.replaceChildren();
 if(placementLive()){const n=observedResultRows().length;node.dataset.state=n?'ready':'loading';node.textContent=n?`${run.generation}세대 탐색 배치 ${n}개 · 새 세대가 준비되면 자동 갱신합니다. 최종 해는 계산 종료 후 표시됩니다.`:'첫 세대의 평가 결과를 기다리는 중입니다. 계산은 계속 진행됩니다.';$('selectionPosition').textContent=n?`${Math.max(1,visibleRows().findIndex(r=>r.id===selected)+1)} / ${n}개`:'첫 세대 준비';return;}
 if(placementScope!=='observed'){node.textContent=placementLive()?`${run.generation}세대 탐색 과정 · 최종 해집합과 별도`:'계산 결과';return;}
 const c=placementPage?.collection_counts,past=c&&c.generation<c.last_generation;
 const label=placementSelection==='archive'?(past?`${c.generation}세대까지 ${filter==='targets'?'목표 통과 ':''}비지배 해`:(filter==='targets'?'목표 통과 최종 비지배 해':'최종 비지배 해 전체')):placementSelection==='history'?'세대별 비지배 이력':'관측 배치 비교';
 if(placementPending){node.dataset.state='loading';node.textContent=label+'를 읽는 중입니다. 조회가 끝나기 전에는 0개로 판정하지 않습니다.';$('selectionPosition').textContent='조회 중';return;}
 if(placementError||!placementPage){node.dataset.state='error';node.textContent=placementError?'목록 조회 실패: '+placementError:'목록을 아직 받지 못했습니다.';const retry=document.createElement('button');retry.textContent='목록 다시 읽기';retry.onclick=safe(()=>loadPlacementPage(0));node.append(retry);$('selectionPosition').textContent='조회 필요';return;}
 node.dataset.state=placementPage.total?'ready':'empty';node.textContent=`${label} · ${filter==='targets'?'저장 목표 통과만':'목표 미달 포함'} · ${placementPage.total.toLocaleString()}개 중 ${placementPage.rows.length}개 표시 · ${run.generation}세대 기준`;
 if(!placementPage.total){const empty=emptyFeasibleCollectionMeaning();if(empty){node.textContent=empty.title+` · ${run.generation}세대 기준`;appendEmptyCollectionEvidence(node);}else{const reset=document.createElement('button');reset.textContent='표시 조건 초기화 · 최종 해 전체 보기';reset.onclick=safe(()=>chooseResultCollection('final'));node.append(reset);}}
}
let largePlacementOptionsOpen=false;
function renderPlacementControls(host,prefix=''){
 if(prefix==='large_'&&workbench?.task==='compare'&&typeof renderLargeComparisonTools==='function'){renderLargeComparisonTools(host,prefix);return;}
 const group=document.createElement('div');group.className='placementControls';
 if(prefix==='large_'){
  const fold=document.createElement('details');fold.id=prefix+'placementControls';fold.className='largePlacementOptions';fold.open=largePlacementOptionsOpen;
  const title=document.createElement('summary');title.textContent='해집합·성능 순서·비교 근거 변경';fold.append(title);
  const back=document.createElement('button');back.type='button';back.textContent='설정 접고 지도 보기';back.onclick=()=>{largePlacementOptionsOpen=false;fold.open=false;title.focus();};group.append(back);
  fold.append(group);fold.addEventListener('toggle',()=>{if(fold.isConnected)largePlacementOptionsOpen=fold.open;});host.append(fold);
 }else{group.id=prefix+'placementControls';host.prepend(group);}
 renderCollectionChoices(group,prefix);
 const advanced=document.createElement('details'),advancedTitle=document.createElement('summary');advancedTitle.textContent='세대 재생·고급 집합 선택';advanced.append(advancedTitle);group.append(advanced);selectControl(advanced,'결과 범위',[['generation','현재 세대 배치 · 목표 미달 포함'],['history','세대별 비지배 이력 · 전체 누적'],['observed','관측 배치 · 추출 / 전체 조회'],['archive','현재 누적 비지배 해집합']],placementLive()?'generation':frontCollection()?placementSelection:placementScope,v=>safe(()=>changePlacementScope(v))(),prefix+'placementScope');
 noteText(advanced,'저장 실행 '+run.run_id.slice(0,8)+' · '+goalSummary(savedAreaGoals(),run.metadata));
 if(placementLive()){if(!terminal.has(run.state))group.querySelector('select').disabled=true;noteText(group,`${run.generation}세대 모집단 ${observedResultRows().length}개 · 탐색 과정 · 목표·모델 제약 미달 포함. 세대 슬라이더로 배치 변화를 확인합니다. 누적 100개 추출은 계산 종료 후 제공합니다.`);return;}
 if(placementScope==='archive'){
  const historyButton=document.createElement('button');historyButton.id=prefix+'showHistoricalFronts';historyButton.textContent=`세대별 비지배 이력 ${run.historical_nondominated_count??''}개 모두 보기`;historyButton.onclick=safe(()=>changePlacementScope('history'));group.append(historyButton);
  const total=run.evaluation_summary?.unique_feasible??0;
  noteText(group,`비지배 ${archiveRowCount()}개 · 관측된 서로 다른 제약 통과 배치 ${total.toLocaleString()}개. 낮은 성능의 지배된 배치는 아래에서 비교할 수 있습니다.`);
  const b=document.createElement('button');b.id=prefix+'showObservedAlternatives';b.textContent='성능 우선 배치 100개 비교';b.onclick=safe(async()=>{placementSelection='primary100';placementArea='all';filter='all';await changePlacementScope('observed');});group.append(b);
  const projection=run.solver?.objective_projection,cost=projection?.excluded?.find(v=>v.objective_id==='cost');
  if(cost)noteText(group,`이 실행은 전량 사용으로 비용 ${cost.cost} 고정입니다. 낮은 성능 배치도 비용은 같습니다.`);
 }
 if(placementScope!=='observed')return;
 const p=placementPage;
 selectControl(group,'설치 배치 구분',layoutScopeOptions(),placementLayoutScope,v=>safe(async()=>{placementLayoutScope=v;frontGroup=0;frontRepresentatives=false;placementComparisons.clear();compared.clear();await loadPlacementPage(0);})(),prefix+'layoutScope');
 if(p?.layout_scope&&p.layout_scope!=='all')noteText(group,`전체 센서 배치 ${p.layout_scope_source_count}개 → ${layoutSensorName(p.layout_scope)} 독립 배치 ${p.sensor_layouts.length}개. 같은 ${layoutSensorName(p.layout_scope)} 위치는 ${p.performance_order.length?'선택 성능, 나머지 성능, 원시 행 번호순':'현재 정렬값, 원시 행 번호순'}으로 대표 배치를 고릅니다. Hamming은 ${layoutSensorName(p.layout_scope)} 설치 위치만 비교합니다. 모든 센서의 성능과 비용은 선택된 원래 전체 배치의 값입니다.`);
 if(savedAreaGoals())selectControl(group,'목표 표시',[['all','저장 목표 통과·미달 모두'],['targets','저장 목표 통과 배치만']],filter==='targets'?'targets':'all',v=>safe(async()=>{filter=v;cluster='all';await loadPlacementPage(0);})(),prefix+'placementGoalFilter');
 if(!frontCollection())selectControl(group,'배치 추출',[['primary100','선택 성능별 · 서로 다른 배치 100개'],['front100','비지배 성능 보존 우선 · 최대 100개'],['performance100','전체 성능 순서 · 상위 100개'],['diverse100','비용 우선 · Hamming 다양성 100개'],['all','전체 배치 · 페이지별 조회']],placementSelection,v=>safe(async()=>{placementSelection=v;await loadPlacementPage(0);})(),prefix+'placementSelection');
 if(representativeSelection(placementSelection)||frontCollection()){
  const ms=placementPerformanceMetrics();selectControl(group,'성능 우선순위',ms.map(m=>[m.id,m.name+' 우선']),sort,v=>safe(async()=>{sort=v;await loadPlacementPage(0);})(),prefix+'performancePriority');
  noteText(group,placementSelection==='front100'?'관측 비지배 성능과 목적별 최상을 먼저 보존합니다. 표의 정렬 우선순위는 모든 목적에서 가장 좋다는 뜻이 아닙니다.':placementSelection==='primary100'?'선택 성능값이 다른 배치를 먼저 한 개씩 고릅니다. 같은 값이면 위치 차이로 구분합니다.':'우선 성능이 같으면 나머지 성능을 비교하고, 모든 성능이 같을 때 위치 차이로 순서를 정합니다.');
 }
 const areaOptions=[['all','영역 구분 없이 전체'],['coverage_any','모델 커버율: 하나 이상 지표가 0보다 큼'],['coverage_all','모델 커버율: 모든 지표가 0보다 큼'],['coverage_none','모델 커버율: 모든 지표가 0'],['range_any','하나 이상 센서 범위가 영역에 닿음'],['range_all','모든 센서 범위가 영역에 닿음'],['range_none','모든 센서 범위가 영역 밖'],['site_any','하나 이상 설치 위치가 영역 안'],['site_all','모든 설치 위치가 영역 안'],['site_none','모든 설치 위치가 영역 밖'],['empty','설치된 센서 없음']];
 const areaDetail=document.createElement('details'),areaTitle=document.createElement('summary');areaTitle.textContent='영역·위치로 더 좁혀 보기'+(placementArea==='all'?' · 제한 없음':' · 필터 적용 중');areaDetail.append(areaTitle);group.append(areaDetail);
 const a=selectControl(areaDetail,'평가영역 관계',areaOptions,placementArea,v=>safe(async()=>{placementArea=v;await loadPlacementPage(0);})(),prefix+'placementArea');
 for(const o of a.options)if(p&&((o.value.startsWith('coverage_')&&!p.area_capabilities.coverage)||(o.value.startsWith('range_')&&!p.area_capabilities.range)||(o.value.startsWith('site_')&&!p.area_capabilities.site)))o.disabled=true;
 noteText(areaDetail,'영역 성능은 평가영역을 얼마나 관측하는지, 설치 위치는 센서 중심이 어디 있는지를 뜻합니다. 영역 밖 센서도 영역을 관측할 수 있습니다. 범위가 닿는 것만으로 목표 성능을 만족하지는 않습니다. 이 필터는 목록만 좁히며 계산 조건을 바꾸지 않습니다.');
 if(placementPending){noteText(group,'계산된 배치 목록 불러오는 중…');return;}
 if(placementError){noteText(group,'목록 조회 실패 · '+placementError);const retry=document.createElement('button');retry.textContent='목록 다시 조회';retry.onclick=safe(()=>loadPlacementPage(0));group.append(retry);return;}
 if(!p)return;
 renderSubsetFidelity(group,p);
 if(frontCollection())renderFrontGroups(group,p,prefix);
 if(p.selection==='history')noteText(group,`역대 비지배 이력 ${p.total}개를 페이지별로 모두 제공합니다. 현재 지배된 이력도 포함하며, 현재 비지배 해로 재분류하지 않습니다. 선택 배치의 최초·마지막 비지배 세대를 지도에 표시합니다.`);
 if(p.targets&&p.total===0){noteText(group,'저장 목표를 통과한 배치가 0개입니다. 미달 배치를 통과 해로 표시하지 않습니다. 전체 관측 배치에서 성능과 미달 이유를 확인할 수 있습니다.');const b=document.createElement('button');b.id=prefix+'showGoalFailures';b.textContent='목표 미달 포함 · 전체 성능 보기';b.onclick=safe(async()=>{filter='all';await loadPlacementPage(0);});group.append(b);}
 if(!p.area_capabilities.site)noteText(group,'저장 모델에 평가영역 경계가 없어 안/밖 판정을 제공하지 않습니다.');
 if(representativeSelection(p.selection)){
  noteText(group,`제약·표시필터 통과 ${p.eligible.toLocaleString()}개 → 성능 비교 대표 ${p.total}개 · 지배된 배치 포함`);
  noteText(group,'비교 순서: '+p.performance_order.map(id=>run.metadata.metrics.find(m=>m.id===id)?.name||id).join(' → ')+(p.selection==='front100'?' · 비지배 성능을 보존해 추린 뒤 성능순으로 표시합니다. 같은 성능은 원시 배치 번호순입니다.':p.selection==='primary100'?' · 첫 지표 값별 Hamming 대표 (나머지 지표는 비교용)':' → Hamming 동률 비교'));
  const frame=document.createElement('div');frame.style.cssText='max-height:220px;overflow:auto;margin-top:8px';
  const table=document.createElement('table');table.className='performanceRankTable';table.style.cssText='width:100%;table-layout:fixed;font-size:12px';
  const head=table.createTHead().insertRow();for(const label of ['순위',...p.performance_order.map(id=>run.metadata.metrics.find(m=>m.id===id)?.name||id),'Hamming']){const th=document.createElement('th');th.textContent=label;th.style.cssText='overflow-wrap:anywhere;position:sticky;top:0;background:#eaf3f7';head.append(th);}
  const body=table.createTBody();for(const r of p.rows){const tr=body.insertRow();tr.dataset.performanceRow=String(r.id);const b=document.createElement('button');b.textContent=String(r.representative_rank)+(r.observed_is_nondominated?' · P':'');b.title='행 '+r.id+' · '+(r.observed_is_nondominated?'비지배':'지배된 관측 배치');b.onclick=()=>choose(r.id);tr.insertCell().append(b);for(const id of p.performance_order){const cell=tr.insertCell();cell.textContent=placementMetricText(id,r.named_metrics[id]);cell.title=String(r.named_metrics[id])+' '+(run.metadata.metrics.find(m=>m.id===id)?.unit||'');}tr.insertCell().textContent=r.hamming_to_selected_min??'—';}
  frame.append(table);group.append(frame);noteText(group,'순위 버튼으로 지도 선택 · P는 비지배 해 · Hamming은 앞선 배치와의 최소 설치 비트 차이. 표는 모델 목적값이며 커버율(%)은 지도 위에 표시합니다.');
  return;
 }
 if(p.selection==='diverse100'){
  noteText(group,`필터 통과 ${p.eligible.toLocaleString()}개 → 대표 ${p.total}개`);
  const detail=document.createElement('details'),title=document.createElement('summary');title.textContent='추출·영역 판정 기준';detail.append(title);
  noteText(detail,'비용 오름차순, 같은 비용은 앞서 고른 배치들과의 최소 Hamming 거리 최대화. 최초는 해당 비용의 비지배 행 우선, 동률은 원시 행 번호순입니다. 낮은 비용에서 100개가 채워지면 더 비싼 배치는 포함되지 않습니다. 영역과 명목 원의 교차는 실제 관측·품질 판정과 다릅니다.');group.append(detail);return;
 }
 const pages=Math.max(1,Math.ceil(p.total/p.limit)),current=Math.floor(p.offset/p.limit);
 const line=document.createElement('div');line.className='placementPageNav';group.append(line);
 for(const [name,text,next,disabled] of [['first','처음',0,current===0],['previous','이전',p.offset-p.limit,current===0],['next','다음',p.offset+p.limit,current===pages-1],['last','마지막',(pages-1)*p.limit,current===pages-1]]){const b=document.createElement('button');b.id=prefix+'placements_'+name;b.textContent=text;b.disabled=disabled;b.onclick=safe(()=>loadPlacementPage(next));line.append(b);}
 const picker=selectControl(group,'페이지',Array.from({length:pages},(_,i)=>[String(i),`${i+1} / ${pages}`]),String(current),v=>safe(()=>loadPlacementPage(+v*p.limit))(),prefix+'placementPage');picker.disabled=!p.total;
 noteText(group,`${p.total? p.offset+1:0}–${p.offset+p.rows.length} / ${p.total.toLocaleString()}개 · 전체 목록 정렬·목표 필터 후 페이지 표시`);
}
const placementOldScope=renderResultScope;
renderResultScope=function(parent,rows){
 if(placementLive()){const box=document.createElement('div');box.id='resultScope';parent.append(box);noteText(box,`${run.generation}세대 탐색 모집단 · 원시 행 ${currentRow()?.id??'없음'} · 비지배 해집합과 별도. 목표·모델 제약 미달 개체도 탐색 과정을 위해 표시합니다.`);return;}
 if(frontCollection()){const box=document.createElement('div');box.id='resultScope';parent.append(box);noteText(box,`${placementSelection==='history'?'세대별 비지배 이력':'현재 누적 비지배'} · 전체 성능 순서 · ${placementPage?.grouping?.groups.length??0} Hamming군 · 현재 조건 ${placementPage?.total??0}배치`);noteText(box,goalSummary(savedAreaGoals(),run.metadata));noteText(box,placementSelection==='history'?'과거 비지배 배치도 포함합니다. 현재 지배된 이력을 현재 비지배 해로 바꾸지 않습니다.':'전 평가의 현재 비지배 배치만 대상으로 합니다. 다른 집합의 행을 추가하지 않습니다.');return;}
 if(placementScope==='observed'&&placementSelection==='history'){const box=document.createElement('div');box.id='resultScope';parent.append(box);noteText(box,`세대별 비지배 이력 · 표시 ${rows.length} / 필터 통과 ${placementPage?.total??0}개 · 전체 이력 ${run.historical_nondominated_count??0}개 · 현재 비지배 ${archiveRowCount()}개`);noteText(box,goalSummary(savedAreaGoals(),run.metadata));noteText(box,'과거 세대의 비지배 배치를 보존한 이력입니다. 현재 비지배 집합에 다시 추가하거나 목적값을 바꾸지 않습니다.');return;}
 if(placementScope!=='observed')return placementOldScope(parent,rows);
 const box=document.createElement('div');box.id='resultScope';box.className='resultScope';box.setAttribute('role','status');parent.append(box);
 const b=document.createElement('b');b.textContent=(representativeSelection(placementSelection)?'성능 우선·Hamming 배치':placementSelection==='diverse100'?'비용·Hamming 대표 배치':'계산된 배치 전체')+' · '+run.run_id.slice(0,8)+' · '+run.generation+'세대까지';box.append(b);
 noteText(box,goalSummary(savedAreaGoals(),run.metadata)+' · '+resourceSummary(run.config));
 const p=placementPage,e=run.evaluation_summary;
 noteText(box,`서로 다른 제약 통과 배치 ${(p?.unique_feasible??e?.unique_feasible??0).toLocaleString()}개 · 누적 비지배 ${archiveRowCount()}개 · 원시 평가 ${e?.evaluated??run.nfe}회`);
 noteText(box,'탐색 중 계산한 배치입니다. 지배된 배치도 포함하며, 가능한 모든 조합을 전수 탐색한 결과는 아닙니다.');
 if(placementSelection==='history')noteText(box,'세대별 비지배 이력 · 현재 지배된 배치도 포함');
 if(currentRow())noteText(box,'선택 행 '+currentRow().id+' · '+(currentRow().observed_is_nondominated?'누적 비지배 배치':'다른 관측 배치에 지배됨')+' · 센서 '+currentRow().sensor_counts.join(' / ')+'대');
 const r=currentRow(),ar=r?.area_relation;
 if(ar)noteText(box,`설치 ${ar.installed}대 · 영역 안 설치 ${ar.site_inside??'판정 불가'}대 · 영역과 범위 교차 ${ar.range_intersects??'판정 불가'}대${r.representative_rank?' · 추출 순번 '+r.representative_rank+' · 앞선 배치들과 최소 Hamming '+(r.hamming_to_selected_min??'시작 배치'):''}`);
 if(archiveRowCount()===1)noteText(box,'비지배 1개는 이 실행에서 관측된 판정입니다. 미탐색 배치까지 포함한 전역 해집합의 개수가 아닙니다.');
 if(cluster!=='all'||filter!=='all'||placementArea!=='all'){const reset=document.createElement('button');reset.id='showAllResults';reset.textContent='영역·목표·군집 필터 해제';reset.onclick=safe(async()=>{filter='all';cluster='all';placementArea='all';await loadPlacementPage(0);});box.append(reset);}
 if(e?.infeasible_examples?.length){const inspect=document.createElement('button');inspect.id='inspectInfeasible';inspect.textContent='제약 미달 후보·이유 보기';inspect.onclick=openInfeasibleCandidates;box.append(inspect);}
};
const placementOldDock=renderDock;
renderDock=function(){
 placementOldDock();if(!configured())return;
 renderPlacementControls($('dockBody'));
 if(placementLive()){const f=$('frontFilter');if(f){f.disabled=true;f.options[f.selectedIndex].textContent='현재 세대 모집단 · 목표 미달 포함';}$('resultCount').textContent=`현재 세대 ${observedResultRows().length}개 · 누적 비지배 ${archiveRowCount()}개`;}
 if(frontCollection()){$('structureFilter')?.parentElement.remove();}
 if(placementScope==='observed'){$('frontFilter')?.parentElement.remove();if(frontCollection()||representativeSelection(placementSelection))$('rowSort')?.parentElement.remove();}
 if(placementScope==='observed'&&!placementLive()){
  $('resultCount').textContent=`표시 조건 통과 ${placementPage?.total??0}개 · 이번 페이지 ${placementPage?.rows.length??0}개`;
  if(placementSelection==='history')$('resultCount').textContent=`세대별 비지배 이력 ${placementPage?.total??0} · 현재 비지배 ${archiveRowCount()}`;
  if(placementPending)$('resultCount').textContent='해집합 조회 중 · 저장 비지배 '+archiveRowCount()+'개';
  else if(placementError)$('resultCount').textContent='목록 연결 실패 · 저장 비지배 '+archiveRowCount()+'개';
  const h=$('structureFilter');if(h?.parentElement)h.parentElement.firstChild.textContent='Hamming · 현재 페이지 ';
  const f=$('frontFilter');if(f?.options[0])f.options[0].textContent='현재 조회 집합';
  for(const check of $('dockBody').querySelectorAll('tr[data-row] input[type=checkbox]')){const original=check.onchange;check.onchange=()=>{original?.();const id=+check.closest('tr').dataset.row;if(check.checked){const row=resultRows().find(r=>r.id===id);if(row)placementComparisons.set(id,row);}else placementComparisons.delete(id);};}
 }
 for(const [id,kind] of [['frontFilter','filter'],['rowSort','sort']]){const el=$(id);if(el&&placementScope==='observed'){if(kind==='sort')el.disabled=frontCollection()||!['all','history'].includes(placementSelection);el.onchange=safe(async()=>{if(kind==='filter')filter=el.value;else sort=el.value;await loadPlacementPage(0);});}}
};
const placementOldFetch=fetchRun;
fetchRun=async function(id,g=null){
 const hold={cid:draft.sensor,id,sequence:++placementSpatialSequence,epoch:placementSpatialEpoch,deferred:false};placementSpatialHolds.add(hold);
 try{
 const before=placementKey(),previousScope=placementScope,previousId=run?.run_id,previousState=run?.state;
 await placementOldFetch(id,g);
 if(hold.sequence!==placementSpatialSequence||hold.epoch!==placementSpatialEpoch||hold.cid!==draft.sensor||!configured()||run?.run_id!==id)return;
 if(placementLive()&&before===placementKey()&&previousState===run.state)return;
 if(previousId===id&&before!==placementKey()){placementComparisons.clear();compared.clear();}
 if(previousId!==id){placementComparisons.clear();placementArea='all';const choice=localStorage.getItem('solsol.collection.v2.'+id)||(savedAreaGoals()?'qualified':'final');placementScope='observed';placementSelection=choice==='history'?'history':choice==='observed'?'primary100':'archive';filter=choice==='qualified'&&savedAreaGoals()?'targets':'all';frontGroup=0;frontRepresentatives=false;}
 if(placementLive()){placementPending=false;selected=visibleRows()[0]?.id??null;placementRefresh();}
 else if(placementScope==='observed'&&(before!==placementKey()||!placementPage||placementPage.key!==placementKey()))await loadPlacementPage(0);
 else if(previousScope!==placementScope)placementRefresh();
 }finally{
  placementSpatialHolds.delete(hold);
  if(hold.deferred&&hold.sequence===placementSpatialSequence&&hold.epoch===placementSpatialEpoch&&hold.cid===draft.sensor&&run?.run_id===id&&!placementDefersMainSpatial())renderMaps();
 }
};
const placementOldClear=clearRun;
clearRun=function(){++placementSpatialEpoch;placementSpatialHolds.clear();++placementEpoch;placementScope='archive';placementSelection='primary100';placementArea='all';frontGroup=0;frontRadius=2;frontRepresentatives=false;frontQuery='';placementPage=null;placementPending=false;placementError='';placementComparisons.clear();placementOldClear();};
const placementOldExpand=expand;
expand=function(){placementOldExpand();if(configured()&&mode==='result'){renderPlacementControls($('largeTools'),'large_');expandControlsRefresh();}};
$('expandMap').onclick=expand;
const placementOldExpandRefresh=expandControlsRefresh;
expandControlsRefresh=function(){placementOldExpandRefresh();if(!$('mapDialog').open||!configured())return;
 $('large_placementControls')?.remove();renderPlacementControls($('largeTools'),'large_');
 if(frontCollection())$('large_structureFilter')?.parentElement.remove();
 const h=$('large_structureFilter');if(h){option(h,[['all','전체'],...M.cluster(resultRows()).map((g,i)=>[String(i),`${i+1}군 · ${g.length}개`])],cluster);h.parentElement.firstChild.textContent=placementScope==='observed'?'Hamming · 현재 페이지 ':'Hamming ';}
 if(placementScope==='observed'){const f=$('large_frontFilter');if(f?.options[0])f.options[0].textContent='전체 계산 배치 · 현재 페이지';for(const [id,kind] of [['large_frontFilter','filter'],['large_rowSort','sort']]){const el=$(id);if(el){if(kind==='sort')el.disabled=!['all','history'].includes(placementSelection);el.onchange=safe(async()=>{if(kind==='filter')filter=el.value;else sort=el.value;await loadPlacementPage(0);});}}}
};
const placementOldVisible=visibleRows;
visibleRows=function(){if(placementLive()){const m=placementPerformanceMetrics().find(m=>m.id===sort)||placementPerformanceMetrics()[0];return observedResultRows().slice().sort((a,b)=>m?(a.named_metrics[m.id]-b.named_metrics[m.id])*(m.direction==='maximize'?-1:1)||a.id-b.id:a.id-b.id);}const rows=placementOldVisible();return placementScope==='observed'&&(frontCollection()||!['all','history'].includes(placementSelection))?rows.slice().sort((a,b)=>(a.representative_rank??Infinity)-(b.representative_rank??Infinity)):rows;};
const placementOldSelection=syncSelectionBar;
function placementCaption(r){const order=placementPage?.performance_order||[],performance=order.map(id=>{const m=run.metadata.metrics.find(m=>m.id===id);return (m?.name||id)+' '+placementMetricText(id,r.named_metrics[id]);});const coverage=(run.metadata.coverage_metrics||[]).filter(m=>Number.isFinite(r.coverage_metrics?.[m.id])).map(m=>m.name+' '+r.coverage_metrics[m.id].toFixed(2)+'%');return `${r.representative_rank??''}위 · 행 ${r.id} · ${performance.join(' / ')} · 커버: ${coverage.join(' / ')} · Hamming ${r.hamming_to_selected_min??'시작'} · ${r.observed_is_nondominated?'비지배':'관측'}`;}
syncSelectionBar=function(){placementOldSelection();if(placementScope==='observed'&&run&&placementPage){$('selectionPosition').textContent=`${representativeSelection(placementSelection)?'성능 순위':'페이지 내'} ${Math.max(0,visibleRows().findIndex(r=>r.id===selected)+1)} / ${visibleRows().length} · 총 ${placementPage.total.toLocaleString()}개`;if(representativeSelection(placementSelection))for(const o of $('solutionPicker').options){const r=resultRows().find(r=>r.id===+o.value);if(r)o.textContent=placementCaption(r);}}};
const placementOldChoose=choose;
choose=function(id){placementOldChoose(id);if(placementScope==='observed')renderDock();};
const placementOldMaps=renderMaps;
renderMaps=function(){placementOldMaps();let host=$('mapPlacementTools');if(!host){host=document.createElement('div');host.id='mapPlacementTools';$('solutionBar').after(host);}host.replaceChildren();host.hidden=!configured()||mode!=='result';if(!host.hidden){if(typeof renderCompactPlacementTools==='function')renderCompactPlacementTools(host);else renderPlacementControls(host,'map_');}if(placementScope==='observed'&&mode==='result'&&currentRow())$('mapBadge').textContent+=' · '+(currentRow().observed_is_nondominated?'관측 비지배':'지배된 관측 배치');if(mode==='result'&&placementLive())$('mapBadge').textContent=`${run.generation}세대 탐색 배치 · 행 ${currentRow()?.id??'없음'} · ${currentRow()?.qualified===true?'목표 통과':currentRow()?.qualified===false?'목표 미달':'목표 미설정'} · 비지배 판정과 별도`;if(mode==='result'&&currentRow()?.nondominance_history){const h=currentRow().nondominance_history;$('mapBadge').textContent=`행 ${currentRow().id} · 비지배 이력 ${h.first_generation}–${h.last_generation}세대 · ${currentRow().observed_is_nondominated?'현재도 비지배':'현재는 지배됨'}`;}if(mode==='result'&&frontCollection()&&currentRow()?.hamming){const h=currentRow().hamming;$('mapBadge').textContent+=` · 성능 ${h.performance_rank}위 · ${h.group_id}군 · 대표 행 ${h.representative_id}와 Hamming ${h.distance_to_representative}`;}renderSavedConditionContext();renderCollectionStatus();};

function renderSavedConditionContext(){
 const editing=mode==='design'&&workbench?.task==='settings',base=baselinePreview?.cid===draft.sensor?baselinePreview:null;
 $('initialSolution').hidden=!!(editing&&base?.row);
 if(editing&&base?.row){
  const r=base.row,metadata=base.metadata||(run?.experiment_contract_id===base.cid?run.metadata:null),reading=$('initialCard').querySelector('.mapReading');
  $('initialCard').querySelector('.mapCardTitle').firstChild.textContent='고정한 저장 배치 · '+base.label+' · 행 '+r.id+' ';
  const performance=(metadata?.coverage_metrics||[]).map(m=>m.name+' '+(Number.isFinite(r.coverage_metrics?.[m.id])?r.coverage_metrics[m.id].toFixed(2)+'%':'미기록'));
  if(!performance.length)for(const m of metadata?.metrics||[])if(m.id!=='cost'&&Number.isFinite(r.named_metrics?.[m.id]))performance.push(m.name+' '+r.named_metrics[m.id]);
  if(reading){reading.dataset.savedRowId=String(r.id);reading.textContent='저장 배치 성능 · '+performance.join(' · ')+' · 센서 '+r.sensor_counts.join('/')+'대 · '+qualityQualification(r,Object.hasOwn(base,'goals')?base.goals:savedAreaGoals());}
  $('initialMap').dataset.savedRowId=String(r.id);
 }
 let actions=$('savedResultActions');if(!actions){actions=document.createElement('span');actions.id='savedResultActions';$('conditionCompareTools').append(actions);}actions.replaceChildren();actions.hidden=!editing||!configured();if(actions.hidden)return;
 const savedGoals=savedAreaGoals(),hasGoals=!!savedGoals&&Object.keys(savedGoals).length>0;
 for(const [id,label,targets] of [['savedQualifiedResults','저장 목표 통과 · 성능 상위100 보기',true],['savedAllResults','저장 전체 배치 · 성능 상위100 보기',false]]){
  if(targets&&!hasGoals)continue;const button=document.createElement('button');button.id=id;button.textContent=label;button.onclick=safe(async()=>{$('task_map').click();placementSelection='primary100';placementArea='all';filter=targets?'targets':'all';cluster='all';await changePlacementScope('observed');});actions.append(button);
 }
 const note=document.createElement('span');note.className='formNote';note.textContent='왼쪽은 고정해 둔 한 배치, 오른쪽은 미계산 초안입니다. 결과 버튼은 현재 저장 실행 '+run.run_id.slice(0,8)+'의 배치를 엽니다.';actions.append(note);
}

function placementRankLabel(row){
 const id=placementPage?.performance_order?.[0],metric=run?.metadata?.metrics?.find(m=>m.id===id);
 const basis=metric?.name||(id?String(id):'저장 성능 순서');
 return `${basis} 우선 ${row.hamming.performance_rank}위`;
}
function frontCaption(r){const h=r.hamming;return `${placementRankLabel(r)} · ${h.group_id}군${r.id===h.representative_id?' 대표':''} · 행 ${r.id} · 대표와 ${layoutHammingPrefix()}Hamming ${h.distance_to_representative} · `+(placementPage?.performance_order||[]).map(id=>(run.metadata.metrics.find(m=>m.id===id)?.name||id)+' '+placementMetricText(id,r.named_metrics[id])).join(' / ');}
function frontPickerLabels(){if(!frontCollection()||!placementPage?.grouping)return;for(const id of ['solutionPicker','largeSolution'])for(const o of $(id)?.options||[]){if(o.value==='')continue;const r=resultRows().find(r=>r.id===+o.value);if(r?.hamming)o.textContent=frontCaption(r);}}
function syncExpandedNavigation(){
 if(!$('mapDialog').open||!$('largeSolution'))return;
 let nav=$('largeSolutionNavigation');
 if(!nav){const label=$('largeSolution').parentElement;nav=document.createElement('div');nav.id='largeSolutionNavigation';label.before(nav);
  for(const [id,base,text] of [['largePreviousSolution','previousSolution','◀'],['largeNextSolution','nextSolution','▶']]){const b=document.createElement('button');b.id=id;b.textContent=text;b.setAttribute('aria-label',base==='previousSolution'?'이전 배치':'다음 배치');b.onclick=()=>$(base).click();nav.append(b);if(base==='previousSolution')nav.append(label);}
  const position=document.createElement('span');position.id='largeSelectionPosition';nav.append(position);
 }
 const rows=visibleRows();for(const id of ['largePreviousSolution','largeNextSolution'])$(id).disabled=placementPending||!rows.length;
 $('largeSelectionPosition').textContent=rows.length?`${Math.max(0,rows.findIndex(r=>r.id===selected)+1)} / ${rows.length}개 · 현재 페이지`:'표시할 배치 없음';
}
const frontSelection=syncSelectionBar;syncSelectionBar=function(){frontSelection();frontPickerLabels();syncExpandedNavigation();};
const frontExpanded=expandControlsRefresh;expandControlsRefresh=function(){frontExpanded();frontPickerLabels();syncExpandedNavigation();if(frontCollection()&&$('large_rowSort'))$('large_rowSort').disabled=true;};

// The expanded viewport repeats the selected map's saved metrics verbatim.
function renderEmptyResultMap(){
 if(mode!=='result'||!run||currentRow())return;
 const empty=emptyFeasibleCollectionMeaning();
 const title=placementPending?'저장 배치 선택':empty?.title||'표시할 저장 배치 없음',message=placementError?'해집합 조회에 실패했습니다. 해 목록에서 다시 조회하세요.':placementPending?'해집합을 확인한 뒤 선택한 저장 배치를 표시합니다.':empty?.text||(filter==='targets'?'현재 표시 조건에서 저장 목표를 통과한 배치가 없습니다. ‘최종 해 전체 보기’로 목표 미달 배치와 비교할 수 있습니다.':'현재 필터에 맞는 저장 배치가 없습니다. 해집합과 표시 조건을 확인하세요.');
 for(const id of ['mainMap','largeMap']){const host=$(id);host.replaceChildren();const box=document.createElement('div');box.className='empty';const h=document.createElement('b');h.textContent=title;const p=document.createElement('p');p.textContent=message;box.append(h,p);host.append(box);}
 $('mapTitle').textContent=title;$('mapBadge').textContent='저장 실행 '+run.run_id.slice(0,8)+' · 선택 배치 없음';
 const reading=$('mainMap').closest('.mapCard').querySelector('.mapReading');if(reading)reading.textContent='';
 const large=$('largeMapReading');if(large){large.textContent='';large.hidden=true;}
}
const radarViewMaps=renderMaps;
function syncExpandedMapLayout(){
 const dialog=$('mapDialog');if(!dialog.open)return;
 let toggle=$('largeControlsToggle');
 if(!toggle){
  toggle=document.createElement('button');toggle.id='largeControlsToggle';toggle.setAttribute('aria-controls','largeTools');
  dialog.querySelector('.dialogHead').append(toggle);
  dialog.classList.toggle('mapControlsCollapsed',window.matchMedia('(max-width:900px)').matches);
  toggle.onclick=()=>{dialog.classList.toggle('mapControlsCollapsed');syncExpandedMapLayout();};
 }
 const collapsed=dialog.classList.contains('mapControlsCollapsed');
 toggle.textContent=collapsed?'지도 설정 펼치기':'지도 설정 접기';toggle.setAttribute('aria-expanded',String(!collapsed));
}
renderMaps=function(){
 radarViewMaps();
 let reading=$('largeMapReading');
 if(!reading){reading=document.createElement('div');reading.id='largeMapReading';reading.className='expandedMapReading';($('largeComparison')||$('largeMap')).before(reading);}
 const original=$('mainMap').closest('.mapCard').querySelector('.mapReading');
 reading.textContent=original?.textContent||'';reading.hidden=!reading.textContent;
 reading.dataset.rawId=String(currentRow()?.id??'');
 let picker=$('radarLayoutView');
 if(!picker){const label=document.createElement('label');label.id='radarLayoutLabel';label.textContent='배치 구분 ';picker=document.createElement('select');picker.id='radarLayoutView';picker.setAttribute('aria-label','배치 구분');label.append(picker);$('solutionBar').append(label);picker.onchange=safe(async()=>{placementLayoutScope=picker.value;frontGroup=0;frontRepresentatives=false;if(placementScope!=='observed'){placementScope='observed';placementSelection='archive';}await loadPlacementPage(0);});}
 option(picker,layoutScopeOptions(),placementLayoutScope);
 $('radarLayoutLabel').hidden=!configured()||!run?.registry?.sensor_order.length||placementLive();picker.value=placementLayoutScope;picker.disabled=placementPending;
 $('differenceSummary').before($('radarLayoutLabel'));
 if(layoutHammingPrefix()&&currentRow()){
  const baseline=referenceRow||initialRows.find(r=>String(r.id)===String(initial)),idx=run.registry.sensor_order.indexOf(placementPage.layout_scope);
  if(baseline&&idx>=0)$('differenceSummary').textContent=layoutHammingPrefix()+'Hamming '+currentRow().X.reduce((n,x,i)=>n+(x[idx]!==baseline.X[i][idx]?1:0),0);
 }
 if(layoutHammingPrefix()&&frontCollection()&&currentRow()?.hamming)$('mapBadge').textContent=$('mapBadge').textContent.replace('Hamming ',layoutHammingPrefix()+'Hamming ');
 if(mode==='result'&&frontCollection()&&currentRow()?.hamming){const row=currentRow();$('mapBadge').textContent=$('mapBadge').textContent.replace(`성능 ${row.hamming.performance_rank}위`,placementRankLabel(row));}
 renderEmptyResultMap();syncExpandedMapLayout();
};
