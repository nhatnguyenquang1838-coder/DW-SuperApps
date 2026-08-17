"""Transport-neutral TaskController Agent interaction primitives."""

from .audit import audit_event_from_envelope, record_envelope_event
from .continuation import (
    CONTINUATION_MANIFEST_KIND,
    CONTINUATION_PROTOCOL,
    CONTINUATION_STATE_KEY,
    ControllerContinuation,
    ContinuationPhase,
    ContinuationStatus,
    MailboxPollTarget,
    assert_controller_may_finalize,
    bind_continuation,
    continuation_from_envelope,
    persist_before_dispatch,
    persist_continuation,
    recover_continuation,
)
from .envelope import A2A_PROTOCOL, A2AEnvelope, EnvelopeKind, MailboxCursor
from .github_mailbox import mailbox_operation, parse_mailbox_comment, render_mailbox_comment
from .human_projection import HumanEvent, HumanEventKind, project_envelope_for_human
from .wakeup import WAKEUP_PROTOCOL, WakeupSignal

__all__ = [
    "A2A_PROTOCOL",
    "A2AEnvelope",
    "CONTINUATION_MANIFEST_KIND",
    "CONTINUATION_PROTOCOL",
    "CONTINUATION_STATE_KEY",
    "ControllerContinuation",
    "ContinuationPhase",
    "ContinuationStatus",
    "EnvelopeKind",
    "HumanEvent",
    "HumanEventKind",
    "MailboxCursor",
    "MailboxPollTarget",
    "WAKEUP_PROTOCOL",
    "WakeupSignal",
    "assert_controller_may_finalize",
    "audit_event_from_envelope",
    "bind_continuation",
    "continuation_from_envelope",
    "mailbox_operation",
    "parse_mailbox_comment",
    "persist_before_dispatch",
    "persist_continuation",
    "project_envelope_for_human",
    "record_envelope_event",
    "recover_continuation",
    "render_mailbox_comment",
]
