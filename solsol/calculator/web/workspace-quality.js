'use strict';
// Waiting for HTTP is not evidence that the worker has stopped or completed.
const qualityWaitingText=new WeakMap();
async function qualityStatusRequest(request,status,current,label='검산 기록 조회'){
 const previous=qualityWaitingText.get(status),started=Date.now(),last=previous?.shown===status.textContent?previous.last:status.textContent;let timer;
 const show=()=>{if(!current()){clearInterval(timer);return;}const shown=`${label} · 응답 대기 ${Math.floor((Date.now()-started)/1000)}초. 서버 응답을 기다리는 중이며 계산 중단·완료 여부는 아직 확인하지 못했습니다. 직전 표시: ${last}`;qualityWaitingText.set(status,{shown,last});status.textContent=shown;};
 timer=setInterval(show,1000);show();
 try{return await request;}finally{clearInterval(timer);}
}
function qualityInventoryMeaning(rule){
 if(!rule)return '저장 장비 조건';
 if(rule.mode!=='shared_resources_v1')return (rule.limits||[]).join(' / ')+'대 · '+(rule.mode==='all'?'전량 사용':'저장 재고 조건');
 return (rule.sensor_order||[]).map((id,i)=>id+': '+(rule.count_modes[i]==='OFF'?'수량 제한 없음':rule.count_modes[i]==='EXACT'?rule.lower[i]+'대 고정':rule.lower[i]+'–'+rule.upper[i]+'대')).join(' · ')+' · '+(rule.budget?.mode==='MAX'?'설치 예산 '+rule.budget.limit:'예산 제한 없음');
}
function qualityProgressText(packet,frozen){
 if(packet.schema!=='SOLSOL_PERSISTED_QUALITY_PROGRESS_LIST_V1'||!Array.isArray(packet.jobs)||packet.results_certified!==false)throw Error('저장 진행 응답 형식 불일치');
 const labels={RUNNING:'검산 중으로 저장됨',QUEUED:'대기로 저장됨',INTERRUPTED:'중단으로 저장됨',STOPPED:'사용자 중지로 저장됨',COMPLETED:'완료로 저장됨',EMPTY:'대상 없음으로 저장됨',ERROR:'오류로 저장됨'};
 return packet.jobs.map(j=>{
  if(j.parent?.run_id!==frozen.run_id||j.parent?.experiment_contract_id!==frozen.experiment_contract_id||j.parent?.config_sha256!==frozen.config_sha256||j.observation?.kind!=='PERSISTED_SNAPSHOT'||j.observation?.results_certified!==false||j.observation?.worker_liveness!=='UNKNOWN')throw Error('저장 진행과 선택 실행의 결속 불일치');
  return `검산 ${j.job_id} · ${labels[j.status]||'알 수 없는 저장 상태'} · 평가 ${Number.isFinite(j.evaluated)?j.evaluated.toLocaleString():'미기록'}회 · ${j.phase||'단계 미기록'}`;
 });
}
function qualityProgressPanel(parent,frozen,current){
 const section=document.createElement('details'),title=document.createElement('summary'),message=document.createElement('p'),rows=document.createElement('div'),button=document.createElement('button');
 section.id='qualityProgressSnapshot';section.open=true;title.textContent='저장된 검산 진행 먼저 확인';message.setAttribute('role','status');button.textContent='저장 진행 다시 읽기';section.append(title,message,rows,button);parent.append(section);let request=0;
 async function refresh(){const token=++request;button.disabled=true;message.textContent='저장 진행 기록 조회 중… 상세 결과 조회와 별도로 읽습니다.';
  try{const packet=await api(frozen.experiment_contract_id,'engine/runs/'+frozen.run_id+'/quality-jobs/progress');if(!current()||!section.isConnected||token!==request)return;const texts=qualityProgressText(packet,frozen);rows.replaceChildren();for(const text of texts){const p=document.createElement('p');p.textContent=text;rows.append(p);}message.textContent=texts.length?'저장 기록만 확인했습니다. 현재 실행 여부는 미확인입니다. 상세 기록과 검산 근거를 별도로 확인하세요.':'조회한 저장 위치에 검산 진행 기록이 없습니다.';}
  catch(e){if(current()&&section.isConnected&&token===request){rows.replaceChildren();message.textContent='빠른 진행 조회를 사용할 수 없습니다. 상세 조회는 계속됩니다. '+e.message;}}
  finally{if(current()&&section.isConnected&&token===request)button.disabled=false;}
 }
 button.onclick=refresh;refresh();return section;
}
// A stored example explains what changed; it never replaces the selected raw layout.
async function renderStoredImprovementExample(host,frozen,cid,jobs,current){
 host.replaceChildren();
 const refinement=jobs.find(j=>j.method==='refine');
 if(refinement){
  const base='engine/runs/'+frozen.run_id+'/quality-jobs/'+refinement.job_id;
  async function display(j){if(!current()||!host.isConnected)return;host.replaceChildren();
   const liveStatus=$('qualityStatus');if(liveStatus)liveStatus.textContent=`전체 개선: ${j.status} · ${j.phase} · ${j.evaluated.toLocaleString()}회 평가`;
   const title=document.createElement('h3');title.textContent='고정 문제 · 전체 해집합 개선';host.append(title);
   const r=j.refinement||{},n=r.current_source_count??j.source_count;
   noteText(host,`${qualityInventoryMeaning(frozen.compilation?.inventory_rule||frozen.problem?.inventory_rule)} · 원래 ${j.source_count}배치`);
   noteText(host,`${j.status} · ${j.phase} · ${j.evaluated.toLocaleString()}회 평가`);
   noteText(host,`${1+(j.refinement_round||0)}차 탐색 ${n}배치 · 비용 절감 검사 ${r.delete_completed||0}/${n} · 삭제·추가·이동 완료 ${r.local_completed||0}/${n}`);
   noteText(host,`채택한 연속 개선 ${r.accepted_steps||0}회 · 원해 대비 개선 발견 ${j.witness_count}행`);
   noteText(host,'원래 해 전체에서 시작해 개선 배치로 탐색을 이어갑니다. 해집합에 남는 새 대안도 다음 차수에서 검사합니다.');
   if(j.error)noteText(host,j.error);
   if(['RUNNING','QUEUED'].includes(j.status)){
    dButton(host,'refinementQuickStop','전체 개선 중지',async()=>{await api(cid,base+'/cancel',{});noteText(host,'현재 평가를 저장한 뒤 중지합니다.');});
    setTimeout(async()=>{if(!current()||!host.isConnected)return;try{await display(await api(cid,base));}catch(e){noteText(host,'진행 조회 실패: '+e.message);}},3000);
   }else if(['STOPPED','INTERRUPTED'].includes(j.status))dButton(host,'refinementQuickResume','저장 지점부터 전체 개선 계속',async()=>{await display(await api(cid,base+'/resume',{}));});
   if(j.status==='COMPLETED')noteText(host,`최종 개선 해집합 ${j.derived_front?.count??0}개. 검산·개선 배치 탭에서 전체 목록과 지도를 열 수 있습니다.`);
  }
  await display(refinement);return;
 }
 const job=jobs.find(j=>j.status==='COMPLETED'&&j.witness_count>0);
 if(!job){noteText(host,jobs.length?'저장된 검사에서 완료된 개선 사례를 아직 확인하지 못했습니다. 검사 기록에서 대상과 진행 상태를 확인하세요.':'이 실행에서 저장된 배치 개선 사례는 아직 없습니다.');return;}
 host.id='qualityImprovementExample';host.replaceChildren();noteText(host,'어떤 배치가 어떻게 바뀌었는지 저장된 개선 사례를 읽는 중…');
 try{
  for(const key of ['run_id','experiment_contract_id','config_sha256','evaluator_sha256'])if(job.parent[key]!==frozen[key])throw Error('저장 검사와 실행의 출처가 다릅니다.');
  const base='engine/runs/'+frozen.run_id+'/quality-jobs/'+job.job_id;
  const page=await api(cid,base+'/rows?offset=0&witnesses=true');if(!current()||!host.isConnected)return;
  if(page.job.job_id!==job.job_id||page.job.status!=='COMPLETED')throw Error('완료된 저장 검사 확인이 필요합니다.');
  const candidate=page.rows.find(r=>r.operation==='one_delete'&&r.improved_for?.length)||page.rows.find(r=>r.improved_for?.length);
  if(!candidate)throw Error('개선 배치의 실제 행을 읽지 못했습니다.');
  const source=candidate.improved_for[0],index=job.source_ids.indexOf(source);if(index<0)throw Error('원래 배치가 검사 대상에 없습니다.');
  // Replay rows are the mandatory source-ordered prefix in this stored job.
  const prefix=await api(cid,base+'/rows?offset='+index+'&witnesses=false');if(!current()||!host.isConnected)return;
  const replay=prefix.rows[0];if(prefix.job.job_id!==job.job_id||replay?.operation!=='replay'||replay.source_id!==source)throw Error('원래 배치의 저장 재평가 행을 확인하지 못했습니다.');
  const original={...replay,id:source},sensors=frozen.metadata.sensors,changes=[];
  if(original.X.length!==candidate.X.length)throw Error('두 배치의 후보 순서가 다릅니다.');
  original.X.forEach((row,i)=>{if(row.length!==candidate.X[i].length)throw Error('센서 순서가 다릅니다.');row.forEach((v,j)=>{if(v!==candidate.X[i][j])changes.push({site:i+1,sensor:sensors[j].id,name:sensors[j].name||sensors[j].label||sensors[j].id,removed:!!v});});});
  const metrics=frozen.metadata.metrics.filter(m=>m.id!=='cost'&&frozen.registry.objective_order.includes(m.id));
  const same=metrics.length>0&&metrics.every(m=>Number.isFinite(original.named_metrics?.[m.id])&&original.named_metrics[m.id]===candidate.named_metrics?.[m.id]);
  const cheaper=Number.isFinite(original.cost)&&Number.isFinite(candidate.cost)&&candidate.cost<original.cost;
  host.replaceChildren();host.dataset.sourceId=source;host.dataset.jobId=job.job_id;host.dataset.sequence=candidate.sequence;
  const title=document.createElement('h3');title.textContent=same&&cheaper?'이전에 만든 배치 하나에서 성능을 유지하고 비용을 줄였습니다':'이전에 만든 배치보다 좋아진 별도 배치를 찾았습니다';host.append(title);
  const action=changes.length===1?(changes[0].name+' 센서 1대를 후보 '+changes[0].site+'번에서 '+(changes[0].removed?'제거':'추가')):changes.length+'개 설치 항목 변경';
  const answer=document.createElement('p');answer.className='qualityConcreteAnswer';answer.textContent=`원래 배치 ${source} → ${action}. 비용 ${original.cost} → ${candidate.cost}${cheaper?' (절감 '+(original.cost-candidate.cost)+')':''}. ${same?'선택한 성능 목적값은 모두 같습니다.':'성능별 변화는 아래 표에서 확인하세요.'}`;host.append(answer);
  if(same&&cheaper)noteText(host,`${candidate.cost}보다 더 싼 같은 성능의 배치가 없는지는 아직 모릅니다. 확인된 것은 이 두 배치 사이의 비용 절감입니다.`);
  noteText(host,`이 검사는 원래 배치 ${job.source_count}개를 대상으로 했습니다. 아래는 저장된 개선 ${page.total}행 중 한 사례입니다. 현재 지도에서 선택한 배치를 바꾼 것이 아니며, 전체 해집합을 고쳤거나 가능한 모든 배치의 최저 비용을 증명한 결과도 아닙니다.`);
  const maps=document.createElement('div');maps.className='qualityCompareMaps qualityConcreteMaps';maps.id='qualityConcreteMaps';host.append(maps);
  for(const [label,row] of [['변경 전 · 원래 배치 '+source,original],['변경 후 · 별도 검산 배치',candidate]]){
   const panel=document.createElement('div');panel.dataset.sourceId=source;panel.dataset.x=JSON.stringify(row.X);const heading=document.createElement('h4');heading.textContent=label+' · 비용 '+row.cost;panel.append(heading);panel.insertAdjacentHTML('beforeend',qualityGeometryMap(frozen.problem,{...row,id:label}));maps.append(panel);
   for(const change of changes){const anchor=panel.querySelector('[data-site="'+change.site+'"]')||panel.querySelector('[data-marker-site="'+change.site+'"]');const svg=panel.querySelector('svg');if(!anchor||!svg)continue;const x=anchor.getAttribute('cx')??anchor.dataset.anchorX,y=anchor.getAttribute('cy')??anchor.dataset.anchorY;if(x==null||y==null)continue;const mark=document.createElementNS(svg.namespaceURI,'circle');for(const [k,v] of Object.entries({cx:x,cy:y,r:20,fill:'none',stroke:'#b12c62','stroke-width':4,'vector-effect':'non-scaling-stroke','data-changed-site':change.site}))mark.setAttribute(k,v);const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=change.name+' '+(change.removed?'제거한':'추가한')+' 위치 · 후보 '+change.site;mark.append(title);svg.append(mark);}
  }
  noteText(host,'자주색 테두리는 설치가 달라진 후보 위치입니다. 변경 전·후의 같은 위치를 비교하세요. 원은 명목 센서 범위이며 성능값은 저장된 검산 결과를 사용합니다.');
  renderQualityImprovement(host,frozen,original,candidate);
  const coverage=(frozen.metadata.coverage_metrics||[]).filter(m=>Number.isFinite(original.coverage_metrics?.[m.id])&&Number.isFinite(candidate.coverage_metrics?.[m.id]));if(coverage.length)evidenceTable(host,['평가영역 지표','변경 전','변경 후'],coverage.map(m=>[m.name,original.coverage_metrics[m.id].toFixed(2)+'%',candidate.coverage_metrics[m.id].toFixed(2)+'%']));
  const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent='검사 범위·배치 출처';detail.append(summary);noteText(detail,'실행 '+frozen.run_id+' · 원래 배치 '+source+' · 별도 검산 '+job.job_id+' / 평가행 '+candidate.sequence+' · '+job.evaluated+'회 평가. 이 지도는 원래 배치의 저장 재평가 행과 별도 개선 행을 비교합니다.');host.append(detail);
 }catch(e){if(current()&&host.isConnected){host.replaceChildren();noteText(host,'배치 개선 사례 조회 실패: '+e.message+' 저장 검사 목록에서 개별 기록을 확인하세요.');}}
}
// Shared quality entry point; consumes the same frozen run and public API for every model.
let qualityEpoch=0;
function renderCostReference(parent,frozen,cid,current,onAvailability=()=>{}){
 const section=qualitySection(parent,'저장 목표를 지키면서 비용을 더 줄일 수 있나요?');section.id='costReferenceSection';
 noteText(section,'저장 후보·설치 조건·수량·영역 목표를 유지한 별도 비용 배치를 계산합니다. 같은 수량이어도 공유 설치 지점에 따라 비용이 달라질 수 있습니다.');
 const status=document.createElement('p');status.id='costReferenceStatus';status.setAttribute('role','status');section.append(status);
 const controls=document.createElement('div'),output=document.createElement('div');section.append(controls,output);
 const base='engine/runs/'+frozen.run_id+'/cost-reference';let selected=null,timer=null,pending=false,supported=false,loaded=false;
 const active=j=>['QUEUED','RUNNING'].includes(j?.status);
 const fmt=v=>Number.isFinite(v)?v.toFixed(4).replace(/\.?0+$/,''):'미기록';
 function maps(r,container){
  container.replaceChildren();container.classList.add('costReferenceMaps');
  for(const [title,row] of [[r.observed_row?'원시 배치 '+r.observed_row.id:'목표 통과 관측 배치 없음',r.observed_row],['별도 비용 배치 '+r.reference_id,r.row]]){
   const cell=document.createElement('div');noteText(cell,title);if(row){const canvas=document.createElement('div');canvas.innerHTML=qualityGeometryMap(frozen.problem,row);cell.append(canvas);canvas.dataset.placementId=String(row.id);canvas.dataset.x=JSON.stringify(row.X);}container.append(cell);
  }
 }
 function render(job){
  output.replaceChildren();status.textContent=`${job.phase} · ${Math.round(job.elapsed_seconds)}초 · Model 평가 ${job.evaluations}회 / 요청 ${job.evaluation_attempts}회`;
  const start=controls.querySelector('#costReferenceStart');if(start)start.disabled=!supported||active(job)||pending;
  if(active(job))dButton(output,'costReferenceStop','중지',async()=>{try{const s=await api(cid,base+'/'+job.job_id+'/cancel',{});if(current()&&selected===job.job_id)status.textContent=s.stop_requested?'중지 요청됨 · 완료 단계 저장 중…':s.phase;}catch(e){if(current())status.textContent='중지 요청 실패: '+e.message;}});
  if(['STOPPED','INTERRUPTED'].includes(job.status))dButton(output,'costReferenceResume','저장 완료 단계부터 재개',async()=>{try{const next=await api(cid,base+'/'+job.job_id+'/resume',{});if(current())watch(next);}catch(e){if(current())status.textContent='재개 실패: '+e.message;}});
  if(job.status==='ERROR')noteText(output,'실패 사유: '+job.error+' · 이 기록으로 비용 개선을 판정하지 않습니다.');
  if(job.status==='COMPLETED'){
   const r=job.result;const answer=document.createElement('p');answer.className='qualityVerdict';
   answer.textContent=r.observed_minimum===null?`목표를 지키는 별도 비용 ${fmt(r.feasible_upper_bound)} 배치를 찾았습니다. 비교할 목표 통과 관측 배치가 없습니다.`:r.observed_cost_difference>1e-7?`목표를 지키면서 관측 최소 ${fmt(r.observed_minimum)}보다 비용이 ${fmt(r.observed_cost_difference)} 낮은 별도 배치 ${fmt(r.feasible_upper_bound)}를 찾았습니다.`:`별도 배치 비용 ${fmt(r.feasible_upper_bound)}, 관측 최소 ${fmt(r.observed_minimum)}입니다. 관측 최소와의 차이는 ${fmt(r.observed_cost_difference)}입니다.`;output.append(answer);
   evidenceTable(output,['비용 판단','값'],[['연속 완화 하한',fmt(r.lp_lower_bound)],['정수 solver 하한',fmt(r.integer_lower_bound)],['같은 Model 재평가 · 실현 상한',fmt(r.feasible_upper_bound)],['저장 목표·설치 통과 관측 최소',fmt(r.observed_minimum)],['관측 최소 − 별도 배치 비용',fmt(r.observed_cost_difference)]]);
   const sensorNames={radar:'Radar',rf_scanner:'RF'},coverageNames=Object.fromEntries((frozen.metadata.coverage_metrics||[]).map(m=>[m.id,m.name]));
   noteText(output,`${r.sensor_order.map((s,i)=>(sensorNames[s]||s)+' '+r.sensor_counts[i]+'대').join(' / ')} · 저장 영역 목표 ${r.targets.map(t=>(coverageNames[t.metric_id]||t.metric_id)+' '+t.epsilon+'%').join(' / ')}. 관측 비교 ${r.observed_qualified_count}행.`);
   noteText(output,'비용이 낮아져도 다른 성능은 낮아질 수 있습니다. 아래 원시 배치와 별도 배치의 성능·지도를 함께 비교하세요.');
   const metricValue=(row,m)=>{const value=row?.named_metrics?.[m.id];return Number.isFinite(value)?fmt(value*(m.display_scale||1)):'미기록';};
   const specs=frozen.metadata.metrics||[];evidenceTable(output,['모델 성능·비용','관측 최소 원시 배치','별도 비용 배치'],specs.filter(m=>Number.isFinite(r.row.named_metrics?.[m.id])||Number.isFinite(r.observed_row?.named_metrics?.[m.id])||frozen.registry.objective_order.includes(m.id)).map(m=>[m.name+' ('+m.unit+')',metricValue(r.observed_row,m),metricValue(r.row,m)]));
   const coverageKeys=[...new Set([...r.targets.map(t=>t.metric_id),...Object.keys(r.observed_row?.coverage_metrics||{}),...Object.keys(r.row.coverage_metrics||{})])];
   const coverageValue=(row,key)=>{const value=row?.coverage_metrics?.[key];return Number.isFinite(value)?fmt(value)+'%':'미기록';};
   evidenceTable(output,['영역 성능','관측 최소 원시 배치','별도 비용 배치'],coverageKeys.map(k=>[coverageNames[k]||k,coverageValue(r.observed_row,k),coverageValue(r.row,k)]));
   const mapBox=document.createElement('div');mapBox.id='costReferenceMaps';mapBox.className='qualityWitnessMaps';output.append(mapBox);maps(r,mapBox);
   dButton(output,'costReferenceExpand','두 배치 지도 크게 보기',()=>{const dialog=document.createElement('dialog');dialog.className='qualityDialog';dialog.id='costReferenceMapDialog';const close=document.createElement('button');close.textContent='닫기';close.onclick=()=>dialog.remove();dialog.append(close);noteText(dialog,'원시 optimizer 배치와 별도 비용 reference · 설치 위치와 명목 범위 비교');const box=document.createElement('div');dialog.append(box);document.body.append(dialog);maps(r,box);dialog.showModal();dialog.addEventListener('close',()=>dialog.remove(),{once:true});});
   noteText(output,r.meaning);noteText(output,'적용 범위: '+r.bound_scope);
   const details=qualitySection(output,'F/G와 출처');
   evidenceTable(details,['목적 F · 최소화 방향','관측 원시','별도 reference'],r.row.F.map((v,i)=>[frozen.registry.objective_order[i],fmt(r.observed_row?.F[i]),fmt(v)]));
   noteText(details,'별도 배치 G: '+JSON.stringify(r.row.G)+' · 설치 검증: '+r.validate_installation+' · 실행 '+frozen.run_id+' · formulation '+r.formulation_sha256);
   qualityFold(details,'원시 F/G·설치 검증·동일 실행 근거 보기');
  }
  dButton(output,'costReferenceDownload','비용 reference 근거 내려받기',async()=>{try{const evidence=await api(cid,base+'/'+job.job_id+'/export');if(current()&&selected===job.job_id)qualityDownload(evidence,'cost-reference-'+job.job_id+'.json');}catch(e){if(current())status.textContent='근거 내려받기 실패: '+e.message;}});
 }
 async function watch(job){if(!current()||selected!==job.job_id)return;clearTimeout(timer);render(job);if(active(job))timer=setTimeout(async()=>{if(!current()||selected!==job.job_id)return;try{await watch(await api(cid,base+'/'+job.job_id));}catch(e){if(current()&&selected===job.job_id)status.textContent='상태 조회 실패: '+e.message+' · 다시 열면 저장 기록을 조회합니다.';}},1000);}
 async function select(job){clearTimeout(timer);selected=job.job_id;const key=selected;output.replaceChildren();status.textContent='저장 비용 reference 조회 중…';try{const fresh=await api(cid,base+'/'+key);if(current()&&selected===key)watch(fresh);}catch(e){if(current()&&selected===key)status.textContent='저장 기록 조회 실패: '+e.message;}}
 async function load(){try{const data=await api(cid,base);if(!current())return;controls.replaceChildren();loaded=true;
  dButton(controls,'costReferenceStart','저장 목표의 비용 reference 계산',async()=>{if(pending)return;pending=true;controls.querySelector('#costReferenceStart').disabled=true;status.textContent='비용 reference 요청 중…';try{const job=await api(cid,base,{});pending=false;if(current())select(job);}catch(e){pending=false;if(current()){status.textContent='시작 실패: '+e.message;controls.querySelector('#costReferenceStart').disabled=false;}}});
  supported=data.capability.supported;controls.querySelector('#costReferenceStart').disabled=!supported;
  onAvailability(data);
  status.textContent=data.capability.supported?'미실행 · 버튼을 누르면 저장 조건으로 별도 계산합니다.':'비용 하한 계산 미지원: '+data.capability.reason+' 저장 검산 조회와는 별개입니다.';
  if(data.jobs.length){selectControl(controls,'저장 비용 reference',data.jobs.map(j=>[j.job_id,new Date(j.created_at*1000).toLocaleString()+' · '+j.status]),data.jobs[0].job_id,id=>select(data.jobs.find(j=>j.job_id===id)),'costReferenceHistory');select(data.jobs[0]);}
 }catch(e){if(current()){status.textContent='비용 reference 조회 실패: '+e.message;onAvailability(null,e);}}}
 let ready=load();return {open:async(key)=>{await ready;if(!current())return;if(!loaded){ready=load();await ready;if(!current())return;}if(key){const history=controls.querySelector('#costReferenceHistory');if(history)history.value=key;await select({job_id:key});}section.scrollIntoView({block:'start'});}};
}
function renderGridComparison(parent,frozen,row,cid,current){
 const section=qualitySection(parent,'평가점을 더 촘촘히 잡아도 성능이 유지되나요?');
 section.id='gridComparisonSection';
 noteText(section,'센서 위치와 수량은 고정하고 평가점 간격만 바꿉니다. 배치 개선이나 새 최적화가 아니라, 표본 간격에 따른 성능 변화입니다.');
 const status=document.createElement('p');status.setAttribute('role','status');section.append(status);
 const controls=document.createElement('div');section.append(controls);
 const output=document.createElement('div');section.append(output);
 const base='engine/runs/'+frozen.run_id+'/grid-comparison';let pending=false,selectedJob=null,poll=null;
 function render(job){
  output.replaceChildren();
  if(job.status!=='COMPLETED'){status.textContent=job.status==='ERROR'?'비교 실패: '+job.message:job.status==='INTERRUPTED'?job.message:'같은 배치를 두 격자에서 계산 중입니다…';return;}
  const r=job.result,a=r.original,b=r.comparison;
  const sensorNames=Object.fromEntries((frozen.metadata.sensors||[]).map(s=>[s.id,s.name||s.label||({radar:'Radar',rf_scanner:'RF',eoir:'EO/IR'}[s.id])]));
  status.textContent=`저장 배치 ${r.raw_id} · ${r.sensor_counts.map((n,i)=>(sensorNames[r.sensor_order[i]]||r.sensor_order[i])+' '+n+'대').join(' / ')} · 위치 동일`;
  noteText(output,`${a.step}m · ${a.point_count.toLocaleString()}점 → ${b.step}m · ${b.point_count.toLocaleString()}점. 비용 ${r.cost_unchanged===true?'동일 확인':'출력 미기록'}.`);
  if(r.baseline_reassessment)noteText(output,`왼쪽은 저장된 원본 결과, 오른쪽은 별도 비교 ${job.job_id}의 재평가 결과입니다. 새 평가 버전으로 원래 ${a.step}m 간격을 먼저 재현해 목적값·제약값·비용 일치를 확인했습니다. 센서 위치는 원본 배치 ${r.raw_id}와 같습니다.`);
  const specs=r.metadata.coverage_metrics||[],names=Object.fromEntries(specs.map(s=>[s.id,s.name]));
  const keys=Object.keys(a.coverage_metrics);
  evidenceTable(output,['평가영역 성능',`${a.step}m`,`${b.step}m`,'변화'],keys.map(k=>[names[k]||k,a.coverage_metrics[k].toFixed(2)+'%',b.coverage_metrics[k].toFixed(2)+'%',(b.coverage_metrics[k]-a.coverage_metrics[k]).toFixed(2)+'%p']));
  const metrics=(frozen.metadata.metrics||[]).filter(m=>m.id!=='cost'&&Number.isFinite(a.named_metrics[m.id])&&Number.isFinite(b.named_metrics[m.id]));
  if(metrics.length)evidenceTable(output,['모델 성능 · 목적 계산 값',`${a.step}m`,`${b.step}m`,'변화'],metrics.map(m=>{const scale=m.display_scale||1,x=a.named_metrics[m.id]*scale,y=b.named_metrics[m.id]*scale;return[m.name+' ('+m.unit+')',x.toFixed(4),y.toFixed(4),(y-x).toFixed(4)];}));
  const pass=v=>v===null?'목표 미설정':v?'목표 통과':'목표 미달';
  if(r.goal_kind==='MODEL_QUALITY_0_1'&&r.goals!==null)noteText(output,'이 과거 실행은 모델 품질 0–1 목표를 사용합니다. 위 영역 커버율 목표와는 다른 판정입니다.');
  if(r.goals!==null)noteText(output,r.goal_kind==='MODEL_QUALITY_0_1'?'저장 모델 품질 목표: '+r.goals.join(' / '):'저장 영역 목표: '+Object.entries(r.goals).map(([k,v])=>(names[k]||k)+' '+v+'%').join(' · '));
  noteText(output,r.goals===null?'이 실행에는 정량 목표가 없습니다. 위 성능 변화로 표본 간격에 대한 민감도를 판단하세요.':`저장 목표 판정: ${pass(a.target_pass)} → ${pass(b.target_pass)}. ${a.target_pass!==b.target_pass?'평가 간격에 따라 판정이 바뀌었습니다.':'두 간격에서 판정이 같습니다.'}`);
  noteText(output,r.meaning);
  const detail=qualitySection(output,'목적값과 재현 근거');
  evidenceTable(detail,['목적 · 최소화 방향 원시 F','원래 간격','비교 간격'],a.F.map((v,i)=>[frozen.registry.objective_order[i],v,b.F[i]]));
  dButton(detail,'gridDownload','비교 수치·입력 출처 내려받기',()=>qualityDownload(job,'grid-comparison-'+job.job_id+'.json'));qualityFold(detail,'목적값·실행 식별값과 계산 근거 보기');
 }
 async function watch(job){if(!current()||selectedJob!==job.job_id)return;render(job);if(['QUEUED','RUNNING'].includes(job.status)){poll=setTimeout(async()=>{if(!current()||selectedJob!==job.job_id)return;try{await watch(await api(cid,base+'/'+job.job_id));}catch(e){if(current()&&selectedJob===job.job_id)status.textContent='상태 조회 실패: '+e.message;}},1000);}else{pending=false;const b=controls.querySelector('#gridCompareStart');if(b)b.disabled=!row;}}
 function selectJob(job){clearTimeout(poll);selectedJob=job.job_id;watch(job);}
 async function load(){try{
  const data=await api(cid,base);if(!current())return;
  if(!data.capability.supported){status.textContent=data.capability.reason;return;}
  selectControl(controls,'비교할 평가점 간격',data.capability.steps.map(s=>[String(s),s+' m']),'250',()=>{},'gridCompareStep');
  dButton(controls,'gridCompareStart',row?`선택 배치 ${row.id}의 간격 비교 시작`:'지도에서 배치를 먼저 선택하세요',async()=>{
   if(pending||!row)return;pending=true;document.getElementById('gridCompareStart').disabled=true;status.textContent='비교 요청 중…';
   const history=controls.querySelector('#gridCompareHistory');if(history)history.disabled=true;
   try{const response=await api(cid,base,{raw_id:row.id,step:Number(controls.querySelector('#gridCompareStep').value)});if(current())selectJob(response);}catch(e){if(current()){pending=false;controls.querySelector('#gridCompareStart').disabled=false;status.textContent='비교 시작 실패: '+e.message;}}finally{if(current()&&history)history.disabled=false;}
  });controls.querySelector('#gridCompareStart').disabled=!row;
  if(data.jobs.length)selectControl(controls,'저장된 간격 비교',[['','기록 선택'],...data.jobs.map(j=>[j.job_id,`배치 ${j.options.raw_id} · ${j.options.step}m · ${j.status}`])],'',id=>{if(id)selectJob(data.jobs.find(j=>j.job_id===id));else{clearTimeout(poll);selectedJob=null;output.replaceChildren();}},'gridCompareHistory');
  status.textContent=row?'아래 버튼을 누르면 현재 선택 배치만 별도로 평가합니다.':'지도에서 비교할 배치를 선택한 뒤 다시 열어주세요.';
 }catch(e){if(current())status.textContent='간격 비교 기능 조회 실패: '+e.message;}}
 load();
}
function qualityGeometryMap(problem,row){
 const demand=$('showDemand'),layer=$('mapLayer'),area=$('showArea'),saved=[demand.checked,layer.value,area.checked];
 try{demand.checked=false;layer.value='all';area.checked=true;const svg=mapHTML(problem,row);requestAnimationFrame(syncSensorSymbols);return svg+'<div class="qualityMapLegend">'+($('registeredLegend')?.innerHTML||'')+'</div>';}finally{demand.checked=saved[0];layer.value=saved[1];area.checked=saved[2];}
}
function qualitySection(parent,title){const s=document.createElement('section');s.className='qualitySection';const h=document.createElement('h3');h.textContent=title;s.append(h);parent.append(s);return s;}
function qualityFold(section,label){const d=document.createElement('details'),s=document.createElement('summary');s.textContent=label;d.className='qualityEvidenceFold';section.before(d);d.append(s,section);return d;}
function qualityNavigation(parent,panels,initial='summary'){
 const nav=document.createElement('nav');nav.className='qualityNavigation';nav.setAttribute('aria-label','해품질 읽는 순서');parent.prepend(nav);
 const names={summary:'1. 해집합 판단',evidence:'2. 탐색·재현 근거',checks:'3. 검산·개선 배치'};
 function show(id){parent.closest('dialog')?.scrollTo({top:0});for(const [key,p] of Object.entries(panels)){p.hidden=key!==id;nav.querySelector('[data-quality-view='+key+']')?.setAttribute('aria-pressed',String(key===id));}}
 for(const [id,label] of Object.entries(names)){const b=document.createElement('button');b.dataset.qualityView=id;b.textContent=label;b.onclick=()=>show(id);nav.append(b);}show(initial);return show;
}
function qualityDownload(value,name){const u=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),2000);}
async function openQualityCenter(selectedJobId=null,destination=null){
 const old=$('qualityDialog');if(old){old.close();old.remove();}const d=document.createElement('dialog');d.id='qualityDialog';d.className='qualityDialog';document.body.append(d);
 const head=document.createElement('div');head.className='dialogHead';const h=document.createElement('h2');h.textContent='해품질 · 탐색 품질 · 검산';head.append(h);dButton(head,'qualityClose','닫기',()=>{qualityEpoch++;d.close();d.remove();});d.append(head);
 const intro=qualitySection(d,'계산부터 검산까지');noteText(intro,'공통 영역·후보지 → 모델별 센서·목적·제약 → 공통 초기화·탐색 → 원시 해집합 → 별도 검산·개선 후보 순서입니다. 검산 결과는 원시 해집합을 덮어쓰지 않습니다.');
 const guide=document.createElement('a');guide.href='/quality-guide.html';guide.target='_blank';guide.rel='noopener';guide.textContent='실행·설정·품질 지표·검산·기존 연구 안내 읽기 ↗';intro.append(guide);
 evidenceTable(intro,['확인할 내용','판단 기준'],[['해품질','실현가능 비지배 해·정량 목표 통과 해·Hamming 구조 다양성을 구분합니다.'],['탐색 품질','세대별 평가 수, 고유 배치 수, 중복 평가, 누적 해 수를 함께 봅니다. 해 수가 줄었다고 탐색 실패는 아닙니다.'],['검산','원시 재평가 → 센서 삭제·추가·위치 이동 → 제약·목표 확인 → 지배 개선 여부 순으로 봅니다.'],['MILP·ε 제약','전체 이웃의 MILP 판정과 전체 설치 조합 판정을 구분합니다. 전체 조합은 규모에 따라 오래 걸리며 완료한 범위에서만 판정합니다.']]);
 if(!run||mode!=='result'){noteText(d,'먼저 저장 실행을 선택하세요. 설정 화면에서는 공통 영역·센서·목적·계산 탭을 사용합니다.');d.showModal();return;}
 const rid=run.run_id,cid=draft.sensor,epoch=++qualityEpoch,frozen=structuredClone(run),frozenSelected=structuredClone(currentRow());let loaded=null,result=null,busy=false,job=null,pageOffset=0,witnessOnly=true,pollTimer=null,pageRequest=0;
 const status=document.createElement('p');status.id='qualityStatus';status.setAttribute('role','status');status.textContent='저장된 품질 근거를 읽는 중…';d.append(status);d.showModal();
 const current=()=>qualityEpoch===epoch&&d.open&&d.isConnected&&run?.run_id===rid&&draft.sensor===cid;
 qualityProgressPanel(d,frozen,current);
 const content=document.createElement('div');d.append(content);
 const panels={summary:document.createElement('div'),checks:document.createElement('div'),evidence:document.createElement('div')};for(const [id,p] of Object.entries(panels)){p.dataset.qualityPanel=id;content.append(p);}
 panels.evidence.append(intro);const showPanel=qualityNavigation(content,panels,selectedJobId?'checks':'summary');
 const availability=document.createElement('div');availability.className='qualityAvailability';availability.id='qualityAvailability';const availabilityDetails=document.createElement('details'),availabilityTitle=document.createElement('summary');availabilityTitle.textContent='기능 지원·조회 상태';availabilityDetails.className='qualityEvidenceFold';availabilityDetails.append(availabilityTitle,availability);content.before(availabilityDetails);
 const improvementExample=document.createElement('section');improvementExample.className='qualitySection';improvementExample.id='qualityImprovementExample';panels.summary.prepend(improvementExample);noteText(improvementExample,'저장된 배치 개선 결과를 확인하는 중…');
 const savedState=document.createElement('p'),costState=document.createElement('p');savedState.id='qualitySavedAvailability';costState.id='qualityCostAvailability';savedState.setAttribute('role','status');costState.setAttribute('role','status');savedState.textContent='저장 검산 · 조회 중…';costState.textContent='비용 하한 · 지원 여부 조회 중…';availability.append(savedState,costState);
 dButton(availability,'qualitySavedAccess','저장 검산 보기',()=>{showPanel('checks');const target=$('qualitySavedFirst')||$('qualityCheckResult');target?.scrollIntoView({block:'start'});});
 dButton(availability,'qualityCostAccess','비용 하한 적용 범위',()=>{showPanel('checks');costController.open();});
 const costController=renderCostReference(panels.checks,frozen,cid,current,(data,error)=>{costState.textContent=error?'비용 하한 · 조회 실패 (미지원 판정 아님)':data.capability.supported?'비용 하한 · 계산 지원 · 저장 기록 '+data.jobs.length+'건':'비용 하한 · 이 저장 조건에서 계산 미지원 · 저장 검산과 별개';});
 renderGridComparison(panels.checks,frozen,frozenSelected,cid,current);
 function navigate(target){if(target==='cost'||target.startsWith('costEvidence:')){showPanel('checks');costController.open(target==='cost'?null:target.slice('costEvidence:'.length));return;}if(target==='grid'){showPanel('checks');panels.checks.querySelector('#gridComparisonSection').scrollIntoView({block:'start'});return;}if(target==='tradeoff'){openTradeoff();return;}if(target==='repeatSetup'){qualityEpoch++;d.close();d.remove();openValidation(false,structuredClone(frozen.submitted_request));return;}if(target==='checks'){showPanel('checks');const fold=$('qualityScope')?.closest('details');if(fold)fold.open=true;$('qualityRun')?.focus();return;}showPanel('evidence');const el=panels.evidence.querySelector('[data-evidence="'+target+'"]');if(el){for(let n=el;n&&n!==panels.evidence;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;el.scrollIntoView({block:'start'});}}
 d.addEventListener('quality-navigate',e=>navigate(e.detail));
 if(destination&&(destination==='checks'||destination==='cost'||destination==='grid'||destination.startsWith('costEvidence:'))){navigate(destination);destination=null;}
 const context=document.createElement('p');context.className='qualityContext';context.textContent=`저장 실행 ${rid.slice(0,8)}의 최종 해집합을 판단합니다. 지도에서 선택한 배치는 ${frozenSelected?.id??'없음'}입니다. 목록 필터와 검산 대상은 별도로 선택합니다.`;content.before(context);
 function renderResult(){const body=$('qualityCheckResult');if(!body)return;body.replaceChildren();if(!result){noteText(body,'검산 미실행입니다. 검산 대상과 방법을 선택하거나 저장 검산을 여세요.');return;}
  const words={COMPLETED:'지정 이웃 검사 완료',PARTIAL:'일부 검사 · 이어서 가능',EMPTY:'대상 해 없음',ERROR:'검산 오류',BOUNDED:'예산 내 후보 검사 완료'};
  noteText(body,`${words[result.status]||result.status} · 대상 ${result.source_count}배치 · 이번 평가 ${result.tested} · 누적 ${result.cumulative_tested}/${result.total} · 남은 이웃 ${result.untested} · 개선 후보 ${result.improvement_count}개`);
  if(result.error)noteText(body,result.error);noteText(body,result.claim);noteText(body,'정확 수량 사용에서는 1개 삭제가 수량 제약을 위반할 수 있습니다. 이 경우 검산은 수행됐지만 개선해에는 포함하지 않습니다.');
  evidenceTable(body,['원시 행','검사','제약','정량 목표','비용','개선'],result.rows.slice(0,100).map(r=>[r.raw_id,{replay:'원시 재평가',one_delete:'1개 삭제',one_swap:'1개 이동'}[r.operation]||r.operation,r.feasible?'충족':'미충족',qualityQualification(r,loaded.assessment.goals),r.cost,r.improved?'발견':r.replay_match===false?'재평가 불일치':'—']));
  if(result.rows.length>100)noteText(body,`상세 ${result.rows.length}행 중100행 표시. 전체는 검산 기록 내려받기에 있습니다.`);
  dButton(body,'qualityExport','검산 기록 내려받기',()=>qualityDownload(result,'quality-'+result.check_id+'.json'));
  if(result.next_offset!==null)noteText(body,'과거 평가 제한 방식의 기록입니다. 새 전체 검산은 아래 공통 검사에서 시작하세요.');
  const improved=qualitySection(body,'검산에서 찾은 개선 배치');if(!result.witnesses.length)noteText(improved,'이번 검사에서는 지배 개선 후보를 찾지 못했습니다. 미검사 이웃과 전역 최적성은 별개입니다.');
  result.witnesses.slice(0,100).forEach((w,i)=>dButton(improved,'qualityWitness'+i,`원시 행 ${w.raw_id} → 검산 후보 ${i+1} · 비용 ${w.cost}`,()=>{const maps=$('qualityWitnessMaps');maps.replaceChildren();
   if(!current())return;const original=frozen.rows.find(r=>r.id===w.raw_id)||(frozenSelected?.id===w.raw_id?frozenSelected:null);noteText(maps,`원시 행 ${w.raw_id} → 검산 개선 후보 ${i+1}. 설치 위치·명목 반경의 기하 비교입니다. 공간 품질 heatmap이 아니며 원시 optimizer 해가 아닙니다.`);
   if(original){const left=document.createElement('div');left.innerHTML=qualityGeometryMap(frozen.problem,original);maps.append(left);}const right=document.createElement('div');right.innerHTML=qualityGeometryMap(frozen.problem,{...w,id:'검산 '+(i+1)});maps.append(right);
   noteText(maps,'아래 F는 모델이 최적화기에 제공한 최소화 방향의 값입니다. 품질이 좋아지면 F는 작아질 수 있으며, 비용 F도 표시 비용과 척도가 다를 수 있습니다. 개선 판정은 모든 F가 나빠지지 않고 하나 이상 좋아지며 제약을 만족할 때입니다.');
   evidenceTable(maps,['목적','원래 F · 작을수록 좋음','검산 F · 작을수록 좋음'],w.F.map((v,j)=>[frozen.registry.objective_order[j],original?.F[j]??'원시 파일 참조',v]));}));
  const maps=document.createElement('div');maps.id='qualityWitnessMaps';body.append(maps);
 }
 const jobBase='engine/runs/'+rid+'/quality-jobs';
 const savedFirst=qualitySection(panels.checks,'저장 검산 바로 열기');savedFirst.id='qualitySavedFirst';panels.checks.prepend(savedFirst);
 const savedMessage=document.createElement('p');savedMessage.textContent='저장 검산 목록 조회 중…';savedFirst.append(savedMessage);
 async function loadSavedFirst(){
  try{const data=await api(cid,jobBase);if(!current())return;
   const completed=data.jobs.filter(j=>j.status==='COMPLETED').length;
   savedState.textContent=data.jobs.length?`저장 검산 · 조회 가능 · ${data.jobs.length}건 중 완료 ${completed}건 · 검사 범위는 각 기록에서 확인`:'저장 검산 · 조회 가능 · 저장 기록 없음 (미지원 아님)';
   renderStoredImprovementExample(improvementExample,frozen,cid,data.jobs,current);
   if(!savedFirst.isConnected)return;
   savedMessage.textContent=data.jobs.length?'종합 지표 계산을 기다리지 않고 저장 검산을 열 수 있습니다.':'이 실행에는 아직 저장된 검산이 없습니다. 원시 해집합은 지도에서 볼 수 있으며, 아래 검산 설정은 별도로 준비됩니다.';
   for(const item of data.jobs)dButton(savedFirst,'quickSaved_'+item.job_id,(data.methods[item.method]?.label||item.method)+' · '+item.status+' · 개선 발견 '+item.witness_count+'행',async()=>{
    const box=savedFirst.querySelector('.quickSavedResult')||document.createElement('div');box.className='quickSavedResult';savedFirst.append(box);box.replaceChildren();noteText(box,'선택한 검산 결과 조회 중…');
    try{const v=await api(cid,jobBase+'/'+item.job_id+'/rows?offset=0&witnesses=true');if(!current()||!box.isConnected)return;box.replaceChildren();noteText(box,'검산 '+item.job_id+' · '+v.job.status+' · '+v.job.evaluated+'회 평가 · 개선 발견 총 '+v.total+'행 중 첫 '+v.rows.length+'행 표시. 전체 페이지는 아래 검산 결과에서 볼 수 있습니다. 원시 optimizer 해와 별도인 저장 기록입니다.');if(v.job.status==='ERROR'){noteText(box,'검산 오류로 개선 여부를 판정할 수 없습니다: '+(v.job.error||''));return;}
     evidenceTable(box,['검사','비용','목표 판정','개선 대상 원시 행'],v.rows.map(r=>[r.operation,r.cost,r.qualified===true?'통과':r.qualified===false?'미달':'미설정·미기록',r.improved_for.join(', ')]));
     if(!v.rows.length)noteText(box,'이 기록에서 표시할 개선 배치가 없습니다. 미완료 검사는 개선 없음으로 확정하지 않습니다.');
     for(const [i,r] of v.rows.entries())dButton(box,'quickMap_'+i,'별도 개선 배치 '+(i+1)+' 지도',()=>{const map=document.createElement('div');map.innerHTML=qualityGeometryMap(frozen.problem,{...r,id:'검산 '+item.job_id.slice(0,8)+' / '+i});box.append(map);});
    }catch(e){box.replaceChildren();noteText(box,'저장 검산 조회 실패: '+e.message);}
   });
  }catch(e){if(current()){savedState.textContent='저장 검산 · 조회 실패 (기록 없음·미지원 판정 아님)';savedMessage.textContent='저장 검산 목록 조회 실패: '+e.message;improvementExample.replaceChildren();noteText(improvementExample,'저장된 배치 개선 결과를 조회하지 못했습니다. 개선 없음으로 판정한 것이 아닙니다.');}}
 }
 loadSavedFirst();

 const running=j=>['QUEUED','RUNNING'].includes(j?.status);
 async function refreshJob(){if(!current()||!job)return;clearTimeout(pollTimer);const selected=job.job_id,request=++pageRequest;if($('qualityCheckResult').dataset.jobId!==selected){$('qualityCheckResult').replaceChildren();status.textContent='선택한 검산 기록을 읽는 중…';}
  try{const value=await qualityStatusRequest(api(cid,jobBase+'/'+selected+'/rows?offset='+pageOffset+'&witnesses='+witnessOnly),status,()=>current()&&job?.job_id===selected&&request===pageRequest,'검산 상태·배치 조회');if(!current()||job?.job_id!==selected||request!==pageRequest)return;job=value.job;renderJob(value);if(running(job))pollTimer=setTimeout(refreshJob,1000);}catch(e){if(current()&&request===pageRequest&&job?.job_id===selected)status.textContent='검산 상태 연결 실패: '+e.message+' · 계산이 끝났다는 뜻이 아닙니다. 창을 다시 열면 저장 상태를 조회합니다.';}
 }
 function renderJob(value){const body=$('qualityCheckResult');body.replaceChildren();body.dataset.jobId=job.job_id;const labels={QUEUED:'준비',RUNNING:'검산 중',STOPPED:'사용자가 중지함',INTERRUPTED:'서버 종료로 중단됨',COMPLETED:'선택 범위 전체 완료',EMPTY:'대상 해 없음',ERROR:'검산 오류'};
  // Reading an unchanged completed check must not recompute the whole saved study.
  // New/running/completed-since-load jobs still invalidate evidence for the next read.
  if(!qualityCheckEvidenceUnchanged(loaded,job))qualityEvidenceCache.delete(qualityEvidenceKey(frozen));
  const judgement=document.createElement('p');judgement.className='qualityVerdict';judgement.textContent=job.status==='ERROR'?'검산 오류로 개선 여부를 판정할 수 없습니다.':job.witness_count>0?'검사한 원해보다 모든 목적이 나빠지지 않고 하나 이상 좋아지는 개선 배치를 찾았습니다. 아래 지도에서 원해와 비교하세요.':job.status==='COMPLETED'&&job.scope_complete?'선택한 검사 범위를 모두 확인했으며 지배 개선 배치를 찾지 못했습니다. 이 범위에서의 결과이며 전역 최적 증명은 아닙니다.':'검사가 완료되지 않았습니다. 개선 후보가 아직 없다는 이유로 좋은 해라고 판정하지 않습니다.';body.append(judgement);
  status.textContent=`저장 검산: ${labels[job.status]||job.status} · ${job.evaluated.toLocaleString()}회 평가 · ${Math.round(job.elapsed_seconds)}초`;
  if(job.method==='refine'){
   const r=job.refinement||{},n=r.current_source_count??job.source_count;
   judgement.textContent=job.status==='ERROR'?'반복 개선 오류: 저장 근거를 확인하세요.':job.status==='COMPLETED'?'개선 해집합에 남은 모든 배치의 삭제·추가·위치 이동 탐색을 마쳤습니다.':'고정 조건에서 전체 배치를 개선하고, 살아남은 새 대안도 이어서 탐색하고 있습니다.';
   noteText(body,`원래 전체 ${job.source_count}배치 · ${1+(job.refinement_round||0)}차 탐색 · ${job.phase}`);
   noteText(body,`이번 차수 ${n}배치: 비용 절감 ${r.delete_completed||0}/${n} · 위치 변경까지 완료 ${r.local_completed||0}/${n} · 채택한 연속 개선 ${r.accepted_steps||0}회`);
   noteText(body,'후속 탐색은 발견한 개선 배치에서 시작합니다. 성능을 떨어뜨리지 않는 비용 절감과 실제 성능 개선을 채택하며, 후보·모델·목적·예산은 저장 조건으로 고정합니다.');
   if(job.derived_front&&job.status==='COMPLETED')dButton(body,'qualityRefinedFront','최종 개선 해집합 '+job.derived_front.count+'개 열기',async()=>{
    const box=document.createElement('div');body.append(box);
    async function show(offset){try{const v=await api(cid,jobBase+'/'+job.job_id+'/front?offset='+offset);if(!current()||!box.isConnected)return;box.replaceChildren();noteText(box,`전체 관측으로 갱신한 개선 해집합 ${v.total}개 · ${offset+1}–${Math.min(offset+100,v.total)} 표시. 원래 해집합과 별도로 저장했습니다.`);
     evidenceTable(box,['출처','비용','센서 수','정량 목표'],v.rows.map(r=>[r.reference.kind==='raw'?'원시 '+r.reference.raw_id:'개선 '+r.reference.sequence,r.cost,r.sensor_counts.join(' / '),qualityQualification(r,loaded.assessment.goals)]));
     for(const [i,r] of v.rows.entries())dButton(box,'refinedMap'+i,'비용 '+r.cost+' · 개선 배치 지도',()=>{box.querySelector('.refinedMap')?.remove();const map=document.createElement('div');map.className='refinedMap';map.innerHTML=qualityGeometryMap(frozen.problem,{...r,id:r.reference.kind==='raw'?'원시 '+r.reference.raw_id:'개선 '+r.reference.sequence});box.append(map);});
     dButton(box,'refinedPrev','이전 100개',()=>show(Math.max(0,offset-100)),offset===0);dButton(box,'refinedNext','다음 100개',()=>show(offset+100),offset+100>=v.total);
    }catch(e){noteText(box,'개선집합 조회 실패: '+e.message);}}await show(0);
   });
  }
  noteText(body,'별도 검산 ID: '+job.job_id);noteText(body,`이 기록의 검사 대상은 ${job.source_count}배치입니다. 최종 전체 ${loaded.assessment.archive_unique_X}배치와 구분하세요. ${job.source_ids.includes(frozenSelected?.id)?'현재 선택 배치도 검사했습니다.':'현재 선택 배치는 이 검사의 대상이 아닙니다.'}`);
  noteText(body,`검사 ${job.evaluated.toLocaleString()} / ${job.total??('최대 '+(job.total_upper_bound??'계산 중'))}회 · 개선 발견 평가행 ${job.witness_count}개 (같은 설치 배치의 반복 발견 포함). 개선은 모든 목적이 나빠지지 않고 하나 이상 좋아지는 실제 배치입니다.`);
  const completed=(loaded.budget_quality?.checked_jobs||[]).find(j=>j.job_id===job.job_id);if(completed){evidenceTable(body,['집계 구분','현재 기록'],[['개선 발견 평가행',completed.improvement_evaluation_rows??completed.improvement_count],['서로 다른 개선 배치',completed.improvement_unique_X??'미집계'],['개선된 최종 원해',completed.improved_source_count??'미집계'],['저장 목표 통과 개선 배치',loaded.assessment.goals===null?'목표 미설정':completed.qualified_improvement_unique_X??'판정 미기록']]);}
  if(job.error)noteText(body,job.error);noteText(body,'설치 영역·장비 수량·Model 제약과 저장 정량 목표를 각각 확인합니다. 검산 배치는 원시 optimizer 해집합과 분리합니다.');
  if(running(job))dButton(body,'qualityStop','검산 중지',async()=>{await api(cid,jobBase+'/'+job.job_id+'/cancel',{});status.textContent='중지 요청됨 · 현재 Model 또는 MILP 응답 후 저장합니다.';});
  if(['STOPPED','INTERRUPTED'].includes(job.status))dButton(body,'qualityResume','저장 지점부터 계속',async()=>{try{job=await api(cid,jobBase+'/'+job.job_id+'/resume',{});refreshJob();}catch(e){status.textContent=e.message;}});
  dButton(body,'qualityExport','전체 검산 근거 내려받기',async()=>{try{const response=await fetch('/contracts/'+encodeURIComponent(cid)+'/api/'+jobBase+'/'+job.job_id+'/export',{headers:{'X-Experiment-Contract':cid}});if(!response.ok)throw new Error(await response.text());const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='quality-'+job.job_id+'.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}catch(e){status.textContent='내려받기 실패: '+e.message;}});
  selectControl(body,'결과 보기',[['true','개선 배치'],['false','검사한 배치 전체']],String(witnessOnly),v=>{witnessOnly=v==='true';pageOffset=0;refreshJob();},'qualityRowsFilter');
  noteText(body,`${value.total}개 중 ${value.total?value.offset+1:0}–${Math.min(value.total,value.offset+value.rows.length)} 표시. 100개 단위 표시는 화면 페이지이며 검산 제한이 아닙니다.`);
  dButton(body,'qualityPrevPage','이전 100개',()=>{pageOffset=Math.max(0,pageOffset-100);refreshJob();},pageOffset===0);dButton(body,'qualityNextPage','다음 100개',()=>{pageOffset+=100;refreshJob();},pageOffset+100>=value.total);
  evidenceTable(body,['검사','제약·재고','정량 목표','비용','개선 대상 원시 행'],value.rows.map(r=>[{replay:'원시 재평가',one_delete:'삭제',one_add:'추가',one_swap:'위치 이동',exact_reference:'전체 조합'}[r.operation],r.feasible?'충족':'미충족',qualityQualification(r,loaded.assessment.goals),r.cost,r.improved_for.join(', ')||'—']));
  const maps=document.createElement('div');maps.id='qualityWitnessMaps';
  value.rows.filter(r=>r.improved_for.length&&job.status!=='ERROR').forEach((r,i)=>dButton(body,'qualityWitness'+i,'개선 발견 '+(value.offset+i+1)+' · '+qualityQualification(r,loaded.assessment.goals)+' · 지도 비교',()=>{maps.replaceChildren();const baseId=r.improved_for[0],original=frozen.rows.find(x=>x.id===baseId)||loaded?.budget_quality?.final_layouts?.find(x=>x.id===baseId)||(frozenSelected?.id===baseId?frozenSelected:null);noteText(maps,'검산 배치 ID '+job.job_id+' / '+r.sequence+' · 원시 행 '+baseId+' 대비 개선. 설치 위치·명목 반경의 기하 비교이며 성능 heatmap은 아닙니다. F는 최소화 방향 값으로 작을수록 좋습니다.');if(original){const left=document.createElement('div');left.innerHTML=qualityGeometryMap(frozen.problem,original);maps.append(left);}const right=document.createElement('div');right.innerHTML=qualityGeometryMap(frozen.problem,{...r,id:'검산'});maps.append(right);renderQualityImprovement(maps,frozen,original,r);const raw=document.createElement('details'),title=document.createElement('summary');title.textContent='모델 F 원문 · 계산 근거';raw.append(title);maps.append(raw);evidenceTable(raw,['목적','원래 F','검산 F'],r.F.map((v,j)=>[frozen.registry.objective_order[j],original?.F[j]??'원시 참조',v]));}));body.append(maps);
  if(job.certificates.length){const section=qualitySection(body,'MILP·ε-constraint 판정');noteText(section,job.method==='milp'?'모든 검사 이웃 중 다른 목적 F를 원래 해보다 나쁘게 하지 않는 후보의 최솟값을 MILP로 구하고 직접 최소값과 대조했습니다. 전체 설치 공간의 전역 증명은 아닙니다.':'선언된 설치 영역·재고 조건의 전체 조합을 평가하고 다른 F의 상한을 원래 해로 고정해 최솟값을 구합니다. 완료된 범위에서만 판정합니다.');evidenceTable(section,['원시 행','최소화 목적','조건 통과 후보','최선 F','검사 범위'],job.certificates.map(c=>[c.raw_id,frozen.registry.objective_order[c.objective],c.eligible,c.best_F??'없음',job.method==='milp'?'전체 단일 변경 이웃':'전체 설치 조합']));}
  $('qualityRun').disabled=running(job);
 }
 async function compute(){if(busy||!current())return;busy=true;$('qualityRun').disabled=true;
  const scope=$('qualityScope').value;
  const options={scope,raw_id:frozenSelected?.id,generation:scope==='selected'?frozen.generation:loaded.assessment.generation,method:$('qualityMethod').value};
  try{job=await api(cid,jobBase,options);pageOffset=0;await refreshJob();}catch(e){if(current())status.textContent='검산 요청 실패: '+e.message;}finally{busy=false;if(current())$('qualityRun').disabled=running(job);}
 }
 try{const evidence=await loadQualityEvidence(frozen);loaded=evidence.loaded;if(!current())return;status.textContent='저장된 계산 근거를 불러왔습니다. 결과 판단에서 요약을 읽고, 검산과 계산 근거에서 확인하세요.';
  renderQualityAssessment(panels.summary,loaded,frozen,frozenSelected);
  const methods=panels.summary.querySelector('.qualityMethodDetails');if(methods)panels.evidence.append(methods);
  const search=qualitySection(panels.evidence,'세대별 탐색 품질');noteText(search,'고유 배치는 새로 확인한 설치 형태 수입니다. 반복 평가는 같은 배치를 다시 계산한 횟수입니다. 비지배 수가 감소해도 더 좋은 해가 이전 해를 대체한 것일 수 있습니다.');evidenceTable(search,['세대','평가 수','모델 제약 통과','고유 배치','반복 평가','누적 비지배','목표 통과'],loaded.search.search_quality.map(r=>[r.generation,r.nfe,r.feasible,r.unique_decisions,r.repeated_evaluations,r.archive_size,r.target_count??'미설정']));qualityFold(search,'세대별 평가·중복·해 개수 원표 보기');
  const init=qualitySection(panels.evidence,'초기 배치를 어떻게 준비했나요?');const a=loaded.initialization||{};evidenceTable(init,['항목','저장 근거'],[['방법',a.method||'과거 정책'],['준비 평가',a.preparation_evaluations??'미기록'],['주입 후보',a.seed_count??'미기록'],['결과',a.outcome||a.status||'미기록']]);noteText(init,'준비 평가는 진화 탐색 평가 수와 별도입니다. MILP의 최적성 수치는 준비에 사용한 근사 문제의 근거입니다.');jsonDetails(init,'초기화 solver 원문',a,'qualityInitRaw');qualityFold(init,'초기화 방법·준비 계산 근거');
  const more=qualitySection(panels.evidence,'같은 조건의 반복 결과 연결');noteText(more,'한 번의 탐색 결과가 seed를 바꿔도 유지되는지 비교합니다. 반복은 추가 계산이며 이미 저장된 검산과 다릅니다.');dButton(more,'qualityValidation','반복 연구 · 저장된 지표와 검증 목록',()=>{qualityEpoch++;d.close();d.remove();openValidation(false,structuredClone(frozen.submitted_request));});
  const jobs=evidence.jobs;if(!current())return;
  renderQualityJobSummary(panels.checks,jobs,frozenSelected,loaded.assessment);
  const controls=qualitySection(panels.checks,'추가 검산 시작');selectControl(controls,'대상',[['selected','선택한 배치'],['archive','최종 비지배 해 전체'],['qualified','저장 정량 목표 통과 해 전체']],'archive',updateScope,'qualityScope');selectControl(controls,'검사',Object.entries(jobs.methods).map(([id,m])=>[id,m.label]),'local',updateScope,'qualityMethod');const scopeText=document.createElement('p');scopeText.id='qualityScopeMeaning';scopeText.className='qualityContext';controls.append(scopeText);function updateScope(){if(!$('qualityScope')||!$('qualityMethod'))return;const scope=$('qualityScope').value,m=$('qualityMethod').value;scopeText.textContent=`이번에 검사할 대상: ${scope==='selected'?`현재 지도 배치 ${frozenSelected?.id??'없음'} 1개`:scope==='qualified'?`최종 목표 통과 ${loaded.assessment.target_count??0}개`:`최종 비지배 전체 ${loaded.assessment.archive_unique_X}개`}. ${m==='exact'?'설치 가능한 전체 조합을 비교합니다.':m==='milp'?'한 번 삭제·추가·이동으로 만든 이웃 중 최선의 개선 후보를 MILP로 확인합니다.':'원래 수치를 다시 계산하고 센서를 한 번 삭제·추가·이동해 개선 가능성을 검사합니다.'} 목록에서 보던 필터는 검사 범위를 자동으로 바꾸지 않습니다.`;}$('qualityScope').querySelector('option[value=qualified]').disabled=loaded.assessment.goals===null;updateScope();noteText(controls,'평가·시간 제한 없이 선택 범위를 검사합니다. 중지 후 이어서 검사할 수 있습니다. 수량·설치 제약과 저장 목표는 유지합니다.');dButton(controls,'qualityRun','위 대상·방법으로 검산 시작',()=>compute());
  if(jobs.jobs.length)selectControl(controls,'저장된 전체 검산',[['','기록 선택'],...jobs.jobs.map(r=>[r.job_id,`${jobs.methods[r.method].label} · ${r.evaluated}회 · ${r.status}`])],'',async id=>{if(!id)return;job={job_id:id};pageOffset=0;refreshJob();},'qualityJobHistory');
  $('qualityScope').querySelector('option[value=selected]').disabled=!frozenSelected;
  if(loaded.history.length)selectControl(controls,'과거 제한 검산 기록',[['','과거 기록 선택'],...loaded.history.map(r=>[r.check_id,`${r.method} · ${r.scope} · ${r.status} · ${r.tested}회`])],'',async id=>{if(!id)return;clearTimeout(pollTimer);job=null;try{const value=await api(cid,'engine/runs/'+rid+'/quality-workflow/'+id);if(current()){result=value;renderResult();$('qualityRun').disabled=false;}}catch(e){status.textContent=e.message;}},'qualityHistory');
  const body=qualitySection(panels.checks,'검산 결과 · 개선 후보');body.id='qualityCheckResult';panels.checks.prepend(body);noteText(body,'위 저장 기록을 선택하면 검사한 범위와 개선 배치를 볼 수 있습니다. 새 검산은 아래에서 시작합니다.');const active=jobs.jobs.find(r=>r.job_id===selectedJobId)||jobs.jobs.find(r=>running(r))||jobs.jobs.find(r=>r.status==='COMPLETED'&&r.witness_count>0)||jobs.jobs.find(r=>r.generation===frozen.generation&&r.source_ids.includes(frozenSelected?.id));if(active){job=active;const history=$('qualityJobHistory');if(history)history.value=job.job_id;refreshJob();}
  savedFirst.remove();panels.checks.append(controls);qualityFold(controls,'새 검산의 대상·방법 설정');
  const checkAction=document.createElement('div');checkAction.className='qualityAction';const checkHint=document.createElement('span');checkHint.textContent='검산은 추가 계산입니다. 대상과 방법을 확인하고 시작하세요. 실행 중에는 진행률과 중지 버튼이 표시됩니다.';checkAction.append(checkHint);dButton(checkAction,'qualityPrepare','검산 설정 열기',()=>{const fold=controls.closest('details');fold.open=true;$('qualityRun').scrollIntoView({block:'center'});$('qualityRun').focus();});panels.checks.prepend(checkAction);$('qualityRun').classList.add('nextAction');if(destination)navigate(destination);
 }catch(e){if(current())status.textContent='품질 근거를 읽지 못했습니다: '+e.message;}
}
const qualityButton=document.createElement('button');qualityButton.id='qualityCenter';qualityButton.textContent='해품질·검산';qualityButton.onclick=()=>openQualityCenter();document.querySelector('.projectActions').append(qualityButton);
openPlacementAnalysis=openQualityCenter;
const qualityDock=renderDock;renderDock=function(){qualityDock();if(run&&mode==='result'){const b=document.createElement('button');b.id='openQualityFromResults';b.textContent='이 실행의 품질 판단·검산 근거';b.onclick=()=>openQualityCenter();$('dockBody').prepend(b);}};

function qualityValue(m,v){return v==null||!Number.isFinite(v)?'미기록':(v*(m.display_scale||1)).toFixed(4)+' '+m.unit;}
function qualityQualification(row,goals){return goals===null?'목표 미설정':row.qualified===true?'목표 통과':row.qualified===false?'목표 미달':'목표 판정 미기록';}
function qualityConstraintMeaning(row,tol){if(!row)return '미판정';if(!Array.isArray(row.G)||!row.G.every(Number.isFinite))return '제약 수치 오류·미기록: 충족 여부 미판정';return row.G.every(g=>g<=tol)?'모델 제약 충족':'모델 제약 미충족';}
const meaningInspector=renderInspector;
renderInspector=function(){meaningInspector();if(!configured()||mode!=='result'||!currentRow())return;const host=$('inspectorBody'),nodes=[...host.childNodes];host.replaceChildren();renderSelectedMeaning(host,currentRow(),true);const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='목적값·센서 기여도·저장 조건 자세히';details.className='qualityEvidenceFold';details.append(summary,...nodes);host.append(details);};
function renderLegacyQualityJourney(parent,loaded,frozen){
 const a=loaded.assessment,q=loaded.budget_quality||{},joint=q.joint_evidence,checks=q.checked_jobs||[];
 const s=qualitySection(parent,'이 해집합을 어디까지 믿고 사용할 수 있나요?');s.classList.add('qualityJourney');s.dataset.runId=a.run_id;
 const hasImprovement=joint?.runs_improving_any>0||checks.some(j=>j.improvement_count>0),whole=checks.find(j=>j.covers_entire_final);
 const verdict=document.createElement('p');verdict.className='qualityVerdict';verdict.textContent=!a.archive_unique_X?'최종 조건을 통과한 배치가 없습니다. 조건과 미달 원인을 먼저 확인하세요.':hasImprovement?'수량·설치 허용·모델 제약을 만족하는 해집합이지만, 같은 조건에서 더 좋은 배치를 실제로 찾았습니다. 개선 배치를 함께 비교해 선택하세요.':whole?'수량·설치 허용·모델 제약을 만족하며, 완료한 검산 범위에서는 어느 목적도 나빠지지 않고 하나 이상 개선하는 배치를 찾지 못했습니다. 아래 검사 범위까지 확인된 결과입니다.':'수량·설치 허용·모델 제약을 만족하는 관측 해집합입니다. 현재 탐색 성과는 아래에서 확인하고, 위치 변경 검산으로 남은 개선 가능성을 확인하세요.';s.append(verdict);
 const rule=a.inventory_rule;noteText(s,`실행 ${a.run_id.slice(0,8)} · ${a.generation}세대 · ${a.nfe.toLocaleString()}회 평가${rule?' · '+qualityInventoryMeaning(rule):''}. ${a.goals===null?'정량 목표 없음: 성능을 최대한 높이는 비교입니다.':'저장된 정량 목표를 별도로 적용합니다.'}`);
 if(a.goals!==null)noteText(s,`별도 정량 목표: ${goalSummary(a.goals,frozen.metadata)} · 최종 비지배 ${a.archive_unique_X}배치 중 ${a.target_count}배치 통과. 목표 미달 배치는 수량·설치 조건을 충족해도 목표 합격해가 아닙니다.`);
 noteText(s,'판단 대상은 최종 해집합 전체입니다. 선택한 한 배치의 목표 여유는 지도 옆 선택 설명에서 확인합니다.');
 const ledger=document.createElement('div');ledger.className='qualityAnswerLedger';s.append(ledger);
 evidenceTable(ledger,['사용자가 판단할 질문','이 실행에서 확인한 답','근거가 뜻하는 것'],[
 ['계산값을 다시 얻을 수 있나?',loaded.replay?.raw_replay==='PASS'?'같은 배치의 재평가가 저장 수치와 일치':'저장 재생 검사 결과 확인 필요','재현성 근거입니다. 더 좋은 배치가 없다는 뜻은 아닙니다.'],
 ['실제로 얼마나 탐색했나?',`${a.nfe.toLocaleString()}회 평가 · 서로 다른 배치 ${a.unique_all.toLocaleString()}개`,`같은 배치 재평가 ${a.repeated_evaluations.toLocaleString()}회는 새로운 위치가 아닙니다.`],
 ['다시 탐색해도 비슷한가?',joint?.repeat_count?`동일 조건 반복 ${joint.repeat_count}회 · 원래 해 전체 개선 ${joint.runs_improving_entire_original}회`:q.status==='DEFERRED'?'저장 반복 근거 미조회':'연결된 동일 조건 반복 없음','관측된 반복 안정성을 봅니다. 최적일 확률로 환산하지 않습니다.'],
 ['직접 바꾸면 더 좋아지는가?',checks.length?`완료 검산 ${checks.length}건 · ${checks.some(j=>j.improvement_count>0)?'개선 배치 발견':'검사 범위 내 개선 없음'}`:'연결된 완료 검산 없음','실제 변경 후보와 원해를 비교한 근거입니다. 아래에서 검사 범위를 확인하세요.']]);
 const questions=qualitySection(s,'1. 계산 결과와 탐색 성과');
 noteText(questions,`수량·설치 허용·모델 제약을 통과한 고유 배치 ${a.unique_feasible.toLocaleString()}개를 관측했고, 그중 최종 비지배 배치는 ${a.archive_unique_X}개입니다. 이는 관측한 배치끼리 비교해 모든 목적에서 같거나 좋고 하나 이상 더 좋은 다른 관측 배치가 없는 해입니다.`);
 noteText(questions,`목적값 조합은 ${a.archive_unique_F}종입니다. ${a.archive_unique_X>a.archive_unique_F?'위치가 달라도 같은 성능이 나올 수 있으므로 배치 수와 성능 종류를 나누어 셉니다.':'해의 개수만으로 좋은 탐색인지 판단하지 않습니다.'} 센서 중심이 평가영역 밖이어도 설치 허용 조건을 만족하면 유효하며, 평가영역의 성능으로 비교합니다.`);
 noteText(questions,loaded.replay?.raw_replay==='PASS'?`원시 재생 검사: 같은 배치를 다시 평가한 수치가 저장값과 일치했습니다. 이는 계산 재현의 근거이며 성능 우수성 검사는 아래와 같습니다.`:'원시 재생 결과가 확인되지 않았습니다. 아래 전체 검산은 대상 원해의 재평가부터 수행합니다.');
 evidenceTable(questions,['성능 목적','초기 관측 최선','최종 해집합의 성능 범위'],a.metrics.map(x=>[x.metric.name,qualityValue(x.metric,x.initial_best),qualityValue(x.metric,x.archive_min)+' ~ '+qualityValue(x.metric,x.archive_max)]));
 noteText(questions,'이 표는 목적별 범위입니다. 여러 목적의 최댓값을 한 배치가 동시에 달성한다는 뜻은 아닙니다. 아래 개선 비교는 실제 한 배치의 성능입니다.');
 const repeated=qualitySection(s,'2. 같은 계산량으로 다시 탐색했을 때');repeated.dataset.evidence='repeat';
 if(joint?.repeat_count&&joint.original_count){noteText(repeated,`원래 실행을 제외한 동일 조건 반복 ${joint.repeat_count}회 중 ${joint.runs_attaining_entire_original}회에서 원래 최종 배치 모두와 같거나 더 좋은 성능을 달성했습니다. ${joint.runs_improving_entire_original}회에서는 원래 최종 배치 모두보다 엄격히 좋은 배치를 찾았습니다.`);noteText(repeated,'각 원래 배치에 대해 모든 목적이 나빠지지 않는 실제 배치가 있는지 검사했습니다. 반복마다 서로 다른 배치가 대응할 수 있습니다. 이 빈도는 이번 반복의 관측 결과이며 전역 최적 확률이 아닙니다.');
 const available=joint.runs.filter(r=>r.witnesses.length),options=available.map((r,i)=>[r.run_id,`반복 ${joint.runs.indexOf(r)+1} · 개선 대상 ${r.improved_ids.length}배치`]);
 if(options.length){const box=document.createElement('div');selectControl(repeated,'실제 개선 사례',options,options[0][0],show,'qualityRepeatWitness');repeated.append(box);function show(id){box.replaceChildren();const r=available.find(x=>x.run_id===id),w=r.witnesses[0],original=joint.original_layouts.find(x=>x.id===w.original_id);renderQualityImprovement(box,frozen,original,w.candidate,'반복 탐색');noteText(box,`출처: 원래 ${a.run_id.slice(0,8)} / 행 ${original.id} → 반복 ${r.run_id.slice(0,8)} / 행 ${w.candidate.id}. 동일 후보 순서·평가기·설정·평가 횟수를 대조한 반복입니다.`);dButton(box,'qualityJointMaps','원래 배치와 이 반복 배치 지도 비교',()=>{box.querySelector('.qualityCompareMaps')?.remove();const maps=document.createElement('div');maps.className='qualityCompareMaps';for(const [title,row] of [['원래 배치',original],['반복에서 찾은 개선 배치',w.candidate]]){const panel=document.createElement('div');noteText(panel,title+' · 행 '+row.id);panel.insertAdjacentHTML('beforeend',qualityGeometryMap(frozen.problem,row));maps.append(panel);}box.append(maps);});}show(options[0][0]);}
 }else noteText(repeated,q.status==='DEFERRED'?'저장 반복 근거는 아직 조회하지 않았습니다. 탐색 근거 별도 조회에서 확인하세요.':'이 실행에 결속된 동일 조건 반복 비교가 아직 없습니다. 현재 실행 내부의 개선과 아래 검산은 판단할 수 있습니다. 반복 변동까지 확인하려면 저장 조건으로 반복 계산한 뒤 결과를 연결하세요.');
 const local=qualitySection(s,'3. 센서 위치를 바꿔 더 좋아질 수 있나요?');
 if(checks.length){for(const j of checks){noteText(local,`${j.covers_entire_final?'최종 비지배 배치 전체':'최종 해집합 일부 '+j.final_source_count+'배치'}에 대해 ${j.evaluated.toLocaleString()}회 검사 · 원래 배치 재평가 ${j.replayed}회 · 개선 발견 평가행 ${j.improvement_count}개 · 서로 다른 배치 ${j.improvement_unique_X??'미집계'}개 · 개선된 원해 ${j.improved_source_count??'미집계'}개 · 목표 통과 고유 배치 ${a.goals===null?'목표 미설정':j.qualified_improvement_unique_X??'판정 미기록'}. ${j.method==='exact'?'전체 설치 조합':j.method==='milp'?'한 번의 변경으로 만든 전체 이웃의 MILP 선택':'센서 한 번 삭제·추가·이동'} 검사입니다.`);dButton(local,'qualityJourneyCheck_'+j.job_id,'검산에서 찾은 배치·성능 변화 보기',()=>openQualityCenter(j.job_id));}}else noteText(local,'최종 해집합에 연결된 완료 검산이 없습니다. 아래 검산을 시작하면 원래 배치를 재평가한 뒤, 센서 위치를 하나씩 바꾸어 모든 목적이 나빠지지 않는 개선 배치를 찾습니다.');
 noteText(local,'전량 사용 조건에서는 수량을 유지하는 위치 이동이 유효한 개선 대안입니다. 삭제·추가로 수량을 어긴 결과는 개선해로 채택하지 않습니다. 검산 개선 배치는 원시 탐색 결과와 구분해 보존합니다.');
 qualityFold(questions,'근거 1 · 관측 성능 범위와 계산 재현');qualityFold(repeated,'근거 2 · 반복 탐색의 실제 비교');qualityFold(local,'근거 3 · 센서 변경 검산과 개선 배치');
 return s;
}
function renderQualityAssessment(parent,loaded,frozen,row){
 const a=loaded.assessment;if(!a||!frozen.metadata){noteText(parent,'이 저장 형식의 공통 품질 해석 자료가 없습니다. 아래 원시 근거와 해당 계약의 검산 기록을 확인하세요.');return;}
 const journey=renderQualityJourney(parent,loaded,frozen);
 const details=document.createElement('details'),title=document.createElement('summary');title.textContent='계산 방법·탐색 곡선·선택 배치 수치·논문 근거 자세히 보기';details.className='qualityMethodDetails';details.append(title);parent.append(details);parent=details;
 renderBudgetQuality(parent,loaded.budget_quality,frozen);
 const budget=parent.querySelector('.budgetQuality');if(budget)budget.dataset.evidence='search';
 const legacy=renderLegacyQualityJourney(parent,loaded,frozen);qualityFold(legacy,'반복·검산 상세 사례와 기존 설명');
 renderQualityProvenance(parent,loaded,frozen);
 const s=qualitySection(parent,'이 계산 결과를 어떻게 판단하나요?');s.classList.add('qualityAssessment');s.dataset.runId=a.run_id;
 noteText(s,`저장 실행 ${a.run_id.slice(0,8)} · 최종 ${a.generation}세대 · ${a.nfe.toLocaleString()}회 평가. 아래 집합 통계는 화면 필터와 무관한 최종 저장 실행 기준입니다. 선택 행 ${row?.id??'없음'} · 화면 ${frozen.generation}세대.`);
 const rule=a.inventory_rule;noteText(s,rule?`장비 조건: ${qualityInventoryMeaning(rule)}. 평가영역 밖 중심도 저장된 설치 허용 조건을 만족하면 유효합니다.`:'장비 조건은 저장 설정을 따릅니다.');
 const audit=row?.installation_audit;
 evidenceTable(s,['판단 항목','계산 근거','해석'],[
  ['수량·설치 허용',audit?`선택 ${audit.selected_sensor_count.join(' / ')}대 · 위반 ${audit.hard_constraint_violation}`:'선택 배치 검사 미기록',audit?.hard_pass===true?'저장된 수량·설치 조건 충족':audit?'위반 배치 · 품질 비교 전에 조건 수정 필요':'미판정'],
  ['모델 제약',row&&Array.isArray(row.G)&&row.G.every(Number.isFinite)?`검사 조건 ${row.G.length}개 · 위반 ${row.G.filter(g=>g>frozen.archive_policy.tolerance).length}개`:row?'제약 수치 확인 필요':'선택 없음',qualityConstraintMeaning(row,frozen.archive_policy.tolerance)],
  ['선택 배치의 위치',`선택 세대 ${frozen.generation} · 원시 행 ${row?.id??'없음'}`,!row?'배치 미선택':a.archive_ids.includes(row.id)?'최종 저장 비지배 집합에 포함됩니다.':'최종 저장 비지배 집합의 원시 행이 아닌 비교 배치입니다.'],
  ['정량 목표',a.goals===null?'미설정':goalSummary(a.goals,frozen.metadata),a.goals===null?'절대 성능 합격/불합격 기준 없음. 성능값과 개선 여지로 비교합니다.':`${a.target_count}개 최종 비지배 배치가 저장 목표 통과`],
  ['관측된 해집합',`서로 다른 배치 ${a.archive_unique_X}개 · 목적벡터 ${a.archive_unique_F}종`,a.archive_unique_F===1&&a.archive_unique_X>1?'배치는 다르지만 목적값이 같습니다. 성능 절충 다양성과 위치 다양성을 구분하세요.':'관측한 비지배 해입니다. 미탐색 배치에 대한 최적성 증명은 아닙니다.'],
  ['원시 재생',loaded.replay?.raw_replay||'미실행','같은 입력의 수치 재현 여부입니다. 성능 우수 또는 전역 최적 판정이 아닙니다.']
 ]);
 const perf=qualitySection(parent,'선택 배치의 성능 · 초기 탐색과 비교');
 noteText(perf,'최선은 이 실행에서 관측한 값입니다. 초기 최선과 현재 최선은 목적별로 서로 다른 배치일 수 있습니다. 표시 단위를 맞춰 비교하며 임의의 종합 점수는 만들지 않습니다.');
 evidenceTable(perf,['목적','선택 값','초기 관측 최선','전체 관측 최선','선택 값의 최선 대비 부족량','해석'],a.metrics.map(x=>{const m=x.metric,v=row?.named_metrics?.[m.id],gap=v==null||x.observed_best==null?null:(m.direction==='maximize'?x.observed_best-v:v-x.observed_best);return[m.name+' · '+(m.direction==='maximize'?'높을수록 좋음':'낮을수록 좋음'),qualityValue(m,v),qualityValue(m,x.initial_best),qualityValue(m,x.observed_best),qualityValue({...m,unit:m.unit==='%'?'%p':m.unit},gap),gap==null?'유효 관측 없음':gap < -1e-12?'선택값이 제약 통과 관측 최선보다 좋습니다. 선택 배치의 제약 충족 여부가 달라 같은 기준의 우수해로 판단할 수 없습니다.':x.constant_observed?'관측값이 일정해 이 실행의 배치를 구분하지 못합니다.':Math.abs(gap)<=1e-12?'이 목적에서 관측 최선과 같습니다.':'이 목적에서 더 좋은 관측값이 있습니다. 다른 목적의 손실도 함께 확인하세요.'];}));
 if(row&&frozen.metadata.coverage_metrics.length){const g=qualitySection(parent,'평가영역 커버율 · 저장 목표와 차이');evidenceTable(g,['영역 지표','선택 값','저장 목표','여유 / 부족'],frozen.metadata.coverage_metrics.map(m=>{const v=row.coverage_metrics?.[m.id],t=a.goals?.[m.id];return[m.name,qualityValue(m,v),t==null?'미설정':t+' %',t==null?'목표 판정 없음':v==null?'미기록':(v-t).toFixed(4)+' %p'];}));}
 const search=qualitySection(parent,'탐색으로 얼마나 확인했나요?');
 const repeat=a.nfe?100*a.repeated_evaluations/a.nfe:0;
 noteText(search,`평가 ${a.nfe.toLocaleString()}회 중 고유 배치 ${a.unique_all.toLocaleString()}개, 반복 평가 ${a.repeated_evaluations.toLocaleString()}회 (${repeat.toFixed(1)}%). 같은 배치의 재평가는 새로운 위치를 탐색한 횟수가 아닙니다.`);
 noteText(search,`수량·설치 위반 ${a.hard_invalid}행, 모델 제약 미충족 ${a.model_invalid}행. 두 조건을 모두 통과한 서로 다른 관측 배치는 ${a.unique_feasible.toLocaleString()}개입니다. 두 위반 수는 겹칠 수 있습니다.`);
 noteText(search,a.hamming.pair_count?`최종 비지배 배치 간 Hamming 거리: 최소 ${a.hamming.minimum}, 평균 ${a.hamming.mean.toFixed(2)}, 최대 ${a.hamming.maximum}. 센서 한 대 위치 이동은 보통 2비트 차이입니다. 작은 거리는 유사한 배치라는 뜻이며 성능 불량 판정은 아닙니다.`:'비교할 비지배 배치 쌍이 없어 Hamming 다양성은 판정하지 않습니다.');
 const remain=qualitySection(parent,'판단의 범위와 계산 근거');noteText(remain,'위 개선 곡선은 사용한 탐색 예산의 효과를, 반복 실행은 관측 변동을, 위치 변경 검산은 직접 확인한 개선 가능성을 보여줍니다. 서로 다른 질문의 근거이므로 하나의 신뢰 확률로 합치지 않습니다.');
 noteText(remain,`근거: 설정 ${loaded.parent.config_sha256.slice(0,12)} · 평가기 ${loaded.parent.evaluator_sha256.slice(0,12)} · 원시 ${loaded.parent.raw_sha256.slice(0,12)}. 원시 결과는 변경하지 않습니다.`);
}
function renderBudgetQuality(parent,q,frozen=null){
 if(!q)return;
 const s=qualitySection(parent,'이 탐색 예산으로 얼마나 좋아졌나요?');s.classList.add('budgetQuality');
 for(const e of q.eligibility||[])if(e.invalid_values>0)noteText(s,`실행 ${e.run_id.slice(0,8)}: 수치 오류·미기록 ${e.invalid_values}개는 품질 계산에서 제외했습니다. 유효한 제약 통과 평가 ${e.accepted}개로 계산하며, 제외된 값을 성능 0으로 바꾸지 않습니다.`);
 if(q.status!=='OBSERVED'){noteText(s,q.reason);if(q.status==='DEFERRED'&&frozen)dButton(s,'qualityLoadCurve','세대별 HV·IGD+ 근거 별도로 조회',async()=>{const b=s.querySelector('button');b.disabled=true;noteText(s,'세대별 지표 계산 중입니다. 저장 검산과 지도는 계속 사용할 수 있습니다.');try{const value=await api(frozen.experiment_contract_id,'engine/runs/'+frozen.run_id+'/quality-workflow');if(!s.isConnected)return;if(value.parent.run_id!==frozen.run_id||value.parent.config_sha256!==frozen.config_sha256||value.parent.evaluator_sha256!==frozen.evaluator_sha256)throw Error('저장 실행 결속 불일치');s.replaceChildren();renderQualityAssessment(s,value,frozen,null);}catch(e){noteText(s,'지표 조회 실패: '+e.message);b.disabled=false;}});return;}
 const t=q.runs[0],first=t.trace[0],last=t.final;
 if(!last)return;
 noteText(s,`평가 ${first.nfe.toLocaleString()} → ${last.nfe.toLocaleString()}회 동안, 최종 관측 성능을 기준으로 확보한 성능 공간이 ${first.reference_percent?.toFixed(2)??'—'}% → ${last.reference_percent?.toFixed(2)??'—'}%로 변화했습니다.`);
 noteText(s,`마지막 구간 ${t.tail_start.nfe.toLocaleString()}–${last.nfe.toLocaleString()}회에서 추가 이득 ${t.last_fifth_gain_pp?.toFixed(3)??'—'}%p. 이미 사용한 후반 예산의 효과이며, 앞으로 예산을 늘렸을 때의 개선량을 예측한 값은 아닙니다.`);
 noteText(s,'아래 100%는 이번 실행의 최종 관측값입니다. 최적해를 찾을 확률이나 실제 지도 커버율 100%를 뜻하지 않습니다.');
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 800 250');svg.setAttribute('role','img');svg.setAttribute('aria-label','평가 횟수에 따른 최종 관측 기준 성능 공간 확보율');svg.classList.add('qualityCurve');
 function node(tag,attrs,text){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text)n.textContent=text;svg.append(n);return n;}
 for(const y of [0,25,50,75,100]){const py=210-y*1.7;node('line',{x1:66,y1:py,x2:775,y2:py,stroke:'#d4e2e9'});node('text',{x:56,y:py+4,'text-anchor':'end',fill:'#284e61','font-size':13},y+'%');}
 node('polyline',{points:t.trace.filter(x=>x.reference_percent!==null).map(x=>`${66+709*x.nfe/last.nfe},${210-1.7*x.reference_percent}`).join(' '),fill:'none',stroke:'#007f9c','stroke-width':3});
 node('text',{x:66,y:235,fill:'#284e61','font-size':13},'0');node('text',{x:775,y:235,'text-anchor':'end',fill:'#284e61','font-size':13},last.nfe.toLocaleString()+'회 평가');s.append(svg);
 const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent='계산 방법·세대별 수치·논문 보기';detail.append(summary);s.append(detail);
 noteText(detail,'성능 공간은 HV(높을수록 좋음)입니다. 모든 세대에 같은 관측 min/max와 참조점을 사용합니다. 평균 부족 거리는 IGD+(낮을수록 좋음)이며 최종 관측 집합에 대한 과거의 거리입니다. 둘 다 이 보고서 안의 비교 지표입니다.');
 if(q.comparison_basis)noteText(detail,`이 보고서의 고정 비교 기준 ${q.comparison_basis.sha256.slice(0,12)}: 모든 세대에 같은 척도와 최종 관측 집합을 사용합니다. 반복 실행을 추가하면 새 기준이 만들어지므로 이전 보고서의 점수와 직접 비교하지 않습니다. 대표 100개가 놓친 성능을 계산하는 기준과도 별개입니다.`);
 const objectiveName=i=>{const id=frozen?.registry?.objective_order[i];return frozen?.metadata?.metrics?.find(m=>m.id===id)?.name||id||('목적 '+(i+1));};
 noteText(detail,`변화가 없어 지표에서 제외한 목적: ${q.normalization.constant_indices.map(objectiveName).join(', ')||'없음'}. 관측한 값이 일정하다는 뜻이며 모든 가능한 배치의 상수임을 증명한 것은 아닙니다. 원래 목적값과 최적화 설정은 그대로 보존합니다.`);
 evidenceTable(detail,['세대','평가 횟수','관측 기준 대비 성능 공간','평균 부족 거리'],t.trace.map(x=>[x.generation,x.nfe,(x.reference_percent?.toFixed(3)??'—')+'%',x.igd_plus?.toFixed(6)??'제약 통과 해 없음']));
 for(const ref of q.sources){const a=document.createElement('a');a.href=ref.url;a.target='_blank';a.rel='noopener';a.textContent=ref.label;const p=document.createElement('p');p.append(a);detail.append(p);}
 if(q.repeat_study){
  const st=q.repeat_study,r=st.report,sec=qualitySection(parent,'같은 조건으로 다시 계산해도 비슷한가요?');sec.classList.add('qualityRepeats');
  if(st.recalculated_from_saved_raw)noteText(sec,'기존 반복 실행의 원시 자료를 현재 품질 판정으로 다시 계산했습니다. 과거 보고서는 보존하며 새 최적화 실행을 수행한 것은 아닙니다.');
  if(r.status!=='OBSERVED'){noteText(sec,r.reason||'반복 비교의 품질 수치를 계산할 수 없습니다.');return;}
  noteText(sec,`기존 실행과 새 seed ${st.independent_repeat_count}회. 센서 수량·후보지·목적·초기화·평가 예산은 같고 난수만 바꿨습니다. 아래 모든 실행을 같은 척도와 관측 합집합 기준으로 비교합니다.`);
  const vals=r.runs.map(x=>x.final?.reference_percent).filter(x=>x!=null),lo=Math.min(...vals),hi=Math.max(...vals);noteText(sec,vals.length?`관측 성능 공간 범위 ${lo.toFixed(3)}–${hi.toFixed(3)}%. 폭 ${(hi-lo).toFixed(3)}%p가 이번 반복에서 나타난 탐색 결과의 변동입니다.`:'비교 가능한 최종 참조 해가 없습니다. 제약 통과 상태를 확인하세요.');
  evidenceTable(sec,['실행','같은 예산의 성능 공간 확보율','평균 부족 거리'],r.runs.map((x,i)=>[i===0?'원래 실행':`반복 ${i}`,x.final?.reference_percent==null?'참조 해 없음':x.final.reference_percent.toFixed(3)+'%',x.final?.igd_plus?.toFixed(6)??'—']));
  sec.querySelectorAll('tbody tr').forEach((tr,i)=>{const bar=document.createElement('div');bar.className='qualityBar';const fill=document.createElement('span');fill.style.width=Math.max(0,Math.min(100,r.runs[i].final?.reference_percent??0))+'%';bar.append(fill);const label=document.createElement('strong');label.textContent=tr.cells[1].textContent;bar.append(label);tr.cells[1].replaceChildren(bar);});
  const counts=r.attainment.reference_point_counts,hist=new Map();counts.forEach(n=>hist.set(n,(hist.get(n)||0)+1));noteText(sec,`관측 기준 성능 ${counts.length}종의 반복 달성 횟수입니다. 같은 성능 또는 모든 목적에서 더 좋은 성능이 나온 실행을 셉니다. 이 비교 기준 자체에 실행들이 포함되어 있으므로 독립 시험의 합격 확률은 아닙니다.`);
  evidenceTable(sec,['비교한 전체 실행 수','같거나 더 좋게 달성한 실행 수','그 빈도로 달성된 기준 성능 수'],[...hist.entries()].sort((a,b)=>b[0]-a[0]).map(([n,size])=>[r.attainment.run_count+'회',n+'회',size+'종']));
  if(r.performance?.length){noteText(sec,'실제 성능 단위로 비교: 각 실행의 최종 비지배 배치들이 가진 범위입니다. 목적별 최댓값을 한 배치가 동시에 달성한다는 뜻은 아닙니다.');evidenceTable(sec,['실행',...r.performance[0].metrics.map(x=>x.metric.name)],r.performance.map((x,i)=>[i===0?'원래 실행':`반복 ${i}`,...x.metrics.map(m=>qualityValue(m.metric,m.minimum)+' ~ '+qualityValue(m.metric,m.maximum))]));}
  if(frozen){const links=document.createElement('p');r.runs.forEach((x,i)=>{const a=document.createElement('a');a.href='/live.html?contract='+encodeURIComponent(frozen.experiment_contract_id)+'&run='+x.run_id;a.target='_blank';a.rel='noopener';a.textContent=(i===0?'원래 실행':`반복 ${i}`)+' 배치 지도 ↗';a.style.marginRight='16px';links.append(a);});sec.append(links);}
  noteText(sec,'그래프의 100%는 관측 합집합과 같은 성능 공간을 확보했다는 뜻입니다. 전역 최적성 대신, 실제 반복 변동과 아래 위치 변경 검산의 개선량을 함께 판단하세요.');
 }
}
function renderQualityJobSummary(parent,jobs,row,assessment){
 const s=qualitySection(parent,'검산으로 확인된 개선 가능성');s.classList.add('qualityJobSummary');
 const list=jobs.jobs||[];if(!list.length)noteText(s,'저장된 공통 검산이 없습니다. 원시 재생 PASS만으로 센서 이동·대체 후 개선 가능성을 판단할 수 없습니다. 아래 검산 실행을 사용하세요.');
 noteText(s,`저장 검사 ${list.length}건입니다. 아래 기록은 검사한 대상이 서로 다를 수 있으므로 개선 개수를 합쳐 최종 해 수로 읽지 마세요.`);
 const detail=document.createElement('details'),title=document.createElement('summary');title.textContent='검사별 범위·진행·판정 표';detail.append(title);s.append(detail);
 evidenceTable(detail,['검사·저장 세대','검사 범위','진행','개선 발견 평가행','판단'],list.map(j=>{const complete=j.status==='COMPLETED'&&j.scope_complete===true;const applies=row&&j.source_ids.includes(row.id);return[jobs.methods[j.method]?.label||j.method,`${j.generation}세대 · ${j.source_ids.length}배치${applies?' · 선택 행 포함':' · 선택 행과 별도'}`,`${j.status} · ${j.evaluated}/${j.total??'미확정'}`,j.witness_count,j.status==='ERROR'?'오류로 판정 불가':j.witness_count>0?'검사 대상에서 개선 발견':complete?'이 검사 범위에서 개선 없음':'미완료 · 진행 결과'];}));
 noteText(s,'삭제·추가·이동은 한 번의 변경 범위, MILP·ε는 검사 이웃 내 선택, 전체 조합은 명시한 설치 공간 검사입니다. 보유 수량 전부 사용에서는 삭제·추가가 수량 조건을 위반할 수 있으므로 대안 해로 채택하지 않습니다.');
 for(const j of list)dButton(s,'qualitySaved_'+j.job_id,`${jobs.methods[j.method]?.label||j.method} · 개선 발견 ${j.witness_count}행 · 결과·지도 열기`,()=>openQualityCenter(j.job_id));
 return s;
}

const qualityEvidenceCache=new Map();
function qualityEvidenceKey(f){return [f.experiment_contract_id,f.run_id,f.config_sha256,f.evaluator_sha256,f.state,f.nfe].join(':');}
async function loadQualityEvidence(f,force=false){
 const key=qualityEvidenceKey(f);if(!force&&qualityEvidenceCache.has(key))return qualityEvidenceCache.get(key);
 const request=Promise.all([api(f.experiment_contract_id,'engine/runs/'+f.run_id+'/quality-workflow?view=summary'),api(f.experiment_contract_id,'engine/runs/'+f.run_id+'/quality-jobs')]).then(([loaded,jobs])=>{if(loaded.parent.run_id!==f.run_id||loaded.parent.config_sha256!==f.config_sha256||loaded.parent.evaluator_sha256!==f.evaluator_sha256)throw Error('품질 근거와 저장 실행의 결속 불일치');return {loaded,jobs};}).catch(e=>{qualityEvidenceCache.delete(key);throw e;});
 qualityEvidenceCache.set(key,request);if(qualityEvidenceCache.size>8)qualityEvidenceCache.delete(qualityEvidenceCache.keys().next().value);return request;
}
const qualityExplainedDock=renderDock;
renderDock=function(){
 qualityExplainedDock();if(!configured()||mode!=='result'||!['quality','evidence'].includes(dock))return;
 const body=$('dockBody'),basic=$('basicDiagnostics'),frozen=structuredClone(run),row=structuredClone(currentRow());body.replaceChildren();
 dButton(body,'openQualityFromResults','품질 판단 → 검산 → 계산 근거 열기',()=>openQualityCenter());
 const actions=document.createElement('details'),actionTitle=document.createElement('summary');actionTitle.textContent='근거 새로 읽기·반복 연구 연결';actions.append(actionTitle);body.append(actions);
 dButton(body,'refreshQualityAssessment','검산 결과 새로 읽기',()=>{qualityEvidenceCache.delete(qualityEvidenceKey(run));renderDock();});
 dButton(body,'openQualityValidation','이 저장 조건으로 반복 계산·결과 열기',()=>openValidation(false,structuredClone(run.submitted_request)));
 dButton(body,'compareQualityRepeats','완료한 반복 결과를 품질표로 비교',()=>openQualityStudyPicker(structuredClone(run)));
 for(const id of ['refreshQualityAssessment','openQualityValidation','compareQualityRepeats'])actions.append($(id));
 const host=document.createElement('div');host.id='qualityAssessmentHost';body.append(host);noteText(host,'저장 조건과 해품질 근거를 계산해 읽는 중…');
 if(basic){const details=document.createElement('details'),title=document.createElement('summary');title.textContent='목적함수 분산·상관·센서 기여도 상세 진단';details.append(title,basic);body.append(details);}
 if(!terminal.has(run.state)){host.replaceChildren();noteText(host,'계산 저장 후 최종 해품질을 판정합니다. 계산 중 배치는 지도 탐색에서 확인하세요.');return;}
 loadQualityEvidence(frozen).then(({loaded,jobs})=>{if(!host.isConnected||run?.run_id!==frozen.run_id||run?.config_sha256!==frozen.config_sha256)return;host.replaceChildren();renderQualityAssessment(host,loaded,frozen,row);qualityFold(renderQualityJobSummary(host,jobs,row,loaded.assessment),'저장 검산별 범위·결과 바로가기');}).catch(e=>{if(host.isConnected){host.replaceChildren();noteText(host,'해품질 근거 조회 실패: '+e.message+' · 미검사를 통과로 표시하지 않습니다.');}});
};
document.querySelector('[data-dock="evidence"]').addEventListener('click',()=>{if(configured()&&mode==='result')workbench?.setTask('solutions');});

function renderQualityImprovement(parent,frozen,original,candidate,origin='검산'){
 const section=qualitySection(parent,'개선 배치의 실제 성능 변화');
 if(original){const metrics=frozen.metadata.metrics.filter(m=>m.id!=='cost'&&frozen.registry.objective_order.includes(m.id));if(metrics.length&&metrics.every(m=>Number.isFinite(original.named_metrics?.[m.id])&&candidate.named_metrics?.[m.id]===original.named_metrics[m.id])&&candidate.cost<original.cost)noteText(section,'선택한 모든 성능 목적을 그대로 유지하면서 비용이 '+original.cost+' → '+candidate.cost+'로 '+(original.cost-candidate.cost)+' 줄었습니다. 설치 허용·목표 통과만으로 불필요한 센서가 없다고 보장되지는 않습니다.');}
 noteText(section,`원시 행 ${original?.id??candidate.source_id??'근거 참조'} → ${origin} 배치. 센서 ${candidate.sensor_counts?.join(' / ')??'저장 조건'}대 · 비용 ${candidate.cost}. ${origin==='검산'?'원시 optimizer 배치와 분리된 검산 결과입니다.':'같은 조건으로 별도 실행한 탐색 결과입니다.'}`);
 evidenceTable(section,['지표','원래 배치',origin+' 배치','좋아진 양'],frozen.metadata.metrics.filter(m=>frozen.registry.objective_order.includes(m.id)||m.id==='cost').map(m=>{const a=original?.named_metrics?.[m.id],b=candidate.named_metrics?.[m.id];return [m.name,qualityValue(m,a),qualityValue(m,b),qualityValue({...m,unit:m.unit==='%'?'%p':m.unit},a==null||b==null?null:(m.direction==='maximize'?b-a:a-b))];}));
}
async function openQualityStudyPicker(frozen){
 const d=vDialog('같은 조건의 반복 결과 비교'),status=document.createElement('p');d.append(status);
 noteText(d,'선택한 저장 실행과 같은 조건·평가 횟수로 완료한 반복 연구를 선택하세요. 센서·후보·목적·제약·알고리즘이 다르면 비교를 거부합니다. 새 최적화 없이 저장된 값을 계산합니다.');
 const select=document.createElement('select');select.id='qualityStudySelect';select.setAttribute('aria-label','완료한 반복 연구');d.append(select);
 try{const list=await api(frozen.experiment_contract_id,'engine/validations');if(!d.isConnected)return;const completed=list.validations.filter(x=>x.state==='completed');option(select,completed.map(x=>[x.validation_id,`${new Date(x.created_at*1000).toLocaleString('ko-KR')} · ${x.total_cells}회 · 평가 ${x.expected_nfe.toLocaleString()}회`]));if(!completed.length){status.textContent='아직 완료한 반복 연구가 없습니다. 저장 조건으로 반복 계산을 먼저 실행하세요.';return;}
 const compute=dButton(d,'qualityStudyCompute','선택 결과 계산·품질표에 연결',async()=>{compute.disabled=true;try{status.textContent='동일 조건과 원시 파일을 대조하고 품질을 계산하는 중…';const g=await api(frozen.experiment_contract_id,'engine/validations/'+select.value);if(g.cells.some(x=>x.state!=='completed'))throw Error('선택한 반복 연구가 완료되지 않았습니다.');const ids=g.cells.map(x=>x.attempts.at(-1).run_id).filter(id=>id!==frozen.run_id),path='engine/runs/'+frozen.run_id+'/quality-research';let job=await api(frozen.experiment_contract_id,path,{run_ids:ids});while(job.state==='running'){if(!d.isConnected)return;status.textContent=`${job.phase} · 원시 ${job.loaded_runs}/${job.total_runs}개. 창을 닫아도 저장 비교는 계속됩니다.`;await new Promise(resolve=>setTimeout(resolve,1500));job=await api(frozen.experiment_contract_id,path+'/'+job.comparison_id);}if(job.state!=='completed')throw Error(job.error||'비교가 완료되지 않았습니다.');qualityEvidenceCache.delete(qualityEvidenceKey(frozen));status.textContent='비교 저장 완료. 품질 화면에 반영했습니다.';if(d.isConnected&&run?.run_id===frozen.run_id){d.close();d.remove();renderDock();}}catch(e){if(d.isConnected)status.textContent='비교하지 못했습니다: '+e.message;}finally{compute.disabled=false;}});
 }catch(e){status.textContent='비교할 연구를 읽지 못했습니다: '+e.message;}
}
