"""Report HTTP routes."""

from __future__ import annotations

import inspect
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.domains.report import (
    InMemoryReportRepository,
    Report,
    ReportRepository,
    ReportResponse,
)


class ReportNotFoundResponse(BaseModel):
    """Stable error body for a missing Report."""

    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    message: str = Field(min_length=1)


router = APIRouter(prefix="/v1/research-runs", tags=["reports"])
report_repository = InMemoryReportRepository()


def get_report_repository() -> ReportRepository:
    """Provide the Report persistence boundary used by the route."""

    return report_repository


ReportRepositoryDependency = Annotated[
    ReportRepository, Depends(get_report_repository)
]

# Short alias for callers that use the generic dependency name.
get_repository = get_report_repository


async def _read_report(
    repository: ReportRepository,
    research_run_id: str,
) -> Report | None:
    """Read a Report while allowing synchronous test adapters as well."""

    result: Any = repository.get_by_research_run_id(research_run_id)
    if inspect.isawaitable(result):
        return await result
    return result


@router.get(
    "/{research_run_id}/report",
    response_model=ReportResponse,
    response_model_exclude_none=True,
    responses={status.HTTP_404_NOT_FOUND: {"model": ReportNotFoundResponse}},
)
async def get_report_route(
    research_run_id: str,
    repository: ReportRepositoryDependency,
) -> ReportResponse | JSONResponse:
    """Return a deterministic cited Markdown Report or a stable 404."""

    report = await _read_report(repository, research_run_id)
    if report is None:
        error = ReportNotFoundResponse(
            error_code="report_not_found",
            message="Report not found.",
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error.model_dump(mode="json"),
        )

    return ReportResponse.from_report(report)


__all__ = [
    "ReportNotFoundResponse",
    "get_report_repository",
    "get_report_route",
    "get_repository",
    "report_repository",
    "router",
]
