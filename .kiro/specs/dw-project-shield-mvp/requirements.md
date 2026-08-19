# DW Project Shield MVP — Requirements

Status: SPEC-DRIVEN PLANNING ONLY. Implementation authority is not granted by this file.
Bound architecture: PR #69 at `1bf75ba68beaa140bc8cd2b19a9da39f3a99b90e`.
Target pilot window: 19 Aug 2026 — 18 Nov 2026.

## Objective
Deliver a pilot-ready Project Shield from zero Shield implementation while reusing TaskController/GWC boundaries and preserving local authority, evidence-first action, durable recovery, bounded self-healing and Global correlation/fencing semantics.

## Requirements
- **SHIELD-REQ-001 — Modular runtime.** Shield SHALL remain a replaceable DW-SuperApps module and SHALL reuse TaskController for bounded runs, A2A, continuation, execution and audit rather than duplicating the kernel.
- **SHIELD-REQ-002 — Immutable observations.** Sensors SHALL emit append-only Observations with exact subject/source/fingerprint/freshness/evidence references; later signals SHALL NOT mutate prior observations.
- **SHIELD-REQ-003 — Trigger policy.** Trigger Engine SHALL support direct, threshold, correlation, persistence, absence and sequence semantics plus dedupe/debounce/cooldown/suppression without directly performing arbitrary fixes.
- **SHIELD-REQ-004 — Evidence-backed findings.** SignalCluster/FindingCandidate SHALL be pre-canonical; only evidence-validated/reconciled Findings enter canonical Finding state. Conflicts SHALL produce further research/review rather than majority vote.
- **SHIELD-REQ-005 — Protection contract.** Protection SHALL use scoped directives, leases, explicit expiry behavior, exact receipt/readback and assurance class; unacknowledged protection SHALL NOT be reported as effective.
- **SHIELD-REQ-006 — Authority isolation.** Shield policy/config SHALL bound capability but SHALL NOT create execution/merge/deploy/production authority. Governed effects SHALL bind actual GWC scope/approval/readback evidence where applicable.
- **SHIELD-REQ-007 — Bounded healing.** Diagnosis, FixPlan and HealingAttempt SHALL be separate; H0-H2 may operate within standing policy, H3 is governed engineering change, H4 requires explicit applicable authority. Finite attempt/replan/revert budgets are mandatory.
- **SHIELD-REQ-008 — Verification and recurrence.** Successful execution SHALL NOT close a Finding. Technical, behavioral and policy-required operational monitoring SHALL determine HEALED/MONITORING/CLOSED or RECURRENT.
- **SHIELD-REQ-009 — Local/shared durability.** MVP SHALL preserve local SQLite audit and add atomic outbox + idempotent shared PostgreSQL replication with explicit LOCAL_DURABLE/SHARED_DURABLE assurance.
- **SHIELD-REQ-010 — Single writer fencing.** Mutation-bearing runs SHALL require current writer epoch/lease/fencing token before protected mutation; stale writers SHALL fail closed.
- **SHIELD-REQ-011 — Effect recovery.** Protected mutation SHALL use EffectIntent → Effect → EffectReceipt. Intent-without-receipt recovery SHALL reconcile provider state and SHALL NOT blindly repeat the effect.
- **SHIELD-REQ-012 — Scheduled self-review.** POST_RUN/project review SHALL be normal bounded TaskController runs triggered by schedule/event signals with recursion guard, idempotency key and finite review budget.
- **SHIELD-REQ-013 — Telemetry boundary.** Logs/metrics/traces MAY be OpenTelemetry-compatible derivatives correlated to TaskController IDs; telemetry SHALL NOT replace Run Ledger audit truth or require chain-of-thought/raw prompt storage.
- **SHIELD-REQ-014 — Learning safety.** ExperienceRecords/eval datasets SHALL be curated/redacted/provenance-bound, split TRAIN/DEVELOPMENT/HOLDOUT, and SHALL NOT enable uncontrolled online self-training or self-authorized policy weakening.
- **SHIELD-REQ-015 — Health semantics.** Health, Exposure and Protection effectiveness SHALL be separately derived. UNKNOWN is first-class; loss of visibility SHALL NOT imply HEALTHY.
- **SHIELD-REQ-016 — Hybrid Global Shield.** Each project SHALL retain local Shield authority. Global Shield MAY correlate and issue policy-authorized fencing but SHALL NOT directly edit local code/merge/deploy/heal.
- **SHIELD-REQ-017 — Selective fail-closed.** Loss of critical assurance SHALL block only effects requiring it while policy-permitted read-only observation/research/diagnosis may continue.
- **SHIELD-REQ-018 — Projection boundaries.** Slack/Notion/Jira/GitHub SHALL remain human/work/evidence projections and SHALL NOT define canonical Finding/authority/audit truth.
- **SHIELD-REQ-019 — Exact evidence.** Protected decisions, reviews, recovery and status claims SHALL bind exact stable IDs/versions/digests/SHA/evidence refs and reject stale/conflicting state.
- **SHIELD-REQ-020 — Pilot acceptance.** MVP SHALL prove local Observe→Finding→Protect/Plan→bounded Heal→Verify/Monitor, distributed recovery, scheduled self-review and a bounded two-project Global correlation/fencing scenario with adversarial negative tests.

## Non-goals for 90 days
Online self-training; fine-tuning/RL; adaptive ML routing; autonomous H4; mandatory Kafka/Temporal/NATS; full multi-region HA; dependence on Slack/Hermes/one provider.
