from __future__ import annotations

import importlib
import json

import pytest


def _store_module():
    try:
        return importlib.import_module("taskcontroller.runtime.certification_store")
    except ModuleNotFoundError as exc:  # RED until the store module exists.
        pytest.fail(f"certification_store is not implemented yet: {exc}")


def _legacy_record():
    return {
        "run_id": "run-legacy-001",
        "case_id": "TC-RP-001",
        "scenario": "standard_real_run",
        "acceptance": "login works",
        "branch": "prove/legacy/TC-RP-001",
        "base_sha": "0" * 40,
        "head_sha": "1" * 40,
        "executor": "Hermes-Mac",
        "model": "legacy-model",
        "pr_id": "116",
        "runtime_plan_ref": "legacy-plan/r1",
        "runtime_plan_digest": "sha256:" + "d" * 64,
        "mode": "STANDARD_REAL_RUN",
        "verdict": "PASS",
        "evidence": {"ci": {"status": "success"}},
        "expected": "login works",
        "actual": "login works",
        "branch_deleted": False,
    }


def test_append_and_replay_preserve_hash_chain(tmp_path):
    models = _store_module()
    path = tmp_path / "certification.events.jsonl"
    store = models.CertificationStore(path)
    first = store.append("CAMPAIGN_CREATED", "RP-CERT-001", {"status": "ACTIVE"})
    second = store.append("RUN_RECORDED", "RP-CERT-001", {"run_id": "run-001"})

    assert first.schema_version == 1
    assert first.event_seq == 1
    assert first.previous_digest == "GENESIS"
    assert second.event_seq == 2
    assert second.previous_digest == first.record_digest
    assert store.replay() == (first, second)
    assert models.CertificationStore(path).replay() == (first, second)


def test_event_payload_is_deeply_immutable_and_detached(tmp_path):
    models = _store_module()
    payload = {"nested": {"items": ["original"]}}
    event = models.CertificationStore(tmp_path / "events.jsonl").append(
        "RUN_RECORDED", "run-001", payload
    )
    payload["nested"]["items"].append("outside")
    assert event.payload["nested"]["items"] == ("original",)
    with pytest.raises(TypeError):
        event.payload["nested"] = {}
    detached = event.to_dict()
    detached["payload"]["nested"]["items"].append("detached")
    assert event.payload["nested"]["items"] == ("original",)


def test_tampered_record_digest_fails_closed(tmp_path):
    models = _store_module()
    path = tmp_path / "tampered.jsonl"
    models.CertificationStore(path).append("RUN_RECORDED", "run-001", {"ok": True})
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["ok"] = False
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        models.CertificationStore(path)


def test_broken_previous_digest_and_sequence_fail_closed(tmp_path):
    models = _store_module()
    path = tmp_path / "broken-chain.jsonl"
    store = models.CertificationStore(path)
    store.append("CAMPAIGN_CREATED", "RP-CERT-001", {})
    store.append("RUN_RECORDED", "RP-CERT-001", {})
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[1]["previous_digest"] = "0" * 64
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="previous_digest|chain|digest"):
        models.CertificationStore(path)

    bad_seq = tmp_path / "bad-seq.jsonl"
    store = models.CertificationStore(bad_seq)
    store.append("CAMPAIGN_CREATED", "RP-CERT-001", {})
    records = [json.loads(line) for line in bad_seq.read_text(encoding="utf-8").splitlines()]
    records[0]["event_seq"] = 2
    bad_seq.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="event_seq|sequence|digest"):
        models.CertificationStore(bad_seq)


def test_invalid_schema_version_fails_closed(tmp_path):
    models = _store_module()
    path = tmp_path / "bad-schema.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "event_seq": 1,
                "event_type": "RUN_RECORDED",
                "aggregate_id": "run-001",
                "payload": {},
                "previous_digest": "GENESIS",
                "record_digest": "0" * 64,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema"):
        models.CertificationStore(path)


def test_legacy_v1_jsonl_loads_as_explicit_immutable_evidence(tmp_path):
    models = _store_module()
    path = tmp_path / "legacy-v1.jsonl"
    path.write_text(json.dumps(_legacy_record()) + "\n", encoding="utf-8")
    runs = models.CertificationStore(tmp_path / "events.jsonl").load_legacy_runs(path)
    assert len(runs) == 1
    run = runs[0]
    assert run.run_id == "run-legacy-001"
    assert run.verdict == "PASS"
    assert run.legacy is True
    detached = run.to_dict()
    detached["evidence"]["ci"]["status"] = "changed"
    assert run.evidence["ci"]["status"] == "success"
