"""GitHub-backed durable export/import and fresh verification for Runtime Proving Lab.

The local CertificationStore may live anywhere (including a host-local temporary
workspace), but qualifying final evidence must be exported with an immutable
GitHub source binding.  The verifier reconstructs campaign truth solely from the
exported hash-chained event stream plus its manifest; it never scans branches or
uses Slack/Notion/transcript state.

SCRUM-725 GREEN: evidence binding has two independent identities:
  - intrinsic manifest binding: repository + ref + path + intrinsic hashes
    (events_sha256 + manifest_digest).  This is content-addressed and
    self-contained.
  - external retaining commit attestation: repository + ref + commit_sha + path.
    This is verified against the actual Git tree of the retaining commit.

The old circular self-binding (commit_sha embedded inside the manifest blob that
the commit itself retains) has been removed.  The verifier requires the external
attestation and checks it against real Git tree content.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
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
    """Intrinsic manifest binding: content-addressed, self-contained.

    Does NOT contain the retaining commit SHA (SCRUM-725).  The manifest is
    bound to repository + ref + path plus its own intrinsic hashes
    (events_sha256 + manifest_digest).
    """

    repository: str
    ref: str
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or _REPOSITORY.fullmatch(self.repository) is None:
            raise CertificationEvidenceError("repository must be owner/name")
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise CertificationEvidenceError("GitHub evidence ref is required")
        normalized_ref = self.ref.removeprefix("refs/heads/")
        if not normalized_ref.startswith("evidence/"):
            raise CertificationEvidenceError("GitHub evidence ref must be an evidence/* branch")
        object.__setattr__(self, "path", _validate_repo_path(self.path))

    def to_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "ref": self.ref,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GitHubEvidenceBinding":
        try:
            return cls(
                repository=str(payload["repository"]),
                ref=str(payload["ref"]),
                path=str(payload["path"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CertificationEvidenceError(f"invalid GitHub evidence binding: {exc}") from exc


@dataclass(frozen=True)
class GitHubRetainingCommitAttestation:
    """External retaining commit attestation: verified against actual Git tree.

    This is a SEPARATE identity from the manifest's intrinsic binding.  It is
    NOT embedded in the manifest (SCRUM-725).  The qualifier independently
    verifies this attestation against the actual commit tree at the supplied
    repository/ref/commit_sha/path.

    Durable identity only — no host-local paths.
    """

    repository: str
    ref: str
    commit_sha: str
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or _REPOSITORY.fullmatch(self.repository) is None:
            raise CertificationEvidenceError("attestation repository must be owner/name")
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise CertificationEvidenceError("GitHub evidence ref is required")
        normalized_ref = self.ref.removeprefix("refs/heads/")
        if not normalized_ref.startswith("evidence/"):
            raise CertificationEvidenceError("GitHub evidence ref must be an evidence/* branch")
        if not isinstance(self.commit_sha, str) or _SHA40.fullmatch(self.commit_sha) is None:
            raise CertificationEvidenceError("GitHub retaining commit_sha must be exact 40-hex")
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
    def from_dict(cls, payload: Mapping[str, Any]) -> "GitHubRetainingCommitAttestation":
        try:
            return cls(
                repository=str(payload["repository"]),
                ref=str(payload["ref"]),
                commit_sha=str(payload["commit_sha"]),
                path=str(payload["path"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CertificationEvidenceError(f"invalid retaining commit attestation: {exc}") from exc


@dataclass(frozen=True)
class FreshVerificationResult:
    binding: GitHubEvidenceBinding
    attestation: GitHubRetainingCommitAttestation
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
    """Intrinsic manifest core: binding (no commit_sha) + intrinsic hashes."""
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
    bound to the GitHub repository/ref/path that retains it (SCRUM-725: no
    commit_sha in the manifest binding — retaining commit is verified externally).
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


def verify_retaining_commit_attestation(
    attestation: GitHubRetainingCommitAttestation,
    bundle_root: str | Path,
    manifest: Mapping[str, Any],
) -> None:
    """Verify the external retaining commit attestation against actual Git content.

    Fail-closed: any mismatch raises CertificationEvidenceError.
    """
    repo_path = Path(bundle_root)
    if not (repo_path / ".git").exists():
        raise CertificationEvidenceError(
            f"retaining commit verification requires a real Git repository at {repo_path}"
        )

    # 1. Verify the attested commit exists and is a valid commit object
    try:
        commit_type = subprocess.run(
            ["git", "-C", str(repo_path), "cat-file", "-t", attestation.commit_sha],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise CertificationEvidenceError(
            f"retaining commit {attestation.commit_sha} not found in repository"
        ) from exc
    if commit_type != "commit":
        raise CertificationEvidenceError(
            f"retaining commit {attestation.commit_sha} is not a commit object ({commit_type})"
        )

    # 2. Verify the path exists in the commit tree
    relative_path = PurePosixPath(attestation.path)
    try:
        tree_entry = subprocess.run(
            ["git", "-C", str(repo_path), "ls-tree", "-r", "--name-only", attestation.commit_sha],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
    except subprocess.CalledProcessError as exc:
        raise CertificationEvidenceError(
            f"cannot list tree for commit {attestation.commit_sha}"
        ) from exc

    expected_files = {str(relative_path / _MANIFEST_NAME), str(relative_path / _EVENTS_NAME)}
    actual_files = set(tree_entry)
    missing = expected_files - actual_files
    if missing:
        raise CertificationEvidenceError(
            f"retaining commit {attestation.commit_sha} is missing expected files: {missing}"
        )

    # 3. Verify the manifest blob SHA-1 matches what's in the commit tree
    try:
        manifest_blob_sha = subprocess.run(
            ["git", "-C", str(repo_path), "ls-tree",
             "-r", "--object-only", attestation.commit_sha,
             str(relative_path / _MANIFEST_NAME)],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise CertificationEvidenceError(
            f"cannot get manifest blob SHA from commit {attestation.commit_sha}"
        ) from exc

    try:
        committed_manifest = subprocess.run(
            ["git", "-C", str(repo_path), "cat-file", "-p", manifest_blob_sha],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise CertificationEvidenceError(
            f"cannot read manifest blob {manifest_blob_sha} from commit {attestation.commit_sha}"
        ) from exc

    committed_manifest_obj = json.loads(committed_manifest)
    if committed_manifest_obj != manifest:
        raise CertificationEvidenceError(
            "manifest committed at retaining commit does not match the exported manifest"
        )

    # 4. Verify the events blob SHA-1 matches
    try:
        events_blob_sha = subprocess.run(
            ["git", "-C", str(repo_path), "ls-tree",
             "-r", "--object-only", attestation.commit_sha,
             str(relative_path / _EVENTS_NAME)],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise CertificationEvidenceError(
            f"cannot get events blob SHA from commit {attestation.commit_sha}"
        ) from exc

    events_path = Path(bundle_root) / relative_path / _EVENTS_NAME
    try:
        local_events_bytes = events_path.read_bytes()
    except OSError as exc:
        raise CertificationEvidenceError(f"cannot read local events file: {exc}") from exc
    expected_events_blob = hashlib.sha1(b"blob " + str(len(local_events_bytes)).encode() + b"\0" + local_events_bytes).hexdigest()
    if events_blob_sha != expected_events_blob:
        raise CertificationEvidenceError(
            f"events blob mismatch: committed={events_blob_sha}, expected={expected_events_blob}"
        )


def fresh_verify_campaign(
    destination: str | Path,
    campaign_id: str,
    attestation: GitHubRetainingCommitAttestation,
    git_repo_root: str | Path,
) -> FreshVerificationResult:
    """Reconstruct campaign truth from the GitHub-backed bundle + external attestation.

    Fail-closed: attestation + git_repo_root are both mandatory for qualifying
    evidence.  The verifier does NOT trust the manifest's self-claims about
    retaining commit identity.
    """
    if not isinstance(campaign_id, str) or not campaign_id.strip():
        raise CertificationEvidenceError("campaign_id is required")
    if not isinstance(attestation, GitHubRetainingCommitAttestation):
        raise CertificationEvidenceError("GitHubRetainingCommitAttestation required for qualifying evidence")
    git_repo_root = Path(git_repo_root)
    if not git_repo_root.is_dir() or not (git_repo_root / ".git").exists():
        raise CertificationEvidenceError(
            f"qualifying verification requires git_repo_root at {git_repo_root}"
        )

    binding, events_path, events, manifest = _load_verified_bundle(destination)

    # Mandatory external retaining commit attestation (SCRUM-725)
    verify_retaining_commit_attestation(attestation, git_repo_root, manifest)

    # Cross-check: attestation repo/ref/path must match manifest binding
    if (attestation.repository != binding.repository
            or attestation.ref != binding.ref
            or attestation.path != binding.path):
        raise CertificationEvidenceError(
            "retaining commit attestation repository/ref/path does not match manifest binding"
        )

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
        attestation=attestation,
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
    "GitHubRetainingCommitAttestation",
    "export_github_backed_evidence",
    "fresh_verify_campaign",
    "verify_retaining_commit_attestation",
]
