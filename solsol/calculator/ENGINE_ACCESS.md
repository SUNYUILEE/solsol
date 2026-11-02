# 전체 계산기 접근

현재 실행은 저장소 루트에서 `python -m solsol serve`입니다. 기본 URL은 `http://127.0.0.1:8877`, 저장은 `data/full-calculator`입니다. 원본 작업공간이나 별도 과거 모델 프로젝트를 참조하지 않습니다.

Python: `from solsol.calculator.client import EngineClient`. 명령줄: `python -m solsol.calculator.engine_client --contract ABC_COVERAGE_RESOURCE_V1 --url http://127.0.0.1:8877 registry`.

브라우저·앱·AI는 같은 HTTP 서비스에 구성 검증, 실행, 취소, 상태, 저장 조회, 품질 진단, 반복 연구, 내보내기를 요청합니다. 클라이언트가 별도 최적화기를 실행하지 않습니다. `/api/openapi.json`과 `engine/registry`에서 계약을 확인합니다.

일반 실행은 `engine/validate`의 확정 입력 SHA와 request ID를 `engine/runs`에 전달합니다. `submit_configuration`이 이를 처리합니다. 응답이 불확실하면 같은 request ID로 조회합니다. 설정·평가기·계약·후보/센서 순서가 달라진 결과를 같은 실험으로 합치지 않습니다.

외부 모델은 명시적인 플러그인 또는 보존한 remote_model_client로 연결합니다. 기본 모델은 중립 A/B/C 예제이며 원래 장비 모델을 등록하지 않습니다. 자세한 실행 예제와 모델 경계는 루트 README와 docs/FULL_API.md, docs/FULL_MODEL_API.md에 있습니다.
