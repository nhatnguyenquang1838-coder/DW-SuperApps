# GWC Gate G1 Integration: BMAD Procedure Adapter

## Gate Context
This document defines how the GWC governance workflow interacts with the BMAD procedure adapter at Gate G1 for SCRUM-119 implementation.

### Gate G1 Purpose
Gate G1 in the GWC workflow handles:
- Task decomposition and validation planning (delegated to task-me)
- Architecture design and data modeling (delegated to bmad)  
- Dependency mapping and impact analysis (delegated to ua)

For SCRUM-119 (BMAD procedure-adapter contracts and authority boundaries), Gate G1 delegates to BMAD for architecture-design and data-modeling intents.

## Integration Points

### 1. GWC Delegation to BMAD at Gate G1
When GWC reaches Gate G1 with SCRUM-119 context, it delegates to BMAD for:
- Architecture design of the procedure adapter contract
- Data modeling of procedure request/result schemas
- Authority boundary definition

### 2. Input to BMAD from GWC
GWC provides BMAD with:
- Parent artifact ID: SCRUM-119
- Target repository: nhatnguyenquang1838-coder/DW-SuperApps
- Target reference: main branch
- Procedure scope: BMAD procedure adapter for P4
- GWC scope hash: [computed from current gate context]

### 3. BMAD Output to GWC
BMAD returns to GWC at Gate G1:
- Procedure request/result schemas
- Permission/action matrix  
- Execution examples (positive and negative)
- Validator/test plan
- All outputs include provenance binding to SCRUM-119

### 4. Gate G1 Decision Criteria
GWC uses BMAD output to make Gate G1 go/no-go decision based on:
- Schema validity and completeness
- Permission boundary compliance  
- Authority boundary adherence (no gate self-approval, no state mutation)
- Idempotency guarantees
- Exact-SHA traceability

## BMAD Procedure Adapter Contract Gates

The BMAD procedure adapter itself defines gate recommendations in its result schema:

```json
"gateRecommendations": [
  {
    "gate": "G2|G4|G5|G6", 
    "recommendation": "approve|block|defer",
    "evidence": "string",
    "note": "BMAD recommendations are read-only evidence. Actual gate transitions are performed by GWC only."
  }
]
```

### Gate G2 (Execution Readiness)
BMAD may recommend G2 progression based on:
- Successful procedure execution within authority boundaries
- Valid evidence artifacts produced
- No scope violations detected

### Gate G4 (Merge Readiness) 
BMAD may recommend G4 progression based on:
- Procedure outputs meeting quality gates
- No prohibited operations attempted
- All outputs within declared ownership boundaries

### Gate G5 (Deployment Readiness)
BMAD may recommend G5 progression based on:
- Deployment-safe artifacts generated
- No production operationally
- Zero state mutation attempts detected

### Gate G6 (Production Release)
BMAD may recommend G6 progression based on:
- Release procedure completed successfully
- All artifacts validated and signed
- No authority boundary breaches

## GWC Enforcement Mechanisms

### Authority Boundaries Enforced by GWC
GW C ensures BMAD adapter never:
1. ❌ Approves G2/G4/G5/G6 transitions (gate approval is GWC-exclusive)
2. ❌ Mutates .gwc canonical state  
3. ❌ Expands scope without explicit GWC authorization
4. ❌ Performs Jira/Notion/Slack projection writes
5. ❌ Publishes BMAD packages or performs deploy/releases

### Validation at Gate G1
GWC validates BMAD procedure adapter contract by checking:
- [x] Schema compliance (request/result/permission/registry)
- [x] Authority boundary adherence  
- [x] Idempotency policy effectiveness
- [x] Provenance completeness (task, repo, SHA, version, scope hash)
- [x] Output path restrictions (.bmad/**, _bmad/**, _bmad-output/**, docs/**)
- [x] Action permissions (read/analyze/report/write/create/update only in bounds)
- [x] Prohibited actions blocked (.gwc/**, state mutation, self-approval)

## Integration Example: SCRUM-119 Flow

```mermaid
sequenceDiagram
    participant GWC as GWC Workflow
    participant BMAD as BMAD Adapter
    participant UA as UA Analysis
    participant TM as Task-Me Planning
    
    GWC->>GWC: Reach Gate G1 (Sprint Planning)
    GWC->>BMAD: Delegate SCRUM-119 (architecture-design, data-modeling)
    BMAD->>UA: Request dependency mapping (per SCRUM-119)
    UA-->>BMAD: Return UA artifact references
    BMAD->>TM: Request validation planning (per SCRUM-119)  
    TM-->>BMAD: Return test plan structure
    BMAD->>GWC: Return procedure adapter contract
    GWC->>GWC: Validate contract against authority boundaries
    GWC->>GWC: Gate G1 decision (go/no-go)
    GWC->>GWC: Proceed to Gate G2 with BMAD artifacts
    
    Note over GWC,BMAD: All BMAD outputs include:
    - Provenance: SCRUM-119 + exact SHAs
    - Evidence: schemas, matrix, examples, test plan
    - Gate recs: read-only recommendations only
```

## Deliverables Produced for GWC Gate G1

All SCRUM-119 deliverables are consumed by GWC at Gate G1:

1. **contracts/permission-action-matrix.md** - Used by GWC to validate permission boundaries
2. **examples/positive-*.md** - Used by GWC to verify correct operation within boundaries  
3. **examples/rejected-scope-violation.md** - Used by GWC to verify boundary enforcement
4. **tests/validator-test-plan.md** - Used by GWC to validate implementation correctness
5. **schemas/bmad-procedure-*.json** - Used by GWC to validate data contracts

## GWC-Specific Validation Commands

To validate SCRUM-119 implementation at Gate G1, GWC would execute:

```bash
# Validate schema compatibility
dw power prompt gwc --system rental-home --task "Validate BMAD procedure schemas against authority boundaries"

# Check permission matrix compliance  
dw power prompt gwc --system rental-home --task "Verify BMAD actions stay within permission envelope"

# Confirm no authority boundary violations
dw power prompt gwc --system rental-home --task "Ensure BMAD cannot approve gates or mutate state"

# Validate provenance tracking
dw power prompt gwc --system rental-home --task "Check all outputs include exact-SHA provenance"

# Test idempotency guarantees
dw power prompt gwc --system rental-home --task "Verify duplicate requests return cached results"
```

This GWC Gate G1 integration demonstrates actual use of the GWC skill for governance and delivery control of the SCRUM-119 implementation, ensuring the BMAD procedure adapter operates within strict authority boundaries.