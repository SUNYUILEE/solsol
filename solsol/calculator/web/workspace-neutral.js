'use strict';
// Narrow adapters on the original workbench, not a substitute workbench.
(()=>{
 renderSettingSummaries=function(){
  if(!draft||!registered())return;const c=draft.sensors[draft.sensor],s=selection(),r=s?.resource_contract;
  if($('limitSummary'))$('limitSummary').textContent=r?resourceSummary({_resource_contract:r}):registered().sensors.map(v=>v.name+' '+(c[v.id+'_minimum']??0)+'–'+(c[v.id+'_stock']??'명세 참조')+'대').join(' · ');
  if($('budgetSummary'))$('budgetSummary').textContent='초기 세대 0 + 진화 '+draft.optimizer.generations+'세대 · 최적화 평가 예산 '+draft.optimizer.population*(draft.optimizer.generations+1)+'회 · 준비/진단 평가는 별도 기록';
  if($('costBreakdown')){const p=$('costBreakdown');p.replaceChildren();if(r?.cost)evidenceTable(p,['비용 항목','값'],[...Object.entries(r.cost.sensor_unit_costs),['공유 지점 비용',r.cost.site_cost]]);else noteText(p,'등록 모델의 센서 비용·공유 지점 비용을 사용합니다. 상세 항목은 센서 설정과 저장된 실행 명세에서 확인합니다.');}
 };
 const originalReplacedResourceField=replacedResourceField;
 replacedResourceField=function(key,cid){return originalReplacedResourceField(key,cid)||cid==='ABC_COVERAGE_RESOURCE_V1'&&(/^[ABC]_(stock|minimum|cost)$/.test(key)||['inventory_mode','budget','activation_cost'].includes(key));};
 const palette=['#287dad','#c18421','#388e62','#885ba8','#b94b72','#347a78'];
 const originalHeader=renderHeader,originalSettings=renderSettings,originalInspector=renderInspector;
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 renderHeader=function(){originalHeader();const old=document.querySelector('.sensorChooser [role=group]');if(old)old.hidden=true;};
 sensorVisual=function(id){const sensors=(mode==='result'&&run?.metadata?run.metadata:registered())?.sensors||[];const i=Math.max(0,sensors.findIndex(s=>s.id===id));return {color:palette[i%palette.length],letter:id.slice(0,2),name:sensors[i]?.name||id,shape:['circle','diamond','square','triangle'][i%4],dash:['','10 6','3 5','12 4 2 4'][i%4]};};
 mapHTML=function(p,row){
  if(!p)return '';const meta=p._metadata||(configured()&&mode==='result'?run.metadata:registered());if(!meta)return '';
  renderSensorLegend(meta);const unit=(p.map_metres||1000)/800;
  let svg=p.geometry?LiveCore.map(p,null,{layer:'none',candidates:false,defense:$('showArea').checked,demand:false,candidateLabels:false}):'<svg viewBox="0 0 930 945" role="img" aria-label="명시 후보지 지도 · 평가영역 경계 미제공"><rect x="60" y="50" width="800" height="800" fill="#f4f8fa"/><text x="60" y="30">명시 좌표 · 평가영역 경계 미제공</text></svg>';
  if(p.geometry){const doc=new DOMParser().parseFromString(svg,'image/svg+xml'),bar=doc.querySelector('[data-scale-metres]');if(bar){const length=(p.map_metres||1000)/5;bar.setAttribute('data-scale-metres',length);bar.setAttribute('d',`M90 899h${length/unit}`);const text=bar.nextElementSibling;if(text){text.setAttribute('x',90+length/unit/2);text.textContent=Number((length/1000).toFixed(3))+' km';}svg=doc.documentElement.outerHTML;}}
  let marks='';const layer=$('mapLayer').value;
  for(const b of p.obstacles||[])marks+=`<rect data-los-obstacle x="${60+b.xmin/unit}" y="${850-b.ymax/unit}" width="${(b.xmax-b.xmin)/unit}" height="${(b.ymax-b.ymin)/unit}" fill="#6c7a83" opacity=".3"><title>높이 ${escape(b.zmax-b.zmin)} m · LOS 장애물</title></rect>`;
  if($('showDemand').checked)for(let k=0;k<(p.demand||[]).length;k++){
   const point=p.demand[k],covered=row?.neutral_spatial?.covered_points?.[k]??row?.covered_points?.[k];
   marks+=`<circle data-model-observation="${covered===undefined?'PREVIEW':covered?'COVERED':'UNCOVERED'}" cx="${60+point[0]/unit}" cy="${850-point[1]/unit}" r="3" fill="${covered===undefined?'#94a6b2':covered?'#188354':'#b15143'}"><title>평가 지점 ${k+1} · ${covered===undefined?'계산 전':covered?'모델 커버':'모델 미커버'}</title></circle>`;
  }
  p.sites.forEach((point,i)=>{
   const x=60+point[0]/unit,y=850-point[1]/unit;
   if(layer!=='none'||!row||row.X[i].some(Boolean))marks+=`<circle data-site="${i+1}" cx="${x}" cy="${y}" r="3" fill="#798894"><title>후보지 ${i+1}</title></circle>`;
   if($('showLabels').checked&&(layer!=='none'||!row||row.X[i].some(Boolean)))marks+=`<text x="${x+5}" y="${y-5}" font-size="10">${i+1}</text>`;
   meta.sensors.forEach((s,j)=>{if(row?.X?.[i]?.[j]&&(layer==='all'||layer==='none'||layer===s.id)){
    if(layer!=='none')marks+=sensorRange(s.id,x,y,(p.radii[j]||0)/unit);
    marks+=sensorMarker(s.id,x,y,j,meta.sensors.length,i+1,row.id);
   }});
  });
  return svg.replace(/<\/svg>$/,clipMapMarks(marks)+'</svg>');
 };
 renderInspector=function(){
  if(mode==='result'&&configured())return originalInspector();
  const body=$('inspectorBody');body.replaceChildren();const meta=registered();
  const problem=preview?.problem;
  if(!problem?.sites?.length||site===null){noteText(body,'지도에서 후보지를 선택하면 좌표·센서 범위·설치 조건을 확인합니다.');return;}
  const point=problem.sites[site];if(!point)return;
  evidenceTable(body,['항목','값'],[['후보지',site+1],['X (m)',point[0]],['Y (m)',point[1]],...meta.sensors.map((s,j)=>[s.name+' 수평 범위',(problem.radii[j]||0)+' m'])]);
 };
 renderSettings=function(){
  originalSettings();if(!draft||!registered())return;const c=draft.sensors[draft.sensor];
  if(setting==='sensors'&&registered().id==='ABC_COVERAGE_RESOURCE_V1'){
   const g=group('센서 관계·LOS');const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!!c.los_enabled;check.onchange=()=>{c.los_enabled=check.checked;updateDraft();};label.append(check,document.createTextNode(' 명시적인 장애물 LOS 적용'));g.append(label);
   for(const [key,title] of [['relations','공동 커버 관계'],['obstacles','3D 장애물']]){
    const d=document.createElement('details'),summary=document.createElement('summary');summary.textContent=title+' · 구조 입력';d.append(summary);const textarea=document.createElement('textarea');textarea.value=JSON.stringify(c[key]||[],null,2);textarea.setAttribute('aria-label',title);textarea.onchange=()=>{try{const value=JSON.parse(textarea.value);if(!Array.isArray(value))throw Error('배열 입력이 필요합니다.');c[key]=value;updateDraft();}catch(e){notice(e.message);}};d.append(textarea);g.append(d);
   }
   noteText(g,'관계는 같은 지점의 공동 커버를 뜻합니다. 측정 오차·조향·장비 융합 수식은 포함하지 않습니다.');
  }
 };
})();
