# DW SuperApps

DW SuperApps is a host-neutral control workspace for reusable AI Powers, editable project repositories, product systems, model providers, and agent hosts.

## Current workspace model

```text
DW-SuperApps
├── projects/*                 editable project and Power-source repositories
├── manifests/powers/*         logical Power contracts and routing metadata
├── .dw/powers/*               installed, validated Power packages
├── .dw/inbox/powers/*         local/offline package drop zone
├── .dw/cache/*                package cache
├── .dw/history/powers/*       package rollback history
├── .dw/bindings/*             system-to-package bindings
├── host adapter roots         thin workspace-owned native routing
└── <system runtime roots>     .gwc, .ua, .task-me, .bmad
```

The workspace owns Power distributions and host adapters. Each registered system owns its runtime data and project configuration. Normal Power onboarding must not copy Power packages or host skill implementations into the target system.

## Quick start

```bash
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
bash bin/dw install --shell auto --init

dw project list
dw power list
dw system list
dw doctor all
```

## Create another Super Project

Run from an initialized DW-SuperApps checkout:

```bash
dw workspace init ../my-super-project \
  --id my-super-project \
  --name "My Super Project"

cd ../my-super-project
bash bin/dw install --shell auto
```

The initializer copies the governed DW runtime and manifests, creates an empty project registry, prepares the workspace-owned package inbox, and initializes Git. It does not copy product repositories, installed Power packages, runtime data, credentials, or generated host adapters.

To initialize an existing management repository:

```bash
cd existing-super-project
dw workspace init . \
  --id existing-super-project \
  --name "Existing Super Project" \
  --in-place
```

Initialization is non-destructive and refuses to replace an existing `workspace.yaml` or managed runtime path.

## Add a project or system

```bash
dw project add rental-home \
  --repo nhatnguyenquang1838-coder/rental_home \
  --role product \
  --role system \
  --system \
  --enable-powers gwc,ua,task-me,bmad
```

Review and validate:

```bash
git diff -- .gitmodules workspace.yaml
dw project list
dw validate
dw doctor all --offline
```

`dw project add` creates a Git submodule and updates `workspace.yaml`. It does not install a Power package or write project runtime data.

## Install and operate Powers

```bash
dw power list
dw power info gwc
dw power install gwc --source auto --target projects/rental-home
dw power sanity gwc
dw power doctor gwc --target projects/rental-home
```

Required lifecycle:

```text
DISCOVER → PREFLIGHT → INSTALL → CONFIGURE → ACTIVATE → DOCTOR → USE → REPORT
```

The package store and runtime target are separate:

```text
package store   = workspace distribution.storeRoot
runtime target  = selected project/system path
```

Use `--store-root` only for tests or an explicitly external workspace layout. A store root must not overlap or resolve inside the runtime target.

### Offline Power installation

Use offline installation when the package ZIPs and checksum sidecars have already been transferred to the machine. The package inbox belongs to DW-SuperApps; never place offline packages under the target system.

First resolve the target and enabled Powers from the local workspace registry:

```bash
./bin/dw workspace info
./bin/dw power list
```

Each selected Power must have exactly one ZIP and matching checksum sidecar in the workspace inbox:

```text
.dw/inbox/powers/<power-id>/<package>.zip
.dw/inbox/powers/<power-id>/<package>.zip.sha256
```

Install each Power with an explicit package path and runtime target:

```bash
./bin/dw power install <power-id> \
  --source package \
  --package .dw/inbox/powers/<power-id>/<package>.zip \
  --checksum .dw/inbox/powers/<power-id>/<package>.zip.sha256 \
  --target projects/<system-id>
```

The installer verifies the archive checksum, package identity, `MANIFEST.json`, declared file sizes and hashes, entrypoints, runtime root, archive paths, and managed-overwrite safety. It preserves the ZIP and checksum, writes the package to `.dw/powers/<power-id>/`, updates `.dw/bindings/<system-id>/`, and keeps runtime data in the target's declared `.gwc/`, `.ua/`, `.task-me/`, or `.bmad/` root.

After installation, configure only when the package contract requires it, refresh workspace-owned host adapters, and validate without remote acquisition:

```bash
./bin/dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target projects/<system-id>
./bin/dw host install all --mode wrapper
./bin/dw power doctor <power-id> --target projects/<system-id>
./bin/dw validate
./bin/dw doctor all --offline
```

Offline mode must not run Git fetch/clone, release downloads, `curl`, `wget`, remote `power-dist`, or Power submodule initialization. Existing `<system>/.dw/powers/<power-id>` paths are reported as `LEGACY_TARGET_INSTALL` and preserved. For the complete agent workflow and evidence requirements, use [the offline ZIP onboarding prompt](prompts/power-dist/onboard-offline-zip.md) and [the offline installation guide](docs/installation/OFFLINE_INSTALL.md).

## Native Power activation

Power aliases select native host skills. They are not terminal commands.

```text
/dw-gwc      governance, gates, approvals, delivery control, validation
/dw-ua       architecture, semantic analysis, dependency and impact mapping
/dw-task-me  implementation planning, task decomposition, coding guidance
/dw-bmad     product, specification, architecture, implementation, review
```

Example user request:

```text
/dw-gwc Review the delivery scope and prepare the governed execution.
```

The agent must resolve the target system, load the selected installed Power entrypoint, and apply it directly to the remainder of the request. It must not ask the user to run an activation command or generate a copy-and-paste task prompt.

The DW CLI owns installation, configuration, inspection, validation, doctor, history, rollback, and uninstall operations. Task prompt generation is owned by the selected Power/host skill, not by the CLI.

### Understand a Power before using it

Use the offline, manifest-backed help command when you need to know what a Power
does, when it applies, how to invoke it, why it exists, what it produces, and
what authority it does not grant:

```bash
./bin/dw power help gwc
./bin/dw power help ua
./bin/dw power help task-me
./bin/dw power help bmad
```

The shorter discovery alias is also available:

```bash
./bin/dw skill gwc --help
```

These commands are read-only diagnostics. They do not activate a Power, create
a prompt, modify a project, or contact GitHub. To use a Power, invoke its
native host alias after installation:

```text
/dw-gwc      governance, context, intake, preflight, and delivery boundaries
/dw-ua       semantic analysis and project knowledge
/dw-task-me  impact analysis and implementation planning
/dw-bmad     product and software-delivery lifecycle workflows
```

## Hosts, providers, and orchestration

Configured native host families include Kiro, Codex, GitHub Copilot, Cline, Kilo Code, Claude Code, and custom agents. Thin adapters may coexist in the workspace, but each task should resolve one canonical Power entrypoint.

```bash
dw host install all --mode wrapper
dw host status all
dw provider status all
```

OpenClaw ACPX is the configured multi-agent orchestrator. It can route governed work to Codex, Claude, Kiro, and Kilo Code workers. GWC remains the primary governance workflow for registered systems.

Ollama is an OpenAI-compatible model provider, not an agent host. The workspace default endpoint is:

```text
http://localhost:11434/v1
```

Provider configuration must not contain real secrets.

## Current Powers

| Power | Purpose | Runtime root |
|---|---|---|
| GWC | Governance and governed delivery | `.gwc/` |
| Understand Anything | Architecture and semantic codebase knowledge | `.ua/` |
| Task Me | Impact analysis and implementation planning | `.task-me/` |
| BMAD Method | Product and delivery lifecycle workflows | `.bmad/`, `_bmad/`, `_bmad-output/` when declared |

Installing a Power does not grant GitHub write, Jira write, Slack, merge, deployment, approval, or production authority.

## Daily operations

```bash
dw status all
dw sync all
dw doctor all
dw clean all
```

`dw clean all` removes generated adapters and caches only. Runtime data is preserved unless destructive runtime cleanup is explicitly authorized with `--include-runtime --yes`.

## Reports

Generate user-facing Markdown reports from GWC gate artifacts:

```bash
dw report g1 --workspace .gwc/tasks/<task-id>
```

## Installation and operations guides

- [Installation index](docs/installation/README.md)
- [Create a Super Project](docs/installation/CREATE_SUPER_PROJECT.md)
- [Add a project or system](docs/installation/ADD_PROJECT.md)
- [Install Powers](docs/installation/INSTALL_POWERS.md)
- [Power distribution onboarding](docs/runbooks/POWER_DIST_ONBOARDING.md)
- [Portable multi-host routing](docs/PORTABLE_MULTI_HOST_ROUTER.md)
- [Offline installation](docs/installation/OFFLINE_INSTALL.md)
- [Migrate an existing workspace](docs/installation/MIGRATION.md)
- [Troubleshooting](docs/installation/TROUBLESHOOTING.md)

## Safety and authority boundaries

- Repository state, package manifests, checksums, governance artifacts, and audit records are authoritative.
- Never invent credentials, approvals, checksums, package identities, or validation evidence.
- Preserve legacy target installations unless a separate migration or cleanup is authorized.
- Refuse path traversal, archive symlinks, store/runtime overlap, unmanaged overwrite, and package identity mismatch.
- Do not write directly to protected `main`.
- Use a dedicated branch, review the complete diff, run applicable validation, and create a reviewable PR.
- Merge, deployment, release, secrets, migrations, production configuration, and production data require separate authority.

## Child-project independence

Standalone project contracts and direct Power injection without a parent Super Project are tracked separately in GitHub Issue #15. The current Super Project bootstrap keeps package-store ownership in the parent workspace.
