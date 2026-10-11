"""Fail-closed orchestration policies for mailbox/v2 and peer collaboration.

Legacy Controller/Executor mailbox roles remain valid transport/writer
namespaces, not an agent hierarchy. Two separately admitted AI peers may
propose, challenge and agree within existing delegated authority. Agreements,
Loop wake-ups and cursor observation never issue lease/approval/effect authority.

The policy is deliberately transport-neutral and grants no authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, NoReturn, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope


BLOCKER_AUTHORITY_BOUNDARY = "AUTHORITY_BOUNDARY"
BLOCKER_SCOPE_EXPANSION = "SCOPE_EXPANSION"
BLOCKER_MATERIAL_PLAN_INVALIDATION = "MATERIAL_PLAN_INVALIDATION"
BLOCKER_EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY_BLOCKED"

EXECUTOR_BLOCKER_CLASSES = frozenset(
    {
        BLOCKER_AUTHORITY_BOUNDARY,
        BLOCKER_SCOPE_EXPANSION,
        BLOCKER_MATERIAL_PLAN_INVALIDATION,
        BLOCKER_EXTERNAL_DEPENDENCY,
    }
)

HOLD_EFFECT = "EFFECT_HOLD"
HOLD_RUN = "RUN_HOLD"
HOLD_TYPES = frozenset({HOLD_EFFECT, HOLD_RUN})

_BLOCKING_PROGRESS_STATUSES = frozenset({"BLOCKED", "NEEDS_CLARIFICATION"})
_FORBIDDEN_USER_WAIT_PREFIXES = ("WAIT_USER", "WAIT_HUMAN")
_FORBIDDEN_EXECUTOR_HITL_KEYS = frozenset(
    {
        "approval_command",
        "approval_token",
        "human_approval_command",
        "user_approval",
        "wait_user",
    }
)


class OrchestrationPolicyError(TaskControllerValidationError):
    """Stable fail-closed error for anti-stuck orchestration invariants."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise OrchestrationPolicyError(code, message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must be non-empty")
    return value.strip()


def _string_list(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must be an array")
    result = tuple(_text(item, f"{field}[]") for item in value)
    if not allow_empty and not result:
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must not be empty")
    if len(set(result)) != len(result):
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class ExecutorProgressOutcome:
    """Validated Executor progress/completion/boundary report."""

    envelope: V2MailboxEnvelope
    status: str
    typed_next: str | None
    blocker_class: str | None
    blocker_detail: str | None
    report_type: str | None

    @property
    def requires_controller_action(self) -> bool:
        return self.blocker_class is not None or self.status in _BLOCKING_PROGRESS_STATUSES

    @property
    def completed(self) -> bool:
        return self.status == "SUCCEEDED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "typed_next": self.typed_next,
            "blocker_class": self.blocker_class,
            "blocker_detail": self.blocker_detail,
            "report_type": self.report_type,
            "requires_controller_action": self.requires_controller_action,
            "completed": self.completed,
        }


def validate_executor_progress(envelope: V2MailboxEnvelope) -> ExecutorProgressOutcome:
    """Validate one executor_to_controller execution_progress envelope.

    A blocker is always reported to the Controller. The Executor cannot emit
    a User/Human wait semantic or carry an approval command/token.
    """

    if not isinstance(envelope, V2MailboxEnvelope):
        _fail("EXECUTOR_PROGRESS_INVALID", "progress must be a V2MailboxEnvelope")
    raw = envelope.to_dict()
    if raw.get("message_type") != "execution_progress":
        _fail("EXECUTOR_PROGRESS_INVALID", "message_type must be execution_progress")
    if raw.get("direction") != "executor_to_controller":
        _fail("EXECUTOR_PROGRESS_DIRECTION_INVALID", "Executor progress must flow executor_to_controller")
    producer = raw.get("producer")
    if not isinstance(producer, Mapping) or producer.get("role") != "executor":
        _fail("EXECUTOR_PROGRESS_PRODUCER_INVALID", "execution_progress producer role must be executor")
    recipient = raw.get("recipient")
    if not isinstance(recipient, Mapping) or recipient.get("capability") != "taskcontroller.controller":
        _fail("EXECUTOR_PROGRESS_RECIPIENT_INVALID", "Executor progress must target taskcontroller.controller")

    payload = raw.get("payload")
    if not isinstance(payload, Mapping):
        _fail("EXECUTOR_PROGRESS_INVALID", "execution_progress payload must be an object")
    forbidden = _FORBIDDEN_EXECUTOR_HITL_KEYS.intersection(payload)
    if forbidden:
        _fail(
            "EXECUTOR_USER_HITL_FORBIDDEN",
            "Executor cannot materialize User/Human approval fields: " + ", ".join(sorted(forbidden)),
        )

    provenance = raw.get("provenance")
    provenance_status = provenance.get("status") if isinstance(provenance, Mapping) else None
    status = _text(payload.get("status", provenance_status), "payload.status").upper()

    typed_next_raw = payload.get("typed_next")
    typed_next = None if typed_next_raw is None else _text(typed_next_raw, "payload.typed_next")
    if typed_next is not None and typed_next.upper().startswith(_FORBIDDEN_USER_WAIT_PREFIXES):
        _fail(
            "EXECUTOR_USER_HITL_FORBIDDEN",
            "Executor must return a Controller boundary; it cannot wait for User/Human approval directly",
        )

    blocker_raw = payload.get("blocker_class")
    blocker_class = None if blocker_raw is None else _text(blocker_raw, "payload.blocker_class").upper()
    if blocker_class is not None and blocker_class not in EXECUTOR_BLOCKER_CLASSES:
        _fail(
            "EXECUTOR_BLOCKER_CLASS_INVALID",
            "blocker_class must be one of " + ", ".join(sorted(EXECUTOR_BLOCKER_CLASSES)),
        )
    if status in _BLOCKING_PROGRESS_STATUSES and blocker_class is None:
        _fail(
            "EXECUTOR_BLOCKER_CLASS_REQUIRED",
            "blocked/needs-clarification progress requires one canonical blocker_class",
        )

    detail_raw = payload.get("blocker_detail")
    blocker_detail = None if detail_raw is None else _text(detail_raw, "payload.blocker_detail")
    if blocker_class is not None and blocker_detail is None:
        _fail("EXECUTOR_BLOCKER_DETAIL_REQUIRED", "blocker_class requires blocker_detail")

    report_raw = payload.get("report_type")
    report_type = None if report_raw is None else _text(report_raw, "payload.report_type")

    return ExecutorProgressOutcome(
        envelope=envelope,
        status=status,
        typed_next=typed_next,
        blocker_class=blocker_class,
        blocker_detail=blocker_detail,
        report_type=report_type,
    )


@dataclass(frozen=True, slots=True)
class HoldSemantics:
    hold_type: str
    denied_effects: tuple[str, ...]
    control_loop_continues: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.hold_type,
            "denied_effects": list(self.denied_effects),
            "control_loop_continues": self.control_loop_continues,
        }


def validate_hold_semantics(payload: Mapping[str, Any]) -> HoldSemantics | None:
    """Validate explicit EFFECT_HOLD vs RUN_HOLD semantics on Controller payloads."""

    if not isinstance(payload, Mapping):
        _fail("ORCHESTRATION_POLICY_INVALID", "Controller payload must be an object")
    hold = payload.get("hold")
    disposition = payload.get("disposition")
    disposition_mentions_hold = isinstance(disposition, str) and "HOLD" in disposition.upper()
    if hold is None:
        if disposition_mentions_hold:
            _fail(
                "AMBIGUOUS_HOLD_FORBIDDEN",
                "HOLD disposition must declare typed hold semantics (EFFECT_HOLD or RUN_HOLD)",
            )
        return None
    if not isinstance(hold, Mapping):
        _fail("HOLD_POLICY_INVALID", "hold must be an object")

    hold_type = _text(hold.get("type"), "hold.type").upper()
    if hold_type not in HOLD_TYPES:
        _fail("HOLD_POLICY_INVALID", "hold.type must be EFFECT_HOLD or RUN_HOLD")
    denied_effects = _string_list(
        hold.get("denied_effects", ()),
        "hold.denied_effects",
        allow_empty=hold_type == HOLD_RUN,
    )
    continues = hold.get("control_loop_continues")
    if not isinstance(continues, bool):
        _fail("HOLD_POLICY_INVALID", "hold.control_loop_continues must be boolean")

    if hold_type == HOLD_EFFECT and not continues:
        _fail(
            "EFFECT_HOLD_MUST_CONTINUE_CONTROL_LOOP",
            "EFFECT_HOLD gates named effects only; Controller reasoning/planning must continue",
        )
    if hold_type == HOLD_RUN and continues:
        _fail("RUN_HOLD_MUST_STOP_CONTROL_LOOP", "RUN_HOLD must stop new run actions")

    return HoldSemantics(
        hold_type=hold_type,
        denied_effects=denied_effects,
        control_loop_continues=continues,
    )


# Native Hermes LoopManager rows are *host schedulers*, never TaskController
# continuation state. In particular, pausing a polling Loop MUST NOT be used
# as a proxy for terminating the Executor session or the Controller run.

# This is a Controller *resolution* decision, not an authority grant.  A
# historical event/approval can never be rebound to a fresh run by this API.
AUTHORITY_REQUEST_ROUTES = frozenset({"HUMAN", "DELEGATE", "NONE"})


@dataclass(frozen=True, slots=True)
class AuthorityRecoveryDecision:
    next_action: str
    next_owner: str
    protected_effects_allowed: bool
    approval_request_required: bool
    actionable_request_required: bool
    current_run_id: str
    rejected_historical_run_id: str | None = None


def decide_stale_authority_recovery(
    *,
    current_run_id: str,
    observed_event_run_id: str,
    approval_current: bool,
    execution_lease_current: bool,
    renewal_route: str,
    user_paused: bool = False,
    run_hold: bool = False,
) -> AuthorityRecoveryDecision:
    """Resolve expired authority without replay, forging approval or dispatch.

    The Controller calls this on an exact-read current run.  A request route
    is a capability to ASK only; it never authorizes an Executor effect.
    A valid approval with an expired attempt lease must not needlessly be
    re-approved. The caller must validate lease issuance capabilities before
    generating any new attempt/lease and must materialize/route requests
    through the existing canonical approval machinery.
    """
    current = _text(current_run_id, "current_run_id")
    observed = _text(observed_event_run_id, "observed_event_run_id")
    route = _text(renewal_route, "renewal_route").upper()
    if route not in AUTHORITY_REQUEST_ROUTES:
        _fail("AUTHORITY_ROUTE_INVALID", "renewal_route must be HUMAN, DELEGATE, or NONE")
    for name, value in (
        ("approval_current", approval_current),
        ("execution_lease_current", execution_lease_current),
        ("user_paused", user_paused),
        ("run_hold", run_hold),
    ):
        if not isinstance(value, bool):
            _fail("AUTHORITY_RECOVERY_INVALID", f"{name} must be boolean")
    if run_hold or user_paused:
        return AuthorityRecoveryDecision(
            next_action="RESOLVE_RUN_HOLD" if run_hold else "RESOLVE_USER_PAUSE",
            next_owner="CONTROLLER",
            protected_effects_allowed=False,
            approval_request_required=False,
            actionable_request_required=False,
            current_run_id=current,
            rejected_historical_run_id=observed if observed != current else None,
        )
    if observed != current:
        return AuthorityRecoveryDecision(
            next_action="RECOVER_CURRENT_RUN_BINDING",
            next_owner="CONTROLLER",
            protected_effects_allowed=False,
            approval_request_required=False,
            actionable_request_required=False,
            current_run_id=current,
            rejected_historical_run_id=observed,
        )
    if approval_current:
        return AuthorityRecoveryDecision(
            next_action="CONTINUE_WITH_CURRENT_FENCE" if execution_lease_current else "ISSUE_FRESH_ATTEMPT_LEASE",
            next_owner="CONTROLLER",
            protected_effects_allowed=False,
            approval_request_required=False,
            actionable_request_required=False,
            current_run_id=current,
        )
    if route == "NONE":
        return AuthorityRecoveryDecision(
            next_action="AUTHORITY_REQUEST_UNROUTED",
            next_owner="CONTROLLER",
            protected_effects_allowed=False,
            approval_request_required=True,
            actionable_request_required=True,
            current_run_id=current,
        )
    return AuthorityRecoveryDecision(
        next_action="MATERIALIZE_HUMAN_APPROVAL_REQUEST" if route == "HUMAN" else "DISPATCH_DELEGATED_AUTHORITY_REQUEST",
        next_owner="CONTROLLER",
        protected_effects_allowed=False,
        approval_request_required=True,
        actionable_request_required=True,
        current_run_id=current,
    )


@dataclass(frozen=True, slots=True)
class PeerCollaborationDecision:
    """A shared semantic decision, not a new execution or approval grant."""

    status: str
    typed_next: str
    requires_human: bool
    authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "typed_next": self.typed_next,
            "requires_human": self.requires_human,
            "authority_granted": self.authority_granted,
        }


def decide_peer_collaboration(
    *,
    actor_a: str,
    actor_b: str,
    proposal_digest_a: str | None,
    proposal_digest_b: str | None,
    scope_current: bool,
    existing_effect_authority: bool,
    discussion_round: int,
    max_rounds: int,
    user_paused: bool = False,
    run_hold: bool = False,
) -> PeerCollaborationDecision:
    """Symmetric, bounded peer decision over pre-existing delegated authority.

    Both digests refer to an independently persisted/signed common proposal;
    caller is responsible for validating artifact, actor credentials and scope.
    The result does NOT issue a lease, append a mailbox event, authorize a
    protected effect, or substitute for either actor's immutable receipt.
    It is safe for either peer to initiate the discussion.
    """
    first, second = _text(actor_a, "actor_a"), _text(actor_b, "actor_b")
    if first == second:
        _fail("PEER_IDENTITY_COLLISION", "peer actors must be distinct")
    for name, val in (
        ("scope_current", scope_current),
        ("existing_effect_authority", existing_effect_authority),
        ("user_paused", user_paused),
        ("run_hold", run_hold),
    ):
        if not isinstance(val, bool):
            _fail("PEER_BINDING_INVALID", f"{name} must be boolean")
    if (type(max_rounds) is not int or type(discussion_round) is not int
        or max_rounds < 1 or not 1 <= discussion_round <= max_rounds):
        _fail("PEER_ROUND_INVALID", "discussion budget/round is invalid")
    for name, digest in (("proposal_digest_a", proposal_digest_a), ("proposal_digest_b", proposal_digest_b)):
        if digest is None:
            continue
        if (not isinstance(digest, str) or not digest.startswith("sha256:")
            or len(digest) != 71 or any(c not in "0123456789abcdef" for c in digest[7:])):
            _fail("PEER_DIGEST_INVALID", f"{name} must be a canonical sha256 digest")

    def result(status: str, next_action: str, *, human: bool = False) -> PeerCollaborationDecision:
        return PeerCollaborationDecision(status, next_action, human)

    if user_paused:
        return result("PAUSED", "RESOLVE_USER_PAUSE")
    if run_hold:
        return result("PAUSED", "RESOLVE_RUN_HOLD")
    if proposal_digest_a and proposal_digest_a == proposal_digest_b:
        if not scope_current or not existing_effect_authority:
            return result("AUTHORITY_BOUNDARY", "REQUEST_BOUNDED_AUTHORITY")
        return result("AGREED", "CONTINUE_WITH_EXISTING_AUTHORITY")
    if discussion_round >= max_rounds:
        return result("NEEDS_HUMAN_DECISION", "RESOLVE_PEER_DISAGREEMENT", human=True)
    return result("DISCUSS", "CONTINUE_PEER_DISCUSSION")


HOST_LOOP_ROLES = frozenset({"MAILBOX_POLL", "CONTROLLER_WAKEUP_POLL", "MAILBOX_OBSERVER", "ENGINEERING_WORK", "UNRELATED"})
POLLING_LOOP_ROLES = frozenset({"MAILBOX_POLL", "CONTROLLER_WAKEUP_POLL"})


@dataclass(frozen=True, slots=True)
class ExecutorLoopContinuity:
    """Pure, transport-neutral Loop/Executor boundary decision; no host mutation."""

    scheduler_action: str
    executor_session_action: str
    next_owner: str
    typed_next: str
    effects_allowed: bool
    auto_resume_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduler_action": self.scheduler_action,
            "executor_session_action": self.executor_session_action,
            "next_owner": self.next_owner,
            "typed_next": self.typed_next,
            "effects_allowed": self.effects_allowed,
            "auto_resume_allowed": self.auto_resume_allowed,
        }


def decide_executor_loop_continuity(
    *,
    loop_role: str,
    loop_run_id: str,
    canonical_run_id: str,
    execute_contract_current: bool,
    awaiting_controller_event: bool = False,
    hold_type: str | None = None,
    user_paused: bool = False,
    terminal_verified: bool = False,
    event_adapter_qualified: bool = True,
    mailbox_observer_qualified: bool = False,
    newer_event_observed: bool = False,
) -> ExecutorLoopContinuity:
    """Disentangle *native scheduler control* from *TaskController liveness*.

    This does NOT issue a LoopManager.pause()/resume(), grant effect authority,
    admit an actor/adapter, verify a lease, or create a mailbox event.
    Callers supply live exact-readback booleans and use an independently
    admitted event adapter. A waiting Executor is not a terminal run.

    Old unqualified mailbox-poll schedulers stay quarantined/paused.
    A separately qualified MAILBOX_OBSERVER may inspect the exact cursor with
    a bounded read-only cadence, independent of effect/lease authority. Even a
    new event requires exact readback and fresh PRECHECK before effect writes.
    This pure decision never starts, resumes or fires native Hermes LoopManager.
    """
    if loop_role not in HOST_LOOP_ROLES:
        _fail("LOOP_ROLE_INVALID", f"unsupported loop_role: {loop_role!r}")
    _text(loop_run_id, "loop_run_id")
    _text(canonical_run_id, "canonical_run_id")
    if hold_type is not None and hold_type not in HOLD_TYPES:
        _fail("LOOP_HOLD_INVALID", "hold_type must be EFFECT_HOLD, RUN_HOLD, or None")
    for key, value in (
        ("execute_contract_current", execute_contract_current),
        ("awaiting_controller_event", awaiting_controller_event),
        ("user_paused", user_paused),
        ("terminal_verified", terminal_verified),
        ("event_adapter_qualified", event_adapter_qualified),
        ("mailbox_observer_qualified", mailbox_observer_qualified),
        ("newer_event_observed", newer_event_observed),
    ):
        if not isinstance(value, bool):
            _fail("LOOP_CONTRACT_INVALID", f"{key} must be boolean")

    # An unrelated host scheduler is never ours to pause or quarantine, even
    # when it belongs to a different run. Its owner controls that Loop row.
    if loop_role == "UNRELATED":
        return ExecutorLoopContinuity(
            scheduler_action="NO_AUTOMATIC_LOOP_MUTATION",
            executor_session_action="PRESERVE_EXECUTOR_SESSION",
            next_owner="CONTROLLER",
            typed_next="RESOLVE_LOOP_BINDING",
            effects_allowed=False,
        )

    stale_binding = loop_run_id != canonical_run_id
    if stale_binding:
        scheduler_action = "QUARANTINE_STALE_LOOP"
    elif loop_role == "MAILBOX_OBSERVER":
        scheduler_action = (
            "ALLOW_READ_ONLY_MAILBOX_OBSERVATION"
            if mailbox_observer_qualified else "PAUSE_UNQUALIFIED_MAILBOX_OBSERVER"
        )
    elif loop_role in POLLING_LOOP_ROLES:
        scheduler_action = "PAUSE_MAILBOX_POLL_SCHEDULER"
    else:
        scheduler_action = "NO_AUTOMATIC_LOOP_MUTATION"

    def outcome(session: str, owner: str, next_action: str, *, effects: bool = False) -> ExecutorLoopContinuity:
        # A qualified observer must not keep its poll cadence armed when an
        # explicit user pause or RUN_HOLD applies, even for read-only checks.
        effective_scheduler_action = (
            "PAUSE_OBSERVER_DURING_HOLD"
            if loop_role == "MAILBOX_OBSERVER" and (user_paused or hold_type == HOLD_RUN)
            else scheduler_action
        )
        return ExecutorLoopContinuity(
            scheduler_action=effective_scheduler_action,
            executor_session_action=session,
            next_owner=owner,
            typed_next=next_action,
            effects_allowed=effects,
        )

    # User pause and RUN_HOLD are explicit independent holds. No implicit
    # unpause, even if a newer event or currently authorized action exists.
    if user_paused:
        return outcome("AWAIT_EXPLICIT_UNPAUSE", "CONTROLLER", "RESOLVE_USER_PAUSE")
    if hold_type == HOLD_RUN:
        return outcome("STOP_NEW_RUN_ACTIONS", "CONTROLLER", "RESOLVE_RUN_HOLD")

    # Check the run binding BEFORE accepting terminal evidence: a terminal
    # event on a prior Loop cannot terminate the distinct active run.
    if stale_binding:
        return outcome("PRESERVE_EXECUTOR_SESSION", "CONTROLLER", "RESOLVE_RUN_BINDING")
    if terminal_verified:
        return outcome("TERMINAL", "CONTROLLER", "ACCEPT_VERIFIED_TERMINAL")
    if loop_role == "MAILBOX_OBSERVER":
        if not mailbox_observer_qualified:
            return outcome("AWAIT_QUALIFIED_MAILBOX_OBSERVER", "AGENT", "QUALIFY_MAILBOX_OBSERVER")
        # EFFECT_HOLD and missing EXECUTE authority block mutations but do not
        # prohibit this separately scoped, read-only discovery path.
        if newer_event_observed:
            return outcome("PRESERVE_EXECUTOR_SESSION", "AGENT", "EXACT_READ_NEW_CONTROLLER_EVENT")
        return outcome("AWAIT_NEW_MAILBOX_EVENT", "AGENT", "OBSERVE_MAILBOX_CURSOR")
    if hold_type == HOLD_EFFECT:
        return outcome("PRESERVE_EXECUTOR_SESSION", "CONTROLLER", "RESOLVE_EFFECT_AUTHORITY")
    if not execute_contract_current:
        return outcome("AWAIT_VALID_EXECUTE", "CONTROLLER", "RESOLVE_EXECUTION_AUTHORITY")
    if awaiting_controller_event:
        if not event_adapter_qualified:
            return outcome("AWAIT_QUALIFIED_EVENT_ADAPTER", "CONTROLLER", "QUALIFY_EVENT_ADAPTER")
        return outcome("AWAIT_EVENT_DRIVEN_SUCCESSOR", "CONTROLLER", "AWAIT_VALID_CONTROLLER_EVENT")
    if loop_role in POLLING_LOOP_ROLES:
        # Authorization permits work via the native goal/Executor path only;
        # it never converts a C/E polling Loop into an execution mechanism.
        return outcome("CONTINUE_EXECUTE_WITHOUT_MAILBOX_POLL", "EXECUTOR", "EXECUTE_NEXT_READY_WORK", effects=True)
    if loop_role == "UNRELATED":
        return outcome("PRESERVE_EXECUTOR_SESSION", "CONTROLLER", "RESOLVE_LOOP_BINDING")
    return outcome("CONTINUE_EXECUTE", "EXECUTOR", "EXECUTE_NEXT_READY_WORK", effects=True)


__all__ = [
    "AUTHORITY_REQUEST_ROUTES",
    "AuthorityRecoveryDecision",
    "decide_stale_authority_recovery",
    "BLOCKER_AUTHORITY_BOUNDARY",
    "BLOCKER_EXTERNAL_DEPENDENCY",
    "BLOCKER_MATERIAL_PLAN_INVALIDATION",
    "BLOCKER_SCOPE_EXPANSION",
    "EXECUTOR_BLOCKER_CLASSES",
    "PeerCollaborationDecision",
    "decide_peer_collaboration",
    "HOST_LOOP_ROLES",
    "POLLING_LOOP_ROLES",
    "ExecutorLoopContinuity",
    "decide_executor_loop_continuity",
    "ExecutorProgressOutcome",
    "HOLD_EFFECT",
    "HOLD_RUN",
    "HOLD_TYPES",
    "HoldSemantics",
    "OrchestrationPolicyError",
    "validate_executor_progress",
    "validate_hold_semantics",
]
