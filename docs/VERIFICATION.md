# 검증 인덱스

> 0.1 축소 구현의 과거 기록입니다. 현재 전체 계산기 검증은 `08_검증/PROGRAM_QUALITY_INDEX.md`와 `docs/evidence/full/`을 사용합니다. 이 문서의 과거 PASS를 전체 이식 완료 근거로 사용하지 않습니다.

범위는 새 중립 계산기 연구 기반의 추출·구현·재현·업로드다. 원본 전체 제품의 출시급 승인이나 과거 연구의 과학적 승격이 아니다.

| 근거 | 내용 |
| --- | --- |
| [자동검사 원문](evidence/pytest.txt) | 해석적 커버리지·관계·공유비용·자원 제약, 입력 거절, LOS, 초기화/solver 조합, seed 재현, archive, 전량 재생, 저장 오염·불변성, HTTP, 극단 가중치·목적 순서·lifecycle 반례 |
| [브라우저 검사](evidence/browser.json) | 실제 Edge의 조건 변경→계산→저장→다운로드→새 서버 프로세스 복원→전체 재생, 중지. 레이어·세대·정렬·Hamming은 smoke 상호작용이며 exhaustive UI 검사는 아님 |
| [원본 보존](evidence/source-preservation.json) | 사전 고정한 원본 텍스트/소스 파일 SHA와 Git 작업 상태의 동일성. 대형 원시/수입/실행 데이터 트리는 범위에서 제외 |
| [종합 자동검증](evidence/verification.json) | 검사 수, 실행 환경, wheel 설치 후 실제 계산·재생, 출판 파일 검사와 한계 |
| [독립 검토](evidence/independent-review.json) | 구현자와 별도 검토자가 확인한 대상 파일 지문, 발견사항과 교정 상태 |
| [추출 계보](../MIGRATION_MANIFEST.json) | 원본/대상 바이트 지문, 전체 추출·함수 추출·설계 참조의 구분 |

독립 tiny oracle는 2후보 × 2종류의 모든 16배치를 손계산 식과 비교한다. 정확한 비지배 집합 6개를 별도로 고정하며, 탐색이 이 6개를 전부 발견했다고 가정하지 않는다. 동일한 작은 문제에서 NSGA-II/III × 무작위/Greedy/MILP를 seed 고정해 비교하고 매 raw 행을 독립 식과 대조한다.

1920×1080, 1440×900, 1280×720의 실제 브라우저 screenshot을 같은 폴더에 보관한다. 화면 검사는 자동 상호작용과 시각 검토이며 실제 사람의 이해도/사용성은 NOT_MEASURED다. 실제 현장 성능과 전역 최적성도 인증하지 않는다. Linux/Python 버전별 GitHub Actions는 설정했으며 원격 실행 여부는 GitHub에서 따로 확인한다.
