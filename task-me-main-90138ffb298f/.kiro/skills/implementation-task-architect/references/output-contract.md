# Output Contract

## Core invariant

Every task plan is a directory, not merely a section in a combined document.

For every task record with stable ID `task_id`, resolve exactly one unique folder from:

```text
<output.root>/<run_folder_pattern>/<task_folder_pattern>
```

The configured task folder pattern must contain `{task_id}` and `{slug}`.

## Run structure

```text
<output.root>/<run-id>/
├── task-index.yaml
├── task-dag.mmd
├── RUN-SUMMARY.md
├── <shared-folder>/
│   ├── source inventory
│   ├── traceability
│   ├── evidence graph
│   ├── run impact analysis
│   └── validation report
└── tasks/
    └── <task-id>-<slug>/
        ├── task.yaml
        ├── README.md
        ├── impact-analysis.md
        ├── implementation-plan.md
        ├── coding-guide.md
        ├── test-plan.md
        ├── evidence.json
        └── decisions.md
```

## Required task content

Each task folder must include:

- ID and title;
- objective;
- requirement and design traceability;
- included and excluded scope;
- verified task-specific impact;
- ordered implementation plan;
- detailed coding guide;
- tests and validation commands;
- dependencies and delivery wave;
- complexity, risk and effort;
- assumptions, confidence and unresolved items;
- measurable definition of done;
- task-specific evidence subset;
- observable decision records.

## Canonical and derived files

- `task.yaml` is the canonical machine-readable record for a task.
- `README.md` is the task handoff entry point.
- Other Markdown files separate detailed concerns so an implementation agent can load only what it needs.
- `evidence.json` contains a task-specific subset even when the full evidence graph also exists in the shared folder.
- Run-level indexes are derived views. They are not canonical task plans.

## Independence requirement

A task folder must remain understandable when copied without sibling task folders. It may reference stable requirement/design IDs and shared evidence IDs, but it must summarize all evidence necessary to understand and implement that task.

## Validation invariants

```text
one task ID -> one folder
one folder -> one task.yaml
all folder paths unique
all required files present
all dependencies refer to known task IDs
no output escapes output.root
```

The run must also produce the configured shared evidence and run-level index files.
