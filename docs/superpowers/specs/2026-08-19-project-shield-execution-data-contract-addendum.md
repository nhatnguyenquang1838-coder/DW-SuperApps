# DW Project Shield — Execution, Scheduling & Canonical Data Contract Addendum

Date: 2026-08-19
Status: **Design refinement responding to PR #69 architecture review; implementation not authorized**
Parent design: `docs/superpowers/specs/2026-08-19-project-shield-design.md`
Learning/storage addendum: `docs/superpowers/specs/2026-08-19-project-shield-learning-storage-addendum.md`
Repository: `nhatnguyenquang1838-coder/DW-SuperApps`
Design branch: `design/project-shield-20260819`

## 1. Purpose and precedence

This addendum closes the two must-fix design-completeness gaps identified in the PR #69 architecture review:

1. execution/scheduling ownership and continuation semantics;
2. canonical object identity, required fields, version/digest rules, and exact acknowledgement/readback contracts.

It also resolves the review's authority-binding, sync-consistency, ADR-rationale, and terminology concerns and incorporates distributed-effect hardening discovered during adversarial review.

This document is normative for the concerns it covers. If wording in the parent design or learning/storage addendum conflicts with this addendum on execution ownership, persistence assurance, object identity, sync reconciliation, authority binding, or terminology, this addendum takes precedence.

No new ADR numbers are introduced. The intent is to harden and clarify ADR-SHIELD-001 through ADR-SHIELD-044 rather than inflate the decision count.

## 2. Runtime ownership model

### 2.1 Project Shield is a logical supervisor, not one immortal TaskController run

A Project Shield is a durable logical protection instance for a project. It may have long-lived sensor/scheduler/receiver processes, but **continuous Shield operation is not represented by one forever-running TaskController Run**.

The separation is:

```text
Project Shield durable state
        │
        ├── sensors / event receivers
        ├── schedule due signals
        ├── trigger evaluation
        ├── finding/protection/health state
        │
        └── material work
              ↓
        bounded TaskController Run
              ↓
        continuation checkpoints while active
              ↓
        terminal result + durable artifacts
```

A TaskController Run is created only when a material workflow requires orchestration, such as research, independent review, diagnosis/planning, healing, verification, systemic investigation, or fencing coordination.

A quiet Project Shield with no material trigger therefore needs no active TaskController Run.

### 2.2 Global Shield Supervisor uses the same model

Global Shield is also a durable logical supervisor, not a super-TaskController and not one immortal run.

Global components may continuously receive normalized heartbeats/findings. Material cross-project work creates bounded TaskController runs:

```text
normalized project signals
        ↓
Global correlation
        ↓
material systemic candidate?
   │ no               │ yes
   ▼                  ▼
record only      TaskController Run
                       ↓
               systemic investigation
                       ↓
              systemic finding/protection
```

### 2.3 Trigger sources

A material Shield run may be triggered by:

```text
EVENT       source/webhook/provider event
POLL        periodic sensor reconciliation
SCHEDULE    self-review due signal
RECOVERY    explicit recovery of a non-terminal durable continuation
HUMAN       explicit review/research/remediation request
GLOBAL      Global→Project systemic/fencing request
```

A schedule is only a trigger source. It does not become the execution engine and does not replace active in-session Controller wait/recheck behavior inside a live governed run.

### 2.4 Run lifetime

Each TaskController Run has a finite semantic objective and terminal boundary. A run may persist across host/model invocations using the existing continuation contract, but the durable continuation is active only while the bounded workflow is non-terminal.

Required lifecycle:

```text
trigger
  ↓
create/bind run
  ↓
persist continuation before dispatch
  ↓
write/readback canonical mailbox/reference
  ↓
wake provider if required
  ↓
active in-session poll/review while host remains alive
  ↓
checkpoint/recovery if host changes
  ↓
terminal workflow result
  ↓
close continuation
```

A fresh scheduled tick never "continues" a terminal run. It creates a new run referencing prior findings/artifacts when additional work is required.

## 3. End-to-end local protect-and-heal sequence

```text
Sensor / Event Source
        │
        │ 1. immutable signal
        ▼
Observation Store
        │
        │ 2. Observation@id
        ▼
Trigger Engine
        │
        ├── NO_ACTION / RECORD_ONLY ───────────────► stop
        │
        │ 3. material investigation/action
        ▼
TaskController Run created
        │
        │ 4. persist continuation checkpoint
        ▼
Research / Review nodes
        │
        │ 5. frozen evidence + review artifacts
        ▼
Finding Engine
        │
        ├── candidate rejected/duplicate ──────────► terminal run result
        │
        │ 6. canonical Finding@version
        ▼
Diagnosis + FixPlan
        │
        │ 7. exact Finding version + FixPlan digest
        ▼
Authority / Effect Gate
        │
        ├── authority missing/drift ───────────────► WAIT / ESCALATE
        │
        │ 8. mutation-bearing action only:
        │    acquire current writer epoch/fencing token
        │    persist exact effect intent when shared durability required
        ▼
Executor / HealingAttempt
        │
        │ 9. effect + exact receipt/evidence
        ▼
Verification
        │
        ├── FAIL ─────────► replan/revert within finite budget
        │
        │ 10. technical + behavioral pass
        ▼
Finding = HEALED / MONITORING
        │
        │ 11. event/time observation window
        ▼
V3 Operational verification
        │
        ├── recurrence ───► new bounded diagnosis run
        │
        └── stable ───────► Finding CLOSED
```

### 3.1 TaskController continuation binding

Before every Executor dispatch/wakeup in steps 4, 5, 8, or 9, the Controller follows the active TaskController A2A contract:

```text
persist continuation
→ write Controller mailbox/reference with same checkpoint
→ exact readback
→ provider wake-up if needed
→ poll exact Executor mailbox/reference
```

Shield adds Finding/FixPlan/Protection/effect references to bounded state; it does not create a second continuation mechanism.

### 3.2 No implicit mutation from research

Research, review, diagnosis, and planning runs do not gain mutation authority merely because the Trigger Engine classified a Finding as HIGH/CRITICAL. Mutation requires the separate authority/effect gate described below.

## 4. End-to-end Global systemic-to-fence sequence

```text
Project Shield A ──heartbeat/finding──┐
Project Shield B ──heartbeat/finding──┼──► Global Correlation
Project Shield C ──heartbeat/finding──┘          │
                                                 │ 1. correlation candidate
                                                 ▼
                                      Global TaskController Run
                                                 │
                                                 │ 2. cross-project evidence
                                                 ▼
                                      Systemic Finding validation
                                                 │
                                      ┌──────────┴──────────┐
                                      │ insufficient         │ confirmed
                                      ▼                      ▼
                              research / terminal     Global policy eval
                                                            │
                                                            │ 3. directive
                                                            ▼
                                            ProtectionDirective@digest
                                                            │
                         ┌──────────────────────────────────┼─────────────────────────────────┐
                         ▼                                  ▼                                 ▼
                 Project Shield A                    Project Shield B                 Project Shield C
                         │                                  │                                 │
                         │ 4. authenticate + verify         │                                 │
                         │    audience/policy/digest        │                                 │
                         ▼                                  ▼                                 ▼
                 local policy evaluator              local policy evaluator            local policy evaluator
                         │                                  │                                 │
                         │ 5. local materialization         │                                 │
                         ▼                                  ▼                                 ▼
                  ProtectionReceipt                  ProtectionReceipt                 ProtectionReceipt
                         │                                  │                                 │
                         └────────────── exact refs/readback/assurance ──────────────────────┘
                                                            │
                                                            ▼
                                               Global coverage evaluation
                                                            │
                                             ┌──────────────┴──────────────┐
                                             ▼                             ▼
                                         EFFECTIVE                  PARTIAL / UNKNOWN
```

Global Shield never performs local code remediation in this sequence. A systemic remediation request starts a separate bounded Project Shield run under local authority.

## 5. Mutation writer fencing and recovery

### 5.1 Why sequencing alone is insufficient

The local SQLite ledger orders events on one host, but a host failover can otherwise create two writers that independently believe they own the next local sequence. Cloud uniqueness may detect divergence too late, after an external effect has occurred.

Therefore a mutation-bearing run requires a **single current writer epoch** before it can perform a protected mutation.

### 5.2 Run writer lease

Conceptual contract:

```yaml
run_writer_lease:
  run_id: required
  epoch: required integer >= 1
  writer_id: required stable runtime identity
  fencing_token: required opaque exact token/digest
  issued_at: required
  expires_at: required
  state: ACTIVE | EXPIRED | REVOKED
  shared_durability_ref: required for mutation-bearing runs
```

Rules:

1. an epoch monotonically increases when ownership transfers;
2. only the current active epoch may emit mutation intents/effects;
3. a stale writer that wakes after a newer epoch exists must fail closed for mutation;
4. read-only local observation/research may continue without acquiring mutation ownership when policy permits;
5. writer lease acquisition/transfer is shared-durable before mutation.

This extends the existing TaskController continuation notion of `run/epoch`; it does not introduce a general distributed-consensus platform.

### 5.3 Effect intent and receipt

Protected external mutations use:

```text
EffectIntent → Effect → EffectReceipt
```

Conceptual intent:

```yaml
effect_intent:
  id: required
  run_id: required
  writer_epoch: required
  fencing_token_ref: required
  capability: required
  target_ref: required
  idempotency_key: required
  authority_ref: required where policy requires authority
  precondition_refs: required list (may be empty only for explicitly safe effects)
  intent_digest: required sha256
  durability: LOCAL_DURABLE | SHARED_DURABLE
```

Conceptual receipt:

```yaml
effect_receipt:
  id: required
  intent_ref: required
  intent_digest: required
  provider_effect_ref: required when provider returns one
  outcome: APPLIED | NOOP_IDEMPOTENT | FAILED | UNKNOWN
  observed_at: required
  evidence_refs: required list
```

Recovery rule:

```text
intent exists + receipt absent
        ↓
RECONCILE provider state
        ↓
never blindly repeat the effect
```

## 6. Persistence assurance and sync reconciliation

### 6.1 Two durability assurance levels

```text
LOCAL_DURABLE
    event/intention is durably persisted on the current host ledger

SHARED_DURABLE
    exact event/intention has been persisted and read back from the shared PostgreSQL ledger
```

Local durability is enough for read-only/diagnostic work unless project policy says otherwise.

Shared durability is required by default for:

```text
cross-host mutation ownership transfer
H2/H3/H4 mutation that cannot be proven idempotent locally
Global protection state transition
critical authority consumption
protected EffectIntent
```

A project may tighten these requirements. It may not silently weaken higher-level policy.

### 6.2 Atomic local ledger + outbox unit of work

The implementation must provide one transaction boundary for:

```text
append audit event
+
enqueue sync outbox record
```

Calling an API that commits the audit event and then inserting an outbox row in a second transaction does **not** satisfy the design.

The current SQLite `append()` behavior therefore cannot simply be wrapped by a second independent outbox write; implementation must expose or add an atomic Unit-of-Work boundary.

### 6.3 Conflict-resolution matrix

No last-write-wins reconciliation is permitted for canonical audit/effect records.

| Condition | Resolution |
|---|---|
| same `event_id`, same digest | idempotent replay; ACK existing record |
| same `run_id + sequence`, same digest | idempotent replay |
| same `run_id + sequence`, different digest | `SPLIT_BRAIN_CONFLICT`; block mutation and reconcile writer epochs |
| cloud missing local outbox rows from current epoch | replay exact outbox rows idempotently |
| local host missing cloud-ACKed rows | recover/read shared rows before assuming next sequence/state |
| stale writer epoch attempts sync/mutation | reject as `STALE_WRITER` |
| effect intent exists, receipt missing | provider-state reconciliation; no blind retry |
| receipt exists but local projection missing | reconstruct local projection from exact shared intent/receipt refs |

The local ledger remains the source-of-origin truth for unsynced events emitted by its current writer epoch. The shared ledger is the cross-host recovery and mutation-ownership truth. Neither side may overwrite a conflicting record to "make them match".

### 6.4 Cloud outage behavior

When the shared PostgreSQL ledger is unavailable:

```text
observe / research / review / diagnose / plan   may continue locally
existing already-materialized protections       remain effective
new shared-durability-required mutation          WAIT / fail closed
cross-host mutation takeover                     forbidden
```

This preserves local Shield usefulness without allowing disconnected split-brain mutation.

## 7. Canonical identity and digest rules

### 7.1 Canonical IDs are opaque and globally unique

Human-friendly examples such as `F-GWC-0042` are aliases/projections, not canonical allocation rules.

Canonical object IDs use:

```text
<type-prefix>-<project-or-global>-<uuid>
```

Examples:

```text
OBS-gwc-550e8400-e29b-41d4-a716-446655440000
F-gwc-6ba7b810-9dad-41d1-80b4-00c04fd430c8
PRT-global-6ba7b811-9dad-41d1-80b4-00c04fd430c8
FP-gwc-6ba7b812-9dad-41d1-80b4-00c04fd430c8
HA-gwc-6ba7b813-9dad-41d1-80b4-00c04fd430c8
```

Required properties:

- generated without a central sequential allocator;
- stable for the lifetime of that entity;
- never reused after deletion/dismissal;
- human aliases may be assigned separately for UI/Jira/Slack.

UUID version is an implementation choice as long as collision resistance and canonical string normalization are deterministic. Domain semantics must not depend on timestamp ordering of the UUID.

### 7.2 Entity versioning

Mutable canonical entities such as Finding and Protection have an integer `version` starting at 1.

Updates use compare-and-swap semantics against the expected prior version. A stale version cannot silently overwrite a newer version.

```text
expected version = 4
current version  = 5
→ STALE_VERSION / re-read
```

### 7.3 Artifact digests

Immutable artifacts/snapshots use canonical JSON serialization:

```text
UTF-8
sorted keys
no insignificant whitespace
explicit null/omission rules defined by schema
```

Digest:

```text
sha256:<64 lowercase hex>
```

An artifact reference that gates action binds both object identity/version and digest where applicable.

Example:

```text
shield://gwc/fix-plans/<uuid>@v2#sha256:<digest>
```

The exact URI syntax is illustrative; the required semantics are `id + version + digest`.

## 8. Canonical object contract appendix

Cardinality notation:

```text
1      required exactly once
0..1   optional
0..N   optional list
1..N   non-empty list
```

### 8.1 Observation

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | canonical unique ID |
| `project_id` | 1 | registered Project Shield ID |
| `sensor.id` | 1 | sensor identity |
| `sensor.capability` | 1 | capability ID |
| `sensor.version` | 1 | version/ref |
| `type` | 1 | observation type |
| `subject.ref` | 1 | exact subject reference |
| `observed_at` | 1 | timestamp |
| `source_ref` | 1 | exact source/evidence reference |
| `fingerprint` | 1 | normalized correlation fingerprint |
| `evidence_refs` | 0..N | exact evidence refs |
| `signal` | 1 | bounded observed value |
| `freshness` | 1 | freshness metadata |
| `confidence` | 1 | sensor confidence, not Finding severity |
| `labels` | 0..N | non-authoritative tags |

Observation is immutable after append.

### 8.2 Finding

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | stable canonical ID |
| `version` | 1 | CAS-managed integer |
| `scope` | 1 | PROJECT or GLOBAL plus owner |
| `classification.category` | 1 | category |
| `classification.severity` | 1 | severity |
| `classification.confidence` | 1 | evidence confidence |
| `statement.summary` | 1 | canonical problem statement |
| `statement.expected` | 1 | expected state/behavior |
| `statement.observed` | 1 | observed state/behavior |
| `statement.impact` | 1 | bounded impact statement |
| `provenance.observation_refs` | 1..N | finding cannot be confirmed without evidence origin |
| `provenance.research_artifact_refs` | 0..N | research refs |
| `provenance.review_refs` | 0..N | review refs; required when policy requires review |
| `evidence.claims` | 1..N | claim/evidence mapping |
| `affected` | 1 | bounded assets/capabilities/runs |
| `lifecycle.status` | 1 | canonical lifecycle state |
| `lifecycle.first_seen` | 1 | timestamp |
| `lifecycle.last_seen` | 1 | timestamp |
| `lifecycle.recurrence_count` | 1 | non-negative integer |
| `relationships` | 1 | may contain empty lists/nulls |
| `ownership.shield` | 1 | authoritative Shield instance |
| `projection_refs` | 0..N | non-canonical external refs |

A `CONFIRMED` Finding requires at least one proven/accepted evidence claim. A low-confidence AI assertion alone cannot satisfy a critical protected effect.

### 8.3 ProtectionDirective

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | canonical directive ID |
| `version` | 1 | CAS-managed integer |
| `reason_finding_ref` | 1 | canonical Finding version/ref |
| `scope` | 1 | exact type + target |
| `action` | 1 | closed action vocabulary |
| `authority.source` | 1 | policy/authority source ref |
| `authority.rule` | 1 | exact rule ID/version |
| `issuer_identity_ref` | 1 | authenticated issuer identity |
| `audience_project` | 1..N | exact intended project(s) |
| `issued_at` | 1 | timestamp |
| `expires_at` | 1 | timestamp/lease boundary |
| `expiry_behavior` | 1 | `FAIL_OPEN` or `FAIL_SAFE` |
| `nonce` | 1 | replay-resistant unique nonce |
| `payload_digest` | 1 | canonical digest |
| `authentication_ref` | 1 | transport/workload/signed-artifact auth evidence |
| `release_conditions` | 0..N | explicit release requirements |

Receiver validation requires issuer authenticity, correct audience, current policy/rule, digest integrity, nonce freshness, and non-stale directive version.

A critical `FAIL_SAFE` fence does not silently release merely because Global Shield/control-plane connectivity is lost. It enters control-plane-unknown/release-pending semantics until release evidence is valid.

### 8.4 ProtectionReceipt

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | canonical receipt ID |
| `directive_ref` | 1 | exact directive ID/version/digest |
| `project` | 1 | receiving project |
| `status` | 1 | APPLIED/PARTIAL/REJECTED/FAILED |
| `effective_scope` | 1 | exact materialized scope |
| `active_runs_affected` | 0..N | exact run refs |
| `new_execution_denied` | 1 | boolean when relevant |
| `applied_at` | 1 | timestamp |
| `evidence_refs` | 1..N | local effect/readback evidence |
| `receipt_digest` | 1 | canonical digest |
| `assurance_class` | 1 | A1/A2/A3 defined below |

Protection assurance classes:

```text
A1 LOCAL_READBACK          Project Shield exact local readback
A2 EXTERNAL_READBACK       independent target/provider state readback
A3 INDEPENDENT_ATTESTATION independent verifier/attestation required by policy
```

A Global `QUARANTINE`/`LOCKDOWN` policy may require A2 or A3; a self-reported ACK is not automatically sufficient for critical fleet-wide protection.

### 8.5 DiagnosisArtifact

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | immutable artifact ID |
| `finding_ref` | 1 | exact Finding version |
| `hypotheses` | 1..N | each includes supporting/contradicting evidence |
| `selected_root_cause` | 0..1 | may be absent for containment/uncertain diagnosis |
| `unresolved_questions` | 0..N | explicit unknowns |
| `affected_scope` | 1 | known + uncertain scope |
| `diagnosis_confidence` | 1 | confidence |
| `digest` | 1 | immutable artifact digest |

### 8.6 FixPlan

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | stable plan identity |
| `version` | 1 | increments on material plan revision |
| `finding_ref` | 1 | exact Finding version |
| `diagnosis_ref` | 1 | exact diagnosis digest/ref |
| `strategy` | 1 | ROOT_CAUSE_FIX/MITIGATION/CONTAINMENT |
| `objective` | 1 | expected target behavior |
| `selected_option` | 1 | selected change + rationale |
| `scope.included` | 1..N | exact bounded scope |
| `scope.excluded` | 0..N | explicit exclusions |
| `changes` | 1..N | intended capabilities/targets |
| `dependencies` | 0..N | exact refs |
| `risks` | 0..N | risks |
| `protection_requirements` | 0..N | protections required during healing |
| `verification` | 1 | technical/behavioral/monitoring requirements |
| `rollback` | 1 | rollback class/strategy |
| `required_healing_level` | 1 | H0-H4 |
| `digest` | 1 | canonical digest of exact version |

A material scope/change/authority/verification change creates a new FixPlan version and digest.

### 8.7 HealingAttempt

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | immutable attempt ID |
| `finding_ref` | 1 | exact Finding version |
| `fix_plan_ref` | 1 | exact plan version/digest |
| `attempt_no` | 1 | per-finding monotonic attempt counter |
| `authority_ref` | 0..1 | required when effect policy requires authority |
| `writer_epoch` | 0..1 | required for mutation-bearing attempt |
| `effect_intent_refs` | 0..N | required for protected external effects |
| `preconditions` | 1 | exact state/SHA/protection refs |
| `executor` | 1 | capability + provider identity |
| `started_at` | 1 | timestamp |
| `mutation_refs` | 0..N | exact effect refs |
| `result.state` | 1 | RUNNING/SUCCEEDED/FAILED/REVERTED/INCONCLUSIVE |
| `verification_ref` | 0..1 | required before HEALED transition |

The attempt identity is immutable; retries/replans create new attempts.

### 8.8 HealthSnapshot

Canonical dimensions are exactly:

```text
Delivery
Runtime
Security
Governance
Agent/Provider
Protection
Observability
```

Each dimension is required and uses:

```text
HEALTHY | DEGRADED | AT_RISK | CRITICAL | UNKNOWN
```

Health, Exposure, and Protection Effectiveness remain separate axes.

Snapshot fields:

| Field | Cardinality | Rule |
|---|---:|---|
| `id` | 1 | immutable snapshot ID |
| `project` | 1 | project ID |
| `at` | 1 | timestamp |
| `health` | 1 | derived overall health |
| `exposure` | 1 | UNEXPOSED/LIMITED/EXPOSED/WIDESPREAD/UNKNOWN |
| `protection` | 1 | EFFECTIVE/PARTIAL/DEGRADED/FAILED/UNKNOWN |
| `dimensions` | 1 | all seven required dimensions |
| `reasons` | 0..N | exact finding/protection/sensor refs |
| `confidence` | 1 | derived confidence |
| `digest` | 1 | immutable snapshot digest |

### 8.9 ExperienceRecord and LearningCandidate

The learning/storage addendum remains authoritative for their semantic fields with these extra mandatory provenance rules:

```text
ExperienceRecord
  source run/trace refs       required
  producer/provider/version   required when known
  evidence provenance digest required
  eligibility state          required

LearningCandidate
  source Experience refs      required non-empty
  frozen evaluation dataset   required before VALIDATED
  target version              required
  promotion authority ref     required before production promotion
```

## 9. Exact A2A protection ACK/readback contract

The A2A envelope remains `dw.taskcontroller.a2a/v1`.

Directive command:

```yaml
kind: COMMAND
request:
  capability: shield.protection.apply
artifact_refs:
  - <exact ProtectionDirective ref including version/digest>
state:
  directive_digest: sha256:...
  expected_project: gwc
  required_assurance: A2
```

Project reply:

```yaml
kind: REPORT
request:
  capability: shield.protection.ack
artifact_refs:
  - <exact ProtectionReceipt ref>
state:
  directive_digest: sha256:...
  receipt_digest: sha256:...
  status: APPLIED
  assurance_class: A2
```

The REPORT itself is not final proof. The Controller/Global Shield must fetch the exact `ProtectionReceipt` artifact referenced by the envelope and verify:

```text
directive ID/version/digest
project/audience
receipt digest
effective scope
status
required assurance class
evidence refs
freshness/lease
```

Only then may coverage be counted as EFFECTIVE for that project.

## 10. Authority binding contract

### 10.1 Shield configuration is an upper bound, never a grant

Configuration such as:

```yaml
healing:
  autonomous_max_level: H2
  standing_authority_max_level: H3
```

means only:

> Shield policy will never autonomously exceed this level even if an authority provider presents broader authority.

It does **not** mean authority exists.

Every effect separately resolves applicable authority through the project's authority adapter/provider.

### 10.2 Governed-project binding to GWC

For GWC-governed work, Shield must bind to the existing GWC authority/evidence contract rather than inventing a second approval model.

Relevant current GWC artifacts include:

```text
tools/node_architect/scope_hash_calculation.py
tools/node_architect/approval_command_validation.py
schemas/node-architect/gate-authority/approval-request.schema.json
```

The GWC scope identity binds semantic scope such as:

```text
task_id
repository
base_ref/base_sha
working_branch/head_sha when required
risk_class
authorized_paths
authorized_actions
excluded_actions
additional bindings
```

and emits a deterministic `scope_hash` only when scope is READY. The scope hash itself does not grant authority.

GWC approval validation binds an exact generated approval request to:

```text
request ID
gate
scope hash short/full request binding
expiry
current base/head/scope/repository readback
actor target
action target / branch / PR/environment as applicable
single-consumption/idempotency key
```

and rejects drift, stale/expired responses, actor/target mismatch, and replay. Validation itself still does not grant execution/merge/deploy authority; the next authority node remains authoritative.

### 10.3 Shield effect authority evidence

A Shield mutation in a governed project must be able to reference, where applicable:

```yaml
authority_binding:
  authority_provider: gwc
  scope_identity_ref: required
  scope_hash: required
  approval_request_ref: required when human gate applies
  approval_validation_ref: required when human gate applies
  current_readback_ref: required
  consumption_key: required for consumable approval
  authority_node_ref: required for the actual grant/effect decision
```

Shield never reconstructs authority from Slack text, A2A state, Jira status, a prior conversation, or a bare `APPROVE` string.

### 10.4 Raising autonomy limits

Changing a project's `autonomous_max_level`, `standing_authority_max_level`, allowed action set, or protection weakening is itself an authority-sensitive configuration change. It must be versioned/audited and pass the governing project's applicable config/authority policy.

An Executor/Healer/LearningCandidate cannot raise these values as part of its own remediation.

## 11. Scheduled self-review recursion and budget guard

Scheduled self-review uses bounded TaskController runs and cannot recursively review itself without limit.

Required origin metadata:

```yaml
review_origin:
  source: POST_RUN | SCHEDULED | HUMAN | SYSTEMIC
  parent_review_ref: optional
  review_depth: required integer
  review_window_ref: required
  idempotency_key: required
```

Rules:

1. a self-review run does not trigger another automatic POST_RUN self-review by default;
2. default `max_review_depth = 1`;
3. the same `scope + window + review_profile_version` produces the same idempotency identity;
4. each profile has a finite token/time/run budget;
5. budget exhaustion produces a bounded finding/metric or escalation, not another self-review run;
6. a human or policy may explicitly request a second-level review, but it is a new bounded authority/trigger decision.

## 12. Learning provenance and holdout isolation

Dataset eligibility alone is insufficient to resist feedback/self-confirmation loops.

Each dataset item records:

```yaml
dataset_item:
  experience_ref: required
  provenance_digest: required
  label:
    source: DETERMINISTIC | HUMAN | LLM
    producer_ref: required
    confidence: required
  trust_tier: required
  dataset_role: TRAIN | DEVELOPMENT | HOLDOUT
  membership_version: required
```

Hard rules:

- optimizer/training procedures may not consume HOLDOUT labels as training feedback;
- critical golden HOLDOUT membership cannot be rewritten by the candidate being evaluated;
- an LLM-generated label is not treated as independent human/deterministic truth;
- train/development/holdout contamination invalidates the comparison;
- promotion evidence records exact dataset version/digests and evaluator versions;
- adversarial/poisoned/low-provenance experience remains quarantined.

## 13. Systemic correlation independence

Project breadth alone is not evidence independence. Global correlation records at least:

```yaml
correlation_evidence:
  project_count: ...
  independent_sensor_sources: ...
  independent_provider_sources: ...
  common_dependencies: []
  shared_failure_domain: ...
  independence_confidence: ...
```

Three projects that all repeat one faulty shared sensor/provider output justify investigation, but do not automatically equal three independent proofs of the systemic hypothesis.

## 14. Canonical terminology corrections

### 14.1 Detection loop vs Finding lifecycle

Use this closed-loop wording:

```text
OBSERVE
→ RESEARCH / UNDERSTAND
→ DETECT SIGNAL / BUILD FINDING CANDIDATE
→ VALIDATE / CONFIRM FINDING
→ DIAGNOSE
→ PLAN
→ HEAL / PROTECT
→ VERIFY
→ MONITOR
```

`DETECTED` remains a Finding lifecycle state. "DETECT/FINDING" in the high-level loop should be read as `DETECT SIGNAL / BUILD FINDING CANDIDATE`, not as immediate canonical Finding creation.

### 14.2 Health dimensions

The canonical dimension list is the seven dimensions in §8.8 of this addendum. Any abbreviated earlier list must be interpreted as non-exhaustive shorthand.

## 15. PostgreSQL deployment decision rule

`PostgresRunLedger` remains provider-neutral.

The earlier "Supabase preferred" wording is refined into an environment decision rule:

```text
low-ops/shared MVP or development
    → Supabase PostgreSQL is a reasonable default

AWS-hosted protected production with private VPC/network/governance needs
    → Amazon RDS for PostgreSQL is preferred
```

Why Supabase can still be first for a low-ops MVP:

- standard PostgreSQL semantics;
- low provisioning/operations overhead;
- sufficient shared durability for validating the ledger/outbox/recovery contract;
- provider choice can change without changing Shield semantics.

Why RDS may supersede it for protected AWS production:

- private VPC topology;
- AWS-native identity/network/operations integration;
- Multi-AZ/backup/enterprise controls aligned with an AWS-hosted runtime.

The implementation plan must select the deployment target from the actual environment rather than treating Supabase as a universal architecture requirement.

## 16. MVP scope refinement

The architecture remains broad, but the first implementation slice must prove safety before Learning/ML expansion.

### MVP-0 — Protection and durable execution foundation

Required:

```text
Project Shield profile
Observation + Trigger basics
bounded TaskController run creation/continuation
canonical object IDs/version/digests
Finding + Protection + FixPlan + HealingAttempt contracts
local SQLite audit
atomic audit+outbox Unit of Work
shared PostgreSQL replication
writer epoch/fencing for mutation
EffectIntent/Receipt for protected effects
authority adapter binding
one local protect/heal sequence
one Global systemic/fence sequence
basic deterministic scheduled review
```

Explicitly deferred from MVP-0:

```text
full OpenTelemetry platform deployment
MLflow/Langfuse dependency
adaptive ML routing
fine-tuning
RL
automatic prompt/skill promotion
```

### MVP-1 — Observability and learning foundation

```text
trace/span IDs
ExperienceRecord
dataset provenance and frozen holdout
scheduled Project/Global learning review
human-reviewed LearningCandidate
```

### MVP-2 — Versioned self-improvement experiments

```text
prompt challenger
skill challenger
workflow challenger
champion/challenger promotion evidence
```

Adaptive ML routing and model-weight training remain future work requiring independent approval/specification.

## 17. ADR rejected-alternative register

The existing ADRs remain valid. This appendix records the principal rejected alternative so each entry acts as a decision rather than only a rule statement.

| ADR | Principal rejected alternative |
|---|---|
| 001 | one global Shield with direct project control, or fully isolated projects with no global correlation |
| 002 | Global can only observe and cannot fence systemic emergencies |
| 003 | Global directly edits/heals project state |
| 004 | Jira/GitHub issue identity is canonical Finding identity |
| 005 | fire-and-forget protection without lease/readback/ACK |
| 006 | sensor directly assigns canonical problem conclusion |
| 007 | mutate prior Observation to represent resolution |
| 008 | trigger engine limited to simple single-event rules |
| 009 | autonomous protection on weak/ambiguous evidence by default |
| 010 | fail-stop the entire project when one protection dependency fails |
| 011 | every noisy signal immediately becomes canonical Finding |
| 012 | Finding identity changes when severity/ticket/recurrence changes |
| 013 | collapse severity, confidence, and priority into one score |
| 014 | systemic Finding absorbs/moves local evidence ownership |
| 015 | resolve reviewer conflict by majority vote |
| 016 | Jira/GitHub Done automatically closes Finding |
| 017 | diagnosis, plan, and execution are one mutable AI response |
| 018 | "autonomous mode" implicitly grants unlimited healing authority |
| 019 | multiple concurrent mutation attempts may heal same Finding scope |
| 020 | infinite retries until a healer eventually succeeds |
| 021 | healer may weaken tests/sensors/policy to get green status |
| 022 | successful HealingAttempt immediately closes Finding |
| 023 | protection release is an implicit side effect of fix success |
| 024 | boolean health and/or absence of evidence means healthy |
| 025 | protection/containment rewrites underlying health as healthy |
| 026 | monitoring uses only wall-clock duration regardless of relevant events |
| 027 | recurrence simply replays the previous fix |
| 028 | Shield health is invisible/unmanaged |
| 029 | Global Supervisor outage disables local Project Shield protection |
| 030 | alert/finding volume is the main effectiveness KPI |
| 031 | telemetry/evaluation backend becomes canonical audit truth |
| 032 | vendor-specific tracing IDs replace TaskController semantic IDs |
| 033 | raw AuditEvent automatically becomes learning/training sample |
| 034 | detached scheduler replaces active TaskController monitoring/continuation semantics |
| 035 | LLM judge is used as universal evaluator even for deterministic evidence |
| 036 | evaluation datasets contain only failures or are unversioned |
| 037 | start with model training before prompt/skill/workflow improvement |
| 038 | online production agent self-trains and continues as trusted runtime |
| 039 | learned behavior promotes directly without frozen regression comparison |
| 040 | learning system directly rewrites authority/protection policy |
| 041 | canonical audit lifetime is tied to one Agent host |
| 042 | naive independent dual-write to SQLite and cloud |
| 043 | Shield domain schema depends on Supabase- or RDS-specific semantics |
| 044 | every ordinary event blocks on cloud durability, or no critical effect ever requires shared durability |

## 18. Review-gap closure map

| PR #69 review gap | Design response |
|---|---|
| #1 execution/scheduling under-specified | §§2–4 define logical supervisor vs bounded TaskController run; local and Global E2E sequences bind continuation/A2A |
| #2 schemas illustrative | §§7–9 define canonical IDs, CAS versions, digests, field cardinality, exact protection ACK/readback |
| #3 ADRs lack rejected alternatives | §17 rejected-alternative register for ADR-001→044 |
| #4 standing authority/config seam | §10 binds config as upper bound and references actual GWC scope/approval/readback contract |
| #5 sync divergence unclear | §§5–6 define writer fencing, two durability levels, atomic UoW and conflict matrix |
| #6 terminology/provider rationale | §§14–15 normalize detection/health language and make Supabase-vs-RDS an environment decision |

## 19. Design handoff boundary

This addendum remains design-only.

It authorizes no code/config/database changes, no Supabase/RDS provisioning, no runtime mutation, no model training, no merge/deploy, and no H4 effect.

After this refinement, the written Project Shield architecture consists of the parent design, the learning/storage addendum, and this execution/data-contract addendum. The next process gate remains human review of the written design before any implementation plan is created.
