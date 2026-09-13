from __future__ import annotations

import hashlib

import pytest

from taskcontroller.execution.result_normalizer import (
    MAX_FINDINGS,
    ChildResultNormalizer,
    NormalizationStatus,
)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalizer() -> ChildResultNormalizer:
    return ChildResultNormalizer(
        child_contract_digest=_digest("child-contract"),
        source_digest=_digest("source"),
        lens="security",
        reviewer="agent-1",
    )


def _finding(*, finding_id: str = "finding-1", claim: str = "unsafe boundary") -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "severity": "major",
        "category": "security",
        "lens": "security",
        "claim": claim,
        "evidence_refs": ["artifact-1"],
        "recommendation": "tighten the boundary",
        "reviewer": "agent-1",
        "confidence": 0.9,
        "disposition": "OPEN",
        "conflict_group": None,
    }


def test_plain_text_output_becomes_digest_bound_artifact_without_raw_text() -> None:
    result = _normalizer().normalize("Review is complete")

    assert result.status is NormalizationStatus.SUCCEEDED
    assert result.failure is None
    assert result.findings == ()
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.digest == _digest("Review is complete")
    assert artifact.content_ref == f"inline:{artifact.digest}"
    assert artifact.provenance["child_contract_digest"] == _digest("child-contract")
    serialized = result.to_dict()
    assert "raw_output" not in serialized
    assert "transcript" not in serialized
    assert "Review is complete" not in str(serialized)


def test_structured_output_normalizes_artifact_and_finding_fields() -> None:
    raw = {
        "artifacts": [
            {
                "artifact_id": "artifact-1",
                "content": "evidence text",
                "media_type": "text/plain",
            }
        ],
        "findings": [_finding()],
    }

    result = _normalizer().normalize(raw)

    assert result.status is NormalizationStatus.SUCCEEDED
    assert result.artifacts[0].artifact_id == "artifact-1"
    assert result.findings[0].severity == "major"
    assert result.findings[0].evidence_refs == ("artifact-1",)
    assert result.findings[0].reviewer == "agent-1"
    assert result.to_dict()["findings"][0]["disposition"] == "OPEN"


def test_input_order_does_not_change_normalized_digest() -> None:
    raw_a = {
        "artifacts": [
            {"artifact_id": "artifact-1", "content": "one"},
            {"artifact_id": "artifact-2", "content": "two"},
        ],
        "findings": [
            _finding(finding_id="finding-1", claim="first"),
            _finding(finding_id="finding-2", claim="second"),
        ],
    }
    raw_b = {
        "artifacts": list(reversed(raw_a["artifacts"])),
        "findings": list(reversed(raw_a["findings"])),
    }

    first = _normalizer().normalize(raw_a)
    second = _normalizer().normalize(raw_b)

    assert first.status is NormalizationStatus.SUCCEEDED
    assert second.status is NormalizationStatus.SUCCEEDED
    assert first.normalization_digest == second.normalization_digest
    assert [item.artifact_id for item in first.artifacts] == ["artifact-1", "artifact-2"]
    assert [item.finding_id for item in first.findings] == ["finding-1", "finding-2"]


def test_missing_required_finding_is_explicit_needs_retry() -> None:
    result = _normalizer().normalize({"findings": [{"severity": "major"}]})

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.failure.code == "CHILD_OUTPUT_INVALID"
    assert result.failure.retryable is True
    assert result.artifacts == ()
    assert result.findings == ()
    assert result.raw_output_digest.startswith("sha256:")


def test_invalid_item_does_not_silently_keep_valid_siblings() -> None:
    raw = {
        "artifacts": [{"artifact_id": "artifact-1", "content": "valid"}, {"artifact_id": "bad"}],
        "findings": [_finding()],
    }

    result = _normalizer().normalize(raw)

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.artifacts == ()
    assert result.findings == ()


def test_unrecognized_top_level_fields_are_not_dropped() -> None:
    result = _normalizer().normalize({"findings": [], "model_private_reasoning": "secret"})

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.failure.code == "CHILD_OUTPUT_INVALID"
    assert "model_private_reasoning" not in result.failure.message


def test_child_reported_failure_is_preserved_as_failed_result() -> None:
    result = _normalizer().normalize(
        {"status": "FAILED", "failure_code": "PROVIDER_ERROR", "message": "adapter failed"}
    )

    assert result.status is NormalizationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "CHILD_REPORTED_FAILURE"
    assert result.failure.retryable is True
    assert result.artifacts == ()
    assert result.findings == ()
    assert "adapter failed" not in result.failure.message


def test_finding_without_id_gets_stable_content_derived_id() -> None:
    raw = {"findings": [{key: value for key, value in _finding().items() if key != "finding_id"}]}

    first = _normalizer().normalize(raw)
    second = _normalizer().normalize(raw)

    assert first.status is NormalizationStatus.SUCCEEDED
    assert first.findings[0].finding_id.startswith("finding-")
    assert first.normalization_digest == second.normalization_digest


def test_finding_count_limit_is_explicit_failure() -> None:
    findings = [_finding(finding_id=f"finding-{index}") for index in range(MAX_FINDINGS + 1)]

    result = _normalizer().normalize({"findings": findings})

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.failure.code == "CHILD_OUTPUT_LIMIT_EXCEEDED"
    assert result.artifacts == ()
    assert result.findings == ()


def test_invalid_child_binding_is_needs_retry_not_an_exception() -> None:
    result = ChildResultNormalizer(child_contract_digest="not-a-digest").normalize("text")

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.failure.code == "CHILD_BINDING_INVALID"


@pytest.mark.parametrize("raw", [None, [], 42, {"artifacts": [], "findings": []}])
def test_empty_or_unsupported_output_is_never_silently_accepted(raw: object) -> None:
    result = _normalizer().normalize(raw)

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.artifacts == ()
    assert result.findings == ()


def test_non_string_keys_fail_closed_without_leaking_a_type_error() -> None:
    result = _normalizer().normalize({1: "unsupported"})

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.failure.code == "CHILD_OUTPUT_INVALID"


def test_reported_failure_with_payload_is_not_silently_omitted() -> None:
    result = _normalizer().normalize(
        {"status": "FAILED", "artifacts": [{"content": "would be omitted"}]}
    )

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.failure.code == "CHILD_OUTPUT_INVALID"
    assert result.artifacts == ()


def test_oversized_plain_text_is_explicitly_rejected() -> None:
    result = _normalizer().normalize("x" * (256 * 1024 + 1))

    assert result.status is NormalizationStatus.NEEDS_RETRY
    assert result.failure is not None
    assert result.failure.code == "CHILD_OUTPUT_LIMIT_EXCEEDED"


def test_reviewer_defaults_to_bound_child_identity_when_not_supplied() -> None:
    finding = _finding()
    finding.pop("reviewer")
    result = ChildResultNormalizer(lens="security").normalize("child-7", {"findings": [finding]})

    assert result.status is NormalizationStatus.SUCCEEDED
    assert result.findings[0].reviewer == "child-7"
