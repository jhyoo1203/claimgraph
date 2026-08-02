from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.worker.state import (
    INVALID_STATUS_ERROR_CODE,
    INVALID_STATUS_TRANSITION_ERROR_CODE,
    RESEARCH_RUN_TRANSITIONS,
    TASK_TRANSITIONS,
    InvalidStatusError,
    InvalidStatusTransitionError,
    ResearchRunStatus,
    TaskStatus,
    is_research_run_transition_allowed,
    is_task_transition_allowed,
    retryable_task_failure,
    terminal_task_failure,
    transition_research_run_status,
    transition_task_failure,
    transition_task_status,
    validate_research_run_status,
    validate_task_status,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages/schemas/claimgraph-contract.schema.json"


def schema_status_values(name: str) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema["$defs"][name]["enum"]


def test_worker_enums_match_canonical_schema_values() -> None:
    assert schema_status_values("ResearchRunStatus") == [
        status.value for status in ResearchRunStatus
    ]
    assert schema_status_values("TaskStatus") == [
        status.value for status in TaskStatus
    ]


@pytest.mark.parametrize(
    ("current", "next_status"),
    [
        (ResearchRunStatus.QUEUED, ResearchRunStatus.RUNNING),
        (ResearchRunStatus.QUEUED, ResearchRunStatus.CANCELLED),
        (ResearchRunStatus.RUNNING, ResearchRunStatus.COMPLETED),
        (ResearchRunStatus.RUNNING, ResearchRunStatus.FAILED),
        (ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED),
    ],
)
def test_allowed_research_run_transitions(
    current: ResearchRunStatus, next_status: ResearchRunStatus
) -> None:
    assert transition_research_run_status(current, next_status) is next_status
    assert is_research_run_transition_allowed(current.value, next_status.value)


@pytest.mark.parametrize(
    ("current", "next_status"),
    [
        (TaskStatus.QUEUED, TaskStatus.RUNNING),
        (TaskStatus.QUEUED, TaskStatus.CANCELLED),
        (TaskStatus.RUNNING, TaskStatus.SUCCEEDED),
        (TaskStatus.RUNNING, TaskStatus.RETRYING),
        (TaskStatus.RUNNING, TaskStatus.FAILED),
        (TaskStatus.RUNNING, TaskStatus.CANCELLED),
        (TaskStatus.RETRYING, TaskStatus.QUEUED),
        (TaskStatus.RETRYING, TaskStatus.CANCELLED),
    ],
)
def test_allowed_task_transitions(
    current: TaskStatus, next_status: TaskStatus
) -> None:
    assert transition_task_status(current, next_status) is next_status
    assert is_task_transition_allowed(current.value, next_status.value)


@pytest.mark.parametrize(
    ("current", "next_status"),
    [
        (ResearchRunStatus.COMPLETED, ResearchRunStatus.RUNNING),
        (ResearchRunStatus.FAILED, ResearchRunStatus.RUNNING),
        (ResearchRunStatus.CANCELLED, ResearchRunStatus.RUNNING),
        (TaskStatus.SUCCEEDED, TaskStatus.RUNNING),
        (TaskStatus.FAILED, TaskStatus.QUEUED),
        (TaskStatus.CANCELLED, TaskStatus.QUEUED),
        (TaskStatus.RETRYING, TaskStatus.SUCCEEDED),
    ],
)
def test_terminal_or_unlisted_transitions_are_rejected(
    current: ResearchRunStatus | TaskStatus,
    next_status: ResearchRunStatus | TaskStatus,
) -> None:
    transition = (
        transition_research_run_status
        if isinstance(current, ResearchRunStatus)
        else transition_task_status
    )

    with pytest.raises(InvalidStatusTransitionError) as error:
        transition(current, next_status)

    assert error.value.error_code == INVALID_STATUS_TRANSITION_ERROR_CODE


def test_unknown_status_has_stable_error_code() -> None:
    with pytest.raises(InvalidStatusError) as error:
        validate_task_status("paused")

    assert error.value.error_code == INVALID_STATUS_ERROR_CODE
    assert error.value.status_kind == "task"

    with pytest.raises(InvalidStatusError) as wrong_enum:
        validate_research_run_status(TaskStatus.RUNNING)

    assert wrong_enum.value.error_code == INVALID_STATUS_ERROR_CODE


def test_failure_helpers_choose_retrying_or_failed() -> None:
    assert retryable_task_failure() is TaskStatus.RETRYING
    assert terminal_task_failure() is TaskStatus.FAILED
    assert (
        transition_task_failure(TaskStatus.RUNNING, retryable=True)
        is TaskStatus.RETRYING
    )
    assert (
        transition_task_failure(TaskStatus.RUNNING, retryable=False)
        is TaskStatus.FAILED
    )


def test_transition_tables_cover_every_schema_status() -> None:
    assert set(RESEARCH_RUN_TRANSITIONS) == set(ResearchRunStatus)
    assert set(TASK_TRANSITIONS) == set(TaskStatus)
