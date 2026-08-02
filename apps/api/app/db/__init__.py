"""Persistence boundaries for ClaimGraph domain objects."""

from app.db.source_repository import (
    InMemorySourceRepository,
    SourceRepository,
    SourceRepositoryProtocol,
)

__all__ = [
    "InMemorySourceRepository",
    "SourceRepository",
    "SourceRepositoryProtocol",
]
