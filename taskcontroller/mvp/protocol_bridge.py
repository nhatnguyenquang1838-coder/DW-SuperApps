"""MVP protocol bridge — stateless translation only (NO GWC).

Purpose
-------
``agents/shared/slack-controller-executor-protocol.md`` on current ``main`` is the
sole active protocol authority. It mandates the control vocabulary

    After report = CONTINUE | WAIT_CONTROLLER | TERMINAL

plus a bounded ``INTERCEPT`` raised on exactly five drift conditions. The
TaskController core library speaks a different, richer vocabulary
(``RunStatus`` / ``NodeStatus`` / ``DecisionType``) and is a *dormant* library:
its Full-E2E surface (leases, journal, checkpoint, recovery, event routing,
host packs) is explicitly deferred by the same protocol document.

This module is the ONLY thing that binds the two. It translates a contracted
subtask boundary plus an executor report into one protocol verdict.

Hard rules upheld here
----------------------
1. STATELESS / PURE. Owns no state. Never reads or writes a store, never
   performs CAS, never takes a lease, never appends to a journal, never
   checkpoints. No network, no subprocess, no wall clock, no randomness, no
   Slack client. Same inputs always produce the same verdict.
2. NO SECOND ENGINE. It issues no transition. All legal transitions remain in
   ``taskcontroller.kernel.transitions``. This module cannot move a node or a
   run between states, so it can never reopen or fabricate ``DONE``.
3. NO SECOND SCHEMA AUTHORITY. It defines no JSON schema and reads none. The
   canonical contracts stay under ``taskcontroller/schemas/``.
4. EXACT VOCABULARY. The only verdicts emitted are the four literals
   ``CONTINUE``, ``WAIT_CONTROLLER``, ``TERMINAL``, ``INTERCEPT``. No aliases,
   no supersets, no lowercase variants.
5. DELEGATED-CONTROL VERDICTS ONLY. ``WAIT_CONTROLLER`` / ``TERMINAL`` /
   ``INTERCEPT`` describe the *delegated control segment*, never a
   ``RunStatus`` or ``NodeStatus``. ``TERMINAL`` ends a delegated segment; it
   is NOT runtime ``DONE`` and grants no merge/approve authority.
6. AUTHORITY STAYS EXTERNAL. ``APPROVE`` / ``MERGE`` are never translated into
   a runtime mutation. An authority-required signal maps to ``INTERCEPT``
   (authority drift) so a human boundary is surfaced, never crossed.
7. FAIL CLOSED. Unknown/mismatched input never degrades to ``CONTINUE``.

Deliberately NOT imported (deferred Full-E2E surface):
``SlackTaskControllerPack``, ``LeaseManager``, ``EventRouter``, and the
``journal`` / ``recovery`` / ``checkpoint`` / ``store`` modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from taskcontroller.errors import TaskControllerValidationError

# --------------------------------------------------------------------------
# Exact protocol vocabulary (current-main MVP contract).
# --------------------------------------------------------------------------
CONTINUE = "CONTINUE"
WAIT_CONTROLLER = "WAIT_CONTROLLER"
TERMINAL = "TERMINAL"
INTERCEPT = "INTERCEPT"

#: The four literals, in contract order. Nothing else may ever be emitted.
PROTOCOL_VERDICTS = (CONTINUE, WAIT_CONTROLLER, TERMINAL, INTERCEPT)

#: Values legal in a contracted subtask's ``After report`` field. ``INTERCEPT``
#: is a runtime-raised exception path, never a plannable boundary.
CONTRACTED_AFTER_VALUES = (CONTINUE, WAIT_CONTROLLER, TERMINAL)

#: Executor report statuses defined by the MVP Executor thread-update block.
REPORT_STATUSES = ("RUNNING", "DONE", "BLOCKED", "FAILED")


class InterceptReason:
    """The five — and only five — MVP intercept conditions."""

    SCOPE_DRIFT = "scope_drift"
    AUTHORITY_DRIFT = "authority_drift"
    PLAN_DRIFT = "plan_drift"
    EVIDENCE_CONFLICT = "evidence_conflict"
    MATERIAL_FINDING = "material_finding"

    ALL = (
        SCOPE_DRIFT,
        AUTHORITY_DRIFT,
        PLAN_DRIFT,
        EVIDENCE_CONFLICT,
        MATERIAL_FINDING,
    )


@dataclass(frozen=True)
class ContractedSubtask:
    """The Controller-side contract for one subtask boundary.

    Mirrors the five fields the MVP protocol requires, reduced to what a
    verdict actually depends on. This is NOT a plan engine: it holds no
    ordering, no index, no cursor, and it never advances.
    """

    subtask_id: str
    after_report: str

    def __post_init__(self) -> None:
        if not isinstance(self.subtask_id, str) or not self.subtask_id:
            raise TaskControllerValidationError("subtask_id must be a non-empty string")
        if self.after_report not in CONTRACTED_AFTER_VALUES:
            raise TaskControllerValidationError(
                f"invalid contracted after_report: {self.after_report!r}; "
                f"expected one of {CONTRACTED_AFTER_VALUES}"
            )


@dataclass(frozen=True)
class ExecutorReport:
    """One Executor thread update at a contracted milestone.

    ``authority_required`` carries a projection-layer authority signal (e.g. an
    ``AuthorityResult`` for APPROVE/MERGE). ``evidence_conflict`` carries a
    surfaced CAS/expected-version conflict. Neither is acted upon here.
    """

    subtask_id: str
    status: str
    after: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    drift: tuple[str, ...] = field(default_factory=tuple)
    material_finding: bool = False
    authority_required: bool = False
    evidence_conflict: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.subtask_id, str) or not self.subtask_id:
            raise TaskControllerValidationError("subtask_id must be a non-empty string")
        if self.status not in REPORT_STATUSES:
            raise TaskControllerValidationError(
                f"invalid report status: {self.status!r}; expected one of {REPORT_STATUSES}"
            )
        if self.after not in CONTRACTED_AFTER_VALUES:
            raise TaskControllerValidationError(
                f"invalid report after value: {self.after!r}; "
                f"expected one of {CONTRACTED_AFTER_VALUES}"
            )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ExecutorReport":
        """Build from a plain mapping. Validates; defines no JSON schema."""
        if not isinstance(payload, Mapping):
            raise TaskControllerValidationError("report payload must be a mapping")
        return cls(
            subtask_id=payload.get("subtask_id", ""),
            status=payload.get("status", ""),
            after=payload.get("after", ""),
            evidence=tuple(payload.get("evidence", ()) or ()),
            drift=tuple(payload.get("drift", ()) or ()),
            material_finding=bool(payload.get("material_finding", False)),
            authority_required=bool(payload.get("authority_required", False)),
            evidence_conflict=bool(payload.get("evidence_conflict", False)),
        )


@dataclass(frozen=True)
class ProtocolVerdict:
    """Immutable translation result.

    ``verdict`` is always one of :data:`PROTOCOL_VERDICTS`. ``intercept_reason``
    is set only when ``verdict == INTERCEPT``. ``runtime_mutated`` is a
    structural self-attestation: this module performs no mutation, so it is
    always ``False``.
    """

    verdict: str
    detail: str
    subtask_id: str
    intercept_reason: str | None = None
    runtime_mutated: bool = False

    def __post_init__(self) -> None:
        if self.verdict not in PROTOCOL_VERDICTS:
            raise TaskControllerValidationError(f"invalid verdict: {self.verdict!r}")
        if self.verdict == INTERCEPT:
            if self.intercept_reason not in InterceptReason.ALL:
                raise TaskControllerValidationError(
                    f"INTERCEPT requires one of {InterceptReason.ALL}"
                )
        elif self.intercept_reason is not None:
            raise TaskControllerValidationError(
                "intercept_reason is only valid with an INTERCEPT verdict"
            )
        if self.runtime_mutated:
            raise TaskControllerValidationError(
                "protocol bridge must never report a runtime mutation"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "detail": self.detail,
            "subtask_id": self.subtask_id,
            "intercept_reason": self.intercept_reason,
            "runtime_mutated": self.runtime_mutated,
        }


def classify_report(
    contracted: ContractedSubtask,
    report: ExecutorReport | Mapping[str, Any],
) -> ProtocolVerdict:
    """Translate one contracted boundary + report into a protocol verdict.

    Pure function. Reads its two arguments and returns a verdict. It performs
    no I/O, issues no transition, and mutates neither argument (both are frozen
    dataclasses).

    Precedence — first match wins, so drift can never be masked by a
    later "looks fine" branch:

    1. reported subtask != contracted subtask  -> INTERCEPT (scope drift)
    2. authority required (APPROVE/MERGE)      -> INTERCEPT (authority drift)
    3. reported ``after`` != contracted        -> INTERCEPT (plan drift)
    4. surfaced CAS/version conflict           -> INTERCEPT (evidence conflict)
    5. explicit drift flags / material finding -> INTERCEPT (material finding)
    6. status BLOCKED or FAILED                -> TERMINAL (segment ends)
    7. contracted WAIT_CONTROLLER              -> WAIT_CONTROLLER
    8. contracted TERMINAL                     -> TERMINAL (segment, not DONE)
    9. otherwise                               -> CONTINUE
    """
    if isinstance(report, Mapping):
        report = ExecutorReport.from_payload(report)
    if not isinstance(contracted, ContractedSubtask):
        raise TaskControllerValidationError("contracted must be a ContractedSubtask")

    sid = report.subtask_id

    # 1. scope drift — fail closed on a report for the wrong subtask.
    if report.subtask_id != contracted.subtask_id:
        return ProtocolVerdict(
            verdict=INTERCEPT,
            detail=(
                f"report targets {report.subtask_id!r}, "
                f"contracted boundary is {contracted.subtask_id!r}"
            ),
            subtask_id=sid,
            intercept_reason=InterceptReason.SCOPE_DRIFT,
        )

    # 2. authority drift — surface the human boundary, never cross it.
    if report.authority_required:
        return ProtocolVerdict(
            verdict=INTERCEPT,
            detail="external authority required; runtime not mutated, not approved, not merged",
            subtask_id=sid,
            intercept_reason=InterceptReason.AUTHORITY_DRIFT,
        )

    # 3. plan drift — reported boundary disagrees with the contract.
    if report.after != contracted.after_report:
        return ProtocolVerdict(
            verdict=INTERCEPT,
            detail=(
                f"report boundary {report.after} conflicts with "
                f"contracted {contracted.after_report}"
            ),
            subtask_id=sid,
            intercept_reason=InterceptReason.PLAN_DRIFT,
        )

    # 4. evidence conflict — a surfaced CAS/expected_version mismatch is never masked.
    if report.evidence_conflict:
        return ProtocolVerdict(
            verdict=INTERCEPT,
            detail="evidence conflict: stale expected_version / conflicting evidence surfaced",
            subtask_id=sid,
            intercept_reason=InterceptReason.EVIDENCE_CONFLICT,
        )

    # 5. material finding invalidating the contracted next step.
    if report.material_finding or report.drift:
        detail = "material finding invalidates the contracted next step"
        if report.drift:
            detail += ": " + ", ".join(report.drift)
        return ProtocolVerdict(
            verdict=INTERCEPT,
            detail=detail,
            subtask_id=sid,
            intercept_reason=InterceptReason.MATERIAL_FINDING,
        )

    # 6. blocker/failure ends the delegated segment (not runtime DONE).
    if report.status in ("BLOCKED", "FAILED"):
        return ProtocolVerdict(
            verdict=TERMINAL,
            detail=f"executor reported {report.status.lower()}; delegated segment ends",
            subtask_id=sid,
        )

    # 7. contracted controller review.
    if contracted.after_report == WAIT_CONTROLLER:
        return ProtocolVerdict(
            verdict=WAIT_CONTROLLER,
            detail="contracted controller review required before release",
            subtask_id=sid,
        )

    # 8. contracted end of the delegated segment. NOT runtime DONE, NOT merge authority.
    if contracted.after_report == TERMINAL:
        return ProtocolVerdict(
            verdict=TERMINAL,
            detail=(
                "contracted delegated-segment termination; "
                "grants no DONE, approve or merge authority"
            ),
            subtask_id=sid,
        )

    # 9. normal contracted milestone.
    return ProtocolVerdict(
        verdict=CONTINUE,
        detail="contracted milestone satisfied; controller may release next subtask",
        subtask_id=sid,
    )
