'use strict';
// Reuse the common controls; never create a second set of map state.
(()=>{
 const tools=document.querySelector('.mapTools');if(!tools)return;
 const button=document.createElement('button');button.id='mapToolsDisclosure';
 button.type='button';button.textContent='지도 도구 열기';button.setAttribute('aria-expanded','false');
 tools.id=tools.id||'sharedMapTools';button.setAttribute('aria-controls',tools.id);
 tools.classList.add('mapToolsCollapsed');tools.prepend(button);
 button.onclick=()=>{const closed=tools.classList.toggle('mapToolsCollapsed');button.setAttribute('aria-expanded',String(!closed));button.textContent=closed?'지도 도구 열기':'지도 도구 접기';};
})();
