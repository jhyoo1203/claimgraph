"""Runtime Source snapshots and their storage port.

The shared Source artifact intentionally contains metadata only.  This module
keeps the original source text in a runtime snapshot so a later adapter can
persist it separately without changing the shared artifact schema.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol, TypeAlias, runtime_checkable

SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {"web", "document", "paper", "dataset", "api", "manual"}
)
SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^sha256:[a-f0-9]{64}$")
SOURCE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^src_[A-Za-z0-9_-]+$")
RESEARCH_RUN_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^rr_[A-Za-z0-9_-]+$")

MetadataValue: TypeAlias = str | int | float | bool | None


class ExtractionStatus(StrEnum):
    """Lifecycle of extracting searchable text from an original Source."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# The longer spelling is useful to callers that want to make the boundary
# explicit while keeping the domain term convenient for worker code.
SourceExtractionStatus = ExtractionStatus


def content_hash_for(content: str) -> str:
    """Return the canonical SHA-256 hash for a UTF-8 Source snapshot."""

    if not isinstance(content, str):
        raise TypeError("source snapshot content must be a string")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# Descriptive aliases make the hashing rule discoverable at adapter
# boundaries without creating another implementation of it.
sha256_content_hash = content_hash_for
calculate_content_hash = content_hash_for


def source_id_for(research_run_id: str, content_hash: str) -> str:
    """Create a deterministic Source ID for one run and content hash."""

    _validate_research_run_id(research_run_id)
    _validate_content_hash(content_hash)
    identity = f"{research_run_id}\x00{content_hash}".encode()
    return f"src_{hashlib.sha256(identity).hexdigest()}"


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Original Source text plus the metadata needed to replay retrieval.

    ``original_content`` is deliberately separate from generated Evidence or
    summaries.  The content hash is checked against the exact UTF-8 text at
    construction time, so adapters cannot silently persist mismatched data.
    """

    source_id: str
    research_run_id: str
    source_type: str
    title: str
    locator: str
    original_content: str
    retrieved_at: datetime
    content_hash: str
    extraction_status: ExtractionStatus | str
    publisher: str | None = None
    published_at: datetime | None = None
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_source_id(self.source_id)
        _validate_research_run_id(self.research_run_id)
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unsupported source_type: {self.source_type!r}")
        if not self.title.strip():
            raise ValueError("source title must not be blank")
        if not self.locator.strip():
            raise ValueError("source locator must not be blank")
        if not isinstance(self.original_content, str):
            raise TypeError("original_content must be a string")
        _validate_timestamp(self.retrieved_at, "retrieved_at")
        if self.published_at is not None:
            _validate_timestamp(self.published_at, "published_at")
        _validate_content_hash(self.content_hash)
        if self.content_hash != content_hash_for(self.original_content):
            raise ValueError("content_hash does not match original_content")

        status = ExtractionStatus(self.extraction_status)
        object.__setattr__(self, "extraction_status", status)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def content(self) -> str:
        """Compatibility accessor for callers using ``content`` terminology."""

        return self.original_content

    @property
    def snapshot(self) -> str:
        """Compatibility accessor for callers using ``snapshot`` terminology."""

        return self.original_content

    def to_dict(self) -> dict[str, object]:
        """Serialize the complete runtime snapshot without losing raw text."""

        return {
            "source_id": self.source_id,
            "research_run_id": self.research_run_id,
            "source_type": self.source_type,
            "title": self.title,
            "locator": self.locator,
            "publisher": self.publisher,
            "published_at": self.published_at.isoformat()
            if self.published_at is not None
            else None,
            "original_content": self.original_content,
            "retrieved_at": self.retrieved_at.isoformat(),
            "content_hash": self.content_hash,
            "extraction_status": ExtractionStatus(self.extraction_status).value,
            "metadata": dict(self.metadata),
        }

    def to_source_artifact_body(self) -> dict[str, object]:
        """Project metadata into the canonical shared ``Source`` body.

        The shared schema keeps full source text and worker extraction state
        outside the Source artifact.  A persistence adapter can store this
        body alongside the runtime snapshot.
        """

        body: dict[str, object] = {
            "source_id": self.source_id,
            "research_run_id": self.research_run_id,
            "source_type": self.source_type,
            "title": self.title,
            "locator": self.locator,
            "retrieved_at": self.retrieved_at.isoformat(),
            "content_hash": self.content_hash,
        }
        if self.publisher is not None:
            body["publisher"] = self.publisher
        if self.published_at is not None:
            body["published_at"] = self.published_at.isoformat()
        if self.metadata:
            body["metadata"] = dict(self.metadata)
        return body


# ``SourceSnapshotRecord`` is an explicit name for storage adapters while the
# shorter domain name remains the primary public type.
SourceSnapshotRecord = SourceSnapshot


class SnapshotWriteStatus(StrEnum):
    """Outcome of an idempotent Source snapshot write."""

    CREATED = "created"
    DEDUPLICATED = "deduplicated"


@dataclass(frozen=True, slots=True)
class SnapshotWriteResult:
    """Stored snapshot and whether this call created a new record."""

    snapshot: SourceSnapshot
    created: bool

    @property
    def status(self) -> SnapshotWriteStatus:
        return (
            SnapshotWriteStatus.CREATED
            if self.created
            else SnapshotWriteStatus.DEDUPLICATED
        )

    @property
    def inserted(self) -> bool:
        """Alias used by repository adapters that call writes inserts."""

        return self.created

    @property
    def deduplicated(self) -> bool:
        return not self.created


@runtime_checkable
class SourceSnapshotStore(Protocol):
    """Persistence port consumed by the retrieval orchestrator.

    Implementations must treat ``(research_run_id, content_hash)`` as an
    idempotency key and return the first stored snapshot for duplicates.
    """

    async def save(self, snapshot: SourceSnapshot) -> SnapshotWriteResult:
        """Insert a snapshot or return the existing equal-content record."""

    async def get_by_id(self, source_id: str) -> SourceSnapshot | None:
        """Return a snapshot by stable Source ID."""

    async def get_by_content_hash(
        self, research_run_id: str, content_hash: str
    ) -> SourceSnapshot | None:
        """Return the snapshot stored for a run and content hash."""


# Repository is a useful synonym for callers that use repository vocabulary.
SourceSnapshotRepository = SourceSnapshotStore


class InMemorySourceSnapshotStore:
    """Deterministic, dependency-free Source snapshot store for the MVP."""

    def __init__(self, snapshots: Iterable[SourceSnapshot] = ()) -> None:
        self._by_key: dict[tuple[str, str], SourceSnapshot] = {}
        self._by_id: dict[str, SourceSnapshot] = {}
        for snapshot in snapshots:
            self._insert_initial(snapshot)

    async def save(self, snapshot: SourceSnapshot) -> SnapshotWriteResult:
        """Save once and make repeated writes idempotent by content hash."""

        key = (snapshot.research_run_id, snapshot.content_hash)
        existing = self._by_key.get(key)
        if existing is not None:
            return SnapshotWriteResult(snapshot=existing, created=False)

        existing_id = self._by_id.get(snapshot.source_id)
        if existing_id is not None:
            raise ValueError("source_id is already associated with another snapshot")

        self._by_key[key] = snapshot
        self._by_id[snapshot.source_id] = snapshot
        return SnapshotWriteResult(snapshot=snapshot, created=True)

    async def get_by_id(self, source_id: str) -> SourceSnapshot | None:
        return self._by_id.get(source_id)

    async def get_by_content_hash(
        self, research_run_id: str, content_hash: str
    ) -> SourceSnapshot | None:
        _validate_research_run_id(research_run_id)
        _validate_content_hash(content_hash)
        return self._by_key.get((research_run_id, content_hash))

    async def get_by_hash(
        self, research_run_id: str, content_hash: str
    ) -> SourceSnapshot | None:
        """Alias for adapters that use the shorter hash lookup name."""

        return await self.get_by_content_hash(research_run_id, content_hash)

    async def list_for_run(self, research_run_id: str) -> tuple[SourceSnapshot, ...]:
        _validate_research_run_id(research_run_id)
        return tuple(
            snapshot
            for (run_id, _), snapshot in self._by_key.items()
            if run_id == research_run_id
        )

    async def put(self, snapshot: SourceSnapshot) -> SnapshotWriteResult:
        """Repository spelling for ``save``."""

        return await self.save(snapshot)

    async def upsert(self, snapshot: SourceSnapshot) -> SnapshotWriteResult:
        """Repository spelling for the idempotent ``save`` operation."""

        return await self.save(snapshot)

    def __len__(self) -> int:
        return len(self._by_id)

    def _insert_initial(self, snapshot: SourceSnapshot) -> None:
        key = (snapshot.research_run_id, snapshot.content_hash)
        if key in self._by_key:
            return
        if snapshot.source_id in self._by_id:
            raise ValueError("source_id is already associated with another snapshot")
        self._by_key[key] = snapshot
        self._by_id[snapshot.source_id] = snapshot


InMemorySourceSnapshotRepository = InMemorySourceSnapshotStore


def _validate_source_id(source_id: str) -> None:
    if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise ValueError("source_id must match src_<identifier>")


def _validate_research_run_id(research_run_id: str) -> None:
    if RESEARCH_RUN_ID_PATTERN.fullmatch(research_run_id) is None:
        raise ValueError("research_run_id must match rr_<identifier>")


def _validate_content_hash(content_hash: str) -> None:
    if SHA256_PATTERN.fullmatch(content_hash) is None:
        raise ValueError("content_hash must match sha256:<64 lowercase hex characters>")


def _validate_timestamp(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


__all__ = [
    "SHA256_PATTERN",
    "SOURCE_TYPES",
    "ExtractionStatus",
    "InMemorySourceSnapshotRepository",
    "InMemorySourceSnapshotStore",
    "MetadataValue",
    "SnapshotWriteResult",
    "SnapshotWriteStatus",
    "SourceExtractionStatus",
    "SourceSnapshot",
    "SourceSnapshotRecord",
    "SourceSnapshotRepository",
    "SourceSnapshotStore",
    "calculate_content_hash",
    "content_hash_for",
    "sha256_content_hash",
    "source_id_for",
]
