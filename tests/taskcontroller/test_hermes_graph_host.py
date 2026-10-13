"""Synthetic host contract evidence, NOT live Desktop qualification."""
import hashlib
import importlib
import importlib.util
from dataclasses import replace

import pytest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.communication_v2 import CommunicationV2


def api():
    name = "taskcontroller.runtime.hermes_graph_host"
    assert importlib.util.find_spec(name) is not None, "bounded host adapter missing"
    return importlib.import_module(name)


def binding():
    return api().HostBinding(
        run_id="synthetic-run", task_id="synthetic-task", session_id="synthetic-session",
        agent_instance="synthetic-hermes", actor="Hermes", peer_actor="GPT",
        thread_url="https://github.com/test/repo/issues/162",
        source_ref="github://test/repo@" + "a" * 40,
    )


def command(seq=1, **kwargs):
    values = {"run": "synthetic-run", "seq": seq, "sender": "GPT", "recipient": "Hermes",
                  "kind": "COMMAND", "goal": "Synthetic task", "next_action": "Test bounded source",
                  "source_ref": "github://test/repo@" + "a" * 40}
    values.update(kwargs)
    return CommunicationV2(**values).render()


def digest(body):
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()


class Comments:
    def __init__(self, body=None, actor="GPT"):
        self.body = body or command()
        self.actor = actor
        self.reads = []

    def exact_read(self, url):
        self.reads.append(url)
        return api().AuthenticatedComment(url=url, body=self.body, actor=self.actor)


def host(tmp_path, comments=None, **kwargs):
    return api().HermesGraphHost(tmp_path / "host.sqlite", binding(),
                                 comments=comments or Comments(), **kwargs)


def test_command_consumption_receipt_is_exact_durable_and_not_machine_seq(tmp_path):
    comments = Comments()
    adapter = host(tmp_path, comments)
    url = binding().thread_url + "#issuecomment-1"
    receipt = adapter.consume_communication(url, expected_digest=digest(comments.body))
    assert receipt["status"] == "CONSUMED"
    assert {k: receipt[k] for k in ("url", "digest", "actor", "session_id", "run_id", "seq")} == {
        "url": url, "digest": digest(comments.body), "actor": "GPT",
        "session_id": "synthetic-session", "run_id": "synthetic-run", "seq": 1,
    }
    assert receipt["agent_instance"] == "synthetic-hermes"
    adapter.close()
    reopened = host(tmp_path, comments)
    assert reopened.consume_communication(url, expected_digest=digest(comments.body)) == receipt
    assert reopened.receipts() == [receipt]
    assert "controller_event_seq" not in receipt
    reopened.close()


@pytest.mark.parametrize("bad", ["run", "actor", "digest", "thread", "recipient", "source", "gap", "hold"])
def test_invalid_communication_and_run_hold_fail_closed(tmp_path, bad):
    comments = Comments()
    url = binding().thread_url + "#issuecomment-1"
    if bad == "run":
        comments.body = command(run="wrong-run")
    elif bad == "actor":
        comments.actor = "impostor"
    elif bad == "thread":
        url = "https://github.com/test/repo/issues/999#issuecomment-1"
    elif bad == "recipient":
        comments.body = command(recipient="Other")
    elif bad == "source":
        comments.body = command(source_ref="none")
    elif bad == "gap":
        comments.body = command(seq=2)
    adapter = host(tmp_path, comments)
    expected = digest(comments.body) if bad != "digest" else "sha256:" + "f" * 64
    with pytest.raises(Exception, match="COMMUNICATION_|RUN_HOLD"):
        adapter.consume_communication(url, expected_digest=expected, run_hold=bad == "hold")
    assert adapter.receipts() == []
    adapter.close()


def test_overlapping_writer_and_rebound_store_are_rejected(tmp_path):
    first = host(tmp_path)
    second = host(tmp_path)
    assert hasattr(first, "writer"), "serialized writer guard missing"
    with first.writer(), pytest.raises(Exception, match="HOST_WRITER_BUSY"):
        second.consume_communication(binding().thread_url + "#issuecomment-1",
                                     expected_digest=digest(command()))
    first.close()
    second.close()
    with pytest.raises(Exception, match="HOST_BINDING_MISMATCH"):
        api().HermesGraphHost(tmp_path / "host.sqlite", replace(binding(), session_id="other"),
                              comments=Comments())


class ExactSource:
    """Synthetic exact port backed by the repository's real in-memory materializer."""
    def __init__(self):
        import copy
        import json
        from pathlib import Path

        from taskcontroller.interaction.continuation import ControllerContinuation
        from taskcontroller.interaction.mailbox_repository import (
            InMemoryMailboxRepository,
            MailboxActorCursor,
        )
        from taskcontroller.interaction.mailbox_v2 import (
            V2MailboxEnvelope,
            canonical_digest,
        )
        self.repo = InMemoryMailboxRepository()
        self.calls = []
        self.events = {}
        fixture = json.loads((Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json").read_text())
        for name in ("controller", "executor"):
            payload = copy.deepcopy(fixture["cases"]["execution_request"])
            payload["run_id"] = payload["execution_identity"]["run_id"] = "synthetic-run"
            payload["seq"] = 1
            payload["recipient"]["agent_instance"] = "synthetic-hermes"
            payload["producer"].update(namespace=name, actor_id="GPT" if name == "controller" else "Hermes", role=name)
            if name == "executor":
                payload["direction"] = "executor_to_controller"
            payload["digest"] = canonical_digest(payload)
            env = V2MailboxEnvelope.from_dict(payload)
            ref = "github://test/repo/issues/162#" + name
            self.repo.write(ref, -1, env)
            event = self.repo.read(ref).events[-1]
            cursor = MailboxActorCursor.initial(ref, run_id="synthetic-run", node_id="node-1", actor_namespace=name).observe(event)
            self.repo.acknowledge_cursor(cursor)
            self.events[name] = event
        self.continuation = ControllerContinuation(
            run_id="synthetic-run", controller_epoch=1, phase="WAIT_EXECUTOR", status="ACTIVE",
            next_action="AWAIT_EXECUTOR_EVENT", controller_mailbox_ref="github://test/repo/issues/162#controller",
            controller_seq=1, executor_actor="Hermes", executor_mailbox_ref="github://test/repo/issues/162#executor",
            expected_executor_seq=2, last_seen_executor_seq=1, wakeup_binding="synthetic",
            exact_head_sha="a" * 40, updated_at="2026-10-14T00:00:00Z")

    def read_cursor(self, ref, run, node, actor):
        self.calls.append(("cursor", ref))
        return self.repo.read_cursor(ref, run, node, actor)

    def read_event(self, ref, event_id):
        self.calls.append(("event", ref, event_id))
        return next(e for e in self.repo.read(ref).events if e.event_id == event_id)

    def read_continuation(self, ref):
        self.calls.append(("continuation", ref))
        return self.continuation


def observer_binding(source):
    return api().ObserverBinding(
        controller_ref=source.continuation.controller_mailbox_ref,
        executor_ref=source.continuation.executor_mailbox_ref,
        continuation_ref="synthetic://continuation/1", checkpoint_digest=source.continuation.checkpoint_id,
        node_id="node-1", exact_head_sha="a" * 40,
        interval_seconds=10, max_reads=8,
    )


def test_observer_exact_ce_and_continuation_is_disabled_bounded_and_not_consumption(tmp_path):
    source = ExactSource()
    adapter = host(tmp_path)
    assert hasattr(adapter, "observe"), "qualified observer missing"
    config = observer_binding(source)
    assert adapter.observe(source, config, now=0) == ()  # disabled by default
    assert source.calls == []
    events = adapter.observe(source, config, enabled=True, now=0)
    assert events == (source.events["controller"], source.events["executor"])
    assert len(source.calls) == 5  # two cursors, two exact events, one continuation
    assert adapter.receipts() == []
    assert adapter.observe(source, config, enabled=True, now=1) == ()
    assert len(source.calls) == 5
    assert adapter.observe(source, config, enabled=True, now=10) == ()
    assert len(source.calls) == 8
    assert adapter.observe(source, config, enabled=True, now=20) == ()  # read budget exhausted
    assert len(source.calls) == 8
    adapter.close()



def real_backend():
    from typing import TypedDict
    graph_api = pytest.importorskip("langgraph.graph", reason="optional real LangGraph synthetic harness dependency")
    StateGraph, START, END = graph_api.StateGraph, graph_api.START, graph_api.END
    class State(TypedDict):
        run_id: str
        task_id: str
        steps: int
    graph = StateGraph(State)
    graph.add_node("bounded_work", lambda state: {"steps": state.get("steps", 0) + 1})
    graph.add_edge(START, "bounded_work")
    graph.add_edge("bounded_work", END)
    return graph.compile()


def graph_binding():
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    plan = repo / "tests/taskcontroller/fixtures/v2_contract_fixtures.json"
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return api().GraphBinding(repository_path=str(repo), exact_head_sha=head,
                              plan_path=str(plan), plan_digest=digest(plan.read_text()), max_steps=4)


def native_admit(bound, receipt, event, continuation):
    return api().WorkAdmission(run_id=bound.run_id, task_id=bound.task_id,
                               session_id=bound.session_id, agent_instance=bound.agent_instance,
                               source_ref=bound.source_ref, command_digest=receipt["digest"],
                               authority_ref="synthetic://native-engineering-admission")


def test_real_injected_langgraph_invokes_once_and_has_exact_load_pins(tmp_path):
    adapter = host(tmp_path)
    assert hasattr(adapter, "invoke_work"), "injected graph invocation missing"
    url = binding().thread_url + "#issuecomment-1"
    receipt = adapter.consume_communication(url, expected_digest=digest(command()))
    backend = real_backend()
    result = adapter.invoke_work(receipt, backend=backend, graph=graph_binding(), admit=native_admit)
    assert result["status"] == "COMPLETED"
    assert result["result"] == {"run_id": "synthetic-run", "task_id": "synthetic-task", "steps": 1}
    assert result["load_proof"]["exact_head_sha"] == graph_binding().exact_head_sha
    adapter.close()
    reopened = host(tmp_path)
    assert reopened.invoke_work(receipt, backend=backend, graph=graph_binding(), admit=native_admit) == result
    reopened.close()



def completed_work(adapter):
    receipt = adapter.consume_communication(binding().thread_url + "#issuecomment-1", expected_digest=digest(command()))
    return adapter.invoke_work(receipt, backend=real_backend(), graph=graph_binding(), admit=native_admit)


def boundary(work, **changes):
    from taskcontroller.interaction.mailbox_v2 import canonical_digest
    values = {"run_id": "synthetic-run", "task_id": "synthetic-task", "kind": "DEADLOCK_UNLOCK",
                  "evidence_ref": "synthetic://completed-recovery/1", "evidence_digest": canonical_digest(work["result"]),
                  "blocker_fingerprint": "synthetic-no-legal-next", "owner": "GPT",
                  "completed_recovery": True, "legal_next": False}
    values.update(changes)
    return api().VerifiedBoundary(**values)


class Delivery:
    def __init__(self):
        self.sent = []
        self.receipts = {}
    def send(self, pointer):
        self.sent.append(pointer)
        receipt = dict(pointer, delivery_ref="synthetic://delivery/1")
        self.receipts[pointer["correlation_id"]] = receipt
        return receipt
    def readback(self, correlation):
        return self.receipts.get(correlation)


def test_deadlock_outbox_dedupes_restart_push_observer_busy_and_delivers_pointer_only(tmp_path):
    adapter = host(tmp_path)
    work = completed_work(adapter)
    assert hasattr(adapter, "prepare_wake"), "semantic persistent outbox missing"
    verified = boundary(work)
    verify = lambda value, completed: value  # synthetic native source validator seam
    intent = adapter.prepare_wake(work, verified, verify=verify)
    assert intent["state"] == "PENDING"
    assert intent["task_status"] == "BLOCKED_PENDING_CONTROLLER"
    correlation = intent["pointer"]["correlation_id"]
    assert adapter.prepare_wake(work, verified, verify=verify) == intent
    delivery = Delivery()
    assert adapter.deliver_wake(correlation, delivery, gpt_state="GPT_BUSY")["state"] == "PENDING"
    assert delivery.sent == []
    adapter.close()
    reopened = host(tmp_path)
    assert reopened.prepare_wake(work, verified, verify=verify) == intent
    delivered = reopened.deliver_wake(correlation, delivery, gpt_state="GPT_IDLE")
    assert delivered["state"] == "DELIVERED"
    assert reopened.deliver_wake(correlation, delivery, gpt_state="GPT_IDLE") == delivered
    assert len(delivery.sent) == 1
    assert set(delivery.sent[0]) == {"run_id", "task_id", "thread_url", "recipient", "evidence_ref", "evidence_digest", "correlation_id"}
    assert "CONSUMED" not in str(delivered)
    reopened.close()



def test_shared_communication_sequence_readback_does_not_consume_own_report(tmp_path):
    comments = Comments()
    adapter = host(tmp_path, comments)
    first_url = binding().thread_url + "#issuecomment-1"
    adapter.consume_communication(first_url, expected_digest=digest(comments.body))
    assert hasattr(adapter, "record_posted"), "independent shared communication readback missing"
    comments.body = command(seq=2, sender="Hermes", recipient="GPT", kind="REPORT", reply_to=first_url)
    comments.actor = "Hermes"
    posted_url = binding().thread_url + "#issuecomment-2"
    posted = adapter.record_posted(posted_url, expected_digest=digest(comments.body))
    assert posted["status"] == "POSTED_NOT_CONSUMED"
    comments.body = command(seq=3, reply_to=posted_url)
    comments.actor = "GPT"
    assert adapter.consume_communication(binding().thread_url + "#issuecomment-3", expected_digest=digest(comments.body))["seq"] == 3
    adapter.close()



def test_verified_unlock_resumes_same_task_and_clears_one_pending_correlation(tmp_path):
    comments = Comments()
    adapter = host(tmp_path, comments)
    work = completed_work(adapter)
    report_url = binding().thread_url + "#issuecomment-2"
    comments.body = command(seq=2, sender="Hermes", recipient="GPT", kind="REPORT")
    comments.actor = "Hermes"
    adapter.record_posted(report_url, expected_digest=digest(comments.body))
    intent = adapter.prepare_wake(work, boundary(work, evidence_ref=report_url), verify=lambda b, w: b)
    correlation = intent["pointer"]["correlation_id"]
    adapter.deliver_wake(correlation, Delivery(), gpt_state="GPT_BUSY")
    assert hasattr(adapter, "consume_unlock"), "same-task exact unlock missing"
    comments.body = command(seq=3, reply_to=report_url)
    comments.actor = "GPT"
    unlock_url = binding().thread_url + "#issuecomment-3"
    def verify(message, bound, pending):
        return api().UnlockDecision(run_id=bound.run_id, task_id=bound.task_id,
                                     session_id=bound.session_id, correlation_id=correlation,
                                     command_digest=digest(comments.body), authority_ref="synthetic://unlock/1")
    unlocked = adapter.consume_unlock(unlock_url, expected_digest=digest(comments.body),
                                      correlation=correlation, verify=verify)
    assert unlocked["task_status"] == "RUNNING"
    assert unlocked["run_id"] == work["result"]["run_id"]
    assert unlocked["task_id"] == work["result"]["task_id"]
    assert adapter.receipts()[-1]["seq"] == 3
    resumed = adapter.invoke_work(adapter.receipts()[-1], backend=real_backend(), graph=graph_binding(), admit=native_admit)
    assert resumed["status"] == "COMPLETED"
    adapter.close()



def test_new_typed_command_requires_separate_admission_and_local_consumption(tmp_path):
    source = ExactSource()
    adapter = host(tmp_path)
    assert hasattr(adapter, "consume_typed"), "typed exact command consumption missing"
    config = observer_binding(source)
    event = source.events["controller"]
    def protected(bound, receipt, event, checkpoint):
        return replace(native_admit(bound, receipt, event, checkpoint),
                       protected_event_digest=event.event_digest, checkpoint_digest=checkpoint.checkpoint_id)
    def denied(*args):
        raise ValueError("PROTECTED_ADMISSION_DENIED")
    with pytest.raises(ValueError, match="PROTECTED_ADMISSION_DENIED"):
        adapter.consume_typed(source, config, event_id=event.event_id,
                              expected_digest=event.event_digest, admit=denied)
    assert adapter.receipts() == []
    consumed = adapter.consume_typed(source, config, event_id=event.event_id,
                                     expected_digest=event.event_digest, admit=protected)
    assert consumed["stream"] == "mailbox/v2"
    assert consumed["event_seq"] == event.event_seq
    assert consumed["status"] == "CONSUMED"
    assert adapter.receipts() == []  # independent human-readable seq stream
    invoked = adapter.invoke_work(consumed, backend=real_backend(), graph=graph_binding(),
                                  admit=protected, event=event, continuation=source.continuation)
    assert invoked["status"] == "COMPLETED"
    assert adapter.consume_typed(source, config, event_id=event.event_id,
                                 expected_digest=event.event_digest, admit=protected) == consumed
    adapter.close()



@pytest.mark.parametrize("bad", ["report", "empty_authority", "typed_substitution"])
def test_work_rejects_noncommand_or_unbound_authority_before_backend(tmp_path, bad):
    comments = Comments(command(kind="REPORT") if bad == "report" else command())
    adapter = host(tmp_path, comments)
    receipt = adapter.consume_communication(binding().thread_url + "#issuecomment-1", expected_digest=digest(comments.body))
    def admit(bound, receipt, event, checkpoint):
        return replace(native_admit(bound, receipt, event, checkpoint), authority_ref="" if bad == "empty_authority" else "synthetic://valid")
    class Never:
        def invoke(self, *args, **kwargs):
            pytest.fail("invalid work reached backend")
    with pytest.raises(Exception, match="WORK_|PROTECTED_"):
        adapter.invoke_work(receipt, backend=Never(), graph=graph_binding(), admit=admit,
                            event=ExactSource().events["controller"] if bad == "typed_substitution" else None)
    adapter.close()


def test_observer_rejects_tampered_event_body_before_highwater_write(tmp_path):
    source = ExactSource()
    event = source.events["controller"]
    object.__setattr__(event, "envelope_digest", "sha256:" + "f" * 64)
    adapter = host(tmp_path)
    with pytest.raises(Exception, match="OBSERVER_EVENT_MISMATCH"):
        adapter.observe(source, observer_binding(source), enabled=True, now=0)
    assert adapter.receipts() == []
    adapter.close()



def test_terminal_boundary_is_once_for_completed_work_not_caller_fingerprint(tmp_path):
    adapter = host(tmp_path)
    work = completed_work(adapter)
    first = adapter.prepare_wake(work, boundary(work, kind="TASK_TERMINAL", blocker_fingerprint="one"), verify=lambda b, w: b)
    second = adapter.prepare_wake(work, boundary(work, kind="TASK_TERMINAL", blocker_fingerprint="two"), verify=lambda b, w: b)
    assert second == first, "terminal task must not be re-woken by a changed diagnostic label"
    adapter.close()


def test_resolved_unlock_cannot_be_delivered_again(tmp_path):
    adapter = host(tmp_path)
    work = completed_work(adapter)
    intent = adapter.prepare_wake(work, boundary(work), verify=lambda b, w: b)
    correlation = intent["pointer"]["correlation_id"]
    # Synthetic restore of a previously verified resolution; no machine record.
    intent["state"] = "RESOLVED"
    adapter._put("outbox:" + correlation, intent)
    delivery = Delivery()
    assert adapter.deliver_wake(correlation, delivery, gpt_state="GPT_IDLE")["state"] == "RESOLVED"
    assert delivery.sent == []
    adapter.close()


def test_graph_load_proof_identifies_actual_injected_module(tmp_path):
    adapter = host(tmp_path)
    work = completed_work(adapter)
    proof = work["load_proof"]
    assert proof.get("backend_class") == "CompiledStateGraph", "loaded backend identity missing"
    assert proof["backend_module"] == "langgraph.graph.state"
    assert proof["backend_module_digest"].startswith("sha256:")
    adapter.close()



def protected_admit(bound, receipt, event, checkpoint):
    return replace(native_admit(bound, receipt, event, checkpoint),
                   protected_event_digest=event.event_digest, checkpoint_digest=checkpoint.checkpoint_id)


def test_typed_terminal_work_uses_its_own_consumed_stream_for_outbox(tmp_path):
    source = ExactSource()
    adapter = host(tmp_path)
    event = source.events["controller"]
    receipt = adapter.consume_typed(source, observer_binding(source), event_id=event.event_id,
                                     expected_digest=event.event_digest, admit=protected_admit)
    work = adapter.invoke_work(receipt, backend=real_backend(), graph=graph_binding(),
                               admit=protected_admit, event=event, continuation=source.continuation)
    intent = adapter.prepare_wake(work, boundary(work, kind="TASK_TERMINAL"), verify=lambda b, w: b)
    assert intent["consumed_stream"] == "mailbox/v2"
    assert intent["consumed_command_seq"] == receipt["seq"]
    adapter.close()



def test_typed_receipt_and_consumed_cursor_commit_atomically(tmp_path):
    import sqlite3
    source = ExactSource()
    adapter = host(tmp_path)
    event = source.events["controller"]
    adapter.db.execute("CREATE TRIGGER reject_cursor BEFORE INSERT ON state WHEN NEW.key='consumed_controller' BEGIN SELECT RAISE(ABORT, 'synthetic crash'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic crash"):
        adapter.consume_typed(source, observer_binding(source), event_id=event.event_id,
                              expected_digest=event.event_digest, admit=protected_admit)
    assert adapter._get("typed:" + event.envelope_digest) is None, "receipt committed without consumption cursor"
    adapter.close()



@pytest.mark.parametrize("change", [{"kind": "PROGRESS"}, {"kind": "OBSERVER_TICK"},
                                    {"completed_recovery": False}, {"legal_next": True}, {"owner": "Hermes"}])
def test_intermediate_progress_or_legal_recovery_never_wakes_gpt(tmp_path, change):
    adapter = host(tmp_path)
    work = completed_work(adapter)
    assert adapter.prepare_wake(work, boundary(work, **change), verify=lambda b, w: b) is None
    adapter.close()


@pytest.mark.parametrize("bad", ["run", "digest", "actor", "hold", "continuation"])
def test_typed_invalid_identity_digest_hold_or_checkpoint_cannot_consume(tmp_path, bad):
    source = ExactSource()
    adapter = host(tmp_path)
    config = observer_binding(source)
    event = source.events["controller"]
    expected = event.event_digest
    if bad == "run":
        # Source returns a canonical cursor for a different run.
        old = source.read_cursor
        source.read_cursor = lambda *args: replace(old(*args), run_id="wrong-run")
    elif bad == "digest":
        expected = "sha256:" + "f" * 64
    elif bad == "actor":
        def denied(bound, receipt, event, checkpoint):
            return replace(protected_admit(bound, receipt, event, checkpoint), agent_instance="wrong-actor")
    elif bad == "continuation":
        source.continuation = replace(source.continuation, exact_head_sha="f" * 40)
    with pytest.raises(TaskControllerValidationError):
        adapter.consume_typed(source, config, event_id=event.event_id, expected_digest=expected,
                              admit=denied if bad == "actor" else protected_admit, run_hold=bad == "hold")
    assert adapter._get("consumed_controller") is None
    assert adapter.receipts() == []
    adapter.close()


def test_unknown_transport_send_uses_readback_not_resend_after_restart(tmp_path):
    adapter = host(tmp_path)
    work = completed_work(adapter)
    intent = adapter.prepare_wake(work, boundary(work), verify=lambda b, w: b)
    correlation = intent["pointer"]["correlation_id"]
    class LostResponse(Delivery):
        def send(self, pointer):
            super().send(pointer)
            raise OSError("synthetic response lost after send")
    delivery = LostResponse()
    with pytest.raises(OSError):
        adapter.deliver_wake(correlation, delivery, gpt_state="GPT_IDLE")
    adapter.close()
    reopened = host(tmp_path)
    assert reopened.deliver_wake(correlation, delivery, gpt_state="GPT_IDLE")["state"] == "DELIVERED"
    assert len(delivery.sent) == 1
    reopened.close()


def test_graph_exception_is_durable_unknown_and_never_reexecuted(tmp_path):
    adapter = host(tmp_path)
    receipt = adapter.consume_communication(binding().thread_url + "#issuecomment-1", expected_digest=digest(command()))
    class CrashingBackend:
        calls = 0
        def invoke(self, *args, **kwargs):
            self.calls += 1
            raise OSError("synthetic backend interrupted")
    backend = CrashingBackend()
    with pytest.raises(OSError):
        adapter.invoke_work(receipt, backend=backend, graph=graph_binding(), admit=native_admit)
    adapter.close()
    reopened = host(tmp_path)
    assert reopened.invoke_work(receipt, backend=backend, graph=graph_binding(), admit=native_admit)["status"] == "UNKNOWN"
    assert backend.calls == 1
    reopened.close()


def test_old_protected_wait_does_not_block_independently_admitted_native_work(tmp_path):
    adapter = host(tmp_path)
    adapter._put("legacy_R3", {"next": "WAIT_CONTROLLER", "lease": "EXPIRED", "scheduler": "ROUTE_BINDING_MISMATCH"})
    work = completed_work(adapter)
    assert work["status"] == "COMPLETED"
    assert adapter._get("legacy_R3")["lease"] == "EXPIRED"  # not repaired/fabricated
    adapter.close()


@pytest.mark.parametrize("bad", ["task", "session", "correlation", "reply"])
def test_invalid_unlock_never_advances_consumption(tmp_path, bad):
    comments = Comments()
    adapter = host(tmp_path, comments)
    work = completed_work(adapter)
    intent = adapter.prepare_wake(work, boundary(work), verify=lambda b, w: b)
    correlation = intent["pointer"]["correlation_id"]
    comments.body = command(seq=2, reply_to="wrong-ref" if bad == "reply" else intent["pointer"]["evidence_ref"])
    def verify(message, bound, pending):
        return api().UnlockDecision(run_id=bound.run_id, task_id="wrong" if bad == "task" else bound.task_id,
                                     session_id="wrong" if bad == "session" else bound.session_id,
                                     correlation_id="wrong" if bad == "correlation" else correlation,
                                     command_digest=digest(comments.body), authority_ref="synthetic://unlock/1")
    with pytest.raises(Exception, match="UNLOCK_"):
        adapter.consume_unlock(binding().thread_url + "#issuecomment-2", expected_digest=digest(comments.body),
                               correlation=correlation, verify=verify)
    assert [r["seq"] for r in adapter.receipts()] == [1]
    adapter.close()



def test_typed_execution_cannot_substitute_another_event_after_consumption(tmp_path):
    source = ExactSource()
    adapter = host(tmp_path)
    event = source.events["controller"]
    receipt = adapter.consume_typed(source, observer_binding(source), event_id=event.event_id,
                                     expected_digest=event.event_digest, admit=protected_admit)
    other = source.events["executor"]
    with pytest.raises(Exception, match="PROTECTED_RECEIPT_MISMATCH"):
        adapter.invoke_work(receipt, backend=real_backend(), graph=graph_binding(),
                            admit=protected_admit, event=other, continuation=source.continuation)
    adapter.close()



def test_backend_receives_explicit_native_input_and_bound_command_reference(tmp_path):
    adapter = host(tmp_path)
    receipt = adapter.consume_communication(binding().thread_url + "#issuecomment-1", expected_digest=digest(command()))
    class RecordingBackend:
        def invoke(self, state, config):
            assert state == {"native_node": "synthetic-recovery", "opaque": [1, 2]}
            assert config["configurable"]["command_ref"] == receipt["url"]
            assert config["configurable"]["command_digest"] == receipt["digest"]
            return {"native_outcome": "synthetic-completed"}
    work = adapter.invoke_work(receipt, backend=RecordingBackend(), graph=graph_binding(),
                               admit=native_admit, input_state={"native_node": "synthetic-recovery", "opaque": [1, 2]})
    assert work["result"] == {"native_outcome": "synthetic-completed"}
    adapter.close()



def test_writer_fence_is_effective_across_processes(tmp_path):
    import json
    import subprocess
    import sys
    from dataclasses import asdict
    adapter = host(tmp_path)
    code = """
import json, sys
from taskcontroller.runtime.hermes_graph_host import HermesGraphHost, HostBinding
try:
    HermesGraphHost(sys.argv[1], HostBinding(**json.loads(sys.argv[2])), comments=None)
except Exception as exc:
    print(str(exc))
    sys.exit(0 if 'HOST_WRITER_BUSY' in str(exc) else 2)
sys.exit(1)
"""
    with adapter.writer():
        child = subprocess.run([sys.executable, "-c", code, str(tmp_path / "host.sqlite"), json.dumps(asdict(binding()))],
                                check=False, capture_output=True, text=True, timeout=15)
    assert child.returncode == 0, child.stdout + child.stderr
    assert adapter.receipts() == []
    adapter.close()


def test_busy_state_keeps_one_active_pending_correlation(tmp_path):
    adapter = host(tmp_path)
    work = completed_work(adapter)
    first = adapter.prepare_wake(work, boundary(work), verify=lambda b, w: b)
    second = adapter.prepare_wake(work, boundary(work, blocker_fingerprint="another"), verify=lambda b, w: b)
    delivery = Delivery()
    adapter.deliver_wake(first["pointer"]["correlation_id"], delivery, gpt_state="GPT_BUSY")
    adapter.deliver_wake(second["pointer"]["correlation_id"], delivery, gpt_state="GPT_IDLE")
    assert adapter._get("pending_correlation") == first["pointer"]["correlation_id"]
    assert delivery.sent == []
    adapter.close()
