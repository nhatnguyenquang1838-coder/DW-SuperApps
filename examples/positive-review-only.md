# Positive Example: Review-Only Procedure

## Scenario

BMAD adapter executes a review-only procedure that reads code and produces a review report without writing any project files.

## Request

```json
{
  "apiVersion": "dw.superapps/v1",
  "kind": "BmadProcedureRequest",
  "procedureId": "code-review",
  "procedureVersion": "1.0.0",
  "targetSha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "baseSha": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5",
  "gwcScopeHash": "sha256:abc123scopehash456def789",
  "inputs": {
    "reviewType": "code-review",
    "targetPaths": ["src/services/"],
    "reviewCriteria": ["security", "performance", "maintainability"]
  },
  "permissionEnvelope": {
    "allowedPaths": [".bmad/**", "docs/**"],
    "actions": ["read", "analyze", "report"]
  },
  "idempotencyKey": "code-review-a1b2c3d4-abc123scopehash",
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

1. BMAD adapter validates the permission envelope — `actions` are limited to `read`, `analyze`, `report`.
2. Adapter reads the target paths `src/services/` (read action only).
3. Adapter performs code review analysis using BMAD methodology.
4. Adapter writes review report to `.bmad/outputs/code-review-1.0.0.md` (boundedWrite write action).
5. Adapter returns result with evidence references.

## Result

```json
{
  "status": "success",
  "procedureId": "code-review",
  "procedureVersion": "1.0.0",
  "evidenceRefs": [
    {
      "artifactId": "review-report",
      "path": ".bmad/outputs/code-review-1.0.0.md",
      "type": "report",
      "sha256": "sha256:reviewsha256hash"
    }
  ],
  "changedPaths": [".bmad/outputs/code-review-1.0.0.md"],
  "testResults": [
    {"name": "security-review", "status": "pass", "durationMs": 2000},
    {"name": "performance-review", "status": "pass", "durationMs": 1500},
    {"name": "maintainability-review", "status": "pass", "durationMs": 1800}
  ],
  "findings": [
    {
      "category": "security",
      "severity": "medium",
      "description": "Input validation missing on payment endpoint.",
      "recommendation": "Add input validation middleware to the payment route."
    },
    {
      "category": "performance",
      "severity": "low",
      "description": "N+1 query pattern detected in user lookup.",
      "recommendation": "Use eager loading for user associations."
    }
  ],
  "residualRisks": [],
  "errors": [],
  "gateRecommendations": [],
  "provenance": {
    "artifactId": "code-review-result",
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

- All output paths are within `.bmad/**` and `docs/**` (boundedWrite allowedPaths).
- No `.gwc/` paths were modified.
- No gate approval was attempted.
- No scope expansion recommendation was auto-executed.
- `delete` action was not used (denied for boundedWrite).
- Provenance includes task ID, repo, SHA, procedure version, and scope hash.
- Idempotency key was respected; duplicate request returns cached result.