# Rejected Example: Scope Violation (Self-Approval Attempt)

## Scenario

BMAD adapter attempts to self-approve a G4 gate transition, which is prohibited by the authority boundary.

## Request

```json
{
  "apiVersion": "dw.superapps/v1",
  "kind": "BmadProcedureRequest",
  "procedureId": "architecture-analysis",
  "procedureVersion": "1.0.0",
  "targetSha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "gwcScopeHash": "sha256:abc123scopehash456def789",
  "inputs": {
    "analysisType": "architecture",
    "autoApprove": true
  },
  "permissionEnvelope": {
    "allowedPaths": [".bmad/**", "docs/**"],
    "actions": ["read", "analyze", "report", "write"]
  },
  "idempotencyKey": "arch-violation-a1b2c3d4-abc123scopehash",
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

## Rejection

The BMAD adapter detects the scope violation before executing any side effects:

```json
{
  "status": "scope-violation",
  "procedureId": "architecture-analysis",
  "procedureVersion": "1.0.0",
  "evidenceRefs": [],
  "changedPaths": [],
  "testResults": [],
  "findings": [],
  "residualRisks": [],
  "errors": [
    {
      "code": "SCOPE_VIOLATION",
      "message": "BMAD adapter cannot self-approve gate transitions. Gate approval is a GWC-only action. The 'autoApprove' input field is not within the permission envelope.",
      "details": {
        "violationType": "self-approval",
        "prohibitedAction": "approve",
        "enforcedBy": "GWC governance layer",
        "allowedGates": ["G2", "G4", "G5", "G6"],
        "recommendation": "Remove 'autoApprove' from inputs and submit the analysis result as read-only evidence for GWC to review."
      }
    }
  ],
  "gateRecommendations": [
    {
      "gate": "G4",
      "recommendation": "block",
      "evidence": "BMAD adapter cannot self-approve. The procedure request includes an 'autoApprove' field which violates the permission envelope.",
      "note": "BMAD recommendations are read-only evidence. Actual gate transitions are performed by GWC only."
    }
  ],
  "provenance": {
    "artifactId": "arch-violation-result",
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

- The adapter refused the request before any side effects occurred.
- No `.gwc/` paths were modified.
- No gate transition was executed.
- The error is returned as a `scope-violation` status with a typed error code.
- The scope-changing recommendation is reported as a `blocker`, never auto-executed.
- Provenance includes task ID, repo, SHA, procedure version, and scope hash.