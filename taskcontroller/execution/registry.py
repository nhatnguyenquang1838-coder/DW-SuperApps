"""WP4 adapter registry (explicit, immutable snapshot, NO GWC).

No provider/network/tool discovery. The registry is a fixed snapshot mapping an
adapter key -> ExecutionAdapter instance. Duplicate conflicting registration
fails closed; identical (key + same instance) registration is idempotent. Lookup
is deterministic by adapter key or by supported BindingType.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from taskcontroller.domain.enums import BindingType
from taskcontroller.execution.errors import AdapterNotFoundError, ExecutionFabricError
from taskcontroller.execution.ports import ExecutionAdapter


@dataclass(frozen=True)
class AdapterRegistry:
    """Immutable snapshot of adapter_key -> adapter."""

    adapters: dict[str, ExecutionAdapter] = field(default_factory=dict)

    def get(self, adapter_key: str) -> ExecutionAdapter | None:
        return self.adapters.get(adapter_key)

    def lookup_by_key(self, adapter_key: str) -> ExecutionAdapter:
        adapter = self.adapters.get(adapter_key)
        if adapter is None:
            raise AdapterNotFoundError(f"no adapter registered for key {adapter_key!r}")
        return adapter

    def lookup_by_binding_type(self, binding_type: str) -> ExecutionAdapter:
        """Return the single adapter supporting this BindingType (deterministic)."""
        matches = [
            a for a in self.adapters.values()
            if binding_type in a.supported_binding_types
        ]
        if not matches:
            raise AdapterNotFoundError(
                f"no adapter supports binding type {binding_type!r}"
            )
        # deterministic: stable by adapter key
        matches.sort(key=lambda a: getattr(a, "adapter_key", ""))
        return matches[0]

    def adapter_keys(self) -> list[str]:
        return sorted(self.adapters.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapters": {
                k: {
                    "adapter_key": getattr(v, "adapter_key", k),
                    "supported_binding_types": list(v.supported_binding_types),
                }
                for k, v in self.adapters.items()
            }
        }


def build_registry(adapters: list[ExecutionAdapter]) -> AdapterRegistry:
    """Build an immutable AdapterRegistry, enforcing duplicate-key semantics."""
    reg: dict[str, ExecutionAdapter] = {}
    for a in adapters:
        key = getattr(a, "adapter_key", None)
        if not isinstance(key, str) or not key:
            raise ExecutionFabricError("adapter has no string adapter_key")
        existing = reg.get(key)
        if existing is not None:
            # identical (same instance) => idempotent no-op
            if existing is a:
                continue
            raise ExecutionFabricError(
                f"duplicate adapter_key {key!r} with non-identical adapter"
            )
        reg[key] = a
    return AdapterRegistry(adapters=reg)
