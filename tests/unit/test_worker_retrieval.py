from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apps.worker.providers.search import (
    EMPTY_RESULT_ERROR_CODE,
    PROVIDER_FAILURE_ERROR_CODE,
    FakeSearchProvider,
    SearchCandidate,
    SearchOutcomeStatus,
    SearchResponse,
)
from apps.worker.retrieval import RetrievalStatus, retrieve_sources
from apps.worker.source_snapshots import (
    ExtractionStatus,
    InMemorySourceSnapshotStore,
    content_hash_for,
)

RETRIEVED_AT = datetime(2026, 8, 3, 1, 30, tzinfo=timezone.utc)


def run(coroutine: object) -> object:
    return asyncio.run(coroutine)  # type: ignore[arg-type]


def test_fake_provider_is_deterministic_and_returns_structured_candidates() -> None:
    candidate = SearchCandidate(
        locator="https://example.test/source",
        title="Example source",
        content="The original source text.",
    )
    provider = FakeSearchProvider({"question": [candidate]})

    first = run(provider.search("question"))
    second = run(provider.search("question"))

    assert first == second
    assert first.status is SearchOutcomeStatus.SUCCEEDED
    assert first.candidates == (candidate,)
    assert provider.calls == ("question", "question")


def test_retrieval_preserves_snapshot_fields_and_calculates_hash() -> None:
    candidate = SearchCandidate(
        locator="https://example.test/source",
        title="Example source",
        content="The original source text.",
        extraction_status=ExtractionStatus.PENDING,
    )
    provider = FakeSearchProvider({"question": [candidate]})
    store = InMemorySourceSnapshotStore()

    result = run(
        retrieve_sources(
            " question ",
            "rr_demo",
            provider,
            store,
            retrieved_at=RETRIEVED_AT,
        )
    )

    assert result.status is RetrievalStatus.SUCCEEDED
    assert result.error is None
    assert len(result.sources) == 1
    snapshot = result.sources[0]
    assert snapshot.original_content == "The original source text."
    assert snapshot.content == snapshot.original_content
    assert snapshot.snapshot == snapshot.original_content
    assert snapshot.retrieved_at == RETRIEVED_AT
    assert snapshot.content_hash == content_hash_for(snapshot.original_content)
    assert snapshot.extraction_status is ExtractionStatus.PENDING
    assert result.writes[0].created
    assert len(store) == 1


def test_same_content_hash_is_idempotent_within_a_research_run() -> None:
    candidates = [
        SearchCandidate(
            locator="https://example.test/first",
            title="First title",
            content="same raw source",
        ),
        SearchCandidate(
            locator="https://example.test/second",
            title="Second title",
            content="same raw source",
        ),
    ]
    provider = FakeSearchProvider({"question": candidates})
    store = InMemorySourceSnapshotStore()

    first = run(
        retrieve_sources(
            "question",
            "rr_demo",
            provider,
            store,
            retrieved_at=RETRIEVED_AT,
        )
    )
    second = run(
        retrieve_sources(
            "question",
            "rr_demo",
            provider,
            store,
            retrieved_at=datetime(2026, 8, 3, 2, tzinfo=timezone.utc),
        )
    )

    assert first.status is RetrievalStatus.SUCCEEDED
    assert len(first.sources) == 1
    assert [write.created for write in first.writes] == [True, False]
    assert first.deduplicated_count == 1
    assert second.status is RetrievalStatus.SUCCEEDED
    assert second.deduplicated_count == 2
    assert second.sources == first.sources
    assert second.sources[0].title == "First title"
    assert len(store) == 1


def test_empty_result_is_distinct_from_provider_failure_and_writes_nothing() -> None:
    empty_provider = FakeSearchProvider(empty_questions={"empty question"})
    failed_provider = FakeSearchProvider(failure_questions={"failed question"})
    empty_store = InMemorySourceSnapshotStore()
    failed_store = InMemorySourceSnapshotStore()

    empty = run(
        retrieve_sources(
            "empty question",
            "rr_empty",
            empty_provider,
            empty_store,
            retrieved_at=RETRIEVED_AT,
        )
    )
    failed = run(
        retrieve_sources(
            "failed question",
            "rr_failed",
            failed_provider,
            failed_store,
            retrieved_at=RETRIEVED_AT,
        )
    )

    assert empty.status is RetrievalStatus.EMPTY
    assert empty.error_code == EMPTY_RESULT_ERROR_CODE
    assert empty.sources == ()
    assert empty.writes == ()
    assert failed.status is RetrievalStatus.FAILED
    assert failed.error_code == PROVIDER_FAILURE_ERROR_CODE
    assert failed.sources == ()
    assert failed.writes == ()
    assert len(empty_store) == 0
    assert len(failed_store) == 0


def test_provider_exception_is_normalized_without_exposing_exception_text() -> None:
    class RaisingProvider:
        async def search(self, question: str) -> SearchResponse:
            raise RuntimeError("secret-token=must-not-be-returned")

    result = run(
        retrieve_sources(
            "question",
            "rr_demo",
            RaisingProvider(),
            InMemorySourceSnapshotStore(),
            retrieved_at=RETRIEVED_AT,
        )
    )

    assert result.status is RetrievalStatus.FAILED
    assert result.error_code == PROVIDER_FAILURE_ERROR_CODE
    assert result.error is not None
    assert "secret-token" not in result.error.message


def test_empty_source_content_is_retained_with_failed_extraction_status() -> None:
    candidate = SearchCandidate(
        locator="https://example.test/empty",
        title="Empty source",
        content="",
    )
    provider = FakeSearchProvider({"question": [candidate]})
    store = InMemorySourceSnapshotStore()

    result = run(
        retrieve_sources(
            "question",
            "rr_demo",
            provider,
            store,
            retrieved_at=RETRIEVED_AT,
        )
    )

    assert result.status is RetrievalStatus.SUCCEEDED
    assert result.sources[0].original_content == ""
    assert result.sources[0].extraction_status is ExtractionStatus.FAILED
    assert result.sources[0].content_hash == content_hash_for("")
