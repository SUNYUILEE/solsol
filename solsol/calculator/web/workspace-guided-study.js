'use strict';
function guidedArmLabel(c){if(c.label.startsWith('비용 대조 V1|'))return '예산 '+c.request.resource_contract.budget.limit+' · 비용 목적 '+(c.request.objective_ids.includes('cost')?'유지':'제외');return c.label.startsWith('비용 연구 B|')?'B · 예산 '+c.request.resource_contract.budget.limit:'A · 성능과 비용';}
// Shared by all three contracts. Validation plans and quality jobs are the truth;
// localStorage holds only an unresolved submission receipt, never completion.
const openAdvancedResourceStudy=openResourceStudy;
openResourceStudy=openGuidedCostBudget;
async function openGuidedCostBudget(source=null){
 const old=$('guidedStudyDialog');if(old){old.focus();return;}
 const cid=draft.sensor,d=vDialog('비용과 성능 · 순서대로 연구하기');d.id='guidedStudyDialog';
 d.style.width='min(1200px, 94vw)';
 const style=document.createElement('style');style.textContent='#guidedStudyDialog table{table-layout:fixed;width:100%}#guidedStudyDialog th,#guidedStudyDialog td{white-space:normal!important;overflow-wrap:anywhere;line-height:1.6;padding:10px}#guidedStudyDialog .qualityCompareMaps{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:16px}#guidedStudyDialog .qualityCompareMaps svg{width:100%;height:auto;max-height:520px}';d.append(style);
 const saved=source==='draft'?null:run?.experiment_contract_id===cid?run:null;
 const preparing=document.createElement('p');preparing.setAttribute('role','status');preparing.textContent=saved?'저장된 조건을 불러오는 중…':'편집 조건을 준비하는 중…';d.append(preparing);
 let base;
 try{base=structuredClone(saved?(await api(cid,'engine/runs/'+saved.run_id+'/copy')).request:requestConfiguration());}
 catch(error){d.close();d.remove();throw error;}
 if(!d.isConnected||draft.sensor!==cid){d.close();d.remove();return;}
 preparing.remove();
 let a=null,b=null,preview=null,proposal=null,report=null,jobs={},checkReport=null,cell=null,displayScope=null,view='setup',busy=false,timer=null,epoch=0;
 const active=g=>g&&['queued','preparing','running','verifying','saving','analyzing','stop_requested'].includes(g.state);
 const complete=g=>g?.cells?.length&&g.cells.every(c=>c.state==='completed');
 const controlled=()=>b?.cells?.[0]?.label.startsWith('비용 대조 V1|');let controlAvailable=false;
 const alive=()=>d.isConnected&&draft.sensor===cid;
 const status=document.createElement('p');status.id='guidedStatus';status.setAttribute('role','status');status.style.cssText='min-height:3em;padding:14px;background:#e6f4f8;font-size:17px';d.append(status);
 const track=document.createElement('nav');track.setAttribute('aria-label','연구 순서');track.style.cssText='display:flex;gap:8px;flex-wrap:wrap';d.append(track);
 const steps=['1. 조건·비용 탐색','2. 예산 후보 선택','3. 예산 탐색','4. 선택 배치 검산','5. 검산 결과 비교'];
 const tabs=steps.map((label,i)=>dButton(track,'guidedStep'+i,label,()=>act(async()=>{
  if(i===0){view='setup';render();}
  if(i===1){await derive();}
  if(i===2){view=b?'bprogress':'proposal';render();}
  if(i===3){await analyze();view='compare';render();}
  if(i===4){view='result';render();}
 })));
 const purpose=vDetails(d,'이 연구는 무엇을 알아보는 실험인가요?');purpose.id='guidedPurpose';purpose.open=false;
 noteText(purpose,'저장된 연구를 열면 당시 실행한 조건의 결과를 비교합니다. 이 지도 비교 자체가 새로운 난이도 실험을 실행하지는 않습니다. 관측 범위·수량 조건을 바꾸어 비교하려면 바꿀 조건과 반복 실행 기준을 정한 뒤 별도 실험을 실행해야 합니다.');
 noteText(purpose,'예산·센서 관측 범위·수량 제약을 체계적으로 바꾸어 문제의 난이도와 자원 경쟁 구조를 조절하고, 최적화기가 어떤 성능과 배치 구조를 찾아내는지 진단합니다. 실제 문제의 조건 설정에 활용하기 위해 지도에서 구별되는 대안을 비교합니다.');
 noteText(purpose,'조건을 바꾼 실험과, 같은 조건에서 탐색량·seed를 바꾼 실험을 구분합니다. 절충 미관측이 난이도 때문인지는 아직 가설입니다. 바꾼 조건 → 예상한 변화 → 실제 성능·배치 변화 → 근거와 한계 순서로 판단하며, 빈 결과나 실패도 숨기지 않습니다.');
 const panel=document.createElement('section');panel.id='guidedContent';d.append(panel);
 const actions=document.createElement('div');actions.style.cssText='display:flex;gap:10px;flex-wrap:wrap;margin:18px 0;position:sticky;bottom:0;background:white;padding:14px 0;border-top:1px solid #b9d2df;z-index:5';d.append(actions);
 const next=dButton(actions,'guidedNext','조건 확인',()=>act(proceed));next.classList.add('primary');
 const stop=dButton(actions,'guidedStop','중지 요청·저장',()=>act(async()=>{const g=active(b)?b:active(a)?a:null;if(g)await api(cid,'engine/validations/'+g.validation_id+'/cancel',{});else for(const side of ['a','b'])if(jobs[side]&&['QUEUED','RUNNING'].includes(jobs[side].status))await api(cid,'engine/runs/'+cell[side+'_run_id']+'/quality-jobs/'+jobs[side].job_id+'/cancel',{});await refresh();}));
 const progress=document.createElement('div');progress.id='guidedProgress';track.after(progress);
 const observations=new Map();let receivedAt=0,polling=false,refreshPending=false;
 const freshness=document.createElement('p');freshness.id='guidedFreshness';status.after(freshness);
 const clock=setInterval(()=>{if(!alive()){clearInterval(clock);return;}if(receivedAt)freshness.textContent='마지막 상태 응답 '+Math.floor((Date.now()-receivedAt)/1000)+'초 전'+(polling?' · 조회 중…':'')+' · 화면을 닫아도 서버의 계산은 계속됩니다.';},1000);
 const phaseLabel=s=>({queued:'순서 대기',preparing:'초기 배치 준비',running:'배치 탐색',verifying:'원시 결과 재평가',saving:'파일 저장',analyzing:'결과 분석',stop_requested:'중지 요청 처리',completed:'완료·저장됨',cancelled:'중지됨',failed:'실패',time_limit:'시간 제한 도달',interrupted:'실행 중단',completed_with_failures:'일부 미완료'})[s]||s;
 const duration=s=>Number.isFinite(s)?Math.floor(s/60)+'분 '+Math.floor(s%60)+'초':'미기록';
 async function readStatus(id){const response=await fetch('/contracts/'+cid+'/api/engine/validations/'+id,{headers:{'X-Experiment-Contract':cid},signal:AbortSignal.timeout(10000)});if(response.headers.get('X-Experiment-Contract')!==cid)throw Error('응답 계약 불일치');const g=await response.json();if(!response.ok)throw Error(g.error||'상태 조회 실패');if(g.experiment_contract_id!==cid||g.validation_id!==id)throw Error('실행 응답 불일치');return g;}
 const history=vDetails(d,'저장된 연구 이어 보기');
 const ah=selectControl(history,'비용 탐색 A',[['','새 연구']],'',id=>act(async()=>{epoch++;a=id?await api(cid,'engine/validations/'+id):null;b=null;preview=null;proposal=null;report=null;checkReport=null;jobs={};if(a)hydrateA();view=id?'aprogress':'setup';await histories();render();await refresh();}),'guidedHistoryA');
 const bh=selectControl(history,'연결된 예산 탐색 B',[['','아직 없음']],'',id=>act(async()=>{epoch++;b=id?await api(cid,'engine/validations/'+id):null;preview=null;report=null;checkReport=null;jobs={};view=id?'bprogress':'aprogress';render();await refresh();}),'guidedHistoryB');
 const pendingKey='solsol-guided-pending:'+cid;
 dButton(history,'guidedRecover','미확정 제출 확인',()=>act(async()=>{const p=JSON.parse(localStorage.getItem(pendingKey)||'null');if(!p){status.textContent='미확정 제출이 없습니다.';return;}await submit(p);}));
 dButton(history,'guidedAdvanced','고급: 예산·관측반경 조합 연구',()=>{d.close();d.remove();openAdvancedResourceStudy(source);});
 const settings={seeds:String(base.optimizer.seed??1),population:String(base.optimizer.population),generations:String(base.optimizer.generations??base.optimizer.checkpoints-1),scope:'all',budgets:'',design:'LEGACY_AB'};
 d.addEventListener('close',()=>{epoch++;clearTimeout(timer);clearInterval(clock);});
 function text(message){status.textContent=message;}
 function hydrateA(){const q=a.cells[0].request;settings.seeds=a.cells.map(c=>c.seed).join(', ');settings.population=String(q.optimizer.population);settings.generations=String(q.optimizer.generations??q.optimizer.checkpoints-1);}
 async function act(fn){if(busy||!alive())return;busy=true;buttons();try{await fn();}catch(e){if(alive())text('진행하지 못했습니다: '+e.message+' · 원인 확인 후 같은 단계에서 다시 시도하세요.');}finally{busy=false;if(alive())buttons();}}
 function buttons(){const running=active(a)||active(b)||Object.values(jobs).some(j=>['RUNNING','QUEUED'].includes(j.status));
  tabs.forEach((t,i)=>{t.disabled=busy||running||i===1&&!complete(a)||i===2&&!proposal&&!b||i===3&&!complete(b)||i===4&&!checkReport?.complete;t.title=t.disabled?'앞 단계의 계산·저장·검산 완료가 필요합니다.':'이 단계의 연구 내용 보기';});
  for(const input of panel.querySelectorAll('input,select'))input.disabled=busy||running||(view==='setup'&&!!a);
  if($('guidedQuickTest'))$('guidedQuickTest').disabled=busy||running;
  ah.disabled=bh.disabled=busy||running;next.disabled=busy||running;stop.disabled=busy||!running;
  if(view==='setup'){next.textContent=preview?'확인한 조건으로 A 계산 시작':'1. 조건과 계산량 확인';if(a)next.disabled=true;}
  else if(view==='aprogress'){next.textContent=complete(a)?'A 완료 · 눌러서 예산 후보 보기':active(a)?'A 실행 중 · 위 진행 확인':'A 미완료 · 저장 결과와 중단 사유 확인';next.disabled=busy||!complete(a);}
  else if(view==='proposal'){next.textContent=preview?'확인한 예산으로 B 계산 시작':'2. 선택한 예산과 계산량 확인';next.disabled=busy||!proposal?.candidates.length||running;}
  else if(view==='bprogress'){next.textContent=complete(b)?'B 완료 · 눌러서 비교·검산 배치 보기':active(b)?'B 실행 중 · 위 진행 확인':'B 일부 미완료 · 저장 결과는 위에서 열기';next.disabled=busy||!complete(b);}
  else if(view==='compare'){next.textContent=controlled()?'4. 선택한 예산의 유지·제외 배치 검산 시작':'4. 표시된 A·B 두 배치 검산 시작';next.disabled=busy||running||!cell?.a_example||!cell?.b_example;}
  else if(view==='checking'){const done=Object.values(jobs).length===2&&Object.values(jobs).every(j=>j.status==='COMPLETED'&&j.scope_complete);next.textContent=done?'검산 완료 · 눌러서 결과 비교 보기':'검산 중 · 기다려 주세요';next.disabled=busy||!done;}
  else {next.textContent='다른 예산의 배치 비교·검산';next.disabled=busy;}
  next.setAttribute('aria-busy',String(!!running||busy));
 }
 function render(){panel.replaceChildren();d.scrollTop=0;
  if(view==='setup'){
   noteText(panel,'먼저 성능을 높이는 데 비용이 얼마나 필요한지 탐색합니다. 다음에는 여기서 관측한 비용으로 예산을 정하고, 비용 목적을 제외하여 같은 성능끼리 비교합니다.');
   noteText(panel,(a?'저장된 A 연구 '+a.validation_id.slice(0,8):saved?'기준 저장 실행 '+saved.run_id.slice(0,8):'기준: 현재 초안')+' · 후보지·평가영역·반경·단가·수량 조건·목표는 A와 B에서 같습니다. A에서는 예산 제한을 사용하지 않습니다.');
   evidenceTable(panel,['A: 성능과 비용','B: 한정 예산의 성능'],[['성능 목적 + 비용 최소화','같은 성능 목적만 · 비용 ≤ 선택 예산'],['비용별 성능 향상을 관측','성능 사이 절충 발생 여부를 새로 탐색']]);
   for(const [key,label] of [['seeds','반복 난수 시드 · 쉼표 구분'],['population','각 실행 개체 수'],['generations','각 실행 세대 수']]){const input=vField(panel,'guided_'+key,label,settings[key]);input.disabled=!!a;input.oninput=()=>{settings[key]=input.value;preview=null;text('입력이 바뀌었습니다. 조건을 다시 확인하세요.');buttons();};}
   if(!a){dButton(panel,'guidedQuickTest','작동 확인용 소규모 설정 · 8개 × 3세대',()=>{if(busy||active(a)||active(b))return;settings.population='8';settings.generations='2';settings.seeds=settings.seeds.split(',')[0].trim();preview=null;render();text('작동 확인용: 초기 세대 포함 24회 탐색/실행 + 준비·재평가 별도입니다. 성능·수렴 판단용 연구가 아닙니다. 조건 확인 후 직접 실행하세요.');});}
   noteText(panel,'초기화 방식과 설치 후보 정책은 기준 조건을 따릅니다. 목적 수가 바뀌므로 NSGA-III 참조방향은 각 목적 수로 다시 생성하며 집단 수는 동일하게 유지합니다.');
   if(!base.resource_contract&&!base.model_config?._resource_contract){noteText(panel,'현재 조건에 센서별 비용·공통 자원 설정이 없습니다. 먼저 조건을 설정하세요.');dButton(panel,'guidedOpenSettings','센서 비용·수량 조건 설정으로',()=>{d.close();d.remove();setting='sensors';workbench?.setTask('settings');document.body.classList.remove('settingsHidden');$('toggleSettings').setAttribute('aria-expanded','true');renderSettings();});}
   text(a?'저장된 A 조건입니다. 2번 단계에서 예산 후보를 보세요.':'다음 행동: 아래 「1. 조건과 계산량 확인」을 누르세요. 아직 계산하지 않았습니다.');
  }else if(view==='proposal'){
   if(controlAvailable)selectControl(panel,'비교 설계',[['BUDGET_MATCHED_COST_ROLE_V1','세 조건 비교 · 같은 예산의 비용 목적 유지/제외'],['LEGACY_AB','기존 두 조건 · 비용 목적에서 예산 제약으로']],settings.design,value=>{settings.design=value;preview=null;buttons();},'guidedDesign');
   if(settings.design==='BUDGET_MATCHED_COST_ROLE_V1')noteText(panel,'선택 예산마다 비용 목적 유지·제외 두 실행을 만듭니다. 기준 A ↔ 유지군은 예산 효과, 유지군 ↔ 제외군은 비용 목적 효과를 비교합니다. 다음 확인에서 실행 수와 계산량을 확인하세요.');
   noteText(panel,proposal.meaning);noteText(panel,'관측 고유 비용 '+proposal.observed_unique_costs+'개 · 관측 목표 통과 최소 '+(proposal.observed_target_minimum??'없음·미설정')+' · 수량 고정/넉넉한 예산/목적 간 같은 경향 때문에 절충이 없을 수도 있습니다.');
   selectControl(panel,'예산을 추출할 A 집합',[['all','누적 비지배 해 전체'],['targets','목표 통과 누적 비지배 해']],settings.scope,value=>act(async()=>{settings.scope=value;await derive();}),'guidedScope');
   evidenceTable(panel,['예산 후보','선정 이유','출처 원시 행'],proposal.candidates.map(c=>[c.budget,c.reason,c.source.run_id.slice(0,8)+' / '+c.source.raw_id]));
   const input=vField(panel,'guidedBudgets','다음 실험 예산 · 쉼표 구분 · 직접 수정 가능',settings.budgets);input.oninput=()=>{settings.budgets=input.value;preview=null;text('예산 변경: 계산량을 다시 확인하세요. 직접 입력한 예산도 원래 후보 근거와 함께 보존됩니다.');buttons();};
   text(proposal.candidates.length?'다음 행동: 예산 후보를 확인하고 아래 버튼으로 B 조건을 확인하세요.':'선택 집합에 결과가 없습니다. 집합을 바꾸거나 A 탐색 조건을 다시 구성하세요.');
  }else if((view==='compare'||view==='result')&&controlled()){
   selectControl(panel,'검산할 예산·seed',report.pairs.filter(p=>p.complete).map(p=>[p.budget+'|'+p.seed,'예산 '+p.budget+' · seed '+p.seed]),cell?.cell_id,value=>{const pair=report.pairs.find(p=>p.budget+'|'+p.seed===value);selectControlPair(pair);jobs={};checkReport=null;view='compare';render();},'guidedControlPair');
   if(cell?.a_example&&cell?.b_example)noteText(panel,'검산 대상: 비용 목적 유지 원시 행 '+cell.a_example.raw_id+' / 제외 원시 행 '+cell.b_example.raw_id+' · 각 조건의 공통 성능 전선에서 대표 한 개씩입니다. 전체 해집합 검산은 아닙니다.');
   selectControl(panel,'현재 비교할 해집합',[['all','누적 비지배 해 전체'],['targets','목표 통과 누적 비지배 해']],report.scope,value=>act(async()=>{displayScope=value;await analyze();render();}),'guidedDisplayScope');
   noteText(panel,report.meaning);
   noteText(panel,'예산 산출 집합: '+report.proposal_scope+' · 현재 비교 집합: '+report.scope+' · 비용 차이를 성능 간 절충과 구분하세요.');
   for(const pair of report.pairs){
    const detail=vDetails(panel,'예산 '+pair.budget+' · seed '+pair.seed);detail.open=report.pairs.length===1;
    if(!pair.complete){noteText(detail,'아직 세 조건이 모두 완료되지 않았습니다.');jsonDetails(detail,'상태',pair.states);continue;}
    const names={BASELINE:'기준 · 비용 목적 / 예산 없음',ON:'대조 · 비용 목적 / 예산 제한',OFF:'실험 · 성능 목적 / 같은 예산'};
    evidenceTable(detail,['조건','비지배 해','공통 성능 전선','비용 범위','실제 탐색 평가'],Object.entries(pair.arms).map(([role,r])=>[names[role],r.archive_count,r.performance_front_count,r.cost_range?.join(' ~ ')??'없음',r.search_nfe]));
    noteText(detail,pair.matched_search_nfe===true?'실제 탐색 평가 수가 같습니다. 초기화·재평가 비용은 별도입니다.':pair.matched_search_nfe===false?'실제 탐색 평가 수가 다릅니다. 탐색량 차이를 고려해야 합니다.':'실제 탐색 평가 수가 미기록되어 같은 탐색량인지 판단할 수 없습니다.');
    for(const [role,r] of Object.entries(pair.arms)){
     const arm=vDetails(detail,names[role]+' · 성능·지도·검산');
     evidenceTable(arm,['공통 성능','관측 범위'],Object.entries(r.performance_ranges).map(([key,values])=>[key,values?.join(' ~ ')??'없음']));
     noteText(arm,'원시 실행 '+r.run_id+' · 같은 예산 이하의 선택 archive '+r.budget_eligible_archive_count+'개');
     const link=document.createElement('a');link.className='button';link.textContent='이 조건의 저장 지도 열기 · 배치 선택 후 검산';link.href='/live.html?contract='+encodeURIComponent(cid)+'&run='+encodeURIComponent(r.run_id);link.target='_blank';link.rel='noopener';arm.append(link);
     if(r.conflict){const maps=document.createElement('div');maps.className='qualityCompareMaps';arm.append(maps);dButton(arm,'','이 조건에서 성능이 교차하는 두 배치 보기',()=>act(async()=>{const p=await api(cid,'engine/runs/'+r.run_id+'/view');if(!alive()||!maps.isConnected)return;maps.replaceChildren();for(const row of Object.values(r.conflict)){const column=document.createElement('div');noteText(column,'원시 행 '+row.id+' · 비용 '+row.cost);column.insertAdjacentHTML('beforeend',qualityGeometryMap(p.problem,row));evidenceTable(column,['지표','값'],Object.entries(row.named_metrics||{}));maps.append(column);}}));}
     else noteText(arm,'선택한 집합에서 성능 교차 쌍이 관측되지 않았습니다. 절충이 불가능하다는 증명은 아닙니다.');
    }
   }
   dButton(panel,'guidedControlExport','세 조건 비교 근거 저장',()=>qualityDownload(report,'controlled-cost-budget-comparison.json'));
   if(view==='result'&&checkReport){noteText(panel,'선택한 두 원시 배치의 검산 결과입니다. 전체 해집합·전역 최적 검증이 아닙니다.');evidenceTable(panel,['비용 목적','검산 상태','평가 수','성능 엄격 개선','같은 성능의 비용 절감'],checkReport.results.map(r=>[r.cost_role==='ON'?'유지':'제외',r.status,r.evaluated,r.strict_performance_improvements.length,r.equal_performance_cost_savings.length]));noteText(panel,'비용 목적을 제외한 조건에서는 같은 성능의 더 저렴한 대안이 발견되어도 원래 성능 목적의 지배 오류는 아닙니다. 별도 비용 절감 근거로 봅니다.');jsonDetails(panel,'검산 출처와 별도 대안',checkReport);}
   if(view==='result'&&checkReport)renderCheckMaps(checkReport,['비용 목적 유지','비용 목적 제외']);
   text(view==='result'?'검산 완료 결과를 표시했습니다. 성능 개선과 비용 절감을 구분해 확인하세요.':'세 조건의 저장 결과입니다. 아래 활성 버튼으로 표시된 유지·제외 배치를 검산하세요. 이 비교 표 자체는 검산 완료 표시가 아닙니다.');
  }else if(view==='compare'||view==='result'){
   selectControl(panel,'현재 비교할 해집합',[['all','누적 비지배 해 전체'],['targets','목표 통과 누적 비지배 해']],report.scope,value=>act(async()=>{displayScope=value;jobs={};checkReport=null;await analyze();view='compare';render();}),'guidedDisplayScope');
   noteText(panel,'예산 후보 산출: '+(report.proposal_scope==='targets'?'목표 통과 해':'누적 비지배 해 전체')+' · 현재 표시: '+(report.scope==='targets'?'목표 통과 해':'누적 비지배 해 전체')+'. 표시를 바꾸어도 저장된 A/B 조건과 예산 후보 근거는 바뀌지 않습니다.');
   selectControl(panel,'비교할 예산·seed',report.cells.filter(c=>c.state==='completed').map(c=>[c.cell_id,'예산 '+c.budget+' · seed '+c.seed]),cell?.cell_id,value=>act(async()=>{cell=report.cells.find(c=>c.cell_id===value);jobs={};checkReport=null;view='compare';render();}),'guidedCell');
   if(cell){const explanation=document.createElement('section');explanation.id='guidedExplanation';explanation.style.cssText='padding:18px;border-left:5px solid #0085a4;background:#eef8fb;margin:16px 0';panel.append(explanation);const e=cell.explanation;const title=document.createElement('h3');title.textContent=e.answer;explanation.append(title);for(const key of ['numbers','meaning','scope'])noteText(explanation,e[key]);noteText(explanation,'다음 행동: '+e.next_action);
    if(cell.b_conflict){const pair=cell.b_conflict;const proof=vDetails(panel,'절충을 보여 주는 실제 두 배치의 수치');proof.open=true;noteText(proof,'두 행은 모두 같은 B 실행의 현재 표시 집합에 있습니다. 숫자의 높고 낮음은 각 성능의 공개 방향을 따릅니다.');evidenceTable(proof,['저장 성능','원시 행 '+pair.A.id,'원시 행 '+pair.B.id],cell.metrics.map(m=>[m.name,pair.A.named_metrics[m.id],pair.B.named_metrics[m.id]]));noteText(proof,'비용: '+pair.A.cost+' / '+pair.B.cost+' · B 실행 '+cell.b_run_id);
     renderPlacementDifference(proof,pair.A,pair.B,cell.metrics,cell.sensor_labels,'B 배치 1','B 배치 2');
     const witnessMaps=document.createElement('div');proof.append(witnessMaps);const selectedCell=cell;
     dButton(proof,'guidedWitnessButton','이 절충을 보여 주는 두 원시 배치 지도 보기',()=>act(async()=>{const p=await api(cid,'engine/runs/'+selectedCell.b_run_id+'/view');if(!alive()||!witnessMaps.isConnected)return;witnessMaps.replaceChildren();renderFilteredPlacementMaps(witnessMaps,p.problem,pair.A,pair.B,selectedCell.sensor_labels,'B 배치 1','B 배치 2','guidedWitnessMaps');text('같은 예산의 B 원시 배치 두 개를 비교합니다. 비용 목적 A와 B의 비교는 아래 별도 항목입니다.');}));
     renderPairContribution(proof,cid,selectedCell,report.scope,report.b_id,act);
    }
    const execution=vDetails(panel,'실제 탐색량과 초기 배치 생성 방식');for(const side of ['a','b']){const a=cell.accounting?.[side],i=a?.initialization;noteText(execution,side.toUpperCase()+' · 탐색 '+a?.search_nfe+'회 · 준비 '+(a?.counters?.preparation_evaluations??'미기록')+'회 · 재평가 '+(a?.counters?.replay_evaluations??'미기록')+'회');if(i)noteText(execution,'요청 '+i.method+' · 준비에서 얻은 seed '+i.seed_count+'개'+(i.seed_count===0?' · 실제 초기 인구는 저장된 대체 방식 사용':'')+' · '+(i.approximation||i.outcome||i.status));}jsonDetails(execution,'초기화·시도별 저장 근거',cell.accounting);
    const counts=vDetails(panel,'다른 예산·seed의 배치 수와 잔여 예산 비교');noteText(counts,report.meaning);
    evidenceTable(counts,['예산 / seed','A 원 비지배 / 성능 최선값','A 전체 관측 / 성능 최선값','B 비지배 / 성능 최선값','B 최소 잔여 예산'],report.cells.filter(c=>c.state==='completed').map(c=>[c.budget+' / '+c.seed,c.a_original_archive_eligible+' / '+c.a_archive_performance_front,c.a_raw_eligible+' / '+c.a_raw_performance_front,c.b_archive_count+' / '+c.b_performance_front,c.min_budget_slack??'미관측']));
    evidenceTable(panel,['공통 성능','A 같은 예산 이하 관측 범위','B 관측 범위'],cell.metrics.map(m=>[m.name,m.a_range?.map(v=>Number(v).toPrecision(5)).join(' – ')??'없음',m.b_range?.map(v=>Number(v).toPrecision(5)).join(' – ')??'없음']));
    noteText(panel,'아래 두 행은 공통 성능 순서→비용→원시 번호로 고른 비교 예시입니다. 검산은 이 두 행만 확인하며 전체 해집합 검증이 아닙니다.');
    for(const side of ['a','b']){const row=cell[side+'_example'];noteText(panel,side.toUpperCase()+': '+(row?'원시 행 '+row.raw_id+' · 비용 '+row.cost+' · 성능 '+row.performance_F.map(v=>Number(v).toPrecision(4)).join(' / '):'이 예산·집합에 비교할 배치 없음'));const link=document.createElement('a');link.href='/live.html?contract='+encodeURIComponent(cid)+'&run='+cell[side+'_run_id'];link.target='_blank';link.rel='noopener';link.textContent=side.toUpperCase()+' 원시 해집합·지도 열기';panel.append(link);}
    if(cell.a_example&&cell.b_example){const comparison=renderPlacementDifference(panel,cell.a_example,cell.b_example,cell.metrics,cell.sensor_labels,'비용 목적 A','예산 제약 B');noteText(comparison.box,'A 전체 관측 중 같은 예산 이하의 공통 성능 최선값에서 고른 예시와 B 예시입니다. A 원래 비용 포함 Pareto 전체 또는 두 방식 전체의 우열을 이 한 쌍으로 판단하지 않습니다.');const maps=document.createElement('div');comparison.box.append(maps);const selected=cell;dButton(comparison.box,'guidedABMaps','비용 목적 A와 예산 제약 B의 위치 차이 지도 보기',()=>act(async()=>{const p=await api(cid,'engine/runs/'+selected.a_run_id+'/view');if(!alive()||!maps.isConnected)return;maps.replaceChildren();renderFilteredPlacementMaps(maps,p.problem,selected.a_example,selected.b_example,selected.sensor_labels,'비용 목적 A','예산 제약 B','guidedABMapCanvas');text('같은 예산 이하의 A 예시와 B 예시를 표시했습니다. 전체 방식의 우열이나 인과 증명이 아닙니다.');}));}
   }
   if(view==='result'&&checkReport){noteText(panel,'검산 완료: 같은 예산·목표 조건으로 성능 개선과 같은 성능의 비용 절감을 따로 비교합니다.');for(const [i,r] of checkReport.results.entries()){const box=vDetails(panel,(i?'B':'A')+' 검산 · 원시 '+r.raw_id+' · '+r.evaluated+'/'+r.total);box.open=true;noteText(box,r.meaning);noteText(box,'엄격한 성능 개선 '+r.strict_performance_improvements.length+'건 · 같은 성능 비용 절감 '+r.equal_performance_cost_savings.length+'건');evidenceTable(box,['구분','검산 배치 ID','작업','비용','공통 성능 F'],[...r.strict_performance_improvements.map(x=>['성능 개선',x]),...r.equal_performance_cost_savings.map(x=>['같은 성능 비용 절감',x])].map(([label,x])=>[label,r.job_id.slice(0,8)+' / '+x.sequence,x.operation,x.cost,x.performance_F.join(' / ')]));jsonDetails(box,'원시와 분리된 검산 근거',r);}}
   if(view==='result'&&checkReport)renderCheckMaps(checkReport,['A','B']);
   text(view==='result'?'검산 결과를 표시했습니다. 비용만 절감되는 동률 배치는 비용 없는 B 목적의 지배 오류로 판단하지 않습니다.':'다음 행동: 비교할 예산을 고른 뒤 표시된 두 배치를 검산하세요.');
  }else{noteText(panel,view==='checking'?'선택한 A·B 각 한 행을 원래 Model로 다시 평가하고 전체 1회 삭제·추가·이동을 검사합니다. 임의 시간·평가 상한으로 끊지 않습니다. 중지하면 저장하고 이어서 검사할 수 있습니다.':'각 실행은 탐색 → 원시 재평가 → 저장 순서로 진행합니다. 완료 전에 다음 계산을 시작하지 않습니다.');}
  for(const table of panel.querySelectorAll('table'))if(table.querySelectorAll('tr').length===1)table.remove();
  buttons();
 }
 function renderCheckMaps(evidence,labels){
    const maps=vDetails(panel,'선택 배치·검산 배치를 지도와 실제 수치로 비교');maps.open=true;
    noteText(maps,'왼쪽은 '+labels[0]+', 오른쪽은 '+labels[1]+'입니다. 원시 배치와 별도 검산 배치를 구분하여 선택하세요.');
    const choices={};for(const [i,r] of evidence.results.entries())choices[i]=selectControl(maps,labels[i]+' 지도 배치',[['0','원시 행 '+r.raw_id+' 재평가'],...r.strict_performance_improvements.filter(x=>x.sequence!==0).map(x=>[String(x.sequence),'검산 '+x.sequence+' · 성능 개선 · 비용 '+x.cost]),...r.equal_performance_cost_savings.filter(x=>x.sequence!==0).map(x=>[String(x.sequence),'검산 '+x.sequence+' · 동일 성능 · 비용 '+x.cost])],'0',()=>{},'guidedMapChoice'+i);
    const canvas=document.createElement('div');canvas.className='qualityCompareMaps';maps.append(canvas);
    dButton(maps,'guidedMaps','선택한 두 배치 지도 보기',()=>act(async()=>{
     text('저장된 검산 배치 지도를 불러오는 중입니다. 새 최적화는 실행하지 않습니다.');
     canvas.replaceChildren();
     const values=await Promise.all(evidence.results.map(async(r,i)=>{const [p,v]=await Promise.all([api(cid,'engine/runs/'+r.run_id+'/view'),api(cid,'engine/runs/'+r.run_id+'/quality-jobs/'+r.job_id+'/rows?offset='+choices[i].value+'&witnesses=false')]);if(p.run_id!==r.run_id||v.job.job_id!==r.job_id||v.job.parent?.run_id!==r.run_id||v.job.parent?.config_sha256!==p.config_sha256||v.job.source_ids?.length!==1||v.job.source_ids[0]!==r.raw_id)throw Error('검산 지도 출처가 선택 배치와 일치하지 않습니다.');if(v.job.status!=='COMPLETED'||!v.job.scope_complete)throw Error('완료된 검산만 지도에 비교합니다.');const row=v.rows.find(x=>x.sequence===Number(choices[i].value));if(!row)throw Error('저장 검산 배치를 찾지 못했습니다.');return {p,row,r,i};}));
     if(!alive()||!canvas.isConnected)return;canvas.replaceChildren();for(const {p,row,r,i} of values){const side=document.createElement('div');const original=row.operation==='replay';noteText(side,labels[i]+' · '+(original?'원시 행 '+r.raw_id:'별도 검산 '+r.job_id.slice(0,8)+' / '+row.sequence)+' · 비용 '+row.cost+' · 센서 '+(row.sensor_counts||[]).join(' / '));side.insertAdjacentHTML('beforeend',qualityGeometryMap(p.problem,{...row,id:original?r.raw_id:'검산 '+row.sequence}));evidenceTable(side,['지표','저장 값'],Object.entries(row.named_metrics||{}));canvas.append(side);}text('원시와 별도 검산 배치의 지도·수치를 표시했습니다.');
    }));
    dButton(maps,'guidedExport','이 비교 근거 JSON 저장',()=>qualityDownload({report,checkReport:evidence},'cost-budget-comparison.json'));
 }
 async function derive(){proposal=await api(cid,'engine/guided-cost-budget/'+a.validation_id+'/proposal?scope='+settings.scope);settings.budgets=proposal.candidates.map(c=>c.budget).join(', ');preview=null;view='proposal';render();}
 function selectControlPair(pair){cell=pair?{cell_id:pair.budget+'|'+pair.seed,budget:pair.budget,seed:pair.seed,a_run_id:pair.arms.ON.run_id,b_run_id:pair.arms.OFF.run_id,a_example:pair.arms.ON.example,b_example:pair.arms.OFF.example}:null;}
 async function analyze(){report=await api(cid,'engine/guided-cost-budget/'+b.validation_id+'/'+(controlled()?'controlled-comparison':'comparison')+(displayScope?'?scope='+displayScope:''));if(controlled())selectControlPair(report.pairs.find(p=>p.complete&&p.budget+'|'+p.seed===cell?.cell_id)||report.pairs.find(p=>p.complete));else cell=report.cells.find(c=>c.cell_id===cell?.cell_id)||report.cells.find(c=>c.state==='completed');}
 async function submit(p){text('접수 확인 중입니다. 중복 제출하지 말고 기다려 주세요.');const g=await api(cid,'engine/validations',p.body,{'X-Request-ID':p.id,'X-Execution-SHA256':p.sha});if(localStorage.getItem(pendingKey)===JSON.stringify(p))localStorage.removeItem(pendingKey);if(!alive())return;if(p.kind==='A'){a=g;b=null;view='aprogress';}else{b=g;const parts=g.cells[0].label.split('|');a=await api(cid,'engine/validations/'+parts[1]);settings.scope=parts[2];view='bprogress';}hydrateA();preview=null;await histories();render();await refresh();}
 async function proceed(){
  if(view==='setup'||view==='proposal'){
   if(localStorage.getItem(pendingKey))throw Error('미확정 제출이 있습니다. 저장된 연구 이어 보기에서 동일 요청을 확인하세요.');
   if(preview){const p={id:crypto.randomUUID(),kind:view==='setup'?'A':'B',sha:preview.plan.plan_sha256,body:preview.request};localStorage.setItem(pendingKey,JSON.stringify(p));await submit(p);return;}
   text('Model 조건·계산량 확인 중입니다. 기다려 주세요.');
   if(view==='setup'){const q=structuredClone(base);q.optimizer.population=Number(settings.population);q.optimizer.generations=Number(settings.generations);delete q.optimizer.checkpoints;preview=await api(cid,'engine/guided-cost-budget/preview-a',{base_request:q,seeds:settings.seeds.split(',').map(s=>s.trim()===''?null:Number(s))});}
   else preview=await api(cid,'engine/guided-cost-budget/'+(settings.design==='BUDGET_MATCHED_COST_ROLE_V1'?'preview-controlled':'preview-b'),{a_id:a.validation_id,scope:settings.scope,proposal_sha256:proposal.proposal_sha256,budgets:settings.budgets.split(',').map(s=>s.trim()===''?null:Number(s))});
   text('조건 확인 완료: '+preview.plan.total_cells+'개 실행 · 탐색 '+preview.plan.expected_nfe+'회 + 초기화·재평가 별도. 아래 활성 버튼을 누르면 계산을 시작합니다.');return;
  }
  if(view==='aprogress'){await derive();return;}
  if(view==='bprogress'){await analyze();view='compare';render();return;}
  if(view==='compare'){view='checking';render();try{for(const side of ['a','b']){const path='engine/runs/'+cell[side+'_run_id']+'/quality-jobs',list=await api(cid,path);const match=list.jobs.find(j=>j.definition_sha256===list.definition_sha256&&j.method==='local'&&j.scope==='selected'&&j.source_ids.length===1&&j.source_ids[0]===cell[side+'_example'].raw_id&&j.status!=='ERROR');jobs[side]=match||await api(cid,path,{scope:'selected',raw_id:cell[side+'_example'].raw_id,method:'local'});if(['STOPPED','INTERRUPTED'].includes(jobs[side].status))jobs[side]=await api(cid,path+'/'+jobs[side].job_id+'/resume',{});}}finally{await refresh();}return;}
  if(view==='checking'){checkReport=await api(cid,'engine/guided-cost-budget/'+(controlled()?'controlled-checks':'checks'),controlled()?{study_id:b.validation_id,budget:cell.budget,seed:cell.seed,a_job:jobs.a.job_id,b_job:jobs.b.job_id,scope:report.scope}:{b_id:b.validation_id,cell_id:cell.cell_id,a_job:jobs.a.job_id,b_job:jobs.b.job_id,scope:report.scope});if(!checkReport.complete)throw Error('두 검산 모두 완료되지 않았습니다.');view='result';render();return;}
  view='compare';render();
 }
 async function histories(){const previous=status.textContent;text('저장된 연구 목록과 원시 결속을 조회 중입니다. 완료되면 선택 항목이 활성화됩니다.');const list=await api(cid,'engine/guided-cost-budget');if(!alive())return;text(previous);const had=controlAvailable;controlAvailable=list.designs?.includes('BUDGET_MATCHED_COST_ROLE_V1')===true;if(controlAvailable&&!had)settings.design='BUDGET_MATCHED_COST_ROLE_V1';option(ah,[['','새 연구'],...list.studies.filter(s=>s.kind==='A').map(s=>[s.validation_id,s.validation_id.slice(0,8)+' · '+s.state])],a?.validation_id||'');option(bh,[['','선택하세요'],...list.studies.filter(s=>s.kind==='B'&&s.a_id===a?.validation_id).map(s=>[s.validation_id,s.validation_id.slice(0,8)+' · '+(s.design?'세 조건 · ':'')+s.scope+' · '+s.state])],b?.validation_id||'');}
 async function refresh(){clearTimeout(timer);if(!alive())return;if(polling){refreshPending=true;return;}const ticket=epoch,oldA=a,oldB=b;polling=true;try{
  let nextA=oldA,nextB=oldB;const nextJobs={...jobs};
  if(oldA&&(!receivedAt||active(oldA)||!oldB))nextA=await readStatus(oldA.validation_id);if(oldB)nextB=await readStatus(oldB.validation_id);
  for(const side of Object.keys(nextJobs))nextJobs[side]=await api(cid,'engine/runs/'+cell[side+'_run_id']+'/quality-jobs/'+nextJobs[side].job_id);
  if(!alive()||ticket!==epoch||a!==oldA||b!==oldB)return;a=nextA;b=nextB;jobs=nextJobs;receivedAt=Date.now();progress.replaceChildren();
  const g=active(b)?b:active(a)?a:view==='aprogress'?a:view==='bprogress'?b:null;
  if(g){const done=g.cells.filter(c=>c.state==='completed').length;
   const current=g.cells.find(c=>c.state==='running');text('총 '+g.cells.length+'개 실행 중 '+done+'개 완료·저장 · '+phaseLabel(current?.phase||g.state)+'. 탐색 횟수의 완료와 재평가·저장 완료는 별도입니다.');
   evidenceTable(progress,['실행 · seed','현재 단계','탐색 진행','경과 · 최근 변화'],g.cells.map(c=>{const t=c.attempts.at(-1),p=c.progress||{},n=t?.nfe??0,total=c.execution_snapshot.declared_nfe,key=t?.run_id||c.cell_id,state=c.phase||c.state,signature=[state,n,p.counters?.replay_evaluations].join(':');let o=observations.get(key);if(!o||o.signature!==signature){o={signature,at:Date.now()};observations.set(key,o);}const age=Math.floor((Date.now()-o.at)/1000);const counts=state==='verifying'?'재평가 '+(p.counters?.replay_evaluations??'미기록')+' / '+n:state==='queued'||!t?'아직 시작 안 함':n+' / '+total+'회 ('+Math.min(100,Math.floor(n/total*100))+'%)';return [guidedArmLabel(c)+' · seed '+c.seed,phaseLabel(!t&&c.state==='cancelled'?'cancelled':state)+(p.generation!=null?' · '+p.generation+'/'+p.requested_generations+'세대':''),counts,t?duration(t.elapsed_seconds)+(active(g)&&c.state==='running'?' · '+age+'초간 수치 변화 '+(age>=30?'없음 — 응답은 수신 중, 지연 확인 필요':'관찰 중'):''):'—'];}));
   for(const c of g.cells){const t=c.attempts.at(-1);if(!t?.run_id||!['completed','cancelled','time_limit','interrupted'].includes(c.state)||!t.artifact_sha256?.['manifest.json'])continue;const link=document.createElement('a');link.className='button';link.href='/live.html?contract='+encodeURIComponent(cid)+'&run='+encodeURIComponent(t.run_id);link.target='_blank';link.rel='noopener';link.textContent=guidedArmLabel(c)+' · '+(c.state==='completed'?'완료 결과':'중지까지의 부분 결과')+' 지도 열기'+(t.archive_count!=null?' · 누적 비지배 '+t.archive_count+'개':'');link.style.cssText='display:inline-block;margin:8px;padding:8px;border:1px solid #8caebf';progress.append(link);}
   const retry=g.cells.filter(c=>['failed','cancelled','time_limit','interrupted'].includes(c.state));if(retry.length&&!active(g)){text(done+'개 완료·저장 · '+retry.filter(c=>c.attempts.length).length+'개 중지·미완료 · '+retry.filter(c=>!c.attempts.length).length+'개 미실행. 저장 결과를 바로 열 수 있습니다. 다시 시작하면 미완료 실행은 새 시도로 계산됩니다.');dButton(progress,'guidedRetry','미완료 실행만 다시 시작',()=>act(async()=>{await api(cid,'engine/validations/'+g.validation_id+'/retry',{cell_ids:retry.map(c=>c.cell_id)});await refresh();}));jsonDetails(progress,'실패·중단 근거',retry);}
  }
  if(Object.keys(jobs).length){evidenceTable(progress,['검산','상태·단계','평가 진행'],Object.entries(jobs).map(([side,j])=>[side.toUpperCase(),j.status+' · '+j.phase,j.evaluated+' / '+(j.total??'범위 준비 중')]));
   for(const [side,j] of Object.entries(jobs))if(['STOPPED','INTERRUPTED'].includes(j.status))dButton(progress,'guidedResume'+side,side.toUpperCase()+' 저장 지점부터 검산 재개',()=>act(async()=>{jobs[side]=await api(cid,'engine/runs/'+cell[side+'_run_id']+'/quality-jobs/'+j.job_id+'/resume',{});await refresh();}));
   if(Object.values(jobs).some(j=>j.status==='ERROR')){text('검산 실패입니다. 개선 근거를 완료 결과로 사용하지 않습니다.');jsonDetails(progress,'검산 실패 원인',jobs);dButton(progress,'guidedCheckRetry','원인 확인 후 검산 접수 다시 확인',()=>act(async()=>{view='compare';await proceed();}));}
   else text(Object.keys(jobs).length===2&&Object.values(jobs).every(j=>j.status==='COMPLETED')?'두 배치 검산 완료. 활성 버튼을 눌러 성능 개선과 비용 절감을 비교하세요.':'검산 진행 또는 중지 상태입니다. 진행 수와 재개 버튼을 확인하세요.');
  }
  if(view==='checking'&&Object.keys(jobs).length<2)dButton(progress,'guidedMissingCheck','누락·미확정 검산 접수 확인',()=>act(async()=>{view='compare';await proceed();}));
  buttons();if(active(a)||active(b)||Object.values(jobs).some(j=>['RUNNING','QUEUED'].includes(j.status)))timer=setTimeout(refresh,3000);
 }catch(e){if(alive()&&ticket===epoch){text('진행 조회 실패: '+e.message+' · 서버 계산의 중지 여부는 확인되지 않았습니다. 5초 후 다시 조회합니다.');if(!$('guidedPollRetry'))dButton(progress,'guidedPollRetry','진행 상태 다시 조회',()=>act(refresh));timer=setTimeout(refresh,5000);}}finally{polling=false;if(refreshPending&&alive()){refreshPending=false;clearTimeout(timer);timer=setTimeout(refresh,0);}}}
 render();await act(histories);
}
const guidedEntry=document.createElement('button');guidedEntry.id='guidedResearch';guidedEntry.textContent='순서대로 연구';guidedEntry.onclick=()=>safe(openGuidedCostBudget)();$('calculate').before(guidedEntry);
const guidedSettings=renderSettings;renderSettings=function(){
 guidedSettings();const setup=$('resourceStudySetup'),edited=$('resourceStudyDraft');if(!setup)return;
 const panel=document.createElement('section');panel.id='resourceStudyActions';panel.setAttribute('aria-label','비용·예산 비교 연구');panel.style.cssText='display:grid;gap:12px;margin:18px 0;padding-top:14px;border-top:1px solid #c9dce5';
 const heading=document.createElement('h3');heading.textContent='비용·예산 비교 연구';heading.style.margin='0';panel.append(heading);setup.before(panel);
 const item=(button,label,description)=>{const box=document.createElement('div');box.style.cssText='display:grid;gap:6px';button.textContent=label;button.style.cssText='width:100%;white-space:normal;text-align:left';box.append(button);noteText(box,description);panel.append(box);};
 item(setup,edited?'저장 조건으로 연구 준비':'현재 조건으로 연구 준비',edited?'저장 실행 '+run.run_id.slice(0,8)+'의 조건을 사용합니다. 현재 편집값은 포함하지 않습니다.':'화면의 현재 조건을 사용합니다.');
 if(edited){item(edited,'편집 조건으로 연구 준비','편집 중인 센서·목표·탐색 설정을 기준으로 준비합니다.');edited.disabled=previewPending||!preview?.execution_supported;}
 else setup.disabled=previewPending||!preview?.execution_supported;
 noteText(panel,'이 비교 연구는 먼저 예산 제한 없이 비용을 탐색하고, 다음 단계에서 비교할 예산을 정합니다. 현재 예산으로 한 번 계산하려면 상단의 계산 실행을 누르세요.');
 noteText(panel,'여기서는 연구 계획만 엽니다. 계산은 연구 창의 시작 버튼을 눌러야 실행됩니다.');
};
const guidedTradeoff=renderTradeoff;renderTradeoff=function(host,...args){guidedTradeoff(host,...args);if($('resourceStudyFromTradeoff'))$('resourceStudyFromTradeoff').textContent='비용 목적 ↔ 예산 제약 · 순서대로 비교 연구';};
