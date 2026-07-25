# DW SuperApps Agent Routing

DW SuperApps is an executable control workspace for reusable AI Powers, product systems, model providers, and multiple agent hosts. Treat it as a working project, not as documentation-only reference material.

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

## Discovery

1. Read `workspace.yaml`.
2. Resolve one target system.
3. Load only Powers enabled for that system.
4. Read target-local instructions.
5. Read only the selected Power entrypoint.
6. Keep generated and runtime data inside the owning target system.

Do not ask for facts already available from repository state, manifests, governance artifacts, or connected systems.

## Power routing

- `gwc`: governance, gates, approvals, delivery control, and validation orchestration.
- `ua`: architecture, semantic analysis, dependency mapping, and project knowledge.
- `task-me`: impact analysis, implementation planning, task decomposition, coding guidance, and validation planning.
- `bmad`: structured product, specification, architecture, implementation, and review workflows.

Installing a Power does not grant GitHub write, Jira write, Slack, merge, deployment, approval, or production authority.

## Mandatory runbooks

When the request concerns Power installation, update, configuration, activation, validation, doctor, repair, offline ZIP use, or initial host setup, the agent MUST read and execute:

- `docs/runbooks/POWER_DIST_ONBOARDING.md`

For portable IDE/host routing, adapter deduplication, or cross-host skill discovery, the agent MUST also read:

- `docs/PORTABLE_MULTI_HOST_ROUTER.md`

Reusable human prompts are stored separately:

- `prompts/power-dist/onboard.md`
- `prompts/power-dist/onboard-offline-zip.md`

Do not duplicate those runbooks or prompts inside this file.

## Power onboarding invariant

The required lifecycle is:

```text
DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT
```

Do not stop after describing commands when execution capabilities are available. Do not claim `READY` when required configuration, host routing, doctor, dedupe, or invocation remains incomplete.

Local package precedence applies when the user supplies a package path, a valid package exists in the target inbox during offline/manual mode, or GitHub package acquisition is unavailable.

The target inbox is:

```text
<target-project>/.dw/inbox/powers/<power-id>/
```

The managed installation is:

```text
<target-project>/.dw/powers/<power-id>/
```

Never manually extract package content into `.dw/powers`.

## Portable multi-host invariant

The user must be able to open the same target project in different configured IDEs without reinstalling Powers or changing a global active-host setting.

Target architecture:

```text
one canonical Power store
  -> one canonical DW router
  -> thin native adapters for configured hosts
```

Rules:

1. canonical Power implementation stays under `.dw/powers`;
2. host adapters contain routing only, not copied Power logic;
3. all configured native adapters may coexist;
4. each host must see only one logical DW router/Power identity;
5. detect duplicate skill names, cross-host compatibility leakage, stale adapters, and broken targets;
6. load only one selected canonical Power entrypoint for a task;
7. do not invent portable-router commands not implemented by the checked-out runtime;
8. when the current runtime still generates one adapter per Power, use it as a compatibility fallback and report router migration as pending.

## Runtime ownership

| Power | Target-owned runtime root |
|---|---|
| GWC | `.gwc/` |
| UA | `.ua/` |
| Task Me | `.task-me/` |
| BMAD | `.bmad/`, `_bmad/`, and `_bmad-output/` only when declared by the installed package/modules |

Preserve runtime by default. Destructive cleanup requires explicit authorization and required confirmation flags.

## Safety

- Never invent credentials, approvals, checksums, package identities, or validation evidence.
- Refuse path traversal, archive symlinks, unmanaged overwrite, and package identity mismatch.
- In offline package mode, do not acquire the supplied Power through Git, GitHub, release URLs, `curl`, `wget`, `power-dist`, or submodules.
- Do not install dashboards, project tasks, generated plans, secrets, tests, evals, or unrelated source content as part of Power onboarding.
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

Slack is an optional visibility layer, not governance truth, task storage, or approval authority.

Record canonical state and evidence first. Use one root task/execution message and post later updates in its thread when supported. Slack failure must never block execution or change the result.
