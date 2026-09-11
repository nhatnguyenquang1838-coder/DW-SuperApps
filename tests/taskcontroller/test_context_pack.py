"""TC-MBX-405: bounded task context-pack contract."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

import pytest

from taskcontroller.standards import (
    ContextPackBuilder,
    ContextPackError,
    ContextPackLimits,
    EvidenceRef,
    StandardsProfile,
    StandardsResolver,
    StandardsSourceRef,
)


_COMMIT_A = "a" * 40
_COMMIT_B = "b" * 40
_COMMIT_S = "c" * 40


class SourceReader:
    def __init__(self, values: dict[tuple[str, str], bytes]) -> None:
        self.values = values
        self.calls: list[tuple[str, str]] = []

    def read_exact(self, source: StandardsSourceRef) -> bytes:
        key = (source.commit_sha, source.path)
        self.calls.append(key)
        return self.values[key]


class EvidenceReader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.calls: list[str] = []

    def read_exact(self, evidence: EvidenceRef) -> bytes:
        self.calls.append(evidence.ref)
        return self.values[evidence.ref]


def _source(commit: str, path: str, content: str) -> StandardsSourceRef:
    return StandardsSourceRef(
        repository="owner-repo",
        commit_sha=commit,
        path=path,
        blob_digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
    )


def _evidence(ref: str, content: str, media_type: str = "text/plain") -> EvidenceRef:
    return EvidenceRef(
        ref=ref,
        digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
        media_type=media_type,
    )


def _standards() -> tuple[Any, StandardsSourceRef, SourceReader]:
    source = _source(_COMMIT_S, "standards/AGENTS.md", "standards rules")
    reader = SourceReader({(_COMMIT_S, source.path): b"standards rules"})
    profile = StandardsProfile.create(
        profile_id="taskcontroller.engineering",
        version="v1",
        sources=(source,),
    )
    return StandardsResolver(reader).resolve(profile).session_context, source, reader


def test_materializes_only_declared_sources_evidence_and_resolved_standards() -> None:
    standards, standards_source, standards_reader = _standards()
    source = _source(_COMMIT_A, "src/task.py", "task source")
    ambient_source = _source(_COMMIT_B, "src/ambient.py", "ambient source")
    source_reader = SourceReader(
        {
            (_COMMIT_A, source.path): b"task source",
            (_COMMIT_B, ambient_source.path): b"ambient source",
        }
    )
    evidence = _evidence("github://evidence/1", "exact evidence")
    evidence_reader = EvidenceReader(
        {evidence.ref: b"exact evidence", "github://evidence/ambient": b"ambient"}
    )

    pack = ContextPackBuilder(source_reader, evidence_reader).build(
        source_refs=(source,), evidence_refs=(evidence,), standards=standards
    )

    assert [item.source.path for item in pack.sources] == ["src/task.py"]
    assert [item.content for item in pack.sources] == ["task source"]
    assert [item.reference.ref for item in pack.evidence] == [evidence.ref]
    assert [item.content for item in pack.evidence] == [b"exact evidence"]
    assert source_reader.calls == [(_COMMIT_A, source.path)]
    assert evidence_reader.calls == [evidence.ref]
    assert standards_reader.calls == [(_COMMIT_S, standards_source.path)]
    serialized = pack.to_dict()
    assert "slack_history" not in serialized
    assert "conversation_history" not in serialized
    assert "gpt_history" not in serialized


def test_inventory_and_digest_are_reproducible_when_inputs_are_reordered() -> None:
    standards, _, _ = _standards()
    first = _source(_COMMIT_A, "src/a.py", "A")
    second = _source(_COMMIT_B, "src/b.py", "B")
    evidence_a = _evidence("github://evidence/a", "EA")
    evidence_b = _evidence("github://evidence/b", "EB")
    source_values = {
        (_COMMIT_A, first.path): b"A",
        (_COMMIT_B, second.path): b"B",
    }
    evidence_values = {evidence_a.ref: b"EA", evidence_b.ref: b"EB"}

    left = ContextPackBuilder(SourceReader(source_values), EvidenceReader(evidence_values)).build(
        source_refs=(second, first),
        evidence_refs=(evidence_b, evidence_a),
        standards=standards,
    )
    right = ContextPackBuilder(SourceReader(source_values), EvidenceReader(evidence_values)).build(
        source_refs=(first, second),
        evidence_refs=(evidence_a, evidence_b),
        standards=standards,
    )

    assert left.inventory == right.inventory
    assert left.inventory_digest == right.inventory_digest
    assert left.canonical_bytes() == right.canonical_bytes()


def test_inventory_binds_exact_source_evidence_and_standards_identity() -> None:
    standards, _, _ = _standards()
    source = _source(_COMMIT_A, "src/task.py", "task")
    evidence = _evidence("github://evidence/1", "evidence")
    pack = ContextPackBuilder(
        SourceReader({(_COMMIT_A, source.path): b"task"}),
        EvidenceReader({evidence.ref: b"evidence"}),
    ).build(source_refs=(source,), evidence_refs=(evidence,), standards=standards)

    assert pack.inventory["protocol"] == "dw.taskcontroller.context-pack/v1"
    assert pack.inventory["source_refs"] == [source.to_dict()]
    assert pack.inventory["evidence_refs"] == [evidence.to_dict()]
    assert pack.inventory["standards"]["digest"] == standards.receipt.digest
    assert pack.inventory["standards"]["context_digest"] == standards.receipt.context_digest
    assert pack.inventory_digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [("source", "CONTEXT_SOURCE_DIGEST_MISMATCH"), ("evidence", "CONTEXT_EVIDENCE_DIGEST_MISMATCH")],
)
def test_digest_drift_fails_closed(kind: str, expected_code: str) -> None:
    standards, _, _ = _standards()
    source = _source(_COMMIT_A, "src/task.py", "approved")
    evidence = _evidence("github://evidence/1", "approved")
    source_values = {(_COMMIT_A, source.path): b"substituted" if kind == "source" else b"approved"}
    evidence_values = {evidence.ref: b"substituted" if kind == "evidence" else b"approved"}

    with pytest.raises(ContextPackError) as caught:
        ContextPackBuilder(SourceReader(source_values), EvidenceReader(evidence_values)).build(
            source_refs=(source,), evidence_refs=(evidence,), standards=standards
        )

    assert caught.value.code == expected_code


def test_evidence_without_content_digest_is_rejected_before_read() -> None:
    standards, _, _ = _standards()
    reader = EvidenceReader({"github://evidence/1": b"evidence"})

    with pytest.raises(ContextPackError) as caught:
        ContextPackBuilder(SourceReader({}), reader).build(
            source_refs=(),
            evidence_refs=("github://evidence/1",),
            standards=standards,
        )

    assert caught.value.code == "CONTEXT_EVIDENCE_REF_INVALID"
    assert reader.calls == []


def test_duplicate_references_are_rejected_without_materialization() -> None:
    standards, _, _ = _standards()
    source = _source(_COMMIT_A, "src/task.py", "task")
    source_reader = SourceReader({(_COMMIT_A, source.path): b"task"})

    with pytest.raises(ContextPackError) as caught:
        ContextPackBuilder(source_reader).build(
            source_refs=(source, source), evidence_refs=(), standards=standards
        )

    assert caught.value.code == "CONTEXT_DUPLICATE_REF"
    assert source_reader.calls == []


def test_reference_and_content_bounds_fail_closed() -> None:
    standards, _, _ = _standards()
    source = _source(_COMMIT_A, "src/task.py", "task")
    evidence = _evidence("github://evidence/1", "evidence")
    source_reader = SourceReader({(_COMMIT_A, source.path): b"task"})
    evidence_reader = EvidenceReader({evidence.ref: b"evidence"})

    with pytest.raises(ContextPackError) as caught:
        ContextPackBuilder(
            source_reader,
            evidence_reader,
            limits=ContextPackLimits(max_sources=0),
        ).build(source_refs=(source,), evidence_refs=(), standards=standards)
    assert caught.value.code == "CONTEXT_SOURCE_LIMIT_EXCEEDED"
    assert source_reader.calls == []

    with pytest.raises(ContextPackError) as caught:
        ContextPackBuilder(
            source_reader,
            evidence_reader,
            limits=ContextPackLimits(max_total_bytes=1, max_single_bytes=1),
        ).build(source_refs=(source,), evidence_refs=(evidence,), standards=standards)
    assert caught.value.code == "CONTEXT_SIZE_LIMIT_EXCEEDED"


def test_missing_or_invalid_standards_context_is_rejected() -> None:
    source = _source(_COMMIT_A, "src/task.py", "task")
    with pytest.raises(ContextPackError) as caught:
        ContextPackBuilder(SourceReader({(_COMMIT_A, source.path): b"task"})).build(
            source_refs=(source,), evidence_refs=(), standards=None
        )
    assert caught.value.code == "CONTEXT_STANDARDS_REQUIRED"


def test_pack_is_immutable_and_serialization_is_not_an_authority_channel() -> None:
    standards, _, _ = _standards()
    source = _source(_COMMIT_A, "src/task.py", "task")
    evidence = _evidence("github://evidence/1", "evidence")
    pack = ContextPackBuilder(
        SourceReader({(_COMMIT_A, source.path): b"task"}),
        EvidenceReader({evidence.ref: b"evidence"}),
    ).build(source_refs=(source,), evidence_refs=(evidence,), standards=standards)

    with pytest.raises(AttributeError):
        pack.sources = ()  # type: ignore[misc]
    payload = pack.to_dict()
    payload["inventory"]["source_refs"].clear()
    assert pack.inventory["source_refs"] == [source.to_dict()]
    assert all("history" not in key.lower() for key in payload)
