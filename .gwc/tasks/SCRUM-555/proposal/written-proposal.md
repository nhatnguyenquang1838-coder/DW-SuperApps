# DW-OBS-G6-READINESS-R1 — Written Proposal

**Run:** DW-OBS-G6-READINESS-R1 · **Task:** SCRUM-555 (DW Run Observatory)
**Repository:** nhatnguyenquang1838-coder/DW-SuperApps
**Base:** pre-prod@0ee1b41b33ca83242d02c2098e6ef96a7c510301
**Branch:** auto/SCRUM-555-observatory-g6-readiness-r1
**Goal:** Make DW Observatory real Supabase mode deployable BEFORE any G6 remote apply.

## Scope
Add a canonical live event ledger (`projection_events`) and read-only publishable-key
access to the existing Observatory, WITHOUT fabricating historical event evidence.
Dual-store: `run_*` audit metadata (read by UI for run metadata/gates/nodes) +
`projection_events` canonical ledger (read by timeline/replay/live). A reconstructed
historical run with zero canonical events surfaces `PROJECTION_UNAVAILABLE`, never fixture LIVE.

## Architecture
1. `run_*` = historical/audit metadata + reconstructed evidence; never synthesize missing canonical events.
2. `projection_events` = canonical live event ledger for real-mode + Realtime.
3. Real UI reads run metadata/gates/nodes from `run_*`; timeline/replay/live reads `projection_events`.
4. Reconstructed run with zero canonical events → `PROJECTION_UNAVAILABLE` / history unavailable.
5. Exactly ONE new migration for `projection_events`, broadcast trigger + hardened SELECT-only RLS for publishable client; no client write. No new `src/observatory/*` module layer.

## Stack
Next.js / TypeScript / Vitest / Supabase / Postgres. No new npm dependencies.

## Global constraints (hard)
- No remote apply; no GWC mutation; no deploy; no service-role fallback; no invented events/ordering.
- Branch targets `pre-prod`. Remote Supabase READ-ONLY (G6 STOP).
- Excluded lanes: SCRUM-554, Project Shield, SCRUM-288/NA81, Rental Home, global Power compat repair.

## Deliverables (TDD, docs first)
- Docs: `docs/superpowers/specs/2026-08-23-observatory-g6-readiness-design.md`, `.../plans/...`
- Exactly ONE new migration `20260823T100000Z_projection_events.sql` (projection_events + broadcast trigger + SELECT-only RLS)
- Adapter `lib/serverRunRead.ts`; UI `app/runs/page.tsx`, `app/runs/[runId]/page.tsx`
- Contract tests (RED then GREEN):
  - `tests/unit/supabaseMigrationContract.test.ts` (migration contract)
  - `tests/unit/serverRunRead.test.ts` (real run metadata adapter)
- Refresh `G6_PACKET.md` after code stabilizes.

## Acceptance
AC-1 migration cols/indexes/trigger/SELECT-only RLS; old 8-table DDL/DML hashes unchanged
(DDL ef880051…, DML 5bcee0d6…).
AC-2 real-mode reads run_* via publishable key, no mutation, exact mapping.
AC-3 zero-event reconstructed run → PROJECTION_UNAVAILABLE, never fixture LIVE.
AC-4 full Vitest + strict typecheck + SQL contract test pass; no old migration hash drift.

## Risk
Gate class **R3**. Operational concern remains R4-grade (new SELECT-only RLS + observer read path
touching production Supabase schema); recorded as narrative only, not a gate class.
