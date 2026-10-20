"""Bounded, inert-by-default Hermes host integration.

Local receipts are host evidence, never canonical mailbox records or authority.
All authenticated reads, native admission and delivery are injected host ports.
This module neither registers a scheduler nor imports a cross-repository runtime.
The sidecar outbox is deliberately not WakeupOutbox: that protected dispatcher
requires a real DispatchCommitted receipt. Native communication must never
fabricate such a receipt or silently migrate the existing typed dispatch lane.
Provider qualification, authentication, current hold/lease/fence and native
boundary validation remain obligations of the injected ports, not these models.
"""
from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.communication_v2 import parse
from taskcontroller.interaction.mailbox_repository import MailboxActorCursor
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest


@dataclass(frozen=True)
class ObserverBinding:
    controller_ref: str
    executor_ref: str
    continuation_ref: str
    checkpoint_digest: str
    node_id: str
    exact_head_sha: str
    interval_seconds: float
    max_reads: int


@dataclass(frozen=True)
class UnlockDecision:
    run_id: str
    task_id: str
    session_id: str
    correlation_id: str
    command_digest: str
    authority_ref: str


@dataclass(frozen=True)
class VerifiedBoundary:
    """Native validator output; the host does not derive lifecycle/deadlock truth."""
    run_id: str
    task_id: str
    kind: str
    evidence_ref: str
    evidence_digest: str
    blocker_fingerprint: str
    owner: str
    completed_recovery: bool
    legal_next: bool


@dataclass(frozen=True)
class GraphBinding:
    repository_path: str
    exact_head_sha: str
    plan_path: str
    plan_digest: str
    max_steps: int = 16


@dataclass(frozen=True)
class WorkAdmission:
    """Receipt from the owning native/protected validator, not host-issued rights."""
    run_id: str
    task_id: str
    session_id: str
    agent_instance: str
    source_ref: str
    command_digest: str
    authority_ref: str
    protected_event_digest: str | None = None
    checkpoint_digest: str | None = None


@dataclass(frozen=True)
class HostBinding:
    run_id: str
    task_id: str
    session_id: str
    agent_instance: str
    actor: str
    peer_actor: str
    thread_url: str
    source_ref: str


@dataclass(frozen=True)
class AuthenticatedComment:
    """actor must come from the authenticated connector, not Markdown from:."""
    url: str
    body: str
    actor: str


def text_digest(body: str) -> str:
    """Transport content pin for communication only, not machine authority."""
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def serialized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self.writer():
            return method(self, *args, **kwargs)
    return guarded


class HermesGraphHost:
    def __init__(self, db_path: str | Path, binding: HostBinding, *, comments):
        self.binding = binding
        self.comments = comments
        self.db_path = Path(db_path).resolve()
        self.db = sqlite3.connect(self.db_path)
        with self.writer():
            self.db.execute("CREATE TABLE IF NOT EXISTS binding (body TEXT NOT NULL)")
            pin = json.dumps(asdict(binding), sort_keys=True)
            old = self.db.execute("SELECT body FROM binding").fetchone()
            if old and old[0] != pin:
                self.db.close()
                raise TaskControllerValidationError("HOST_BINDING_MISMATCH")
            if not old:
                self.db.execute("INSERT INTO binding VALUES (?)", (pin,))
            self.db.execute("CREATE TABLE IF NOT EXISTS receipts (url TEXT PRIMARY KEY, body TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, body TEXT NOT NULL)")
            self.db.commit()

    @contextmanager
    def writer(self):
        # Host-local serialization only; NOT distributed GitHub CAS or a lease.
        with self.db_path.with_suffix(".lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise TaskControllerValidationError("HOST_WRITER_BUSY") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def close(self):
        self.db.close()

    def receipts(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT body FROM receipts ORDER BY rowid")]

    @serialized
    def consume_communication(self, url: str, *, expected_digest: str, run_hold: bool = False):
        return self._communication(url, expected_digest=expected_digest, run_hold=run_hold)

    @serialized
    def record_posted(self, url: str, *, expected_digest: str, run_hold: bool = False):
        """Exact-read an already posted own message; never writes GitHub or implies receiver ACK."""
        return self._communication(url, expected_digest=expected_digest, run_hold=run_hold, posted=True)

    def _communication(self, url: str, *, expected_digest: str, run_hold=False, posted=False, accept=None):
        if run_hold:
            raise TaskControllerValidationError("RUN_HOLD")
        if not url.startswith(self.binding.thread_url + "#issuecomment-") or not url.removeprefix(self.binding.thread_url + "#issuecomment-").isdigit():
            raise TaskControllerValidationError("COMMUNICATION_THREAD_MISMATCH")
        comment = self.comments.exact_read(url)
        message = parse(comment.body)
        if message is None or text_digest(comment.body) != expected_digest:
            raise TaskControllerValidationError("COMMUNICATION_DIGEST_MISMATCH")
        expected_actor = self.binding.actor if posted else self.binding.peer_actor
        expected_recipient = self.binding.peer_actor if posted else self.binding.actor
        if (comment.url != url or comment.actor != expected_actor
                or message.sender != comment.actor or message.run != self.binding.run_id
                or message.recipient != expected_recipient or message.source_ref != self.binding.source_ref):
            raise TaskControllerValidationError("COMMUNICATION_BINDING_MISMATCH")
        if accept is not None:
            accept(message)
        old = self.db.execute("SELECT body FROM receipts WHERE url=?", (url,)).fetchone()
        if old:
            receipt = json.loads(old[0])
            if receipt["digest"] != expected_digest:
                raise TaskControllerValidationError("COMMUNICATION_DIGEST_MISMATCH")
            return receipt
        latest = self.db.execute("SELECT body FROM receipts ORDER BY rowid DESC LIMIT 1").fetchone()
        previous_seq = json.loads(latest[0])["seq"] if latest else 0
        if message.seq != previous_seq + 1:
            raise TaskControllerValidationError("COMMUNICATION_SEQUENCE_GAP")
        receipt = dict(asdict(self.binding), url=url, digest=expected_digest,
                       actor=comment.actor, seq=message.seq, kind=message.kind, stream="communication/v2",
                       status="POSTED_NOT_CONSUMED" if posted else "CONSUMED")
        self.db.execute("INSERT INTO receipts VALUES (?,?)", (url, json.dumps(receipt, sort_keys=True)))
        self.db.commit()
        return receipt

    def _get(self, key, default=None):
        row = self.db.execute("SELECT body FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _put(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value, sort_keys=True, allow_nan=False)))
        self.db.commit()

    @serialized
    def observe(self, source, config: ObserverBinding, *, enabled=False, now: float,
                run_hold=False, user_pause=False):
        if not enabled or run_hold or user_pause:
            return ()
        if config.interval_seconds <= 0 or type(config.max_reads) is not int or not 5 <= config.max_reads <= 1000:
            raise TaskControllerValidationError("OBSERVER_BOUNDS_INVALID")
        pin = asdict(config)
        old = self._get("observer_binding")
        if old is not None and old != pin:
            raise TaskControllerValidationError("OBSERVER_BINDING_MISMATCH")
        self._put("observer_binding", pin)
        last = self._get("observer_last")
        reads = self._get("observer_reads", 0)
        if (last is not None and now - last < config.interval_seconds) or reads + 3 > config.max_reads:
            return ()
        self._put("observer_last", now)

        def read(method, *args):
            count = self._get("observer_reads", 0)
            if count >= config.max_reads:
                raise TaskControllerValidationError("OBSERVER_READ_BUDGET")
            self._put("observer_reads", count + 1)
            return method(*args)

        changed = []
        cursors = []
        for namespace, ref, actor in (("controller", config.controller_ref, self.binding.peer_actor),
                                      ("executor", config.executor_ref, self.binding.actor)):
            cursor = read(source.read_cursor, ref, self.binding.run_id, config.node_id, namespace)
            if (cursor.mailbox_ref, cursor.run_id, cursor.node_id, cursor.actor_namespace) != (
                    ref, self.binding.run_id, config.node_id, namespace):
                raise TaskControllerValidationError("OBSERVER_CURSOR_MISMATCH")
            previous = self._get("observed:" + namespace)
            if previous == cursor.to_dict():
                continue
            if previous and cursor.last_event_seq <= previous["last_event_seq"]:
                raise TaskControllerValidationError("OBSERVER_CURSOR_REGRESSION")
            if cursor.last_event_seq >= 0:
                event = read(source.read_event, ref, cursor.last_event_id)
                envelope = V2MailboxEnvelope.from_dict(event.envelope.to_dict())
                # Current producer cursor must equal this exact event, not any historical event.
                if (cursor.observe(event) != cursor or envelope.to_dict()["producer"]["actor_id"] != actor
                        or canonical_digest(event._body()) != event.event_digest
                        or envelope.digest() != event.envelope_digest):
                    raise TaskControllerValidationError("OBSERVER_EVENT_MISMATCH")
                changed.append(event)
            cursors.append((namespace, cursor))
        continuation = read(source.read_continuation, config.continuation_ref)
        if (continuation.checkpoint_id != config.checkpoint_digest
                or continuation.run_id != self.binding.run_id
                or continuation.controller_mailbox_ref != config.controller_ref
                or continuation.executor_mailbox_ref != config.executor_ref
                or continuation.exact_head_sha != config.exact_head_sha):
            raise TaskControllerValidationError("OBSERVER_CONTINUATION_MISMATCH")
        for namespace, cursor in cursors:
            self._put("observed:" + namespace, cursor.to_dict())
        self._put("observed_continuation", {"ref": config.continuation_ref, "digest": continuation.checkpoint_id})
        return tuple(changed)

    @serialized
    def invoke_work(self, receipt, *, backend, graph: GraphBinding, admit,
                    event=None, continuation=None, input_state=None, run_hold=False, user_pause=False):
        if run_hold or user_pause:
            raise TaskControllerValidationError("RUN_HOLD")
        typed = self._get("typed:" + receipt["digest"])
        row = self.db.execute("SELECT body FROM receipts WHERE url=?", (receipt["url"],)).fetchone()
        communication = json.loads(row[0]) if row else None
        if ((receipt != communication and receipt != typed) or receipt["status"] != "CONSUMED"
                or receipt["kind"] not in {"COMMAND", "execution_request"}):
            raise TaskControllerValidationError("WORK_RECEIPT_INVALID")
        key = "work:" + receipt["digest"]
        old = self._get(key)
        if old:
            return old  # including IN_FLIGHT/UNKNOWN: never blindly replay a crash
        admission = admit(self.binding, receipt, event, continuation)
        self._validate_admission(admission, receipt, event, continuation)
        if typed is not None:
            if event is None or continuation is None:
                raise TaskControllerValidationError("PROTECTED_ADMISSION_REQUIRED")
            if (receipt["event_id"] != event.event_id or receipt["event_digest"] != event.event_digest
                    or receipt["digest"] != event.envelope_digest
                    or receipt["checkpoint_digest"] != continuation.checkpoint_id):
                raise TaskControllerValidationError("PROTECTED_RECEIPT_MISMATCH")
        repo = Path(graph.repository_path)
        plan = Path(graph.plan_path)
        if not repo.is_absolute() or not plan.is_absolute() or not plan.resolve().is_relative_to(repo.resolve()):
            raise TaskControllerValidationError("GRAPH_SOURCE_INVALID")
        actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10).strip()
        if actual != graph.exact_head_sha or text_digest(plan.read_text(encoding="utf-8")) != graph.plan_digest:
            raise TaskControllerValidationError("GRAPH_SOURCE_DRIFT")
        if type(graph.max_steps) is not int or not 1 <= graph.max_steps <= 128:
            raise TaskControllerValidationError("GRAPH_BOUNDS_INVALID")
        module_path = inspect.getsourcefile(type(backend))
        if module_path is None:
            raise TaskControllerValidationError("GRAPH_BACKEND_UNVERIFIED")
        proof = dict(asdict(graph), backend_class=type(backend).__name__,
                     backend_module=type(backend).__module__, backend_module_path=module_path,
                     backend_module_digest="sha256:" + hashlib.sha256(Path(module_path).read_bytes()).hexdigest())
        work = {"status": "IN_FLIGHT", "command_url": receipt["url"], "command_digest": receipt["digest"],
                    "admission": asdict(admission), "load_proof": proof}
        self._put(key, work)
        try:
            # Native graph input is opaque to the host; no local DAG/RunState is invented.
            state = input_state if input_state is not None else {"run_id": self.binding.run_id, "task_id": self.binding.task_id}
            result = backend.invoke(state,
                                    config={"configurable": {"thread_id": self.binding.run_id + ":" + self.binding.task_id,
                                                              "command_ref": receipt["url"], "command_digest": receipt["digest"]},
                                            "recursion_limit": graph.max_steps})
            work.update(status="COMPLETED", result=result)
            self._put(key, work)
        except Exception:
            work["status"] = "UNKNOWN"
            self._put(key, work)
            raise
        return work

    @serialized
    def prepare_wake(self, work, boundary, *, verify, run_hold=False, user_pause=False):
        if run_hold or user_pause:
            raise TaskControllerValidationError("RUN_HOLD")
        durable = self._get("work:" + work["command_digest"])
        if durable != work or work["status"] != "COMPLETED":
            raise TaskControllerValidationError("WAKE_WORK_UNVERIFIED")
        checked = verify(boundary, work)
        if not isinstance(checked, VerifiedBoundary) or (checked.run_id, checked.task_id) != (
                self.binding.run_id, self.binding.task_id):
            raise TaskControllerValidationError("WAKE_BOUNDARY_UNVERIFIED")
        if checked.kind not in {"TASK_TERMINAL", "DEADLOCK_UNLOCK"}:
            return None  # progress, timer and observer changes never wake GPT
        if checked.kind == "DEADLOCK_UNLOCK" and (
                not checked.completed_recovery or checked.legal_next or checked.owner != self.binding.peer_actor):
            return None
        if checked.evidence_digest != canonical_digest(work["result"]):
            raise TaskControllerValidationError("WAKE_EVIDENCE_MISMATCH")
        command = self._get("typed:" + work["command_digest"])
        if command is None:
            row = self.db.execute("SELECT body FROM receipts WHERE url=?", (work["command_url"],)).fetchone()
            command = json.loads(row[0]) if row else None
        if command is None or command["digest"] != work["command_digest"]:
            raise TaskControllerValidationError("WAKE_WORK_UNVERIFIED")
        consumed = command["seq"]
        stream = command["stream"]
        fingerprint = canonical_digest({"run": self.binding.run_id, "task": self.binding.task_id,
                                             "thread": self.binding.thread_url, "kind": checked.kind,
                                             "consumed_stream": stream, "consumed_command_seq": consumed,
                                             "blocker": work["command_digest"] if checked.kind == "TASK_TERMINAL" else checked.blocker_fingerprint})
        correlation = "host-wake:" + fingerprint.removeprefix("sha256:")
        key = "outbox:" + correlation
        old = self._get(key)
        if old:
            return old
        pointer = {"run_id": self.binding.run_id, "task_id": self.binding.task_id,
                       "thread_url": self.binding.thread_url, "recipient": self.binding.peer_actor,
                       "evidence_ref": checked.evidence_ref, "evidence_digest": checked.evidence_digest,
                       "correlation_id": correlation}
        intent = {"pointer": pointer, "state": "PENDING", "fingerprint": fingerprint,
                      "kind": checked.kind, "consumed_stream": stream, "consumed_command_seq": consumed,
                      "task_status": "BLOCKED_PENDING_CONTROLLER" if checked.kind == "DEADLOCK_UNLOCK" else "TASK_TERMINAL"}
        self._put(key, intent)
        return intent

    @serialized
    def deliver_wake(self, correlation, transport, *, gpt_state, run_hold=False, user_pause=False):
        if run_hold or user_pause:
            raise TaskControllerValidationError("RUN_HOLD")
        key = "outbox:" + correlation
        intent = self._get(key)
        if not intent:
            raise TaskControllerValidationError("WAKE_UNKNOWN_CORRELATION")
        if intent["state"] in {"DELIVERED", "RESOLVED"}:
            return intent
        active = self._get("pending_correlation")
        if active is not None and active != correlation:
            return intent
        self._put("pending_correlation", correlation)
        if gpt_state != "GPT_IDLE":
            return intent  # BUSY and UNVERIFIED never open another GPT turn
        if intent["state"] == "PENDING":
            intent["state"] = "IN_FLIGHT"
            self._put(key, intent)
            try:
                transport.send(dict(intent["pointer"]))
            except Exception:
                intent["state"] = "UNKNOWN"
                self._put(key, intent)
                raise
        # Exact transport readback, not send success, proves delivery only.
        receipt = transport.readback(correlation)
        if receipt is not None and receipt.get("delivery_ref") and all(
                receipt.get(k) == v for k, v in intent["pointer"].items()):
            intent.update(state="DELIVERED", delivery_receipt=receipt)
            self._put(key, intent)
        return intent

    @serialized
    def consume_unlock(self, url, *, expected_digest, correlation, verify, run_hold=False, user_pause=False):
        if run_hold or user_pause:
            raise TaskControllerValidationError("RUN_HOLD")
        intent = self._get("outbox:" + correlation)
        if not intent or intent["kind"] != "DEADLOCK_UNLOCK":
            raise TaskControllerValidationError("UNLOCK_CORRELATION_INVALID")
        def accept(message):
            if message.kind != "COMMAND" or message.reply_to != intent["pointer"]["evidence_ref"]:
                raise TaskControllerValidationError("UNLOCK_REPLY_MISMATCH")
            decision = verify(message, self.binding, intent)
            if not isinstance(decision, UnlockDecision) or (
                    decision.run_id, decision.task_id, decision.session_id, decision.correlation_id,
                    decision.command_digest) != (self.binding.run_id, self.binding.task_id,
                    self.binding.session_id, correlation, expected_digest):
                raise TaskControllerValidationError("UNLOCK_ADMISSION_INVALID")
        receipt = self._communication(url, expected_digest=expected_digest, accept=accept)
        unlocked = {"run_id": self.binding.run_id, "task_id": self.binding.task_id, "task_status": "RUNNING",
                        "command_receipt": receipt, "correlation_id": correlation}
        intent.update(state="RESOLVED", task_status="RUNNING", unlock_receipt=unlocked)
        self._put("outbox:" + correlation, intent)
        if self._get("pending_correlation") == correlation:
            self._put("pending_correlation", None)
        return unlocked

    def _validate_admission(self, admission, receipt, event=None, continuation=None):
        if not isinstance(admission, WorkAdmission) or not admission.authority_ref.strip() or (
                admission.run_id, admission.task_id, admission.session_id, admission.agent_instance,
                admission.source_ref, admission.command_digest) != (
                self.binding.run_id, self.binding.task_id, self.binding.session_id,
                self.binding.agent_instance, self.binding.source_ref, receipt["digest"]):
            raise TaskControllerValidationError("WORK_ADMISSION_INVALID")
        if event is not None and (continuation is None or admission.protected_event_digest != event.event_digest
                                  or admission.checkpoint_digest != continuation.checkpoint_id):
            raise TaskControllerValidationError("PROTECTED_ADMISSION_REQUIRED")

    @serialized
    def consume_typed(self, source, config: ObserverBinding, *, event_id, expected_digest, admit,
                      run_hold=False, user_pause=False):
        if run_hold or user_pause:
            raise TaskControllerValidationError("RUN_HOLD")
        cursor = source.read_cursor(config.controller_ref, self.binding.run_id, config.node_id, "controller")
        event = source.read_event(config.controller_ref, event_id)
        envelope = V2MailboxEnvelope.from_dict(event.envelope.to_dict())
        payload = envelope.to_dict()
        if (expected_digest != event.event_digest or canonical_digest(event._body()) != event.event_digest
                or envelope.digest() != event.envelope_digest or cursor.observe(event) != cursor
                or payload["producer"]["actor_id"] != self.binding.peer_actor
                or payload["direction"] != "controller_to_executor" or payload["message_type"] != "execution_request"
                or payload["recipient"]["agent_instance"] != self.binding.agent_instance):
            raise TaskControllerValidationError("TYPED_COMMAND_INVALID")
        checkpoint = source.read_continuation(config.continuation_ref)
        if (checkpoint.checkpoint_id != config.checkpoint_digest or checkpoint.run_id != self.binding.run_id
                or checkpoint.exact_head_sha != config.exact_head_sha
                or checkpoint.controller_mailbox_ref != config.controller_ref
                or checkpoint.executor_mailbox_ref != config.executor_ref):
            raise TaskControllerValidationError("TYPED_CONTINUATION_INVALID")
        receipt = dict(asdict(self.binding), stream="mailbox/v2", status="CONSUMED",
                       kind="execution_request", url=config.controller_ref, digest=event.envelope_digest,
                       event_id=event.event_id, event_seq=event.event_seq, seq=event.logical_seq,
                       event_digest=event.event_digest, continuation_ref=config.continuation_ref,
                       checkpoint_digest=checkpoint.checkpoint_id)
        self._validate_admission(admit(self.binding, receipt, event, checkpoint), receipt, event, checkpoint)
        old = self._get("typed:" + receipt["digest"])
        if old:
            if old != receipt:
                raise TaskControllerValidationError("TYPED_RECEIPT_MISMATCH")
            return old
        previous = self._get("consumed_controller")
        current = MailboxActorCursor.from_dict(previous) if previous else MailboxActorCursor.initial(
            config.controller_ref, run_id=self.binding.run_id, node_id=config.node_id, actor_namespace="controller")
        advanced = current.observe(event)
        with self.db:
            for key, value in (("typed:" + receipt["digest"], receipt), ("consumed_controller", advanced.to_dict())):
                self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value, sort_keys=True)))
        return receipt
