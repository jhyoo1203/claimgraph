"""Source metadata and original-content contracts.

The canonical artifact schema deliberately keeps source text out of persisted
artifacts.  The API read contract can still return the original text alongside
the metadata when a repository has it available.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, TypeAlias

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


_SOURCE_ID_PATTERN = re.compile(r"^src_[A-Za-z0-9_-]+$")
_RESEARCH_RUN_ID_PATTERN = re.compile(r"^rr_[A-Za-z0-9_-]+$")
_SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")

MetadataValue: TypeAlias = str | int | float | bool | None


class SourceType(str, Enum):
    """Supported source categories from the shared ClaimGraph contract."""

    WEB = "web"
    DOCUMENT = "document"
    PAPER = "paper"
    DATASET = "dataset"
    API = "api"
    MANUAL = "manual"


class ExtractionStatus(str, Enum):
    """Lifecycle of extracting searchable text from the original source."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# The longer name is useful at API boundaries while the short name remains
# convenient for callers that already use the domain term.
SourceExtractionStatus = ExtractionStatus


class SourceRecord(BaseModel):
    """Repository representation of Source metadata and optional source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, pattern=r"^src_[A-Za-z0-9_-]+$")
    research_run_id: str = Field(min_length=1, pattern=r"^rr_[A-Za-z0-9_-]+$")
    source_type: SourceType
    title: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    publisher: str | None = Field(default=None, min_length=1)
    published_at: datetime | None = None
    retrieved_at: datetime
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    extraction_status: ExtractionStatus
    # ``content`` is accepted as an input alias for repository adapters.  The
    # explicit API name keeps the distinction from generated summaries clear.
    original_content: str | None = Field(
        default=None,
        validation_alias=AliasChoices("original_content", "content"),
    )
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        if _SOURCE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("source_id must match src_<identifier>")
        return value

    @field_validator("research_run_id")
    @classmethod
    def validate_research_run_id(cls, value: str) -> str:
        if _RESEARCH_RUN_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("research_run_id must match rr_<identifier>")
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("content_hash must match sha256:<64 lowercase hex characters>")
        return value

    @field_validator("published_at", "retrieved_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must include a timezone")
        return value

    @property
    def content(self) -> str | None:
        """Compatibility accessor for callers that call the original text content."""

        return self.original_content


# ``Source`` is a domain-friendly alias used by repository and service code.
Source = SourceRecord


class SourceResponse(SourceRecord):
    """HTTP response model for a Source metadata/original-content lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_record(cls, source: SourceRecord | SourceResponse | dict[str, Any]) -> SourceResponse:
        """Build a response while reapplying the public contract validators."""

        if isinstance(source, cls):
            return source
        if isinstance(source, SourceRecord):
            return cls.model_validate(source.model_dump())
        return cls.model_validate(source)
