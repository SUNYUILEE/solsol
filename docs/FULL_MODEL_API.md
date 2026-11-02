# 교체 가능한 모델 경계

계산기는 배치·초기화·탐색·저장·화면·HTTP 실행을 소유하고 모델은 센서, 허용 설치, 재고/비용/제약, 목적·진단 F/G와 지도 파생값을 제공합니다. 이전 장비 이름을 치환해 물리식을 상속하지 않습니다.

서버 시작: `python -m solsol serve --model-plugin package.module`. 모듈의 `register_models(adapter)`에서 명시적으로 등록합니다. 원본 프로젝트의 모델 소스를 가져오거나 복사하지 않습니다.

`register_model(contract_id, metadata, schema, converter)`는 중립 범위·자원 모델의 새 센서/관계 설정을 canonical CoverageModel 입력으로 변환합니다. metadata에 sensors, metrics(direction/unit), default_objective_ids, coverage_metrics, policies와 실제 capability를 제공합니다. schema에는 defaults와 common/sensors/objectives 폼을 제공합니다. 변환기는 자체 파일에 정의해야 하며 소스 지문에 묶입니다.

`register_compiled_model(contract_id, metadata, schema, builder)`는 일반 평가 계약을 구현한 다른 모델용입니다. builder는 `(cid, config, enabled_sensor_ids, objective_ids, diagnostic_ids)`를 받아 compiled problem을 반환합니다. `space/codec`, candidate/sensor/objective/constraint 순서, config/evaluator/input/problem hashes, service_identity, registry_snapshot, bundle, objective_specs, evaluate_physical, batch, view_problem이 필요합니다. 기존 generic 초기화는 공개 F/G로 제안하고 재평가하므로 모델 전용 초기화가 필수는 아닙니다.

중립 예제의 정확 Boolean formulation·sensor support는 그 모델에서만 제공합니다. 일반 builder에 지원 없는 capability를 자동 생성하지 않고 명시적 UNSUPPORTED로 거절합니다. 모델별 특수 기능은 실제 제공 시에만 메타데이터로 노출하세요. 외부 서비스 연결에는 원본의 버전 고정 HTTP transport `remote_model_client.py`를 보존했습니다. 실제 서비스 URL·버전·설정은 사용자가 명시해야 하며 기본값으로 과거 모델을 연결하지 않습니다.

서버 실행 전 모델을 등록하고 연구 도중 catalog/evaluator 파일을 수정하지 마세요. 모델 소스 지문이 바뀌면 재시작하고 새 실행으로 분리합니다. 다중 파일 플러그인은 평가 의존성을 명시적으로 고정한 자체 builder hash/서비스 버전이 필요합니다. 아직 임의 외부 모델의 과학적 타당성이 검증된 것은 아닙니다.
