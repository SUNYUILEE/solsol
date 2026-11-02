'use strict';
// Installation-bit comparison only. No inferred movement pairing or sensor physics.
function placementPositionDifference(left,right,sensorNames){
 if(!Array.isArray(left)||!Array.isArray(right)||left.length!==right.length||!Array.isArray(sensorNames)||!sensorNames.length)throw Error('배치 후보 순서와 센서 구성이 일치해야 합니다.');
 for(const rows of [left,right])for(const row of rows)if(!Array.isArray(row)||row.length!==sensorNames.length||row.some(v=>v!==0&&v!==1))throw Error('저장 설치 비트 형식이 올바르지 않습니다.');
 return sensorNames.map((name,j)=>{
  const shared=[],leftOnly=[],rightOnly=[];
  for(let i=0;i<left.length;i++){if(left[i][j]&&right[i][j])shared.push(i);else if(left[i][j])leftOnly.push(i);else if(right[i][j])rightOnly.push(i);}
  return {name,sensor_index:j,left_count:shared.length+leftOnly.length,right_count:shared.length+rightOnly.length,shared,left_only:leftOnly,right_only:rightOnly,hamming:leftOnly.length+rightOnly.length,
   meaning:'위치 차이입니다. 어느 센서가 어느 위치로 이동했는지 또는 그 변화가 성능 차이의 단독 원인인지는 추정하지 않습니다.'};
 });
}
if(typeof module!=='undefined'&&module.exports)module.exports={placementPositionDifference};

function renderPlacementDifference(parent,left,right,metrics,sensors,leftLabel,rightLabel){
 const box=vDetails(parent,leftLabel+' ↔ '+rightLabel+' · 얻은 성능과 달라진 위치');box.open=true;
 const a=left.performance_F||left.F,b=right.performance_F||right.F,gains=[],losses=[];
 for(let j=0;j<metrics.length;j++){const m=metrics[j];if(b[j]<a[j])gains.push(m.name);else if(b[j]>a[j])losses.push(m.name);}
 noteText(box,rightLabel+'는 '+(gains.length?gains.join('·')+'에서 좋아집니다':'더 좋아진 성능이 없습니다')+'; '+(losses.length?losses.join('·')+'에서는 낮아집니다':'낮아진 성능은 없습니다')+'.');
 if(gains.length&&!losses.length)noteText(box,'이 두 행은 성능 간 절충이 아니라 관측된 성능 개선 관계입니다. 비용 차이는 별도로 비교하세요.');
 const n=x=>Number(x).toPrecision(6);
 evidenceTable(box,['성능',leftLabel,rightLabel,'변화 · 원래 단위'],metrics.map(m=>[m.name,n(left.named_metrics[m.id]),n(right.named_metrics[m.id]),n(right.named_metrics[m.id]-left.named_metrics[m.id])+' '+(m.unit||'')]));
 noteText(box,'비용 '+left.cost+' → '+right.cost+' · 차이 '+n(right.cost-left.cost)+'. 센서 위치 변화와 성능 변화가 함께 관측된 것이며 특정 센서 이동만의 인과 효과를 뜻하지 않습니다.');
 const diff=placementPositionDifference(left.X,right.X,sensors);
 evidenceTable(box,['센서',leftLabel+' 수량',rightLabel+' 수량','같은 위치',leftLabel+'에만',rightLabel+'에만'],diff.map(x=>[x.name,x.left_count,x.right_count,x.shared.length,x.left_only.length,x.right_only.length]));
 const ids=vDetails(box,'센서별 다른 후보 위치 번호와 Hamming');noteText(ids,'후보 번호는 1부터 표시합니다. Hamming은 다른 설치 비트 수이며 이동한 센서 수가 아닙니다.');
 evidenceTable(ids,['센서',leftLabel+'에만 있는 후보',rightLabel+'에만 있는 후보','Hamming'],diff.map(x=>[x.name,x.left_only.map(i=>i+1).join(', ')||'없음',x.right_only.map(i=>i+1).join(', ')||'없음',x.hamming]));
 return {box,diff};
}

function renderFilteredPlacementMaps(parent,problem,left,right,sensors,leftLabel,rightLabel,id){
 const box=vDetails(parent,'센서별 위치 차이를 지도에서 보기');box.open=true;
 noteText(box,'평가영역 밖의 센서도 안쪽을 관측할 수 있습니다. 원으로 표시한 명목 범위와 실제 측정 품질은 다릅니다. 위치의 실제 기여는 별도 삭제·이동 검산 근거로 판단합니다.');
 noteText(box,'영역 안·밖은 지도에 그려진 평가영역 경계로 구분합니다. 평가점이 놓인 가장 바깥 위치와 영역 경계는 다를 수 있습니다.');
 const sensor=selectControl(box,'표시 센서',[['all','전체 센서'],...sensors.map((s,i)=>[String(i),s])],'all',draw,id+'Sensor');
 const mode=selectControl(box,'표시할 위치',[['all','전체 설치 위치'],['different','서로 다른 설치 위치만']],'all',draw,id+'Mode');
 const canvas=document.createElement('div');canvas.className='qualityCompareMaps';canvas.id=id;box.append(canvas);
 function draw(){canvas.replaceChildren();for(const [name,row,other] of [[leftLabel,left,right],[rightLabel,right,left]]){const filtered=row.X.map((r,i)=>r.map((v,j)=>v&&(sensor.value==='all'||Number(sensor.value)===j)&&(mode.value==='all'||!other.X[i][j])?1:0));const panel=document.createElement('div');noteText(panel,name+' · 원시 행 '+(row.raw_id??row.id)+' · 원래 전체 비용 '+row.cost);panel.insertAdjacentHTML('beforeend',qualityGeometryMap(problem,{...row,id:row.raw_id??row.id,X:filtered}));canvas.append(panel);}}
 noteText(box,'센서/위치 필터는 표시만 바꿉니다. 원시 배치·비용·성능을 다시 계산하거나 수정하지 않습니다.');draw();return box;
}

function renderPairContribution(parent,cid,cell,scope,bid,act){
 const box=vDetails(parent,'이 두 B 배치의 센서는 실제로 기여하나요?');box.id='guidedContribution';
 noteText(box,'영역 밖이라는 이유로 삭제하지 않습니다. 각 배치의 센서 삭제·추가·위치 이동을 검사하고, 아래에서는 센서 하나 삭제의 실제 성능·비용·목표 변화를 보여줍니다. 원시 두 행만 대상이며 전체 해집합 검증은 아닙니다.');
 const status=document.createElement('p');status.id='guidedContributionStatus';status.setAttribute('role','status');status.textContent='아직 조회하지 않았습니다. 아래 버튼으로 저장 검산을 확인하거나 시작하세요.';box.append(status);
 const body=document.createElement('div');let stopped=false,current=null,working=false,cancelSent=false;const path='engine/runs/'+cell.b_run_id+'/quality-jobs';
 async function cancelCurrent(){if(!cancelSent&&current&&['QUEUED','RUNNING'].includes(current.status)){cancelSent=true;try{await api(cid,path+'/'+current.job_id+'/cancel',{});status.textContent='중지 요청을 보냈습니다. 현재 처리와 저장 완료를 기다려 주세요.';}catch(e){cancelSent=false;status.textContent='중지 접수 확인 실패: '+e.message+' · 상태를 조회하며 중지 요청을 다시 확인합니다.';}}}
 const stop=dButton(box,'guidedContributionStop','검산 중지 요청·저장',async()=>{stopped=true;try{await cancelCurrent();}catch(e){status.textContent='중지 접수 확인 실패: '+e.message;cancelSent=false;}});stop.disabled=true;
 const start=dButton(box,'guidedContributionStart','저장 검산 확인 · 없으면 두 배치 검산 시작',()=>act(async()=>{
  working=true;stopped=false;start.disabled=true;stop.disabled=false;
  try{for(const row of Object.values(cell.b_conflict)){if(stopped||!box.isConnected)break;current=null;cancelSent=false;const listing=await api(cid,path);if(stopped||!box.isConnected)break;const matches=listing.jobs.filter(j=>j.definition_sha256===listing.definition_sha256&&j.method==='local'&&j.source_ids.length===1&&j.source_ids[0]===row.id&&j.status!=='ERROR');current=matches.find(j=>j.status==='COMPLETED'&&j.scope_complete)||matches[0]||await api(cid,path,{scope:'selected',raw_id:row.id,method:'local'});
   if(stopped)await cancelCurrent();if(!box.isConnected)return;
   if(['STOPPED','INTERRUPTED'].includes(current.status)&&!stopped)current=await api(cid,path+'/'+current.job_id+'/resume',{});
   while(['QUEUED','RUNNING'].includes(current.status)&&box.isConnected){if(stopped)await cancelCurrent();status.textContent='원시 행 '+row.id+' · '+current.phase+' · '+current.evaluated+' / '+(current.total??'범위 산정 중')+'회 · 기다려 주세요';await new Promise(r=>setTimeout(r,1500));current=await api(cid,path+'/'+current.job_id);}
   if(!box.isConnected)return;if(stopped||current.status!=='COMPLETED')break;
  }await show();}finally{working=false;start.disabled=false;stop.disabled=true;}
 }));
 dButton(box,'guidedContributionRead','저장된 검산 결과만 조회',()=>act(show));box.append(body);
 async function show(){const v=await api(cid,'engine/guided-cost-budget/placement-checks',{b_id:bid,cell_id:cell.cell_id,scope});if(!box.isConnected)return;body.replaceChildren();noteText(body,v.meaning);const complete=v.results.length===2&&v.results.every(r=>r.status==='COMPLETED'&&r.scope_complete);status.textContent=complete?'두 배치 검산·저장 완료. 아래 삭제별 결과를 비교하세요.':'검산 미완료입니다. 상태를 확인하고 시작·재개 버튼을 누르세요.';
  for(const r of v.results){const detail=vDetails(body,'원시 행 '+r.raw_id+' · '+r.status+' · '+(r.evaluated??0)+' / '+(r.total??'미산정'));detail.open=true;if(r.status!=='COMPLETED'||!r.scope_complete){noteText(detail,'미완료 결과로 센서의 불필요 여부를 판정하지 않습니다.');continue;}
   evidenceTable(detail,['삭제 센서·후보','설치 중심','삭제 후 비용','판정','성능 변화'],r.deletions.map(x=>[x.sensor+' · 후보 '+(x.candidate_index+1),x.outside_evaluation_area===null?'영역 미상':x.outside_evaluation_area?'평가영역 밖':'평가영역 안',x.cost,x.meaning,cell.metrics.map(m=>m.name+' '+Number(x.performance_changes[m.id]).toPrecision(4)).join(' / ')]));
   noteText(detail,'별도 검산 ID '+r.job_id+' · 선택한 성능이 동일해도 실제 모든 용도에서 불필요하다는 뜻은 아닙니다.');
  }
 }
 return box;
}
