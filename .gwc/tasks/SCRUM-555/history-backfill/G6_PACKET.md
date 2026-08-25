# SCRUM-555 · DW-OBS-G6-READINESS-R1 · G6 APPROVAL PACKET (REFRESHED)

**STOP — human authority required before any remote apply.** G6 not started; actual apply remains G6-forbidden.

## Target
- Supabase project ref: `auswvdxoetufwiaxutib`, schema `public`.
- Current remote truth (pre-G6): ACTIVE_HEALTHY, `migrations=[]`, `public tables=[]`
  (no fresh read-only evidence to the contrary; remote apply NEVER performed).
- Expected post-apply schema = **9 public tables** including `projection_events`.

## Migrations (3, all committed under `supabase/migrations/`, G6-gated; git-blob SHA-256)
| # | Migration | SHA-256 (git-blob/LF) |
|---|-----------|-----------------------|
| 1 | `20260823T080000Z_observatory_history.sql` (DDL, 8 tables) | `ef880051d8fb7caf40005206d1200c3824509f8084ec771324866ee29500e185` |
| 2 | `20260823T090000Z_observatory_backfill_dml.sql` (DML, idempotent) | `5bcee0d6ea6a34b0b8cef91ff5a860ff2289a0f23ff9386a92105ee62aff23df` |
|| 3 | `20260823T100000Z_projection_events.sql` (projection_events) | `D79F7811325501B7EF7D321219D3A6EBD003EB65717E50CEC60A8414B3A716FC` |

## Expected post-apply schema (9 public tables)
`runs`, `run_events`, `run_gates`, `run_nodes`, `run_artifacts`, `run_checkpoints`, `run_edges`, `run_sources`, `projection_events`.

## Historical counts (unchanged, from committed DML — deterministic)
```
runs=4, run_events=0, run_gates=3, run_nodes=3, run_artifacts=17,
run_checkpoints=0, run_edges=0, run_sources=23
projection_events=0 (before live writes; no historical projection backfill)
```

## projection_events contract (migration 3) — TERRAFORMED for E2E GREEN
- Table `projection_events` — canonical live event ledger, aligned to
  `projects/dw-observation/sql/projection_events.sql` (RunProjectionEvent v1).
- Normalized canonical columns: `id` (BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY),
  `projection_ordinal` (BIGINT GENERATED ALWAYS AS IDENTITY — DB-assigned durable
  global ordinal), `run_id`, `source_system`, `source_event_id`, `sequence`
  (INTEGER NOT NULL CHECK (sequence >= 0)), `event_type`, `occurred_at`,
  `gate`, `node_id`, `actor`, `outcome`, `before`, `after`, `evidence_refs`,
  `authority_ref`, `source_digest` (TEXT NOT NULL), `read_only_projection`
  (BOOLEAN NOT NULL DEFAULT TRUE).
- Unique canonical identity `(run_id, source_system, source_event_id)`.
- Strict per-run ordering: `CREATE UNIQUE INDEX idx_projection_events_run_ordinal
  ON projection_events (run_id, projection_ordinal)` (in addition to the global
  IDENTITY which is globally unique); plus per-source index
  `idx_projection_events_run_src_seq ON projection_events (run_id, source_system, sequence)`.
- `notify_projection_event()` + AFTER INSERT trigger
  `trg_projection_events_after_insert`.
- Broadcast via `PERFORM realtime.send(jsonb_build_object(...) , 'projection_event',
  'observatory:' || NEW.run_id, false)` — raw jsonb payload (NO `::text` cast),
  NOT pg_notify.
- RLS enabled; SELECT-only policy `projection_events_select_publishable ON
  projection_events FOR SELECT TO anon, authenticated USING (true)`.
- NO client INSERT/UPDATE/DELETE policy; NO historical projection backfill.
- Authorization: Human G2 V2 CONSUMED (`ar-scrum-555-g2-correction-v2-20260824 / 5a3a480bd37fdd7b`).

## Real app read path (Task 3, publishable/RLS-compatible) — TERRAFORMED for E2E GREEN
- `lib/serverRunRead.ts`: real list/detail read `runs`, `run_gates`, `run_nodes`,
  `projection_events` via PUBLISHABLE (anon) key boundary.
- `lib/postgresEventStore.ts`: SELECT normalized ProjectionEvent columns
  (`run_id, source_system, source_event_id, sequence, projection_ordinal,
  event_type, occurred_at, gate, node_id, actor, outcome, before, after,
  evidence_refs, authority_ref, source_digest, read_only_projection`) from
  `projection_events` ordered by `projection_ordinal`.
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

### Incident 1 — local amend (displaced lineage)
- One prohibited LOCAL/UNPUSHED amend `147cc34 -> c32fac3` occurred during
  Task 2 GREEN, displacing `147cc34` from branch ancestry.
- Detected and preserved in audit artifact commit `70ddd1c`
  (`.gwc/tasks/SCRUM-555/repair/VIOLATION_EVIDENCE.md`).
- Branch was NEVER pushed → incident never reached remote; no
  force-push/shared-history corruption. DAG NOT rewritten to hide it.

### Incident 2 — G3_SCOPE_VIOLATION_LOCAL_ONLY (new branch/worktree during G3)
- Local correction branch/worktree `correction/SCRUM-555-g3-changes-required` created
  during G3 despite the `no new branch/worktree` prohibition.
- Scope: local-only; no remote ref created; no committed diff pushed.
- Evidence preserved locally; NO cleanup/reset under this G2.
- Remote impact: none — never reached remote; no shared-history corruption.

## Implementation checkpoint (pre-packet, not self-bound)

This packet records implementation state at the time of its refresh. It does NOT
self-bind the final pushed HEAD SHA or CI result — those are bound externally by
Controller/G3 delivery evidence (exact-head CI run, PR head OID).

At the time of this refresh:
- Execution baseline: `70ddd1c` (resume); Task 2 GREEN frozen; Task 3 GREEN
  accepted; Task 4 (this packet) refreshed.
- Pre-packet HEAD (before this correction pass): `cb972da4325cbee36969f058a0a070aaabe87b17`.
- Migration SHA256 (LF, pre-R7): `99ecc412c24ef30715ee7546073b546e05052ff60debbd7286d035b4aed87831`.
- Verification evidence (pre-R7): serverRunRead 6/6, migration contract
  16/16, full vitest 257/257 (16 files), `tsc --noEmit` 0 errors; frozen Task-2
  hashes unchanged (DDL `ef880051…`, DML `5bcee0d6…`).
- Lifecycle status at refresh: **pre-push, pre-G3, pre-G4, pre-G6**.

After R6 correction pass:
- Migration SHA256 (LF, with UNIQUE ordinal index): `1e9768bbb09ff46adf245b1336863e8ca0062ef7fdd30b66630a7de7cbeeff86`.
- Verification evidence: migration contract 17/17, serverRunRead 6/6, full
  vitest 258/258.
- Final pushed HEAD: `7ce6aacec4510d8a471f3e7ec65c100fad1f1692`; CI
  `Validate workspace` run `32743287917` = SUCCESS (bound by Controller/G3
  delivery evidence, not by this artifact).

After R7 G2 additive recovery (RESTORE_ALL_THREE_UNAUTHORIZED_PATHS_EXACTLY):

- Recovery commit: `3aa7f7cc452cf7b94cf8c9009e57d536330d18b3` (additive, non-force push on `auto/SCRUM-555-observatory-g6-readiness-r1`; preserves `089539eb` history).
- Restored to exact `da8b514` tree content: `lib/live.ts`, `lib/postgresEventStore.ts`; deleted `tests/unit/occurredAtContract.ts`.
- Approved surfaces retained: `projects/dw-observation/supabase/migrations/20260823T100000Z_projection_events.sql` (BLOCKER A `occurred_at TIMESTAMPTZ NOT NULL`, no DEFAULT), `lib/serverRunRead.ts` (BLOCKER B `source_digest` + `read_only_projection`), `app/runs/[runId]/page.tsx`, `tests/unit/serverRunRead.test.ts`.
- Inline occurred_at contract assertions in `tests/unit/supabaseMigrationContract.test.ts` (no separate helper file on disk).
- Validation: migration contract 27/27 PASS, serverRunRead 8/8 PASS, full vitest 270/270 PASS (16 files), `tsc --noEmit` 0 errors.
- Migration SHA256 (LF): `D79F7811325501B7EF7D321219D3A6EBD003EB65717E50CEC60A8414B3A716FC`.
- Guard hashes unchanged: DDL `ef880051…`, DML `5bcee0d6…`.
- Final pushed HEAD `3aa7f7cc` + CI not yet bound by Controller/G3 delivery evidence.

## Exclusions
- No remote Supabase apply (G6 boundary). No pre-prod→main, no deploy, no GWC
  mutation, no force-push/rewrite.
- Final pushed HEAD and CI result are bound by Controller/G3 delivery evidence,
  not by self-referential claims in this artifact.
