"""Fail-closed Controller admission for high-integrity TaskController runs.

The guard prevents a host/controller from bypassing the typed mailbox/control-plane
contracts when the selected task needs strong authority, gate, digest, or governed
execution semantics. It grants no execution authority and performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V1_PROTOCOL, V2_PROTOCOL


ADMISSION_PROTOCOL: Final = "dw.taskcontroller.controller-admission/v1"

MAILBOX_READ_EXACT: Final = "exact_mailbox_ref"
INTEGRITY_CANONICAL_ENVELOPE: Final = "canonical_envelope_digest"
SCHEMA_DESCRIPTOR_BOUND: Final = "descriptor_bound"
GATE_STATE_CURRENT_BOUNDARY: Final = "current_verified_boundary"
APPROVAL_TYPED_ARTIFACT: Final = "typed_artifact_command_digest"

DIGEST_SOURCES: Final = frozenset({"observed", "canonical_recompute"})


class ControllerAdmissionError(TaskControllerValidationError):
    """Stable fail-closed error raised before high-integrity dispatch/review."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ControllerAdmissionInput:
    """Host-bound Controller interaction choices.

    requires_v2_semantics is selected by the Controller/host when the task
    requires authority/gate/digest semantics that cannot be represented safely
    by the mutable v1 compatibility mailbox.
    """

    requires_v2_semantics: bool
    protocol: str
    mailbox_ref: str
    mailbox_read_scope: str = MAILBOX_READ_EXACT
    integrity_binding: str = INTEGRITY_CANONICAL_ENVELOPE
    digest_source: str = "observed"
    schema_resolution: str = SCHEMA_DESCRIPTOR_BOUND
    gate_state_basis: str = GATE_STATE_CURRENT_BOUNDARY
    approval_binding: str = APPROVAL_TYPED_ARTIFACT
    raw_comment_body_sha_authoritative: bool = False
    issue_wide_machine_scan: bool = False
    predicted_digest_allowed: bool = False


@dataclass(frozen=True, slots=True)
class ControllerAdmissionReceipt:
    protocol: str
    mailbox_ref: str
    mode: str
    reason_codes: tuple[str, ...]
    authority_granted: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": ADMISSION_PROTOCOL,
            "interaction_protocol": self.protocol,
            "mailbox_ref": self.mailbox_ref,
            "mode": self.mode,
            "reason_codes": list(self.reason_codes),
            "authority_granted": self.authority_granted,
        }


def _fail(code: str, message: str) -> None:
    raise ControllerAdmissionError(code, message)


def validate_controller_admission(
    value: ControllerAdmissionInput,
) -> ControllerAdmissionReceipt:
    """Validate one Controller interaction boundary without granting authority."""

    if not isinstance(value, ControllerAdmissionInput):
        _fail("CONTROLLER_ADMISSION_INPUT_INVALID", "input must be ControllerAdmissionInput")

    if value.protocol not in {V1_PROTOCOL, V2_PROTOCOL}:
        _fail("CONTROLLER_ADMISSION_PROTOCOL_UNSUPPORTED", "unsupported interaction protocol")
    if not isinstance(value.mailbox_ref, str) or not value.mailbox_ref.strip():
        _fail("CONTROLLER_ADMISSION_MAILBOX_REQUIRED", "exact mailbox reference is required")

    if not value.requires_v2_semantics:
        return ControllerAdmissionReceipt(
            protocol=value.protocol,
            mailbox_ref=value.mailbox_ref,
            mode="COMPATIBILITY",
            reason_codes=("CONTROLLER_ADMISSION_COMPATIBILITY",),
        )

    if value.protocol != V2_PROTOCOL:
        _fail(
            "CONTROLLER_ADMISSION_V2_REQUIRED",
            "high-integrity run requires dw.taskcontroller.mailbox/v2",
        )
    if value.mailbox_read_scope != MAILBOX_READ_EXACT:
        _fail(
            "CONTROLLER_ADMISSION_EXACT_MAILBOX_REQUIRED",
            "machine state must be read from the exact bound mailbox reference",
        )
    if value.issue_wide_machine_scan:
        _fail(
            "CONTROLLER_ADMISSION_ISSUE_SCAN_FORBIDDEN",
            "whole-issue comment history is not a machine-state source",
        )
    if value.integrity_binding != INTEGRITY_CANONICAL_ENVELOPE:
        _fail(
            "CONTROLLER_ADMISSION_SEMANTIC_DIGEST_REQUIRED",
            "integrity must bind the canonical typed envelope digest",
        )
    if value.raw_comment_body_sha_authoritative:
        _fail(
            "CONTROLLER_ADMISSION_RAW_BODY_SHA_FORBIDDEN",
            "mutable comment-body SHA is transport evidence, not semantic identity",
        )
    if value.digest_source not in DIGEST_SOURCES or value.predicted_digest_allowed:
        _fail(
            "CONTROLLER_ADMISSION_PREDICTED_DIGEST_FORBIDDEN",
            "digests must be observed or canonically recomputed, never predicted",
        )
    if value.schema_resolution != SCHEMA_DESCRIPTOR_BOUND:
        _fail(
            "CONTROLLER_ADMISSION_DESCRIPTOR_SCHEMA_REQUIRED",
            "schema must be resolved from the canonical descriptor/source binding",
        )
    if value.gate_state_basis != GATE_STATE_CURRENT_BOUNDARY:
        _fail(
            "CONTROLLER_ADMISSION_GATE_BOOTSTRAP_FORBIDDEN",
            "preapproval must start from the current verified boundary, not a target gate",
        )
    if value.approval_binding != APPROVAL_TYPED_ARTIFACT:
        _fail(
            "CONTROLLER_ADMISSION_TYPED_APPROVAL_REQUIRED",
            "human approval presentation must bind typed request + command digest",
        )

    return ControllerAdmissionReceipt(
        protocol=value.protocol,
        mailbox_ref=value.mailbox_ref,
        mode="HIGH_INTEGRITY",
        reason_codes=("CONTROLLER_ADMISSION_OK",),
    )


__all__ = [
    "ADMISSION_PROTOCOL",
    "APPROVAL_TYPED_ARTIFACT",
    "ControllerAdmissionError",
    "ControllerAdmissionInput",
    "ControllerAdmissionReceipt",
    "DIGEST_SOURCES",
    "GATE_STATE_CURRENT_BOUNDARY",
    "INTEGRITY_CANONICAL_ENVELOPE",
    "MAILBOX_READ_EXACT",
    "SCHEMA_DESCRIPTOR_BOUND",
    "validate_controller_admission",
]
