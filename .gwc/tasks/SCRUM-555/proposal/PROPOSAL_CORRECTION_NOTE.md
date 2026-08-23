# Proposal Evidence Correction Note — DW-OBS-G6-READINESS-R1

## Superseded artifacts
The `change-plan.yaml` and `written-proposal.md` committed in `d1f547f` (CORRECTION) and
carried into `27d0dac` / `41fd059` still described the **pre-Correction-3** scope:
- TWO new migrations (`...100000Z_projection_events.sql` + `...100500Z_projection_events_broadcast_rls.sql`)
- unapproved `src/observatory/*.ts` production module paths
- `risk_class: R4`

These were **stale relative to the Human-approved G2 envelope** (Correction-3, scope hash
`sha256:3fabfceb591e95c552685245f9bf49576cd356bfc712a5738f2401311b4286d3`), which the
Controller accepted at G2 STRUCTURAL REVIEW = PASS / HUMAN AUTHORITY REQUIRED.

## This repair (commit on working branch only, no push)
Updates `change-plan.yaml` + `written-proposal.md` to match the **already-approved**
Correction-3 scope exactly:
- risk class R3 (R4 concern recorded as narrative `risk_note` only)
- exactly ONE new migration `20260823T100000Z_projection_events.sql`
- `lib/serverRunRead.ts` + two run pages + final `G6_PACKET.md`
- RED tests `supabaseMigrationContract.test.ts` and `serverRunRead.test.ts`
- NO `src/observatory/*`, NO second migration, NO remote Supabase apply

## Frozen (NOT modified)
`g2/scope_inputs.json`, `g2/execution-envelope.yaml`, `g2/scope_hash.txt`, and the
approved scope hash `sha256:3fabfceb…` are byte-identical before and after this repair
(see commit diff: only proposal/ files changed). G2 authority remains valid; no new token required.
