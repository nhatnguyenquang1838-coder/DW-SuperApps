"""WP5 S3 control-plane orchestration facade (NO GWC).

One entrypoint binds a typed intent to the engine and returns the authoritative
persisted result plus a fresh projection of the resulting state. The projection is
always re-derived from the live store after the command commits, so the read model
and the persisted truth can never disagree. No execution adapter is invoked.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.controlplane.engine import ControlEngine
from taskcontroller.controlplane.intents import ControlIntent, ControlResult
from taskcontroller.controlplane.projection import RunProjection


class ControlPlane:
    """Thin facade over the CAS-backed engine + fresh projection."""

    def __init__(self, store: Any) -> None:
        self._engine = ControlEngine(store)
        self._store = store

    def command(self, intent: ControlIntent) -> tuple[ControlResult, RunProjection]:
        """Apply the intent and return (persisted result, fresh projection).

        The projection is derived from the store AFTER the commit, guaranteeing
        the controller read model agrees with the persisted truth.
        """
        result = self._engine.apply(intent)
        projection = RunProjection.from_versioned(self._store.get_run(intent.run_id))
        return result, projection
