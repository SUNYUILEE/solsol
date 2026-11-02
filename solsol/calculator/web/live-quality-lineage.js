'use strict';
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.LiveQualityLineage=api;
})(typeof window!=='undefined'?window:globalThis,function(){
 const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 function need(value,message){if(!value)throw new Error(message);}
 function sha256(bytes){
  const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const data=Array.from(bytes),bitLength=data.length*8;
  data.push(0x80);while(data.length%64!==56)data.push(0);
  for(let shift=56;shift>=0;shift-=8)data.push(shift>=32?0:(bitLength>>>shift)&255);
  let h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const rotr=(value,count)=>(value>>>count)|(value<<(32-count));
  for(let offset=0;offset<data.length;offset+=64){
   const w=new Array(64);
   for(let i=0;i<16;i++){const p=offset+i*4;w[i]=((data[p]<<24)|(data[p+1]<<16)|(data[p+2]<<8)|data[p+3])|0;}
   for(let i=16;i<64;i++){const s0=rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>>3),s1=rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>>10);w[i]=(w[i-16]+s0+w[i-7]+s1)|0;}
   let [a,b,c,d,e,f,g,hh]=h;
   for(let i=0;i<64;i++){const s1=rotr(e,6)^rotr(e,11)^rotr(e,25),ch=(e&f)^(~e&g),t1=(hh+s1+ch+k[i]+w[i])|0,s0=rotr(a,2)^rotr(a,13)^rotr(a,22),maj=(a&b)^(a&c)^(b&c),t2=(s0+maj)|0;hh=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;}
   h=[(h[0]+a)|0,(h[1]+b)|0,(h[2]+c)|0,(h[3]+d)|0,(h[4]+e)|0,(h[5]+f)|0,(h[6]+g)|0,(h[7]+hh)|0];
  }
  return h.map(value=>(value>>>0).toString(16).padStart(8,'0')).join('');
 }
 function validateSetPoint(point,candidateCount){
  need(point&&Array.isArray(point.mask),'해집합 배치벡터가 없습니다.');
  need(Number.isInteger(candidateCount)&&candidateCount>0&&point.mask.length===candidateCount,'해집합 배치벡터 길이가 현재 후보지 수와 다릅니다.');
  need(point.mask.every(state=>Number.isInteger(state)&&state>=0&&state<=3),'해집합 배치벡터에 허용되지 않은 센서 상태가 있습니다.');
  const bits=point.mask.flatMap(state=>[(state===1||state===3)?1:0,(state===2||state===3)?1:0]);
  need(sha256(bits)===point.decision_sha256,'해집합 결정벡터 해시가 배치벡터와 다릅니다.');
  return true;
 }
 function physicalBits(point){return point.mask.flatMap(state=>[(state===1||state===3)?1:0,(state===2||state===3)?1:0]);}
 function hammingDistance(left,right){
  const a=physicalBits(left),b=physicalBits(right);need(a.length===b.length,'Hamming 구성해의 결정벡터 길이가 다릅니다.');
  return a.reduce((total,value,index)=>total+(value!==b[index]?1:0),0);
 }
 function validateClusterGroup(group,pool,admitted,label){
  const clusters=group?.clusters||[],byId=new Map(pool.map(point=>[String(point.id),point])),seen=new Set();
  need(Number(group?.cluster_count??clusters.length)===clusters.length,`${label} 군집 수가 선언값과 다릅니다.`);
  for(const cluster of clusters){
   const members=(cluster.member_ids||[]).map(String);
   need(members.length>0,`${label} 배치군이 비어 있습니다.`);
   need(new Set(members).size===members.length,`${label} 배치군 구성해가 중복됩니다.`);
   need(members.every(id=>byId.has(id)),`${label} 구성해가 허용 집합에 없습니다.`);
   need(members.every(id=>!seen.has(id)),`${label} 구성해가 둘 이상의 배치군에 중복 편입됐습니다.`);
   members.forEach(id=>seen.add(id));
   const memberPoints=members.map(id=>byId.get(id));
   need(memberPoints.every(admitted),`${label} 구성해가 계보·admission 조건을 만족하지 않습니다.`);
   need(members.includes(String(cluster.representative_id)),`${label} 대표해가 해당 배치군 구성원이 아닙니다.`);
   need(members.includes(String(cluster.medoid_member_id)),`${label} medoid가 해당 배치군 구성원이 아닙니다.`);
   if(cluster.cost_priority_member_id!==undefined)need(members.includes(String(cluster.cost_priority_member_id)),`${label} 비용우선 해가 해당 배치군 구성원이 아닙니다.`);
   let diameter=0;
   for(let i=0;i<memberPoints.length;i++)for(let j=i+1;j<memberPoints.length;j++)diameter=Math.max(diameter,hammingDistance(memberPoints[i],memberPoints[j]));
   need(Number(cluster.diameter)===diameter,`${label} 선언 직경이 실제 결정벡터 Hamming 직경과 다릅니다.`);
   const threshold=Number(group?.threshold);
   need(Number.isFinite(threshold)&&diameter<threshold,`${label} 배치군 직경이 complete-link 임계값 미만이 아닙니다.`);
  }
  const admittedIds=new Set(pool.filter(admitted).map(point=>String(point.id)));
  need(admittedIds.size===seen.size&&[...admittedIds].every(id=>seen.has(id)),`${label} admission 통과 배치와 군집 partition이 완전히 일치하지 않습니다.`);
  need(Number(group?.admitted_unique_layouts??seen.size)===seen.size,`${label} 편입 배치 수가 실제 partition과 다릅니다.`);
  return true;
 }
 function validateQuality(result,expected){
  need(result?.schema==='LIVE_SOLUTION_QUALITY_V1','해품질 응답 스키마가 맞지 않습니다.');
  need(result.run_id===expected.run_id,'해품질 실행 ID가 현재 화면과 다릅니다.');
  need(Number(result.generation)===Number(expected.generation),'해품질 세대가 현재 화면과 다릅니다.');
  need(Number(result.solution_id)===Number(expected.solution_id),'해품질 배치 ID가 현재 화면과 다릅니다.');
  need(result?.identity?.problem_sha256===expected.problem_sha256,'해품질 문제 해시가 현재 화면과 다릅니다.');
  need(result?.identity?.decision_sha256===expected.decision_sha256,'해품질 결정벡터 해시가 현재 지도와 다릅니다.');
  need(result?.identity?.row_binding_sha256===expected.row_binding_sha256,'해품질 원시행 결속 해시가 현재 실행행과 다릅니다.');
  need(same(result?.selected?.mask,expected.mask),'해품질 배치벡터가 현재 지도와 다릅니다.');
  validateSetPoint({mask:result?.selected?.mask,decision_sha256:result?.identity?.decision_sha256},expected.mask.length);
  return true;
 }
 function validateSet(result,expected){
  need(result?.schema==='LIVE_SOLUTION_SET_CONFIDENCE_V2','해집합 응답 스키마가 맞지 않습니다.');
  need(result.run_id===expected.run_id,'해집합 실행 ID가 현재 화면과 다릅니다.');
  need(Number(result.generation)===Number(expected.generation),'해집합 세대가 현재 화면과 다릅니다.');
  need(result?.source?.problem_sha256===expected.problem_sha256,'해집합 문제 해시가 현재 화면과 다릅니다.');
  const points=result?.corrected_set?.points;
  need(Array.isArray(points),'해집합 배치 배열이 없습니다.');
  const candidateCount=Number(expected.candidate_count);
  points.forEach(point=>validateSetPoint(point,candidateCount));
  const allowedProvenance=new Set(['RAW_MOEA_OBSERVED','DERIVED_AUDIT_NOT_MOEA']);
  need(points.every(point=>allowedProvenance.has(point.provenance)),'원시·감사 해집합에 허용되지 않은 계보가 섞였습니다.');
  need(points.every(point=>point.provenance!=='MATHEMATICAL_FEASIBILITY_WITNESS_NOT_MOEA'),'수학 기준 배치는 원시·감사 해집합에 편입할 수 없습니다.');
  const ids=points.map(point=>String(point.id));
  const decisions=points.map(point=>String(point.decision_sha256));
  need(new Set(ids).size===ids.length,'해집합 외부 ID가 중복됩니다.');
  need(new Set(decisions).size===decisions.length,'해집합 결정벡터가 중복됩니다.');
  const known=new Set(ids);
  for(const group of [result.hamming_raw_stable,result.hamming_promotion,result.hamming]){
   for(const cluster of group?.clusters||[]){
   need(known.has(String(cluster.representative_id)),'Hamming 대표해가 해집합에 없습니다.');
   need(known.has(String(cluster.medoid_member_id)),'Hamming medoid가 해집합에 없습니다.');
    const members=(cluster.member_ids||[]).map(String);
    need(members.length>0,'Hamming 배치군이 비어 있습니다.');
    need(new Set(members).size===members.length,'Hamming 배치군 구성해가 중복됩니다.');
    need(members.every(id=>known.has(id)),'Hamming 구성해가 해집합에 없습니다.');
    need(members.includes(String(cluster.representative_id)),'Hamming 대표해가 해당 배치군 구성원이 아닙니다.');
    need(members.includes(String(cluster.medoid_member_id)),'Hamming medoid가 해당 배치군 구성원이 아닙니다.');
    if(cluster.cost_priority_member_id!==undefined)need(members.includes(String(cluster.cost_priority_member_id)),'Hamming 비용우선 해가 해당 배치군 구성원이 아닙니다.');
   }
  }
  const audited=result?.audited_explanation_set||{},auditedPoints=audited.points||[];
  auditedPoints.forEach(point=>validateSetPoint(point,candidateCount));
  const auditedIds=auditedPoints.map(point=>String(point.id));
  const auditedDecisions=auditedPoints.map(point=>String(point.decision_sha256));
  need(new Set(auditedIds).size===auditedIds.length,'감사 설명 후보 ID가 중복됩니다.');
  need(new Set(auditedDecisions).size===auditedDecisions.length,'감사 설명 후보 결정벡터가 중복됩니다.');
  need(auditedIds.every(id=>!known.has(id)),'원시·교정 해집합과 감사 설명 후보의 ID가 충돌합니다.');
  const correctedDecisions=new Set(decisions);
  need(auditedDecisions.every(digest=>!correctedDecisions.has(digest)),'원시·교정 해집합과 감사 설명 후보의 결정벡터가 충돌합니다.');
  need(auditedPoints.every(point=>point.provenance==='DERIVED_AUDIT_NOT_MOEA'),'감사 설명 후보의 파생 계보 표시가 없습니다.');
  validateClusterGroup(result.hamming_raw_stable,points,point=>point.provenance==='RAW_MOEA_OBSERVED'&&point?.quality_admission?.raw_stable_explanation_candidate===true,'원시 안정 Hamming');
  validateClusterGroup(result.hamming_promotion,points,point=>point.provenance==='RAW_MOEA_OBSERVED'&&point?.quality_admission?.promotion_candidate===true,'원시 승격 Hamming');
  validateClusterGroup(audited.hamming,auditedPoints,point=>point.provenance==='DERIVED_AUDIT_NOT_MOEA'&&point?.quality_admission?.audited_explanation_candidate===true,'감사 설명 Hamming');
  const occurrences=result?.source?.raw_source_occurrences;
  need(Array.isArray(occurrences),'원시 배치 발생 계보가 없습니다.');
  const rawBindings=new Set(occurrences.map(row=>`${String(row.canonical_raw_id)}:${String(row.decision_sha256)}`));
  const rawSourceIds=new Set((result?.source?.raw_source_ids||[]).map(String));
  need(points.filter(point=>point.provenance==='RAW_MOEA_OBSERVED').every(point=>rawBindings.has(`${String(point.id)}:${String(point.decision_sha256)}`)),'원시 해집합 ID·결정벡터가 원시 발생행 계보와 다릅니다.');
  need([...points,...auditedPoints].filter(point=>point.provenance==='DERIVED_AUDIT_NOT_MOEA').every(point=>rawSourceIds.has(String(point?.lineage?.source_raw_id))),'감사 파생 후보의 원시 출처 ID가 누적 원시 해집합에 없습니다.');
  const auditedKnown=new Set(auditedIds);
  for(const cluster of audited?.hamming?.clusters||[]){
   const members=(cluster.member_ids||[]).map(String);
   need(members.length>0,'감사 Hamming 배치군이 비어 있습니다.');
   need(members.every(id=>auditedKnown.has(id)),'감사 Hamming 구성해가 감사 후보집합에 없습니다.');
   need(members.includes(String(cluster.representative_id)),'감사 Hamming 대표가 해당 배치군 구성원이 아닙니다.');
  }
  return true;
 }
 function admissionText(point){
  const qa=point?.quality_admission||{},derived=point?.provenance==='DERIVED_AUDIT_NOT_MOEA';
  const pass500=qa.target_qualified===true,pass250=qa.grid_250_target_retained===true,minimal=qa.target_resource_minimal===true;
  const stable=qa.raw_stable_explanation_candidate===true,promoted=qa.promotion_candidate===true;
  if(derived){
   const e=point?.lineage?.edit||{},iterated=e==='iterated_dH2_closure',steps=Number(point?.lineage?.steps?.length||point?.local_closure?.steps||0);
   const kind=iterated?`dH=2 위치교환 ${steps}단계 후 국소폐쇄`:e.kind==='delete'?'한 대 삭제':'한 위치 교환';
   const target=pass500?'95%·90% 성능 기준선 통과':'95%·90% 성능 기준선 미달 또는 미검사';
   const closure=iterated&&qa.one_swap_exhaustive&&qa.two_grid_local_closure?' 최종 배치의 가능한 dH=2 교환을 전수검사해 두 격자 기준의 추가 국소 개선 반례가 없었습니다.':'';
   return `원시 배치 #${point?.lineage?.source_raw_id}에서 ${kind}로 만든 감사 설명 배치입니다. 현행 물리 제약을 만족하고 ${target} 상태입니다.${closure} 원시 MOEA 산출물이나 전역 최적해가 아닙니다.`;
  }
  const grid=pass250?'250m에서도 목표 유지':'250m에서는 목표 미달 또는 미검사';
  const deletion=minimal?'한 대 삭제 전수검사에서 목표유지 불필요 장비 없음':'목표를 유지한 한 대 삭제가 존재하거나 아직 배제되지 않음';
  const inconsistent=(promoted&&!(pass500&&pass250&&minimal&&stable))||(stable&&!(pass500&&pass250));
  const role=inconsistent?'품질판정 입력계약 불일치 · 승격 차단':promoted?'엄격 승격후보 조건 통과':stable?'구조 비교용 원시 안정 설명후보':'진단용 원시 해 · 안정 설명후보 아님';
  return `실제 NSGA-III 원시 관측 해 · 500m ${pass500?'목표 통과':'목표 미달'} · ${grid} · ${deletion} · ${role}.`;
 }
 function robustProofKey(context,threshold){
  return context?.last&&context.generation!==undefined&&context?.problem?.problem_sha256?`${context.last.id}:${context.generation}:${context.problem.problem_sha256}:${Number(threshold)}`:'';
 }
 function robustProofResponseIsCurrent(requestKey,requestSerial,currentContext,currentThreshold,currentSerial){
  return Number(requestSerial)===Number(currentSerial)&&requestKey===robustProofKey(currentContext,currentThreshold);
 }
 function validateRobustProof(result,expected){
  need(result?.schema==='LIVE_ROBUST_COST_PROOF_V1','비용 정밀검산 응답 스키마가 맞지 않습니다.');
  need(result.run_id===expected.run_id,'비용 정밀검산 실행 ID가 현재 화면과 다릅니다.');
  need(Number(result.generation)===Number(expected.generation),'비용 정밀검산 세대가 현재 화면과 다릅니다.');
  need(Number(result.threshold)===Number(expected.threshold),'비용 정밀검산 Hamming 기준이 현재 화면과 다릅니다.');
  need(result.problem_sha256===expected.problem_sha256,'비용 정밀검산 문제 해시가 현재 화면과 다릅니다.');
  const lineage=result?.lineage_comparison||{},mathematical=lineage.mathematical_reference;
  if(result.exact_minimum_robust_target_cost!==null&&result.exact_minimum_robust_target_cost!==undefined){
   need(mathematical?.provenance==='MATHEMATICAL_FEASIBILITY_WITNESS_NOT_MOEA','수학 비용 기준의 계보가 없거나 잘못되었습니다.');
   const exactRow=(result.rows||[]).find(row=>Number(row.cost)===Number(result.exact_minimum_robust_target_cost));
   need(exactRow?.reference_layout?.decision_sha256===mathematical.decision_sha256,'비용 증명행과 수학 기준 배치의 결정벡터 해시가 다릅니다.');
  }
  if(lineage.best_raw_moea!==null&&lineage.best_raw_moea!==undefined)need(lineage.best_raw_moea.provenance==='RAW_MOEA_OBSERVED','원시 NSGA-III 비용 기준의 계보가 잘못되었습니다.');
  if(lineage.best_audit_derived!==null&&lineage.best_audit_derived!==undefined)need(lineage.best_audit_derived.provenance==='DERIVED_AUDIT_NOT_MOEA','감사 파생 비용 기준의 계보가 잘못되었습니다.');
  return true;
 }
 return{validateQuality,validateSet,validateSetPoint,validateRobustProof,admissionText,robustProofKey,robustProofResponseIsCurrent};
});
