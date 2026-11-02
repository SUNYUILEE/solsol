'use strict';
// Read-only observation of saved populations; never a fabricated ancestry path.
const LiveReplay=(()=>{
 let initial=null,anchorId=null,observationId=null,automatic=true,playing=false,playTimer=null,epoch=0;
 const list=()=>displayPoints().slice().sort((a,b)=>a.id-b.id);
 function stop(){++pollSerial;playing=false;++epoch;clearTimeout(playTimer);$('playReplay').textContent='진화 재생';$('mapPlay').textContent='▶ 진화 재생';$('mapReadout').textContent=automatic?'자동 관찰':'개별 배치 확인';$('mapReadout').className='replayState';}
 function reset(){stop();initial=null;anchorId=null;observationId=null;automatic=true;if(typeof LiveInitialContext!=='undefined')LiveInitialContext.clear();}
 async function initialFor(d){if(initial?.id===d.id)return initial;if(!d.snapshot)return null;const x=d.snapshot.generation===0?d:await request('/api/jobs/'+d.id+'?generation=0');if(x.id!==d.id||x.snapshot?.generation!==0)throw Error('초기 세대 자료를 확인할 수 없습니다.');return x;}
 function initialRows(){return initial?.current_population_points||initial?.points||[];}
 function originals(){return(initial?.initialization?.sources||[]).filter(s=>s.kind==='original'&&initialRows().some(p=>p.id===s.index)).slice().sort((a,b)=>a.index-b.index);}
 function accept(d,zero){if(initial?.id!==d.id){initial=zero;anchorId=originals()[0]?.index??initialRows().slice().sort((a,b)=>b.id-a.id)[0]?.id??null;observationId=null;automatic=true;}else if(!initial&&zero)initial=zero;}
 function remember(){++viewLoadSerial;automatic=false;observationId=null;}
 function beginAutomatic(){automatic=true;observationId=null;selectedId=null;}
 function choose(){if(automatic)observationId=list().at(-1)?.id??null;}
 function observationPoint(){return automatic?displayPoints().find(p=>p.id===observationId)||null:null;}
 function source(p){if(typeof LiveInitialContext!=='undefined'){const issue=LiveInitialContext.sourceIssue(initial,p);if(issue)return issue;}const info=initial?.initialization,src=info?.sources?.find(s=>s.index===p.id);if(src)return `${src.method==='milp'?'MILP':src.method==='greedy'?'Greedy':'준비해'} · ${src.kind==='original'?'준비 원본':'준비 배치 변형'} · 준비 목표 ${src.targets.map(v=>Math.round(v*100)+'%').join(' / ')}`;return info&&(info.method==='random'||Array.isArray(info.sources))?'무작위 초기 배치':'초기 배치 · 세부 생성 출처 미기록';}
 function inspectionStart(job){
  if(!job?.id||initial?.id!==job.id||initial?.snapshot?.generation!==0)return null;
  const point=initial.points?.find(p=>p.id===anchorId);
  return point?{problem,point,job:initial,generation:0,source:source(point)}:null;
 }
 function verify(p){ModelDisplay.call('inspect_metrics',problem,p,initial?.config?.objective_contract||'binary_coverage_v1');}
 function render(point){
  const pts=initialRows().slice().sort((a,b)=>a.id-b.id),anchor=pts.find(p=>p.id===anchorId)||null;
  const prepared=originals(),info=initial?.initialization,sources=(info?.sources||[]).filter(s=>pts.some(p=>p.id===s.index));
  $('initialPrepared').innerHTML='<option value="">준비 원본 선택</option>'+prepared.map(s=>{const p=pts.find(p=>p.id===s.index);return `<option value="${p.id}">#${p.id} · ${source(p)} · ${p.cost}점</option>`;}).join('');
  $('initialPrepared').value=prepared.some(s=>s.index===anchorId)?String(anchorId):'';$('initialPrepared').disabled=!prepared.length;
  $('initialComposition').textContent=!pts.length?'초기 집단 준비 중':!info||(info.method!=='random'&&!Array.isArray(info.sources))?'초기 집단 '+pts.length+'개 · 세부 생성 출처 미기록':info.method==='random'?`초기 집단 ${pts.length}개 · 무작위 초기화`:`초기 집단 ${pts.length}개 · 준비해 ${sources.length}개 (원본 ${prepared.length}개·변형 ${sources.length-prepared.length}개) + 무작위 ${pts.length-sources.length}개. ${prepared.length?'왼쪽 기본 표시는 첫 준비 원본이며, 최적해 추천이 아닙니다.':'주입된 준비 원본이 없습니다. 아래 계산 근거에서 솔버 상태를 확인하세요.'}`;
  const qualifyingCost=rows=>{const values=(rows||[]).filter(p=>p.qualified).map(p=>p.cost);return values.length?Math.min(...values):null;},startCost=qualifyingCost(pts),nowCost=qualifyingCost(last?.points);
  $('initialComparison').textContent=LiveCore.costStory(last?.config,startCost,nowCost,last?.snapshot?.generation??0);
  if(typeof LiveProgress!=='undefined')LiveProgress.render(initial,last,anchor?.id,point?.id);
  if(typeof LiveInitialContext!=='undefined')LiveInitialContext.render(initial,last,anchor?.id,point?.id);
  $('initialSolution').innerHTML='<option value="">초기 배치를 선택하세요</option>'+pts.map(p=>`<option value="${p.id}">#${p.id} · ${source(p)} · ${p.cost}점 · R${p.sensor_counts[0]} / E${p.sensor_counts[1]}</option>`).join('');
  $('initialSolution').value=anchorId===null?'':String(anchorId);$('initialSolution').disabled=!pts.length;
  $('initialTitle').textContent=anchor?`시작 배치 · 0세대 · #${anchor.id}`:'시작 배치 · 준비 중';
  $('initialText').textContent=anchor?`${source(anchor)}.\n탐지 ${LiveCore.pct(anchor.performance[0])} · 식별 ${LiveCore.pct(anchor.performance[1])} · 비용 ${anchor.cost}점\nRadar ${anchor.sensor_counts[0]}대 · EO/IR ${anchor.sensor_counts[1]}대 · 재생 중 고정`:'초기 집단 평가가 끝나면 시작 배치가 표시됩니다.';
  if(anchor)verify(anchor);
  $('initialMap').innerHTML=anchor?LiveCore.map(problem,anchor,options()):'<div class="empty selectionEmpty">왼쪽에 고정할 초기 배치를 선택하세요.</div>';
  const s=last?.snapshot,h=last?.history||[];
  $('generationRange').max=String(last?.latest_generation||0);if(document.activeElement!==$('generationRange'))$('generationRange').value=String(s?.generation||0);$('generationRange').disabled=!s;$('goGeneration').disabled=!s;
  $('timeline').max=String(last?.latest_generation||0);$('timeline').value=String(s?.generation||0);$('timeline').disabled=!s;$('timeline').setAttribute('aria-valuetext',`${s?.generation||0}세대`);
  $('generationReadout').textContent=generationReadout(last);
  $('dockGeneration').textContent=s?`${s.generation} / ${last.latest_generation}세대`:'세대 자료 대기';
  $('firstGeneration').disabled=$('lastGeneration').disabled=!s;$('playReplay').disabled=!s||h.length<2;
  const live=!!s&&['queued','initializing','running'].includes(last?.state);
  $('followLatest').disabled=!live;$('followLatest').setAttribute('aria-pressed',String(live&&$('follow').checked));
  $('mapPlay').disabled=$('playReplay').disabled;$('mapPrevious').disabled=!s||s.generation===0;$('mapNext').disabled=!s||s.generation>=last.latest_generation;
  $('mapReadout').textContent=playing?'재생 중':automatic?'자동 관찰':'개별 배치 확인';
  $('mapReadout').className=playing?'replayState playing':'replayState';
  $('replayNote').textContent=automatic?`오른쪽은 ${$('diagnostics').checked?'현재 세대 생존집단':'선택 세대까지 누적된 좋은 배치'} 중 가장 나중에 관측된 배치입니다. 세대마다 자동 갱신하며 최고·권장·참 Pareto 해를 뜻하지 않습니다.`:'개별 배치를 확인 중입니다. 진화 재생이나 세대 이동을 누르면 자동 관찰로 돌아갑니다.';
  const targetScope=!$('diagnostics').checked&&($('solutionScope')?.value||'target_front')==='target_front';
  $('frameStatus').textContent=!s?'세대 자료를 기다리고 있습니다.':!point?(list().length?'배치를 선택하지 않았습니다. 아래 목록이나 그래프에서 선택하거나 진화 재생으로 관찰할 수 있습니다.':'이 세대에는 현재 목록 조건에 맞는 배치가 없습니다.'):`${$('diagnostics').checked?'누적 원시 진단':targetScope?'0–'+s.generation+'세대 누적 목표통과 비지배 해':'0–'+s.generation+'세대 누적 전체 물리 비지배 해'} ${displayPoints().length}개 중 #${point.id} 표시 · ${LiveSelection.targetQualified(point)?'탐지·식별 목표 통과':'목표 미달 · 전체 절충 배치'}`;
  if(!anchor||!point){$('deploymentDelta').textContent='양쪽 배치를 선택하면 비용·모델 성능·설치 구성의 차이를 표시합니다.';return;}
  const added=[],removed=[];point.mask.forEach((m,i)=>[1,2].forEach((bit,t)=>{const label=`후보 ${i+1} ${t?'EO/IR':'Radar'}`;if((m&bit)&&!(anchor.mask[i]&bit))added.push(label);if(!(m&bit)&&(anchor.mask[i]&bit))removed.push(label);}));
  const sign=v=>(v>0?'+':'')+v.toFixed(2);
  $('deploymentDelta').innerHTML=`<strong>초기 #${anchor.id} → ${s.generation}세대 #${point.id} 비교</strong><div class="deltaValues"><span>비용 <b>${anchor.cost} → ${point.cost}점 (${sign(point.cost-anchor.cost)})</b></span><span>탐지 <b>${LiveCore.pct(anchor.performance[0])} → ${LiveCore.pct(point.performance[0])} (${sign(100*(point.performance[0]-anchor.performance[0]))}%p)</b></span><span>식별 <b>${LiveCore.pct(anchor.performance[1])} → ${LiveCore.pct(point.performance[1])} (${sign(100*(point.performance[1]-anchor.performance[1]))}%p)</b></span></div><details><summary>설치 구성 차이 · 추가 ${added.length}대 / 제외 ${removed.length}대</summary><p>오른쪽에만 설치: ${added.join(', ')||'없음'}</p><p>왼쪽에만 설치: ${removed.join(', ')||'없음'}</p><p>선택한 두 배치의 차이이며, 실제로 실행된 변이 동작이나 부모·자식 관계를 뜻하지 않습니다.</p></details>`;
 }
 async function seek(g){stop();beginAutomatic();$('follow').checked=false;await poll(g);}
 async function followLatest(){if(!last?.snapshot||!['queued','initializing','running'].includes(last.state))return;stop();beginAutomatic();$('follow').checked=true;await poll();}
 async function advance(runEpoch){if(!playing||runEpoch!==epoch)return;const h=last?.history||[],i=h.findIndex(s=>s.generation===last?.snapshot?.generation),step=+$('replayStep').value||1;if(i<0||i>=h.length-1){stop();return;}await poll(h[Math.min(i+step,h.length-1)].generation);if(!playing||runEpoch!==epoch)return;if(!$('error').hidden){stop();return;}playTimer=setTimeout(()=>advance(runEpoch),+$('replaySpeed').value||1200);}
 function bind(){
  $('initialPrepared').onchange=()=>{if($('initialPrepared').value==='')return;++viewLoadSerial;stop();anchorId=+$('initialPrepared').value;draw();};
  $('initialSolution').onchange=()=>{++viewLoadSerial;stop();anchorId=$('initialSolution').value===''?null:+$('initialSolution').value;draw();};
  $('timeline').onchange=()=>seek(+$('timeline').value);
  $('goGeneration').onclick=()=>{const value=$('generationRange').value,g=Number(value);if(value===''||!Number.isInteger(g)||!last?.history?.some(s=>s.generation===g)){fail(Error('저장된 세대 번호를 입력하세요: 0~'+(last?.latest_generation||0)));return;}return seek(g);};
  $('generationRange').addEventListener('keydown',e=>{if(e.key==='Enter')$('goGeneration').onclick();});
  $('firstGeneration').onclick=()=>seek(0);$('lastGeneration').onclick=()=>seek(last.latest_generation);
  $('followLatest').onclick=followLatest;
  $('playReplay').onclick=async()=>{if(playing){stop();draw();return;}if(!last?.snapshot||last.history.length<2)return;clearTimeout(timer);$('follow').checked=false;beginAutomatic();playing=true;const e=++epoch;$('playReplay').textContent='일시정지';$('mapPlay').textContent='Ⅱ 일시정지';choose();draw();if(last.snapshot.generation===last.latest_generation)await poll(0);if(playing&&e===epoch)document.querySelector('.maps')?.scrollIntoView?.({block:'start',behavior:'instant'});if(playing&&e===epoch)playTimer=setTimeout(()=>advance(e),+$('replaySpeed').value||1200);};
  $('mapPlay').onclick=async()=>{await $('playReplay').onclick();document.querySelector('.maps')?.scrollIntoView?.({block:'start',behavior:'instant'});};$('mapPrevious').onclick=()=>$('previous').onclick();$('mapNext').onclick=()=>$('next').onclick();
 }
 return{reset,stop,initialFor,accept,remember,choose,observationPoint,render,bind,seek,inspectionStart,isPlaying:()=>playing,isAutomatic:()=>automatic};
})();
