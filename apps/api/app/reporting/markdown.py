"""Deterministic Markdown rendering for cited ClaimGraph Reports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from app.domains.report import (
    ClaimEvidenceRelation,
    ClaimEvidenceRelationType,
    ClaimStatus,
    EvidenceKind,
    Report,
    ReportClaim,
    ReportEvidence,
    ReportSource,
)


def _coerce_report(report: Report | Mapping[str, Any]) -> Report:
    if isinstance(report, Report):
        return report
    if "body" in report and isinstance(report["body"], Mapping):
        return Report.model_validate(report["body"])
    return Report.model_validate(report)


def _single_line(value: str) -> str:
    """Keep user text from changing the renderer's Markdown structure."""

    return " ".join(value.replace("\r\n", "\n").replace("\r", "\n").splitlines())


def _normalise_block(value: str) -> list[str]:
    return value.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _code_fence(value: str) -> str:
    """Choose a fence longer than any fence sequence in source content."""

    max_backticks = 0
    max_tildes = 0
    current_backticks = 0
    current_tildes = 0
    for character in value:
        if character == "`":
            current_backticks += 1
            current_tildes = 0
            max_backticks = max(max_backticks, current_backticks)
        elif character == "~":
            current_tildes += 1
            current_backticks = 0
            max_tildes = max(max_tildes, current_tildes)
        else:
            current_backticks = 0
            current_tildes = 0
    if max_backticks <= 3 and max_tildes <= 3:
        return "```"
    if max_backticks <= max_tildes:
        return "~" * max(3, max_tildes + 1)
    return "`" * max(3, max_backticks + 1)


def _append_blockquote(lines: list[str], text: str, indent: str) -> None:
    for line in _normalise_block(text):
        lines.append(f"{indent}> {line}" if line else f"{indent}>")


def _append_code_block(lines: list[str], text: str, indent: str) -> None:
    fence = _code_fence(text)
    lines.append(f"{indent}{fence}text")
    for line in _normalise_block(text):
        lines.append(f"{indent}{line}")
    lines.append(f"{indent}{fence}")


def _statement_rows(
    report: Report,
) -> list[tuple[int, str, str, ReportClaim | None]]:
    claims_by_id = {claim.claim_id: claim for claim in report.claims}
    if report.statements:
        statements = sorted(
            report.statements,
            key=lambda statement: (
                statement.position,
                statement.claim_id,
                statement.statement_id,
            ),
        )
        rows: list[tuple[int, str, str, ReportClaim | None]] = []
        for statement in statements:
            claim = claims_by_id.get(statement.claim_id)
            text = statement.text or (claim.text if claim is not None else None)
            rows.append(
                (
                    statement.position,
                    statement.claim_id,
                    text or "Claim text unavailable.",
                    claim,
                )
            )
        return rows

    claims = sorted(report.claims, key=lambda claim: (claim.claim_id, claim.text))
    return [
        (position, claim.claim_id, claim.text, claim)
        for position, claim in enumerate(claims)
    ]


def _relation_key(relation: ClaimEvidenceRelation) -> tuple[str, str, str]:
    return (
        relation.evidence_id,
        relation.relation_type.value,
        relation.relation_id or "",
    )


def _unsupported_reason(
    claim: ReportClaim | None,
    relations: list[ClaimEvidenceRelation],
    evidence_by_id: dict[str, ReportEvidence],
) -> str:
    if claim is not None and claim.unsupported_reason:
        return claim.unsupported_reason

    has_linked_support = any(
        relation.relation_type is ClaimEvidenceRelationType.SUPPORTS
        and relation.evidence_id in evidence_by_id
        for relation in relations
    )
    if not relations:
        return "No Evidence is linked to this Claim."
    if not has_linked_support:
        return "Linked Evidence does not sufficiently support this Claim."
    return "The Claim is marked unsupported despite linked supporting Evidence."


def _render_source_details(
    lines: list[str],
    source: ReportSource | None,
    source_id: str,
) -> None:
    if source is None:
        lines.append(f"    - Source original: unavailable (`{source_id}` not found).")
        return

    lines.append(
        f"    - Source: `{source.source_id}` — {_single_line(source.title)}"
    )
    lines.append(f"      - Locator: `{source.locator}`")
    lines.append("      - Source original:")
    if source.original_content is None:
        lines.append("        unavailable.")
    else:
        _append_code_block(lines, source.original_content, "        ")


def _render_evidence_details(
    lines: list[str],
    evidence: ReportEvidence | None,
    source_by_id: dict[str, ReportSource],
    evidence_id: str,
) -> None:
    if evidence is None:
        lines.append(f"    - Evidence: `{evidence_id}` not found.")
        return

    lines.append(f"    - Evidence kind: `{evidence.kind.value}`")
    if evidence.locator is not None:
        lines.append(f"    - Evidence locator: `{evidence.locator}`")
    if evidence.kind is EvidenceKind.SUMMARY:
        lines.append("    - AI summary:")
    elif evidence.kind is EvidenceKind.QUOTE:
        lines.append("    - Evidence quote:")
    else:
        lines.append("    - Evidence detail:")
    _append_blockquote(lines, evidence.quote_or_summary, "      ")
    _render_source_details(lines, source_by_id.get(evidence.source_id), evidence.source_id)


def render_markdown(report: Report | Mapping[str, Any]) -> str:
    """Render a Report snapshot into stable, citation-aware Markdown.

    Statement and relation input order never affects the output.  Statements
    are ordered by their explicit position, while each Claim's relation path
    is ordered by Evidence ID, relation type, and relation ID.
    """

    record = _coerce_report(report)
    claims_by_id = {claim.claim_id: claim for claim in record.claims}
    evidence_by_id = {item.evidence_id: item for item in record.evidence}
    sources_by_id = {source.source_id: source for source in record.sources}
    relations_by_claim: defaultdict[str, list[ClaimEvidenceRelation]] = defaultdict(
        list
    )
    for relation in record.claim_evidence_relations:
        relations_by_claim[relation.claim_id].append(relation)
    for relations in relations_by_claim.values():
        relations.sort(key=_relation_key)

    lines = [
        f"# {_single_line(record.title)}",
        "",
        f"ResearchRun: `{record.research_run_id}`",
        f"Report status: `{record.status.value}`",
        "",
        "## Statements",
        "",
    ]

    rows = _statement_rows(record)
    if not rows:
        lines.append("_No statements available._")
    for index, (_, statement_claim_id, statement_text, claim) in enumerate(
        rows, start=1
    ):
        lines.extend(
            [
                f"### {index}. {_single_line(statement_text)}",
                "",
                f"- Claim: `{statement_claim_id}`",
            ]
        )
        if claim is None:
            lines.append("- Claim status: unavailable.")
        else:
            lines.append(f"- Claim status: `{claim.status.value}`")

        relations = relations_by_claim.get(statement_claim_id, [])
        if claim is not None and claim.status is ClaimStatus.UNSUPPORTED:
            reason = _unsupported_reason(claim, relations, evidence_by_id)
            lines.append(f"- Warning: `unsupported` — {reason}")

        if not relations:
            lines.append("  - Evidence path: none (no linked Evidence).")
            lines.append("")
            continue

        for relation in relations:
            evidence = evidence_by_id.get(relation.evidence_id)
            source_id = evidence.source_id if evidence is not None else "missing"
            lines.append(
                "  - Evidence path: "
                f"Claim `{statement_claim_id}` -> Evidence `{relation.evidence_id}` "
                f"-> Source `{source_id}`"
            )
            lines.append(f"    - Relation: `{relation.relation_type.value}`")
            _render_evidence_details(
                lines,
                evidence,
                sources_by_id,
                relation.evidence_id,
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


render_report_markdown = render_markdown


__all__ = ["render_markdown", "render_report_markdown"]
