"""Report contracts, graph snapshot, and in-memory repository.

The current ResearchRun HTTP contract intentionally stays small.  A Report
keeps the graph objects needed to render a cited document in this separate
module so a future persistent adapter can replace the in-memory repository
without changing the route or renderer boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, TypeAlias, runtime_checkable

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


REPORT_ID_PATTERN = r"^rpt_[A-Za-z0-9_-]+$"
STATEMENT_ID_PATTERN = r"^stmt_[A-Za-z0-9_-]+$"
CLAIM_ID_PATTERN = r"^clm_[A-Za-z0-9_-]+$"
EVIDENCE_ID_PATTERN = r"^ev_[A-Za-z0-9_-]+$"
SOURCE_ID_PATTERN = r"^src_[A-Za-z0-9_-]+$"
RESEARCH_RUN_ID_PATTERN = r"^rr_[A-Za-z0-9_-]+$"
RELATION_ID_PATTERN = r"^rel_[A-Za-z0-9_-]+$"
SHA256_PATTERN = r"^sha256:[a-f0-9]{64}$"


class ReportStatus(StrEnum):
    """Lifecycle values from the shared Report contract."""

    DRAFT = "draft"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"


class ClaimStatus(StrEnum):
    """Claim status values kept in the shared contract."""

    UNSUPPORTED = "unsupported"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    MIXED = "mixed"
    NEEDS_REVIEW = "needs_review"


class EvidenceKind(StrEnum):
    """Evidence kinds from the shared ClaimGraph contract."""

    QUOTE = "quote"
    SUMMARY = "summary"
    TABLE = "table"
    METRIC = "metric"
    OBSERVATION = "observation"


class ClaimEvidenceRelationType(StrEnum):
    """Typed edges between a Claim and an Evidence record."""

    SUPPORTS = "supports"
    REFUTES = "refutes"
    QUALIFIES = "qualifies"
    MENTIONS = "mentions"


class _ReportModel(BaseModel):
    """Shared validation settings for Report graph records."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class ReportSource(_ReportModel):
    """Source metadata plus an optional original-content snapshot.

    The canonical artifact schema does not store source text.  The API report
    snapshot may receive it as ``original_content`` so the renderer can keep it
    visibly separate from Evidence's generated quote or summary.
    """

    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    research_run_id: str = Field(pattern=RESEARCH_RUN_ID_PATTERN)
    title: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    original_content: str | None = Field(
        default=None,
        validation_alias=AliasChoices("original_content", "content"),
    )
    source_type: str | None = None
    publisher: str | None = Field(default=None, min_length=1)
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    content_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )

    @property
    def content(self) -> str | None:
        """Compatibility accessor for callers that use ``content``."""

        return self.original_content


class ReportEvidence(_ReportModel):
    """An Evidence item linked to a Source."""

    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    research_run_id: str = Field(pattern=RESEARCH_RUN_ID_PATTERN)
    kind: EvidenceKind = EvidenceKind.SUMMARY
    quote_or_summary: str = Field(
        min_length=1,
        validation_alias=AliasChoices("quote_or_summary", "summary"),
    )
    locator: str | None = Field(default=None, min_length=1)
    content_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    collected_at: datetime | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class ReportClaim(_ReportModel):
    """A Claim rendered as one or more cited report statements."""

    claim_id: str = Field(pattern=CLAIM_ID_PATTERN)
    research_run_id: str = Field(pattern=RESEARCH_RUN_ID_PATTERN)
    text: str = Field(min_length=1)
    status: ClaimStatus
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime | None = None
    unsupported_reason: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("unsupported_reason", "reason"),
    )
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )

    @property
    def reason(self) -> str | None:
        """Short alias for the explicit unsupported reason."""

        return self.unsupported_reason


class ClaimEvidenceRelation(_ReportModel):
    """A typed Claim-to-Evidence graph edge."""

    relation_id: str | None = Field(default=None, pattern=RELATION_ID_PATTERN)
    claim_id: str = Field(pattern=CLAIM_ID_PATTERN)
    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    relation_type: ClaimEvidenceRelationType = ClaimEvidenceRelationType.SUPPORTS
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class ReportStatement(_ReportModel):
    """An ordered report sentence connected to exactly one Claim."""

    statement_id: str = Field(default="stmt_generated", pattern=STATEMENT_ID_PATTERN)
    report_id: str | None = Field(default=None, pattern=REPORT_ID_PATTERN)
    claim_id: str = Field(pattern=CLAIM_ID_PATTERN)
    position: int = Field(default=0, ge=0)
    text: str | None = Field(default=None, min_length=1)
    created_at: datetime | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class Report(_ReportModel):
    """Stored Report graph snapshot used by the renderer and API route."""

    report_id: str = Field(pattern=REPORT_ID_PATTERN)
    research_run_id: str = Field(pattern=RESEARCH_RUN_ID_PATTERN)
    title: str = Field(min_length=1)
    status: ReportStatus
    created_at: datetime
    published_at: datetime | None = None
    statements: list[ReportStatement] = Field(default_factory=list)
    claims: list[ReportClaim] = Field(default_factory=list)
    evidence: list[ReportEvidence] = Field(default_factory=list)
    sources: list[ReportSource] = Field(default_factory=list)
    claim_evidence_relations: list[ClaimEvidenceRelation] = Field(
        default_factory=list
    )
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class ReportResponse(_ReportModel):
    """Minimum HTTP response for a Markdown Report lookup."""

    report_id: str = Field(pattern=REPORT_ID_PATTERN)
    research_run_id: str = Field(pattern=RESEARCH_RUN_ID_PATTERN)
    title: str = Field(min_length=1)
    status: ReportStatus
    created_at: datetime
    published_at: datetime | None = None
    markdown: str = Field(min_length=1)

    @classmethod
    def from_report(cls, report: Report) -> "ReportResponse":
        """Build the public response and render Markdown at the boundary."""

        from app.reporting.markdown import render_markdown

        return cls(
            report_id=report.report_id,
            research_run_id=report.research_run_id,
            title=report.title,
            status=report.status,
            created_at=report.created_at,
            published_at=report.published_at,
            markdown=render_markdown(report),
        )


ReportInput: TypeAlias = Report | Mapping[str, Any]


@runtime_checkable
class ReportRepository(Protocol):
    """Storage boundary required by the Report route."""

    async def save(self, report: Report) -> Report:
        """Persist and return a Report."""

    async def get_by_research_run_id(self, research_run_id: str) -> Report | None:
        """Return the Report for a ResearchRun, if one exists."""


class InMemoryReportRepository:
    """Deterministic repository adapter for local development and tests."""

    def __init__(self, reports: Iterable[ReportInput] | Mapping[str, ReportInput] = ()) -> None:
        self._reports: dict[str, Report] = {}
        self._report_ids_by_research_run: dict[str, str] = {}

        if isinstance(reports, Mapping) and "report_id" not in reports:
            report_values = reports.values()
        elif isinstance(reports, Mapping):
            report_values = (reports,)
        else:
            report_values = reports

        for report in report_values:
            self.put(report)

    def put(self, report: ReportInput) -> Report:
        """Validate and synchronously store a Report for test setup."""

        record = report if isinstance(report, Report) else Report.model_validate(report)
        stored = record.model_copy(deep=True)
        previous_report_id = self._report_ids_by_research_run.get(
            stored.research_run_id
        )
        if previous_report_id is not None and previous_report_id != stored.report_id:
            self._reports.pop(previous_report_id, None)
        self._reports[stored.report_id] = stored
        self._report_ids_by_research_run[stored.research_run_id] = stored.report_id
        return stored.model_copy(deep=True)

    add = put

    async def save(self, report: ReportInput) -> Report:
        """Persist a Report through the async repository boundary."""

        return self.put(report)

    async def create(self, report: ReportInput) -> Report:
        """Alias matching the existing ResearchRun repository vocabulary."""

        return await self.save(report)

    async def get_by_research_run_id(self, research_run_id: str) -> Report | None:
        report_id = self._report_ids_by_research_run.get(research_run_id)
        report = self._reports.get(report_id) if report_id is not None else None
        return report.model_copy(deep=True) if report is not None else None

    async def get_by_id(self, report_id: str) -> Report | None:
        report = self._reports.get(report_id)
        return report.model_copy(deep=True) if report is not None else None

    async def get(self, report_id: str) -> Report | None:
        """Compatibility alias for repository adapters using ``get``."""

        return await self.get_by_id(report_id)

    def __len__(self) -> int:
        return len(self._reports)


# Common domain spellings keep the small contract easy to discover without
# duplicating model definitions.
Claim = ReportClaim
Evidence = ReportEvidence
Source = ReportSource
ReportRecord = Report
ReportModel = Report


__all__ = [
    "Claim",
    "ClaimEvidenceRelation",
    "ClaimEvidenceRelationType",
    "ClaimStatus",
    "Evidence",
    "EvidenceKind",
    "InMemoryReportRepository",
    "Report",
    "ReportClaim",
    "ReportEvidence",
    "ReportInput",
    "ReportModel",
    "ReportRecord",
    "ReportRepository",
    "ReportResponse",
    "ReportSource",
    "ReportStatement",
    "ReportStatus",
    "Source",
]
