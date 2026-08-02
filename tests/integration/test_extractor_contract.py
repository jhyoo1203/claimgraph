from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from apps.worker.extractor import (
    ExtractorInput,
    FixtureClaim,
    FixtureEvidence,
    FixtureExtractor,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages/schemas/claimgraph-contract.schema.json"
FIXTURE_PATH = ROOT / "packages/schemas/fixtures/valid-extractor-output.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def contract_validator() -> Draft202012Validator:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_extractor_fixture_passes_canonical_schema() -> None:
    contract_validator().validate(load_json(FIXTURE_PATH))


def test_extractor_output_passes_canonical_schema() -> None:
    output = FixtureExtractor().extract(
        ExtractorInput(
            research_run_id="rr_contract_001",
            source_id="src_contract_001",
            source_type="document",
            title="Contract fixture source",
            locator="fixture://contract",
            snapshot="A contract fixture supports this claim.",
            claims=(
                FixtureClaim(
                    text="A contract fixture supports this claim.",
                    evidence=(
                        FixtureEvidence(
                            quote_or_summary="A contract fixture supports this claim.",
                            locator="section:contract",
                        ),
                    ),
                ),
                FixtureClaim(text="A claim deliberately lacks evidence."),
            ),
        )
    )

    contract_validator().validate(output.envelope)


def test_artifact_envelope_requires_model_and_prompt_version() -> None:
    document = load_json(FIXTURE_PATH)
    document.pop("model")
    document.pop("prompt_version")

    errors = list(contract_validator().iter_errors(document))

    assert any("model" in error.message for error in errors)
    assert any("prompt_version" in error.message for error in errors)
