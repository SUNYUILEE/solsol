'use strict';
const LiveWorkspace=(()=>{
 const resourceNames={off:'제한 끔',all:'전부 사용 · 수량 고정',partial:'일부 사용 · 수량 상한'};
 const shapeNames={circle:'원형',square:'사각형',hexagon:'정육각형',overlap:'겹치는 두 원'};
 const defaults={resource_mode:'off',radar_stock:10,eo_stock:30,area_factor:1,identification_area_factor:.5,initializer:'random',map_km:20,candidate_count:100,site_seed:0,geometry_contract:'legacy_square_v1',objective_contract:'binary_coverage_v1'};
 const val=(c,k)=>c?.[k]??defaults[k];
 const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function scaleMap(p,extentMetres){
  if(!p)return '<div class="scaleEmpty">아직 실행 결과가 없습니다.<br>오른쪽에서 다음 계산의 크기를 확인하세요.</div>';
  const extent=Math.max(p.map_metres||20000,extentMetres||0),unit=extent/800,cx=60+p.geometry.center[0]/unit,cy=850-p.geometry.center[1]/unit;
  let svg=LiveCore.map(p,null,{defense:true,candidates:true,demand:false,layer:'none',extentMetres:extent});
  // Same metre-to-pixel transform as the actual placement map. These rulers are not solutions.
  const rr=p.radii[0]/unit,re=p.radii[1]/unit;
  const rulers=`<g data-size-ruler="true"><circle cx="${cx}" cy="${cy}" r="${rr}" fill="#087ca8" fill-opacity=".08" stroke="#0077a9" stroke-width="5"/><circle cx="${cx}" cy="${cy}" r="${re}" fill="none" stroke="#ad5200" stroke-width="5" stroke-dasharray="12 8"/><path d="M${cx} ${cy}h${rr}" stroke="#0077a9" stroke-width="3"/><path d="M${cx} ${cy}v${re}" stroke="#ad5200" stroke-width="3"/><circle cx="${cx}" cy="${cy}" r="6" fill="#18364b"/><text x="${cx+rr/2}" y="${cy-15}" text-anchor="middle" font-size="26" font-weight="bold" paint-order="stroke" stroke="white" stroke-width="7" fill="#00628e">R ${p.radii[0]/1000} km</text><text x="${cx+15}" y="${cy+re*.65}" font-size="26" font-weight="bold" paint-order="stroke" stroke="white" stroke-width="7" fill="#944600">E ${p.radii[1]/1000} km</text></g>`;
  return svg.replace('</svg>',rulers+'</svg>').replace(`${(p.map_metres||20000)/1000}km 지도와 평가영역 및 센서 배치`,'같은 축척의 평가영역과 센서 반경 크기 비교 · 설치 결과 아님');
 }
 function rows(before,after,bp,ap){
  const spec=[['평가영역 모양',c=>shapeNames[c.shape]],['탐지 평가 면적',(_,p)=>p?p.geometry.area_km2.toFixed(2)+' km²':'확인 중'],['식별 평가 면적',c=>val(c,'objective_contract')==='layered_mission_v7'?(36*Math.PI*val(c,'identification_area_factor')).toFixed(2)+' km² (현재 사용함)':'사용 안 함 (전체 면적 동일 적용)'],['Radar 반경',c=>c.radar+' km'],['EO/IR 반경',c=>c.eo+' km'],['목적함수',c=>({full_area_tradeoff_v6:'전체영역 절충 · 목표선 분리 · V6',layered_mission_v7:'단계형 평가영역 · V7',binary_coverage_v1:'전체 영역 충족률 · V2',max_margin_quality_v3:'거리 여유 · V3 비교',zoned_nominal_v4:'중심 식별·외곽 탐지 · V4 격리'}[val(c,'objective_contract')])],['자원 규칙',c=>resourceNames[val(c,'resource_mode')]],['보유 Radar / EO/IR',c=>val(c,'resource_mode')==='off'?'보유량 미지정':val(c,'radar_stock')+' / '+val(c,'eo_stock')+'대'],['유전자·진화 설계',c=>c.design+' 설계'],['참조방향 / 개체 수',c=>`${(+c.h+1)*(+c.h+2)/2}방향 / ${{7:36,12:92,19:212}[c.h]}개체 (H=${c.h})`],['요청 세대 / 반복번호',c=>`${c.generations}세대 / ${c.seed}`],['초기화',c=>({random:'무작위',greedy:'Greedy + 무작위',milp:'MILP/ε + 무작위'}[val(c,'initializer')])]];
  spec.unshift(['지도 / 후보 배치',c=>`${val(c,'map_km')}×${val(c,'map_km')} km · ${val(c,'candidate_count')}곳 · ${(val(c,'candidate_count')/val(c,'map_km')**2).toFixed(3)}곳/km² · ${val(c,'site_seed')===0?'기본 배치':'배치 '+val(c,'site_seed')}`]);
  return spec.map(([label,f])=>{const a=before?f(before,bp):'실행 없음',b=f(after,ap),changed=!!before&&a!==b;return `<tr${changed?' class="changed"':''}><th scope="row">${label}</th><td>${esc(a)}</td><td>${changed?'<span class="changeChip">변경</span> ':''}${esc(b)}</td></tr>`;}).join('');
 }
 function same(a,b){
  if(!a)return false;
  const fieldsSame=['radar','eo','shape','area_factor','identification_area_factor','map_km','candidate_count','site_seed','design','h','seed','initializer','generations','resource_mode','radar_stock','eo_stock','objective_contract'].every(k=>((k==='radar_stock'||k==='eo_stock')&&val(a,'resource_mode')==='off'&&val(b,'resource_mode')==='off')||val(a,k)===val(b,k));
  const geometrySame=(a.shape!=='square'&&b.shape!=='square')||val(a,'geometry_contract')===val(b,'geometry_contract');
  return fieldsSame&&geometrySame;
 }
 const diagnosticCache=new WeakMap();
 function difficulty(p){
  if(diagnosticCache.has(p))return diagnosticCache.get(p);
  const N=p.demand.length,maxima=[0,0];
  for(const site of p.sites){const n=[0,0];for(const q of p.demand){const d=(site[0]-q[0])**2+(site[1]-q[1])**2;for(let t=0;t<2;t++)if(d<=p.radii[t]**2)n[t]++;}for(let t=0;t<2;t++)maxima[t]=Math.max(maxima[t],n[t]);}
  const result={maxima,ratios:maxima.map(x=>x/N),necessary:[.95,.9].map((t,i)=>maxima[i]?Math.ceil(Math.ceil(t*N-1e-9)/maxima[i]):null)};
  diagnosticCache.set(p,result);return result;
 }
 function scenario(p,c){
  if(!p)return '<p class="pendingScenario">유효한 조건을 선택하면 면적과 한 대의 최대 도달률을 확인합니다.</p>';
  const d=difficulty(p),g=p.geometry,n=d.necessary,card=(label,value,explain)=>`<article><span>${label}</span><strong>${value}</strong><small>${explain}</small></article>`;
  return card('평가할 면적',g.area_km2.toFixed(1)+' km²',`${val(c,'area_factor')*100}% · 모든 도형의 기준 113.10 km² · 길이는 √배율로 변화`)+card('Radar 한 대 최대 탐지',(d.ratios[0]*100).toFixed(1)+'%',`실제 ${p.sites.length}후보 중 최대 · 목표 95% · 필요 하한 ${n[0]??'계산 불가'}대 (충분조건 아님)`)+card('EO/IR 한 대 최대 도달',(d.ratios[1]*100).toFixed(1)+'%',`단독 식별률 아님 · 목표 90% · 필요 하한 ${n[1]??'계산 불가'}대 (충분조건 아님)`);
 }
 function describeResource(c){const m=val(c,'resource_mode');return m==='off'?'보유 대수 제약을 추가하지 않습니다. 미사용 보유량은 정의되지 않으며, 빈 후보지 수와 혼동하지 않습니다.':m==='all'?`Radar ${c.radar_stock}대와 EO/IR ${c.eo_stock}대를 정확히 모두 설치합니다. 이 실행의 비용은 ${6*c.radar_stock+2*c.eo_stock}점으로 고정되므로 위치에 따른 탐지·식별을 비교합니다.`:`Radar는 최대 ${c.radar_stock}대, EO/IR는 최대 ${c.eo_stock}대입니다. 더 적게 써도 목표를 만족하면 허용합니다. 목표 달성 후에도 남은 세대 동안 비용·성능을 탐색합니다.`;}
 function outcome(point,run,p){
  if(!point)return {summary:'배치를 선택하면 목표 달성률과 자원 사용량을 표시합니다.',html:'<tr><td colspan="5">배치 선택 대기</td></tr>'};
  const c=run.config,m=val(c,'resource_mode'),N=p.demand.length,counts=point.sensor_counts,z=LiveSelection.zones(p,c.objective_contract),denominators=[z.detectionN,z.identificationN],covered=[Math.round(point.performance[0]*denominators[0]),Math.round(point.performance[1]*denominators[1])];
  const row=(a,b,c,d,e)=>`<tr><th scope="row">${a}</th><td>${b}</td><td>${c}</td><td>${d}</td><td>${e}</td></tr>`;
  let html=[.95,.90].map((t,i)=>{const dn=denominators[i],need=Math.ceil(t*dn-1e-9),gap=Math.max(0,need-covered[i]),pp=Math.max(0,(t-point.performance[i])*100),zone=c.objective_contract==='zoned_nominal_v4'?(i?'중심부':'외곽부'):'전체 영역';return row(i?'식별':'탐지',`${zone} ${t*100}% · ${need}/${dn}점 이상`,`${(100*point.performance[i]).toFixed(2)}% · ${covered[i]}/${dn}점`,`${pp.toFixed(2)}%p · ${gap}개 평가점 부족`,gap?'목표 미달':'목표 충족');}).join('');
  for(let i=0;i<2;i++){const stock=val(c,i?'eo_stock':'radar_stock'),unused=stock-counts[i],ok=m==='off'||(m==='all'?unused===0:unused>=0);html+=row(i?'EO/IR 자원':'Radar 자원',m==='off'?'보유량 미지정':`${stock}대 ${m==='all'?'모두 설치':'이내'}`,counts[i]+'대 설치',m==='off'?'미사용량 해당 없음':unused>=0?unused+'대 미사용':(-unused)+'대 초과',ok?(m==='all'?'정확 수량 충족':m==='partial'?'보유 수량 이내':'대수 제약 없음'):'자원 조건 위반');}
  html+=row('설치 비용','Radar 6점 · EO/IR 2점',`${point.cost}점 = ${counts[0]}×6 + ${counts[1]}×2`,m==='off'?'보유 예산 미지정':`${6*(val(c,'radar_stock')-counts[0])+2*(val(c,'eo_stock')-counts[1])}점의 미사용 장비 가치`,m==='all'?'전부 사용: 비용 상수':'일부 배치 간 비용·성능 절충');
  return {summary:`배치 #${point.id} · ${resourceNames[m]} · ${point.qualified?'임무·자원 조건 통과':'목표 또는 자원 조건 미달'} · ${run.snapshot.generation}세대의 실제 해`,html};
 }
 function limits(run){if(!run)return '결과 없음 · 배치 조건에서 계산을 시작하세요.';const s=run.snapshot,i=run.initialization,state={queued:'준비',initializing:'초기화',running:'계산 중',saving:'결과 검증·저장',completed:'요청 세대 계산 완료',cancelled:'사용자 중지',time_limit:'시간 제한',failed:'실패'}[run.state]||'상태 확인 필요';return `요청 ${run.config.generations}세대 / 현재 표시 ${s?.generation??'준비 중'}세대 / 최신 완료 ${Math.max(0,run.latest_generation)}세대. 표시 시점의 진화 평가 ${s?.evaluations?.toLocaleString()??0}회. 초기화 준비 ${i?.seconds??'미확정'}초·${i?.preparation_evaluations??'미확정'}회와 진화 평가는 별개입니다. 실행 상태: ${state}. 진화 시간 상한 300초이며 ${run.state==='time_limit'?'시간 제한으로 요청 세대에 도달하기 전에 중단되었습니다.':run.state==='cancelled'?'사용자 중지로 부분 결과입니다.':run.state==='completed'?'요청 계산이 종료된 것이며 전역 최적성 인증이 아닙니다.':'진행 중 값은 최종 결과가 아닙니다.'} 성능은 500m 표본 기준이며 250m 검산 상태는 위 별도 안내를 확인하세요. 재고를 모두 설치해도 위치·반경 때문에 목표에 못 미칠 수 있습니다.`;}
 return {scaleMap,rows,same,describeResource,outcome,limits,resourceNames,val,difficulty,scenario};
})();
if(typeof module!=='undefined')module.exports=LiveWorkspace;
