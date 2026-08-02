"""Reproducible Phase 1 vertical-slice evaluator.

The evaluator is the intentionally small integration adapter for CG-14.  It
uses the existing in-memory contracts only:

``CreateResearchRunRequest`` -> ``FakeSearchProvider``/``retrieve_sources``
-> ``FixtureExtractor`` (once per Source) -> API ``Report`` repository and
Markdown route -> the Web mock ``{report: ...}`` envelope.

There is no network, model, queue, database, Redis, clock, or authentication in
this path.  The fixture supplies the deterministic search response and claim
candidates so the evaluator tests orchestration and traceability rather than
answer quality from an LLM.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "api"
for import_path in (str(ROOT), str(API_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.api.reports import get_report_route  # noqa: E402
from app.domains.report import (  # noqa: E402
    ClaimEvidenceRelation,
    ClaimEvidenceRelationType,
    ClaimStatus,
    EvidenceKind,
    InMemoryReportRepository,
    Report,
    ReportClaim,
    ReportEvidence,
    ReportResponse,
    ReportSource,
    ReportStatement,
    ReportStatus,
)
from app.domains.research_run import (  # noqa: E402
    CreateResearchRunRequest,
    InMemoryResearchRunRepository,
    ResearchRun,
    ResearchRunOutputFormat,
    ResearchRunStatus,
    ResearchRunBudget,
    create_research_run,
)
from app.reporting.markdown import render_markdown  # noqa: E402
from apps.worker.extractor import (  # noqa: E402
    ExtractorInput,
    FixtureClaim,
    FixtureEvidence,
    FixtureExtractor,
)
from apps.worker.providers.search import FakeSearchProvider, SearchCandidate  # noqa: E402
from apps.worker.retrieval import RetrievalStatus, retrieve_sources  # noqa: E402
from apps.worker.source_snapshots import (  # noqa: E402
    InMemorySourceSnapshotStore,
    SourceSnapshot,
)
from apps.worker.state import (  # noqa: E402
    ResearchRunStatus as WorkerResearchRunStatus,
    transition_research_run_status,
)


SCHEMA_VERSION = "2026-08-02"
FIXTURE_MODEL = "fixture-extractor"
FIXTURE_PROMPT_VERSION = "fixture-extractor@1"
FIXTURE_PRODUCER = {"name": "claimgraph-phase1-evaluator", "version": "0.1.0"}
QUESTIONS_PATH = ROOT / "tests" / "eval" / "questions.json"
EXPECTATIONS_DIR = ROOT / "tests" / "eval" / "expectations"
FIXTURE_PATH = ROOT / "tests" / "eval" / "phase1_fixture.json"
SCHEMA_PATH = ROOT / "packages" / "schemas" / "claimgraph-contract.schema.json"


JsonObject = dict[str, Any]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return f"sha256:{sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{sha256(_canonical_json(parts).encode('utf-8')).hexdigest()[:24]}"


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Phase 1 fixture timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _load_json(path: Path) -> JsonObject | list[JsonObject]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be an array")
    return [
        _require_mapping(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    ]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class Phase1Run:
    """All artifacts produced by one deterministic Phase 1 question."""

    question_id: str
    research_run: ResearchRun
    snapshots: tuple[SourceSnapshot, ...]
    artifact: JsonObject
    report: Report
    report_response: ReportResponse
    web_mock_response: JsonObject
    provider_calls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase1QuestionResult:
    question_id: str
    status: str
    report_id: str | None
    citation_paths: tuple[str, ...]
    unsupported_claim_ids: tuple[str, ...]
    checks: Mapping[str, bool]
    error: str | None = None

    def to_dict(self) -> JsonObject:
        result: JsonObject = {
            "question_id": self.question_id,
            "status": self.status,
            "pass": self.status == "pass",
            "report_id": self.report_id,
            "report_citation_paths": list(self.citation_paths),
            "unsupported_claim_ids": list(self.unsupported_claim_ids),
            "checks": dict(self.checks),
        }
        if self.error is not None:
            result["error"] = self.error
        return result


class Phase1IntegrationAdapter:
    """Connect existing MVP ports without adding a Phase 2 runtime.

    A search response can contain multiple canonical Source records.  The
    existing extractor intentionally handles one Source at a time, so this
    adapter calls it once for each returned Source and deterministically merges
    the Claim/Evidence edges by the fixture claim key.  This keeps the CG-11
    and CG-12 boundaries unchanged while allowing the five evaluation questions
    to cite more than one source type.
    """

    def __init__(self, fixture: Mapping[str, Any]) -> None:
        self._fixture = fixture
        self._retrieved_at = _parse_timestamp(
            _require_text(fixture.get("retrieved_at"), "fixture.retrieved_at")
        )

    async def run(self, question_id: str, question: str) -> Phase1Run:
        question_fixture = _require_mapping(
            _require_mapping(self._fixture.get("questions"), "fixture.questions").get(
                question_id
            ),
            f"fixture.questions.{question_id}",
        )
        sources_fixture = _require_list(
            question_fixture.get("sources"), f"{question_id}.sources"
        )
        claims_fixture = _require_list(
            question_fixture.get("claims"), f"{question_id}.claims"
        )
        run_id = f"rr_phase1_{question_id}"
        input_hash = _sha256(
            {
                "question_id": question_id,
                "question": question,
                "fixture": question_fixture,
            }
        )

        research_run_repository = InMemoryResearchRunRepository()
        request = CreateResearchRunRequest(
            question=question,
            input_hash=input_hash,
            output_format=ResearchRunOutputFormat.MARKDOWN,
            budget=ResearchRunBudget(max_tasks=len(sources_fixture) + 2),
        )
        research_run = create_research_run(
            request,
            now=self._retrieved_at,
            id_factory=lambda: run_id,
        )
        await research_run_repository.create(research_run)

        research_run = await self._transition_run(
            research_run_repository,
            research_run,
            ResearchRunStatus.RUNNING,
        )

        candidates = tuple(
            SearchCandidate(
                locator=_require_text(source.get("locator"), "source.locator"),
                title=_require_text(source.get("title"), "source.title"),
                content=_require_text(source.get("content"), "source.content"),
                source_type=_require_text(
                    source.get("source_type"), "source.source_type"
                ),
                publisher=source.get("publisher"),
                metadata={
                    "eval_source_type": _require_text(
                        source.get("eval_source_type"), "source.eval_source_type"
                    )
                },
            )
            for source in sources_fixture
        )
        provider = FakeSearchProvider({question: candidates})
        snapshot_store = InMemorySourceSnapshotStore()
        retrieval = await retrieve_sources(
            question,
            run_id,
            provider,
            snapshot_store,
            retrieved_at=self._retrieved_at,
        )
        if retrieval.status is not RetrievalStatus.SUCCEEDED:
            raise AssertionError(f"retrieval did not succeed: {retrieval.error_code}")
        if len(provider.calls) != 1 or provider.calls != (question,):
            raise AssertionError(f"expected one search call, got {provider.calls!r}")

        snapshots = tuple(retrieval.sources)
        if len(snapshots) != len(sources_fixture):
            raise AssertionError("retrieval did not preserve every fixture Source")
        persisted_snapshots = tuple(
            [
                await snapshot_store.get_by_id(snapshot.source_id)
                for snapshot in snapshots
            ]
        )
        if any(snapshot is None for snapshot in persisted_snapshots):
            raise AssertionError("a Source snapshot was not persisted")

        artifact = self._extract_and_merge(
            question_id=question_id,
            question=question,
            run_id=run_id,
            input_hash=input_hash,
            snapshots=snapshots,
            claims_fixture=claims_fixture,
        )
        Draft202012Validator(
            _load_json(SCHEMA_PATH), format_checker=FormatChecker()
        ).validate(artifact)

        report = self._build_report(
            question_id=question_id,
            question=question,
            artifact=artifact,
            snapshots=snapshots,
        )
        report_repository = InMemoryReportRepository()
        await report_repository.save(report)
        route_response = await get_report_route(run_id, report_repository)
        if not isinstance(route_response, ReportResponse):
            raise AssertionError("Report route did not return a ReportResponse")
        web_mock_response = self._to_web_mock_response(
            question=question,
            report=report,
            markdown=route_response.markdown,
        )

        completed_run = await self._transition_run(
            research_run_repository,
            research_run,
            ResearchRunStatus.COMPLETED,
        )
        return Phase1Run(
            question_id=question_id,
            research_run=completed_run,
            snapshots=snapshots,
            artifact=artifact,
            report=report,
            report_response=route_response,
            web_mock_response=web_mock_response,
            provider_calls=provider.calls,
        )

    async def _transition_run(
        self,
        repository: InMemoryResearchRunRepository,
        research_run: ResearchRun,
        next_status: ResearchRunStatus,
    ) -> ResearchRun:
        current_worker_status = WorkerResearchRunStatus(research_run.status.value)
        transition_research_run_status(
            current_worker_status,
            WorkerResearchRunStatus(next_status.value),
        )
        updated = research_run.model_copy(update={"status": next_status})
        return await repository.create(updated)

    def _extract_and_merge(
        self,
        *,
        question_id: str,
        question: str,
        run_id: str,
        input_hash: str,
        snapshots: tuple[SourceSnapshot, ...],
        claims_fixture: list[Mapping[str, Any]],
    ) -> JsonObject:
        extractor = FixtureExtractor()
        outputs: list[tuple[int, list[str], Any]] = []
        for source_index, snapshot in enumerate(snapshots):
            source_claims: list[FixtureClaim] = []
            source_claim_keys: list[str] = []
            for claim_index, claim in enumerate(claims_fixture):
                evidence_fixture = [
                    evidence
                    for evidence in _require_list(
                        claim.get("evidence"),
                        f"{question_id}.claims[{claim_index}].evidence",
                    )
                    if evidence.get("source_index") == source_index
                ]
                if evidence_fixture:
                    source_claims.append(
                        FixtureClaim(
                            text=_require_text(claim.get("text"), "claim.text"),
                            confidence=claim.get("confidence", 0.8),
                            evidence=tuple(
                                FixtureEvidence(
                                    quote_or_summary=_require_text(
                                        evidence.get("quote_or_summary"),
                                        "evidence.quote_or_summary",
                                    ),
                                    locator=_require_text(
                                        evidence.get("locator"), "evidence.locator"
                                    ),
                                    kind=evidence.get("kind", "quote"),
                                )
                                for evidence in evidence_fixture
                            ),
                        )
                    )
                    source_claim_keys.append(
                        _require_text(claim.get("key"), "claim.key")
                    )
                elif not claim.get("evidence") and claim.get("source_index") == source_index:
                    source_claims.append(
                        FixtureClaim(
                            text=_require_text(claim.get("text"), "claim.text"),
                            confidence=claim.get("confidence", 0.8),
                        )
                    )
                    source_claim_keys.append(
                        _require_text(claim.get("key"), "claim.key")
                    )

            if not source_claims:
                continue
            output = extractor.extract(
                ExtractorInput(
                    research_run_id=run_id,
                    source_id=snapshot.source_id,
                    source_type=snapshot.source_type,
                    title=snapshot.title,
                    locator=snapshot.locator,
                    snapshot=snapshot.original_content,
                    claims=tuple(source_claims),
                    question=question,
                    retrieved_at=self._retrieved_at.isoformat().replace("+00:00", "Z"),
                )
            )
            outputs.append((source_index, source_claim_keys, output))

        claims_by_key: dict[str, JsonObject] = {}
        evidence: list[JsonObject] = []
        relations: list[JsonObject] = []
        tasks: list[JsonObject] = []
        claim_id_by_key = {
            _require_text(claim.get("key"), "claim.key"): _stable_id(
                "clm", run_id, _require_text(claim.get("key"), "claim.key")
            )
            for claim in claims_fixture
        }

        for source_index, source_claim_keys, output in outputs:
            tasks.extend(output.body["tasks"])
            canonical_claim_id_by_local_id: dict[str, str] = {}
            for claim_key, local_claim in zip(source_claim_keys, output.claims, strict=True):
                canonical_claim_id = claim_id_by_key[claim_key]
                canonical_claim_id_by_local_id[local_claim["claim_id"]] = (
                    canonical_claim_id
                )
                existing = claims_by_key.get(claim_key)
                if existing is None:
                    claims_by_key[claim_key] = {
                        "claim_id": canonical_claim_id,
                        "research_run_id": run_id,
                        "text": local_claim["text"],
                        "status": local_claim["status"],
                        "confidence": local_claim["confidence"],
                        "created_at": local_claim["created_at"],
                    }
                elif local_claim["status"] == "supported":
                    existing["status"] = "supported"
                    existing["confidence"] = max(
                        existing["confidence"], local_claim["confidence"]
                    )

            evidence.extend(output.evidence)
            relations.extend(
                {
                    **relation,
                    "claim_id": canonical_claim_id_by_local_id[relation["claim_id"]],
                }
                for relation in output.relations
            )

        for claim in claims_fixture:
            key = _require_text(claim.get("key"), "claim.key")
            if key in claims_by_key:
                continue
            claims_by_key[key] = {
                "claim_id": claim_id_by_key[key],
                "research_run_id": run_id,
                "text": _require_text(claim.get("text"), "claim.text"),
                "status": "unsupported",
                "confidence": 0.0,
                "created_at": self._retrieved_at.isoformat().replace("+00:00", "Z"),
            }

        ordered_claims = [
            claims_by_key[_require_text(claim.get("key"), "claim.key")]
            for claim in claims_fixture
        ]
        statements = [
            {
                "statement_id": _stable_id("stmt", run_id, claim["claim_id"]),
                "report_id": _stable_id("rpt", run_id),
                "claim_id": claim["claim_id"],
                "position": position,
                "text": claim["text"],
                "created_at": claim["created_at"],
            }
            for position, claim in enumerate(ordered_claims)
        ]
        body: JsonObject = {
            "research_run_id": run_id,
            "question": question,
            "status": "completed",
            "started_at": self._retrieved_at.isoformat().replace("+00:00", "Z"),
            "completed_at": self._retrieved_at.isoformat().replace("+00:00", "Z"),
            "tasks": tasks,
            "sources": [snapshot.to_source_artifact_body() for snapshot in snapshots],
            "evidence": evidence,
            "claims": ordered_claims,
            "claim_evidence_relations": relations,
            "reports": [
                {
                    "report_id": _stable_id("rpt", run_id),
                    "research_run_id": run_id,
                    "title": f"Phase 1 report: {question_id}",
                    "status": "ready",
                    "created_at": self._retrieved_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "statements": statements,
                }
            ],
        }
        return {
            "artifact_id": _stable_id("art", run_id, input_hash, FIXTURE_PROMPT_VERSION),
            "artifact_type": "research_run",
            "schema_version": SCHEMA_VERSION,
            "created_at": self._retrieved_at.isoformat().replace("+00:00", "Z"),
            "producer": FIXTURE_PRODUCER,
            "input_hash": input_hash,
            "model": FIXTURE_MODEL,
            "prompt_version": FIXTURE_PROMPT_VERSION,
            "body": body,
        }

    def _build_report(
        self,
        *,
        question_id: str,
        question: str,
        artifact: JsonObject,
        snapshots: tuple[SourceSnapshot, ...],
    ) -> Report:
        body = artifact["body"]
        report_id = _stable_id("rpt", body["research_run_id"])
        created_at = self._retrieved_at
        claims = [
            ReportClaim(
                claim_id=claim["claim_id"],
                research_run_id=body["research_run_id"],
                text=claim["text"],
                status=ClaimStatus(claim["status"]),
                confidence=claim["confidence"],
                created_at=created_at,
                unsupported_reason=(
                    "연결된 근거가 없습니다."
                    if claim["status"] == "unsupported"
                    else None
                ),
            )
            for claim in body["claims"]
        ]
        evidence = [
            ReportEvidence(
                evidence_id=item["evidence_id"],
                source_id=item["source_id"],
                research_run_id=item["research_run_id"],
                kind=EvidenceKind(item["kind"]),
                quote_or_summary=item["quote_or_summary"],
                locator=item["locator"],
                content_hash=item["content_hash"],
                collected_at=created_at,
            )
            for item in body["evidence"]
        ]
        source_by_id = {snapshot.source_id: snapshot for snapshot in snapshots}
        sources = [
            ReportSource(
                source_id=snapshot.source_id,
                research_run_id=snapshot.research_run_id,
                source_type=snapshot.source_type,
                title=snapshot.title,
                locator=snapshot.locator,
                original_content=snapshot.original_content,
                publisher=snapshot.publisher,
                published_at=snapshot.published_at,
                retrieved_at=snapshot.retrieved_at,
                content_hash=snapshot.content_hash,
                metadata=dict(snapshot.metadata),
            )
            for snapshot in snapshots
        ]
        relations = [ClaimEvidenceRelation.model_validate(item) for item in body["claim_evidence_relations"]]
        statements = [
            ReportStatement(
                statement_id=statement["statement_id"],
                report_id=report_id,
                claim_id=statement["claim_id"],
                position=statement["position"],
                text=statement["text"],
                created_at=created_at,
            )
            for statement in body["reports"][0]["statements"]
        ]
        if {source.source_id for source in sources} != set(source_by_id):
            raise AssertionError("Report Source adapter lost a snapshot")
        return Report(
            report_id=report_id,
            research_run_id=body["research_run_id"],
            title=f"Phase 1 report: {question_id}",
            status=ReportStatus.READY,
            created_at=created_at,
            statements=statements,
            claims=claims,
            evidence=evidence,
            sources=sources,
            claim_evidence_relations=relations,
            metadata={"question_id": question_id, "question": question},
        )

    @staticmethod
    def _to_web_mock_response(
        *, question: str, report: Report, markdown: str
    ) -> JsonObject:
        payload = report.model_dump(mode="json")
        payload["question"] = question
        payload["markdown"] = markdown
        for source in payload["sources"]:
            source["source_url"] = (
                source["locator"]
                if str(source["locator"]).lower().startswith("https://")
                else None
            )
        return {"report": payload}


def _citation_paths(report: Report, markdown: str) -> tuple[str, ...]:
    evidence_by_id = {item.evidence_id: item for item in report.evidence}
    source_by_id = {item.source_id: item for item in report.sources}
    relations_by_claim: dict[str, list[ClaimEvidenceRelation]] = {}
    for relation in report.claim_evidence_relations:
        relations_by_claim.setdefault(relation.claim_id, []).append(relation)

    paths: list[str] = []
    for claim in report.claims:
        if claim.status is not ClaimStatus.SUPPORTED:
            continue
        relations = relations_by_claim.get(claim.claim_id, [])
        if not relations:
            raise AssertionError(f"supported Claim has no Evidence: {claim.claim_id}")
        relation = relations[0]
        evidence = evidence_by_id.get(relation.evidence_id)
        source = source_by_id.get(evidence.source_id) if evidence else None
        if evidence is None or source is None:
            raise AssertionError(f"broken citation path for {claim.claim_id}")
        path = (
            f"Claim `{claim.claim_id}` -> Evidence `{evidence.evidence_id}` -> "
            f"Source `{source.source_id}`"
        )
        if path not in markdown:
            raise AssertionError(f"Markdown is missing citation path: {path}")
        paths.append(path)
    return tuple(paths)


def _evaluate_question(
    *,
    adapter: Phase1IntegrationAdapter,
    question_id: str,
    question: str,
    expectation: Mapping[str, Any],
) -> Phase1QuestionResult:
    run = asyncio.run(adapter.run(question_id, question))
    report = run.report
    body = run.artifact["body"]
    claims_by_text = {claim.text: claim for claim in report.claims}
    evidence_by_id = {item.evidence_id: item for item in report.evidence}
    sources_by_id = {item.source_id: item for item in report.sources}
    relations_by_claim: dict[str, list[ClaimEvidenceRelation]] = {}
    for relation in report.claim_evidence_relations:
        relations_by_claim.setdefault(relation.claim_id, []).append(relation)

    checks: dict[str, bool] = {
        "research_run_created_and_completed": run.research_run.status
        is ResearchRunStatus.COMPLETED,
        "single_search": run.provider_calls == (question,),
        "source_snapshots_persisted": len(run.snapshots) == len(body["sources"]),
        "artifact_schema_valid": True,
        "report_created_and_retrieved": run.report_response.report_id == report.report_id,
        "web_mock_report_envelope": run.web_mock_response.get("report", {}).get(
            "research_run_id"
        )
        == report.research_run_id,
    }

    citation_paths: list[str] = []
    expected_claims = _require_list(
        expectation.get("expected_claims"), f"{question_id}.expected_claims"
    )
    for expected in expected_claims:
        claim = claims_by_text.get(_require_text(expected.get("text"), "expected.text"))
        if claim is None:
            raise AssertionError(f"expected Claim is missing: {expected['id']}")
        if claim.status.value != expected.get("status"):
            raise AssertionError(
                f"Claim {expected['id']} has status {claim.status.value!r}"
            )
        linked_evidence = [
            evidence_by_id[relation.evidence_id]
            for relation in relations_by_claim.get(claim.claim_id, [])
            if relation.evidence_id in evidence_by_id
        ]
        for required in _require_list(
            expected.get("evidence"), f"{question_id}.{expected['id']}.evidence"
        ):
            required_type = _require_text(required.get("source_type"), "source_type")
            matches = [
                item
                for item in linked_evidence
                if sources_by_id[item.source_id].metadata.get("eval_source_type")
                == required_type
                and item.locator is not None
                and ":" in item.locator
            ]
            if not matches:
                raise AssertionError(
                    f"Claim {expected['id']} lacks a specific {required_type} citation"
                )
        citation_paths.append(
            _citation_path_for_claim(claim, linked_evidence, sources_by_id)
        )

    unsupported_claims = tuple(
        claim.claim_id
        for claim in report.claims
        if claim.status is ClaimStatus.UNSUPPORTED
    )
    if not unsupported_claims:
        raise AssertionError("unsupported Claim was not preserved")
    unsupported_texts = [
        claim.text
        for claim in report.claims
        if claim.status is ClaimStatus.UNSUPPORTED
    ]
    if not all(
        text in run.report_response.markdown
        and "Warning: `unsupported`" in run.report_response.markdown
        for text in unsupported_texts
    ):
        raise AssertionError("unsupported Claim is not visible in Markdown Report")
    citation_paths = list(_citation_paths(report, run.report_response.markdown))
    checks["expected_claims_and_source_types"] = True
    checks["citation_paths_in_markdown"] = len(citation_paths) == len(expected_claims)
    checks["unsupported_preserved"] = True
    if not all(checks.values()):
        raise AssertionError(f"failed Phase 1 checks: {checks}")
    return Phase1QuestionResult(
        question_id=question_id,
        status="pass",
        report_id=report.report_id,
        citation_paths=tuple(citation_paths),
        unsupported_claim_ids=unsupported_claims,
        checks=checks,
    )


def _citation_path_for_claim(
    claim: ReportClaim,
    evidence: list[ReportEvidence],
    sources_by_id: Mapping[str, ReportSource],
) -> str:
    if not evidence:
        raise AssertionError(f"Claim has no linked Evidence: {claim.claim_id}")
    source = sources_by_id[evidence[0].source_id]
    return (
        f"Claim `{claim.claim_id}` -> Evidence `{evidence[0].evidence_id}` -> "
        f"Source `{source.source_id}`"
    )


def evaluate_phase1() -> JsonObject:
    questions = _require_list(_load_json(QUESTIONS_PATH), "questions.json")
    phase1_questions = [
        question for question in questions if question.get("phase1_candidate") is True
    ]
    if len(phase1_questions) != 5:
        raise AssertionError(f"expected exactly five Phase 1 questions, got {len(phase1_questions)}")
    fixture = _require_mapping(_load_json(FIXTURE_PATH), "phase1_fixture.json")
    adapter = Phase1IntegrationAdapter(fixture)

    results: list[Phase1QuestionResult] = []
    for question in phase1_questions:
        question_id = _require_text(question.get("id"), "question.id")
        expectation = _require_mapping(
            _load_json(EXPECTATIONS_DIR / f"{question_id}.json"),
            f"expectation.{question_id}",
        )
        try:
            results.append(
                _evaluate_question(
                    adapter=adapter,
                    question_id=question_id,
                    question=_require_text(question.get("question"), "question.question"),
                    expectation=expectation,
                )
            )
        except Exception as exc:  # noqa: BLE001 - report all five questions
            results.append(
                Phase1QuestionResult(
                    question_id=question_id,
                    status="fail",
                    report_id=None,
                    citation_paths=(),
                    unsupported_claim_ids=(),
                    checks={},
                    error=str(exc),
                )
            )

    passed = sum(result.status == "pass" for result in results)
    return {
        "evaluator": "claimgraph-phase1",
        "fixture": str(FIXTURE_PATH.relative_to(ROOT)),
        "question_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "status": "pass" if passed == len(results) else "fail",
        "results": [result.to_dict() for result in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON instead of the concise table",
    )
    args = parser.parse_args(argv)
    summary = evaluate_phase1()
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for result in summary["results"]:
            marker = "PASS" if result["pass"] else "FAIL"
            print(
                f"{marker} {result['question_id']}: "
                f"{len(result['report_citation_paths'])} citation path(s), "
                f"{len(result['unsupported_claim_ids'])} unsupported Claim(s)"
            )
        print(
            f"Phase 1: {summary['passed']}/{summary['question_count']} passed"
        )
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
