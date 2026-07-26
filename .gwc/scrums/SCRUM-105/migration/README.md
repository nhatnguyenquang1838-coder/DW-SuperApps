# Storage Migration Path

## Current State: SQLite Pilot

Events are stored in a single SQLite database file at `.gwc/runtime-store.db`. Schema:

| Table | Columns |
|---|---|
| `events` | `id`, `stream_id`, `sequence`, `type`, `timestamp`, `payload_json`, `metadata_json` |
| `checkpoints` | `stream_id`, `sequence_number`, `snapshot_json`, `checkpoint_type`, `created_at` |
| `pending_actions` | `action_id`, `stream_id`, `state`, `action_type`, `payload_json`, `result_json`, `created_at`, `claimed_at`, `completed_at`, `claimed_by` |

## Target State: PostgreSQL / Supabase

### Tables

| Table | Notes |
|---|---|
| `events` | Same logical columns; `payload_json` and `metadata_json` become `JSONB` |
| `checkpoints` | Normalized; `snapshot_json` becomes `JSONB` |
| `pending_actions` | New table for the readback model |
| `leases` | New table for lease management (`key`, `holder_id`, `expires_at`, `fencing_token`) |
| `fencing_tokens` | New table tracking per-node fencing state (`node_id`, `token`, `updated_at`) |

### Indexes

- `(stream_id, sequence)` on `events`
- `(event_type, timestamp)` on `events`
- `(stream_id)` on `checkpoints`
- `(stream_id, state)` on `pending_actions`
- `(key)` on `leases`
- `(node_id)` on `fencing_tokens`

### Supabase-Specific

- Row-level security enabled for tenant isolation.
- Realtime subscriptions available for event streams (optional).
- Connection pooling via Supabase connection string.

## Migration Steps

### Phase 1: Extract
1. Read all events from SQLite in stream-order using sequence numbers.
2. Write extraction log with per-stream counts and checksums.

### Phase 2: Transform
1. Validate each event against the new JSON schema (`runtime-event.schema.json`).
2. Convert SQLite JSON strings to PostgreSQL-compatible JSONB.
3. Generate per-event SHA-256 checksum for verification.

### Phase 3: Load
1. Create target PostgreSQL tables and indexes.
2. Batch-insert events using `COPY` or batched `INSERT`.
3. Load checkpoints and pending actions.

### Phase 4: Verify
1. Compare row counts per stream between SQLite and PostgreSQL.
2. Compare per-event checksums.
3. Verify checkpoint snapshots match.
4. Run verification script: `tools/verify-migration.py`.

### Phase 5: Cutover
1. Switch runtime store adapter from SQLite to PostgreSQL.
2. Deprecate SQLite reads (keep file for archival).
3. Monitor writes for 24 hours; watch for errors.

### Phase 6: Archive
1. Set SQLite file to read-only.
2. Retain for 30 days post-cutover.
3. Remove dual-write adapter and SQLite dependency.

### Rollback
If verification fails at any phase:
1. Stop cutover.
2. Continue reading from SQLite.
3. Fix extraction/transform/load issues.
4. Re-run verification.

Rollback plan kept in `migration/rollback.md`.