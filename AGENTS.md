# DW SuperApps Agent Routing

DW SuperApps is an executable control workspace for reusable AI Powers, product systems, model providers, and multiple agent hosts. Treat it as a working project, not as documentation-only reference material.

## Discovery

1. Read `workspace.yaml`.
2. Resolve the target system under `systems/`.
3. Load only the Powers enabled for that system.
4. Read the target system `AGENTS.md` when present.
5. Read each selected `manifests/powers/<power-id>.yaml`.
6. Keep generated and runtime data inside the owning target system.

## Power roles

- `gwc`: governance, gate workflow, approvals, delivery control, and validation orchestration.
- `ua`: semantic/codebase analysis, architecture graph, dependency mapping, and project knowledge.
- `task-me`: impact analysis, implementation planning, task decomposition, coding guidance, and validation planning.
- `bmad`: structured product analysis, planning, architecture, implementation, and review lifecycle.

## Working-project onboarding rule

When the user asks to set up, onboard, install, update, activate, validate, doctor, repair, or use DW Powers, execute the complete lifecycle:

```text
DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT
```

Do not stop after describing commands when the current environment provides the required repository and filesystem access. Do not claim readiness when package installation, host activation, or doctor validation remains incomplete.

## Resolve onboarding inputs

Resolve available information instead of asking the user to repeat it.

1. **Workspace:** current `DW-SuperApps` checkout.
2. **Target system:** explicit user target; otherwise the matching `workspace.yaml` system; otherwise the only enabled system; otherwise `BLOCKED_TARGET_AMBIGUOUS`.
3. **Target path:** system `path`, unless the user explicitly supplies an external consumer path.
4. **Powers:** explicit list; otherwise the target system's `enabled_powers`.
5. **Host:** explicit host; otherwise detect the active host. Activate all configured hosts only when full multi-host setup was requested.
6. **Source priority:**
   - explicit local package path;
   - valid local inbox ZIP when offline/manual package mode applies;
   - manifest `defaultMode` through `--source auto` when online;
   - submodule only for explicitly requested migration or recovery.

Never silently replace a supplied local package with a Git checkout, release download, `power-dist` archive, or submodule.

## Source of truth

Read and reconcile:

1. local checkout and exact local HEAD;
2. root and target `AGENTS.md` files;
3. `workspace.yaml`;
4. selected Power manifests;
5. `manifests/power-distribution-evidence.json` when present;
6. supplied ZIP/checksum and its internal `MANIFEST.json`;
7. existing `.dw/powers/<power-id>/MANIFEST.json`;
8. applicable runtime documentation.

When online, verify current default branch and exact `main` SHA. When GitHub connectivity is explicitly unavailable, record remote verification as `SKIPPED_OFFLINE`; do not block installation when the local control checkout and valid local packages are available.

If identity, version, checksum, manifest, entrypoints, or recorded evidence conflict, report `BLOCKED_DISTRIBUTION_DRIFT`.

## Preflight

Before installation:

1. detect OS, shell, Python, Git, network/GitHub availability, active host, and Node/npm when BMAD is selected;
2. verify the target path exists or can be created and is writable;
3. inspect `.dw/inbox/powers`, `.dw/powers`, `.dw/config`, `.dw/history`, host adapters, and runtime roots;
4. preserve consumer runtime data by default;
5. refuse to overwrite unmanaged installation, configuration, or host files;
6. record the pre-install state for the final evidence report.

Do not initialize Power submodules during normal Power Dist or offline ZIP onboarding.

## Online Power installation

From the `DW-SuperApps` root:

### Bash, Zsh, Linux, macOS, Git Bash

```bash
./bin/dw power install <power-id> --source auto --target <target-project>
./bin/dw power doctor <power-id> --target <target-project>
```

### Windows PowerShell

Probe `dw.ps1`. If that wrapper does not dispatch package lifecycle commands, use the repository-provided Python entrypoint.

```powershell
# Preferred when supported
.\dw.ps1 power install <power-id> --source auto --target <target-project>
.\dw.ps1 power doctor <power-id> --target <target-project>

# Required compatibility fallback
py -3 .\scripts\dw_power_package.py install <power-id> `
  --source auto `
  --target <target-project>

py -3 .\scripts\dw_power_package.py doctor <power-id> `
  --target <target-project>
```

A launcher compatibility failure is not a Power failure when the direct runtime entrypoint succeeds.

## Offline ZIP inbox contract

Use this contract when the user manually copies distribution ZIPs or GitHub/package download access is blocked.

### Recommended structure

Place packages in the target project, outside the managed installation directory:

```text
<target-project>/
├── .dw/
│   ├── inbox/
│   │   └── powers/
│   │       ├── gwc/
│   │       │   ├── gwc-<version>.zip
│   │       │   └── gwc-<version>.zip.sha256
│   │       ├── ua/
│   │       │   ├── ua-<version>.zip
│   │       │   └── ua-<version>.zip.sha256
│   │       ├── task-me/
│   │       │   ├── task-me-<version>.zip
│   │       │   └── task-me-<version>.zip.sha256
│   │       └── bmad/
│   │           ├── bmad-<version>.zip
│   │           └── bmad-<version>.zip.sha256
│   ├── powers/                 # managed installation; agent writes here
│   ├── config/                 # managed consumer configuration
│   └── history/                # managed rollback history
├── .gwc/
├── .ua/
├── .task-me/
└── .bmad/
```

The user-managed drop zone is `.dw/inbox/powers/`. Never manually extract or copy package contents into `.dw/powers/`; that directory is owned by the installer.

### Offline discovery and installation

For each selected Power:

1. scan `<target-project>/.dw/inbox/powers/<power-id>/`;
2. require exactly one candidate ZIP and matching `.zip.sha256` sidecar, unless the user named an exact path;
3. identify unconventional filenames using the internal `MANIFEST.json`, not the filename alone;
4. verify `MANIFEST.json.metadata.powerId` matches the requested Power;
5. verify the archive sidecar checksum before extraction;
6. verify every file size and SHA-256 declared by the internal manifest;
7. reject absolute paths, parent traversal, archive symlinks, unmanaged overwrite, and identity mismatch;
8. install with `--source package --package <zip> --checksum <sidecar>`;
9. preserve the inbox ZIP and checksum after installation;
10. continue through configuration, activation, doctor, and real invocation validation.

Use these blockers:

- `BLOCKED_LOCAL_PACKAGE_MISSING`
- `BLOCKED_LOCAL_PACKAGE_AMBIGUOUS`
- `BLOCKED_LOCAL_CHECKSUM_MISSING`
- `BLOCKED_LOCAL_CHECKSUM_INVALID`
- `BLOCKED_PACKAGE_IDENTITY_MISMATCH`

### Offline commands

Bash, Zsh, or Git Bash:

```bash
./bin/dw power install <power-id> \
  --source package \
  --package "<target-project>/.dw/inbox/powers/<power-id>/<package>.zip" \
  --checksum "<target-project>/.dw/inbox/powers/<power-id>/<package>.zip.sha256" \
  --target "<target-project>"

./bin/dw power doctor <power-id> --target "<target-project>"
```

Windows PowerShell:

```powershell
py -3 .\scripts\dw_power_package.py install <power-id> `
  --source package `
  --package "<target-project>\.dw\inbox\powers\<power-id>\<package>.zip" `
  --checksum "<target-project>\.dw\inbox\powers\<power-id>\<package>.zip.sha256" `
  --target "<target-project>"

py -3 .\scripts\dw_power_package.py doctor <power-id> `
  --target "<target-project>"
```

### Offline no-network rule

In local/offline/manual-package mode, do not use the network for Power acquisition. Do not run:

- `git pull`, `git fetch`, `git clone`, or submodule initialization;
- `gh release download` or GitHub API package acquisition;
- `curl`, `wget`, release URLs, or `power-dist` branch downloads;
- `--source auto`, `--source release`, or `--source power-dist` for a Power supplied locally;
- fallback to a Power repository checkout.

Local read-only Git inspection remains allowed. Lack of GitHub connectivity is not a blocker when a valid ZIP and checksum are present.

## Configuration and consumer contracts

After package installation:

1. inspect the package manifest and declared distribution directories;
2. determine whether configuration is required;
3. use target-owned configuration and consumer contracts;
4. never invent secrets, credentials, or external authority;
5. run `power configure` only with verified files;
6. rerun doctor with `--require-config` when configuration is mandatory.

```bash
dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target <target-project>
```

Optional missing configuration is `optional-missing`, not failure.

## Consumer host activation

Canonical Power code remains in:

```text
<target-project>/.dw/powers/<power-id>/
```

Host adapters are thin discovery layers and must not duplicate Power code, schemas, runtime data, task records, plans, dashboards, or generated evidence.

| Host | Consumer adapter location |
|---|---|
| Kiro | `.kiro/skills/<power-id>/SKILL.md` |
| Codex | `.codex/skills/<power-id>/SKILL.md` |
| GitHub Copilot | `.github/skills/<power-id>/SKILL.md` |
| Claude Code | `.claude/skills/<power-id>/SKILL.md` |
| Custom agent | `.agents/skills/<power-id>/SKILL.md` |
| Cline | `.clinerules/` instruction file |
| Kilo Code | `.kilo/rules/` instruction file |

Activation order:

1. use a package-native host bootstrap when declared;
2. otherwise create a generated thin adapter that reads the target instructions, installed `MANIFEST.json`, and first existing declared entrypoint;
3. ensure runtime writes go only to the manifest's target-owned runtime root;
4. never modify the managed package during normal consumer use;
5. refuse to overwrite unmanaged host instructions;
6. validate the exact adapter and canonical entrypoint.

Workspace-level `dw host install` is not proof that an independently installed consumer package is activated.

## BMAD handling

BMAD requires its package-native bootstrap.

1. Install and doctor the managed BMAD package first.
2. Verify Node.js and npm requirements.
3. Run `distribution/lib/bootstrap_bmad.py` for the selected host.
4. If bootstrap rejects a package located inside the consumer target, copy the already verified package to a temporary directory outside the target, bootstrap from that verified copy, then remove the temporary copy.
5. Validate generated host files and `.dw/bmad-bootstrap.json`.
6. Use `bmad-help` to route the lifecycle.

Do not install the BMAD website, dashboard, repository tests, evals, generated web bundles, or source-repository project data.

## Runtime ownership

| Power | Target-owned runtime root |
|---|---|
| GWC | `.gwc/` |
| UA | `.ua/` |
| Task Me | `.task-me/` |
| BMAD | `.bmad/`, `_bmad/`, and `_bmad-output/` only when declared by the installed package/modules |

Uninstall preserves runtime by default. Runtime deletion requires explicit destructive authorization and confirmation flags.

## Doctor matrix

For every selected Power validate:

| Gate | Required result |
|---|---|
| Source | Online distribution is valid, or local package mode is explicitly selected. |
| Local package | ZIP and checksum are present, unambiguous, and valid when offline mode applies. |
| Integrity | Package identity, declared sizes, and SHA-256 hashes pass. |
| Installation | `.dw/powers/<power-id>/` is managed and contains `.dw-managed.json`. |
| Entrypoint | At least one declared entrypoint exists. |
| Runtime | Target-owned runtime root exists and stays inside the target. |
| Configuration | Required config/contract is managed and valid. |
| Host | Adapter exists and resolves the installed package. |
| Native bootstrap | Required package-specific marker and generated files exist. |
| Workspace | `dw validate` passes when applicable. |
| Safety | No secret, traversal, unmanaged overwrite, dashboard, task, plan, or unrelated-source contamination. |
| Network discipline | No remote acquisition command ran during offline mode. |

Use statuses exactly:

- `READY`: install, config when required, activation, doctor, and invocation pass.
- `PARTIAL`: package is valid but config, bootstrap, activation, or invocation remains incomplete.
- `BLOCKED`: a required dependency, authority, package, checksum, target, or safety condition prevents progress.
- `FAILED`: an executed validation returned a real failure.

Never convert `PARTIAL` or `BLOCKED` into `READY`.

## Use after onboarding

Before executing a Power task:

1. confirm the Power is enabled for the target;
2. read target instructions;
3. read the installed package manifest;
4. read the first existing canonical entrypoint;
5. keep outputs in the target-owned runtime root;
6. follow Power authority boundaries;
7. record canonical evidence before external notification.

Installing a Power does not grant GitHub write, Jira write, Slack, deployment, merge, approval, or production authority.

## Required completion report

Return:

| Power | Source | Package path | Version/SHA | Install | Config | Host | Doctor | Runtime | Status |
|---|---|---|---|---|---|---|---|---|---|

Also include target system/path, detected tools and network mode, sanitized commands, changed paths, validation evidence, blockers, rollback/uninstall commands, and confirmations that runtime and inbox packages were preserved.

## Canonical one-prompt onboarding request

Agents must recognize and execute this request without requiring the lifecycle to be restated:

```text
Onboard DW SUPER Power Dist for the current target system and active host.

Treat `DW-SuperApps` as the working control project and repository state as the source of truth.

Read and follow the latest root `AGENTS.md`. Resolve the target system from `workspace.yaml`, then install or update all Powers enabled for that system using their validated distribution defaults.

Execute the complete lifecycle:

DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT

Requirements:

- Use a local validated package when an explicit package path is provided, a valid package is present in the target `.dw/inbox/powers/<power-id>/`, offline/manual ZIP mode is requested, or GitHub access is unavailable.
- In local/offline mode, use `--source package` with the local ZIP and sidecar checksum. Do not run Git pull/fetch/clone, GitHub release download, release URLs, power-dist download, or submodule initialization for Power acquisition.
- Otherwise use Power Dist or immutable release according to current Power manifests and publication evidence.
- Do not silently fall back to submodules.
- Install packages under the target project's `.dw/powers/`; never manually extract package content there.
- Configure required consumer configuration and contracts.
- Activate the current host against the installed consumer packages.
- Run complete package, checksum, runtime, entrypoint, configuration, native-bootstrap, host, workspace, and real-invocation checks.
- Repair safe setup issues when possible.
- Preserve `.gwc`, `.ua`, `.task-me`, `.bmad`, `_bmad`, `_bmad-output`, and local inbox ZIP/checksum files.
- Do not install dashboards, project tasks, generated plans, secrets, tests, evals, or unrelated source content.
- Do not claim READY when any required activation or doctor check remains incomplete.
- Do not stop after providing instructions. Perform every available setup and validation action now.

Return the resolved target and environment, exact versions/source SHAs/package paths/checksums, installation and activation evidence, commands, changed paths, doctor and invocation results, rollback instructions, blockers, and READY/PARTIAL/BLOCKED/FAILED status for every Power.
```

## Canonical offline ZIP one-prompt request

Use this request when ZIPs were copied manually and GitHub access is blocked:

```text
Onboard DW SUPER from local Power ZIPs for the current target system and active host.

GitHub and outbound package acquisition are unavailable. Treat the existing local `DW-SuperApps` checkout as the control project. Read and follow its root `AGENTS.md` and resolve the target from `workspace.yaml`.

For every enabled Power, search only in:

<target-project>/.dw/inbox/powers/<power-id>/

Require exactly one valid ZIP and matching `.zip.sha256` file per requested Power. Verify the archive checksum, package identity, internal `MANIFEST.json`, every declared file hash, entrypoints, and runtime root.

Install with `--source package --package <local-zip> --checksum <local-sidecar>`. Do not run git pull, git fetch, git clone, GitHub API/release download, curl, wget, power-dist download, or submodule initialization for Power acquisition. Do not replace the local package with a repository checkout.

Install into `.dw/powers/<power-id>/`, configure required consumer contracts, activate the current host, run complete package and host doctor checks, execute one real invocation per Power, and repair only safe setup issues.

Preserve inbox ZIP/checksum files and existing runtime data. Do not install dashboards, tasks, plans, tests, evals, secrets, or unrelated source content.

Return exact local package paths, checksums, versions, installed paths, host adapters, commands, doctor evidence, rollback commands, and READY/PARTIAL/BLOCKED/FAILED status for every Power. Do not stop after describing commands; perform all available local setup and validation actions now.
```

## Host neutrality

Supported hosts include Kiro, Codex, GitHub Copilot, Cline, Kilo Code, Claude Code, and generic/custom agents. Host folders expose only thin discovery adapters.

`bionics`, `biotic`, and `ollama` are aliases for `custom`. Ollama is a model provider, not a host.

## Model providers

Local Ollama compatibility:

- Base URL: `http://localhost:11434/v1`
- API key placeholder: `ollama`
- Model override: `OLLAMA_MODEL`

Provider configuration must not contain real secrets.

## Cross-repository work

A multi-repository change must identify every impacted repository. One repository's branch, approval, task, or validation does not authorize another repository.

For repository changes:

1. verify repository, default branch, exact base SHA, and target file;
2. use a dedicated branch;
3. do not write directly to protected `main`;
4. review the complete diff;
5. run applicable validation;
6. create a reviewable PR unless local-only work was explicitly requested;
7. do not merge or deploy without separate authority.

## Slack notification behavior

Slack is an optional visibility channel, not governance truth, task storage, or approval authority.

After important execution events:

1. update canonical task/governance state;
2. record evidence and audit information;
3. notify Slack when available;
4. continue when Slack is unavailable.

Slack failure must never change the execution result or block work.
