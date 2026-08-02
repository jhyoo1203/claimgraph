"""ResearchRun domain contract and repository boundary.

The API does not persist ResearchRuns yet.  The repository protocol keeps the
route independent from that future storage choice while the in-memory
implementation makes the contract usable in local development and tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SHA256_PATTERN = r"^sha256:[a-f0-9]{64}$"
RESEARCH_RUN_ID_PATTERN = r"^rr_[A-Za-z0-9_-]+$"


class ResearchRunStatus(StrEnum):
    """Lifecycle states exposed by the ResearchRun contract."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchRunOutputFormat(StrEnum):
    """Formats supported by the initial ResearchRun API contract."""

    MARKDOWN = "markdown"
    JSON = "json"
    BOTH = "both"


class ResearchRunBudget(BaseModel):
    """Execution limits recorded with a ResearchRun.

    ``max_tasks`` is the required MVP limit.  The other limits are optional so
    the API can add a caller's token, cost, or wall-clock ceiling without
    requiring every client to provide all dimensions of a budget.
    """

    model_config = ConfigDict(extra="forbid")

    max_tasks: int = Field(default=10, ge=1, le=1_000)
    max_tokens: int | None = Field(default=None, ge=1, le=10_000_000)
    max_cost_usd: float | None = Field(default=None, gt=0, le=1_000)
    max_duration_seconds: int | None = Field(default=None, ge=1, le=86_400)

    @model_validator(mode="before")
    @classmethod
    def accept_task_budget_number(cls, value: object) -> object:
        """Accept a scalar task limit while keeping the response structured.

        Early MVP callers commonly have only one budget dimension.  Treating a
        positive integer as ``max_tasks`` keeps that payload compatible with
        the structured budget contract and still lets Pydantic enforce bounds.
        """

        if isinstance(value, bool):
            raise ValueError("budget must be an object or positive integer")
        if isinstance(value, int):
            return {"max_tasks": value}
        return value


class _UtcTimestampModel(BaseModel):
    """Shared UTC-aware timestamp validation for public ResearchRun models."""

    @field_validator("created_at", check_fields=False)
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a UTC timezone")
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be in UTC")
        return value.astimezone(timezone.utc)


class CreateResearchRunRequest(BaseModel):
    """Validated payload accepted by ``POST /v1/research-runs``."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    input_hash: str = Field(pattern=SHA256_PATTERN)
    output_format: ResearchRunOutputFormat
    budget: ResearchRunBudget

    @field_validator("question")
    @classmethod
    def require_question_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


class ResearchRun(_UtcTimestampModel):
    """A ResearchRun record returned by the API."""

    model_config = ConfigDict(extra="forbid")

    research_run_id: str = Field(pattern=RESEARCH_RUN_ID_PATTERN)
    question: str = Field(min_length=1)
    status: ResearchRunStatus
    input_hash: str = Field(pattern=SHA256_PATTERN)
    output_format: ResearchRunOutputFormat
    budget: ResearchRunBudget
    created_at: datetime

    @field_validator("question")
    @classmethod
    def require_question_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


class ResearchRunResponse(ResearchRun):
    """Response model kept separate for an explicit API boundary."""


# Resource-oriented aliases make the contract discoverable under both common
# naming conventions without duplicating model definitions.
ResearchRunCreateRequest = CreateResearchRunRequest
ResearchRunCreateResponse = ResearchRunResponse
OutputFormat = ResearchRunOutputFormat
Budget = ResearchRunBudget


@runtime_checkable
class ResearchRunRepository(Protocol):
    """Storage boundary required by the ResearchRun routes."""

    async def create(self, research_run: ResearchRun) -> ResearchRun:
        """Persist and return a ResearchRun."""

    async def get_by_id(self, research_run_id: str) -> ResearchRun | None:
        """Return a ResearchRun or ``None`` when it does not exist."""


class InMemoryResearchRunRepository:
    """Small repository implementation for tests and local API smoke checks."""

    def __init__(self) -> None:
        self._research_runs: dict[str, ResearchRun] = {}

    async def create(self, research_run: ResearchRun) -> ResearchRun:
        stored = research_run.model_copy(deep=True)
        self._research_runs[stored.research_run_id] = stored
        return stored.model_copy(deep=True)

    async def get_by_id(self, research_run_id: str) -> ResearchRun | None:
        research_run = self._research_runs.get(research_run_id)
        return research_run.model_copy(deep=True) if research_run else None

    # These aliases keep the in-memory adapter convenient for unit tests and
    # make its CRUD vocabulary compatible with repository implementations that
    # call the methods ``save`` and ``get``.
    async def save(self, research_run: ResearchRun) -> ResearchRun:
        return await self.create(research_run)

    async def get(self, research_run_id: str) -> ResearchRun | None:
        return await self.get_by_id(research_run_id)


def create_research_run(
    request: CreateResearchRunRequest,
    *,
    now: datetime | None = None,
    id_factory: Callable[[], str] | None = None,
) -> ResearchRun:
    """Build a queued ResearchRun with a server-issued UTC timestamp and ID."""

    created_at = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("timestamp must include a UTC timezone")
    if created_at.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be in UTC")

    research_run_id = id_factory() if id_factory else f"rr_{uuid4().hex}"
    return ResearchRun(
        research_run_id=research_run_id,
        question=request.question,
        status=ResearchRunStatus.QUEUED,
        input_hash=request.input_hash,
        output_format=request.output_format,
        budget=request.budget,
        created_at=created_at.astimezone(timezone.utc),
    )


__all__ = [
    "Budget",
    "CreateResearchRunRequest",
    "InMemoryResearchRunRepository",
    "OutputFormat",
    "ResearchRun",
    "ResearchRunBudget",
    "ResearchRunCreateRequest",
    "ResearchRunCreateResponse",
    "ResearchRunOutputFormat",
    "ResearchRunRepository",
    "ResearchRunResponse",
    "ResearchRunStatus",
    "create_research_run",
]
