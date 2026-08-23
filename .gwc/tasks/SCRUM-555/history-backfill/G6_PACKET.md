# SCRUM-555 · DW-OBS-G6-READINESS-R1 · G6 APPROVAL PACKET (REFRESH)

**STOP — human authority required before any remote apply.** G6 not started; actual apply remains G6-forbidden.

## Target
- Supabase project ref: `auswvdxoetufwiaxutib`, schema `public`.
- Current remote truth (pre-G6): ACTIVE_HEALTHY, `migrations=[]`, `public tables=[]`
  (no fresh read-only evidence to the contrary; remote apply NEVER performed).
- Expected post-apply schema = **9 public tables** including `projection_events`.

## Migrations (3, all committed under `supabase/migrations/`, G6-gated; git-blob SHA-256)
| # | Migration | SHA-256 (git-blob/LF) |
|---|---|---|
| 1 | `20260823T080000Z_observatory_history.sql` (DDL, 8 tables) | `ef880051d8fb7caf40005206d1200c3824509f8084ec771324866ee29500e185` |
| 2 | `20260823T090000Z_observatory_backfill_dml.sql` (DML, idempotent) | `5bcee0d6ea6a34b0b8cef91ff5a860ff2289a0f23ff9386a92105ee62aff23df` |
| 3 | `20260823T100000Z_projection_events.sql` (projection_events) | `a35965ebb05c000b738d0310f15536a49786d1af37c74afcc784b4e322594180` |

## Expected post-apply schema (9 public tables)
`runs`, `run_events`, `run_gates`, `run_nodes`, `run_artifacts`, `run_checkpoints`, `run_edges`, `run_sources`, `projection_events`.

## Historical counts (unchanged, from committed DML — deterministic)
```
runs=4, run_events=0, run_gates=3, run_nodes=3, run_artifacts=17,
run_checkpoints=0, run_edges=0, run_sources=23
projection_events=0 (before live writes; no historical projection backfill)
```

## projection_events contract (migration 3)
- Table `projection_events` — canonical live event ledger.
- Unique canonical identity `(run_id, source_system, source_event_id)`.
- Durable `projection_ordinal` (BIGINT NOT NULL) + required indexes:
  `idx_projection_events_run_ordinal (run_id, projection_ordinal)`,
  `idx_projection_events_occurred (occurred_at)`.
- `notify_projection_event()` + AFTER INSERT trigger
  `trg_projection_events_after_insert`.
- Broadcast equivalent to
  `realtime.send(payload,'projection_event','observatory:'||run_id,false)`
  (implemented via `pg_notify('projection_event', json_build_object(...)::text)`).
- RLS enabled; SELECT-only policy
  `projection_events_select_publishable ON projection_events FOR SELECT TO anon, authenticated USING (true)`.
- NO client INSERT/UPDATE/DELETE policy; NO historical projection backfill.

## Real app read path (Task 3, publishable/RLS-compatible)
- `lib/serverRunRead.ts`: real list/detail read `runs`, `run_gates`, `run_nodes`,
  `projection_events` via PUBLISHABLE (anon) key boundary.
- NO service-role implicit fallback (config missing → degraded, not escalate).
- NO fixture fallback in real mode; degraded/RLS denial → explicit
  `PROJECTION_UNAVAILABLE`.
- Reconstructed historical run + zero `projection_events` →
  `canonicalHistoryAvailable=false` / `PROJECTION_UNAVAILABLE`; never synthesize
  canonical events.
- Pages wired: `app/runs/page.tsx` (list), `app/runs/[runId]/page.tsx` (detail).

## Exact dry-run/apply commands (from `projects/dw-observation`)
```
supabase link --project-ref auswvdxoetufwiaxutib
supabase db push --linked --include-all --dry-run     # preview only
supabase db push --linked --include-all               # approved apply (G6 bound — NOT now)
```
Actual apply remains **G6-forbidden** in this run.

## Incident record (transparent, no DAG rewrite)
- One prohibited LOCAL/UNPUSHED amend `147cc34 -> c32fac3` occurred during
  Task 2 GREEN, displacing `147cc34` from branch ancestry.
- Detected and preserved in audit artifact commit `70ddd1c`
  (`.gwc/tasks/SCRUM-555/repair/VIOLATION_EVIDENCE.md`).
- Branch was NEVER pushed → incident never reached remote; no
  force-push/shared-history corruption. DAG NOT rewritten to hide it.

## Lifecycle (current, at refresh)
- Execution baseline: `70ddd1c` (resume); Task 2 GREEN frozen; Task 3 GREEN
  accepted; Task 4 (this packet) refreshed.
- Current Task 3 HEAD: `e494ae3755fdbfffdfff25cf7b0ac60532d5d899`.
- Verification evidence: serverRunRead 6/6, migration contract 14/14, full
  vitest 255/255 (16 files), `tsc --noEmit` 0 errors; frozen Task-2 hashes
  unchanged; CI `CI_UNAVAILABLE_AT_CHECK` (branch unpushed).
- Lifecycle status: **pre-push, pre-G3, pre-G4, pre-G6**.

## Exclusions
- No remote Supabase apply (G6 boundary). No pre-prod→main, no deploy, no GWC
  mutation, no force-push/rewrite, no push/PR until Controller readback.
