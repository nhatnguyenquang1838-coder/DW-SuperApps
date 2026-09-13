"""Controller-side continuation binding for mailbox/v2 dispatch.

This module is a narrow boundary between the existing durable continuation
manifest and the pure v2 request compiler. It performs no remote mailbox,
Slack, routing, or executor I/O. The only durable operation is the existing
``persist_before_dispatch`` exact-readback path.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, NoReturn

from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
)
from taskcontroller.interaction.continuation import (
    ContinuationStore,
    ControllerContinuation,
    persist_before_dispatch,
    recover_continuation,
)
def _fail(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


def _bound_request(
    request: BoundedMailboxRequest | Mapping[str, Any],
) -> BoundedMailboxRequest:
    if isinstance(request, BoundedMailboxRequest):
        return request
    if isinstance(request, Mapping):
        return BoundedMailboxRequest.from_mapping(request)
    _fail(
        MailboxV2ErrorCode.SCHEMA_INVALID,
        "v2 continuation dispatch request must be an object",
    )


def _bind_checkpoint(
    request: BoundedMailboxRequest,
    checkpoint: ControllerContinuation,
) -> BoundedMailboxRequest:
    checkpoint_id = checkpoint.checkpoint_id
    if request.checkpoint_id is not None and request.checkpoint_id != checkpoint_id:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "request checkpoint ID does not match continuation checkpoint",
        )

    try:
        payload = dict(request.payload)
    except (TypeError, ValueError) as exc:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"request payload must be an object: {exc}")
    payload_checkpoint_id = payload.pop("checkpoint_id", None)
    if payload_checkpoint_id is not None and payload_checkpoint_id != checkpoint_id:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "request payload checkpoint ID does not match continuation checkpoint",
        )
    return replace(request, checkpoint_id=checkpoint_id, payload=payload)


def _assert_request_binding(
    request: BoundedMailboxRequest,
    checkpoint: ControllerContinuation,
) -> None:
    if request.run_id != checkpoint.run_id:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "request run_id does not match continuation checkpoint",
        )
    if request.seq != checkpoint.controller_seq:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "request seq does not match continuation checkpoint controller seq",
        )
    if request.agent_instance != checkpoint.executor_actor:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "request AgentInstance does not match continuation executor",
        )


def prepare_v2_dispatch(
    store: ContinuationStore,
    checkpoint: ControllerContinuation,
    request: BoundedMailboxRequest | Mapping[str, Any],
) -> V2MailboxEnvelope:
    """Persist and read back continuation before preparing one v2 request.

    The checkpoint is validated against the request before any write. Once the
    binding is valid, ``persist_before_dispatch`` is the first stateful action;
    it must complete its durable readback before the v2 request is compiled.
    """

    if not isinstance(checkpoint, ControllerContinuation):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "continuation checkpoint is required")
    bound = _bound_request(request)
    _assert_request_binding(bound, checkpoint)
    bound = _bind_checkpoint(bound, checkpoint)

    persisted = persist_before_dispatch(store, checkpoint)
    envelope = compile_bounded_mailbox_request(bound)
    payload = envelope.to_dict()
    if payload["payload"].get("checkpoint_id") != persisted.checkpoint_id:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "compiled request checkpoint ID does not match persisted checkpoint",
        )
    return envelope


def recover_v2_dispatch(
    store: ContinuationStore,
    envelope: V2MailboxEnvelope,
) -> ControllerContinuation:
    """Recover a v2 dispatch from durable continuation plus mailbox evidence.

    The caller supplies the exact mailbox envelope readback. No chat transcript
    or Slack projection is consulted or accepted as recovery input.
    """

    if not isinstance(envelope, V2MailboxEnvelope):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "v2 mailbox envelope is required")
    payload = envelope.to_dict()
    if payload.get("message_type") != "execution_request":
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "recovery requires an execution_request envelope",
        )
    request_payload = payload.get("payload")
    if not isinstance(request_payload, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "execution request payload is not an object")
    checkpoint_id = request_payload.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "execution request is missing checkpoint ID",
        )

    checkpoint = recover_continuation(store, envelope.run_id)
    if checkpoint is None:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "durable continuation checkpoint is missing",
        )
    checkpoint.poll_target()
    if checkpoint.checkpoint_id != checkpoint_id:
        _fail(
            MailboxV2ErrorCode.DIGEST_MISMATCH,
            "checkpoint ID does not match durable continuation",
        )
    if checkpoint.controller_seq != envelope.seq:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "mailbox request seq does not match continuation checkpoint",
        )
    recipient = payload.get("recipient")
    if not isinstance(recipient, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "execution request recipient is not an object")
    if recipient.get("agent_instance") != checkpoint.executor_actor:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "execution request AgentInstance does not match continuation executor",
        )
    return checkpoint


__all__ = ["prepare_v2_dispatch", "recover_v2_dispatch"]
