"""WP7 S1 host pack contract + restart-safe host state (NO GWC, NO network).

Defines the immutable/configurable vertical pack contract and the canonical host
state. The critical WP7 invariant: the run/task -> Slack root binding is stored as
*host state/evidence* (via the projection BindingRegistry snapshot), NOT as
session metadata, and survives Controller/host restart. Restoring the binding
before materialize permanently prevents the duplicate-root regression.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Default vertical executor profile (overridable per host contract).
DEFAULT_EXECUTOR_PROFILE = "HERMES_CLOUD"


@dataclass(frozen=True)
class TaskControllerHostConfig:
    """Immutable, configurable host contract.

    - explicit run/task identity
    - controller profile + executor profile (default HERMES_CLOUD, overridable)
    - projection target (channel) + identity prefix
    """

    run_id: str
    task_id: str
    controller_profile: str = "WP5_CONTROL_PLANE"
    executor_profile: str = DEFAULT_EXECUTOR_PROFILE
    projection_target: str = "slack"
    host_id: str = "host.default"

    def binding_key(self) -> str:
        # stable task/run identity + projection target (binding identity only)
        return f"{self.run_id}#{self.projection_target}"


@dataclass(frozen=True)
class TaskControllerHostState:
    """Restart-safe host evidence.

    The Slack binding snapshot is the canonical record of which root a run maps
    to. Storing it as host state (not session metadata) is what makes restart
    restore the SAME root.
    """

    config: TaskControllerHostConfig
    binding_snapshot: dict[str, dict[str, Any]]
    # mutable projection metadata (content only, NOT binding identity)
    session_id: str | None = None
    model: str | None = None
    executor: str | None = None
    # monotonically increasing host checkpoint version (deterministic)
    checkpoint_version: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "run_id": self.config.run_id,
                "task_id": self.config.task_id,
                "controller_profile": self.config.controller_profile,
                "executor_profile": self.config.executor_profile,
                "projection_target": self.config.projection_target,
                "host_id": self.config.host_id,
            },
            "binding_snapshot": self.binding_snapshot,
            "session_id": self.session_id,
            "model": self.model,
            "executor": self.executor,
            "checkpoint_version": self.checkpoint_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskControllerHostState":
        cfg = data["config"]
        return cls(
            config=TaskControllerHostConfig(
                run_id=cfg["run_id"],
                task_id=cfg["task_id"],
                controller_profile=cfg.get("controller_profile", "WP5_CONTROL_PLANE"),
                executor_profile=cfg.get("executor_profile", DEFAULT_EXECUTOR_PROFILE),
                projection_target=cfg.get("projection_target", "slack"),
                host_id=cfg.get("host_id", "host.default"),
            ),
            binding_snapshot=data["binding_snapshot"],
            session_id=data.get("session_id"),
            model=data.get("model"),
            executor=data.get("executor"),
            checkpoint_version=data.get("checkpoint_version", 0),
        )

    # deterministic serialize/restore round-trip (no wall clock/random/network)
    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def restore(cls, payload: str) -> "TaskControllerHostState":
        return cls.from_dict(json.loads(payload))

    def with_metadata(
        self,
        session_id: str | None = None,
        model: str | None = None,
        executor: str | None = None,
    ) -> "TaskControllerHostState":
        """Return a copy with updated mutable metadata (never the binding)."""
        return TaskControllerHostState(
            config=self.config,
            binding_snapshot=self.binding_snapshot,
            session_id=session_id if session_id is not None else self.session_id,
            model=model if model is not None else self.model,
            executor=executor if executor is not None else self.executor,
            checkpoint_version=self.checkpoint_version,
        )

    def next_checkpoint(self) -> "TaskControllerHostState":
        return TaskControllerHostState(
            config=self.config,
            binding_snapshot=self.binding_snapshot,
            session_id=self.session_id,
            model=self.model,
            executor=self.executor,
            checkpoint_version=self.checkpoint_version + 1,
        )
