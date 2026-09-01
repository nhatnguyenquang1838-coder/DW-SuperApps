"""Seq20 C3 — durable GitHub-backed certification evidence (RED first).

/tmp is working storage only. Sanitized append-only event chains + manifests
must be exportable to a GitHub-backed location and reconstructable by a fresh
verifier WITHOUT the original host /tmp files. Tamper / missing event /
cross-campaign substitution must fail closed.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest


def _export_module():
    return importlib.import_module("taskcontroller.runtime.certification_export")


def _store_module():
    return importlib.import_module("taskcontroller.runtime.certification_store")


def _make_store(tmp_path: Path) -> object:
    store = _store_module().CertificationStore(tmp_path / "working.events.jsonl")
    store.append("CAMPAIGN_CREATED", "RP-CERT-001", {"campaign_id": "RP-CERT-001", "status": "ACTIVE"})
    store.append(
        "RUN_VERDICT_RECORDED",
        "run-1",
        {
            "run_id": "run-1",
            "campaign_id": "RP-CERT-001",
            "case_id": "TC-RP-001",
            "verdict": "PASS",
            "gwc_sha": "c" * 40,
        },
    )
    return store


def test_export_sanitized_evidence_and_manifest(tmp_path):
    mod = _export_module()
    store = _make_store(tmp_path)
    target = tmp_path / "evidence"
    manifest = mod.export_durable_evidence(store, target)
    assert (target / "events.jsonl").exists()
    assert (target / "manifest.json").exists()
    assert manifest["campaign_id"] == "RP-CERT-001"
    assert manifest["record_count"] == 2
    assert manifest["final_manifest_digest"]
    # sanitized: no local absolute paths, no secrets
    raw = (target / "manifest.json").read_text(encoding="utf-8")
    assert "/tmp/" not in raw
    assert str(tmp_path) not in raw
    assert "token" not in raw.lower() and "secret" not in raw.lower()


def test_fresh_verifier_reconstructs_without_original_tmp(tmp_path):
    mod = _export_module()
    original = tmp_path / "working.events.jsonl"
    store = _store_module().CertificationStore(original)
    store.append("CAMPAIGN_CREATED", "RP-CERT-001", {"campaign_id": "RP-CERT-001"})
    store.append("RUN_VERDICT_RECORDED", "run-1", {"run_id": "run-1", "verdict": "PASS", "campaign_id": "RP-CERT-001"})
    target = tmp_path / "evidence"
    mod.export_durable_evidence(store, target)

    # Simulate a fresh host: original working store unavailable.
    fresh_dir = tmp_path / "fresh-clone"
    fresh_dir.mkdir()
    for item in target.iterdir():
        (fresh_dir / item.name).write_bytes(item.read_bytes())
    original.unlink()

    events = mod.reconstruct_evidence(fresh_dir / "manifest.json")
    assert len(events) == 2
    assert events[0].payload["campaign_id"] == "RP-CERT-001"
    assert events[1].payload["verdict"] == "PASS"


def test_tampered_event_fails_closed(tmp_path):
    mod = _export_module()
    store = _make_store(tmp_path)
    target = tmp_path / "evidence"
    mod.export_durable_evidence(store, target)
    events_path = target / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["payload"]["verdict"] = "FAIL"
    lines[1] = json.dumps(record)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest|tamper|chain"):
        mod.reconstruct_evidence(target / "manifest.json")


def test_missing_event_and_cross_campaign_fail_closed(tmp_path):
    mod = _export_module()
    store = _make_store(tmp_path)
    target = tmp_path / "evidence"
    mod.export_durable_evidence(store, target)
    lines = (target / "events.jsonl").read_text(encoding="utf-8").splitlines()
    (target / "events.jsonl").write_text(lines[0] + "\n", encoding="utf-8")  # drop event 2
    with pytest.raises(ValueError, match="record_count|chain|digest|missing"):
        mod.reconstruct_evidence(target / "manifest.json")

    # cross-campaign substitution
    target2 = tmp_path / "evidence2"
    mod.export_durable_evidence(_make_store(tmp_path), target2)
    manifest = json.loads((target2 / "manifest.json").read_text(encoding="utf-8"))
    manifest["campaign_id"] = "RP-CERT-999"
    (target2 / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="campaign|digest|manifest"):
        mod.reconstruct_evidence(target2 / "manifest.json")
