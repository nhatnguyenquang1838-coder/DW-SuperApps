"""TC-MBX-701: canonical terminal parent result write/readback contract."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
from typing import Any

import pytest

from taskcontroller.interaction.mailbox_repository import InMemoryMailboxRepository
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope
from taskcontroller.execution.terminal_result import (
    TerminalParentResult,
    TerminalResultError,
    build_terminal_parent_result,
    verify_terminal_result_readback,
    write_terminal_parent_result,
)


_FIXTURE = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
_DIGEST = "sha256:" + "a" * 64


def _request() -> V2MailboxEnvelope:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]["execution_request"]
    return V2MailboxEnvelope.from_dict(copy.deepcopy(payload))


def _normalized_parent_result() -> dict[str, Any]:
    return {
        "protocol": "dw.taskcontroller.parent-synthesis/v1",
        "proposed_verdict": "PASS",
        "final_verdict": "PASS",
        "verdict": "PASS",
        "status": "PASS",
        "findings": [
            {
                "finding_id": "finding-701",
                "severity": "minor",
                "category": "evidence",
                "lens": "implementation",
                "claim": "The terminal result carries deterministic evidence.",
                "evidence_refs": ["artifact://evidence-701"],
                "recommendation": "Retain the canonical digest.",
                "reviewer": "reviewer-701",
                "disposition": "ACCEPTED",
            }
        ],
        "child_refs": [
            {
                "child_id": "child-701",
                "status": "SUCCEEDED",
                "result_digest": _DIGEST,
                "normalization_digest": _DIGEST,
                "raw_output_digest": "sha256:" + "b" * 64,
                "child_contract_digest": "sha256:" + "c" * 64,
                "source_digest": "sha256:" + "d" * 64,
                "lens": "implementation",
                "reviewer": "reviewer-701",
            }
        ],
        "child_result_digests": [_DIGEST],
        "residual_risks": [],
        "unresolved_questions": [],
        "conflicts": [],
        "controller_decision": {
            "decision_id": "decision-701",
            "run_ref": "run-1",
            "decision_type": "COMPLETE",
            "rationale": "The evidence-backed parent result is complete.",
            "evidence_refs": ["artifact://evidence-701"],
        },
    }


def test_builds_one_v2_terminal_parent_result_with_bound_evidence() -> None:
    terminal = build_terminal_parent_result(
        _request(),
        _normalized_parent_result(),
        message_id="terminal-701",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-701",
    )

    assert isinstance(terminal, TerminalParentResult)
    envelope = terminal.envelope
    assert envelope.to_dict()["message_type"] == "terminal_result"
    assert envelope.to_dict()["direction"] == "executor_to_controller"
    assert envelope.execution_identity["attempt_id"] == "attempt-1"
    assert envelope.execution_identity["lease_generation"] == 1
    assert envelope.execution_identity["fencing_token"] == "fence-1"
    assert envelope.to_dict()["result"]["result_digest"] == terminal.result_digest
    assert envelope.to_dict()["result"]["findings"][0]["finding_id"] == "finding-701"
    assert envelope.to_dict()["payload"]["child_provenance"][0]["child_id"] == "child-701"
    assert envelope.to_dict()["payload"]["standards_digest"] == "sha256:" + "6" * 64
    assert envelope.to_dict()["payload"]["source_digest"] == "sha256:" + "4" * 64
    assert envelope.to_dict()["provenance"]["result_digest"] == terminal.result_digest
    assert terminal.canonical_bytes() == terminal.envelope.canonical_bytes()


def test_terminal_write_exact_readback_matches_controller_consumption() -> None:
    repository = InMemoryMailboxRepository()
    terminal = build_terminal_parent_result(
        _request(),
        _normalized_parent_result(),
        message_id="terminal-701-readback",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-701-readback",
    )

    receipt, consumed = write_terminal_parent_result(
        repository,
        "github://owner/repo/issues/701#controller",
        expected_seq=-1,
        terminal=terminal,
    )

    assert receipt.idempotent is False
    assert consumed == terminal
    assert consumed.to_dict() == terminal.to_dict()
    assert repository.read("github://owner/repo/issues/701#controller").events[-1].envelope == terminal.envelope
    verify_terminal_result_readback(terminal, repository.exact_readback(receipt), receipt)


def test_terminal_result_rejects_identity_mismatch_and_raw_chat() -> None:
    request = _request()
    with pytest.raises(TerminalResultError) as identity_error:
        build_terminal_parent_result(
            request,
            _normalized_parent_result(),
            message_id="terminal-701-identity",
            seq=1,
            producer_namespace="hermes-executor",
            producer_actor_id="hermes-mac",
            recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
            idempotency_key="terminal-idem-701-identity",
            expected_identity={"fencing_token": "stale-fence"},
        )
    assert identity_error.value.code == "TERMINAL_IDENTITY_MISMATCH"

    raw_chat = _normalized_parent_result()
    raw_chat["transcript"] = "do not serialize this chat"
    with pytest.raises(TerminalResultError) as raw_error:
        build_terminal_parent_result(
            request,
            raw_chat,
            message_id="terminal-701-raw",
            seq=1,
            producer_namespace="hermes-executor",
            producer_actor_id="hermes-mac",
            recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
            idempotency_key="terminal-idem-701-raw",
        )
    assert raw_error.value.code == "TERMINAL_RAW_CONTEXT_FORBIDDEN"


def test_exact_readback_rejects_a_different_terminal_digest() -> None:
    repository = InMemoryMailboxRepository()
    terminal = build_terminal_parent_result(
        _request(),
        _normalized_parent_result(),
        message_id="terminal-701-tamper",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-701-tamper",
    )
    receipt, _ = write_terminal_parent_result(
        repository,
        "github://owner/repo/issues/701#controller",
        expected_seq=-1,
        terminal=terminal,
    )
    altered = _normalized_parent_result()
    altered["residual_risks"] = ["a materially different result"]
    different = build_terminal_parent_result(
        _request(),
        altered,
        message_id="terminal-701-tamper",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-701-tamper",
    )

    assert different.result_digest != terminal.result_digest
    with pytest.raises(TerminalResultError) as mismatch:
        verify_terminal_result_readback(different, repository.exact_readback(receipt), receipt)
    assert mismatch.value.code == "TERMINAL_READBACK_MISMATCH"


def test_same_current_terminal_digest_is_idempotent_across_delivery_keys() -> None:
    repository = InMemoryMailboxRepository()
    first = build_terminal_parent_result(
        _request(),
        _normalized_parent_result(),
        message_id="terminal-702-first",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-702-first",
    )
    first_receipt, _ = write_terminal_parent_result(
        repository,
        "github://owner/repo/issues/702#controller",
        expected_seq=-1,
        terminal=first,
    )
    duplicate = build_terminal_parent_result(
        _request(),
        _normalized_parent_result(),
        message_id="terminal-702-duplicate",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-702-duplicate",
    )

    duplicate_receipt, consumed = write_terminal_parent_result(
        repository,
        "github://owner/repo/issues/702#controller",
        expected_seq=0,
        terminal=duplicate,
    )

    assert duplicate_receipt.idempotent is True
    assert duplicate_receipt.event_id == first_receipt.event_id
    assert consumed == first
    assert len(repository.read("github://owner/repo/issues/702#controller").events) == 1


def test_conflicting_terminal_digest_for_current_identity_rejects_before_append() -> None:
    repository = InMemoryMailboxRepository()
    first = build_terminal_parent_result(
        _request(),
        _normalized_parent_result(),
        message_id="terminal-702-conflict-first",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-702-conflict-first",
    )
    write_terminal_parent_result(
        repository,
        "github://owner/repo/issues/702#controller",
        expected_seq=-1,
        terminal=first,
    )
    altered = _normalized_parent_result()
    altered["residual_risks"] = ["a conflicting current-attempt result"]
    conflicting = build_terminal_parent_result(
        _request(),
        altered,
        message_id="terminal-702-conflict-second",
        seq=2,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-702-conflict-second",
    )

    with pytest.raises(TerminalResultError) as conflict:
        write_terminal_parent_result(
            repository,
            "github://owner/repo/issues/702#controller",
            expected_seq=0,
            terminal=conflicting,
        )

    assert conflict.value.code == "TERMINAL_RESULT_CONFLICT"
    assert len(repository.read("github://owner/repo/issues/702#controller").events) == 1


def test_concurrent_same_terminal_digest_converges_to_one_current_truth() -> None:
    class BarrierRepository(InMemoryMailboxRepository):
        def __init__(self, participants: int) -> None:
            super().__init__()
            self._participants = participants
            self._read_count = 0
            self._read_lock = Lock()
            self._read_barrier = Barrier(participants)

        def read(self, mailbox_ref: str):  # type: ignore[no-untyped-def]
            snapshot = super().read(mailbox_ref)
            with self._read_lock:
                self._read_count += 1
                synchronize = self._read_count <= self._participants
            if synchronize:
                self._read_barrier.wait(timeout=5)
            return snapshot

    repository = BarrierRepository(6)
    terminals = [
        build_terminal_parent_result(
            _request(),
            _normalized_parent_result(),
            message_id=f"terminal-702-concurrent-{index}",
            seq=1,
            producer_namespace="hermes-executor",
            producer_actor_id="hermes-mac",
            recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
            idempotency_key=f"terminal-idem-702-concurrent-{index}",
        )
        for index in range(6)
    ]

    def deliver(terminal: TerminalParentResult) -> tuple[bool, TerminalParentResult]:
        receipt, consumed = write_terminal_parent_result(
            repository,
            "github://owner/repo/issues/702#controller",
            expected_seq=-1,
            terminal=terminal,
        )
        return receipt.idempotent, consumed

    with ThreadPoolExecutor(max_workers=len(terminals)) as pool:
        outcomes = list(pool.map(deliver, terminals))

    assert sum(idempotent for idempotent, _ in outcomes) == len(terminals) - 1
    assert {consumed.result_digest for _, consumed in outcomes} == {terminals[0].result_digest}
    assert len(repository.read("github://owner/repo/issues/702#controller").events) == 1
