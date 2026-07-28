# BMAD Permission/Action Matrix

| Action | Architecture Analysis | TDD Implementation | Review-Only | Scope Violation |
|---|---|---|---|---|
| Read project context | allowed | allowed | allowed | allowed |
| Write BMAD/project-owned paths | allowed | allowed | denied | denied |
| Mutate .gwc canonical state | denied | denied | denied | denied |
| Self-approve gate transition | denied | denied | denied | denied |
| Publish BMAD package | denied | denied | denied | denied |
| Merge/deploy/release | denied | denied | denied | denied |
| Recommend scope change | proposal/blocker | proposal/blocker | proposal/blocker | blocker |

## Permission Levels

### readAnalysis
- **Description**: BMAD may read project context, analyze code, and produce findings without writing.
- **Allowed Paths**: `**` (read-only)
- **Allowed Actions**: `read`, `analyze`, `report`

### boundedWrite
- **Description**: BMAD may write outputs to declared BMAD/project-owned paths only.
- **Allowed Paths**: `.bmad/**`, `_bmad/**`, `_bmad-output/**`, `docs/**`
- **Allowed Actions**: `read`, `analyze`, `report`, `write`, `create`, `update`
- **Denied Actions**: `delete`

### prohibited
- **Description**: BMAD must never perform these actions under any circumstances.
- **Denied Paths**: `.gwc/**`, `.env*`, `**/secrets/**`, `.git/**`
- **Denied Actions**: `delete`, `approve`, `merge`, `deploy`, `release`, `publish`

## Authority Boundaries

### Gate Approval
- **Rule**: BMAD cannot approve G2/G4/G5/G6. Gate transitions are performed by GWC only.
- **Enforced By**: GWC governance layer
- **Gates**: G2, G4, G5, G6

### Canonical State
- **Rule**: BMAD cannot alter .gwc canonical state.
- **Protected Paths**: `.gwc/**`

### Scope Expansion
- **Rule**: BMAD cannot expand scope without explicit GWC authorization.
- **Authorization Required**: GWC scope hash, gate approval

### Projection Writes
- **Rule**: BMAD cannot perform Jira/Notion/Slack projection writes.
- **Systems**: jira, notion, slack

## Idempotency

- **Scope**: `procedureId`, `targetSha`, `gwcScopeHash`
- **Duplicate Handling**: `reject` — same idempotency key with same targetSha and scopeHash returns cached result; never duplicates side effects.

## Provenance

Every invocation must bind to:
- Exact task ID
- Repository owner/name
- Base SHA and head SHA
- Procedure version
- GWC scope hash