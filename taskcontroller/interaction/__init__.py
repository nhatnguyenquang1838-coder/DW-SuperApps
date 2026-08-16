"""Transport-neutral TaskController Agent interaction primitives."""

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
    "mailbox_operation",
    "parse_mailbox_comment",
    "project_envelope_for_human",
    "render_mailbox_comment",
]
