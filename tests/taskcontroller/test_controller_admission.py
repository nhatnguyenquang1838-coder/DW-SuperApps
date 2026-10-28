from __future__ import annotations

import pytest

from taskcontroller.controlplane.controller_admission import (
    APPROVAL_TYPED_ARTIFACT,
    GATE_STATE_CURRENT_BOUNDARY,
    INTEGRITY_CANONICAL_ENVELOPE,
    MAILBOX_READ_EXACT,
    SCHEMA_DESCRIPTOR_BOUND,
    ControllerAdmissionError,
    ControllerAdmissionInput,
    validate_controller_admission,
)
from taskcontroller.interaction.mailbox_v2 import V1_PROTOCOL, V2_PROTOCOL


MAILBOX = "github://org/repo/issues/575#issuecomment-executor"


def _high_integrity(**overrides) -> ControllerAdmissionInput:
    values = {
        "requires_v2_semantics": True,
        "protocol": V2_PROTOCOL,
        "mailbox_ref": MAILBOX,
        "mailbox_read_scope": MAILBOX_READ_EXACT,
        "integrity_binding": INTEGRITY_CANONICAL_ENVELOPE,
        "digest_source": "observed",
        "schema_resolution": SCHEMA_DESCRIPTOR_BOUND,
        "gate_state_basis": GATE_STATE_CURRENT_BOUNDARY,
        "approval_binding": APPROVAL_TYPED_ARTIFACT,
        "raw_comment_body_sha_authoritative": False,
        "issue_wide_machine_scan": False,
        "predicted_digest_allowed": False,
    }
    values.update(overrides)
    return ControllerAdmissionInput(**values)


def test_high_integrity_admission_passes_only_typed_v2_semantics() -> None:
    receipt = validate_controller_admission(_high_integrity())

    assert receipt.mode == "HIGH_INTEGRITY"
    assert receipt.protocol == V2_PROTOCOL
    assert receipt.mailbox_ref == MAILBOX
    assert receipt.reason_codes == ("CONTROLLER_ADMISSION_OK",)
    assert receipt.authority_granted is False


def test_v1_remains_available_only_for_compatibility_lane() -> None:
    receipt = validate_controller_admission(
        ControllerAdmissionInput(
            requires_v2_semantics=False,
            protocol=V1_PROTOCOL,
            mailbox_ref=MAILBOX,
        )
    )

    assert receipt.mode == "COMPATIBILITY"
    assert receipt.authority_granted is False


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"protocol": V1_PROTOCOL}, "CONTROLLER_ADMISSION_V2_REQUIRED"),
        ({"mailbox_read_scope": "whole_issue"}, "CONTROLLER_ADMISSION_EXACT_MAILBOX_REQUIRED"),
        ({"issue_wide_machine_scan": True}, "CONTROLLER_ADMISSION_ISSUE_SCAN_FORBIDDEN"),
        ({"integrity_binding": "full_comment_body_sha256"}, "CONTROLLER_ADMISSION_SEMANTIC_DIGEST_REQUIRED"),
        ({"raw_comment_body_sha_authoritative": True}, "CONTROLLER_ADMISSION_RAW_BODY_SHA_FORBIDDEN"),
        ({"digest_source": "controller_prediction"}, "CONTROLLER_ADMISSION_PREDICTED_DIGEST_FORBIDDEN"),
        ({"predicted_digest_allowed": True}, "CONTROLLER_ADMISSION_PREDICTED_DIGEST_FORBIDDEN"),
        ({"schema_resolution": "legacy_path_guess"}, "CONTROLLER_ADMISSION_DESCRIPTOR_SCHEMA_REQUIRED"),
        ({"gate_state_basis": "target_gate_bootstrap"}, "CONTROLLER_ADMISSION_GATE_BOOTSTRAP_FORBIDDEN"),
        ({"approval_binding": "mailbox_body_sha"}, "CONTROLLER_ADMISSION_TYPED_APPROVAL_REQUIRED"),
    ],
)
def test_observed_controller_failure_modes_fail_closed(overrides: dict, code: str) -> None:
    with pytest.raises(ControllerAdmissionError) as exc:
        validate_controller_admission(_high_integrity(**overrides))

    assert exc.value.code == code


def test_missing_exact_mailbox_reference_fails_closed() -> None:
    with pytest.raises(ControllerAdmissionError) as exc:
        validate_controller_admission(_high_integrity(mailbox_ref=""))

    assert exc.value.code == "CONTROLLER_ADMISSION_MAILBOX_REQUIRED"


def test_recomputed_digest_is_allowed_but_prediction_is_not() -> None:
    receipt = validate_controller_admission(_high_integrity(digest_source="canonical_recompute"))
    assert receipt.reason_codes == ("CONTROLLER_ADMISSION_OK",)
