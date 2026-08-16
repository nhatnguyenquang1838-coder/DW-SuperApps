"""Pure GitHub mailbox comment codec for the reference-based A2A pilot.

Network I/O belongs to a host adapter/connector. This module only defines the
deterministic representation stored in one mutable comment per actor.
"""

from __future__ import annotations

import json
import re

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope

_MARKER = re.compile(r"<!-- taskcontroller:mailbox:([A-Za-z0-9._-]+) -->")
_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def render_mailbox_comment(envelope: A2AEnvelope) -> str:
    if not isinstance(envelope, A2AEnvelope):
        raise TaskControllerValidationError("github mailbox requires A2AEnvelope")
    encoded = json.dumps(
        envelope.to_dict(),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        f"<!-- taskcontroller:mailbox:{envelope.sender} -->\n"
        f"TaskController mailbox · {envelope.sender}\n"
        f"Latest seq: {envelope.seq}\n"
        f"Kind: {envelope.kind}\n"
        f"Updated: {envelope.updated_at}\n\n"
        "```json\n"
        f"{encoded}\n"
        "```\n"
    )


def parse_mailbox_comment(body: str) -> A2AEnvelope:
    if not isinstance(body, str) or not body:
        raise TaskControllerValidationError("github mailbox body must be non-empty")

    markers = _MARKER.findall(body)
    if len(markers) != 1:
        raise TaskControllerValidationError(
            "github mailbox must contain exactly one actor marker"
        )

    payloads = _JSON_FENCE.findall(body)
    if len(payloads) != 1:
        raise TaskControllerValidationError(
            "github mailbox must contain exactly one JSON envelope"
        )
    try:
        decoded = json.loads(payloads[0])
    except json.JSONDecodeError as exc:
        raise TaskControllerValidationError("github mailbox JSON is malformed") from exc

    envelope = A2AEnvelope.from_dict(decoded)
    if markers[0] != envelope.sender:
        raise TaskControllerValidationError(
            "github mailbox actor marker does not match envelope sender"
        )
    return envelope


def mailbox_operation(comment_id: int | str | None) -> str:
    """Return host write intent while preserving one-actor-one-comment semantics."""

    if comment_id is None:
        return "CREATE_COMMENT"
    if isinstance(comment_id, bool):
        raise TaskControllerValidationError("mailbox comment id is invalid")
    if isinstance(comment_id, int):
        if comment_id <= 0:
            raise TaskControllerValidationError("mailbox comment id must be positive")
        return "UPDATE_COMMENT"
    if isinstance(comment_id, str) and comment_id:
        return "UPDATE_COMMENT"
    raise TaskControllerValidationError("mailbox comment id is invalid")
