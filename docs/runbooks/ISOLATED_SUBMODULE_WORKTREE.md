# Isolated Submodule Worktree Engineering Standard

## Purpose

DW-SuperApps is the canonical workspace and control root for all registered projects. Child project source must not be developed in the pinned submodule checkout under `projects/<project>` or in unrelated standalone folders elsewhere on disk.

For every writable repository execution unit, create an isolated linked worktree of the child repository under the DW-SuperApps root:

```text
DW-SuperApps/
├── projects/<project>/                         # submodule admin anchor + pinned gitlink
└── worktrees/<project>/<execution-unit>/      # writable development surface
```

This standard applies to registered Git submodule projects in `workspace.yaml`. It does not vendor child repositories, does not convert DW-SuperApps into a monorepo, and does not make the parent repository own child source history.

## Canonical invariants

1. `DW-SuperApps` is the workspace/control/integration root.
2. `projects/<project>` is a submodule administration anchor and pinned gitlink; do not edit project source there.
3. All child source edits occur under `worktrees/<project>/<execution-unit>`.
4. One writable repository execution unit owns exactly one worktree, one branch, and one writer at a time.
5. Agent identity is execution/lease metadata, not branch identity. A replacement Executor continues the same branch/worktree when authority permits.
6. Resolve and record the exact remote base SHA before creating a worktree. Do not use a stale local `origin/main` assumption as evidence.
7. Child repository development may run in parallel. Parent DW-SuperApps gitlink mutation is a separate, explicit, serialized integration action.
8. A child PR and a parent gitlink PR are separate review/evidence surfaces.
9. Runtime resources that can collide across executions must be namespaced per execution unit.
10. Shared Git common-state mutations are repository-admin/controller operations, not ordinary Executor behavior.

## Execution identity

Use a repository execution unit rather than assuming one Jira task always maps to one worktree.

Examples:

```text
SCRUM-555
SCRUM-555/M5-G6
SCRUM-600/WP1
```

A single task that changes multiple repositories has one execution unit per writable repository surface:

```text
worktrees/gwc/SCRUM-600/WP1
worktrees/task-me/SCRUM-600/WP2
```

A task that deliberately fans out independent work packages in the same repository may use multiple execution units:

```text
worktrees/gwc/SCRUM-600/WP1
worktrees/gwc/SCRUM-600/WP2
```

Do not make the branch name depend on the current agent. Preferred branch shape:

```text
work/<TASK-ID>
work/<TASK-ID>/<WORK-PACKAGE>
```

For non-Jira work, use a stable task slug and date only when no durable task identity exists.

## Create lifecycle

Run from the canonical DW-SuperApps root. `<project>` must be registered in `workspace.yaml` and map to `projects/<project>`.

Initialize the submodule administration anchor if required:

```bash
git submodule update --init --checkout -- projects/<project>
```

Refresh remote refs and resolve an exact base:

```bash
git -C projects/<project> fetch --prune origin
BASE_SHA=$(git -C projects/<project> rev-parse origin/main)
```

Record `BASE_SHA` in the task/run evidence before mutation.

Create the child-repository worktree:

```bash
git -C projects/<project> worktree add \
  -b work/<execution-unit> \
  worktrees/<project>/<execution-unit> \
  "$BASE_SHA"
```

Verify:

```bash
git -C projects/<project> worktree list --porcelain
git -C worktrees/<project>/<execution-unit> rev-parse HEAD
git -C worktrees/<project>/<execution-unit> status --short
```

Do not use `--force` to defeat Git worktree branch ownership checks during normal execution.

## Develop lifecycle

The Executor working directory for child source mutation is:

```text
DW-SuperApps/worktrees/<project>/<execution-unit>
```

The Executor may read workspace-level policy/configuration from DW-SuperApps, but it does not mutate child source in `projects/<project>`.

Before a meaningful gate/handoff, capture at minimum:

```yaml
repository: <child-repo>
project: <project>
execution_unit: <id>
worktree: worktrees/<project>/<execution-unit>
branch: <branch>
base_sha: <exact-base>
head_sha: <exact-head>
writer: <executor-id>
dirty: false
```

## Parallel execution

Linked worktrees isolate per-worktree files such as working files, HEAD, and index. They still share repository common state and object storage.

Safe parallel surfaces include:

- source file writes inside separate worktrees;
- per-worktree index and uncommitted state;
- task-local generated output;
- task-local gate/runtime artifacts.

Shared or potentially shared surfaces require additional discipline:

- repository refs and remote-tracking refs;
- common Git configuration and hooks;
- maintenance/gc state;
- ports and dev servers;
- Docker project/container/volume names;
- temporary paths and PID/socket files;
- test databases/schemas;
- CPU/RAM/GPU.

Ordinary Executors must not change remotes, common Git configuration, hooks, repository maintenance policy, or delete shared repository administration state.

## Runtime namespace

Every execution unit that starts local runtime resources must derive a unique namespace. The concrete implementation may vary by project, but the identity must be deterministic and carried in task evidence.

Examples:

```yaml
resources:
  namespace: SCRUM-555-M5-G6
  docker_project: dw-scrum-555-m5-g6
  temp_root: worktrees/gwc/SCRUM-555/M5-G6/.tmp
  test_database: dw_scrum_555_m5_g6
```

Do not assume Git worktree isolation also isolates runtime resources.

## Child delivery

Push only the child task branch and create the child repository PR according to the active governance contract:

```bash
git -C worktrees/<project>/<execution-unit> push -u origin <branch>
```

Do not merge merely because the worktree is complete. GWC/TaskController authority remains separate when active.

## Parent gitlink integration

Child implementation and parent integration are distinct operations.

After the child PR is merged or another exact reachable child SHA is explicitly approved for integration:

1. Resolve the exact child integration SHA from authoritative remote evidence.
2. Acquire the parent integration writer boundary defined by the active controller/process.
3. Use a dedicated DW-SuperApps integration branch.
4. Move only the submodule administration anchor to the approved exact SHA.
5. Stage the resulting gitlink change in DW-SuperApps.
6. Review the parent diff.
7. Create a separate parent PR.

Fetching the child repository does **not** update the parent gitlink by itself. `git add projects/<project>` stages whatever child commit is currently checked out at that anchor; therefore the anchor must first be moved explicitly to the intended exact SHA.

Conceptual flow:

```text
child PR -> child merge SHA -> exclusive parent integration -> gitlink bump -> parent validation -> parent PR
```

Never bump a gitlink implicitly as a side effect of project development.

## Parent integration serialization

Multiple child tasks may execute in parallel. Mutation of the same DW-SuperApps integration surface must not be concurrent.

The active controller/process must serialize parent gitlink integration or otherwise provide an exclusive parent writer. This prevents two completed child tasks from racing on `projects/<project>` or the parent index.

## Cleanup

After delivery reaches the lifecycle point at which the local worktree is no longer required:

```bash
git -C projects/<project> worktree remove worktrees/<project>/<execution-unit>
git -C projects/<project> worktree prune
```

Delete the local task branch only when it is safe and no evidence/recovery contract still depends on it:

```bash
git -C projects/<project> branch -d <branch>
```

Do not manually delete `.git/modules/<project>` or other shared repository administration state.

Normal relocation uses `git worktree move` when supported. `git worktree repair` is a recovery mechanism for administrative metadata drift, such as after an improper/manual move; it is not the normal move command.

If a worktree directory was manually removed, use `git worktree prune` to clean stale administrative records after confirming no recoverable work remains.

## Recovery and destructive Git operations

Tracked files that are missing or unexpectedly empty should be restored from authoritative Git history/evidence rather than recreated from memory.

Normal governed execution forbids force-push and direct writes to protected/default branches.

`reset --hard`, `clean -fd`, history rewrite, or rebase must not be used casually. If recovery genuinely requires a destructive operation, first preserve evidence and follow the active repository/governance recovery authority. Once PR/CI/approval/mailbox evidence is bound to a SHA, history rewrite requires explicit reset/rebinding of that evidence.

## Validation

Static workspace/routing validation:

```bash
python scripts/validate_workspace_worktree_policy.py
```

On a trusted local DW-SuperApps checkout, also validate active worktrees and anchors:

```bash
python scripts/validate_workspace_worktree_policy.py --runtime
```

CI runs the static validator and unit tests through `.github/workflows/workspace-worktree-policy.yml`.

## TaskController routing

When TaskController is active, `controllers/executor-worktree-policy.md` is the canonical Executor overlay for this standard. The Controller contract/mailbox should carry repository, exact base/head SHA, execution-unit identity, worktree path, branch, writer identity, child PR, and parent integration PR when applicable.

Current TaskController runtime capability is authoritative. This standard defines safe worktree binding and the target concurrency model; it does not claim multi-executor routing or LeaseManager is active unless the current controller registry/runtime says so.

## Execution-mode boundary

This standard applies to trusted local execution environments with a real Git checkout, such as a local Hermes/Codex executor or approved CI/developer host.

It does not override `chat_connector_only` behavior. A ChatGPT connector-only session controls and validates through exact remote/connector evidence rather than pretending local `git worktree`, `git status`, or checkout operations were executed.

## References

- Root routing: `AGENTS.md`
- Machine-readable contract: `workspace.yaml` → `development`
- TaskController Executor overlay: `controllers/executor-worktree-policy.md`
- Validation: `scripts/validate_workspace_worktree_policy.py`
- CI: `.github/workflows/workspace-worktree-policy.yml`

Do not add floating host-local skills as canonical authority. If a host adapter/skill projects this policy into `~/.hermes` or another host directory, DW-SuperApps remains the canonical source.
