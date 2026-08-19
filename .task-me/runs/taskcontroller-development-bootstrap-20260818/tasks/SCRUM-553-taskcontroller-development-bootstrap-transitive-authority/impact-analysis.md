# Impact analysis

## Candidate direct surfaces
- `taskcontroller/execution/dispatch.py`
- `taskcontroller/execution/types.py`
- `taskcontroller/interaction/continuation.py`
- `taskcontroller/mvp/pilot.py`
- `tests/taskcontroller/`

These remain candidate implementation surfaces until the fresh implementation session re-materializes their exact blob/tree identities against current `main`.

## Transitive impact
- Controller/governance decisions can trigger GitHub Actions, bots, release/archive retention, deployment providers, cross-repository writes, or production-capable integrations.
- Both deterministic and conditionally reachable effects must be represented. A conditional mutating effect is not discarded merely because its predicate is unresolved.
- A child effect in another repository is a separate authority lane.
- TaskController depends on the exact GWC SCRUM-554 capability/effect contract; policy drift invalidates the pre-dispatch receipt.

## Risk
- Risk class: **R2** because the change affects governance/control-plane decisions.
- Primary failure mode: false PASS broadens authority or attaches valid evidence to the wrong execution identity.
- Compatibility risk: TaskController must consume GWC compatibility semantics instead of independently grandfathering legacy packets.
