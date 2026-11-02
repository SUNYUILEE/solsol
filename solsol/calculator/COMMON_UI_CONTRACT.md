# Common calculator UI contract

2026-09-16: The quality/evidence tab must render readable run-bound assessment, not the placement extraction form or only a diagnostics link. Reuse the same assessment in the quality dialog. Explain optional targets, installation and Model feasibility, initial and observed best, constant cost, repeated evaluations, distinct X versus F, and completed diagnostic scope. Binding errors and late responses must not display another run's report. Witness maps include human-unit before/after values. Evidence: `08_검증/QUALITY_EXPLANATION/REVIEW_NOTES.md`.

2026-09-15: Current archive and historical fronts use shared full-performance ordering and global leader-radius Hamming groups before pagination. Deduplicate raw X, retain provenance, expose all members or representatives, group sizes and distances. Group/representative filter changes clear stale comparisons. Three-model normal/enlarged regression evidence: `08_검증/FRONT_HAMMING/REVIEW_NOTES.md`.

## Saved baseline and goal-aware result entry

In settings mode a frozen row is one selected saved placement, not a newly optimized draft. Bind its metadata, run ID, row ID, actual coverage and goal status; never overwrite saved performance with nominal radius-area ratios. Shared `renderSavedConditionContext` runs after model map adapters. Draft geometry remains unevaluated. Opening results defaults to performance100 with saved goals applied when configured; a user's explicit archive choice remains available. Empty qualified sets must be explicit and require an explicit action to include failing rows. The settings shortcuts must not mutate draft inputs.

## Performance-first observed results

`workspace-placements.js` and `engine/placements.py` share `performance100` across configurable models. Select the primary active non-cost objective; remaining active performance objectives retain saved order and each Model direction. Only exact performance ties use max-min bit Hamming. The API selects globally before paging, preserves raw IDs and archive provenance, and returns ranking/order evidence. Normal and expanded controls use the same priority and row. Display actual named objective values separately from coverage percentages. A clickable rank table exposes dominated alternatives. Never treat a successful button/map check as evidence that the ranking serves the user's requested performance priority.

## Shared quality workflow

Current complete-scope execution uses `engine/quality_jobs.py` and `/api/engine/runs/{id}/quality-jobs`. The shared METHODS registry supplies model1/2/3 labels and scope. No evaluation, time or bit-count cap stops a new diagnostic job. Internal32-row batches and100-row pages are transport units. Frozen raw/domain/inventory/goals remain bound. A local/MILP job exhausts its one-change neighborhood; exact exhausts the declared resource-feasible installation space. MILP uses one-hot selection of Model-evaluated alternatives under source-F epsilon bounds, not a linearization or a global nonlinear proof. Persisted checksummed JSON batches and manifest support restart interruption and same-definition resume. The old quality-workflow POST also starts these jobs; budget/offset inputs are rejected. Old bounded records remain GET-only evidence.

`workspace-quality.js` is the shared entry from the top bar and saved-result dock for all registered model contracts. `engine/quality_workflow.py` owns bounded diagnostic orchestration; Model API remains the only F/G evaluator. UI and EngineClient use the same `/api/engine/runs/{id}/quality-workflow` routes. No model may replace these common controls with raw JSON. Display original replay, stock/domain feasibility, saved goal qualification, budget and remaining work, and diagnostic improvement provenance separately. A changed diagnostic code hash invalidates continuation, not historical evidence. Replay mismatch is ERROR and quarantines improvement witnesses. Model-specific mathematical proof methods require separate applicability evidence; common MILP proposals are not exact nonlinear proofs.

New geometric configuration requests default to inside-area at the backend even when the field is omitted. RunService and RunSession enforce the same domain. Legacy policies cannot silently bypass this condition; use the generic policy, or explicitly declare original model space for reproduction. Historical copy explicitly preserves its original domain. Execution snapshots, request identity and run comparisons bind the domain separately from the unchanged Model F/G hash. See `00_research_ops/contracts/PLACEMENT_PROBLEM_ACCEPTANCE.md`; a UI-only assertion does not satisfy QG-06-28.

The calculator owns the shell, draft geometry, execution plan, controls, map interaction and saved-result workflow. Model API owns parameter schemas, scientific definitions, F/G, costs and spatial evaluation. A new model must reuse common UI functions and add only model-specific interpretation.

## Shared implementation

| Concern | Existing shared owner |
| --- | --- |
| Schema fields, units, bounds, presets, conditions and summary slots | workspace-configuration.js: renderSchemaFields |
| Algorithm selection | renderCommonAlgorithm; generic NSGA-III/NSGA-II, legacy policy retains its supported algorithm |
| Random/Greedy/MILP initialization and preparation budget | renderCommonInitialization |
| Generations, population and seed | workspace.js: renderCommonSearchQuantities |
| Quick budget and explicit time limit | workspace-diagnostics.js: renderCommonQuickSettings |
| Objective/diagnostic selection, order, definition and direction | renderMetricControls |
| Archive filter and metric sorting in both normal/expanded maps | resultFilterOptions / resultSortOptions |
| Observed feasible placement collection, global sorting, pages and raw-row selection | engine/placements.py, workspace-placements.js, resultRows; archive remains run.rows |
| Radius-area ratio and its limitation | footprintSummary / footprintNote |
| Frozen comparison conditions | freezeConditionBaseline, preserving row and source parameters |
| Installation changes and map clipping | mapDifference / clipMapMarks |
| Scenario persistence and immutable saved run | saveScenario / openScenarios / common request snapshot |

Reuse the existing shell, IDs, controls and state. Do not add a new UI wrapper for common controls. Model-specific map projections may remain adapters, but must obey all/individual/installed-only layers, comparison identity, main/expanded parity and status semantics. Keep each SVG's intrinsic viewBox when fitting/zooming.

## Meaningful differences

Area goals must default to unset for a fresh scenario. Saved goals and resource mode must remain visible and immutable when the next draft changes. A target filter is offered only when the saved run actually has area goals. Stale target/cluster filters must recover to all accumulated nondominated placements; equal-F distinct-X placements remain available. Display raw evaluation count separately from archive count, which can decrease through dominance. An empty archive must show raw feasible/infeasible counts and constraint reasons. Diagnostic raw candidates remain outside the archive and keep their original X/F/G and run identity. Test with `tools/archive_audit_browser.cjs`, `tools/archive_audit_matrix.py`, `tools/archive_audit_execution.cjs` and `tools/archive_common_regression.cjs`.

HMSP-2D-V1 generates common 2D geometry and uses Model-owned sensor parameters and cue evaluation. HMSP-EXEC-V1 retains explicit external cue/quality/cost inputs; do not manufacture those inputs. Its quality goals are Model G constraints, not coverage percentages. Models without coverage metrics do not offer an area-target archive filter. Historical raw files and evaluator identities remain immutable.

## Required integration evidence

User clarification 2026-09-15 supersedes the prior inside-center default: new normal configurations use the full Model-allowed installation candidate set. Evaluation region defines performance integration, not legal sensor-center locations. Exact species inventory remains hard and independent of optional performance thresholds. A center outside the region can be a useful valid installation. Normal copy uses the full installation domain; historical raw and explicitly recorded restricted domains remain unchanged on read/replay. Initial result view is the cumulative empirical Pareto set; the separate cost/Hamming100 observed collection can contain dominated placements and is never an optimized-set substitute. Show raw ID, counts, hard-constraint audit, effective objective projection and matching reference dimensions. Test full-domain and outside-center coverage acceptance across models1/2/3.

Observed results default to at most 100 cost-prioritized max-min bit-Hamming representatives. Preserve the all-rows paging option and original archive. Filter the whole observed generation prefix before selecting representatives. Same-cost choices use maximum distance to the closest already selected X; seed the lowest-cost band with an archive member if present, then raw-ID ties. This does not guarantee all cost bands or global diversity optimality. Area filters use frozen public boundary and nominal radii, independently from numeric goals; distinguish any/all/no installed centers inside from any/all/no nominal disks intersecting. Empty installations form their own case. Unknown boundaries/radii must be unavailable, never inferred from demand extents. Comparison caches obey the current area filter. Test representative IDs/ranks/Hamming, geometry boundaries, target-off, empty/unsupported, reset, expanded and model switching with tools/representative_area_verify.py and tools/representative_area_browser.cjs.

All-inventory configurable runs open the observed feasible unique-X collection by default, unless the user saved a collection preference. The collection includes dominated placements and is not an enumeration of all possible installations. The original nondominated archive is a separate scope and is never overwritten to populate the screen. Use server-wide sorting/target filtering before pagination, first feasible raw ID per exact X, and the selected generation boundary. Main, comparison and expanded views share scope, page and selection. Hamming groups on a page must be explicitly labelled page-local. Preserve raw X/F/G and sensor counts; verify all pages against raw, cross-page map comparison, invalid queries, failed page retry and scope restoration. Tests: tools/all_placements_verify.py, tools/all_placements_browser.cjs, tools/all_placements_common.cjs.

Update the model/function coverage matrix. Check common geometry and execution controls, objective order in confirmed request, fixed versus editable conditions, installed-only layer, compare and expanded selection/sort/filter, scenario and saved-run restoration, input errors and spatial retry. Run the bounded real UI calculation appropriate to the change and compare exported/restored raw identities. Inspect desktop and narrow/zoom-equivalent screenshots; distinguish visual inspection from representative-user/accessibility certification.

Current reusable regression: tools/common_ux_verify.cjs. Bounded UI execution/reload/export: tools/common_ux_execution.cjs. Tests use disposable browser contexts and their own run receipts; never interrupt user calculations.

## Semantic and perceptual regression — 2026-09-14

세대별 비지배 이력은 선택 checkpoint까지의 archive 합집합이며 현재 누적 archive와 별도다. 공통 `history` 조회에서 전체 페이지, 원시 ID, 최초/마지막 비지배 세대, 현재 지배 여부를 제공한다. 저장 목표는 범위 선택 옆에 명시하고 다음 초안과 혼동하지 않는다. 목표 OFF에는 목표 통과 필터를 표시하지 않는다. 근거: `08_검증/ARCHIVE_HISTORY/REVIEW_NOTES.md`.

2026-09-15: 계산 중에는 공통 `generation_population`을 표시하고, 목표/모델 제약 미달을 탐색 개체로 명시한다. 같은 세대 polling에서 지도 전체 재생성과 누적 대표 추출을 하지 않는다. 저장 세대 모집단은 누적 비지배 집합과 구분한다. 기본 `primary100`은 주목적 값별 대표를 먼저 선택하고 같은 값에서 max-min Hamming을 사용한다. 보조 목적은 비교용이며 기존 `performance100`은 별도 선택이다. 근거: `08_검증/LIVE_DIVERSITY/REVIEW_NOTES.md`.

Use `renderReferenceDirections` for every model, displaying actual Das–Dennis count H=C(M+h−1,M−1). Valid UI choices obey the calculator's H<=population guard. Auto mode is an explicit heuristic; copied/saved h is fixed. NSGA-II does not offer this control. Compare selected h with the actual saved solver vectors, not just DOM presence.

Use `sensorVisual`, `sensorMarker`, `sensorRange`, `syncSensorSymbols` and the common legend. Radar is circle/R/solid, RF diamond/F/dashed, EOIR square/E/dotted. Icons stay screen-sized; displaced co-located icons retain a leader to the true site. A preview radius is a comparison at the map centre, never an installation or model coverage assertion.

Use `renderExecutionDetails` for readable snapshot tables and an enlarged detail dialog. Raw JSON is explicit advanced disclosure. Scalar sensor/cost inputs must come from the frozen model configuration and its field schema.

Required evidence adds QG-06-21/22/23: inject incorrect H, identical sensor glyphs, and JSON-only details in a disposable browser and demonstrate rejection. Inspect actual installed and co-located rows at normal/paired/enlarged sizes. Preserve earlier raw, filter, geometry, copy and restoration invariants. DOM count or screenshot existence alone is insufficient. Tests: tools/nsga_visual_verify.cjs, tools/nsga_visual_execution.cjs, tools/nsga_visual_negative.cjs.
# 논문 기반 예산 품질 · 2026-09-16

집합과 선택배치 설명은 `renderSelectedMeaning` 및 `renderCollectionChoices`의 같은 메타데이터/원시 행을 사용한다. 목표 대비 차이는 실제 coverage−저장목표(%p), 성능 순위는 선택 목적 우선 순서이며 모든 목적 최고로 표현하지 않는다. 과거 checkpoint/고정비용/목표OFF/선택없음도 별도 설명한다. 품질센터는 `qualityNavigation`으로 판단·검산·근거 과업을 나누며 원표를 지우지 않고 상세에 보존한다. 목록 필터는 검사 대상을 자동 변경하지 않는다. 검산 실행 전 대상 개수·방법·선택 행 포함을 명시한다. 기능 DOM 존재만으로 이해 가능성을 판정하지 않고 실제 수치와 설명·출처·다음 행동을 함께 확인한다.

해집합 선택은 `renderCollectionChoices`를 공통 사용한다. 저장 목표가 있으면 최초 진입은 목표 통과 최종 비지배 집합이다. 최종 전체·세대별 이력·관측 배치·검산 개선은 별도 선택이며 검산 원시를 optimizer에 합치지 않는다. `collection_counts`는 선택 checkpoint의 정확한 X 중복 제거 집계다. 최종으로 이동하는 버튼에 과거 checkpoint 개수를 붙이지 않는다. 조회 변경 직후 이전 페이지를 비우고 로딩/오류/실제 빈 집합을 구분한다. 늦은 응답은 실행/세대/요청 epoch로 거부한다. 정상·확대 지도와 모델1/2/3에서 동일 적용한다.

품질 보고서는 `renderQualityJourney`로 최종 실행 전체의 판단을 먼저 보여주고 기존 `renderBudgetQuality`의 지표·논문·상세표는 펼쳐보기로 보존한다. `quality_judgment.py`의 실제 공동 목적 비교로 원본을 제외한 반복 빈도와 개선 배치를 계산한다. 원시 재현·성능/탐색·반복·직접 검산은 각각 다른 질문에 답하며 하나의 최적 확률로 합치지 않는다. 검산 기본은 최종 archive 전체이고 선택 행 검산만 화면 세대를 따른다. 개선 비교 지도는 모든 센서·평가영역의 기하를 표시하고 메인 지도 레이어/평가점 설정을 복원한다. 검사: `tools/quality_journey_check.py`, `tools/quality_journey_browser.cjs`, 근거 `08_검증/QUALITY_JOURNEY`.

`quality_research.py`와 `renderBudgetQuality`는 모든 모델의 동일한 품질 계산/표시 경로다. 세대별 고정 척도 HV와 경험적 참조 IGD+는 저장된 hard/G 통과 값만 사용한다. 목표 OFF에서도 표시하며 해당 목표 합격률을 만들지 않는다. 반복 비교는 다른 seed 이외에 동일 조건·예산·평가 계약을 요구한다. 원시 optimizer 결과와 검산 개선 후보는 계속 분리한다. 공통 품질 화면과 검산 창에 같은 보고서를 사용하고 새 모델 전용 복사 UI를 만들지 않는다.
# 공통 절충 분석과 실행 흐름 · 2026-09-17

`workspace-tradeoff.js`가 목적 메타데이터에 따라 모든 구성 모델의 절충 분석과 실행 순서를 표시한다. 저장 목록 조회는 초기 조건 검증과 새 실행 세대 화면을 막지 않는다. 계산 중에는 실제 현재 세대 population을 사용하며 저장 페이지 미수신을 실패로 표시하지 않는다. 평행좌표의 방향·범위·상수 축·선 표본 수, A/B 원단위 차이, 지도 run/row 결속을 검증한다. 상반 목적은 관측 집합의 관계이며 목표 달성·비용과 별도로 설명한다. 가이드 추가 시 작은 화면 지도 높이와 reduced-motion을 검사한다.
# 배치 비교 공통 경로 · 2026-09-17

왼쪽 배치 비교는 기준 A/대안 B 지도의 단일 소유 경로이다. 분석 표 체크 부분집합은 '체크한 배치만 보기'로 구분한다. 전체 목록 폼을 지도 위 고정높이 영역에 넣지 않는다. 공통 `workspace-comparison.js`가 선택·설명·목록창을 연결하며 기존 지도/평가기/저장 행을 사용한다. 변경 검사는 `tools/compare_check.cjs`로 세 모델·작은 화면·확대 지도·실제 체크 동작을 검사한다.
