"""ResearchRun HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.domains.research_run import (
    CreateResearchRunRequest,
    InMemoryResearchRunRepository,
    ResearchRunRepository,
    ResearchRunResponse,
    create_research_run,
)


class ResearchRunNotFoundResponse(BaseModel):
    """Stable error body for missing ResearchRuns."""

    error_code: str
    message: str


router = APIRouter(prefix="/v1/research-runs", tags=["research-runs"])
_repository = InMemoryResearchRunRepository()


def get_research_run_repository() -> ResearchRunRepository:
    """Provide the repository adapter used by the route.

    Applications and tests can replace this dependency with a persistent
    implementation later without changing the HTTP contract.
    """

    return _repository


# Short alias for callers that use the generic dependency name.
get_repository = get_research_run_repository
RepositoryDependency = Annotated[
    ResearchRunRepository, Depends(get_research_run_repository)
]


@router.post(
    "",
    response_model=ResearchRunResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"model": ResearchRunResponse},
    },
)
async def create_research_run_route(
    request: CreateResearchRunRequest,
    repository: RepositoryDependency,
) -> ResearchRunResponse:
    """Create a queued ResearchRun without enqueueing worker work yet."""

    research_run = create_research_run(request)
    stored = await repository.create(research_run)
    return ResearchRunResponse.model_validate(stored.model_dump())


@router.get(
    "/{research_run_id}",
    response_model=ResearchRunResponse,
    response_model_exclude_none=True,
    responses={status.HTTP_404_NOT_FOUND: {"model": ResearchRunNotFoundResponse}},
)
async def get_research_run_route(
    research_run_id: str,
    repository: RepositoryDependency,
) -> ResearchRunResponse | JSONResponse:
    """Fetch a ResearchRun by ID or return a stable 404 error."""

    research_run = await repository.get_by_id(research_run_id)
    if research_run is None:
        error = ResearchRunNotFoundResponse(
            error_code="research_run_not_found",
            message="Research run not found.",
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error.model_dump(mode="json"),
        )
    return ResearchRunResponse.model_validate(research_run.model_dump())


__all__ = [
    "ResearchRunNotFoundResponse",
    "create_research_run_route",
    "get_research_run_repository",
    "get_research_run_route",
    "router",
]
