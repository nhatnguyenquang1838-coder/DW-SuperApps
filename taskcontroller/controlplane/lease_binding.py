"""TC-MBX-801: bind one attempt to one WorkLease and fence result advancement.

The runtime ``WorkLease`` is the authoritative holder/fence/expiry reference.
This module is pure: it validates a caller-supplied attempt/result against that
lease and returns an evidence-only decision for missing, stale or mismatched
fences. It never mutates the lease, envelope, mailbox or run state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from taskcontroller.domain.enums import LeaseStatus
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import WorkLease
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope


class LeaseFenceDisposition(str, Enum):
    """Pure dispositions for a candidate state-advancing result."""

    ACCEPTED = "ACCEPTED"
    STALE_RESULT = "STALE_RESULT"


class LeaseBindingError(TaskControllerValidationError):
    """Fail-closed caller/input error for attempt-to-lease binding."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        failed_checks: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.failed_checks = tuple(failed_checks)
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class AttemptLeaseBinding:
    """Immutable binding between an attempt envelope and one WorkLease."""

    run_id: str
    node_id: str
    execution_id: str
    attempt_id: str
    lease_id: str
    holder: ProviderRef
    fencing_token: str
    lease_generation: int
    granted_at: str
    expires_at: str
    resource_ref: str | None
    status: str

    def __post_init__(self) -> None:
        if not isinstance(self.holder, ProviderRef):
            raise LeaseBindingError("ATTEMPT_LEASE_INVALID", "holder is invalid")
        if (
            isinstance(self.lease_generation, bool)
            or not isinstance(self.lease_generation, int)
            or self.lease_generation < 0
        ):
            raise LeaseBindingError(
                "ATTEMPT_LEASE_INVALID",
                "lease_generation must be an integer greater than or equal to zero",
            )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "execution_id": self.execution_id,
            "attempt_id": self.attempt_id,
            "lease_id": self.lease_id,
            "holder": self.holder.to_dict(),
            "fencing_token": self.fencing_token,
            "lease_generation": self.lease_generation,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }
        if self.resource_ref is not None:
            value["resource_ref"] = self.resource_ref
        return value


@dataclass(frozen=True, slots=True)
class LeaseFenceDecision:
    """Non-mutating result of checking a candidate against an active fence."""

    disposition: str
    advances_state: bool
    evidence_only: bool
    envelope_digest: str
    failed_checks: tuple[str, ...] = ()
    binding: AttemptLeaseBinding | None = None

    def __post_init__(self) -> None:
        if self.disposition == LeaseFenceDisposition.ACCEPTED.value:
            if not self.advances_state or self.evidence_only or self.failed_checks:
                raise ValueError("accepted lease fence must advance without failed checks")
            if self.binding is None:
                raise ValueError("accepted lease fence requires a binding")
        elif self.disposition == LeaseFenceDisposition.STALE_RESULT.value:
            if self.advances_state or not self.evidence_only or not self.failed_checks:
                raise ValueError("stale lease fence must be evidence-only")
        else:
            raise ValueError(f"unsupported lease fence disposition: {self.disposition!r}")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise LeaseBindingError("ATTEMPT_LEASE_INVALID", f"{field} must be a non-empty text value")
    return value.strip()


def _instant(value: Any, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise LeaseBindingError("LEASE_TIME_INVALID", f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise LeaseBindingError("LEASE_TIME_INVALID", f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _attempt_values(
    attempt: V2MailboxEnvelope | Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    if isinstance(attempt, V2MailboxEnvelope):
        return attempt.attempt, attempt.execution_identity
    if isinstance(attempt, Mapping):
        return dict(attempt), None
    raise LeaseBindingError(
        "ATTEMPT_LEASE_INVALID",
        "attempt must be a V2MailboxEnvelope or mapping",
    )


def _mismatch(
    failed_checks: list[str],
    field: str,
    actual: Any,
    expected: Any,
) -> None:
    if actual != expected:
        failed_checks.append(field)


def bind_attempt_to_work_lease(
    attempt: V2MailboxEnvelope | Mapping[str, Any],
    lease: WorkLease,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> AttemptLeaseBinding:
    """Bind an attempt's identity to the exact WorkLease supplied by Controller.

    The comparison is intentionally exact for the holder, fencing token and
    expiry string. A caller can retain a failed candidate as evidence, but it
    cannot turn a different lease into the current attempt by normalization.
    """

    if not isinstance(lease, WorkLease):
        raise LeaseBindingError("WORK_LEASE_INVALID", "active lease must be a WorkLease")
    attempt_values, envelope_identity = _attempt_values(attempt)
    identity = dict(envelope_identity or {})
    if expected_identity is not None:
        if not isinstance(expected_identity, Mapping):
            raise LeaseBindingError("ATTEMPT_LEASE_INVALID", "expected_identity must be an object")
        for key, value in expected_identity.items():
            if key in identity and identity[key] != value:
                raise LeaseBindingError(
                    "ATTEMPT_LEASE_MISMATCH",
                    f"expected identity differs for {key}",
                    failed_checks=(key,),
                )
            identity[key] = value

    required = ("attempt_id", "fencing_token", "agent_instance", "lease_expires_at", "lease_generation")
    missing = tuple(field for field in required if field not in attempt_values)
    if missing:
        raise LeaseBindingError(
            "ATTEMPT_LEASE_INVALID",
            "attempt is missing: " + ", ".join(missing),
            failed_checks=missing,
        )

    attempt_id = _text(attempt_values["attempt_id"], "attempt_id")
    fencing_token = _text(attempt_values["fencing_token"], "fencing_token")
    agent_instance = _text(attempt_values["agent_instance"], "agent_instance")
    expires_at = _text(attempt_values["lease_expires_at"], "lease_expires_at")
    lease_generation = attempt_values["lease_generation"]
    if (
        isinstance(lease_generation, bool)
        or not isinstance(lease_generation, int)
        or lease_generation < 0
    ):
        raise LeaseBindingError(
            "ATTEMPT_LEASE_INVALID",
            "lease_generation must be an integer greater than or equal to zero",
            failed_checks=("lease_generation",),
        )

    failed: list[str] = []
    _mismatch(failed, "attempt_id", attempt_id, lease.attempt_id)
    _mismatch(failed, "fencing_token", fencing_token, lease.fencing_token)
    _mismatch(failed, "holder", agent_instance, lease.holder.provider_id)
    _mismatch(failed, "lease_expires_at", expires_at, lease.expires_at)
    if lease.lease_generation is not None:
        _mismatch(failed, "lease_generation", lease_generation, lease.lease_generation)
    for field in ("run_id", "node_id"):
        if field in identity:
            _mismatch(failed, field, identity[field], getattr(lease, field))
    if "execution_id" in identity:
        _mismatch(failed, "execution_id", identity["execution_id"], lease.execution_id)
    if "attempt_id" in identity:
        _mismatch(failed, "attempt_id", identity["attempt_id"], lease.attempt_id)
    if "fencing_token" in identity:
        _mismatch(failed, "fencing_token", identity["fencing_token"], lease.fencing_token)
    if "lease_generation" in identity:
        _mismatch(failed, "lease_generation", identity["lease_generation"], lease_generation)
    if "lease_id" in attempt_values:
        _mismatch(failed, "lease_id", attempt_values["lease_id"], lease.lease_id)

    if failed:
        ordered = tuple(dict.fromkeys(failed))
        raise LeaseBindingError(
            "ATTEMPT_LEASE_MISMATCH",
            "attempt does not bind the supplied WorkLease: " + ", ".join(ordered),
            failed_checks=ordered,
        )

    return AttemptLeaseBinding(
        run_id=lease.run_id,
        node_id=lease.node_id,
        execution_id=lease.execution_id,
        attempt_id=lease.attempt_id,
        lease_id=lease.lease_id,
        holder=lease.holder,
        fencing_token=lease.fencing_token,
        lease_generation=lease_generation,
        granted_at=lease.granted_at,
        expires_at=lease.expires_at,
        resource_ref=lease.resource_ref,
        status=lease.status,
    )


def _stale(
    envelope_digest: str,
    failed_checks: tuple[str, ...],
    *,
    binding: AttemptLeaseBinding | None = None,
) -> LeaseFenceDecision:
    return LeaseFenceDecision(
        disposition=LeaseFenceDisposition.STALE_RESULT.value,
        advances_state=False,
        evidence_only=True,
        envelope_digest=envelope_digest,
        failed_checks=failed_checks,
        binding=binding,
    )


def evaluate_result_fence(
    envelope: V2MailboxEnvelope,
    active_lease: WorkLease | None,
    *,
    now: str | None,
) -> LeaseFenceDecision:
    """Classify a result as current or historical evidence only.

    ``active_lease=None`` is an explicit no-fence observation and therefore
    cannot advance state. ``now`` is caller-supplied; no wall clock is read.
    """

    if not isinstance(envelope, V2MailboxEnvelope):
        raise LeaseBindingError("RESULT_INVALID", "result fence evaluation requires a v2 envelope")
    envelope_digest = envelope.digest()
    if active_lease is None:
        return _stale(envelope_digest, ("active_lease",))
    try:
        binding = bind_attempt_to_work_lease(envelope, active_lease)
    except LeaseBindingError as exc:
        return _stale(envelope_digest, exc.failed_checks or ("lease_binding",))

    if active_lease.status != LeaseStatus.ACTIVE.value:
        return _stale(envelope_digest, ("lease_status",), binding=binding)
    if now is None:
        raise LeaseBindingError("LEASE_TIME_REQUIRED", "now is required for active lease evaluation")
    if _instant(active_lease.expires_at, "lease.expires_at") < _instant(now, "now"):
        return _stale(envelope_digest, ("lease_expiry",), binding=binding)

    return LeaseFenceDecision(
        disposition=LeaseFenceDisposition.ACCEPTED.value,
        advances_state=True,
        evidence_only=False,
        envelope_digest=envelope_digest,
        binding=binding,
    )


__all__ = [
    "AttemptLeaseBinding",
    "LeaseBindingError",
    "LeaseFenceDecision",
    "LeaseFenceDisposition",
    "bind_attempt_to_work_lease",
    "evaluate_result_fence",
]
