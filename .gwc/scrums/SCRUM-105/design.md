# SCRUM-105: Design Durable Runtime Store, Event Model, and Adapter Contracts

| Field | Value |
|---|---|
| Key | SCRUM-105 |
| Priority | P2 (High) |
| Lane | Knowledge |
| Phase | 2 |
| Status | Design |
| Labels | event-sourcing, gwc-runtime, high-priority, knowledge-lane, phase-2, runtime-store |

## 1. Purpose

Design a durable runtime store for the GWC governance engine that provides event-sourced state management, checkpointing, CAS-based concurrency control, lease and fencing semantics, pending-action/readback messaging, and a node request/result adapter contract. The design must also define a storage migration path from the current SQLite pilot to PostgreSQL/Supabase.

## 2. Scope

### In scope
- Run/event/checkpoint JSON schema definitions
- Store API surface and semantics
- CAS, lease, and fencing semantics
- Pending-action/readback model
- Node request/result adapter contract
- SQLite-to-PostgreSQL/Supabase migration path

### Out of scope
- Runtime store implementation (SCRUM-104 covers the implementation lane)
- Database provisioning or infrastructure provisioning
- User-facing UI for store inspection

## 3. Run / Event / Checkpoint Schemas

### 3.1 Runtime Event Envelope

Every event admitted to the store follows this envelope:

```json
{
  "eventId": "uuid-v7",
  "streamId": "string (aggregate identifier)",
  "streamVersion": "uint64",
  "eventType": "string (fully qualified name)",
  "timestamp": "ISO-8601 with timezone",
  "traceId": "uuid (optional, for distributed tracing)",
  "payload": { },
  "metadata": {
    "actor": "string",
    "source": "string",
    "correlationId": "uuid (optional)"
  }
}
```

### 3.2 Checkpoint Event

Checkpoints are a special event type that marks a durable snapshot of stream state:

```json
{
  "eventId": "uuid-v7",
  "streamId": "string",
  "streamVersion": "uint64",
  "eventType": "checkpoint",
  "timestamp": "ISO-8601",
  "payload": {
    "snapshot": { },
    "sequenceNumber": "uint64",
    "checkpointType": "manual | auto | recovery"
  },
  "metadata": {}
}
```

### 3.3 Run Event

A run event represents a single execution unit within the GWC runtime:

```json
{
  "eventId": "uuid-v7",
  "streamId": "string",
  "streamVersion": "uint64",
  "eventType": "run.started | run.completed | run.failed | run.cancelled",
  "timestamp": "ISO-8601",
  "payload": {
    "runId": "string",
    "workflowId": "string",
    "phase": "string",
    "inputs": { },
    "outputs": { },
    "error": {
      "code": "string",
      "message": "string",
      "stackTrace": "string (optional)"
    }
  },
  "metadata": {}
}
```

## 4. Store API

### 4.1 Core Operations

| Operation | Method | Path | Semantics |
|---|---|---|---|
| Append | POST | `/streams/{streamId}/events` | Append one or more events; server assigns sequence numbers |
| Read | GET | `/streams/{streamId}/events?from={seq}&limit={n}` | Read events from a sequence number forward |
| Snapshot | GET | `/streams/{streamId}/checkpoint` | Read the latest checkpoint for a stream |
| Store | PUT | `/store/{key}` | Conditional put with CAS token |
| Load | GET | `/store/{key}` | Read current value for a key |
| Delete | DELETE | `/store/{key}` | Conditional delete with CAS token |
| Lease | POST | `/store/{key}/lease` | Acquire a lease on a key |
| Renew | POST | `/store/{key}/lease/renew` | Renew an existing lease |
| Release | POST | `/store/{key}/lease/release` | Release a lease |
| Pending | POST | `/store/{key}/pending` | Submit a pending action |
| Readback | GET | `/store/{key}/pending/{actionId}` | Read back a pending action result |

### 4.2 API Conventions

- All responses include `X-Event-Stream-Version` header indicating the current stream version.
- All write operations are idempotent when the `If-Match` header carries a valid CAS token.
- Pagination uses `from` (inclusive) and `limit` query parameters; max limit is 100.
- Errors return a structured envelope: `{ "code": "string", "message": "string", "details": {} }`.

## 5. CAS, Lease, and Fencing Semantics

### 5.1 Compare-and-Swap (CAS)

- Every read returns a CAS token (the event stream version at read time).
- Write operations include `If-Match: <token>` header.
- If the server-side version does not match, the write is rejected with `409 Conflict`.
- The client must re-read and retry with the new token.

### 5.2 Leases

- A lease grants exclusive write access to a key for a bounded duration.
- Lease requests include `TTL` (time-to-live in seconds, max 300).
- Lease holders are identified by a `holderId` (node identifier).
- A lease can be renewed before expiry; renewal resets the TTL.
- When a lease expires, write access reverts to CAS-only.

### 5.3 Fencing

- Fencing tokens are monotonic integers assigned by the store per node.
- Every write must carry the current fencing token.
- A node with a stale fencing token is fenced out; writes are rejected with `403 Forbidden`.
- Fencing tokens are published via the lease renewal response and checkpoint events.

## 6. Pending-Action / Readback Model

### 6.1 Pattern

A pending action represents an asynchronous operation requested by a node:

1. Node submits a pending action via `POST /store/{key}/pending` with the action payload.
2. The store assigns an `actionId` and persists the action in `PENDING` state.
3. A worker node picks up the action, executes it, and records the result.
4. The requesting node reads back the result via `GET /store/{key}/pending/{actionId}`.

### 6.2 State Machine

```
PENDING → CLAIMED → EXECUTING → COMPLETED
                               → FAILED
```

**Transitions:**

| From | To | Trigger | Actor |
|---|---|---|---|
| PENDING | CLAIMED | Worker node claims the action | Worker node |
| CLAIMED | EXECUTING | Worker begins execution | Worker node |
| EXECUTING | COMPLETED | Action succeeds | Worker node |
| EXECUTING | FAILED | Action raises error | Worker node |

### 6.3 Schema

```json
{
  "actionId": "uuid-v7",
  "streamId": "string",
  "state": "pending | claimed | executing | completed | failed",
  "actionType": "string",
  "payload": { },
  "result": {
    "success": "boolean",
    "data": { },
    "error": { "code": "string", "message": "string" }
  },
  "createdAt": "ISO-8601",
  "claimedAt": "ISO-8601 (optional)",
  "completedAt": "ISO-8601 (optional)",
  "claimedBy": "string (nodeId, optional)"
}
```

## 7. Node Request / Result Adapter Contract

### 7.1 Interface

Nodes communicate with the runtime store through a request/result adapter. The contract defines:

```yaml
adapterContract:
  version: "1.0.0"
  nodeId: "string (unique node identifier)"
  requestTimeoutMs: "integer (default 30000)"
  retryPolicy:
    maxRetries: 3
    backoffMs: 1000
    jitterMs: 500
  supportedOperations:
    - store.load
    - store.append
    - store.lease
    - store.pending
    - store.readback
  handshake:
    request:
      type: "adapter.handshake"
      payload:
        capabilities: "string[]"
        fencingToken: "uint64"
    response:
      type: "adapter.handshake.ack"
      payload:
        fencingToken: "uint64"
        leaseDurationMs: "integer"
```

### 7.2 Rules

- A node must complete the handshake before any store operations.
- Handshake responses carry the current fencing token and lease duration.
- Store operations without a valid fencing token are rejected.
- The adapter translates between node-local requests and store API calls, handling retries and timeout.

## 8. Storage Migration Path

### 8.1 Current State: SQLite Pilot

- Events are stored in a single SQLite database file.
- Schema uses a single `events` table with columns: `id`, `stream_id`, `sequence`, `type`, `timestamp`, `payload_json`, `metadata_json`.
- Checkpoints stored in a `checkpoints` table.

### 8.2 Target State: PostgreSQL / Supabase

- Events table with same logical columns but using PostgreSQL JSONB for payload and metadata.
- Checkpoints table normalized separately.
- Pending actions table for the readback model.
- Row-level security enabled for tenant isolation.
- Indexes on `(stream_id, sequence)` and `(event_type, timestamp)`.

### 8.3 Migration Steps

1. **Extract** — Read all events from SQLite in stream-order using the current sequence numbers.
2. **Transform** — Validate each event against the new JSON schema; convert SQLite types to PostgreSQL-compatible types. JSON string columns become JSONB.
3. **Load** — Batch-insert events into PostgreSQL using `COPY` or batched `INSERT`.
4. **Verify** — Compare row counts and checksums per stream between source and target.
5. **Cutover** — Switch store adapter to PostgreSQL; deprecate SQLite reads.
6. **Retain** — Keep SQLite file as read-only archive for 30 days post-cutover.

### 8.4 Migration Artifacts

| Artifact | Location |
|---|---|
| Migration script | `tools/migrate-runtime-store.py` |
| Dual-write adapter (interim) | `adapters/runtime-store-dual.py` |
| Verification script | `tools/verify-migration.py` |
| Rollback plan | `migration/rollback.md` |

### 8.5 Dual-Write (Interim)

During migration, a dual-write adapter writes to both SQLite and PostgreSQL simultaneously:

- Writes go to both stores.
- Reads continue from SQLite until cutover.
- After cutover, reads switch to PostgreSQL.
- The dual-write adapter is removed after the retention period.

## 9. Acceptance Criteria

1. All schemas validate against their JSON Schema definitions.
2. Store API operations satisfy the contract for success, error, and timeout cases.
3. CAS rejects stale writes with `409 Conflict`.
4. Leases expire after TTL and release exclusive access.
5. Fencing tokens monotonically increase and reject stale writes.
6. Pending actions follow the defined state machine.
7. Adapter contract handshake completes before any store operation.
8. Migration script extracts, transforms, and loads without data loss.
9. Verification script confirms row counts and checksums match.

## 10. Dependencies

- P1-I2 (SCRUM-104) — canonical registries and validators supply schema validation infrastructure.
- P2-K2 (SCRUM-106) — vertical-slice scenarios and crash/recovery test matrix inform checkpoint design.

## 11. References

- SCRUM-104: [P1-I2] Build canonical registries, validators and v3 data binding
- SCRUM-106: [P2-K2] Define vertical-slice scenarios and crash/recovery test matrix
- GWC Governance: `powers/gwc/skills/gwc-g1/SKILL.md`