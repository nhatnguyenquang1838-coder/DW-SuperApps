# GWC Simulation Lab Agent Rules

This system is a deterministic test harness. It is not a governance authority or production runtime.

## Boundaries

- Run only against checked-in fixtures and task seeds.
- Do not call GitHub, Jira, Slack, Notion, deployment, database, secret, or production APIs.
- Mock approval envelopes must set `simulation_only: true` and `real_authority: false`.
- Never reuse a simulation envelope as a G2, G4, G5, or G6 approval.
- Generated reports belong under `.simulation/` and must not be committed.
- Keep node count at 81, materialized scenario count at 14, declared scenario count at 116, and seed count at 100 unless the pinned GWC source changes through a reviewed update.
