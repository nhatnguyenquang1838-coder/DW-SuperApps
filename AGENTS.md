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
- doctor or repair an existing `.dw/powers` installation.

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
6. **Distribution source:** use `auto` after validating the Power manifest. `auto` resolves `spec.distribution.defaultMode`.

### Source-of-truth order

Read and reconcile these sources before making changes:

1. current default branch and exact `main` SHA;
2. root `AGENTS.md`;
3. `workspace.yaml`;
4. target system `AGENTS.md` when present;
5. `manifests/powers/<power-id>.yaml`;
6. `manifests/power-distribution-evidence.json` when present;
7. installed package `MANIFEST.json` when present;
8. applicable runtime and Power documentation.

Repository state, package manifests, release checksums, and recorded evidence are authoritative. Conversation memory and Slack messages are not authoritative.

If manifest state, publication evidence, release assets, or documentation disagree, report `BLOCKED_DISTRIBUTION_DRIFT`. Do not silently choose whichever source is convenient.

### Preflight

Before installation, the agent MUST:

1. identify OS, shell, Python executable, Git availability, and selected host;
2. verify the target path is correct and writable;
3. inspect existing `.dw/powers/<power-id>/`, `.dw/history/<power-id>/`, host adapters, configuration, and runtime roots;
4. preserve consumer runtime data by default;
5. verify required provider state is `published` for `release` or `power-dist` consumption;
6. verify Node.js and npm before BMAD bootstrap;
7. detect dirty or unmanaged paths and refuse unsafe overwrite;
8. record the pre-install state for the final report.

Do not initialize Power submodules during a normal Power Dist onboarding. Submodules are migration and recovery fallbacks only.

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
| `auto` | Preferred. Resolve the current manifest default after provider-state validation. |
| `release` | Preferred for immutable production-like consumption. Exact version and checksum are required. |
| `power-dist` | Use for the current validated distribution branch when mutable-channel consumption is intended. |
| `package` | Use for a local validated ZIP or package directory, including offline installation. |
| `submodule` | Recovery or migration fallback only. Never silently substitute it for a blocked distribution. |

For `release`, derive the version from current publication evidence or an exact verified release. Do not hard-code a stale version into reusable automation.

For `package`, require `MANIFEST.json`; verify every declared file size and SHA-256; require the external checksum when supplied; reject absolute paths, parent traversal, and archive symlinks.

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
| Distribution | Manifest provider state and selected source are valid. |
| Integrity | Package identity, file sizes, and SHA-256 hashes pass. |
| Installation | `.dw/powers/<power-id>/` is managed and contains `.dw-managed.json`. |
| Entrypoint | At least one manifest-declared entrypoint exists. |
| Runtime | Consumer runtime root exists and remains inside the target project. |
| Configuration | Required config and contract are managed and valid. |
| Host | Selected host adapter exists and resolves the installed package. |
| Native bootstrap | Required package-specific bootstrap marker and generated files exist. |
| Workspace | `dw validate` passes when running inside DW-SuperApps. |
| Safety | No secrets, traversal, unmanaged overwrite, dashboard, task, plan, or generated-source contamination. |

Use these statuses consistently:

- `READY`: installation, activation, and doctor all pass;
- `PARTIAL`: package is valid but configuration, native bootstrap, or host activation remains incomplete;
- `BLOCKED`: a required dependency, authority, release, checksum, target, or safety condition prevents completion;
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

| Power | Source | Version/SHA | Install | Config | Host | Doctor | Runtime | Status |
|---|---|---|---|---|---|---|---|---|

Also include:

- target system and absolute target path;
- detected OS, shell, Python, Node/npm when applicable, and host;
- exact commands executed with secrets removed;
- created or changed paths;
- validation results;
- unresolved risks or blockers;
- rollback or uninstall command;
- confirmation that runtime data was preserved;
- confirmation that no dashboard, task, plan, secret, or unrelated source content was installed.

### Canonical one-prompt onboarding request

Agents must recognize and execute the following request without requiring the user to restate the lifecycle:

```text
Onboard DW SUPER Power Dist for <target system or project path> on <host>.
Treat DW-SuperApps as the working control project and repository state as source of truth.
Install or update all Powers enabled for the target using their validated distribution defaults.
Configure required consumer contracts, activate the selected host, run complete package and host doctor checks, repair safe setup issues, and validate actual Power invocation.
Preserve existing runtime data and do not install dashboards, tasks, plans, secrets, or unrelated source content.
Return exact versions, paths, commands, evidence, rollback instructions, and READY/PARTIAL/BLOCKED status for every Power.
Do not stop after giving instructions; perform all available setup and validation actions now.
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
