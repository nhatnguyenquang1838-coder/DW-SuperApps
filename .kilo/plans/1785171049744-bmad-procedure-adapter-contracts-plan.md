# SCRUM-119: BMAD Procedure-Adapter Contracts and Authority Boundaries

| Field | Value |
|---|---|
| Key | SCRUM-119 |
| Parent | SCRUM-98 (GWC-P4 DW SUPER APP End-to-End Integration) |
| Priority | P4 (High) |
| Lane | Knowledge |
| Phase | 4 |
| Status | To Do |
| Blocks | SCRUM-120 |
| Parallel | SCRUM-116, SCRUM-117, SCRUM-118 |

## 1. Purpose

Define BMAD as a bounded procedure adapter for P4. The adapter may execute an approved methodology step, but it must never own canonical gate state, broaden scope, self-approve, or mutate unowned runtime roots.

## 2. Scope

### In scope
- Versioned procedure/request/result schemas for BMAD adapter invocations
- Permission/action matrix defining allowed and prohibited BMAD actions per gate
- Positive execution example (architecture analysis, TDD implementation, review-only)
- Rejected scope-violation example (self-approval, canonical-state mutation, scope expansion)
- Validator/test plan with exact-SHA review evidence
- Idempotency key scope and duplicate-handling policy
- Reference to ownership/provenance contract from SCRUM-116

### Out of scope
- BMAD package publication
- Canonical-state mutation (GWC-owned)
- Self-approval, merge, deploy, release, or production operations
- Jira/Notion/Slack projection writes
- GWC gate transition logic (GWC owns this)

## 3. Skill Roles

| Skill | Role in This Issue |
|---|---|
| **GWC** | Validate authority boundaries; enforce that BMAD never owns gate state or self-approves; define approval boundaries in the permission matrix |
| **UA** | Map BMAD procedure dependencies on GWC, task-me, and ua artifact references; identify semantic boundaries between adapter and runtime |
| **task-me** | Decompose the implementation into tasks: schema definitions, permission matrix, examples, validator/test plan |
| **BMAD** | Provide the structured methodology for the adapter contract itself; use BMAD's analysis and planning workflows to produce the deliverables |

## 4. Orchestration Sequence

```text
GWC (g1) → task-me (task-decomposition, validation-planning) → g1-options
GWC (g1) → bmad (architecture-design, data-modeling) → g1-options
GWC (g1) → ua (dependency-mapping, impact-analysis) → g1-preflight
GWC (g2) → execution of adapter contract implementation
GWC (g3) → draft PR with schemas, matrix, examples, test plan
GWC (g4) → merge with exact-head bound review evidence
```

## 5. Deliverables

### 5.1 Versioned Schemas (`schemas/bmad-procedure-adapter/`)
- `procedure-request.schema.json` — procedure invocation request (procedureId, version, targetRepo, baseSha, headSha, scopeHash, taskId, runId, gate, authorizedScope)
- `procedure-result.schema.json` — procedure result (procedureId, status, outputs[], evidence[], scopeChangeProposal?)
- `procedure-registry.schema.json` — already exists at `schemas/bmad-procedure-registry.schema.json`; extend if needed

### 5.2 Permission/Action Matrix (`contracts/permission-action-matrix.md`)
| Action | Architecture Analysis | TDD Implementation | Review-Only | Scope Violation |
|---|---|---|---|---|
| Read project context | allowed | allowed | allowed | allowed |
| Write BMAD/project-owned paths | allowed | allowed | denied | denied |
| Mutate .gwc canonical state | denied | denied | denied | denied |
| Self-approve gate transition | denied | denied | denied | denied |
| Publish BMAD package | denied | denied | denied | denied |
| Merge/deploy/release | denied | denied | denied | denied |
| Recommend scope change | proposal/blocker | proposal/blocker | proposal/blocker | blocker |

### 5.3 Execution Examples (`examples/`)
- `positive-architecture-analysis.md` — BMAD adapter executing architecture analysis within scope
- `positive-tdd-implementation.md` — BMAD adapter executing TDD implementation within scope
- `positive-review-only.md` — BMAD adapter executing review-only within scope
- `rejected-scope-violation.md` — BMAD adapter attempting self-approval (rejected)

### 5.4 Validator/Test Plan (`tests/`)
- Idempotency key test (same key → cached result, no duplicate side effects)
- Scope envelope test (files outside permission → refused before side effects)
- Gate authority test (BMAD cannot approve G2/G4/G5/G6)
- Provenance test (every output includes task, repo, SHA, procedure version, scope hash)
- Exact-SHA review evidence checklist

## 6. Authority Boundaries

| Boundary | Rule |
|---|---|
| Gate state | BMAD never owns canonical gate state; GWC owns all gate transitions |
| Scope expansion | BMAD can only recommend scope changes as proposal/blocker; GWC authorizes |
| Runtime roots | BMAD cannot mutate `.gwc/` runtime data; writes only to `.bmad/`, `_bmad/`, `_bmad-output/` |
| Idempotency | Same idempotency key + same targetSha + same scopeHash → return cached result, never duplicate side effects |
| Provenance | Every invocation binds to exact task, repository, base/head SHA, procedure version, and GWC scope hash |

## 7. Reference Contracts

- SCRUM-105 store API contract (`.gwc/scrums/SCRUM-105/contracts/store-api.md`) — for CAS, lease, fencing patterns
- SCRUM-105 node adapter contract (`.gwc/scrums/SCRUM-105/contracts/node-adapter.md`) — for handshake and request/result flow
- SCRUM-105 checkpoint schema (`.gwc/scrums/SCRUM-105/schemas/checkpoint.schema.json`) — for provenance binding patterns
- SCRUM-116 ownership/provenance contract (referenced, not yet fetched)
- BMAD procedure registry schema (`schemas/bmad-procedure-registry.schema.json`) — existing foundation

## 8. Validation Plan

1. Load BMAD skill and GWC skill; confirm skill instructions are applied
2. Validate all JSON schemas against `schemas/bmad-procedure-registry.schema.json`
3. Run positive execution examples through the adapter contract
4. Verify rejected scope-violation example is correctly blocked
5. Confirm idempotency key prevents duplicate side effects
6. Confirm BMAD cannot approve G2/G4/G5/G6 transitions
7. Confirm all outputs include provenance fields (task, repo, SHA, version, scope hash)
8. Create exact-SHA review evidence and attach to GWC run

## 9. Open Questions

1. SCRUM-116 ownership/provenance contract details — need to fetch and reference
2. Exact BMAD source/package commit and adapter version to pin in the registry
3. Whether the existing `schemas/bmad-procedure-registry.schema.json` is sufficient or needs extension for SCRUM-119 deliverables
4. GWC scope hash computation method (SHA of what exactly?)
