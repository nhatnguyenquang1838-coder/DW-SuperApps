# GWC HTML Report Generation Plan

## Goal

Generate a single HTML report from GWC artifacts at every gate, stored in the task directory, regenerated fully on each run.

## Context

GWC (Governance) produces YAML/MD artifacts across gates G0–G6 under `.gwc/tasks/<task-id>/`. An existing `scripts/dw_report.py` generates G1-only markdown reports. The new script must produce a self-contained HTML report covering all gates with gate-status and artifact-summaries content, styled with clean visual hierarchy (canvas-design principles).

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Target system: `gwc` | GWC owns the artifacts and the report is a governance deliverable |
| 2 | Scope: all gates (G0–G6) | Full lifecycle visibility |
| 3 | Output: `.gwc/tasks/<task-id>/report.html` | Co-located with task artifacts |
| 4 | Content: gate-status + artifact-summaries | Status overview per gate + file-level summaries |
| 5 | Style: embedded CSS, canvas-design aesthetic | Clean layout, status badges, visual hierarchy, no external deps |
| 6 | Trigger: standalone script, full regeneration | Simplest, always consistent, no stale sections |
| 7 | Script: `scripts/gwc_report.py` (new file) | Separate from existing `dw_report.py` which is G1-markdown only |
| 8 | Invocation: `dw gwc report --task <task-id>` | CLI integration with existing `dw` command |

## Implementation Tasks

### 1. Create `scripts/gwc_report.py`

New script with:
- `load_task_artifacts(task_id)` — scans `.gwc/tasks/<task-id>/` for all YAML/MD artifacts, groups by gate
- `build_gate_status(artifacts)` — extracts gate name, status, timestamp, key decisions from each artifact
- `build_artifact_summaries(artifacts)` — lists file names, sizes, and brief content summaries per artifact
- `render_html(gate_data)` — generates a single self-contained HTML file with embedded CSS
- `cmd_report(args)` — CLI entry point

### 2. Add `report` subcommand to `bin/dw`

Route `dw gwc report --task <task-id>` to `scripts/gwc_report.py`.

### 3. Add post-gate hook in GWC workflow

After each gate YAML artifact is written, invoke `dw gwc report --task <task-id>` to regenerate the report. This can be a shell hook or CI step.

### 4. HTML Report Design

- Single-page, scrollable
- Per-gate collapsible sections (details/summary or JS toggle)
- Status badges (pass/fail/pending/blocked)
- Artifact table per gate: filename, type, size, last-modified, brief summary
- Summary dashboard at top: gate progression bar, overall status
- Embedded CSS reflecting canvas-design principles: visual hierarchy, ample whitespace, minimal text, status-driven color coding

### 5. Validation

- `dw gwc report --task SCRUM-119` produces valid HTML at `.gwc/tasks/SCRUM-119/report.html`
- Report includes all gates G0–G5 with correct status and artifact summaries
- Re-running the script produces identical output (idempotent full-regeneration)
- `dw doctor all --offline` still passes

## Risks

- Low: new script is isolated from existing `dw_report.py`
- Medium: post-gate hook integration depends on GWC gate completion mechanism (needs verification)
- Low: HTML report is self-contained, no external dependencies

## Rollback

- Remove `report` subcommand from `bin/dw`
- Delete `scripts/gwc_report.py`
- Remove post-gate hook from GWC workflow
- Delete any generated `report.html` files
