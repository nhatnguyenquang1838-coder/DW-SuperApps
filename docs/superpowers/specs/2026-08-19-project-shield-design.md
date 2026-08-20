# DW Project Shield — Hybrid Proactive Project Protection Design

Date: 2026-08-19
Status: **Design approved in chat; implementation not authorized**
Repository: `nhatnguyenquang1838-coder/DW-SuperApps`
Base: `main@3f9c81d7c13098ce502dfa48c82d1d92f82e34ee`
Design branch: `design/project-shield-20260819`
Working product name: **DW Project Shield**
Architecture description: **Continuous Project Assurance & Autonomous Remediation Framework**

Related existing contracts at the bound base:

- `agents/shared/taskcontroller-a2a-protocol.md`
- `docs/superpowers/specs/2026-08-16-taskcontroller-reference-a2a-design.md`
- `taskcontroller/domain/enums.py`

## 1. Purpose

DW Project Shield is a proactive protection capability for DW SUPER projects. It continuously observes project and execution health, researches uncertain signals, validates findings, plans remediation, heals within explicit authority, verifies outcomes, monitors recurrence, and prevents unsafe effects.

The feature is intentionally **not** a monolithic Shield Agent and **not** a replacement for TaskController. Shield owns protection semantics and policies. TaskController remains the generic coordination/runtime layer for deterministic runs, nodes, reviews, A2A interaction, leases, continuation, and audit.

The core closed loop is:

```text
OBSERVE
   ↓
UNDERSTAND / RESEARCH
   ↓
DETECT / FINDING
   ↓
DIAGNOSE
   ↓
PLAN
   ↓
HEAL / PROTECT
   ↓
VERIFY
   ↓
MONITOR
   ↓
LEARN / POLICY PROPOSAL
   └──────────────────────► OBSERVE
```

The architecture must support multiple projects, multiple research/review/healing providers, heterogeneous agents, and project-specific governance without hard-coding a vendor or review lens into the kernel.

## 2. Architectural position

```text
                         DW SUPER
                            │
                            ▼
              ┌──────────────────────────┐
              │ Global Shield Supervisor │
              │                          │
              │ Cross-project correlation│
              │ Global policy            │
              │ Systemic findings        │
              │ Emergency fencing        │
              │ Fleet health             │
              └────────────┬─────────────┘
                           │ Shield A2A
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
 ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
 │ Project Shield │ │ Project Shield │ │ Project Shield │
 │ Project A      │ │ Project B      │ │ Project C      │
 │                │ │                │ │                │
 │ Observe        │ │ Observe        │ │ Observe        │
 │ Research       │ │ Research       │ │ Research       │
 │ Findings       │ │ Findings       │ │ Findings       │
 │ Diagnose       │ │ Diagnose       │ │ Diagnose       │
 │ Heal           │ │ Heal           │ │ Heal           │
 │ Protect        │ │ Protect        │ │ Protect        │
 │ Verify/Monitor │ │ Verify/Monitor │ │ Verify/Monitor │
 └───────┬────────┘ └───────┬────────┘ └───────┬────────┘
         │                  │                  │
         └──────────────────┼──────────────────┘
                            ▼
                  TaskController Fabric
                            │
                 capability-based routing
                            │
              Agents / Powers / Providers
```

### 2.1 Boundary

The selected topology is **Hybrid**:

- every project has an independent Project Shield control loop;
- a Global Shield Supervisor receives normalized project health and finding projections;
- the Global Supervisor performs cross-project correlation and systemic protection;
- a Global failure must not disable local Project Shield protection;
- project remediation authority remains local;
- the Global Supervisor may issue policy-bound emergency fencing directives but may not directly mutate project code, merge, deploy, or perform local remediation.

The governing principle is:

> **Authority stays local. Coordination and emergency fencing may be global.**

## 3. Design principles

1. **Capability-first, provider-neutral.** Sensors, research, review, planning, healing, verification, and projections are selected by capability/profile rather than product name.
2. **TaskController remains the coordination kernel.** Shield does not duplicate run/node scheduling, A2A, continuation, lease, or generic review primitives.
3. **Evidence before action.** Raw observations are not findings; findings are not fixes; successful execution is not closure.
4. **Reference over replay.** Repository state, evidence, findings, plans, and verification use durable exact references and digests.
5. **Slack remains Human Control Plane.** It is a semantic projection and optional pointer-only wake-up surface, never canonical Shield state.
6. **Jira/GitHub issues are projections.** Canonical finding identity remains inside Shield state/artifacts.
7. **Local isolation.** One project or Global Supervisor failure must not collapse unrelated project protection.
8. **Reversible protection before destructive action.** Global emergency actions prefer pause/fence/quarantine over cancel or mutation.
9. **Selective fail-closed.** Loss of a critical protection capability blocks only effects that require that capability; read-only/research work may continue.
10. **No self-authorizing healer.** Healing may not weaken the controls, tests, policies, sensors, or authority boundaries that govern it.
11. **No infrastructure-first expansion.** MVP proves semantics on existing TaskController/A2A/reference bindings before introducing a new event bus or distributed orchestration substrate.
12. **No chain-of-thought dependency.** Recovery and audit use bounded state, evidence references, decisions, and artifacts.

## 4. Logical components

### 4.1 Project Shield

A Project Shield is the authoritative local protection instance for one project or one explicitly owned shared-infrastructure domain.

Logical components:

- **Sensor Manager** — runs event, poll, and meta sensors.
- **Observation Store** — append-only immutable observations.
- **Trigger Engine** — evaluates deterministic/configured trigger policy.
- **Research Orchestrator** — invokes research capabilities when evidence is incomplete.
- **Finding Engine** — correlates signals, validates candidates, reconciles review, and owns canonical findings.
- **Diagnosis Service** — builds root-cause hypotheses and evidence-backed diagnosis artifacts.
- **Fix Planner** — creates bounded FixPlan artifacts.
- **Healing Coordinator** — executes authorized healing attempts through TaskController.
- **Protection Manager** — applies, renews, downgrades, and releases local protections.
- **Verification & Monitoring** — verifies technical/behavioral outcomes and recurrence windows.
- **Health Evaluator** — derives health/exposure/protection snapshots.
- **Meta Shield** — observes Shield health itself and creates Shield degradation findings.
- **Projection Adapters** — Jira/GitHub/Slack/Notion or future external projections.

These are logical boundaries, not a requirement for one service/process/database per component.

### 4.2 Global Shield Supervisor

Logical components:

- **Shield Registry** — known Project Shields, ownership, modes, capabilities, and escalation routes.
- **Fleet Heartbeat Receiver** — normalized project health/protection heartbeats.
- **Global Correlation Engine** — correlates local findings/signals across projects.
- **Systemic Finding Service** — owns global findings that reference local findings.
- **Global Policy Evaluator** — evaluates inheritance and emergency-fencing policy.
- **Emergency Fencing Service** — issues scoped reversible directives and tracks exact ACK coverage.
- **Fleet Health Evaluator** — derives global/fleet health.
- **Policy Proposal Engine** — produces evidence-backed policy/routing proposals; it does not silently mutate policy.

The Global Supervisor does not become a super-TaskController. It requests project-local action over Shield A2A and relies on each Project Shield to evaluate and execute within local authority.

## 5. Canonical Shield model

The minimal canonical model is:

```text
Shield
├── Observation
├── Finding
├── Protection
├── HealingAttempt
└── HealthState
```

Research artifacts, reviews, diagnoses, FixPlans, verification results, signal clusters, and candidates support these canonical objects and workflows.

### 5.1 Observation

An Observation is an immutable fact emitted by a sensor.

```yaml
observation:
  id: OBS-...
  project_id: gwc
  sensor:
    id: github-ci
    capability: shield.sensor.ci
    version: ...
  type: CI_RUN_FAILED
  subject:
    kind: pull_request
    ref: github://...
  observed_at: ...
  source_ref:
    exact_ref: ...
    sha: ...
  fingerprint: ...
  evidence_refs: []
  signal:
    value: FAILED
  freshness:
    observed_age: ...
    source_age: ...
  confidence: HIGH
  labels: [ci]
```

Observations do not carry canonical Finding severity. Sensors are evidence producers, not decision makers.

Observation Store semantics are append-only. Resolution is represented by later observations, not mutation of old observations.

### 5.2 SignalCluster

SignalCluster is a pre-canonical correlation object.

```yaml
signal_cluster:
  id: SC-...
  fingerprint: ...
  scope: PROJECT
  observation_refs: []
  first_seen: ...
  last_seen: ...
  occurrences: 14
  affected_assets: []
  correlation:
    method: SAME_FINGERPRINT
    confidence: HIGH
```

### 5.3 FindingCandidate

A FindingCandidate represents a hypothesis requiring evidence/review before canonical promotion.

```yaml
finding_candidate:
  id: FC-...
  cluster_refs: []
  hypothesis: ...
  category: PROVIDER_DEGRADATION
  evidence_status:
    proven: []
    partial: []
    missing: []
    stale: []
    conflict: []
  confidence: MEDIUM
  review_required: true
```

Candidate terminal dispositions include `CONFIRMED`, `DUPLICATE`, `INSUFFICIENT_EVIDENCE`, `EXPECTED_BEHAVIOR`, and `FALSE_POSITIVE`.

### 5.4 Finding

Finding is the canonical, stable, versioned assertion that a validated problem/risk exists.

```yaml
finding:
  id: F-GWC-0042
  version: 3
  scope:
    level: PROJECT
    project_id: gwc
  classification:
    category: PROVIDER_DEGRADATION
    severity: HIGH
    confidence: HIGH
  statement:
    summary: ...
    expected: ...
    observed: ...
    impact: ...
  provenance:
    observation_refs: []
    cluster_refs: []
    research_artifact_refs: []
    review_refs: []
  evidence:
    claims: []
    evidence_refs: []
  affected:
    assets: []
    capabilities: []
    runs: []
  lifecycle:
    status: CONFIRMED
    first_seen: ...
    last_seen: ...
    recurrence_count: 0
  relationships:
    duplicate_of: null
    parent_finding: null
    child_findings: []
    related_findings: []
  ownership:
    shield: shield://gwc
  projection_refs:
    github: []
    jira: []
```

Finding identity remains stable when severity, evidence, projections, planning, or recurrence changes.

Severity, confidence, and remediation priority are distinct dimensions. Shield assigns severity/confidence from evidence. Planning determines priority from severity plus exposure, blast radius, urgency, dependencies, cost, and business context.

### 5.5 ProtectionDirective

Protection is independent from Finding lifecycle.

```yaml
protection:
  id: PRT-...
  reason_finding_ref: F-...
  scope:
    type: PROVIDER
    target: hermes-cloud
  action: QUARANTINE
  authority:
    source: global-shield-policy
    rule: provider-critical-fencing
  state: ACTIVE
  issued_at: ...
  expires_at: ...
  release_conditions: []
```

MVP action vocabulary:

```text
WARN
DENY_NEW_EXECUTION
PAUSE
QUARANTINE
LOCKDOWN
```

Global Shield does not receive an implicit `CANCEL` or mutation power.

### 5.6 ProtectionReceipt

Global protection requires exact local acknowledgement.

```yaml
protection_receipt:
  directive_ref: shield://global/protections/PRT-009
  project: gwc
  status: APPLIED | PARTIAL | REJECTED | FAILED
  effective_scope: []
  active_runs_affected: []
  new_execution_denied: true
  applied_at: ...
  evidence_refs: []
```

A sent directive without ACK is `FENCING_UNKNOWN`, never `PROTECTED`.

### 5.7 DiagnosisArtifact

```yaml
diagnosis:
  finding_ref: shield://gwc/F-42
  version: 2
  symptoms: []
  hypotheses:
    - id: H1
      statement: ...
      confidence: HIGH
      supporting_evidence: []
      contradicting_evidence: []
  selected_root_cause:
    hypothesis_ref: H1
    rationale: ...
  unresolved_questions: []
  affected_scope:
    known: []
    uncertain: []
  diagnosis_confidence: HIGH
```

A FixPlan may choose `ROOT_CAUSE_FIX`, `MITIGATION`, or `CONTAINMENT`. Mitigation/containment does not automatically close the underlying finding.

### 5.8 FixPlan

```yaml
fix_plan:
  id: FP-...
  finding_ref: F-42
  based_on:
    diagnosis_ref: DIAG-...
    finding_version: 4
  strategy: ROOT_CAUSE_FIX
  objective:
    expected_behavior: ...
  selected_option:
    description: ...
    rationale: ...
  scope:
    included: []
    excluded: []
  changes: []
  dependencies: []
  risks: []
  protection_requirements: []
  verification:
    required_tests: []
    required_evidence: []
    observation_window: ...
  rollback:
    possible: true
    strategy: ...
  authority:
    required_healing_level: H3
```

Explicit excluded scope prevents opportunistic scope expansion by the healer.

### 5.9 HealingAttempt

```yaml
healing_attempt:
  id: HA-003
  finding_ref: F-42
  fix_plan_ref: FP-12@digest
  attempt_no: 2
  authority:
    level: H3
    authority_ref: ...
  preconditions:
    finding_version: 4
    target_sha: ...
    protection_state: ...
  executor:
    capability: code.fix
    provider: ...
  started_at: ...
  mutation_refs: []
  result:
    state: RUNNING | SUCCEEDED | FAILED | REVERTED | INCONCLUSIVE
  verification_ref: ...
```

A HealingAttempt is immutable as an attempt identity. Retries/replans create new attempts.

### 5.10 HealthSnapshot

Health is derived from observations, findings, protections, healing attempts, sensor coverage, recurrence, and policy.

```yaml
health_snapshot:
  project: gwc
  at: ...
  health: AT_RISK
  exposure: LIMITED
  protection: EFFECTIVE
  dimensions:
    delivery: DEGRADED
    runtime: HEALTHY
    security: HEALTHY
    governance: AT_RISK
    agent_provider: HEALTHY
    protection: HEALTHY
    observability: HEALTHY
  reasons: []
  confidence: HIGH
```

`UNKNOWN` is a first-class state. Loss of visibility must not be interpreted as health.

## 6. Sensor and trigger model

### 6.1 Sensor classes

**Event sensors** respond to source events such as CI completion, PR lifecycle, deployment, agent failure, and protection change.

**Poll sensors** reconcile sources that lack suitable events or require periodic freshness checks such as dependency state, stale PRs, Jira state, provider health, governance drift, and runtime health.

**Derived/meta sensors** observe Shield itself, including stale sensors, missing A2A progress, stuck Controller continuation, healing loops, missing protection ACKs, provider degradation, and audit gaps.

Each critical sensor has a health contract:

```text
HEALTHY | DEGRADED | STALE | FAILED
```

### 6.2 Trigger outcomes

Trigger Engine may produce:

```text
NO_ACTION
RECORD_ONLY
RESEARCH
REVIEW
FINDING_CANDIDATE
PROTECT
ESCALATE
```

A trigger never directly performs an arbitrary fix.

### 6.3 Trigger semantics

The engine supports:

- direct conditions;
- thresholds in a time/event window;
- cross-signal/project correlation;
- persistence (`persist_for`);
- absence/missing expected signal;
- sequence/state-transition patterns.

Noise controls:

```text
DEDUPE
DEBOUNCE
COOLDOWN
SUPPRESSION
AGGREGATION
```

Suppression prevents repeated action, not evidence capture. Observations continue to be recorded.

### 6.4 Protection trigger classes

- **PREVENTIVE** — intercept an unsafe action before effect.
- **RESPONSIVE** — contain an already observed harmful condition and reduce blast radius.

Evidence-first is default. Immediate `protect-first / diagnose-second` is allowed only for explicit deterministic hard-guard conditions such as invalid authority signature, explicitly revoked credential/identity, known compromised provider identity, or a destructive effect violating a hard policy.

## 7. Research and independent review workflow

Research is a capability-composed workflow, not a kernel-specific agent.

Reference DAG:

```text
R0 RESEARCH_INTAKE
   ↓
R1 RESEARCH_COLLECT[*]
   ↓
R2 RESEARCH_SYNTHESIZE → ResearchArtifact@digest
   ↓ freeze
V1 INDEPENDENT_REVIEW[*]
   ↓
V2 REVIEW_RECONCILE
   ↓
F1 FINDING_NORMALIZE
   ↓
I1 ISSUE_PROJECT (optional projection)
   ↓
P1 FIX_PLAN
   ↓
P2 PLAN_REVIEW
   ↓
H1 IMPLEMENTATION_HANDOFF
```

Research providers may include repository research, Context7/docs research, web/domain research, audit history, or domain-specific Powers. Provider names are resolved from capability/profile configuration.

A review profile is composable. For example, one project may require architecture/security/runtime/governance reviews, while another may use application/database/security reviews. Review lens names are never kernel enums.

Independent review uses a frozen artifact digest. Reviewers do not review a moving target.

Conflicting reviewer conclusions produce `EVIDENCE_CONFLICT` and targeted research or another independent review; majority vote does not establish truth.

## 8. Finding Engine and systemic promotion

### 8.1 Correlation/deduplication

Correlation levels:

1. exact normalized fingerprint;
2. asset + failure mode;
3. semantic/root-cause relation;
4. explicit reviewer reconciliation when confidence is insufficient.

Deduplication does not collapse useful local detail. Parent/child and related-finding relationships preserve distinct manifestations.

### 8.2 Evidence graph

Shield should be able to answer why a Finding exists:

```text
Observations ─► Evidence ─► Claims ─► Finding
Documents/refs ───────────► Claims ─► Finding
Reviews ────────────────────────────► Finding
```

Evidence status vocabulary for Shield is:

```text
PROVEN | PARTIAL | MISSING | STALE | CONFLICT
```

This preserves the established GWC-style evidence states while making conflict explicit for Shield reconciliation.

### 8.3 Systemic promotion

A Local Finding does not become global merely because several projects show similar symptoms.

```text
Local Findings
      ↓
Global correlation
      ↓
Systemic Candidate
      ↓
Cross-project/shared-asset evidence
      ↓
Systemic Finding
```

Promotion may be caused by breadth, a critical shared asset, a common vulnerable dependency, or a defect in shared framework/provider/governance infrastructure.

A Systemic Finding references local Findings rather than absorbing their ownership/evidence.

## 9. Finding lifecycle and projections

Canonical lifecycle:

```text
DETECTED
   ↓
VALIDATING
   ├────────────► DISMISSED
   ↓
CONFIRMED
   ↓
DIAGNOSING
   ↓
PLANNED
   ↓
MITIGATING
   ↓
HEALED
   ↓
MONITORING
   ├────────────► RECURRENT ─► DIAGNOSING
   └────────────► CLOSED
```

Other dispositions include:

```text
OPEN
FIX_PLANNED
ACCEPTED_RISK
DEFERRED
DUPLICATE
DISMISSED
```

`ACCEPTED_RISK` requires an applicable authority reference. An AI agent may not self-accept risk.

Jira/GitHub issue state is not canonical Finding state. A projected issue may be `DONE` while the Finding remains `MITIGATING` or `MONITORING` until verification completes. Issue closure without required verification may itself become an observation/finding.

## 10. Protection and emergency fencing

### 10.1 Global authority

Global Shield may:

```text
OBSERVE
RESEARCH cross-project
CORRELATE
CREATE SYSTEMIC FINDING
WARN
DENY NEW EXECUTION
PAUSE
QUARANTINE
LOCKDOWN when explicit policy allows
```

Global Shield may not directly:

```text
EDIT project code
MERGE
DEPLOY
perform destructive/data/security mutation
execute local remediation
```

### 10.2 Local application and ACK

A global directive is sent to the relevant Project Shield. The Project Shield evaluates exact directive/policy scope and returns a ProtectionReceipt.

```text
FENCE_REQUEST
    ↓
Project policy evaluation
    ↓
FENCE_APPLIED / PARTIAL / REJECTED / FAILED
    ↓
exact readback
    ↓
ProtectionReceipt
```

Conflicts or irreversible operations in progress must be surfaced as `PARTIAL`/exception evidence, never silently ignored.

### 10.3 Protection lease

Protection directives are leased unless policy explicitly requires human release:

```text
issued_at
ttl
renew_before
release_conditions
```

A persistent systemic condition renews the lease. Recovery evaluates downgrade/release separately.

## 11. Healing authority and self-protection

Healing authority ladder:

| Level | Meaning | Typical effect |
|---|---|---|
| H0 | Observe/diagnose | no mutation |
| H1 | Recommend/plan | Finding, Diagnosis, FixPlan, issue projection |
| H2 | Safe heal | reversible bounded runtime/state operation |
| H3 | Engineering heal | branch/code/config/test + Draft PR + validation |
| H4 | Critical effect | merge/deploy/destructive/security/authority-sensitive effect |

Each project declares `autonomous_max_level`. H4 always requires explicit applicable authority; self-healing mode cannot imply it.

### 11.1 Preconditions and stale fencing

Before any effect, Healing Coordinator revalidates:

- Finding remains active/current;
- FixPlan digest/version remains current;
- target base/head SHA remains applicable;
- authority remains valid;
- protection state still permits the action;
- no conflicting higher-priority Finding invalidates the plan.

Critical drift makes the attempt stale and forces replan rather than silent continuation.

### 11.2 One active mutation attempt

By default one Finding has at most one active mutation attempt. Attempt/lease/fencing identity prevents two agents from healing the same scope concurrently. Lease expiry requires state reconciliation before a new attempt claims the mutation lane.

### 11.3 Attempt budget

Healing is finite. Policies define bounded attempts, same-plan retries, and replan/escalation thresholds. Infinite retry is forbidden.

Failure taxonomy includes:

```text
EXECUTION_FAILURE
VALIDATION_FAILURE
PRECONDITION_DRIFT
AUTHORITY_EXPIRED
PROVIDER_FAILURE
ROLLBACK_FAILURE
INCONCLUSIVE
```

Provider failure may permit rerouting without invalidating the plan. Validation failure normally requires re-diagnosis/replan.

### 11.4 Healer hard guards

A healer must never manufacture success by weakening the protection system. Forbidden defaults include:

- disabling a failing required test;
- bypassing required CI/review;
- lowering a security/governance policy;
- broadening its own authority;
- suppressing/closing a Finding without authority/evidence;
- disabling the sensor that detected the problem.

A proposed protection-bypass action is itself evidence for a new protection/governance Finding.

## 12. Rollback, verification, monitoring, recurrence

### 12.1 Rollback

FixPlan declares rollback class:

```text
AUTOMATIC
MANUAL
NOT_POSSIBLE
```

Rollback has explicit trigger conditions, checkpoint/evidence reference, and post-rollback verification. `ROLLBACK_FAILURE` is a high-severity escalation condition because the remediation increased uncertainty/blast radius.

### 12.2 Verification levels

**V1 Technical**

- required tests/validator pass;
- exact-SHA CI evidence when applicable.

**V2 Behavioral**

- original symptom/unsafe behavior is actually removed or contained.

**V3 Operational**

- required monitoring window completes without recurrence.

For high-risk H3/H4 work, mutation and verification should be independent actors/capabilities when policy requires.

Verification must include negative/regression checks so that a fix cannot pass only because the original path was disabled or protection weakened.

### 12.3 Monitoring window

Monitoring supports both time and event evidence:

```yaml
monitoring:
  minimum_duration: 24h
  minimum_observations: 20
  required_conditions:
    - original_fingerprint_absent
    - verification_signal_healthy
  reset_on:
    - recurrence
    - relevant_deployment
```

A HealingAttempt may be `SUCCEEDED` while the Finding remains `HEALED`/`MONITORING`.

### 12.4 Recurrence

Recurrence matching has three levels:

- exact fingerprint;
- behavioral recurrence;
- validated root-cause recurrence.

Semantic/root-cause recurrence requires review when confidence is insufficient. Recurrent failure reopens/re-diagnoses the stable Finding and reduces confidence in the previous Diagnosis/FixPlan; it does not merely increase severity or replay the same fix.

Repeated local recurrence may trigger architectural research. Similar recurrence across projects may trigger systemic investigation.

## 13. Health model

Health is multidimensional derived state, not a mutable boolean.

Dimensions:

```text
Delivery Health
Runtime Health
Security Health
Governance Health
Agent/Provider Health
Protection Health
Observability Health
```

Dimension states:

```text
HEALTHY
DEGRADED
AT_RISK
CRITICAL
UNKNOWN
```

Health, Exposure, and Protection Effectiveness remain separate axes.

Exposure states:

```text
UNEXPOSED
LIMITED
EXPOSED
WIDESPREAD
UNKNOWN
```

Protection effectiveness:

```text
EFFECTIVE
PARTIAL
DEGRADED
FAILED
UNKNOWN
```

Example:

```text
Health       CRITICAL
Exposure     LIMITED
Protection   EFFECTIVE
```

An active fence does not redefine an unhealthy system as healthy.

## 14. Shield self-protection

Project Shield state:

```text
FULL
DEGRADED
SAFE_MODE
OFFLINE
```

- **FULL** — all critical protection capabilities satisfy required health.
- **DEGRADED** — partial research/monitoring capabilities unavailable while core protections remain trustworthy.
- **SAFE_MODE** — confidence is insufficient for autonomous mutation; read-only research and existing protections may continue.
- **OFFLINE** — core invariants cannot be assured; the system must not claim Shield protection.

Minimum meta guards:

1. no silent critical-sensor death;
2. no silent A2A delivery loss;
3. no infinite healing loop;
4. no healer mutation of its own authority/fencing policy;
5. no protected effect without required durable audit/evidence;
6. no stale Controller continuation silently becoming terminal success.

Meta failures create normal canonical `SHIELD_DEGRADATION` observations/findings rather than using a hidden maintenance channel.

Global Supervisor has its own health model. If it fails, Project Shields continue locally; only new global correlation/fleet fencing becomes unavailable/degraded.

## 15. Shield A2A integration

Shield reuses `dw.taskcontroller.a2a/v1` and existing TaskController kinds:

```text
COMMAND
REPORT
REVIEW_REQUEST
CORRECTION
TERMINAL
HEALTH
```

No new A2A message kind is required for MVP.

Capability examples:

```text
shield.health.report
shield.research.execute
shield.finding.review
shield.finding.reconcile
shield.protection.apply
shield.protection.release
shield.healing.plan
shield.healing.execute
shield.healing.verify
shield.systemic.investigate
```

Example Global-to-Project directive:

```yaml
kind: COMMAND
request:
  capability: shield.protection.apply
artifact_refs:
  - shield://global/protections/PRT-009
```

Project reply:

```yaml
kind: REPORT
request:
  capability: shield.protection.ack
artifact_refs:
  - shield://gwc/protection-receipts/PRR-31
```

The A2A envelope continues to carry compact semantics and exact artifact references. Large Shield objects live as artifacts/canonical records.

Existing TaskController monotonic sequence, per-actor cursor, continuation checkpoint, exact readback, provider wake-up, and stale-sequence rules remain applicable. Shield directives/attempts additionally bind directive version, attempt/fencing identity, lease, and exact referenced state. A stale or superseded request may not mutate current state.

## 16. TaskController mapping

Shield workflow nodes use existing TaskController runtime states rather than creating Shield-specific kernel status enums.

Existing useful primitives include:

- `RunStatus`: `CREATED | PLANNED | RUNNING | PAUSED | BLOCKED | COMPLETED | FAILED | CANCELLED`;
- `NodeStatus`: `PENDING | READY | CLAIMED | RUNNING | REVIEWING | DONE | BLOCKED | FAILED | RETRY_READY | CANCELLED | LEASE_EXPIRED`;
- `ReviewVerdict`: `PASS | FAIL | NEEDS_FIX | NEEDS_CLARIFICATION`;
- `DecisionType`: `CONTINUE | WAIT | RETRY | REPLAN | CANCEL | COMPLETE | ESCALATE`.

Shield lifecycle vocabulary remains artifact/domain semantics layered over those generic orchestration states.

The first implementation should prefer typed Shield artifacts plus TaskController Run Ledger/audit references rather than changing the coordination kernel solely to encode Shield-specific lifecycle states.

## 17. Policy hierarchy

Policy inheritance:

```text
DW SUPER Global Policy
        ↓
Organization/Profile Policy
        ↓
Project Shield Policy
        ↓
Run Policy
```

Lower scopes may tighten inherited protection by default. Weakening a higher-level protection requires an explicit applicable authority path; it is never an implied project override.

Example project profile:

```yaml
shield:
  enabled: true
  mode: GUARDED

  watch:
    repository: true
    ci: true
    dependencies: true
    runtime: true
    governance: true

  research:
    capabilities:
      - research.repo
      - research.docs
      - research.web

  review_profile:
    - review.architecture
    - review.security
    - review.runtime

  healing:
    autonomous_max_level: H2
    standing_authority_max_level: H3

  protection:
    block_on:
      - CRITICAL
      - HIGH_SECURITY
      - AUTHORITY_DRIFT

  monitoring:
    recurrence_policy: project-defined
```

Modes may include:

```text
OBSERVE
ADVISORY
GUARDED
AUTONOMOUS (within explicit standing authority)
LOCKDOWN
```

Mode never creates authority beyond the applicable project/governance contract.

## 18. Human Control Plane and external projections

Slack should expose compact project/global Shield RootCards and semantic events, for example:

```text
PROJECT SHIELD · <project>
Shield          FULL
Health          DEGRADED
Exposure        LIMITED
Protection      EFFECTIVE
Critical sensors 12/12
Open findings     7
High findings     2
Active healing    1
Monitoring        3
Prevented effects 4
```

Global projection includes fleet/project counts, systemic findings, provider health, and protection ACK coverage.

Slack is not canonical state or audit storage. GitHub/Jira issue/task objects are work projections. Notion may carry long-lived architecture/research/management projections. Projection failure must not destroy the canonical Finding/Protection/Healing state; project policy decides whether failure is degraded or blocking for a particular effect.

## 19. Fleet heartbeat

Project Shield emits a normalized heartbeat suitable for Global correlation without streaming raw logs/prompts/source code:

```yaml
shield_heartbeat:
  project: gwc
  shield_state: FULL
  health:
    overall: DEGRADED
  critical_sensor_coverage: 1.0
  findings:
    critical: 0
    high: 2
  protections:
    effective: 1
    partial: 0
  healing:
    active: 1
  emitted_at: ...
```

Missing expected heartbeat is an Observation. It may become `PROJECT_SHIELD_UNREACHABLE` after policy threshold, but it does not by itself prove compromise.

## 20. Learning and policy proposals

Shield records healing/protection outcomes such as:

- finding type;
- diagnosis/fix strategy;
- executor/provider;
- attempt cost/duration;
- verified outcome;
- rollback;
- recurrence;
- protection effectiveness.

These data may generate routing recommendations or policy proposals. Learning does **not** silently rewrite authority, protection, or routing policy. Promotion is a reviewed decision with evidence.

## 21. Effectiveness metrics

Do not evaluate Shield by raw finding/alert count.

Core measures:

```text
MTTD — time to validated detection/finding
MTTC — time to containment
MTTR — time to verified remediation
recurrence rate
false-positive rate
healing verified-success rate
rollback rate
protection ACK coverage
critical sensor coverage
finding-to-evidence traceability
human intervention rate
autonomous-fix regression rate
Prevented Effect Count
```

`Prevented Effect Count` captures proactive value such as unsafe merges/deploys/agent effects stopped before execution.

## 22. Failure behavior

Examples of required behavior:

- non-critical sensor unavailable → Shield `DEGRADED`, continue unrelated work;
- critical authority/validation sensor unavailable → health `UNKNOWN/AT_RISK`, fail closed only for effects requiring that sensor;
- Global directive lacks ACK → `FENCING_UNKNOWN`, do not claim protection;
- repeated healing failure → replan/re-diagnose, consume finite attempt budget, then escalate;
- provider failure during a valid plan → may reroute provider if policy permits without silently changing plan scope;
- validation failure → invalidate/review plan assumptions;
- rollback failure → protection/escalation with increased risk;
- issue projection unavailable → canonical Finding remains intact; policy determines whether workflow degrades or blocks;
- Global Supervisor unavailable → Project Shields continue local protection and mark global correlation/fencing degraded.

## 23. Security and authority invariants

1. A2A envelopes, Slack buttons/messages, Executor completion, and previous chat approvals do not create merge/deploy/destructive authority.
2. `ACCEPTED_RISK` requires authority evidence.
3. H4 always requires explicit applicable authority.
4. A healer cannot broaden its own authority.
5. A protection directive cannot silently exceed its scoped target/action/lease.
6. Stale or superseded directive/attempt/sequence/digest cannot mutate current state.
7. Exact readback/ACK is required before a Global fence is considered applied.
8. A Project Shield may expose an exception/partial application but must never silently ignore a valid directive.
9. Loss of visibility is `UNKNOWN/AT_RISK`, not healthy.
10. Protected effect validation must be bound to exact applicable source/evidence where project governance requires it.

## 24. MVP architecture slice

MVP should prove the protection semantics with existing infrastructure rather than implement the entire vision at once.

### Slice A — Local observe/trigger foundation

- Project Shield profile/config;
- event/poll/meta sensor interfaces;
- immutable Observation representation;
- append-only observation persistence via existing artifact/audit facilities where practical;
- fingerprint/dedupe/noise-control primitives;
- Trigger Engine with direct/threshold/persistence/absence/sequence policies;
- sensor health and selective fail-closed semantics.

### Slice B — Research/finding loop

- capability-based research fan-out/join;
- frozen ResearchArtifact digest;
- configurable independent review profile;
- SignalCluster/FindingCandidate/Finding artifacts;
- evidence status/claim mapping;
- deterministic reconciliation and projection references;
- first project RootCard projection.

### Slice C — Guarded remediation

- DiagnosisArtifact and FixPlan;
- healing levels H0-H3 semantics;
- one active mutation attempt with lease/preconditions;
- finite attempt budget/failure taxonomy;
- verification artifact and monitoring state;
- no H4 autonomous effect.

### Slice D — Hybrid Global Supervisor

- Shield Registry;
- normalized heartbeats;
- global correlation/systemic candidate/finding;
- scoped emergency fencing `WARN/DENY_NEW_EXECUTION/PAUSE/QUARANTINE`;
- exact ACK/partial/failed receipts;
- lease/renew/downgrade/release;
- no direct project remediation.

### Slice E — Health/self-protection/effectiveness

- multidimensional HealthSnapshot;
- Exposure/Protection axes;
- meta sensors/findings;
- `FULL/DEGRADED/SAFE_MODE/OFFLINE`;
- recurrence loop;
- prevention/healing/coverage metrics;
- Global fleet health projection.

The MVP does not require Kafka, NATS, Temporal, a new workflow engine, or a new distributed database. Those are future implementation options only if proven operational requirements exceed current TaskController/reference-binding capabilities.

## 25. Non-goals

This design does not authorize or require:

- a monolithic autonomous Shield Agent;
- replacement of TaskController;
- a new A2A protocol version solely for Shield;
- Kafka/MSK/NATS/Temporal in the MVP;
- a global agent with unrestricted project write authority;
- automatic merge/deploy/destructive changes;
- AI-controlled authority-policy mutation;
- Jira or Slack as canonical Finding Store;
- automatic closure of Findings because a ticket is Done or a CI run is green;
- hard-coded 4-lens review inside TaskController kernel;
- raw log/chat/prompt replication into Global Shield;
- replay of full Slack/GPT history for recovery.

## 26. Acceptance criteria for architecture implementation

An eventual implementation of this design is acceptable only when it demonstrates the following end-to-end properties:

1. **Traceability:** research question → exact evidence → frozen claim → independent review → canonical Finding → FixPlan → HealingAttempt → verification/monitoring is bidirectionally traceable.
2. **Determinism:** duplicate/stale observations/directives/attempts cannot create duplicate or stale effects.
3. **Authority isolation:** Global Shield can fence but cannot directly heal project code/state beyond explicitly owned global assets.
4. **Local survivability:** Project Shield protection continues when Global Supervisor is unavailable.
5. **No false health:** critical sensor/protection uncertainty is represented as `UNKNOWN/AT_RISK`, not `HEALTHY`.
6. **Exact fencing:** Global protection is considered effective only after scoped Project Shield ACK/readback.
7. **Finite healing:** healing cannot retry indefinitely and cannot weaken its own guards to pass.
8. **Independent verification:** policy can require a verifier distinct from the mutating executor.
9. **Closure discipline:** successful execution/CI/ticket completion cannot close a Finding without required verification/monitoring.
10. **Systemic correlation:** a Systemic Finding can reference multiple local findings while preserving local ownership/evidence.
11. **Transport neutrality:** Shield semantics work through TaskController A2A/reference contracts without Slack/product coupling.
12. **Recovery:** Controller/Shield run recovery does not require replaying prior GPT/Slack conversations.
13. **Protection value:** the system can record and explain at least one prevented unsafe effect, not merely generate alerts.

## 27. Approved architecture decisions

### ADR-SHIELD-001 — Hybrid architecture
Each project owns an independent Project Shield; a Global Shield Supervisor provides cross-project correlation and fleet protection.

### ADR-SHIELD-002 — Global Emergency Fencing
Global Shield may issue policy-bound reversible emergency fences.

### ADR-SHIELD-003 — Local Remediation Authority
Project Shield retains local diagnosis/healing authority; Global Shield does not directly remediate project code/state.

### ADR-SHIELD-004 — Finding is canonical
Jira/GitHub issues are projections of canonical Shield Findings.

### ADR-SHIELD-005 — Protection requires lease and exact acknowledgement
A fence is not considered applied without scoped receipt/readback; protection is leased unless policy requires human release.

### ADR-SHIELD-006 — Sensors are evidence producers
Sensors emit observations; they do not assign canonical Finding conclusions.

### ADR-SHIELD-007 — Observations are immutable and append-only
New evidence creates new observations rather than mutating history.

### ADR-SHIELD-008 — Trigger Engine supports rich temporal/correlation semantics
Threshold, correlation, persistence, absence, and sequence rules are first-class.

### ADR-SHIELD-009 — Evidence-first protection by default
Only explicit hard-guard policies may protect-first/diagnose-second.

### ADR-SHIELD-010 — Selective fail-closed
Critical protection capability loss blocks affected protected effects without unnecessarily freezing unrelated/read-only work.

### ADR-SHIELD-011 — SignalCluster/FindingCandidate are pre-canonical
Only validated Findings enter canonical Finding state.

### ADR-SHIELD-012 — Stable versioned Finding identity
Finding identity does not follow ticket IDs, severity revisions, or recurrence events.

### ADR-SHIELD-013 — Severity, confidence, and remediation priority are separate
They must not be collapsed into one risk score.

### ADR-SHIELD-014 — Systemic Finding references local Findings
Systemic correlation does not transfer/collapse local evidence ownership.

### ADR-SHIELD-015 — Conflicts require evidence reconciliation
Reviewer disagreement is not resolved by majority vote.

### ADR-SHIELD-016 — External issue completion does not close Finding
Jira/GitHub workflow is projection-only for canonical lifecycle.

### ADR-SHIELD-017 — Diagnosis, FixPlan, and HealingAttempt are separate
Reasoning, intended change, and actual execution have separate identities/evidence.

### ADR-SHIELD-018 — Healing authority is level-bounded
Projects define autonomous maximum; H4 always requires explicit applicable authority.

### ADR-SHIELD-019 — One active mutation attempt per Finding by default
Attempt lease, exact preconditions, and stale fencing prevent concurrent/superseded healing effects.

### ADR-SHIELD-020 — Healing has finite attempt budget
Repeated failure forces replan/re-diagnosis/escalation rather than infinite retry.

### ADR-SHIELD-021 — Healer cannot weaken protection to succeed
Tests, sensors, security, governance, and authority controls cannot be disabled/bypassed as remediation success criteria.

### ADR-SHIELD-022 — Successful HealingAttempt is not closure
Finding closure requires policy-defined verification and monitoring.

### ADR-SHIELD-023 — Protection release is an explicit evidence-backed decision
Release/downgrade/renew is not a side effect of a successful fix.

### ADR-SHIELD-024 — Health is derived and multidimensional
`UNKNOWN` is canonical; loss of visibility is never inferred healthy.

### ADR-SHIELD-025 — Health, Exposure, and Protection effectiveness are separate axes
Containment does not redefine underlying system health.

### ADR-SHIELD-026 — Monitoring supports time and event evidence
Closure may require both duration and sufficient relevant observations.

### ADR-SHIELD-027 — Recurrence reopens/re-diagnoses the stable Finding
It reduces confidence in previous diagnosis/fix assumptions rather than blindly replaying the fix.

### ADR-SHIELD-028 — Shield self-monitors
Project Shield has `FULL | DEGRADED | SAFE_MODE | OFFLINE` and meta sensors/findings.

### ADR-SHIELD-029 — Global failure does not disable local protection
Hybrid architecture provides failure isolation by construction.

### ADR-SHIELD-030 — Effectiveness measures prevention and verified outcomes
Alert/finding volume is not a success metric; prevention, validated remediation, recurrence, coverage, and regression are.

## 28. Design handoff boundary

This document records the approved architecture direction only.

It does **not** grant implementation, merge, deployment, destructive-operation, or production authority. The next allowed design-process step after human review of this written spec is to create a separate implementation plan. Any subsequent governed repository execution must bind exact source/authority/CI evidence required by that project and effect.
