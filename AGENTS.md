# AGENTS.md

이 파일은 저장소 전체에 적용된다.

## 기본 원칙

- MVP는 단순하게 유지한다. 기존 패턴과 코드를 먼저 재사용하고, 새 추상화·의존성은 필요할 때만 추가한다.
- Claim, Evidence, Source, ResearchRun, Task, AgentRun, Report, Review, Artifact 용어를 도메인 명칭으로 고정한다.
- LLM은 구조화된 출력만 반환한다. 노드 연결, 상태 전이, 재시도, 예산, 종료 조건은 코드가 결정한다.
- Source 원문과 AI 생성 요약을 분리한다. 근거 없는 Claim은 숨기지 않고 `unsupported`로 표시한다.
- 모든 Task와 외부 도구 호출은 재현 가능하도록 입력 hash, 모델, 프롬프트 버전, schema 버전, 오류를 기록한다.
- 비밀값, 개인정보, 원문 전체를 로그에 남기지 않는다.

## 패키지 구조

```text
.
├── apps/
│   ├── web/                 # Next.js + React UI
│   ├── api/                 # FastAPI HTTP API
│   └── worker/              # 큐 소비자와 에이전트 실행기
├── packages/
│   └── schemas/             # JSON Schema 정본과 생성 타입
├── infra/                   # Docker, DB migration, 로컬 인프라 설정
├── tests/
│   ├── eval/                # 대표 질문과 기대 Claim/Evidence fixture
│   ├── integration/         # PostgreSQL, Redis, object storage 연동
│   └── e2e/                 # 핵심 사용자 흐름
├── scripts/                 # 반복 가능한 개발·평가 스크립트
├── .env.example
├── .gitignore
└── README.md
```

### 앱 내부 규칙

- `apps/web`: 화면과 API client만 둔다. 도메인 규칙은 API에서 판단한다.
- `apps/api`: `app/api`, `app/domains`, `app/db`, `app/core`로 나눈다.
- `apps/worker`: `agents`, `orchestrator`, `providers`, `runtime`으로 나눈다.
- `packages/schemas`: 언어 중립적인 JSON Schema를 먼저 수정하고 TypeScript/Python 타입을 생성한다.
- 에이전트별 패키지를 따로 만들지 않는다. Worker 내부 모듈로 유지한다.
- 기능이 하나뿐인 파일을 위해 폴더를 만들지 않는다.
- `infra`는 애플리케이션 코드를 포함하지 않는다.

## 코드 컨벤션

### 공통

- 함수와 모듈은 한 가지 책임만 가진다.
- 공개 경계(API, Worker 입력·출력, DB model)는 타입을 명시한다.
- 도메인 상태는 임의 문자열 대신 enum과 허용된 전이표를 사용한다.
- 오류는 안정적인 `error_code`와 사용자용 메시지를 분리한다.
- 주석은 무엇을 하는지보다 왜 필요한지를 설명할 때만 쓴다.
- 포맷터와 린터의 기본 설정을 따른다. 개인별 포맷 예외를 추가하지 않는다.

### Python

- `snake_case` 함수·변수, `PascalCase` 클래스·Pydantic 모델을 사용한다.
- I/O는 async 경계에서 처리하고, 순수 변환 로직은 동기 함수로 둔다.
- API 입력·출력은 Pydantic schema로 검증한다.
- DB 접근은 domain service에서 직접 흩어지지 않도록 `app/db` 경계로 모은다.

### TypeScript/React

- `camelCase` 함수·변수, `PascalCase` 컴포넌트·타입을 사용한다.
- 컴포넌트는 표시와 사용자 상호작용에 집중하고, 데이터 변환은 client/domain utility로 분리한다.
- `any`는 사용하지 않는다. 외부 입력은 `unknown`으로 받고 검증한다.
- API 응답 타입은 `packages/schemas`에서 가져온다.

### API와 데이터

- API 경로는 `/v1`로 시작한다.
- mutation에는 인증과 idempotency key를 적용한다.
- 보고서 문장은 Claim을 참조하고, Claim은 Evidence 경로를 조회할 수 있어야 한다.
- PostgreSQL 관계 테이블을 그래프 정본으로 사용한다. Neo4j는 실제 병목이 확인된 뒤 검토한다.
- Redis는 큐와 lease에만 사용하고, 실행 상태와 artifact의 정본으로 사용하지 않는다.

## 테스트와 검증

- 변경한 동작에 대한 단위 테스트를 먼저 추가한다.
- 상태 전이, JSON Schema, artifact envelope, 재시도·복구는 회귀 테스트를 유지한다.
- Evidence 없는 Claim은 `supported`가 될 수 없다.
- Verifier 실패 보고서는 자동으로 `completed`가 될 수 없다.
- 같은 snapshot과 버전으로 replay할 수 있어야 한다.
- 커밋 전 가능한 범위에서 formatter, lint, typecheck, unit/integration test를 실행한다.

## Git과 커밋

### 브랜치와 PR

- 기본 개발 브랜치는 `develop`, 릴리스 브랜치는 `main`으로 사용한다.
- 모든 작업 브랜치는 Notion Work Item ID를 포함한 `feature/CG-<번호>` 형식을 사용한다.
- MVP에서는 Feature, Bug, Chore, Spike를 구분하지 않고 동일한 브랜치 형식을 사용한다.
- 예: `feature/CG-1`, `feature/CG-12`
- 작업 브랜치는 `develop`에서 만들고, PR 대상도 `develop`으로 지정한다.
- GitHub Actions가 브랜치 push 시 `In Progress`, PR 생성 시 `Review`, `develop` 머지 시 `Done`으로 Notion 카드를 갱신한다.
- Notion 카드가 없는 ID나 형식에 맞지 않는 브랜치는 자동 동기화 대상에서 제외한다.
- 모든 PR은 하나 이상의 assignee와 label을 반드시 등록한다.

### Conventional Commits

Codex가 커밋할 때는 Conventional Commits를 사용한다.

```text
<type>(<scope>): <짧은 현재형 설명>
```

허용 type은 `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `ci`, `perf`, `style`, `revert`다.

- 한 커밋은 하나의 목적만 포함한다.
- Conventional Commit의 type과 scope는 표준 토큰을 유지하되, 제목의 설명은 한국어로 작성한다.
- 커밋 본문을 작성할 때도 한국어를 사용한다.
- 제목은 짧고 명확하게 작성한다.
- 본문은 동작 변경의 이유나 호환성 영향을 설명할 때만 추가한다.
- 테스트가 통과하지 않으면 커밋하지 않는다. 불가피한 경우 커밋 본문에 검증 gap을 기록한다.

### PR 작성 규칙

- PR 제목의 Conventional Commit type token은 `feat:`, `fix:`, `docs:`, `test:`, `chore:` 등 표준 영문을 그대로 유지한다. `기능:`, `수정:`, `문서:`처럼 type token을 한국어로 번역하지 않는다.
- PR 제목의 설명 부분과 본문은 한국어로 작성한다.
- 예: `feat: ResearchRun 생성·조회 API 계약 구현`, `docs: 웹 디자인 전략 정리`
- PR 본문에는 변경 요약, 검증 결과, 설정·리스크를 포함한다.
- PR 생성 시 assignee와 label을 빠뜨리지 않는다.

### 금지 사항

- `Co-authored-by:` 또는 `Co-Authored-By:` trailer를 추가하지 않는다.
- `--author`나 환경변수로 co-author 메타데이터를 주입하지 않는다.
- `git push --force`, `git push -f`, `git push --force-with-lease`를 사용하지 않는다.
- 사용자 요청 없이 원격 브랜치, 태그, 커밋 이력을 삭제·재작성하지 않는다.
- 사용자 요청 없이 `git reset --hard`, `git checkout --`, 대량 삭제를 실행하지 않는다.
- force push가 필요한 상황이면 작업을 멈추고 사용자에게 명시적으로 확인한다.

## 환경변수와 무시할 파일

비밀값은 커밋하지 않는다. 로컬 실행·MCP·OMX 설정과 생성물은 버전 관리 대상이 아니다. 공유가 필요한 설정은 `.env.example`로 제공한다.

`.gitignore`에는 다음 범주를 유지한다.

- 환경변수와 secret: `.env`, `.env.*` 및 인증서·키 파일
- Python: `__pycache__`, `.venv`, `.pytest_cache`, `.ruff_cache`
- Node: `node_modules`, `.next`, `dist`, `coverage`
- 로컬 도구: `.mcp.json`, `.omx`, `.codex`, IDE·OS 메타데이터
- 로컬 인프라: DB volume, Redis dump, object storage snapshot, 로그
- 임시 파일: `tmp`, `temp`, `*.local.*`

무시 목록에 들어간 파일이라도 제품 동작에 필요한 예시 설정이나 migration은 저장소에 명시적으로 추가한다.

## 작업 방식

1. 변경 전 관련 domain과 schema를 확인한다.
2. 가장 작은 변경을 구현한다.
3. 변경된 경로를 테스트하고 lint/typecheck를 실행한다.
4. 결과와 남은 위험을 커밋 또는 리뷰 설명에 남긴다.

## Notion Work Item Sync

GitHub Actions synchronizes ClaimGraph Work Items in Notion from the branch and pull request lifecycle.

Configure these repository values once:

- Secret: `NOTION_TOKEN`
- Repository variable 또는 Secret: `CLAIMGRAPH_NOTION_DATA_SOURCE_ID`

The workflow expects branches in the form `feature/CG-<number>`. A branch push moves the matching work item to `In Progress`, a pull request targeting `develop` moves it to `Review`, and a merged pull request moves it to `Done`.
