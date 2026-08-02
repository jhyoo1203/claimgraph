from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages/schemas/claimgraph-contract.schema.json"
VALID_FIXTURE_PATH = ROOT / "packages/schemas/fixtures/valid-research-run.json"
INVALID_FIXTURE_PATH = ROOT / "packages/schemas/fixtures/invalid-claim-status.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def contract_validator() -> Draft202012Validator:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validation_errors(document: dict[str, Any]) -> list[str]:
    validator = contract_validator()
    return [error.message for error in validator.iter_errors(document)]


def test_valid_research_run_fixture_passes() -> None:
    errors = validation_errors(load_json(VALID_FIXTURE_PATH))

    assert errors == []


def test_invalid_claim_status_fixture_fails() -> None:
    errors = validation_errors(load_json(INVALID_FIXTURE_PATH))

    assert errors
    assert any("proven" in error for error in errors)


def test_artifact_type_must_match_body() -> None:
    document = load_json(VALID_FIXTURE_PATH)
    document["artifact_type"] = "claim"

    errors = validation_errors(document)

    assert errors


def test_completed_run_requires_completed_at() -> None:
    document = load_json(VALID_FIXTURE_PATH)
    document["body"].pop("completed_at")

    errors = validation_errors(document)

    assert any("completed_at" in error for error in errors)


def test_terminal_task_requires_finished_at() -> None:
    document = load_json(VALID_FIXTURE_PATH)
    task = deepcopy(document["body"]["tasks"][0])
    task.pop("finished_at")
    document["body"]["tasks"] = [task]

    errors = validation_errors(document)

    assert any("finished_at" in error for error in errors)
