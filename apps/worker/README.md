# Worker retrieval boundary

CG-10의 retrieval 흐름은 외부 검색·저장 구현을 Worker orchestration에서
분리한다. 현재 구현에는 네트워크, Redis, PostgreSQL, object storage가 없고
결정론적 fake와 in-memory store만 있다.

## Port

`apps.worker.providers.search.SearchProvider`는 질문 하나를 받아
`SearchResponse`를 반환하는 async port다.

```python
response = await provider.search(question)
```

응답 상태는 다음 세 가지로 고정한다.

| 상태 | error code | 의미 |
| --- | --- | --- |
| `succeeded` | 없음 | 하나 이상의 Source 후보가 반환됨 |
| `empty` | `search_empty_result` | provider 호출은 성공했지만 결과가 없음 |
| `failed` | `search_provider_failed` | provider 예외 또는 실패 응답 |

`FakeSearchProvider`는 질문별 응답 map을 사용하고, 알 수 없는 질문은
`empty`를 반환한다. 따라서 테스트에서 네트워크나 시계를 사용할 필요가
없다.

## Snapshot flow

`apps.worker.retrieval.retrieve_sources`가 다음 순서를 소유한다.

1. 질문을 검증하고 `SearchProvider`를 한 번 호출한다.
2. 각 후보의 원문을 UTF-8로 SHA-256 해시한다.
3. `SourceSnapshot`에 `original_content`, `retrieved_at`, `content_hash`,
   `extraction_status`와 Source metadata를 함께 보존한다.
4. `SourceSnapshotStore`에 저장하고, `(research_run_id, content_hash)`가
   이미 있으면 첫 snapshot을 반환하는 방식으로 멱등 처리한다.

빈 결과와 provider 실패는 snapshot을 만들거나 저장하지 않는다. 후보의
원문이 비어 있으면 후보 자체는 보존하되 `extraction_status`를
`failed`로 표시한다.

## CG-11 adapter boundary

CG-11은 `SearchProvider`와 `SourceSnapshotStore`를 주입한다. 검색 SDK,
인증, retry/backoff, PostgreSQL/object storage 구현은 이 두 port 뒤에만
둔다. `SourceSnapshotStore.save`는 `(research_run_id, content_hash)`를
idempotency key로 취급하고 `SnapshotWriteResult.created`로 신규 저장과
중복을 구분해야 한다.

`SourceSnapshot.to_source_artifact_body()`는
`packages/schemas/claimgraph-contract.schema.json`의 metadata-only
`Source` body를 만든다. 원문과 `extraction_status`는 공용 Artifact body에
넣지 않고 snapshot 저장 경계에서 별도로 보존한다. `apps/worker/__init__.py`
와 공용 schema에 retrieval 타입을 재-export하거나 중복 정의하지 않는 것이
의도된 경계다.

## CG-14 Phase 1 integration adapter

`tests/eval/phase1_evaluator.py`는 이 포트들을 실제 외부 인프라 없이 잇는
재현 가능한 adapter다. `FakeSearchProvider`는 질문당 한 번 호출되고,
`retrieve_sources`가 반환한 여러 Source snapshot에 기존
`FixtureExtractor`를 각각 적용한 뒤 Claim key 기준으로 결과를 합친다.
그 결과를 API의 in-memory `ReportRepository`에 저장하고 Report 조회 route의
인용 Markdown과 Web mock envelope를 함께 검증한다. 원문 snapshot과
Evidence 요약은 서로 다른 필드로 유지된다.

이 adapter는 LLM, 실제 검색, PostgreSQL, Redis, 인증, queue를 추가하지 않는다.
`tests/eval/phase1_fixture.json`의 fixture 데이터는 deterministic extraction과
인용 경로 회귀용이며, Phase 2의 최신성·검색 품질·운영 저장소를 검증하지 않는다.
