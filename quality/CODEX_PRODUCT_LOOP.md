# Codex 제품 품질·UI 고도화 루프 및 설치 지시

문서 ID: CPL-002  
버전: 2.0.1  
목적: 연구 무결성을 보존하면서 문서형 시제품을 상용 제품형 작업공간으로 고도화한다.

기존 품질기준 1.0 프로젝트에 처음 통합할 때는 이 문서만 단독 적용하지 말고 `APPLY_QUALITY_2_0_TO_EXISTING_PROJECT.md`의 호환성 감사와 gate 적용 profile을 먼저 적용한다. 이는 최종 품질기준을 완화하는 규칙이 아니라 연구 반복과 제품 전체 exit 판정의 실행 시점을 분리하는 adapter다.

## 1. 핵심 명령

Codex는 과거 PDF의 화면 배치를 복제하지 않는다. PDF와 기존 UI에서 목적함수, 실행 계보, 결과 의미, 검산 계약만 추출하고 화면 구조는 최신 연구 내용·사용자 과업·참조 디자인을 바탕으로 다시 설계한다.

기능을 모두 넣었다는 사실은 UI 완료 증거가 아니다. 내부 구성요소 목록을 카드와 섹션으로 옮기는 방식은 금지한다.

## 2. 설치 위치

기존 운영체계를 먼저 읽고 동등한 위치가 없을 때만 다음을 사용한다.

```text
<repository-root>/
  governance/quality/
    PRODUCT_QUALITY_STANDARD.md
    QUALITY_GATES.yaml
    CODEX_PRODUCT_LOOP.md
    QUALITY_REPORT.schema.json
  quality-reports/
  design-evidence/
    UI_REFERENCE_BRIEF.md
    screenshots/
    prototypes/
    usability/
```

기존 파일과 디렉터리를 임의로 삭제·이름 변경·덮어쓰지 않는다.

## 3. Codex 창에 전달할 설치·재설계 지시문

```text
첨부한 품질 패키지 4개는 버전 2.0.1이다. 먼저 AGENTS.md와 기존 운영체계, 최신 연구 상태, 결정·변경·실험 기록을 읽고 기존 구조를 보존한 채 통합하라.

이전 PDF와 현재 UI는 기능·연구 의미의 근거이지 디자인 청사진이 아니다. 긴 단일 페이지와 구성요소 나열 구조를 유지하지 마라. 최신 승인 연구내용을 먼저 추출하고, 현재 UI의 전체 screenshot과 문제를 기록한 뒤, 공식 디자인 시스템과 실제 엔터프라이즈·과학·지도 분석 제품을 웹에서 최신 조사하라. 최소 6개 참조를 URL·조사일·채택/비채택 패턴과 함께 design-evidence/UI_REFERENCE_BRIEF.md에 기록하라.

사용자 과업 기준으로 실행 대시보드, 실험 설정, 실행 모니터, 해 탐색 작업공간, 비교·근거, 방법·가정 도움말의 정보구조를 검토하라. 최소 2개 구조 대안을 만들고 비교한 뒤 근거 있는 하나를 선택하라. 지도·Pareto plot·선택 해 inspector를 중심 작업공간으로 두고, 장문 설명과 고급 설정은 문맥 패널·drawer·도움말로 단계적으로 공개하라. 연구요소가 추가될 때마다 새 카드와 새 메뉴를 붙이지 말고 schema/metadata 기반 목록·필터·열 구성·상세 패널로 흡수하라.

실제 UI를 구현하고 브라우저에서 1920x1080, 1440x900, 1280x720 화면을 직접 캡처하여 검토하라. mockup이나 정적 placeholder를 실제 기능처럼 제출하지 마라. 핵심 과업을 실제 데이터로 검증하고 접근성·시각 회귀·사용성 증거를 남겨라.

개발 중에는 품질 미충족을 기록하며 계속 작업할 수 있다. 그러나 완료·출시급·상용 수준을 선언할 때는 QUALITY_GATES.yaml을 전부 실행하고 QUALITY_REPORT.schema.json을 만족하는 보고서를 생성하라. QG-06이 PASS하지 않으면 기능이 모두 있어도 출시급으로 선언하지 마라.

설치 후 실제 경로, 기존 구조와의 통합 방식, 1.0→2.0 변경 영향, 네 파일의 해시, UI_REFERENCE_BRIEF 생성 위치, 현재 QG-06 미통과 항목을 보고하라. 설치만으로 제품이 통과했다고 판정하지 마라.
```

## 4. UI 작업 시작 전 조사 루프

### 4.1 최신 연구 상태 읽기

다음 순서로 읽는다.

1. AGENTS.md와 저장소 지침
2. 최신 current state/checkpoint
3. 승인된 모델·목적·제약·센서·데이터 계약
4. 결정·변경·미해결 기록
5. 현재 코드와 실행 가능한 UI
6. 과거 PDF와 사용자 제공 참조 이미지

최신 연구 상태와 PDF가 다르면 최신 승인 기록을 기준으로 하고 차이를 남긴다.

### 4.2 현재 UI 진단

실제 프로그램을 실행하고 주요 경로를 캡처한다.

- 첫 실행/저장 실행 없음
- 저장 실행 목록
- 실험 설정 및 변경 미리보기
- 실행 중/중단/실패/완료
- 해 미선택/선택
- 세대 이동
- 비교·근거 다운로드
- 좁은 화면과 200% 확대

각 화면에 대해 `사용자 질문`, `주 행동`, `핵심 데이터`, `불필요한 상시 노출`, `오해 위험`, `재설계 기회`를 기록한다.

### 4.3 최신 참조 검색

중대한 UI 작업마다 인터넷 검색을 새로 수행한다. 공식 제품 문서·공식 디자인 시스템·실제 제품 화면을 우선한다.

검색 범주:

- enterprise application shell/navigation
- scientific experiment dashboard
- multi-objective optimization visualization
- geospatial analysis workspace
- linked chart/map selection
- accessible complex data visualization
- dense data table and compare workflow

최소 6개 참조를 수집하고 90일 이내 조사 여부를 기록한다. 블로그 이미지 하나를 전체 디자인 근거로 삼지 않는다. 라이선스가 불명확한 시각 자산을 복제하지 않는다.

### 4.4 UI_REFERENCE_BRIEF 필수 내용

```markdown
# UI Reference Brief

## 대상 revision과 조사일
## 최신 연구 콘텐츠 인벤토리
## 사용자 역할과 핵심 과업 5개
## 현재 화면 inventory와 문제
## 외부 참조 6개 이상
## 채택할 패턴 / 채택하지 않을 패턴
## 정보구조 대안 A
## 정보구조 대안 B
## 선택 방향과 근거
## 화면별 핵심 질문·주 행동·데이터
## 디자인 토큰 방향
## 접근성·반응형 전략
## 검증 계획
```

## 5. 설계 루프

### 5.1 구성요소가 아니라 과업으로 시작

잘못된 접근:

```text
입력 카드 + 지도 카드 + 표 카드 + 설명 카드 + 그래프 카드 + 다운로드 카드
```

올바른 접근:

```text
사용자가 새 실험을 만든다
→ 진행 상태를 감시한다
→ 해를 직접 탐색한다
→ 2~4개 해/실행을 비교한다
→ 근거를 검증·내보낸다
```

### 5.2 최소 2개 구조 대안

색상만 다른 두 시안은 대안이 아니다. navigation, screen split, primary canvas, inspector, compare flow가 실제로 달라야 한다. 다음 기준으로 비교한다.

- 핵심 과업 이동 수
- 첫 viewport의 명확성
- 지도/plot 작업공간 크기
- 연구 설명의 단계적 공개
- 새 센서·목적·제약 확장성
- 접근성과 좁은 화면 대응
- 구현 복잡도와 기존 코드 영향

### 5.3 권장 기본 구조

```text
App shell
├─ 실행
│  ├─ 실행 대시보드
│  └─ 새 실험 / 실험 편집
├─ 분석
│  ├─ 실행 모니터
│  ├─ 해 탐색
│  └─ 비교·근거
└─ 방법·가정
```

메뉴 명칭은 사용자 언어를 사용한다. `Evaluator`, `ArchiveManager`, `MILPSeeder` 같은 내부 모듈명을 전역 메뉴로 노출하지 않는다.

### 5.4 디자인 토큰과 component contract

구현 전에 최소 토큰을 정의한다.

- semantic colors와 data palette
- typography scale
- 4/8px 기반 spacing scale
- border/radius/elevation
- icon family와 크기
- control height와 table density
- motion duration/easing
- viewport breakpoints

component는 loading, empty, error, disabled, selected, focus 상태를 포함한다.

## 6. 구현 루프

1. 앱 셸과 라우팅/상태 경계를 먼저 만든다.
2. mock data가 아닌 기존 실제 data contract에 연결한다.
3. 화면마다 가장 중요한 end-to-end 과업 하나를 먼저 완성한다.
4. 실제 browser screenshot을 보고 밀도·정렬·hierarchy를 수정한다.
5. 목록-plot-지도-inspector 선택 동기화를 검증한다.
6. 장문 설명과 고급 설정을 기본 화면에서 제거하되 접근 가능하게 유지한다.
7. 연구 의미와 계보가 UI 변화로 훼손되지 않았는지 검사한다.
8. 새 연구 요소는 공통 metadata renderer와 필터/열 구성으로 흡수한다.

Codex는 코드만 보고 디자인을 완료로 판단하지 않는다. 매 의미 있는 UI 변경 후 실제 화면을 열어 캡처하고 시각적으로 검사한다.

## 7. 필수 핵심 과업

최소 다음 5개 과업을 실제 데이터로 검증한다.

1. 저장 실행을 찾아 열고 해당 실행 조건을 확인한다.
2. 기존 결과를 바꾸지 않고 다음 실행 조건을 변경·검증·실행한다.
3. 실행 진행·NFE·시간을 확인하고 안전하게 중단 또는 완료한다.
4. 세대와 해를 직접 선택해 지도·plot·표·inspector의 동일 ID를 확인한다.
5. 두 개 이상의 해/실행을 비교하고 원시 결과와 검증 근거를 내보낸다.

보조 과업:

- infeasible/실패/부분 저장 상태 이해
- LP/MILP/Greedy 근거와 한계 확인
- 500m 결과와 250m 검산 구분
- 키보드로 해 선택과 필터 수행

## 8. 사용성·시각 검증 루프

### 8.1 실제 화면 검토

각 주요 화면을 1920×1080, 1440×900, 1280×720, 200% 확대에서 캡처한다. 다음을 확인한다.

- 제목·현재 상태·주 행동·핵심 결과가 첫 viewport에 있는가
- 핵심 캔버스가 설명문과 설정에 밀리지 않는가
- 간격, baseline, border, radius, icon이 일관적인가
- 표·그래프·지도 label이 잘리거나 겹치지 않는가
- empty/loading/error 상태가 의도적으로 설계되었는가
- card nesting과 불필요한 container가 없는가

### 8.2 사용자 과업 평가

대표 사용자 5명 이상을 우선한다. 각 과업에 성공/실패, 시간, 치명 오류, 도움 요청, 혼동 지점을 기록한다. 핵심 과업 성공률 90% 미만 또는 치명 오조작이 있으면 QG-06은 FAIL이다.

실제 사용자 평가가 불가능하면 다음 모두가 필요하다.

- 전문 휴리스틱 검토
- 사용자 또는 책임자의 대체 평가 승인
- 미검증 위험의 명시

이 대체 경로를 사용한 결과를 일반 사용자 검증 완료라고 표현하지 않는다.

### 8.3 접근성

- WCAG 2.2 AA 자동 검사
- 키보드와 focus order 수동 검사
- color-only 의미 금지
- chart/map 요약과 구조화된 대체 데이터
- 200% 확대와 reflow
- screen reader용 이름·역할·상태

## 9. 완료 판정 루프

PRODUCT_EXIT인 경우에만 다음 전체 판정을 수행한다. CONTINUOUS_RESEARCH는 연구 무결성 관련 check만, CHANGE_INTEGRATION은 변경 영향 check만 실행하고 나머지를 실패로 만들지 않는다.

1. 판정 대상 commit/배포물과 hash를 고정한다.
2. QUALITY_GATES.yaml QG-00~QG-12를 실행한다.
3. `design_evidence`를 포함한 품질 보고서를 생성한다.
4. QUALITY_REPORT.schema.json Draft 2020-12 검증을 실행한다.
5. 필수 gate의 FAIL/NOT_RUN/BLOCKED와 미해결 BLOCKER/MAJOR를 확인한다.
6. 최종 배포물에서 설치·핵심 과업·다운로드·screenshot을 다시 검증한다.

판정:

```text
schema invalid → FAIL
required FAIL/NOT_RUN/BLOCKED 존재 → FAIL
QG-06 FAIL 또는 UI design evidence 부족 → FAIL
미해결 BLOCKER/MAJOR 존재 → FAIL
그 외 모든 필수 gate PASS/승인된 N/A → PASS
```

## 10. 변경 영향별 최소 재실행

| 변경 | 최소 게이트 |
|---|---|
| 문구·도움말 | QG-06, QG-10, QG-11, QG-12 |
| navigation·layout·상태 표시 | QG-01, QG-03, QG-06, QG-11, QG-12 |
| plot·지도·선택 연결 | QG-01, QG-03, QG-04, QG-06, QG-11, QG-12 |
| 목적·제약·수선·알고리즘 | QG-01, QG-02, QG-03, QG-04, QG-06, QG-08, QG-11, QG-12 |
| 저장·복구·export | QG-01, QG-03, QG-05, QG-07, QG-09, QG-11, QG-12 |
| 배포 패키지 | QG-07, QG-09, QG-10, QG-12 |

QG-00과 QG-12는 모든 완료 판정에서 실행한다. 중대한 UI 변경이면 QG-06 전체를 실행한다.

## 11. Codex 최종 보고 형식

### 통과

```text
대상 <revision>은 제품 품질 exit gate를 통과했습니다.
보고서: <path>
UI 근거: <UI_REFERENCE_BRIEF, prototype, screenshot, usability 경로>
판정: PASS
검증한 핵심 과업: <목록>
알려진 한계: <목록>
```

### 미통과

```text
기능 구현은 진행되었지만 제품 완료 판정은 FAIL입니다.
보고서: <path>
미통과 gate/check: <목록>
UI 상태: <문서형/과밀/참조조사 미완료/실사용 검증 미완료 등>
필요 조치: <구체적 작업>
따라서 출시급 또는 상용 수준으로 선언하지 않습니다.
```

## 12. 설치 검증

- [ ] 네 파일이 2.0.1로 설치되었다.
- [ ] 기존 운영·연구기록을 보존했다.
- [ ] `design-evidence/` 위치가 정해졌다.
- [ ] YAML과 JSON Schema가 parser 검증을 통과했다.
- [ ] 기존 보고서 1.0과 2.0의 schema version을 구분한다.
- [ ] UI_REFERENCE_BRIEF를 만들지 않은 상태를 PASS로 표시하지 않았다.
- [ ] 기존 PDF 레이아웃을 디자인 기준으로 고정하지 않았다.

