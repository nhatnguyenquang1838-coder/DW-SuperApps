# Plan: Update UA Knowledge Graph and Install UA Apps to DW SuperApps

## Goal

1. Use the dw-ua power to update the knowledge graph mapping the relationships between distribution, workspace.yaml, power installation, and host adapters in the DW SuperApps workspace.
2. Install UA apps (host adapters + runtime) into the DW SuperApps system with correct binding and runtime paths.

## Current State

- **UA power** is installed at `.dw/powers/ua/` (version `ua-main-3-4d5fda706fc9683d097cedc947a02011f11baa38`), managed by `dw-superapps-power-store`.
- **Knowledge graph** at `.ua/knowledge-graph.json` has 530 nodes / 1100 edges, last analyzed 2026-07-28 (stale — 2 days).
- **Bindings** are incorrect: `rental-home` binding points to `projects/rental-home/.ua` (wrong); a new `external-acd3de1c6f0f` binding was accidentally created by a test `dw power install ua` run pointing to `systems/rental-home/.ua` (empty dir).
- **Actual runtime data** lives at `/Users/mac/prj/DW-SuperApps/.ua/` (repo root).
- **`systems/rental-home/.ua/`** exists but is empty — a phantom runtime path from the broken install.
- **Host adapters** are already ready for all 7 hosts (kiro, codex, copilot, cline, kilo, claude, custom).
- **`dw doctor all --offline`** passes with exit 1 only due to missing `dw-chatgpt-app` manifest (pre-existing, unrelated).
- **`dw power doctor ua`** fails with `BLOCKED_STORE_RUNTIME_OVERLAP` — the store root (`.dw/powers`) and the system target path overlap in the binding configuration.
- **`dw host install ua`** is invalid — `ua` is a power, not a host. Host install only accepts host names.

## Decisions

1. **Graph update**: Run the UA `/understand --full` skill against the repo root to rebuild the knowledge graph from scratch, covering all distribution files, workspace.yaml, power manifests, and host adapter configurations. A full rebuild is warranted because 85+ commits have changed the workspace structure since the last analysis.

2. **UA installation fix**: The `dw power install ua` command creates a binding with a `systems/` runtime path that does not match the actual `.ua/` location, and the STORE_RUNTIME_OVERLAP error indicates a path conflict. The correct approach is to:
   - Remove the broken `external-acd3de1c6f0f` binding.
   - Update the `rental-home` binding to point to the correct runtime path (`/Users/mac/prj/DW-SuperApps/.ua/`).
   - Do NOT re-run `dw power install ua` until the binding paths are corrected.

3. **UA apps installation**: The host adapters (`.kiro/skills/ua/SKILL.md`, `.codex/skills/ua/SKILL.md`, etc.) are already present and marked "ready". No additional host adapter installation is needed. The "install ua apps" step is satisfied by ensuring the binding is correct and the runtime is populated.

## Execution Steps

### Phase 1: Update the UA knowledge graph

1. Activate the dw-ua skill for target system `rental-home`.
2. Read the canonical installed entrypoint at `.dw/powers/ua/understand-anything-plugin/skills/understand/SKILL.md`.
3. Run the `/understand --full` command against the repo root (`/Users/mac/prj/DW-SuperApps`).
4. Let the scan complete through all phases (0–7), producing an updated `knowledge-graph.json`, `fingerprints.json`, and `meta.json` in `.ua/`.

### Phase 2: Fix UA binding and runtime paths

1. Remove the broken external binding: `rm .dw/bindings/external-acd3de1c6f0f/ua.json` and `rmdir .dw/bindings/external-acd3de1c6f0f`.
2. Update the `rental-home` binding at `.dw/bindings/rental-home/ua.json` to set `runtimePath` to `/Users/mac/prj/DW-SuperApps/.ua/` and `targetPath` to `/Users/mac/prj/DW-SuperApps`.
3. Remove the empty phantom directory: `rm -rf systems/rental-home/.ua/`.
4. Validate the binding by running `dw power doctor ua` — it should no longer report `STORE_RUNTIME_OVERLAP`.

### Phase 3: Validate installation

1. Run `dw doctor all --offline` — should exit 0 (or only warn about the pre-existing `dw-chatgpt-app` missing manifest).
2. Verify `.ua/knowledge-graph.json` is valid JSON and has updated node/edge counts.
3. Verify `.ua/meta.json` has a current `lastAnalyzedAt` timestamp and the correct `gitCommitHash` for HEAD.
4. Verify all 7 host adapters for ua are still present and ready.

## Constraints

- Do not modify the `.dw/powers/ua/` package store contents.
- Do not create a target-local `.dw/powers` in the system directory.
- Do not write host adapters or package payloads into registered system directories.
- The knowledge graph must be regenerated with `--full`, not incremental, because the workspace structure has significantly changed since the last analysis.

## Risks

- The `/understand --full` scan may take a significant amount of time for a large workspace.
- The `BLOCKED_STORE_RUNTIME_OVERLAP` error from `dw power doctor` may be a pre-existing configuration issue that is not fixable by just correcting the binding — it may require restructuring the store/target relationship per the onboarding runbook.
- The `dw-chatgpt-app` power manifest is missing from `projects/dw-chatgpt-app/`, which causes `dw doctor` to exit 1 — this is pre-existing and out of scope.

## Open Questions

- Whether `systems/rental-home/` is the correct runtime target path per workspace.yaml conventions, or whether `.ua/` at repo root is the intended location for this workspace layout. workspace.yaml has `data_ownership.roots.ua: .ua` which points to repo root, but the host adapters and system directory use `systems/rental-home/`.
- Whether the `dw power install ua` command needs a `--store-root` flag to avoid the overlap error, given the workspace-level store root is `.dw/powers`.
