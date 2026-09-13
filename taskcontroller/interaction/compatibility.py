"""Explicit, lossless v1 request compatibility for mailbox/v2 rollout.

This adapter is deliberately narrower than the v1 envelope codec.  Existing
v1 mailbox actors continue to use their current codec and cursor semantics;
only an atomic v1 request with an explicitly Controller-bound v2 envelope may
cross into the v2 consumer lane.  No identity, boundary, generation, source,
or standards value is inferred from the legacy message.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope, EnvelopeKind
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    adapt_v1_to_v2,
)


_SUPPORTED_V1_REQUEST_KINDS = frozenset(
    {EnvelopeKind.COMMAND.value, EnvelopeKind.CORRECTION.value}
)

# These keys have v2 state-advancing meaning and must never be inferred from
# a v1 mutable state object.  A caller that needs them must use a native v2
# request or replan through Controller.
_V2_ONLY_STATE_KEYS = frozenset(
    {
        "attempt_id",
        "boundary_digest",
        "child_lifecycle",
        "contract_digest",
        "execution_boundary",
        "execution_identity",
        "fanout_manifest",
        "fencing_token",
        "generation",
        "join_policy",
        "lease_generation",
        "mixer_seal",
        "plan_version",
        "source_digest",
        "source_manifest",
        "standards_manifest",
        "standards_profile",
    }
)


def _reject(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


def _as_v1_envelope(value: A2AEnvelope | Mapping[str, Any]) -> A2AEnvelope:
    if isinstance(value, A2AEnvelope):
        return value
    if not isinstance(value, Mapping):
        _reject(MailboxV2ErrorCode.SCHEMA_INVALID, "v1 adapter input must be an envelope object")
    try:
        return A2AEnvelope.from_dict(dict(value))
    except TaskControllerValidationError as exc:
        _reject(MailboxV2ErrorCode.SCHEMA_INVALID, f"invalid v1 envelope: {exc}")


def _require_explicit_atomic_binding(
    legacy: A2AEnvelope,
    bound_v2_fields: Mapping[str, Any],
) -> None:
    if legacy.kind not in _SUPPORTED_V1_REQUEST_KINDS:
        _reject(
            MailboxV2ErrorCode.PROTOCOL_DOWNGRADE_UNSUPPORTED,
            f"v1 kind {legacy.kind!r} is not an atomic execution request",
        )
    if legacy.request is None or not legacy.request.strip():
        _reject(
            MailboxV2ErrorCode.REPLAN_REQUIRED,
            "v1 request text is required for a lossless atomic adapter",
        )

    state_keys = sorted(_V2_ONLY_STATE_KEYS.intersection(legacy.state))
    if state_keys:
        _reject(
            MailboxV2ErrorCode.REPLAN_REQUIRED,
            "v1 state contains v2-only semantics: " + ", ".join(state_keys),
        )

    required_top_level = {
        "protocol": "dw.taskcontroller.mailbox/v2",
        "run_id": legacy.run_id,
        "node_id": legacy.node_id,
        "seq": legacy.seq,
        "direction": "controller_to_executor",
        "message_type": "execution_request",
    }
    for key, expected in required_top_level.items():
        if bound_v2_fields.get(key) != expected:
            _reject(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                f"explicit v2 binding {key!r} does not preserve the v1 request",
            )

    producer = bound_v2_fields.get("producer")
    if not isinstance(producer, Mapping) or producer.get("actor_id") != legacy.sender:
        _reject(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "explicit v2 producer actor does not preserve the v1 sender",
        )

    recipient = bound_v2_fields.get("recipient")
    if not isinstance(recipient, Mapping) or recipient.get("agent_instance") != legacy.recipient:
        _reject(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "explicit v2 recipient instance does not preserve the v1 recipient",
        )

    logical_contract = bound_v2_fields.get("logical_contract")
    payload = bound_v2_fields.get("payload")
    if not isinstance(logical_contract, Mapping) or not isinstance(payload, Mapping):
        _reject(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "explicit v2 logical_contract and payload objects are required",
        )
    if logical_contract.get("objective") != legacy.request or payload.get("objective") != legacy.request:
        _reject(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "explicit v2 objective does not preserve the v1 request",
        )


def adapt_v1_request_to_v2(
    v1_envelope: A2AEnvelope | Mapping[str, Any],
    *,
    bound_v2_fields: Mapping[str, Any] | None = None,
) -> V2MailboxEnvelope:
    """Adapt one safe v1 request using Controller-supplied v2 bindings.

    The adapter is intentionally not a generic schema upgrader.  It accepts
    only atomic request kinds and requires the caller to provide every v2
    identity/boundary/source/standards field.  The original v1 object is
    retained as ``payload.legacy_v1`` evidence, while v2 validation and digest
    binding remain authoritative for the resulting envelope.
    """

    legacy = _as_v1_envelope(v1_envelope)
    if bound_v2_fields is None or not isinstance(bound_v2_fields, Mapping):
        _reject(
            MailboxV2ErrorCode.PROTOCOL_DOWNGRADE_UNSUPPORTED,
            "v2 bindings must be supplied explicitly; the adapter never infers them",
        )
    _require_explicit_atomic_binding(legacy, bound_v2_fields)
    return adapt_v1_to_v2(legacy.to_dict(), bound_v2_fields=bound_v2_fields)


class V1CompatibilityAdapter:
    """Stateless facade used by rollout adapters and tests."""

    @staticmethod
    def to_v2(
        v1_envelope: A2AEnvelope | Mapping[str, Any],
        *,
        bound_v2_fields: Mapping[str, Any] | None = None,
    ) -> V2MailboxEnvelope:
        return adapt_v1_request_to_v2(v1_envelope, bound_v2_fields=bound_v2_fields)


__all__ = ["V1CompatibilityAdapter", "adapt_v1_request_to_v2"]
