"""WP7 S2 vertical host pack facade (NO GWC).

Composes existing layers WITHOUT creating a new source of truth or duplicating
their authority:

- materialize()              -> WP6 projection (one root, restart-safe)
- route_and_dispatch()       -> WP3 routing + WP4 dispatch only
- forward_signal()           -> WP2 EventRouter (trusted adapter signal)
- controller_action()        -> WP5 control plane via WP6 action mapping
- rotate_executor/session/model -> metadata update + UPDATE_ROOT only
- checkpoint_host_state() / restore_host_state() -> binding restored before next materialize

The host NEVER mutates run/node state directly; every state change goes through
the composed layer's own authority (WP2 CAS, WP5 CAS, WP4 fabric preflight).
Host/session/model/executor rotation is projection metadata, not a semantic human
event, so it updates the existing RootCard without adding thread chatter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.facade import AuditFacade, NoOpAuditFacade
from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.execution.orchestrator import (
    forward_signal_to_router,
    route_and_dispatch,
    signal_to_event,
)
from taskcontroller.packs.host_state import (
    DEFAULT_EXECUTOR_PROFILE,
    TaskControllerHostConfig,
    TaskControllerHostState,
)
from taskcontroller.projections.adapter import SlackProjectionAdapter
from taskcontroller.projections.binding import BindingRegistry, DuplicateRootError
from taskcontroller.projections.transport import FakeSlackTransport


class SlackTaskControllerPack:
    """One host-facing workflow over WP2..WP6, restart-safe by construction."""

    def __init__(
        self,
        config: TaskControllerHostConfig,
        control_plane: ControlPlane,
        transport: FakeSlackTransport,
        host_state: TaskControllerHostState | None = None,
        audit: AuditFacade | NoOpAuditFacade | None = None,
    ) -> None:
        self._config = config
        self._cp = control_plane
        self._transport = transport
        self._audit = audit or NoOpAuditFacade()
        # restart-safe: restore the binding registry from host state BEFORE any
        # materialization. This is the core invariant against duplicate roots.
        # The host owns the registry and shares the SAME object with the adapter
        # (no private-field reach-through).
        registry = (
            BindingRegistry.from_snapshot(host_state.binding_snapshot)
            if host_state is not None
            else BindingRegistry()
        )
        self._registry = registry  # host-owned, authoritative root-identity source
        self._adapter = SlackProjectionAdapter(control_plane, transport, registry)
        self._state = host_state or TaskControllerHostState(
            config=config, binding_snapshot=registry.snapshot()
        )

    def _metadata(self) -> dict[str, Any]:
        return {
            "session_id": self._state.session_id,
            "model": self._state.model,
            "executor": self._state.executor,
        }

    def _audit_event(
        self,
        decision_kind: str,
        payload_summary: str,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        event = AuditEvent(
            event_id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=self._config.run_id,
            source="host_pack",
            decision_kind=decision_kind,
            payload_summary=payload_summary,
            before=before or {},
            after=after or {},
        )
        self._audit.record(self._config.run_id, event)

    def _capture_binding_snapshot(self) -> None:
        """Persist adapter binding identity into host state without changing metadata."""
        self._state = TaskControllerHostState(
            config=self._state.config,
            binding_snapshot=self._adapter.binding_snapshot(),
            session_id=self._state.session_id,
            model=self._state.model,
            executor=self._state.executor,
            checkpoint_version=self._state.checkpoint_version,
        )

    # -- projection (WP6) --------------------------------------------------
    def materialize(self, session_id=None, model=None, executor=None) -> dict[str, Any]:
        before = self._metadata()
        # refresh mutable metadata from the latest host state
        if session_id is not None:
            self._state = self._state.with_metadata(session_id=session_id, model=model, executor=executor)
        proj = self._adapter.materialize(
            self._config.run_id,
            session_id=self._state.session_id,
            model=self._state.model,
            executor=self._state.executor,
        )
        # capture any binding the adapter created/updated into host state so the
        # next checkpoint persists it (restart-safe root identity)
        self._capture_binding_snapshot()
        self._audit_event(
            "HOST_MATERIALIZED",
            f"materialize run={self._config.run_id}",
            before=before,
            after={**self._metadata(), "checkpoint_version": self._state.checkpoint_version},
        )
        return proj

    # -- routing + execution (WP3 + WP4) -----------------------------------
    def route_and_dispatch(self, route_registry, request, receipt_id, lease_mgr,
                           adapter_registry, node_id, now, accepted_at=None,
                           command_id=None, adapter_key=None):
        # pure WP3 route() -> WP4 dispatch; no host authority duplication
        return route_and_dispatch(
            route_registry, request, receipt_id, lease_mgr, adapter_registry,
            self._config.run_id, node_id, now, accepted_at=accepted_at,
            command_id=command_id, adapter_key=adapter_key,
        )

    # -- trusted adapter signal -> WP2 EventRouter -------------------------
    def forward_signal(self, signal, router, store) -> Any:
        # WP2 remains the sole acceptance authority for adapter signals
        return forward_signal_to_router(signal, router, store)

    def signal_to_event(self, signal):
        return signal_to_event(signal)

    # -- control plane (WP5) via WP6 action mapping -------------------------
    def controller_action(self, action, expected_version, command_id=None,
                          new_plan_version=None) -> dict[str, Any]:
        result = self._adapter.apply_action(
            self._config.run_id, action, expected_version, command_id, new_plan_version
        )
        result_summary = (
            {"result_keys": sorted(str(key) for key in result.keys())}
            if isinstance(result, dict)
            else {"result_type": type(result).__name__}
        )
        self._audit_event(
            "HOST_CONTROLLER_ACTION",
            f"controller action run={self._config.run_id} action={action}",
            before={"action": action, "expected_version": expected_version},
            after=result_summary,
        )
        return result

    # -- rotation ----------------------------------------------------------
    def rotate(self, session_id=None, model=None, executor=None) -> None:
        """Rotate host metadata and refresh the SAME RootCard without thread spam."""
        before = self._metadata()
        self._state = self._state.with_metadata(
            session_id=session_id, model=model, executor=executor
        )
        # Rotation is internal projection metadata. If a RootCard already exists,
        # render an UPDATE_ROOT of that same binding. It is not a semantic human
        # timeline event and therefore emits no REPLY_THREAD.
        if self._registry.has(self._config.binding_key()):
            self._adapter.materialize(
                self._config.run_id,
                session_id=self._state.session_id,
                model=self._state.model,
                executor=self._state.executor,
            )
            self._capture_binding_snapshot()
        self._audit_event(
            "HOST_ROTATED",
            f"rotate run={self._config.run_id}",
            before=before,
            after=self._metadata(),
        )

    # -- checkpoint / restore (restart-safe) -------------------------------
    def checkpoint_host_state(self) -> TaskControllerHostState:
        previous_version = self._state.checkpoint_version
        snapshot = self._adapter.binding_snapshot()
        self._state = TaskControllerHostState(
            config=self._state.config,
            binding_snapshot=snapshot,
            session_id=self._state.session_id,
            model=self._state.model,
            executor=self._state.executor,
            checkpoint_version=previous_version + 1,
        )
        self._audit_event(
            "HOST_CHECKPOINTED",
            f"checkpoint run={self._config.run_id} v={self._state.checkpoint_version}",
            before={"checkpoint_version": previous_version},
            after={"checkpoint_version": self._state.checkpoint_version},
        )
        return self._state

    @classmethod
    def restore(
        cls,
        state: TaskControllerHostState,
        control_plane: ControlPlane,
        transport: FakeSlackTransport,
        audit: AuditFacade | NoOpAuditFacade | None = None,
    ) -> "SlackTaskControllerPack":
        # reconstruct a fresh host from persisted state; binding is restored into
        # the adapter's registry before any materialize
        return cls(state.config, control_plane, transport, host_state=state, audit=audit)

    def attempt_second_root(self) -> None:
        """Attempting a second root for the same task/target must fail closed.

        Uses the host-owned registry directly; never reads adapter private state.
        """
        reg = self._registry
        key = self._config.binding_key()
        existing = reg.lookup(key)
        if existing is None:
            raise AssertionError("expected an existing binding in this host")
        # deliberately attempt a DIFFERENT root => DuplicateRootError
        reg.bind(key, existing.channel, "root.EVIL", session_id="x")

    def root_count(self) -> int:
        return self._transport.root_count()

    def root_for(self, run_id: str) -> str | None:
        """Public read of the host-owned root identity (no adapter private state)."""
        b = self._registry.lookup(self._config.binding_key() if run_id == self._config.run_id else f"{run_id}#slack")
        return b.root if b is not None else None
