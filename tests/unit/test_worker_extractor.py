from __future__ import annotations

from apps.worker.extractor import (
    ExtractorInput,
    FixtureClaim,
    FixtureEvidence,
    FixtureExtractor,
)


def fixture_input() -> ExtractorInput:
    return ExtractorInput(
        research_run_id="rr_fixture_001",
        source_id="src_fixture_001",
        source_type="document",
        title="Fixture source",
        locator="fixture://cg-11",
        snapshot="The fixture source supports the first claim.",
        claims=(
            FixtureClaim(
                text="The fixture source supports the first claim.",
                evidence=(
                    FixtureEvidence(
                        quote_or_summary="The fixture source supports the first claim.",
                        locator="section:1",
                    ),
                ),
                confidence=0.9,
            ),
            FixtureClaim(text="This claim has no evidence.", confidence=0.4),
        ),
        question="Which fixture claim is supported?",
        retrieved_at="2026-08-02T14:04:00Z",
    )


def test_fixture_extractor_builds_claim_evidence_graph() -> None:
    output = FixtureExtractor().extract(fixture_input())

    assert len(output.claims) == 2
    assert len(output.evidence) == 1
    assert len(output.relations) == 1

    supported_claim, unsupported_claim = output.claims
    evidence = output.evidence[0]
    relation = output.relations[0]

    assert supported_claim["status"] == "supported"
    assert supported_claim["confidence"] == 0.9
    assert unsupported_claim["status"] == "unsupported"
    assert unsupported_claim["confidence"] == 0.0
    assert relation["relation_type"] == "supports"
    assert relation["claim_id"] == supported_claim["claim_id"]
    assert relation["evidence_id"] == evidence["evidence_id"]
    assert evidence["source_id"] == "src_fixture_001"
    assert evidence["locator"] == "section:1"
    assert "The fixture source supports the first claim." in output.to_json()
    assert output.body["sources"][0]["content_hash"].startswith("sha256:")
    assert "snapshot" not in output.to_json()


def test_claim_without_evidence_is_preserved_as_unsupported_without_relation() -> None:
    output = FixtureExtractor().extract(fixture_input())

    unsupported_claim = next(
        claim for claim in output.claims if claim["status"] == "unsupported"
    )

    assert unsupported_claim["claim_id"] not in {
        relation["claim_id"] for relation in output.relations
    }


def test_artifact_records_reproducibility_metadata() -> None:
    output = FixtureExtractor().extract(fixture_input())
    envelope = output.envelope

    assert envelope["input_hash"].startswith("sha256:")
    assert envelope["model"] == "fixture-extractor"
    assert envelope["prompt_version"] == "fixture-extractor@1"
    assert envelope["schema_version"] == "2026-08-02"
    task = output.body["tasks"][0]
    assert task["input_hash"] == envelope["input_hash"]
    assert task["model"] == envelope["model"]
    assert task["prompt_version"] == envelope["prompt_version"]
    assert task["schema_version"] == envelope["schema_version"]


def test_same_snapshot_and_versions_are_byte_for_byte_replayable() -> None:
    extractor = FixtureExtractor()
    first = extractor.extract(fixture_input())
    second = extractor.extract(fixture_input())

    assert first.to_json() == second.to_json()
    assert first.input_hash == second.input_hash


def test_changed_snapshot_changes_input_hash_and_artifact_identity() -> None:
    original = fixture_input()
    changed = ExtractorInput(
        **{
            **original.to_dict(),
            "snapshot": "The changed fixture source has a different snapshot.",
        }
    )

    first = FixtureExtractor().extract(original)
    second = FixtureExtractor().extract(changed)

    assert first.input_hash != second.input_hash
    assert first.envelope["artifact_id"] != second.envelope["artifact_id"]


def test_mapping_candidates_are_normalized_into_input_models() -> None:
    input_model = ExtractorInput(
        research_run_id="rr_fixture_mapping",
        source_id="src_fixture_mapping",
        source_type="manual",
        title="Mapping fixture",
        locator="fixture://mapping",
        snapshot="A mapped source.",
        claims=(
            {
                "text": "A mapped claim.",
                "confidence": 0.7,
                "evidence": [
                    {
                        "quote": "A mapped source.",
                        "locator": "line:1",
                    },
                ],
            },
        ),
    )

    output = FixtureExtractor().extract(input_model)

    assert output.claims[0]["status"] == "supported"
    assert output.evidence[0]["quote_or_summary"] == "A mapped source."
