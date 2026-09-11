"""TC-MBX-403: exact standards profile resolution and session materialization."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any

import pytest

from taskcontroller.standards import (
    StandardsProfile,
    StandardsResolutionError,
    StandardsResolver,
    StandardsSourceRef,
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

    assert error.value.code == "STANDARDS_SOURCE_DIGEST_MISMATCH"
    assert "instructions/policy.md" in str(error.value)


def test_resolver_rejects_profile_digest_mismatch_after_exact_sources_load() -> None:
    source = _source(_COMMIT_A, "instructions/policy.md", "approved")
    profile = _profile(source)
    tampered = replace(profile, digest="sha256:" + "0" * 64)

    with pytest.raises(StandardsResolutionError) as error:
        StandardsResolver(_reader((source, "approved"))).resolve(tampered)

    assert error.value.code == "STANDARDS_PROFILE_DIGEST_MISMATCH"


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
