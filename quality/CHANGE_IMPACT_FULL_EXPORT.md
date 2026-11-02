# 전체 계산기 이식의 품질 영향

적용 profile: CHANGE_INTEGRATION. 원본 품질 표준·보고서 스키마와 120개 세부 gate 식별자를 보존합니다. 과거 R06 supplement는 기준 문서의 이력이며 현재 모델의 PASS 근거가 아닙니다.

변경 범위는 공통 엔진 재사용, 중립 모델 경계, 전체 UI 연결, HTTP 셸·공개 클라이언트, 패키지와 업로드 하네스입니다. 원본 엔진의 unsigned 설치 검산과 compact checkpoint JSON 직렬화 문제는 새 복사본에서 교정하고 회귀 사례를 추가했습니다. 원본 파일은 수정하지 않습니다.

필수 확인은 원시 X/F/G 재생·순서·config/evaluator/contract 결속, 누적 경험적 archive, 준비/탐색 평가 분리, 모델 교체·저장 복원, 실제 브라우저 설정→계산→지도→검산→복원, API 제출/취소/다중 seed/내보내기, 원시·사후 진단 분리입니다. 상세 실행 결과는 docs/evidence/full과 docs/migration/capability-map.json에서 연결합니다.

PRODUCT_EXIT, 현장 신뢰성, 센서 물리 검증, 독립 대규모 reference, 사람 사용성은 새 예제에 수행되지 않았습니다. 자동 기능 회귀 PASS를 이러한 품질의 PASS로 바꾸지 않습니다. 새 모델/실험별 gate 적용과 독립 검증은 계속 누적합니다. 모든 세부 gate는 QUALITY_GATES.yaml 원문을 유지하고, 해당 실험의 실제 근거와 적용 여부를 따로 작성합니다.
