# BMAD Procedure-Adapter Validator/Test Plan

## Purpose

Validate that BMAD procedure-adapter contracts and authority boundaries are correctly implemented per SCRUM-119. Every test must produce exact-SHA review evidence.

## Test Environment

- BMAD source commit: `bb45db4aa4496c69239f9c0629c290fd1b072fc9`
- GWC source commit: `62689ce35e279751a3bf17b5255ac258dafbe7d`
- Task-Me source commit: `ef0b890b1fb9140109c04cbb490b41d9aa94bfff`
- UA source commit: `c0e4821c519f564d6c8b353537cf121eb52a1617`
- GWC scope hash: computed from the active gate run SHA

## Test Cases

### TC-1: Idempotency Key Prevents Duplicate Side Effects

| Field | Value |
|---|---|
| ID | TC-1 |
| Name | Idempotency Key Duplicate Prevention |
| Priority | Critical |
| Procedure | architecture-analysis |

**Steps**:
1. Submit a `BmadProcedureRequest` with `idempotencyKey: "test-idempotency-001"`.
2. Verify the procedure executes and produces a result.
3. Submit the same request with the same `idempotencyKey`, `targetSha`, and `gwcScopeHash`.
4. Verify the adapter returns the cached result without executing side effects again.

**Expected**: The second request returns the same result as the first. No duplicate files are written. No duplicate side effects occur.

**Pass Criteria**: The `evidenceRefs` and `changedPaths` are identical between the two runs. No new files are created on the second run.

### TC-2: Scope Envelope Refuses Files Outside Permission

| Field | Value |
|---|---|
| ID | TC-2 |
| Name | Scope Envelope Enforcement |
| Priority | Critical |
| Procedure | architecture-analysis |

**Steps**:
1. Submit a `BmadProcedureRequest` with `permissionEnvelope.allowedPaths: [".bmad/**"]`.
2. Set `inputs.targetPaths` to include a path outside `.bmad/` (e.g., `.gwc/`).
3. Verify the adapter refuses the operation before any side effects.

**Expected**: The adapter returns `status: "scope-violation"` with error code `SCOPE_VIOLATION`. No files in `.gwc/` are modified.

**Pass Criteria**: The error response includes `code: "SCOPE_VIOLATION"` and `changedPaths` is empty.

### TC-3: BMAD Cannot Approve G2/G4/G5/G6 Transitions

| Field | Value |
|---|---|
| ID | TC-3 |
| Name | Gate Authority Boundary |
| Priority | Critical |
| Procedure | architecture-analysis |

**Steps**:
1. Submit a `BmadProcedureRequest` that includes a `gateRecommendations` entry with `recommendation: "approve"` for G4.
2. Verify the adapter does not execute the gate transition.
3. Verify the adapter returns the recommendation as read-only evidence only.

**Expected**: The `gateRecommendations` array contains the recommendation with `recommendation: "approve"`, but the actual G4 gate is not transitioned. The note field states "BMAD recommendations are read-only evidence."

**Pass Criteria**: The G4 gate remains in its original state after the procedure. The recommendation is returned as evidence only.

### TC-4: Provenance Fields Are Complete

| Field | Value |
|---|---|
| ID | TC-4 |
| Name | Provenance Completeness |
| Priority | High |
| Procedure | architecture-analysis |

**Steps**:
1. Submit a valid `BmadProcedureRequest` with all provenance fields populated.
2. Verify the result includes complete provenance.

**Expected**: The result `provenance` includes `artifactId`, `parentArtifactId`, `sourceRepo`, `sourceRef`, `sourceCommit`, `schemaVersion`, `ownerRoot`, and `generatedTime`.

**Pass Criteria**: All provenance fields are present and non-empty. `sourceCommit` matches the exact HEAD SHA of the target repository.

### TC-5: Exact-SHA Review Evidence

| Field | Value |
|---|---|
| ID | TC-5 |
| Name | Exact-SHA Review Evidence |
| Priority | High |
| Procedure | architecture-analysis |

**Steps**:
1. Record the exact SHA of the BMAD source commit used in the test.
2. Record the exact SHA of the GWC source commit used in the test.
3. Record the exact SHA of the target repository HEAD.
4. Record the GWC scope hash.
5. Run the procedure and capture the result.
6. Verify all SHAs in the result match the recorded values.

**Expected**: The result `provenance.sourceCommit` matches the BMAD source commit. The result `provenance.sourceCommit` in the request matches the target repo HEAD. The `gwcScopeHash` in the request matches the recorded scope hash.

**Pass Criteria**: All SHA values in the result are exact matches to the recorded values. No implicit or latest versions are used.

### TC-6: Positive Architecture Analysis Execution

| Field | Value |
|---|---|
| ID | TC-6 |
| Name | Positive Architecture Analysis |
| Priority | High |
| Procedure | architecture-analysis |

**Steps**:
1. Execute the positive architecture analysis example (`examples/positive-architecture-analysis.md`).
2. Verify the result status is `success`.
3. Verify all output paths are within `.bmad/**` and `docs/**`.
4. Verify no `.gwc/` paths were modified.
5. Verify no gate approval was attempted.

**Expected**: The procedure completes successfully with evidence references. All outputs are within the permission envelope.

**Pass Criteria**: `status: "success"`, `changedPaths` are within allowedPaths, `gateRecommendations` is empty or read-only.

### TC-7: Positive TDD Implementation Execution

| Field | Value |
|---|---|
| ID | TC-7 |
| Name | Positive TDD Implementation |
| Priority | High |
| Procedure | tdd-implementation |

**Steps**:
1. Execute the positive TDD implementation example (`examples/positive-tdd-implementation.md`).
2. Verify the result status is `success`.
3. Verify all output paths are within `.bmad/**`, `src/**`, and `tests/**`.
4. Verify no `.gwc/` paths were modified.

**Expected**: The procedure completes successfully with test results and evidence references.

**Pass Criteria**: `status: "success"`, test results contain at least one `pass`, `changedPaths` are within allowedPaths.

### TC-8: Positive Review-Only Execution

| Field | Value |
|---|---|
| ID | TC-8 |
| Name | Positive Review-Only |
| Priority | High |
| Procedure | code-review |

**Steps**:
1. Execute the positive review-only example (`examples/positive-review-only.md`).
2. Verify the result status is `success`.
3. Verify `delete` action was not used.
4. Verify no `.gwc/` paths were modified.

**Expected**: The procedure completes successfully with a review report. No destructive actions were taken.

**Pass Criteria**: `status: "success"`, no `delete` actions in `changedPaths`, `gateRecommendations` is empty.

### TC-9: Rejected Scope Violation (Self-Approval)

| Field | Value |
|---|---|
| ID | TC-9 |
| Name | Rejected Self-Approval Scope Violation |
| Priority | Critical |
| Procedure | architecture-analysis |

**Steps**:
1. Execute the rejected scope-violation example (`examples/rejected-scope-violation.md`).
2. Verify the result status is `scope-violation`.
3. Verify the error code is `SCOPE_VIOLATION`.
4. Verify no side effects occurred.

**Expected**: The adapter returns `status: "scope-violation"` with `code: "SCOPE_VIOLATION"`. No files were modified.

**Pass Criteria**: `status: "scope-violation"`, `changedPaths` is empty, error message explains the prohibition.

### TC-10: Idempotency Key Scope Composition

| Field | Value |
|---|---|
| ID | TC-10 |
| Name | Idempotency Key Scope |
| Priority | High |
| Procedure | architecture-analysis |

**Steps**:
1. Submit two requests with the same `idempotencyKey` but different `targetSha`.
2. Verify the adapter treats them as distinct requests and executes both.
3. Submit two requests with the same `idempotencyKey` and `targetSha` but different `gwcScopeHash`.
4. Verify the adapter treats them as distinct requests and executes both.

**Expected**: Requests with different `targetSha` or `gwcScopeHash` are not considered duplicates. Each executes independently.

**Pass Criteria**: Both requests produce distinct results. No cached result is returned for requests with different scope fields.

## Review Evidence Checklist

- [ ] BMAD source commit SHA recorded: `bb45db4aa4496c69239f9c0629c290fd1b072fc9`
- [ ] GWC source commit SHA recorded: `62689ce35e279751a3bf17b5255ac258dafbe7d`
- [ ] Task-Me source commit SHA recorded: `ef0b890b1fb9140109c04cbb490b41d9aa94bfff`
- [ ] UA source commit SHA recorded: `c0e4821c519f564d6c8b353537cf121eb52a1617`
- [ ] GWC scope hash computed and recorded
- [ ] All JSON schemas validated against `schemas/bmad-procedure-registry.schema.json`
- [ ] All test cases pass
- [ ] Exact-SHA review evidence attached to GWC run
- [ ] No BMAD package publication performed
- [ ] No canonical-state mutation performed
- [ ] No self-approval performed
- [ ] No merge, deploy, release, or production operation performed