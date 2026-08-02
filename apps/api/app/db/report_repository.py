"""Report repository exports kept at the persistence boundary."""

from app.domains.report import InMemoryReportRepository, ReportRepository

__all__ = ["InMemoryReportRepository", "ReportRepository"]
