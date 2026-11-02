'use strict';
(()=>{
 const problem={sites:[[0,0]],radii:[3000,1500],costs:[6,2],targets:[.95,.9],grid_metres:500,problem_sha256:'fixture',map_metres:20000,demand:[],geometry:{kind:'circle',center:[10000,10000],radius:6000}};
 const point={id:5260,mask:[1],F:[0,1,.0075],G:[0,0],performance:[1,0],cost:6,sensor_counts:[1,0],qualified:true};
 const run={id:'TEST_ONLY_V56',state:'completed',snapshot:{generation:150,evaluations:5436,population_ids:[5260]},points:[point],problem,config:{},persistence:{}};
 LiveExport.update(problem,run,point,{selection_mode:'manual'});LiveGridCheck.update(problem,point,run,150);
 document.getElementById('hardFixture').onclick=()=>LiveSolutionQuality.applyGate({integrity:'FAIL',constraint:'PASS',search:'BOUNDED_INCONCLUSIVE',message:'TEST_ONLY',run_id:run.id,generation:150,solution_id:5260});
 document.getElementById('warningFixture').onclick=()=>LiveSolutionQuality.applyGate({integrity:'PASS',constraint:'PASS',search:'WARNING_DOMINANCE_WITNESS',message:'TEST_ONLY',run_id:run.id,generation:150,solution_id:5260});
 document.getElementById('qualityDecision').textContent='테스트 전용 상태 전환';
})();
