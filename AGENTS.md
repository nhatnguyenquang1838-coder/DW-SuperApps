# DW SuperApps Agent Routing

This repository is an orchestration workspace for multiple AI hosts, reusable Powers, model providers, and product systems.

## Discovery

1. Read `workspace.yaml`.
2. Resolve the target system under `systems/`.
3. Load only the Powers enabled for that system.
4. Treat each Power repository as independently versioned source.
5. Keep generated and runtime data inside the owning system repository.

## Working-project rule

Treat `DW-SuperApps` as an executable control project, not as documentation-only reference material.

When the user asks to set up, onboard, install, activate, validate, repair, or use DW Powers, the agent MUST execute the applicable lifecycle end to end:

```text
DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT
```

Do not stop after describing commands when the current environment provides the required repository and filesystem capabilities. Do not claim readiness when only part of the lifecycle is complete.

## Power Dist onboarding

### Trigger

Apply this section when the request contains intent such as:

- set up DW SUPER for a project;
- install or update GWC, UA, Task Me, BMAD, or all enabled Powers;
- validate Power Dist installation;
- make a Power usable by Codex, Kiro, GitHub Copilot, Claude Code, Cline, Kilo Code, or a custom agent;
- doctor or repair an existing `.dw/powers` installation;
- install manually copied local distribution ZIPs when GitHub or network access is unavailable.

### Required outcome

A successful onboarding must leave the target project with:

1. the requested Power packages installed under `.dw/powers/<power-id>/`;
2. package identity and manifest hashes validated;
3. the consumer-owned runtime root created;
4. required configuration and consumer contracts installed when applicable;
5. the selected host able to discover the installed Power;
6. Power and host doctor checks passing;
7. an evidence report showing exact source, version, paths, commands, and results.

Package installation alone is not sufficient. Host discovery alone is not sufficient. Both must be validated.

### Defaults and input resolution

Resolve inputs without asking for information already available in the repository.

1. **Workspace root:** the current `DW-SuperApps` checkout.
2. **Target system:**
   - use the system explicitly named by the user;
   - otherwise use the system containing the requested target path;
   - otherwise, when exactly one enabled system exists in `workspace.yaml`, use that system;
   - otherwise report `BLOCKED_TARGET_AMBIGUOUS`.
3. **Target project path:** use the system `path` from `workspace.yaml`, unless the user provides an external consumer path.
4. **Powers:**
   - use the explicit requested list;
   - otherwise use the target system's `enabled_powers`;
   - never install a Power not enabled for the resolved system unless the user explicitly requests it.
5. **Host:** use the explicitly named host; otherwise detect the active host from repository folders or the execution environment. If detection remains ambiguous, activate all configured hosts only when the user requested full setup.
6. **Distribution source:**
   - when the user supplies a local package path, requests offline/local/manual ZIP onboarding, or GitHub access is unavailable, use `package` and the local package only;
   - otherwise use `auto` after validating the Power manifest; `auto` resolves `spec.distribution.defaultMode`.

### Source-of-truth order

Read and reconcile these sources before making changes:

1. current local checkout and exact local HEAD;
2. root `AGENTS.md`;
3. `workspace.yaml`;
4. target system `AGENTS.md` when present;
5. `manifests/powers/<power-id>.yaml`;
6. `manifests/power-distribution-evidence.json` when present;
7. local inbox ZIP/checksum and its internal `MANIFEST.json` when offline packages are supplied;
8. installed package `MANIFEST.json` when present;
9. applicable runtime and Power documentation.

When repository connectivity is available, verify the current default branch and exact `main` SHA. When connectivity is explicitly unavailable, do not block local package onboarding merely because remote state cannot be queried; report remote verification as `SKIPPED_OFFLINE` and rely on the local control checkout, package checksum, and package manifest.

Repository state, package manifests, release checksums, and recorded evidence are authoritative. Conversation memory and Slack messages are not authoritative.

If local manifest state, publication evidence, supplied package identity, checksum, or documentation disagree, report `BLOCKED_DISTRIBUTION_DRIFT`. Do not silently choose whichever source is convenient.

### Preflight

Before installation, the agent MUST:

1. identify OS, shell, Python executable, Git availability, network/GitHub availability, and selected host;
2. verify the target path is correct and writable;
3. inspect existing `.dw/powers/<power-id>/`, `.dw/history/<power-id>/`, `.dw/inbox/powers/`, host adapters, configuration, and runtime roots;
4. preserve consumer runtime data by default;
5. verify required provider state is `published` for `release` or `power-dist` consumption;
6. for local package consumption, verify the ZIP, sidecar checksum, package identity, version, and internal manifest instead of requiring remote provider access;
7. verify Node.js and npm before BMAD bootstrap;
8. detect dirty or unmanaged paths and refuse unsafe overwrite;
9. record the pre-install state for the final report.

Do not initialize Power submodules during normal Power Dist or offline package onboarding. Submodules are migration and recovery fallbacks only.

### Install commands

Run package lifecycle commands from the `DW-SuperApps` root.

#### Bash, Zsh, Linux, macOS, or Git Bash

```bash
./bin/dw power install <power-id> \
  --source auto \
  --target <target-project>

./bin/dw power doctor <power-id> \
  --target <target-project>
```

When the global launcher has already been installed, `dw` may replace `./bin/dw`.

#### Windows PowerShell

First probe whether the current wrapper supports package lifecycle dispatch. If it does not, use the direct consumer runtime entrypoint.

```powershell
# Preferred when supported
.\dw.ps1 power install <power-id> --source auto --target <target-project>
.\dw.ps1 power doctor <power-id> --target <target-project>

# Required fallback for repository versions whose dw.ps1 does not dispatch package commands
py -3 .\scripts\dw_power_package.py install <power-id> `
  --source auto `
  --target <target-project>

py -3 .\scripts\dw_power_package.py doctor <power-id> `
  --target <target-project>
```

Do not report the Power as failed merely because one launcher is unsupported when the repository-provided direct entrypoint works.

### Source selection rules

Supported consumer sources are:

| Source | Use |
|---|---|
| `package` | Highest priority when the user provides a local ZIP/path, requests offline installation, or GitHub access is unavailable. |
| `auto` | Preferred only when no local package override applies. Resolve the current manifest default after provider-state validation. |
| `release` | Preferred for immutable online consumption. Exact version and checksum are required. |
| `power-dist` | Use for the current validated distribution branch when mutable-channel consumption is intended. |
| `submodule` | Recovery or migration fallback only. Never silently substitute it for a blocked distribution. |

For `release`, derive the version from current publication evidence or an exact verified release. Do not hard-code a stale version into reusable automation.

For `package`, require `MANIFEST.json`; verify every declared file size and SHA-256; require the external checksum for automatically discovered inbox ZIPs; reject absolute paths, parent traversal, and archive symlinks.

### Offline ZIP inbox contract

Use this contract when the user manually copies distribution packages because GitHub, `gh`, release download, or outbound network access is blocked.

#### Recommended consumer structure

Place each immutable Power ZIP and its sidecar checksum under the target project, outside the managed installation directory:

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
│   ├── config/                 # managed consumer config when applicable
│   └── history/                # managed rollback history
├── .gwc/
├── .ua/
├── .task-me/
└── .bmad/
```

Do not manually extract or copy package contents into `.dw/powers/`. `.dw/powers/` is owned by the installer. The user-managed drop zone is `.dw/inbox/powers/`.

#### Inbox discovery

For every requested Power, the agent MUST:

1. scan `<target-project>/.dw/inbox/powers/<power-id>/`;
2. find exactly one candidate ZIP and its matching `.zip.sha256` sidecar;
3. when filenames are unconventional, identify the package from the internal `MANIFEST.json`, not from the filename alone;
4. verify that `MANIFEST.json.metadata.powerId` matches the requested Power;
5. verify the external archive checksum before extraction;
6. verify every file declared by the internal manifest;
7. install with `--source package --package <zip> --checksum <sidecar>`;
8. leave the inbox ZIP and checksum unchanged after installation so they remain available for audit or reinstall;
9. run package doctor, host activation, host doctor, and actual invocation validation;
10. record the local package path and checksum in the completion evidence.

If no valid local package exists, report `BLOCKED_LOCAL_PACKAGE_MISSING`. If multiple candidates exist and no exact package was named by the user, report `BLOCKED_LOCAL_PACKAGE_AMIGUOUS`. If the sidecar is absent or invalid, report `BLOCKED_LOCAL_CHECKSUM_MISSING` or `BLOCKED_LOCAL_CHECKSUM_INVALID`.

#### No-network rule

When local/offline/manual-package mode applies, the agent MUST NOT run:

- `git pull`, `git fetch`, `git clone`, or submodule initialization for Power acquisition;
- `gh release download` or other GitHub API acquisition;
- `curl`, `wget`, or release/power-dist URL downloads;
- `--source auto`, `--source release`, or `--source power-dist` for the supplied Power;
- any fallback that replaces the supplied local package with a repository checkout.

Git may still be used locally for read-only inspection of the existing checkout or for separately authorized repository changes. Lack of GitHub connectivity is not a blocker when a valid local package and checksum are present.

#### Offline package commands

Bash/Zsh/Git Bash:

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

### Configuration and consumer contracts

After installation:

1. inspect the installed package manifest and distribution directories;
2. determine whether configuration is required;
3. use target-owned configuration and consumer contracts;
4. never place real secrets in repository configuration;
5. never invent credentials or external authority;
6. run `power configure` only with verified inputs;
7. rerun doctor with `--require-config` when configuration is mandatory.

Generic form:

```bash
dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target <target-project>
```

If configuration is optional and absent, report `configuration: optional-missing`, not failure.

### Host activation contract

The canonical Power implementation remains in:

```text
<target-project>/.dw/powers/<power-id>/
```

Host adapters must remain thin discovery layers. They must not copy Power logic, schemas, runtime data, task records, plans, dashboards, or generated evidence.

`dw host install` configures workspace-level adapters. It MUST NOT be treated as proof that an independently installed consumer package is activated. For a consumer target, validate that the host adapter resolves the target's `.dw/powers/<power-id>/MANIFEST.json` and a declared entrypoint.

Host locations:

| Host | Consumer adapter root |
|---|---|
| Kiro | `.kiro/skills/<power-id>/SKILL.md` |
| Codex | `.codex/skills/<power-id>/SKILL.md` |
| GitHub Copilot | `.github/skills/<power-id>/SKILL.md` |
| Claude Code | `.claude/skills/<power-id>/SKILL.md` |
| Custom agent | `.agents/skills/<power-id>/SKILL.md` |
| Cline | `.clinerules/` instruction file |
| Kilo Code | `.kilo/rules/` instruction file |

Activation order:

1. use a package-native host bootstrap when the package declares one;
2. otherwise generate a thin adapter that tells the host to:
   - read the target project's instructions;
   - read `.dw/powers/<power-id>/MANIFEST.json`;
   - select the first existing declared entrypoint;
   - write runtime data only to the manifest's consumer runtime root;
   - never modify the managed package during consumer use;
3. refuse to overwrite unmanaged host instructions;
4. mark generated adapters so they can be safely refreshed or removed;
5. validate the exact adapter path and canonical entrypoint after generation.

### BMAD handling

BMAD is a release-first, skills-only external Power and requires its package-native bootstrap to render the selected host integration.

The agent MUST:

1. verify the exact release or local package and checksum;
2. install and doctor the managed package first;
3. verify Node.js and npm requirements;
4. run `distribution/lib/bootstrap_bmad.py` for the selected host;
5. when the bootstrap safety contract rejects a package located inside the consumer target, copy the already verified package to a temporary directory outside the target, run bootstrap from that verified copy, then remove the temporary copy;
6. validate generated BMAD host files and the `.dw/bmad-bootstrap.json` marker;
7. invoke `bmad-help` as the routing entrypoint.

Do not add the BMAD website, dashboard, repository tests, evals, generated web bundles, or source-repository project data to the consumer project.

### Power-specific runtime ownership

| Power | Canonical consumer runtime root |
|---|---|
| GWC | `.gwc/` |
| Understand Anything | `.ua/` |
| Task Me | `.task-me/` |
| BMAD | `.bmad/`, `_bmad/`, and `_bmad-output/` only as declared by the installed package and selected BMAD modules |

Uninstall preserves consumer runtime by default. Runtime deletion requires explicit destructive authorization and the package runtime's confirmation flags.

### Doctor matrix

For every requested Power, validate all applicable checks:

| Gate | Required check |
|---|---|
| Distribution | Manifest provider state and selected source are valid, or local package mode is explicitly selected. |
| Local package | Offline inbox ZIP and sidecar checksum are present, unambiguous, and valid when package mode applies. |
| Integrity | Package identity, file sizes, and SHA-256 hashes pass. |
| Installation | `.dw/powers/<power-id>/` is managed and contains `.dw-managed.json`. |
| Entrypoint | At least one manifest-declared entrypoint exists. |
| Runtime | Consumer runtime root exists and remains inside the target project. |
| Configuration | Required config and contract are managed and valid. |
| Host | Selected host adapter exists and resolves the installed package. |
| Native bootstrap | Required package-specific bootstrap marker and generated files exist. |
| Workspace | `dw validate` passes when running inside DW-SuperApps. |
| Safety | No secrets, traversal, unmanaged overwrite, dashboard, task, plan, or generated-source contamination. |
| Network discipline | No remote acquisition command was used during offline/local-package mode. |

Use these statuses consistently:

- `READY`: installation, activation, and doctor all pass;
- `PARTIAL`: package is valid but configuration, native bootstrap, or host activation remains incomplete;
- `BLOCKED`: a required dependency, authority, package, checksum, target, or safety condition prevents completion;
- `FAILED`: an executed validation completed and returned a real failure.

Never convert `PARTIAL` or `BLOCKED` into `READY` to simplify reporting.

### Use after onboarding

Before executing a Power task:

1. resolve the target system and confirm the Power is enabled;
2. read the target project instructions;
3. read the installed package manifest;
4. read the first existing canonical skill entrypoint;
5. keep outputs in the target-owned runtime root;
6. follow the Power's authority boundaries;
7. record evidence in the owning repository before publishing external notifications.

Power routing:

- **GWC:** governance state, gate workflow, approval boundaries, delivery control, and validation orchestration.
- **UA:** semantic analysis, architecture discovery, dependency mapping, and knowledge generation.
- **Task Me:** impact analysis, implementation planning, task decomposition, coding guidance, and validation planning.
- **BMAD:** structured product analysis, planning, architecture, implementation, and review procedures; use `bmad-help` to route the lifecycle.

A Power installation does not grant GitHub write, Jira write, Slack, deployment, merge, approval, or production authority. Those capabilities remain separately governed.

### Required completion report

Return a compact evidence table:

| Power | Source | Package path | Version/SHA | Install | Config | Host | Doctor | Runtime | Status |
|---|---|---|---|---|---|---|---|---|---|

Also include:

- target system and absolute target path;
- detected OS, shell, Python, Node/npm when applicable, host, and network mode;
- exact commands executed with secrets removed;
- created or changed paths;
- validation results;
- unresolved risks or blockers;
- rollback or uninstall command;
- confirmation that runtime data was preserved;
- confirmation that local inbox files were preserved;
- confirmation that no remote acquisition command ran in offline mode;
- confirmation that no dashboard, task, plan, secret, or unrelated source content was installed.

### Canonical one-prompt onboarding request

Agents must recognize and execute the following request without requiring the user to restate the lifecycle:

```text
Onboard DW SUPER Power Dist for the current target system and active host.

Treat `DW-SuperApps` as the working control project and repository state as the source of truth.

Read and follow the latest root `AGENTS.md`. Resolve the target system from `workspace.yaml`, then install or update all Powers enabled for that system using their validated distribution defaults.

Execute the complete lifecycle:

DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT

Requirements:

- Use a local validated package when an explicit package path is provided, a valid package is present in the target `.dw/inbox/powers/<power-id>/`, offline/manual ZIP mode is requested, or GitHub access is unavailable.
- In local/offline mode, use `--source package` with the local ZIP and sidecar checksum. Do not run Git pull/fetch/clone, GitHub release download, release URLs, power-dist branch download, or submodule initialization for Power acquisition.
- Otherwise use Power Dist or immutable release according to the current Power manifests and publication evidence.
- Do not silently fall back to submodules.
- Install packages under the target project's `.dw/powers/` and never manually extract package content there.
- Configure required consumer configuration and contracts.
- Activate the current host against the installed consumer packages.
- Run complete package, local checksum, runtime, entrypoint, configuration, native-bootstrap, host, and workspace doctor checks.
- Repair safe setup issues when possible.
- Validate one real Power invocation for each installed Power.
- Preserve existing `.gwc`, `.ua`, `.task-me`, `.bmad`, `_bmad`, and `_bmad-output` runtime data.
- Preserve local ZIP and checksum files in `.dw/inbox/powers/`.
- Do not install dashboards, project tasks, generated plans, secrets, tests, evals, or unrelated source content.
- Do not claim READY when package installation succeeds but host activation or doctor remains incomplete.
- Do not stop after providing instructions. Perform every available setup and validation action now.

Return:

- resolved target system and absolute project path;
- detected OS, shell, Python, Node/npm where applicable, active host, and online/offline mode;
- exact installed Power versions, source SHAs, local package paths, and archive checksums;
- installation, configuration, host activation, doctor, and invocation results;
- created or changed paths;
- sanitized commands executed;
- rollback and uninstall commands;
- unresolved blockers and risks;
- one evidence table with READY, PARTIAL, BLOCKED, or FAILED status for every Power.
```

### Canonical offline ZIP one-prompt request

Use this exact request when the distribution ZIPs have been copied manually and GitHub access is blocked:

```text
Onboard DW SUPER from local Power ZIPs for the current target system and active host.

GitHub and outbound package acquisition are unavailable. Treat the existing local `DW-SuperApps` checkout as the control project. Read and follow its root `AGENTS.md` and resolve the target from `workspace.yaml`.

For every enabled Power, search only in:

<target-project>/.dw/inbox/powers/<power-id>/

Require exactly one valid ZIP and matching `.zip.sha256` file per requested Power. Verify the archive checksum, package identity, internal `MANIFEST.json`, every declared file hash, entrypoints, and runtime root.

Install with `--source package --package <local-zip> --checksum <local-sidecar>`. Do not run git pull, git fetch, git clone, GitHub API or release download, curl, wget, power-dist download, or submodule initialization for Power acquisition. Do not replace the local package with a repository checkout.

Install into `.dw/powers/<power-id>/`, configure required consumer contracts, activate the current host, run complete package and host doctor checks, execute one real invocation per Power, and repair only safe setup issues.

Preserve the inbox ZIP/checksum files and all existing runtime data. Do not install dashboards, tasks, plans, tests, evals, secrets, or unrelated source content.

Return exact local package paths, checksums, versions, installed paths, host adapters, commands, doctor evidence, rollback commands, and READY/PARTIAL/BLOCKED/FAILED status for each Power. Do not stop after describing commands; perform all available local setup and validation actions now.
```

## Power roles

- `powers/gwc`: governance and delivery workflows.
- `powers/ua`: semantic/codebase knowledge generation and query.
- `powers/task-me`: impact analysis and implementation task planning.
- `bmad` distribution: structured analysis-to-implementation delivery workflows packaged from pinned external BMAD source.

## Host neutrality

Supported hosts include Kiro, Codex, GitHub Copilot, Cline, Kilo Code, Claude Code, and generic/custom agents. Host-specific folders expose only thin discovery adapters. They must not duplicate Power logic, schemas, or runtime data.

`bionics`, `biotic`, and `ollama` are accepted aliases for the generic `custom` host. Ollama itself is a model provider, not a host; its OpenAI-compatible endpoint is registered separately.

## Model providers

Local Ollama compatibility uses:

- Base URL: `http://localhost:11434/v1`
- API key placeholder: `ollama`
- Model override: `OLLAMA_MODEL`

Provider configuration must not contain real secrets.

## Cross-repository work

A change affecting multiple systems must identify every impacted repository explicitly. Do not assume one repository approval, branch, task, or validation result applies to another repository.

For repository changes:

1. verify repository, default branch, exact base SHA, and target file state before writing;
2. use a dedicated branch;
3. never write directly to a protected default branch;
4. review the complete diff;
5. run applicable validation;
6. create a reviewable pull request unless the user explicitly requested local-only changes;
7. do not merge, deploy, or perform production operations without separate authority.

## Slack Notification Behavior

Slack is an optional notification channel for execution visibility.

Slack is used for:

- Gate transition updates
- Blocker notifications
- Important milestone notifications
- Human visibility of agent execution

Slack is NOT:

- The governance source of truth
- The task state store
- The approval authority

## Gate Event Rule

After important execution events, the agent should:

1. Confirm or update the current task state.
2. Record evidence and audit information.
3. Send Slack notification when Slack capability is available.
4. Continue execution if Slack is unavailable.

Important events include:

- Task started
- Gate started
- Gate completed
- Gate blocked
- PR created
- CI validation completed
- Approval requested
- Human override
- Task completed

## Slack Failure Handling

Slack availability must never block work.

If Slack is unavailable:

- Continue the workflow.
- Record or mention that notification was skipped.
- Keep the execution result unchanged.
