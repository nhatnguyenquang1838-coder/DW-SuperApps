"""TC-MBX-804: Controller-bound lease-generation takeover.

Takeover is a lease handoff for the same logical attempt.  New-attempt creation
belongs to ``retry.py``; this module only retires the old lease, routes the same
contract to a compatible generic AgentInstance, and grants a strictly newer
fence after retirement.  It performs no mailbox, Slack, GitHub, dispatch, or
worker side effect.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, NoReturn

from taskcontroller.controlplane.agent_routing import (
    RoutedMailboxRequest,
    route_bounded_mailbox_request,
)
from taskcontroller.controlplane.lease_binding import bind_attempt_to_work_lease
from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.domain.enums import LeaseStatus
from taskcontroller.domain.models import WorkLease
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.routing.registry import Registry
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import VersionedRunState


class TakeoverRetirement(str, Enum):
    """Explicit disposition for the lease being taken over."""

    REVOKE = "REVOKE"
    EXPIRE = "EXPIRE"


class TakeoverValidationError(TaskControllerValidationError):
    """Fail-closed validation error for a takeover candidate."""

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
class TakeoverResult:
    """The routed replacement and the post-CAS runtime state."""

    routed: RoutedMailboxRequest
    retired_lease: WorkLease
    replacement_lease: WorkLease
    retired_status: str
    state: VersionedRunState


def _fail(
    code: str,
    message: str,
    *,
    failed_checks: tuple[str, ...] = (),
) -> NoReturn:
    raise TakeoverValidationError(code, message, failed_checks=failed_checks)


def _request(
    value: BoundedMailboxRequest | Mapping[str, Any],
) -> BoundedMailboxRequest:
    if isinstance(value, BoundedMailboxRequest):
        return value
    if isinstance(value, Mapping):
        return BoundedMailboxRequest.from_mapping(value)
    _fail("TAKEOVER_REQUEST_INVALID", "request must be a BoundedMailboxRequest or mapping")


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _fail("TAKEOVER_TIME_INVALID", f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise TakeoverValidationError(
            "TAKEOVER_TIME_INVALID", f"{field} is not ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        _fail("TAKEOVER_TIME_INVALID", f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _state_lease(state: VersionedRunState, lease_id: str) -> WorkLease | None:
    meta = state.meta
    leases = getattr(meta, "leases", None)
    if leases is not None and hasattr(leases, "leases"):
        candidate = leases.leases.get(lease_id)
        return candidate if isinstance(candidate, WorkLease) else None
    if isinstance(meta, Mapping):
        raw = meta.get("leases", {})
        if hasattr(raw, "leases"):
            candidate = raw.leases.get(lease_id)
            return candidate if isinstance(candidate, WorkLease) else None
        if isinstance(raw, Mapping):
            candidate = raw.get(lease_id)
            if isinstance(candidate, WorkLease):
                return candidate
            if isinstance(candidate, Mapping):
                return WorkLease.from_dict(dict(candidate))
    return None


def _same_logical_attempt(
    old_request: BoundedMailboxRequest,
    replacement_request: BoundedMailboxRequest,
) -> None:
    old_envelope = compile_bounded_mailbox_request(old_request)
    replacement_envelope = compile_bounded_mailbox_request(replacement_request)
    if old_envelope.logical_contract != replacement_envelope.logical_contract:
        _fail(
            "TAKEOVER_CONTRACT_MISMATCH",
            "replacement changes the logical TaskContract",
            failed_checks=("logical_contract",),
        )

    for field in (
        "run_id",
        "node_id",
        "contract_id",
        "plan_version",
        "contract_digest",
        "boundary_digest",
        "source_digest",
        "source_manifest_ref",
        "standards_profile_ref",
        "objective",
        "scope",
        "authority_constraints",
        "acceptance_criteria",
        "source_refs",
        "evidence_refs",
        "recipient_capability",
        "environment_requirements",
        "execution_id",
        "attempt_id",
        "attempt_number",
        "producer_namespace",
        "producer_actor_id",
    ):
        if getattr(old_request, field) != getattr(replacement_request, field):
            _fail(
                "TAKEOVER_IDENTITY_MISMATCH",
                f"replacement differs for {field}",
                failed_checks=(field,),
            )

    old_identity = old_envelope.execution_identity
    replacement_identity = replacement_envelope.execution_identity
    for field in (
        "run_id",
        "node_id",
        "plan_version",
        "contract_digest",
        "boundary_digest",
        "source_digest",
        "attempt_id",
    ):
        if old_identity[field] != replacement_identity[field]:
            _fail(
                "TAKEOVER_IDENTITY_MISMATCH",
                f"replacement execution identity differs for {field}",
                failed_checks=(field,),
            )

    if replacement_request.message_id == old_request.message_id:
        _fail("TAKEOVER_ORDER_INVALID", "replacement message_id must be new", failed_checks=("message_id",))
    if replacement_request.seq <= old_request.seq:
        _fail("TAKEOVER_ORDER_INVALID", "replacement seq must be newer", failed_checks=("seq",))
    if replacement_request.lease_generation <= old_request.lease_generation:
        _fail(
            "TAKEOVER_ORDER_INVALID",
            "replacement lease_generation must be strictly newer",
            failed_checks=("lease_generation",),
        )
    if replacement_request.fencing_token == old_request.fencing_token:
        _fail(
            "TAKEOVER_FENCE_REUSE",
            "replacement fencing_token must be new",
            failed_checks=("fencing_token",),
        )
    if replacement_request.idempotency_key == old_request.idempotency_key:
        _fail(
            "TAKEOVER_IDEMPOTENCY_REUSE",
            "replacement idempotency_key must be new",
            failed_checks=("idempotency_key",),
        )


def takeover_bounded_mailbox_request(
    registry: Registry,
    old_request: BoundedMailboxRequest | Mapping[str, Any],
    old_lease: WorkLease,
    replacement_request: BoundedMailboxRequest | Mapping[str, Any],
    replacement_lease: WorkLease,
    *,
    lease_manager: LeaseManager,
    current_state: VersionedRunState,
    expected_version: int,
    retirement: TakeoverRetirement | str,
    now: str,
    receipt_id: str,
    accepted_at: str | None = None,
) -> TakeoverResult:
    """Retire one lease, route its same attempt, then grant the replacement.

    All identity, ordering, routing and lease checks happen before the first
    state mutation.  The old lease is retired with the explicit disposition;
    only then does the existing ``LeaseManager.grant`` CAS the replacement.
    """
    old = _request(old_request)
    replacement = _request(replacement_request)
    if not isinstance(old_lease, WorkLease) or not isinstance(replacement_lease, WorkLease):
        _fail("TAKEOVER_LEASE_INVALID", "old and replacement leases are required")
    if not isinstance(current_state, VersionedRunState):
        _fail("TAKEOVER_STATE_INVALID", "current_state must be a VersionedRunState")
    if expected_version != current_state.version:
        _fail(
            "TAKEOVER_VERSION_INVALID",
            "expected_version must bind the supplied current_state",
            failed_checks=("expected_version",),
        )

    try:
        mode = retirement if isinstance(retirement, TakeoverRetirement) else TakeoverRetirement(retirement)
    except (TypeError, ValueError) as exc:
        raise TakeoverValidationError(
            "TAKEOVER_RETIREMENT_INVALID", f"unsupported retirement: {retirement!r}"
        ) from exc
    now_instant = _instant(now, "now")

    old_envelope = compile_bounded_mailbox_request(old)
    bind_attempt_to_work_lease(old_envelope, old_lease)
    if old_lease.status != LeaseStatus.ACTIVE.value:
        _fail(
            "TAKEOVER_OLD_LEASE_NOT_ACTIVE",
            f"old lease is {old_lease.status}, not ACTIVE",
            failed_checks=("old_lease.status",),
        )
    stored_old = _state_lease(current_state, old_lease.lease_id)
    if stored_old is None or stored_old.to_dict() != old_lease.to_dict():
        _fail(
            "TAKEOVER_OLD_LEASE_MISMATCH",
            "old lease is not the exact current runtime lease",
            failed_checks=("old_lease",),
        )

    _same_logical_attempt(old, replacement)
    if replacement.attempt_id != old.attempt_id:
        _fail(
            "TAKEOVER_ATTEMPT_CHANGED",
            "takeover cannot create a new attempt; use retry.py",
            failed_checks=("attempt_id",),
        )
    if replacement_lease.lease_id == old_lease.lease_id:
        _fail("TAKEOVER_LEASE_REUSE", "replacement lease_id must be new", failed_checks=("lease_id",))
    if replacement_lease.fencing_token == old_lease.fencing_token:
        _fail(
            "TAKEOVER_FENCE_REUSE",
            "replacement WorkLease fencing_token must be new",
            failed_checks=("fencing_token",),
        )
    if replacement_lease.status != LeaseStatus.ACTIVE.value:
        _fail(
            "TAKEOVER_REPLACEMENT_NOT_ACTIVE",
            "replacement WorkLease must be ACTIVE",
            failed_checks=("replacement_lease.status",),
        )
    if (
        replacement_lease.lease_generation is not None
        and replacement_lease.lease_generation != replacement.lease_generation
    ):
        _fail(
            "TAKEOVER_GENERATION_MISMATCH",
            "replacement WorkLease generation differs from replacement request",
            failed_checks=("lease_generation",),
        )
    # A v2 replacement request is the generation authority.  Normalize an
    # omitted legacy WorkLease field to that request generation before binding
    # and granting, while rejecting an explicitly conflicting fence.
    replacement_lease = replace(
        replacement_lease,
        lease_generation=replacement.lease_generation,
    )
    if mode is TakeoverRetirement.EXPIRE and _instant(old_lease.expires_at, "old_lease.expires_at") >= now_instant:
        _fail(
            "TAKEOVER_EXPIRE_REQUIRES_EXPIRED_LEASE",
            "EXPIRE is reserved for a lease already past expiry; use REVOKE for forced takeover",
            failed_checks=("old_lease.expires_at",),
        )

    routed = route_bounded_mailbox_request(
        registry,
        replacement,
        receipt_id=receipt_id,
        accepted_at=accepted_at,
    )
    if routed.request.attempt_id != old.attempt_id:
        _fail("TAKEOVER_ATTEMPT_CHANGED", "route changed attempt_id", failed_checks=("attempt_id",))
    if routed.request.agent_instance == old.agent_instance and mode is TakeoverRetirement.REVOKE:
        _fail(
            "TAKEOVER_AGENT_NOT_CHANGED",
            "forced takeover must route to a different AgentInstance",
            failed_checks=("agent_instance",),
        )
    bind_attempt_to_work_lease(routed.envelope, replacement_lease)
    if replacement_lease.run_id != old_lease.run_id or replacement_lease.node_id != old_lease.node_id:
        _fail(
            "TAKEOVER_LEASE_SCOPE_MISMATCH",
            "replacement WorkLease does not bind the same run/node",
            failed_checks=("run_id", "node_id"),
        )
    if replacement_lease.execution_id != old_lease.execution_id or replacement_lease.attempt_id != old_lease.attempt_id:
        _fail(
            "TAKEOVER_LEASE_SCOPE_MISMATCH",
            "replacement WorkLease does not bind the same execution/attempt",
            failed_checks=("execution_id", "attempt_id"),
        )
    if replacement_lease.holder.provider_id != routed.selected_agent_instance:
        _fail(
            "TAKEOVER_ROUTE_LEASE_MISMATCH",
            "replacement lease holder differs from selected AgentInstance",
            failed_checks=("holder",),
        )

    if mode is TakeoverRetirement.EXPIRE:
        retired_state = lease_manager.expire(
            old_lease.lease_id,
            expected_version,
            current_state,
            now,
        )
    else:
        retired_state = lease_manager.revoke(
            old_lease.lease_id,
            expected_version,
            current_state,
        )
    active_state = lease_manager.grant(
        replacement_lease,
        retired_state.version,
        retired_state,
    )

    expected_retired_status = (
        LeaseStatus.REVOKED.value
        if mode is TakeoverRetirement.REVOKE
        else LeaseStatus.EXPIRED.value
    )
    retired = _state_lease(active_state, old_lease.lease_id)
    current_replacement = _state_lease(active_state, replacement_lease.lease_id)
    if retired is None or retired.status != expected_retired_status:
        _fail(
            "TAKEOVER_RETIREMENT_READBACK_FAILED",
            "old lease retirement did not read back as requested",
            failed_checks=("old_lease.status",),
        )
    if current_replacement is None or current_replacement.status != LeaseStatus.ACTIVE.value:
        _fail(
            "TAKEOVER_GRANT_READBACK_FAILED",
            "replacement lease did not read back ACTIVE",
            failed_checks=("replacement_lease.status",),
        )

    return TakeoverResult(
        routed=routed,
        retired_lease=retired,
        replacement_lease=current_replacement,
        retired_status=expected_retired_status,
        state=active_state,
    )


__all__ = [
    "TakeoverRetirement",
    "TakeoverResult",
    "TakeoverValidationError",
    "takeover_bounded_mailbox_request",
]
