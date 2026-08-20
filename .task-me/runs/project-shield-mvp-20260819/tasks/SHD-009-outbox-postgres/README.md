# SHD-009 — Durable outbox + PostgreSQL
Preserve SQLite as the immediate local audit path and add a reliable outbox/shared PostgreSQL replica. Run Ledger remains canonical audit truth; cloud sync adds cross-host durability and readback, not an independent competing history.
