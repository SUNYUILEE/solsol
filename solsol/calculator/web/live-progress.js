'use strict';
// Population summaries are not a selected deployment or a lineage claim.
const LiveProgress=(()=>{
 const numeric=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
 function population(points){
  if(!Array.isArray(points))return null;
  const qualified=points.filter(p=>p.qualified===true&&numeric(p.cost)&&Number.isInteger(p.id)&&p.id>=0);
  const cost=qualified.length?Math.min(...qualified.map(p=>p.cost)):null;
  const rawTies=qualified.filter(p=>p.cost===cost).slice().sort((a,b)=>a.id-b.id);
  const ties=typeof LiveFrontInsight==='undefined'?rawTies:LiveFrontInsight.uniquePoints(rawTies);
  return {total:points.length,qualified:qualified.length,cost,ties,rawTieRows:rawTies.length};
 }
 function model(zero,run){
  if(!run||run.state==='failed'||run.error||!run.snapshot)return null;
  const generation=run.snapshot.generation;
  if(!Number.isInteger(generation)||generation<0)return null;
  const start=zero?.id===run.id&&zero.snapshot?.generation===0?population(zero.points):null;
  const current=population(run.points);
  const series=(run.history||[]).filter(s=>Number.isInteger(s.generation)&&s.generation>=0&&s.generation<=generation&&numeric(s.evaluations)).map(s=>({generation:s.generation,nfe:s.evaluations,cost:s.qualified_count>0&&numeric(s.current_cost)?s.current_cost:null}));
  const costs=series.filter(s=>s.cost!==null).map(s=>s.cost);
  return {generation,start,current,series,best:costs.length?Math.min(...costs):null,
   decrease:start?.cost!==null&&start?.cost!==undefined&&current?.cost!==null&&current?.cost!==undefined?start.cost-current.cost:null,
   fixedCost:run.config?.resource_mode==='all',latest:run.latest_generation};
 }
 function story(m){
  if(!m.start||!m.current)return '초기 집단 또는 현재 집단 자료를 확인할 수 없습니다.';
  if(m.start.cost===null)return m.current.cost===null?'초기와 현재 집단에 목표를 통과한 배치가 없습니다. 비용 감소를 계산할 수 없습니다.':'초기 집단에서는 목표를 통과하지 못했고, 현재 세대에서 목표 통과 배치가 관측됩니다. 이를 0점에서의 비용 절감으로 계산하지 않습니다.';
  if(m.current.cost===null)return '초기에는 목표 통과 배치가 있었지만 현재 생존 집단에는 없습니다. 이전에 찾은 비용과 현재의 목표 달성을 구분하세요.';
  if(m.decrease===0)return `목표 통과 최저비용은 ${m.start.cost} → ${m.current.cost}점입니다. 초기 집단 대비 추가 비용 감소는 0점입니다. 같은 비용에서도 성능과 설치 위치는 다를 수 있습니다.`;
  return `목표 통과 최저비용은 ${m.start.cost} → ${m.current.cost}점으로 ${Math.abs(m.decrease)}점 ${m.decrease>0?'감소':'증가'}했습니다. 이 값은 두 집단의 관측값 차이이며, 같은 개체의 성장이나 모든 성능의 향상을 뜻하지 않습니다.`;
 }
 function chart(m){
  const valid=m.series.filter(s=>s.cost!==null);if(!valid.length)return '<p>이 시점까지 목표 통과 배치가 없어 비용 곡선을 표시할 수 없습니다.</p>';
  const x0=66,x1=836,y0=28,y1=206,maxX=Math.max(1,...m.series.map(s=>s.nfe)),maxY=Math.max(1,...valid.map(s=>s.cost))*1.12;
  const x=s=>x0+(x1-x0)*s.nfe/maxX,y=c=>y1-(y1-y0)*c/maxY;
  const lines=[];let points=[];for(const s of m.series){if(s.cost===null){if(points.length)lines.push(points.join(' '));points=[];}else points.push(x(s).toFixed(2)+','+y(s.cost).toFixed(2));}if(points.length)lines.push(points.join(' '));
  let body='';for(let i=0;i<=4;i++){const yy=y1-(y1-y0)*i/4,xx=x0+(x1-x0)*i/4;body+=`<path d="M${x0} ${yy}H${x1}" stroke="#dbe5ed"/><text x="${x0-9}" y="${yy+5}" text-anchor="end">${(maxY*i/4).toFixed(0)}</text><text x="${xx}" y="${y1+24}" text-anchor="middle">${Math.round(maxX*i/4).toLocaleString('ko-KR')}</text>`;}
  body+=lines.map(p=>`<polyline points="${p}" fill="none" stroke="#087da4" stroke-width="3"/>`).join('');
  if(m.start?.cost!==null&&m.start?.cost!==undefined)body+=`<path d="M${x0} ${y(m.start.cost)}H${x1}" stroke="#7954a0" stroke-width="2" stroke-dasharray="7 5"/>`;
  const final=m.series.at(-1);if(final?.cost!==null&&final?.cost!==undefined)body+=`<circle cx="${x(final)}" cy="${y(final.cost)}" r="6" fill="#bb4229" stroke="white" stroke-width="2"/>`;
  return `<svg viewBox="0 0 900 272" role="img" aria-label="선택한 ${m.generation}세대까지의 목표 통과 최저비용. 보라 파선은 초기 집단 비용, 파란 선은 각 세대 생존 집단 비용입니다."><g fill="#29485b" font-size="14">${body}<text x="66" y="18">합성 비용점수 · 낮을수록 저렴</text><text x="451" y="262" text-anchor="middle">누적 진화 평가 횟수 (NFE)</text></g></svg>`;
 }
 function render(zero,run,initialId,currentId){
  const host=document.getElementById('costProgress');if(!host)return;
  const m=model(zero,run);
  if(!m){host.innerHTML='<p>정상 저장된 세대 자료를 불러오면 초기 집단과 비교할 수 있습니다.</p>';return;}
  const row=(label,s)=>`<tr><th scope="row">${label}</th><td>${s?s.qualified+' / '+s.total+'개':'미기록'}</td><td>${s?(s.cost===null?'목표 통과 없음':s.cost+'점'):'미기록'}</td><td>${s?`${s.ties.length}개 고유 X${s.rawTieRows>s.ties.length?` · 원시 ${s.rawTieRows}행`:''}`:'미기록'}</td></tr>`;
  host.innerHTML=`<h3>초기 집단과 현재 세대의 비용</h3><p id="costProgressStory">${story(m)}</p><div class="tableWrap"><table><thead><tr><th scope="col">비교 집단</th><th scope="col">기준 충족 / 전체</th><th scope="col">관측 최저비용</th><th scope="col">같은 비용의 고유 배치</th></tr></thead><tbody>${row('초기 집단 · 0세대',m.start)}${row('현재 집단 · '+m.generation+'세대',m.current)}</tbody></table></div><p>배치 선택은 배치 결과의 ‘고유 배치 해 탐색’에서 한 번만 수행합니다. 같은 설치벡터로 반복 평가된 ID는 삭제하지 않고 한 배치로 묶어 집계합니다.</p><a href="#frontInsight">고유 배치 해 탐색으로 이동</a><div class="costCurve">${chart(m)}</div><p class="costCurveLegend"><span>━ 파란 선: 각 세대 기준 충족 최저비용</span> <span>┄ 보라 파선: 0세대 기준</span> <span>● 빨간 점: 표시 중인 세대</span></p><label class="costSeekLabel" for="costSeek">비교 시점 · ${m.generation} / ${m.latest}세대</label><input id="costSeek" type="range" min="0" max="${m.latest}" step="1" value="${m.generation}" aria-valuetext="${m.generation}세대"><p>슬라이더를 놓으면 두 지도와 해집합도 해당 세대로 이동합니다. 곡선은 현재 선택 시점까지만 표시하고, 기준 충족 해가 없는 구간은 선을 끊습니다.</p><p>${m.fixedCost?'보유 장비 전부 사용 조건에서는 설치 대수와 단가로 비용이 고정됩니다.':'비용 감소는 모델 성능과의 절충일 수 있습니다. 이 곡선은 참 Pareto 전선 수렴 인증이 아닙니다.'}</p>`;
  document.getElementById('costSeek').onchange=()=>LiveReplay.seek(+document.getElementById('costSeek').value);
  const nav=document.createElement('div');nav.className='costNavigation';nav.setAttribute('aria-label','비용 비교 세대 이동');
  for(const [label,g,disabled] of [['처음 시점',0,m.generation===0],['이전 10세대',Math.max(0,m.generation-10),m.generation===0],['다음 10세대',Math.min(m.latest,m.generation+10),m.generation===m.latest],['마지막 시점',m.latest,m.generation===m.latest]]){const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=disabled;button.onclick=()=>LiveReplay.seek(g);nav.appendChild(button);}
  document.getElementById('costSeek').insertAdjacentElement('afterend',nav);
 }
 return {model,population,story,chart,render};
})();
