"""Bound-input integrity tracking for TaskController audit.

Tracks the exact execution inputs bound by the Controller contract:
repo refs, contract overlays, execution contract, and source evidence.

Hermes internal skill/self-improvement store is NOT monitored merely
because it changes. Surface only changes that affect bound input/scope/
authority/output evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class BoundInputSnapshot:
    """Snapshot of bound execution inputs at a point in time."""

    repo_refs: dict[str, str] = field(default_factory=dict)
    contract_overlays: list[str] = field(default_factory=list)
    execution_contract: dict[str, Any] = field(default_factory=dict)
    source_evidence: list[str] = field(default_factory=list)

    def canonical_json(self) -> str:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def compute_snapshot_hash(snapshot: BoundInputSnapshot) -> str:
    data = snapshot.canonical_json()
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IntegrityChange:
    category: str
    before: Any
    after: Any
    material: bool


def diff_snapshots(before: BoundInputSnapshot, after: BoundInputSnapshot) -> list[IntegrityChange]:
    changes: list[IntegrityChange] = []

    categories = [
        ("repo_refs", before.repo_refs, after.repo_refs),
        ("contract_overlays", before.contract_overlays, after.contract_overlays),
        ("execution_contract", before.execution_contract, after.execution_contract),
        ("source_evidence", before.source_evidence, after.source_evidence),
    ]

    for category, b, a in categories:
        if b != a:
            changes.append(
                IntegrityChange(
                    category=category,
                    before=b,
                    after=a,
                    material=True,
                )
            )

    return changes


def is_material_integrity_change(changes: list[IntegrityChange]) -> bool:
    return any(c.material for c in changes)
