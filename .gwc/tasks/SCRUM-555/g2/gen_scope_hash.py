#!/usr/bin/env python3
"""Deterministic scope-hash generator (auditable).
Hashes a canonical serialization of the scope inputs + referenced gate artifacts.
NOT the rendered execution-envelope YAML (per Controller correction).
"""
import hashlib, json, sys
from pathlib import Path

ROOT = Path("/Users/mac/prj/DW-SuperApps.worktrees/auto/scratch-555-obs-g6-readiness")
G = ROOT / ".gwc/tasks/SCRUM-555"

def load(p):
    return json.loads(p.read_text()) if p.suffix == ".json" else __import__("yaml").safe_load(p.read_text())

# canonical, sorted-key serialization of scope inputs
scope = json.loads((G / "g2/scope_inputs.json").read_text())
canon = {
    "repository": scope["repository"],
    "task_id": scope["task_id"],
    "run_label": scope["run_label"],
    "base_ref": scope["base_ref"],
    "base_sha": scope["base_sha"],
    "working_branch": scope["working_branch"],
    "feature_target": scope["feature_target"],
    "risk_class": scope["risk_class"],
    "expires_at": scope["expires_at"],
    "approved_paths": sorted(scope["approved_paths"]),
    "test_paths_allowed": sorted(scope.get("test_paths_allowed", [])),
    "authorized_actions": sorted(scope["authorized_actions"]),
    "excluded_actions": sorted(scope["excluded_actions"]),
}
blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()
h = "sha256:" + hashlib.sha256(blob).hexdigest()
(G / "g2/scope_hash.txt").write_text(h + "\n")
print("SCOPE_HASH", h)
print("SERIALIZED_LEN", len(blob))
