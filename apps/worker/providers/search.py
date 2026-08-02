"""Single-search provider port and deterministic fake implementation.

Only the ``SearchProvider`` boundary knows how a search is executed.  The
retrieval orchestrator consumes the structured response and owns persistence,
hashing, deduplication, and error classification.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol, TypeAlias, runtime_checkable

from apps.worker.source_snapshots import (
    SOURCE_TYPES,
    ExtractionStatus,
    MetadataValue,
)

PROVIDER_FAILURE_ERROR_CODE: Final = "search_provider_failed"
EMPTY_RESULT_ERROR_CODE: Final = "search_empty_result"
INVALID_RESPONSE_ERROR_CODE: Final = "search_invalid_response"


class SearchOutcomeStatus(StrEnum):
    """Stable outcome categories for one provider call."""

    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    FAILED = "failed"

    # ``SUCCESS`` is a readable alias for callers that use that vocabulary.
    SUCCESS = "succeeded"


SearchStatus = SearchOutcomeStatus


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """A provider result containing metadata and the raw source snapshot."""

    locator: str
    title: str
    content: str | None = None
    source_type: str = "web"
    publisher: str | None = None
    published_at: datetime | None = None
    extraction_status: ExtractionStatus | str = ExtractionStatus.SUCCEEDED
    original_content: str | None = None
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.locator.strip():
            raise ValueError("search candidate locator must not be blank")
        if not self.title.strip():
            raise ValueError("search candidate title must not be blank")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unsupported source_type: {self.source_type!r}")
        if self.publisher is not None and not self.publisher.strip():
            raise ValueError("search candidate publisher must not be blank")
        if self.published_at is not None and (
            self.published_at.tzinfo is None or self.published_at.utcoffset() is None
        ):
            raise ValueError("published_at must include a timezone")

        if self.content is None:
            raw_content = self.original_content or ""
        elif (
            self.original_content is not None and self.original_content != self.content
        ):
            raise ValueError("content and original_content must match")
        else:
            raw_content = self.content

        status = ExtractionStatus(self.extraction_status)
        if not raw_content and status is ExtractionStatus.SUCCEEDED:
            status = ExtractionStatus.FAILED
        object.__setattr__(self, "content", raw_content)
        object.__setattr__(self, "original_content", raw_content)
        object.__setattr__(self, "extraction_status", status)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


# Both names are useful at the provider/retrieval seam and point to one type.
SourceCandidate = SearchCandidate


@dataclass(frozen=True, slots=True)
class SearchError:
    """Stable, non-sensitive provider error details."""

    error_code: str
    message: str
    retryable: bool = True

    @classmethod
    def provider_failure(cls) -> SearchError:
        return cls(
            error_code=PROVIDER_FAILURE_ERROR_CODE,
            message="Search provider failed.",
            retryable=True,
        )

    @classmethod
    def empty_result(cls) -> SearchError:
        return cls(
            error_code=EMPTY_RESULT_ERROR_CODE,
            message="Search provider returned no results.",
            retryable=False,
        )


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Structured result returned across the single-search provider port."""

    candidates: tuple[SearchCandidate, ...] = ()
    status: SearchOutcomeStatus | str | None = None
    error: SearchError | None = None

    def __post_init__(self) -> None:
        candidates = tuple(
            _coerce_candidate(candidate) for candidate in self.candidates
        )
        status = (
            SearchOutcomeStatus(self.status)
            if self.status is not None
            else _infer_status(candidates, self.error)
        )

        if status is SearchOutcomeStatus.SUCCEEDED and not candidates:
            status = SearchOutcomeStatus.EMPTY
        if status is SearchOutcomeStatus.EMPTY:
            candidates = ()
            if self.error is None:
                object.__setattr__(self, "error", SearchError.empty_result())
        elif status is SearchOutcomeStatus.FAILED:
            if self.error is None:
                object.__setattr__(self, "error", SearchError.provider_failure())
        elif self.error is not None:
            raise ValueError("successful search responses cannot include an error")

        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "status", status)

    @classmethod
    def succeeded(cls, candidates: Iterable[SearchCandidate]) -> SearchResponse:
        return cls(candidates=tuple(candidates), status=SearchOutcomeStatus.SUCCEEDED)

    @classmethod
    def empty(cls) -> SearchResponse:
        return cls(status=SearchOutcomeStatus.EMPTY, error=SearchError.empty_result())

    @classmethod
    def failed(cls, error: SearchError | None = None) -> SearchResponse:
        return cls(
            status=SearchOutcomeStatus.FAILED,
            error=error or SearchError.provider_failure(),
        )

    @property
    def is_empty(self) -> bool:
        return self.status is SearchOutcomeStatus.EMPTY

    @property
    def is_failed(self) -> bool:
        return self.status is SearchOutcomeStatus.FAILED


SearchProviderResponse = SearchResponse
SearchOutcome = SearchResponse


@runtime_checkable
class SearchProvider(Protocol):
    """Async port for exactly one search operation from a question."""

    async def search(self, question: str) -> SearchResponse:
        """Return a structured success, empty, or provider-failure outcome."""


SingleSearchProvider = SearchProvider


SearchResponseInput: TypeAlias = SearchResponse | Iterable[SearchCandidate] | None


class FakeSearchProvider:
    """Deterministic provider backed by an explicit question-to-response map.

    Unknown questions return an empty result.  No network or clock is touched;
    callers can inject all response data and inspect the exact call sequence.
    """

    def __init__(
        self,
        responses: Mapping[str, SearchResponseInput] | None = None,
        *,
        failure_questions: Iterable[str] = (),
        failures: Mapping[str, object] | Iterable[str] = (),
        empty_questions: Iterable[str] = (),
        default_response: SearchResponseInput = None,
    ) -> None:
        self._responses = {
            question: _coerce_response(response)
            for question, response in (responses or {}).items()
        }
        self._failure_questions = set(failure_questions)
        if isinstance(failures, Mapping):
            self._failure_questions.update(failures)
        else:
            self._failure_questions.update(failures)
        self._empty_questions = set(empty_questions)
        self._default_response = _coerce_response(default_response)
        self._calls: list[str] = []

    @property
    def calls(self) -> tuple[str, ...]:
        """Return the immutable sequence of questions received by the fake."""

        return tuple(self._calls)

    async def search(self, question: str) -> SearchResponse:
        self._calls.append(question)
        if question in self._failure_questions:
            return SearchResponse.failed()
        if question in self._empty_questions:
            return SearchResponse.empty()
        return self._responses.get(question, self._default_response)

    def add_response(self, question: str, response: SearchResponseInput) -> None:
        """Add a deterministic response without changing provider semantics."""

        self._responses[question] = _coerce_response(response)


def _coerce_candidate(
    candidate: SearchCandidate | Mapping[str, object],
) -> SearchCandidate:
    if isinstance(candidate, SearchCandidate):
        return candidate
    return SearchCandidate(**candidate)  # type: ignore[arg-type]


def _coerce_response(response: SearchResponseInput) -> SearchResponse:
    if isinstance(response, SearchResponse):
        return response
    if response is None:
        return SearchResponse.empty()
    return SearchResponse.succeeded(response)


def _infer_status(
    candidates: tuple[SearchCandidate, ...], error: SearchError | None
) -> SearchOutcomeStatus:
    if error is not None:
        return SearchOutcomeStatus.FAILED
    return SearchOutcomeStatus.SUCCEEDED if candidates else SearchOutcomeStatus.EMPTY


__all__ = [
    "EMPTY_RESULT_ERROR_CODE",
    "INVALID_RESPONSE_ERROR_CODE",
    "PROVIDER_FAILURE_ERROR_CODE",
    "FakeSearchProvider",
    "SearchCandidate",
    "SearchError",
    "SearchOutcome",
    "SearchOutcomeStatus",
    "SearchProvider",
    "SearchProviderResponse",
    "SearchResponse",
    "SearchStatus",
    "SingleSearchProvider",
    "SourceCandidate",
]
