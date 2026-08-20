"""Read-only adapters for dw-observation.

These adapters only *read* external state and emit RunProjectionEvent (v1)
records. They never mutate TaskController, GWC, governance, Slack, or any repo.

Adapter contract (v1 envelope):
  - Preserve the exact source identity: ``source_system`` + ``source_event_id``.
  - Preserve the deterministic ``sequence`` from the source record.
  - Preserve ``outcome``, ``before``/``after``, ``evidence_refs``,
    ``authority_ref``, and ``source_digest``.
  - Never invent a TC gate; gates are taken verbatim from source artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .events import RunProjectionEvent, compute_digest


class TaskControllerAdapter:
    """Reads a structured TaskController run log (JSON/dict, not Slack).

    Input contract (v1): a mapping with ``run_id`` and a list of ``events``.
    Each event may be expressed either as a *legacy* short form
    (``kind/ts/seq/run_id/node/gate/actor/data``) or as a full v1 envelope.
    Legacy fields are normalized into the explicit v1 envelope so the
    canonical model is always the explicit one.
    """

    def __init__(self, source: Optional[Any] = None) -> None:
        self._source = source

    def from_run_log(self, run_log: Dict[str, Any]) -> List[RunProjectionEvent]:
        run_id = run_log.get("run_id")
        raw_events: List[Dict[str, Any]] = run_log.get("events", [])
        out: List[RunProjectionEvent] = []
        for i, raw in enumerate(raw_events):
            try:
                ev = self._normalize(run_id, raw, i)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"event[{i}] invalid: {exc}") from exc
            out.append(ev)
        return out

    def from_json(self, text: str) -> List[RunProjectionEvent]:
        return self.from_run_log(json.loads(text))

    def _normalize(
        self, run_id: Optional[str], raw: Dict[str, Any], index: int
    ) -> RunProjectionEvent:
        # Already a full v1 envelope?
        if "occurred_at" in raw or "event_type" in raw:
            digest = raw.get("source_digest") or compute_digest(raw)
            return RunProjectionEvent.from_dict(
                {
                    **raw,
                    "run_id": raw.get("run_id") or run_id,
                    "source_system": raw.get("source_system", "taskcontroller"),
                    "source_event_id": raw.get("source_event_id", f"tc:{run_id}:{index}"),
                    "source_digest": digest,
                }
            )

        # Legacy short form -> explicit v1 envelope.
        kind = raw.get("kind", "projection_snapshot")
        ts = raw.get("ts", "1970-01-01T00:00:00Z")
        seq = raw.get("seq", index)
        node = raw.get("node")
        gate = raw.get("gate")
        actor = raw.get("actor")
        data = raw.get("data", {}) or {}

        # Map legacy kind -> event_type/outcome.
        event_type = kind
        outcome = data.get("outcome")
        if kind == "run_started":
            outcome = outcome or "started"
        elif kind == "gate_approved":
            outcome = outcome or "approved"
        elif kind == "gate_released":
            outcome = outcome or "released"
        elif kind == "node_progress":
            outcome = outcome or data.get("status")

        summary = data.get("summary") or _legacy_summary(kind, gate, node, data)

        evidence_refs: List[str] = []
        if data.get("artifact"):
            evidence_refs.append(str(data["artifact"]))
        authority_ref = data.get("authority_ref") or data.get("scope_sha256")

        digest = compute_digest(raw)
        return RunProjectionEvent(
            run_id=run_id or raw.get("run_id"),
            sequence=seq,
            source_system="taskcontroller",
            source_event_id=f"tc:{run_id}:{index}",
            occurred_at=ts,
            gate=gate,
            node_id=node,
            event_type=event_type,
            outcome=outcome,
            actor=actor,
            summary=summary,
            before=data.get("before"),
            after=data.get("after"),
            evidence_refs=evidence_refs,
            authority_ref=authority_ref,
            source_digest=digest,
        )


def _legacy_summary(kind: str, gate: Optional[str], node: Optional[str], data: Dict[str, Any]) -> str:
    if kind == "run_started":
        return f"Run started (jira={data.get('jira')}, node={data.get('node')})"
    if kind == "gate_approved":
        return f"Gate {gate} approved"
    if kind == "gate_released":
        return f"Gate {gate} released ({data.get('release')})"
    if kind == "node_progress":
        return f"Node {node} -> {data.get('status')}"
    if kind == "projection_snapshot":
        return "Projection snapshot captured"
    return kind


class GwcAdapter:
    """Reads gwc governance artifacts from a local checkout (read-only).

    Does NOT clone, fetch, push, or mutate the gwc repository. It reads files
    under the provided ``gwc_root`` path and emits projection observations as
    v1 events that preserve the source artifact identity and authority.
    """

    def __init__(self, gwc_root: str | Path) -> None:
        self.gwc_root = Path(gwc_root)
        if not self.gwc_root.exists():
            raise FileNotFoundError(f"gwc checkout not found: {self.gwc_root}")

    def read_gate_states(self, run_id: Optional[str] = None) -> List[RunProjectionEvent]:
        """Emit gate_approved observations for gwc fastlane envelopes found
        under ``.gwc/tasks/**`` (read-only scan).

        This is a *projection* only; it does not validate or approve anything.
        """
        out: List[RunProjectionEvent] = []
        tasks_dir = self.gwc_root / ".gwc" / "tasks"
        if not tasks_dir.exists():
            return out
        for seq, env in enumerate(sorted(tasks_dir.glob("*/g4/*.yaml")), start=1):
            rel = str(env.relative_to(self.gwc_root))
            out.append(
                RunProjectionEvent(
                    run_id=run_id,
                    sequence=seq,
                    source_system="gwc",
                    source_event_id=f"gwc:{rel}",
                    occurred_at="1970-01-01T00:00:00Z",  # placeholder; real ts from artifact
                    gate="G4",
                    event_type="gate_approved",
                    outcome="approved",
                    actor="gwc-fastlane",
                    summary=f"GWC G4 artifact observed: {rel}",
                    evidence_refs=[rel],
                    authority_ref=None,
                    source_digest=compute_digest({"artifact": rel}),
                )
            )
        return out
