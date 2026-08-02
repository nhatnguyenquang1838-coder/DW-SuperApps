# SCRUM-182 Dependency and Traceability Map

**Date:** 2026-08-02  
**Task:** SCRUM-182 | intake_context.intake-card-render — M1 → M4  
**Gate:** G1 Discovery Complete

---

## 1. Upstream Dependencies (Blocking)

### SCRUM-175: intake_context Entity Definition

```
SCRUM-182 → SCRUM-175
           (must deliver before SCRUM-182-01)
```

| Aspect             | Dependency                                                                                              | Impact on SCRUM-182                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **Field list**     | Complete enum of all intake_context fields (id, created_at, customer_name, customer_phone, metadata, …) | Drives schema design in SCRUM-182-01; incomplete list → missing schema fields |
| **Field types**    | Types for each field (string, iso8601, object, number, …)                                               | Drives JSON Schema `type` properties; wrong types → validation failures       |
| **Nullable flags** | Which fields are required vs. optional (minOccurs, nullable in OpenAPI terms)                           | Drives schema `required` array; missed nullables → validation rejections      |
| **Constraints**    | Field validation rules (regex, length limits, format patterns)                                          | Drives schema `pattern`, `maxLength`, `format` properties                     |
| **Nesting**        | Structure of nested objects (e.g., metadata sub-fields)                                                 | Drives recursive schema definitions; missed nesting → incomplete coverage     |

**Evidence of completion:**

- Spec document: `SCRUM-175.md` or equivalent in `.kiro/specs/`
- Schema draft or acceptance criteria including example intake_context JSON
- No open questions in decision matrix

**Action if delayed:**

- Start SCRUM-182-01 with assumed schema (see decision_matrix in VALIDATION_GATES.yaml)
- Flag for spec review meeting by end of G2 day 2
- Lock schema once SCRUM-175 spec is available

---

### SCRUM-176: Redaction Rule Specification

```
SCRUM-182 → SCRUM-176
           (must deliver before SCRUM-182-01)
```

| Aspect                   | Dependency                                                                                        | Impact on SCRUM-182                                                      |
| ------------------------ | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Sensitive field list** | Which fields need redaction (customer_name, customer_phone, email, address, …)                    | Drives schema `x-redacted` markers; incomplete list → missing redactions |
| **Redaction formats**    | How to mask each field (phone: "**_-_**-XXXX", email: "XXX@domain.com", address: "[REDACTED]", …) | Drives renderer logic in SCRUM-182-03; ambiguous formats → test failures |
| **Partial vs. full**     | Which fields get partial masks (show last 4 digits) vs. full hide                                 | Drives regex patterns; wrong mask strategy → security misconfiguration   |
| **Fallback behavior**    | What to do if a sensitive field is missing or null                                                | Drives Task 3 error handling; undefined fallback → edge case bugs        |
| **Examples**             | Real intake_card examples showing redacted output                                                 | Drives test fixtures in Task 4; no examples → test design delays         |

**Evidence of completion:**

- Spec document: `SCRUM-176.md` or security/compliance decision matrix
- 5+ worked examples (original + redacted version)
- Decision matrix with rationale for each redaction rule

**Action if delayed:**

- Schedule spec review with security/compliance team by G2 day 1
- Use assumed redaction rules (see decision_matrix in VALIDATION_GATES.yaml) as placeholders
- Validation gate G1.2 becomes CONDITIONAL until rules are clear

---

### SCRUM-177: Immutability & Determinism Specification

```
SCRUM-182 → SCRUM-177
           (should deliver before SCRUM-182-03)
```

| Aspect                 | Dependency                                                               | Impact on SCRUM-182                                                              |
| ---------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| **No side effects**    | Clarify that render_intake_card() must not mutate input or global state  | Drives Task 3 design (pure function); violates → test failures in Task 4         |
| **Timestamp handling** | How to preserve input timestamps (no system clock injection)             | Drives Task 3 implementation; wrong approach → non-determinism detected by tests |
| **Field order**        | Stable field ordering (alphabetical, declaration order, or schema order) | Drives canonical JSON serialization; unstable order → determinism tests fail     |
| **Formatting rules**   | How to format numbers, dates, nested objects for determinism             | Drives Task 3 serialization; inconsistent formatting → hash mismatch in tests    |

**Evidence of completion:**

- Spec document: `SCRUM-177.md` or technical design
- Decision matrix: timestamp handling, field order, formatting rules
- Examples: input → output with annotations

**Action if delayed:**

- Low impact (can infer from SCRUM-175 + SCRUM-176)
- Use assumed rules in Task 3 implementation
- Validation gate G1.3 (Renderer Determinism) may need early test run to verify assumptions

---

### SCRUM-178: Error Handling Contract

```
SCRUM-182 → SCRUM-178
           (should deliver before SCRUM-182-03)
```

| Aspect                     | Dependency                                                                  | Impact on SCRUM-182                                                                        |
| -------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Invalid input behavior** | How to handle malformed intake_context (wrong type, missing required field) | Drives Task 3 error handling (raise vs. silent skip); ambiguity → inconsistent test design |
| **Logging strategy**       | What to log and at what level (warn, error, debug)                          | Drives Task 3 implementation; affects test assertions in Task 4                            |
| **Retry logic**            | Whether renderer should retry (typically no for pure function)              | Drives Task 3 signature and behavior contract; affects downstream integration              |
| **Exception types**        | Specific exceptions to raise (TypeError, ValueError, ValidationError, …)    | Drives Task 4 test design (expect statements); wrong types → test mismatches               |

**Evidence of completion:**

- Spec document: `SCRUM-178.md` or error-handling runbook
- Decision matrix: invalid input cases → expected behavior
- Examples: error scenarios with stack traces

**Action if delayed:**

- Moderate impact (can infer safe defaults)
- Use fail-closed assumption in Task 3 (raise on invalid input)
- Task 4 tests use flexible exception matching until spec clarifies

---

## 2. Intra-Task Dependencies (Serial)

### Task Dependency DAG

```
┌─────────────────────────────────────────────┐
│  SCRUM-175–178 (Upstream; External)         │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │ SCRUM-182-01           │
         │ Schema Definition      │
         │ (intake-card.schema)   │
         └─────────┬──────────────┘
                   │
       ┌───────────┴───────────┐
       │                       │
       ▼                       ▼
    182-02                  182-03
    Metadata              Renderer
    node.json             (Python)
       │                       │
       │                       │
       └───────────┬───────────┘
                   │
                   ▼
         ┌────────────────────────┐
         │ SCRUM-182-04           │
         │ Test Suite (19+ cases) │
         │ (RED-first validation) │
         └─────────┬──────────────┘
                   │
                   ▼
         ┌────────────────────────┐
         │ SCRUM-182-05           │
         │ Validation Gates       │
         │ (G1.1–G1.6 pass)       │
         └─────────┬──────────────┘
                   │
                   ▼
         ┌────────────────────────┐
         │ G2 EXECUTION READY     │
         │ (No blockers)          │
         └────────────────────────┘
```

### Critical Path (Serial Blocking)

| Sequence | Task                     | Duration | Cumulative | Blocker          |
| -------- | ------------------------ | -------- | ---------- | ---------------- |
| 1        | SCRUM-175–178 (upstream) | Varies   | —          | Yes (G1.5)       |
| 2        | SCRUM-182-01 (schema)    | 1–2d     | 1–2d       | Yes (G1.1, G1.2) |
| 3        | SCRUM-182-03 (renderer)  | 3–8d     | 4–10d      | Yes (G1.3, G1.4) |
| 4        | SCRUM-182-04 (tests)     | 2–5d     | 6–15d      | Yes (G1.3, G1.4) |
| 5        | SCRUM-182-05 (gates)     | 1–4d     | 7–19d      | Yes (G1.5, G1.6) |

**Critical path duration:** 12–19 days (serial, all upstream specs available)

### Parallel Opportunity

**Task 2 (metadata node.json)** can start immediately after **Task 1 (schema)** and develop in parallel with **Task 3 (renderer)**:

```
182-01 (schema) ──┬─→ 182-02 (metadata) ──┐
                  │                       │
                  └─→ 182-03 (renderer) ──┴─→ 182-04 (tests)
```

**Potential time saving:** 1–2 days if Tasks 2 and 3 are parallelized  
**Adjusted critical path:** 10–17 days with parallelization

---

## 3. Downstream Dependencies (Non-Blocking)

### intake-family Validator

```
SCRUM-182 ──(output)──→ [intake-family-validator task]
           (consumed)
```

| Aspect                 | Expectation                                            | Verification                                              |
| ---------------------- | ------------------------------------------------------ | --------------------------------------------------------- |
| **Function signature** | `render_intake_card(intake_context: dict) -> dict`     | Downstream task imports and calls function; no exceptions |
| **Output format**      | JSON dict matching `schemas/intake-card.schema.json`   | Downstream task validates output against schema           |
| **Error handling**     | Raises on invalid input; returns valid dict on success | Downstream task handles exceptions gracefully             |
| **Performance**        | Sub-second rendering per intake_context                | Downstream task benchmarks for bulk processing            |
| **Determinism**        | Same input always produces same output                 | Downstream task assumes idempotency                       |

**Downstream owner:** [TBD; intake-family-validator task owner]  
**Integration gate:** Non-blocking (G1.6); separate task handles any incompatibilities

---

### context-gap Evaluation Pipeline

```
SCRUM-182 ──(output)──→ [context-gap-evaluation task]
           (consumed)
```

| Aspect                    | Expectation                                                      | Verification                                                                   |
| ------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Bulk rendering**        | Ability to render 1000+ intake_cards efficiently                 | Downstream task benchmarks and optimizes if needed                             |
| **Batch error handling**  | Clear error messages when batch processing fails                 | Downstream task logs and reports failures                                      |
| **Metadata availability** | Optional metadata in redacted output available for gap detection | Downstream task inspects metadata fields in schema                             |
| **Extensibility**         | Schema allows future fields without breaking                     | Downstream task assumes `additionalProperties: false` false for forward compat |

**Downstream owner:** [TBD; context-gap-evaluation task owner]  
**Integration gate:** Non-blocking (G1.6); separate task handles any incompatibilities

---

## 4. Traceability Matrix

### Requirements → Implementation

| Requirement          | Source      | Task           | Verification                    | Status         |
| -------------------- | ----------- | -------------- | ------------------------------- | -------------- |
| intake_context shape | SCRUM-175   | 182-01         | Schema covers all fields        | TBD (upstream) |
| Redaction rules      | SCRUM-176   | 182-01, 182-03 | Schema markers + renderer logic | TBD (upstream) |
| Determinism          | SCRUM-177   | 182-03, 182-04 | Tests 13–14 pass; hash equality | TBD (upstream) |
| Error handling       | SCRUM-178   | 182-03, 182-04 | Tests 15–16; exception types    | TBD (upstream) |
| Immutability         | SCRUM-177   | 182-03         | No mutation assertions in tests | TBD (upstream) |
| Schema validation    | G1.1 (gate) | 182-01, 182-04 | AJV validation; test assertions | TBD (G1)       |
| Redaction validation | G1.2 (gate) | 182-01, 182-03 | Decision matrix + test coverage | TBD (G1)       |

### Implementation → Testing

| Task              | Output                                                                         | Test Input                           | Test Assertion                     | Status   |
| ----------------- | ------------------------------------------------------------------------------ | ------------------------------------ | ---------------------------------- | -------- |
| 182-01 (schema)   | `schemas/intake-card.schema.json`                                              | 10+ fixtures (positive + negative)   | AJV validates; no exceptions       | TBD (G1) |
| 182-02 (metadata) | `core/node-architect/node-catalog/intake_context/intake-card-render.node.json` | Metadata validator tool              | Node resolves; contracts traceable | TBD (G1) |
| 182-03 (renderer) | `tools/node_architect/intake_card_render.py`                                   | 19 test cases; edge cases            | All tests pass; 90%+ coverage      | TBD (G1) |
| 182-04 (tests)    | `tests/test_intake_context_intake_card_render_m4.py`                           | Task 3 output + fixtures             | pytest exit code 0; coverage ≥90%  | TBD (G1) |
| 182-05 (gates)    | `VALIDATION_GATES.yaml`                                                        | All 19 test results + upstream specs | All gates G1.1–G1.6 pass           | TBD (G1) |

### Testing → Deployment

| Test Result                                  | Gate       | Status      | Next Action                                      |
| -------------------------------------------- | ---------- | ----------- | ------------------------------------------------ |
| All 19 tests pass (Task 4)                   | G1.3, G1.4 | Ready       | Proceed to G2 execution                          |
| Determinism tests pass (Task 4, cases 13–14) | G1.3       | Ready       | Proceed to G2 execution                          |
| Validation gates G1.1–G1.6 pass              | G1.5, G1.6 | Ready       | Proceed to G2 execution                          |
| Any test fails                               | G1.3, G1.4 | Blocked     | Debug, fix, retest; re-validate gates            |
| Upstream spec incomplete (SCRUM-175–178)     | G1.5       | Conditional | Defer G2 or start with assumptions + spec review |

---

## 5. Deployment and Integration Sequencing

### G2 Execution Phase

**Files created/modified (in order):**

```
Week 1:
  Mon–Tue: SCRUM-182-01 (schema) + SCRUM-182-02 (metadata) ───→ PR #[TBD]
  Wed–Fri: SCRUM-182-03 (renderer) implementation              ───→ Review

Week 2:
  Mon–Tue: SCRUM-182-04 (test suite) + fixture refinement      ───→ PR #[TBD]
  Wed:     SCRUM-182-05 (validation gates) + decision matrix   ───→ PR #[TBD]
  Thu–Fri: Integration testing with downstream (non-blocking)  ───→ Feedback
```

### G3 PR Phase

- One PR per task (5 PRs total) OR one umbrella PR for all subtasks (TBD in G2 approval)
- Each PR must:
  - Pass CI: typecheck, test, lint
  - Include decision records (why this implementation)
  - Reference upstream specs (SCRUM-175–178) or flag missing contracts
  - Verify no merge conflicts with main

### G4 Merge Phase

- Merge order: 182-01 → 182-02 → 182-03 → 182-04 → 182-05
- Or merge together if umbrella PR
- No special production requirements (no schema migration, no RLS changes, no secrets)

### G5 Deployment Phase

- No deployment required (SCRUM-182 is pure code; no schema/migration/RLS)
- Renderer available in toolchain for downstream tasks immediately after merge

---

## 6. Handoff to Downstream Tasks

### intake-family Validator Task

**Handoff artifacts:**

- `tools/node_architect/intake_card_render.py` (function signature, error behavior)
- `schemas/intake-card.schema.json` (output validation reference)
- Test fixtures (optional, for integration testing)

**Handoff checklist:**

- [ ] Renderer function is importable: `from tools.node_architect.intake_card_render import render_intake_card`
- [ ] Function signature matches downstream expectations
- [ ] Error handling behavior is documented (what exceptions to expect)
- [ ] Performance characteristics documented (latency per intake_context)

### context-gap Evaluation Task

**Handoff artifacts:**

- `tools/node_architect/intake_card_render.py` (bulk rendering capability)
- `core/node-architect/node-catalog/intake_context/intake-card-render.node.json` (node identity)
- Node-architect tooling (if required for discovery)

**Handoff checklist:**

- [ ] Renderer supports bulk processing (no global state, idempotent)
- [ ] Redacted fields are stable (same input → same redaction every time)
- [ ] Metadata fields are available for gap detection logic
- [ ] Node catalog allows discovery of renderer without hardcoding path

---

## 7. Decision Record

### Key Decisions

| Decision                                            | Rationale                                                     | Alternative Considered                     | Status                                           |
| --------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------ |
| Python renderer (not TypeScript)                    | Toolchain; node-architect pattern uses Python                 | TypeScript implementation in `src/`        | Assumed; confirm in G1 approval                  |
| RED-first testing (19+ cases before implementation) | Ensures spec is clear before coding; catches edge cases early | Incremental testing during development     | Preferred; builds discipline                     |
| Static node metadata (separate from renderer)       | Supports discovery, dependency mapping, governance            | Metadata in renderer file or docstring     | Preferred; enables tooling ecosystem             |
| Determinism via test suite (not formal proof)       | Practical; catches most non-determinism bugs                  | Formal property-based testing (hypothesis) | Practical approach; can add property tests later |
| Schema-first design (contract before code)          | Validates upstream specs early; unblocks tests                | Code-first with schema validation later    | Preferred; avoids rework                         |

### Unresolved Questions

| Question                                      | Impact                      | Status                                                             | Action                                      |
| --------------------------------------------- | --------------------------- | ------------------------------------------------------------------ | ------------------------------------------- |
| Are SCRUM-175–178 specs available?            | Critical blocker if missing | Assume available by G2 day 2                                       | Check status before G1 approval             |
| Is node-architect tooling available?          | Nice-to-have for Task 2     | Can defer metadata validation if tooling unavailable               | Determine tooling status before G2          |
| Can we parallelize Tasks 2 and 3?             | Could save 1–2 days         | Yes, after schema is finalized                                     | Assign owners; coordinate start times in G2 |
| Is Python available in rental-home toolchain? | Required for Task 3         | Current repo is TypeScript/Node.js; verify if Python is acceptable | Confirm in G1 approval                      |

---

## 8. Risk Mitigation Plan

### Risk: Upstream Contract Incomplete

**Trigger:** SCRUM-175–178 not delivered by G2 day 2  
**Impact:** Tasks 3–5 blocked; estimated delay 2–5 days  
**Mitigation:**

1. Schedule spec review meeting by EOD G2 day 1
2. Use assumed schema (see VALIDATION_GATES.yaml decision_matrix) as placeholders
3. Lock schema once specs arrive; update Task 3 if needed
4. Flag delay to product owner; update critical path estimates

### Risk: Redaction Rules Ambiguous

**Trigger:** SCRUM-176 spec lacks worked examples or has conflicting rules  
**Impact:** Task 1 and Task 3 rework; estimated delay 1–3 days  
**Mitigation:**

1. Create redaction decision matrix with 5+ examples early in Task 1
2. Pair with security/compliance team during Task 1 schema design
3. Validate test fixtures (Task 4) against examples; flag mismatches early
4. If conflict arises, escalate to SCRUM-176 owner; don't speculate

### Risk: Determinism Hard to Verify

**Trigger:** Task 4 determinism tests (cases 13–14) fail intermittently  
**Impact:** Task 3 rework; estimated delay 1–2 days  
**Mitigation:**

1. Run determinism tests 10+ times; capture any hash mismatches
2. Use property-based testing (hypothesis library) to fuzz inputs if determinism fails
3. Add canonical JSON serialization (sort keys, consistent number formatting)
4. Pair with Task 3 owner to debug non-determinism source

### Risk: Downstream Consumer Incompatibility

**Trigger:** intake-family validator or context-gap evaluation task finds renderer incompatible  
**Impact:** SCRUM-182 rework or downstream task rework; estimated delay 1–3 days  
**Mitigation:**

1. Review downstream task specs (if available) before G1 approval
2. Design renderer for extensibility: `additionalProperties: false` in schema
3. Use generic `dict` output; allow downstream to add fields without breaking
4. Schedule early integration test (G2 day 3) if downstream specs are available

---

## 9. Sign-Off and Approval

**G1 Discovery Status:** COMPLETE  
**Ready for G1 Alignment Review:** YES

**Next Gates:**

- ✓ G0 (Context): Complete (this document)
- → G1 (Alignment): Ready for approval (awaiting gate authority)
- → G2 (Execution): Ready after G1 approval
- → G3 (PR): After G2 delivery
- → G4 (Merge): After G3 review
- → G5 (Deploy): After G4 merge (no special deployment)

**Approval Command Template (generated by gate authority):**

```
APPROVE G1 SCRUM-182 [scope_hash_16] [expires_at_utc]
```

---

**End of Dependency and Traceability Map**
