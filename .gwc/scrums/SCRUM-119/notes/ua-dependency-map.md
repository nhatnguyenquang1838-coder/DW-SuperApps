# UA Dependency Map for SCRUM-119

## Core Dependencies

- `schemas/bmad-procedure-request.schema.json`
- `schemas/bmad-procedure-result.schema.json`
- `schemas/bmad-permission-model.schema.json`
- `schemas/bmad-procedure-registry.schema.json`
- `contracts/permission-action-matrix.md`
- `examples/*.md`
- `tests/validator-test-plan.md`
- `.gwc/g1/decision/g1-SCRUM-119-20260728-0023.yaml`
- `.gwc/g1/preflight/g1-SCRUM-119-20260728-0023.yaml`

## Impact Analysis

- The request schema binds exact task/repo/SHA/scope inputs.
- The result schema carries evidence and read-only gate recommendations.
- The permission model constrains BMAD to bounded writes only.
- The registry schema anchors procedure metadata and idempotency policy.
- GWC records are the authoritative approval/control surface.

## Dependency Risks

- If scope hash derivation changes, gate records and test expectations must be regenerated.
- If BMAD output paths change, the permission matrix and examples must be updated.
- If GWC gate semantics change, the authority boundaries in the matrix must be revised.
