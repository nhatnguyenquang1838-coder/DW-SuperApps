from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, cast

import pytest

from taskcontroller.runtime.certification_models import (
    CertificationCampaign,
    ExecutionReceipt,
    SourceRevision,
    TestCase,
    TestRun,
)
from taskcontroller.runtime.certification_store import CertificationStore
from taskcontroller.runtime.live_certification_harness import LiveCertificationError, LiveCertificationHarness


_SHA_A = "a" * 40
_SHA_B = "b" * 40
_SHA_C = "c" * 40
_SHA_D = "d" * 40


def _campaign() -> CertificationCampaign:
    return CertificationCampaign(
        campaign_id="C-SAFETY",
        mode="RUNTIME_PROVING_LAB",
        runtime_branch="runtime/C-SAFETY",
        proving_branch="prove/C-SAFETY",
        test_case_id="TC-SAFETY",
        test_case_revision="r1",
        baseline_runtime_sha=_SHA_A,
        baseline_subject_sha=_SHA_B,
        gwc_sha=_SHA_C,
        status="ACTIVE",
    )


def _case() -> TestCase:
    return TestCase(
        case_id="TC-SAFETY",
        revision="r1",
        scenario="safety",
        acceptance="safety",
        declared_paths=("taskcontroller/runtime",),
    )


def _receipt(execution_id: str) -> ExecutionReceipt:
    return ExecutionReceipt(
        execution_id=execution_id,
        started_at="2026-09-10T00:00:00Z",
        ended_at="2026-09-10T00:00:01Z",
        controller_seq_start=1,
        controller_seq_end=1,
        executor_seq_start=1,
        executor_seq_end=1,
        cursor_before="before",
        cursor_after="after",
        semantic_step_receipt_digests=("sha256:" + "e" * 64,),
    )


def _start(harness: LiveCertificationHarness, run_id: str = "run-safe"):
    return harness.start_run(
        campaign_id="C-SAFETY",
        case_id="TC-SAFETY",
        runtime=SourceRevision("nhatnguyenquang1838-coder/DW-SuperApps", "runtime/C-SAFETY", _SHA_A, _SHA_D),
        subject=SourceRevision("nhatnguyenquang1838-coder/DW-SuperApps", "prove/C-SAFETY", _SHA_B, _SHA_D),
        gwc_sha=_SHA_C,
        executor="Hermes",
        model="test-model",
        run_id=run_id,
        runtime_plan_ref="plan://C-SAFETY/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "f" * 64,
    )


def test_start_run_rejects_attacker_controlled_source_bindings():
    harness = LiveCertificationHarness()
    harness.create_campaign(_campaign())
    harness.register_case(_case())

    with pytest.raises(LiveCertificationError, match="source binding"):
        harness.start_run(
            campaign_id="C-SAFETY",
            case_id="TC-SAFETY",
            runtime=SourceRevision("attacker/repo", "attacker/runtime", _SHA_D, _SHA_D),
            subject=SourceRevision("attacker/repo", "attacker/subject", _SHA_D, _SHA_D),
            gwc_sha=_SHA_C,
            executor="Hermes",
            model="attacker-model",
            run_id="run-attacker",
            runtime_plan_ref="plan://C-SAFETY/r1",
            runtime_plan_revision="r1",
            runtime_plan_digest="sha256:" + "f" * 64,
        )


def test_replay_rejects_run_event_for_unknown_campaign(tmp_path: Path):
    path = tmp_path / "campaign.events.jsonl"
    store = CertificationStore(path)
    campaign = _campaign()
    store.append("CAMPAIGN_CREATED", campaign.campaign_id, campaign.to_dict())
    orphan = TestRun(
        run_id="run-orphan",
        campaign_id="missing-campaign",
        case_id="TC-SAFETY",
        case_revision="r1",
        runtime=SourceRevision("nhatnguyenquang1838-coder/DW-SuperApps", "runtime/C-SAFETY", _SHA_A, _SHA_D),
        subject=SourceRevision("nhatnguyenquang1838-coder/DW-SuperApps", "prove/C-SAFETY", _SHA_B, _SHA_D),
        gwc_sha=_SHA_C,
        runtime_plan_ref="plan://C-SAFETY/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "f" * 64,
        executor="Hermes",
        model="test-model",
        verdict="PENDING",
    )
    store.append("RUN_STARTED", orphan.run_id, orphan.to_dict())

    with pytest.raises(LiveCertificationError, match="campaign"):
        LiveCertificationHarness(store=path)


def test_terminal_evidence_redacts_secret_values_before_persistence(tmp_path: Path):
    path = tmp_path / "campaign.events.jsonl"
    harness = LiveCertificationHarness(store=path)
    harness.create_campaign(_campaign())
    harness.register_case(_case())
    run = _start(harness)

    harness.record_verdict(
        run.run_id,
        "PASS",
        {
            "password": "PASSWORD-SENTINEL",
            "nested": {"access_token": "TOKEN-SENTINEL"},
            "safe": "retained",
        },
        execution_receipt=_receipt("exec-safe"),
    )

    raw = path.read_text(encoding="utf-8")
    assert "PASSWORD-SENTINEL" not in raw
    assert "TOKEN-SENTINEL" not in raw
    restored = LiveCertificationHarness(store=path).list_campaign_runs("C-SAFETY")[-1]
    evidence = cast(Mapping[str, object], restored.evidence)
    nested = cast(Mapping[str, object], evidence["nested"])
    assert evidence["password"] == "[REDACTED]"
    assert nested["access_token"] == "[REDACTED]"
    assert evidence["safe"] == "retained"


def test_certification_store_concurrent_appends_preserve_one_chain(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "events.jsonl"

    def append(index: int) -> int:
        return CertificationStore(path).append("TEST", f"aggregate-{index}", {"index": index}).event_seq

    with ThreadPoolExecutor(max_workers=8) as pool:
        sequences = list(pool.map(append, range(8)))

    assert sorted(sequences) == list(range(1, 9))
    assert [event.event_seq for event in CertificationStore(path).replay()] == list(range(1, 9))
