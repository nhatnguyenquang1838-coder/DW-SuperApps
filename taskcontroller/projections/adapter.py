"""WP6 S4 Slack projection adapter (NO GWC, fake transport in tests).

Bridges WP5 control-plane + projection to Slack as a concrete projection target.
Slack is projection/interaction ONLY — never source of runtime truth. The adapter:

- materialize(run_id): builds the projection from the live store, renders the
  ROOT card, and applies it via the transport. First time for a task/target =>
  CREATE_ROOT + bind (exactly one root). Subsequent calls => UPDATE_ROOT of the
  SAME root (never a new root), even across session/model/executor rotation.
- apply_action(run_id, action, ...): maps the UI action. Control actions go
  through WP5 CAS (stale version is rejected by WP5 and is NOT masked as success;
  on success the root is re-materialized). Authority actions (APPROVE/MERGE)
  produce a thread-only AUTHORITY_REQUIRED signal and never mutate the runtime.
- emit_thread(run_id, kind, text): REPLY_THREAD event log on the SAME root.

The hard invariant is enforced by the binding registry: a second root for the
same task/target raises DuplicateRootError and produces ZERO transport side effect.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.controlplane.errors import (
    ControlPlaneError,
    StaleVersionError,
    TerminalRunError,
)
from taskcontroller.controlplane.intents import ControlIntent
from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.projections.actions import map_action
from taskcontroller.projections.binding import BindingRegistry, DuplicateRootError
from taskcontroller.projections.domain import build_view
from taskcontroller.projections.slack_renderer import render_root_op, render_thread_op
from taskcontroller.projections.transport import FakeSlackTransport

_CHANNEL = "slack"
_TARGET = "slack"


class SlackProjectionAdapter:
    def __init__(self, control_plane: ControlPlane, transport: FakeSlackTransport) -> None:
        self._cp = control_plane
        self._transport = transport
        self._registry = BindingRegistry()

    def _key(self, run_id: str) -> str:
        return f"{run_id}#{_TARGET}"

    def materialize(
        self,
        run_id: str,
        session_id: str | None = None,
        model: str | None = None,
        executor: str | None = None,
        token_usage: int | None = None,
    ) -> dict[str, Any]:
        """Render + apply the ROOT card for a run (CREATE first time, else UPDATE)."""
        current = self._cp._store.get_run(run_id)
        if current is None:
            raise ControlPlaneError(f"no such run: {run_id!r}")
        proj = RunProjection.from_versioned(current)
        view = build_view(proj, session_id=session_id, model=model, executor=executor, token_usage=token_usage)
        key = self._key(run_id)
        binding = self._registry.lookup(key)

        if binding is None:
            # allocate a single root identity for this task/target, then bind
            allocated_root = f"root.{run_id}"
            binding = self._registry.bind(key, _CHANNEL, allocated_root,
                                           session_id=session_id, model=model, executor=executor)
            op = render_root_op(view, key, _CHANNEL, None)
            op = op.__class__(op.op, op.binding_key, op.channel, allocated_root, op.payload, op.authority_required)
            self._transport.apply(op.to_dict())
        else:
            # rotation: refresh metadata (content only), UPDATE same root
            self._registry.update_metadata(key, session_id=session_id, model=model, executor=executor)
            op = render_root_op(view, key, _CHANNEL, binding)
            self._transport.apply(op.to_dict())
        return proj.to_dict()

    def apply_action(
        self,
        run_id: str,
        action: str,
        expected_version: int,
        command_id: str | None = None,
        new_plan_version: str | None = None,
    ) -> dict[str, Any]:
        """Apply a UI action. Control goes through WP5 CAS; authority is thread-only."""
        key = self._key(run_id)
        binding = self._registry.lookup(key)
        mapping = map_action(action, run_id, expected_version, command_id, new_plan_version)

        if mapping.authority_result is not None:
            # APPROVE/MERGE: never mutate runtime; thread-only authority signal
            if binding is not None:
                op = render_thread_op(
                    key, _CHANNEL, binding, "AUTHORITY_REQUIRED",
                    f"{action} requires external authority", authority_required=True,
                )
                self._transport.apply(op.to_dict())
            return {"authority_required": True, "action": action, "run_id": run_id}

        # control action -> WP5 CAS
        intent: ControlIntent = mapping.control_intent
        try:
            result, proj = self._cp.command(intent)
        except (StaleVersionError, TerminalRunError, ControlPlaneError) as exc:
            # do NOT update root as success; emit thread error only
            if binding is not None:
                op = render_thread_op(key, _CHANNEL, binding, "COMMAND_REJECTED", str(exc))
                self._transport.apply(op.to_dict())
            return {"accepted": False, "error": str(exc), "action": action}

        # success: re-materialize root (UPDATE, same root) + thread command log
        view = build_view(proj)
        op_root = render_root_op(view, key, _CHANNEL, binding)
        self._transport.apply(op_root.to_dict())
        if binding is not None:
            op_thread = render_thread_op(key, _CHANNEL, binding, "CONTROLLER_COMMAND", f"{action} accepted")
            self._transport.apply(op_thread.to_dict())
        return {"accepted": True, "action": action, "new_status": result.status}

    def emit_thread(self, run_id: str, kind: str, text: str) -> None:
        """REPLY_THREAD event log on the SAME root (never a new root)."""
        key = self._key(run_id)
        binding = self._registry.lookup(key)
        if binding is None:
            raise ControlPlaneError(f"no binding for {key!r}; bind via materialize first")
        op = render_thread_op(key, _CHANNEL, binding, kind, text)
        self._transport.apply(op.to_dict())

    def attempt_second_root(self, run_id: str) -> None:
        """Attempting a 2nd root for the same task/target must fail closed."""
        key = self._key(run_id)
        # simulate a fresh allocation attempt; registry must refuse
        self._registry.bind(key, _CHANNEL, f"root.EVIL.{run_id}")
