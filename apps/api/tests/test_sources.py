from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.sources import get_source_repository
from app.db.source_repository import InMemorySourceRepository
from app.domains.sources import ExtractionStatus, SourceRecord
from app.main import app


def source_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_id": "src_demo",
        "research_run_id": "rr_demo",
        "source_type": "web",
        "title": "Demo source",
        "locator": "https://example.test/source",
        "publisher": "Example",
        "published_at": "2026-08-01T12:00:00+09:00",
        "retrieved_at": "2026-08-02T12:00:00Z",
        "content_hash": "sha256:" + "a" * 64,
        "extraction_status": "succeeded",
        "original_content": "Original source text.",
        "metadata": {"language": "en", "pages": 2, "is_public": True},
    }
    payload.update(overrides)
    return payload


def test_source_record_validates_timezone_hash_and_status() -> None:
    source = SourceRecord.model_validate(source_payload())

    assert source.retrieved_at.tzinfo is not None
    assert source.published_at is not None
    assert source.published_at.utcoffset() is not None
    assert source.content_hash == "sha256:" + "a" * 64
    assert source.extraction_status is ExtractionStatus.SUCCEEDED
    assert source.content == "Original source text."


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retrieved_at", "2026-08-02T12:00:00"),
        ("published_at", "2026-08-01T12:00:00"),
        ("content_hash", "sha256:NOT_A_HASH"),
        ("extraction_status", "unknown"),
    ],
)
def test_source_record_rejects_invalid_contract_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        SourceRecord.model_validate(source_payload(**{field: value}))


def test_in_memory_repository_validates_and_copies_records() -> None:
    repository = InMemorySourceRepository([source_payload()])

    source = repository.get_source("src_demo")

    assert source is not None
    assert source.source_id == "src_demo"
    assert source is not repository.get_source("src_demo")
    assert repository.get_source("src_missing") is None


async def _request(
    application: FastAPI,
    path: str,
    method: str = "GET",
) -> tuple[int, dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await application(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        },
        receive,
        send,
    )

    start = next(message for message in messages if message["type"] == "http.response.start")
    body = next(message for message in messages if message["type"] == "http.response.body")
    return int(start["status"]), json.loads(body.get("body", b"{}"))


def test_source_get_endpoint_returns_metadata_and_original_content() -> None:
    repository = InMemorySourceRepository([source_payload()])
    app.dependency_overrides[get_source_repository] = lambda: repository

    try:
        status, body = asyncio.run(_request(app, "/v1/sources/src_demo"))
    finally:
        app.dependency_overrides.pop(get_source_repository, None)

    assert status == 200
    assert body["source_id"] == "src_demo"
    assert body["original_content"] == "Original source text."
    assert body["content_hash"] == "sha256:" + "a" * 64
    assert body["extraction_status"] == "succeeded"
    assert body["retrieved_at"].endswith("Z")


def test_source_get_endpoint_returns_stable_not_found_error() -> None:
    app.dependency_overrides[get_source_repository] = lambda: InMemorySourceRepository()

    try:
        status, body = asyncio.run(_request(app, "/v1/sources/src_missing"))
    finally:
        app.dependency_overrides.pop(get_source_repository, None)

    assert status == 404
    assert body == {
        "error_code": "source_not_found",
        "message": "Source not found.",
    }


def test_source_openapi_contract_compiles() -> None:
    document = app.openapi()

    assert "/v1/sources/{source_id}" in document["paths"]
    source_schema = document["components"]["schemas"]["SourceResponse"]
    assert source_schema["properties"]["content_hash"]["pattern"] == r"^sha256:[a-f0-9]{64}$"
    assert source_schema["properties"]["extraction_status"]["$ref"].endswith("/ExtractionStatus")
