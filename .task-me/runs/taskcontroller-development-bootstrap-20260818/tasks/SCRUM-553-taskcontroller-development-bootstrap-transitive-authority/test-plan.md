# Test plan

## Planned focused tests
- `tests/taskcontroller/test_materialized_execution_contract.py`
- `tests/taskcontroller/test_transitive_authority_preflight.py`
- `tests/taskcontroller/test_evidence_binding_identity.py`
- `tests/taskcontroller/test_fresh_session_handoff.py`

## Required scenarios
1. Missing or stale materialization identity fails closed before dispatch.
2. Authorized direct action + unauthorized deterministic mutating child is blocked before execution.
3. Conditional mutating child with predicate `false` is excluded only with bound predicate evidence.
4. Conditional mutating child with predicate `true` participates in authority closure.
5. Conditional mutating child with predicate `unknown` is treated as potentially reachable and blocks unless worst-case child authority is independently valid.
6. Safe read-only/compute child does not spuriously escalate authority but remains observable.
7. Cross-repository mutating child without independent repo authority is blocked.
8. Correct PR-head evidence cannot satisfy a merge-SHA/post-merge node.
9. A successful historical workflow/check from another SHA/event/gate cannot become current authority evidence.
10. Same replay identity is equivalent; semantic drift under the same identity is rejected.
11. Exact-base/head or GWC-policy digest drift invalidates stale evidence.
12. Fresh-session handoff rejects mismatched spec head, Task-Me package digest, GG Section 1A hash, or GWC capability/effect contract digest.

## CI discipline
After every pushed implementation/spec head, check CI for that exact SHA. If non-terminal, remain in-session, sleep 60 seconds, and re-read the exact SHA until terminal.
