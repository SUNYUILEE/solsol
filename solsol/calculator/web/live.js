'use strict';
const $=id=>document.getElementById(id), names={circle:'원형',square:'사각형',hexagon:'정육각형',overlap:'겹치는 두 원'}, states={queued:'계산 준비',running:'계산 중',saving:'결과 검증·저장 중',completed:'계산 완료',cancelled:'사용자 중지 · 부분 결과 보존',time_limit:'시간 제한 · 부분 결과 보존',failed:'실행 실패'};
states.initializing='LP 하한·초기 배치 준비 중 (최대 약 30초)';
const initNames={random:'무작위',greedy:'다중 우선비 Greedy + 무작위',milp:'MILP/ε + 무작위'};
const objectiveNames={binary_coverage_v1:'기준 충족 우선 탐색 · 절충 비교 제한',max_margin_quality_v3:'거리 여유 가설 · 비교 전용',zoned_nominal_v4:'중심·외곽 평가구역 가설 · 격리',full_area_tradeoff_v6:'전체 평가영역 3목적 절충 · 기준선 별도 판정',layered_mission_v7:'분리 평가구역 실험 · 외곽 탐지/내부 식별'};
let token='',problem=null,currentJob=null,last=null,selectedId=null,timer=null,previewSerial=0,pollSerial=0,viewLoadSerial=0,draftProblem=null,draftValid=false,failedView=null;
(()=>{
 const manual=document.querySelector('.manualInspection');if(typeof manual?.querySelector==='function'){const summary=manual.querySelector('summary');if(summary)summary.textContent='누적 Pareto 근사해 선택';const diagnosticText=$('diagnostics')?.parentElement?.querySelector?.('span');if(diagnosticText)diagnosticText.textContent='현재 세대 전체 진단 · 지배 배치 포함';}
 const details=document.querySelector('.inspectDisplayOptions'),controls=typeof details?.querySelector==='function'?details.querySelector('.inspectControls'):null;if(controls)details.open=true;
 const addToggle=(id,text,checked)=>{if(!controls||$(id))return;const label=document.createElement('label');label.innerHTML=`<input id="${id}" type="checkbox"${checked?' checked':''}><span>${text}</span>`;controls.insertBefore(label,$('inspectCenter'));};
 addToggle('inspectCandidateLabels','후보지 번호',false);addToggle('inspectDefense','평가영역 강조',true);
 if($('inspectCandidates')?.parentElement?.lastChild){$('inspectCandidates').checked=true;$('inspectCandidates').parentElement.lastChild.textContent=' 후보지 100곳';}
 if(typeof details?.querySelector==='function'&&details.querySelector('summary'))details.querySelector('summary').textContent='지도 표시 설정';
 if($('inspectCenter'))$('inspectCenter').textContent='지도 중심 맞춤';
 const mapControls=document.querySelector('#mapSection .sectionHead .viewControls'),mapAnchor=document.querySelector('#mapSection .inspectAction');
 if(mapControls&&mapAnchor){mapControls.classList.add('mapViewToolbar');mapControls.setAttribute('aria-label','배치 지도 표시 설정');mapAnchor.before(mapControls);}
})();
const keys=['radar','eo','shape','generations','design','refinement','h','seed','initializer','area_factor','identification_area_factor','resource_mode','radar_stock','eo_stock','map_km','candidate_count','site_seed','objective_contract'];
const isActive=()=>!!last&&['queued','initializing','running','saving'].includes(last.state);
function resourceOK(p,c){const m=c.resource_mode||'off';return m==='off'||p.sensor_counts.every((n,i)=>m==='all'?n===(i?c.eo_stock:c.radar_stock):n<=(i?c.eo_stock:c.radar_stock));}
function currentPoints(){return last?.current_population_points||[];}
function diagnosticPoints(){const seen=new Set();return [...(last?.points||[]),...currentPoints()].filter(p=>!seen.has(p.id)&&seen.add(p.id));}
function displayPoints(){if($('diagnostics')?.checked)return diagnosticPoints();const scope=$('solutionScope')?.value||'target_front',raw=LiveSelection.inScope(last?.points||[],scope).filter(p=>resourceOK(p,last?.config||{}));return $('localMinimal')?.checked&&problem?raw.filter(p=>LiveSelection.oneDeleteMinimal(problem,p,last?.config?.objective_contract)):raw;}
function displayFrontIds(){return $('diagnostics')?.checked?(last?.snapshot?.front_ids||[]):displayPoints().map(p=>p.id);}
function findPoint(id){return [...(last?.points||[]),...currentPoints()].find(p=>p.id===id)||null;}
function pairTradeoff(rows,a,b){let comparable=0,opposed=0;for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){const x=rows[i].F[a]-rows[j].F[a],y=rows[i].F[b]-rows[j].F[b];if(x&&y){comparable++;if(x*y<0)opposed++;}}return{comparable,opposed,rate:comparable?opposed/comparable:null};}
function objectiveDistribution(rows){
 const node=$('objectiveDistributionAudit')||(()=>{const n=document.createElement('div');n.id='objectiveDistributionAudit';n.className='explain';n.setAttribute('role','status');$('objectiveContractAudit').insertAdjacentElement('afterend',n);return n;})();
 if(!rows.length){node.textContent='결과가 생기면 세 목적의 고유값·범위와 쌍별 절충 정도를 계산합니다.';return;}
 const names=['탐지 목적','식별 목적','비용 목적'],stat=names.map((name,k)=>{const v=rows.map(p=>p.F[k]),u=new Set(v.map(x=>x.toPrecision(15))).size;return `${name} ${u}개 값 (${Math.min(...v).toFixed(4)}–${Math.max(...v).toFixed(4)})`;});
 const pairs=[[0,1,'탐지↔식별'],[0,2,'탐지↔비용'],[1,2,'식별↔비용']].map(([a,b,name])=>{const q=pairTradeoff(rows,a,b);return `${name} ${q.rate===null?'비교 불가':(100*q.rate).toFixed(1)+'%'}`;});
 const q=pairTradeoff(rows,0,1),aligned=q.rate!==null&&q.rate<.4;
 node.className='explain '+(aligned?'gridWarning':'qualityPass');
 node.textContent=`목적 분포 감사 · 중복 ID를 뺀 ${rows.length}개 표시행 · ${stat.join(' · ')}. 서로 한쪽이 좋아질 때 다른 쪽이 나빠진 비교쌍 비율: ${pairs.join(' · ')}. ${aligned?'탐지와 식별은 대부분 같은 방향으로 움직여 세 목적의 상호 절충이 충분하지 않습니다. NSGA-III 참조방향은 없는 충돌을 만들어내지 않습니다.':'현재 관측 범위에서는 탐지와 식별 사이에도 절충쌍이 나타납니다. 이것만으로 참 Pareto 전선이나 모든 설정의 충돌을 보장하지는 않습니다.'}`;
}
function objectiveExplanation(){
 const cfg=last?.config||config(),v3=cfg.objective_contract==='max_margin_quality_v3',v4=cfg.objective_contract==='zoned_nominal_v4',v6=cfg.objective_contract==='full_area_tradeoff_v6',v7=cfg.objective_contract==='layered_mission_v7',loaded=!!last;
 $('objectiveContractHelp').textContent=v7?'바깥 조기탐지 띠와 안쪽 식별 평가구역을 따로 평가합니다. 제한된 Radar를 두 평가구역에 배분할 때만 물리적 경쟁 가설이 성립합니다. 95%·90%는 성능 기준선입니다.':v6?'전체 평가영역의 탐지·식별·비용 절충을 모두 보존하고, 95%·90%는 기준충족 후보 판정선으로만 표시합니다.':v4?'이 중심·외곽 가설은 원래 연구문제와 달라 격리된 비교 계약입니다.':v3?'거리 여유 0.2는 고정 민감도 가설이며 탐지·식별 충돌을 충분히 만들지 못한 비교 계약입니다.':'전체 평가영역을 계산하지만 95%·90% 목표를 생존제약으로 강제합니다.';
 $('objectiveResultBadge').textContent=`${loaded?'현재 결과':'다음 계산'} · ${v7?'분리 평가구역 실험':v6?'전체 평가영역 3목적 절충':v4?'구역 분리 가설 · 격리':v3?'거리여유 · 비교 전용':'기준 충족 우선 탐색'}`;
 $('objectiveResultBadge').className='qualityDecision '+(loaded?(v7||v4||v3?'warning':'pass'):'neutral');
 $('objective1Title').textContent=v7?'외곽 조기탐지 손실 최소화':v4?'외곽 평가구역 탐지 손실 최소화':v3?'탐지 거리여유 손실 최소화':'탐지 손실 최소화';
 $('objective1Formula').textContent=v7?'f₁ = 1 − 외곽 탐지구역 Radar 커버율':v4?'f₁ = 1 − 외곽부 Radar 탐지율':v3?'f₁ = 1 − (0.8 × 명목 탐지율 + 0.2 × Radar 거리여유)':'f₁ = 1 − 명목 탐지율';
 $('objective1Description').textContent=v7?'바깥 탐지 경계와 안쪽 식별 경계 사이의 평가점 중 Radar 반경에 한 번 이상 들어온 비율입니다. 제한된 Radar를 외곽에 두면 조기탐지가 좋아지지만 안쪽 식별을 지원할 Radar가 줄 수 있습니다.':v4?'평가영역 중심에서 먼 평가점 절반 중 Radar 반경에 한 번 이상 들어온 비율입니다. 경계 관측을 나타내며 중복 커버는 한 번만 셉니다.':v3?'명목 탐지율은 Radar 반경 안의 평가점 비율입니다. 거리여유는 각 평가점에서 가장 유리한 Radar 하나의 q=max(0, 1−거리²/반경²)를 평균합니다. 여러 Radar의 값을 더하지 않습니다.':'Radar 반경 안에 들어온 평가점 비율이며 중복 커버는 한 번만 셉니다.';
 $('objective2Title').textContent=v7?'내부 평가구역 식별 손실 최소화':v4?'중심 평가구역 식별 손실 최소화':v3?'식별 거리여유 손실 최소화':'식별 손실 최소화';
 $('objective2Formula').textContent=v7?'f₂ = 1 − 내부 식별구역 Radar·EO/IR 공동 커버율':v4?'f₂ = 1 − 중심부 Radar·EO/IR 공동 식별률':v3?'f₂ = 1 − (0.8 × 명목 식별률 + 0.2 × Radar·EO/IR 거리여유)':'f₂ = 1 − 명목 식별률';
 $('objective2Description').textContent=v7?'안쪽 식별 평가구역의 점이 Radar와 EO/IR 반경에 모두 포함될 때만 식별로 셉니다. EO/IR만 배치하거나 외곽 Radar가 해당 점을 보지 못하면 식별 성능 충족으로 세지 않습니다.':v4?'평가영역 중심에서 가까운 평가점 절반 중 Radar와 EO/IR 반경에 모두 들어온 비율입니다. 외곽 탐지와 다른 공간 평가구역을 사용해 위치 절충을 만듭니다.':v3?'명목 식별률은 Radar와 EO/IR 반경에 모두 든 평가점 비율입니다. 거리여유는 가장 유리한 Radar와 EO/IR의 q 중 작은 값을 평가점별로 평균합니다. 이 값은 합성 품질이며 실제 검출확률이 아닙니다.':'Radar와 EO/IR 반경에 모두 들어온 평가점 비율이며 EO/IR만 있는 점은 식별 성능 충족으로 세지 않습니다.';
 const evidence=$('objectiveEvidence')||(()=>{const n=document.createElement('div');n.id='objectiveEvidence';n.className='objectiveEvidence';document.querySelector('.objectiveGrid').insertAdjacentElement('afterend',n);return n;})();
 evidence.innerHTML=v7?'<h3>왜 두 평가구역을 나누는가</h3><p>CWA 18150은 탐지·추적·식별 성능을 사용자 시나리오와 평가 요구에 맞춰 시험하도록 설명합니다. 열상·가시광 센서가 Radar보다 짧은 범위에서 식별 정보를 제공한다는 일반적 센서 특성을 단순화하여, 넓은 탐지 평가구역과 안쪽 식별 평가구역을 둔 합성 실험입니다. 동심원은 표준이 요구한 유일한 형상이 아니며 현실 절차를 재현하지 않습니다.</p><p><b>경쟁이 생기는 조건:</b> Radar 보유량 상한을 공유하므로 같은 Radar를 바깥 탐지와 안쪽 식별 지원에 동시에 최적으로 놓기 어려울 때입니다. 구역만 나누고 수량 제한을 끄면 과배치로 두 목적을 함께 포화시킬 수 있으므로 V7은 “일부 사용·수량 상한”에서만 실행됩니다.</p><p><a href="https://www.cencenelec.eu/media/CEN-CENELEC/CWAs/ICT/cwa-18150.pdf" target="_blank" rel="noreferrer">CWA 18150:2024 · DTI 시험방법 참고자료</a></p>':'';
  const rows=[...(last?.points||[]),...currentPoints()].filter((p,i,a)=>a.findIndex(q=>q.id===p.id)===i),ok=loaded&&rows.length&&rows.every(p=>{const q=v3?p.objective_performance:p.performance,targetOk=v6||v7||Math.abs(.95-p.performance[0]-p.G[0])<1e-12&&Math.abs(.90-p.performance[1]-p.G[1])<1e-12;return Math.abs(1-q[0]-p.F[0])<1e-12&&Math.abs(1-q[1]-p.F[1])<1e-12&&Math.abs(p.cost/800-p.F[2])<1e-12&&targetOk;});
  $('objectiveContractAudit').textContent=!loaded?'아직 결과가 없습니다. 새 계산을 시작하면 저장된 목적값과 화면 식을 행별로 대조합니다.':`${ok?'연결 검산 PASS':'연결 검산 FAIL'} · 실행 ${last.id} · ${rows.length}개 고유 표시행의 F₁·F₂·F₃를 재대조했습니다. ${v6||v7?'95%·90%는 G가 아니라 각 행의 기준충족 라벨과 초록 목표선으로 별도 검사합니다.':'이 계약은 목표 부족분을 G에 포함합니다.'}`;
 $('objectiveContractAudit').className='explain '+(loaded?(ok?'qualityPass':'gridWarning'):'');
 objectiveDistribution(rows);
}
function workspace(){
 if(typeof LiveProgress!=='undefined'&&(!last?.snapshot||failedView))LiveProgress.render(null,failedView||last);
 if(typeof LiveTiming!=='undefined')LiveTiming.render(failedView||last);
  const c=config(),f=last?.config||null,same=LiveWorkspace.same(f,c),m=c.resource_mode;
  const layered=c.objective_contract==='layered_mission_v7';
  const statusEl=$('identificationAreaStatus');
  if(statusEl){
   statusEl.textContent=layered?'현재 사용함':'사용 안 함';
   statusEl.className='fieldBadge '+(layered?'badgeActive':'badgeInactive');
  }
  $('identification_area_factor').disabled=!layered;
  $('identificationAreaField').hidden=false;
  $('missionAreaHelp').hidden=false;
  $('missionAreaHelp').textContent=layered?'바깥 평가 면적은 조기탐지 구역 전체, 식별 면적은 그 안의 식별 평가구역입니다. 식별 면적은 바깥 면적보다 작아야 합니다.':'현재 3목적 절충 목적식에서는 식별 면적을 별도 분리하지 않고 전체 평가 면적을 동일 적용합니다 (현재 목적식 미사용). V7 분리 평가구역 선택 시에만 별도 활성화됩니다.';
  $('area_factor').closest('label').childNodes[0].textContent=layered?'탐지 평가 면적':'평가 면적';
 $('resourceExplain').textContent=LiveWorkspace.describeResource(c);
 $('radar_stock').disabled=m==='off';$('eo_stock').disabled=m==='off';
 const extent=Math.max(last?.problem?.map_metres||20000,(c.map_km||20)*1000);
 $('beforeScale').innerHTML=LiveWorkspace.scaleMap(last?.problem||null,extent);
 $('afterScale').innerHTML=draftValid?LiveWorkspace.scaleMap(draftProblem,extent):'<div class="scaleEmpty">새 조건 확인 중 · 입력 오류가 있으면 안내를 확인하세요.</div>';
 $('scaleCaption').textContent=`동일 축척: 두 그림 모두 0–${extent/1000} km 축을 사용합니다. 흰 영역은 해당 지도, 회색은 지도 밖입니다. 중앙 R·E 원은 크기 비교용이며 설치 결과가 아닙니다. 보라 경계는 평가영역, ◆는 ${c.candidate_count}개 후보지입니다.`;
 $('candidates').parentElement.lastChild.textContent=` 후보지 ${problem?.sites?.length??c.candidate_count}곳`;
 $('scenarioMetrics').innerHTML=LiveWorkspace.scenario(draftValid?draftProblem:null,c);
 $('searchSummary').textContent=`${objectiveNames[c.objective_contract]} · ${c.design} 설계 · H${c.h} · ${c.generations}세대 · ${initNames[c.initializer]}`;
 $('inventorySummary').textContent=LiveWorkspace.resourceNames[m]+(m==='off'?'':` · R${c.radar_stock} / E${c.eo_stock}대`);
 if(draftValid){const d=LiveWorkspace.difficulty(draftProblem),u=draftProblem.upper_bound;const geometricReach=u.performance[0]>=.95-1e-10&&u.performance[1]>=.90-1e-10;$('scenarioValidation').textContent=!geometricReach?'도달 한계: 보유 수량을 무시하고 모든 후보를 사용해도 성능 기준에 미달합니다. 반경·지도·평가영역을 검토하세요.':d.ratios[0]>=.95?'Radar 한 대로 탐지 기준을 충족할 수 있는 조건입니다. 다중 배치를 비교하려면 면적을 더 키워 보세요.':'Radar 여러 대의 결합이 필요한 조건입니다. 보유 수량 내 실제 기준 충족은 실행 후 확인하세요.';if(c.objective_contract==='zoned_nominal_v4'){const matched=c.shape==='square'&&c.area_factor===1.5&&c.radar===4&&c.eo===2&&c.map_km===20&&c.candidate_count===100&&c.eo_stock===20;if(matched&&c.radar_stock===6)$('scenarioValidation').textContent='V4 탐색 근거가 있는 비교 조건입니다. 50세대·2개 seed의 제한 실험에서 바깥 탐지 95–97%, 중심 식별 90–100%, 비용 64–76점의 누적 경험적 비지배 해가 관측됐습니다. 참 Pareto 또는 수렴 인증은 아닙니다.';else if(matched&&[7,8].includes(c.radar_stock))$('scenarioValidation').textContent=`V4 민감도 비교 범위입니다. Radar 상한 ${c.radar_stock}대에서는 기준 충족과 더 넓은 성능 범위가 관측됐지만 R6보다 탐지 포화가 늘었습니다. 동일 seed·NFE 비교 결과를 실행 기록과 함께 해석하세요.`;else $('scenarioValidation').textContent='V4는 이 조건에서도 계산할 수 있지만 현재 다중 seed 민감도 근거 범위 밖입니다. 검증된 비교 조건은 사각형 150%, R4/E2 km, 후보 100곳, 일부 사용 R6/E20입니다.';}}
 $('configDiff').innerHTML=LiveWorkspace.rows(f,c,last?.problem,draftValid?draftProblem:null);
 $('draftStatus').textContent=!draftValid?'새 조건 확인 중 · 실행할 수 없습니다':!f?'입력 조건 미리보기':same?'현재 결과와 동일한 조건':'변경사항 있음 · 계산 시작 시 적용';
 const legacySquare=!!f&&f.shape==='square'&&!f.geometry_contract;
 $('draftStatus').classList.toggle('isChanged',!!f&&!same);$('restoreConfig').disabled=!f||same;
 $('restoreConfig').textContent=legacySquare?'새 동일면적 기준으로 가져오기':'현재 조건 복원';
 $('restoreConfig').title=legacySquare?'이 저장 실행은 과거 6 km × 6 km 사각형입니다. 버튼을 누르면 다른 도형과 같은 면적의 새 사각형 입력으로 변환하며, 과거 결과 자체는 바꾸지 않습니다.':'';
 $('resultContext').textContent=f?`현재 결과: ${objectiveNames[f.objective_contract||'binary_coverage_v1']} 목적 · ${f.map_km??20}km 지도 · 후보 ${f.candidate_count??100}곳 · ${f.site_seed?'배치 '+f.site_seed:'기본 배치'} · ${names[f.shape]} ${last.problem.geometry.area_km2.toFixed(2)} km² · Radar 반경 ${f.radar} km / EO/IR ${f.eo} km · ${LiveWorkspace.resourceNames[f.resource_mode||'off']} · ${f.design} / H${f.h} · 실행 ${last.id.slice(0,8)}. ${same?'위 입력과 같은 조건입니다.':'위에서 변경한 입력은 아직 이 결과에 적용되지 않았습니다.'}`:'입력 지도만 준비되었습니다. 실제 배치는 계산 후 ID를 선택해야 표시됩니다.';
 objectiveExplanation();
 if(failedView)failedEmptyView(failedView);
}
function drawChoices(point){
 if(!point){$('selectionReason').textContent='배치 목록 또는 그래프에서 배치를 선택하세요.';$('contributionRows').innerHTML='';$('contributionSummary').textContent='배치 선택 후 한 대씩 삭제했을 때의 영향을 표시합니다.';return;}
 const archived=last.snapshot.archive_ids.includes(point.id),front=last.snapshot.front_ids.includes(point.id);
 const targetOK=LiveSelection.targetQualified(point);
 $('selectionReason').textContent=`선택 배치 #${point.id} · 그래프의 빨간 점과 선택 배치 지도에 표시. ${archived&&targetOK?'정량목표를 통과한 누적 관측 경험적 비지배 해':!targetOK?'현재 세대 목표 미달 진단 배치':front?'현재 세대 비지배 진단 배치':'현재 세대에서 지배되는 진단 배치'}. 참 Pareto 또는 전역 최적 인증은 아닙니다.`;
 const rows=LiveSelection.contributions(problem,point,last.config.objective_contract),redundant=rows.filter(r=>r.removableWithoutLoss);
 $('contributionSummary').classList.toggle('warning',redundant.length>0);
 $('contributionSummary').textContent=`배치 #${point.id}: 설치 ${rows.length}대. 한 대씩 검사했을 때 탐지·식별을 모두 유지하며 삭제 가능한 센서 ${redundant.length}대. ${redundant.length?'성능을 유지하면서 비용을 낮출 가능성이 있습니다.':'단일 삭제에서는 두 성능을 유지하는 비용 개선이 없습니다. 이동·교환이나 여러 대의 조합 개선까지 배제하는 검사는 아닙니다.'}`;
 $('contributionRows').innerHTML=rows.map(r=>`<tr><td>${r.site} / ${r.type?'EO/IR':'Radar'}</td><td>${r.xy.map(v=>(v/1000).toFixed(2)).join(', ')}</td><td>${r.covered}개</td><td>${r.lostD}개 (${(100*r.lostD/r.detectionN).toFixed(2)}%p)</td><td>${r.lostI}개 (${(100*r.lostI/r.identificationN).toFixed(2)}%p)</td><td>${r.afterD>=.95&&r.afterI>=.90?'통과':'미달'}${r.removableWithoutLoss?' · 성능 동일':''}</td></tr>`).join('');
}
function config(){const c={};keys.forEach(k=>c[k]=['shape','design','refinement','initializer','resource_mode','objective_contract'].includes(k)?$(k).value:$(k).value===''?NaN:+$(k).value);c.geometry_contract='equal_area_v2';return c;}
function options(){return{layer:$('layer').value,candidates:$('candidates').checked,demand:$('demand').checked,defense:$('defense').checked,candidateLabels:$('candidateLabels').checked};}
const readJson=LiveTransport.create({totalMs:180000,attemptMs:60000,delays:[1000,4000]}),recoveringReads=new Set();
function connectionNotice(){const node=$('connectionNotice');node.hidden=!recoveringReads.size;node.textContent=recoveringReads.size?'연결 복구 중 · 마지막 지도와 선택을 유지하며 결과를 다시 조회합니다.':'';}
function configActivityNode(){
 let node=$('configActivity');
 if(node)return node;
 node=document.createElement('p');node.id='configActivity';node.setAttribute('role','status');node.setAttribute('aria-live','polite');
 document.querySelector('.runBar .actions')?.insertAdjacentElement('beforebegin',node);
 return node;
}
function configActivity(kind,text){
 const node=configActivityNode();if(!node)return;
 const colors={checking:['#fff6df','#b86a00','#704400'],ready:['#eef9f3','#248357','#175d3d'],failed:['#fff2ef','#b83221','#7e1d12']},c=colors[kind]||['#f2f8fb','#1976a4','#244b63'];
 node.className='configActivity '+kind;node.textContent=text;node.style.cssText=`margin:0 0 12px;padding:12px 14px;border:1px solid ${c[1]};border-left:5px solid ${c[1]};background:${c[0]};font-weight:700;color:${c[2]}`;
}
function validateView(d){
 const array=Array.isArray;
 const base=d&&typeof d.id==='string'&&d.config&&Number.isInteger(d.config.generations)&&d.problem&&array(d.problem.sites)&&array(d.problem.demand)&&array(d.points)&&array(d.current_population_points)&&array(d.history);
 const s=d?.snapshot;
 const frame=s===null||(s&&Number.isInteger(s.generation)&&Number.isFinite(s.evaluations)&&array(s.front_ids)&&array(s.population_ids)&&array(s.archive_ids));
  const contract=d?.config?.objective_contract||'binary_coverage_v1';
  const v6=contract==='full_area_tradeoff_v6'||contract==='layered_mission_v7',gMinimum=v6?0:2;
  const points=base&&d.points.every(p=>p&&Number.isInteger(p.id)&&array(p.mask)&&p.mask.length===d.problem.sites.length&&p.mask.every(v=>Number.isInteger(v)&&v>=0&&v<=3)&&array(p.performance)&&p.performance.length===2&&p.performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)&&(contract==='binary_coverage_v1'||v6||(array(p.objective_performance)&&p.objective_performance.length===2&&p.objective_performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)))&&array(p.F)&&p.F.length===3&&p.F.every(Number.isFinite)&&array(p.G)&&p.G.length>=gMinimum&&p.G.every(Number.isFinite)&&Number.isFinite(p.cost)&&array(p.sensor_counts)&&p.sensor_counts.length===2);
  const pointShape=p=>p&&Number.isInteger(p.id)&&array(p.mask)&&p.mask.length===d.problem.sites.length&&p.mask.every(v=>Number.isInteger(v)&&v>=0&&v<=3)&&array(p.performance)&&p.performance.length===2&&p.performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)&&(contract==='binary_coverage_v1'||v6||(array(p.objective_performance)&&p.objective_performance.length===2&&p.objective_performance.every(v=>Number.isFinite(v)&&v>=0&&v<=1)))&&array(p.F)&&p.F.length===3&&p.F.every(Number.isFinite)&&array(p.G)&&p.G.length>=gMinimum&&p.G.every(Number.isFinite)&&Number.isFinite(p.cost)&&array(p.sensor_counts)&&p.sensor_counts.length===2;
  const currentOk=base&&d.current_population_points.every(pointShape);
  const ids=points?d.points.map(p=>p.id):[],currentIds=base?d.current_population_points.map(p=>p.id):[],uniqueIds=new Set(ids),population=new Set(s?.population_ids||[]),archive=new Set(s?.archive_ids||[]),front=new Set(s?.front_ids||[]),uniqueMasks=new Set(base?d.points.map(p=>p.mask.join(',')):[]);
  const complete=!s||(uniqueIds.size===ids.length&&uniqueMasks.size===ids.length&&ids.every(id=>archive.has(id))&&[...archive].every(id=>uniqueIds.has(id))&&currentIds.length===population.size&&new Set(currentIds).size===currentIds.length&&currentIds.every(id=>population.has(id))&&[...population].every(id=>currentIds.includes(id))&&[...front].every(id=>population.has(id))&&(v6||d.points.every(p=>p.qualified)));
  const numeric=points&&currentOk&&[...d.points,...d.current_population_points].every(p=>{const q=contract==='max_margin_quality_v3'?p.objective_performance:p.performance,targetRelation=v6?true:Math.abs(.95-p.performance[0]-p.G[0])<1e-12&&Math.abs(.90-p.performance[1]-p.G[1])<1e-12,qualification=v6?p.performance[0]>=.95-1e-10&&p.performance[1]>=.90-1e-10:p.G.every(v=>v<=1e-10);return Math.abs((1-q[0])-p.F[0])<1e-12&&Math.abs((1-q[1])-p.F[1])<1e-12&&targetRelation&&Math.abs(p.cost/800-p.F[2])<1e-12&&p.qualified===qualification;});
  if(!base||!frame||!points||!complete||!numeric)throw Error('배치 응답에 필요한 자료 또는 ID·목적값·제약·세대 연결이 완전하지 않습니다. 기존 지도와 선택을 유지합니다.');
}
async function request(path,body){
 const id=crypto.randomUUID();
 try{
  for(let attempt=0;attempt<2;attempt++){
   try{return await readJson(path,{body,headers:body===undefined?{}:{'Content-Type':'application/json','X-Run-Token':token,'X-Request-ID':id},onRetry:()=>{recoveringReads.add(id);connectionNotice();}});}
   catch(e){
    if(e.status===403&&body!==undefined&&attempt===0){const c=await request('/api/config');token=c.token;continue;}
    if(e.status===409&&path==='/api/jobs'){const active=await request('/api/config');if(active.active){$('activeRun').hidden=false;$('activeRun').href='/live.html?run='+active.active;}}
    throw e;
   }
  }
 }finally{recoveringReads.delete(id);connectionNotice();}
}
function researchTerms(message){return String(message||'').replaceAll('최적 방어배치','Pareto 센서 배치 해').replaceAll('방어 배치','센서 배치 해').replaceAll('방어영역','평가영역').replaceAll('방어 영역','평가영역').replaceAll('방어구역','평가영역').replaceAll('방어 면적','평가 면적').replaceAll('운용구역','구역별').replaceAll('임무 성공률','성능 기준 충족률').replaceAll('임무 목표','성능 기준').replaceAll('운용목표','성능 기준').replaceAll('임무성능','모델 성능').replaceAll('작전 시나리오','실험 시나리오').replaceAll('위협 시나리오','입력 시나리오');}
function fail(e){const message=researchTerms(e.message);$('error').hidden=false;$('error').textContent=message;$('reconnect').disabled=false;if(!draftValid){$('scenarioValidation').textContent=message;$('draftStatus').textContent='입력 조건 확인 필요 · 현재 결과는 그대로 유지됩니다';}}
function failureMessage(d){
 const messages={STORAGE_PERMISSION:'저장 위치에 쓸 수 없습니다. 결과 폴더의 쓰기 권한과 파일 잠금을 확인한 뒤 새 계산을 시작하세요.',STORAGE_FULL:'저장 공간이 부족합니다. 디스크 여유 공간을 확보한 뒤 새 계산을 시작하세요.',SAVED_DATA_INVALID:'저장 결과의 무결성을 확인하지 못했습니다. 이 실행의 결과를 사용하지 말고 다른 저장 실행을 선택하세요.'};
 return `실행 ${d.id} · ${messages[d.failure?.code]||'계산 또는 결과 저장을 끝내지 못했습니다. 다른 저장 실행을 열거나 실행 번호로 관리자에게 점검을 요청하세요.'} 이 실행은 저장 완료로 확인되지 않았습니다.`;
}
function verificationText(d){
 const evaluated=d.audit?.raw_replay==='PASS'?'계산값 검산 완료':'계산값 검산 미확인';
 const stored=d.state==='failed'||d.persistence?.state==='failed'?'저장 실패 · 결과 사용 불가':d.persistence?.state==='verified'?'저장 완료':'저장 대기';
 return `실행 ${d.id} · ${evaluated} · ${stored}`;
}
function failedEmptyView(d){
 if(typeof LiveInitialContext!=='undefined')LiveInitialContext.clear();
 if(typeof LivePointPicker!=='undefined')LivePointPicker.invalidate();
 if(typeof LiveExport!=='undefined')LiveExport.update(null,null,null,null);
 if(typeof LiveInspector!=='undefined')LiveInspector.update(null,null,null,null);
 LiveReplay.render(null);
 $('status').textContent='실패한 실행 · 다른 저장 실행을 열거나 새 계산을 시작하세요.';
 $('download').hidden=true;$('progress').value=0;
 for(const id of ['checkpoint','previous','next','mapPlay','mapPrevious','mapNext'])$(id).disabled=true;
 $('jobs').value=d.id;$('resultContext').textContent=`실행 ${d.id} · 저장 실패 · 검증된 배치를 불러올 수 없습니다.`;
 $('mapReadout').textContent='표시 불가';$('generationReadout').textContent='세대 자료 사용 불가';$('dockGeneration').textContent='저장 실패';
 $('replayNote').textContent='이 실패 기록은 세대별 재생을 제공하지 않습니다.';$('frameStatus').textContent='계산을 기다리는 상태가 아닙니다. 다른 저장 실행을 선택하세요.';
 $('runId').textContent=verificationText(d);$('mode').textContent='저장 실패 · 검증된 배치 없음';
 $('initialTitle').textContent='시작 배치 · 표시할 수 없음';$('currentTitle').textContent='실행 실패 · 배치 표시 불가';
 $('initialText').textContent='이 실패 기록에는 검증된 초기 배치가 제공되지 않습니다.';
 $('currentText').textContent='배치가 0개라는 뜻이 아닙니다. 저장 완료되지 않은 결과는 지도에 표시하지 않습니다.';
 for(const id of ['initialMap','currentMap'])$(id).innerHTML='<div class="empty selectionEmpty">검증된 배치 자료 없음 · 다른 저장 실행을 선택하세요.</div>';
 $('initialComposition').textContent='실패 기록 · 초기 집단 표시 불가';$('initialComparison').textContent='정상 저장 실행을 불러오면 초기·후속 세대를 비교할 수 있습니다.';
 $('stats').innerHTML='<div class="stat">결과 상태<b>검증된 배치 자료 없음</b></div>';
 for(const id of ['scatter','trend'])$(id).innerHTML='<div class="empty">실패한 실행에는 표시할 검증된 결과가 없습니다.</div>';
 $('selectionReason').textContent='이 실패 기록에서는 배치를 선택하거나 재생할 수 없습니다.';
}
function initExplanation(){$('initExplain').textContent=`${initNames[config().initializer]}: `+{random:'초기 개체는 전부 무작위입니다. 비교용 LP 비용 하한만 계산하며 그 숫자를 배치로 주입하지 않습니다.',greedy:'탐지와 식별의 구성 우선비 21개를 결정론적으로 비교해 목표를 통과하는 Greedy 배치를 찾습니다. 가장 낮은 목표 부족분, 낮은 비용 순으로 원본을 고르고 작은 변형과 함께 최대 25%를 주입하며 나머지는 무작위로 채웁니다. 이 우선비는 초기 배치 구성용이며 세 목적함수의 가중치가 아닙니다.',milp:'탐지/식별 목표 95/90, 100/90, 100/100마다 최대 5초 MILP를 풀어 정수 배치를 준비합니다. 원본과 작은 변형은 최대 25%, 나머지는 무작위입니다. 준비 비용은 진화 비용과 따로 표시합니다.'}[config().initializer];}
function bounds(){const info=last?.initialization;if(!info){$('seedSummary').textContent=last?'초기화 비용 자료가 아직 없거나 제공되지 않는 실행입니다.':'계산 후 초기화 비용을 표시합니다.';$('boundRows').innerHTML='';return;}const seedOutcome=info.method!=='random'&&info.seed_count===0?' · 실제 준비 배치 0개: 이 실행은 무작위 초기집단과 동일하게 시작했습니다. 초기화 방법 이름만으로 seeded 실행으로 해석하지 마세요.':'';$('seedSummary').textContent=`${initNames[info.method]} · 준비 ${info.seconds}초 · 개체 ${info.population}개 중 실제 주입 ${info.seed_count}개 (원본 ${info.original_seed_count}개, 나머지는 목표 통과 변형)${seedOutcome} · 준비 평가 ${info.preparation_evaluations}회 · Greedy 후보 점수 검사 ${info.greedy_score_trials}회 · 현재 진화 평가 ${last.snapshot?.evaluations??0}회. LP/MILP 내부 계산은 준비 시간에 포함되며 진화 평가 횟수로 환산하지 않습니다.`;$('boundRows').innerHTML=info.targets.map((r,i)=>{const eligible=(last.points||[]).filter(p=>resourceOK(p,last.config)&&p.performance.every((v,j)=>v>=r.targets[j]-1e-10));const best=eligible.length?Math.min(...eligible.map(p=>p.cost)):null;const lb=r.lower_bound;return `<tr><td>${r.targets.map(v=>(v*100).toFixed(0)+'%').join(' / ')}</td><td>${lb===null?'미확정':lb.toFixed(2)+'점'}</td><td>${r.upper_bound===null?'배치 없음':r.upper_bound+'점'}</td><td>${best===null?'이 세대는 미달':best+'점'}</td><td>${best===null||lb===null?'—':(best-lb).toFixed(2)+'점 ('+(100*(best-lb)/Math.max(Math.abs(lb),1e-12)).toFixed(1)+'%)'}</td><td>${r.cost_optimal_certified?'해당 요구수준 최소비용 일치':r.milp_status===1?'MILP 시간제한 · 현재 경계':r.milp_status===0?'MILP 최적 종료':info.method==='greedy'?'Greedy 상한 / LP 하한':'LP 하한만'} · ${r.seconds}초</td></tr>`;}).join('');$('boundNote').textContent='전부 사용 모드에서 비용 하한과 상한의 일치는 고정된 설치비용만 확인하며 최상의 배치 위치를 증명하지 않습니다. 차이 = 현재 세대에서 해당 요구수준을 통과한 최저 비용 − 같은 요구수준의 하한. 괄호는 하한 대비 비율이며 실제 최적비용과의 정확한 차이는 아닙니다. 현재 세대 비용이 준비 상한보다 낮다면 준비 원본보다 저렴한 배치입니다. 초기화 변형에서 이미 개선되었을 수 있으므로 진화가 새로 개선했는지는 0세대 최저비용과 원시 생성시점을 함께 확인해야 합니다.';}
function solutionOptions(){
 const ids=new Set(displayFrontIds());
  const raw=displayPoints();
  let points=typeof LiveFrontInsight==='undefined'?LiveSelection.costOrdered(raw):LiveFrontInsight.uniquePoints(raw);
  if(selectedId!==null&&typeof LiveFrontInsight!=='undefined')points=points.map(p=>p.duplicateIds?.includes(selectedId)?{...p,id:selectedId}:p);
 if(selectedId!==null&&!points.some(p=>p.id===selectedId))selectedId=null;
 const placeholder=last?.snapshot?'배치를 선택하세요':'계산 후 선택할 수 있습니다';
  const isMargin=last?.config?.objective_contract==='max_margin_quality_v3';
  const option=(p,rank,total)=>`<option value="${p.id}">비용순 ${rank}/${total} · #${p.id} · 비용 ${p.cost}점 · 탐지 ${LiveCore.pct(p.performance[0])} / 식별 ${LiveCore.pct(p.performance[1])} · ${LiveSelection.targetQualified(p)?'목표 통과':'목표 미달 · 진단'}${ids.has(p.id)?($('diagnostics').checked?' · 현재세대 비지배':' · 누적 비지배'):''}${isMargin?` · 거리품질 ${LiveCore.pct(p.objective_performance[0])}/${LiveCore.pct(p.objective_performance[1])}`:''}${p.occurrences>1?' · 동일 X '+p.occurrences+'회':''}</option>`;
  const target=points.filter(LiveSelection.targetQualified),other=points.filter(p=>!LiveSelection.targetQualified(p));
  const groups=[];
  if(target.length)groups.push(`<optgroup label="목표통과 누적 비지배 · ${target.length}개 · 비용 낮은 순">${target.map((p,i)=>option(p,i+1,target.length)).join('')}</optgroup>`);
  if(other.length)groups.push(`<optgroup label="목표 미달 절충·진단 · ${other.length}개 · 비용 낮은 순">${other.map((p,i)=>option(p,i+1,other.length)).join('')}</optgroup>`);
  const html=`<option value="">${placeholder}</option>`+groups.join('');
 for(const k of ['solution','plotSolution']){$(k).innerHTML=html;$(k).value=selectedId===null?'':String(selectedId);$(k).disabled=!last?.snapshot;}
  const costs=points.map(p=>p.cost),costRange=costs.length?(Math.min(...costs)===Math.max(...costs)?`${costs[0]}점`:`${Math.min(...costs)}–${Math.max(...costs)}점`):'없음';
  $('solutionCount').textContent=last?.snapshot?($('diagnostics').checked?`현재 세대 진단 ${points.length}개 · 목표통과 ${target.length}개 · 비용 ${costRange}. 지배 배치가 포함될 수 있습니다.`:$('solutionScope')?.value==='target_front'?`목표통과 누적 비지배 ${target.length}개 · 비용 낮은 순 · 비용 범위 ${costRange} · 0–${last.snapshot.generation}세대 ${last.snapshot.evaluations.toLocaleString()}회 평가${$('localMinimal').checked?' · 한 대 삭제 과배치 제외':''}.`:`전체 누적 비지배 ${points.length}개 · 목표통과 ${target.length}개 · 비용 낮은 순 · 비용 범위 ${costRange} · 목표 미달 절충은 별도 묶음.`):'계산된 배치가 아직 없습니다.';
}
function renderOverlap(preferred){
 const visible=displayPoints();$('showSelectedMap').disabled=selectedId===null||!visible.some(p=>p.id===selectedId);
 const mode=$('chartType').value,groups=LiveCore.pointGroups(visible,mode,$('metric').value,last?.config?.objective_contract||'binary_coverage_v1').filter(g=>g.length>1);
 const chosen=groups.find(g=>String(g[0].id)===preferred)||groups.find(g=>g.some(p=>p.id===selectedId))||groups.find(g=>String(g[0].id)===$('overlapGroup').value)||groups[0];
 $('plotOverlapSummary').textContent=!last?.snapshot?'계산 후 겹친 배치를 확인할 수 있습니다.':groups.length?`${visible.length}개 배치 중 ${groups.reduce((n,g)=>n+g.length,0)}개가 ${groups.length}곳의 같은 좌표에 겹칩니다. ${mode==='2d'?'2D에서 숨긴 모델 성능은 서로 다를 수 있습니다.':'탐지·식별·비용이 정확히 같은 배치들입니다. 그 외 시점에 따른 가림도 생길 수 있습니다.'} 가려진 배치를 아래 목록에서 선택하면 지도와 빨간 점이 바뀝니다.`:'같은 목적 좌표의 배치가 없습니다. 점 크기나 3D 시점 때문에 가려지면 전체 배치 ID 목록을 사용하세요.';
 $('overlapControls').hidden=!groups.length;
 $('overlapGroup').innerHTML=groups.map(g=>`<option value="${g[0].id}">${g.length}개 배치 · 비용 ${g[0].cost}점 · ${mode==='2d'?($('metric').value==='d'?'탐지 ':'식별 ')+LiveCore.pct(g[0].performance[$('metric').value==='d'?0:1]):'탐지 '+LiveCore.pct(g[0].performance[0])+' / 식별 '+LiveCore.pct(g[0].performance[1])}</option>`).join('');
 $('overlapGroup').value=chosen?String(chosen[0].id):'';
 $('overlapSolution').innerHTML='<option value="">지도에서 볼 배치 선택</option>'+(chosen||[]).map(p=>`<option value="${p.id}">#${p.id} · Radar ${p.sensor_counts[0]}대 / EO/IR ${p.sensor_counts[1]}대 · 탐지 ${LiveCore.pct(p.performance[0])} / 식별 ${LiveCore.pct(p.performance[1])}</option>`).join('');
 $('overlapSolution').value=chosen?.some(p=>p.id===selectedId)?String(selectedId):'';
 $('overlapDetail').textContent=chosen?`이 묶음은 배치 ID ${chosen.length}개, 서로 다른 설치 구성 ${new Set(chosen.map(p=>JSON.stringify(p.mask))).size}개입니다. ${mode==='2d'?'표시한 두 좌표가 같아도 숨긴 모델 성능과 설치 위치는 다를 수 있습니다.':'목적값이 같아도 설치 위치가 다를 수 있습니다.'}`:'';
}
function explain(){areaOptions();const c=config(),P={7:36,12:92,19:212}[c.h],bits=2*c.candidate_count;$('budgetNote').textContent=`개체 ${P}개 × (초기 1회 + 업데이트 ${c.generations}회) = 검색 평가 ${(P*(1+c.generations)).toLocaleString()}회. 최대 300초. 설정 변경은 다음 새 실행에 적용됩니다.${c.refinement==='target_delete_v1'?' 비용 정련의 삭제 후보 검사는 검색 NFE와 별도 노력으로 기록합니다.':''}`;$('designExplain').textContent={A:`A · 후보지마다 Radar / EO/IR 설치 여부를 ${bits}개의 스위치로 봅니다. 교차 확률 90%: 각 스위치를 부모 중 하나에서 독립적으로 가져옵니다. 이후 평균 1.5번 무작위 스위치를 뒤집습니다.`,B:`B · ${c.candidate_count}개 후보지의 [Radar, EO/IR] 두 스위치를 후보지별 묶음으로 봅니다. 교차 확률 90%: 같은 후보지의 두 스위치를 같은 부모에게서 받습니다. 이후 평균 1.5번 스위치를 뒤집습니다. A와 달라지는 것은 교차 단위입니다.`,C:`C · ${c.candidate_count}개 후보지 묶음 교차 확률 20%. 이후 삭제 50% / 같은 종류 센서 이동 30% / 추가 20% 중 하나를 무작위로 시도합니다.${c.refinement==='target_delete_v1'?' 그 뒤 95%·90%를 이미 만족한 자식에서 목표를 유지하는 장비 한 대를 최대 한 번 제거하고, 공식 평가와 기존 NSGA-III 생존선택을 그대로 통과시킵니다.':' 삭제·이동·추가 대상을 무작위로 선택합니다.'}`}[c.design];objectiveExplanation();}
function areaOptions(){const v=$('area_factor').value||'1',base=36*Math.PI;$('area_factor').innerHTML=[.5,.75,1,1.5,2,2.5,3].map(f=>`<option value="${f}">${f*100}% · ${(base*f).toFixed(2)} km²${f===1?' · 기준':''}</option>`).join('');$('area_factor').value=v;}
function meta(p){const g=p.geometry,u=p.upper_bound,rs=p.resources;$('geometryNote').textContent=`${names[g.kind]} 평가 면적 ${g.area_km2.toFixed(2)} km² · 500m 평가점 ${p.demand.length}개. ${g.kind==='square'?'한 변 '+(g.side/1000).toFixed(2)+' km.':g.kind==='circle'?'반경 '+(g.radius/1000).toFixed(2)+' km.':'같은 면적의 원형과 비교할 수 있습니다.'} 수량 제한을 무시하고 모든 후보에 설치한 기하학적 최대: 탐지 ${LiveCore.pct(u.performance[0])}, 식별 ${LiveCore.pct(u.performance[1])}. ${rs?'이 값은 입력 보유량으로 달성 가능한 성능이라는 뜻이 아닙니다. 자원 제약을 포함한 실행 결과와 경계를 확인하세요.':u.qualified?'이 표본 지도는 수량 제한 없는 목표 통과 배치가 존재합니다.':'이 표본 지도는 모든 후보에 설치해도 목표에 미달합니다.'}`;}
function fineEvidence(point){const a=typeof LIVE_AREA_AUDITS==='undefined'?null:LIVE_AREA_AUDITS[last?.id];const box=$('gridEvidence');if(typeof LiveGridCheck!=='undefined'){box.textContent='목록·그래프·원래 성능은 500m 평가 결과입니다. 아래에서 선택 배치의 평가 간격 민감도를 별도로 확인할 수 있습니다.';box.className='explain';return;}if(!point||!a||a.id!==point.id){box.textContent='평가 해상도: 500m · 이 배치의 250m 추가 검증 자료 없음';box.className='explain';return;}box.className='explain'+(a.pass?'':' gridWarning');box.textContent=`동일 배치 #${point.id} · 250m 간격으로 별도 검산: 탐지 ${LiveCore.pct(a.performance[0])}, 식별 ${LiveCore.pct(a.performance[1])} · ${a.pass?'95%/90% 목표 유지':'목표 미달 — 500m 판정만으로 영역 전체의 목표 달성을 보증할 수 없습니다'}. 같은 설치 위치를 평가한 값입니다. 250m 평가도 표본 기반입니다.`;}
// Graph navigation changes focus only; activation selects the saved raw ID.
function plotNodes(){return Array.from($('scatter').querySelectorAll?.('[data-id]')||[]).sort((a,b)=>+a.dataset.id-+b.dataset.id);}
function plotAccessibility(focusId){
 const nodes=plotNodes(),entry=nodes.find(n=>+n.dataset.id===(focusId??selectedId))||nodes[0];
 const svg=$('scatter').querySelector?.('svg');
 if(svg){svg.setAttribute('role','group');svg.setAttribute('aria-describedby','plotKeyboardHelp');}
 nodes.forEach(n=>{n.setAttribute('tabindex',n===entry?'0':'-1');n.setAttribute('aria-pressed',String(+n.dataset.id===selectedId));});
 if(focusId!==undefined){
  entry?.focus({preventScroll:true});
  $('plotFocusStatus').textContent=entry&&+entry.dataset.id!==focusId?`배치 #${focusId}는 이 세대에 없습니다. 초점을 #${entry.dataset.id}로 이동했습니다. 배치를 선택하려면 Enter를 누르세요.`:'';
 }
}
function selectPlot(c,keyboard=false){
 if(!c||!displayPoints().some(p=>p.id===+c.dataset.id))return;
 const id=+c.dataset.id;LiveReplay.stop();selectedId=id;$('diagnostics').checked=true;LiveReplay.remember();draw();
 if(keyboard)plotAccessibility(id);
}
function pausePlotPicking(){
 clearTimeout(timer);LiveReplay.stop();$('follow').checked=false;
 return ()=>{if(isActive()){clearTimeout(timer);timer=setTimeout(()=>poll(+$('checkpoint').value),700);}};
}
function plotKey(e){
 const c=e.target.closest('[data-id]');if(!c)return;
 if(e.key==='Escape'){e.preventDefault();$('plotSolution').focus();return;}
 if(e.key==='Enter'||e.key===' '){e.preventDefault();selectPlot(c,true);return;}
 if(!['ArrowRight','ArrowLeft','ArrowUp','ArrowDown','Home','End'].includes(e.key))return;
 const nodes=plotNodes(),i=nodes.indexOf(c);if(i<0)return;e.preventDefault();
 const j=e.key==='Home'?0:e.key==='End'?nodes.length-1:Math.max(0,Math.min(nodes.length-1,i+(['ArrowRight','ArrowDown'].includes(e.key)?1:-1)));
 plotAccessibility(+nodes[j].dataset.id);
}
function draw(){
 if(typeof LivePointPicker!=='undefined')LivePointPicker.invalidate();
 const plotFocusId=$('scatter').contains?.(document.activeElement)?document.activeElement?.dataset?.id:undefined;
 if(!problem)return;
 workspace();
 if(failedView)return;
  bounds();solutionOptions();renderOverlap();if(typeof LiveFrontInsight!=='undefined')LiveFrontInsight.render(last,selectedId);
 const selectedPoint=findPoint(selectedId),point=selectedPoint||LiveReplay.observationPoint(),s=last?.snapshot,visible=displayPoints();
 if(typeof LiveSolutionQuality!=='undefined')LiveSolutionQuality.update(request,last,selectedPoint,problem,s?.generation);
 if(typeof LiveExport!=='undefined')LiveExport.update(null,null,null,null);
 if(typeof LiveInspector!=='undefined')LiveInspector.update(problem,selectedPoint,last,s?.generation);
 if(typeof LiveGridCheck!=='undefined')LiveGridCheck.update(problem,selectedPoint,last,s?.generation);
 const outcome=LiveWorkspace.outcome(selectedPoint,last,problem);$('outcomeSummary').textContent=outcome.summary;$('outcomeRows').innerHTML=outcome.html;$('runLimits').textContent=LiveWorkspace.limits(last);
 drawChoices(selectedPoint);fineEvidence(selectedPoint);
 if(selectedPoint&&last.config.resource_mode==='all')$('contributionSummary').textContent='전부 사용 실험에서는 한 대 삭제가 보유량 전부 설치 조건을 위반합니다. 아래 표는 성능 기여만 보여주는 진단이며, 삭제를 허용하는 개선안이나 비용 절감으로 해석하지 않습니다.';
 LiveReplay.render(point);
 $('currentMap').innerHTML=point?LiveCore.map(problem,point,options()):'<div class="empty selectionEmpty">아직 배치를 선택하지 않았습니다.<br>배치 목록 또는 그래프에서 선택하세요.</div>';
 $('scatter').innerHTML=s?LiveCore.scatter(visible,selectedId,displayFrontIds(),$('chartType').value,$('metric').value,$('angle').value,last.config.objective_contract||'binary_coverage_v1'):'<div class="empty">계산 후 누적 좋은 배치들이 표시됩니다.</div>';
 plotAccessibility(plotFocusId===undefined?undefined:+plotFocusId);
 const history=(last?.history||[]).filter(x=>s&&x.generation<=s.generation);
 $('trend').innerHTML=s?LiveCore.trend(history):'<div class="empty">계산 후 세대별 비용 통계가 표시됩니다.</div>';
 $('traceRows').innerHTML=history.slice(-100).map(x=>`<tr><td>${x.generation}</td><td>${x.evaluations.toLocaleString()}</td><td>${x.qualified_count}</td><td>${x.current_cost??'목표 통과 없음'}</td><td>${x.best_cost??'아직 없음'}</td></tr>`).join('');
  const perf=point?LiveSelection.performance(problem,point.mask,last.config.objective_contract):null,r=perf?.[0]??null,e=perf?.[1]??null;
  const counts=point?[point.mask.filter(q=>q&1).length,point.mask.filter(q=>q&2).length]:null,cost=counts?6*counts[0]+2*counts[1]:null;
  if(point&&(Math.abs(r-point.performance[0])>1e-10||Math.abs(e-point.performance[1])>1e-10||cost!==point.cost||counts.some((n,i)=>n!==point.sensor_counts[i])))throw Error('지도 재계산과 원시 성능·비용이 다릅니다. 표시를 신뢰하지 마세요.');
  if(!selectedPoint){
  $('stats').innerHTML='<div class="stat">분석 배치 선택<b>선택 대기</b></div>'+(point?[['자동 관찰 ID','#'+point.id],['탐지',LiveCore.pct(point.performance[0])],['식별',LiveCore.pct(point.performance[1])],['비용',point.cost+'점']].map(([k,v])=>`<div class="stat autoObservationStat">${k}<b>${v}</b></div>`).join(''):'');
  $('currentTitle').textContent=point?`${s.generation}세대 자동 관찰 · #${point.id}`:'선택 배치';
  $('currentText').textContent=point?`세대 변화를 보기 위한 관찰 배치입니다. 최고·권장·대표해가 아니며 분석 해로 선택되지 않았습니다.\n탐지 ${LiveCore.pct(point.performance[0])} · 식별 ${LiveCore.pct(point.performance[1])} · 비용 ${point.cost}점`:s?`${s.generation}세대 · 목록과 그래프에서 고를 수 있습니다.`:'계산 전입니다.';
  $('placementExplain').textContent=point?'지도는 세대 관찰용 배치를 보여줍니다. 상세 검산·다운로드할 분석 배치는 목록이나 그래프에서 직접 선택하세요.':'배치 선택 후 설치 구성과 비용을 표시합니다.';
  $('gridEvidence').textContent='배치 선택 후 평가 해상도를 표시합니다.';
  return;
 }
 $('stats').innerHTML=[['탐지 / 목표 95%',LiveCore.pct(point.performance[0])],['식별 / 목표 90%',LiveCore.pct(point.performance[1])],['합성 비용',point.cost+'점'],['Radar 설치',point.sensor_counts[0]+'대'],['EO/IR 설치',point.sensor_counts[1]+'대'],['500m 표본 판정',point.qualified?'통과':'미달']].map(([k,v])=>`<div class="stat">${k}<b>${v}</b></div>`).join('');
 $('currentTitle').textContent=`${s.generation}세대 배치 · #${point.id}`;
 $('currentText').textContent=`탐지 ${LiveCore.pct(point.performance[0])} · 식별 ${LiveCore.pct(point.performance[1])} · 비용 ${point.cost}점\nRadar ${point.sensor_counts[0]}대 · EO/IR ${point.sensor_counts[1]}대\n${point.qualified?'목표 통과':'목표 미달 · 탐색 중'} · ${LiveReplay.isAutomatic()?'자동 관찰':'직접 선택'}`;
 // Automatic observation is display-only. Only an explicit analytical selection
 // may be promoted into the derived "selected placement" export.
 if(typeof LiveExport!=='undefined')LiveExport.update(problem,last,selectedPoint,{chart_type:$('chartType').value,metric:$('metric').value,angle:$('angle').value,layer:$('layer').value,selection_mode:'manual'});
 const zone=LiveSelection.zones(problem,last.config.objective_contract),covered=[Math.round(point.performance[0]*zone.detectionN),Math.round(point.performance[1]*zone.identificationN)],zoneText=['zoned_nominal_v4','layered_mission_v7'].includes(last.config.objective_contract)?`바깥 탐지구역 ${covered[0]}/${zone.detectionN}점 · 안쪽 식별구역 ${covered[1]}/${zone.identificationN}점. 보라색 바깥 경계는 탐지 평가구역, 청록색 안쪽 경계는 식별 평가구역입니다.`:`전체영역 탐지 ${covered[0]}/${zone.detectionN}점 · 식별 ${covered[1]}/${zone.identificationN}점.`;
 $('placementExplain').textContent=`커버 평가: ${zoneText} 비용 = Radar ${counts[0]}대×6 + EO/IR ${counts[1]}대×2 = ${cost}점 (목적함수 비용값 ${(cost/800).toFixed(4)}). ${cost===0?'두 센서 모두 미설치한 실제 계산해입니다. 탐지·식별 0%이므로 목표 미달입니다.':''} 기호가 겹치면 살짝 벌리지만 커버 원 중심은 실제 후보 좌표입니다.`;
}
function busy(on){
 $('run').disabled=on||!draftValid;$('cancel').disabled=!on;$('loadJob').disabled=on;
 clearTimeout(busy.paintTimer);busy.paintTimer=setTimeout(()=>{const node=$('status'),animate=on&&!/실패|오류|중지 요청/.test(node.textContent);runStatus(node.textContent,animate);},0);
}
function runStatus(text,active=false){
 const node=$('status');node.textContent=text;node.classList.toggle('isBusy',active);
 if(active){const pulse=document.createElement('span');pulse.className='loadingPulse';pulse.setAttribute('role','status');pulse.setAttribute('aria-label','로딩 중');pulse.innerHTML='로딩 중... <i aria-hidden="true">▌</i>';node.append(' ',pulse);}
}
function generationMode(d,follow){
 if(d.state==='failed'||d.persistence?.state==='failed')return '실행 또는 저장 검증 실패 · 표시 중인 부분 결과는 정상 저장 결과가 아닙니다';
 const saved=Math.max(0,d.latest_generation),requested=d.config.generations;
 if(['queued','initializing','running'].includes(d.state))return follow?'현재 계산 따라가기 · 진행 이력은 아직 파일 저장 전':`계산 중 이력 다시 보기 · 현재 ${saved} / 요청 ${requested}세대 · 파일 저장 전`;
 if(d.state==='saving')return '마지막 세대 검증·저장 중 · 다운로드 준비 전';
 if(!['completed','cancelled','time_limit'].includes(d.state)||d.persistence?.state!=='verified'||d.persistence?.download_allowed!==true)return '결과 보존 확인 전 · 저장 상태를 확인하세요';
 if(!follow)return `저장된 세대 다시 보기 · 마지막 저장 ${saved} / 요청 ${requested}세대`;
 if(d.state==='cancelled')return `중지한 실행의 마지막 저장 세대 · ${saved} / 요청 ${requested}세대`;
 if(d.state==='time_limit')return `시간 제한까지 저장한 세대 · ${saved} / 요청 ${requested}세대`;
 if(d.state==='completed')return `요청한 ${requested}세대 계산 종료 · 마지막 저장 세대`;
 return '실행 상태 확인 필요 · 저장 결과를 확인하세요';
}
function generationReadout(d){
 const s=d?.snapshot;if(!s)return '세대 자료 대기';
 const latest=Math.max(0,d.latest_generation),active=['queued','initializing','running'].includes(d.state);
 const failed=d.state==='failed'||d.persistence?.state==='failed';
 const stored=['completed','cancelled','time_limit'].includes(d.state)&&d.persistence?.state==='verified'&&d.persistence?.download_allowed===true;
 const label=failed?'보존 검증 실패':active?'계산 중 이력 · 파일 저장 전':d.state==='saving'?'결과 검증·저장 중':stored?'보존된 결과':'보존 확인 전';
 return `${s.generation}세대 / 현재 ${latest}세대 · 누적 ${s.evaluations.toLocaleString()}회 평가 · ${label}`;
}
async function preview(){const serial=++previewSerial;draftValid=false;$('run').disabled=true;explain();initExplanation();workspace();try{const c=config();if(['radar_stock','eo_stock'].some(k=>!Number.isInteger(c[k])||c[k]<0||c[k]>100))throw Error('보유 장비 수는 종류별 0~100의 정수로 입력하세요. 빈칸은 0이 아닙니다.');if(!Number.isInteger(c.seed)||c.seed<0||c.seed>2147483647)throw Error('난수 시드는 0~2147483647 정수로 입력하세요.');if(c.objective_contract==='layered_mission_v7'&&c.identification_area_factor>=c.area_factor)throw Error('식별 평가 면적은 탐지 평가 면적보다 작게 선택하세요.');if(c.objective_contract==='layered_mission_v7'&&c.resource_mode!=='partial')throw Error('V7 분리 평가구역은 제한된 Radar 배분 경쟁을 검사하므로 “보유 수량 이내 일부 사용”을 선택하세요.');if(c.objective_contract==='zoned_nominal_v4'&&c.resource_mode!=='partial')throw Error('V4 구역별 절충은 “보유 수량 이내 일부 사용”을 선택해야 합니다. 제한 끔은 과배치를 허용하고 전부 사용은 비용을 고정하므로 비용 절충을 확인할 수 없습니다.');if(c.objective_contract==='zoned_nominal_v4'&&c.initializer==='greedy')throw Error('V4의 Greedy 초기화는 아직 같은 중심·바깥 목적함수로 검증되지 않았습니다. 무작위 또는 MILP/ε 초기화를 선택하세요.');const p=await request('/api/preview',c);if(serial!==previewSerial)return;draftProblem=p;draftValid=true;if(!last)problem=p;meta(p);draw();$('run').disabled=isActive();$('error').hidden=true;if(!last&&!failedView){$('status').textContent='계산 준비 완료';$('download').hidden=true;$('mode').textContent='조건 미리보기';$('checkpoint').disabled=true;$('previous').disabled=true;$('next').disabled=true;$('progress').value=0;$('runId').textContent='실행 기록 없음';}if(failedView)fail(Error(failureMessage(failedView)));}catch(e){if(serial!==previewSerial)return;draftValid=false;workspace();$('run').disabled=true;fail(e);}}
async function poll(generation,prepared){if(!currentJob)return;const serial=++pollSerial,job=currentJob,failureFallback=failedView;try{const d=prepared?.data||await request('/api/jobs/'+job+(generation===undefined?'':'?generation='+generation));if(job!==currentJob||serial!==pollSerial)return;if(d.id!==job)throw Error('요청한 실행과 받은 실행이 다릅니다. 기존 지도와 선택을 유지합니다.');validateView(d);const zero=prepared?prepared.zero:await LiveReplay.initialFor(d);if(d.id!==currentJob||serial!==pollSerial)return;LiveReplay.accept(d,zero);failedView=null;last=d;LiveReplay.choose();problem=d.problem;meta(draftProblem||problem);const active=['queued','initializing','running','saving'].includes(d.state);busy(active);$('cancel').disabled=!['queued','initializing','running'].includes(d.state);$('status').textContent=`${states[d.state]} · ${Math.max(0,d.latest_generation)} / ${d.config.generations}세대 · ${d.seconds}초`;$('runId').textContent=verificationText(d);$('progress').value=100*Math.max(0,d.latest_generation)/d.config.generations;$('download').hidden=active||d.state==='failed'||d.persistence?.download_allowed!==true;$('download').href='/api/jobs/'+d.id+'/download';$('error').hidden=true;const failed=d.state==='failed'||!!d.error;if(failed){clearTimeout(timer);LiveReplay.stop();fail(Error(failureMessage(d)));$('status').textContent=d.state==='failed'?'실행 실패 · 저장 완료되지 않음':'저장 결과 확인 실패 · 결과 사용 불가';}bounds();if(!d.snapshot)draw();
if(d.snapshot){
if(![...d.points,...d.current_population_points].some(p=>p.id===selectedId))selectedId=null;$('checkpoint').innerHTML=d.history.map(s=>`<option value="${s.generation}">${s.generation}세대 · ${s.evaluations.toLocaleString()}회 평가</option>`).join('');$('checkpoint').value=d.snapshot.generation;$('checkpoint').disabled=false;$('previous').disabled=d.snapshot.generation===0;$('next').disabled=d.snapshot.generation>=d.latest_generation;$('mode').textContent=generationMode(d,$('follow').checked);draw();}
clearTimeout(timer);if(active&&!LiveReplay.isPlaying())timer=setTimeout(()=>poll($('follow').checked?undefined:+$('checkpoint').value),700);else await jobs();return true;}catch(e){if(serial!==pollSerial||job!==currentJob)return;clearTimeout(timer);LiveReplay.stop();if(failureFallback){failedView=failureFallback;last=null;currentJob=null;selectedId=null;LiveReplay.reset();if(typeof history!=='undefined')history.replaceState(null,'','/live.html?run='+failureFallback.id);failedEmptyView(failureFallback);}fail(e);$('status').textContent='연결 또는 실행 오류 · 아래 오류를 확인하세요.';return false;}}
async function jobs(){if(typeof LiveRunArchive!=='undefined')return LiveRunArchive.refresh(request,last,currentJob||failedView?.id);const rows=await request('/api/jobs');$('jobs').innerHTML=rows.length?rows.slice().reverse().map(j=>`<option value="${j.id}">${LiveCore.resourceLabel(j.config)} · ${initNames[j.config.initializer||'random']} · ${j.config.map_km??20}km 지도 · ${names[j.config.shape]} · 면적 ${(j.config.area_factor??1)*100}% · R${j.config.radar}/E${j.config.eo} · ${j.config.design} · H${j.config.h} · ${j.config.generations}세대 · ${states[j.state]} · ${j.id.slice(0,8)}</option>`).join(''):'<option value="">실행 기록 없음</option>';if(currentJob||failedView)$('jobs').value=currentJob||failedView.id; if(typeof LiveRunComparison!=='undefined')LiveRunComparison.render(rows,last);}
$('run').onclick=async()=>{try{++previewSerial;$('error').hidden=true;busy(true);$('status').textContent='새 계산 요청 중 · 입력 조건을 고정하고 있습니다.';$('activeRun').hidden=true;const cfg=config(),d=await request('/api/jobs',cfg);LiveReplay.reset();++viewLoadSerial;++pollSerial;currentJob=d.id;failedView=null;if(typeof history!=='undefined')history.replaceState(null,'','/live.html?run='+d.id);problem=d.problem;last=null;selectedId=null;if(typeof LiveExport!=='undefined')LiveExport.update(null,null,null,null);$('follow').checked=true;await poll();}catch(e){busy(false);if(failedView)failedEmptyView(failedView);fail(e);}};
$('cancel').onclick=async()=>{try{await request('/api/jobs/'+currentJob+'/cancel',{});$('status').textContent='중지 요청 · 진행 중인 세대 저장 후 멈춥니다.';$('cancel').disabled=true;}catch(e){fail(e);}};
keys.forEach(k=>$(k).addEventListener('change',preview));['layer','candidates','candidateLabels','defense','demand','chartType','metric','angle'].forEach(k=>$(k).addEventListener('change',()=>{try{draw();}catch(e){fail(e);}}));
['radar_stock','eo_stock','seed','site_seed'].forEach(k=>$(k).addEventListener('input',preview));
$('shuffleSites').onclick=()=>{const old=+String($('site_seed').value||0);let next=crypto.getRandomValues(new Uint32Array(1))[0]&0x7fffffff;if(next===old)next=(old+1)&0x7fffffff;$('site_seed').value=String(next||1);preview();};
$('largeMap').onchange=()=>document.querySelector('.maps').classList.toggle('large', $('largeMap').checked);
$('fitMap').onchange=()=>document.querySelector('.maps').classList.toggle('fit', $('fitMap').checked);
if(typeof LiveInspector!=='undefined')LiveInspector.init();
if(typeof LivePointPicker!=='undefined')LivePointPicker.bind();
 if(typeof LiveExport!=='undefined')LiveExport.bind();
if(typeof LiveGridCheck!=='undefined')LiveGridCheck.init();
$('checkpoint').onchange=()=>LiveReplay.seek(+$('checkpoint').value);$('previous').onclick=()=>LiveReplay.seek(Math.max(0,+$('checkpoint').value-1));$('next').onclick=()=>LiveReplay.seek(+$('checkpoint').value+1);$('follow').onchange=()=>{LiveReplay.stop();poll($('follow').checked?undefined:+$('checkpoint').value);};
$('scatter').addEventListener('click',e=>{if(typeof LivePointPicker!=='undefined')LivePointPicker.handle(e,()=>last,id=>selectPlot(plotNodes().find(n=>+n.dataset.id===id),true),pausePlotPicking);else selectPlot(e.target.closest('[data-id]'));});$('scatter').addEventListener('keydown',plotKey);
function selectFrom(id){LiveReplay.stop();selectedId=$(id).value===''?null:+$(id).value;LiveReplay.remember();draw();}
$('solution').onchange=()=>selectFrom('solution');$('solutionScope').onchange=()=>{LiveReplay.stop();selectedId=null;LiveReplay.choose();draw();};$('localMinimal').onchange=()=>{LiveReplay.stop();if(selectedId!==null&&!displayPoints().some(p=>p.id===selectedId))selectedId=null;LiveReplay.choose();draw();};$('diagnostics').onchange=()=>{LiveReplay.stop();selectedId=null;LiveReplay.choose();draw();};
$('plotSolution').onchange=()=>selectFrom('plotSolution');
$('overlapGroup').onchange=()=>{LiveReplay.stop();renderOverlap($('overlapGroup').value);};
$('overlapSolution').onchange=()=>{if($('overlapSolution').value!=='')selectFrom('overlapSolution');};
$('showSelectedMap').onclick=()=>{if(selectedId!==null)document.querySelector('.maps')?.scrollIntoView?.({block:'start',behavior:'instant'});};
// Do not replace a visible run until both its selected and initial snapshots are available.
async function loadStoredRun(id,viewSerial,preserveView=false){
 const keep=preserveView&&last?.id===id&&last.snapshot;
 const savedFollow=$('follow').checked;
 const d=await request('/api/jobs/'+id+(keep?'?generation='+last.snapshot.generation:''));
 if(viewSerial!==viewLoadSerial)return false;
 if(d.id!==id)throw Error('요청한 실행과 받은 실행이 다릅니다. 기존 결과를 유지합니다.');
 if(d.error||d.state==='failed'){
  if(!last){
   failedView=d;
   if(typeof history!=='undefined')history.replaceState(null,'','/live.html?run='+id);
   await preview();
   if(viewSerial!==viewLoadSerial)return false;
   failedEmptyView(d);
  }
  const e=Error(failureMessage(d)+(last?' 현재 보고 있던 배치와 선택은 유지됩니다.':''));e.failedRun=true;throw e;
 }
 validateView(d);const zero=await LiveReplay.initialFor(d);
 if(viewSerial!==viewLoadSerial)return false;
 if(currentJob!==id){LiveReplay.reset();selectedId=null;}
 ++pollSerial;currentJob=id;
 if(typeof history!=='undefined')history.replaceState(null,'','/live.html?run='+id);
 $('follow').checked=keep?savedFollow:true;if(!keep)setConfig(d.config);explain();initExplanation();
 const accepted=await poll(undefined,{data:d,zero});
 if(accepted===false)return false;
 if(viewSerial!==viewLoadSerial)return false;
 await preview();return true;
}
$('loadJob').onclick=async()=>{
 const target=$('jobs').value;if(!target)return;
 const viewSerial=++viewLoadSerial;++previewSerial;LiveReplay.stop();clearTimeout(timer);
 try{await loadStoredRun(target,viewSerial);}
 catch(e){if(viewSerial!==viewLoadSerial)return;
  if(last){$('jobs').value=last.id;$('status').textContent='실행을 불러오지 못했습니다. 기존 배치와 선택을 유지합니다.';}
  else if(failedView)failedEmptyView(failedView);
  fail(e);
 }
};
function setConfig(c){const defaults={area_factor:1,identification_area_factor:.5,initializer:'milp',resource_mode:'partial',radar_stock:10,eo_stock:21,map_km:20,candidate_count:100,site_seed:0,objective_contract:'full_area_tradeoff_v6',refinement:'off'};keys.forEach(k=>{if(k==='generations'&&!Array.from($(k).options).some(o=>+o.value===c[k]))$(k).add(new Option(c[k]+'세대 (저장 실행)',c[k]));$(k).value=c[k]??defaults[k];});draftValid=false;}
$('restoreConfig').onclick=async()=>{if(!last)return;setConfig(last.config);await preview();};
async function connect(first=false){
 const viewSerial=++viewLoadSerial;LiveReplay.stop();clearTimeout(timer);
 try{
  const c=await request('/api/config');if(viewSerial!==viewLoadSerial)return;
  token=c.token;$('error').hidden=true;busy(false);if(first)setConfig(c.default);
  await jobs();if(viewSerial!==viewLoadSerial)return;
  const initialParams=first?new URLSearchParams(location.search):null;
  const id=(initialParams?.get('run'))||currentJob||failedView?.id||c.active||$('jobs').value;
  if(id){
   const p=await request('/api/jobs/'+id+'/progress');if(viewSerial!==viewLoadSerial)return;
   if(['queued','initializing','running','saving'].includes(p.state)){
    currentJob=id;failedView=null;if(first)setConfig(p.config);if(typeof history!=='undefined')history.replaceState(null,'','/live.html?run='+id);
    await preview();if(viewSerial===viewLoadSerial)await poll();
   }else{++previewSerial;await loadStoredRun(id,viewSerial,!first);}
  }else await preview();
 }catch(e){if(viewSerial!==viewLoadSerial)return;$('run').disabled=e.failedRun?(!draftValid||isActive()):true;$('status').textContent=e.failedRun?'실패한 실행 · 다른 저장 실행을 열거나 새 계산을 시작하세요.':'실행 연결 실패 · 저장된 실행을 선택하거나 다시 연결하세요.';fail(e);}
}
// Poll a compact state endpoint while a run is preparing or publishing.  The
// full map/archive payload is loaded only when it can change the visible map,
// preventing overlapping 40k-row archive derivations from looking like a
// calculation failure.
const fullResultPoll=poll;let lastFullResultPoll=0;
poll=async function(generation,prepared){
 if(prepared||generation!==undefined)return fullResultPoll(generation,prepared);
 if(!currentJob)return;
 const job=currentJob;
 try{
  const p=await request('/api/jobs/'+job+'/progress');if(job!==currentJob)return;
  if(['queued','initializing','saving'].includes(p.state)){
   busy(true);$('cancel').disabled=p.state==='saving';
   const label=p.state==='saving'?'계산 완료 · 결과 검산과 저장 중':states[p.state];
   $('status').textContent=`${label} · ${Math.max(0,p.latest_generation)} / ${p.requested_generations}세대 · ${p.seconds??0}초`;
   $('runId').textContent=`실행 ${p.id} · ${p.state==='saving'?'계산값 검산·저장 진행 중':'계산 진행 상태 확인됨'}`;
   $('progress').value=100*Math.max(0,p.latest_generation)/Math.max(1,p.requested_generations);
   $('error').hidden=true;clearTimeout(timer);timer=setTimeout(()=>poll(),1000);return true;
  }
  if(p.state==='running'&&Date.now()-lastFullResultPoll<1800){
   $('status').textContent=`계산 중 · ${Math.max(0,p.latest_generation)} / ${p.requested_generations}세대 · ${p.seconds??0}초`;
   clearTimeout(timer);timer=setTimeout(()=>poll(),700);return true;
  }
  lastFullResultPoll=Date.now();return fullResultPoll();
 }catch(e){
  if(job!==currentJob)return false;clearTimeout(timer);
  $('status').textContent='상태 조회 지연 · 계산 중단 여부는 확인되지 않았습니다';
  $('runId').textContent=`실행 ${job} · 마지막 지도 유지 · 자동 재확인 중`;
  configActivity('checking','계산 상태를 다시 확인하고 있습니다. 새 계산을 중복 요청하지 않습니다.');
  timer=setTimeout(()=>poll(),2500);return false;
 }
};

// Make setting work visible next to the action buttons.  draftStatus is the
// single source of truth already updated by preview(); this observer mirrors
// it into a persistent, high-contrast operation state.
const draftObserver=new MutationObserver(()=>{
 const text=$('draftStatus')?.textContent||'';
 if(text.includes('확인 중'))configActivity('checking','설정 변경 확인 중 · 지도·후보·자원 조건을 계산하고 있습니다.');
 else if(text.includes('확인 필요'))configActivity('failed','설정 변경 오류 · 안내 내용을 수정해야 새 계산을 시작할 수 있습니다.');
 else configActivity('ready',isActive()?'설정 변경 준비 완료 · 현재 계산이 끝나면 새 조건으로 실행할 수 있습니다.':'설정 변경 준비 완료 · 계산 시작을 누르면 이 조건을 적용합니다.');
});
if($('draftStatus'))draftObserver.observe($('draftStatus'),{childList:true,characterData:true,subtree:true});
document.addEventListener('change',e=>{if(keys.includes(e.target?.id))configActivity('checking','설정 변경 감지 · 새 조건을 확인하고 있습니다.');},true);
document.addEventListener('input',e=>{if(['radar_stock','eo_stock','seed','site_seed'].includes(e.target?.id))configActivity('checking','입력 변경 감지 · 값과 계산 가능 범위를 확인하고 있습니다.');},true);

LiveReplay.bind();if(typeof LiveRunArchive!=='undefined')LiveRunArchive.bind(()=>jobs());$('reconnect').onclick=()=>connect();connect(true);

/* Keep the product navigation synchronized with the visible work area. */
(()=>{const nav=document.querySelector('.labNav');if(!nav)return;const links=[...nav.querySelectorAll('a[href^="#"]')];const pairs=links.map(link=>{const target=document.querySelector(link.getAttribute('href'));const section=target?.closest('section')||target;return section?{link,section}:null;}).filter(Boolean);const activate=link=>{links.forEach(item=>item.removeAttribute('aria-current'));link.setAttribute('aria-current','location');link.scrollIntoView({block:'nearest',inline:'nearest'});};links.forEach(link=>link.addEventListener('click',()=>activate(link)));if(!('IntersectionObserver'in window)||!pairs.length){if(links[0])activate(links[0]);return;}const visible=new Map();const observer=new IntersectionObserver(entries=>{entries.forEach(entry=>visible.set(entry.target,entry.isIntersecting?entry.intersectionRatio:0));const current=pairs.filter(pair=>(visible.get(pair.section)||0)>0).sort((a,b)=>(visible.get(b.section)||0)-(visible.get(a.section)||0))[0];if(current)activate(current.link);},{rootMargin:'-15% 0px -65% 0px',threshold:[0,.1,.25,.5]});pairs.forEach(pair=>observer.observe(pair.section));activate(links.find(link=>link.hash===location.hash)||links[0]);})();
