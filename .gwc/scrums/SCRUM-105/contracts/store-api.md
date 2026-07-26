# GWC Store API Contract

## Overview

The GWC runtime store API is an HTTP-compatible service providing durable key-value and event-stream operations. All API paths are relative to the store base URL.

## Base URL

```
https://{store-host}/api/v1
```

## Headers

| Header | Required | Description |
|---|---|---|
| `Content-Type` | Yes | `application/json` |
| `Authorization` | Yes | `Bearer <token>` |
| `If-Match` | Conditional | CAS token for conditional writes |
| `Idempotency-Key` | Required for side effects | Stable key for safe retry/readback |
| `X-Operation-Id` | Required for side effects | Stable operation identity |
| `X-Fencing-Token` | Yes for writes | Current fencing token for the resource lease epoch |
| `X-Node-Id` | Yes | Unique node identifier |

## Endpoints

### Append Events

```
POST /streams/{streamId}/events
```

Request body: `{ "operationId": "string", "idempotencyKey": "string", "events": [ ... ] }`; event objects omit server-assigned `eventId` and `streamVersion`.

Response `201`:
```json
{
  "streamId": "string",
  "streamVersion": 42,
  "eventIds": ["uuid-v7", "uuid-v7"],
  "casToken": 42
}
```

Response `409`: CAS conflict (stream version mismatch).
Response `403`: Fencing token is stale, expired, or belongs to another holder.

### Read Events

```
GET /streams/{streamId}/events?from={seq}&limit={n}
```

Query parameters:
- `from` (optional): Start from this sequence number (inclusive). Omit for latest.
- `limit` (optional): Max 100 events. Default 50.

Response `200`:
```json
{
  "streamId": "string",
  "streamVersion": 42,
  "events": [ { "eventId": "...", "streamVersion": 42, "eventType": "...", "timestamp": "...", "payload": {}, "metadata": {} } ]
}
```

### Read Checkpoint

```
GET /streams/{streamId}/checkpoint
```

Response `200`:
```json
{
  "checkpointId": "uuid-v7",
  "runId": "string",
  "projectId": "string",
  "repository": "owner/repository",
  "taskId": "string",
  "cursor": { "gate": "G2_EXECUTION", "status": "STABLE", "attempt": 0 },
  "bindings": { "baseSha": "40-hex-sha", "headSha": "40-hex-sha", "scopeHash": "string" },
  "pendingAction": { "operationId": null, "idempotencyKey": null, "resultState": null },
  "continuation": { "mechanism": null, "nextCheckAtUtc": null, "active": false },
  "ownership": { "revision": 1, "leaseOwner": null, "leaseExpiresAtUtc": null }
}
```

Response `404`: No checkpoint exists.

### Store Put

```
PUT /store/{key}
```

Request body: `{ "value": { ... }, "operationId": "string", "idempotencyKey": "string" }`; pass the expected version in `If-Match`.

Response `200`: `{ "key": "...", "version": <casToken>, "fencingToken": <uint64> }`
Response `409`: CAS conflict.
Response `403`: Fencing rejection.
Response `403`: Fencing token is stale, expired, or belongs to another holder.

### Store Load

```
GET /store/{key}
```

Response `200`:
```json
{ "key": "...", "value": { ... }, "version": 42, "fencingToken": 7, "leaseEpoch": 7 }
```

Response `404`: Key not found.

### Store Delete

```
DELETE /store/{key}
```

Request body: `{ "operationId": "string", "idempotencyKey": "string" }`; pass the expected version in `If-Match`.

Response `200`: `{ "key": "...", "deleted": true }`
Response `409`: CAS conflict.

### Lease Acquire

```
POST /store/{key}/lease
```

Request body: `{ "holderId": "string", "ttlSeconds": <integer>, "operationId": "string", "idempotencyKey": "string" }`

Response `200`: `{ "key": "...", "holderId": "...", "expiresAt": "ISO-8601", "fencingToken": <uint64>, "leaseEpoch": <uint64> }`
Response `409`: Lease already held by another node.

### Lease Renew

```
POST /store/{key}/lease/renew
```

Request body: `{ "holderId": "string", "ttlSeconds": <integer>, "operationId": "string", "idempotencyKey": "string" }`

Response `200`: `{ "key": "...", "expiresAt": "ISO-8601", "fencingToken": <uint64>, "leaseEpoch": <uint64> }`
Response `403`: Not the current lease holder.

### Lease Release

```
POST /store/{key}/lease/release
```

Request body: `{ "holderId": "string", "operationId": "string", "idempotencyKey": "string" }`

Response `200`: `{ "key": "...", "released": true }`

### Pending Action Submit

```
POST /store/{key}/pending
```

Request body:
```json
{
  "operationId": "string",
  "idempotencyKey": "string",
  "actionType": "string",
  "payload": {},
  "fencingToken": <uint64>
}
```

Response `201`:
```json
{
  "actionId": "uuid-v7",
  "streamId": "key",
  "state": "pending",
  "createdAt": "ISO-8601"
}
```

### Readback Pending Action

```
GET /store/{key}/pending/{actionId}
```

Response `200`: Full pending action object with result (if completed).
Response `404`: Action not found.

## Error Envelope

All error responses follow this structure:

```json
{
  "code": "string",
  "message": "string",
  "details": {}
}
```

Common error codes:
- `CAS_MISMATCH` — 409 — Stream version does not match `If-Match` token.
- `FENCED_OUT` — 403 — Fencing token is stale, expired, or does not belong to the current lease holder.
- `LEASE_HELD_BY_OTHER` — 409 — Another node holds the lease.
- `NOT_FOUND` — 404 — Resource does not exist.
- `INVALID_REQUEST` — 400 — Request body does not conform to schema.
- `TIMEOUT` — 504 — Operation exceeded the configured timeout.
