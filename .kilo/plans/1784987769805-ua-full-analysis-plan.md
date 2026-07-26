# DW SuperApps — UA Full Analysis Plan

## Goal
Run the Understand Anything (UA) power in full mode against the DW SuperApps workspace to produce the complete set of knowledge-graph artifacts under `.ua/`.

## Current State
- `.ua/` does not exist.
- All four Powers are registered and host adapters are ready.
- `projects/ua` submodule is checked out at commit `6ae71878beb50226a1e4b7e2f52ac6468c86f74b` (tag `v1.3.0-555-g6ae7187`).

## Artifacts to Generate
Run `dw power prompt ua --system dw-superapps --task "Full UA analysis"` or invoke the UA skill directly to produce:

1. `.ua/knowledge-graph.json` — The canonical knowledge graph (nodes, edges, layers, tour).
2. `.ua/intermediate/scan-result.json` — File inventory with languages, frameworks, and import map.
3. `.ua/intermediate/batches.json` — Semantic batches for parallel analysis.
4. `.ua/intermediate/assembled-graph.json` — Merged graph after Phase 2 normalization.
5. `.ua/intermediate/layers.json` — Architectural layer definitions.
6. `.ua/intermediate/tour.json` — Guided tour steps.
7. `.ua/intermediate/review.json` — Validation report (issues/warnings/stats).
8. `.ua/meta.json` — Analysis metadata (timestamp, commit hash, file count).
9. `.ua/config.json` — UA runtime config (autoUpdate, outputLanguage).
10. `.ua/.understandignore` — Exclusion rules for incremental runs.

## Architecture Summary (from preliminary exploration)
Use this to validate the final graph:

- **Hub:** `workspace.yaml` (hosts, providers, powers, systems, data ownership)
- **Spokes:** `projects/*` (gwc, ua, task-me, rental-home), `powers/bmad`, `plugins/bmad-method`
- **CLI surface:** `bin/dw` → `scripts/dw_entry.py` / `scripts/dw_cli.py` / `scripts/dw_power_package.py`
- **Host adapters:** `.kilo/`, `.github/`, `.agents/`, `.claude/`, `.codex/`, `.kiro/`, `.clinerules/`
- **Distribution:** `scripts/power_dist.py` + `schemas/` + `templates/` + `plugins/bmad-method/`
- **Governance:** `.gwc/` + `manifests/evidence/`

## Key Node Types Expected
- `file:` for source files in `scripts/`, `bin/`, `tests/`
- `config:` for YAML/JSON configs (`workspace.yaml`, `kilo.jsonc`, manifests, schemas)
- `document:` for Markdown docs (`README.md`, `AGENTS.md`, `docs/`)
- `service:` / `pipeline:` for CI workflows (`.github/workflows/`)
- `endpoint:` if any API routes exist in scripts
- `module:` / `concept:` for logical groupings (Power Runtime v2, distribution builder, host adapter layer)

## Key Edge Types Expected
- `imports` between Python scripts
- `configures` from `workspace.yaml` → manifests, powers, systems
- `documents` from `AGENTS.md` / `README.md` → components
- `deploys` from CI workflows → distribution/validation steps
- `depends_on` from `bin/dw` → Python scripts
- `contains` for directory containment
- `tested_by` from `tests/` → scripts

## Steps to Execute
1. Ensure Node.js >= 22 and pnpm >= 10 are installed (required by UA plugin).
2. Build the UA plugin if needed: `cd projects/ua/understand-anything-plugin && pnpm install && pnpm --filter @understand-anything/core build`
3. Run full analysis:
   ```bash
   cd /Users/mac/prj/DW-SuperApps
   ./bin/dw power prompt ua --system dw-superapps --task "Full UA analysis" --full
   ```
   Or run the skill directly if the power prompt resolves to the skill invocation.
4. Verify `.ua/knowledge-graph.json` exists and passes validation.
5. Optionally run `--review` for LLM graph review instead of inline validation.

## Validation Criteria
- `dw doctor all` passes after generation.
- `.ua/knowledge-graph.json` contains nodes, edges, layers, and tour.
- No `.ua/intermediate/*` files other than `scan-result.json` remain after cleanup (Phase 7 moves them to `.trash-*`).
- `meta.json` records the current git commit hash and analyzed file count.

## Risks / Notes
- The UA plugin requires a Node.js build step. If `pnpm` is missing, the skill will prompt for installation.
- Running with `--full` forces rebuild; incremental runs require `scan-result.json` to be preserved.
- The `projects/ua` submodule is large; Phase 1 scan may take a while.
- If any Phase 2 subagent dispatch fails, the skill retries once then continues with partial results.
