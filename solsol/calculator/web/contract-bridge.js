'use strict';
// Preserve the baseline payload shape while making every API route explicit.
const originalFetch=window.fetch.bind(window);
window.fetch=(input,options={})=>{
 const url=typeof input==='string'?input:input.url;
 if(url.startsWith('/api/')){
  const headers=new Headers(options.headers||{});headers.set('X-Experiment-Contract','RADAR_EOIR');
  return originalFetch('/contracts/RADAR_EOIR'+url,{...options,headers}).then(async response=>{
   if(response.headers.get('X-Experiment-Contract')!=='RADAR_EOIR')throw new Error('Experiment contract mismatch');
   if(response.headers.get('Content-Type')?.includes('application/json')){
    const packet=await response.clone().json();if(response.headers.get('X-Experiment-Contract')!=='RADAR_EOIR'||(!Array.isArray(packet)&&packet.experiment_contract_id!=='RADAR_EOIR'))throw new Error('Experiment contract mismatch');
   }return response;
  });
}return originalFetch(input,options);
};
document.addEventListener('click',async event=>{
 const anchor=event.target.closest?.('a');if(!anchor)return;
 const path=anchor.getAttribute('href');if(!path?.startsWith('/api/'))return;
 event.preventDefault();
 try{const response=await window.fetch(path);if(!response.ok)throw new Error('Download HTTP '+response.status);
 const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
 link.href=url;link.download=anchor.download||'RADAR_EOIR_'+path.split('/').at(-2)+'.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(error){const status=document.querySelector('#status');if(status)status.textContent='내보내기 실패 · '+error.message;}
});
document.addEventListener('DOMContentLoaded',()=>{
 const area=document.querySelector('#mapSection')||document.querySelector('main');
 const label=document.createElement('label');label.textContent='실험 선택 ';label.style.cssText='display:block;padding:12px;background:#e6eff5;font-weight:bold';
 const select=document.createElement('select');select.setAttribute('aria-label','실험 선택');
 for(const [id,name] of [['RADAR_EOIR','Radar + EO/IR'],['RADAR_RF_SCANNER','Radar + RF Scanner · 합성 진단']]){const o=document.createElement('option');o.value=id;o.textContent=name;select.append(o);}
 select.onchange=()=>{if(select.value==='RADAR_RF_SCANNER'){label.append(' 조건 반영 중');location.assign('/rf.html');}};
 label.append(select);area.prepend(label);
});
