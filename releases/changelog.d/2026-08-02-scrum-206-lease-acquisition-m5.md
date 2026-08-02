---
task_id: SCRUM-206
node_id: runtime_checkpoint.lease-acquisition
maturity: M2 -> M5_REPLAY_SAFE
gate: G2_EXECUTION
summary: >
  Implement deterministic, replay-safe lease acquisition decision utility (MAT-F4-N05).
  Acquisition is gated on valid bindings (task_id, run_id, scope_hash, repository, branch),
  monotonic fencing token, and scope validation. Competing agents and stale workers are
  rejected; expired leases route to RECONCILE or REACQUIRE_REQUIRED based on side-effect state.
tests:
  - tests/test_lease_acquisition.py (unit tests covering determinism, competing-agent rejection, scope validation)
verified:
  - PYTHONPATH=tools python tests/test_lease_acquisition.py -> pending
exclusions:
  - merge_to_main, deploy, release, edit_core_governance, credentials,
    migrations, manual_g5_deploy, recursive_evidence_pr