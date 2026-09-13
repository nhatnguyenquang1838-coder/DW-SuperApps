"""TC-MBX-704: Controller-side semantic acceptance of terminal results.

The executor's operational SUCCESS is evidence, not node completion.  This
adapter binds one validated terminal parent result to one TaskContract and
returns an immutable acceptance projection; it never mutates node/run state,
invokes a provider, or grants merge/deploy authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from taskcontroller.domain.models import TaskContract
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.execution.terminal_result import TerminalParentResult


_SEMANTIC_ACCEPTANCE_PROTOCOL = "dw.taskcontroller.semantic-acceptance/v1"


class SemanticAcceptanceError(TaskControllerValidationError):
    """Stable fail-closed error for invalid contract/result binding."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise SemanticAcceptanceError(code, message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("SEMANTIC_RESULT_INVALID", f"{field} must be a non-empty string")
    normalized = value.strip()
    if "\x00" in normalized:
        _fail("SEMANTIC_RESULT_INVALID", f"{field} must not contain NUL")
    return normalized


def _text_values(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        _fail("SEMANTIC_RESULT_INVALID", f"{field} must be an array")
    return tuple(sorted({_text(item, f"{field}[]") for item in value}))


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("SEMANTIC_RESULT_INVALID", f"{field} must be an object")
    return value


def _evidence_spec_tokens(spec: Any, index: int) -> tuple[str, tuple[str, ...]]:
    if isinstance(spec, Mapping):
        evidence_id = spec.get("evidence_id")
        artifact_ref = spec.get("artifact_ref")
    else:
        evidence_id = getattr(spec, "evidence_id", None)
        artifact_ref = getattr(spec, "artifact_ref", None)
    evidence_id = _text(evidence_id, f"required_evidence[{index}].evidence_id")
    tokens = [evidence_id]
    if artifact_ref is not None:
        tokens.append(_text(artifact_ref, f"required_evidence[{index}].artifact_ref"))
    return evidence_id, tuple(sorted(set(tokens)))


def _contract_identity(
    contract: TaskContract,
    terminal: TerminalParentResult,
    expected_contract_digest: str | None,
) -> None:
    payload = terminal.envelope.to_dict()
    logical_contract = _mapping(payload.get("logical_contract"), "terminal.logical_contract")
    identity = _mapping(payload.get("execution_identity"), "terminal.execution_identity")
    if payload.get("run_id") != contract.run_id or identity.get("run_id") != contract.run_id:
        _fail("SEMANTIC_CONTRACT_MISMATCH", "terminal run_id does not bind the TaskContract")
    if payload.get("node_id") != contract.node_id or identity.get("node_id") != contract.node_id:
        _fail("SEMANTIC_CONTRACT_MISMATCH", "terminal node_id does not bind the TaskContract")
    if logical_contract.get("contract_id") != contract.contract_id:
        _fail("SEMANTIC_CONTRACT_MISMATCH", "terminal contract_id does not bind the TaskContract")
    if contract.plan_version and logical_contract.get("plan_version") != contract.plan_version:
        _fail("SEMANTIC_CONTRACT_MISMATCH", "terminal plan_version does not bind the TaskContract")
    if expected_contract_digest is not None:
        if identity.get("contract_digest") != _text(expected_contract_digest, "expected_contract_digest"):
            _fail("SEMANTIC_CONTRACT_MISMATCH", "terminal contract_digest does not match the Controller binding")


def _result_evidence_refs(normalized: Mapping[str, Any], terminal: TerminalParentResult) -> tuple[str, ...]:
    refs: set[str] = set()
    refs.update(_text_values(normalized.get("evidence_refs"), "normalized_parent_result.evidence_refs"))
    refs.update(_text_values(normalized.get("artifact_refs"), "normalized_parent_result.artifact_refs"))
    decision = normalized.get("controller_decision")
    if decision is not None:
        decision_mapping = _mapping(decision, "normalized_parent_result.controller_decision")
        refs.update(_text_values(decision_mapping.get("evidence_refs"), "controller_decision.evidence_refs"))
    findings = normalized.get("findings", ())
    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes, bytearray)):
        _fail("SEMANTIC_RESULT_INVALID", "normalized_parent_result.findings must be an array")
    for index, finding in enumerate(findings):
        finding_mapping = _mapping(finding, f"findings[{index}]")
        refs.update(_text_values(finding_mapping.get("evidence_refs"), f"findings[{index}].evidence_refs"))
    result = _mapping(terminal.envelope.to_dict().get("result"), "terminal.result")
    refs.update(_text_values(result.get("artifact_refs"), "terminal.result.artifact_refs"))
    return tuple(sorted(refs))


def _result_criteria(normalized: Mapping[str, Any]) -> tuple[str, ...]:
    criteria = list(_text_values(normalized.get("accepted_criteria"), "accepted_criteria"))
    criteria.extend(_text_values(normalized.get("criteria"), "criteria"))
    decision = normalized.get("controller_decision")
    if decision is not None:
        decision_mapping = _mapping(decision, "normalized_parent_result.controller_decision")
        criteria.extend(_text_values(decision_mapping.get("accepted_criteria"), "controller_decision.accepted_criteria"))
        criteria.extend(_text_values(decision_mapping.get("criteria"), "controller_decision.criteria"))
    return tuple(sorted(set(criteria)))


@dataclass(frozen=True, slots=True)
class SemanticAcceptance:
    """Controller-owned acceptance projection; it is not a node-state mutation."""

    accepted: bool
    contract_id: str
    run_id: str
    node_id: str
    terminal_status: str
    result_digest: str
    criteria_covered: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    missing_criteria: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    protocol: str = _SEMANTIC_ACCEPTANCE_PROTOCOL

    @property
    def can_close(self) -> bool:
        """Explicit alias for the Controller's DONE gate."""

        return self.accepted

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "accepted": self.accepted,
            "can_close": self.can_close,
            "contract_id": self.contract_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "terminal_status": self.terminal_status,
            "result_digest": self.result_digest,
            "criteria_covered": list(self.criteria_covered),
            "evidence_refs": list(self.evidence_refs),
            "missing_criteria": list(self.missing_criteria),
            "missing_evidence": list(self.missing_evidence),
            "reason_codes": list(self.reason_codes),
        }


def evaluate_terminal_acceptance(
    contract: TaskContract,
    terminal: TerminalParentResult,
    *,
    expected_contract_digest: str | None = None,
) -> SemanticAcceptance:
    """Evaluate contract AC/evidence before the Controller can close a node."""

    if not isinstance(contract, TaskContract):
        _fail("SEMANTIC_CONTRACT_INVALID", "contract must be a TaskContract")
    if not isinstance(terminal, TerminalParentResult):
        _fail("SEMANTIC_RESULT_INVALID", "terminal must be a TerminalParentResult")
    _contract_identity(contract, terminal, expected_contract_digest)

    normalized = terminal.normalized_result
    terminal_payload = terminal.envelope.to_dict()
    result = _mapping(terminal_payload.get("result"), "terminal.result")
    terminal_status = _text(result.get("status"), "terminal.result.status").upper()
    criteria_covered = _result_criteria(normalized)
    evidence_refs = _result_evidence_refs(normalized, terminal)

    required_criteria = tuple(sorted({_text(item, "contract.acceptance_criteria[]") for item in contract.acceptance_criteria}))
    missing_criteria = tuple(item for item in required_criteria if item not in criteria_covered)
    missing_evidence: list[str] = []
    for index, spec in enumerate(contract.required_evidence):
        evidence_id, tokens = _evidence_spec_tokens(spec, index)
        if not any(token in evidence_refs for token in tokens):
            missing_evidence.append(evidence_id)

    reasons: list[str] = []
    if terminal_status != "SUCCEEDED":
        reasons.append("TERMINAL_NOT_SUCCEEDED")
    if missing_criteria:
        reasons.append("MISSING_ACCEPTANCE_CRITERIA")
    if missing_evidence:
        reasons.append("MISSING_REQUIRED_EVIDENCE")
    accepted = not reasons
    if accepted:
        reasons.append("ACCEPTED")

    return SemanticAcceptance(
        accepted=accepted,
        contract_id=contract.contract_id,
        run_id=contract.run_id,
        node_id=contract.node_id,
        terminal_status=terminal_status,
        result_digest=terminal.result_digest,
        criteria_covered=criteria_covered,
        evidence_refs=evidence_refs,
        missing_criteria=missing_criteria,
        missing_evidence=tuple(sorted(missing_evidence)),
        reason_codes=tuple(reasons),
    )


semantic_acceptance = evaluate_terminal_acceptance


__all__ = [
    "SemanticAcceptance",
    "SemanticAcceptanceError",
    "evaluate_terminal_acceptance",
    "semantic_acceptance",
]
