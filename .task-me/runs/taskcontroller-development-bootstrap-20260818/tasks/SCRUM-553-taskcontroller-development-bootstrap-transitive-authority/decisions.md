# Observable decisions

## Decision 1 — repository ownership
Evidence: current DW-SuperApps and GWC contracts.
Alternatives: one umbrella repo; duplicate policy in both repos; independent repo lanes.
Decision: independent repository lanes `SCRUM-553` and `SCRUM-554` with separate base/branch/authority.
Confidence: high.

## Decision 2 — canonical specification
Evidence: user selection B and current Task-Me skill boundary.
Decision: Task-Me package is canonical; no competing `docs/superpowers/**` spec tree.
Confidence: high.

## Decision 3 — architecture boundary
TaskController owns orchestration, materialization and pre-dispatch enforcement. GWC owns capability vocabulary and transitive authority-closure semantics. TaskController consumes an exact GWC policy identity; it MUST NOT duplicate/re-derive that policy.
Confidence: high.

## Decision 4 — conditional effects
A conditional mutating child can be excluded only when its predicate is proven false. A true or unresolved predicate is authority-closed as reachable/potentially reachable using the GWC-owned worst-case capability. Read-only conditional children remain observable without needless escalation.
Confidence: high.

## Decision 5 — fresh-session identity
The handoff must bind the exact spec head, deterministic Task-Me package SHA-256, GG revision + semantic edition + Section 1A hash, and the exact GWC capability/effect policy digest.
Confidence: high.

## Remaining implementation uncertainty
Exact source file set may narrow after fresh-session drift/materialization readback; narrowing is allowed, scope expansion is not. No semantic policy question may be deferred to implementation by inventing a local answer.
