# DW Project Shield MVP — SDD Design

## Source architecture
This SDD projects PR #69 (`ADR-SHIELD-001..044`) into implementation boundaries; it does not supersede the three architecture documents.

## Package boundary
Shield is a sibling product/module layer that composes existing `taskcontroller/` contracts. SHD-001 must verify the final new package root against repository conventions before source creation; subsequent tasks must consume that decision rather than hard-code an unverified path.

## Components
1. Shield domain/serialization: Observation, Finding, Protection, Diagnosis, FixPlan, HealingAttempt, HealthSnapshot, identifiers/digests.
2. Sensor/Observation + Trigger/Finding services.
3. TaskController workflow adapter for bounded research/review/diagnosis/heal/verify runs.
4. Protection/authority adapter and assurance/readback.
5. Healing/verification/monitoring/recurrence.
6. Persistence adapter: SQLite atomic outbox → provider-neutral PostgreSQL replica.
7. Mutation safety: writer epoch/fencing + EffectIntent/EffectReceipt reconciliation.
8. Self-review + telemetry/ExperienceRecord/eval foundation.
9. Global registry/heartbeat/systemic correlation/fencing.
10. Projection adapters and pilot/runbooks.

## Verified integration anchors at bound head
`taskcontroller/domain/**`, `taskcontroller/audit/**`, `taskcontroller/kernel/**`, `taskcontroller/interaction/**`, `taskcontroller/execution/**`, `taskcontroller/runtime/**`, `taskcontroller/projections/**`, `tests/taskcontroller/**`, `.github/workflows/taskcontroller-validation.yml`.

## Runtime sequence
Event/Poll/Schedule/Human/Global trigger → local Trigger evaluation → bounded TaskController Run for material work → exact evidence/readback → optional protection/healing under authority → verification/monitoring → audit/health/learning projection.

## Persistence sequence
Local transaction writes audit event + outbox → idempotent PostgreSQL sync/readback. Shared durability gates cross-host mutation ownership/protected EffectIntent according to policy.

## Safety invariants
No implicit authority; no stale writer mutation; no blind effect retry; no finding closure from issue status/execution success; no self-weakening healer; no raw CoT dependency; critical sensor loss becomes UNKNOWN/AT_RISK; Global failure does not disable local Shield.

## Test strategy
Use deterministic unit/contract tests first. Extend `tests/taskcontroller/**` for reused seam contracts and add Shield-owned tests at the package root chosen by SHD-001. Authoritative existing TaskController CI command is `PYTHONPATH=. pytest tests/taskcontroller/`; implementation planning must add Shield tests to an appropriate CI path without weakening existing coverage.
