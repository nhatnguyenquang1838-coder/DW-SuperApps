"""WP4 adapter port + deterministic fake adapter (NO GWC, NO real I/O).

The ExecutionAdapter port is product-neutral. WP4 ships ONLY a deterministic
recording/fake adapter used by tests; concrete Hermes/Slack/MCP/HTTP/CLI adapters
remain later materialization (explicitly out of WP4 scope).

No adapter implementation here calls wall-clock/random/network/subprocess. All
identities/timestamps returned in acks/signals are caller/adapter supplied.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from taskcontroller.execution.errors import AdapterUnsupportedError
from taskcontroller.execution.types import (
    CancelAck,
    DispatchAck,
    DispatchEnvelope,
)


class ExecutionAdapter(ABC):
    """Product-neutral adapter port.

    Operations:
    - dispatch(envelope) -> DispatchAck  (required)
    - cancel(envelope) -> CancelAck     (optional; raise AdapterUnsupportedError
                                         if not supported — never silently succeed)
    """

    #: binding types (BindingType values) this adapter can serve.
    supported_binding_types: tuple[str, ...] = ()

    @abstractmethod
    def dispatch(self, envelope: DispatchEnvelope) -> DispatchAck:
        """Dispatch the envelope, returning a normalized DispatchAck."""
        raise NotImplementedError

    def supports_cancel(self) -> bool:
        """Whether this adapter declares cancel support."""
        return False

    def cancel(self, envelope: DispatchEnvelope) -> CancelAck:
        """Cancel a prior dispatch. Unsupported adapters fail typed."""
        raise AdapterUnsupportedError(
            f"adapter {type(self).__name__} does not support cancel"
        )


class FakeExecutionAdapter(ExecutionAdapter):
    """Deterministic recording adapter for tests (NO real I/O).

    Records every dispatch/cancel call. By default accepts dispatch and does
    NOT emit signals (tests drive signals explicitly via produce_signal to keep
    effects deterministic and inspectable). cancel is supported.
    """

    def __init__(self, adapter_key: str = "fake.1", binding_type: str = "LOCAL_IPC") -> None:
        self.adapter_key = adapter_key
        self.supported_binding_types = (binding_type,)
        self.dispatched: list[DispatchEnvelope] = []
        self.cancelled: list[DispatchEnvelope] = []
        self._should_accept = True
        self._fail_next_dispatch = False

    def set_reject_next_dispatch(self) -> None:
        self._fail_next_dispatch = True

    def dispatch(self, envelope: DispatchEnvelope) -> DispatchAck:
        self.dispatched.append(envelope)
        if self._fail_next_dispatch:
            self._fail_next_dispatch = False
            return DispatchAck(
                command_id=envelope.command_id,
                accepted=True,
                status="REJECTED",
                adapter_key=self.adapter_key,
                detail="adapter rejected dispatch",
            )
        return DispatchAck(
            command_id=envelope.command_id,
            accepted=self._should_accept,
            status="ACCEPTED" if self._should_accept else "FAILED",
            adapter_key=self.adapter_key,
        )

    def supports_cancel(self) -> bool:
        return True

    def cancel(self, envelope: DispatchEnvelope) -> CancelAck:
        self.cancelled.append(envelope)
        return CancelAck(
            command_id=envelope.command_id,
            accepted=True,
            status="ACCEPTED",
            adapter_key=self.adapter_key,
        )
