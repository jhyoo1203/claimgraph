"""Source lookup HTTP contract."""

from __future__ import annotations

import inspect
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field

from app.db.source_repository import InMemorySourceRepository, SourceRepository
from app.domains.sources import SourceRecord, SourceResponse


router = APIRouter(prefix="/v1/sources", tags=["sources"])


class SourceNotFoundError(LookupError):
    """Raised when a Source ID is not present in the configured repository."""

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        super().__init__(f"Source '{source_id}' was not found.")


class SourceErrorResponse(BaseModel):
    """Stable error body for Source lookup failures."""

    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    message: str = Field(min_length=1)


source_repository: SourceRepository = InMemorySourceRepository()


def get_source_repository() -> SourceRepository:
    """FastAPI dependency for the Source persistence boundary."""

    return source_repository


RepositoryResult = SourceRecord | dict[str, Any] | None


async def _read_source(repository: SourceRepository, source_id: str) -> RepositoryResult:
    result = repository.get_source(source_id)
    if inspect.isawaitable(result):
        return await result
    return result


@router.get(
    "/{source_id}",
    response_model=SourceResponse,
    responses={
        404: {
            "description": "Source was not found",
            "model": SourceErrorResponse,
        }
    },
)
async def get_source(
    source_id: Annotated[str, Path(min_length=1)],
    repository: Annotated[SourceRepository, Depends(get_source_repository)],
) -> SourceResponse:
    """Return Source metadata and original content by stable Source ID."""

    source = await _read_source(repository, source_id)
    if source is None:
        raise SourceNotFoundError(source_id)
    return SourceResponse.from_record(source)
