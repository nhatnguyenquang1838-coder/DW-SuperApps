# SCRUM-555 — abandoned two-parent repair SUPERSEDED

## Incident 1 — local amend (displaced lineage)

- **Commit displaced**: `147cc34` → amended to `c32fac3` (local, unpushed)
- **Detected**: during Task 2 GREEN
- **Preserved**: `.gwc/tasks/SCRUM-555/repair/VIOLATION_EVIDENCE.md` (commit `70ddd1c`)
- **Remote impact**: none — branch NEVER pushed; no shared-history corruption
- **DAG**: NOT rewritten to hide the incident

## Incident 2 — task run missed heartbeat (host recovery)

- **Run**: SCRUM-555 TaskController E2E HOST RECOVERY R4 (`1787569433.468359`)
- **Cause**: >2h without Hermes heartbeat; host session migrated, execution NOT restarted
- **Preservation**: local state intact; no reset/clean/revert; this root becomes current Human Control Plane
- **Branch**: `auto/SCRUM-555-observatory-g6-readiness-r1`
- **Last confirmed HEAD before recovery**: `cb972da4325cbee36969f058a0a070aaabe87b17`

## Human authority

- **G2 V2 consumed**: `ar-scrum-555-g2-correction-v2-20260824 / 5a3a480bd37fdd7b`
- **Expiry**: `2026-08-25T09:59:32Z`
- **Authorized actions**: `modify_approved_files`, `run_sandboxed_validation`, `stage`, `create_commit`, `push_working_branch`
- **No authority expansion** from this recovery

Both incidents are preserved locally. No cleanup, no reset, no force-push.
