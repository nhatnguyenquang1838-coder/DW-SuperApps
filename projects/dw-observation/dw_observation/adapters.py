"""Read-only adapters for dw-observation.

These adapters only *read* external state and emit RunProjectionEvent records.
They never mutate TaskController, GWC, governance, Slack, or any repo.

Adapters are intentionally dependency-light:
  - TaskControllerAdapter: parses a structured run-log dict/JSON (NOT Slack text).
  - GwcAdapter: reads gwc governance artifacts from a local checkout path
    (read-only filesystem access to the bound submodule).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .events import RunProjectionEvent


class TaskControllerAdapter:
    """Reads a structured TaskController run log (JSON/dict, not Slack).

    Input contract (v1): a mapping with `run_id`, optional `dag_nodes`, and a
    list of `events` each matching RunProjectionEvent.from_dict fields.
    """

    def __init__(self, source: Optional[Any] = None) -> None:
        self._source = source

    def from_run_log(self, run_log: Dict[str, Any]) -> List[RunProjectionEvent]:
        run_id = run_log.get("run_id")
        raw_events = run_log.get("events", [])
        out: List[RunProjectionEvent] = []
        for i, raw in enumerate(raw_events):
            try:
                ev = RunProjectionEvent.from_dict(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"event[{i}] invalid: {exc}") from exc
            # inherit run_id when not set on the event
            if ev.run_id is None and run_id is not None:
                ev = RunProjectionEvent(
                    kind=ev.kind,
                    ts=ev.ts,
                    seq=ev.seq,
                    run_id=run_id,
                    node=ev.node,
                    gate=ev.gate,
                    actor=ev.actor,
                    data=ev.data,
                )
            out.append(ev)
        return out

    def from_json(self, text: str) -> List[RunProjectionEvent]:
        return self.from_run_log(json.loads(text))


class GwcAdapter:
    """Reads gwc governance artifacts from a local checkout (read-only).

    Does NOT clone, fetch, push, or mutate the gwc repository. It reads files
    under the provided `gwc_root` path and emits projection observations.
    """

    def __init__(self, gwc_root: str | Path) -> None:
        self.gwc_root = Path(gwc_root)
        if not self.gwc_root.exists():
            raise FileNotFoundError(f"gwc checkout not found: {self.gwc_root}")

    def read_gate_states(self, run_id: Optional[str] = None) -> List[RunProjectionEvent]:
        """Emit gate_approved/gate_released observations for gwc fastlane
        envelopes found under `.gwc/tasks/**` (read-only scan).

        This is a *projection* only; it does not validate or approve anything.
        """
        out: List[RunProjectionEvent] = []
        seq = 0
        # Scan gwc task directories for any approval envelope artifacts.
        tasks_dir = self.gwc_root / ".gwc" / "tasks"
        if not tasks_dir.exists():
            return out
        for env in sorted(tasks_dir.glob("*/g4/*.yaml")):
            seq += 1
            out.append(
                RunProjectionEvent(
                    kind="gate_approved",
                    ts="1970-01-01T00:00:00Z",  # placeholder; real ts from artifact
                    seq=seq,
                    run_id=run_id,
                    gate="G4",
                    actor="gwc-fastlane",
                    data={"artifact": str(env.relative_to(self.gwc_root))},
                )
            )
        return out
