'use strict';
const domainFetchRun=fetchRun;
fetchRun=async function(id,g=null){const cid=draft.sensor;await domainFetchRun(id,g);if(cid===draft.sensor&&run?.run_id===id){const url=new URL(location.href);url.searchParams.set('contract',cid);url.searchParams.set('run',id);if(url.href!==location.href)history.replaceState(null,'',url);}};
// One domain selector for the common calculator; historical runs remain immutable.
function installationDomainChoice(){
 draft.research??={};draft.research.installationDomains??={};
 return draft.research.installationDomains[draft.sensor]==='model_supported'?'model_supported':'model';
}
const domainRequest=requestConfiguration;
requestConfiguration=function(){const mode=installationDomainChoice();if(mode==='model_supported')selection().solver_policy='generic_v1';return {...domainRequest(),installation_domain:mode};};
const domainSettings=renderSettings;
renderSettings=function(){domainSettings();if(!registryData||!draft.research||!['common','objectives','optimizer'].includes(setting))return;
 const g=document.createElement('section');g.className='settingGroup';g.id='installationDomainSettings';$('settingsBody').prepend(g);
 const h=document.createElement('h3');h.textContent='설치 후보와 평가영역';g.append(h);
 const support=registered()?.sensor_support||registryData.ui_models?.[draft.sensor]?.model?.sensor_support;
 const enabled=support?.status==='SUPPORTED'&&support.version==='SENSOR_SUPPORT_V1';
 const options=[['model','전체 설치 가능 후보에서 위치 최적화'],...(enabled||installationDomainChoice()==='model_supported'?[['model_supported','새 탐색: Model이 안전하게 제외한 무기여 슬롯 사용 안 함']]:[])];
 selectControl(g,'설치 위치',options,installationDomainChoice(),v=>{draft.research.installationDomains[draft.sensor]=v;if(v==='model_supported')selection().solver_policy='generic_v1';updateDraft();renderSettings();},'installationDomain');
 noteText(g,'평가영역 밖의 센서도 영역 관측에 기여할 수 있습니다. 영역 밖이라는 이유만으로 제외하지 않습니다. 수량과 예산은 별도 설정을 따릅니다.');
 if(installationDomainChoice()==='model_supported')noteText(g,'새 실행에서만 공개 Model 증명에 따른 안전 제외 마스크를 적용합니다. 양의 최소 수량이 필요한 센서는 보수적으로 유지하며, 남긴 슬롯이 모든 배치에서 유용하다는 뜻은 아닙니다. 반경·조건이 바뀌면 증명을 다시 확인합니다. 과거 원시는 변경하지 않습니다.');
 if(!enabled)noteText(g,'현재 모델 연결에서 안전 제외 capability를 확인하지 못했습니다. 기존 전체 후보 방식은 사용할 수 있습니다.');
 if(configurationSummary?.objective_projection?.excluded.length)noteText(g,'고정 비용은 탐색 방향에서 제외합니다. 성능 목적 '+configurationSummary.objective_projection.effective_indices.length+'개를 최적화하며 비용은 결과에 보존합니다.');
 const d=configurationSummary?.installation_domain;if(d&&d.mode===installationDomainChoice())noteText(g,`설치 가능 후보 ${d.eligible_sites} / ${d.candidate_count}곳 · 허용 센서 슬롯 ${d.active_slots}개`);
 if(installationDomainChoice()==='model_supported')noteText(g,'지도 후보점: 청록 = 허용 센서 슬롯 있음 · 흐린 회색 = 모든 슬롯 탐색 제외. 센서별 마스크는 확정 실행 근거에 보존합니다.');
};
const domainMap=mapHTML;
mapHTML=function(p,row){const html=domainMap(p,row),d=p?.calculator_installation_domain;if(!['inside_area','model_supported'].includes(d?.mode))return html;
 const doc=document.createElement('div');doc.innerHTML=html;
 for(const point of doc.querySelectorAll('circle[data-site]')){const slots=d.safe_search_allowed||d.allowed;const allowed=slots?.[+point.dataset.site-1]?.some(Boolean);point.dataset.installationAllowed=String(!!allowed);point.setAttribute('fill',allowed?'#087e82':'#9aa5ad');point.setAttribute('opacity',allowed?'1':'.22');let title=point.querySelector('title');if(!title){title=document.createElementNS('http://www.w3.org/2000/svg','title');point.append(title);}title.textContent=`후보지 ${point.dataset.site} · ${allowed?'허용 센서 슬롯 있음':'이 실행의 탐색에서 제외'}`;}
 return doc.innerHTML;
};
const domainCopy=$('copyRun').onclick;
$('copyRun').onclick=async function(...args){if(run){draft.research??={};draft.research.installationDomains??={};const saved=run.submitted_request?.installation_domain||run.problem?.calculator_installation_domain?.mode;draft.research.installationDomains[draft.sensor]=saved==='model_supported'?'model_supported':'model';}return domainCopy.apply(this,args);};
const domainScope=renderResultScope;
renderResultScope=function(parent,rows){domainScope(parent,rows);const box=$('resultScope');if(!box||!run)return;const d=run.problem?.calculator_installation_domain;
 if(run.installation_audit_summary?.invalid_raw_rows)noteText(box,`현재 필수 설치 조건 미달 ${run.installation_audit_summary.invalid_raw_rows}행은 대표해·Pareto 표시에서 제외했습니다. 과거 원시는 보존됩니다. 아래에서 조건을 복사해 새 계산을 실행하세요.`);
 const audit=typeof currentRow==='function'?currentRow()?.installation_audit:null;
 if(audit)noteText(box,`행 ${audit.solution_id} · 수량 ${audit.selected_sensor_count.join('/')} / 요구 ${(audit.expected_sensor_count||[]).join('/')} · 중복 ${audit.duplicate_count} · 필수 제약 위반 ${audit.hard_constraint_violation} · 평가영역 밖 센서 중심은 허용`);
 noteText(box,d?.mode==='inside_area'?`과거 실행: 영역 안 후보만 사용 ${d.eligible_sites}/${d.candidate_count}곳 · 새 조건 복사 시 전체 설치 후보 사용`:d?.mode==='model_supported'?'실행 설치 조건: 공개 Model 증명에 따른 안전 제외 마스크 · 과거 원시와 별도인 새 탐색 조건':'실행 설치 조건: 전체 설치 가능 후보 · 평가영역 커버 성능 최적화');
};
