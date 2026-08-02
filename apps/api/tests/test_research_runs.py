from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domains.research_run import (  # noqa: E402
    CreateResearchRunRequest,
    InMemoryResearchRunRepository,
    ResearchRunStatus,
    create_research_run,
)
from app.main import app  # noqa: E402


VALID_HASH = "sha256:" + "a" * 64


def valid_request(**overrides: Any) -> CreateResearchRunRequest:
    payload: dict[str, Any] = {
        "question": "Which claims are supported?",
        "input_hash": VALID_HASH,
        "output_format": "markdown",
        "budget": {"max_tasks": 5},
    }
    payload.update(overrides)
    return CreateResearchRunRequest.model_validate(payload)


def test_request_validates_hash_output_format_and_budget() -> None:
    request = valid_request()

    assert request.input_hash == VALID_HASH
    assert request.output_format.value == "markdown"
    assert request.budget.max_tasks == 5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_hash", "sha256:" + "A" * 64),
        ("input_hash", "not-a-hash"),
        ("output_format", "xml"),
        ("budget", {"max_tasks": 0}),
        ("budget", {"max_tasks": -1}),
    ],
)
def test_request_rejects_invalid_contract_values(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        valid_request(**{field: value})


def test_response_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC"):
        create_research_run(valid_request(), now=datetime(2026, 8, 3, 12, 0))


def test_response_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC"):
        create_research_run(
            valid_request(),
            now=datetime.fromisoformat("2026-08-03T21:00:00+09:00"),
        )


def test_queued_run_has_server_id_and_utc_timestamp() -> None:
    created_at = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

    research_run = create_research_run(valid_request(), now=created_at)

    assert research_run.research_run_id.startswith("rr_")
    assert research_run.status is ResearchRunStatus.QUEUED
    assert research_run.created_at == created_at
    assert research_run.created_at.utcoffset().total_seconds() == 0


def test_in_memory_repository_round_trips_and_returns_missing_as_none() -> None:
    async def scenario() -> None:
        repository = InMemoryResearchRunRepository()
        research_run = create_research_run(valid_request())

        saved = await repository.create(research_run)
        loaded = await repository.get_by_id(research_run.research_run_id)

        assert saved == research_run
        assert loaded == research_run
        assert loaded is not research_run
        assert await repository.get_by_id("rr_missing") is None

    asyncio.run(scenario())


async def asgi_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    request_consumed = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal request_consumed
        if request_consumed:
            return {"type": "http.disconnect"}
        request_consumed = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    headers = [(b"host", b"testserver")]
    if payload is not None:
        headers.extend(
            [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ]
        )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }
    await app(scope, receive, send)

    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = next(
        message["body"]
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(response_body)


def test_asgi_smoke_covers_health_create_get_and_stable_404() -> None:
    async def scenario() -> None:
        health_status, health_body = await asgi_request("GET", "/health")
        assert health_status == 200
        assert health_body == {"status": "ok"}

        create_status, created = await asgi_request(
            "POST",
            "/v1/research-runs",
            {
                "question": "Which claims are supported?",
                "input_hash": VALID_HASH,
                "output_format": "json",
                "budget": {"max_tasks": 3, "max_tokens": 1_000},
            },
        )
        assert create_status == 201
        assert created["status"] == "queued"
        assert created["input_hash"] == VALID_HASH
        assert created["created_at"].endswith("Z")

        get_status, fetched = await asgi_request(
            "GET", f"/v1/research-runs/{created['research_run_id']}"
        )
        assert get_status == 200
        assert fetched == created

        missing_status, missing = await asgi_request(
            "GET", "/v1/research-runs/rr_does_not_exist"
        )
        assert missing_status == 404
        assert missing == {
            "error_code": "research_run_not_found",
            "message": "Research run not found.",
        }

    asyncio.run(scenario())
