# SCRUM-108 — Runtime Store and Runtime Nodes Implementation Plan

## Context

- **Jira**: `https://nhatnguyenquang1838.atlassian.net/browse/SCRUM-108`
- **Blocked by**: SCRUM-106 (crash/recovery scenario matrix, Draft PR #111)
- **Upstream design**: SCRUM-105 merged — durable runtime store schemas, CAS/lease/fencing semantics, adapter contracts, migration path
- **Repository**: `nhatnguyenquang1838-coder/gwc` (consumed as submodule at `projects/gwc`)
- **Protected base**: current `main`
- **Execution mode**: `local_agent` (trusted checkout + isolated worktree + validators available)

> **Note**: Jira MCP auth was not available in this planning session. The issue was confirmed to exist but returned `404` via anonymous API. Proceed with the repo-local evidence below; confirm exact acceptance criteria against the Jira ticket before G2.

## Assumed Scope (to be confirmed against Jira)

Based on `SCRUM-105` design (`projects/gwc/.gwc/scrums/SCRUM-105/design.md`) and `SCRUM-106` matrix (`projects/gwc/.gwc/tasks/SCRUM-106/g1/decision/P2_SCENARIO_MATRIX.md`), SCRUM-108 is expected to cover:

1. **Runtime store engine** (SQLite pilot, PostgreSQL/Supabase adapter-ready)
   - Event append/read with sequence ordering
   - Checkpoint read/write with CAS revision
   - Store `put/load/delete` with CAS tokens
   - Lease acquire/renew/release with TTL and fencing tokens
   - Pending-action submit + readback state machine
2. **Pilot runtime nodes** (3 node classes from SCRUM-106)
   - `read-only-exact-state`
   - `bounded-external-write` (with idempotency key + deterministic readback)
   - `durable-checkpoint-cas-lease-resume`
3. **Adapter contract handshake** and operation routing
4. **Validators and tests** bound to the 27-scenario matrix
5. **Package export** updates for new runtime artifacts

**Out of scope (confirm against Jira)**: production migration execution, database provisioning, UI, GWC workflow changes, Power distribution changes.

## Worktree and Branch

- **Worktree path**: `/Users/mac/prj/DW-SuperApps/.kilo/worktrees/scrum-108-20260727`
- **Branch**: `knowledge/scrum-108-p2-runtime-store-nodes-20260727`
- **Base**: current `main` HEAD (rebase if base drifts before G2)

## Gate Sequence

### G0_CONTEXT — READY

Create `.gwc/tasks/SCRUM-108/g0/context-snapshot.yaml` with:
- Active project profile: `gwc`
- Repository: `nhatnguyenquang1838-coder/gwc`
- Base SHA: exact `main` HEAD at G0 time
- Connector identity and execution mode
- Task identity: `SCRUM-108`
- Blockers: `SCRUM-106` not yet merged (expected blocker until PR #111 merges)

### G1_ALIGNMENT — PASS

Create task-scoped G1 artifacts under `.gwc/tasks/SCRUM-108/g1/`:
- `intake/g1-intake-brief.yaml` — problem, desired outcome, scope, constraints, stakeholders, acceptance criteria
- `preflight/g1-preflight-report.yaml` — base drift, missing sources, risk signals
- `brainstorming/g1-options.yaml` — bounded implementation options
- `decision/g1-decision-record.yaml` — selected option and rationale

Run validator:
```bash
python tools/validate_g01.py --workspace .gwc/tasks/SCRUM-108
```

Expected: `PASS`, exit 0, zero issues.

### G2_EXECUTION — ENTERED

Generate `.gwc/tasks/SCRUM-108/g2/execution-envelope.yaml` with:
- Exact repository, base SHA, working branch, scope hash
- File/module scope (runtime store module, node runtime module, adapters, validators, tests, schemas, package export)
- Authorized actions: create branch, create worktree, write scoped files, run validators/tests, create Draft PR
- Excluded actions: protected-main write, merge, deploy, release, production data/migration

### Implementation (scoped to G2 envelope)

**Module layout (proposed)**:
```
projects/gwc/
  runtime/
    __init__.py
    store/
      __init__.py
      sqlite_adapter.py
      postgres_adapter.py   # stub or minimal, bound to migration schema
      lease.py
      pending_action.py
      cas.py
      checkpoint.py
    nodes/
      __init__.py
      base_node.py
      read_only_context.py
      bounded_external_write.py
      durable_checkpoint_cas_lease_resume.py
      adapter_handshake.py
    engine/
      __init__.py
      runtime_engine.py
      event_emitter.py
  tests/
    test_runtime_store.py
    test_runtime_nodes.py
    test_adapter_contract.py
    test_checkpoint_engine.py
```

**Key invariants to encode**:
- CAS expected revision mandatory for every checkpoint advance
- Only active lease holder with current fencing token may advance state
- Unknown external outcomes reconciled before retry
- Checkpoint persisted before suspend/human decision
- No blind retry; readback before PASS
- Idempotency keys for bounded external writes

**Validator additions**:
- `tools/node_architect/validate_runtime_store_contract.py`
- `tools/node_architect/validate_pilot_nodes.py`

### G3_PR

- Create Draft PR from `knowledge/scrum-108-p2-runtime-store-nodes-20260727` targeting `main`
- Deliver `.gwc/tasks/SCRUM-108/g3/delivery-record.yaml`
- Required CI: Validate instructions + Build instruction packages on exact head
- Read-only review pass before marking ready for review

### G4_MERGE

- Separate exact-head approval command required
- Do not merge, auto-merge, or deploy without it

## Validation Checklist

- [ ] `python tools/validate_g01.py --workspace .gwc/tasks/SCRUM-108` → PASS
- [ ] `python tools/validate_instructions.py` → PASS
- [ ] `python -m unittest discover -s tests -p 'test_*.py'` → PASS (existing + new runtime tests)
- [ ] `python tools/build_project_package.py gwc --output dist` → PASS
- [ ] Full PR diff review — zero base drift, scope confined to task-owned paths
- [ ] Read-only review pass recorded in G3 delivery record

## Risks

| ID | Description | Mitigation |
|---|---|---|
| RISK-1 | SCRUM-106 not merged when SCRUM-108 starts | Gate G2 start on SCRUM-106 merge; rebase if base drifts |
| RISK-2 | PostgreSQL adapter scope creep | Keep PostgreSQL as adapter stub/migration-schema conformance only; live migration is out of scope |
| RISK-3 | Node catalog scale-out confusion | Implement exactly 3 pilot nodes; 81-node expansion deferred to later batch per `CONTROLLED_81_NODE_CATALOG_EXPANSION_PLAN_v0.1.md` |
| RISK-4 | CAS/lease/fencing subtle concurrency bugs | Bind every write path to explicit fencing token + lease owner checks; add property-based or matrix tests |

## Open Questions

1. **Exact SCRUM-108 acceptance criteria** — confirm against Jira ticket before G2 (Jira MCP auth required).
2. **PostgreSQL adapter depth** — is a live PostgreSQL connection pool expected, or schema-only conformance?
3. **Node class granularity** — does SCRUM-108 require all 3 pilot node classes, or a subset?

## Next Step

Switch to an implementation-capable agent with Jira MCP auth loaded. The agent should:
1. Fetch `SCRUM-108` Jira issue to confirm exact scope and AC
2. Create the worktree at `.kilo/worktrees/scrum-108-20260727`
3. Create branch `knowledge/scrum-108-p2-runtime-store-nodes-20260727`
4. Materialize G0/G1 artifacts and run `validate_g01.py`
5. Enter G2 and implement scoped runtime store + pilot nodes
