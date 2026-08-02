# SCRUM-182 G1 Discovery Index

**Task:** SCRUM-182 | [MAT-F1-N08] intake_context.intake-card-render — M1 → M4  
**Gate:** G1 Discovery Complete  
**Date:** 2026-08-02  
**Status:** READY FOR G1 ALIGNMENT REVIEW

---

## 📋 Quick Summary

SCRUM-182 implements a **deterministic, immutable, redacted intake_card projection renderer** following the node-architect M1→M4 maturity pattern. The task decomposes into **five sequential implementation tasks** with clear dependencies and validation gates.

**Critical facts:**

- **Duration:** 12–19 days (serial path, all upstream specs available)
- **Complexity:** Medium (deterministic projection, immutability, redaction logic)
- **Risk:** Medium (upstream contract clarity, redaction rule completeness)
- **Effort:** Low: 3d | Nominal: 8d | High: 16d (across all tasks)
- **Blocking:** Upstream SCRUM-175–181 must deliver contracts

---

## 📂 Artifact Structure

This discovery package contains:

```
.task-me/scrum-182-g1-discovery/
├── INDEX.md                                 (this file; navigation)
├── G1_DISCOVERY_BRIEF.md                    (detailed decomposition; 5 tasks)
├── VALIDATION_GATES.yaml                    (upstream blockers; success criteria)
├── DEPENDENCY_AND_TRACEABILITY_MAP.md       (DAG; parallel opportunities; handoff)
└── [Generated outputs from execution]
    ├── TASK_MATRIX.yaml                     (effort/complexity/risk summary)
    ├── CRITICAL_PATH.mmd                    (Mermaid diagram; task sequencing)
    └── INTEGRATION_CHECKLIST.md             (G2 readiness; downstream handoff)
```

---

## 📖 Reading Guide

**For decision-makers (5 min read):**

1. This INDEX (you are here)
2. **G1_DISCOVERY_BRIEF.md** § 1–2 (Executive Summary + Strategy)
3. **VALIDATION_GATES.yaml** (Upstream blockers; success criteria)

**For task owners (15 min read):**

1. **G1_DISCOVERY_BRIEF.md** § 3 (Concrete Implementation Tasks)
2. **DEPENDENCY_AND_TRACEABILITY_MAP.md** § 2 (Task Dependencies)
3. Assigned task section (e.g., "Task 1: intake-card Artifact Schema")

**For integration owners (10 min read):**

1. **DEPENDENCY_AND_TRACEABILITY_MAP.md** § 3–5 (Downstream; Integration Sequencing; Handoff)
2. **G1_DISCOVERY_BRIEF.md** § 7 (Integration Handoff Checklist)

**For risk/compliance review (20 min read):**

1. **VALIDATION_GATES.yaml** (All upstream blockers; decision matrix; unresolved questions)
2. **G1_DISCOVERY_BRIEF.md** § 4–5 (Risk Assessment; Dependency Ordering)
3. **DEPENDENCY_AND_TRACEABILITY_MAP.md** § 8 (Risk Mitigation Plan)

---

## 🎯 Key Deliverables

### G1 Discovery Output

| Artifact             | File                               | Purpose                                                                             |
| -------------------- | ---------------------------------- | ----------------------------------------------------------------------------------- |
| **Discovery Brief**  | G1_DISCOVERY_BRIEF.md              | Detailed task decomposition (5 tasks × files/effort/complexity/acceptance criteria) |
| **Validation Gates** | VALIDATION_GATES.yaml              | Upstream blockers; success criteria; decision matrix; unresolved questions          |
| **Traceability Map** | DEPENDENCY_AND_TRACEABILITY_MAP.md | Task DAG; parallel opportunities; integration sequencing; handoff checklist         |
| **Index**            | INDEX.md                           | Navigation guide (this file)                                                        |

### Pre-G2 Checklist

Before G2 authorization, complete:

- [ ] **Upstream contract verification:** SCRUM-175–178 specs available or scheduled delivery by G2 day 2
- [ ] **Downstream consumer review:** intake-family validator and context-gap evaluation task specs reviewed (non-blocking, but helps avoid rework)
- [ ] **Tooling confirmation:** Python runtime available in rental-home toolchain; node-architect tooling availability confirmed (optional, but helpful)
- [ ] **Owner assignment:** One owner per task (1 person per task or serial owner); coordinate start times for parallel opportunities
- [ ] **Risk mitigation:** Review DEPENDENCY_AND_TRACEABILITY_MAP.md § 8; assign escalation points for upstream delays

---

## 🔗 Five Implementation Tasks

### Task 1: intake-card Artifact Schema Definition

**ID:** SCRUM-182-01 | **Duration:** 1–3d | **Complexity:** Low | **Risk:** Low

Deliverable: `schemas/intake-card.schema.json`  
Validation: AJV validation of 10+ fixtures; schema covers SCRUM-175–178 fields

→ See **G1_DISCOVERY_BRIEF.md § 3.1** for details

---

### Task 2: intake-card-render Node Descriptor

**ID:** SCRUM-182-02 | **Duration:** 1–2d | **Complexity:** Low | **Risk:** Low

Deliverable: `core/node-architect/node-catalog/intake_context/intake-card-render.node.json`  
Validation: Node metadata valid; contracts traceable; maturity level = M4

→ See **G1_DISCOVERY_BRIEF.md § 3.2** for details

---

### Task 3: intake-card-render Python Renderer

**ID:** SCRUM-182-03 | **Duration:** 3–8d | **Complexity:** Medium | **Risk:** Medium

Deliverable: `tools/node_architect/intake_card_render.py`  
Function: `render_intake_card(intake_context: dict) -> dict`  
Validation: 19+ test cases pass; deterministic; redaction rules applied; output validates against schema

→ See **G1_DISCOVERY_BRIEF.md § 3.3** for details

---

### Task 4: intake-card-render RED-First Test Suite

**ID:** SCRUM-182-04 | **Duration:** 2–5d | **Complexity:** Medium | **Risk:** Low

Deliverable: `tests/test_intake_context_intake_card_render_m4.py` (19+ test cases)  
Validation: All tests pass; ≥90% coverage; happy path + redaction + edge cases + determinism + validation + error handling

→ See **G1_DISCOVERY_BRIEF.md § 3.4** for details

---

### Task 5: intake-card Validation Gates and Upstream Contract Verification

**ID:** SCRUM-182-05 | **Duration:** 1–4d | **Complexity:** Medium | **Risk:** Medium

Deliverable: `.task-me/scrum-182/VALIDATION_GATES.yaml` + `.task-me/scrum-182/DEPENDENCY_MAP.md`  
Validation: All gates G1.1–G1.6 pass; no unresolved blockers; downstream readiness confirmed

→ See **G1_DISCOVERY_BRIEF.md § 3.5** for details

---

## 📊 At-a-Glance Metrics

### Effort Estimates (Three-Point)

| Task                             | Low    | Nominal | High    | Critical Path | Notes                                   |
| -------------------------------- | ------ | ------- | ------- | ------------- | --------------------------------------- |
| SCRUM-182-01                     | 1d     | 2d      | 3d      | **2d**        | Schema definition; blocks all others    |
| SCRUM-182-02                     | 1d     | 1.5d    | 2d      | —             | Metadata; can parallel with Task 3      |
| SCRUM-182-03                     | 3d     | 4d      | 8d      | **4d**        | Renderer implementation                 |
| SCRUM-182-04                     | 2d     | 3d      | 5d      | **3d**        | Test suite; depends on Task 3           |
| SCRUM-182-05                     | 1d     | 2d      | 4d      | **2d**        | Validation gates; final readiness check |
| **Subtotal (serial)**            | **7d** | **12d** | **22d** | **13d**       | With upstream specs available           |
| **Subtotal (with parallel 1+3)** | **7d** | **10d** | **19d** | **11d**       | Task 2 in parallel with Task 3          |

### Complexity and Risk Summary

| Task   | Complexity | Risk   | Mitigation                                                              |
| ------ | ---------- | ------ | ----------------------------------------------------------------------- |
| 182-01 | Low        | Low    | Schema-first validation; early review with upstream                     |
| 182-02 | Low        | Low    | Use reference implementations; lightweight task                         |
| 182-03 | Medium     | Medium | RED-first testing; property-based testing if needed; pair with Task 4   |
| 182-04 | Medium     | Low    | 19+ test cases cover all scenarios; no new tech                         |
| 182-05 | Medium     | Medium | Escalation path for upstream delays; decision matrix tracks assumptions |

---

## 🚦 Validation Gates (G1 to G2 Transition)

| Gate     | Checkpoint            | Success Criteria                                       | Status             |
| -------- | --------------------- | ------------------------------------------------------ | ------------------ |
| **G1.1** | Contract Completeness | Schema covers all SCRUM-175–178 fields                 | TBD (upstream)     |
| **G1.2** | Redaction Rules       | All SCRUM-176 patterns marked in schema                | TBD (upstream)     |
| **G1.3** | Renderer Determinism  | Test cases 13–14 pass; hash equality verified          | TBD (G2)           |
| **G1.4** | Output Validation     | All 19+ test outputs validate against schema           | TBD (G2)           |
| **G1.5** | Upstream Clarity      | All SCRUM-175–178 specs available & unambiguous        | TBD (upstream)     |
| **G1.6** | Downstream Readiness  | intake-family validator & context-gap tasks compatible | TBD (non-blocking) |

**Gate decision:** G1 PASSES when G1.1–G1.5 are met; G1.6 is non-blocking (separate task handles integration)

---

## 🔄 Task Sequencing

### Critical Path (Serial, No Parallelization)

```
SCRUM-175–181 (upstream specs)
    ↓ (assume available by G2 day 2)
SCRUM-182-01 (schema definition)    — 2d
    ↓
SCRUM-182-03 (renderer)             — 4d
    ↓
SCRUM-182-04 (test suite)           — 3d
    ↓
SCRUM-182-05 (validation gates)     — 2d
────────────────────────────────────────
Total: ~13 days
```

### Optimized Path (With Parallelization)

```
SCRUM-175–181 (upstream specs)
    ↓
SCRUM-182-01 (schema)               — 2d
    ├─→ SCRUM-182-02 (metadata)     — 1.5d (parallel with next task)
    │
    └─→ SCRUM-182-03 (renderer)     — 4d
            ↓
        SCRUM-182-04 (tests)        — 3d
            ↓
        SCRUM-182-05 (gates)        — 2d
────────────────────────────────────────
Total: ~11 days (saves ~2 days)
```

---

## 🎬 Getting Started (Next Steps)

### Before G1 Approval

1. **Verify upstream contracts:**
   - [ ] SCRUM-175–178 specs exist and are scheduled
   - [ ] Schedule spec review meeting (day 1 of G2)

2. **Confirm tooling:**
   - [ ] Python 3.8+ available in rental-home environment
   - [ ] node-architect tools available (optional, but helpful for Task 2)

3. **Assign owners:**
   - [ ] Task 1 owner: schema design + validation
   - [ ] Task 2 owner: node metadata
   - [ ] Task 3 owner: renderer implementation
   - [ ] Task 4 owner: test suite design + execution
   - [ ] Task 5 owner: validation gates + final sign-off

4. **Review risk mitigations:**
   - [ ] DEPENDENCY_AND_TRACEABILITY_MAP.md § 8 (Risk Mitigation Plan)
   - [ ] Escalation points assigned for upstream delays

### After G1 Approval (G2 Execution)

**Week 1:**

- [ ] Day 1–2: Task 1 (schema) + Task 2 (metadata) start; spec review meeting
- [ ] Day 3–5: Task 3 (renderer) implementation begins; Task 2 completes

**Week 2:**

- [ ] Day 1–3: Task 4 (test suite) development; Task 3 refinement
- [ ] Day 4–5: Task 5 (validation gates) completion; final sign-off

**Week 3:**

- [ ] Day 1–2: Integration testing with downstream tasks (non-blocking)
- [ ] Day 3–5: PR review, CI validation, merge (G3 → G4)

---

## 📞 Contacts & Escalation

**Task Coordination:**

- Assign one SCRUM-182 coordinator to track dependencies and escalate upstream delays

**Upstream Contact (SCRUM-175–181 Owner):**

- [TBD] — Responsible for intake_context specs, redaction rules, error handling contract

**Downstream Contact (intake-family Validator):**

- [TBD] — Integration point; non-blocking (separate task handles compatibility)

**Downstream Contact (context-gap Evaluation):**

- [TBD] — Integration point; non-blocking (separate task handles compatibility)

---

## 📝 Document Version History

| Version | Date       | Author            | Change                        |
| ------- | ---------- | ----------------- | ----------------------------- |
| 1.0     | 2026-08-02 | task-me discovery | Initial G1 discovery complete |

---

## ✅ Approval Checklist

**G1 Discovery is READY FOR ALIGNMENT REVIEW when:**

- [x] Five tasks decomposed with concrete files, functions, and test cases
- [x] Upstream blockers identified (SCRUM-175–178)
- [x] Validation gates documented (G1.1–G1.6)
- [x] Risk factors assessed with mitigation strategies
- [x] Effort estimates provided (three-point: low/nominal/high)
- [x] Test strategy defined (RED-first, 19+ test cases)
- [x] Traceability matrix complete (requirements → implementation → testing)
- [x] No unresolved uncertainty blocking G1 decision

**Next Action:** Awaiting G1 alignment review and approval. Approval command:

```
APPROVE G1 SCRUM-182 [scope_hash_16] [expires_at_utc]
```

---

**End of Index**

For detailed information on any task, refer to **G1_DISCOVERY_BRIEF.md** § 3.  
For upstream blockers, refer to **VALIDATION_GATES.yaml**.  
For integration sequencing, refer to **DEPENDENCY_AND_TRACEABILITY_MAP.md**.
