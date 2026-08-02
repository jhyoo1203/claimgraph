"""Deterministic Claim/Evidence extraction contracts for worker fixtures.

This module intentionally does not call a model or a search provider.  The
fixture extractor turns explicitly supplied claim and evidence candidates into
the canonical ``ResearchRun`` artifact envelope so the graph rules can be
tested before an LLM-backed extractor exists.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Final, TypeAlias

SCHEMA_VERSION: Final = "2026-08-02"
FIXTURE_MODEL: Final = "fixture-extractor"
FIXTURE_PROMPT_VERSION: Final = "fixture-extractor@1"
FIXTURE_PRODUCER_NAME: Final = "claimgraph-fixture-extractor"
FIXTURE_PRODUCER_VERSION: Final = "0.1.0"
DEFAULT_RETRIEVED_AT: Final = "2026-08-02T00:00:00Z"

_ID_PATTERNS: Final = {
    "research_run_id": re.compile(r"^rr_[A-Za-z0-9_-]+$"),
    "source_id": re.compile(r"^src_[A-Za-z0-9_-]+$"),
}
_SOURCE_TYPES: Final = frozenset(
    {"web", "document", "paper", "dataset", "api", "manual"}
)
_EVIDENCE_KINDS: Final = frozenset(
    {"quote", "summary", "table", "metric", "observation"}
)

JsonObject: TypeAlias = dict[str, Any]


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _validate_confidence(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number between 0 and 1")
    confidence = float(value)
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return confidence


def _validate_timestamp(value: object, field_name: str) -> str:
    timestamp = _require_text(value, field_name)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return timestamp


def _sha256(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256(_canonical_json(list(parts)).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


@dataclass(frozen=True, slots=True)
class FixtureEvidence:
    """Evidence candidate supplied to the deterministic fixture extractor."""

    quote_or_summary: str
    locator: str
    kind: str = "quote"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "quote_or_summary",
            _require_text(self.quote_or_summary, "quote_or_summary"),
        )
        object.__setattr__(self, "locator", _require_text(self.locator, "locator"))
        kind = _require_text(self.kind, "kind")
        if kind not in _EVIDENCE_KINDS:
            raise ValueError(f"kind must be one of {sorted(_EVIDENCE_KINDS)}")
        object.__setattr__(self, "kind", kind)


@dataclass(frozen=True, slots=True)
class FixtureClaim:
    """Claim candidate and its optional supporting Evidence candidates."""

    text: str
    evidence: tuple[FixtureEvidence, ...] = ()
    confidence: float = 0.8

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _require_text(self.text, "text"))
        normalized_evidence = tuple(_coerce_evidence(item) for item in self.evidence)
        object.__setattr__(self, "evidence", normalized_evidence)
        object.__setattr__(
            self,
            "confidence",
            _validate_confidence(self.confidence, "confidence"),
        )


def _coerce_evidence(value: FixtureEvidence | Mapping[str, Any]) -> FixtureEvidence:
    if isinstance(value, FixtureEvidence):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("evidence candidates must be FixtureEvidence or objects")

    quote_or_summary = value.get("quote_or_summary")
    if quote_or_summary is None:
        quote_or_summary = value.get("quote", value.get("summary"))
    return FixtureEvidence(
        quote_or_summary=quote_or_summary,
        locator=value.get("locator"),
        kind=value.get("kind", "quote"),
    )


def _coerce_claim(value: FixtureClaim | Mapping[str, Any]) -> FixtureClaim:
    if isinstance(value, FixtureClaim):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("claim candidates must be FixtureClaim or objects")
    return FixtureClaim(
        text=value.get("text"),
        evidence=tuple(value.get("evidence", ())),
        confidence=value.get("confidence", 0.8),
    )


@dataclass(frozen=True, slots=True)
class ExtractorInput:
    """Immutable, replayable input for one fixture extraction run.

    ``snapshot`` is the source snapshot text held outside the persisted
    artifact.  Only its hash is emitted in the artifact; the full text never
    appears in Evidence or worker output.
    """

    research_run_id: str
    source_id: str
    source_type: str
    title: str
    locator: str
    snapshot: str
    claims: tuple[FixtureClaim, ...] = ()
    question: str = "Fixture extraction"
    retrieved_at: str = DEFAULT_RETRIEVED_AT
    model: str = FIXTURE_MODEL
    prompt_version: str = FIXTURE_PROMPT_VERSION
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name, pattern in _ID_PATTERNS.items():
            value = _require_text(getattr(self, field_name), field_name)
            if pattern.fullmatch(value) is None:
                raise ValueError(f"{field_name} must match {pattern.pattern}")
            object.__setattr__(self, field_name, value)

        source_type = _require_text(self.source_type, "source_type")
        if source_type not in _SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(_SOURCE_TYPES)}")
        object.__setattr__(self, "source_type", source_type)
        for field_name in (
            "title",
            "locator",
            "snapshot",
            "question",
            "model",
            "prompt_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "retrieved_at",
            _validate_timestamp(self.retrieved_at, "retrieved_at"),
        )
        schema_version = _require_text(self.schema_version, "schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(
            self,
            "claims",
            tuple(_coerce_claim(item) for item in self.claims),
        )

    @property
    def source_snapshot(self) -> str:
        """Alias used by callers that name the snapshot explicitly."""

        return self.snapshot

    @property
    def input_hash(self) -> str:
        """Hash of the complete normalized input and extractor versions."""

        return _sha256(_canonical_json(self.to_dict()))

    def to_dict(self) -> JsonObject:
        """Return the normalized input, including the snapshot for hashing."""

        return {
            "research_run_id": self.research_run_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "title": self.title,
            "locator": self.locator,
            "snapshot": self.snapshot,
            "claims": [
                {
                    "text": claim.text,
                    "confidence": claim.confidence,
                    "evidence": [
                        {
                            "kind": evidence.kind,
                            "locator": evidence.locator,
                            "quote_or_summary": evidence.quote_or_summary,
                        }
                        for evidence in claim.evidence
                    ],
                }
                for claim in self.claims
            ],
            "question": self.question,
            "retrieved_at": self.retrieved_at,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
        }

    model_dump = to_dict


@dataclass(frozen=True, slots=True)
class ExtractorOutput:
    """Structured extractor result backed by one canonical artifact envelope."""

    envelope: JsonObject

    @property
    def artifact(self) -> JsonObject:
        """Compatibility alias for callers that call the envelope an artifact."""

        return self.envelope

    @property
    def body(self) -> JsonObject:
        return self.envelope["body"]

    @property
    def claims(self) -> list[JsonObject]:
        return self.body["claims"]

    @property
    def evidence(self) -> list[JsonObject]:
        return self.body["evidence"]

    @property
    def claim_evidence_relations(self) -> list[JsonObject]:
        return self.body["claim_evidence_relations"]

    @property
    def relations(self) -> list[JsonObject]:
        return self.claim_evidence_relations

    @property
    def input_hash(self) -> str:
        return self.envelope["input_hash"]

    def to_dict(self) -> JsonObject:
        """Return a JSON-compatible copy of the envelope."""

        return json.loads(_canonical_json(self.envelope))

    model_dump = to_dict

    def to_json(self) -> str:
        """Serialize the result canonically for replay comparisons."""

        return _canonical_json(self.envelope)


class FixtureExtractor:
    """Build deterministic Claim, Evidence, and ``supports`` relations."""

    def __init__(
        self,
        *,
        producer_name: str = FIXTURE_PRODUCER_NAME,
        producer_version: str = FIXTURE_PRODUCER_VERSION,
    ) -> None:
        self._producer_name = _require_text(producer_name, "producer_name")
        self._producer_version = _require_text(producer_version, "producer_version")

    def extract(self, input: ExtractorInput) -> ExtractorOutput:
        """Extract a replayable ResearchRun artifact from fixture candidates."""

        if not isinstance(input, ExtractorInput):
            raise TypeError("input must be an ExtractorInput")

        input_hash = input.input_hash
        source_content_hash = _sha256(input.snapshot)
        claims: list[JsonObject] = []
        evidence_items: list[JsonObject] = []
        relations: list[JsonObject] = []

        for claim_index, candidate in enumerate(input.claims):
            claim_id = _stable_id(
                "clm",
                input.research_run_id,
                input.source_id,
                str(claim_index),
                candidate.text,
            )
            claim_has_evidence = bool(candidate.evidence)
            claim_confidence = candidate.confidence if claim_has_evidence else 0.0
            claims.append(
                {
                    "claim_id": claim_id,
                    "research_run_id": input.research_run_id,
                    "text": candidate.text,
                    "status": "supported" if claim_has_evidence else "unsupported",
                    "confidence": claim_confidence,
                    "created_at": input.retrieved_at,
                }
            )

            for evidence_index, candidate_evidence in enumerate(candidate.evidence):
                evidence_id = _stable_id(
                    "ev",
                    input.research_run_id,
                    input.source_id,
                    str(claim_index),
                    str(evidence_index),
                    candidate_evidence.quote_or_summary,
                    candidate_evidence.locator,
                )
                evidence_items.append(
                    {
                        "evidence_id": evidence_id,
                        "source_id": input.source_id,
                        "research_run_id": input.research_run_id,
                        "kind": candidate_evidence.kind,
                        "quote_or_summary": candidate_evidence.quote_or_summary,
                        "locator": candidate_evidence.locator,
                        "content_hash": _sha256(candidate_evidence.quote_or_summary),
                        "collected_at": input.retrieved_at,
                    }
                )
                relations.append(
                    {
                        "relation_id": _stable_id(
                            "rel",
                            claim_id,
                            evidence_id,
                            "supports",
                        ),
                        "claim_id": claim_id,
                        "evidence_id": evidence_id,
                        "relation_type": "supports",
                        "confidence": candidate.confidence,
                        "created_at": input.retrieved_at,
                    }
                )

        task_id = _stable_id(
            "task",
            input.research_run_id,
            input_hash,
            input.model,
            input.prompt_version,
            input.schema_version,
        )
        artifact_id = _stable_id(
            "art",
            input.research_run_id,
            input_hash,
            input.model,
            input.prompt_version,
            input.schema_version,
            self._producer_name,
            self._producer_version,
        )
        body: JsonObject = {
            "research_run_id": input.research_run_id,
            "question": input.question,
            "status": "completed",
            "started_at": input.retrieved_at,
            "completed_at": input.retrieved_at,
            "tasks": [
                {
                    "task_id": task_id,
                    "research_run_id": input.research_run_id,
                    "kind": "extract_evidence",
                    "status": "succeeded",
                    "input_hash": input_hash,
                    "model": input.model,
                    "prompt_version": input.prompt_version,
                    "schema_version": input.schema_version,
                    "attempt": 1,
                    "created_at": input.retrieved_at,
                    "started_at": input.retrieved_at,
                    "finished_at": input.retrieved_at,
                }
            ],
            "sources": [
                {
                    "source_id": input.source_id,
                    "research_run_id": input.research_run_id,
                    "source_type": input.source_type,
                    "title": input.title,
                    "locator": input.locator,
                    "retrieved_at": input.retrieved_at,
                    "content_hash": source_content_hash,
                }
            ],
            "evidence": evidence_items,
            "claims": claims,
            "claim_evidence_relations": relations,
        }
        envelope: JsonObject = {
            "artifact_id": artifact_id,
            "artifact_type": "research_run",
            "schema_version": input.schema_version,
            "created_at": input.retrieved_at,
            "producer": {
                "name": self._producer_name,
                "version": self._producer_version,
            },
            "input_hash": input_hash,
            "model": input.model,
            "prompt_version": input.prompt_version,
            "body": body,
        }
        return ExtractorOutput(envelope=envelope)

    run = extract


DeterministicFixtureExtractor = FixtureExtractor
Extractor = FixtureExtractor
ClaimCandidate = FixtureClaim
EvidenceCandidate = FixtureEvidence


def extract_fixture(input: ExtractorInput) -> ExtractorOutput:
    """Convenience function for one deterministic fixture extraction."""

    return FixtureExtractor().extract(input)


__all__ = [
    "FIXTURE_MODEL",
    "FIXTURE_PROMPT_VERSION",
    "SCHEMA_VERSION",
    "ClaimCandidate",
    "DeterministicFixtureExtractor",
    "EvidenceCandidate",
    "Extractor",
    "ExtractorInput",
    "ExtractorOutput",
    "FixtureClaim",
    "FixtureEvidence",
    "FixtureExtractor",
    "extract_fixture",
]
