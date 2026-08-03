---
name: implementation-task-architect
description: Analyze repository-local requirements, designs, architecture documents, system graphs, source code and tests to generate evidence-backed implementation tasks with impact analysis, complexity, effort estimates, dependencies and detailed coding guidance. Use for implementation planning and task decomposition. Every generated task plan must be written into its own output folder. Do not use to modify application code, run Git delivery, or publish to external task systems.
---

# Implementation Task Architect

## Operating boundary

Work entirely from the current repository. Do not require MCP or external services.

Read `.task-architect/config.json` first. It is the single owner-managed path configuration.

Allowed outcomes:

- Read configured repository files.
- Run bundled read-only analysis scripts.
- Write canonical planning knowledge under `.ua/extensions/` and generated planning views only under `output.root`.
- Materialize exactly one self-contained output folder for every task plan.

Forbidden outcomes:

- Do not edit application source, tests, requirements or design files.
- Do not create branches, commits or pull requests.
- Do not call external task systems.
- Do not invent files, symbols, dependencies or architecture components.
- Do not combine multiple canonical task plans into one folder or one canonical plan file.

## Required runbook

1. Validate configuration, output boundary and `folder_mode=per_task`.
2. Expand configured globs and create the source inventory.
3. Read every matched requirements, design, system-graph and repository-context document.
4. Inspect code and tests in bounded batches. Build a repository manifest and lightweight dependency evidence.
5. Normalize requirement, acceptance-criterion and design-decision identifiers.
6. Create requirement-to-code trace candidates using explicit names, lexical matches, structural dependencies and tests.
7. Verify candidate paths and symbols against the repository.
8. Build the evidence graph and classify direct, transitive, contract, data, test and operational impact.
9. Decompose the change using the rules in `references/task-decomposition.md`.
10. Assign every task a stable ID and a filesystem-safe unique slug.
11. Build and validate the task dependency DAG.
12. Calculate complexity, risk and three-point effort estimates.
13. Generate detailed coding guidance from verified repository patterns.
14. Validate every task independently against the quality rubric.
15. Refine failed task sections only, for at most three evaluation rounds.
16. Update `.ua/extensions/planning-graph.json` and `.ua/extensions/traceability-graph.json` before materializing derived task folders.
17. Create the run folder, shared-evidence folder and one folder per task using the configured patterns.
18. Write each task's canonical `task.yaml` and required companion files into that task's folder.
19. Validate task-folder completeness, then write `task-index.yaml`, `task-dag.mmd` and `RUN-SUMMARY.md`.

## Per-task folder invariant

For each task `T`, there must be exactly one directory resolved from `output.task_folder_pattern`.

That folder must contain all configured `output.task_files`. The canonical record is `task.yaml`. Run-level or shared files may reference the task, but must not replace its folder.

Each task folder must include enough local context to hand the task to an implementation agent independently:

- task identity and objective;
- requirement/design traceability;
- task-specific impact subset;
- ordered implementation plan;
- detailed coding guide;
- test plan and validation commands;
- dependency IDs and delivery wave;
- complexity, risk and effort;
- task-specific evidence and observable decisions.

## Blocking rules

Return a structured blocked result when:

- Required configured paths match no files.
- Requirements or design are contradictory and materially affect task scope.
- A proposed implementation target cannot be verified.
- The evidence graph is insufficient to distinguish implementation from discovery.
- The output path is outside the configured repository boundary.
- Two tasks resolve to the same output folder.
- A required task file is missing after materialization.

Create a discovery task when uncertainty can be resolved through bounded repository investigation. A discovery task follows the same one-folder-per-task contract.

## Observable decision record

Do not expose private chain-of-thought. Persist concise, reviewable decision records in each task folder instead:

- evidence used;
- alternatives considered;
- rule applied;
- decision made;
- confidence;
- unresolved uncertainty.

## References

Load only when entering the related stage:

- `references/runbook.md`
- `references/evidence-model.md`
- `references/task-decomposition.md`
- `references/estimation.md`
- `references/output-contract.md`
