#!/usr/bin/env python3
"""Compute artifact hashes for SCRUM-746 proposal artifacts."""
import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FILES = [
    "g0/context-snapshot.yaml",
    "g1/intake/g1-intake-brief.yaml",
    "g1/preflight/g1-preflight-report.yaml",
    "g1/brainstorming/g1-options.yaml",
    "g1/decision/g1-decision-record.yaml",
    "g2/execution-envelope.yaml",
    "g2/scope_inputs.json",
    "g2/gen_scope_hash.py",
    "g2/scope_hash.txt",
    "proposal/written-proposal.md",
    "proposal/change-plan.yaml",
    "proposal/overview.mmd",
    "proposal/detailed.svg",
    "proposal/detailed.png",
    "proposal/approval-envelope.yaml",
]

def compute(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

lines = []
for f in FILES:
    p = BASE / f
    if p.exists():
        h = compute(p)
        lines.append(f"sha256:{h}  {f}")
    else:
        lines.append(f"MISSING  {f}")

content = "\n".join(lines) + "\n"
out = BASE / "proposal" / "artifact-hashes.txt"
out.write_text(content)
print(content)
print(f"Written to: {out}")
