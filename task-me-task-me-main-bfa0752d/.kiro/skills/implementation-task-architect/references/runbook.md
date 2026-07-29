# Runbook

## R0 — Bootstrap

Entry: Skill invoked.

Actions:
- Read `.task-architect/config.json`.
- Resolve repository root.
- Confirm output path is inside repository root.
- Confirm `output.folder_mode` is `per_task`.
- Validate run, shared and task folder patterns.

Exit: Configuration valid.

## R1 — Source inventory

Actions:
- Expand all configured globs.
- Apply exclusions.
- Record path, type, size and content hash.
- Fail if mandatory categories are empty.

Exit artifact: run shared file `01-source-inventory.json`.

## R2 — Complete document intake

Actions:
- Read all matched requirements, design, ADR, system graph and context documents.
- Split large files into bounded ranges without omitting sections.
- Record conflicts and unresolved references.

Exit: Complete document coverage confirmed.

## R3 — Repository evidence scan

Actions:
- Inventory source and test files.
- Extract imports, references, declarations, routes, schemas and test links where detectable.
- Verify important findings by direct file reads.

Exit: Repository evidence manifest available.

## R4 — Traceability

Actions:
- Normalize requirements, acceptance criteria and design decisions.
- Generate candidate links to systems, files, symbols and tests.
- Verify candidates and assign confidence.

Exit artifact: run shared file `02-traceability.json`.

## R5 — Evidence graph and impact

Actions:
- Build typed nodes and edges.
- Traverse bounded upstream and downstream dependencies.
- Classify direct, transitive, contract, data, test, operational and unknown impact.
- Preserve a task-specific evidence subset for later folder materialization.

Exit shared artifacts:
- `03-evidence-graph.json`
- `04-impact-analysis.md`

## R6 — Task decomposition

Actions:
- Apply hierarchical decomposition templates.
- Split on repository, deployable, ownership, migration, rollback and independent-test boundaries.
- Create discovery tasks for unresolved targets.
- Assign each task a stable task ID and unique filesystem-safe slug.
- Reject any decomposition that combines multiple primary outcomes in one task folder.

Exit: Atomic task candidates with folder identities.

## R7 — Dependency planning

Actions:
- Derive BLOCKS, REQUIRES and PARALLEL_WITH relations.
- Detect cycles.
- Resolve cycles by merge, compatibility layer, activation split or discovery task.
- Produce delivery waves.
- Ensure dependency references use stable task IDs, not folder names.

Exit: Valid task DAG.

## R8 — Complexity, risk and effort

Actions:
- Score breadth, coupling, domain logic, contract/data, testing, operations and uncertainty.
- Score risk separately.
- Produce optimistic, likely and pessimistic effort.

Exit: Every task has explained estimates.

## R9 — Coding guide

Actions:
- Name only verified paths and symbols.
- Identify patterns to follow, invariants, ordered edits, tests, commands and prohibited changes.
- Use discovery instructions where exact targets remain unknown.
- Generate a task-specific guide; do not rely only on a combined run document.

Exit: Each task is executable without redesign.

## R10 — Per-task validation and refinement

Hard checks per task:
- Stable unique task ID and folder-safe slug.
- Paths and symbols verified.
- Requirement coverage complete.
- Dependency IDs exist.
- No task exceeds configured maximum without split justification.
- All configured task files can be produced.

Run-level hard checks:
- DAG acyclic.
- No two tasks resolve to the same folder.
- No output outside output root.

Semantic review:
- Task outcome clarity.
- Downstream impact coverage.
- Coding-guide usefulness.
- Risk and rollback completeness.
- Folder is self-contained enough for independent handoff.

Maximum three refinement rounds.

## R11 — Materialize per-task folders

1. Resolve the run folder from `output.run_folder_pattern`.
2. Create the configured shared folder and write shared evidence.
3. Resolve one unique directory per task from `output.task_folder_pattern`.
4. Write every configured `output.task_files` entry into each task directory.
5. Run `validate_output_layout.py` against the materialized run folder.
6. Write run-level `task-index.yaml`, `task-dag.mmd` and `RUN-SUMMARY.md` only after all task folders pass.

Required final invariant:

```text
number of task folders == number of task records == number of task-index entries
```

A run is not complete when task content exists only in a combined Markdown or YAML file.
