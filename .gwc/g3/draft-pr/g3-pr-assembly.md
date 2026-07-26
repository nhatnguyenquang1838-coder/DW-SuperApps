# G3.1 PR Assembly — SCRUM-105

> SUPERSEDED: this assembly predates the G2 repair and must not be used for G3/G4 approval.

## Repository
- Repository: DW-SuperApps
- Base ref: main
- Base SHA (origin/main): 8cf13d7d6bef535bff77e36815b737aff9d7f709
- Guarded branch: marmalade-beanie (protected: no direct push to main)
- Superseded review head SHA: c3418e85388e2a24c2730e1bea43be9c0db99383
- Scope hash: 839f04638ba15dca6a1b4d901cae5ee2b6b6f1c4 (from G1 decision)

## Changed Paths
All changes are additive, under `.gwc/`:
- `.gwc/g0/context-snapshot.yaml` — G0 context
- `.gwc/g1/intake/g1-intake-brief.yaml` — G1 intake
- `.gwc/g1/brainstorming/g1-options.yaml` — G1 options
- `.gwc/g1/preflight/g1-preflight-report.yaml` — G1 preflight
- `.gwc/g1/decision/g1-decision-record.yaml` — G1 decision
- `.gwc/g2/execution/g2-execution-record.yaml` — G2 execution record
- `.gwc/g3/draft-pr/g3-delivery-record.yaml` — superseded G3 delivery record
- `.gwc/g3/draft-pr/g3-independent-review.md` — superseded independent review
- `.gwc/g3/draft-pr/g3-pr-assembly.md` — superseded assembly
- `.gwc/g3/draft-pr/g3-review-closure.md` — superseded review closure
- `.gwc/scrums/SCRUM-105/design.md` — Design document
- `.gwc/scrums/SCRUM-105/schemas/runtime-event.schema.json`
- `.gwc/scrums/SCRUM-105/schemas/checkpoint.schema.json`
- `.gwc/scrums/SCRUM-105/schemas/store-api.schema.json`
- `.gwc/scrums/SCRUM-105/schemas/pending-action-readback.schema.json`
- `.gwc/scrums/SCRUM-105/contracts/store-api.md`
- `.gwc/scrums/SCRUM-105/contracts/cas-lease-fencing.md`
- `.gwc/scrums/SCRUM-105/contracts/node-adapter.md`
- `.gwc/scrums/SCRUM-105/migration/README.md`

## Validation
CI status: REVALIDATION_REQUIRED after G2 repair
G3 delivery validation tool: `tools/validate_g3_delivery.py` not present in worktree — manual validation applied.

## Acceptance Criteria Verification (per G1 intake AC-1 through AC-9)
| AC | Criterion | Status |
|----|-----------|--------|
| AC-1 | All schemas validate against JSON Schema draft 2020-12 | PASS — schema files use `$schema` draft 2020-12, `additionalProperties: false`, and proper `required` arrays |
| AC-2 | Store API operations satisfy success/error/timeout contract | PASS — store-api.md documents all 11 operations with request/response envelopes and error codes |
| AC-3 | CAS rejects stale writes with 409 Conflict | PASS — cas-lease-fencing.md and store-api.md specify 409 for CAS mismatch |
| AC-4 | Leases expire after TTL and release exclusive access | PASS — lease lifecycle documented with EXPIRED transition |
| AC-5 | Fencing tokens monotonically increase and reject stale writes | PASS — fencing doc specifies monotonically increasing tokens and 403 for stale |
| AC-6 | Pending actions follow defined state machine | PASS — pending-action-readback.schema.json defines PENDING→CLAIMED→EXECUTING→COMPLETED|FAILED |
| AC-7 | Adapter contract handshake completes before store operations | PASS — node-adapter.md mandates handshake first, with rules and retry policy |
| AC-8 | Migration design defines extract, transform, load, verify, cutover and rollback invariants | DESIGN-ONLY — execution is a separate implementation task |
| AC-9 | Verification design defines row counts and checksums readback | DESIGN-ONLY — execution is a separate implementation task |

## Exclusions
- No G4_MERGE authority (GWC governance boundary)
- No G5_DEPLOY authority
- No G6_PRODUCTION_DATA authority
- No production configuration changes
- No database provisioning
- No migration execution (design only)

## Head SHA Stability
This record is superseded. A fresh G3 review must bind to the exact post-repair PR head and current CI readback.
