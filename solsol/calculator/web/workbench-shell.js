/* Layout owns no scientific state. Controller callbacks own every run/selection. */
export function mountWorkbench(actions) {
 const el=id=>document.getElementById(id), root=document.querySelector('.workbench');
 const nav=document.createElement('nav');nav.className='taskNav';nav.setAttribute('aria-label','작업 선택');
 const tasks=[['settings','01','조건 설정'],['map','02','지도 탐색'],['compare','03','배치 비교'],['solutions','04','해집합 분석'],['verify','05','검증·근거']];
 for(const [id,n,label] of tasks){const b=document.createElement('button');b.id='task_'+id;b.dataset.task=id;b.innerHTML='<span>'+n+'</span><b>'+label+'</b>';b.onclick=()=>actions.selectTask(id);nav.append(b);}
 root.prepend(nav);
 const context=document.querySelector('.mapTop');root.before(context);
 const title=document.createElement('h1');title.id='taskTitle';title.textContent='조건 설정';context.prepend(title);
 const side=document.createElement('section');side.className='sideStack';side.setAttribute('aria-label','배치 목록과 선택 설명');
 const tabs=document.createElement('div');tabs.className='sideTabs';tabs.innerHTML='<button id="sideSolutions" aria-pressed="true">해 목록</button><button id="sideProperties" aria-pressed="false">선택 설명</button>';
 const dock=document.querySelector('.resultDock'),inspector=document.querySelector('.inspector');side.append(tabs,dock,inspector);root.append(side);
 const analysis=el('placementAnalysis');root.append(analysis);
 const canvas=document.querySelector('.canvasColumn');
 let task='settings',sideView='solutions';
 function showSide(view){sideView=view;side.dataset.view=view;el('sideSolutions').setAttribute('aria-pressed',view==='solutions');el('sideProperties').setAttribute('aria-pressed',view==='properties');}
 el('sideSolutions').onclick=()=>showSide('solutions');el('sideProperties').onclick=()=>showSide('properties');
 function setTask(next){task=next;document.body.dataset.task=next;nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',b.dataset.task===next?'page':'false'));el('taskTitle').textContent=tasks.find(t=>t[0]===next)?.[2]||'센서 분석';
  if(next==='solutions'){root.append(dock);showSide('properties');}else{side.insertBefore(dock,inspector);if(next==='map')showSide('solutions');}
  el('toggleSettings').textContent=next==='settings'?'지도로 돌아가기':'조건 편집';
  el('toggleSettings').setAttribute('aria-expanded',next==='settings');
 }
 function contextChanged(){if(task==='verify'&&!analysis.open)actions.selectTask('map');}
 // The historical HTML remains a pinned bootstrap, never an alternate product flow.
 el('advancedDialog').remove();
 const help=el('helpDialog');help.querySelectorAll('p').forEach(p=>p.remove());
 const p=document.createElement('p');p.textContent='두 센서 조합 모두 같은 조건 설정·지도·배치 비교·해집합·검증 화면을 사용합니다. 공통 후보지 RF 계산은 현재 프로그램에 연결되어 있습니다. 저장된 조건과 다음 계산 초안은 구분됩니다.';help.append(p);
 setTask('settings');showSide(sideView);
 return {setTask,showSide,contextChanged,get task(){return task;},canvas};
}
