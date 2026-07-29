# Task Me host mode

Task Me host mode lets the Task Me distribution run as a skills-only planning source for an external DW SUPER app or superproject.

## Boundary

Task Me has two roots in host mode:

- **package root**: the installed Task Me package or source checkout.
- **host root**: the consumer-owned superproject that contains `.ua`, `.task-me`, source documents, and generated planning output.

The package root and host root must be different paths. Task Me writes only under the configured host output root.

## Validate a host

```bash
python3 scripts/task-me-host.py validate \
  --package-root /path/to/task-me \
  --host-root /path/to/superproject \
  --config .task-me/task-architect.yaml
```

The validator resolves:

- `package_root`
- `host_root`
- `config`
- `ua_root`
- `output_root`
- `runtime_root`

It rejects absolute or relative paths that escape the host root.

## Minimal host-owned config

```yaml
schemaVersion: "1.0"
folderMode: per_task
repositoryRoot: .
knowledgeRoot: .ua
outputRoot: .ua/generated/task-plans
runtimeRoot: .task-me
inputs:
  requirements: []
  designs: []
  systemGraphs: []
  sourceRoots: []
  testRoots: []
output:
  taskFolderPattern: "tasks/{task_id}-{slug}"
  taskFiles:
    - task.yaml
    - README.md
    - impact-analysis.md
    - implementation-plan.md
    - coding-guide.md
    - test-plan.md
    - evidence.json
    - decisions.md
```

## Non-goals

Host mode does not start the dashboard, create Jira tasks, open pull requests, deploy, migrate data, or modify product source.
