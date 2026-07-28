# DW SuperApps Agent Routing

DW SuperApps is the executable control workspace for reusable AI Powers, product systems, model providers, and multiple agent hosts. Treat it as a working project, not as documentation-only reference material.

## Source of truth

Use this order:

1. current repository state and exact local HEAD;
2. root `AGENTS.md`;
3. `workspace.yaml`;
4. target system `AGENTS.md` when present;
5. `manifests/powers/<power-id>.yaml`;
6. installed package `MANIFEST.json` and validated distribution evidence;
7. applicable runbooks and host adapters.

Repository state, package manifests, checksums, governance artifacts, and audit records are authoritative. Conversation memory and Slack are not authoritative.

When online, verify the current default branch and exact `main` SHA. When GitHub is explicitly unavailable, record remote verification as `SKIPPED_OFFLINE`; do not block a valid local-package workflow.

## Workspace and system boundary

DW-SuperApps owns the distribution and host-control plane:

```text
DW-SuperApps/.dw/powers/          installed Power packages
DW-SuperApps/.dw/inbox/powers/    local package drop zone
DW-SuperApps/.dw/cache/           package cache
DW-SuperApps/.dw/history/powers/  package rollback history
DW-SuperApps/.dw/bindings/        system-to-package bindings
DW-SuperApps/.codex/              Codex adapters
DW-SuperApps/.kiro/               Kiro adapters
DW-SuperApps/.claude/             Claude adapters
DW-SuperApps/.github/             Copilot adapters
DW-SuperApps/.kilo/               Kilo adapters
DW-SuperApps/.clinerules/         Cline adapters
DW-SuperApps/.agents/             configured custom-host adapters
```

Registered systems own runtime and project configuration only:

| Power | Target-owned runtime root |
|---|---|
| GWC | `.gwc/` |
| UA | `.ua/` |
| Task Me | `.task-me/` |
| BMAD | `.bmad/`, `_bmad/`, and `_bmad-output/` when declared by the package/modules |

Normal Power onboarding must not create `<system>/.dw/`, Power package payloads, or host skill adapters in a registered system.

Existing `<system>/.dw/powers/<power-id>` paths are legacy installations. Report `LEGACY_TARGET_INSTALL` and preserve them. Migration or cleanup requires a separate authorized change.

## Discovery

1. Read `workspace.yaml`.
2. Resolve one target system.
3. Load only Powers enabled for that system.
4. Read target-local instructions.
5. Prefer the selected installed package entrypoint under `.dw/powers/<power-id>/`.
6. Use a Power source submodule only as an explicit compatibility or development fallback.
7. Keep generated runtime and project configuration inside the owning target system.

Do not ask for facts already available from repository state, manifests, governance artifacts, or connected systems.

## Power routing

- `gwc`: governance, gates, approvals, delivery control, and validation orchestration.
- `ua`: architecture, semantic analysis, dependency mapping, and project knowledge.
- `task-me`: impact analysis, implementation planning, task decomposition, coding guidance, and validation planning.
- `bmad`: structured product, specification, architecture, implementation, and review workflows.

Installing a Power does not grant GitHub write, Jira write, Slack, merge, deployment, approval, or production authority.

## Mandatory runbooks

For Power installation, update, configuration, activation, validation, doctor, repair, offline ZIP use, or initial host setup, read and execute:

- `docs/runbooks/POWER_DIST_ONBOARDING.md`

For portable IDE/host routing, adapter deduplication, or cross-host skill discovery, also read:

- `docs/PORTABLE_MULTI_HOST_ROUTER.md`

Reusable prompts:

- `prompts/power-dist/onboard.md`
- `prompts/power-dist/onboard-offline-zip.md`

## Power onboarding invariant

The required lifecycle is:

```text
DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT
```

The package store and system target are separate concepts:

```text
package store   = workspace `distribution.storeRoot`
runtime target = `--target` system path
```

Default installation:

```bash
./bin/dw power install <power-id> \
  --source auto \
  --target systems/<system-id>
```

Use `--store-root` only for tests or an explicitly external workspace layout. A store root must not overlap or resolve inside the runtime target.

Do not claim `READY` when required configuration, host routing, doctor, dedupe, or invocation remains incomplete.

## Portable multi-host invariant

The user must be able to open the DW-SuperApps root in different configured IDEs without reinstalling Powers or changing a global active-host setting.

Target architecture:

```text
DW-SuperApps/.dw/powers
  -> one canonical DW router when implemented
  -> thin native adapters in DW-SuperApps
  -> selected system runtime root
```

Rules:

1. canonical Power implementation stays in the workspace package store;
2. host adapters contain routing only, not copied Power logic;
3. all configured native adapters may coexist in DW-SuperApps;
4. systems receive no generated Power skill payloads;
5. each host must see only one logical DW router/Power identity;
6. detect duplicate skill names, cross-host compatibility leakage, stale adapters, and broken targets;
7. load only one selected canonical Power entrypoint for a task;
8. do not invent portable-router commands not implemented by the checked-out runtime;
9. when the runtime still generates one adapter per Power, use it as a compatibility layer and report router migration as pending.

## BMAD ownership

BMAD package code and host skills belong to DW-SuperApps. BMAD project configuration and generated project assets belong to the selected system:

```text
DW-SuperApps/.dw/powers/bmad/
DW-SuperApps/<host-adapter-roots>/
<system>/.bmad/
<system>/_bmad/
<system>/_bmad-output/
```

BMAD bootstrap must not place package code or host skills in the system.

## Safety

- Never invent credentials, approvals, checksums, package identities, or validation evidence.
- Refuse path traversal, archive symlinks, store/runtime overlap, unmanaged overwrite, and package identity mismatch.
- In offline package mode, do not acquire supplied Powers through Git, GitHub, release URLs, `curl`, `wget`, `power-dist`, or submodules.
- Do not install dashboards, project tasks, generated plans, secrets, tests, evals, or unrelated source content as part of Power onboarding.
- Preserve runtime by default. Destructive runtime cleanup requires explicit authorization and confirmation flags.
- Shared package uninstall must not break another bound system. Detach the selected system and remove a shared package only when no bindings remain.
- Use `READY`, `PARTIAL`, `BLOCKED`, and `FAILED` exactly as defined by the onboarding runbook.

## Model providers

Ollama is a model provider, not a host. Local OpenAI-compatible defaults are:

- Base URL: `http://localhost:11434/v1`
- API key placeholder: `ollama`
- Model override: `OLLAMA_MODEL`

Provider configuration must not contain real secrets.

## Repository changes

For repository modifications:

1. verify repository, default branch, exact base SHA, and target files;
2. use a dedicated branch;
3. do not write directly to protected `main`;
4. review the complete diff;
5. run applicable validation;
6. create a reviewable PR unless local-only work was explicitly requested;
7. do not merge, deploy, or perform production operations without separate authority.

A multi-repository change must identify every impacted repository. One repository's task, branch, approval, or validation does not authorize another repository.

## Slack behavior

Before any DW SUPER Slack communication, load the Slack connector and read the latest Slack Communication Policy and Governance Behavior canvases.

Slack is an optional visibility layer, not governance truth, task storage, or approval authority. Record canonical state and evidence first. Use one root task/execution message and post later updates in its thread when supported. Slack failure must never block execution or change the result.
