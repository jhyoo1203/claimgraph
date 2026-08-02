# ClaimGraph

출처와 주장 사이의 연결을 투명하게 보여주는 AI 리서치 워크스페이스.

현재 저장소는 MVP 구현을 위한 최소 프로젝트 구조만 생성된 상태다. 구현 규칙은 [AGENTS.md](./AGENTS.md), 제품·기술 기준은 [Notion 테크스펙](https://app.notion.com/p/3b0d9f28841281ac8350fcdf586311ad)을 따른다.

```text
apps/web         Next.js Web
apps/api         FastAPI API
apps/worker      에이전트 Worker
packages/schemas 공유 JSON Schema
infra            로컬 인프라와 migration
tests             평가·통합·E2E 테스트
scripts           반복 작업 스크립트
```

기능 구현과 의존성 설치는 다음 작업에서 진행한다.

## Notion Work Item Sync

GitHub Actions synchronizes ClaimGraph Work Items in Notion from the branch and pull request lifecycle.

Configure these repository values once:

- Secret: `NOTION_TOKEN`
- Repository variable: `CLAIMGRAPH_NOTION_DATA_SOURCE_ID`

The workflow expects branches in the form `feature/CG-<number>`. A branch push moves the matching work item to `In Progress`, a pull request targeting `develop` moves it to `Review`, and a merged pull request moves it to `Done`.
