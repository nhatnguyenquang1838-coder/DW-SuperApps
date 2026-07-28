# GWC-Core Orchestration Plan

## Goal

Make GWC the core governance workflow and DW SuperApps the orchestration extension, without modifying generated or power-package files that get overwritten by `dw host install` or `dw power install`.

## Constraints

- Do not hand-edit `.dw/powers/<power>/` — reinstalls overwrite it.
- Do not hand-edit generated host adapters (`.kilo/rules/`, `.agents/skills/`, etc.) — `dw host install` regenerates them.
- All orchestration rules must live in workspace-owned files and survive regeneration.

## Decision

- **Primary:** GWC owns G0–G6 lifecycle, approval boundaries, and validation.
- **Extension:** DW SuperApps owns orchestration — when to delegate, to which worker power, and how to feed results back.
- **Mechanism:** workspace-level intent registry + hybrid matching + composed prompts.

## Schema

### `workspace.yaml` system-level orchestration block

```yaml
orchestration:
  primary: gwc
  workers:
    - task-me
    - bmad
    - ua
  hooks:
    - gate: g1
      intents:
        - task-decomposition
        - validation-planning
      worker: task-me
      output_into: g1-options
    - gate: g1
      intents:
        - architecture-design
        - data-modeling
      worker: bmad
      output_into: g1-options
    - gate: g1
      intents:
        - dependency-mapping
        - impact-analysis
      worker: ua
      output_into: g1-preflight
```

### `manifests/orchestration/intents.yaml`

```yaml
intents:
  task-decomposition:
    description: Break work into bounded implementation tasks and validation plans
    worker: task-me
  validation-planning:
    description: Plan validation strategy for implementation tasks
    worker: task-me
  architecture-design:
    description: Design service boundaries, modules, or system architecture
    worker: bmad
  data-modeling:
    description: Design or change data models and schemas
    worker: bmad
  dependency-mapping:
    description: Map repository dependencies and coupling
    worker: ua
  impact-analysis:
    description: Analyze blast radius and downstream impact of changes
    worker: ua
```

## Implementation Tasks

### 1. Add `manifests/orchestration/intents.yaml`

Create the workspace-level intent registry with declared intents for `task-me`, `bmad`, and `ua`.

### 2. Add `orchestration` block to `workspace.yaml`

Add the block under the `rental-home` system entry, referencing intents by ID.

### 3. Create `scripts/dw_orchestrator.py`

New module with subcommands:
- `dw orchestrator prompt --system <system> --task "<task>"` — single composed prompt
- `dw orchestrator run --system <system> --task "<task>"` — structured JSON execution plan

**Matching logic (hybrid):**
1. Extract candidate intents from the task text by exact intent-ID match.
2. If matches found, use them.
3. If no exact matches, query the host LLM with remaining candidate intents and let it select applicable ones.
4. Resolve hooks for matched intents; if multiple hooks match the same intent, use the first declared hook for that `(gate, worker)` pair.

**`prompt` output shape:**
- Human-readable composed prompt with GWC as primary, followed by applicable worker delegation sections.

**`run` output shape:**
- Structured JSON with ordered phases, each phase containing `power`, `task`, `expected_output`, and `feeds_into`.

### 4. Update `bin/dw`

Add orchestration command routing to `bin/dw` to dispatch to `dw_orchestrator.py`.

### 5. Update `scripts/dw_workspace_dist.py`

Modify `host_instruction_content()` and `wrapper_content()` to inject a lightweight orchestration section into generated adapters, derived from `workspace.yaml`:

```markdown
## Orchestration for <system>

Primary: `gwc`
Workers: `task-me`, `bmad`, `ua`
Delegation hooks: ...

Use `dw orchestrator prompt --system <system> --task "<task>"` for composed prompts.
```

Because content is derived from `workspace.yaml`, regeneration preserves rules.

### 6. Do not modify GWC package

Leave `.dw/powers/gwc/` untouched. If GWC upstream adds native orchestration hooks later, this workspace layer can be deprecated without affecting installed packages.

## Validation

- `git status` shows no modifications inside `.dw/powers/`.
- `dw host install all --mode wrapper` regenerates adapters with orchestration section intact.
- `dw orchestrator prompt --system rental-home --task "..."` returns a composed prompt referencing GWC + applicable workers.
- `dw orchestrator run --system rental-home --task "..."` returns structured JSON with phases.
- `dw doctor all --offline` remains PASS.

## Rollback

- Remove `orchestration` block from `workspace.yaml`.
- Delete `manifests/orchestration/intents.yaml`.
- Delete `scripts/dw_orchestrator.py` and its `bin/dw` routing.
- Revert `scripts/dw_workspace_dist.py` changes.
- Re-run `dw host install all --mode wrapper`.

## Risk

- Low: no generated or installed package files are hand-edited.
- Medium: workspace-level orchestration may become redundant if GWC upstream adds native orchestration; removable without affecting packages.
