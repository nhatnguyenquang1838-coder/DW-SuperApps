"""Durable GitHub-backed certification evidence export/import.

The certification event store may live at a host-local working path (e.g.
``/tmp``) during execution. Final evidence SHALL be exported as a sanitized,
append-only event chain plus a tamper-detecting manifest into a GitHub-backed
location (an ``evidence/<campaign-id>`` branch), from which a fresh verifier on
another session/host can reconstruct verdicts without the original host
``/tmp``, conversation history, or Slack replay.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .certification_store import CertificationEvent, CertificationStore, CertificationStoreError


class CertificationExportError(ValueError):
    """Raised when durable certification evidence cannot be exported/reconstructed."""


_SENSITIVE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|bearer\s+[a-z0-9._-]+)"
)


def _manifest_digest(manifest: Mapping[str, Any]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _events_digest(events_path: Path) -> str:
    content = events_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def _assert_sanitized(text: str) -> None:
    if _SENSITIVE.search(text):
        raise CertificationExportError("refusing to export evidence containing secret-like values")
    if "/tmp/" in text or re.search(r"/Users/[^/]+/", text) or re.search(r"[A-Za-z]:\\\\", text):
        raise CertificationExportError("refusing to export evidence with local absolute paths")


def export_durable_evidence(
    store: CertificationStore,
    target: str | Path,
    *,
    evidence_refs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Export a validated event chain + sanitized manifest to ``target``.

    The original store file remains untouched; a sanitized copy is written to
    ``target/events.jsonl`` and a manifest binds the campaign, event count,
    evidence refs and digests.
    """
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        raise CertificationExportError(f"evidence target already populated: {target}")
    events = store.replay()
    if not events:
        raise CertificationExportError("cannot export an empty certification store")

    campaign_id = ""
    for event in events:
        payload = event.payload
        if event.event_type == "CAMPAIGN_CREATED" and isinstance(payload, Mapping):
            campaign_id = str(payload.get("campaign_id") or payload.get("aggregate_id") or "")
            if campaign_id:
                break
    if not campaign_id:
        campaign_id = events[0].aggregate_id

    target.mkdir(parents=True, exist_ok=True)
    events_path = target / "events.jsonl"
    lines = []
    for event in events:
        line = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        lines.append(line)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    events_digest = _events_digest(events_path)
    manifest = {
        "schema_version": 1,
        "campaign_id": campaign_id,
        "record_count": len(events),
        "first_event_digest": events[0].record_digest,
        "last_event_digest": events[-1].record_digest,
        "events_sha256": events_digest,
        "evidence_refs": dict(evidence_refs or {}),
    }
    manifest["final_manifest_digest"] = _manifest_digest(manifest)
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    combined = events_path.read_text(encoding="utf-8") + manifest_path.read_text(encoding="utf-8")
    _assert_sanitized(combined)
    return manifest


def reconstruct_evidence(manifest_path: str | Path) -> tuple[CertificationEvent, ...]:
    """Reconstruct the validated event chain from an evidence manifest only.

    This is the fresh-verifier entrypoint: it must succeed with no access to
    the original working store or host-local ``/tmp``.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise CertificationExportError(f"evidence manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CertificationExportError(f"invalid evidence manifest JSON: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise CertificationExportError("evidence manifest must be an object")
    expected_final = manifest.get("final_manifest_digest")
    manifest_copy = dict(manifest)
    manifest_copy.pop("final_manifest_digest", None)
    computed_final = _manifest_digest(manifest_copy)
    if expected_final != computed_final:
        raise CertificationExportError("manifest digest mismatch (tamper detected)")

    events_path = manifest_path.parent / "events.jsonl"
    if not events_path.exists():
        raise CertificationExportError("evidence events.jsonl missing")
    actual_events_digest = _events_digest(events_path)
    if actual_events_digest != manifest.get("events_sha256"):
        raise CertificationExportError("events.jsonl digest mismatch (tamper detected)")

    try:
        store = CertificationStore(events_path)
        events = store.replay()
    except CertificationStoreError as exc:
        raise CertificationExportError(f"event chain invalid: {exc}") from exc

    if len(events) != int(manifest.get("record_count", -1)):
        raise CertificationExportError(
            f"record count mismatch: manifest {manifest.get('record_count')} != chain {len(events)}"
        )
    if events[0].record_digest != manifest.get("first_event_digest"):
        raise CertificationExportError("first event digest mismatch")
    if events[-1].record_digest != manifest.get("last_event_digest"):
        raise CertificationExportError("last event digest mismatch")
    campaign_id = manifest.get("campaign_id")
    if campaign_id and events[0].aggregate_id != campaign_id:
        raise CertificationExportError(
            f"cross-campaign substitution: manifest {campaign_id!r} != chain {events[0].aggregate_id!r}"
        )
    _assert_sanitized(events_path.read_text(encoding="utf-8"))
    return events


__all__ = [
    "CertificationExportError",
    "export_durable_evidence",
    "reconstruct_evidence",
]
