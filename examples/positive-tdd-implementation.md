# Positive Example: TDD Implementation

## Scenario

BMAD adapter executes a TDD implementation procedure within its permission envelope.

## Request

```json
{
  "apiVersion": "dw.superapps/v1",
  "kind": "BmadProcedureRequest",
  "procedureId": "tdd-implementation",
  "procedureVersion": "1.0.0",
  "targetSha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "baseSha": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5",
  "gwcScopeHash": "sha256:abc123scopehash456def789",
  "inputs": {
    "testFramework": "pytest",
    "targetModule": "src/services/payment",
    "testCases": ["payment-processing", "refund-validation", "timeout-handling"]
  },
  "permissionEnvelope": {
    "allowedPaths": [".bmad/**", "src/**", "tests/**"],
    "actions": ["read", "analyze", "report", "write", "create", "update"]
  },
  "idempotencyKey": "tdd-imp-a1b2c3d4-abc123scopehash",
  "provenance": {
    "parentArtifactId": "SCRUM-119",
    "sourceRepo": "nhatnguyenquang1838-coder/DW-SuperApps",
    "sourceRef": "main",
    "sourceCommit": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    "schemaVersion": "dw.superapps/v1",
    "ownerRoot": ".bmad/"
  }
}
```

## Execution Flow

1. BMAD adapter validates the permission envelope — `allowedPaths` include `src/**` and `tests/**`.
2. Adapter reads the target module `src/services/payment` (read action).
3. Adapter generates test cases and writes them to `tests/services/test_payment.py` (boundedWrite create action).
4. Adapter writes implementation guidance to `.bmad/outputs/tdd-implementation-1.0.0.md` (boundedWrite write action).
5. Adapter runs the generated tests and records results.
6. Adapter returns result with evidence references.

## Result

```json
{
  "status": "success",
  "procedureId": "tdd-implementation",
  "procedureVersion": "1.0.0",
  "evidenceRefs": [
    {
      "artifactId": "test-file",
      "path": "tests/services/test_payment.py",
      "type": "test",
      "sha256": "sha256:testsha256hash"
    },
    {
      "artifactId": "tdd-report",
      "path": ".bmad/outputs/tdd-implementation-1.0.0.md",
      "type": "report",
      "sha256": "sha256:reportsha256hash"
    }
  ],
  "changedPaths": ["tests/services/test_payment.py", ".bmad/outputs/tdd-implementation-1.0.0.md"],
  "testResults": [
    {"name": "payment-processing", "status": "pass", "durationMs": 1500},
    {"name": "refund-validation", "status": "pass", "durationMs": 900},
    {"name": "timeout-handling", "status": "pass", "durationMs": 1100}
  ],
  "findings": [],
  "residualRisks": [],
  "errors": [],
  "gateRecommendations": [],
  "provenance": {
    "artifactId": "tdd-result",
    "parentArtifactId": "SCRUM-119",
    "sourceRepo": "nhatnguyenquang1838-coder/DW-SuperApps",
    "sourceRef": "main",
    "sourceCommit": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    "toolCommit": "bb45db4aa4496c69239f9c0629c290fd1b072fc9",
    "schemaVersion": "dw.superapps/v1",
    "ownerRoot": ".bmad/",
    "generatedTime": "2026-07-27T23:59:45+07:00"
  }
}
```

## Validation

- All output paths are within `.bmad/**`, `src/**`, and `tests/**` (boundedWrite allowedPaths).
- No `.gwc/` paths were modified.
- No gate approval was attempted.
- No scope expansion recommendation was auto-executed.
- Provenance includes task ID, repo, SHA, procedure version, and scope hash.
- Idempotency key was respected; duplicate request returns cached result.