# SCRUM-119: BMAD Procedure-Adapter Contracts and Authority Boundaries

| Field | Value |
|---|---|
| Key | SCRUM-119 |
| Parent | SCRUM-98 |
| Status | In Progress |
| Gate | G1 |
| Owner | GWC |
| Workers | bmad, task-me, ua |

## Gate Control

GWC owns the gate. BMAD does not approve gates, mutate `.gwc/`, or broaden scope.
GWC delegates the following gate-1 intents:
- `architecture-design` and `data-modeling` to BMAD
- `dependency-mapping` and `impact-analysis` to UA
- `task-decomposition` and `validation-planning` to task-me

## Decision Frame

Gate G1 may pass only if the BMAD adapter artifacts satisfy:
- exact provenance binding
- permission envelope enforcement
- idempotency policy
- read-only gate recommendations
- no canonical-state mutation

## Evidence Bound to GWC

GWC consumes the following artifacts as gate evidence:
- `contracts/permission-action-matrix.md`
- `examples/*.md`
- `tests/validator-test-plan.md`
- `schemas/bmad-procedure-*.json`

## Authority Boundary

BMAD may propose, analyze, and write only within declared BMAD-owned paths.
GWC remains the only actor authorized to transition gates G2, G4, G5, and G6.