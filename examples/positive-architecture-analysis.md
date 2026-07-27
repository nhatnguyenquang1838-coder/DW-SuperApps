# Positive Example: Architecture Analysis

## Scenario

BMAD adapter executes an architecture analysis procedure within its permission envelope.

## Request

```json
{
  "apiVersion": "dw.superapps/v1",
  "kind": "BmadProcedureRequest",
  "procedureId": "architecture-analysis",
  "procedureVersion": "1.0.0",
  "targetSha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "baseSha": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5",
  "gwcScopeHash": "sha256:abc123scopehash456def789",
  "snapshotId": "ua-snapshot-20260727-001",
  "inputs": {
    "analysisType": "architecture",
    "targetPaths": ["src/", "docs/"],
    "includeDependencies": true
  },
  "permissionEnvelope": {
    "allowedPaths": [".bmad/**", "docs/**"],
    "actions": ["read", "analyze", "report", "write"]
  },
  "idempotencyKey": "arch-analysis-a1b2c3d4-abc123scopehash",
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

1. BMAD adapter validates the permission envelope — `allowedPaths` and `actions` are within bounds.
2. Adapter reads project source files under `src/` and `docs/` (read-only action).
3. Adapter performs architecture analysis using BMAD methodology.
4. Adapter writes analysis report to `.bmad/outputs/architecture-analysis-1.0.0.md` (boundedWrite action).
5. Adapter returns result with evidence references.

## Result

```json
{
  "status": "success",
  "procedureId": "architecture-analysis",
  "procedureVersion": "1.0.0",
  "evidenceRefs": [
    {
      "artifactId": "arch-analysis-report",
      "path": ".bmad/outputs/architecture-analysis-1.0.0.md",
      "type": "document",
      "sha256": "sha256:reportsha256hash"
    },
    {
      "artifactId": "dependency-graph",
      "path": ".bmad/outputs/dependency-graph-1.0.0.json",
      "type": "graph",
      "sha256": "sha256:graphsha256hash"
    }
  ],
  "changedPaths": [".bmad/outputs/architecture-analysis-1.0.0.md", ".bmad/outputs/dependency-graph-1.0.0.json"],
  "testResults": [
    {"name": "architecture-coherence", "status": "pass", "durationMs": 1200},
    {"name": "dependency-consistency", "status": "pass", "durationMs": 800}
  ],
  "findings": [
    {
      "category": "architecture",
      "severity": "info",
      "description": "Module boundaries are well-defined with clear separation of concerns.",
      "recommendation": "Consider extracting shared utilities into a dedicated package."
    }
  ],
  "residualRisks": [],
  "errors": [],
  "gateRecommendations": [],
  "provenance": {
    "artifactId": "arch-analysis-result",
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
- Provenance includes task ID, repo, SHA, procedure version, and scope hash.
- Idempotency key was respected; duplicate request returns cached result.