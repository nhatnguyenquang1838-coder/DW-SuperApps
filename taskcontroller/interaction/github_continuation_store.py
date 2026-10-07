"""GitHub append-only durable ContinuationStore for high-integrity TaskController runs.

The store persists ``RunManifest`` snapshots as immutable issue comments.  A
per-run/per-kind record sequence and digest chain make recovery independent of
mutable comment bodies, chat history, or process-local SQLite state.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from taskcontroller.audit.manifest import RunManifest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.github_mailbox_v2 import (
    GitHubIssueComment,
    GitHubIssueCommentTransport,
)
from taskcontroller.interaction.mailbox_v2 import canonical_digest


GITHUB_CONTINUATION_RECORD_PROTOCOL = "dw.taskcontroller.github-continuation-record/v1"


@dataclass(frozen=True, slots=True)
class ContinuationWriteReceipt:
    """Immutable GitHub evidence for one continuation record."""

    comment_id: str
    comment_ref: str
    run_id: str
    manifest_kind: str
    record_seq: int
    previous_record_digest: str | None
    manifest_digest: str
    record_digest: str
    idempotent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "comment_ref": self.comment_ref,
            "run_id": self.run_id,
            "manifest_kind": self.manifest_kind,
            "record_seq": self.record_seq,
            "previous_record_digest": self.previous_record_digest,
            "manifest_digest": self.manifest_digest,
            "record_digest": self.record_digest,
            "idempotent": self.idempotent,
        }


@dataclass(frozen=True, slots=True)
class _ContinuationRecord:
    comment_id: str
    run_id: str
    manifest_kind: str
    record_seq: int
    previous_record_digest: Optional[str]
    manifest_digest: str
    manifest: RunManifest
    record_digest: str


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"{name} must be non-empty")
    return value


def _manifest_payload(manifest: RunManifest) -> dict[str, Any]:
    if not isinstance(manifest, RunManifest):
        raise TaskControllerValidationError("continuation store requires RunManifest")
    return {
        "run_id": manifest.run_id,
        "manifest_kind": manifest.manifest_kind,
        "schema_version": manifest.schema_version,
        "created_at": manifest.created_at,
        "updated_at": manifest.updated_at,
        "metadata": copy.deepcopy(dict(manifest.metadata)),
    }


def _manifest_from_payload(payload: Mapping[str, Any]) -> RunManifest:
    if not isinstance(payload, Mapping):
        raise TaskControllerValidationError("continuation manifest payload must be an object")
    allowed = {
        "run_id",
        "manifest_kind",
        "schema_version",
        "created_at",
        "updated_at",
        "metadata",
    }
    if set(payload) != allowed:
        raise TaskControllerValidationError("continuation manifest fields are not canonical")
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise TaskControllerValidationError("continuation manifest metadata must be an object")
    try:
        return RunManifest(
            run_id=payload["run_id"],
            manifest_kind=payload["manifest_kind"],
            schema_version=payload["schema_version"],
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            metadata=copy.deepcopy(dict(metadata)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TaskControllerValidationError("invalid continuation RunManifest") from exc


def _record_body(
    *,
    run_id: str,
    manifest_kind: str,
    record_seq: int,
    previous_record_digest: Optional[str],
    manifest_digest: str,
    manifest_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "protocol": GITHUB_CONTINUATION_RECORD_PROTOCOL,
        "run_id": run_id,
        "manifest_kind": manifest_kind,
        "record_seq": record_seq,
        "previous_record_digest": previous_record_digest,
        "manifest_digest": manifest_digest,
        "manifest": copy.deepcopy(dict(manifest_payload)),
    }


def _render_record(body: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(body))
    payload["digest"] = canonical_digest(payload)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _comment_sort_key(comment: GitHubIssueComment) -> tuple[int, int | str]:
    try:
        return (0, int(comment.comment_id))
    except ValueError:
        return (1, comment.comment_id)


def _parse_record(comment: GitHubIssueComment) -> _ContinuationRecord | None:
    body = comment.body.strip()
    if not body:
        return None
    tagged = GITHUB_CONTINUATION_RECORD_PROTOCOL in body
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        if tagged:
            raise TaskControllerValidationError(
                f"tagged continuation comment {comment.comment_id} is not valid JSON"
            ) from exc
        return None
    if not isinstance(value, Mapping):
        return None
    if value.get("protocol") != GITHUB_CONTINUATION_RECORD_PROTOCOL:
        return None
    allowed = {
        "protocol",
        "run_id",
        "manifest_kind",
        "record_seq",
        "previous_record_digest",
        "manifest_digest",
        "manifest",
        "digest",
    }
    if set(value) != allowed:
        raise TaskControllerValidationError("continuation record fields are not canonical")
    record_seq = value.get("record_seq")
    if isinstance(record_seq, bool) or not isinstance(record_seq, int) or record_seq < 0:
        raise TaskControllerValidationError("continuation record_seq must be int >= 0")
    previous = value.get("previous_record_digest")
    if previous is not None and (not isinstance(previous, str) or not previous):
        raise TaskControllerValidationError("continuation previous_record_digest is invalid")
    run_id = _text(value.get("run_id"), "continuation run_id")
    manifest_kind = _text(value.get("manifest_kind"), "continuation manifest_kind")
    manifest_digest = _text(value.get("manifest_digest"), "continuation manifest_digest")
    record_digest = _text(value.get("digest"), "continuation record digest")
    manifest_payload = value.get("manifest")
    if not isinstance(manifest_payload, Mapping):
        raise TaskControllerValidationError("continuation manifest must be an object")
    if manifest_digest != canonical_digest(manifest_payload):
        raise TaskControllerValidationError("continuation manifest digest mismatch")
    manifest = _manifest_from_payload(manifest_payload)
    if manifest.run_id != run_id or manifest.manifest_kind != manifest_kind:
        raise TaskControllerValidationError("continuation record identity mismatch")
    unsigned = {key: copy.deepcopy(val) for key, val in value.items() if key != "digest"}
    if record_digest != canonical_digest(unsigned):
        raise TaskControllerValidationError("continuation record digest mismatch")
    return _ContinuationRecord(
        comment_id=comment.comment_id,
        run_id=run_id,
        manifest_kind=manifest_kind,
        record_seq=record_seq,
        previous_record_digest=previous,
        manifest_digest=manifest_digest,
        manifest=manifest,
        record_digest=record_digest,
    )


def _parse_instant(value: str) -> datetime:
    text = _text(value, "continuation timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TaskControllerValidationError("continuation timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise TaskControllerValidationError("continuation timestamp must include timezone")
    return parsed


class GitHubContinuationStore:
    """GitHub-backed implementation of ``ContinuationStore``.

    The configured issue is a shared durable recovery plane.  Records for other
    runs and manifest kinds coexist on the same issue and are filtered by exact
    identity.  Current TaskController topology requires one Controller writer.
    """

    def __init__(
        self,
        transport: GitHubIssueCommentTransport,
        *,
        repository: str,
        issue_number: int,
    ) -> None:
        if not isinstance(transport, GitHubIssueCommentTransport):
            raise TaskControllerValidationError(
                "GitHubContinuationStore requires GitHubIssueCommentTransport"
            )
        self.transport = transport
        self.repository = _text(repository, "continuation repository")
        if (
            isinstance(issue_number, bool)
            or not isinstance(issue_number, int)
            or issue_number <= 0
        ):
            raise TaskControllerValidationError("continuation issue_number must be int > 0")
        self.issue_number = issue_number

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "protocol": GITHUB_CONTINUATION_RECORD_PROTOCOL,
            "adapter": "github_issue_comments",
            "append_only": True,
            "exact_readback": True,
            "chat_history_recovery": False,
            "single_writer_required": True,
            "cross_process_multi_writer_cas": False,
            "operations": ["save_manifest", "load_manifest"],
        }

    def _all_records(self) -> tuple[_ContinuationRecord, ...]:
        comments = self.transport.list_comments(self.repository, self.issue_number)
        records: list[_ContinuationRecord] = []
        for comment in sorted(tuple(comments), key=_comment_sort_key):
            if not isinstance(comment, GitHubIssueComment):
                raise TaskControllerValidationError(
                    "GitHubIssueCommentTransport returned an invalid comment"
                )
            record = _parse_record(comment)
            if record is not None:
                records.append(record)
        return tuple(records)

    def _history(self, run_id: str, manifest_kind: str) -> tuple[_ContinuationRecord, ...]:
        _text(run_id, "continuation run_id")
        _text(manifest_kind, "continuation manifest_kind")
        records = tuple(
            record
            for record in self._all_records()
            if record.run_id == run_id and record.manifest_kind == manifest_kind
        )
        previous: str | None = None
        for index, record in enumerate(records):
            if record.record_seq != index:
                raise TaskControllerValidationError("continuation record sequence is not contiguous")
            if record.previous_record_digest != previous:
                raise TaskControllerValidationError("continuation record digest chain is broken")
            previous = record.record_digest
        return records

    def load_manifest(self, run_id: str, manifest_kind: str) -> RunManifest | None:
        history = self._history(run_id, manifest_kind)
        return history[-1].manifest if history else None

    def _receipt(self, record: _ContinuationRecord, *, idempotent: bool = False) -> ContinuationWriteReceipt:
        return ContinuationWriteReceipt(
            comment_id=record.comment_id,
            comment_ref=(
                f"github://{self.repository}/issues/{self.issue_number}"
                f"#issuecomment-{record.comment_id}"
            ),
            run_id=record.run_id,
            manifest_kind=record.manifest_kind,
            record_seq=record.record_seq,
            previous_record_digest=record.previous_record_digest,
            manifest_digest=record.manifest_digest,
            record_digest=record.record_digest,
            idempotent=idempotent,
        )

    def latest_receipt(self, run_id: str, manifest_kind: str) -> ContinuationWriteReceipt | None:
        history = self._history(run_id, manifest_kind)
        return self._receipt(history[-1], idempotent=True) if history else None

    def save_manifest_with_receipt(self, manifest: RunManifest) -> ContinuationWriteReceipt:
        payload = _manifest_payload(manifest)
        manifest_digest = canonical_digest(payload)
        history = self._history(manifest.run_id, manifest.manifest_kind)
        latest = history[-1] if history else None
        if latest is not None:
            if latest.manifest_digest == manifest_digest:
                return self._receipt(latest, idempotent=True)
            if latest.manifest.created_at != manifest.created_at:
                raise TaskControllerValidationError(
                    "continuation created_at cannot change for an existing run/kind"
                )
            if _parse_instant(manifest.updated_at) <= _parse_instant(latest.manifest.updated_at):
                raise TaskControllerValidationError(
                    "changed continuation updated_at must move strictly forward"
                )
        else:
            _parse_instant(manifest.created_at)
        _parse_instant(manifest.updated_at)
        record_seq = len(history)
        body = _record_body(
            run_id=manifest.run_id,
            manifest_kind=manifest.manifest_kind,
            record_seq=record_seq,
            previous_record_digest=latest.record_digest if latest is not None else None,
            manifest_digest=manifest_digest,
            manifest_payload=payload,
        )
        created = self.transport.create_comment(
            self.repository,
            self.issue_number,
            _render_record(body),
        )
        readback = self._history(manifest.run_id, manifest.manifest_kind)
        if len(readback) != record_seq + 1:
            raise TaskControllerValidationError("continuation exact readback record count mismatch")
        observed = readback[-1]
        if (
            observed.comment_id != created.comment_id
            or observed.manifest_digest != manifest_digest
            or observed.manifest != manifest
        ):
            raise TaskControllerValidationError("continuation exact readback differs from manifest")
        return self._receipt(observed)

    def save_manifest(self, manifest: RunManifest) -> None:
        self.save_manifest_with_receipt(manifest)


__all__ = [
    "ContinuationWriteReceipt",
    "GITHUB_CONTINUATION_RECORD_PROTOCOL",
    "GitHubContinuationStore",
]
