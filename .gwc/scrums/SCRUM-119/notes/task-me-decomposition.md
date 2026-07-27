# Task-Me Decomposition for SCRUM-119

## Decomposition

1. Verify the BMAD schema set is valid JSON and internally consistent.
2. Verify the permission matrix matches the authority boundaries in the registry.
3. Verify the positive examples stay within allowed paths and actions.
4. Verify the rejected example blocks self-approval before side effects.
5. Verify the GWC gate records reference the exact deliverables.

## Execution Order

- Schemas first
- Governance records second
- Examples third
- Validator/test plan last

## Completion Criteria

- GWC gate evidence exists in `.gwc/g1/`.
- UA impact/dependency mapping is captured.
- BMAD contract artifacts are present at repo root.
- Scope violations are rejected before any write outside permitted paths.
