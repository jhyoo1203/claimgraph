"""Source repository protocol and in-memory adapter.

The protocol is intentionally small so a PostgreSQL/object-storage adapter can
be added later without changing the HTTP boundary.  In-memory storage is used
for local development and deterministic tests only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, TypeAlias

from app.domains.sources import SourceRecord


SourceInput: TypeAlias = SourceRecord | Mapping[str, Any]


class SourceRepository(Protocol):
    """Read boundary for Source records."""

    def get_source(self, source_id: str) -> SourceRecord | None:
        """Return a Source by stable ID, or ``None`` when it does not exist."""


SourceRepositoryProtocol = SourceRepository


class InMemorySourceRepository:
    """Deterministic repository implementation for tests and local API runs."""

    def __init__(self, sources: Iterable[SourceInput] | Mapping[str, SourceInput] = ()) -> None:
        self._sources: dict[str, SourceRecord] = {}
        if isinstance(sources, Mapping) and "source_id" not in sources:
            source_values = sources.values()
        elif isinstance(sources, Mapping):
            source_values = (sources,)
        else:
            source_values = sources
        for source in source_values:
            self.put(source)

    def put(self, source: SourceInput) -> SourceRecord:
        """Validate and store a Source, returning the stored record."""

        record = source if isinstance(source, SourceRecord) else SourceRecord.model_validate(source)
        self._sources[record.source_id] = record
        return record

    add = put
    save = put

    def get_source(self, source_id: str) -> SourceRecord | None:
        """Return a defensive copy so callers cannot mutate repository state."""

        record = self._sources.get(source_id)
        return record.model_copy(deep=True) if record is not None else None

    # Common repository spellings are kept as thin aliases for adapters and
    # tests; the protocol's canonical operation is ``get_source``.
    get = get_source
    get_by_id = get_source

    def __len__(self) -> int:
        return len(self._sources)
