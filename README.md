# SOLSOL — 모델을 교체하는 센서 배치 연구 계산기

원본의 **공통 계산 엔진, 전체 작업 화면, 설정·지도·해집합 분석, 검산·연구 기능, 품질 기준과 증거 구조**를 옮긴 독립 프로젝트입니다. A/B/C 예제는 범위·공동 커버 관계·비용·재고·공유 자원·LOS를 조절합니다. 이전 장비의 오차·각도·조향·융합 모델과 수치결과는 가져오지 않습니다. 원본 디렉터리를 수정하거나 실행 중 참조하지 않습니다.

이전 0.1의 작은 계산기 대체 구현은 전체 추출 요건을 충족하지 못했습니다. 현재 실행 진입점은 `solsol/calculator/`의 기존 전체 계산기입니다. `solsol/engine`, `solsol/server.py`, `solsol/web`의 0.1 코드는 이력·수식 회귀용이며 현재 UI나 CLI 실행 엔진으로 사용하지 않습니다. 과거 검증 보고서를 새 전체 이식의 PASS로 상속하지 않습니다.

## 설치와 실행

Python 3.11 이상, Windows PowerShell:

```powershell
git clone https://github.com/SUNYUILEE/solsol.git
cd solsol
py -3 -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m solsol serve
```

[연구 계산기 열기](http://127.0.0.1:8877). `START.cmd`도 같은 프로그램을 실행합니다. 저장 위치는 `data/full-calculator`이며 `serve --data-dir PATH`로 바꿀 수 있습니다. Linux/macOS에서는 `.venv/bin/python`을 사용합니다.

## 연구 흐름

1. 공통 영역·후보지·평가 간격, 모델의 센서·목적·관계·LOS, 수량·예산·단가를 설정합니다. 설정 전후 지도와 시나리오 저장을 사용합니다.
2. NSGA-II/III, 무작위·Greedy·국소 MILP·저장 초기해, seed·개체 수·세대·참조방향을 선택합니다. 준비 평가와 탐색 NFE는 분리합니다.
3. 실행·중지·상태·세대 재생, 전체 관측·누적 경험적 비지배 집합·목표 통과 집합을 확인합니다. 정렬·필터·Hamming 대표해·기본/확대/비교 지도를 사용합니다.
4. 해품질·탐색 품질·검산 센터에서 원시 재생, 삭제·이동·국소 MILP·전수·개선 검사를 실행하고 중지·재개·내보내기합니다. 사후 진단 해는 optimizer 원시 해에 합치지 않습니다.
5. 반복 seed 검증, 자원·반경·예산 연구, 실행 비교, 고정 기준의 집합/탐색 품질과 reference를 축적합니다. 실행 입력·코드·X/F/G·seed·NFE·세대·지도·진단의 결속을 보존합니다.

## 다른 앱·AI에서 호출

브라우저와 Python 클라이언트는 **같은 서버·동일 저장소·동일 실행 서비스**를 사용합니다. 서버를 시작한 뒤:

```powershell
python -m solsol example --output request.json
python -m solsol run --config request.json
python -m solsol list
python -m solsol replay RUN_UUID
python -m solsol audit RUN_UUID
python -m solsol.calculator.engine_client --contract ABC_COVERAGE_RESOURCE_V1 registry
```

`request.json`의 optimizer/model_config를 바꿔 연구합니다. CLI `replay`는 서버의 저장 결과·재생 상태를 조회합니다. 새 독립 검산은 `audit` 또는 quality API로 요청합니다. 자동 POST 재시도는 하지 않으며 request ID로 불확실한 제출을 복구합니다.

[HTTP·Python API 사용법](docs/FULL_API.md), [모델 연결 계약](docs/FULL_MODEL_API.md), [계산기 접근 안내](solsol/calculator/ENGINE_ACCESS.md)를 참고하세요. `/api/openapi.json`과 등록 모델 메타데이터를 조회할 수 있습니다.

## 보존 범위·품질·검증

| 위치 | 역할 |
| --- | --- |
| `solsol/calculator/engine` | 원본 공통 실행·archive·저장·진단·검증·비교·연구 서비스 |
| `solsol/calculator/web` | 원본 전체 작업 화면과 중립 모델 연결 |
| `solsol/calculator/model_service_client.py` | 새 모델 등록·버전·입출력·평가 경계 |
| `solsol/calculator/remote_model_client.py` | 보존한 외부 Model HTTP 전송 클라이언트 |
| `quality` | 원본 품질 표준·상세 gate·보고서 스키마 |
| `docs/migration` | 원본 파일/함수/컨트롤 목록과 기능별 이식·제외 근거 |
| `docs/evidence/full` | 전체 계산기에서 새로 실행한 검사와 브라우저 증거 |
| `.agents/skills/solsol-calculator-export` | 전체 기능 대조와 업로드 차단 하네스 skill |

`research_ops.py`와 `00_research_ops/`에는 작업 등록·원문 고정·사전 점검·실패·근거·인계 하네스가 있습니다. `01_목표`–`13_설명문서`는 새 연구용 빈 기록 구조입니다. `doctor`와 `system-audit`로 구조를 확인한 뒤 task를 등록하고 acknowledge/preflight/run으로 실행합니다. 과거 작업·승인·원시 연구 기록은 이 새 프로젝트에 상속하지 않습니다.

[전체 이식 계획](docs/FULL_FIDELITY_PLAN.md)을 기준으로 검사합니다. 추출한 파일 수나 작은 예제의 테스트 PASS를 전체 기능 완료로 해석하지 않습니다. 확인되지 않은 항목은 `NOT_RUN`/`BLOCKED`로 남기며 [이식 판정](docs/migration/parity-report.json)과 독립 검토를 확인해야 합니다.

```powershell
python -m pytest -q -p no:cacheprovider
python tools/full_browser_workflows.py
python tools/calculator_export.py check --inventory docs/migration/source-inventory.json --mapping docs/migration/capability-map.json --target . --output docs/migration/parity-report.json
```

예제의 공동 커버는 공간 관계입니다. LOS는 명시 3D 직육면체와 선분의 교차이며 접촉도 차폐합니다. 커버율은 이산 평가점의 가중 비율입니다. 실제 장비 성능·통신 연동·측정 오차·현장 신뢰성·연속 면적 적분·전역 최적성·사람 사용성은 인증하지 않습니다. 원시 검산 PASS, 집합 지표, 탐색 안정성과 독립 과학 검증을 구분합니다.
