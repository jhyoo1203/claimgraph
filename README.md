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

## Worker 상태 전이

Worker의 상태 값은 `packages/schemas/claimgraph-contract.schema.json`과
`apps/worker/state.py`에서 함께 관리한다. 상태 문자열은 검증한 뒤 전이
함수를 통해서만 변경한다.

```python
from apps.worker.state import (
    TaskStatus,
    task_failure_status,
    transition_task_status,
)

next_status = transition_task_status(TaskStatus.QUEUED, TaskStatus.RUNNING)
failure_status = transition_task_status(
    next_status, task_failure_status(retryable=True)
)
assert failure_status is TaskStatus.RETRYING
```

Retryable failure는 `retrying`으로, 재시도하지 않는 failure는 `failed`로
표현한다. `retrying` task는 `queued`로 돌아가 다음 시도를 시작하며,
terminal 상태(`succeeded`, `failed`, `cancelled`)는 다시 전이할 수 없다.
