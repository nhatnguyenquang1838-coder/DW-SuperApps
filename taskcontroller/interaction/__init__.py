"""Transport-neutral TaskController Agent interaction primitives."""

from .audit import audit_event_from_envelope, record_envelope_event
from .envelope import A2A_PROTOCOL, A2AEnvelope, EnvelopeKind, MailboxCursor
from .github_mailbox import mailbox_operation, parse_mailbox_comment, render_mailbox_comment
from .human_projection import HumanEvent, HumanEventKind, project_envelope_for_human

__all__ = [
    "A2A_PROTOCOL",
    "A2AEnvelope",
    "EnvelopeKind",
    "HumanEvent",
    "HumanEventKind",
    "MailboxCursor",
    "audit_event_from_envelope",
    "mailbox_operation",
    "parse_mailbox_comment",
    "project_envelope_for_human",
    "record_envelope_event",
    "render_mailbox_comment",
]
