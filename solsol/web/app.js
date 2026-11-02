'use strict';
const $=id=>document.getElementById(id);
const clone=value=>structuredClone(value);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,n=1)=>v===null||v===undefined?'—':Number(v).toFixed(n);
const pct=v=>v===null||v===undefined?'—':fmt(v*100)+'%';
const labels={coverage:'커버리지',joint_coverage:'공동 커버리지',cost:'비용'};
const colors=['#008b8b','#d58522','#7d6bbb','#be5277','#427dc4'];
let config=null,run=null,selected=null,draft=true,jobId=null,timer=null,filtered=[];
const phases={waiting:'대기',preparing:'초기 배치 준비',running:'계산 중',verifying:'검증 중',saving:'저장 중',completed:'계산 · 저장 완료',stopped:'중지됨',stop_requested:'중지 요청',time_limit:'시간 예산 종료',failed:'실패',restoring:'복원 중',reconnecting:'재연결 중'};
async function api(path,body){
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value=await response.json();if(!response.ok)throw Error(value.error||response.statusText);return value;
}
function error(e){$('error').textContent=e.message||String(e);$('error').hidden=false;}
function safe(fn){return async(...args)=>{try{$('error').hidden=true;await fn(...args);}catch(e){error(e);}};}
function status(value,progress){$('status').textContent=phases[value]||value;$('status').className=['waiting','preparing','running','verifying','saving','restoring','reconnecting'].includes(value)?'busy':'';
  if(progress)$('progress').textContent=`세대 ${progress.generation} · NFE ${progress.nfe} · ${fmt(progress.elapsed_seconds)}초 · 준비 평가 ${progress.preparation_evaluations||0}`;}
function numericInput(value,key,index,collection,step='any'){return `<input type="number" step="${step}" value="${esc(value)}" data-collection="${collection}" data-index="${index}" data-key="${key}" aria-label="${esc(collection+' '+index+' '+key)}">`;}
function fillForm(c){config=clone(c);
  $('sensors').querySelector('tbody').innerHTML=c.sensors.map((s,i)=>`<tr><td><input value="${esc(s.id)}" data-collection="sensors" data-index="${i}" data-key="id" aria-label="센서 ID ${i}"></td>${['radius','height','cost','resource','minimum','maximum'].map(k=>`<td>${numericInput(s[k],k,i,'sensors')}</td>`).join('')}<td><button class="quiet" data-remove="sensors" data-index="${i}" aria-label="센서 삭제 ${i}">×</button></td></tr>`).join('');
  $('relations').innerHTML=c.relations.map((r,i)=>`<div class="relation"><input value="${esc(r.id)}" data-collection="relations" data-index="${i}" data-key="id" aria-label="관계 ID ${i}"><input value="${esc(r.sensors.join(','))}" data-collection="relations" data-index="${i}" data-key="sensors" aria-label="관계 센서 ${i}"><button class="quiet" data-remove="relations" data-index="${i}" aria-label="관계 삭제 ${i}">×</button></div>`).join('');
  $('sites').querySelector('tbody').innerHTML=c.sites.map((s,i)=>`<tr><td><input value="${esc(s.id)}" data-collection="sites" data-index="${i}" data-key="id" aria-label="후보지 ID ${i}"></td>${['x','y','z','capacity','activation_cost'].map(k=>`<td>${numericInput(s[k],k,i,'sites')}</td>`).join('')}<td><input value="${esc((s.allowed||c.sensors.map(s=>s.id)).join(','))}" data-collection="sites" data-index="${i}" data-key="allowed" aria-label="후보지 허용 센서 ${i}"></td><td><button class="quiet" data-remove="sites" data-index="${i}" aria-label="후보지 삭제 ${i}">×</button></td></tr>`).join('');
  $('obstacles').querySelector('tbody').innerHTML=c.obstacles.map((s,i)=>`<tr>${['xmin','xmax','ymin','ymax','zmin','zmax'].map(k=>`<td>${numericInput(s[k],k,i,'obstacles')}</td>`).join('')}<td><button class="quiet" data-remove="obstacles" data-index="${i}" aria-label="장애물 삭제 ${i}">×</button></td></tr>`).join('');
  $('budget').value=c.budget??'';$('total-resource').value=c.total_resource??'';$('los').checked=c.los;$('colocation').checked=c.co_location;
  $('coverage-goal').value=c.goals.coverage??'';$('joint-goal').value=c.goals.joint_coverage??'';
  $('objectives').innerHTML=['coverage','joint_coverage','cost'].map(k=>`<label><input type="checkbox" data-objective="${k}" ${c.objectives.includes(k)?'checked':''}>${labels[k]}</label>`).join('');
  $('point-count').textContent=`평가 지점 ${c.points.length}개 · 좌표계: Cartesian m`;
  draft=true;selected=null;renderAll();
}
function optimizer(){return {algorithm:$('algorithm').value,initializer:$('initializer').value,seed:Number($('seed').value),population:Number($('population').value),generations:Number($('generations').value),preparation_budget:Number($('prep-budget').value),ref_partitions:Number($('partitions').value)};}
function setOptimizer(o){for(const [id,k] of Object.entries({algorithm:'algorithm',initializer:'initializer',seed:'seed',population:'population',generations:'generations','prep-budget':'preparation_budget',partitions:'ref_partitions'}))if(o[k]!==undefined)$(id).value=o[k];}
function dirty(){draft=true;selected=null;$('validation').textContent='조건 변경됨 · 다음 실행에 적용됩니다.';renderAll();}
document.querySelector('aside').addEventListener('input',event=>{
  if(!config)return;const t=event.target,collection=t.dataset.collection,key=t.dataset.key;
  if(collection){let value=t.type==='number'?Number(t.value):t.value;if(['sensors','allowed'].includes(key))value=t.value.split(',').map(s=>s.trim()).filter(Boolean);config[collection][Number(t.dataset.index)][key]=value;}
  if(t.id==='budget')config.budget=t.value===''?null:Number(t.value);
  if(t.id==='total-resource')config.total_resource=t.value===''?null:Number(t.value);
  if(t.id==='los')config.los=t.checked;if(t.id==='colocation')config.co_location=t.checked;
  if(['coverage-goal','joint-goal'].includes(t.id)){const k=t.id==='coverage-goal'?'coverage':'joint_coverage';if(t.value==='')delete config.goals[k];else config.goals[k]=Number(t.value);}
  if(t.dataset.objective)config.objectives=[...document.querySelectorAll('[data-objective]:checked')].map(e=>e.dataset.objective);
  if(t.id!=='advanced'&&!['xmin','xmax','ymin','ymax','grid-step','point-height'].includes(t.id))dirty();
});
document.querySelector('aside').addEventListener('click',event=>{
  const t=event.target;if(t.dataset.remove){config[t.dataset.remove].splice(Number(t.dataset.index),1);fillForm(config);dirty();}
});
$('add-sensor').onclick=()=>{let i=config.sensors.length+1;while(config.sensors.some(s=>s.id==='S'+i))i++;config.sensors.push({id:'S'+i,radius:100,height:5,cost:3,resource:1,minimum:0,maximum:3});fillForm(config);dirty();};
$('add-relation').onclick=()=>{config.relations.push({id:'R'+(config.relations.length+1),sensors:config.sensors.slice(0,2).map(s=>s.id)});fillForm(config);dirty();};
$('add-site').onclick=()=>{let i=config.sites.length+1;while(config.sites.some(s=>s.id==='S'+i))i++;config.sites.push({id:'S'+i,x:0,y:0,z:0,capacity:4,activation_cost:2});fillForm(config);dirty();};
$('add-obstacle').onclick=()=>{config.obstacles.push({xmin:100,xmax:150,ymin:100,ymax:150,zmin:0,zmax:10});fillForm(config);dirty();};
$('grid').onclick=safe(()=>{const xmin=Number($('xmin').value),xmax=Number($('xmax').value),ymin=Number($('ymin').value),ymax=Number($('ymax').value),step=Number($('grid-step').value),z=Number($('point-height').value);
  if(![xmin,xmax,ymin,ymax,step,z].every(Number.isFinite)||step<=0||xmin>=xmax||ymin>=ymax)throw Error('영역과 양수 격자 간격을 확인하세요.');
  if(Math.ceil((xmax-xmin)/step)*Math.ceil((ymax-ymin)/step)>10000)throw Error('격자 지점은 최대 10000개입니다.');
  const points=[];for(let y=ymin+step/2;y<ymax;y+=step)for(let x=xmin+step/2;x<xmax;x+=step)points.push({id:'P'+(points.length+1),x,y,z,weight:1});config.points=points;fillForm(config);dirty();});
$('export-config').onclick=()=>{$('advanced').value=JSON.stringify(config,null,2);};
$('import-config').onclick=safe(async()=>{const c=JSON.parse($('advanced').value);await api('/api/validate',{config:c,optimizer:optimizer()});fillForm(c);dirty();});
$('reset').onclick=safe(async()=>{fillForm((await api('/api/example')).config);dirty();});
$('validate').onclick=safe(async()=>{status('조건 반영 중');const v=await api('/api/validate',{config,optimizer:optimizer()});$('validation').textContent=`확인됨 · 후보 ${v.candidate_count} / 평가 ${v.point_count} · 계약 ${v.experiment_contract_id.slice(0,12)}`;status('준비');});
function lock(active){$('run').disabled=active;$('stop').disabled=!active;}
$('run').onclick=safe(async()=>{lock(true);status('waiting');try{const v=await api('/api/jobs',{config:clone(config),optimizer:optimizer()});jobId=v.job_id;poll();}catch(e){lock(false);status('failed');throw e;}});
$('stop').onclick=safe(async()=>{if(jobId){await api('/api/jobs/'+jobId+'/stop',{});status('stop_requested');}});
async function poll(){
  try{const j=await api('/api/jobs/'+jobId);status(j.status,j);
    if(['completed','stopped','time_limit','failed'].includes(j.status)){lock(false);if(j.error)throw Error(j.error);if(j.run_id){loadRun(await api('/api/runs/'+j.run_id));await savedList();}return;}
  }catch(e){if(e.message.includes('Failed to fetch')){status('reconnecting');timer=setTimeout(poll,1500);return;}error(e);lock(false);return;}
  timer=setTimeout(poll,350);
}
function loadRun(value){run=value;draft=false;selected=value.archive_ids[0]??null;setOptimizer(value.optimizer);
  $('checkpoint').innerHTML='<option value="all">전체 관측</option>'+value.checkpoints.map(cp=>`<option value="${cp.generation}">${cp.generation}세대 · ${cp.nfe} NFE</option>`).join('');
  $('verification').textContent=value.verification?`저장 전 전체 재생: ${value.verification.status} · 탐색 ${value.verification.checked_rows}행 / 준비 ${value.verification.checked_preparation_rows}행`:'저장 checksum 확인 · 전체 재생 검산 가능';renderAll();}
function row(){return !draft&&run&&selected!==null?run.rows[selected]:null;}
function ids(){if(!run)return[];const cp=$('checkpoint').value;return cp==='all'?run.archive_ids:run.checkpoints[Number(cp)].archive_ids;}
function renderResults(){
  if(!run)return;const sort=$('sort').value;let values=ids().map(i=>run.rows[i]);
  if($('goal-only').checked)values=values.filter(r=>Object.entries(run.config.goals).every(([k,v])=>r.named_metrics[k]>=v));
  values.sort((a,b)=>sort==='cost'?a.cost-b.cost||a.id-b.id:(b[sort]??-Infinity)-(a[sort]??-Infinity)||a.id-b.id);
  const threshold=Number($('hamming').value)||0;const keep=[];
  for(const r of values)if(!threshold||keep.every(t=>r.X.flat().filter((v,i)=>v!==t.X.flat()[i]).length>=threshold))keep.push(r);
  filtered=keep;if(!draft&&!keep.some(r=>r.id===selected))selected=keep[0]?.id??null;
  $('archive-count').textContent=`누적 ${ids().length}개 · 표시 ${keep.length}개${threshold?' · 사후 Hamming 부분집합':''}`;
  $('results').querySelector('tbody').innerHTML=keep.map(r=>`<tr data-id="${r.id}" class="${r.id===selected&&!draft?'selected':''}" tabindex="0" aria-label="원시 행 ${r.id}"><td>#${r.id}</td><td>${pct(r.coverage)}</td><td>${pct(r.joint_coverage)}</td><td>${fmt(r.cost)}</td><td>${r.counts.reduce((a,b)=>a+b,0)}</td><td>${r.provenance==='INITIAL_POPULATION'?'초기 집단':'탐색'}</td></tr>`).join('');
  const points=keep;const costs=points.map(r=>r.cost);const max=Math.max(1,...costs),min=Math.min(0,...costs);
  $('pareto').innerHTML=`<path d="M45 15 V175 H780" fill="none" stroke="#9eb4bf"/><text x="8" y="25" font-size="10" fill="#5a717e">100%</text><text x="8" y="175" font-size="10" fill="#5a717e">0%</text><text x="365" y="202" font-size="11" fill="#5a717e">설치·장비 비용 (${fmt(min,0)}~${fmt(max,0)})</text>`+points.map(r=>`<circle data-id="${r.id}" cx="${45+725*(r.cost-min)/(max-min)}" cy="${175-155*r.coverage}" r="${r.id===selected&&!draft?6:4}" fill="${r.id===selected&&!draft?'#d58522':'#008b8b'}" opacity=".8" style="cursor:pointer"><title>#${r.id} · 비용 ${r.cost} · 커버리지 ${pct(r.coverage)}</title></circle>`).join('');
}
function renderAll(){if(!config)return;renderResults();renderMap();const r=row();
  $('identity').textContent=draft?'새 조건 미리보기 · 저장 결과와 별개':run?`실행 ${run.run_id.slice(0,8)} · 계약 ${run.experiment_contract_id.slice(0,12)} · 원시 행 ${selected??'없음'}`:'조건 미리보기';
  const values=r?[pct(r.coverage),pct(r.joint_coverage),fmt(r.cost),r.counts.reduce((a,b)=>a+b,0)]:['—','—','—','—'];
  [...$('metrics').querySelectorAll('b')].forEach((e,i)=>e.textContent=values[i]);
  $('evidence').textContent=r?`원시 #${r.id} · ${r.provenance} · X ${r.placement_hash.slice(0,12)} · 제약 ${r.feasible?'통과':'미통과'} · LOS 차폐 링크 ${r.blocked_links} · 원시 F/G와 같은 지도`:'미리보기에는 탐색 성능값을 표시하지 않습니다. 결과 행을 선택하면 해당 실행 조건으로 지도를 표시합니다.';
}
function selectRow(id){selected=Number(id);draft=false;renderAll();}
$('results').onclick=e=>{const tr=e.target.closest('[data-id]');if(tr)selectRow(tr.dataset.id);};
$('results').onkeydown=e=>{if(e.key==='Enter'){const tr=e.target.closest('[data-id]');if(tr)selectRow(tr.dataset.id);}};
$('pareto').onclick=e=>{if(e.target.dataset.id!==undefined)selectRow(e.target.dataset.id);};
for(const id of ['sort','checkpoint','goal-only','hamming'])$(id).onchange=()=>{if(run){const eligible=ids();if(!eligible.includes(selected))selected=eligible[0]??null;}renderAll();};
function lineVisible(start,end,boxes){const d=end.map((v,i)=>v-start[i]);for(const b of boxes){let lo=0,hi=1;for(const [j,a] of ['x','y','z'].entries()){if(d[j]===0){if(start[j]<b[a+'min']||start[j]>b[a+'max']){lo=2;break;}}else{const t0=(b[a+'min']-start[j])/d[j],t1=(b[a+'max']-start[j])/d[j];lo=Math.max(lo,Math.min(t0,t1));hi=Math.min(hi,Math.max(t0,t1));if(lo>hi)break;}}if(lo<=hi)return false;}return true;}
function renderMap(){
  const c=draft?config:run.config,r=row();const all=[...c.sites,...c.points];if(!all.length)return;
  document.querySelector('.legend').innerHTML=c.sensors.map((s,j)=>`<span>${esc(s.id)} <i style="background:${colors[j%colors.length]}"></i></span>`).join('')+'<span>● 커버됨</span><span>· 미커버</span><span>▧ 장애물</span>';
  const xs=all.map(p=>p.x),ys=all.map(p=>p.y);if(![...xs,...ys].every(Number.isFinite))return;
  let minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);const pad=Math.max(maxx-minx,maxy-miny,100)*.10;minx-=pad;maxx+=pad;miny-=pad;maxy+=pad;
  const scale=Math.min(800/(maxx-minx),590/(maxy-miny));const px=x=>20+(x-minx)*scale,py=y=>610-(y-miny)*scale;
  let out=`<rect width="840" height="640" fill="#f5f9fa"/><text x="20" y="20" fill="#6f8792" font-size="12">${draft?'새 조건 미리보기':'저장 실행 · 원시 #'+selected} / Cartesian m</text>`;
  for(const b of c.obstacles)out+=`<rect x="${px(b.xmin)}" y="${py(b.ymax)}" width="${(b.xmax-b.xmin)*scale}" height="${(b.ymax-b.ymin)*scale}" fill="#87999f" fill-opacity=".35" stroke="#6b7e86"><title>LOS 장애물 높이 ${esc(b.zmax-b.zmin)} m</title></rect>`;
  if($('show-points').checked)c.points.forEach((p,i)=>{out+=`<circle cx="${px(p.x)}" cy="${py(p.y)}" r="${r?3:2}" fill="${r?.covered_points[i]?'#45a89b':'#b5c5cd'}"><title>${esc(p.id)} · weight ${esc(p.weight)}${r?' · '+(r.covered_points[i]?'커버됨':'미커버'):''}</title></circle>`;});
  const installs=[];if(r)r.X.forEach((v,i)=>v.forEach((on,j)=>{if(on)installs.push([i,j]);}));
  if(!r&&$('show-ranges').checked&&c.sites.length)c.sensors.forEach((s,j)=>{const site=c.sites[0];if(Number.isFinite(s.radius))out+=`<circle cx="${px(site.x)}" cy="${py(site.y)}" r="${s.radius*scale}" fill="none" stroke="${colors[j%colors.length]}" stroke-dasharray="5 6" opacity=".4"/>`;});
  const old=$('installation-select').value;$('installation-select').innerHTML=installs.map(([i,j],k)=>`<option value="${k}">${esc(c.sites[i].id+' / '+c.sensors[j].id)}</option>`).join('');if([...$('installation-select').options].some(o=>o.value===old))$('installation-select').value=old;
  installs.forEach(([i,j])=>{const p=c.sites[i],s=c.sensors[j],color=colors[j%colors.length];if($('show-ranges').checked)out+=`<circle cx="${px(p.x)}" cy="${py(p.y)}" r="${s.radius*scale}" fill="${color}" fill-opacity=".035" stroke="${color}" opacity=".65"/>`;out+=`<circle cx="${px(p.x)+j*5}" cy="${py(p.y)}" r="5" fill="${color}" stroke="white"/><text x="${px(p.x)+7}" y="${py(p.y)-8-j*12}" fill="${color}" font-size="11">${esc(s.id)}</text>`;});
  if($('show-los').checked&&installs.length){const [i,j]=installs[Number($('installation-select').value)||0],site=c.sites[i],s=c.sensors[j];for(const p of c.points){if(Math.hypot(site.x-p.x,site.y-p.y)>s.radius)continue;const ok=!c.los||lineVisible([site.x,site.y,site.z+s.height],[p.x,p.y,p.z],c.obstacles);out+=`<line x1="${px(site.x)}" y1="${py(site.y)}" x2="${px(p.x)}" y2="${py(p.y)}" stroke="${ok?'#008b8b':'#b3543a'}" opacity=".3" stroke-width="1" ${ok?'':'stroke-dasharray="3 4"'}/>`;}}
  c.sites.forEach(p=>out+=`<path d="M${px(p.x)-3} ${py(p.y)-3}l6 6m0-6l-6 6" stroke="#26495b"/><text x="${px(p.x)+5}" y="${py(p.y)+15}" font-size="10" fill="#59727e">${esc(p.id)}</text>`);
  $('map').innerHTML=out;
}
for(const id of ['show-ranges','show-points','show-los','installation-select'])$(id).onchange=renderMap;
$('expand').onclick=()=>{$('map-wrap').classList.add('expanded');renderMap();};$('close-map').onclick=()=>{$('map-wrap').classList.remove('expanded');};document.addEventListener('keydown',e=>{if(e.key==='Escape')$('map-wrap').classList.remove('expanded');});
async function savedList(){const runs=await api('/api/runs');$('saved').innerHTML=runs.map(r=>`<option value="${esc(r.run_id)}">${esc(r.run_id.slice(0,8))} · ${esc(r.status)} · ${esc(r.nfe??'?')} NFE</option>`).join('');if(!runs.length)$('saved').innerHTML='<option value="">저장 결과 없음</option>';}
$('refresh').onclick=safe(savedList);
$('restore').onclick=safe(async()=>{if(!$('saved').value)return;status('restoring');loadRun(await api('/api/runs/'+$('saved').value));status(run.status,{generation:run.checkpoints.length-1,nfe:run.rows.length,elapsed_seconds:run.elapsed_seconds,preparation_evaluations:run.preparation.length});});
$('copy-config').onclick=safe(()=>{if(!run)throw Error('먼저 결과를 선택하세요.');fillForm(run.config);setOptimizer(run.optimizer);dirty();});
$('download').onclick=safe(()=>{if(!run)throw Error('먼저 결과를 선택하세요.');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:'application/json'}));a.download=run.run_id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);});
$('replay').onclick=safe(async()=>{if(!run)throw Error('먼저 결과를 선택하세요.');$('verification').textContent='전체 원시 행 검산 중…';const v=await api('/api/replay',{run_id:run.run_id});$('verification').textContent=`재생 ${v.status} · 탐색 ${v.checked_rows}행 · 준비 ${v.checked_preparation_rows??0}행${v.error?' · '+v.error:''}`;});
safe(async()=>{fillForm((await api('/api/example')).config);await savedList();status('준비');})();
