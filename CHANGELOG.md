# Changelog

All notable changes to the DW SuperApps workspace control plane are documented here.

## 2026-07-27 — GWC-core orchestration

### Added

- `manifests/orchestration/intents.yaml` — workspace-level intent registry declaring worker intents for `task-me`, `bmad`, and `ua`.
- `scripts/dw_orchestrator.py` — new orchestration runtime with `prompt` and `run` subcommands.
- `dw orchestrator prompt --system <system> --task "<task>"` — composed human-readable prompt with GWC as primary and applicable worker delegation notes.
- `dw orchestrator run --system <system> --task "<task>"` — structured JSON execution plan with ordered phases.
- Hybrid intent matching: exact intent-ID match first, then candidate intent list for host LLM judgment when no exact match is found.

### Changed

- `workspace.yaml` system entries now support an optional `orchestration` block with `primary`, `workers`, and `hooks`.
- Generated host adapters now include an `## Orchestration` section derived from `workspace.yaml`, so regeneration preserves orchestration rules.
- `bin/dw` now routes `orchestrator prompt|run` to the new orchestrator runtime.

### Safety

- No generated or installed package files were hand-edited.
- No `.dw/powers/` contents were modified.
- No host adapter contents were hand-edited; orchestration metadata is injected during adapter generation from workspace-owned config.
