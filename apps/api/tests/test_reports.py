from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.reports import get_report_repository  # noqa: E402
from app.domains.report import (  # noqa: E402
    ClaimEvidenceRelation,
    ClaimEvidenceRelationType,
    ClaimStatus,
    EvidenceKind,
    InMemoryReportRepository,
    Report,
    ReportClaim,
    ReportEvidence,
    ReportSource,
    ReportStatement,
    ReportStatus,
)
from app.main import app  # noqa: E402
from app.reporting.markdown import render_markdown  # noqa: E402


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def report_fixture() -> Report:
    source = ReportSource(
        source_id="src_primary",
        research_run_id="rr_report_001",
        title="Primary source",
        locator="https://example.test/source",
        original_content="Original source text.\nIt is not an AI summary.",
    )
    evidence = ReportEvidence(
        evidence_id="ev_supported",
        source_id=source.source_id,
        research_run_id=source.research_run_id,
        kind=EvidenceKind.SUMMARY,
        quote_or_summary="AI-generated summary of the relevant passage.",
        locator="section-2",
    )
    supported_claim = ReportClaim(
        claim_id="clm_supported",
        research_run_id=source.research_run_id,
        text="The primary source supports the first claim.",
        status=ClaimStatus.SUPPORTED,
    )
    unsupported_claim = ReportClaim(
        claim_id="clm_unsupported",
        research_run_id=source.research_run_id,
        text="This claim has no sufficient evidence.",
        status=ClaimStatus.UNSUPPORTED,
    )
    return Report(
        report_id="rpt_report_001",
        research_run_id=source.research_run_id,
        title="Cited report",
        status=ReportStatus.READY,
        created_at=NOW,
        statements=[
            ReportStatement(
                statement_id="stmt_unsupported",
                report_id="rpt_report_001",
                claim_id=unsupported_claim.claim_id,
                position=1,
                text=unsupported_claim.text,
            ),
            ReportStatement(
                statement_id="stmt_supported",
                report_id="rpt_report_001",
                claim_id=supported_claim.claim_id,
                position=0,
                text=supported_claim.text,
            ),
        ],
        claims=[unsupported_claim, supported_claim],
        evidence=[evidence],
        sources=[source],
        claim_evidence_relations=[
            ClaimEvidenceRelation(
                relation_id="rel_supported",
                claim_id=supported_claim.claim_id,
                evidence_id=evidence.evidence_id,
                relation_type=ClaimEvidenceRelationType.SUPPORTS,
            )
        ],
    )


def test_markdown_is_deterministic_and_keeps_citation_path_per_statement() -> None:
    report = report_fixture()
    shuffled = report.model_copy(
        deep=True,
        update={
            "statements": list(reversed(report.statements)),
            "claims": list(reversed(report.claims)),
            "claim_evidence_relations": list(reversed(report.claim_evidence_relations)),
        },
    )

    rendered = render_markdown(report)

    assert rendered == render_markdown(shuffled)
    assert "Claim `clm_supported` -> Evidence `ev_supported` -> Source `src_primary`" in rendered
    assert "Source original:" in rendered
    assert "Original source text." in rendered
    assert "AI summary:" in rendered
    assert "AI-generated summary of the relevant passage." in rendered
    assert "Warning: `unsupported`" in rendered
    assert "No Evidence is linked to this Claim." in rendered


def test_in_memory_report_repository_round_trips_a_defensive_copy() -> None:
    async def scenario() -> None:
        repository = InMemoryReportRepository()
        report = report_fixture()

        saved = await repository.save(report)
        loaded = await repository.get_by_research_run_id(report.research_run_id)

        assert saved == report
        assert loaded == report
        assert loaded is not report
        assert await repository.get_by_research_run_id("rr_missing") is None

    asyncio.run(scenario())


async def asgi_request(method: str, path: str) -> tuple[int, dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    request_consumed = False

    async def receive() -> dict[str, Any]:
        nonlocal request_consumed
        if request_consumed:
            return {"type": "http.disconnect"}
        request_consumed = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "root_path": "",
        },
        receive,
        send,
    )

    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = next(
        message["body"]
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(response_body)


def test_report_get_contract_and_stable_not_found_error() -> None:
    async def scenario() -> None:
        repository = InMemoryReportRepository([report_fixture()])
        app.dependency_overrides[get_report_repository] = lambda: repository
        try:
            response_status, body = await asgi_request(
                "GET", "/v1/research-runs/rr_report_001/report"
            )
            assert response_status == 200
            assert body["report_id"] == "rpt_report_001"
            assert body["research_run_id"] == "rr_report_001"
            assert body["status"] == "ready"
            assert "markdown" in body
            assert "AI summary:" in body["markdown"]

            missing_status, missing = await asgi_request(
                "GET", "/v1/research-runs/rr_missing/report"
            )
            assert missing_status == 404
            assert missing == {
                "error_code": "report_not_found",
                "message": "Report not found.",
            }
        finally:
            app.dependency_overrides.pop(get_report_repository, None)

    asyncio.run(scenario())
