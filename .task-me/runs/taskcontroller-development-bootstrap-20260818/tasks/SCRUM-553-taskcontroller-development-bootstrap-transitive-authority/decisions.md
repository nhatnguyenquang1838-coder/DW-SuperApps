# Observable decisions

## Decision 1 — repository ownership
Evidence: current DW-SuperApps and GWC contracts.
Alternatives: one umbrella repo; duplicate policy in both repos; independent repo lanes.
Decision: independent repository lanes `SCRUM-553` with separate base/branch/authority.
Confidence: high.

## Decision 2 — canonical specification
Evidence: user selection B and current Task-Me skill boundary.
Decision: Task-Me package is canonical; no competing `docs/superpowers/**` spec tree.
Confidence: high.

## Decision 3 — architecture boundary
Keep TaskController responsible for orchestration/pre-dispatch enforcement; GWC remains the authority vocabulary/validator source. Do not duplicate GWC capability policy inside TaskController.
Confidence: high.

## Unresolved uncertainty
No design uncertainty blocks the spec. Exact implementation file set may narrow after fresh-session drift/materialization readback; narrowing is allowed, scope expansion is not.
