#!/usr/bin/env python3
"""
DWO-UR-30-V1 fixture pack generator (CR-822-A/B/C).

Deterministically materializes the official DWO-UR-30-V1 fixture specification
into executable dev-mode fixture artifacts:

  DWO-UR-30-V1/
    fixture-set.yaml
    runs/DEV-RUN-001..030.yaml
    events/projection-events.jsonl
    evidence/{authority,execution,verification,target,closure,handoff,qualification}/
    expected/{run-list,hierarchy,states,replay-checkpoints,anomalies}.json

Design rules (from the canonical catalog):
  * projection-events.jsonl is the EXECUTABLE stream; runs/*.yaml is authoring/
    reference only and never feeds UI directly (no fixture-to-UI bypass).
  * Deterministic IDs, ActorRefs, timestamps, digests (JCS+SHA-256).
  * Defaults: source_profile=DEV_NATIVE, sync_state=LIVE,
    semantic_qualification=PENDING, authority_state=NOT_APPLICABLE, anomaly_count=0.
  * QUALIFIED is never implicit — requires a synthetic qualification record.
  * DEV-RUN-020 is an incompatible-source negative fixture -> INCOMPATIBLE,
    no fabricated G0..G6.
  * DEV-RUN-030 authority NOT_APPLICABLE (no manufactured UNKNOWN/DENIED).
  * Universal runtime facts and DWO-derived projection fields are separate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # projects/dw-observation
OUT = ROOT / "dwo-v2" / "fixtures" / "DWO-UR-30-V1"

# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

def jcs(obj) -> str:
    """Deterministic JSON serialization (RFC 8785-ish: sorted keys, no spaces)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(obj) -> str:
    return hashlib.sha256(jcs(obj).encode("utf-8")).hexdigest()


def record(run_id: str, schema_id: str, created_by: str, created_at: str, body: dict) -> dict:
    """Canonical immutable record envelope (kernel §1.3)."""
    payload = {
        "record_id": f"{run_id}-{schema_id}",
        "schema_id": schema_id,
        "schema_version": 1,
        "run_id": run_id,
        "created_at": created_at,
        "created_by": created_by,
        "content_digest": {
            "algorithm": "sha256",
            "canonicalization": "JCS",
            "value": sha256_hex(body),
        },
        "provenance": {"predecessor_refs": [], "source_refs": []},
        **body,
    }
    return payload


# ---------------------------------------------------------------------------
# Fixture spec table (canonical, from the catalog)
# ---------------------------------------------------------------------------
# Each entry: id, domain, kind, parent, gate, gate_state, run_state,
#             source_profile, sync_state, semantic_qualification,
#             authority_state, anomaly_count, purpose, children, deps

FIXTURES = [
    # --- Core software/runtime semantic pack 001..020 ---
    dict(id="DEV-RUN-001", domain="CORE", kind="ROOT", parent=None, gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="recursive Root/ALL_REQUIRED with children 002/003/004", children=["DEV-RUN-002", "DEV-RUN-003", "DEV-RUN-004"], deps=[]),
    dict(id="DEV-RUN-002", domain="CORE", kind="ATOMIC", parent="DEV-RUN-001", gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="RETRY_STEP same semantic identity, attempt increments", children=[], deps=[]),
    dict(id="DEV-RUN-003", domain="CORE", kind="ATOMIC", parent="DEV-RUN-001", gate="G2", gate_state="BLOCKED", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="dependency on 002 unmet", children=[], deps=["DEV-RUN-002"]),
    dict(id="DEV-RUN-004", domain="CORE", kind="ATOMIC", parent="DEV-RUN-001", gate="G2", gate_state="BLOCKED", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="DENIED", anomaly=0, purpose="effect requires authority, DENIED", children=[], deps=[]),
    dict(id="DEV-RUN-005", domain="CORE", kind="ROOT", parent=None, gate="G3", gate_state="FAILED", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="parent composition FAIL despite accepted children 006/007", children=["DEV-RUN-006", "DEV-RUN-007"], deps=[]),
    dict(id="DEV-RUN-006", domain="CORE", kind="ATOMIC", parent="DEV-RUN-005", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="G4 IN_PLACE no-transfer integration", children=[], deps=[]),
    dict(id="DEV-RUN-007", domain="CORE", kind="ATOMIC", parent="DEV-RUN-005", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="RESET_DERIVED_STATE rebuild parity", children=[], deps=[]),
    dict(id="DEV-RUN-008", domain="CORE", kind="ROOT", parent=None, gate="G4", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="QUORUM 2/3 aggregation", children=["DEV-RUN-009", "DEV-RUN-010", "DEV-RUN-011"], deps=[]),
    dict(id="DEV-RUN-009", domain="CORE", kind="ATOMIC", parent="DEV-RUN-008", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="RERUN_STEP new semantic generation", children=[], deps=[]),
    dict(id="DEV-RUN-010", domain="CORE", kind="ATOMIC", parent="DEV-RUN-008", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="atomic normal success", children=[], deps=[]),
    dict(id="DEV-RUN-011", domain="CORE", kind="ATOMIC", parent="DEV-RUN-008", gate="G3", gate_state="FAILED", run_state="FAILED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="atomic terminal failure", children=[], deps=[]),
    dict(id="DEV-RUN-012", domain="CORE", kind="ROOT", parent=None, gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="REPLAN_RUN plan revision 2, drift REPLAN_REQUIRED", children=[], deps=[]),
    dict(id="DEV-RUN-013", domain="CORE", kind="CHILD", parent="DEV-RUN-014", gate="G6", gate_state="CANCELLED", run_state="CANCELLED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="child generation 1 cancelled", children=[], deps=[]),
    dict(id="DEV-RUN-014", domain="CORE", kind="ROOT", parent=None, gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="RERUN_SUBTREE child generation 2", children=["DEV-RUN-013"], deps=[]),
    dict(id="DEV-RUN-015", domain="CORE", kind="ROOT", parent=None, gate="G6", gate_state="SUPERSEDED", run_state="SUPERSEDED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="old ROOT objective superseded by 016", children=[], deps=[]),
    dict(id="DEV-RUN-016", domain="CORE", kind="ROOT", parent=None, gate="G0", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="RESTART_AS_NEW_RUN new run_id + lineage", children=[], deps=[]),
    dict(id="DEV-RUN-017", domain="EVENT", kind="ROOT", parent=None, gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Home Party Root, physical event target", children=["DEV-RUN-018"], deps=[]),
    dict(id="DEV-RUN-018", domain="EVENT", kind="CHILD", parent="DEV-RUN-017", gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Food Run recursive child", children=["DEV-RUN-019"], deps=[]),
    dict(id="DEV-RUN-019", domain="EVENT", kind="ATOMIC", parent="DEV-RUN-018", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Buy Cake physical delivery, HUMAN_CONFIRMED", children=[], deps=[]),
    dict(id="DEV-RUN-020", domain="CORE", kind="NEGATIVE", parent=None, gate=None, gate_state=None, run_state="INCOMPATIBLE", source="UNKNOWN", sync="UNAVAILABLE", qual="INCOMPATIBLE", authority="NOT_APPLICABLE", anomaly=0, purpose="intentional incompatible-source negative fixture, fail closed", children=[], deps=[]),
    # --- Party Holding pack 021..023 ---
    dict(id="DEV-RUN-021", domain="EVENT/PARTY_HOLDING", kind="ROOT", parent=None, gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Party Holding Root, ALL_REQUIRED", children=["DEV-RUN-022", "DEV-RUN-023"], deps=[]),
    dict(id="DEV-RUN-022", domain="EVENT/PARTY_HOLDING", kind="CHILD", parent="DEV-RUN-021", gate="G5", gate_state="WAITING", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Guest Coordination, external confirmations pending", children=[], deps=[]),
    dict(id="DEV-RUN-023", domain="EVENT/PARTY_HOLDING", kind="CHILD", parent="DEV-RUN-021", gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Outdoor Setup / Rain Contingency, CONDITIONAL", children=[], deps=[]),
    # --- Researching pack 024..026 ---
    dict(id="DEV-RUN-024", domain="RESEARCH", kind="ROOT", parent=None, gate="G3", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Independent Research Root, parent synthesis pending", children=["DEV-RUN-025", "DEV-RUN-026"], deps=[]),
    dict(id="DEV-RUN-025", domain="RESEARCH", kind="CHILD", parent="DEV-RUN-024", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Source Collection, evidence strength/provenance", children=[], deps=[]),
    dict(id="DEV-RUN-026", domain="RESEARCH", kind="CHILD", parent="DEV-RUN-024", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Research Synthesis, local PASS parent pending", children=[], deps=["DEV-RUN-025"]),
    # --- Wedding pack 027..030 ---
    dict(id="DEV-RUN-027", domain="EVENT/WEDDING", kind="ROOT", parent=None, gate="G2", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Wedding Planning Root, ALL_REQUIRED", children=["DEV-RUN-028", "DEV-RUN-029", "DEV-RUN-030"], deps=[]),
    dict(id="DEV-RUN-028", domain="EVENT/WEDDING", kind="CHILD", parent="DEV-RUN-027", gate="G6", gate_state="PASSED", run_state="ACCEPTED", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Venue Booking, EXTERNAL_ACK, BIND", children=[], deps=[]),
    dict(id="DEV-RUN-029", domain="EVENT/WEDDING", kind="CHILD", parent="DEV-RUN-027", gate="G2", gate_state="BLOCKED", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Catering Selection, dependency revalidation required", children=[], deps=["DEV-RUN-028"]),
    dict(id="DEV-RUN-030", domain="EVENT/WEDDING", kind="CHILD", parent="DEV-RUN-027", gate="G5", gate_state="ACTIVE", run_state="OPEN", source="DEV_NATIVE", sync="LIVE", qual="PENDING", authority="NOT_APPLICABLE", anomaly=0, purpose="Ceremony Day, HUMAN_CONFIRMED, no authority requirement", children=[], deps=[]),
]

# Deterministic timestamps (RFC3339, fixed so replay is stable)
T0 = "2026-09-01T00:00:00Z"
ACTOR = "fixture://dwo-ur-30-v1/generator"


def fixture_bundle(f: dict) -> dict:
    """Build the canonical fixture bundle (runtime_facts + dwo_expected_projection)."""
    runtime_facts = {
        "run_id": f["id"],
        "run_kind": f["kind"],
        "lifecycle_profile": {"id": "gwc.universal-run", "version": 1},
        "domain_profile_ref": f["domain"],
        "target_contract_ref": f"TARGET-{f['id'].replace('DEV-RUN-','')}-R1",
        "active_runtime_plan_ref": f"PLAN-{f['id'].replace('DEV-RUN-','')}-R1",
        "active_runtime_plan_revision": 1,
        "active_runtime_plan_digest": sha256_hex({"plan": f["id"], "rev": 1}),
        "atomic": f["kind"] == "ATOMIC",
        "child_run_refs": f["children"],
        "dependency_refs": f["deps"],
        "parent_run_ref": f["parent"],
        "lifecycle": {
            "G0": "PASSED" if f["gate"] != "G0" else "ACTIVE",
            "G1": "PASSED" if f["gate"] not in ("G0", "G1") else ("ACTIVE" if f["gate"] == "G1" else "NOT_STARTED"),
            "G2": f["gate_state"] if f["gate"] == "G2" else ("PASSED" if f["gate"] in ("G3", "G4", "G5", "G6") else "NOT_STARTED"),
            "G3": f["gate_state"] if f["gate"] == "G3" else ("PASSED" if f["gate"] in ("G4", "G5", "G6") else "NOT_STARTED"),
            "G4": f["gate_state"] if f["gate"] == "G4" else ("PASSED" if f["gate"] in ("G5", "G6") else "NOT_STARTED"),
            "G5": f["gate_state"] if f["gate"] == "G5" else ("PASSED" if f["gate"] == "G6" else "NOT_STARTED"),
            "G6": f["gate_state"] if f["gate"] == "G6" else "NOT_STARTED",
        },
        "run_state": f["run_state"],
    }
    if f["gate"] == "G5" and f["gate_state"] == "WAITING":
        runtime_facts["waiting_reason"] = "EXTERNAL_GUEST_CONFIRMATIONS_PENDING"
    if f["id"] == "DEV-RUN-029":
        runtime_facts["block_reason"] = "UPSTREAM_DEPENDENCY_REVALIDATION_REQUIRED"
    if f["id"] == "DEV-RUN-004":
        runtime_facts["block_reason"] = "AUTHORITY_DENIED"
    if f["id"] == "DEV-RUN-003":
        runtime_facts["block_reason"] = "UNMET_DEPENDENCY"

    dwo = {
        "source_profile": f["source"],
        "sync_state": f["sync"],
        "semantic_qualification": f["qual"],
        "authority_state": f["authority"],
        "anomaly_count": f["anomaly"],
    }
    return {"runtime_facts": runtime_facts, "dwo_expected_projection": dwo}


def build_all():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "runs").mkdir(exist_ok=True)
    (OUT / "events").mkdir(exist_ok=True)
    for sub in ("authority", "execution", "verification", "target", "closure", "handoff", "qualification"):
        (OUT / "evidence" / sub).mkdir(parents=True, exist_ok=True)
    (OUT / "expected").mkdir(exist_ok=True)

    # fixture-set.yaml
    fixture_set = {
        "fixture_set": "DWO-UR-30-V1",
        "status": "OFFICIAL_DESIGN_BASELINE",
        "semantic_review": "ACCEPTED",
        "materialization": "MATERIALIZED",
        "run_count": len(FIXTURES),
        "conforming_runs": 29,
        "negative_fixture": "DEV-RUN-020",
        "dwo_fixture_projection_defaults": {
            "source_profile": "DEV_NATIVE",
            "sync_state": "LIVE",
            "semantic_qualification": "PENDING",
            "authority_state": "NOT_APPLICABLE",
            "anomaly_count": 0,
        },
        "runs": [f["id"] for f in FIXTURES],
    }
    (OUT / "fixture-set.yaml").write_text(_yaml(fixture_set))

    # runs/*.yaml + projection-events.jsonl
    events = []
    for f in FIXTURES:
        bundle = fixture_bundle(f)
        (OUT / "runs" / f"{f['id']}.yaml").write_text(_yaml(bundle))
        # one projection event per run (deterministic)
        ev = {
            "event_id": f"EVT-{f['id']}",
            "run_id": f["id"],
            "ordinal": int(f["id"].split("-")[2]),
            "source_profile": f["source"],
            "sync_state": f["sync"],
            "semantic_qualification": f["qual"],
            "authority_state": f["authority"],
            "anomaly_count": f["anomaly"],
            "gate": f["gate"],
            "gate_state": f["gate_state"],
            "run_state": f["run_state"],
            "created_at": T0,
            "created_by": ACTOR,
        }
        events.append(ev)
    events.sort(key=lambda e: e["ordinal"])
    (OUT / "events" / "projection-events.jsonl").write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in events) + "\n"
    )

    # evidence (deterministic receipts)
    for f in FIXTURES:
        if f["id"] == "DEV-RUN-020":
            continue  # negative fixture: no fabricated receipts
        if f["run_state"] in ("ACCEPTED", "FAILED", "CANCELLED", "SUPERSEDED"):
            closure = record(f["id"], "ClosureReceipt", ACTOR, T0, {"terminal_outcome": f["run_state"]})
            (OUT / "evidence" / "closure" / f"{f['id']}-closure.json").write_text(json.dumps(closure, indent=2))
            if f["run_state"] == "ACCEPTED":
                handoff = record(f["id"], "HandoffReceipt", ACTOR, T0, {"handoff_to": "fixture://consumer"})
                (OUT / "evidence" / "handoff" / f"{f['id']}-handoff.json").write_text(json.dumps(handoff, indent=2))
        if f["authority"] == "DENIED":
            auth = record(f["id"], "AuthorityDecisionReceipt", ACTOR, T0, {"decision": "DENY", "reason": "fixture policy"})
            (OUT / "evidence" / "authority" / f"{f['id']}-authority.json").write_text(json.dumps(auth, indent=2))
        if f["gate"] in ("G3", "G4", "G5", "G6"):
            verif = record(f["id"], "VerificationAttestation", ACTOR, T0, {"verdict": "PASS" if f["gate_state"] != "FAILED" else "FAIL"})
            (OUT / "evidence" / "verification" / f"{f['id']}-verification.json").write_text(json.dumps(verif, indent=2))
        execr = record(f["id"], "ExecutionReceipt", ACTOR, T0, {"result": "PASS"})
        (OUT / "evidence" / "execution" / f"{f['id']}-execution.json").write_text(json.dumps(execr, indent=2))
        target = record(f["id"], "TargetBindingReceipt", ACTOR, T0, {"outcome": "IN_PLACE" if f["gate"] == "G6" else "PENDING"})
        (OUT / "evidence" / "target" / f"{f['id']}-target.json").write_text(json.dumps(target, indent=2))

    # golden outputs
    run_list = [
        {
            "id": f["id"], "domain": f["domain"], "kind": f["kind"], "parent": f["parent"],
            "gate": f["gate"], "gate_state": f["gate_state"], "run_state": f["run_state"],
            "sync": f["sync"], "qualification": f["qual"], "source_profile": f["source"],
            "authority": f["authority"], "anomaly_count": f["anomaly"],
        }
        for f in FIXTURES
    ]
    (OUT / "expected" / "run-list.json").write_text(json.dumps(run_list, indent=2))

    hierarchy = []
    for f in FIXTURES:
        if f["parent"]:
            hierarchy.append({"parent": f["parent"], "child": f["id"]})
    (OUT / "expected" / "hierarchy.json").write_text(json.dumps(hierarchy, indent=2))

    states = {f["id"]: {"gate": f["gate"], "gate_state": f["gate_state"], "run_state": f["run_state"]} for f in FIXTURES}
    (OUT / "expected" / "states.json").write_text(json.dumps(states, indent=2))

    replay = {f["id"]: {"event_prefix": f"EVT-{f['id']}", "replay_tip": f["run_state"]} for f in FIXTURES}
    (OUT / "expected" / "replay-checkpoints.json").write_text(json.dumps(replay, indent=2))

    anomalies = [f["id"] for f in FIXTURES if f["anomaly"] > 0]
    (OUT / "expected" / "anomalies.json").write_text(json.dumps(anomalies, indent=2))

    print(f"materialized {len(FIXTURES)} fixtures -> {OUT}")


def _yaml(obj: dict) -> str:
    import yaml
    return yaml.safe_dump(obj, sort_keys=False, default_flow_style=False)


if __name__ == "__main__":
    build_all()
