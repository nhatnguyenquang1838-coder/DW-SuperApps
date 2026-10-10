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

## Workspace-rooted child repository development

For trusted local development of any registered Git submodule project, use the canonical machine-readable contract in `workspace.yaml` under `development` and the detailed runbook `docs/runbooks/ISOLATED_SUBMODULE_WORKTREE.md`.

The invariant is:

```text
DW-SuperApps                         = workspace/control/integration root
projects/<project>                  = submodule admin anchor + pinned gitlink
worktrees/<project>/<execution-unit> = writable child-repository development surface
```

Do not edit child project source directly in `projects/<project>` and do not create standalone writable project folders elsewhere on disk as the normal development surface.

For each writable repository execution unit:

1. resolve the registered project from `workspace.yaml`;
2. initialize/use `projects/<project>` only as the child repository administration anchor;
3. fetch/resolve the exact approved remote base SHA;
4. create one child-repository linked worktree under `worktrees/<project>/<execution-unit>`;
5. bind one task branch and one writer to that execution unit;
6. perform child source mutation only inside that worktree;
7. namespace collidable runtime resources per execution unit;
8. deliver the child repository PR first;
9. treat any DW-SuperApps gitlink bump as a separate, explicit, serialized parent integration action and PR.

Agent identity is execution/lease metadata, not durable branch identity. Parallel child worktrees are allowed, but shared Git common-state mutation and parent gitlink integration are controller/repository-admin concerns rather than ordinary Executor behavior.

When TaskController is active and local repository mutation is in scope, the Executor MUST also load `controllers/executor-worktree-policy.md`; this overlay is required by `controllers/taskcontroller.yaml`. The current TaskController registry remains authoritative for whether leases or multi-executor routing are actually active.

Validate the static routing contract with:

```bash
python scripts/validate_workspace_worktree_policy.py
```

On a trusted local checkout, include runtime/worktree inspection with:

```bash
python scripts/validate_workspace_worktree_policy.py --runtime
```

This worktree standard does not override `chat_connector_only` behavior. Connector-only agents use exact remote evidence and must not pretend local worktree operations were executed.

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

**TASKCONTROLLER_IS_OPTIONAL_WORKING_MODE:** TaskController is an explicitly selected workspace working mode, not a dependency or default boot stage for GWC Universal Runtime v2 or Node Architect. The presence of a governed run, node DAG, autonomous task, Executor, connected Slack, or installed skill never implicitly activates TaskController. Unless selected for the current run by explicit user intent or an already-authorized parent/controller binding, do not load TaskController mailbox/v2, continuation, high-integrity admission, RootCard, Human Plane or Controller–Executor constraints. GWC native authority and Node Architect node-runtime contracts remain applicable independently. When selected, TaskController orchestrates but does not replace native GWC authority or Node Architect routing.



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

If a mandatory **repository TaskController entrypoint** is missing or unreadable, activation is `BLOCKED`. Do not fabricate a controller contract or silently fall back to remembered instructions. The active TaskController load chain has no external Slack policy source.

The active Agent interaction contract is canonical mailbox/v2:

- `agents/shared/taskcontroller-a2a-protocol.md` defines transport-neutral Controller↔Executor semantics;
- `dw.taskcontroller.mailbox/v2` with append-only GitHub event/cursor records is the default machine binding;
- `dw.taskcontroller.a2a/v1` mutable-comment semantics are compatibility-only and require explicit opt-in;
- one actor owns one append-only mailbox stream and advances a monotonic sequence;
- exact repo/SHA/PR/file/artifact references carry context and evidence;
- semantic Agent events are recorded to the TaskController audit ledger when audit is configured;
- binding IDs never become canonical TaskController IDs.

**Controller-first bootstrap boundary:** Activating TaskController loads and binds the current Controller runtime; it does **not** require an Executor session, Executor acknowledgement, or a dispatched mailbox event before Controller-owned understanding/planning/recovery. For an active project-native lifecycle (including Universal V2 when explicitly loaded), gate ownership and completion are determined by that native Controller and its evidence contracts. `EFFECT_HOLD` or missing Executor transport blocks only the named effects/dispatch, not otherwise authorized Controller-only work; `RUN_HOLD` remains binding. The **first Executor dispatch**, not Controller-native bootstrap, is the mandatory mailbox/v2 event + durable continuation + cursor/exact-readback boundary. See `agents/chatgpt-agent/agent-instructions.md` and `agents/shared/taskcontroller-a2a-protocol.md`; see `docs/runbooks/HERMES_DESKTOP_RUNTIME.md` only for the Executor-side procedure. This rule never grants effect authority or waives native gate receipts.

**Hermes Loop continuity:** a `LoopManager` timer row is not the persistent TaskController Executor session or Controller continuation. Disabling an obsolete/polling Loop must not be projected as `RUN_HOLD`, a terminal result, or permission to abandon event-driven recovery. Do not re-arm an obsolete Loop to discover newer mailbox commands. The canonical guard is `taskcontroller/controlplane/orchestration_policy.py::decide_executor_loop_continuity`; the detailed procedure is in `docs/runbooks/HERMES_DESKTOP_RUNTIME.md` and `agents/hermes/agent-instructions.md`. This guard grants neither host scheduler effects nor execution authority.

When **Hermes Desktop** is the main Executor, load **one** host procedure: `docs/runbooks/HERMES_DESKTOP_RUNTIME.md`, after `agents/hermes/agent-instructions.md`. It defines one common continuous Executor lifecycle and invokes one **pre-bound Controller strategy only at a semantic decision boundary**: `standalone` = same-session serialized internal Controller phase with separately admitted actor identity and Pattern E → MoA advisory synthesis; `coordination` = GPT Web Controller notified using an approved bound in-app-browser / `drive_preview` pointer after typed Executor mailbox readback. Both require separate Controller/Executor actor ownership, exact event/cursor/continuation, current authority/lease/fence and user-pause guards. `max_children=0` governs child-run authority, **not** Desktop mode. Never infer rights from MoA/GPT prose; no `/loop` mailbox polling or Slack machine fallback. The runbook is host guidance, not an adapter implementation or approval source.

TaskController human-plane behavior is canonical in `agents/shared/taskcontroller-human-plane-policy.md`.

Slack is the Human Control Plane for active TaskController runs. For ChatGPT presenting a controlled run in Slack, the mandatory repository/transport chain includes:

- `agents/chatgpt-agent/agent-instructions.md`;
- `agents/shared/taskcontroller-a2a-protocol.md`;
- `agents/shared/taskcontroller-human-plane-policy.md`;
- `agents/chatgpt-agent/slack-controller-mvp.md`;
- the Slack connector for actual Slack I/O;
- `agents/hermes/agent-instructions.md` when Hermes is the Executor.

The active MVP is one Controller, one main Executor, one live Slack RootCard/thread for human control/visibility, 3–5 contracted subtasks, in-session incremental mailbox observation, `CONTINUE | WAIT_CONTROLLER | TERMINAL`, and bounded `INTERCEPT`. Slack thread replies are a compact semantic human timeline only. Slack thread history MUST NOT be the canonical Agent execution journal or required recovery context.

A fresh Controller recovers from current repository/task/run identity, mailbox envelopes/cursors, referenced PR/SHA/CI/artifacts, audit ledger/checkpoint when configured, and the Slack RootCard binding—not by replaying prior GPT/Slack conversation history.

The current MVP uses `taskcontroller/mvp/activation.py` for activation resolution, `taskcontroller/mvp/protocol_bridge.py` for verdict translation, `taskcontroller/interaction/*` for reference-based Agent interaction, and `taskcontroller/audit/*` for durable run evidence. Full-E2E surfaces including `SlackTaskControllerPack`, leases, recovery/checkpoint orchestration, and multi-executor routing remain deferred unless current repository policy explicitly activates them.

Activating TaskController does not automatically activate any Power. Load only the Power explicitly required by the controlled task.

### TaskController high-integrity admission

When TaskController controls a task whose active project/Power contract introduces a gate, human approval, protected effect, or digest-bound execution identity, the Controller MUST use the high-integrity interaction lane before dispatch, correction, approval presentation, or semantic resume.

High-integrity runs MUST:

1. resolve TaskController with mailbox/v2 semantics;
2. materialize every Controller machine transition through `taskcontroller/runtime/high_integrity_session.py::materialize_controller_transition`;
3. pass `taskcontroller/controlplane/controller_admission.py`;
4. bind machine state to the exact mailbox reference/event cursor and canonical typed envelope/artifact digest;
5. resolve schemas from canonical descriptor/source bindings;
6. use only observed or canonically recomputed expected digests;
7. start preapproval from the current verified boundary rather than synthesizing the target gate before its authority artifact exists;
8. bind human approval presentation to the typed approval-request artifact and verified command digest.

A mutable GitHub comment body, its full-body SHA, issue-wide comment history, a Controller-predicted hash, or a guessed legacy schema path is never semantic authority. Transport-level body hashes may be diagnostic evidence only.

The Controller MUST NOT hand-author GitHub mailbox JSON, event/cursor records, continuation sequence/digests, or any alternate record type. Runtime-owned fields such as `record_type`, `event_seq`, `previous_event_digest`, `event_digest`, cursor state, and continuation record sequencing are emitted only by the canonical v2 materializer/repository/store. Raw token/secret/credential values are forbidden in machine payloads; use durable references/digests instead.

If high-integrity admission cannot be satisfied, stop with `TASKCONTROLLER_HIGH_INTEGRITY_ADMISSION_BLOCKED`. Do not downgrade the run to the v1 compatibility lane to bypass the blocker.

For new high-integrity requests, the Controller must also declare a TaskController execution-contract mode and pass `taskcontroller/controlplane/execution_contracting.py` before dispatch:

- `PLAN` is read/design/validate only;
- `TRANSPORT_REPAIR` is mailbox/protocol repair only;
- `EXECUTE` is bounded real implementation after applicable authority validation.

Once `EXECUTE` is active, readonly is no longer the default. The approved package must contain real writable engineering scope and the Executor continues through routine implementation/test/fix/refactor cycles until AC/continue-until is reached or a real hard boundary occurs. Routine RED/GREEN completion, test failure, lint failure, scoped refactor, or ordinary implementation decisions are not WAIT_CONTROLLER boundaries.

For high-integrity TaskController runs, Human/User authority is Controller-owned: `Human/User <-> Controller <-> Executor`. The Executor reports only to the Controller and MUST NOT emit `WAIT_USER_*` / `WAIT_HUMAN_*`, approval commands, or direct Human approval loops. Executor blockers are normalized to `AUTHORITY_BOUNDARY`, `SCOPE_EXPANSION`, `MATERIAL_PLAN_INVALIDATION`, or `EXTERNAL_DEPENDENCY_BLOCKED`; the Controller resolves the next gate/HITL. A Human wait without an actionable Human request, or a delegated wait without a delegate dispatch receipt, is invalid and fails `AUTHORITY_REQUEST_UNROUTED`.

`execution_progress` is a first-class mailbox/v2 Controller resume input. Internal work-package milestones are progress, not release boundaries; one approved EXECUTE mission remains active until its declared ceiling or a canonical blocker. Atomic `max_children=0` missions may terminate with empty child provenance and MUST NOT fabricate child evidence.

HOLD semantics are typed: `EFFECT_HOLD` blocks explicitly named effects while the Controller control loop continues safe read/plan/recovery work; `RUN_HOLD` stops new run actions. Untyped generic HOLD is invalid.

A single approved EXECUTE package may cover isolated worktree/branch creation, approved edits, validation, stage, commit, push, and Draft PR when explicitly bound. Merge, separately governed Ready-for-Review, deploy, production/data/secret/migration/destructive operations require separate authority.

For the RuntimePlan W7→W9 proving campaign, the durable design and execution plan are:

- `docs/superpowers/specs/2026-09-02-runtime-proving-lab-design.md`
- `docs/superpowers/plans/2026-09-02-runtime-proving-lab-w8-w9.md`

These documents are implementation artifacts under the active TaskController contract; repository policy and exact mailbox state remain authoritative.

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

For local child-repository source mutation, isolated worktree lifecycle, parent gitlink integration, and worktree recovery, read and execute:

- `docs/runbooks/ISOLATED_SUBMODULE_WORKTREE.md`

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

- **Target project submodule** (e.g. `projects/rental-home` → `nhatnguyenquang1838-coder/rental_home`): a product codebase. For a project task, materialize/fetch this registered submodule and resolve its **current `main`** as the task execution base. The parent DW-SuperApps gitlink that pins this submodule is **not** automatically the task execution head and must **not** be bumped implicitly during task work. When local source mutation is required, use the isolated child-repository worktree standard above rather than editing this anchor.
- **Power source submodule** (e.g. `projects/ua` → `Understand-Anything`): the upstream source of a managed Power's code. It is **not** a project runtime target and **not** the default execution surface. The managed installed package under `.dw/powers/<power-id>/` is the execution surface; the source submodule is an explicit compatibility/development fallback only. If source-submodule development is explicitly in scope, use its isolated child-repository worktree under `worktrees/<project>/<execution-unit>`.

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
## Read-only Analyzer Child Run invariants (SCRUM-808)

These invariants prevent read-only Analyzer Child Run deadlock behind effect authority:

1. **READ_ONLY_ANALYSIS Child Run ≠ Repository G2 effect.** A child run whose only work is read-only analysis (inspection, evidence gathering, projection, recommendation) does not constitute a Repository G2 effect. It must not be treated as requiring G2 execution authority, repository write capability, or a gated effect graph.

2. **WAIT_CONTROLLER invalid if runnable read-only work exists.** When the only remaining delegated work is runnable read-only analysis, the Controller MUST NOT emit `WAIT_CONTROLLER` as a blocking verdict. `WAIT_CONTROLLER` is valid only when the next actionable step requires human/gate authority or a capability the Executor lacks. Read-only analysis that the Executor can perform is `CONTINUE`-eligible.

3. **UR-G* vs GWC-G* naming separation.** UR-G* references the Ultimate Responsibility gate authority chain (human approval boundaries). GWC-G* references the GWC gate lifecycle (G0–G6). These are distinct naming spaces and must not be conflated in controller verdicts, envelope decisions, or audit records. A GWC gate decision is never a UR authority delegation, and a UR approval is never a GWC gate transition.


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
3. for registered child-repository local development, use `worktrees/<project>/<execution-unit>` and never develop directly in `projects/<project>`;
4. do not write directly to protected `main`;
5. review the complete diff;
6. run applicable validation, including `python scripts/validate_workspace_worktree_policy.py` when this workspace contract is affected;
7. create a reviewable PR unless local-only work was explicitly requested;
8. do not merge, deploy, or perform production operations without separate authority.

A multi-repository change must identify every impacted repository. One repository's task, branch, approval, or validation does not authorize another repository. Child repository delivery does not implicitly authorize a DW-SuperApps gitlink bump.

## Slack behavior

Before any DW SUPER Slack communication, load the canonical repository policy `agents/shared/taskcontroller-human-plane-policy.md` when TaskController is active, then load the applicable Slack transport overlay and connector. Do not load Slack-hosted policy documents or Power-local communication-policy copies as TaskController instruction sources.

Slack is an optional visibility layer generally and the Human Control Plane when TaskController Slack mode is active. It is not governance truth, canonical task/run storage, Agent progress transport, audit storage, or approval authority. Record canonical state and evidence first. Use one root task/execution message and post only semantic human updates in its thread when supported. Slack failure must never block execution or change the result unless Slack transport itself is the required provider wake-up binding for the selected Executor.
