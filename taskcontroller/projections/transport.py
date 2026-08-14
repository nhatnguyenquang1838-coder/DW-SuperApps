"""WP6 S4 fake Slack transport (NO network; recording only)."""

from __future__ import annotations

from typing import Any


class FakeSlackTransport:
    """Records every operation applied. No network. Deterministic.

    Tracks root count and thread replies so E2E tests can assert the
    1-run = 1-root invariant and that thread events never become roots.
    """

    def __init__(self) -> None:
        self.ops: list[dict[str, Any]] = []
        self.roots_created: list[str] = []
        self.roots_updated: list[str] = []
        self.thread_replies: list[str] = []  # root ids that received a thread reply

    def apply(self, op: dict[str, Any]) -> None:
        self.ops.append(op)
        kind = op.get("op")
        root = op.get("root")
        if kind == "CREATE_ROOT":
            # a NEW root identity is allocated by the adapter and recorded here
            self.roots_created.append(root)
        elif kind == "UPDATE_ROOT":
            self.roots_updated.append(root)
        elif kind == "REPLY_THREAD":
            self.thread_replies.append(root)

    def root_count(self) -> int:
        # distinct roots that were ever created
        return len(set(self.roots_created))
