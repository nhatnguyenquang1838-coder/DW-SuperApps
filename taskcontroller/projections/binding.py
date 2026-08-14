"""WP6 S1 binding registry + errors (NO GWC).

Enforces the hard invariant: 1 task/run = exactly 1 active root/thread for a given
projection target. The binding key is the stable task/run identity + projection
target (channel). Session/model/executor metadata is mutable projection content and
is NEVER part of binding identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from taskcontroller.projections.types import ProjectionOp


class DuplicateRootError(Exception):
    """A binding already exists for this task/target with a different root.

    Fail-closed: the adapter must NOT create a second root.
    """


@dataclass(frozen=True)
class Binding:
    """An immutable binding: task/run identity + projection target -> root."""

    binding_key: str  # stable task/run identity + projection target
    channel: str
    root: str  # root/thread identity (live progress card)
    # mutable projection metadata (content only, NOT identity)
    session_id: str | None = None
    model: str | None = None
    executor: str | None = None


@dataclass
class BindingRegistry:
    """Deterministic binding registry.

    - bind(key, channel, root): first bind creates the binding. Identical rebind
      (same channel+root) is idempotent. Same key with a DIFFERENT root raises
      DuplicateRootError and performs ZERO mutation/transport side effect.
    - lookup(key): pure read, no side effect.
    - snapshot(): deterministic, ordered view (sorted by binding_key).
    """

    _bindings: dict[str, Binding] = field(default_factory=dict)

    def bind(
        self,
        binding_key: str,
        channel: str,
        root: str,
        session_id: str | None = None,
        model: str | None = None,
        executor: str | None = None,
    ) -> Binding:
        existing = self._bindings.get(binding_key)
        if existing is not None:
            # identical rebind (same channel + root) => idempotent no-op
            if existing.channel == channel and existing.root == root:
                return existing
            # same task/target but a different root => fail closed, no side effect
            raise DuplicateRootError(
                f"binding {binding_key!r} already bound to root "
                f"{existing.root!r}; refusing new root {root!r}"
            )
        binding = Binding(
            binding_key=binding_key,
            channel=channel,
            root=root,
            session_id=session_id,
            model=model,
            executor=executor,
        )
        self._bindings[binding_key] = binding
        return binding

    def update_metadata(
        self,
        binding_key: str,
        session_id: str | None = None,
        model: str | None = None,
        executor: str | None = None,
    ) -> Binding:
        """Mutate only projection metadata (never the root/binding identity)."""
        existing = self._bindings.get(binding_key)
        if existing is None:
            raise KeyError(f"no binding for {binding_key!r}")
        new = Binding(
            binding_key=existing.binding_key,
            channel=existing.channel,
            root=existing.root,
            session_id=session_id if session_id is not None else existing.session_id,
            model=model if model is not None else existing.model,
            executor=executor if executor is not None else existing.executor,
        )
        self._bindings[binding_key] = new
        return new

    def lookup(self, binding_key: str) -> Binding | None:
        """Pure read. No side effect."""
        b = self._bindings.get(binding_key)
        return Binding(**b.__dict__) if b is not None else None

    def has(self, binding_key: str) -> bool:
        return binding_key in self._bindings

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Deterministic ordered view of all bindings."""
        return {
            k: self._bindings[k].__dict__.copy()
            for k in sorted(self._bindings.keys())
        }
