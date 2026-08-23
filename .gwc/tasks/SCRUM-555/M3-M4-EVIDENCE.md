# SCRUM-555 · M3 + M4 — DW Run Observatory

Run: `DW-OBS-M3M4-20260823-R1`
Authority: `G2-DW-OBS-M3M4-20260823-R1` · scope `aa5756f5dfc424ba`
Execution base: `pre-prod@edb91060017ea02685718a1fadf1dbb7acddbee7`
Branch: `auto/SCRUM-555-dw-observation-m3m4-r1`
Nodes: M3 `#74` → M4 `#75`

## Scope

Only these paths are touched:

- `projects/dw-observation/dw_observation/replay.py` (new)
- `projects/dw-observation/lib/replay.ts` (new)
- `projects/dw-observation/lib/reviewIntelligence.ts` (new)
- `projects/dw-observation/components/ReplayPane.tsx` (new)
- `projects/dw-observation/components/ReviewPane.tsx` (new)
- `projects/dw-observation/app/runs/[runId]/page.tsx` (wire-up only)
- `projects/dw-observation/tests/test_replay.py` (new)
- `projects/dw-observation/tests/unit/replay.test.ts` (new)
- `projects/dw-observation/tests/unit/reviewIntelligence.test.ts` (new)
- `projects/dw-observation/tests/unit/ReplayPane.test.tsx` (new)
- `projects/dw-observation/tests/unit/ReviewPane.test.tsx` (new)
- `.gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md` (this file)

No `pre-prod -> main`, no deploy/G6, no remote Supabase mutation, no GWC repo
mutation, no force-push or history rewrite. `pnpm-workspace.yaml` is verified
byte-identical to the execution base after install (pnpm mutates it on install;
it is restored and checked against the base blob).

## M3 — deterministic rewind / replay

### Core contract

`RunState(N) = reduce(events[0..N])`. A replay frame at cursor `N` is exactly the
M0 projection of the first `N` events. There is no separate replay reducer, so
replay cannot drift from LIVE semantics.

`cursor` is the NUMBER OF EVENTS APPLIED (`0..len(events)`), which removes the
off-by-one between "rewind to event 3" and "rewind to before event 3".

### Determinism

- Nothing consults wall clock, randomness, or I/O; folding is pure.
- `state_digest` is a canonical (sorted-key) hash of the projection.
- `replay_digest` hashes EVERY intermediate frame digest in cursor order, so two
  streams share a digest only when every intermediate state matches — not merely
  the final state. A stream that reaches the same tip by a different path gets a
  different `replay_digest` (covered by test).
- `verify_determinism()` / `verifyDeterminism()` re-run the whole replay and
  require identical output.

### Whole-screen synchronization

`project_surfaces()` / `projectSurfaces()` fan ONE frame out to all five
surfaces (RootCard, DAG, timeline, CI/evidence, inspector). Each surface is
stamped with the same `cursor` + `state_digest`; `synchronized()` /
`isSynchronized()` asserts they agree. Panes cannot disagree because they are
not computed independently. Rewinding hides gates, nodes, and evidence that had
not yet been observed at that point in history.

Rewinding is stateless: visiting cursor `k` yields the same frame regardless of
the path taken. `is_path_consistent()` verifies this over an arbitrary jumping
path (`[7,0,3,1,6,3,7,2,7]`).

### Anomaly parity with M0/M2

DUPLICATE / OUT_OF_ORDER / STALE / GAP are inherited verbatim from the reducer,
per source system (TaskController and GWC are independent ledgers, so
interleaving them raises no false anomaly). A frame exposes exactly the
anomalies within its own prefix: an anomaly is invisible before its event is
applied, and is never hidden once applied. Missing sequence stays UNKNOWN — the
TS reducer never fabricates `seq ?? 0`.

### LIVE resume without sequence corruption

The canonical stream is append-only. Rewinding moves a cursor only; it never
truncates, reorders, or drops. Frames arriving while rewound land at the
canonical tip (the cursor deliberately stays in the past, but nothing is lost),
and `resume_live()` recomputes the tip from the full stream. Tested: a session
that rewound, received a live event, jumped around, and resumed is byte-identical
to a session that never replayed.

## M4 — review intelligence

Derived read-only from the same immutable event stream. `createsAuthority` is
`false` by construction: the module reports authority refs from source and never
derives them.

Metrics: duration (with `terminated` flag), longest wait, retry profile,
recovery profile, handoff profile.

Honesty rules enforced by tests:

- `value === null` means NOT COMPUTABLE — never zero. An unrecovered failure is
  `recovered: false, ms: null`, never a zero-duration recovery.
- An unterminated run is marked `UNTERMINATED` (elapsed-so-far), never presented
  as a completed duration.
- Missing timestamps/sequences raise explicit `MISSING_TIMESTAMP` /
  `MISSING_SEQUENCE` markers and downgrade `confidence` to `PARTIAL`/`UNKNOWN`.
- Handoffs are never invented from an UNKNOWN actor.
- Every computed aggregate carries `trace: TraceRef[]` with exact
  source_system/source_event_id/sequence/evidence_refs/authority_ref, so any
  number traces back to source.

`compareRuns()` warns rather than misleading: a reducer or schema version
mismatch sets `comparable: false` and SUPPRESSES the numeric deltas, so a
reviewer is never shown a diff computed across two derivation contracts.
Incomplete history and anomalies warn but still compare.

## Validation (at this commit, in the isolated worktree)

| Runner | Result |
|---|---|
| `python -m pytest tests -q` | **112 passed** |
| `vitest run` (full) | **160 passed** (9 files) |
| `tsc --noEmit` | **clean, exit 0** |

New tests added by this change: 42 Python (`test_replay.py`), 38 + 35 TS unit
(`replay.test.ts`, `reviewIntelligence.test.ts`), 13 + 14 component
(`ReplayPane.test.tsx`, `ReviewPane.test.tsx`).

### Defect found and fixed during validation

The `ReplayPane` timeline keyed list items by `sourceEventId`. For a stream
containing a DUPLICATE anomaly — a legitimate case this feature must render —
React raised a duplicate-key warning and could omit a row. Fixed by keying on
`${sourceEventId}-${index}`, so duplicate events remain individually visible.

## Exclusions honoured

- No `pre-prod -> main` merge.
- No deploy / G6.
- No remote Supabase or DB mutation (all replay/analytics are pure in-memory
  reads over events supplied by the caller).
- No GWC repo mutation.
- No force-push, no history rewrite; base commit remains an ancestor
  (`BASE_IS_ANCESTOR_OK`).
- No new dependency added: the component tests use `fireEvent` from the existing
  `@testing-library/react` rather than adding `@testing-library/user-event`,
  keeping the lockfile untouched.
