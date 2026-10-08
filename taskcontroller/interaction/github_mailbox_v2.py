"""GitHub issue-comment adapter for the append-only TaskController mailbox/v2 port.

Each accepted mailbox event and durable cursor acknowledgement is stored as one
new GitHub issue comment. Existing comments are never edited by this adapter.
The adapter deliberately accepts a tiny host-provided transport so the
TaskController kernel remains independent from any GitHub SDK or ChatGPT
connector implementation.

Concurrency model
-----------------
TaskController's current topology binds one writer to one actor mailbox. This
adapter therefore provides expected-sequence CAS under that single-writer
contract and fails closed if duplicate/conflicting event sequences are observed
on readback. It does not claim cross-process multi-writer atomic CAS.
"""

from __future__ import annotations

import copy
import json
import re
import threading
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol, Sequence, Tuple, Union, runtime_checkable

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import (
    EnvelopeInput,
    MailboxActorCursor,
    MailboxEvent,
    MailboxSnapshot,
    WriteReceipt,
)
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    V2_PROTOCOL,
    canonical_digest,
)


GITHUB_RECORD_PROTOCOL = "dw.taskcontroller.github-mailbox-record/v1"
_EVENT_RECORD = "event"
_CURSOR_RECORD = "cursor"
_RECORD_TYPES = frozenset({_EVENT_RECORD, _CURSOR_RECORD})
_MAILBOX_REF_RE = re.compile(
    r"^github://(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue>[1-9][0-9]*)#(?P<mailbox>[A-Za-z0-9._-]+)$"
)


@dataclass(frozen=True, slots=True)
class GitHubIssueComment:
    """Minimal immutable comment view required by the adapter."""

    comment_id: str
    body: str

    def __post_init__(self) -> None:
        if not isinstance(self.comment_id, str) or not self.comment_id:
            raise TaskControllerValidationError("GitHub comment id must be non-empty")
        if not isinstance(self.body, str):
            raise TaskControllerValidationError("GitHub comment body must be a string")


@runtime_checkable
class GitHubIssueCommentTransport(Protocol):
    """Host boundary for GitHub issue-comment list/append operations."""

    def list_comments(self, repository: str, issue_number: int) -> Sequence[GitHubIssueComment]:
        ...

    def create_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> GitHubIssueComment:
        ...


@dataclass(frozen=True, slots=True)
class GitHubMailboxRecordReceipt:
    """Immutable GitHub evidence for one mailbox event/cursor record."""

    comment_id: str
    comment_ref: str
    record_type: str
    mailbox_ref: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", copy.deepcopy(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "comment_ref": self.comment_ref,
            "record_type": self.record_type,
            "mailbox_ref": self.mailbox_ref,
            "payload": copy.deepcopy(dict(self.payload)),
        }


@dataclass(frozen=True, slots=True)
class _MailboxLocation:
    repository: str
    issue_number: int
    mailbox_name: str


@dataclass(frozen=True, slots=True)
class _RemoteRecord:
    comment_id: str
    record_type: str
    mailbox_ref: str
    payload: Mapping[str, Any]


def _fail(code: str, message: str) -> None:
    raise MailboxV2ValidationError(code, message)


def _parse_mailbox_ref(mailbox_ref: str) -> _MailboxLocation:
    if not isinstance(mailbox_ref, str) or not mailbox_ref:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "mailbox_ref must be non-empty")
    matched = _MAILBOX_REF_RE.fullmatch(mailbox_ref)
    if matched is None:
        _fail(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "GitHub mailbox_ref must be github://owner/repo/issues/<number>#<mailbox>",
        )
    return _MailboxLocation(
        repository=f"{matched.group('owner')}/{matched.group('repo')}",
        issue_number=int(matched.group("issue")),
        mailbox_name=matched.group("mailbox"),
    )


def _comment_sort_key(comment: GitHubIssueComment) -> tuple[int, Union[int, str]]:
    try:
        return (0, int(comment.comment_id))
    except ValueError:
        return (1, comment.comment_id)


def _render_record(
    *,
    record_type: str,
    mailbox_ref: str,
    payload: Mapping[str, Any],
) -> str:
    if record_type not in _RECORD_TYPES:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "unsupported GitHub mailbox record type")
    record = {
        "protocol": GITHUB_RECORD_PROTOCOL,
        "record_type": record_type,
        "mailbox_ref": mailbox_ref,
        "payload": copy.deepcopy(dict(payload)),
    }
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_record(comment: GitHubIssueComment) -> Optional[_RemoteRecord]:
    body = comment.body.strip()
    if not body:
        return None
    tagged_hint = GITHUB_RECORD_PROTOCOL in body
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        if tagged_hint:
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                f"tagged GitHub mailbox comment {comment.comment_id} is not valid JSON: {exc}",
            )
        return None
    if not isinstance(value, Mapping):
        return None
    if value.get("protocol") != GITHUB_RECORD_PROTOCOL:
        return None
    allowed = {"protocol", "record_type", "mailbox_ref", "payload"}
    unexpected = set(value) - allowed
    if unexpected:
        _fail(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "GitHub mailbox record contains unknown fields: " + ", ".join(sorted(unexpected)),
        )
    record_type = value.get("record_type")
    mailbox_ref = value.get("mailbox_ref")
    payload = value.get("payload")
    if record_type not in _RECORD_TYPES:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "GitHub mailbox record_type is invalid")
    if not isinstance(mailbox_ref, str) or not mailbox_ref:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "GitHub mailbox record mailbox_ref is invalid")
    if not isinstance(payload, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "GitHub mailbox record payload must be an object")
    return _RemoteRecord(
        comment_id=comment.comment_id,
        record_type=record_type,
        mailbox_ref=mailbox_ref,
        payload=copy.deepcopy(dict(payload)),
    )


def _event_from_payload(mailbox_ref: str, payload: Mapping[str, Any]) -> MailboxEvent:
    required = {
        "mailbox_ref",
        "event_id",
        "event_seq",
        "producer_namespace",
        "logical_seq",
        "previous_event_digest",
        "envelope_digest",
        "idempotency_key",
        "envelope",
        "digest",
    }
    if set(payload) != required:
        _fail(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "GitHub event payload fields do not exactly match MailboxEvent",
        )
    if payload.get("mailbox_ref") != mailbox_ref:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "event mailbox_ref differs from record")
    envelope_payload = payload.get("envelope")
    if not isinstance(envelope_payload, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "event envelope must be an object")
    envelope = V2MailboxEnvelope.from_dict(envelope_payload)
    try:
        event = MailboxEvent(
            mailbox_ref=payload["mailbox_ref"],
            event_id=payload["event_id"],
            event_seq=payload["event_seq"],
            producer_namespace=payload["producer_namespace"],
            logical_seq=payload["logical_seq"],
            previous_event_digest=payload["previous_event_digest"],
            envelope_digest=payload["envelope_digest"],
            idempotency_key=payload["idempotency_key"],
            envelope=envelope,
            event_digest=payload["digest"],
        )
    except (KeyError, TypeError) as exc:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"invalid GitHub event payload: {exc}")
    if event.envelope_digest != envelope.digest():
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "event envelope_digest differs from envelope")
    if event.producer_namespace != envelope.producer_namespace:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "event producer differs from envelope producer")
    if event.logical_seq != envelope.seq:
        _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "event logical sequence differs from envelope")
    if event.idempotency_key != envelope.idempotency_key:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "event idempotency key differs from envelope")
    if event.to_dict() != dict(payload):
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "event canonical readback differs from payload")
    return event


def _cursor_from_payload(mailbox_ref: str, payload: Mapping[str, Any]) -> MailboxActorCursor:
    cursor = MailboxActorCursor.from_dict(payload)
    if cursor.mailbox_ref != mailbox_ref:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "cursor mailbox_ref differs from record")
    return cursor


class GitHubMailboxRepository:
    """Append-only mailbox/v2 repository backed by GitHub issue comments."""

    def __init__(self, transport: GitHubIssueCommentTransport) -> None:
        if not isinstance(transport, GitHubIssueCommentTransport):
            raise TaskControllerValidationError(
                "GitHubMailboxRepository requires GitHubIssueCommentTransport"
            )
        self.transport = transport
        self._lock = threading.RLock()

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "protocol": V2_PROTOCOL,
            "adapter": "github_issue_comments",
            "record_protocol": GITHUB_RECORD_PROTOCOL,
            "append_only": True,
            "single_writer_required": True,
            "cross_process_multi_writer_cas": False,
            "supports_v1": False,
            "supports_v2": True,
            "operations": [
                "read",
                "write",
                "exact_readback",
                "scan_after",
                "read_cursor",
                "scan_after_cursor",
                "acknowledge_cursor",
            ],
        }

    def _records(self, mailbox_ref: str) -> Tuple[_RemoteRecord, ...]:
        location = _parse_mailbox_ref(mailbox_ref)
        comments = self.transport.list_comments(location.repository, location.issue_number)
        parsed: list[_RemoteRecord] = []
        for comment in sorted(tuple(comments), key=_comment_sort_key):
            if not isinstance(comment, GitHubIssueComment):
                raise TaskControllerValidationError(
                    "GitHubIssueCommentTransport returned an invalid comment"
                )

            # Issue comments are a shared append-only plane for many mailbox
            # epochs. A legacy malformed record for a different mailbox must
            # not poison reads of the selected mailbox. Filter by an explicit,
            # well-formed mailbox_ref hint before strict record validation.
            #
            # Fail closed when the tagged record cannot be safely attributed:
            # malformed JSON, missing/invalid mailbox_ref, or the selected
            # mailbox itself still flows through _parse_record().
            body = comment.body.strip()
            if body:
                try:
                    hinted = json.loads(body)
                except json.JSONDecodeError:
                    hinted = None
                if (
                    isinstance(hinted, Mapping)
                    and hinted.get("protocol") == GITHUB_RECORD_PROTOCOL
                ):
                    hinted_mailbox = hinted.get("mailbox_ref")
                    if (
                        isinstance(hinted_mailbox, str)
                        and hinted_mailbox
                        and hinted_mailbox != mailbox_ref
                    ):
                        continue

            record = _parse_record(comment)
            if record is None or record.mailbox_ref != mailbox_ref:
                continue
            parsed.append(record)
        return tuple(parsed)

    def _events(self, mailbox_ref: str) -> Tuple[MailboxEvent, ...]:
        events = tuple(
            _event_from_payload(mailbox_ref, record.payload)
            for record in self._records(mailbox_ref)
            if record.record_type == _EVENT_RECORD
        )
        previous_digest: Optional[str] = None
        producer_sequences: dict[str, int] = {}
        seen_ids: set[str] = set()
        seen_idempotency: dict[str, str] = {}
        for index, event in enumerate(events):
            if event.event_id in seen_ids:
                _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "duplicate mailbox event_id")
            seen_ids.add(event.event_id)
            if event.event_seq != index:
                _fail(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    f"mailbox event sequence is not contiguous at {event.event_id}",
                )
            expected_id = f"{mailbox_ref}:event-{index}"
            if event.event_id != expected_id:
                _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "mailbox event_id is not canonical")
            if event.previous_event_digest != previous_digest:
                _fail(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "mailbox previous_event_digest chain is broken",
                )
            producer_last = producer_sequences.get(event.producer_namespace, -1)
            if event.logical_seq <= producer_last:
                _fail(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    "producer logical sequence is not strictly monotonic",
                )
            producer_sequences[event.producer_namespace] = event.logical_seq
            existing_digest = seen_idempotency.get(event.idempotency_key)
            if existing_digest is not None:
                if existing_digest != event.envelope_digest:
                    _fail(
                        MailboxV2ErrorCode.DIGEST_MISMATCH,
                        "idempotency key is bound to conflicting envelopes",
                    )
                _fail(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    "duplicate idempotency record was appended instead of replayed",
                )
            seen_idempotency[event.idempotency_key] = event.envelope_digest
            previous_digest = event.event_digest
        return events

    def _build_snapshot(self, mailbox_ref: str) -> MailboxSnapshot:
        events = self._events(mailbox_ref)
        producer_cursors: dict[str, int] = {}
        for event in events:
            producer_cursors[event.producer_namespace] = max(
                producer_cursors.get(event.producer_namespace, -1),
                event.logical_seq,
            )
        producer_cursors = dict(sorted(producer_cursors.items()))
        return MailboxSnapshot(
            mailbox_ref=mailbox_ref,
            events=events,
            last_event_seq=len(events) - 1,
            accepted_state={
                "accepted_event_ids": [event.event_id for event in events],
                "last_event_digest": events[-1].event_digest if events else None,
                "last_event_seq": len(events) - 1,
                "producer_sequences": producer_cursors,
            },
            producer_cursors=producer_cursors,
        )

    def read(self, mailbox_ref: str) -> MailboxSnapshot:
        _parse_mailbox_ref(mailbox_ref)
        with self._lock:
            return self._build_snapshot(mailbox_ref)

    @staticmethod
    def _remote_receipt(mailbox_ref: str, record: _RemoteRecord) -> GitHubMailboxRecordReceipt:
        location = _parse_mailbox_ref(mailbox_ref)
        return GitHubMailboxRecordReceipt(
            comment_id=record.comment_id,
            comment_ref=(
                f"github://{location.repository}/issues/{location.issue_number}"
                f"#issuecomment-{record.comment_id}"
            ),
            record_type=record.record_type,
            mailbox_ref=mailbox_ref,
            payload=record.payload,
        )

    def event_receipt(self, mailbox_ref: str, event_id: str) -> GitHubMailboxRecordReceipt:
        matches = tuple(
            record
            for record in self._records(mailbox_ref)
            if record.record_type == _EVENT_RECORD and record.payload.get("event_id") == event_id
        )
        if len(matches) != 1:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "GitHub event receipt did not resolve exactly one remote comment",
            )
        return self._remote_receipt(mailbox_ref, matches[0])

    def cursor_receipt(self, cursor: MailboxActorCursor) -> GitHubMailboxRecordReceipt:
        if not isinstance(cursor, MailboxActorCursor):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "cursor_receipt requires MailboxActorCursor")
        matches: list[_RemoteRecord] = []
        for record in self._records(cursor.mailbox_ref):
            if record.record_type != _CURSOR_RECORD:
                continue
            candidate = _cursor_from_payload(cursor.mailbox_ref, record.payload)
            if candidate == cursor:
                matches.append(record)
        if len(matches) != 1:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "GitHub cursor receipt did not resolve exactly one remote comment",
            )
        return self._remote_receipt(cursor.mailbox_ref, matches[0])

    @staticmethod
    def _coerce_envelope(envelope: EnvelopeInput) -> V2MailboxEnvelope:
        if isinstance(envelope, V2MailboxEnvelope):
            return envelope
        if isinstance(envelope, Mapping):
            return V2MailboxEnvelope.from_dict(envelope)
        _fail(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "repository write requires a v2 envelope or mapping",
        )

    @staticmethod
    def _receipt(event: MailboxEvent, *, idempotent: bool = False) -> WriteReceipt:
        return WriteReceipt(
            mailbox_ref=event.mailbox_ref,
            event_id=event.event_id,
            event_seq=event.event_seq,
            message_id=event.envelope.to_dict()["message_id"],
            envelope_digest=event.envelope_digest,
            event_digest=event.event_digest,
            idempotent=idempotent,
        )

    def write(
        self,
        mailbox_ref: str,
        expected_seq: int,
        envelope: EnvelopeInput,
        *,
        expected_identity: Optional[Mapping[str, Any]] = None,
    ) -> WriteReceipt:
        if isinstance(expected_seq, bool) or not isinstance(expected_seq, int) or expected_seq < -1:
            _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "expected_seq must be >= -1")
        location = _parse_mailbox_ref(mailbox_ref)
        validated = self._coerce_envelope(envelope)
        if expected_identity is not None:
            validated.validate_current_identity(expected_identity)

        with self._lock:
            events = self._events(mailbox_ref)
            for event in events:
                if event.idempotency_key == validated.idempotency_key:
                    if event.envelope_digest != validated.digest():
                        _fail(
                            MailboxV2ErrorCode.DIGEST_MISMATCH,
                            "idempotency key was reused with a different envelope digest",
                        )
                    return self._receipt(event, idempotent=True)

            current_seq = len(events) - 1
            if expected_seq != current_seq:
                _fail(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    f"expected mailbox sequence {expected_seq}, current sequence is {current_seq}",
                )
            producer_last_seq = max(
                (
                    event.logical_seq
                    for event in events
                    if event.producer_namespace == validated.producer_namespace
                ),
                default=-1,
            )
            if validated.seq <= producer_last_seq:
                _fail(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    f"producer sequence {validated.seq} is not newer than {producer_last_seq}",
                )

            event_seq = len(events)
            event_body = {
                "mailbox_ref": mailbox_ref,
                "event_id": f"{mailbox_ref}:event-{event_seq}",
                "event_seq": event_seq,
                "producer_namespace": validated.producer_namespace,
                "logical_seq": validated.seq,
                "previous_event_digest": events[-1].event_digest if events else None,
                "envelope_digest": validated.digest(),
                "idempotency_key": validated.idempotency_key,
                "envelope": validated.to_dict(),
            }
            event = MailboxEvent(
                mailbox_ref=mailbox_ref,
                event_id=event_body["event_id"],
                event_seq=event_seq,
                producer_namespace=validated.producer_namespace,
                logical_seq=validated.seq,
                previous_event_digest=event_body["previous_event_digest"],
                envelope_digest=event_body["envelope_digest"],
                idempotency_key=event_body["idempotency_key"],
                envelope=validated,
                event_digest=canonical_digest(event_body),
            )
            self.transport.create_comment(
                location.repository,
                location.issue_number,
                _render_record(
                    record_type=_EVENT_RECORD,
                    mailbox_ref=mailbox_ref,
                    payload=event.to_dict(),
                ),
            )

            readback = self._events(mailbox_ref)
            if len(readback) != event_seq + 1 or readback[event_seq] != event:
                _fail(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "GitHub mailbox append exact readback differs from event",
                )
            return self._receipt(event)

    def exact_readback(self, receipt: WriteReceipt) -> MailboxSnapshot:
        if not isinstance(receipt, WriteReceipt):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "exact_readback requires WriteReceipt")
        snapshot = self.read(receipt.mailbox_ref)
        matching = tuple(event for event in snapshot.events if event.event_id == receipt.event_id)
        if len(matching) != 1:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "exact readback did not find exactly one receipt event",
            )
        event = matching[0]
        if (
            event.event_seq != receipt.event_seq
            or event.envelope_digest != receipt.envelope_digest
            or event.event_digest != receipt.event_digest
            or event.envelope.to_dict()["message_id"] != receipt.message_id
        ):
            _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "exact readback differs from receipt")
        return snapshot

    def scan_after(self, mailbox_ref: str, cursor: int) -> Tuple[MailboxEvent, ...]:
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < -1:
            _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "scan cursor must be >= -1")
        return tuple(event for event in self.read(mailbox_ref).events if event.event_seq > cursor)

    @staticmethod
    def _cursor_key(cursor: MailboxActorCursor) -> tuple[str, str, str]:
        return (cursor.run_id, cursor.node_id, cursor.actor_namespace)

    def _matching_cursor_records(
        self,
        mailbox_ref: str,
        *,
        run_id: str,
        node_id: str,
        actor_namespace: str,
    ) -> Tuple[MailboxActorCursor, ...]:
        expected = (run_id, node_id, actor_namespace)
        cursors: list[MailboxActorCursor] = []
        for record in self._records(mailbox_ref):
            if record.record_type != _CURSOR_RECORD:
                continue
            cursor = _cursor_from_payload(mailbox_ref, record.payload)
            if self._cursor_key(cursor) == expected:
                cursors.append(cursor)
        prior = MailboxActorCursor.initial(
            mailbox_ref,
            run_id=run_id,
            node_id=node_id,
            actor_namespace=actor_namespace,
        )
        for cursor in cursors:
            if cursor == prior:
                continue
            if cursor.last_event_seq < prior.last_event_seq or cursor.last_logical_seq < prior.last_logical_seq:
                _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "durable GitHub cursor regressed")
            if cursor.last_event_seq == prior.last_event_seq:
                _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "durable GitHub cursor conflicts")
            prior = cursor
        return tuple(cursors)

    def read_cursor(
        self,
        mailbox_ref: str,
        run_id: str,
        node_id: str,
        actor_namespace: str,
    ) -> MailboxActorCursor:
        _parse_mailbox_ref(mailbox_ref)
        for name, value in {
            "run_id": run_id,
            "node_id": node_id,
            "actor_namespace": actor_namespace,
        }.items():
            if not isinstance(value, str) or not value:
                _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be non-empty")
        with self._lock:
            records = self._matching_cursor_records(
                mailbox_ref,
                run_id=run_id,
                node_id=node_id,
                actor_namespace=actor_namespace,
            )
            if records:
                return records[-1]
            return MailboxActorCursor.initial(
                mailbox_ref,
                run_id=run_id,
                node_id=node_id,
                actor_namespace=actor_namespace,
            )

    def scan_after_cursor(self, cursor: MailboxActorCursor) -> Tuple[MailboxEvent, ...]:
        if not isinstance(cursor, MailboxActorCursor):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "scan_after_cursor requires MailboxActorCursor")
        events = self.scan_after(cursor.mailbox_ref, cursor.last_event_seq)
        return tuple(
            event
            for event in events
            if (
                event.envelope.run_id == cursor.run_id
                and event.envelope.node_id == cursor.node_id
                and event.producer_namespace == cursor.actor_namespace
            )
        )

    def acknowledge_cursor(self, cursor: MailboxActorCursor) -> MailboxActorCursor:
        if not isinstance(cursor, MailboxActorCursor):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "acknowledge_cursor requires MailboxActorCursor")
        location = _parse_mailbox_ref(cursor.mailbox_ref)
        with self._lock:
            current = self.read_cursor(
                cursor.mailbox_ref,
                cursor.run_id,
                cursor.node_id,
                cursor.actor_namespace,
            )
            if cursor == current:
                return current
            if (
                cursor.last_event_seq <= current.last_event_seq
                or cursor.last_logical_seq <= current.last_logical_seq
            ):
                _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "cursor acknowledgement is not newer")

            snapshot = self.read(cursor.mailbox_ref)
            if cursor.last_event_seq >= len(snapshot.events):
                _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "cursor points beyond mailbox")
            event = snapshot.events[cursor.last_event_seq]
            cursor._validate_event_binding(event)
            if (
                cursor.last_event_id != event.event_id
                or cursor.last_event_digest != event.event_digest
                or cursor.last_logical_seq != event.logical_seq
            ):
                _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "cursor does not bind exact mailbox event")

            self.transport.create_comment(
                location.repository,
                location.issue_number,
                _render_record(
                    record_type=_CURSOR_RECORD,
                    mailbox_ref=cursor.mailbox_ref,
                    payload=cursor.to_dict(),
                ),
            )
            readback = self.read_cursor(
                cursor.mailbox_ref,
                cursor.run_id,
                cursor.node_id,
                cursor.actor_namespace,
            )
            if readback != cursor:
                _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "cursor exact readback differs")
            return readback


__all__ = [
    "GITHUB_RECORD_PROTOCOL",
    "GitHubIssueComment",
    "GitHubIssueCommentTransport",
    "GitHubMailboxRecordReceipt",
    "GitHubMailboxRepository",
]
