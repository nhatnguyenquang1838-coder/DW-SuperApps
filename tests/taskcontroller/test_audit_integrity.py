"""RED tests for bound-input integrity (S3)."""
from __future__ import annotations

import hashlib
import json

import pytest

from taskcontroller.audit.integrity import (
    BoundInputSnapshot,
    IntegrityChange,
    compute_snapshot_hash,
    diff_snapshots,
    is_material_integrity_change,
)


class TestBoundInputSnapshot:
    def test_hash_is_deterministic(self) -> None:
        snapshot = BoundInputSnapshot(
            repo_refs={"main": "abc123"},
            contract_overlays=["overlay-1"],
            execution_contract={"subtask_id": "S1"},
            source_evidence=["sha1", "sha2"],
        )
        h1 = compute_snapshot_hash(snapshot)
        h2 = compute_snapshot_hash(snapshot)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_identical_snapshots_no_diff(self) -> None:
        a = BoundInputSnapshot(
            repo_refs={"main": "abc"},
            contract_overlays=[],
            execution_contract={"run_id": "r1"},
            source_evidence=[],
        )
        b = BoundInputSnapshot(
            repo_refs={"main": "abc"},
            contract_overlays=[],
            execution_contract={"run_id": "r1"},
            source_evidence=[],
        )
        changes = diff_snapshots(a, b)
        assert changes == []

    def test_repo_ref_change_is_material(self) -> None:
        a = BoundInputSnapshot(
            repo_refs={"main": "abc"},
            contract_overlays=[],
            execution_contract={},
            source_evidence=[],
        )
        b = BoundInputSnapshot(
            repo_refs={"main": "def"},
            contract_overlays=[],
            execution_contract={},
            source_evidence=[],
        )
        changes = diff_snapshots(a, b)
        assert any(c.category == "repo_refs" for c in changes)

    def test_contract_overlay_change_is_material(self) -> None:
        a = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=["overlay-1"],
            execution_contract={},
            source_evidence=[],
        )
        b = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=["overlay-2"],
            execution_contract={},
            source_evidence=[],
        )
        changes = diff_snapshots(a, b)
        assert any(c.category == "contract_overlays" for c in changes)

    def test_execution_contract_change_is_material(self) -> None:
        a = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=[],
            execution_contract={"subtask_id": "S1"},
            source_evidence=[],
        )
        b = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=[],
            execution_contract={"subtask_id": "S2"},
            source_evidence=[],
        )
        changes = diff_snapshots(a, b)
        assert any(c.category == "execution_contract" for c in changes)

    def test_source_evidence_change_is_material(self) -> None:
        a = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=[],
            execution_contract={},
            source_evidence=["sha1"],
        )
        b = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=[],
            execution_contract={},
            source_evidence=["sha2"],
        )
        changes = diff_snapshots(a, b)
        assert any(c.category == "source_evidence" for c in changes)

    def test_skill_mutation_is_not_material_by_default(self) -> None:
        """Hermes internal skill changes are NOT monitored unless bound as input.

        Because skill_hashes is not part of BoundInputSnapshot, two snapshots
        that differ only in skill state produce no diff.
        """
        a = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=[],
            execution_contract={},
            source_evidence=[],
        )
        b = BoundInputSnapshot(
            repo_refs={},
            contract_overlays=[],
            execution_contract={},
            source_evidence=[],
        )
        changes = diff_snapshots(a, b)
        assert changes == []

    def test_is_material_integrity_change_true(self) -> None:
        changes = [
            IntegrityChange(category="repo_refs", before="a", after="b", material=True)
        ]
        assert is_material_integrity_change(changes) is True

    def test_is_material_integrity_change_false(self) -> None:
        assert is_material_integrity_change([]) is False
