# 다른 연구 모델 연결

> 0.1의 모델 수식 회귀용 경계입니다. 현재 전체 프로그램의 모델 연결은 `docs/FULL_MODEL_API.md`, 공개 앱·AI 호출은 `docs/FULL_API.md`를 사용합니다.

계산기 경계는 `solsol.engine.contracts.EvaluationModel`입니다. 새 모델 클래스는 계약 ID, 모델/평가기 버전, immutable 입력의 복사본, `PlacementSpace`, 공개 재고 규칙, 순서가 고정된 목적/제약 ID와 `evaluate(X)`를 제공합니다. 기존 모델 프로젝트나 외부 소스는 import하지 않습니다.

```python
from solsol.engine.runtime import run_experiment, replay
from solsol.engine.storage import RunStore
from my_research.model import MyModel

model = MyModel(config)
result = run_experiment(model, {
    'algorithm': 'NSGA-II', 'initializer': 'random',
    'seed': 7, 'population': 48, 'generations': 30,
})
check = replay(result, model_factory=MyModel)
assert check['status'] == 'PASS'
RunStore('runs/my-model').save(result)
```

`space`: `PlacementSpace(candidate_order, sensor_order, dataset_id, allowed, co_location)`.
`inventory_rule`: `{'mode':'partial','lower':[...],'upper':[...]}`.

평가 결과는 `X`, 최소화 방향 `F`, `G<=0`, `cost`, `counts`, `named_metrics`, `placement_hash`, `experiment_contract_id`, `feasible`를 제공합니다. 현재 공통 요약/지도 UI는 추가로 `coverage`, `joint_coverage`, `covered_points`, `covered_by_sensor`, `site_loads`, `blocked_links`를 사용합니다. 이 항목은 새 모델의 의미에 맞는 명시적 어댑터를 작성해야 하며 없는 성능을 만들어 넣으면 안 됩니다. Greedy는 선택된 성능 목적과 공개 평가를 사용하며 MILP는 F/G 단일 변화의 국소 근사를 제안합니다.

현재 CLI/HTTP 화면에 등록된 모델은 새 커버리지 예제 하나입니다. 다른 모델은 위 Python 인터페이스로 실행할 수 있습니다. 화면까지 연결하려면 `server.py`의 모델 생성 경계를 registry/factory로 확장하고 폼·지도 어댑터를 추가하세요. 기존 예제 schema에 다른 의미의 수식을 몰래 넣지 말고 새 model_id와 evaluator_version을 부여합니다.

직접 외부 패키지로 작성한 모델의 소스는 계산기 코드 지문에 자동 포함되지 않습니다. 이 경우 `contract_id`에 외부 평가기 소스/패키지 digest를 반드시 포함하고 외부 버전을 따로 보관해야 합니다. 원격 모델은 이 프로토콜의 HTTP 어댑터로 연결할 수 있지만 이 버전에 원격 서버 인증·배포 기능은 포함하지 않았습니다.
