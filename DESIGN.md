# Design

## Source of truth

- 상태: Draft. 이 문서는 ClaimGraph Web UI의 디자인 source of truth이며, 실제 화면 구현보다 우선한다.
- 마지막 갱신: 2026-08-03
- 주요 제품 표면:
  - 새 조사: 질문·조사 범위·출력 형식·예산을 입력하고 ResearchRun을 시작하는 화면
  - 실행 모니터: ResearchRun, Task, AgentRun의 상태·비용·지연·재시도·승인 대기를 확인하는 화면
  - 보고서: ReportStatement를 중심으로 Claim과 Evidence를 펼쳐 보는 기본 화면
  - 근거 그래프: Claim·Evidence·Source·Entity의 관계를 필터링하고 이웃을 탐색하는 보조 화면
  - Source 상세: 원문 snapshot, 인용 구간, 수집 시각, content hash, 연결된 Claim을 확인하는 화면
  - Review/Human Gate: 검증 결과를 확인하고 승인·수정 요청·거절을 남기는 화면
- 조사한 근거:
  - `README.md`: ClaimGraph를 “출처와 주장 사이의 연결을 투명하게 보여주는 AI 리서치 워크스페이스”로 정의한다.
  - `AGENTS.md`: Claim, Evidence, Source, ResearchRun, Task, AgentRun, Report, Review, Artifact 용어와 API·상태·보안 규칙을 고정한다.
  - `apps/web/app/layout.tsx`, `apps/web/app/page.tsx`, `apps/web/package.json`: Next.js/React 최소 부트스트랩, 한국어 문서 메타데이터, 추가 UI 의존성·토큰·컴포넌트가 아직 없음을 확인했다.
  - `packages/schemas/README.md`, `packages/schemas/claimgraph-contract.schema.json`: ArtifactEnvelope, Report, ReportStatement, Claim, Evidence, Source의 계약과 상태 enum을 확인했다.
  - `packages/schemas/fixtures/*`, `tests/integration/test_contracts.py`, `tests/eval/*`: unsupported Claim, Claim–Evidence 관계, 인용 locator, 재현 가능한 계약·평가 규칙을 확인했다.
  - [ClaimGraph 테크스펙](https://app.notion.com/p/3b0d9f28841281ac8350fcdf586311ad): 보고서 중심 IA, 그래프를 보조 화면으로 두는 원칙, 실행·검증·재현성·Human Gate를 확인했다.
  - [CG-8 Work Item](https://app.notion.com/p/3b0d9f28841281cf8f22c4dc5b5bec7d): 이번 작업은 Web UI 구현이 아니라 디자인 전략과 이 문서 작성으로 한정됨을 확인했다.
- 사실과 결정의 구분:
  - `현재 확인`: 저장소와 테크스펙에 직접 나타난 사실이다.
  - 이 문서의 나머지 항목: 위 사실에서 도출한 MVP 디자인 결정 또는 아직 확정되지 않은 가정이다. 미확정 내용은 `Open questions`에 남긴다.

## Brand

- 제품 약속: 생성된 답변의 그럴듯함보다 “이 문장이 어떤 근거와 관계를 통해 만들어졌는가”를 먼저 확인할 수 있게 한다.
- 성격: 차분함, 엄밀함, 검증 가능성, 복구 가능성, 작업 집중도를 우선한다. 연구 노트와 운영 콘솔의 장점을 결합하되, 감시 도구처럼 위압적이지 않게 한다.
- 신뢰 신호:
  - 모든 보고서 문장에 Claim 연결을 표시하고, Claim에서 Evidence, Source로 이동할 수 있게 한다.
  - Evidence의 짧은 인용·요약과 locator를 Source 원문 및 AI 요약과 구분한다.
  - Claim status, confidence, 지지·반박·조건부 관계, 발행일·수집일을 함께 보여 준다.
  - ResearchRun·Task·AgentRun의 상태와 실패 이유, 입력 hash·모델·prompt/schema 버전 등 재현성 정보를 숨기지 않는다.
  - 검증 실패, 근거 부족, 충돌하는 자료를 성공처럼 보이는 초록색 하나로 치환하지 않는다.
- 피할 것:
  - 질문창만 남기고 출처 연결을 숨기는 챗봇형 블랙박스
  - 그래프를 기본 진입점으로 삼아 사용자가 구조를 먼저 해석하게 하는 화면
  - 근거가 약한 내용을 “확정”, “정답”, “AI가 확인”처럼 표현하는 문구
  - 장식적인 AI 일러스트, 임의 이미지·폰트, 브랜드 로고를 이번 작업의 범위에 추가하는 일
  - 색상만으로 지원·반박·근거 부족을 구분하거나 Source와 생성 요약을 섞는 시각 처리

## Product goals

- 목표:
  1. 보고서 문장에서 시작해 Claim → Evidence → Source 추적을 한 번의 명확한 상호작용으로 제공한다.
  2. unsupported, disputed, 조건부 관계와 검증 실패를 숨기지 않고 다음 판단에 필요한 맥락과 함께 표시한다.
  3. 새 조사부터 실행 모니터, 보고서 검토, Source 원문 확인까지 사용자가 현재 위치와 다음 행동을 잃지 않게 한다.
  4. 실패한 Task만 재실행하고 이전 artifact·오류·실행 맥락은 보존한다.
  5. 보고서의 신뢰도를 시각적 확신이 아니라 근거의 연결성, 상태, locator, 수집 시각으로 판단하게 한다.
- 비목표:
  - 모든 주제에서 완전한 사실성을 보장하거나 전문가 검토를 대체하는 것
  - 범용 검색 엔진, 일반 대화형 챗봇, 고위험 의료·법률·금융 결론의 자동 확정
  - MVP에서의 대규모 실시간 크롤링, 팀 실시간 공동 편집, 모바일 앱, 다국어 번역 파이프라인
  - CG-8에서 실제 Web 화면, 디자인 라이브러리, Figma 파일, 로고·일러스트를 구현·제작하는 것
- 제품 성공 신호:
  - 테크스펙의 acceptance gate인 평가 질문 20개, Phase 1 후보 5개, 첫 유효 보고서 80% 이상, 핵심 Claim Evidence 연결률 95% 이상을 UI가 측정 가능하게 지원한다.
  - unsupported Claim이 보고서에서 누락되지 않고 상태와 사유를 인지할 수 있다.
  - Verifier 실패 보고서가 자동으로 completed처럼 보이지 않으며, 사용자가 실패 Task를 식별해 재실행할 수 있다.
  - 사용자가 문장 선택 후 근거를 확인하고 다시 보고서로 돌아오는 흐름이 끊기지 않는다. 이 항목의 정량 목표는 실제 사용성 평가 후 결정한다.

## Personas and jobs

- 1차 페르소나 — AI·기술 리서처:
  - 일: 기술 선택, 비교, 릴리스·호환성 확인을 위해 조사 질문을 만들고 보고서를 작성한다.
  - 해야 할 일: 질문과 범위를 정의하고, 보고서의 핵심 문장이 어떤 Source에 근거하는지 빠르게 검증하며, 충돌하는 근거를 보존한 채 결론의 조건을 설명한다.
  - 맥락: 데스크톱 브라우저에서 긴 보고서를 읽고, 한국어 문장과 영문 제품명·논문·코드 식별자가 섞인 상태로 작업한다.
- 2차 페르소나 — 검토자/도메인 전문가:
  - 일: 발행 전 보고서의 인용 정확성·완전성·과도한 확신을 판단한다.
  - 해야 할 일: disputed Claim의 양쪽 Evidence를 비교하고, unsupported Claim을 승인하지 않거나 수정 요청을 남기고, 승인 판단을 추적 가능하게 한다.
- 3차 페르소나 — 실행 운영자/개발자:
  - 일: ResearchRun의 지연·비용·실패를 진단하고 재현한다.
  - 해야 할 일: 현재 Task와 의존성, retry attempt, error code, 모델·prompt/schema 버전을 확인해 독립 Task를 보존하면서 문제가 있는 노드만 재실행한다.
- 공통 사용 맥락:
  - 긴 작업이 끝나지 않았거나 네트워크가 느린 상태에서도 마지막으로 확인한 결과와 현재 실행 상태를 구분해야 한다.
  - 원문 전체를 읽지 않아도 짧은 Evidence와 locator로 판단을 시작하되, 필요할 때 Source snapshot으로 내려가야 한다.

## Information architecture

- 기본 진입 원칙: 그래프가 아니라 보고서가 첫 화면이다. 사용자는 문장을 읽고, 필요할 때 Claim·Evidence·Source를 펼치며, 더 깊은 관계 탐색이 필요할 때만 그래프로 이동한다.
- 제안하는 주요 탐색 구조(현재 코드는 아직 구현하지 않는다):
  - 새 조사: 질문 입력 → 범위/출처 유형/출력 형식/예산 확인 → ResearchRun 시작
  - 조사 결과: Report 탭(기본) · 실행 모니터 탭 · 근거 그래프 탭 · 검토 탭
  - 보고서 안의 보조 패널: 선택한 ReportStatement의 Claim → Evidence 목록 → Source 요약/원문 이동
  - Source 상세: Source 메타데이터 → Evidence locator/인용 → 연결 Claim/ReportStatement
  - 실행 모니터: ResearchRun 요약 → Task DAG/상태 → AgentRun·artifact·비용·오류 → 실패 Task 재실행
- 제안 route 이름:
  - `/research/new`
  - `/research/:researchRunId/report`
  - `/research/:researchRunId/run`
  - `/research/:researchRunId/graph`
  - `/research/:researchRunId/review`
  - `/sources/:sourceId`
- 콘텐츠 계층:
  1. 현재 ResearchRun의 질문, 결과 상태, 생성 시각, 최신 보고서 버전
  2. Report의 제목·요약·문장 순서
  3. 각 ReportStatement의 Claim status·confidence·관계 요약
  4. Evidence의 짧은 인용/요약·locator·관계 유형·Source 메타데이터
  5. 원문 snapshot과 재현성·실행 메타데이터
- 추적성 계약:

  ```text
  ReportStatement.claim_id
        └── Claim.claim_id
              └── ClaimEvidenceRelation.claim_id/evidence_id
                    └── Evidence.source_id
                          └── Source.source_id + locator/content_hash
  ```

  `ReportStatement → Claim → Evidence → Source`의 각 단계는 현재 ResearchRun snapshot 안에서 유효한 ID로 연결되어야 한다. UI는 연결이 끊긴 문장을 정상적인 근거 문장처럼 표시하지 않고, 누락된 경로와 확인 가능한 상위 artifact를 알려 준다.
- 우선순위가 낮은 항목: 그래프 전체 조감도, 커뮤니티 분석, 직접 edge 편집, 장식적인 실시간 애니메이션. MVP에서는 Claim 중심 이웃과 목록형 대체 보기를 우선한다.

## Design principles

1. **근거가 문장보다 먼저 판단된다.** 보고서 문장의 가독성을 유지하되, Claim status와 Evidence 경로를 항상 발견 가능하게 둔다.
2. **불확실성은 데이터다.** unsupported, disputed, refuted, 조건부 관계, 검토 필요를 삭제·승격하지 않고 각각의 이유와 관계를 보여 준다.
3. **보고서 우선, 그래프는 필요할 때 확장한다.** 대부분의 사용자는 결론을 읽고 특정 근거를 검증하므로 기본 흐름을 읽기→확인→확장으로 설계한다.
4. **실패는 복구 가능한 상태다.** 한 Task의 실패가 독립 Task나 기존 결과를 지우지 않으며, 재시도·복구·검토 행동을 상태와 함께 노출한다.
5. **점진적 공개로 정보 밀도와 집중도를 함께 지킨다.** 질문과 문장에 핵심 정보, 패널·details에 locator와 실행 메타데이터를 둔다.
6. **도메인 용어와 데이터 계약을 UI에 보존한다.** Claim, Evidence, Source, ResearchRun 등의 이름을 임의의 일반 용어로 바꾸지 않고, 필요하면 한국어 설명을 덧붙인다.
7. **색상·모션·시각 효과는 보조 수단이다.** 상태는 텍스트·아이콘·구조로도 읽히고, 모션이 없어도 작업을 완료할 수 있어야 한다.
- 트레이드오프:
  - 추적성을 높이면 보고서가 조밀해진다 → 기본 문장은 읽기 쉽게 유지하고 Evidence는 인라인 확장/보조 패널로 공개한다.
  - 메타데이터를 모두 보여 주면 인지 부하가 커진다 → confidence만 크게 강조하지 않고, model·prompt·hash는 “재현성” details로 묶는다.
  - 자동 갱신은 최신성을 주지만 읽기 위치를 잃게 한다 → 업데이트 알림과 명시적 새로고침/재개를 제공한다.
  - 그래프는 관계를 잘 보여 주지만 초기에 복잡하다 → 기본은 Claim 중심 이웃과 목록형 관계이며, 전체 그래프는 별도 화면으로 둔다.

## Visual language

- 전체 방향: 밝은 중성 캔버스 위에 읽기 중심의 흰색 surface, 차분한 indigo/blue accent, 낮은 대비의 경계선과 의미론적 상태 색을 사용한다. “AI가 말한다”보다 “연결을 검사한다”는 인상을 준다.
- 색상 토큰(구현 시 CSS 변수로 승격하며, 이번 작업에서는 코드로 추가하지 않는다):

  | 의미 | 전경 예시 | 배경 예시 | 사용 규칙 |
  | --- | --- | --- | --- |
  | `canvas` | `#172033` | `#F7F8FA` | 앱 배경과 기본 텍스트 |
  | `surface` | `#172033` | `#FFFFFF` | Report, 카드, 패널 |
  | `border` | `#5D6B82` | `#D9E0EA` | 구획·입력·표 경계 |
  | `accent` | `#FFFFFF` | `#3157D5` | 링크, 주요 버튼, 선택 상태 |
  | `supported` | `#0F766E` | `#CCFBF1` | `supported` 상태. “절대적 진실”이 아니라 연결된 Evidence가 있음을 표시 |
  | `disputed` | `#8A4B00` | `#FFF1D6` | 표시용 상태. `mixed` 또는 supports/refutes 충돌을 보수적으로 표현 |
  | `unsupported` | `#4B5563` | `#F3F4F6` | 근거가 없거나 충분하지 않음을 표시; 숨기지 않음 |
  | `refuted` | `#B42318` | `#FEE4E2` | refutes 관계와 검토가 필요한 반대 근거 |
  | `needs-review` | `#6941C6` | `#F4EBFF` | Verifier/Human Gate 검토 대기 |
  | `focus` | `#155EEF` | — | 키보드 focus ring; 상태 색을 겸하지 않음 |

  상태는 반드시 텍스트와 아이콘/형태를 함께 사용한다. 녹색만으로 성공을 암시하지 않고, `disputed`는 빨간색 오류처럼 처리하지 않으며 양쪽 근거를 펼칠 수 있게 한다.
- 타이포그래피:
  - 외부 폰트 패키지나 다운로드 가능한 폰트를 추가하지 않는다. 시스템 우선 스택을 사용한다: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif`.
  - 한글 본문과 영문 용어가 섞여도 줄 높이·baseline이 무너지지 않게 본문 15–16px, line-height 1.6–1.75를 기준으로 한다.
  - 페이지 제목 28–36px, section heading 20–24px, metadata 13–14px를 기준으로 하되 모바일에서는 한 단계 낮춘다.
  - Claim ID, hash, endpoint, 코드·모델·prompt version은 고정폭 fallback을 쓰고 자동 줄바꿈·복사 동작을 제공한다.
- 간격·레이아웃:
  - 4px base scale, 주요 간격 8/12/16/24/32/48px를 사용한다.
  - 보고서 읽기 열은 넓은 화면에서 약 680–760px, Evidence 패널은 약 360–420px를 목표로 한다.
  - 앱 shell·카드·패널의 radius는 8px를 기본으로 하고, 고도(elevation)는 얇은 border와 매우 약한 shadow로만 구분한다.
  - 긴 보고서에서 heading·Claim status·Evidence link가 시야를 잡아 주며, 화면을 dashboard tile로 쪼개지 않는다.
- 모션:
  - 패널·accordion·toast 전환은 120–180ms의 짧은 opacity/transform만 사용한다.
  - 그래프 자동 배치, 장시간 spinner, 숫자 카운트업으로 실행 진행을 과장하지 않는다.
  - `prefers-reduced-motion: reduce`에서는 전환을 제거하고 상태 변경을 텍스트로 전달한다.
- 이미지·아이콘:
  - 조사 내용을 설명하지 못하는 장식 이미지·일러스트·원격 에셋은 사용하지 않는다.
  - 아이콘은 의미가 명확한 기존 텍스트/기호 또는 추후 선택할 단순 아이콘 세트로 제한하며, 라이브러리 도입은 별도 결정으로 남긴다.
  - Source favicon/외부 이미지는 신뢰 신호로 간주하지 않고 실패·누락 시 레이아웃이 깨지지 않게 한다.

## Components

- 현재 재사용 가능한 UI:
  - `apps/web/app/layout.tsx`의 RootLayout과 한국어 metadata만 존재한다.
  - `apps/web/app/page.tsx`는 `ClaimGraph` 텍스트를 렌더링하는 최소 bootstrap이다.
  - 기존 token, theme, component library, assets, story/screenshot은 저장소에서 확인되지 않았다.
- 제안하는 도메인 컴포넌트:
  - `AppShell`, `WorkspaceNav`, `PageHeader`, `QuestionSummary`
  - `ResearchRunStatus`, `TaskStatusBadge`, `RunTimeline`, `TaskTable`, `RetryAction`
  - `ReportHeader`, `ReportSection`, `ReportStatement`, `ClaimStatusChip`, `ConfidenceSummary`
  - `EvidenceLink`, `EvidencePanel`, `EvidenceCard`, `SourceCard`, `SourceMetadata`, `SourceSnapshot`
  - `RelationLegend`, `ClaimNeighborhood`, `GraphFilters`, `GraphListFallback`
  - `ReviewGate`, `ReviewDecision`, `ExportMenu`, `Notice`, `Toast`, `Skeleton`, `EmptyState`, `ErrorState`
- Variants와 상태:
  - ReportStatement: 기본, 선택됨, 근거 패널 열림, 연결 누락, 읽기 전용
  - ClaimStatusChip: `unsupported`, `supported`, `refuted`, `mixed`, `needs_review`; `disputed`는 `mixed` 또는 충돌하는 관계를 위한 표시 레이블이며 저장 enum으로 새로 만들지 않는다.
  - EvidenceCard: `supports`, `refutes`, `qualifies`, `mentions`; 관계가 없는 Evidence는 고립/검토 필요로 표시한다.
  - SourceCard: 원문 확인 가능, snapshot 누락, 중복 Source, 수집 실패
  - Run/Task: queued, running, retrying, succeeded, failed, cancelled 및 API에서 허용한 ResearchRun 상태
  - ReviewGate: 승인 가능, 수정 요청, 거절, Verifier 실패로 보류
- 소유권:
  - 디자인 토큰은 Web의 단일 토큰 파일이 소유하고, 컴포넌트는 토큰을 직접 재정의하지 않는다.
  - Claim·Evidence·Source 상태와 연결 규칙은 API/공유 schema가 소유한다. Web은 표시·탐색·사용자 상호작용을 담당하며 상태 전이를 결정하지 않는다.
  - 접근성 이름, status label, 관계 legend는 컴포넌트와 함께 테스트 가능한 문자열로 관리한다.

## Accessibility

- 목표 표준: WCAG 2.2 AA를 기본 목표로 삼고, 최초 구현부터 키보드·screen reader·reduced motion을 검토한다.
- 키보드·focus:
  - 모든 링크·버튼·accordion·필터·retry·review action을 Tab 순서로 접근한다.
  - focus ring은 배경과 충분히 대비되는 2px 이상으로 표시하고, 패널/대화상자 open 시 focus를 내부로 이동·복귀한다.
  - hover만으로 Evidence나 tooltip을 노출하지 않는다.
- 대비·가독성:
  - 본문·링크·상태 텍스트는 AA 대비를 만족하고, `supported`/`disputed`/`unsupported`를 색상만으로 구분하지 않는다.
  - 긴 인용은 색상 highlight만 제공하지 않고 `<blockquote>`에 가까운 구조, locator 텍스트, 원문 이동 이름을 함께 둔다.
  - 한글·영문·긴 URL·hash는 겹치지 않게 줄바꿈하고, 텍스트 확대에서 수평 스크롤을 최소화한다.
- 의미론:
  - Report는 heading 순서, statement는 읽을 수 있는 문장 단위, status는 `aria-label`을 포함한 텍스트로 구성한다.
  - Evidence 패널에는 source title, locator, retrieved_at, relation type, content hash를 읽을 순서를 명시한다.
  - 그래프에는 동일 정보를 제공하는 Claim 중심 목록/관계 표를 제공해 canvas 시각화가 없어도 탐색할 수 있게 한다.
- 감각·상태:
  - spinner 외에 현재 Task와 예상되지 않은 지연을 텍스트로 설명한다.
  - `prefers-reduced-motion`을 존중하고, 깜박임·자동 이동·색상 섬광을 사용하지 않는다.
  - status와 오류 문구는 screen reader live region을 과도하게 사용하지 않고, 중요한 완료/실패만 명시적으로 알린다.

## Responsive behavior

- 지원 범위: MVP는 데스크톱 우선이지만 320px 이상 모바일과 768px 이상 태블릿에서 핵심 읽기·근거 확인·재시도·검토를 수행할 수 있어야 한다. 최신 Chrome, Safari, Firefox의 지원 버전은 배포 결정 시 확정한다.
- 기준 breakpoint(구현 시 실제 콘텐츠로 조정):
  - `>= 1200px`: 좌측 nav 약 240px + report 읽기 열 + Evidence 보조 패널. 그래프는 별도 full-width 화면.
  - `768–1199px`: nav 축소/접기, report 중심 + 필요할 때 열리는 Evidence panel. metadata는 details로 묶는다.
  - `< 768px`: 단일 열. Evidence는 inline accordion 또는 bottom sheet, graph는 Claim neighborhood 목록과 필터로 제공한다.
- 적응 규칙:
  - ReportStatement의 문장 폭과 line-height를 지키고, Source/Evidence 카드가 화면을 임의로 밀어내지 않게 한다.
  - Task 표는 핵심 상태를 먼저 보여 주며, 나머지 hash·model·prompt version은 행 확장 또는 수평 스크롤로 제공한다.
  - 모바일에서는 고정된 side panel 대신 back/close가 명확한 overlay 또는 inline expansion을 사용한다.
  - 터치 target은 최소 44×44px로 두고, hover 스타일은 touch action의 전제 조건이 아니다.
  - 긴 URL·인용·상태 설명은 줄바꿈하며, 가로 스크롤은 코드·hash·그래프 목록 등 불가피한 내용에만 제한한다.

## Interaction states

- Loading:
  - 최초 로딩은 구조가 보이는 skeleton으로, 실행 중 갱신은 현재 ResearchRun/Task·마지막 업데이트 시각·재연결 상태로 표현한다.
  - 서버가 제공하지 않은 진행률을 임의로 계산하지 않는다. SSE를 사용할 경우 재연결과 last event ID 이후 재생을 고려한다.
  - 이미 생성된 Report/Evidence는 새 Task가 실행되는 동안 숨기지 않고 “업데이트 중”으로 표시한다.
- Empty:
  - 조사 전: 질문 입력과 조사 범위 결정을 유도한다.
  - Report 없음: 실행 상태와 다음 행동(대기, 실패 Task 보기, 재실행)을 함께 보여 준다.
  - Evidence 없음: Claim을 숨기지 않고 `unsupported` 및 근거 부족 사유를 보여 준다.
  - Graph 관계 없음: “관계가 발견되지 않음”과 Report/Claim 목록으로 돌아가는 경로를 제공한다.
  - Source snapshot 없음: Source metadata와 수집 실패/보존 제한 이유를 분리한다.
- Error:
  - 안정적인 `error_code`와 사용자용 메시지를 구분하며, 비밀값·원문 전체·개인정보를 노출하지 않는다.
  - retry 가능 오류는 해당 Task만 재실행한다. 이전 attempt, 결과, 오류를 지우지 않는다.
  - Verifier 실패 Report는 `completed`로 자동 전환하거나 성공 badge를 부여하지 않고 Review/수정 요청으로 보낸다.
  - API·네트워크 오류에는 마지막 성공 시각, 재시도 action, 다시 읽기 action을 제공한다.
- Success:
  - Report `ready`/`published`를 구분하고, 생성·발행 시각과 최신 버전을 보여 준다.
  - “완료”는 모든 핵심 Claim의 Evidence 경로가 검증되고 허용된 상태 전이를 통과한 경우에만 사용한다.
  - 성공 상태에서도 unsupported/disputed Claim은 보고서 안에 계속 표시한다.
- Disabled:
  - 의존 Task가 끝나지 않았거나 권한·예산·상태 전이 때문에 action을 막는 경우 이유와 재개 조건을 함께 보여 준다.
  - 버튼을 비활성화하는 것보다 가능한 대체 탐색(기존 결과 보기, 실패 상세 보기)을 남긴다.
- Offline/slow network:
  - stale data와 현재 연결 상태를 구분하는 banner를 표시한다.
  - 자동 재시도는 제한하고, 사용자가 마지막 결과를 읽는 흐름을 방해하지 않는다.
  - 전송 중 취소·재시도는 idempotency와 서버 상태를 따르며, Web에서 임의로 상태를 확정하지 않는다.
- 상태 표시 매핑:

  | 계약 값 | UI 표시 | 의미 |
  | --- | --- | --- |
  | `supported` | 근거 있음 | supports 관계가 유효함; 확정적 진실을 의미하지 않음 |
  | `unsupported` | 근거 부족 | Evidence가 없거나 Claim을 충분히 지지하지 않음; 숨기지 않음 |
  | `mixed` | disputed / 서로 다른 근거 | supports·refutes 등 충돌하는 경로를 함께 보임 |
  | `refuted` | 반박됨 | 유효한 refutes 관계가 있음 |
  | `needs_review` | 검토 필요 | Verifier/Human Gate 판단이 남아 있음 |
  | `qualifies` 관계 | 조건부 | Claim 상태 enum이 아니라 조건을 설명하는 Evidence 관계 |
  | `rejected` | 기본 보고서 제외 | 실행/Review 기록에서 조회 가능해야 하며 현재 schema ClaimStatus에는 새 enum으로 추가하지 않음 |

## Content voice

- 어조: 짧고 사실 중심이며, 판단의 범위와 불확실성을 문장 안에 남긴다. 사용자를 가르치거나 AI의 권위를 과시하지 않는다.
- 고정 용어: Claim, Evidence, Source, ResearchRun, Task, AgentRun, Report, Review, Artifact를 도메인 명칭으로 유지한다. 첫 노출에서 “Claim(주장)”, “Evidence(근거)”처럼 설명할 수 있으나 임의의 “답변 카드”로 바꾸지 않는다.
- 상태 라벨:
  - `supported`: “근거 있음”
  - `unsupported`: “근거 부족”
  - `mixed` 또는 충돌하는 supports/refutes: “서로 다른 근거 있음” 또는 “disputed”
  - `refuted`: “반박됨”
  - `needs_review`: “검토 필요”
  - `qualifies`: “조건부 근거”
- 문장 규칙:
  - “사실이다”, “정답이다”, “검증 완료”처럼 근거 범위를 넘어서는 확정형 표현을 피한다.
  - confidence는 진실 확률처럼 단정하지 않고 “이 Claim에 연결된 판단 confidence”로 설명한다.
  - Source 원문과 AI 생성 summary를 헤딩·label·배경으로 분리한다. Summary가 원문 인용처럼 읽히지 않게 한다.
  - unsupported에는 상태만 붙이지 말고 “연결된 Evidence가 없음”, “현재 Evidence가 Claim을 충분히 지지하지 않음” 등 사유를 표시한다.
  - 출처에는 제목, publisher, published_at, retrieved_at, locator를 가능한 한 함께 보여 주며 값이 없으면 “확인되지 않음”으로 표시한다.
- 권장 microcopy:
  - “근거 보기”, “원문에서 확인”, “연결된 Claim 보기”, “반박 근거 2개 보기”, “이 Task만 다시 실행”
  - “이 문장은 Claim `clm_…`에 연결되어 있습니다.”
  - “근거가 충분하지 않아 `unsupported`로 표시합니다.”
  - “Verifier 검토가 끝나기 전에는 Report를 완료로 확정할 수 없습니다.”
- 피할 microcopy: “AI가 확인했습니다”, “100% 신뢰”, “문제 없음”, “자동으로 해결됨”, 근거를 숨긴 “더 보기”만 있는 단정형 카드.

## Implementation constraints

- Web 경계:
  - 현재 `apps/web`은 Next.js 16.2.12 + React 19.2.4 최소 부트스트랩이며, `layout.tsx`와 `page.tsx` 외에 UI 구현이 없다.
  - CG-8에서는 화면 구현, 임의의 UI 의존성, 디자인 라이브러리, 이미지/일러스트, 외부 폰트를 추가하지 않는다.
  - API 호출·응답 타입은 `packages/schemas`의 계약을 기준으로 하고, 도메인 상태 전이·연결 유효성·재시도·예산·종료 조건은 API/Worker가 소유한다.
  - API 경로는 `/v1`로 시작하며 Web은 표시와 상호작용, API client에 집중한다.
- Contract-first UI:
  - `ReportStatement.claim_id`에서 Claim을 찾고, Claim–Evidence relation의 `claim_id/evidence_id`로 Evidence를 찾은 뒤, Evidence의 `source_id`로 Source 상세에 도달한다.
  - `Source` 원문(snapshot)과 Evidence의 짧은 `quote_or_summary`를 같은 카드나 같은 label로 합치지 않는다. full source text는 Evidence에 넣지 않는다.
  - JSON Schema의 `ClaimStatus`(`unsupported`, `supported`, `refuted`, `mixed`, `needs_review`)를 그대로 존중한다. `disputed`, `conditional`, `rejected`는 표시/워크플로 의미를 문서화한 파생 개념이며 저장 enum을 임의로 확장하지 않는다.
  - Claim의 `supported`·`refuted`·`mixed` 표시에는 runtime 관계 검증이 선행되어야 한다. 참조 ID가 없거나 다른 ResearchRun에 속하면 경로 끊김 오류로 표시한다.
  - `Report`의 `ready`·`published`와 `ResearchRun`/Task의 terminal 상태를 혼동하지 않는다. Verifier 실패는 자동 완료가 아니다.
- 재현성·보안:
  - Task와 외부 도구 호출에 기록되는 input hash, model, prompt version, schema version, error code는 실행 상세에서 재현성 metadata로 조회할 수 있어야 한다.
  - 화면·클라이언트 로그에 secret, 개인정보, 원문 전체를 남기지 않는다. 원문 HTML은 sanitize 후 표시한다.
  - 사용자별 ResearchRun/Source 권한, mutation 인증, idempotency key는 API 계약에 위임한다.
- Performance:
  - 첫 화면은 Report summary와 현재 status를 우선 로드하고, Evidence 상세·Source snapshot·전체 그래프는 지연 로드한다.
  - 전체 그래프 응답을 기본으로 요청하지 않고 Claim 중심 이웃 조회와 목록형 fallback을 사용한다.
  - 긴 보고서·Source·Task metadata는 목록 virtualization을 도입하기 전에 측정하며, 새 dependency는 명시적 결정 없이 추가하지 않는다.
- 구현·리뷰 checklist:
  - [ ] ReportStatement → Claim → Evidence → Source를 실제 snapshot ID로 탐색할 수 있다.
  - [ ] unsupported와 disputed/충돌 상태가 텍스트·아이콘·관계 설명과 함께 표시된다.
  - [ ] Source 원문, Evidence 인용/요약, AI summary가 시각적·문구상 분리된다.
  - [ ] loading, empty, error, success, disabled, slow/offline 상태가 화면마다 정의되어 있다.
  - [ ] retry가 실패한 Task만 대상으로 하며 이전 attempt/artifact/error를 보존한다.
  - [ ] Verifier 실패 Report가 완료로 보이지 않는다.
  - [ ] 키보드, focus, screen reader, reduced motion, 색상 외 상태 표현을 확인한다.
  - [ ] 320px 모바일, 768px 태블릿, 1200px 이상 데스크톱에서 한글·영문·긴 ID·긴 인용이 깨지지 않는다.
  - [ ] API contract/integration 테스트와 대표 평가 fixture를 통과하고, 구현 변경 시 desktop/mobile screenshot으로 시각 QA를 남긴다.

## Open questions

- [ ] 첫 배포를 로컬 전용으로 할지 인증이 있는 단일 테넌트 클라우드로 할지 — 담당: 제품 오너/Infra — 영향: 인증 진입점, 공유 링크, 빈 상태, Source 접근 권한.
- [ ] 초기 출력 언어를 한국어로 고정할지 입력 언어를 통과시킬지 — 담당: 제품 오너/Content — 영향: 한글·영문 혼용 규칙, 번역/원문 표시, QA fixture.
- [ ] 첫 검색 범위를 공식 문서·논문·GitHub 중 어디까지 둘지 — 담당: Research/Worker — 영향: Source type 필터, Source 카드 metadata, 신뢰 신호와 empty 상태.
- [ ] Source snapshot의 보존 기간과 삭제 정책 — 담당: Infra/보안 — 영향: Source 상세 재현성, 만료 상태, 저장 비용과 개인정보 고지.
- [ ] 모든 핵심 Claim을 Report 생성 전에 검증할지, 일부를 `needs_review`로 발행할지 — 담당: 제품 오너/Verifier — 영향: Report `ready`/`published` gate와 Review UX.
- [ ] `disputed`와 `conditional`을 schema의 `mixed`/`needs_review` 및 `qualifies` 관계로만 파생 표시할지 — 담당: API/Schema 오너 — 영향: 필터·배지·export 계약과 상태 전이.
- [ ] API 이벤트 갱신을 SSE로 확정할지 polling fallback을 함께 둘지 — 담당: API/Web — 영향: 실행 모니터, 재연결 banner, 배터리·네트워크 비용.
- [ ] 사용자 직접 Claim 수정·edge 편집을 MVP에 허용할지 — 담당: 제품 오너/Review — 영향: 편집 권한, AuditEvent, 원본 artifact와 수정본의 구분.
- [ ] MVP에서 사용할 아이콘 표현과 시각 브랜드 자산을 제공할지 — 담당: Design/Brand — 영향: 아이콘 dependency, 로고 처리, favicon·공유 링크의 일관성.
- [ ] 지원 브라우저 버전과 visual QA 기준 해상도를 확정할지 — 담당: Web — 영향: breakpoint, CSS capability, screenshot matrix와 릴리스 체크리스트.
