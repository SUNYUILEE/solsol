'use strict';
const auditMemo=new Map();
function checkPoint(p,a){const expected=[1-a.d/map.demand.length,1-a.i/map.demand.length,a.cost/800];if(Math.abs(p.D-a.d/map.demand.length)>1e-10||Math.abs(p.I-a.i/map.demand.length)>1e-10||p.cost!==a.cost||!p.F||expected.some((v,i)=>Math.abs(v-p.F[i])>1e-10))throw Error('선택 배치의 원시 목적값·비용과 지도 계산이 다릅니다');return a}
function leftPoint(){return $('leftMode').value==='blueprint'?map.blueprints.find(p=>p.id===$('blueprintSelect').value):ref}
function contribution(p){
 const key=map.id+':'+p.q;if(auditMemo.has(key))return checkPoint(p,auditMemo.get(key));
 const nr=new Uint16Array(map.demand.length),ne=new Uint16Array(map.demand.length),devices=[];
 [...p.q].forEach((q,i)=>{for(let t=0;t<2;t++)if(+q&(t?2:1)){const cover=[];map.demand.forEach(([x,y],j)=>{if((map.sites[i][0]-x)**2+(map.sites[i][1]-y)**2<=(t?2250000:9000000)){cover.push(j);(t?ne:nr)[j]++}});devices.push({site:i,type:t,cover})}});
 let d=0,ii=0;for(let j=0;j<nr.length;j++){if(nr[j])d++;if(nr[j]&&ne[j])ii++}
 for(const dev of devices){let ld=0,li=0;for(const j of dev.cover){if(dev.type===0&&nr[j]===1){ld++;if(ne[j])li++}if(dev.type===1&&ne[j]===1&&nr[j])li++}dev.loss=[ld,li];dev.footprint=dev.cover.length;dev.redundant=!ld&&!li}
 const cost=devices.reduce((n,d)=>n+(d.type?2:6),0);
 if(Math.abs(p.D-d/nr.length)>1e-10||Math.abs(p.I-ii/nr.length)>1e-10||p.cost!==cost)throw Error('선택 배치의 원시 성능과 지도 계산이 다릅니다');
 const result={devices,nr,ne,d,i:ii,cost,zero:devices.filter(d=>!d.footprint).length,redundant:devices.filter(d=>d.redundant).length};checkPoint(p,result);auditMemo.set(key,result);return result;
}
function qualityText(p,a){const swap=p.audit?.one_swap_count;return `<b>${ok(p)?'탐지·식별 목표 통과':'목표 미달 · 탐색 중'}</b> · 수요 커버가 전혀 없는 장비 ${a.zero}대 · 한 대 삭제해도 성능이 같은 장비 ${a.redundant}대<br>같은 종류 한 대 위치 교환 검사: ${swap===undefined?'이 선택점은 미검사':swap?'더 좋은 위치 교환 '+swap+'개 발견':'개선 반례 0개'}. ${a.redundant?'이 해는 더 저렴한 대안이 있으므로 파레토 최적해가 아닙니다.':swap?'같은 비용에 성능이 더 좋은 위치 교환이 있으므로 이 해는 파레토 최적해가 아닙니다.':'삭제 가능0대만으로 전체 최적성이 증명되는 것은 아닙니다.'}`}
function focusSensor(){
 if(!selected)return;const a=contribution(selected.p),idx=+$('sensorInspect').value,d=a.devices[idx];
 for(const el of document.querySelectorAll('#runMap .coverage')){const yes=d&&+el.dataset.site===d.site&&+el.dataset.sensor===d.type;el.classList.toggle('focused',!!yes);el.classList.toggle('unfocused',!!d&&!yes)}
 if(!d){$('sensorDetail').textContent='장비를 선택하면 그 커버만 진하게 강조하고, 개별 기여를 설명합니다.';return}
 const xy=map.sites[d.site];$('sensorDetail').innerHTML=`<b>후보${d.site+1} · ${d.type?'EO/IR':'Radar'} · (${(xy[0]/1000).toFixed(3)}, ${(xy[1]/1000).toFixed(3)})km</b><br>해당 장비 반경에 들어오는 평가점 ${d.footprint}개. 이 장비만 제거하면 탐지 ${d.loss[0]}점, 식별 ${d.loss[1]}점을 잃고 비용은 ${d.type?2:6}점 줄어듭니다. ${d.redundant?'<b class="warn">현재 배치에서 불필요한 중복입니다.</b>':'현재 배치의 모델 성능에 기여합니다.'}`;
}
function sampleExplanation(a,j){const xy=map.demand[j];return `<div class="sample-row"><b>수요${j+1} · (${xy[0]/1000}, ${xy[1]/1000})km</b> Radar ${a.nr[j]}대 도달 → d=${a.nr[j]?1:0}; EO/IR ${a.ne[j]}대 도달 → v=${a.ne[j]?1:0}; 식별 i=d×v=${a.nr[j]&&a.ne[j]?1:0}</div>`}
function enhance(){
 if(!selected)return;const p=selected.p,a=contribution(p),lp=leftPoint(),la=contribution(lp),blue=$('leftMode').value==='blueprint';
 for(const btn of document.querySelectorAll('[data-expand]'))btn.onclick=()=>{const source=$(btn.dataset.expand);$('largeMap').innerHTML=source.innerHTML.replace(/id="([^"]+)"/g,'id="large-$1"').replace(/url\(#/g,'url(#large-');$('mapDialog').showModal()};$('closeDialog').onclick=()=>{$('mapDialog').close();$('largeMap').innerHTML=''};
 if(!$('pointChoice'))$('legend').insertAdjacentHTML('afterend','<label>겹친 점을 정확히 선택하기 — 그룹·기록번호·성능·비용<select id="pointChoice"></select></label>');
 $('pointChoice').innerHTML=[['a',A,sa],['b',B,sb]].map(([g,r,s])=>`<optgroup label="${g==='a'?'파란 현재':'보라 비교'} · ${label(r)}">${s.display_ids.map(id=>{const p=r.points[id];return `<option value="${g}:${id}">${g==='a'?'현재':'비교'} 기록${id} · 탐지${pct(p.D)} / 식별${pct(p.I)} / 비용${p.cost}점</option>`}).join('')}</optgroup>`).join('');
 $('pointChoice').value=selected.group+':'+selected.id;$('pointChoice').onchange=()=>{const [group,id]=$('pointChoice').value.split(':'),r=group==='a'?A:B;selected={group,id,p:r.points[id]};render()};
 $('blueprintControl').hidden=!blue;
 $('refTitle').textContent=blue?`◇ 설계 원형 ${lp.id} · 정답 인증 전 출제안`:`◆ 최적성 확인 기준 ${ref.id} · Radar ${ref.sensors[0]}대 / EOIR ${ref.sensors[1]}대`;
 if(blue){$('refMetrics').innerHTML=metrics(lp);$('refMap').innerHTML=mapSvg(lp,'ref');$('refInventory').innerHTML=inventory(lp)}
 $('mapAudit').innerHTML=`<div class="quality-box ${a.redundant||a.zero||p.audit?.one_swap_count?'failed':'passed'}"><h3>오른쪽 실제 탐색 배치의 상태</h3>${qualityText(p,a)}<p>표시한 장비는 원시 실행 그대로입니다. 검사 과정에서 장비를 빼고 결과를 바꾸지 않았습니다.</p></div>`;
 // Mark redundant devices without hiding their actual sensor symbols or footprints.
 for(const dev of a.devices.filter(d=>d.redundant)){const coverage=document.querySelector(`#runMap .coverage[data-site="${dev.site}"][data-sensor="${dev.type}"]`);if(coverage)coverage.classList.add('no-contribution')}
 $('selection').innerHTML+=`<div class="quality-box ${a.redundant||p.audit?.one_swap_count?'failed':'passed'}">${qualityText(p,a)}</div>`;
 const t=selected.group==='a'?traceAt(A,sa):traceAt(B,sb),r=selected.group==='a'?A:B,s=selected.group==='a'?sa:sb;
 const cd=p.cost-ref.cost,hd=[...p.q].reduce((n,q,i)=>n+((+q&1)!==(+ref.q[i]&1))+((+q&2)!==(+ref.q[i]&2)),0);
 $('approachExplanation').innerHTML=`<strong>선택 기준과 실제 배치의 차이</strong>: 비용 ${cd>=0?'+':''}${cd}점, 탐지 ${((p.D-ref.D)*100).toFixed(2)}%p, 식별 ${((p.I-ref.I)*100).toFixed(2)}%p, 설치 스위치 차이 ${hd}개.<br>이 시점 해집합이 고정 기준의 목적값을 그대로 재현한 수: <b>${t.subset_hits} / ${map.unique}개</b>. 기준집합까지 IGD+ ${t.IGD_plus?.toFixed(5)??'미정의'} (작을수록 가까움). 위치가 달라도 같은 성능·비용일 수 있으므로 스위치 차이만으로 오답이라 하지 않습니다. 비용만 더 낮은 해도 성능이 다르면 선택 기준을 지배한 것이 아닙니다.`;
 const every=Math.max(1,Math.floor(r.trace.length/12));const ts=r.trace.filter((t,i)=>i%every===0||i===r.trace.length-1||t.generation===s.generation);
 $('checkpointTable').innerHTML='<table>'+table(['실제 세대','누적 평가','탐지','식별','현재 최저비용','지금까지 최저비용','기준 목적값 재현','지도 보기'],ts.map(t=>[t.generation,num(t.evaluations),pct(t.D),pct(t.I),t.cost??'미달',t.best_ever_cost??'미달',`${t.subset_hits}/${map.unique}`,`<button data-time="${t.evaluations}">이 시점 보기</button>`]))+'</table>';
 for(const btn of $('checkpointTable').querySelectorAll('button'))btn.onclick=()=>{$('time').value=Math.max(+$('time').min,+btn.dataset.time);selected=null;render()};
 $('objectiveExample').innerHTML=`<div class="table-wrap"><table>${table(['목적','선택 배치의 실제 계산','최소화할 값'],[['탐지 손실',`1 − ${a.d}/441`,p.F[0].toFixed(8)],['식별 손실',`1 − ${a.i}/441`,p.F[1].toFixed(8)],['설치비용',`(${p.sensors[0]}×6 + ${p.sensors[1]}×2)/800 = ${p.cost}/800`,p.F[2].toFixed(8)]])}</table></div><p>세 목적벡터 F=(${p.F.map(v=>v.toFixed(6)).join(', ')}). 탐지 ${a.d}≥420: ${a.d>=420?'통과':'미달'}, 식별 ${a.i}≥397: ${a.i>=397?'통과':'미달'}. ${r.id}, 기록${selected.id}, ${s.generation}세대·${num(s.evaluations)}평가의 실제 계산입니다.</p>`;
 const examples=[2,1,0].map(k=>map.demand.findIndex((_,j)=>(a.nr[j]?(a.ne[j]?2:1):0)===k)).filter(j=>j>=0);
 $('objectiveSample').innerHTML=examples.map(j=>sampleExplanation(a,j)).join('');
 const prev=$('sensorInspect').value;$('sensorInspect').innerHTML='<option value="-1">전체 장비 커버 보기</option>'+a.devices.map((d,i)=>`<option value="${i}">후보 ${d.site+1} · ${d.type?'EO/IR':'Radar'} · 커버 ${d.footprint}점${d.redundant?' · 삭제해도 성능 동일':''}</option>`).join('');$('sensorInspect').value=prev!==''&&a.devices[+prev]?prev:'-1';
 $('contributionTable').innerHTML='<table>'+table(['장비','도달 수요','삭제 시 탐지 손실','삭제 시 식별 손실','비용','판정'],a.devices.map((d,i)=>[`<button data-device="${i}">후보${d.site+1} ${d.type?'EO/IR':'Radar'}</button>`,d.footprint,d.loss[0],d.loss[1],d.type?2:6,d.redundant?'<span class="warn">삭제 가능 · 비최적 반례</span>':'기여 있음']))+'</table>';
 for(const btn of $('contributionTable').querySelectorAll('button'))btn.onclick=()=>{$('sensorInspect').value=btn.dataset.device;focusSensor()};
 for(const el of document.querySelectorAll('#runMap .sensor'))el.onclick=()=>{const site=+el.dataset.site;const i=a.devices.findIndex(d=>d.site===site&&el.textContent.includes(d.type?'EO/IR':'Radar'));$('sensorInspect').value=i;focusSensor();$('candidateInfo').textContent=$('sensorDetail').textContent};
 focusSensor();
 for(const el of document.querySelectorAll('#refMap .candidate,#refMap .sensor'))el.onclick=()=>{const i=+el.dataset.site,xy=map.sites[i];$('candidateInfo').textContent=`왼쪽 ${blue?'원형':'인증 기준'} ${lp.id} · 후보${i+1} (${(xy[0]/1000).toFixed(3)}, ${(xy[1]/1000).toFixed(3)})km · Radar ${+lp.q[i]&1?'설치':'없음'} · EO/IR ${+lp.q[i]&2?'설치':'없음'}`};
 $('blueprintTable').innerHTML='<h3>먼저 만든 원형 배치 — 인증 정답과 구분</h3><table>'+table(['원형','탐지','식별','비용','좌측 지도'],map.blueprints.map(p=>[p.id,pct(p.D),pct(p.I),p.cost,`<button data-blueprint="${p.id}">원형 보기</button>`]))+'</table>';
 for(const btn of $('blueprintTable').querySelectorAll('button'))btn.onclick=()=>{$('leftMode').value='blueprint';$('blueprintSelect').value=btn.dataset.blueprint;render()};
 const rows=catalog.rows.filter(x=>x.map===map.id);
 $('resultTable').innerHTML='<table>'+table(['설계 / 실제 설정','평가 / 세대','탐지','식별','비용 / 최저기준 차이','삭제 반례','교환 반례','동일 장면'],rows.map(x=>[`${names[x.design]}<br>${settings[x.setting]}`,`${num(x.actual_evaluations)} / ${x.generations}`,pct(x.D),pct(x.I),`${x.cost} / +${x.cost-map.cstar}`,x.redundant,x.swaps,`<button data-run="${x.id}">배치 확인</button>`]))+'</table>';
 for(const btn of $('resultTable').querySelectorAll('button'))btn.onclick=()=>{const x=rows.find(x=>x.id===btn.dataset.run);$('designA').value=x.design;$('settingA').value=x.setting;loadRuns().then(()=>document.querySelector('#maps').scrollIntoView()).catch(fail)};
 drawC();
}
function drawC(){
 const c=catalog.c_checks[+$('cSelect').value];if(!c)return;
 $('cExplanation').innerHTML=`<p><b>일반 지도 ${+$('cSelect').value+1} · 난수 ${c.seed}</b>: 모든 후보에 두 장비를 놓았을 때 탐지${pct(c.D)}, 식별${pct(c.I)}. ${c.qualified?'현재 표본에서 목표를 달성할 수 있는 입력입니다. 최소비용과 일반지도 NSGA 결과는 아직 계산하지 않았습니다.':'전부 설치해도 식별90%에 미달하므로 이 입력에서는 목표 달성이 불가능합니다.'} 그림은 후보 위치와 평가영역만 표시합니다. 800점 전체설치를 좋은 배치나 정답으로 소개하지 않습니다.</p>`;
 const xx=x=>60+x*.04,yy=y=>840-y*.04;
 let svg=svgOpen(900,900,'class="map-svg" aria-label="원형 없는 일반100후보 지도"')+'<rect x="60" y="40" width="800" height="800" fill="#fbfdff" stroke="#647f90"/><circle cx="460" cy="440" r="240" fill="#eaf1f6" stroke="#294d65" stroke-width="3" stroke-dasharray="12 8"/>';
 for(let k=0;k<=20;k+=2)svg+=`<text x="${xx(k*1000)}" y="870" text-anchor="middle">${k}</text><text x="45" y="${yy(k*1000)}" text-anchor="end">${k}</text>`;
 for(const [x,y]of c.sites)svg+=`<path d="M${xx(x)-4},${yy(y)}h8m-4,-4v8" stroke="#234e69" stroke-width="2"/>`;
 $('cMap').innerHTML=svg+'<text x="60" y="24" font-size="20">일반 후보100곳 · 평가영역 반경6km · 축 단위km</text></svg>';
}
// Detail view scales to actual points plus targets; no point is clipped to fake convergence.
function drawFront(){
 const points=map.refs.filter((r,i,a)=>a.findIndex(v=>v.D===r.D&&v.I===r.I&&v.cost===r.cost)===i).map(p=>({group:'ref',id:p.id,p}));
 for(const [group,r,s]of [['b',B,sb],['a',A,sa]])if(r&&s)points.push(...s.display_ids.map(id=>({group,id:String(id),p:r.points[id]})));
 const dmin=Math.max(0,Math.floor(Math.min(.95,...points.map(o=>o.p.D))*20)/20-.05),imin=Math.max(0,Math.floor(Math.min(.9,...points.map(o=>o.p.I))*20)/20-.05);
 const cmin=Math.max(0,Math.floor(Math.min(...points.map(o=>o.p.cost))/20)*20-20),cmax=Math.ceil(Math.max(...points.map(o=>o.p.cost))/20)*20+20;
 const mode=$('chartMode').value;$('rotation').hidden=mode!=='3d';let svg=svgOpen(900,550,'class="plot-svg" role="img" aria-label="실제 범위로 확대한 탐지 식별 비용 그래프"');
 if(mode==='3d'){
  const az=+$('azimuth').value*Math.PI/180,el=.48,project=(x,y,z)=>[(x-.5)*Math.cos(az)-(y-.5)*Math.sin(az),((x-.5)*Math.sin(az)+(y-.5)*Math.cos(az))*Math.sin(el)-(z-.5)*Math.cos(el)];
  const cube=[];for(let x=0;x<2;x++)for(let y=0;y<2;y++)for(let z=0;z<2;z++)cube.push([x,y,z]);
  const xy=cube.map(p=>project(...p)),xmin=Math.min(...xy.map(p=>p[0])),xmax=Math.max(...xy.map(p=>p[0])),ymin=Math.min(...xy.map(p=>p[1])),ymax=Math.max(...xy.map(p=>p[1]));
  const scale=Math.min(660/(xmax-xmin),340/(ymax-ymin)),at=(x,y,z)=>{const p=project(x,y,z);return[450+(p[0]-(xmin+xmax)/2)*scale,225+(p[1]-(ymin+ymax)/2)*scale]};
  for(const [axis,val]of [[0,(.95-dmin)/(1-dmin)],[1,(.9-imin)/(1-imin)]]){const corners=axis===0?[[val,0,0],[val,1,0],[val,1,1],[val,0,1]]:[[0,val,0],[1,val,0],[1,val,1],[0,val,1]];svg+=`<polygon points="${corners.map(p=>at(...p).join(',')).join(' ')}" fill="${axis?'#a74b00':'#006a9f'}" fill-opacity=".035" stroke="#8296a5" stroke-dasharray="5 5"/>`}
  for(let i=0;i<8;i++)for(let j=i+1;j<8;j++)if(cube[i].reduce((n,v,k)=>n+(v!==cube[j][k]),0)===1){const a=at(...cube[i]),b=at(...cube[j]);svg+=`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="#9caebd" stroke-width="1.5"/>`}
  const origin=at(0,0,0);for(const [v,c]of [[[1,0,0],'#006a9f'],[[0,1,0],'#a74b00'],[[0,0,1],'#71359b']]){const z=at(...v);svg+=`<line x1="${origin[0]}" y1="${origin[1]}" x2="${z[0]}" y2="${z[1]}" stroke="${c}" stroke-width="4"/>`}
  const norm=p=>[(p.D-dmin)/(1-dmin),(p.I-imin)/(1-imin),(p.cost-cmin)/(cmax-cmin)];
  points.sort((a,b)=>{const u=norm(a.p),v=norm(b.p);return (u[0]-v[0])*Math.sin(az)+(u[1]-v[1])*Math.cos(az)});
  for(const o of points){const p=at(...norm(o.p));svg+=marker(p[0],p[1],o.group,o.id,o.p,selected?.group===o.group&&selected?.id===o.id)}
  svg+=`<text x="65" y="455" fill="#006a9f" font-size="19" font-weight="bold">X 탐지 ${Math.round(dmin*100)}~100%</text><text x="355" y="455" fill="#a74b00" font-size="19" font-weight="bold">Y 식별 ${Math.round(imin*100)}~100%</text><text x="650" y="455" fill="#71359b" font-size="19" font-weight="bold">Z 비용 ${cmin}~${cmax}</text><text x="450" y="495" text-anchor="middle" font-size="17">세 굵은 축의 색이 위 수치축 이름과 대응합니다 · 점선 평면: 목표95% / 90%</text><text x="450" y="525" text-anchor="middle" font-size="16">전체 실제 점과 목표를 포함해 축 범위를 자동 확대합니다. 시점마다 축 범위가 달라질 수 있습니다.</text>`;
 }else{
  const cost=mode!=='di',lo=mode==='cd'?dmin:imin,xlo=cost?cmin:dmin,xhi=cost?cmax:1;
  const x=p=>80+740*((cost?p.cost:p.D)-xlo)/(xhi-xlo),y=p=>430-365*((mode==='cd'?p.D:p.I)-lo)/(1-lo);
  for(let k=0;k<=5;k++){const xx=80+k*148,yy=430-k*73;svg+=`<line class="grid" x1="80" y1="${yy}" x2="820" y2="${yy}"/><line class="grid" x1="${xx}" y1="65" x2="${xx}" y2="430"/><text x="66" y="${yy+5}" text-anchor="end" font-size="16">${((lo+(1-lo)*k/5)*100).toFixed(1)}%</text><text x="${xx}" y="458" text-anchor="middle" font-size="16">${cost?Math.round(xlo+(xhi-xlo)*k/5):((xlo+(xhi-xlo)*k/5)*100).toFixed(1)+'%'}</text>`}
  const target=y({D:.95,I:.9});svg+=`<line x1="80" y1="${target}" x2="820" y2="${target}" stroke="#943600" stroke-dasharray="7 5"/><text x="88" y="${target-9}" font-size="16" fill="#943600">${mode==='cd'?'탐지95%':'식별90%'} 목표</text>`;
  if(!cost)svg+=`<line x1="${x({D:.95})}" y1="65" x2="${x({D:.95})}" y2="430" stroke="#943600" stroke-dasharray="7 5"/>`;
  for(const o of points)svg+=marker(x(o.p),y(o.p),o.group,o.id,o.p,selected?.group===o.group&&selected?.id===o.id);
  svg+=`<text x="80" y="30" font-size="20" font-weight="bold">${mode==='cd'?'탐지':'식별'} 달성률 ↑</text><text x="450" y="500" text-anchor="middle" font-size="20" font-weight="bold">${cost?'합성비용점수 → 오른쪽일수록 비쌈':'탐지 달성률 → 오른쪽일수록 높음'}</text><text x="450" y="532" text-anchor="middle" font-size="16">축을 실제 점의 범위에 맞춰 확대했습니다 · 이전 시점과 비교할 때 눈금도 확인하세요</text>`;
 }
 $('frontChart').innerHTML=svg+'</svg>';$('legend').innerHTML=`<span style="color:${colors.ref}">◆ 고정 인증 기준</span><span style="color:${colors.a}">● 현재: ${names[A.design]} / ${settings[A.setting.id]}</span><span style="color:${colors.b}">□ 비교: ${names[B.design]} / ${settings[B.setting.id]}</span><span style="color:${colors.selected}">◉ 붉은 외곽선: 오른쪽 지도</span>`;bindPoints();
}
init().catch(fail);
