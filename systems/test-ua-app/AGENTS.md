# AGENTS.md — Test UA APP

## Purpose

This is a test application for validating the DW-SuperApps workspace-managed GWC workflow and UA Power knowledge graph generation.

## System Identity

- **ID:** test-ua-app
- **Path:** `systems/test-ua-app`
- **Workspace:** DW-SuperApps (dw-superapps)
- **Runtime data root:** `.ua` (knowledge graph), `.gwc` (governance artifacts)

## Powers

This system uses the following Powers from the DW-SuperApps workspace:

- `powers/gwc` — Governance and delivery workflows
- `powers/ua` — Semantic/codebase knowledge generation and query

## Gate Artifact Locations

All GWC gate artifacts live under `systems/test-ua-app/.gwc/tasks/<task-id>/`:

| Gate | Artifact path |
|---|---|
| G0_CONTEXT | `.gwc/tasks/<task-id>/g0/context-snapshot.yaml` |
| G1_ALIGNMENT | `.gwc/tasks/<task-id>/g1/*/` |
| G2_EXECUTION | `.gwc/tasks/<task-id>/g2/execution-envelope.yaml` |
| G3_PR | `.gwc/tasks/<task-id>/g3/delivery-record.yaml` |
| G4_MERGE | `.gwc/tasks/<task-id>/g4/merge-approval.yaml` |
| G5_DEPLOY | `.gwc/tasks/<task-id>/g5/deployment-approval.yaml` |

## UA Runtime Data

All UA artifacts live under `systems/test-ua-app/.ua/`:

| Artifact | Path |
|---|---|
| Knowledge graph | `.ua/knowledge-graph.json` |
| Metadata | `.ua/meta.json` |
| Intermediate files | `.ua/intermediate/` |
| Config | `.ua/config.json` |

## Exclusion Rules

UA analysis must exclude:
- `.git`
- `node_modules`
- `dist`, `build`
- `coverage`
- `test-results`
- `playwright-report`
- `.pnpm-store`
- Caches
- `.env*`
- Credentials and secrets