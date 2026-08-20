# Decisions
- Shield canonical entities are separate from issue/task projections.
- Reuse generic serialization patterns, not TaskController semantic enums.
- Mutable canonical entities use expected-version CAS; immutable artifacts use exact digest refs.
