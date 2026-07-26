# Node Request/Result Adapter Contract

## Overview

The adapter contract defines how GWC runtime nodes interact with the durable runtime store. It provides a handshake protocol, request/result messaging, and retry/fencing integration.

## Version

`1.0.0`

## Handshake Protocol

### Request

```json
{
  "type": "adapter.handshake",
  "requestId": "uuid-v7",
  "payload": {
    "nodeId": "string",
    "capabilities": ["store.load", "store.append", "store.lease", "store.pending", "store.readback"],
    "supportedSchemas": ["runtime-event/v1", "checkpoint/v1", "store-api/v1", "pending-action/v1"]
  }
}
```

### Response (Success)

```json
{
  "type": "adapter.handshake.ack",
  "requestId": "uuid-v7",
  "payload": {
    "nodeId": "string",
    "fencingToken": 1,
    "leaseDurationMs": 30000
  }
}
```

### Response (Failure)

```json
{
  "type": "adapter.handshake.nack",
  "requestId": "uuid-v7",
  "payload": {
    "code": "string",
    "message": "string"
  }
}
```

## Rules

1. **Handshake first** — A node must complete the handshake before any store operations.
2. **Fencing token** — Handshake response carries the current fencing token. All subsequent store operations must include this token via `X-Fencing-Token` header.
3. **Lease duration** — Handshake response includes the granted lease duration in milliseconds.
4. **Capability negotiation** — The node declares its supported operations. The store acknowledges only the operations it supports per node role.

## Request/Result Flow

### Synchronous (Store Operations)

1. Node constructs request with current fencing token and CAS token (if write).
2. Node sends request to store adapter.
3. Adapter forwards to store API, returns response.
4. If `409 Conflict` or `412 Fenced`, adapter retries after re-reading the latest state.
5. Adapter returns result to calling node.

### Asynchronous (Pending Actions)

1. Node submits pending action via `POST /store/{key}/pending`.
2. Adapter returns `actionId` to node.
3. Worker node picks up the action, transitions to `CLAIMED`, executes, and records result.
4. Requesting node polls `GET /store/{key}/pending/{actionId}` or receives a callback.
5. Result is read back.

## Retry Policy

| Parameter | Default | Description |
|---|---|---|
| `maxRetries` | 3 | Maximum retry attempts |
| `backoffMs` | 1000 | Initial backoff between retries |
| `jitterMs` | 500 | Random jitter added to backoff |
| `requestTimeoutMs` | 30000 | Per-request timeout |

## Fencing Integration

- On `403 Fenced Out`, the adapter must stop the node and raise an alert.
- The node must re-handshake before resuming operations.
- Fencing tokens are monotonically increasing; a stale token always indicates the node has been superseded.

## Error Handling

| Error | Action |
|---|---|
| `CAS_MISMATCH` | Re-read state, retry with new CAS token (up to `maxRetries`) |
| `FENCED_OUT` | Stop node operations, require re-handshake |
| `LEASE_EXPIRED` | Re-acquire lease, retry |
| `TIMEOUT` | Retry with exponential backoff (up to `maxRetries`) |
| `INVALID_REQUEST` | Do not retry; report error to operator |