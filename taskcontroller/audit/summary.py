"""Run summary model for SQLite Run Ledger."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RunSummary:
    run_id: str
    first_sequence: int
    last_sequence: int
    event_count: int
    first_event_id: str
    last_event_id: str
    closed_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if self.first_sequence < 1 or self.last_sequence < 1:
            raise ValueError("sequence must be >= 1")
        if self.last_sequence < self.first_sequence:
            raise ValueError("last_sequence must be >= first_sequence")
        if self.event_count != (self.last_sequence - self.first_sequence + 1):
            raise ValueError("event_count must equal last_sequence - first_sequence + 1")
