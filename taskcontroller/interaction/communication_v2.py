"""Human-readable v2 peer communication envelope.

ONE lightweight codec for GPT/Hermes coordination. It does not invoke the
protected TaskController mailbox/v2 materializer, issuer or lease validator.
A host connector owns single-writer append, sender authentication and readback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from taskcontroller.errors import TaskControllerValidationError

PROTOCOL = "dw.taskcontroller.communication/v2"
MARKER = "<!-- dw.taskcontroller.communication/v2 -->"
KINDS = frozenset({"COMMAND", "REPORT", "CORRECTION", "ACK"})
FIELD_RE = re.compile(r"^(run|seq|from|to|kind|source_ref|reply_to): (.+)$")
MAX_TEXT = 4000


def _valid(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise TaskControllerValidationError(f"invalid communication field: {label}")
    return value.strip()


@dataclass(frozen=True)
class CommunicationV2:
    run: str
    seq: int
    sender: str
    recipient: str
    kind: str
    goal: str
    next_action: str
    evidence: str = "none"
    source_ref: str = "none"
    reply_to: str = "none"

    def __post_init__(self) -> None:
        for label in ("run", "sender", "recipient", "source_ref", "reply_to"):
            _valid(getattr(self, label), label)
        if type(self.seq) is not int or self.seq < 1:
            raise TaskControllerValidationError("communication seq must be positive int")
        if self.kind not in KINDS or self.sender == self.recipient:
            raise TaskControllerValidationError("invalid kind or sender/recipient")
        for label in ("goal", "next_action", "evidence"):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
                raise TaskControllerValidationError(f"invalid communication body: {label}")

    def render(self) -> str:
        """Readable template; explicit typed marker distinguishes v2 machine events."""
        return (
            f"{MARKER}\n"
            f"### A2A v2 · {self.kind} #{self.seq}\n"
            f"run: {self.run}\nseq: {self.seq}\nfrom: {self.sender}\n"
            f"to: {self.recipient}\nkind: {self.kind}\n"
            f"source_ref: {self.source_ref}\nreply_to: {self.reply_to}\n\n"
            f"**GOAL**\n{self.goal.strip()}\n\n"
            f"**NEXT**\n{self.next_action.strip()}\n\n"
            f"**EVIDENCE**\n{self.evidence.strip()}\n"
        )


def parse(text: str) -> CommunicationV2 | None:
    """Ignore unrelated comments. Reject malformed comments carrying our marker."""
    if not isinstance(text, str) or MARKER not in text:
        return None
    if text.count(MARKER) != 1:
        raise TaskControllerValidationError("duplicate communication marker")
    lines = text.splitlines()
    if len(lines) < 17 or lines[0] != MARKER:
        raise TaskControllerValidationError("malformed communication header")
    header = {}
    for line in lines[2:9]:
        m = FIELD_RE.fullmatch(line)
        if m is None or m.group(1) in header:
            raise TaskControllerValidationError("malformed communication fields")
        header[m.group(1)] = m.group(2)
    if set(header) != {"run", "seq", "from", "to", "kind", "source_ref", "reply_to"}:
        raise TaskControllerValidationError("missing communication field")
    m = re.fullmatch(r"### A2A v2 · (COMMAND|REPORT|CORRECTION|ACK) #(\d+)", lines[1])
    if m is None or m.group(1) != header["kind"] or m.group(2) != header["seq"]:
        raise TaskControllerValidationError("communication header identity mismatch")
    pattern = re.compile(r"\n\n\*\*GOAL\*\*\n(.*?)\n\n\*\*NEXT\*\*\n(.*?)\n\n\*\*EVIDENCE\*\*\n(.*?)\n?\Z", re.S)
    body = pattern.search(text)
    if body is None:
        raise TaskControllerValidationError("malformed communication sections")
    return CommunicationV2(
        run=header["run"], seq=int(header["seq"]),
        sender=header["from"], recipient=header["to"], kind=header["kind"],
        source_ref=header["source_ref"], reply_to=header["reply_to"],
        goal=body.group(1), next_action=body.group(2), evidence=body.group(3),
    )


def next_seq(history: Sequence[str], *, run: str) -> int:
    """Sequential per-run peer commands, separate from protected C/E logical seq."""
    expected = 1
    for body in history:
        item = parse(body)
        if item is None or item.run != run:
            continue
        if item.seq != expected:
            raise TaskControllerValidationError(
                f"communication sequence gap/fork: expected {expected}, got {item.seq}"
            )
        expected += 1
    return expected


def create_next(history: Sequence[str], *, run: str, sender: str, recipient: str,
                kind: str, goal: str, next_action: str, evidence: str = "none",
                source_ref: str = "none", reply_to: str = "none") -> CommunicationV2:
    return CommunicationV2(
        run=run, seq=next_seq(history, run=run), sender=sender,
        recipient=recipient, kind=kind, goal=goal, next_action=next_action,
        evidence=evidence, source_ref=source_ref, reply_to=reply_to,
    )
