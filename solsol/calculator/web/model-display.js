'use strict';
// Geometry helpers contain no device-specific coverage model. Actual coverage
// colours come only from the frozen model evaluation row/spatial response.
const ModelDisplay=(()=>{
 function call(operation,...args){
  if(operation==='zone_info')return null;
  if(operation==='zones')return {detection:[],identification:[]};
  throw Error('이 모델 표시 연산은 중립 평가 API의 원시 행을 사용해야 합니다: '+operation);
 }
 return {call};
})();
