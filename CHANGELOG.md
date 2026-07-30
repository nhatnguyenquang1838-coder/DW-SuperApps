# Changelog

All notable changes to the DW SuperApps workspace control plane are documented here.

## 2026-07-27 — G1 user-facing report generator

### Added

- `scripts/dw_report.py` — new report generator for GWC gate artifacts.
- `dw report g1 --workspace <path>` — produces a Markdown alignment report from G1 artifacts (`g1-intake-brief.yaml`, `g1-options.yaml`, `g1-preflight-report.yaml`, `g1-decision-record.yaml`).
- Report sections include intake summary, options with recommendation, preflight checks, decision record, authority boundaries, subagent distribution plan, and next steps.

### Changed

- `bin/dw` now routes `report g1` to the new report runtime.

### Safety

- Report generator is read-only; it does not modify artifacts or runtime state.
- No generated or installed package files were hand-edited.

## 2026-07-27 — GWC-core orchestration

### Added

- `manifests/orchestration/intents.yaml` — workspace-level intent registry declaring worker intents for `task-me`, `bmad`, and `ua`.
- `scripts/dw_orchestrator.py` — new orchestration runtime with `prompt` and `run` subcommands.
- `dw orchestrator prompt --system <project-id> --task "<task>"` — composed human-readable prompt with GWC as primary and applicable worker delegation notes. `--system` is a deprecated compatibility flag.
- `dw orchestrator run --system <project-id> --task "<task>"` — structured JSON execution plan with ordered phases. `--system` is a deprecated compatibility flag.
- Hybrid intent matching: exact intent-ID match first, then candidate intent list for host LLM judgment when no exact match is found.

### Changed

- Product project entries in `workspace.yaml` now support an optional `orchestration` block with `primary`, `workers`, and `hooks`.
- Generated host adapters now include an `## Orchestration` section derived from `workspace.yaml`, so regeneration preserves orchestration rules.
- `bin/dw` now routes `orchestrator prompt|run` to the new orchestrator runtime.

### Safety

- No generated or installed package files were hand-edited.
- No `.dw/powers/` contents were modified.
- No host adapter contents were hand-edited; orchestration metadata is injected during adapter generation from workspace-owned config.
