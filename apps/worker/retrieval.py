"""Question-to-Source retrieval orchestration for the Worker MVP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Final

from apps.worker.providers.search import (
    PROVIDER_FAILURE_ERROR_CODE,
    SearchError,
    SearchOutcomeStatus,
    SearchProvider,
    SearchResponse,
)
from apps.worker.source_snapshots import (
    RESEARCH_RUN_ID_PATTERN,
    SnapshotWriteResult,
    SourceSnapshot,
    SourceSnapshotStore,
    content_hash_for,
    source_id_for,
)

SNAPSHOT_STORE_FAILURE_ERROR_CODE: Final = "source_snapshot_store_failed"


class RetrievalStatus(StrEnum):
    """Stable result categories returned by the retrieval flow."""

    SUCCEEDED = SearchOutcomeStatus.SUCCEEDED.value
    EMPTY = SearchOutcomeStatus.EMPTY.value
    FAILED = SearchOutcomeStatus.FAILED.value


@dataclass(frozen=True, slots=True)
class SourceRetrievalResult:
    """Search outcome plus the Source snapshots written for that outcome."""

    status: RetrievalStatus | str
    sources: tuple[SourceSnapshot, ...] = ()
    writes: tuple[SnapshotWriteResult, ...] = ()
    error: SearchError | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", RetrievalStatus(self.status))
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "writes", tuple(self.writes))

    @property
    def snapshots(self) -> tuple[SourceSnapshot, ...]:
        """Alias for callers that use the storage term instead of Source."""

        return self.sources

    @property
    def error_code(self) -> str | None:
        return self.error.error_code if self.error is not None else None

    @property
    def is_empty(self) -> bool:
        return self.status is RetrievalStatus.EMPTY

    @property
    def is_provider_failure(self) -> bool:
        return (
            self.status is RetrievalStatus.FAILED
            and self.error_code == PROVIDER_FAILURE_ERROR_CODE
        )

    @property
    def deduplicated_count(self) -> int:
        return sum(1 for write in self.writes if write.deduplicated)


async def retrieve_sources(
    question: str,
    research_run_id: str,
    provider: SearchProvider,
    store: SourceSnapshotStore,
    *,
    retrieved_at: datetime | None = None,
) -> SourceRetrievalResult:
    """Search once, snapshot every candidate, and return a stable outcome.

    Provider failures and an empty successful response never write snapshots.
    For successful candidates, the supplied retrieval timestamp is reused for
    every Source in the call so a replay can produce the same snapshot set.
    """

    normalized_question = _require_question(question)
    _require_research_run_id(research_run_id)
    retrieval_time = retrieved_at or datetime.now(timezone.utc)
    _require_aware_timestamp(retrieval_time)

    try:
        response: SearchResponse = await provider.search(normalized_question)
    except Exception:  # noqa: BLE001 - normalize arbitrary provider failures
        # Do not expose exception text: provider errors may contain secrets or
        # original source data.  The error code is the stable retry boundary.
        return SourceRetrievalResult(
            status=RetrievalStatus.FAILED,
            error=SearchError.provider_failure(),
        )

    if response.status is SearchOutcomeStatus.FAILED:
        return SourceRetrievalResult(
            status=RetrievalStatus.FAILED,
            error=SearchError.provider_failure(),
        )
    if response.status is SearchOutcomeStatus.EMPTY or not response.candidates:
        return SourceRetrievalResult(
            status=RetrievalStatus.EMPTY,
            error=SearchError.empty_result(),
        )

    try:
        snapshots = tuple(
            _snapshot_for_candidate(
                candidate,
                research_run_id=research_run_id,
                retrieved_at=retrieval_time,
            )
            for candidate in response.candidates
        )
    except Exception:  # noqa: BLE001 - protect the provider boundary
        return SourceRetrievalResult(
            status=RetrievalStatus.FAILED,
            error=SearchError.provider_failure(),
        )

    writes: list[SnapshotWriteResult] = []
    sources_by_id: dict[str, SourceSnapshot] = {}
    try:
        for snapshot in snapshots:
            write = await store.save(snapshot)
            writes.append(write)
            sources_by_id.setdefault(write.snapshot.source_id, write.snapshot)
    except Exception:  # noqa: BLE001 - normalize adapter failures
        return SourceRetrievalResult(
            status=RetrievalStatus.FAILED,
            sources=tuple(sources_by_id.values()),
            writes=tuple(writes),
            error=SearchError(
                error_code=SNAPSHOT_STORE_FAILURE_ERROR_CODE,
                message="Source snapshot store failed.",
                retryable=True,
            ),
        )

    return SourceRetrievalResult(
        status=RetrievalStatus.SUCCEEDED,
        sources=tuple(sources_by_id.values()),
        writes=tuple(writes),
    )


# Names used by downstream Worker tasks can remain descriptive without making
# another orchestration implementation.
retrieve_source_snapshots = retrieve_sources
run_single_search = retrieve_sources
search_and_snapshot = retrieve_sources


def _snapshot_for_candidate(
    candidate: object,
    *,
    research_run_id: str,
    retrieved_at: datetime,
) -> SourceSnapshot:
    content = candidate.content  # type: ignore[attr-defined]
    content_hash = content_hash_for(content)
    return SourceSnapshot(
        source_id=source_id_for(research_run_id, content_hash),
        research_run_id=research_run_id,
        source_type=candidate.source_type,  # type: ignore[attr-defined]
        title=candidate.title,  # type: ignore[attr-defined]
        locator=candidate.locator,  # type: ignore[attr-defined]
        original_content=content,
        retrieved_at=retrieved_at,
        content_hash=content_hash,
        extraction_status=candidate.extraction_status,  # type: ignore[attr-defined]
        publisher=candidate.publisher,  # type: ignore[attr-defined]
        published_at=candidate.published_at,  # type: ignore[attr-defined]
        metadata=candidate.metadata,  # type: ignore[attr-defined]
    )


def _require_question(question: str) -> str:
    normalized = question.strip()
    if not normalized:
        raise ValueError("question must not be blank")
    return normalized


def _require_research_run_id(research_run_id: str) -> None:
    if RESEARCH_RUN_ID_PATTERN.fullmatch(research_run_id) is None:
        raise ValueError("research_run_id must match rr_<identifier>")


def _require_aware_timestamp(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")


__all__ = [
    "SNAPSHOT_STORE_FAILURE_ERROR_CODE",
    "RetrievalStatus",
    "SourceRetrievalResult",
    "retrieve_source_snapshots",
    "retrieve_sources",
    "run_single_search",
    "search_and_snapshot",
]
