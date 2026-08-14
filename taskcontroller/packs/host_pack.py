"""WP7 S2 vertical host pack facade (NO GWC).

Composes existing layers WITHOUT creating a new source of truth or duplicating
their authority:

- materialize()              -> WP6 projection (one root, restart-safe)
- route_and_dispatch()       -> WP3 routing + WP4 dispatch only
- forward_signal()           -> WP2 EventRouter (trusted adapter signal)
- controller_action()        -> WP5 control plane via WP6 action mapping
- rotate_executor/session/model -> metadata update + SESSION_ROTATED thread event
- checkpoint_host_state() / restore_host_state() -> binding restored before next materialize

The host NEVER mutates run/node state directly; every state change goes through
the composed layer's own authority (WP2 CAS, WP5 CAS, WP4 fabric preflight).
"""

from __future__ import annotations

from typing import Any

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
    ) -> None:
        self._config = config
        self._cp = control_plane
        self._transport = transport
        # restart-safe: restore the binding registry from host state BEFORE any
        # materialization. This is the core invariant against duplicate roots.
        registry = (
            BindingRegistry.from_snapshot(host_state.binding_snapshot)
            if host_state is not None
            else BindingRegistry()
        )
        self._adapter = SlackProjectionAdapter(control_plane, transport, registry)
        self._state = host_state or TaskControllerHostState(
            config=config, binding_snapshot=registry.snapshot()
        )

    # -- projection (WP6) --------------------------------------------------
    def materialize(self, session_id=None, model=None, executor=None) -> dict[str, Any]:
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
        self._state = TaskControllerHostState(
            config=self._state.config,
            binding_snapshot=self._adapter.binding_snapshot(),
            session_id=self._state.session_id,
            model=self._state.model,
            executor=self._state.executor,
            checkpoint_version=self._state.checkpoint_version,
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
        return self._adapter.apply_action(
            self._config.run_id, action, expected_version, command_id, new_plan_version
        )

    # -- rotation ----------------------------------------------------------
    def rotate(self, session_id=None, model=None, executor=None) -> None:
        self._state = self._state.with_metadata(
            session_id=session_id, model=model, executor=executor
        )
        self._adapter.emit_thread(
            self._config.run_id, "SESSION_ROTATED",
            f"rotation s={session_id} m={model} e={executor}",
        )

    # -- checkpoint / restore (restart-safe) -------------------------------
    def checkpoint_host_state(self) -> TaskControllerHostState:
        snapshot = self._adapter.binding_snapshot()
        self._state = TaskControllerHostState(
            config=self._state.config,
            binding_snapshot=snapshot,
            session_id=self._state.session_id,
            model=self._state.model,
            executor=self._state.executor,
            checkpoint_version=self._state.checkpoint_version + 1,
        )
        return self._state

    @classmethod
    def restore(cls, state: TaskControllerHostState, control_plane: ControlPlane,
                transport: FakeSlackTransport) -> "SlackTaskControllerPack":
        # reconstruct a fresh host from persisted state; binding is restored into
        # the adapter's registry before any materialize
        return cls(state.config, control_plane, transport, host_state=state)

    def attempt_second_root(self) -> None:
        """Attempting a second root for the same task/target must fail closed."""
        # adapter already holds the binding; a conflicting bind must raise
        from taskcontroller.projections.binding import Binding

        reg = self._adapter._registry
        key = self._config.binding_key()
        existing = reg.lookup(key)
        if existing is None:
            raise AssertionError("expected an existing binding in this host")
        # deliberately attempt a DIFFERENT root => DuplicateRootError
        reg.bind(key, existing.channel, "root.EVIL", session_id="x")

    def root_count(self) -> int:
        return self._transport.root_count()
