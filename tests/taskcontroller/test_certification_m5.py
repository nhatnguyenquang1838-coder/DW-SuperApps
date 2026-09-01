"""M5: W7 LiveCertificationHarness — durable immutable certification.

Fixes the W1-W7 review BLOCKERs on W7:
- B5: ``record_verdict()`` could overwrite a recorded verdict — evidence must
  be immutable once recorded.
- B6: only PASS branch deletion was banned; FAIL/PENDING branches were
  deletable, violating "Never delete PASS/FAIL certification branches".
- designer M2: TestRun lacked ``runtime_plan_digest`` — cannot assert plan
  immutability at execution time without re-fetching the plan.
- durability: the harness stored TestRun state only in-memory (self._runs) —
  a hard restart lost the certification registry. M5 adds a durable JSON
  store so runs survive process restarts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskcontroller.runtime.live_certification_harness import (
    LiveCertificationError,
    LiveCertificationHarness,
    TestCase,
    TestRun,
    TestRunVerdict,
    RunMode,
)


def _case(*, case_id: str = "TC-RP-001", scenario: str = "standard_real_run", acceptance: str = "login works") -> TestCase:
    return TestCase(case_id=case_id, scenario=scenario, acceptance=acceptance)


def _run(harness, *, case=None, branch="feature/m5", base_sha="0" * 40, head_sha="1" * 40, digest="sha256:" + "d" * 64) -> TestRun:
    return harness.start_run(
        case=case or _case(),
        branch=branch,
        base_sha=base_sha,
        head_sha=head_sha,
        executor="Hermes",
        model="gpt",
        runtime_plan_ref="plan.test/r1",
        runtime_plan_digest=digest,
    )


def test_start_run_records_runtime_plan_digest():
    """designer M2: TestRun carries the runtime_plan_digest so certification
    can assert plan immutability at execution time."""
    harness = LiveCertificationHarness()
    run = _run(harness, digest="sha256:" + "d" * 64)
    assert run.runtime_plan_digest == "sha256:" + "d" * 64


def test_record_verdict_is_immutable_after_first_record():
    """B5: a recorded verdict must not be overwritable."""
    harness = LiveCertificationHarness()
    run = _run(harness)
    harness.record_verdict(
        run_id=run.run_id,
        verdict="PASS",
        evidence={"ci": {"run": "r1", "status": "success"}},
    )
    with pytest.raises(LiveCertificationError, match="immutable|already recorded"):
        harness.record_verdict(
            run_id=run.run_id,
            verdict="FAIL",
            evidence={"ci": {"run": "r1", "status": "failed"}},
        )


def test_delete_branch_rejected_for_fail_run():
    """B6: FAIL certification branches must be retained too — never delete
    PASS/FAIL certification branches."""
    harness = LiveCertificationHarness()
    run = _run(harness)
    harness.record_verdict(
        run_id=run.run_id,
        verdict="FAIL",
        evidence={"ci": {"run": "r1", "status": "failed"}},
    )
    with pytest.raises(LiveCertificationError, match="retained"):
        harness.delete_branch(run_id=run.run_id)


def test_delete_branch_rejected_for_pending_run():
    """B6: PENDING runs also retain their branch (no deletion before verdict)."""
    harness = LiveCertificationHarness()
    run = _run(harness)
    with pytest.raises(LiveCertificationError, match="retained"):
        harness.delete_branch(run_id=run.run_id)


def test_harness_restores_runs_from_durable_store(tmp_path: Path):
    """Durability: a new harness over the same store reconstructs the run
    registry exactly (survives process restart)."""
    store = tmp_path / "cert.jsonl"
    harness = LiveCertificationHarness(store=store)
    run = _run(harness)
    harness.record_verdict(
        run_id=run.run_id,
        verdict="PASS",
        evidence={"ci": {"run": "r1", "status": "success"}},
    )

    restored = LiveCertificationHarness(store=store)
    got = restored.get_run(run.run_id)
    assert got.verdict == "PASS"
    assert got.runtime_plan_digest == "sha256:" + "d" * 64
    assert got.evidence == {"ci": {"run": "r1", "status": "success"}}
    # replayed run is immutable too
    with pytest.raises(LiveCertificationError, match="immutable|already recorded"):
        restored.record_verdict(
            run_id=run.run_id,
            verdict="FAIL",
            evidence={"ci": {"run": "r1", "status": "failed"}},
        )


def test_restored_harness_rejects_reused_branch(tmp_path: Path):
    """Durability: branch identity survives restart — a reused branch for a
    new run is still rejected."""
    store = tmp_path / "cert2.jsonl"
    harness = LiveCertificationHarness(store=store)
    _run(harness, branch="feature/keep")
    restored = LiveCertificationHarness(store=store)
    with pytest.raises(LiveCertificationError, match="already used"):
        _run(restored, branch="feature/keep")


def test_evidence_record_schema_wired_into_verdict():
    """designer M1: verdict evidence accepts the canonical EvidenceRecord."""
    from taskcontroller.runtime.evidence_record import EvidenceRecord

    harness = LiveCertificationHarness()
    run = _run(harness)
    rec = EvidenceRecord(
        expected_output={"status": "ok"},
        actual_output={"status": "ok"},
        verdict_reason="all AC pass",
        authority_revalidated=True,
        readback_digest="sha256:readback",
        plan_digest_at_execution="sha256:" + "d" * 64,
    )
    harness.record_verdict(run_id=run.run_id, verdict="PASS", evidence=rec.to_dict())
    assert harness.get_run(run.run_id).evidence["plan_digest_at_execution"] == "sha256:" + "d" * 64


def test_record_verdict_rejects_unknown_verdict():
    """seq=8: verdict allowlist — only PASS/FAIL accepted."""
    harness = LiveCertificationHarness()
    run = _run(harness)
    with pytest.raises(LiveCertificationError, match="must be exactly PASS or FAIL"):
        harness.record_verdict(
            run_id=run.run_id,
            verdict="UNKNOWN",
            evidence={"ci": {"run": "r1", "status": "unknown"}},
        )


def test_record_verdict_rejects_arbitrary_verdict():
    """seq=8: verdict allowlist — arbitrary string rejected."""
    harness = LiveCertificationHarness()
    run = _run(harness)
    with pytest.raises(LiveCertificationError, match="must be exactly PASS or FAIL"):
        harness.record_verdict(
            run_id=run.run_id,
            verdict="MAYBE",
            evidence={"ci": {"run": "r1", "status": "maybe"}},
        )


def test_jsonl_rejects_pass_fail_contradiction(tmp_path: Path):
    """seq=8: JSONL contradiction detection — PASS -> FAIL for same run_id raises on load."""
    store = tmp_path / "contradiction.jsonl"
    harness = LiveCertificationHarness(store=store)
    run = _run(harness)
    harness.record_verdict(
        run_id=run.run_id,
        verdict="PASS",
        evidence={"ci": {"run": "r1", "status": "success"}},
    )
    # Tamper: append conflicting FAIL record for same run_id
    fake = TestRun(
        run_id=run.run_id,
        case_id="TC-RP-001",
        scenario="standard_real_run",
        acceptance="login works",
        branch="feature/m5",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
        verdict=TestRunVerdict.FAIL,
        evidence={"ci": {"run": "r1", "status": "failed"}},
    )
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fake.to_dict(), sort_keys=True) + "\n")
    with pytest.raises(LiveCertificationError, match="contradictory terminal history"):
        LiveCertificationHarness(store=store)


def test_jsonl_restart_pending_to_pass(tmp_path: Path):
    """seq=8: positive restart — PENDING -> PASS is legitimate and reloads."""
    store = tmp_path / "restart_ok.jsonl"
    harness = LiveCertificationHarness(store=store)
    run = _run(harness)
    harness.record_verdict(
        run_id=run.run_id,
        verdict="PASS",
        evidence={"ci": {"run": "r1", "status": "success"}},
    )
    restored = LiveCertificationHarness(store=store)
    got = restored.get_run(run.run_id)
    assert got.verdict == "PASS"
    assert got.evidence == {"ci": {"run": "r1", "status": "success"}}


def test_jsonl_restart_pending_to_fail(tmp_path: Path):
    """seq=8: positive restart — PENDING -> FAIL is legitimate and reloads."""
    store = tmp_path / "restart_fail.jsonl"
    harness = LiveCertificationHarness(store=store)
    run = _run(harness)
    harness.record_verdict(
        run_id=run.run_id,
        verdict="FAIL",
        evidence={"ci": {"run": "r1", "status": "failed"}},
    )
    restored = LiveCertificationHarness(store=store)
    got = restored.get_run(run.run_id)
    assert got.verdict == "FAIL"
