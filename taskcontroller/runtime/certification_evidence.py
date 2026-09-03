"""GitHub-backed durable export/import and fresh verification for Runtime Proving Lab.

The local CertificationStore may live anywhere (including a host-local temporary
workspace), but qualifying final evidence must be exported with an immutable
GitHub source binding.  The verifier reconstructs campaign truth solely from the
exported hash-chained event stream plus its manifest; it never scans branches or
uses Slack/Notion/transcript state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from .certification_models import CertificationCampaign
from .certification_stability import W8StabilityResult, evaluate_w8_stability
from .certification_store import CertificationStore, CertificationStoreError
from .live_certification_harness import LiveCertificationError, LiveCertificationHarness


_SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MANIFEST_NAME = "manifest.json"
_EVENTS_NAME = "campaign.events.jsonl"


class CertificationEvidenceError(ValueError):
    """Raised when durable GitHub-backed evidence cannot be trusted."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _validate_repo_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CertificationEvidenceError("GitHub evidence path is required")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise CertificationEvidenceError("GitHub evidence path must be safe and repository-relative")
    if not path.parts or path.parts[0] != "evidence":
        raise CertificationEvidenceError("GitHub evidence path must live under evidence/")
    return path.as_posix()


@dataclass(frozen=True)
class GitHubEvidenceBinding:
    repository: str
    ref: str
    commit_sha: str
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or _REPOSITORY.fullmatch(self.repository) is None:
            raise CertificationEvidenceError("repository must be owner/name")
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise CertificationEvidenceError("GitHub evidence ref is required")
        normalized_ref = self.ref.removeprefix("refs/heads/")
        if not normalized_ref.startswith("evidence/"):
            raise CertificationEvidenceError("GitHub evidence ref must be an evidence/* branch")
        if not isinstance(self.commit_sha, str) or _SHA40.fullmatch(self.commit_sha) is None:
            raise CertificationEvidenceError("GitHub evidence commit_sha must be exact 40-hex")
        object.__setattr__(self, "commit_sha", self.commit_sha.lower())
        object.__setattr__(self, "path", _validate_repo_path(self.path))

    def to_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "ref": self.ref,
            "commit_sha": self.commit_sha,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GitHubEvidenceBinding":
        try:
            return cls(
                repository=str(payload["repository"]),
                ref=str(payload["ref"]),
                commit_sha=str(payload["commit_sha"]),
                path=str(payload["path"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CertificationEvidenceError(f"invalid GitHub evidence binding: {exc}") from exc


@dataclass(frozen=True)
class FreshVerificationResult:
    binding: GitHubEvidenceBinding
    campaign: CertificationCampaign
    run_ids: tuple[str, ...]
    execution_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    branch_ownership: Mapping[str, str]
    w8_stability: W8StabilityResult
    event_count: int
    terminal_record_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "branch_ownership", MappingProxyType(dict(self.branch_ownership)))


def _serialize_events(store: CertificationStore) -> bytes:
    events = store.replay()
    return b"".join(
        _canonical_json(event.to_dict()) + b"\n"
        for event in events
    )


def _manifest_core(
    *,
    binding: GitHubEvidenceBinding,
    events_sha256: str,
    event_count: int,
    terminal_record_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "github-backed-certification-evidence",
        "binding": binding.to_dict(),
        "events_file": _EVENTS_NAME,
        "events_sha256": events_sha256,
        "event_count": event_count,
        "terminal_record_digest": terminal_record_digest,
    }


def export_github_backed_evidence(
    source_store: str | Path,
    destination: str | Path,
    binding: GitHubEvidenceBinding,
) -> Path:
    """Materialize a deterministic evidence bundle ready to commit to binding.path.

    This function deliberately does not push/commit. Repository mutation remains
    a governed outer action. The bundle itself is self-verifying and explicitly
    bound to the GitHub repository/ref/commit/path that retains it.
    """
    if not isinstance(binding, GitHubEvidenceBinding):
        raise CertificationEvidenceError("GitHubEvidenceBinding required")
    source = Path(source_store)
    try:
        store = CertificationStore(source)
        events = store.replay()
    except (OSError, CertificationStoreError) as exc:
        raise CertificationEvidenceError(f"source certification store is invalid: {exc}") from exc
    if not events:
        raise CertificationEvidenceError("cannot export an empty certification event chain")

    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    events_bytes = _serialize_events(store)
    events_path = destination_path / _EVENTS_NAME
    try:
        with events_path.open("wb") as handle:
            handle.write(events_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise CertificationEvidenceError(f"cannot write exported event chain: {exc}") from exc

    # Re-parse the exported bytes before creating the manifest. This proves the
    # export itself did not corrupt the source hash chain.
    try:
        exported = CertificationStore(events_path).replay()
    except CertificationStoreError as exc:
        raise CertificationEvidenceError(f"exported event chain is invalid: {exc}") from exc

    core = _manifest_core(
        binding=binding,
        events_sha256=_sha256(events_bytes),
        event_count=len(exported),
        terminal_record_digest=exported[-1].record_digest,
    )
    manifest = dict(core)
    manifest["manifest_digest"] = _sha256(_canonical_json(core))
    manifest_path = destination_path / _MANIFEST_NAME
    try:
        with manifest_path.open("wb") as handle:
            handle.write(_canonical_json(manifest) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise CertificationEvidenceError(f"cannot write evidence manifest: {exc}") from exc
    return manifest_path


def _load_verified_bundle(destination: str | Path) -> tuple[GitHubEvidenceBinding, Path, tuple[Any, ...], dict[str, Any]]:
    root = Path(destination)
    manifest_path = root / _MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificationEvidenceError(f"cannot read evidence manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CertificationEvidenceError("evidence manifest must be an object")
    if manifest.get("schema_version") != 1 or manifest.get("artifact_type") != "github-backed-certification-evidence":
        raise CertificationEvidenceError("unsupported evidence manifest schema/type")
    try:
        binding = GitHubEvidenceBinding.from_dict(manifest["binding"])
    except KeyError as exc:
        raise CertificationEvidenceError("manifest binding is required") from exc
    events_file = manifest.get("events_file")
    if events_file != _EVENTS_NAME:
        raise CertificationEvidenceError("manifest events_file is not canonical")

    supplied_manifest_digest = manifest.get("manifest_digest")
    core = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if supplied_manifest_digest != _sha256(_canonical_json(core)):
        raise CertificationEvidenceError("evidence manifest digest mismatch")

    events_path = root / _EVENTS_NAME
    try:
        events_bytes = events_path.read_bytes()
    except OSError as exc:
        raise CertificationEvidenceError(f"cannot read exported event chain: {exc}") from exc
    if manifest.get("events_sha256") != _sha256(events_bytes):
        raise CertificationEvidenceError("exported event-chain SHA256 mismatch")
    try:
        events = CertificationStore(events_path).replay()
    except CertificationStoreError as exc:
        raise CertificationEvidenceError(f"exported event chain failed verification: {exc}") from exc
    if not events:
        raise CertificationEvidenceError("exported event chain is empty")
    if manifest.get("event_count") != len(events):
        raise CertificationEvidenceError("evidence event_count mismatch")
    if manifest.get("terminal_record_digest") != events[-1].record_digest:
        raise CertificationEvidenceError("terminal record digest mismatch")
    return binding, events_path, events, manifest


def fresh_verify_campaign(destination: str | Path, campaign_id: str) -> FreshVerificationResult:
    """Reconstruct campaign truth from the GitHub-backed bundle only."""
    if not isinstance(campaign_id, str) or not campaign_id.strip():
        raise CertificationEvidenceError("campaign_id is required")
    binding, events_path, events, _manifest = _load_verified_bundle(destination)
    try:
        harness = LiveCertificationHarness(store=events_path)
        campaign = harness.get_campaign(campaign_id)
        runs = harness.list_campaign_runs(campaign_id)
        findings = harness.list_campaign_findings(campaign_id)
        ownership = harness.get_campaign_branch_ownership(campaign_id)
    except LiveCertificationError as exc:
        raise CertificationEvidenceError(f"fresh campaign reconstruction failed: {exc}") from exc
    if not runs:
        raise CertificationEvidenceError("fresh verifier found no campaign TestRuns")
    execution_ids: list[str] = []
    for run in runs:
        if run.verdict in {"PASS", "FAIL"}:
            if run.execution_receipt is None:
                raise CertificationEvidenceError(
                    f"terminal run {run.run_id!r} has no ExecutionReceipt"
                )
            execution_ids.append(run.execution_receipt.execution_id)
    stability = evaluate_w8_stability(runs, findings)
    return FreshVerificationResult(
        binding=binding,
        campaign=campaign,
        run_ids=tuple(run.run_id for run in runs),
        execution_ids=tuple(execution_ids),
        finding_ids=tuple(finding.finding_id for finding in findings),
        branch_ownership=ownership,
        w8_stability=stability,
        event_count=len(events),
        terminal_record_digest=events[-1].record_digest,
    )


__all__ = [
    "CertificationEvidenceError",
    "FreshVerificationResult",
    "GitHubEvidenceBinding",
    "export_github_backed_evidence",
    "fresh_verify_campaign",
]
