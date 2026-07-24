# DW Power Distribution v1

## Purpose

DW Power Distribution v1 defines a provider-neutral way to publish GWC, Task Me, UA, and future Powers as skills-only packages. A package is installable without the provider development repository and contains no dashboard, generated task or plan, populated runtime data, secret, or development cache.

## Ownership model

- DW-SuperApps owns the schemas, deterministic builder, portable runtime templates, and reusable publishing workflow.
- Each Power repository owns its explicit distribution recipe and thin caller workflow.
- Consumer applications own runtime data such as `.gwc`, `.ua`, and `.task-me`.
- Release ZIP and `power-dist` must be generated from the same validated staging tree.

## Required package files

```text
POWER.yaml
SOURCE.json
MANIFEST.json
VERSION
bin/install
bin/configure
bin/doctor
bin/uninstall
lib/power_runtime.py
<allowlisted skill source>
```

PowerShell wrappers use the same names with `.ps1`.

`MANIFEST.json` covers every package file except itself. It records path, byte size, SHA-256, and mode. `SOURCE.json` records exact source repository, ref, SHA, recipe API version, and source-date epoch.

## Distribution recipe

A provider recipe uses:

```yaml
apiVersion: dw.superapps/v1
kind: PowerDistribution
metadata:
  id: example
  name: Example Power
spec:
  source:
    repository: owner/example
    defaultRef: main
  package:
    entrypoints:
      - skills/example/SKILL.md
    managedPaths:
      - .agents/skills/example
    runtimeTemplates: true
  include:
    - skills/example/**
    - LICENSE
  exclude:
    - "**/*.tmp"
  forbidden:
    paths:
      - docs/private/**
    contentPatterns: []
  runtime:
    dataRoot: .example
    configRequired: false
```

The builder rejects absolute patterns, parent traversal, symlinks, case-colliding destinations, missing entrypoints, runtime-data paths, dashboards, generated task/plan paths, common secret files, private keys, common cloud tokens, and provider-defined forbidden content.

## Build

```bash
python scripts/power_dist.py validate-recipe \
  --recipe distribution/power-package.yaml

python scripts/power_dist.py build \
  --recipe distribution/power-package.yaml \
  --source . \
  --output dist \
  --version power-main-20260724.1-abcdef0 \
  --source-repository owner/repository \
  --source-ref main \
  --source-sha abcdef0123456789 \
  --source-date-epoch 1700000000
```

Output:

```text
dist/
├── staging/<power-id>-<version>/
└── assets/
    ├── <power-id>-<version>.zip
    └── <power-id>-<version>.zip.sha256
```

Rebuilding from the same source tree, recipe, version, source SHA, and source-date epoch must produce the same archive hash.

## Portable runtime

From an extracted package:

```bash
./bin/install --target /path/to/application
./bin/configure --target /path/to/application \
  --config /path/to/config.yaml \
  --contract /path/to/consumer-contract.yaml
./bin/doctor --target /path/to/application --require-config
./bin/uninstall --target /path/to/application
```

The runtime:

- installs under `<consumer>/.dw/powers/<power-id>`;
- creates an empty consumer-owned runtime root;
- refuses unmanaged overwrite or deletion;
- keeps the previous managed installation in `.dw/history/<power-id>`;
- verifies every manifest file and entrypoint;
- preserves runtime data on uninstall;
- removes runtime data only when both `--include-runtime` and `--yes` are supplied.

## Publishing workflow

Provider repositories call `.github/workflows/reusable-publish-power.yml` by immutable DW-SuperApps commit. The workflow:

1. checks out provider source;
2. checks out the pinned DW distribution foundation;
3. validates the recipe;
4. builds a deterministic staging tree and ZIP;
5. verifies the manifest;
6. smoke-installs and runs doctor;
7. uploads release assets;
8. optionally publishes the GitHub Release;
9. updates `power-dist` using normal fast-forward history.

The generated branch is not a governance source of truth. Source repository commits, release assets, checksums, and manifests remain the evidence.

## Consumer binding

A consumer binding is separate from provider configuration. Configuration controls how a Power runs. The binding controls where it may read/write, which hosts may discover it, whether networking is allowed, and whether external writes are allowed.

Installation never implies permission to create branches, PRs, Jira issues, Slack messages, deployments, approvals, or GWC gate transitions.
