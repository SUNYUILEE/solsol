/* Read recovery is bounded. Ambiguous writes are never automatically repeated. */
'use strict';
const LiveTransport=(()=>{
 const transient=new Set([408,429,502,503,504]);
 function error(message,code,status){return Object.assign(new Error(message),{code,status});}
 function create(env={}){
  const send=env.fetch||((...a)=>fetch(...a)),now=env.now||(()=>performance.now());
  const later=env.setTimeout||setTimeout,clear=env.clearTimeout||clearTimeout;
  const total=env.totalMs??15000,attemptMs=env.attemptMs??5000,delays=env.delays??[300,700];
  return async function json(path,{body,headers={},onRetry=()=>{}}={}){
   const read=body===undefined,start=now(),attempts=read?3:1;
   for(let attempt=0;attempt<attempts;attempt++){
    const remaining=total-(now()-start);if(remaining<=0)break;
    const controller=new AbortController();let timer,knownStatus;
    try{
     const response=await Promise.race([
      (async()=>{
       const r=await send(path,{method:read?'GET':'POST',headers,body:read?undefined:JSON.stringify(body),signal:controller.signal,cache:'no-store'});
       knownStatus=r.status;
       if(read&&transient.has(r.status)){
        r.body?.cancel()?.catch(()=>{});
        throw error(`일시적인 서버 응답 (HTTP ${r.status})`,'TRANSIENT',r.status);
       }
       const text=await r.text();let data;
       try{data=JSON.parse(text);}catch{throw error('서버 응답 형식을 확인할 수 없습니다. 기존 화면은 유지됩니다.','INVALID_DATA',r.status);}
       if(!r.ok)throw error(data?.error||`서버 응답 오류 (HTTP ${r.status})`,'HTTP',r.status);
       return data;
      })(),
      new Promise((_,reject)=>{timer=later(()=>{controller.abort();reject(error('조회 제한시간을 넘었습니다.','TIMEOUT'));},Math.min(read?attemptMs:total,remaining));})
     ]);
     return response;
    }catch(e){
     if(knownStatus!==undefined&&(knownStatus<200||knownStatus>=300)&&(!read||!transient.has(knownStatus))){
      throw e.code==='HTTP'?e:error(`서버가 요청을 거절했습니다 (HTTP ${knownStatus}). 기존 화면은 유지됩니다.`,'HTTP',knownStatus);
     }
     const retryable=['TRANSIENT','TIMEOUT'].includes(e.code)||e instanceof TypeError||['AbortError','TimeoutError'].includes(e.name);
     if(!read){
      if(e.code==='HTTP')throw e;
      throw error('요청 응답을 확인하지 못했습니다. 계산 시작·중지 요청은 이미 접수됐을 수 있습니다. 다시 요청하기 전에 ‘다시 연결’로 실행 기록과 상태를 확인하세요.','WRITE_UNCERTAIN');
     }
     if(!retryable)throw e;
     const wait=delays[attempt]??0;
     if(attempt===attempts-1||now()-start+wait>=total)break;
     onRetry({attempt:attempt+2,maximum:attempts});
     // Cancel the attempt timer before backoff; total budget includes this wait.
     clear(timer);timer=undefined;await new Promise(resolve=>later(resolve,wait));
    }finally{clear(timer);}
   }
   throw error('결과 조회 연결을 복구하지 못했습니다. 마지막 지도와 선택은 유지됩니다. 계산 중단 여부는 아직 확인되지 않았습니다. ‘다시 연결’로 현재 상태를 확인하세요.','READ_UNAVAILABLE');
  };
 }
 return {create};
})();
if(typeof module!=='undefined')module.exports=LiveTransport;
