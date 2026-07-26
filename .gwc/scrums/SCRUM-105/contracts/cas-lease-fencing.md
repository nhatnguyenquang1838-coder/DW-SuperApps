# CAS, Lease, and Fencing Semantics

## Compare-and-Swap (CAS)

### Mechanism

- Every read operation returns a **CAS token**, which is the current event stream version.
- Write operations must include `If-Match: <token>` in the request header.
- On the server side, the CAS token is compared against the current stream version.
- If tokens match: write proceeds, stream version increments, new CAS token returned.
- If tokens do not match: write is rejected with `409 Conflict`.

### Client Responsibilities

1. Read the current state to obtain the CAS token.
2. Prepare the write payload.
3. Submit the write with `If-Match: <token>`.
4. On `409 Conflict`, re-read the latest state and retry.
5. Implement exponential backoff with jitter between retries.

### Idempotency

- The CAS token is a version precondition, not an idempotency key.
- Every side-effecting request carries an `operationId` and `Idempotency-Key`.
- The store persists the first result for that key and returns the same result for an ambiguous retry without repeating the side effect.
- Reusing a CAS token after a successful write is a stale-version conflict, not proof of a duplicate request.

## Leases

### Mechanism

- A lease grants **exclusive write access** to a specific key for a bounded duration.
- Lease requests include `holderId` (node identifier) and `ttlSeconds` (1–300).
- The store tracks active leases in a `leases` table: `(key, holder_id, expires_at, lease_epoch)`.
- Only one lease per key at a time.

### Lease Lifecycle

```
ACQUIRED -> ACTIVE -> EXPIRED | RENEWED | RELEASED -> EXPIRED
```

| Transition | Trigger | Effect |
|---|---|---|
| ACQUIRED | `POST /store/{key}/lease` | Lease created, exclusive access granted |
| ACTIVE | — | Lease is valid, holder has exclusive write access |
| RENEWED | `POST /store/{key}/lease/renew` | TTL resets, fencing token updated |
| RELEASED | `POST /store/{key}/lease/release` | Lease removed, CAS-only mode restored |
| EXPIRED | TTL elapses | Lease removed, CAS-only mode restored |

### Lease and Fencing

- When a lease is acquired or renewed, the store atomically publishes a new fencing token for the fenced key/resource.
- The fencing token is included in the lease response and must be used in subsequent writes.
- Fencing tokens are **monotonically increasing per fenced key/resource lease epoch**, not independently per node.

## Fencing

### Mechanism

- Each lease epoch has a **fencing token** — a monotonically increasing integer assigned by the store for the fenced key/resource.
- Every write operation must carry the current fencing token via `X-Fencing-Token` header.
- The store compares the incoming token and holder identity against the current lease record for the resource.
- A write proceeds only when the incoming token equals the current lease epoch and the holder is the current lease owner.
- Any stale token, equal token from a non-owner, or expired lease is rejected with `403 Forbidden`.

### When Fencing Occurs

1. **Lease acquisition** — New token assigned.
2. **Lease renewal** — Token increments and is published.
3. **Checkpoint** — Token is included in checkpoint bindings.
4. **Node re-handshake** — The node receives the current lease epoch after it has acquired or renewed the resource lease.

### Fencing Recovery

1. A fenced node detects `403 Forbidden` on a write.
2. The node stops all write operations immediately.
3. The node performs the handshake protocol to obtain a new fencing token.
4. If the node cannot complete the handshake (e.g., another node holds the lease), it must wait or escalate.

### Lease vs. Fencing vs. CAS

| Mechanism | Purpose | Scope | Duration |
|---|---|---|---|
| **CAS** | Prevent lost updates | Per-key | Per-operation |
| **Lease** | Exclusive write access | Per-key | Bounded (TTL) |
| **Fencing** | Prevent stale lease-epoch writes | Per-resource lease epoch | Until a newer epoch supersedes it |

### Combined Usage

- Lease + Fencing: When a node holds a lease, it uses the lease epoch token and holder identity for writes.
- CAS without Lease: A caller may use CAS-only operations where explicitly allowed; no stale lease holder may bypass fencing.
- Lease + CAS: The lease owner must satisfy both the current lease epoch and the expected CAS version.
