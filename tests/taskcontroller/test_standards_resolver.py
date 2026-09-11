"""TC-MBX-403: exact standards profile resolution and session materialization."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any

import pytest

from taskcontroller.standards import (
    STANDARDS_MANIFEST_CANONICALIZATION,
    STANDARDS_MATERIALIZATION_PROTOCOL,
    MaterializedSourceReceipt,
    StandardsProfile,
    StandardsResolutionError,
    StandardsResolver,
    StandardsSourceRef,
    canonical_profile_digest,
    canonical_source_manifest,
    canonical_standards_bytes,
)


_COMMIT_A = "a" * 40
_COMMIT_B = "b" * 40


class MappingSourceReader:
    def __init__(self, values: dict[tuple[str, str], bytes]) -> None:
        self._values = values
        self.calls: list[tuple[str, str]] = []

    def read_exact(self, source: StandardsSourceRef) -> bytes:
        key = (source.commit_sha, source.path)
        self.calls.append(key)
        try:
            return self._values[key]
        except KeyError as exc:
            raise FileNotFoundError(f"missing exact source: {key}") from exc


def _source(commit_sha: str, path: str, content: str) -> StandardsSourceRef:
    digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    return StandardsSourceRef(
        repository="dw-superapps",
        commit_sha=commit_sha,
        path=path,
        blob_digest=digest,
    )


def _profile(*sources: StandardsSourceRef) -> StandardsProfile:
    return StandardsProfile.create(
        profile_id="taskcontroller.engineering",
        version="v1",
        sources=sources,
    )


def _reader(*pairs: tuple[StandardsSourceRef, str]) -> MappingSourceReader:
    return MappingSourceReader(
        {(source.commit_sha, source.path): content.encode("utf-8") for source, content in pairs}
    )


def test_resolver_materializes_only_exact_declared_sources_and_receipts_identity() -> None:
    policy = _source(_COMMIT_A, "agents/shared/taskcontroller-a2a-protocol.md", "a2a rules")
    engineering = _source(_COMMIT_B, "agents/hermes/agent-instructions.md", "executor rules")
    reader = _reader((policy, "a2a rules"), (engineering, "executor rules"))

    resolved = StandardsResolver(reader).resolve(_profile(engineering, policy))

    assert [item.source.path for item in resolved.instructions] == [
        "agents/shared/taskcontroller-a2a-protocol.md",
        "agents/hermes/agent-instructions.md",
    ]
    assert [item.content for item in resolved.instructions] == ["a2a rules", "executor rules"]
    assert reader.calls == [
        (_COMMIT_A, "agents/shared/taskcontroller-a2a-protocol.md"),
        (_COMMIT_B, "agents/hermes/agent-instructions.md"),
    ]
    receipt = resolved.receipt.to_dict()
    assert receipt["profile_id"] == "taskcontroller.engineering"
    assert receipt["version"] == "v1"
    assert receipt["digest"] == resolved.profile.digest
    assert receipt["source_count"] == 2
    assert receipt["context_digest"].startswith("sha256:")
    assert resolved.session_context.to_dict()["standards"]["digest"] == resolved.profile.digest


def test_profile_digest_and_context_are_stable_when_source_order_changes() -> None:
    first = _source(_COMMIT_A, "instructions/a.md", "A")
    second = _source(_COMMIT_B, "instructions/b.md", "B")
    left = _profile(first, second)
    right = _profile(second, first)
    left_reader = _reader((first, "A"), (second, "B"))
    right_reader = _reader((first, "A"), (second, "B"))

    left_resolved = StandardsResolver(left_reader).resolve(left)
    right_resolved = StandardsResolver(right_reader).resolve(right)

    assert left.digest == right.digest
    assert left_resolved.session_context.to_dict() == right_resolved.session_context.to_dict()


def test_resolver_rejects_source_content_digest_drift() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    reader = _reader((source, "substituted"))

    with pytest.raises(StandardsResolutionError) as error:
        StandardsResolver(reader).resolve(_profile(source))

    assert error.value.code == "STANDARDS_RESOLUTION_BLOCKED"
    assert "instructions/policy.md" in str(error.value)


def test_resolver_rejects_profile_digest_mismatch_after_exact_sources_load() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    profile = _profile(source)
    tampered = replace(profile, digest="sha256:" + "0" * 64)

    with pytest.raises(StandardsResolutionError) as error:
        StandardsResolver(_reader((source, "approved"))).resolve(tampered)

    assert error.value.code == "STANDARDS_RESOLUTION_BLOCKED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "../AGENTS.md"),
        ("commit_sha", "HEAD"),
        ("blob_digest", "sha256:not-a-digest"),
    ],
)
def test_source_ref_rejects_non_exact_identity(field: str, value: str) -> None:
    values: dict[str, Any] = {
        "repository": "dw-superapps",
        "commit_sha": _COMMIT_A,
        "path": "instructions/policy.md",
        "blob_digest": "sha256:" + "1" * 64,
    }
    values[field] = value

    with pytest.raises(StandardsResolutionError) as error:
        StandardsSourceRef(**values)

    assert error.value.code == "STANDARDS_PROFILE_INVALID"


def test_profile_requires_at_least_one_declared_source() -> None:
    with pytest.raises(StandardsResolutionError) as error:
        StandardsProfile.create(
            profile_id="taskcontroller.engineering",
            version="v1",
            sources=(),
        )

    assert error.value.code == "STANDARDS_PROFILE_INVALID"


def test_resolver_blocks_digest_drift_before_analyzer_callback() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    reader = _reader((source, "newer rules"))
    analyzer_calls: list[Any] = []
    blocked = None

    try:
        resolved = StandardsResolver(reader).resolve(_profile(source))
    except StandardsResolutionError as error:
        blocked = error
    else:
        analyzer_calls.append(resolved.session_context)

    assert blocked is not None
    assert blocked.code == "STANDARDS_RESOLUTION_BLOCKED"
    assert analyzer_calls == []
    assert reader.calls == [(_COMMIT_A, "instructions/policy.md")]


def test_canonical_source_manifest_has_stable_utf8_bytes_and_order() -> None:
    source_z = replace(_source(_COMMIT_A, "z/path.md", "A"), repository="z-repo")
    source_a = replace(_source(_COMMIT_B, "a/path.md", "B"), repository="a-repo")

    manifest = canonical_source_manifest(
        "taskcontroller.engineering", "v1", (source_z, source_a)
    )

    assert manifest["canonicalization"] == STANDARDS_MANIFEST_CANONICALIZATION
    assert [source["repository"] for source in manifest["sources"]] == [
        "a-repo",
        "z-repo",
    ]
    assert canonical_standards_bytes(
        "taskcontroller.engineering", "v1", (source_z, source_a)
    ) == (
        b'{"canonicalization":"dw-source-manifest-json/v1","profile_id":"taskcontroller.engineering",'
        b'"sources":[{"blob_digest":"sha256:df7e70e5021544f4834bbee64a9e3789febc4be81470df629cad6ddb03320a5c",'
        b'"commit_sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","path":"a/path.md","repository":"a-repo"},'
        b'{"blob_digest":"sha256:559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd",'
        b'"commit_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","path":"z/path.md","repository":"z-repo"}],"version":"v1"}'
    )
    assert canonical_profile_digest(
        "taskcontroller.engineering", "v1", (source_z, source_a)
    ) == "sha256:4868cddbed6dabdcba57f0ba42bcfcfd8d43661b7141ef62569424af5f3c3b00"


def test_canonical_profile_digest_is_identical_for_reordered_sources() -> None:
    first = _source(_COMMIT_A, "instructions/a.md", "A")
    second = _source(_COMMIT_B, "instructions/b.md", "B")

    left = canonical_profile_digest("taskcontroller.engineering", "v1", (first, second))
    right = canonical_profile_digest("taskcontroller.engineering", "v1", (second, first))

    assert left == right


def test_canonical_profile_digest_changes_deterministically_for_content_or_identity() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    changed_content = replace(
        source,
        blob_digest="sha256:" + hashlib.sha256(b"changed").hexdigest(),
    )
    changed_path = replace(source, path="instructions/other-policy.md")

    original = canonical_profile_digest("taskcontroller.engineering", "v1", (source,))
    assert canonical_profile_digest("taskcontroller.engineering", "v1", (source,)) == original
    assert canonical_profile_digest("taskcontroller.engineering", "v1", (changed_content,)) != original
    assert canonical_profile_digest("taskcontroller.engineering", "v1", (changed_path,)) != original


def test_profile_rejects_duplicate_source_identity_even_when_blob_digest_differs() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    substituted = replace(
        source,
        blob_digest="sha256:" + hashlib.sha256(b"substituted").hexdigest(),
    )

    with pytest.raises(StandardsResolutionError) as error:
        StandardsProfile.create(
            profile_id="taskcontroller.engineering",
            version="v1",
            sources=(source, substituted),
        )

    assert error.value.code == "STANDARDS_PROFILE_INVALID"
    assert "duplicate source identity" in str(error.value)


def test_canonical_standards_bytes_preserve_utf8_without_text_normalization() -> None:
    source = _source(_COMMIT_A, "instructions/café.md", "règles")
    decomposed = replace(source, path="instructions/cafe\u0301.md")
    encoded = canonical_standards_bytes("taskcontroller.engineering", "v1", (source,))

    assert "café.md".encode("utf-8") in encoded
    assert b"\\u00e9" not in encoded
    assert canonical_profile_digest(
        "taskcontroller.engineering", "v1", (decomposed,)
    ) != canonical_profile_digest("taskcontroller.engineering", "v1", (source,))
    assert "cafe\u0301.md".encode("utf-8") in canonical_standards_bytes(
        "taskcontroller.engineering", "v1", (decomposed,)
    )


def test_resolver_blocks_profile_digest_drift_before_materialization() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    profile = _profile(source)
    tampered = replace(profile, digest="sha256:" + "0" * 64)
    reader = _reader((source, "approved"))

    with pytest.raises(StandardsResolutionError) as error:
        StandardsResolver(reader).resolve(tampered)

    assert error.value.code == "STANDARDS_RESOLUTION_BLOCKED"
    assert reader.calls == []


def test_resolver_records_verified_materialization_manifest_before_session_use() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    resolved = StandardsResolver(_reader((source, "approved"))).resolve(_profile(source))

    receipt = resolved.receipt
    payload = receipt.to_dict()
    assert isinstance(receipt.materialized_sources[0], MaterializedSourceReceipt)
    assert payload["materialization_protocol"] == STANDARDS_MATERIALIZATION_PROTOCOL
    assert payload["materialized_sources"] == [
        {
            "source": source.to_dict(),
            "observed_digest": source.blob_digest,
            "byte_length": len(b"approved"),
        }
    ]
    assert payload["materialization_digest"].startswith("sha256:")
    repeated = StandardsResolver(_reader((source, "approved"))).resolve(_profile(source))
    assert repeated.receipt.materialization_digest == receipt.materialization_digest
    assert resolved.session_context.to_dict()["standards"]["materialization_digest"] == payload[
        "materialization_digest"
    ]


def test_materialization_receipt_and_instructions_are_immutable_after_reader_mutation() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")

    class MutableReader:
        def __init__(self) -> None:
            self.raw = b"approved"

        def read_exact(self, requested: StandardsSourceRef) -> bytes:
            assert requested == source
            return self.raw

    reader = MutableReader()
    resolved = StandardsResolver(reader).resolve(_profile(source))
    before = resolved.receipt.to_dict()
    reader.raw = b"substituted"

    assert resolved.instructions[0].content == "approved"
    assert resolved.receipt.to_dict() == before
    assert resolved.session_context.to_dict()["standards"] == before
