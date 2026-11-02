# ABC_COVERAGE_RESOURCE_V1 / evaluator 1.0.0

> 중립 예제 수식의 계약입니다. 전체 계산기 어댑터의 계약·소스 지문과 CLI/API는 `docs/FULL_MODEL_API.md`를 따릅니다. 전체 계산기의 선택적 영역 목표는 원시 Model G와 별도 통과 집합으로 저장합니다.

모든 좌표와 반경은 Cartesian m, 비용과 공유 자원은 사용자가 정하는 일관된 상대 단위다. 반경은 XY 수평 거리다. 사이트 지면 z + 센서 mounting height가 LOS 출발 높이이며 평가 지점 z가 도착 높이다.

설치 `x[i,s] ∈ {0,1}`. 거리 범위와 선택적 LOS를 통과하는 상수 `v[i,s,p]`를 계산한다.

- `covered[s,p] = OR_i (x[i,s] AND v[i,s,p])`
- `union[p] = OR_s covered[s,p]`
- `relation[r,p] = AND_{s in r} covered[s,p]`
- `coverage = Σ_p normalized_weight[p] · union[p]`
- `joint_coverage = mean_r Σ_p normalized_weight[p] · relation[r,p]`
- `cost = Σ_i,s x[i,s] · sensor_cost[s] + Σ_i any_s(x[i,s]) · activation_cost[i]`
- `load[i] = Σ_s x[i,s] · resource[s]`

각 관계의 비중은 같다. 관계가 없으면 공동 커버리지는 정의하지 않고 해당 목적/목표를 선택할 수 없다. 연속 면적 대신 명시적인 가중 표본을 사용하며 영역 밖 후보지를 자동 제외하지 않는다.

목적 배열 F는 설정된 objective_ids 순서로 성능은 음수, 비용은 양수다. G 순서는 종류별 최소 재고 위반, 최대 재고 위반, 후보별 용량 위반, 선택적 예산, 선택적 총자원, 설정 순서의 목표 부족분이다. 모든 원소 <=0이 실현가능이다. 금지 설치, 비이진 X, 미선언 센서, 잘못된 차원은 입력 오류로 거절한다. 공동 설치 금지 시 같은 후보지에 2개 이상을 설치할 수 없다.

LOS 장애물은 xyz min/max를 가진 닫힌 solid prism이다. 선분의 면 접촉과 끝점 내부도 차폐다. 음영 전파, 회절, 실제 장비 측정 오차나 탐지확률은 계산하지 않는다. 센서 종류 간 관계는 공동 커버리지에만 영향을 주며 조향 신호나 추정치를 전달하지 않는다.

example_config의 모든 좌표·범위·비용·재고·높이는 새로 만든 합성 예제이며 기존 연구 수치를 계승하지 않는다. 새로운 연구 의미는 model_id/version/contract_id를 분리해 추가한다.
