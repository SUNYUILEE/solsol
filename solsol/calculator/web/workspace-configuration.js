'use strict';
// Recompute glyph scale after a native resize as well as map render/zoom.
let sensorResizeFrame;
window.addEventListener('resize',()=>{cancelAnimationFrame(sensorResizeFrame);sensorResizeFrame=requestAnimationFrame(syncSensorSymbols);});
// Configuration and result metadata come from the same server used by AI clients.
let registryData=null,configurationSummary=null,axes=[],axesRun=null;
const historical={settings:renderSettings,header:renderHeader,apply,normalize:M.normalize,validate:M.validate,label:M.label,inspector:renderInspector,dock:renderDock,map:mapHTML,readings:renderMapReadings,comparison:renderConditionComparison,facts:renderRowFacts,fixed:renderFixedConditions,copy:$('copyRun').onclick};
const registered=()=>registryData?.bundles.find(b=>b.id===draft?.sensor);
const configured=()=>!!run?.research_configuration;
function resultRows(){return typeof observedResultRows==='function'?observedResultRows():run?.rows||[];}

function sensorVisual(id){const key=id==='eo'?'eoir':id;return ({radar:{name:'Radar',letter:'R',shape:'circle',color:'#006b9a',dash:''},rf_scanner:{name:'RF',letter:'F',shape:'diamond',color:'#a65f00',dash:'10 5'},eoir:{name:'EO/IR',letter:'E',shape:'square',color:'#176b44',dash:'2 5'}})[key]||{name:id,letter:'S',shape:'triangle',color:'#75489a',dash:'8 3 2 3'};}
function sensorGlyph(id){const v=sensorVisual(id),shape=v.shape==='circle'?'<circle r="9"/>':v.shape==='diamond'?'<path d="M0 -11L11 0 0 11 -11 0Z"/>':v.shape==='square'?'<rect x="-9" y="-9" width="18" height="18" rx="1"/>':'<path d="M0 -10L10 9H-10Z"/>';return `<g fill="white" stroke="${v.color}" stroke-width="2">${shape}</g><text x="0" y="3.5" text-anchor="middle" fill="${v.color}" font-size="10" font-weight="800" stroke="none">${v.letter}</text>`;}
function sensorMarker(id,x,y,j,n,site,rowId){const v=sensorVisual(id);return `<g data-sensor-marker data-sensor-id="${id}" data-symbol="${v.shape}" data-letter="${v.letter}" data-anchor-x="${x}" data-anchor-y="${y}" data-offset="${j-(n-1)/2}" data-marker-site="${site}" transform="translate(${x} ${y})"><title>${v.name} · 후보 ${site} · 행 ${rowId}</title>${sensorGlyph(id)}</g>`;}
function sensorRange(id,x,y,r,reference=false){const v=sensorVisual(id);return `<circle data-sensor-range="${id}" data-range-style="${v.dash||'solid'}" cx="${x}" cy="${y}" r="${r}" fill="${reference?'none':v.color}" fill-opacity=".025" stroke="${v.color}" stroke-width="1.6" vector-effect="non-scaling-stroke" stroke-dasharray="${v.dash}" opacity=".85"><title>${v.name} 입력 반경${reference?' 비교 · 설치 위치 아님':''}</title></circle>`;}
function sensorRangeLabel(id,x,y,r,km,index){const v=sensorVisual(id),angle=[-.2,-1.3,2.6][index%3],lx=x+Math.cos(angle)*r,ly=y+Math.sin(angle)*r;return `<text data-range-label="${id}" x="${lx}" y="${ly}" text-anchor="middle" fill="${v.color}" stroke="white" stroke-width="4" paint-order="stroke" font-size="19" font-weight="700">${v.letter} · ${km} km</text>`;}
function syncSensorSymbols(){for(const host of [$('mainMap'),$('initialMap'),$('largeMap'),$('largeInitialMap'),$('infeasibleMap'),...document.querySelectorAll('.qualityCompareMaps>div,#qualityWitnessMaps>div')]){const svg=host?.querySelector('svg');if(!svg)continue;const box=svg.getBoundingClientRect(),v=svg.viewBox.baseVal,scale=Math.min(box.width/v.width,box.height/v.height);if(!(scale>0))continue;const plot=svg.querySelector('clipPath rect'),left=+(plot?.getAttribute('x')||60),top=+(plot?.getAttribute('y')||50),margin=12/scale;for(const label of host.querySelectorAll('[data-range-label]')){label.setAttribute('font-size',12/scale);label.setAttribute('stroke-width',3/scale);}for(const marker of host.querySelectorAll('[data-sensor-marker]')){const ax=+marker.dataset.anchorX,ay=+marker.dataset.anchorY,offset=+marker.dataset.offset;const base=Math.max(left+margin+22/scale,Math.min(left+800-margin-22/scale,ax)),x=base+offset*22/scale,y=Math.max(top+margin,Math.min(top+800-margin,ay));marker.setAttribute('transform',`translate(${x} ${y}) scale(${1/scale})`);let leader=marker.querySelector('[data-marker-leader]');if(!leader){leader=document.createElementNS('http://www.w3.org/2000/svg','line');leader.dataset.markerLeader='';leader.setAttribute('stroke','#526570');leader.setAttribute('stroke-width','1');marker.prepend(leader);}leader.setAttribute('x1',(ax-x)*scale);leader.setAttribute('y1',(ay-y)*scale);leader.setAttribute('x2',0);leader.setAttribute('y2',0);if(host.id==='mainMap'||host.id==='largeMap'){marker.setAttribute('role','button');marker.setAttribute('tabindex','0');marker.setAttribute('aria-label',sensorVisual(marker.dataset.sensorId).name+' · 후보 '+marker.dataset.markerSite+' 속성');marker.onclick=()=>{site=+marker.dataset.markerSite-1;renderInspector();showSelectionProperties();};marker.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();marker.onclick();}};}}}}

function renderSensorLegend(meta){const old=$('secondLegend').parentElement;old.hidden=true;let el=$('registeredLegend');if(!el){el=document.createElement('span');el.id='registeredLegend';old.after(el);}el.replaceChildren();const enabled=mode==='result'&&configured()?run.research_configuration.enabled_sensor_ids:selection()?.enabled_sensor_ids;meta.sensors.forEach(s=>{const v=sensorVisual(s.id),item=document.createElement('span');item.className='sensorLegendItem';item.innerHTML=`<svg width="27" height="27" viewBox="-14 -14 28 28" aria-hidden="true">${sensorGlyph(s.id)}</svg><svg width="30" height="16" aria-hidden="true"><path d="M0 8H30" stroke="${v.color}" stroke-width="2" stroke-dasharray="${v.dash}"/></svg>`;item.append(document.createTextNode(v.name+(enabled&&!enabled.includes(s.id)?' (비활성)':'')));el.append(item);});const hint=document.createElement('span');hint.className='formNote';hint.textContent='기호 연결선 끝 = 실제 설치 위치';el.append(hint);}
const selection=()=>draft.research.selections[draft.sensor];
const valueText=(m,v)=>v===undefined||v===null?'미계산':(v*(m.display_scale||1)).toFixed(2)+' '+m.unit;
// Presentation categories only; observation and position status are model outputs.
function observationColor(status){if(['CONDITIONAL_LOCAL_BOUND','BEARING_AND_LOCAL_POSITION_BOUND'].includes(status))return '#20794c';if(['SINGLE_ARRAY_BEARING_ONLY','MULTI_ARRAY_BEARING_ONLY'].includes(status))return '#1685ba';if(status==='DEGENERATE_GEOMETRY')return '#b07627';return '#687d88';}
function prepareResearch(){
 for(const b of registryData.bundles){draft.sensors[b.id]??=structuredClone(registryData.ui_models[b.id].defaults);}

 M.setModelSchemas(registryData.ui_models||{});
 const rfBundle=registryData.bundles.find(b=>b.id===RF),rfSchema=registryData.ui_models?.[RF];
 if(rfBundle&&rfSchema&&!draft.sensors[RF]?.evaluator_version)draft.sensors[RF]={...structuredClone(rfSchema.defaults),...draft.sensors[RF],evaluator_version:rfBundle.version};
 draft.research??={schema:'SOLSOL_DRAFT_SELECTIONS_V1',goalsEnabled:false,radar_coverage:95,second_coverage:90,selections:{}};
 for(const b of registryData.bundles){draft.research.selections[b.id]??={enabled_sensor_ids:b.sensors.map(s=>s.id),objective_ids:[...b.default_objective_ids],diagnostic_ids:[],solver_policy:'generic_v1',ref_partitions:1,referenceMode:'auto'};}
 if(registryData.calculator_capabilities?.initialization_owner==='CALCULATOR'&&draft.research.initializationVersion!=='calculator-common-initialization-v1'){for(const s of Object.values(draft.research.selections)){s.solver_policy='generic_v1';s.initializer??=draft.optimizer.initializer||'random';}draft.research.initializationVersion='calculator-common-initialization-v1';draft.migrationNotice='다음 계산은 공통 초기화로 준비합니다. 저장된 과거 실행은 변경하지 않습니다.';}
 draft.sensors.TOY_DIMENSION_V1??={n_candidates:3,n_constraints:0};
 draft.schema='SOLSOL_SHARED_DRAFT_V4';
}
M.label=cid=>registryData?.bundles.find(b=>b.id===cid)?.name||historical.label(cid);
M.validate=d=>{if(d.schema!=='SOLSOL_SHARED_DRAFT_V4')return historical.validate(d);if(!d.research||d.research.schema!=='SOLSOL_DRAFT_SELECTIONS_V1'||!registryData?.bundles.some(b=>b.id===d.sensor))throw Error('시나리오 구성 버전을 확인하세요');return structuredClone(d);};
function archiveRowCount(value=run){return value?.view_schema==='SOLSOL_CONFIGURABLE_SUMMARY_V1'?value.collections.archive.count:(value?.rows?.length??0);}
M.normalize=(p,cid,id)=>{if(!['SOLSOL_CONFIGURABLE_VIEW_V1','SOLSOL_CONFIGURABLE_SUMMARY_V1'].includes(p.view_schema))return historical.normalize(p,cid,id);if(p.experiment_contract_id!==cid||p.run_id!==id||p.problem.config_sha256!==p.config_sha256)throw Error('실행·고정 설정 결속 불일치');const metrics=p.registry.objective_order.map(id=>p.metadata.metrics.find(m=>m.id===id));for(const r of [...(p.archive||[]),...p.initial_archive])if(r.run_id!==id||r.config_sha256!==p.config_sha256||r.F.length!==p.registry.objective_order.length||r.X.some(x=>x.length!==p.registry.sensor_order.length))throw Error('원시 행의 설정·차원 불일치');return {...p,rows:p.archive||[],initialRows:p.initial_archive,latest:p.checkpoints.length-1,seconds:p.elapsed_seconds,history:p.checkpoints,qualityLabels:metrics.slice(0,2).map(m=>m.name)};};
const configurableClusterCache=new WeakMap();
const uncompressedConfigurableCluster=rows=>{if(configurableClusterCache.has(rows))return configurableClusterCache.get(rows);const groups=[],bits=new Map(rows.map(r=>[r,M.rowX(r)]));for(const r of rows){const near=o=>{const a=bits.get(r),b=bits.get(o);let d=0;for(let i=0;i<a.length;i++)for(let j=0;j<a[i].length;j++)if(a[i][j]!==b[i][j]&&++d>=3)return false;return true;};const group=groups.find(g=>g.every(near));if(group)group.push(r);else groups.push([r]);}configurableClusterCache.set(rows,groups);return groups;};
// Preserve complete-link distance <3 and input order; pack only binary, equal-shaped X.
function packedCluster(rows,rowX,fallback){
 const matrices=rows.map(rowX);
 for(const x of matrices){if(!Array.isArray(x))return fallback(rows);for(const a of x){if(!Array.isArray(a))return fallback(rows);for(const v of a)if(v!==0&&v!==1)return fallback(rows);}}
 const shape=matrices[0]?.map(a=>a.length)||[];
 if(matrices.some(x=>!Array.isArray(x)||x.length!==shape.length||x.some((a,i)=>!Array.isArray(a)||a.length!==shape[i]||a.some(v=>v!==0&&v!==1))))return fallback(rows);
 const width=shape.reduce((a,b)=>a+b,0),bits=new Map();
 rows.forEach((r,k)=>{const words=new Uint32Array(Math.ceil(width/32));let index=0,count=0;for(const a of matrices[k])for(const v of a){if(v){words[index>>>5]|=1<<(index&31);count++;}index++;}bits.set(r,{words,count});});
 const near=(a,b)=>{const x=bits.get(a),y=bits.get(b);if(Math.abs(x.count-y.count)>=3)return false;let distance=0;for(let i=0;i<x.words.length;i++){let delta=(x.words[i]^y.words[i])>>>0;while(delta){if(++distance>=3)return false;delta=(delta&(delta-1))>>>0;}}return true;};
 const groups=[];for(const r of rows){const group=groups.find(g=>g.every(o=>near(r,o)));if(group)group.push(r);else groups.push([r]);}return groups;
}
M.cluster=rows=>{if(configurableClusterCache.has(rows))return configurableClusterCache.get(rows);const groups=packedCluster(rows,r=>M.rowX(r),uncompressedConfigurableCluster);configurableClusterCache.set(rows,groups);return groups;};
let mapClipSequence=0;
function clipMapMarks(marks,x=60,y=50){const id='mapPlotClip'+(++mapClipSequence);return `<defs><clipPath id="${id}"><rect x="${x}" y="${y}" width="800" height="800"/></clipPath></defs><g data-map-marks clip-path="url(#${id})">${marks}</g>`;}
function renderSchemaFields(schema,tab,values){for(const section of schema.groups[tab]||[]){const g=group(section.title);for(const spec of section.fields){if(spec.when&&Object.entries(spec.when).some(([k,v])=>values[k]!==v))continue;const source=spec.source==='common'?draft.common:values;if(spec.kind==='quantity')quantity(g,spec.label,spec.key,source,spec.unit,spec.step,spec.presets,spec.scale,spec.minimum,spec.maximum==='candidate_count'?draft.common.candidate_count:spec.maximum);else field(g,spec.label,spec.key,spec.choices,spec.unit,source);}for(const text of section.notes||[])noteText(g,text);if(section.slot){const node=document.createElement('div');node.id=section.slot;g.append(node);}}}

function directionCount(m,h){if(!Number.isInteger(m)||m<1||!Number.isInteger(h)||h<1)return 0;let n=1;for(let i=1;i<m;i++)n=n*(h+i)/i;return Math.round(n);}
function directionChoices(m,pop){return Array.from({length:m===1?1:255},(_,i)=>i+1).map(h=>({h,count:directionCount(m,h)})).filter(x=>x.count<=pop);}
function searchObjectiveCount(s=selection()){const c=draft.sensors[draft.sensor];return s.objective_ids.length-(!s.resource_contract&&!c?._resource_contract&&draft.sensor==='RADAR_EOIR'&&c?.resource_mode==='all'&&c?.objective_contract==='full_area_tradeoff_v6'&&s.objective_ids.includes('cost')?1:0);}
function effectivePartitions(s=selection(),m=searchObjectiveCount(s),pop=draft.optimizer.population){return s.referenceMode==='auto'?(directionChoices(m,pop).at(-1)?.h||1):(s.ref_partitions||1);}
function renderReferenceDirections(g,s=selection()){
 const m=searchObjectiveCount(s),pop=draft.optimizer.population;
 if(draft.optimizer.algorithm!=='NSGA-III'){noteText(g,'NSGA-II는 참조방향을 사용하지 않습니다.');return;}
 if(s.solver_policy!=='generic_v1'){noteText(g,'참조방향은 저장된 기존 재현 정책의 개체 수에 따라 결정됩니다.');return;}
 const choices=directionChoices(m,pop),auto=choices.at(-1),h=effectivePartitions(s),count=directionCount(m,h),fixed=s.referenceMode!=='auto';
 const rows=[['auto',auto?`개체 수에 맞춤 · ${auto.count}방향 (h=${auto.h})`:'현재 개체 수에 맞는 방향 없음'],...choices.map(x=>[String(x.h),`${x.count}방향 · 분할 h=${x.h}`])];
 if(fixed&&!choices.some(x=>x.h===h))rows.push([String(h),`저장값 ${count}방향 (h=${h}) · 개체 수 초과`]);
 selectControl(g,'NSGA-III 참조방향',rows,fixed?String(h):'auto',v=>{s.referenceMode=v==='auto'?'auto':'fixed';if(v!=='auto')s.ref_partitions=+v;updateDraft();renderSettings();},'referenceDirections');
 const p=document.createElement('p');p.id='referenceSummary';p.className='formNote';p.dataset.objectives=m;p.dataset.partitions=h;p.dataset.count=count;p.dataset.population=pop;p.textContent=`목적 ${m}개 · 참조방향 ${count}개 · 개체 ${pop}개. H = C(M+h−1, M−1).`;
 if(count>pop){p.classList.add('referenceError');p.textContent+=' 방향 수가 개체 수보다 큽니다. 방향 수를 다시 선택하거나 개체 수를 늘리세요.';}
 else if(h<m)p.textContent+=' 현재 격자는 모든 목적이 양수인 내부 방향이 없습니다.';
 g.append(p);noteText(g,fixed?'선택·저장된 분할 값을 유지합니다. 목적 수가 달라지면 방향 수도 달라집니다.':'현재 개체 수 안에서 가장 많은 균등 격자 방향을 선택합니다. 최적 성능을 보장하는 설정은 아닙니다.');
}

function renderCommonAlgorithm(g){const generic=selection().solver_policy==='generic_v1';selectControl(g,'탐색 방법',generic?[['NSGA-III','NSGA-III'],['NSGA-II','NSGA-II']]:[['NSGA-III','NSGA-III']],draft.optimizer.algorithm,v=>{draft.optimizer.algorithm=v;updateDraft();},'commonAlgorithm');}
function renderMetricControls(g,b=registered(),s=selection()){
for(const metric of b.metrics){const line=document.createElement('div');line.className='field';const order=s.objective_ids.indexOf(metric.id);selectControl(line,metric.name+' · '+metric.unit+' · '+(metric.direction==='maximize'?'최대화':'최소화'),[['objective','최적화 목적'],['diagnostic','진단만 계산'],['off','계산 결과에서 제외']],order>=0?'objective':s.diagnostic_ids.includes(metric.id)?'diagnostic':'off',v=>{s.objective_ids=s.objective_ids.filter(x=>x!==metric.id);s.diagnostic_ids=s.diagnostic_ids.filter(x=>x!==metric.id);if(v==='objective')s.objective_ids.push(metric.id);if(v==='diagnostic')s.diagnostic_ids.push(metric.id);updateDraft();renderSettings();},'metric_'+metric.id);if(order>=0){const up=document.createElement('button');up.textContent='목적 '+(order+1)+' · 위로';up.disabled=order===0;up.onclick=()=>{[s.objective_ids[order-1],s.objective_ids[order]]=[s.objective_ids[order],s.objective_ids[order-1]];updateDraft();renderSettings();};line.append(up);}const d=document.createElement('details'),sum=document.createElement('summary');sum.textContent='정의와 의존성';d.append(sum,document.createTextNode(metric.definition+' · '+metric.computation));line.append(d);g.append(line);}
}
function savedAreaGoals(){if(!run)return null;if(configured())return run.metadata.coverage_metrics.length?run.research_configuration.goals:null;return run.config?.targets??null;}
function resourceSummary(c){const mode=c?.resource_mode??c?.parameters?.resource_mode??c?.inventory?.mode;return mode==='all'?'보유 수량 전부 사용':mode==='partial'?'보유 수량 내 일부 사용':mode==='off'?'재고 제한 없음':'자원 조건은 확정 설정 참조';}
function goalSummary(goals,meta){if(goals===null||goals===undefined)return '정량 목표 미설정';if(Array.isArray(goals))return goals.map((v,i)=>(meta?.coverage_metrics?.[i]?.name||'영역 '+(i+1))+' '+v+'%').join(' · ');return Object.entries(goals).map(([k,v])=>(meta?.coverage_metrics?.find(m=>m.id===k)?.name||k)+' '+v+'%').join(' · ')||'정량 목표 미설정';}
function resultFilterOptions(){const targets=savedAreaGoals()!==null;return configured()?[['all','전체 누적 비지배 해 · 같은 목적값의 다른 배치 포함'],...(targets?[['targets','저장된 영역 목표 통과']]:[])]:[['all','전체 Pareto 근사해'],['structures','동일 목적값의 다른 배치 포함'],...(targets?[['targets','목표통과 배치']]:[])];}
function normalizeResultFilters(){if(filter==='targets'&&savedAreaGoals()===null)filter='all';if(run&&cluster!=='all'&&!M.cluster(resultRows())[+cluster])cluster='all';}

function constraintName(id){return ({radar_shortfall:'Radar 탐지 부족',joint_shortfall:'공동식별 부족',radar_inventory:'Radar 재고',eoir_inventory:'EO/IR 재고',rf_inventory:'RF 재고',total_excess:'총 설치 수 초과'})[id]||id;}
function openInfeasibleCandidates(){const evidence=run?.evaluation_summary;if(!evidence)return;const source=run,dialog=document.createElement('dialog');dialog.id='infeasibleDialog';const h=document.createElement('h2');h.textContent='제약 미달 후보 · 비지배 해집합에 포함되지 않음';const close=document.createElement('button');close.textContent='닫기';close.onclick=()=>{dialog.close();dialog.remove();};dialog.append(h,close);noteText(dialog,'저장 원시 평가에서 처음 관측한 서로 다른 제약 미달 후보 최대 12개입니다. 목표 필터로 숨긴 해와 다릅니다.');const order=source.registry.constraint_order;const constraints=document.createElement('div');evidenceTable(constraints,['제약','위반 평가 수','G 최솟값','G 최댓값'],order.map((id,j)=>[constraintName(id),evidence.constraint_violations[j],evidence.G_min[j],evidence.G_max[j]]));dialog.append(constraints);const select=document.createElement('select');select.id='infeasibleCandidate';option(select,evidence.infeasible_examples.map(r=>[String(r.id),'원시 행 '+r.id+' · '+r.sensor_counts.join(' / ')+'대']),evidence.infeasible_examples[0]?.id);const detail=document.createElement('div');const show=()=>{if(run!==source)return;const row=evidence.infeasible_examples.find(r=>String(r.id)===select.value);detail.replaceChildren();if(!row)return;const map=document.createElement('div');map.className='infeasibleMap';map.id='infeasibleMap';map.innerHTML=mapHTML({...source.problem,_metadata:source.metadata},row);detail.append(map);evidenceTable(detail,['제약','원시 G','판정'],order.map((id,j)=>[constraintName(id),row.G[j],row.G[j]>evidence.tolerance?'위반':'통과']));evidenceTable(detail,['목적 순서','원시 F'],row.F.map((v,j)=>[source.registry.objective_order[j],v]));syncSensorSymbols();};select.onchange=show;dialog.append(select,detail);document.body.append(dialog);dialog.showModal();show();}

function renderResultScope(parent,rows){const box=document.createElement('div');box.id='resultScope';box.className='resultScope';box.setAttribute('role','status');const title=document.createElement('b');title.textContent='저장 결과 · '+run.run_id.slice(0,8)+' · '+run.generation+'세대까지';box.append(title);noteText(box,goalSummary(savedAreaGoals(),run.metadata)+' · '+resourceSummary(run.config));noteText(box,'표시 '+rows.length+'개 / 누적 비지배 배치 '+archiveRowCount()+'개 · 평가 '+run.nfe.toLocaleString()+'회');if(configured()&&!run.metadata.coverage_metrics.length)noteText(box,'영역 목표 필터를 제공하지 않는 모델입니다. 모델 품질 목표는 설치 제약 G와 함께 평가됩니다.');if(!archiveRowCount())noteText(box,'현재까지 실현가능한 비지배 배치가 없습니다. 계산 상태와 설치 제약을 확인하세요.');else if(!rows.length)noteText(box,'계산 결과는 저장되어 있습니다. 현재 목표·군집 필터가 모든 배치를 숨겼습니다.');else noteText(box,'비지배 배치는 새 해가 기존 해를 지배하면 줄어들 수 있습니다. 평가 횟수와 다릅니다.');if(filter!=='all'||cluster!=='all'){const b=document.createElement('button');b.id='showAllResults';b.textContent='필터 해제 · 전체 '+archiveRowCount()+'개 보기';b.onclick=()=>{filter='all';cluster='all';dock='solutions';renderDock();renderMaps();renderInspector();expandControlsRefresh();};box.append(b);}const e=run.evaluation_summary;if(e){noteText(box,'원시 평가 '+e.evaluated+'회 · 제약 통과 '+e.feasible+'회 · 제약 미달 '+e.infeasible+'회');if(e.infeasible_examples.length){const inspect=document.createElement('button');inspect.id='inspectInfeasible';inspect.textContent='제약 미달 후보·이유 보기';inspect.onclick=openInfeasibleCandidates;box.append(inspect);}}parent.append(box);}
function resultSortOptions(){return configured()?[['cost','비용 낮은 순'],...resultMetrics().filter(m=>m.id!=='cost').map(m=>[m.id,m.name+' '+(m.direction==='maximize'?'높은 순':'낮은 순')])]:[['cost','비용 낮은 순'],['radar',run.qualityLabels[0]],['second',run.qualityLabels[1]]];}

function requestConfiguration(){
 const b=registered(),s=selection();let config;
 if(draft.sensor===EO)config=M.eoirConfig(draft);
 else if(draft.sensor===RF){const p=M.rfPayload(draft);config={common:p.common,parameters:p.parameters};}
 else config={...structuredClone(draft.sensors[draft.sensor]),...structuredClone(draft.common)};
 const optimizer=s.solver_policy==='legacy_eoir_v1'?{}:{algorithm:draft.optimizer.algorithm,seed:draft.optimizer.seed,population:draft.optimizer.population,generations:draft.optimizer.generations,...(s.solver_policy==='generic_v1'?{ref_partitions:s.ref_partitions,...(registryData.calculator_capabilities?.generic_initializers?{initializer:s.initializer||'random',...(registryData.calculator_capabilities.initialization_owner==='CALCULATOR'?{initialization_evaluations:s.initialization_evaluations??128,initialization_seconds:s.initialization_seconds??30,...(registryData.calculator_capabilities.initialization_versions?{initialization_version:s.initialization_version??registryData.calculator_capabilities.initialization_version}:{})}:{})}:{})}:{})};
 return {experiment_contract_id:draft.sensor,model_config:config,enabled_sensor_ids:[...s.enabled_sensor_ids],objective_ids:[...s.objective_ids],diagnostic_ids:[...s.diagnostic_ids],solver_policy:s.solver_policy,optimizer,goals:b.coverage_metrics.length&&draft.research.goalsEnabled?Object.fromEntries(b.coverage_metrics.map(m=>[m.id,draft.research[m.id]])):null};
}
renderHeader=function(){historical.header();if(!registryData)return;$('contextTitle').textContent=M.label(draft.sensor);let picker=$('modelBundle');if(!picker){picker=document.createElement('select');picker.id='modelBundle';picker.setAttribute('aria-label','연구 모델');document.querySelector('.sensorChooser').append(picker);picker.onchange=safe(()=>switchSensor(picker.value));}option(picker,registryData.bundles.map(b=>[b.id,b.name]),draft.sensor);const meta=configured()&&mode==='result'?run.metadata:registered();option($('mapLayer'),[['all','모든 센서'],...(meta?.sensors||[]).map(s=>[s.id,s.name]),['none','설치 위치만']],$('mapLayer').value||'all');};
function savedInitializationSource(s){
 const origin=s.saved_seed_origin||{},copied=s.source_run_id||copyParent;
 const id=s.saved_seed_selected_run_id||copied||origin.run_id||run?.run_id;
 return {run_id:id,sort:origin.run_id===id?(origin.sort||'cost'):'cost',targets:origin.run_id===id?origin.targets===true:false};
}
async function setInitializationMethod(s,v){
  const cid=draft.sensor,epoch=(s.saved_seed_epoch||0)+1;s.saved_seed_epoch=epoch;
  s.initializer=v;s.saved_seed_loading=v==='saved';s.saved_seed_error='';
  if(v==='saved'){delete s.saved_seed;s.saved_seed_info=null;}
  updateDraft();
  if(v!=='saved')return;
  const current=()=>selection()===s&&draft.sensor===cid&&s.initializer==='saved'&&s.saved_seed_epoch===epoch;
  const source=savedInitializationSource(s);
  if(!source.run_id){s.saved_seed_loading=false;s.saved_seed_error='먼저 저장 결과 조건을 초안으로 복사하세요.';renderSettings();throw Error(s.saved_seed_error);}
  s.saved_seed_loading=true;s.saved_seed_error='';delete s.saved_seed;renderSettings();
  try{
   const loaded=await api(cid,'engine/runs/'+source.run_id+'/initial-seed?sort='+encodeURIComponent(source.sort)+'&targets='+source.targets);
   if(!current())return;
   if(loaded.reference?.run_id!==source.run_id)throw Error('요청한 저장 실행과 초기 배치 응답이 다릅니다.');
   s.saved_seed_origin={...source};s.saved_seed=loaded.reference;s.saved_seed_info=loaded;
  }catch(e){if(current()){s.saved_seed_error='초기 배치 원본 '+source.run_id.slice(0,8)+'을 불러오지 못했습니다. '+e.message;throw Error(s.saved_seed_error);}}
  finally{if(current()){s.saved_seed_loading=false;updateDraft();renderSettings();}}
}
function renderExecutionResources(parent){
 const resources=preview?.resource_plan;
 if(!resources||previewPending||previewFailure)return;
 const p=document.createElement('p');p.id='executionResources';p.className='formNote';p.textContent=`탐색 ${resources.search_evaluations.toLocaleString()}회 + 종료 재평가 ${resources.full_replay_evaluations.toLocaleString()}회 · 전체 ${resources.checkpoint_count.toLocaleString()}세대 기록 · 초기화 최대 ${resources.initialization_evaluation_limit}회 별도. 조건 확인 시 사용 가능 RAM ${(resources.available_memory_bytes/1e9).toFixed(1)}GB · 디스크 ${(resources.disk_free_bytes/1e9).toFixed(1)}GB. ${resources.note}`;parent.append(p);
}
let configurationValidation=null;
function validateDraftRequest(cid,request){
 const key=cid+JSON.stringify(request);
 if(configurationValidation?.key===key)return configurationValidation.promise;
 configurationValidation?.controller.abort();
 const controller=new AbortController(),started=Date.now();
 let timedOut=false;
 const timer=setTimeout(()=>{timedOut=true;controller.abort();},60000);
 const progress=setInterval(()=>{if(configurationValidation?.key===key&&draft.sensor===cid){$('saveState').textContent=`새 조건 확인 중 · ${Math.floor((Date.now()-started)/1000)}초 · 계산 시작 대기`;$('calculate').disabled=true;}},1000);
 const pending={key,controller,promise:null};
 pending.promise=api(cid,'engine/validate',request,{}, {signal:controller.signal}).catch(error=>{
  if(timedOut)throw Error('조건 확인 응답을 60초 안에 받지 못했습니다. 입력은 보존했습니다. 조건 확인 버튼으로 다시 시도하세요. 최적화 계산을 시작한 상태는 아닙니다.');
  throw error;
 }).finally(()=>{clearTimeout(timer);clearInterval(progress);if(configurationValidation===pending)configurationValidation=null;});
 configurationValidation=pending;return pending.promise;
}
async function savedInitializationReady(){
 const s=selection();
 if(s.initializer!=='saved')return true;
 if(s.saved_seed_loading){notice('저장된 성능 1순위 배치를 불러오는 중입니다. 완료되면 변경한 조건을 자동으로 확인합니다.','busy');return false;}
 if(s.saved_seed_error){notice(s.saved_seed_error,'error');return false;}
 if(!s.saved_seed){await setInitializationMethod(s,'saved');return false;}
 return true;
}
function renderCommonInitialization(g,s){
 const caps=registryData.calculator_capabilities,methods=caps?.generic_initializers;
 if(!methods)return noteText(g,'현재 서버의 초기화 기능을 확인한 뒤 계산기를 다시 연결하세요.');
 const common=caps.initialization_owner==='CALCULATOR';
 const labels={random:'무작위',greedy:'Greedy',milp:common?'MILP · 국소 선형 근사':'MILP·ε-constraint',saved:'저장 결과의 성능 1순위 배치'};
 selectControl(g,'초기 배치 방법',methods.map(m=>[m,labels[m]||m]),s.initializer||'random',safe(v=>setInitializationMethod(s,v)),'genericInitializer');
 if(common&&Array.isArray(caps.initialization_versions)){
  const versions={'calculator-common-initialization-v1':'기존 규칙 · 영역 목표까지 통과한 후보','calculator-common-initialization-v2':'새 규칙 · 모델 제약을 통과한 후보'};
  selectControl(g,'Greedy·MILP 초기 후보 수용',caps.initialization_versions.map(v=>[v,versions[v]||v]),s.initialization_version??caps.initialization_version,safe(async v=>{s.initialization_version=v;await apply();}),'initializationVersion');
  noteText(g,'새 규칙은 예산·수량 등 모델 제약을 만족한 후보를 영역 목표에 미달해도 탐색 시작점으로 사용합니다. 목표 달성을 보장하지 않습니다. 무작위·저장 배치 방법의 선택 방식은 바꾸지 않습니다. 과거 조건 복사는 기존 규칙을 유지하며 여기서 명시적으로 바꿀 수 있습니다.');
 }
 const savedOption=[...$('genericInitializer').options].find(o=>o.value==='saved');
 if(savedOption&&!s.source_run_id&&!copyParent&&!s.saved_seed_origin&&!run){savedOption.disabled=true;savedOption.textContent+=' · 저장 실행 선택 후 사용';}
 if(s.initializer==='saved'){
  const source=savedInitializationSource(s),sources=[...$('runHistory').options].filter(o=>o.value).map(o=>[o.value,o.textContent]);
  if(source.run_id&&!sources.some(([id])=>id===source.run_id))sources.unshift([source.run_id,'초기 배치 원본 · '+source.run_id.slice(0,8)]);
  selectControl(g,'초기 배치를 가져올 저장 실행',sources,source.run_id||'',safe(async id=>{s.saved_seed_selected_run_id=id;s.saved_seed_origin={run_id:id,sort:'cost',targets:false};await setInitializationMethod(s,'saved');}),'savedSeedSource');
  selectControl(g,'초기 배치 선택 범위',[['all','전체 저장 비지배 배치'],['targets','저장 목표 통과 배치만']],source.targets?'targets':'all',safe(async value=>{s.saved_seed_selected_run_id=source.run_id;s.saved_seed_origin={...source,targets:value==='targets'};await setInitializationMethod(s,'saved');}),'savedSeedScope');
  noteText(g,'조건을 복사한 실행과 초기 배치 원본을 따로 선택할 수 있습니다. 원본 변경은 편집한 예산·세대수·참조방향을 바꾸지 않습니다.');
  const p=s.saved_seed_info,ref=s.saved_seed;
  const retry=document.createElement('button');retry.textContent='선택한 저장 실행에서 초기 배치 다시 불러오기';retry.disabled=!!s.saved_seed_loading;retry.onclick=safe(()=>setInitializationMethod(s,'saved'));g.append(retry);
  if(s.saved_seed_error&&source.targets){const all=document.createElement('button');all.textContent='같은 실행의 전체 비지배 배치에서 선택';all.onclick=safe(async()=>{s.saved_seed_selected_run_id=source.run_id;s.saved_seed_origin={...source,targets:false};await setInitializationMethod(s,'saved');});g.append(all);}
  noteText(g,s.saved_seed_loading?'저장된 누적 비지배 해집합의 성능 1순위 배치를 확인 중입니다.':s.saved_seed_error||ref? s.saved_seed_error||`저장 실행 ${ref.run_id.slice(0,8)} · 행 ${ref.row_id} · 성능 1순위${ref.targets?' · 저장 목표 통과 배치 중':''}`:'저장 초기 배치를 다시 선택하세요.');
  if(p)noteText(g,'우선순위: '+p.performance_order.map(id=>registered().metrics.find(m=>m.id===id)?.name||'성능 항목').join(' → ')+` · 저장 비용 ${p.cost} · 센서 ${p.sensor_counts.join('/')}대`);
  noteText(g,'이 배치를 새 조건으로 재평가해 초기 모집단의 첫 개체에 넣고 나머지는 무작위로 채웁니다. 세대수와 참조방향을 바꿀 수 있습니다. 예산을 낮춰 제약을 넘으면 미충족 초기 후보로 탐색하며, 후보지·센서·수량 조건이 맞지 않으면 실행 전에 알려드립니다.');
 }
 const unavailable=caps.unavailable_initializers_by_contract?.[draft.sensor]||{};
 for(const option of $('genericInitializer').options)if(unavailable[option.value]){option.disabled=true;option.textContent+=' · '+unavailable[option.value];}
 if(common){s.initialization_evaluations??=128;s.initialization_seconds??=30;quantity(g,'초기화 준비 평가 상한','initialization_evaluations',s,'회',1,[],1,1,512);quantity(g,'초기화 준비 시간 상한','initialization_seconds',s,'초',1,[],1,1,120);
 if(s.initializer==='saved'){noteText(g,'저장 배치 재평가는 준비 평가 1회로 기록하며, 첫 세대에서 다시 평가합니다. 원본을 확인하지 못하면 무작위 배치로 대체하지 않고 오류를 표시합니다.');return;}
 noteText(g,'계산기가 공통으로 생성합니다. Greedy는 실제 목적·제약 평가로 이웃 배치를 선택합니다. MILP는 국소 선형 근사로 정수 후보를 제안하고 원래 모델로 확인합니다.');
 noteText(g,'준비 평가는 탐색 NFE와 별도입니다. 무작위 모집단은 같은 seed로 만들며, 검증된 후보가 없으면 원인을 기록하고 이 모집단을 사용합니다. MILP 결과는 원래 모델의 전역 최적해를 보장하지 않습니다.');
 const button=document.createElement('button');button.id='compareInitializers';button.textContent='무작위 · Greedy · MILP 비교';button.onclick=safe(()=>openValidation(true));g.append(button);
 }else noteText(g,'실행 중인 서버는 이전 초기화 정책입니다. 새 공통 기능 반영 후 다시 연결하세요.');
}
renderSettings=function(){
 if(!registryData||!draft.research)return historical.settings();
 const b=registered(),s=selection(),toy=b.id==='TOY_DIMENSION_V1';
 if(!toy)historical.settings();else{$('settingsBody').replaceChildren();document.querySelectorAll('[data-settings]').forEach(v=>v.setAttribute('aria-selected',v.dataset.settings===setting));const g=group(b.name);noteText(g,'손계산 가능한 구조 시험입니다. Radar/RF/EOIR 결합 성능을 나타내지 않습니다.');if(setting==='common')quantity(g,'합성 후보 수','n_candidates',draft.sensors[b.id],'곳',1,[],1,1,12);if(setting==='optimizer'){quantity(g,'진화 세대 수','generations',draft.optimizer,'세대',1,[],1,1,null);quantity(g,'개체 수','population',draft.optimizer,'개',1,[],1,4,256);quantity(g,'seed','seed',draft.optimizer,'정수',1,[],1,0,2147483647);}}
 if(setting==='sensors'){
  const g=group('이번 계산에 사용할 센서');$('settingsBody').prepend(g);for(const sensor of b.sensors){const l=document.createElement('label'),c=document.createElement('input');l.className='field inline';c.type='checkbox';c.id='enabled_'+sensor.id;c.checked=s.enabled_sensor_ids.includes(sensor.id);c.onchange=()=>{s.enabled_sensor_ids=b.sensors.filter(x=>x.id===sensor.id?c.checked:s.enabled_sensor_ids.includes(x.id)).map(x=>x.id);updateDraft();};l.append(c,document.createTextNode(sensor.name));g.append(l);}noteText(g,'비활성 센서는 다음 계산에서 설치 수 0입니다. 지도 레이어 숨김과는 별개입니다. 전부 사용 재고와 모순되면 입력 오류를 표시합니다.');
 }
 if(setting==='objectives'){
  for(const g of [...$('settingsBody').querySelectorAll('fieldset')])if(g.querySelector('#enableTargets'))g.remove(); for(const note of $('settingsBody').querySelectorAll('.formNote'))if(note.textContent.startsWith('탐지95%'))note.remove();
  const g=group('지표 사용 방식과 목적 순서');
  renderMetricControls(g,b,s);
  if(b.coverage_metrics.length){const target=group('정량 목표 · 등록 모델의 영역 비율');$('settingsBody').prepend(target);field(target,'영역 목표 사용','goalsEnabled',null,'',draft.research);for(const m of b.coverage_metrics){const input=quantity(target,m.name,m.id,draft.research,'%',1,[],1,0,100);input.disabled=!draft.research.goalsEnabled;noteText(target,m.definition);}noteText(target,draft.research.goalsEnabled?'다음 계산의 목표통과 분류를 사용합니다. 전체 누적 해는 목표와 별도로 보존됩니다.':'목표로 거르지 않습니다. 설치 제약을 만족하는 계산 배치와 누적 비지배 해를 결과 범위에서 선택합니다.');noteText(target,'영역 비율의 관측 조건은 각 지표의 모델 정의를 따릅니다. 평균 정보품질 목적값과 영역 목표는 서로 다른 지표입니다.');}
 }
 if(['optimizer','objectives','sensors'].includes(setting)){const g=group('계산 정책과 구성 확인');selectControl(g,'계산 정책',b.policies.map(p=>[p,p==='generic_v1'?'일반 구성':'기존 계산 재현']),s.solver_policy,v=>{s.solver_policy=v;updateDraft();renderSettings();},'solverPolicy');if(s.solver_policy==='generic_v1'){
  // A still-running older calculator may serve these updated static assets.
  // Only advertise and submit options the loaded backend actually implements.
  const methods=registryData.calculator_capabilities?.generic_initializers;
  if(methods)renderCommonInitialization(g,s);
  else noteText(g,'현재 실행 중인 계산기는 무작위 초기화만 지원합니다. 계산 완료 후 계산기를 다시 시작하면 추가 초기화 방법을 사용할 수 있습니다.');
  renderReferenceDirections(g,s);noteText(g,'일반 구성은 기존 EOIR ε-constraint 준비·변이 궤적과 다릅니다. 센서·목적 변경에 사용합니다.');
 }const p=document.createElement('p');p.id='compiledSummary';p.className='formNote';p.textContent=configurationSummary?`설치 변수 ${configurationSummary.n_var} · 목적 ${configurationSummary.n_obj} · 제약 ${configurationSummary.n_constr} · ${configurationSummary.declared_nfe} NFE`:'구성을 확인 중입니다.';g.append(p);
 }
};
apply=async function(){clearTimeout(previewTimer);if(typeof configurationCopyPending!=='undefined'&&configurationCopyPending)return;const epoch=++previewEpoch,cid=draft.sensor;previewPending=true;previewFailure='';$('calculate').disabled=true;if(typeof renderExecutionGuide==='function')renderExecutionGuide();if(!registryData){registryData=await api(cid,'engine/registry');prepareResearch();renderHeader();renderSettings();}else prepareResearch();if(!await savedInitializationReady())return;let p;try{p=await validateDraftRequest(cid,requestConfiguration());}catch(error){if(epoch===previewEpoch&&cid===draft.sensor){previewPending=true;previewFailure=error.message;$('calculate').disabled=true;$('saveState').textContent='조건 확인 실패 · 입력 보존 · 다시 확인';if(typeof renderExecutionGuide==='function')renderExecutionGuide();}throw error;}if(epoch!==previewEpoch||cid!==draft.sensor||configurationCopyPending)return;configurationSummary=p.summary;preview={...p,problem:{...p.problem,_metadata:p.summary.metadata}};previewPending=false;previewFailure='';$('saveState').textContent='구성 검증 완료 · 다음 계산 준비';$('calculate').disabled=creating||!!run&&!terminal.has(run.state);renderSettings();renderHeader();if(mode==='design')renderMaps();notice(`구성 확인: 목적 ${p.summary.n_obj}개 · ${p.summary.solver_policy==='generic_v1'?'일반 구성':'기존 계산 재현'} · ${p.summary.declared_nfe} NFE. 정량 목표는 별도 영역 비율로 판정합니다.`);};
$('applyDraft').onclick=safe(apply);
$('calculate').onclick=safe(async()=>{if(creating)return;await apply();if(previewPending)return;const cid=draft.sensor;lockCreation(true);try{notice('로딩중… 계산 구성 저장','busy');const job=await api(cid,'engine/runs',requestConfiguration());clearRun();await histories();await loadRun(job.run_id);}finally{lockCreation(false);}});
const previousSwitch=switchSensor;switchSensor=async cid=>{if(registryData)prepareResearch();await previousSwitch(cid);renderHeader();};
const historicalDifference=mapDifference;
const historicalAnalysis=openPlacementAnalysis;
openPlacementAnalysis=function(){if(!configured())return historicalAnalysis();workbench?.setTask('solutions');dock='quality';renderDock();notice(run.metadata.capabilities.advanced_diagnostics_reason);};
mapDifference=function(row,base,p,host=$('mainMap')){if(!configured())return historicalDifference(row,base,p,host);const svg=host.querySelector('svg');if(!svg||!row||!base)return;let same=0,added=0,removed=0;const layer=$('mapLayer').value;for(let i=0;i<row.X.length;i++)for(let j=0;j<run.metadata.sensors.length;j++){const a=row.X[i][j],b=base.X[i][j],sensor=run.metadata.sensors[j];if(a&&b)same++;if(a===b)continue;a?added++:removed++;if(layer!=='all'&&layer!=='none'&&layer!==sensor.id)continue;const anchor=host.querySelector('[data-site="'+(i+1)+'"]')||$('initialMap').querySelector('[data-site="'+(i+1)+'"]');if(!anchor)continue;const mark=document.createElementNS(svg.namespaceURI,'circle');for(const [k,v] of Object.entries({cx:anchor.getAttribute('cx'),cy:anchor.getAttribute('cy'),r:14,fill:'none',stroke:a?'#128047':'#b12c62','stroke-width':3,'data-difference':a?'added':'removed','data-sensor-id':sensor.id}))mark.setAttribute(k,v);if(!a)mark.setAttribute('stroke-dasharray','5 4');const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=sensor.name+' · 후보 '+(i+1)+' · '+(a?'추가':'제거');mark.append(title);(host.querySelector('[data-map-marks]')||svg).append(mark);}$('differenceSummary').textContent=`기준 대비: 공통 ${same}대 · +${added}대 · −${removed}대 · Hamming ${added+removed}`;};
visibleRows=function(){if(!run)return [];normalizeResultFilters();let rows=resultRows();if(filter==='targets')rows=rows.filter(r=>r.qualified===true);if(cluster!=='all'){const ids=new Set((M.cluster(resultRows())[+cluster]||[]).map(r=>r.id));rows=rows.filter(r=>ids.has(r.id));}return [...rows].sort((a,b)=>{if(sort==='cost')return a.cost-b.cost||a.id-b.id;if(!configured())return M.quality(b)[sort==='radar'?0:1]-M.quality(a)[sort==='radar'?0:1]||a.cost-b.cost;const key=sort==='radar'?run.registry.objective_order[0]:sort==='second'?run.registry.objective_order[1]:sort,m=run.metadata.metrics.find(m=>m.id===key);return ((a.named_metrics[key]??0)-(b.named_metrics[key]??0))*(m?.direction==='maximize'?-1:1)||a.cost-b.cost;});};
syncSelectionBar=function(){const rows=visibleRows(),names=configured()?run.metadata.sensors.map(s=>s.name):['Radar',draft.sensor===EO?'EO/IR':'RF'];option($('solutionPicker'),rows.length?rows.map(r=>[String(r.id),`행 ${r.id} · 비용 ${r.cost} · ${r.sensor_counts.map((v,i)=>names[i]+' '+v).join(' / ')}`]):[['','표시할 해 없음']],selected??'');$('solutionBar').hidden=!run||mode!=='result';$('selectionPosition').textContent=rows.length?`${rows.findIndex(r=>r.id===selected)+1} / ${rows.length}개`:'0개';$('pinSolution').disabled=selected===null;};
function resultMetrics(){const ids=[...run.research_configuration.objective_ids,...run.research_configuration.diagnostic_ids,'cost'];return [...new Set(ids)].map(id=>run.metadata.metrics.find(m=>m.id===id)).filter(Boolean);}
renderDock=function(){if(!configured())return historical.dock();$('advanced').disabled=true;$('advanced').title=run.metadata.capabilities.advanced_diagnostics_reason;const body=$('dockBody');body.replaceChildren();document.querySelectorAll('[data-dock]').forEach(b=>b.setAttribute('aria-selected',b.dataset.dock===dock));let rows=visibleRows();if(!rows.some(r=>r.id===selected))selected=representative(rows)?.id??null;syncSelectionBar();$('resultCount').textContent=`누적 ${archiveRowCount()} · 목표통과 ${run.target_count??'미설정'} · Hamming ${M.cluster(resultRows()).length}군`;const controls=document.createElement('div');controls.className='dockToolbar';selectControl(controls,'집합',resultFilterOptions(),filter,v=>{filter=v;renderDock();renderMaps();renderInspector();},'frontFilter');selectControl(controls,'Hamming',[['all','전체'],...M.cluster(resultRows()).map((g,i)=>[String(i),`${i+1}군 · ${g.length}개`])],cluster,v=>{cluster=v;renderDock();renderMaps();renderInspector();},'structureFilter');selectControl(controls,'정렬',resultSortOptions(),sort,v=>{sort=v;renderDock();},'rowSort');body.append(controls);renderResultScope(body,rows);if(dock==='quality'){noteText(body,run.metadata.capabilities.advanced_diagnostics_reason);noteText(body,'원시 X/F/G 재생: '+(run.audit?.raw_replay||'검증 대기'));const ex=document.createElement('button');ex.textContent='원시 결과 내보내기';ex.onclick=safe(exportRaw);body.append(ex);return;}if(dock==='comparison')rows=rows.filter(r=>compared.has(r.id));const metrics=resultMetrics(),objectives=run.registry.objective_order.map(id=>metrics.find(m=>m.id===id));if(axesRun!==run.run_id){axes=objectives.slice(0,3).map(m=>m.id);axesRun=run.run_id;}else axes=axes.map((id,i)=>i===2&&id===''?'':objectives.some(m=>m.id===id)?id:objectives[i]?.id||'');for(let i=0;i<Math.min(3,objectives.length);i++)selectControl(controls,['X축','Y축','Z축'][i],i===2?[['','2D 표시'],...objectives.map(m=>[m.id,m.name])]:objectives.map(m=>[m.id,m.name]),axes[i],v=>{axes[i]=v;renderDock();},'objectiveAxis'+i);noteText(body,'투영에서 생략된 목적: '+(objectives.filter(m=>!axes.includes(m.id)).map(m=>m.name+' '+(m.direction==='maximize'?'최대화':'최소화')).join(', ')||'없음')+' · 전체 목적값은 아래 표에서 확인합니다.');const plot=document.createElement('div');plot.className='plot';const bounds=axes.map(id=>{const a=rows.map(r=>r.named_metrics[id]);return [Math.min(...a,0),Math.max(...a,1)];});const pos=r=>{const v=axes.map((id,i)=>id?(r.named_metrics[id]-bounds[i][0])/(bounds[i][1]-bounds[i][0]||1):0);return [40+v[0]*270+(axes[2]?v[2]*35:0),180-v[1]*135-(axes[2]?v[2]*25:0)];};plot.innerHTML='<svg viewBox="0 0 400 220" role="img" aria-label="선택 목적의 투영"><path d="M40 25V180H360" fill="none" stroke="#718096"/>'+rows.map(r=>{const [x,y]=pos(r);return `<circle data-row="${r.id}" tabindex="0" role="button" aria-label="그래프 배치 ${r.id} 선택" cx="${x}" cy="${y}" r="${r.id===selected?7:4}" fill="${r.id===selected?'#a5671d':'#23859a'}"><title>행 ${r.id}</title></circle>`;}).join('')+'</svg>';plot.querySelectorAll('[data-row]').forEach(e=>{e.onclick=()=>choose(+e.dataset.row);e.onkeydown=v=>{if(v.key==='Enter')choose(+e.dataset.row);};});const grid=document.createElement('div');grid.className='solutionsGrid';grid.append(plot);body.append(grid);const wrap=document.createElement('div');wrap.className='tableWrap';const table=document.createElement('table'),head=table.createTHead().insertRow();for(const name of ['배치',...metrics.map(m=>m.name+' ('+m.unit+')'),...run.metadata.coverage_metrics.map(m=>m.name+' (%)'),'센서별 설치','목표','비교']){const th=document.createElement('th');th.textContent=name;head.append(th);}for(const r of rows){const tr=table.createTBody().insertRow();tr.dataset.row=r.id;const b=document.createElement('button');b.textContent='행 '+r.id;b.setAttribute('aria-label','배치 '+r.id+' 선택');b.onclick=()=>choose(r.id);tr.insertCell().append(b);for(const v of [...metrics.map(m=>valueText(m,r.named_metrics[m.id])),...run.metadata.coverage_metrics.map(m=>valueText(m,r.coverage_metrics[m.id])),r.sensor_counts.map((v,i)=>run.metadata.sensors[i].name+' '+v).join(' / '),r.qualified===null?'미설정':r.qualified?'통과':'미달'])tr.insertCell().textContent=v;const check=document.createElement('input');check.type='checkbox';check.checked=compared.has(r.id);check.setAttribute('aria-label','배치 '+r.id+' 비교');check.onchange=()=>check.checked?compared.add(r.id):compared.delete(r.id);tr.insertCell().append(check);}wrap.append(table);grid.append(wrap);if(!rows.length&&dock==='comparison')noteText(body,'해 탐색에서 비교할 배치를 선택하세요.');};
renderInspector=function(){if(!configured()||mode!=='result')return historical.inspector();const p=$('inspectorBody'),r=currentRow();p.replaceChildren();$('selectionKind').textContent=r?'저장 원시 행 '+r.id:'해 미선택';if(r){evidenceTable(p,['지표','값'],[...resultMetrics().map(m=>[m.name,valueText(m,r.named_metrics[m.id])]),...run.metadata.coverage_metrics.map(m=>[m.name,valueText(m,r.coverage_metrics[m.id])]),...run.metadata.sensors.map((s,i)=>[s.name,r.sensor_counts[i]+'대'])]);}noteText(p,'고정 설정 '+run.config_sha256.slice(0,12)+' · '+run.solver.policy+' · '+run.registry.objective_order.join(' → '));noteText(p,run.goal_explanation);};
mapHTML=function(p,row){const meta=p?._metadata||(configured()?run.metadata:null);if(!meta)return historical.map(p,row);if(!p)return historical.map(p,row);renderSensorLegend(meta);const unit=(p.map_metres||20000)/800,colors=['#287dad','#c18421','#388e62','#885ba8'];let svg=meta.id==='TOY_DIMENSION_V1'?'<svg viewBox="0 0 930 945"><rect x="60" y="50" width="800" height="800" fill="#f2f6f8"/><text x="60" y="35">합성 후보 배치 · 물리적 커버리지 아님</text></svg>':LiveCore.map(p,null,{layer:'all',candidates:false,defense:$('showArea').checked,demand:$('showDemand').checked&&!row,candidateLabels:false});const layer=$('mapLayer').value;let marks='';for(let i=0;i<p.sites.length;i++){const x=60+p.sites[i][0]/unit,y=850-p.sites[i][1]/unit;if(layer==='none'&&!row?.X?.[i]?.some(Boolean))continue;marks+=`<circle data-site="${i+1}" cx="${x}" cy="${y}" r="3" fill="#798894"><title>후보지 ${i+1}</title></circle>`;if($('showLabels').checked)marks+=`<text x="${x+5}" y="${y-5}" font-size="10">${i+1}</text>`;meta.sensors.forEach((s,j)=>{if(row?.X?.[i]?.[j]&&(layer==='all'||layer==='none'||layer===s.id)){if(layer!=='none')marks+=sensorRange(s.id,x,y,(p.radii[j]||0)/unit);marks+=sensorMarker(s.id,x,y,j,meta.sensors.length,i+1,row.id);}});}if(row&&$('showDemand').checked&&meta.id!=='TOY_DIMENSION_V1'){const spatial=meta.id==='RADAR_RF_SCANNER'?ModelDisplay.call('saved_spatial',meta.id,run.run_id,row.id):null,cv=spatial?null:ModelDisplay.call('coverage',p,row.mask),zone=cv?ModelDisplay.call('zones',p,p.objective_contract):null;for(let i=0;i<p.demand.length;i++){const xy=p.demand[i],status=spatial?.rf_status?.[i],ok=cv?(zone.identification.includes(i)?cv.e[i]:zone.detection.includes(i)&&cv.d[i]):null,color=spatial?observationColor(status):ok?'#188354':cv.d[i]?'#1685ba':'#c84f42';marks+=`<circle data-model-observation="${status||String(ok)}" data-model-position="${spatial?.rf_position_status?.[i]||''}" cx="${60+xy[0]/unit}" cy="${850-xy[1]/unit}" r="3" fill="${color}"><title>${status||'모델 커버 판정 '+ok}${spatial?.rf_position_status?.[i]?' · 위치: '+spatial.rf_position_status[i]:''}</title></circle>`;}}return svg.replace(/<\/svg>$/,clipMapMarks(marks)+'</svg>');};
renderMapReadings=function(){if(configured()){for(const card of document.querySelectorAll('.mapReading')){card.hidden=false;const r=card.closest('.mapCard')?.querySelector('#initialMap')?(referenceRow||initialRows.find(v=>String(v.id)===String(initial))):currentRow();card.textContent=r?run.metadata.coverage_metrics.map(m=>m.name+' '+valueText(m,r.coverage_metrics?.[m.id])).join(' · ')||'합성 구조 시험 · 물리 성능 아님':'해 미선택';}return;}return historical.readings();};
renderConditionComparison=function(){if(draft?.sensor==='TOY_DIMENSION_V1')return;return historical.comparison();};
const oldExport=exportRaw;let pendingRawExport=null;
exportRaw=async function(){
 if(pendingRawExport){notice('원시 결과를 내보내는 중입니다. 응답을 받은 뒤 다시 시도하세요.','busy');return;}
 if(!configured())return oldExport();
 const cid=run.experiment_contract_id,id=run.run_id;
 const name=(run.export_name||readableRunName(run).replace(/[\\/:*?"<>|]/g,'-'))+'.json';
 const controller=new AbortController();let timedOut=false,url=null;
 const timer=setTimeout(()=>{timedOut=true;controller.abort();},180000);
 pendingRawExport={cid,id,controller};$('exportRaw').disabled=true;
 notice('원시 파일·전체 checkpoint를 검사하고 내보내는 중…','busy');
 try{
  const response=await fetch(`/contracts/${cid}/api/engine/runs/${id}/export`,{headers:{'X-Experiment-Contract':cid},signal:controller.signal});
  if(response.headers.get('X-Experiment-Contract')!==cid)throw Error('내보내기 응답 계약 불일치');
  if(!response.ok){let reason='';try{reason=(await response.json()).error||'';}catch{}throw Error(reason||'내보내기 응답 오류 ('+response.status+')');}
  if(response.headers.get('Content-Type')?.split(';')[0].trim()!=='application/json')throw Error('내보내기 응답 형식 불일치');
  const blob=await response.blob(),a=document.createElement('a');url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();
  if(run?.run_id===id&&run?.experiment_contract_id===cid)notice('원시 JSON 응답 수신 · 브라우저 파일 저장 상태는 다운로드 목록에서 확인하세요.');
 }catch(error){
  if(timedOut)throw Error('내보내기 응답을 180초 안에 받지 못했습니다. 저장된 원시는 보존했습니다. 다시 내보내기를 시도하세요.');
  throw error;
 }finally{
  clearTimeout(timer);pendingRawExport=null;
  $('exportRaw').disabled=!run||!terminal.has(run.state);
  if(url)setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
};$('exportRaw').onclick=safe(exportRaw);
$('copyRun').onclick=safeCopy(async()=>{if(!configured())return historical.copy();const research=structuredClone(run.research_configuration);draft.research.selections[draft.sensor]={enabled_sensor_ids:research.enabled_sensor_ids,objective_ids:research.objective_ids,diagnostic_ids:research.diagnostic_ids,solver_policy:research.solver_policy,ref_partitions:run.optimizer.ref_partitions||1,referenceMode:'fixed'};draft.research.goalsEnabled=research.goals!==null;if(research.goals)Object.assign(draft.research,research.goals);if(draft.sensor===EO){draft.sensors[EO]=structuredClone(run.config);for(const k of M.commonKeys)draft.common[k]=run.config[k];}else if(draft.sensor===RF){draft.sensors[RF]=structuredClone(run.config);draft.common=structuredClone(run.config.common);}else {draft.sensors[draft.sensor]=structuredClone(run.config);for(const k of M.commonKeys)if(k in run.config)draft.common[k]=run.config[k];}Object.assign(draft.optimizer,{seed:run.optimizer.seed,population:run.optimizer.population,generations:run.optimizer.checkpoints-1,algorithm:run.optimizer.algorithm});modeTo('design');workbench?.setTask('settings');await apply();});
