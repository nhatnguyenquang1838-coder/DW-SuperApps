# SCRUM-555 · DW-OBS-G6-READINESS-R1 · G6 APPROVAL PACKET (REFRESHED)

**STOP — human authority required before any remote apply.** G6 not started; actual apply remains G6-forbidden.

## Target
- Supabase project ref: `auswvdxoetufwiaxutib`, schema `public`.
- Current remote truth (pre-G6): ACTIVE_HEALTHY, `migrations=[]`, `public tables=[]`
  (no fresh read-only evidence to the contrary; remote apply NEVER performed).
- Expected post-apply schema = **9 public tables** including `projection_events`.

## Migrations (3, all committed under `supabase/migrations/`, G6-gated; git-blob SHA-256)
|| # | Migration | SHA-256 (git-blob/LF) |
|---|---|---|x
| 1 | `20260823T080000Z_observatory_history.sql` (DDL, 8 tables) | `ef880051d8fb7caf40005206d1200c3824509f8084ec771324866ee29500e185` |
| 2 | `20260823T090000Z_observatory_backfill_dml.sql` (DML, idempotent) | `5bcee0d6ea6a34b0b8cef91ff5a860ff2289a0f23ff9386a92105ee62aff23df` |
| 3 | `20260823T100000Z_projection_events.sql` (projection_events) | `99ecc412c24ef30715ee7546073b546e05052ff60debbd7286d035b4aed87831` |

## Expected post-apply schema (9 public tables)
`runs`, `run_events`, `run_gates`, `run_nodes`, `run_artifacts`, `run_checkpoints`, `run_edges`, `run_sources`, `projection_events`.

## Historical counts (unchanged, from committed DML — deterministic)
```
runs=4, run_events=0, run_gates=3, run_nodes=3, run_artifacts=17,
run_checkpoints=0, run_edges=0, run_sources=23
projection_events=0 (before live writes; no historical projection backfill)
```

## projection_events contract (migration 3) — TERRAFORMED for E2E GREEN
- Table `projection_events` — canonical live event ledger.
- Unique canonical identity `(run_id, source_system, source_event_id)`.
- Durable `projection_ordinal` (`BIGINT NOT NULL`, NO DEFAULT) + required indexes:
  `idx_projection_events_run_ordinal (run_id, projection_ordinal)`,
  `idx_projection_events_occurred (occurred_at)`.
- `notify_projection_event()` + AFTER INSERT trigger `trg_projection_events_after_insert`.
- Broadcast via `PERFORM realtime.send(json_build_object(...)::text, 'projection_event', 'observatory:' || NEW.run_id, false)` — NOT pg_notify.
- RLS enabled; SELECT-only policy `projection_events_select_publishable ON projection_events FOR SELECT TO anon, authenticated USING (true)`.
- NO client INSERT/UPDATE/DELETE policy; NO historical projection backfill.
- Authorization: Human G2 V2 CONSUMED (`ar-scrum-555-g2-correction-v2-20260824 / 5a3a480bd37fdd7b`).

## Real app read path (Task 3, publishable/RLS-compatible) — TERRAFORMED for E2E GREEN
- `lib/serverRunRead.ts`: real list/detail read `runs`, `run_gates`, `run_nodes`,
  `projection_events` via PUBLISHABLE (anon) key boundary.
- NO service-role implicit fallback (config missing → degraded, not escalate).
- NO fixture fallback in real mode; degraded/RLS denial → explicit
  `PROJECTION_UNAVAILABLE`.
- Reconstructed historical run + zero `projection_events` →
  `canonicalHistoryAvailable=false` / `PROJECTION_UNAVAILABLE`; never synthesize
  canonical events.
- Stored metadata mapping: `branch`, `pr` (from `pr_number`), `exactHead` (from
  `head_sha`), `ci` (from `ci_status`) surfaced exactly when present; explicit
  UNKNOWN when absent — never fabricated.
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

## Lifecycle (current, at refresh — GREEN terminal)
- Execution baseline: `70ddd1c` (resume); Task 2 GREEN frozen; Task 3 GREEN
  accepted; Task 4 (this packet) refreshed.
- Current HEAD: `cb972da4325cbee36969f058a0a070aaabe87b17` (post GREEN-1 + GREEN-2 + governance).
- Migration SHA256 (LF): `99ecc412c24ef30715ee7546073b546e05052ff60debbd7286d035b4aed87831`.
- Verification evidence: serverRunRead 6/6, migration contract 16/16, full
  vitest 257/257 (16 files), `tsc --noEmit` 0 errors; frozen Task-2 hashes
  unchanged (DDL `ef880051…`, DML `5bcee0d6…`); CI `CI_UNAVAILABLE_AT_CHECK` (branch unpushed).
- Lifecycle status: **pre-push, pre-G3, pre-G4, pre-G6 — E2E terminal PASS locally**.

## Exclusions
- No remote Supabase apply (G6 boundary). No pre-prod→main, no deploy, no GWC
  mutation, no force-push/rewrite, no push/PR until Controller readback.
