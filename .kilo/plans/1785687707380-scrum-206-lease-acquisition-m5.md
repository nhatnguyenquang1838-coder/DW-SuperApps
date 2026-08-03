# SCRUM-206 — runtime_checkpoint.lease-acquisition M2 → M5_REPLAY_SAFE

SOURCE INSTRUCTION: REPO
EXECUTION MODE: local_agent

## 1. Active lane / task

- Jira task: `SCRUM-206`
- Summary: `[MAT-F4-N05] runtime_checkpoint.lease-acquisition — M2 → M5`
- Active lane: G0/G1 preparation (run_id `g1-206-20260802-2328`)
- Repository: `nhatnguyenquang1838-coder/gwc`
- Base branch: `main`
- Base SHA: `d4e507aec14db4f62fd4f21f8f84436df08e6216`
- Working branch: `g1-206-20260802-2328`
- Risk class: R2

## 2. SCRUM-206 claim readback

| Field | Value |
|---|---|
| AI Agent | Kilo |
| Claimed At | 2026-08-02T23:28:00.000+0700 |
| Status | In Progress |

Claim readback: PASS. No `AGENT_TASK_CLAIM_BLOCKED` or `AI_AGENT_CLAIM_CONFLICT`.

## 3. Files READ

- `AGENTS.md`
- `core/Coding_Project_Governance_v1.0.md`
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
- `core/Agent_Operating_Runtime_Contract_v1.0.md`
- `core/task-lifecycle/gate-transition-map.yaml`
- `core/node-architect/node-registry.json`
- `core/node-architect/node-catalog/runtime_checkpoint/lease-acquisition.node.json`
- `core/node-architect/node-catalog/runtime_checkpoint/README.md`
- `core/node-architect/decision-rule-registry.json`
- `projects/gwc/project-profile.yaml`
- `projects/gwc/project-instructions.md`
- `projects/gwc/project-extension.md`
- `agents/chatgpt-agent/agent-instructions.md`
- `agents/dwc/agent-instructions.md`
- `tools/node_architect/checkpoint_capture.py`
- `tools/node_architect/checkpoint_store.py`
- `tools/node_architect/lease_expiry_recovery.py`
- `tests/test_checkpoint_capture.py`
- `tests/test_lease_expiry_recovery.py`
- `.gwc/tasks/SCRUM-202/g2/execution-envelope.yaml`
- `.gwc/tasks/SCRUM-202/g1/intake/g1-intake-brief.yaml`
- `.gwc/tasks/SCRUM-202/g1/decision/g1-decision-record.yaml`
- `.gwc/tasks/SCRUM-202/g1/preflight/g1-preflight-report.yaml`
- `schemas/runtime-checkpoint.schema.json`
- `schemas/duplicate-agent-fencing-decision.schema.json`
- `schemas/lease-expiry-recovery-decision.schema.json`

## 4. Files WRITE

- `tools/node_architect/lease_acquisition.py`
- `tests/test_lease_acquisition.py`
- `schemas/lease-acquisition-decision.schema.json`
- `.gwc/tasks/SCRUM-206/g0/context-snapshot.yaml`
- `.gwc/tasks/SCRUM-206/g1/intake/g1-intake-brief.yaml`
- `.gwc/tasks/SCRUM-206/g1/preflight/g1-preflight-report.yaml`
- `.gwc/tasks/SCRUM-206/g1/brainstorming/g1-options.yaml`
- `.gwc/tasks/SCRUM-206/g1/decision/g1-decision-record.yaml`
- `.gwc/tasks/SCRUM-206/g2/execution-envelope.yaml`
- `releases/changelog.d/2026-08-02-scrum-206-lease-acquisition-m5.md`

## 5. Architecture gap

Current state: `runtime_checkpoint.lease-acquisition` exists only as a node descriptor (`lease-acquisition.node.json`) and a registry slot in `node-registry.json`. There is no implementation, no decision schema, no unit tests, and no gate artifacts for SCRUM-206.

Gap summary:
- No deterministic lease-acquisition decision utility.
- No JSON Schema for lease-acquisition decisions.
- No unit tests covering competing-agent acquisition, stale owner, expired lease, scope mismatch, crash during acquisition, or fencing monotonicity.
- No G0/G1/G2 artifacts scoped to this task.

## 6. Implementation plan

### 6.1 Schema

Add `schemas/lease-acquisition-decision.schema.json`:
- Required fields: `schema_version`, `artifact_type`, `task_id`, `run_id`, `node_id`, `repository`, `branch`, `base_sha`, `head_sha`, `scope_hash`, `lease_id`, `fencing_token`, `actor_id`, `observed_lease_holder`, `observed_fencing_token`, `observed_at`, `outcome`, `reason_code`, `advancement_allowed`, `side_effect_allowed`, `reacquire_required`, `decision_digest`.
- Enums: `outcome` includes `ACQUIRED`, `FENCE_STALE_WORKER`, `FENCE_DUPLICATE_AGENT`, `RECONCILE`, `REACQUIRE_REQUIRED`, `SCOPE_MISMATCH`.
- `fencing_enforced: true` constant.

### 6.2 Implementation

Add `tools/node_architect/lease_acquisition.py`:
- `decide_lease_acquisition(...)` deterministic function.
- Bindings: `task_id`, `run_id`, `node_id`, `gate` (must be known G2 gate), `base_sha`, `head_sha`, `scope_hash`, `repository`, `branch`, `lease_id`, `actor_id`, `observed_lease_holder`, `observed_fencing_token`.
- Fail-closed on missing/ambiguous binding or unknown gate.
- Outcomes:
  - `ACQUIRED` when no competing active lease and binding is valid; emit monotonic fencing token.
  - `FENCE_STALE_WORKER` when `actor_fencing_token < observed_fencing_token`.
  - `FENCE_DUPLICATE_AGENT` when another agent holds the active lease for the same task/scope.
  - `RECONCILE` when observed lease is expired and side effects are `COMMITTED`/`UNKNOWN`/`PENDING`.
  - `REACQUIRE_REQUIRED` when observed lease is expired but readback is not `VERIFIED_ZERO_EFFECT`.
  - `SCOPE_MISMATCH` when `scope_hash` or `repository` does not match observed lease.
- `is_replay_equivalent(first, second)` ignoring `observed_at`.
- `main(argv)` CLI entry for evidence routing.

### 6.3 Tests

Add `tests/test_lease_acquisition.py`:
- Deterministic same-input same-digest.
- Competing-agent acquisition rejection.
- Stale owner fenced by monotonic token.
- Expired lease requires reconciliation/reacquire.
- Scope mismatch rejection.
- Crash-before-persist purity (pure function, no I/O).
- Fencing monotonicity (new token > observed token).
- Replay equivalence ignores observation time.

### 6.4 Gate artifacts

Materialize under `.gwc/tasks/SCRUM-206/`:
- `g0/context-snapshot.yaml`
- `g1/intake/g1-intake-brief.yaml`
- `g1/preflight/g1-preflight-report.yaml`
- `g1/brainstorming/g1-options.yaml`
- `g1/decision/g1-decision-record.yaml`
- `g2/execution-envelope.yaml`

### 6.5 Changelog

Add `releases/changelog.d/2026-08-02-scrum-206-lease-acquisition-m5.md`:
- Document added module, schema, tests, and gate artifacts.
- Restate guardrails: no merge, deploy, production data, runtime engine, or scheduler authority.

### 6.6 Validation

- Run `python -m unittest tests.test_lease_acquisition -v`.
- Run `python tools/validate_g01.py --workspace .gwc/tasks/SCRUM-206`.
- Verify schema validity and no scope drift.

## 7. Exact G2 approval command

```
APPROVE G2_EXECUTION CP-20260802-206-G2-R1 fe88b9bcc740b9bb 2026-08-03T23:28:00Z
```

| Field | Value |
|---|---|
| Repository | nhatnguyenquang1838-coder/gwc |
| Base branch | main |
| Base SHA | d4e507aec14db4f62fd4f21f8f84436df08e6216 |
| Working branch | g1-206-20260802-2328 |
| Scope hash | sha256:fe88b9bcc740b9bb629b14e4282be9b30b981b841f0becf1ce90c7ae7aeb5964 |
| Files READ | (see Section 3) |
| Files WRITE | (see Section 4) |
| Authorized actions | materialize_task_scoped_G0_G1_G2, write_only_approved_modules, run_scoped_validators_and_tests, commit_and_push_guarded_branch, open_or_update_draft_pr |
| Excluded actions | write_to_main, merge_or_auto_merge, deploy_release_publish_or_runtime_reload, production_configuration_data_secret_credential_or_migration, force_push_branch_delete_history_rewrite_or_pr_base_change, scope_expansion_or_unrelated_cleanup |
| Expiry | 2026-08-03T23:28:00Z (24h) |
