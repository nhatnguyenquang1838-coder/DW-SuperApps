# DW SuperApps Agent Routing

DW SuperApps is the executable control workspace for reusable AI Powers, product projects, model providers, workspace controllers, and multiple agent hosts. Treat it as a working project, not as documentation-only reference material.

## Source of truth

Use this order:

1. current repository state and exact local HEAD;
2. root `AGENTS.md`;
3. `workspace.yaml`;
4. applicable workspace controller registry under `controllers/` when a controller is selected;
5. target project `AGENTS.md` when present;
6. `manifests/powers/<power-id>.yaml` when a Power is selected;
7. installed package `MANIFEST.json` and validated distribution evidence;
8. applicable runbooks and host adapters.

Repository state, controller registries, package manifests, checksums, governance artifacts, and audit records are authoritative. Conversation memory and Slack are not authoritative.

When online, verify the current default branch and exact `main` SHA. When GitHub is explicitly unavailable, record remote verification as `SKIPPED_OFFLINE`; do not block a valid local-package workflow.

## Workspace and project boundary

DW-SuperApps owns the distribution and host-control plane:

```text
DW-SuperApps/.dw/powers/          installed Power packages
DW-SuperApps/.dw/inbox/powers/    local package drop zone
DW-SuperApps/.dw/cache/           package cache
DW-SuperApps/.dw/history/powers/  package rollback history
DW-SuperApps/.dw/bindings/        project-to-package bindings
DW-SuperApps/.codex/              Codex adapters
DW-SuperApps/.kiro/               Kiro adapters
DW-SuperApps/.claude/             Claude adapters
DW-SuperApps/.github/             Copilot adapters
DW-SuperApps/.kilo/               Kilo adapters
DW-SuperApps/.clinerules/         Cline adapters
DW-SuperApps/.agents/             configured custom-host adapters
```

Registered product projects own runtime and project configuration only:

| Power | Target-owned runtime root |
|---|---|
| GWC | `.gwc/` |
| UA | `.ua/` |
| Task Me | `.task-me/` |
| BMAD | `.bmad/`, `_bmad/`, and `_bmad-output/` when declared by the package/modules |

Normal Power onboarding must not create `<project>/.dw/`, Power package payloads, or host skill adapters in a registered project.

Existing `<project>/.dw/powers/<power-id>` paths are legacy installations. Report `LEGACY_TARGET_INSTALL` and preserve them. Migration or cleanup requires a separate authorized change.

## Discovery

1. Read `workspace.yaml`.
2. Resolve an explicitly selected workspace controller first, when present.
3. Resolve one target project when the task is project-scoped.
4. Load only Powers enabled for that project.
5. Read target-local instructions.
6. Prefer the selected installed package entrypoint under `.dw/powers/<power-id>/`.
7. Use a Power source submodule only as an explicit compatibility or development fallback.
8. Keep generated runtime and project configuration inside the owning target project.

Do not ask for facts already available from repository state, controller registries, manifests, governance artifacts, or connected systems.

## Workspace controller routing

Workspace controllers are host-control capabilities owned by DW-SuperApps. They are not Powers and do not use `manifests/powers/*` for activation.

### TaskController

`TaskController` is the canonical controller identity registered in `workspace.yaml` at `controllers[].id=taskcontroller` with registry `controllers/taskcontroller.yaml`.

Any explicit user mention of `TaskController`, `task controller`, or `/dw-taskcontroller` MUST activate TaskController before the agent plans, delegates, posts a controller RootCard, or claims that TaskController is booted.

Activation rules:

1. verify current DW-SuperApps repository state and exact `main` when online;
2. read this root `AGENTS.md`;
3. read `workspace.yaml` and confirm the controller is enabled;
4. read `controllers/taskcontroller.yaml`;
5. read `agents/README.md`;
6. load the current host, Agent-interaction, human-plane, and executor overlays declared by the controller registry;
7. only then compile the Controller plan/contract or create/update the RootCard.

Hosts may use `taskcontroller.mvp.resolve_taskcontroller_activation(...)` as the deterministic explicit-mention resolver. Conversation memory, previous-session summaries, old Slack threads, previous "booted" claims, and the mere presence of `taskcontroller/**` Python modules MUST NOT substitute for the canonical load chain.

If a mandatory **repository TaskController entrypoint** is missing or unreadable, activation is `BLOCKED`. Do not fabricate a controller contract or silently fall back to remembered instructions. External human-plane projections such as Slack Canvases are not repository entrypoints and cannot block activation.

The active Agent interaction contract is reference-based A2A:

- `agents/shared/taskcontroller-a2a-protocol.md` defines transport-neutral Controller↔Executor semantics;
- GitHub reference mailbox is the current Agent interaction pilot binding;
- one actor owns one mutable mailbox comment and advances a monotonic sequence;
- exact repo/SHA/PR/file/artifact references carry context and evidence;
- semantic Agent events are recorded to the TaskController audit ledger when audit is configured;
- binding IDs never become canonical TaskController IDs.

TaskController human-plane behavior is canonical in `agents/shared/taskcontroller-human-plane-policy.md`.

Slack is the Human Control Plane for active TaskController runs. For ChatGPT presenting a controlled run in Slack, the mandatory repository/transport chain includes:

- `agents/chatgpt-agent/agent-instructions.md`;
- `agents/shared/taskcontroller-a2a-protocol.md`;
- `agents/shared/taskcontroller-human-plane-policy.md`;
- `agents/chatgpt-agent/slack-controller-mvp.md`;
- the Slack connector for actual Slack I/O;
- `agents/hermes/agent-instructions.md` when Hermes is the Executor.

`Slack Communication Policy` and `Governance Behavior` Slack Canvas projections are optional. Missing, inaccessible, stale, or conflicting Canvas content MUST NOT block TaskController activation. The canonical repository policy wins; projection drift may be reported as `PROJECTION_UNAVAILABLE` or `PROJECTION_STALE` when material.

The active MVP is one Controller, one main Executor, one live Slack RootCard/thread for human control/visibility, 3–5 contracted subtasks, in-session incremental mailbox observation, `CONTINUE | WAIT_CONTROLLER | TERMINAL`, and bounded `INTERCEPT`. Slack thread replies are a compact semantic human timeline only. Slack thread history MUST NOT be the canonical Agent execution journal or required recovery context.

A fresh Controller recovers from current repository/task/run identity, mailbox envelopes/cursors, referenced PR/SHA/CI/artifacts, audit ledger/checkpoint when configured, and the Slack RootCard binding—not by replaying prior GPT/Slack conversation history.

The current MVP uses `taskcontroller/mvp/activation.py` for activation resolution, `taskcontroller/mvp/protocol_bridge.py` for verdict translation, `taskcontroller/interaction/*` for reference-based Agent interaction, and `taskcontroller/audit/*` for durable run evidence. Full-E2E surfaces including `SlackTaskControllerPack`, leases, recovery/checkpoint orchestration, and multi-executor routing remain deferred unless current repository policy explicitly activates them.

Activating TaskController does not automatically activate GWC. Load GWC only when the controlled task/project requires GWC governance.

## Power routing

- `gwc`: governance, gates, approvals, delivery control, and validation orchestration.
- `ua`: architecture, semantic analysis, dependency mapping, and project knowledge.
- `task-me`: impact analysis, implementation planning, task decomposition, coding guidance, and validation planning.
- `bmad`: structured product, specification, architecture, implementation, and review workflows.

Installing a Power does not grant GitHub write, Jira write, Slack, merge, deployment, approval, or production authority.

## Native Power activation

Power aliases such as `/dw-gwc`, `/dw-ua`, `/dw-task-me`, and `/dw-bmad` select native host skills. They are not terminal commands and do not require prompt export.

When a Power is selected, the agent must resolve the target project, load the canonical installed entrypoint, and apply the skill directly to the remainder of the user's request. It must not tell the user to execute an activation command, generate a copy-and-paste prompt, or merely explain the Power instead of using it.

The DW CLI owns installation, configuration, inspection, validation, doctor, history, rollback, and uninstall operations. It does not generate task prompts.

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

The package store and project target are separate concepts:

```text
package store   = workspace `distribution.storeRoot`
runtime target = `--target` project path
```

Default installation:

```bash
./bin/dw power install <power-id> \
  --source auto \
  --target projects/<project-id>
```

Use `--store-root` only for tests or an explicitly external workspace layout. A store root must not overlap or resolve inside the runtime target.

Do not claim `READY` when required configuration, host routing, doctor, dedupe, or invocation remains incomplete.

## Target project submodule vs Power source submodule (binding discipline)

DW-SuperApps registers two distinct submodule classes. Confusing them causes the recurring failure where a product project's *target submodule* is mistaken for a Power *source submodule*, or a Power's source is silently executed as the installed Power.

- **Target project submodule** (e.g. `projects/rental-home` → `nhatnguyenquang1838-coder/rental_home`): a product codebase. For a project task, materialize/fetch this registered submodule and resolve its **current `main`** as the task execution base. The parent DW-SuperApps gitlink that pins this submodule is **not** automatically the task execution head and must **not** be bumped implicitly during task work.
- **Power source submodule** (e.g. `projects/ua` → `Understand-Anything`): the upstream source of a managed Power's code. It is **not** a project runtime target and **not** the default execution surface. The managed installed package under `.dw/powers/<power-id>/` is the execution surface; the source submodule is an explicit compatibility/development fallback only.

A project task that needs a Power does **not** execute the Power's source submodule. It installs/binds the managed package and activates the installed entrypoint.

## Installed/available does not mean activated

The lifecycle `DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT` separates two decisions:

1. **Install/bind (availability)** is decided by the **project profile / `workspace.yaml`**: which Powers are declared `enabled` for the target project. Installing a Power does not by itself run it.
2. **Activate/use (runtime)** is decided by the **task intent**: given the Powers available to the project, only the Powers the current task actually needs are activated. Availability does not imply activation.

For any task, load only the Powers the task requires. Powers that are enabled but not required by the current intent remain available but **inactive**.

## Portable multi-host invariant

The user must be able to open the DW-SuperApps root in different configured IDEs without reinstalling Powers or changing a global active-host setting.

Target architecture:

```text
DW-SuperApps/.dw/powers
  -> one canonical DW router when implemented
  -> thin native adapters in DW-SuperApps
  -> selected project runtime root
```

Rules:

1. canonical Power implementation stays in the workspace package store;
2. host adapters contain routing only, not copied Power logic;
3. all configured native adapters may coexist in DW-SuperApps;
4. projects receive no generated Power skill payloads;
5. each host must see only one logical DW router/Power identity;
6. detect duplicate skill names, cross-host compatibility leakage, stale adapters, and broken targets;
7. load only one selected canonical Power entrypoint for a task;
8. do not invent portable-router commands not implemented by the checked-out runtime;
9. when the runtime still generates one adapter per Power, use it as a compatibility layer and report router migration as pending.

## BMAD ownership

BMAD package code and host skills belong to DW-SuperApps. BMAD project configuration and generated project assets belong to the selected project:

```text
DW-SuperApps/.dw/powers/bmad/
DW-SuperApps/<host-adapter-roots>/
<project>/.bmad/
<project>/_bmad/
<project>/_bmad-output/
```

BMAD bootstrap must not place package code or host skills in the project.

## Safety

- Never invent credentials, approvals, checksums, package identities, controller activation evidence, or validation evidence.
- Refuse path traversal, archive symlinks, store/runtime overlap, unmanaged overwrite, and package identity mismatch.
- In offline package mode, do not acquire supplied Powers through Git, GitHub, release URLs, `curl`, `wget`, `power-dist`, or submodules.
- Do not install dashboards, project tasks, generated plans, secrets, tests, evals, or unrelated source content as part of Power onboarding.
- Preserve runtime by default. Destructive runtime cleanup requires explicit authorization and confirmation flags.
- Shared package uninstall must not break another bound project. Detach the selected project and remove a shared package only when no bindings remain.
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

Before any DW SUPER Slack communication, load the canonical repository policy `agents/shared/taskcontroller-human-plane-policy.md` when TaskController is active, then load the applicable Slack transport overlay and connector.

Slack Canvas projections such as `Slack Communication Policy` and `Governance Behavior` are optional human-readable copies. They may be checked for projection drift when available, but missing/unreadable Canvas content MUST NOT block TaskController activation or execution. Repository policy is canonical.

Slack is an optional visibility layer generally and the Human Control Plane when TaskController Slack mode is active. It is not governance truth, canonical task/run storage, Agent progress transport, audit storage, or approval authority. Record canonical state and evidence first. Use one root task/execution message and post only semantic human updates in its thread when supported. Slack failure must never block execution or change the result unless Slack transport itself is the required provider wake-up binding for the selected Executor.
