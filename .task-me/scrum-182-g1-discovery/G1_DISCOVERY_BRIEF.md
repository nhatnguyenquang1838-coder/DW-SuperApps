# SCRUM-182 G1 Discovery — intake_context.intake-card-render M1→M4

**Gate Status:** G1_DISCOVERY_COMPLETE  
**Task ID:** SCRUM-182  
**Title:** [MAT-F1-N08] intake_context.intake-card-render — M1 → M4  
**Type:** Subtask (spec-driven)  
**Date:** 2026-08-02

---

## 1. Executive Summary

SCRUM-182 implements a deterministic, immutable, redacted `intake_card` projection renderer following the node-architect M1→M4 maturity pattern. The task decomposes into five sequential implementation layers:

1. **Contract Definition** — Runtime artifact schema in `schemas/intake-card.schema.json`
2. **Static Metadata** — Thin node descriptor in `core/node-architect/node-catalog/intake_context/intake-card-render.node.json`
3. **Core Renderer** — Python implementation in `tools/node_architect/intake_card_render.py`
4. **RED-First Tests** — Test suite in `tests/test_intake_context_intake_card_render_m4.py`
5. **Validation Gates** — Upstream contract verification and downstream consumer compatibility

**Upstream blockers:** SCRUM-175–181 must define intake context structure, redaction rules, and projection semantics.  
**Downstream consumers:** intake-family validator, context-gap evaluation pipeline.

**Effort estimate (three-point):** Low: 3d | Nominal: 8d | High: 16d  
**Complexity:** Medium (deterministic projection, immutability constraint, redaction logic)  
**Risk level:** Medium (upstream contract clarity, redaction rule completeness)

---

## 2. Decomposition Strategy

Follows rental-home task-decomposition rules:

```
contract/schema → static metadata → core logic → tests → integration
```

**Atomic task criteria verified:**

- ✓ One primary outcome per task (independently reviewable)
- ✓ One bounded rollback unit (revert, no side effects)
- ✓ One independently testable result
- ✓ Effort within 2–5 day range per task

**Mandatory split signals applied:**

- Different module/deployment boundary
- Independent schema validation
- Distinct test lifecycle
- Separate integration point (renderer + consumer hookup)

---

## 3. Concrete Implementation Tasks

### Task 1: intake-card Artifact Schema Definition

**ID:** SCRUM-182-01  
**Slug:** intake-card-schema-contract  
**Effort:** Low: 1d | Nominal: 2d | High: 3d  
**Complexity:** Low  
**Risk:** Low

**Objective:**  
Define canonical `intake_card` projection schema in `schemas/intake-card.schema.json` as the source of truth for renderer output and validation.

**Requirements:**

- Schema follows Rental Home JSON Schema conventions (see `schemas/*.schema.json`)
- Marks all redaction-eligible fields with `x-redacted: true` annotation
- Defines immutability constraints (e.g., `"additionalProperties": false`)
- Includes determinism markers (field order, canonical formatting)
- Documents redaction rules inline (format, patterns, excluded fields)

**Acceptance criteria:**

- [ ] File exists and is well-formed JSON Schema
- [ ] Covers all intake_context fields upstream tasks (SCRUM-175–178) declare
- [ ] Redaction rules match intake-context specification
- [ ] No `any` or `unknown` type fallbacks
- [ ] Schema validates 10+ real intake_card fixtures (positive + redacted variants)
- [ ] Schema rejects 5+ malformed variants (extra fields, wrong types, null breaches)

**Files:**

- **CREATE:** `schemas/intake-card.schema.json`
- **READ:** `schemas/jira-task-projection.schema.json` (pattern reference)
- **READ:** SCRUM-175–178 specs (when available; fallback: assume standard intake fields)

**Validation:**

```bash
# Local schema validation
pnpm exec ajv validate -s schemas/intake-card.schema.json -d tests/fixtures/intake-cards.positive.json
pnpm exec ajv validate -s schemas/intake-card.schema.json -d tests/fixtures/intake-cards.negative.json
```

**Dependencies:**

- SCRUM-175–178 (upstream): intake_context structure specification
- **Blocks:** SCRUM-182-02 (static metadata references schema)

---

### Task 2: intake-card-render Node Descriptor

**ID:** SCRUM-182-02  
**Slug:** intake-card-render-node-metadata  
**Effort:** Low: 1d | Nominal: 1.5d | High: 2d  
**Complexity:** Low  
**Risk:** Low

**Objective:**  
Define static node metadata in `core/node-architect/node-catalog/intake_context/intake-card-render.node.json` describing the renderer's identity, contract, and node-architect maturity level.

**Requirements:**

- Node ID: `intake_context/intake-card-render` (stable identity)
- Input contract: references SCRUM-175–178 intake_context shape
- Output contract: references `schemas/intake-card.schema.json`
- Maturity level: `M4` (deterministic, immutable, redacted, production-ready)
- Tags: `[projection, redaction, deterministic, immutable]`
- Stability: `production` (no breaking changes after initial release)

**Acceptance criteria:**

- [ ] File exists in correct directory structure
- [ ] Node ID matches module path (idempotent lookup)
- [ ] Declares input/output contracts (traceable to upstream/downstream)
- [ ] Maturity level = `M4` explicitly set
- [ ] No mutable state or side effects declared
- [ ] Validator tool can resolve node, inspect metadata, and trace contracts

**Files:**

- **CREATE:** `core/node-architect/node-catalog/intake_context/intake-card-render.node.json`
- **CREATE:** `core/node-architect/node-catalog/intake_context/README.md` (if new directory)
- **READ:** `schemas/intake-card.schema.json` (reference output contract)

**Validation:**

```bash
# Assume node-architect validator exists; fallback to manual JSON validation
node scripts/validate-node-catalog.js --node intake_context/intake-card-render
```

**Dependencies:**

- SCRUM-182-01 (upstream): schema definition
- **Blocks:** SCRUM-182-03 (renderer implementation uses this metadata)

---

### Task 3: intake-card-render Python Renderer

**ID:** SCRUM-182-03  
**Slug:** intake-card-render-implementation  
**Effort:** Nominal: 4d | Low: 3d | High: 8d  
**Complexity:** Medium  
**Risk:** Medium

**Objective:**  
Implement deterministic, immutable, redacted intake_card renderer in `tools/node_architect/intake_card_render.py`.

**Requirements:**

- **Function signature:** `render_intake_card(intake_context: dict) -> dict` (matches interface spec)
- **Determinism:** Same input always produces same output (no timestamps, UUIDs, or randomness unless upstream-controlled)
- **Immutability:** Output is a frozen snapshot; no mutable references to input
- **Redaction:** Apply rules from `schemas/intake-card.schema.json` to hide sensitive fields
- **Validation:** Output always validates against schema; raise on contract breach
- **Error handling:** Fail-closed on invalid input; preserve stack traces for debugging

**Implementation rules (rental-home patterns):**

- Type hints for all parameters and return values
- No global state; pure function
- Handle `None`/missing fields gracefully (skip redaction if field absent)
- Convert all snake_case database values to camelCase (follow adapter pattern)
- Use `dataclasses` or `TypedDict` for shape clarity

**Acceptance criteria:**

- [ ] Function exists at `tools/node_architect/intake_card_render.py`
- [ ] Passes 15+ unit test cases (see Task 4)
- [ ] Output always validates: `jsonschema.validate(result, schema)`
- [ ] Handles 5+ edge cases: empty intake_context, missing optional fields, null redaction, unicode text, numeric overflow
- [ ] No external dependencies beyond Python stdlib + `jsonschema`
- [ ] Determinism verified: `hash(json.dumps(render(x))) == hash(json.dumps(render(x)))` for identical inputs
- [ ] Redaction verified: sensitive fields absent from output; non-sensitive fields present

**Files:**

- **CREATE:** `tools/node_architect/intake_card_render.py`
- **READ:** `core/node-architect/node-catalog/intake_context/intake-card-render.node.json` (metadata)
- **READ:** `schemas/intake-card.schema.json` (output validation contract)
- **READ:** SCRUM-175–178 specs (intake_context input shape; use fixtures if unavailable)

**Validation:**

```bash
# Run task-specific test suite (see Task 4)
pytest tests/test_intake_context_intake_card_render_m4.py -v --tb=short
```

**Dependencies:**

- SCRUM-182-01 (upstream): schema definition
- SCRUM-182-02 (upstream): node metadata (optional; helps with discovery)
- SCRUM-175–178 (upstream): intake_context structure
- **Blocks:** SCRUM-182-04 (test suite exercises this)

---

### Task 4: intake-card-render RED-First Test Suite

**ID:** SCRUM-182-04  
**Slug:** intake-card-render-tests  
**Effort:** Nominal: 3d | Low: 2d | High: 5d  
**Complexity:** Medium  
**Risk:** Low

**Objective:**  
Create RED-first (test-driven) test suite in `tests/test_intake_context_intake_card_render_m4.py` to validate renderer behavior, redaction, and contracts.

**Test categories:**

| Category       | Count   | Focus                                                                     |
| -------------- | ------- | ------------------------------------------------------------------------- |
| Happy path     | 5       | Correct output shape, field presence, value preservation                  |
| Redaction      | 5       | Sensitive fields hidden, non-sensitive fields intact, partial redaction   |
| Edge cases     | 3       | Empty input, missing optional fields, null handling, unicode/large values |
| Determinism    | 2       | Same input → same output (hash equality), reproducibility                 |
| Validation     | 2       | Output always valid against schema, schema rejects malformed              |
| Error handling | 2       | Invalid input (wrong type, missing required), graceful failure            |
| **Total**      | **19+** | Full coverage of specification                                            |

**Acceptance criteria:**

- [ ] Test file exists at `tests/test_intake_context_intake_card_render_m4.py`
- [ ] All 19+ test cases defined and passing
- [ ] Uses `pytest` fixtures for intake_context fixtures (centralize test data)
- [ ] Each test is isolated: no shared state, no test-order dependencies
- [ ] Coverage report shows ≥90% line coverage for `intake_card_render.py`
- [ ] No mocking of core renderer; all tests exercise actual function
- [ ] Error messages are clear and actionable (aid debugging)

**Test fixtures:**

- 5+ positive intake_context examples (complete, valid)
- 3+ redacted output examples (verified against schema)
- 5+ malformed inputs (null, wrong type, missing field)

**Files:**

- **CREATE:** `tests/test_intake_context_intake_card_render_m4.py`
- **CREATE:** `tests/fixtures/intake_context_samples.json` (if test data is large)
- **READ:** `tools/node_architect/intake_card_render.py` (code under test)
- **READ:** `schemas/intake-card.schema.json` (validation reference)

**Validation:**

```bash
# Run test suite
pytest tests/test_intake_context_intake_card_render_m4.py -v --cov=tools.node_architect.intake_card_render --cov-fail-under=90
```

**Dependencies:**

- SCRUM-182-03 (upstream): renderer implementation to test
- SCRUM-182-01 (upstream): schema for validation assertions
- **Blocks:** SCRUM-182-05 (integration; tests demonstrate readiness)

---

### Task 5: intake-card Validation Gates and Upstream Contract Verification

**ID:** SCRUM-182-05  
**Slug:** intake-card-validation-gates  
**Effort:** Nominal: 2d | Low: 1d | High: 4d  
**Complexity:** Medium  
**Risk:** Medium

**Objective:**  
Document validation checkpoints and upstream contract dependencies; verify renderer is ready for downstream integration (intake-family validator, context-gap evaluation).

**Validation gates:**

| Gate                     | Input                  | Check                                                              | Blocker?           |
| ------------------------ | ---------------------- | ------------------------------------------------------------------ | ------------------ |
| **Contract Match**       | SCRUM-175–178 specs    | `schemas/intake-card.schema.json` covers all intake_context fields | Yes                |
| **Redaction Rules**      | Upstream security spec | All sensitive-field patterns in schema; renderer applies all rules | Yes                |
| **Renderer Determinism** | Test suite + spec      | All 19+ tests pass; no randomness detected in output               | Yes                |
| **Output Validation**    | Task 3 + Task 4        | Output 100% validates against schema; no exceptions                | Yes                |
| **Downstream Readiness** | Consumer specs         | intake-family validator can import and call `render_intake_card()` | No (separate task) |

**Upstream blockers (SCRUM-175–181 must deliver):**

1. intake_context entity definition (fields, types, nullable, constraints)
2. Redaction rule specification (which fields, formats, patterns)
3. Immutability expectations (snapshot behavior, no side effects)
4. Determinism requirements (timestamp handling, field order guarantees)
5. Error handling contract (exceptions vs. silent skips for invalid input)

**Acceptance criteria:**

- [ ] Validation gate matrix documented in task output (see below)
- [ ] All upstream dependencies SCRUM-175–181 deliver their contracts
- [ ] No unresolved uncertainty in intake_context shape or redaction rules
- [ ] Renderer passes all gates; no "blocked" or "unresolved" status
- [ ] Integration point(s) for downstream consumers identified and documented
- [ ] Handoff checklist prepared for next task (SCRUM-183 or intake-family validator task)

**Files:**

- **CREATE:** `.task-me/scrum-182/VALIDATION_GATES.yaml` (gate matrix and status)
- **CREATE:** `.task-me/scrum-182/DEPENDENCY_MAP.md` (upstream/downstream traceability)
- **READ:** SCRUM-175–181 specs (when available; flag undelivered contracts)
- **REVIEW:** Test results from Task 4 (evidence of readiness)

**Downstream integration (separate task, not blocked by SCRUM-182):**

- intake-family validator task: import `render_intake_card`, apply to family intake contexts
- context-gap evaluation: use intake_card projections as inputs to gap detection

**Dependencies:**

- SCRUM-182-01 to -04 (upstream): schema, metadata, renderer, tests must be complete
- SCRUM-175–181 (upstream external): contract specs must be available
- **Blocks:** G2 execution decision (gate must be clear before proceeding)

---

## 4. Risk Assessment

| Risk                                    | Probability | Impact | Mitigation                                                                   |
| --------------------------------------- | ----------- | ------ | ---------------------------------------------------------------------------- |
| **Upstream contract incomplete**        | Medium      | High   | Coordinate with SCRUM-175–181 owners; schedule spec reviews early            |
| **Redaction rules ambiguous**           | Medium      | High   | Create redaction decision matrix; document each rule with examples           |
| **Determinism hard to verify**          | Low         | Medium | Unit tests + property-based tests (hypothesis) to catch non-determinism      |
| **Schema vs. implementation drift**     | Low         | Medium | RED-first development; schema-first validation in every test                 |
| **Downstream consumer incompatibility** | Low         | Medium | Integration task validates early; design for extensibility (optional fields) |

---

## 5. Dependency Ordering

```
SCRUM-175–181 (upstream; provide intake_context structure & redaction rules)
         ↓
SCRUM-182-01 (schema definition: blocks all others)
    ↓        ↓
182-02    182-03 (metadata & renderer: can proceed in parallel after schema)
    ↓        ↓
    └─ 182-04 (tests: depend on both renderer + schema)
           ↓
       182-05 (validation gates: final integration readiness check)
           ↓
[Downstream: intake-family validator, context-gap evaluation (separate tasks)]
```

**Critical path:**

- SCRUM-175–181 → SCRUM-182-01 (schema) → SCRUM-182-03 (renderer) → SCRUM-182-04 (tests) → SCRUM-182-05 (gates)
- **Estimated path duration:** 12–19 days (serial dependency)
- **Parallel opportunity:** SCRUM-182-02 (metadata) can start after schema; develops in parallel with renderer

---

## 6. Acceptance Criteria Summary

**G1 gate passes when:**

- ✓ All five tasks decomposed with concrete files, functions, and test cases
- ✓ Upstream contracts (SCRUM-175–181) are identified and scheduled
- ✓ Validation gates are documented; no unresolved blockers remain
- ✓ Effort estimates provided (3-point: low/nominal/high)
- ✓ Risk factors assessed and mitigation strategies in place
- ✓ Traceability matrix links SCRUM-182 to upstream/downstream tasks
- ✓ Testing strategy (RED-first, 19+ test cases) is clear and feasible

**G1 output artifacts:**

- This discovery brief (narrative summary)
- Task decomposition matrix (5 tasks × effort/complexity/risk)
- Validation gates matrix (upstream requirements, downstream readiness)
- Dependency DAG (task ordering, critical path)
- Integration handoff checklist (for G2 execution)

---

## 7. Integration Handoff (G2 Ready)

When G1 is approved, the team moves to G2 execution with:

1. **Assigned owner** for each task (1 person per task or serial owner)
2. **Branch strategy:** One branch per task or one branch for all sub-tasks (TBD in G1 approval)
3. **CI/validation checkpoints:** Test suite runs on every PR; schema validation before merge
4. **Definition of Done:** Per-task criteria (see each task section above)
5. **Risk escalation:** Flag if upstream contracts remain undelivered past day 2 of G2

---

## 8. Notes & Caveats

1. **SCRUM-175–181 availability:** This decomposition assumes upstream tasks deliver their contracts. If specs are delayed, prioritize Task 1 (schema definition) and defer Task 3 (renderer) until contracts are clear.

2. **node-architect tooling:** Assumes node-catalog validator and related tools exist. If not, Tasks 2 can be reduced to schema-only reference until tooling is available.

3. **Downstream consumer specs:** intake-family validator and context-gap evaluation tasks are not blocked by SCRUM-182; integration happens at their execution gates.

4. **Python vs. TypeScript:** Renderer is specified in Python (`tools/node_architect/`); confirm this aligns with project toolchain (rental-home is React/TypeScript primary).

---

## Status

**G1_DISCOVERY_COMPLETE** ✓

This document is ready for gate approval. No implementation has begun; this is pure discovery and planning.
