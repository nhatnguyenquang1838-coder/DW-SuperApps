"""TC-MBX-701: canonical terminal parent result construction and readback.

This module is a provider-neutral composition boundary.  It turns one already
validated mailbox/v2 execution request plus one normalized parent result into a
single ``terminal_result`` envelope.  The envelope retains the current attempt
and fence, normalized findings, child evidence references, and the exact
standards/source identities used for the execution.  Persistence is delegated to
the mailbox repository; no provider, Slack, GitHub, or runtime worker is
invoked here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import (
    MailboxEvent,
    MailboxRepository,
    MailboxSnapshot,
    WriteReceipt,
)
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    canonical_digest,
)


TERMINAL_RESULT_PROTOCOL = "dw.taskcontroller.terminal-parent-result/v1"
_TERMINAL_MESSAGE_TYPE = "terminal_result"
_EXECUTOR_TO_CONTROLLER = "executor_to_controller"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_FORBIDDEN_CONTEXT_KEYS = frozenset(
    {
        "chat",
        "chat_history",
        "conversation",
        "conversation_history",
        "messages",
        "prompt",
        "raw_chat",
        "raw_output",
        "raw_transcript",
        "transcript",
    }
)
_RESULT_STATUSES = frozenset(
    {"SUCCEEDED", "FAILED", "NEEDS_CLARIFICATION", "STALE", "REJECTED"}
)


class TerminalResultError(TaskControllerValidationError):
    """Stable fail-closed error for terminal-result construction/readback."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise TerminalResultError(code, message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("TERMINAL_RESULT_INVALID", f"{field} must be non-empty")
    normalized = value.strip()
    if "\x00" in normalized:
        _fail("TERMINAL_RESULT_INVALID", f"{field} must not contain NUL")
    return normalized


def _identifier(value: Any, field: str) -> str:
    normalized = _text(value, field)
    if not _ID_RE.fullmatch(normalized):
        _fail("TERMINAL_RESULT_INVALID", f"{field} must be a stable identifier")
    return normalized


def _digest(value: Any, field: str) -> str:
    normalized = _text(value, field)
    if _DIGEST_RE.fullmatch(normalized) is None:
        _fail("TERMINAL_RESULT_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return normalized


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("TERMINAL_RESULT_NOT_SERIALIZABLE", f"canonical result is not JSON: {type(exc).__name__}")


def _canonical_result_digest(payload: Mapping[str, Any]) -> str:
    candidate = copy.deepcopy(dict(payload))
    candidate.pop("result_digest", None)
    return "sha256:" + hashlib.sha256(_canonical_bytes(candidate)).hexdigest()


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        candidate = copy.deepcopy(dict(value))
    elif hasattr(value, "to_dict"):
        converted = value.to_dict()
        if not isinstance(converted, Mapping):
            _fail("TERMINAL_RESULT_INVALID", f"{field}.to_dict() must return an object")
        candidate = copy.deepcopy(dict(converted))
    else:
        _fail("TERMINAL_RESULT_INVALID", f"{field} must be an object or to_dict() value")
    if any(not isinstance(key, str) for key in candidate):
        _fail("TERMINAL_RESULT_INVALID", f"{field} keys must be strings")
    return candidate


def _reject_raw_context(value: Any, *, path: str = "normalized_parent_result") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key.casefold() in _FORBIDDEN_CONTEXT_KEYS:
                _fail("TERMINAL_RAW_CONTEXT_FORBIDDEN", f"{path}.{key} is not canonical evidence")
            _reject_raw_context(nested, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _reject_raw_context(nested, path=f"{path}[{index}]")


def _text_tuple(value: Any, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if value is None:
        values: tuple[Any, ...] = ()
    elif isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("TERMINAL_RESULT_INVALID", f"{field} must be an array")
    else:
        values = tuple(value)
    if not allow_empty and not values:
        _fail("TERMINAL_RESULT_INVALID", f"{field} must not be empty")
    return tuple(sorted({_text(item, f"{field} item") for item in values}))


def _normalize_findings(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("TERMINAL_RESULT_INVALID", "normalized_parent_result.findings must be an array")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        finding = _mapping(item, f"findings[{index}]")
        _identifier(finding.get("finding_id"), f"findings[{index}].finding_id")
        refs = _text_tuple(finding.get("evidence_refs"), f"findings[{index}].evidence_refs", allow_empty=False)
        finding["evidence_refs"] = list(refs)
        normalized.append(finding)
    return sorted(normalized, key=lambda item: (item["finding_id"], _canonical_bytes(item)))


def _normalize_child_provenance(value: Any) -> list[dict[str, Any]]:
    if value is None or not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("TERMINAL_CHILD_PROVENANCE_REQUIRED", "child provenance must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        child = _mapping(item, f"child_provenance[{index}]")
        child_id = _identifier(child.get("child_id"), f"child_provenance[{index}].child_id")
        if child_id in seen:
            _fail("TERMINAL_CHILD_PROVENANCE_INVALID", f"duplicate child_id {child_id!r}")
        seen.add(child_id)
        child["child_id"] = child_id
        child["result_digest"] = _digest(
            child.get("result_digest", child.get("normalization_digest")),
            f"child_provenance[{index}].result_digest",
        )
        if "normalization_digest" in child:
            child["normalization_digest"] = _digest(
                child["normalization_digest"],
                f"child_provenance[{index}].normalization_digest",
            )
        status = child.get("status")
        if status is not None:
            child["status"] = _text(status, f"child_provenance[{index}].status")
        normalized.append(child)
    if not normalized:
        _fail("TERMINAL_CHILD_PROVENANCE_REQUIRED", "child provenance must not be empty")
    return sorted(normalized, key=lambda item: item["child_id"])


def _normalize_parent_result(value: Any) -> dict[str, Any]:
    candidate = _mapping(value, "normalized_parent_result")
    _reject_raw_context(candidate)
    findings = _normalize_findings(candidate.get("findings"))
    child_value = candidate.get("child_refs", candidate.get("child_provenance"))
    child_provenance = _normalize_child_provenance(child_value)
    candidate["findings"] = findings
    candidate["child_refs"] = child_provenance
    candidate["child_provenance"] = copy.deepcopy(child_provenance)
    candidate["child_result_digests"] = [item["result_digest"] for item in child_provenance]
    risks = _text_tuple(candidate.get("residual_risks"), "residual_risks")
    questions = _text_tuple(candidate.get("unresolved_questions"), "unresolved_questions")
    candidate["residual_risks"] = list(risks)
    candidate["unresolved_questions"] = list(questions)
    decision = _mapping(candidate.get("controller_decision"), "controller_decision")
    evidence_refs = _text_tuple(decision.get("evidence_refs"), "controller_decision.evidence_refs", allow_empty=False)
    decision["evidence_refs"] = list(evidence_refs)
    candidate["controller_decision"] = decision

    supplied_digest = candidate.get("result_digest")
    digest_basis = copy.deepcopy(candidate)
    # ``child_provenance`` is the terminal-envelope projection alias.  The
    # existing ParentSynthesisResult digest is defined over ``child_refs`` and
    # ``child_result_digests`` only, so the alias must not alter identity.
    digest_basis.pop("child_provenance", None)
    computed_digest = _canonical_result_digest(digest_basis)
    if supplied_digest is not None and _digest(supplied_digest, "result_digest") != computed_digest:
        _fail("TERMINAL_RESULT_DIGEST_MISMATCH", "normalized parent result digest is not canonical")
    candidate["result_digest"] = computed_digest
    return candidate


def _operational_status(normalized: Mapping[str, Any]) -> str:
    candidate = normalized.get("status", normalized.get("final_verdict", normalized.get("verdict")))
    candidate = _text(candidate, "normalized_parent_result.status").upper()
    if candidate in _RESULT_STATUSES:
        return candidate
    return {
        "PASS": "SUCCEEDED",
        "NEEDS_FIX": "FAILED",
        "FAIL": "FAILED",
        "NEEDS_CLARIFICATION": "NEEDS_CLARIFICATION",
    }.get(candidate, "NEEDS_CLARIFICATION")


def _source_refs(source_manifest: Mapping[str, Any]) -> list[str]:
    sources = source_manifest.get("sources")
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes, bytearray)):
        _fail("TERMINAL_SOURCE_BINDING_INVALID", "source manifest sources must be an array")
    refs: list[str] = []
    for source in sources:
        item = _mapping(source, "source_manifest.sources[]")
        refs.append(
            f"{_text(item.get('repository'), 'source.repository')}@"
            f"{_text(item.get('commit_sha'), 'source.commit_sha')}:"
            f"{_text(item.get('path'), 'source.path')}"
        )
    if not refs:
        _fail("TERMINAL_SOURCE_BINDING_INVALID", "source manifest must contain sources")
    return sorted(set(refs))


def _mailbox_finding(value: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Project a normalized finding into the strict mailbox/v2 finding shape.

    Mixer provenance remains lossless in ``payload.normalized_parent_result``;
    the normative ``result.findings`` array accepts only the schema's finding
    fields because it is declared ``additionalProperties: false``.
    """

    required = (
        "finding_id",
        "severity",
        "category",
        "lens",
        "claim",
        "evidence_refs",
        "recommendation",
        "reviewer",
        "disposition",
    )
    optional = ("confidence", "conflict_group")
    missing = [field for field in required if field not in value]
    if missing:
        _fail(
            "TERMINAL_RESULT_INVALID",
            f"findings[{index}] is missing: {', '.join(missing)}",
        )
    projected = {field: copy.deepcopy(value[field]) for field in required}
    projected.update(
        {field: copy.deepcopy(value[field]) for field in optional if field in value}
    )
    return projected


def _validate_expected_identity(
    actual: Mapping[str, Any], expected: Mapping[str, Any] | None,
) -> None:
    if expected is None:
        return
    if not isinstance(expected, Mapping):
        _fail("TERMINAL_IDENTITY_MISMATCH", "expected_identity must be an object")
    for field, value in expected.items():
        if field not in actual or actual[field] != value:
            _fail("TERMINAL_IDENTITY_MISMATCH", f"current identity mismatch for {field}")


@dataclass(frozen=True, slots=True)
class TerminalParentResult:
    """One immutable terminal parent result and its normalized Controller view."""

    envelope: V2MailboxEnvelope
    normalized_result: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, V2MailboxEnvelope):
            _fail("TERMINAL_RESULT_INVALID", "envelope must be a V2MailboxEnvelope")
        normalized = _normalize_parent_result(self.normalized_result)
        payload = self.envelope.to_dict()
        if payload.get("message_type") != _TERMINAL_MESSAGE_TYPE:
            _fail("TERMINAL_RESULT_INVALID", "envelope is not a terminal_result")
        if payload.get("direction") != _EXECUTOR_TO_CONTROLLER:
            _fail("TERMINAL_RESULT_INVALID", "terminal result must flow executor_to_controller")
        result = payload.get("result")
        if not isinstance(result, Mapping):
            _fail("TERMINAL_RESULT_INVALID", "terminal envelope result is required")
        if result.get("result_digest") != normalized["result_digest"]:
            _fail("TERMINAL_RESULT_DIGEST_MISMATCH", "envelope and normalized result digest differ")
        if result.get("boundary_digest") != payload["execution_identity"]["boundary_digest"]:
            _fail("TERMINAL_BOUNDARY_MISMATCH", "terminal result boundary is not current")
        terminal_payload = payload.get("payload")
        if not isinstance(terminal_payload, Mapping):
            _fail("TERMINAL_RESULT_INVALID", "terminal payload is required")
        if terminal_payload.get("normalized_parent_result") != normalized:
            _fail("TERMINAL_RESULT_DIGEST_MISMATCH", "terminal payload is not canonical")
        if terminal_payload.get("child_provenance") != normalized["child_provenance"]:
            _fail("TERMINAL_CHILD_PROVENANCE_INVALID", "terminal child provenance is not canonical")
        object.__setattr__(self, "normalized_result", normalized)

    @classmethod
    def from_envelope(cls, envelope: V2MailboxEnvelope) -> "TerminalParentResult":
        if not isinstance(envelope, V2MailboxEnvelope):
            _fail("TERMINAL_RESULT_INVALID", "terminal read requires a V2MailboxEnvelope")
        payload = envelope.to_dict()
        terminal_payload = payload.get("payload")
        if not isinstance(terminal_payload, Mapping):
            _fail("TERMINAL_RESULT_INVALID", "terminal payload is missing")
        return cls(envelope=envelope, normalized_result=terminal_payload.get("normalized_parent_result"))

    @property
    def result_digest(self) -> str:
        return self.envelope.to_dict()["result"]["result_digest"]

    @property
    def attempt_id(self) -> str:
        return self.envelope.execution_identity["attempt_id"]

    @property
    def lease_generation(self) -> int:
        return self.envelope.execution_identity["lease_generation"]

    @property
    def fencing_token(self) -> str:
        return self.envelope.execution_identity["fencing_token"]

    def canonical_bytes(self) -> bytes:
        return self.envelope.canonical_bytes()

    def to_dict(self) -> dict[str, Any]:
        return self.envelope.to_dict()


def build_terminal_parent_result(
    request: V2MailboxEnvelope,
    normalized_parent_result: Any,
    *,
    message_id: str,
    seq: int,
    producer_namespace: str,
    producer_actor_id: str,
    recipient: Mapping[str, Any],
    idempotency_key: str,
    expected_identity: Mapping[str, Any] | None = None,
) -> TerminalParentResult:
    """Build one current-attempt terminal result from a validated request."""

    if not isinstance(request, V2MailboxEnvelope):
        _fail("TERMINAL_RESULT_INVALID", "request must be a V2MailboxEnvelope")
    normalized = _normalize_parent_result(normalized_parent_result)
    request_payload = request.to_dict()
    identity = request.execution_identity
    _validate_expected_identity(identity, expected_identity)
    recipient_payload = _mapping(recipient, "recipient")
    recipient_payload = {
        "capability": _text(recipient_payload.get("capability"), "recipient.capability"),
        "agent_instance": _identifier(recipient_payload.get("agent_instance"), "recipient.agent_instance"),
    }
    source_manifest = request_payload["source_manifest"]
    standards_profile = request_payload["standards_profile"]
    source_refs = _source_refs(source_manifest)
    status = _operational_status(normalized)
    evidence_refs = set()
    for finding in normalized["findings"]:
        evidence_refs.update(finding.get("evidence_refs", ()))
    evidence_refs.update(normalized["controller_decision"].get("evidence_refs", ()))

    result = {
        "status": status,
        "boundary_digest": identity["boundary_digest"],
        "result_digest": normalized["result_digest"],
        "artifact_refs": list(normalized.get("artifact_refs", ())),
        "findings": [
            _mailbox_finding(finding, index)
            for index, finding in enumerate(normalized["findings"])
        ],
    }
    candidate: dict[str, Any] = {
        "protocol": request.protocol,
        "message_id": _identifier(message_id, "message_id"),
        "run_id": request.run_id,
        "node_id": request.node_id,
        "seq": seq,
        "correlation_id": request_payload["correlation_id"],
        "direction": _EXECUTOR_TO_CONTROLLER,
        "message_type": _TERMINAL_MESSAGE_TYPE,
        "producer": {
            "namespace": _identifier(producer_namespace, "producer.namespace"),
            "actor_id": _identifier(producer_actor_id, "producer.actor_id"),
            "role": "executor",
        },
        "recipient": recipient_payload,
        "logical_contract": request.logical_contract,
        "attempt": request.attempt,
        "execution_identity": identity,
        "source_manifest": source_manifest,
        "standards_profile": standards_profile,
        "payload": {
            "normalized_parent_result": normalized,
            "child_provenance": copy.deepcopy(normalized["child_provenance"]),
            "standards_digest": standards_profile["digest"],
            "source_digest": source_manifest["digest"],
            "attempt_id": identity["attempt_id"],
            "lease_generation": identity["lease_generation"],
            "fencing_token": identity["fencing_token"],
        },
        "provenance": {
            "origin": "executor",
            "parent_message_id": request_payload["message_id"],
            "child_id": None,
            "lens": "parent-synthesis",
            "agent_instance": request.attempt["agent_instance"],
            "status": status,
            "source_refs": source_refs,
            "evidence_refs": sorted(evidence_refs),
            "result_digest": normalized["result_digest"],
        },
        "result": result,
        "idempotency_key": _identifier(idempotency_key, "idempotency_key"),
    }
    candidate["digest"] = canonical_digest(candidate)
    try:
        envelope = V2MailboxEnvelope.from_dict(candidate)
    except MailboxV2ValidationError as exc:
        _fail("TERMINAL_RESULT_INVALID", str(exc))
    return TerminalParentResult(envelope=envelope, normalized_result=normalized)


def _event_for_receipt(snapshot: MailboxSnapshot, receipt: WriteReceipt) -> MailboxEvent:
    if not isinstance(snapshot, MailboxSnapshot) or not isinstance(receipt, WriteReceipt):
        _fail("TERMINAL_READBACK_MISMATCH", "readback requires snapshot and write receipt")
    if snapshot.mailbox_ref != receipt.mailbox_ref:
        _fail("TERMINAL_READBACK_MISMATCH", "readback mailbox reference differs")
    event = next((item for item in snapshot.events if item.event_id == receipt.event_id), None)
    if event is None:
        _fail("TERMINAL_READBACK_MISMATCH", "receipt event is absent from readback")
    if (
        event.event_seq != receipt.event_seq
        or event.envelope_digest != receipt.envelope_digest
        or event.event_digest != receipt.event_digest
    ):
        _fail("TERMINAL_READBACK_MISMATCH", "receipt does not exactly bind readback event")
    return event


def verify_terminal_result_readback(
    expected: TerminalParentResult,
    snapshot: MailboxSnapshot,
    receipt: WriteReceipt,
) -> TerminalParentResult:
    """Validate exact persisted bytes and return the Controller-consumed view."""

    if not isinstance(expected, TerminalParentResult):
        _fail("TERMINAL_READBACK_MISMATCH", "expected value is not a terminal parent result")
    event = _event_for_receipt(snapshot, receipt)
    consumed = TerminalParentResult.from_envelope(event.envelope)
    if consumed.to_dict() != expected.to_dict():
        _fail("TERMINAL_READBACK_MISMATCH", "Controller readback differs from terminal write")
    return consumed


def _receipt_from_event(event: MailboxEvent) -> WriteReceipt:
    """Reconstruct a receipt for an already persisted terminal event."""

    payload = event.envelope.to_dict()
    return WriteReceipt(
        mailbox_ref=event.mailbox_ref,
        event_id=event.event_id,
        event_seq=event.event_seq,
        message_id=payload["message_id"],
        envelope_digest=event.envelope_digest,
        event_digest=event.event_digest,
        idempotent=True,
    )


def _reconcile_existing_terminal(
    repository: MailboxRepository,
    mailbox_ref: str,
    terminal: TerminalParentResult,
) -> tuple[WriteReceipt, TerminalParentResult] | None:
    """Resolve a duplicate/conflict before generic sequence/idempotency checks."""

    target = terminal.envelope.to_dict()
    target_identity = target["execution_identity"]
    for event in repository.read(mailbox_ref).events:
        candidate = event.envelope.to_dict()
        if candidate.get("message_type") != _TERMINAL_MESSAGE_TYPE:
            continue
        if candidate.get("run_id") != target["run_id"] or candidate.get("node_id") != target["node_id"]:
            continue
        if candidate.get("execution_identity") != target_identity:
            continue

        existing = TerminalParentResult.from_envelope(event.envelope)
        if existing.result_digest == terminal.result_digest:
            receipt = _receipt_from_event(event)
            snapshot = repository.exact_readback(receipt)
            return receipt, verify_terminal_result_readback(existing, snapshot, receipt)
        _fail(
            "TERMINAL_RESULT_CONFLICT",
            "a different terminal result already exists for the current execution identity",
        )
    return None


def write_terminal_parent_result(
    repository: MailboxRepository,
    mailbox_ref: str,
    *,
    expected_seq: int,
    terminal: TerminalParentResult,
    expected_identity: Mapping[str, Any] | None = None,
) -> tuple[WriteReceipt, TerminalParentResult]:
    """Persist one terminal result, exact-read it back, and return both views."""

    if not isinstance(terminal, TerminalParentResult):
        _fail("TERMINAL_RESULT_INVALID", "terminal must be a TerminalParentResult")
    try:
        if expected_identity is not None:
            terminal.envelope.validate_current_identity(expected_identity)
        existing = _reconcile_existing_terminal(repository, mailbox_ref, terminal)
        if existing is not None:
            return existing
        receipt = repository.write(
            mailbox_ref,
            expected_seq,
            terminal.envelope,
            expected_identity=expected_identity,
        )
        snapshot = repository.exact_readback(receipt)
    except MailboxV2ValidationError as exc:
        if getattr(exc, "code", None) == MailboxV2ErrorCode.INVALID_SEQUENCE:
            existing = _reconcile_existing_terminal(repository, mailbox_ref, terminal)
            if existing is not None:
                return existing
        _fail("TERMINAL_WRITE_REJECTED", str(exc))
    consumed = verify_terminal_result_readback(terminal, snapshot, receipt)
    return receipt, consumed


def read_terminal_parent_result(envelope: V2MailboxEnvelope) -> TerminalParentResult:
    """Parse the exact v2 envelope used by Controller consumption."""

    return TerminalParentResult.from_envelope(envelope)


__all__ = [
    "TERMINAL_RESULT_PROTOCOL",
    "TerminalParentResult",
    "TerminalResultError",
    "build_terminal_parent_result",
    "read_terminal_parent_result",
    "verify_terminal_result_readback",
    "write_terminal_parent_result",
]
