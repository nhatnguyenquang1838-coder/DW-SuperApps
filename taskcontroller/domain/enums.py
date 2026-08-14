"""WP0 TaskController canonical enums (language-neutral, product-name free)."""

from __future__ import annotations

from enum import Enum

from taskcontroller.errors import TaskControllerValidationError


class _StrEnum(str, Enum):
    """Enum whose members are also real strings (JSON-serializable)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


def _member_names(cls) -> str:
    return ", ".join(e.value for e in cls)


def as_enum(enum_cls, value, field):
    """Validate ``value`` against ``enum_cls``; raise TaskControllerValidationError on miss."""
    try:
        return enum_cls(value)
    except ValueError:
        valid = _member_names(enum_cls)
        raise TaskControllerValidationError(
            f"invalid {field}: {value!r}; expected one of {valid}"
        ) from None


class ProviderKind(_StrEnum):
    """What kind of executable provider an instance is (generic, not a product)."""

    LOCAL = "LOCAL"
    CONNECTOR = "CONNECTOR"
    AGENT = "AGENT"
    SERVICE = "SERVICE"
    TOOL = "TOOL"


class ActorKind(_StrEnum):
    """Role/actor classification of a runtime host (kept distinct from provider kind)."""

    CONTROLLER = "CONTROLLER"
    AGENT = "AGENT"
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"
    TOOL = "TOOL"


class TrustTier(_StrEnum):
    TRUSTED = "TRUSTED"
    STANDARD = "STANDARD"
    SANDBOX = "SANDBOX"
    UNVERIFIED = "UNVERIFIED"


class Idempotency(_StrEnum):
    IDEMPOTENT = "IDEMPOTENT"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    BEST_EFFORT = "BEST_EFFORT"


class CostClass(_StrEnum):
    FREE = "FREE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BindingType(_StrEnum):
    """Generic communication/channel kind; concrete products map onto these."""

    LOCAL_IPC = "LOCAL_IPC"
    CHAT = "CHAT"
    HTTP_API = "HTTP_API"
    CONNECTOR = "CONNECTOR"
    CLI = "CLI"
    GRPC = "GRPC"
    WEBHOOK = "WEBHOOK"
    MCP = "MCP"


class EventType(_StrEnum):
    TASK_STARTED = "TASK_STARTED"
    PROGRESS = "PROGRESS"
    ARTIFACT_PRODUCED = "ARTIFACT_PRODUCED"
    STATUS_CHANGE = "STATUS_CHANGE"
    NEEDS_INPUT = "NEEDS_INPUT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEW_SUBMITTED = "REVIEW_SUBMITTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    HEARTBEAT = "HEARTBEAT"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"
    CHECKPOINT = "CHECKPOINT"


class ExecutionStatus(_StrEnum):
    PENDING = "PENDING"
    ROUTING = "ROUTING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    WAITING = "WAITING"


class LeaseStatus(_StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"
    REVOKED = "REVOKED"


class RunStatus(_StrEnum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NodeStatus(_StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    REVIEWING = "REVIEWING"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    RETRY_READY = "RETRY_READY"
    CANCELLED = "CANCELLED"
    LEASE_EXPIRED = "LEASE_EXPIRED"


class ReviewVerdict(_StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_FIX = "NEEDS_FIX"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class DecisionType(_StrEnum):
    CONTINUE = "CONTINUE"
    WAIT = "WAIT"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    CANCEL = "CANCEL"
    COMPLETE = "COMPLETE"
    ESCALATE = "ESCALATE"


class Priority(_StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Locality(_StrEnum):
    LOCAL = "LOCAL"
    REMOTE = "REMOTE"
    ANY = "ANY"


__all__ = [
    "ProviderKind",
    "ActorKind",
    "TrustTier",
    "Idempotency",
    "CostClass",
    "BindingType",
    "EventType",
    "ExecutionStatus",
    "LeaseStatus",
    "RunStatus",
    "NodeStatus",
    "ReviewVerdict",
    "DecisionType",
    "Priority",
    "Locality",
]
