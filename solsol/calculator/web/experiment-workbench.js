(async()=>{
 const pct=v=>(100*v).toFixed(1)+'%';
 const res=await fetch('/api/experiment-workbench/v94/latest',{cache:'no-store'}),data=await res.json();
 if(!res.ok)throw Error(data.error||'실험 결과를 열 수 없습니다.');
 const confirms=data.arms.filter(r=>r.arm.startsWith('confirm_'));
 const selected=confirms.filter(r=>r.arm.includes('selected'));
 const baseline=confirms.filter(r=>r.arm.includes('baseline'));
 const group=data.confirmation.groups;
 document.getElementById('integrity').textContent=data.artifact.manifest_verified?`프로그램 실행 ${data.artifact.source_run_count}건·원시 해시 일치`:'무결성 확인 필요';
 document.getElementById('decision').textContent='목적식은 유지하고, 전체 절충해와 목표통과 부분집합을 분리합니다';
 document.getElementById('decisionWhy').textContent=`기본조건 3개 seed의 비지배 전선은 중앙값 ${group.baseline.median_front_objectives}개였고 탐지 100% 비율은 ${pct(group.baseline.median_detection_100_ratio)}, 식별 100%는 ${pct(group.baseline.median_identification_100_ratio)}였습니다. D–비용과 I–비용 절충쌍이 각각 ${pct(group.baseline.median_d_cost_tradeoff_ratio)}, ${pct(group.baseline.median_i_cost_tradeoff_ratio)} 남아 목적식 포화가 아니라 목표통과 필터가 중간성능 해를 숨긴 것이 주된 원인이었습니다.`;
 const label=r=>r.arm.includes('baseline')?'기본 · 면적100% · R3/E1.5 · R10/E21':'비교 · 면적150% · R4/E2 · R8/E18';
 document.getElementById('runCards').innerHTML=confirms.map(r=>`<article class="runCard"><h3>${label(r)} · seed ${r.config.seed}</h3><div class="metricGrid"><div class="metric"><b>${r.empirical_front_objectives}</b><span>전체 물리 비지배 목적벡터</span></div><div class="metric"><b>${r.operational_target_objectives}</b><span>95%·90% 통과 목적벡터</span></div><div class="metric"><b>${pct(r.front_saturation.detection_100_ratio)}</b><span>전선 내 탐지 100%</span></div><div class="metric"><b>${r.front_unique_values.detection}/${r.front_unique_values.identification}/${r.front_unique_values.cost}</b><span>탐지/식별/비용 고유값</span></div><div class="metric"><b>${r.operational_target_min_cost??'없음'}</b><span>관측 목표통과 최저비용</span></div><div class="metric"><b>${r.meaningful_front_status}</b><span>사전등록 변별력 판정</span></div></div><a href="live.html?run=${r.run_id}">전체 절충해와 배치 지도 보기</a></article>`).join('');
 document.getElementById('saturation').innerHTML=`<table class="evidenceTable"><thead><tr><th>조건·seed</th><th>전선</th><th>탐지100%</th><th>식별100%</th><th>D–비용</th><th>I–비용</th></tr></thead><tbody>${confirms.map(r=>`<tr><td>${label(r)} · ${r.config.seed}</td><td>${r.empirical_front_objectives}</td><td>${pct(r.front_saturation.detection_100_ratio)}</td><td>${pct(r.front_saturation.identification_100_ratio)}</td><td>${pct(r.pairwise_tradeoff_ratio.detection_vs_cost)}</td><td>${pct(r.pairwise_tradeoff_ratio.identification_vs_cost)}</td></tr>`).join('')}</tbody></table><p class="good">100% 극단해는 남지만 전선의 대부분을 차지하지 않습니다. 목표통과 필터를 끄면 비용 0부터 고성능 극단까지 같은 실행의 절충구조를 확인할 수 있습니다.</p>`;
 document.getElementById('exact').innerHTML=`<h3>조건 변화 판정</h3><p>기본조건은 seed별 ${baseline.map(r=>r.operational_target_objectives).join('·')}개, 비교조건은 ${selected.map(r=>r.operational_target_objectives).join('·')}개의 목표통과 목적벡터를 찾았습니다. 비교조건의 관측 목표통과 최저비용은 ${selected.map(r=>r.operational_target_min_cost).join('·')}점입니다.</p><p class="warn">반경을 키우면 목표 도달은 쉬워지지만 탐지 고성능 구간도 늘어납니다. 따라서 반경·면적·보유량을 원하는 그래프 모양에 맞춰 임의 조작하지 않고, 시나리오 난이도 옵션으로 분리해야 합니다.</p>`;
 document.getElementById('nextExperiment').innerHTML=['기본 목적식 유지: 전체영역 탐지손실·공동식별손실·설치비용을 그대로 계산','기본 목록은 전체 물리 Pareto 근사해로 표시하고 95%·90% 통과안은 별도 필터로 제공','기본조건은 R3/E1.5·면적100%·R10/E21, 비교 난이도는 R4/E2·면적150%·R8/E18로 구분','D와 I가 반드시 서로 반대가 되도록 인위적 구역이나 가중치를 추가하지 않음; 실제 공용 설치예산·채널 같은 물리 제약이 승인될 때만 별도 실험','각 조건은 다중 seed, 포화율, 고유 목적값, 비용 절충쌍과 배치 지도를 함께 판정'].map(x=>`<li>${x}</li>`).join('');
})().catch(error=>{document.getElementById('decision').textContent='실험 결과를 열지 못했습니다';document.getElementById('decisionWhy').textContent=String(error)});

(async()=>{
 const res=await fetch('/api/experiment-workbench/v96/latest',{cache:'no-store'}),data=await res.json();
 if(!res.ok)throw Error(data.error||'초기화 비교 결과를 열 수 없습니다.');
 const groups=data.groups,names={random:'무작위',greedy:'Greedy',milp:'MILP / ε-constraint'};
 document.getElementById('initializerIntegrity').textContent=data.artifact.manifest_verified&&data.artifact.source_lineage_verified?`원시 실행 ${data.artifact.source_run_count}건 · 해시 일치`:'무결성 확인 필요';
 document.getElementById('initializerDecision').innerHTML='<b>계산 결론:</b> 무작위가 “해를 만들지 못한” 것이 아닙니다. 전체 물리 비지배 목적벡터는 seed별 200–230개였지만 150세대 안에 95%·90%를 동시에 통과한 행이 없었습니다. Greedy는 통과 목적벡터 1개, MILP는 7–8개를 찾았습니다. 따라서 초기화 선택은 목적함수를 바꾸지 않지만 제한된 예산에서 목표 영역에 도달하는 속도에 큰 영향을 줍니다.';
 const rows=Object.entries(groups).map(([key,g])=>`<tr><td>${names[key]}</td><td>${g.nfe.join(' · ')}</td><td>${g.full_front_objectives.join(' · ')}</td><td>${g.target_front_objectives.join(' · ')}</td><td>${g.target_rows.join(' · ')}</td><td>${g.target_min_cost.map(v=>v??'미도달').join(' · ')}</td><td>${g.detection_100_raw_ratio.map(v=>(100*v).toFixed(1)+'%').join(' · ')}</td></tr>`).join('');
 document.getElementById('initializerComparison').innerHTML=`<div class="tableWrap"><table class="evidenceTable"><thead><tr><th>초기화</th><th>실제 NFE</th><th>전체 비지배 목적벡터</th><th>목표통과 비지배 목적벡터</th><th>목표통과 원시 행</th><th>목표통과 최저비용</th><th>원시 탐지 100% 비율</th></tr></thead><tbody>${rows}</tbody></table></div><p class="boundary">세 값은 seed 8701·8702·8703 순서입니다. 전체 해집합은 초기화와 무관하게 충분한 절충 구조를 보였고, 목표통과 부분집합의 차이는 초기화 의존성을 보여줍니다. 무작위·Greedy 결과를 오류로 숨기지 않고 전체 해집합 지도에서 볼 수 있어야 합니다.</p>`;
})().catch(error=>{document.getElementById('initializerIntegrity').textContent='불러오기 실패';document.getElementById('initializerDecision').textContent=String(error)});

(async()=>{
  const runSelect = document.getElementById('compareRunSelect');
  const solSelect = document.getElementById('compareSolutionSelect');
  if(!runSelect || !solSelect) return;

  const res = await fetch('/api/experiment-workbench/solution-comparison', {cache:'no-store'});
  const data = await res.json();
  if(!res.ok) throw Error(data.error || '해 비교 데이터를 불러올 수 없습니다.');

  const problem = data.problem;
  const runs = data.runs;
  const controls = {
    candidates: document.getElementById('compareCandidates'),
    candidateLabels: document.getElementById('compareCandidateLabels'),
    defense: document.getElementById('compareDefense'),
    demand: document.getElementById('compareDemand'),
    layer: document.getElementById('compareLayer')
  };
  let selectedSolution = null;

  runSelect.innerHTML = runs.map(r => `<option value="${r.run_id}">${r.label}</option>`).join('');

  function mapOptions() {
    return {
      candidates: controls.candidates.checked,
      candidateLabels: controls.candidateLabels.checked,
      defense: controls.defense.checked,
      demand: controls.demand.checked,
      layer: controls.layer.value
    };
  }

  function renderComparisonMaps(sol) {
    if(!sol || !window.LiveCore?.map) return;
    const rawPoint = {
      mask: sol.raw_mask,
      performance: sol.raw_performance,
      cost: sol.raw_cost,
      sensor_counts: sol.raw_sensor_counts,
      id: sol.raw_id,
      provenance: 'RAW_MOEA_OBSERVED'
    };
    const improvedPoint = {
      mask: sol.improved_mask,
      performance: sol.improved_performance,
      cost: sol.improved_cost,
      sensor_counts: sol.improved_sensor_counts,
      id: sol.raw_id + '_improved',
      provenance: sol.has_counterexample ? 'DERIVED_AUDIT_NOT_MOEA' : 'RAW_MOEA_OBSERVED'
    };
    const options = mapOptions();
    document.getElementById('rawMapWrap').innerHTML = LiveCore.map(problem, rawPoint, options);
    let improvedSvg = LiveCore.map(problem, improvedPoint, options);

    if(sol.changed_sites?.length) {
      const unit = (problem.map_metres || 20000) / 800;
      const sx = x => 60 + x / unit;
      const sy = y => 850 - y / unit;
      const markers = sol.changed_sites.map((change, index) => {
        const site = problem.sites[change.site];
        if(!site) return '';
        const cx = sx(site[0]), cy = sy(site[1]);
        return `<g data-change-site="${change.site}">
          <title>변경 ${index + 1} · 후보지 ${change.site + 1}번 · ${change.action}</title>
          <circle cx="${cx}" cy="${cy}" r="24" fill="#fff7ed" fill-opacity=".65" stroke="#c2410c" stroke-width="5"/>
          <circle cx="${cx + 18}" cy="${cy - 18}" r="12" fill="#9a3412" stroke="white" stroke-width="2"/>
          <text x="${cx + 18}" y="${cy - 13}" text-anchor="middle" font-size="13" font-weight="bold" fill="white">${index + 1}</text>
        </g>`;
      }).join('');
      improvedSvg = improvedSvg.replace('</svg>', `<g class="changedSitesHighlightOverlay">${markers}</g></svg>`);
    }
    document.getElementById('improvedMapWrap').innerHTML = improvedSvg;

    const summary = document.getElementById('comparisonChangeSummary');
    summary.hidden = !sol.changed_sites?.length;
    summary.innerHTML = sol.changed_sites?.length
      ? `<strong>개선 지도 변경 위치</strong>${sol.changed_sites.map((change, index) => `<span><b>${index + 1}</b> 후보지 ${change.site + 1}번 · ${change.action}</span>`).join('')}`
      : '';
  }

  function renderSelectedSolution() {
    const runId = runSelect.value;
    const run = runs.find(r => r.run_id === runId) || runs[0];
    if(!run || !run.solutions || !run.solutions.length) {
      document.getElementById('solutionDetailCard').innerHTML = '<p class="warn">해당 실험에서 분석 가능한 정량목표 통과 해가 없습니다.</p>';
      document.getElementById('rawMapWrap').innerHTML = '';
      document.getElementById('improvedMapWrap').innerHTML = '';
      document.getElementById('diffTableBody').innerHTML = '';
      document.getElementById('comparisonChangeSummary').hidden = true;
      selectedSolution = null;
      return;
    }

    const solIdx = parseInt(solSelect.value, 10) || 0;
    const sol = run.solutions[solIdx] || run.solutions[0];
    selectedSolution = sol;

    // 1. Detail Card
    const costDelta = sol.raw_cost - sol.improved_cost;
    const dDelta = ((sol.improved_performance[0] - sol.raw_performance[0]) * 100).toFixed(2);
    const iDelta = ((sol.improved_performance[1] - sol.raw_performance[1]) * 100).toFixed(2);

    document.getElementById('solutionDetailCard').innerHTML = `
      <div class="detailCardHead">
        <div class="detailCardTitle">원시 해 #${sol.raw_id} vs 검사 교정 개선해</div>
        <span class="statusBadge ${sol.has_counterexample ? 'counterexample' : 'minimal'}">
          ${sol.has_counterexample ? '⚠️ 국소 검사 반례 발견 (교정 개선 완료)' : '✓ 국소 최소 만족 (반례 없음 · 원시해 승인)'}
        </span>
      </div>
      <p class="detailCardDesc">${sol.improvement_description}</p>
      <div class="detailMetricsGrid">
        <div class="detailMetricItem">
          <span>설치 비용</span>
          <strong>${sol.raw_cost}점 → ${sol.improved_cost}점</strong>
          <small>${costDelta > 0 ? `${costDelta}점 절감 (${((costDelta/sol.raw_cost)*100).toFixed(1)}%↓)` : '동일 비용 유지'}</small>
        </div>
        <div class="detailMetricItem">
          <span>탐지 충족률 (목표 95%)</span>
          <strong>${(sol.raw_performance[0]*100).toFixed(2)}% → ${(sol.improved_performance[0]*100).toFixed(2)}%</strong>
          <small>${parseFloat(dDelta) > 0 ? `+${dDelta}%p 향상` : '목표 충족 유지'}</small>
        </div>
        <div class="detailMetricItem">
          <span>식별 충족률 (목표 90%)</span>
          <strong>${(sol.raw_performance[1]*100).toFixed(2)}% → ${(sol.improved_performance[1]*100).toFixed(2)}%</strong>
          <small>${parseFloat(iDelta) > 0 ? `+${iDelta}%p 향상` : '목표 충족 유지'}</small>
        </div>
        <div class="detailMetricItem">
          <span>센서 구성 (Radar / EO)</span>
          <strong>R${sol.raw_sensor_counts[0]}·E${sol.raw_sensor_counts[1]} → R${sol.improved_sensor_counts[0]}·E${sol.improved_sensor_counts[1]}</strong>
          <small>${sol.has_counterexample ? (sol.improvement_type==='DELETE'?'과배치 센서 제거':'센서 위치 최적 이전'):'원시 최적 구성'}</small>
        </div>
      </div>
    `;

    // 2. Map Summaries
    document.getElementById('rawMetricsSummary').innerHTML = `
      <b>원시해 #${sol.raw_id}</b> · 비용 <strong>${sol.raw_cost}점</strong> · 탐지 <strong>${(sol.raw_performance[0]*100).toFixed(2)}%</strong> · 식별 <strong>${(sol.raw_performance[1]*100).toFixed(2)}%</strong> (Radar ${sol.raw_sensor_counts[0]}대 / EO ${sol.raw_sensor_counts[1]}대)
    `;
    document.getElementById('improvedMetricsSummary').innerHTML = `
      <b>교정 개선해</b> · 비용 <strong>${sol.improved_cost}점</strong> · 탐지 <strong>${(sol.improved_performance[0]*100).toFixed(2)}%</strong> · 식별 <strong>${(sol.improved_performance[1]*100).toFixed(2)}%</strong> (Radar ${sol.improved_sensor_counts[0]}대 / EO ${sol.improved_sensor_counts[1]}대)
    `;

    // 3. SVG Maps
    renderComparisonMaps(sol);

    // 4. Comparison Diff Table Rows
    const tableRows = [
      {
        item: '설치 총비용 (Cost)',
        raw: `${sol.raw_cost}점`,
        improved: `${sol.improved_cost}점`,
        diff: costDelta > 0 ? `<span class="changeHighlight">${costDelta}점 절감 (${((costDelta/sol.raw_cost)*100).toFixed(1)}%↓)</span>` : '동일 비용 유지'
      },
      {
        item: 'Radar 센서 수량',
        raw: `${sol.raw_sensor_counts[0]}대`,
        improved: `${sol.improved_sensor_counts[0]}대`,
        diff: sol.raw_sensor_counts[0] !== sol.improved_sensor_counts[0] ? `<span class="changeHighlight">${sol.raw_sensor_counts[0] - sol.improved_sensor_counts[0]}대 제거</span>` : '변화 없음'
      },
      {
        item: 'EO/IR 센서 수량',
        raw: `${sol.raw_sensor_counts[1]}대`,
        improved: `${sol.improved_sensor_counts[1]}대`,
        diff: sol.raw_sensor_counts[1] !== sol.improved_sensor_counts[1] ? `<span class="changeHighlight">${sol.raw_sensor_counts[1] - sol.improved_sensor_counts[1]}대 제거</span>` : '변화 없음'
      },
      {
        item: '탐지 충족률 (Detection Rate)',
        raw: `${(sol.raw_performance[0]*100).toFixed(2)}%`,
        improved: `${(sol.improved_performance[0]*100).toFixed(2)}%`,
        diff: parseFloat(dDelta) > 0 ? `<span class="changeHighlight">+${dDelta}%p 향상</span>` : '목표(95%) 충족 유지'
      },
      {
        item: '식별 충족률 (Identification Rate)',
        raw: `${(sol.raw_performance[1]*100).toFixed(2)}%`,
        improved: `${(sol.improved_performance[1]*100).toFixed(2)}%`,
        diff: parseFloat(iDelta) > 0 ? `<span class="changeHighlight">+${iDelta}%p 향상</span>` : '목표(90%) 충족 유지'
      },
      {
        item: '국소 검사 반례 분석',
        raw: sol.has_counterexample ? `반례 검출 (${sol.improvement_type === 'DELETE' ? '1-Delete 과배치' : '1-Swap 지배'})` : '1-Delete / 1-Swap 반례 없음',
        improved: sol.has_counterexample ? '교정 완료 (개선안 도출)' : '원시해 구성 승인',
        diff: sol.improvement_description
      },
      {
        item: '개선된 위치 및 변경 내역',
        raw: '원시 최적화 산출 배치',
        improved: sol.changed_sites.length ? sol.changed_sites.map(cs => `<span class="changedSiteTag">후보지 ${cs.site+1}번: ${cs.action}</span>`).join(' ') : '수정 불필요 (국소 최소)',
        diff: sol.improvement_type === 'DELETE' ? '과배치 센서 제거로 동일 성능 대비 예산 절감' : sol.improvement_type === 'SWAP' ? '배치 위치 최적 교체로 커버리지 지배' : '검사 통과'
      }
    ];

    const diffTable = document.getElementById('diffTableBody') || document.getElementById('comparisonDiffRows');
    if(diffTable) {
      diffTable.innerHTML = tableRows.map(r => `
        <tr>
          <td data-label="항목"><b>${r.item}</b></td>
          <td data-label="원시해">${r.raw}</td>
          <td data-label="개선해">${r.improved}</td>
          <td data-label="변화 및 개선 효과">${r.diff}</td>
        </tr>
      `).join('');
    }
  }

  function updateSolutionOptions() {
    const runId = runSelect.value;
    const run = runs.find(r => r.run_id === runId) || runs[0];
    if(!run || !run.solutions) return;

    solSelect.innerHTML = run.solutions.map((s, idx) => {
      const tag = s.has_counterexample ? `[반례개선 → ${s.improved_cost}점]` : '[반례없음]';
      return `<option value="${idx}">해 #${s.raw_id} · 비용 ${s.raw_cost}점 · 탐지 ${(s.raw_performance[0]*100).toFixed(1)}% / 식별 ${(s.raw_performance[1]*100).toFixed(1)}% ${tag}</option>`;
    }).join('');

    renderSelectedSolution();
  }

  runSelect.addEventListener('change', updateSolutionOptions);
  solSelect.addEventListener('change', renderSelectedSolution);
  Object.values(controls).forEach(control => control.addEventListener('change', () => renderComparisonMaps(selectedSolution)));

  updateSolutionOptions();
})().catch(error => {
  console.error('Solution comparison load error:', error);
  const card = document.getElementById('solutionDetailCard');
  if(card) card.innerHTML = `<p class="warn">해 비교 데이터를 불러오지 못했습니다: ${String(error)}</p>`;
});
