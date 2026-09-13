"""Deterministic Controller crash recovery from durable machine references.

This module is intentionally provider-neutral.  It binds the existing
``ControllerContinuation`` to a Run Ledger manifest identity and exact mailbox
references/cursors.  Recovery reads the durable manifest and one canonical
Controller mailbox envelope; Slack and chat transcripts are not inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol

from taskcontroller.audit.manifest import RunManifest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.continuation import (
    CONTINUATION_PROTOCOL,
    ControllerContinuation,
    ContinuationStore,
    continuation_from_envelope,
    persist_continuation,
    recover_continuation,
)
from taskcontroller.interaction.envelope import A2AEnvelope, MailboxCursor
from taskcontroller.interaction.github_mailbox import parse_mailbox_comment
from taskcontroller.interaction.mailbox_v2 import canonical_digest


CRASH_RECOVERY_PROTOCOL = "dw.taskcontroller.crash-recovery/v1"
CRASH_RECOVERY_MANIFEST_KIND = CRASH_RECOVERY_PROTOCOL
CRASH_RECOVERY_SCHEMA_VERSION = "1.0"
LEDGER_REF_PROTOCOL = "dw.taskcontroller.run-ledger-ref/v1"

_CONTINUATION_FIELDS = {
    "protocol",
    "run_id",
    "controller_epoch",
    "phase",
    "status",
    "next_action",
    "controller_mailbox_ref",
    "controller_seq",
    "executor_actor",
    "executor_mailbox_ref",
    "expected_executor_seq",
    "last_seen_executor_seq",
    "wakeup_binding",
    "exact_head_sha",
    "updated_at",
    "human_root_ref",
}
_CURSOR_FIELDS = {"actor", "last_seen_seq", "mailbox_ref", "last_head_sha"}


class CrashRecoveryError(TaskControllerValidationError):
    """Stable fail-closed error for Controller crash recovery."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise CrashRecoveryError(code, message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("RECOVERY_BINDING_INVALID", f"{name} must be a non-empty string")
    if "\x00" in value:
        _fail("RECOVERY_BINDING_INVALID", f"{name} must not contain NUL")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("RECOVERY_BINDING_INVALID", f"{name} must be an integer > 0")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("RECOVERY_BINDING_INVALID", f"{name} must be an integer >= 0")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("RECOVERY_BINDING_INVALID", f"{name} must be an object")
    return value


def _strict_fields(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unexpected = set(value) - allowed
    if unexpected:
        _fail(
            "RECOVERY_BINDING_INVALID",
            f"{name} contains unknown fields: {', '.join(sorted(unexpected))}",
        )


@dataclass(frozen=True, slots=True)
class RunLedgerRef:
    """Stable identity of the Run Ledger manifest used for recovery."""

    run_id: str
    manifest_kind: str = CRASH_RECOVERY_MANIFEST_KIND

    def __post_init__(self) -> None:
        _text(self.run_id, "ledger_ref.run_id")
        if self.manifest_kind != CRASH_RECOVERY_MANIFEST_KIND:
            _fail(
                "RECOVERY_BINDING_INVALID",
                "ledger_ref.manifest_kind must identify the crash-recovery manifest",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": LEDGER_REF_PROTOCOL,
            "run_id": self.run_id,
            "manifest_kind": self.manifest_kind,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunLedgerRef":
        payload = _mapping(payload, "ledger_ref")
        _strict_fields(payload, {"protocol", "run_id", "manifest_kind"}, "ledger_ref")
        if payload.get("protocol") != LEDGER_REF_PROTOCOL:
            _fail("RECOVERY_BINDING_INVALID", "unsupported Run Ledger reference protocol")
        try:
            return cls(run_id=payload["run_id"], manifest_kind=payload["manifest_kind"])
        except KeyError as exc:
            _fail("RECOVERY_BINDING_INVALID", "ledger_ref is missing a required field")
            raise AssertionError("_fail must raise") from exc


@dataclass(frozen=True, slots=True)
class MailboxRecoveryRef:
    """One exact mailbox pointer plus the cursor/target sequence to resume."""

    actor: str
    mailbox_ref: str
    cursor: MailboxCursor
    target_seq: int

    def __post_init__(self) -> None:
        _text(self.actor, "mailbox.actor")
        _text(self.mailbox_ref, "mailbox.mailbox_ref")
        if not isinstance(self.cursor, MailboxCursor):
            _fail("RECOVERY_BINDING_INVALID", "mailbox.cursor must be a MailboxCursor")
        _positive_int(self.target_seq, "mailbox.target_seq")
        if self.cursor.actor != self.actor:
            _fail("RECOVERY_BINDING_INVALID", "mailbox cursor actor does not match mailbox actor")
        if self.cursor.mailbox_ref != self.mailbox_ref:
            _fail("RECOVERY_BINDING_INVALID", "mailbox cursor ref does not match mailbox ref")
        if self.target_seq < self.cursor.last_seen_seq:
            _fail("RECOVERY_BINDING_INVALID", "mailbox target sequence cannot precede cursor")

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "mailbox_ref": self.mailbox_ref,
            "cursor": self.cursor.to_dict(),
            "target_seq": self.target_seq,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MailboxRecoveryRef":
        payload = _mapping(payload, "mailbox")
        _strict_fields(payload, {"actor", "mailbox_ref", "cursor", "target_seq"}, "mailbox")
        cursor_payload = _mapping(payload.get("cursor"), "mailbox.cursor")
        _strict_fields(cursor_payload, _CURSOR_FIELDS, "mailbox.cursor")
        try:
            cursor = MailboxCursor.from_dict(dict(cursor_payload))
            return cls(
                actor=payload["actor"],
                mailbox_ref=payload["mailbox_ref"],
                cursor=cursor,
                target_seq=payload["target_seq"],
            )
        except KeyError as exc:
            _fail("RECOVERY_BINDING_INVALID", "mailbox reference is missing a required field")
            raise AssertionError("_fail must raise") from exc


@dataclass(frozen=True, slots=True)
class LeaseRecoveryRef:
    """Optional current lease/fence identity carried through a restart."""

    lease_id: str
    lease_generation: int
    fencing_token: str

    def __post_init__(self) -> None:
        _text(self.lease_id, "active_lease.lease_id")
        _positive_int(self.lease_generation, "active_lease.lease_generation")
        _text(self.fencing_token, "active_lease.fencing_token")

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "lease_generation": self.lease_generation,
            "fencing_token": self.fencing_token,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LeaseRecoveryRef":
        payload = _mapping(payload, "active_lease")
        _strict_fields(payload, {"lease_id", "lease_generation", "fencing_token"}, "active_lease")
        try:
            return cls(
                lease_id=payload["lease_id"],
                lease_generation=payload["lease_generation"],
                fencing_token=payload["fencing_token"],
            )
        except KeyError as exc:
            _fail("RECOVERY_BINDING_INVALID", "active_lease is missing a required field")
            raise AssertionError("_fail must raise") from exc


@dataclass(frozen=True, slots=True)
class ControllerRecoveryBinding:
    """Durable controller-side recovery identity and exact mailbox pointers."""

    run_id: str
    node_id: str
    controller_actor: str
    continuation: ControllerContinuation
    ledger_ref: RunLedgerRef
    controller_mailbox: MailboxRecoveryRef
    executor_mailbox: MailboxRecoveryRef
    exact_head_sha: str
    updated_at: str
    evidence_refs: tuple[str, ...] = ()
    normalized_result_ref: str | None = None
    active_lease: LeaseRecoveryRef | None = None

    def __post_init__(self) -> None:
        _text(self.run_id, "recovery.run_id")
        _text(self.node_id, "recovery.node_id")
        _text(self.controller_actor, "recovery.controller_actor")
        _text(self.exact_head_sha, "recovery.exact_head_sha")
        _text(self.updated_at, "recovery.updated_at")
        if not isinstance(self.continuation, ControllerContinuation):
            _fail("RECOVERY_BINDING_INVALID", "recovery.continuation is required")
        if not isinstance(self.ledger_ref, RunLedgerRef):
            _fail("RECOVERY_BINDING_INVALID", "recovery.ledger_ref is required")
        if not isinstance(self.controller_mailbox, MailboxRecoveryRef):
            _fail("RECOVERY_BINDING_INVALID", "recovery.controller_mailbox is required")
        if not isinstance(self.executor_mailbox, MailboxRecoveryRef):
            _fail("RECOVERY_BINDING_INVALID", "recovery.executor_mailbox is required")
        if self.run_id != self.continuation.run_id or self.ledger_ref.run_id != self.run_id:
            _fail("RECOVERY_RECONCILIATION_BLOCKED", "run identity differs across recovery surfaces")
        if self.exact_head_sha != self.continuation.exact_head_sha:
            _fail("RECOVERY_RECONCILIATION_BLOCKED", "exact head differs from continuation")
        if (
            self.controller_mailbox.actor != self.controller_actor
            or self.controller_mailbox.mailbox_ref != self.continuation.controller_mailbox_ref
            or self.controller_mailbox.cursor.last_seen_seq != self.continuation.controller_seq
            or self.controller_mailbox.target_seq != self.continuation.controller_seq
        ):
            _fail("RECOVERY_RECONCILIATION_BLOCKED", "Controller mailbox ref/cursor differs from continuation")
        if (
            self.executor_mailbox.actor != self.continuation.executor_actor
            or self.executor_mailbox.mailbox_ref != self.continuation.executor_mailbox_ref
            or self.executor_mailbox.cursor.last_seen_seq != self.continuation.last_seen_executor_seq
            or self.executor_mailbox.target_seq != self.continuation.expected_executor_seq
        ):
            _fail("RECOVERY_RECONCILIATION_BLOCKED", "Executor mailbox ref/cursor differs from continuation")
        if self.normalized_result_ref is not None:
            _text(self.normalized_result_ref, "recovery.normalized_result_ref")
        refs = tuple(self.evidence_refs)
        if any(not isinstance(ref, str) or not ref or "\x00" in ref for ref in refs):
            _fail("RECOVERY_BINDING_INVALID", "recovery.evidence_refs must contain safe non-empty refs")
        if len(set(refs)) != len(refs):
            _fail("RECOVERY_BINDING_INVALID", "recovery.evidence_refs must not contain duplicates")
        object.__setattr__(self, "evidence_refs", refs)
        if self.active_lease is not None and not isinstance(self.active_lease, LeaseRecoveryRef):
            _fail("RECOVERY_BINDING_INVALID", "recovery.active_lease is invalid")

    def _payload(self) -> dict[str, Any]:
        return {
            "protocol": CRASH_RECOVERY_PROTOCOL,
            "schema_version": CRASH_RECOVERY_SCHEMA_VERSION,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "controller_actor": self.controller_actor,
            "continuation": self.continuation.to_dict(),
            "ledger_ref": self.ledger_ref.to_dict(),
            "mailboxes": {
                "controller": self.controller_mailbox.to_dict(),
                "executor": self.executor_mailbox.to_dict(),
            },
            "exact_head_sha": self.exact_head_sha,
            "updated_at": self.updated_at,
            "evidence_refs": list(self.evidence_refs),
            "normalized_result_ref": self.normalized_result_ref,
            "active_lease": self.active_lease.to_dict() if self.active_lease else None,
        }

    @property
    def binding_digest(self) -> str:
        return canonical_digest(self._payload())

    @property
    def checkpoint_id(self) -> str:
        return self.continuation.checkpoint_id

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["binding_digest"] = self.binding_digest
        return payload

    def to_manifest(self, *, created_at: str | None = None) -> RunManifest:
        return RunManifest(
            run_id=self.run_id,
            manifest_kind=CRASH_RECOVERY_MANIFEST_KIND,
            schema_version=CRASH_RECOVERY_SCHEMA_VERSION,
            created_at=created_at or self.updated_at,
            updated_at=self.updated_at,
            metadata=self.to_dict(),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ControllerRecoveryBinding":
        payload = _mapping(payload, "recovery binding")
        allowed = {
            "protocol",
            "schema_version",
            "run_id",
            "node_id",
            "controller_actor",
            "continuation",
            "ledger_ref",
            "mailboxes",
            "exact_head_sha",
            "updated_at",
            "evidence_refs",
            "normalized_result_ref",
            "active_lease",
            "binding_digest",
        }
        _strict_fields(payload, allowed, "recovery binding")
        if payload.get("protocol") != CRASH_RECOVERY_PROTOCOL:
            _fail("RECOVERY_BINDING_INVALID", "unsupported crash-recovery protocol")
        if payload.get("schema_version") != CRASH_RECOVERY_SCHEMA_VERSION:
            _fail("RECOVERY_BINDING_INVALID", "unsupported crash-recovery schema version")
        continuation_payload = _mapping(payload.get("continuation"), "continuation")
        _strict_fields(continuation_payload, _CONTINUATION_FIELDS, "continuation")
        mailboxes = _mapping(payload.get("mailboxes"), "mailboxes")
        _strict_fields(mailboxes, {"controller", "executor"}, "mailboxes")
        evidence = payload.get("evidence_refs", ())
        if not isinstance(evidence, (list, tuple)):
            _fail("RECOVERY_BINDING_INVALID", "evidence_refs must be an array")
        try:
            binding = cls(
                run_id=payload["run_id"],
                node_id=payload["node_id"],
                controller_actor=payload["controller_actor"],
                continuation=ControllerContinuation.from_dict(dict(continuation_payload)),
                ledger_ref=RunLedgerRef.from_dict(_mapping(payload["ledger_ref"], "ledger_ref")),
                controller_mailbox=MailboxRecoveryRef.from_dict(
                    _mapping(mailboxes["controller"], "mailboxes.controller")
                ),
                executor_mailbox=MailboxRecoveryRef.from_dict(
                    _mapping(mailboxes["executor"], "mailboxes.executor")
                ),
                exact_head_sha=payload["exact_head_sha"],
                updated_at=payload["updated_at"],
                evidence_refs=tuple(evidence),
                normalized_result_ref=payload.get("normalized_result_ref"),
                active_lease=(
                    LeaseRecoveryRef.from_dict(_mapping(payload["active_lease"], "active_lease"))
                    if payload.get("active_lease") is not None
                    else None
                ),
            )
        except KeyError as exc:
            _fail("RECOVERY_BINDING_INVALID", "recovery binding is missing a required field")
            raise AssertionError("_fail must raise") from exc
        supplied_digest = payload.get("binding_digest")
        if supplied_digest != binding.binding_digest:
            _fail("RECOVERY_DIGEST_MISMATCH", "recovery binding digest differs from canonical bytes")
        return binding

    @classmethod
    def from_manifest(cls, manifest: RunManifest) -> "ControllerRecoveryBinding":
        if not isinstance(manifest, RunManifest):
            _fail("RECOVERY_BINDING_INVALID", "recovery manifest is invalid")
        if manifest.manifest_kind != CRASH_RECOVERY_MANIFEST_KIND:
            _fail("RECOVERY_BINDING_INVALID", "unexpected crash-recovery manifest kind")
        if manifest.schema_version != CRASH_RECOVERY_SCHEMA_VERSION:
            _fail("RECOVERY_BINDING_INVALID", "unsupported crash-recovery manifest version")
        binding = cls.from_dict(manifest.metadata)
        if binding.run_id != manifest.run_id:
            _fail("RECOVERY_RECONCILIATION_BLOCKED", "manifest and binding run IDs differ")
        return binding


class CanonicalMailboxReader(Protocol):
    """Minimal exact-read boundary for a canonical Controller mailbox."""

    def read_mailbox(self, mailbox_ref: str) -> str:
        ...


@dataclass(frozen=True, slots=True)
class ControllerRecoveryResult:
    """Restart result containing only canonical mailbox/ledger evidence."""

    binding: ControllerRecoveryBinding
    controller_envelope: A2AEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ControllerRecoveryBinding):
            _fail("RECOVERY_BINDING_INVALID", "recovery result binding is invalid")
        if not isinstance(self.controller_envelope, A2AEnvelope):
            _fail("RECOVERY_BINDING_INVALID", "recovery result envelope is invalid")

    @property
    def next_action(self) -> str:
        return self.binding.continuation.next_action

    @property
    def recovery_digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": CRASH_RECOVERY_PROTOCOL,
            "binding": self.binding.to_dict(),
            "controller_envelope": self.controller_envelope.to_dict(),
            "next_action": self.next_action,
            "executor_mailbox_ref": self.binding.executor_mailbox.mailbox_ref,
            "executor_target_seq": self.binding.executor_mailbox.target_seq,
        }


def persist_recovery_binding(
    store: ContinuationStore,
    binding: ControllerRecoveryBinding,
) -> ControllerRecoveryBinding:
    """Persist continuation + recovery manifest with exact readback."""

    if not isinstance(binding, ControllerRecoveryBinding):
        _fail("RECOVERY_BINDING_INVALID", "persist requires a ControllerRecoveryBinding")
    existing_manifest = store.load_manifest(binding.run_id, CRASH_RECOVERY_MANIFEST_KIND)
    if existing_manifest is not None:
        existing = ControllerRecoveryBinding.from_manifest(existing_manifest)
        if existing != binding:
            _fail("RECOVERY_RECONCILIATION_BLOCKED", "existing recovery manifest conflicts with binding")
        durable = recover_continuation(store, binding.run_id)
        if durable != binding.continuation:
            _fail("RECOVERY_RECONCILIATION_BLOCKED", "existing continuation conflicts with binding")
        return binding

    durable = recover_continuation(store, binding.run_id)
    if durable is not None and durable != binding.continuation:
        _fail("RECOVERY_RECONCILIATION_BLOCKED", "existing continuation conflicts with binding")
    persist_continuation(store, binding.continuation)
    store.save_manifest(binding.to_manifest())
    recovered = recover_recovery_binding(store, binding.run_id)
    if recovered != binding:
        _fail("RECOVERY_DIGEST_MISMATCH", "recovery manifest exact readback differs from binding")
    return binding


def recover_recovery_binding(
    store: ContinuationStore,
    run_id: str,
) -> ControllerRecoveryBinding:
    """Read the Run Ledger recovery manifest and reconcile its continuation."""

    _text(run_id, "run_id")
    manifest = store.load_manifest(run_id, CRASH_RECOVERY_MANIFEST_KIND)
    if manifest is None:
        _fail("RECOVERY_RECONCILIATION_BLOCKED", "crash-recovery manifest is missing")
    try:
        binding = ControllerRecoveryBinding.from_manifest(manifest)
    except CrashRecoveryError:
        raise
    except Exception as exc:
        _fail("RECOVERY_RECONCILIATION_BLOCKED", f"recovery manifest cannot be read: {exc}")
    durable = recover_continuation(store, run_id)
    if durable is None or durable != binding.continuation:
        _fail("RECOVERY_RECONCILIATION_BLOCKED", "Run Ledger continuation does not match recovery manifest")
    return binding


def _mailbox_failure(message: str, exc: Exception | None = None) -> NoReturn:
    error = CrashRecoveryError("RECOVERY_RECONCILIATION_BLOCKED", message)
    if exc is not None:
        error.__cause__ = exc
    raise error


def recover_controller_after_restart(
    store: ContinuationStore,
    mailbox_reader: CanonicalMailboxReader,
    *,
    run_id: str,
    controller_actor: str,
) -> ControllerRecoveryResult:
    """Recover from Run Ledger + exact Controller mailbox; never from chat/Slack."""

    binding = recover_recovery_binding(store, run_id)
    if controller_actor != binding.controller_actor:
        _mailbox_failure("Controller actor differs from durable recovery binding")
    if not callable(getattr(mailbox_reader, "read_mailbox", None)):
        _mailbox_failure("canonical mailbox reader is unavailable")
    try:
        body = mailbox_reader.read_mailbox(binding.controller_mailbox.mailbox_ref)
        envelope = parse_mailbox_comment(body)
        embedded = continuation_from_envelope(envelope)
    except Exception as exc:
        _mailbox_failure("canonical Controller mailbox readback is invalid", exc)
    if embedded != binding.continuation:
        _mailbox_failure("canonical mailbox continuation differs from durable recovery binding")
    if (
        envelope.run_id != binding.run_id
        or envelope.node_id != binding.node_id
        or envelope.sender != binding.controller_actor
        or envelope.recipient != binding.continuation.executor_actor
        or envelope.seq != binding.controller_mailbox.target_seq
        or envelope.state.get("head_sha") != binding.exact_head_sha
    ):
        _mailbox_failure("canonical mailbox identity/ref/sequence differs from durable recovery binding")
    return ControllerRecoveryResult(binding=binding, controller_envelope=envelope)


__all__ = [
    "CRASH_RECOVERY_MANIFEST_KIND",
    "CRASH_RECOVERY_PROTOCOL",
    "CRASH_RECOVERY_SCHEMA_VERSION",
    "CanonicalMailboxReader",
    "ControllerRecoveryBinding",
    "ControllerRecoveryResult",
    "CrashRecoveryError",
    "LeaseRecoveryRef",
    "MailboxRecoveryRef",
    "RunLedgerRef",
    "persist_recovery_binding",
    "recover_controller_after_restart",
    "recover_recovery_binding",
]
