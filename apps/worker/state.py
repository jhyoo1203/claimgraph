"""Worker execution state contracts.

The worker owns state transitions because a JSON Schema can constrain the
spelling of a status but cannot validate the history that produced it.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Final, TypeVar


class ResearchRunStatus(str, Enum):
    """Lifecycle states for a research run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    """Lifecycle states for an individual worker task."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


INVALID_STATUS_ERROR_CODE: Final = "invalid_status"
INVALID_STATUS_TRANSITION_ERROR_CODE: Final = "invalid_state_transition"


class WorkerStateError(ValueError):
    """Base class for deterministic worker state errors."""

    error_code: str

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidStatusError(WorkerStateError):
    """Raised when an input is not a member of the requested status enum."""

    error_code = INVALID_STATUS_ERROR_CODE

    def __init__(self, status_kind: str, status: object) -> None:
        self.status_kind = status_kind
        self.status = status
        super().__init__(f"Invalid {status_kind} status: {status!r}")


class InvalidStatusTransitionError(WorkerStateError):
    """Raised when a status transition is not in the worker transition table."""

    error_code = INVALID_STATUS_TRANSITION_ERROR_CODE

    def __init__(
        self,
        status_kind: str,
        current_status: Enum,
        next_status: Enum,
    ) -> None:
        self.status_kind = status_kind
        self.current_status = current_status
        self.next_status = next_status
        super().__init__(
            f"Invalid {status_kind} status transition: "
            f"{current_status.value!r} -> {next_status.value!r}"
        )


# The alias keeps the exception name usable for callers that describe this as
# a state rather than a status, while retaining one stable error contract.
InvalidStateTransitionError = InvalidStatusTransitionError


_ResearchRunStatus = TypeVar("_ResearchRunStatus", bound=ResearchRunStatus)
_TaskStatus = TypeVar("_TaskStatus", bound=TaskStatus)


# A run can be cancelled before it starts, but terminal states cannot be
# reopened. A failed run is terminal even when one of its tasks is retryable;
# retry decisions belong to the task state machine.
RESEARCH_RUN_TRANSITIONS: Final[
    Mapping[ResearchRunStatus, frozenset[ResearchRunStatus]]
] = MappingProxyType(
    {
        ResearchRunStatus.QUEUED: frozenset(
            {ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}
        ),
        ResearchRunStatus.RUNNING: frozenset(
            {
                ResearchRunStatus.COMPLETED,
                ResearchRunStatus.FAILED,
                ResearchRunStatus.CANCELLED,
            }
        ),
        ResearchRunStatus.COMPLETED: frozenset(),
        ResearchRunStatus.FAILED: frozenset(),
        ResearchRunStatus.CANCELLED: frozenset(),
    }
)


# Retryable failure is explicit: running -> retrying, then retrying -> queued
# lets the normal dispatcher own the next attempt. Terminal failure is
# running -> failed. Queued and retrying work may be cancelled before launch.
TASK_TRANSITIONS: Final[Mapping[TaskStatus, frozenset[TaskStatus]]] = MappingProxyType(
    {
        TaskStatus.QUEUED: frozenset(
            {TaskStatus.RUNNING, TaskStatus.CANCELLED}
        ),
        TaskStatus.RUNNING: frozenset(
            {
                TaskStatus.SUCCEEDED,
                TaskStatus.RETRYING,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.RETRYING: frozenset(
            {TaskStatus.QUEUED, TaskStatus.CANCELLED}
        ),
        TaskStatus.SUCCEEDED: frozenset(),
        TaskStatus.FAILED: frozenset(),
        TaskStatus.CANCELLED: frozenset(),
    }
)


def _validate_status(
    status: object,
    status_enum: type[_ResearchRunStatus] | type[_TaskStatus],
    status_kind: str,
) -> _ResearchRunStatus | _TaskStatus:
    if isinstance(status, status_enum):
        return status
    if isinstance(status, Enum):
        raise InvalidStatusError(status_kind, status)

    try:
        return status_enum(status)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise InvalidStatusError(status_kind, status) from None


def validate_research_run_status(status: object) -> ResearchRunStatus:
    """Return a validated research run status or raise ``invalid_status``."""

    return _validate_status(
        status, ResearchRunStatus, "research_run"
    )  # type: ignore[return-value]


def validate_task_status(status: object) -> TaskStatus:
    """Return a validated task status or raise ``invalid_status``."""

    return _validate_status(status, TaskStatus, "task")  # type: ignore[return-value]


def _transition(
    current_status: object,
    next_status: object,
    *,
    validator: object,
    transitions: Mapping[Enum, frozenset[Enum]],
    status_kind: str,
) -> Enum:
    current = validator(current_status)  # type: ignore[operator]
    next_value = validator(next_status)  # type: ignore[operator]
    if next_value not in transitions[current]:
        raise InvalidStatusTransitionError(status_kind, current, next_value)
    return next_value


def transition_research_run_status(
    current_status: object, next_status: object
) -> ResearchRunStatus:
    """Validate and apply one allowed research run transition."""

    return _transition(
        current_status,
        next_status,
        validator=validate_research_run_status,
        transitions=RESEARCH_RUN_TRANSITIONS,
        status_kind="research_run",
    )  # type: ignore[return-value]


def transition_task_status(current_status: object, next_status: object) -> TaskStatus:
    """Validate and apply one allowed task transition."""

    return _transition(
        current_status,
        next_status,
        validator=validate_task_status,
        transitions=TASK_TRANSITIONS,
        status_kind="task",
    )  # type: ignore[return-value]


def is_research_run_transition_allowed(
    current_status: object, next_status: object
) -> bool:
    """Return whether a validated research run transition is allowed."""

    try:
        transition_research_run_status(current_status, next_status)
    except InvalidStatusTransitionError:
        return False
    return True


def is_task_transition_allowed(current_status: object, next_status: object) -> bool:
    """Return whether a validated task transition is allowed."""

    try:
        transition_task_status(current_status, next_status)
    except InvalidStatusTransitionError:
        return False
    return True


def task_failure_status(retryable: bool) -> TaskStatus:
    """Select the next task status for a retryable or terminal failure."""

    return TaskStatus.RETRYING if retryable else TaskStatus.FAILED


def transition_task_failure(
    current_status: object, retryable: bool
) -> TaskStatus:
    """Apply the state transition represented by a task failure."""

    return transition_task_status(
        current_status, task_failure_status(retryable)
    )


def retryable_task_failure() -> TaskStatus:
    """Return the task status for a failure that should be retried."""

    return task_failure_status(True)


def terminal_task_failure() -> TaskStatus:
    """Return the task status for a failure that must not be retried."""

    return task_failure_status(False)
