"""Run manifest model for SQLite Run Ledger."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    manifest_kind: str
    schema_version: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.manifest_kind:
            raise ValueError("manifest_kind is required")
        if not self.schema_version:
            raise ValueError("schema_version is required")
        if not self.created_at:
            raise ValueError("created_at is required")
        if not self.updated_at:
            raise ValueError("updated_at is required")
