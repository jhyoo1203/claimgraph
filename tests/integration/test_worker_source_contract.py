from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from apps.worker.source_snapshots import (
    ExtractionStatus,
    SourceSnapshot,
    content_hash_for,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages/schemas/claimgraph-contract.schema.json"


def test_runtime_snapshot_projects_to_metadata_only_source_artifact() -> None:
    retrieved_at = datetime(2026, 8, 3, 1, 30, tzinfo=timezone.utc)
    snapshot = SourceSnapshot(
        source_id="src_contract",
        research_run_id="rr_contract",
        source_type="web",
        title="Contract source",
        locator="https://example.test/contract",
        original_content="Original source text.",
        retrieved_at=retrieved_at,
        content_hash=content_hash_for("Original source text."),
        extraction_status=ExtractionStatus.SUCCEEDED,
    )
    document: dict[str, Any] = {
        "artifact_id": "art_source_contract",
        "artifact_type": "source",
        "schema_version": "2026-08-02",
        "created_at": retrieved_at.isoformat(),
        "producer": {"name": "claimgraph-worker", "version": "0.1.0"},
        "input_hash": content_hash_for("question"),
        "body": snapshot.to_source_artifact_body(),
    }
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
            document
        )
    )

    assert errors == []
    assert "original_content" not in document["body"]
    assert "extraction_status" not in document["body"]
    assert snapshot.original_content == "Original source text."
    assert snapshot.extraction_status is ExtractionStatus.SUCCEEDED
