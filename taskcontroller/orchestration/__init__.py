from __future__ import annotations

from typing import Any, Callable

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.facade import AuditFacade
from taskcontroller.audit.guardrails import (
    GuardrailResult,
    check_terminal,
    check_duplicate_root,
    check_authority,
    check_sha_format,
)


class GuardrailChain:
    """Sequential pre-checks for a single external action.

    Each check is a pure function; the chain is fail-closed: the first blocked
    guardrail stops the action and emits a GUARDRAIL_BLOCKED audit entry.
    """

    def __init__(self, audit: AuditFacade, run_id: str, now: Callable[[], str]) -> None:
        self._audit = audit
        self._run_id = run_id
        self._now = now

    def run(
        self,
        *,
        run_status: str = "",
        binding_key: str = "",
        existing_root: str | None = None,
        proposed_root: str = "",
        authority_ref: str = "",
        expected_authority: str = "",
        head_sha: str = "",
        action_kind: str = "",
    ) -> GuardrailResult:
        checks: list[GuardrailResult] = []
        if run_status:
            checks.append(check_terminal(run_status))
        if binding_key and existing_root is not None:
            checks.append(check_duplicate_root(existing_root, proposed_root))
        if authority_ref:
            checks.append(check_authority(authority_ref, expected_authority))
        if head_sha:
            checks.append(check_sha_format(head_sha, field_name=f"{action_kind.lower()}_sha"))

        for cr in checks:
            if cr.blocked:
                ts = self._now()
                self._audit.emit(AuditEvent(
                    event_id=f"guardrail-{ts.replace(':', '').replace('-', '')}",
                    timestamp=ts,
                    run_id=self._run_id,
                    source="guardrail.chain",
                    decision_kind="GUARDRAIL_BLOCKED",
                    authority_ref=authority_ref,
                    payload_summary=f"blocked: {cr.reason}",
                    before={},
                    after={},
                    evidence_refs=(f"action_kind:{action_kind}",),
                    annotations={"guardrail_result": cr.to_dict()},
                ))
                return cr

        return GuardrailResult(blocked=False)


def guardrail_pre_check(guard: GuardrailChain) -> GuardrailChain:
    """Identity wrapper — chain.run() is the real check."""
    return guard


# ---------------------------------------------------------------------------
# External action pattern (reference, not executable)
# ---------------------------------------------------------------------------


def external_action_pattern(
    *,
    audit: AuditFacade,
    run_id: str,
    run_status: str,
    action_kind: str,
    authority_ref: str,
    expected_authority: str,
    head_sha: str,
    existing_root: str | None,
    proposed_root: str,
    now: Callable[[], str],
    external_call: Callable[[], dict[str, Any]],
    readback: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Reference pattern: pre-check → action → readback → compare.

    ``external_call`` and ``readback`` are closures supplied by the runtime
    agent. This function is pure and may be reused across Jira/GitHub/Slack.
    """
    chain = GuardrailChain(audit, run_id, now)

    pre = chain.run(
        run_status=run_status,
        binding_key=action_kind,
        existing_root=existing_root,
        proposed_root=proposed_root,
        authority_ref=authority_ref,
        expected_authority=expected_authority,
        head_sha=head_sha,
        action_kind=action_kind,
    )
    if pre.blocked:
        return {"accepted": False, "reason": pre.reason}

    before = {"status": run_status, "head_sha": head_sha}
    result = external_call()
    after = {**result}
    ts = now()

    audit.emit(AuditEvent(
        event_id=f"action-{action_kind}-{ts.replace(':', '').replace('-', '')}",
        timestamp=ts,
        run_id=run_id,
        source=f"external.{action_kind.lower()}",
        decision_kind=action_kind,
        authority_ref=authority_ref,
        before=before,
        after=after,
        payload_summary=f"{action_kind} executed",
        evidence_refs=(f"action_kind:{action_kind}",),
    ))

    readback_result = readback(after)
    if readback_result.get("exact_match") is not True:
        audit.emit(AuditEvent(
            event_id=f"readback-{action_kind}-{ts.replace(':', '').replace('-', '')}",
            timestamp=ts,
            run_id=run_id,
            source="guardrail.readback_mismatch",
            decision_kind=f"{action_kind}_READBACK_MISMATCH",
            authority_ref=authority_ref,
            before=after,
            after=readback_result,
            payload_summary="readback mismatch — no success claimed",
            annotations={"anomaly": True, "readback": readback_result},
        ))
        return {"accepted": False, "reason": "readback_mismatch"}

    return {"accepted": True, "result": result}
