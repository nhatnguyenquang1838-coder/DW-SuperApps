# Issue → spec → implementation/test traceability

Source requirement: GitHub issue #67 / Jira SCRUM-553.

| Issue AC | Requirement | Plan | Planned verification |
|---|---|---|---|
| AC1 | Dispatch blocked when materialization is incomplete/stale | Step 1, Step 3 | Scenarios 1, 11 |
| AC2 | Deterministic downstream effects discovered and authority-closed before mutation | Step 2, Step 3 | Scenarios 2, 4 |
| AC3 | Cross-repo child effects require independent repo authority | Step 2, Step 3 | Scenario 7 |
| AC4 | Evidence cannot be consumed by a different SHA/event/gate-node | Step 4 | Scenarios 8, 9, 10 |
| AC5 | PR-head CI cannot satisfy merge-SHA verification | Step 4 | Scenario 8 |
| AC6 | Continuation/recovery preserves validated contract/effect identity | Step 4 | Scenarios 10, 11 |
| AC7 | Bootstrap emits bounded fresh-session implementation handoff | Step 5 | Scenario 12 |
| AC8 | Pass/fail/drift/replay tests do not grant later-gate authority | Steps 3-6 + Delivery boundary | Scenarios 1-12 + full suite |

Conditional-effect semantics strengthen AC2: a mutating conditional child is never silently ignored merely because its predicate is not yet resolved.
