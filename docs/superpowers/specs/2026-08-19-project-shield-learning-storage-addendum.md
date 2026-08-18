# DW Project Shield — Learning, Telemetry, Self-Review & Cloud Ledger Addendum

Date: 2026-08-19
Status: **Approved design extension; implementation not authorized**
Parent design: `docs/superpowers/specs/2026-08-19-project-shield-design.md`
Repository: `nhatnguyenquang1838-coder/DW-SuperApps`
Design branch: `design/project-shield-20260819`

## 1. Purpose

This addendum extends the Project Shield architecture with four concerns that are intentionally separated from the protection loop itself:

1. durable audit ownership and MVP cloud synchronization;
2. vendor-neutral telemetry and execution tracing;
3. scheduled self-review and evaluation datasets;
4. bounded self-improvement, machine-learning, and optional future training.

It does not replace the parent design. Where this addendum is more specific about persistence, telemetry, or learning, it refines the parent design.

The governing separation is:

```text
Run Ledger       = canonical execution/audit truth
Telemetry        = operational observation of how execution behaved
Experience Store = curated derivative records eligible for evaluation/learning
Eval/ML system   = experiments and improvement evidence, never audit authority
```

A learning/evaluation system must never rewrite canonical audit history, create execution authority, or silently weaken protection/governance policy.

## 2. Current-state audit/logging model

At the currently reviewed TaskController base, the audit foundation already provides:

- immutable/deterministic `AuditEvent` records;
- ordered append-only SQLite event persistence by `run_id` and `sequence`;
- run manifests and run summaries;
- an `AuditFacade` where durable ledger write is authoritative;
- bounded structured-log projection that is best-effort and does not invalidate durable audit state when logging fails;
- bounded log metadata rather than conversation/prompt/full internal payload dumping.

Relevant current files include:

```text
taskcontroller/audit/event.py
taskcontroller/audit/facade.py
taskcontroller/audit/sqlite_writer.py
taskcontroller/audit/structured_log.py
taskcontroller/audit/query.py
```

Current SQLite persistence receives `db_path` from the hosting runtime. Therefore the physical file currently belongs to the host filesystem chosen by the process/container deployment. This is acceptable for local development and single-host MVP execution, but it is not the target ownership model for a multi-host Project Shield.

## 3. Persistence ownership invariant

The canonical Run Ledger belongs to **TaskController/Project Shield infrastructure**, not to an individual Agent.

Agents and Controller hosts are replaceable execution clients. Losing an Agent host must not imply losing the canonical audit history required for recovery, scheduled review, or cross-agent continuation.

Target ownership:

```text
Hermes Mac ─────┐
Hermes Cloud ───┤
ChatGPT ────────┼──► TaskController / Project Shield
Codex ──────────┘                │
                                 ▼
                         Shared durable ledger
```

Local SQLite remains a valid `RunLedger` persistence adapter, especially for local/offline execution. It is not the intended sole production durability boundary for Hybrid Project Shield.

## 4. MVP local-first cloud synchronization

For MVP, preserve the existing local SQLite write path and add reliable asynchronous synchronization to a shared PostgreSQL store.

```text
TaskController
     │
     ▼
Local SQLite Run Ledger
     │
     ├── immediate local durable write
     │
     ▼
Reliable Sync Outbox
     │
     ▼
Shared PostgreSQL Ledger
     │
     ├── cross-host recovery
     ├── scheduled self-review
     ├── Project Shield history
     └── bounded Global Shield projection
```

This design avoids replacing the proven SQLite audit path before cloud durability is demonstrated.

### 4.1 Do not use naive dual-write

Forbidden MVP pattern:

```text
AuditEvent
├── write SQLite
└── write cloud independently
```

Independent dual-write creates an ambiguous partial-success state when one write succeeds and the other fails.

Preferred pattern:

```text
one local transaction
├── append audit event
└── enqueue sync outbox row
        ↓
    sync worker
        ↓
 PostgreSQL idempotent upsert
        ↓
 exact readback / ACK
```

The local transaction is the execution-time write boundary. The cloud replica has explicit synchronization state rather than being assumed current.

### 4.2 Sync state

Conceptual record:

```yaml
audit_sync:
  event_id: EVT-...
  run_id: TC-...
  sequence: 17
  state: LOCAL_PENDING | SYNCING | CLOUD_ACKED | FAILED
  attempts: 2
  last_attempt_at: ...
  cloud_ref: ...
  last_error_class: ...
```

Retries are idempotent. Cloud uniqueness must preserve at least:

```text
UNIQUE(event_id)
UNIQUE(run_id, sequence)
```

A duplicate retry must not create duplicate audit history.

### 4.3 Cloud durability policy

Not every event waits for cloud acknowledgement.

Normal/read-only events such as progress, heartbeat, research outputs, or non-protected execution may continue after the local durable write and synchronize asynchronously.

Policies may require cloud durability before high-impact protected effects. Candidate examples:

```text
H3/H4 protected mutation
merge/deploy authority effect
protection/fencing state transition
critical authority decision
```

When cloud durability is required but unavailable:

```text
local audit         = durable
cloud durability    = UNKNOWN / DEGRADED
protected effect    = WAIT / fail closed according to policy
read-only research  = may continue
```

This is an instance of the parent design's selective fail-closed rule.

## 5. PostgreSQL provider strategy

The architecture is provider-neutral at the ledger contract.

Conceptually:

```text
RunLedgerPort
├── SQLiteRunLedger
└── PostgresRunLedger
```

`PostgresRunLedger` should use normal PostgreSQL semantics rather than embedding a provider-specific domain model.

### 5.1 MVP preferred managed backend: Supabase PostgreSQL

For the first shared-cloud MVP, Supabase PostgreSQL is the preferred managed deployment because it provides a managed PostgreSQL database with low infrastructure overhead while preserving standard PostgreSQL portability.

Supabase is a deployment/provider choice, not a Shield domain dependency.

### 5.2 Alternative/scale path: Amazon RDS for PostgreSQL

Amazon RDS for PostgreSQL is an equivalent future deployment target when DW SUPER requires stronger AWS-native networking, private VPC topology, Multi-AZ/enterprise operations, or consolidated AWS governance.

An Agent running on EC2 is not the database. EC2/agent hosts connect to RDS; the ledger remains independently managed infrastructure.

### 5.3 Portability rule

Migration between managed PostgreSQL providers must not require changing Shield/A2A/Finding semantics. Differences should remain in deployment configuration, connection/security, backup, and operational adapters.

## 6. Cloud data boundary

MVP cloud audit storage should remain small and governance-focused.

Candidate core tables/relations:

```text
shield_runs
audit_events
run_manifests
run_summaries
sync_nodes / sync_receipts
```

Learning/evaluation data is not mixed directly into canonical audit tables. Later learning tables/stores may include:

```text
experience_records
evaluation_runs
learning_candidates
dataset_membership
```

The audit database must not become an unrestricted prompt/conversation warehouse.

## 7. Telemetry definition and boundary

Telemetry is automated operational measurement of how the system executes. It complements but does not replace the Run Ledger.

The useful three-signal model is:

```text
Telemetry
├── Logs    — discrete operational records
├── Metrics — numeric aggregates over time
└── Traces  — causal/execution path across components
```

Examples:

```text
Log:    provider timeout for run TC-42
Metric: provider success rate = 92%
Trace:  research → review → finding → healing → verification
```

Run Ledger answers **what canonical execution/audit event occurred**. Telemetry answers **how execution behaved operationally**.

## 8. Vendor-neutral trace correlation

Shield/TaskController should support vendor-neutral trace/span correlation, aligned with OpenTelemetry concepts.

Existing semantic identities remain primary:

```text
run_id
node_id
execution/attempt identity
A2A sender/seq
finding_ref
healing_attempt_ref
```

Telemetry adds correlation identifiers such as:

```yaml
telemetry:
  trace_id: ...
  span_id: ...
  run_id: TC-...
  node_id: ...
  finding_ref: F-...
  healing_attempt_ref: HA-...
```

Example trace:

```text
trace SHIELD-42
├── research.repo
├── research.docs
├── review.security
├── finding.reconcile
├── healing.execute
└── verification
```

Trace IDs do not replace TaskController IDs and do not create canonical Shield identity.

Default telemetry must not contain chain-of-thought, secrets, credentials, or unrestricted raw conversation/prompt bodies.

## 9. Telemetry stack direction

Preferred architectural direction:

```text
TaskController / Shield
        │
        ▼
OpenTelemetry-compatible instrumentation
        │
        ▼
Collector / exporter boundary
        │
        ├── trace backend
        ├── metrics backend
        └── log backend
```

OpenTelemetry is an observability contract/provider-neutral instrumentation direction, not the canonical Run Ledger.

The MVP may run a local or host-level collector/exporter. A central collector/backend can be introduced when multiple Project Shields require shared observability.

## 10. ExperienceRecord

Learning needs a curated semantic record distinct from raw audit and telemetry.

```yaml
experience_record:
  id: EXP-...
  source:
    run_id: TC-...
    trace_ref: ...
    finding_ref: F-...
    healing_attempt_ref: HA-...
  context:
    project: ...
    capability: review.security
    provider: ...
    model_version: ...
    skill_version: ...
    workflow_profile_version: ...
    policy_version: ...
  outcome:
    technical_success: true
    verification_pass: true
    recurrence: false
    rollback: false
  quality:
    deterministic_scores: {}
    domain_scores: {}
    judge_scores: {}
    human_scores: {}
  efficiency:
    latency_ms: ...
    tokens: ...
    cost: ...
    retries: ...
  learning_eligibility:
    state: ELIGIBLE | QUARANTINED | REJECTED
    reasons: []
```

`ExperienceRecord` is a derivative learning artifact. It never replaces the underlying AuditEvent/evidence references.

## 11. Experience eligibility and data firewall

Production execution does not automatically become training data.

Required curation path:

```text
Audit + Trace
    ↓
Redaction / normalization
    ↓
Eligibility check
    ↓
Deduplication
    ↓
Label/evidence quality check
    ↓
Experience Store / Eval Dataset
```

Default ineligible or quarantine categories include:

```text
secrets / credentials
private conversation body not explicitly needed
chain-of-thought
untrusted external instruction payloads
unverified/low-confidence AI findings
poisoned or adversarial inputs
records without required evidence provenance
```

Training/evaluation eligibility is explicit metadata, not an implicit side effect of logging.

## 12. Evaluation datasets

Production experience should feed versioned evaluation datasets containing more than failures.

Dataset classes should include:

```text
FAILURES
EDGE_CASES
GOOD_EXEMPLARS
CRITICAL_GOLDEN_CASES
RECURRENCE_CASES
HUMAN_CORRECTION_CASES
```

A golden/regression set is frozen/versioned so candidate prompts/skills/providers/models can be compared against the same cases.

Production failures that expose a new edge case may be proposed for dataset inclusion only after evidence/eligibility review.

## 13. Evaluation hierarchy

Scheduled/online self-review should use evidence in this order where applicable:

```text
1. deterministic checks
2. code-based scorers
3. project/domain rules
4. independent LLM judge
5. human feedback / authority decision
```

Do not use an LLM judge for deterministic evidence that already has an exact answer, such as exact-SHA CI, required evidence presence, signature validity, or an authority scope match.

LLM judges are useful for bounded semantic evaluation such as research completeness, contradiction handling, or review quality when deterministic metrics are insufficient.

A single LLM judge result is not critical-effect authority.

## 14. Scheduled Self-Review capability

Scheduled self-review is separate from the existing in-session Controller monitoring loop.

The scheduler/provider emits a due signal; Shield Trigger Engine starts a normal bounded TaskController review run.

```text
Scheduler / timing source
          ↓
     SELF_REVIEW_DUE
          ↓
   Shield Trigger Engine
          ↓
    TaskController Run
          ↓
  Self-Review Workflow
```

TaskController's active in-session polling semantics are not converted into a detached cron runtime.

### 14.1 Review classes

**POST_RUN**

Runs at/after a material terminal boundary and extracts outcome/quality/learning candidates. Straightforward successful runs may use deterministic scoring only.

**MICRO_REVIEW**

Reviews a short recent window for:

```text
failures
novel fingerprints
provider degradation
cost/latency outliers
repeated human correction
repeated scope/authority drift
```

**PROJECT_REVIEW**

Reviews a broader project window for:

```text
finding quality
healing effectiveness
recurrence
false positives
provider/capability performance
sensor coverage
human intervention
protection effectiveness
```

**GLOBAL_LEARNING_REVIEW**

Reviews normalized cross-project experience for systemic patterns, provider/capability effectiveness, shared skill/workflow weaknesses, and training/improvement candidates.

Cadences are project/global profile configuration, not hard-coded TaskController kernel constants.

## 15. Self-review output

A review produces evidence-backed artifacts rather than silently changing production behavior.

Conceptual output:

```yaml
self_review:
  id: SR-...
  scope: PROJECT | GLOBAL
  window: ...
  dataset_refs: []
  metrics: {}
  findings: []
  learning_candidate_refs: []
  policy_proposal_refs: []
  next_review_condition: ...
```

Evaluation dimensions include:

```text
QUALITY
CORRECTNESS
SAFETY
GOVERNANCE
EFFICIENCY
LEARNING
```

Useful measures include Task/Review success, finding precision/recall where labels exist, human correction rate, provider failures, verified healing success, rollback, recurrence, cost, latency, and prevention effectiveness.

## 16. LearningCandidate

Self-improvement is proposed through a versioned candidate object.

```yaml
learning_candidate:
  id: LC-...
  source_experience_refs: []
  target:
    type: PROMPT | SKILL | WORKFLOW | ROUTING | POLICY_PROPOSAL | MODEL_TRAINING
    target_ref: ...
  hypothesis: ...
  proposed_change: ...
  expected_improvement:
    metric: ...
  risk: LOW | MEDIUM | HIGH | CRITICAL
  evaluation_dataset_ref: ...
  state: PROPOSED | EXPERIMENTING | VALIDATED | REJECTED | READY_FOR_PROMOTION
```

A candidate is not production state until a promotion decision occurs under applicable governance.

## 17. Bounded self-improvement ladder

Project Shield should improve in increasing order of cost/risk.

### L0 — Reflective/Episodic Learning

Record evidence-backed lessons and previous outcomes for use as bounded future context. No model-weight change.

### L1 — Prompt / Skill / Workflow Optimization

Create a new versioned candidate prompt/skill/workflow, evaluate against frozen datasets, compare to the current champion, and promote only after regression checks and authority.

This is the preferred first active optimization layer because it is inspectable, versionable, testable, and rollback-friendly.

### L2 — Adaptive Routing / Machine Learning

When enough ExperienceRecords exist, learn or optimize provider/model/review/healing selection from task context and historical performance.

Possible decision inputs:

```text
capability
task/risk class
project
provider health
historical verified quality
latency
cost
human correction
recurrence
```

The learned router optimizes within deterministic policy constraints. It cannot override trust, authority, or protection requirements.

### L3 — Offline Fine-Tuning / RL

Optional future layer only after sufficiently large, high-quality, repeatable datasets exist and prompt/skill/routing optimization is insufficient.

Training is offline from production execution:

```text
Production runtime
       ↓
eligible traces/experiences
       ↓
curated training dataset
       ↓
offline experiment/training
       ↓
candidate model
       ↓
evaluation + regression
       ↓
promotion decision
```

A running production Agent must not modify its own model weights and continue as though the new model were automatically trusted.

## 18. No uncontrolled online self-training

Forbidden default pattern:

```text
AI finding
   ↓ self-label
online train
   ↓
stronger same bias
```

Production self-labels are evidence inputs, not automatically trusted training labels.

Low-confidence/conflicting findings and unverified healing results are quarantined until resolved.

## 19. Champion / Challenger promotion

Every learned behavior change must be testable as a versioned candidate.

```text
Current Champion
       │
       ├────────────┐
       │            │
       ▼            ▼
Frozen Eval Set   Challenger
       │            │
       └──── compare┘
             ↓
    regression / risk checks
             ↓
      Promotion Proposal
             ↓
     applicable authority
             ↓
        new Champion
```

Comparison can include:

```text
correctness / task success
finding precision/recall
false positives
governance/safety violations
human correction
verified recurrence
latency
cost
```

Promotion and rollback references must remain auditable.

## 20. EvalOps provider strategy

The learning/evaluation layer is capability-based rather than hard-wired to one product.

Conceptually:

```text
capability: learning.eval
providers:
  - mlflow
  - alternative compatible provider
```

For MVP, MLflow GenAI is the preferred evaluation/experiment direction because the desired capabilities include traces, datasets, scorers, repeated evaluation, experiment comparison, and versioned improvement evidence.

Langfuse remains a viable alternative for LLM/agent observability and evaluation UX if later operational needs favor it.

Do not deploy both solely for feature overlap in the MVP.

Neither MLflow nor Langfuse becomes Run Ledger authority.

## 21. Learning Plane architecture

```text
                    PROJECT SHIELD
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
      Protection Loop              Learning Loop
            │                           │
            ▼                           ▼
       TaskController                Telemetry
            │                           │
            ▼                           ▼
        Run Ledger ─────────────► Experience Store
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
                  Online Evaluation            Scheduled Review
                         │                             │
                         └──────────────┬──────────────┘
                                        ▼
                                  Eval Datasets
                                        │
                                        ▼
                              Improvement Engine
                         ┌──────┬───────┬───────┐
                         ▼      ▼       ▼       ▼
                      Prompt  Skill   Routing  Model
                         └──────┴───┬───┴───────┘
                                    ▼
                                Experiment
                                    ▼
                           Champion / Challenger
                                    ▼
                           Promotion Decision
```

## 22. MVP extension slices

The parent design's MVP is extended with two slices.

### Slice F — Durable shared audit

- preserve `SQLiteRunLedger` for local-first writes;
- add local outbox/sync state;
- implement idempotent PostgreSQL replication semantics;
- first managed deployment target may be Supabase PostgreSQL;
- keep `PostgresRunLedger` provider-neutral so RDS PostgreSQL remains compatible;
- cloud durability status becomes observable Shield health/evidence;
- selected protected effects may require cloud ACK by policy.

### Slice G — Telemetry and Learning foundation

- vendor-neutral trace/span correlation;
- bounded telemetry tags tied to TaskController/Shield IDs;
- ExperienceRecord derivation and eligibility firewall;
- POST_RUN + scheduled self-review workflow contracts;
- versioned evaluation/golden datasets;
- deterministic/domain/LLM/human evaluation hierarchy;
- LearningCandidate + champion/challenger experiment contract;
- prompt/skill/workflow improvement proposals first;
- no online self-training and no model-weight training in the first MVP.

## 23. Failure behavior

### Local SQLite unavailable

If the canonical execution-time local durable write cannot be made, audit-required execution fails closed according to existing TaskController/project policy.

### Cloud PostgreSQL unavailable

- local writes continue when the action requires only local durability;
- sync state becomes pending/failed and is retried idempotently;
- Shield observability/durability state is degraded/unknown as appropriate;
- protected effects that explicitly require cloud durability wait/fail closed;
- read-only investigation may continue when policy permits.

### Sync worker crash

Unsynced outbox records remain discoverable after restart and are retried. Worker memory is never the only record of pending replication.

### Telemetry backend unavailable

Telemetry loss does not delete or invalidate Run Ledger history. Critical observability requirements may degrade Shield health, but audit truth remains in the ledger.

### Eval/ML backend unavailable

Protection/execution remains independent. Scheduled learning/evaluation is delayed/degraded; it cannot block ordinary protection unless a specific promotion/decision requires that evidence.

## 24. Security and privacy boundaries

1. Canonical audit records remain bounded and evidence-reference oriented.
2. No default raw chain-of-thought persistence.
3. No secret/credential ingestion into learning datasets.
4. Cloud replication must authenticate each Project Shield/host with least privilege.
5. An Agent should not receive broad direct database privileges merely because it executes a task.
6. Global Shield should receive normalized/bounded data and exact refs, not wholesale local audit/telemetry dumps by default.
7. Training/evaluation datasets have explicit eligibility/redaction/versioning.
8. Learning systems cannot modify authority/protection policy directly.
9. Cloud ACK/readback is exact evidence when required; a successful network request alone is not sufficient if exact persistence cannot be verified.

## 25. Approved architecture decisions

### ADR-SHIELD-031 — Run Ledger remains canonical audit
Observability, learning, evaluation, and ML systems consume projections/refs; they do not redefine audit truth.

### ADR-SHIELD-032 — Vendor-neutral trace correlation
TaskController/Shield execution supports trace/span correlation without replacing canonical run/node/attempt/finding identities or requiring conversation replay.

### ADR-SHIELD-033 — ExperienceRecord is distinct from AuditEvent
Only redacted, eligible, evidence-backed derivative experiences enter evaluation/learning datasets.

### ADR-SHIELD-034 — Scheduled Self-Review is a Shield capability
It is separate from in-session Controller monitoring and starts normal bounded TaskController review runs from schedule/due triggers.

### ADR-SHIELD-035 — Evidence-first evaluation hierarchy
Deterministic checks and domain rules precede independent LLM judging and human feedback where applicable.

### ADR-SHIELD-036 — Production experience enriches versioned evaluation datasets
Failures, edge cases, good exemplars, recurrence, human corrections, and critical golden cases become curated dataset candidates.

### ADR-SHIELD-037 — Self-improvement follows an increasing-risk ladder
Prefer reflection, then prompt/skill/workflow optimization, then adaptive routing/ML, and only later optional offline weight training.

### ADR-SHIELD-038 — No uncontrolled online self-training
Production Agents may not self-label, update model weights, and continue as automatically trusted production models.

### ADR-SHIELD-039 — Champion/Challenger promotion is mandatory for learned behavior change
Candidate versions require frozen-dataset evaluation, regression/risk checks, versioned promotion evidence, and rollback capability.

### ADR-SHIELD-040 — Learning cannot self-authorize policy weakening
Learning may generate `PolicyProposal`; it cannot directly weaken or rewrite authority/protection policy.

### ADR-SHIELD-041 — Run Ledger infrastructure is independent of Agent lifetime
The durable audit owner is TaskController/Project Shield infrastructure; local host SQLite is an adapter/deployment choice, not Agent-owned canonical identity.

### ADR-SHIELD-042 — MVP cloud durability uses local-first outbox replication
SQLite event append and sync-outbox enqueue form the local write boundary; cloud PostgreSQL synchronization is idempotent and explicit.

### ADR-SHIELD-043 — Shared cloud ledger uses provider-neutral PostgreSQL semantics
Supabase PostgreSQL is the preferred MVP managed target; Amazon RDS for PostgreSQL is a compatible future deployment target without changing Shield domain semantics.

### ADR-SHIELD-044 — Cloud durability may be an effect-specific guard
Normal events may synchronize asynchronously; explicitly protected/high-impact effects may require exact cloud ACK/readback according to policy.

## 26. Design handoff boundary

This addendum is architecture/design only.

It does **not** authorize implementation, database creation/migration, Supabase/RDS provisioning, secrets/network changes, model training, merge, deployment, destructive operations, or production authority.

The parent design plus this addendum form the current Project Shield written architecture for review. A separate implementation plan is still required before governed implementation begins.
