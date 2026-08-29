# TaskController Executor Worktree Policy

This overlay binds local repository mutation to the DW-SuperApps isolated child-repository worktree standard in `docs/runbooks/ISOLATED_SUBMODULE_WORKTREE.md`.

## Scope

Apply when an Executor performs local Git/code mutation for a registered submodule project from the DW-SuperApps workspace.

This policy does not activate GWC by itself and does not grant merge, deployment, release, production, secret, migration, or destructive authority.

## Mandatory binding before mutation

The Controller contract/mailbox must resolve or require the Executor to resolve and report these fields before child source mutation:

```yaml
workspace:
  repository: nhatnguyenquang1838-coder/DW-SuperApps
  root: <trusted-local-DW-SuperApps-root>

target:
  project: <workspace project id>
  path: projects/<project>
  repository: <child repository>

execution:
  unit_id: <task-or-work-package identity>
  worktree: worktrees/<project>/<execution-unit>
  branch: <task branch>
  base_sha: <exact remote base SHA>
  writer: <executor identity>
```

The worktree path is relative to the DW-SuperApps root unless the transport explicitly requires an absolute path.

## Writable surface

For child source mutation:

```text
ALLOW:  worktrees/<project>/<execution-unit>/**
DENY:   projects/<project>/** as a development surface
```

`projects/<project>` is used only as the registered submodule administration anchor and pinned gitlink surface. Reading it, fetching through it, worktree administration through it, and an explicitly authorized parent-integration checkout are distinct from developing source there.

## Execution-unit invariant

One writable repository execution unit owns:

- one child worktree;
- one task branch;
- one writer at a time.

Agent identity is not encoded as durable branch identity. Executor replacement does not require branch renaming when the Controller transfers execution authority safely.

## Exact-base invariant

Before worktree creation, resolve the target child repository's current approved remote base and exact SHA. Do not treat the parent gitlink or an unrefreshed local `origin/main` as automatically current.

Report exact base/head SHAs in mailbox evidence.

## Parallelism

Independent child worktrees may execute concurrently. Git worktree isolation does not isolate shared repository administration or non-Git runtime resources.

The Executor must namespace collidable runtime resources by execution unit where relevant, including ports, Docker project names, volumes, temporary files, test databases/schemas, browser profiles, PID/socket paths, and generated runtime artifacts.

Ordinary Executors must not mutate shared remotes, common Git configuration, hooks, maintenance/gc policy, or shared `.git/modules` administration.

## Parent integration

Child repository delivery and DW-SuperApps gitlink integration are separate contracted actions.

The normal evidence chain is:

```text
child PR -> exact reachable child integration SHA -> parent integration writer -> gitlink bump -> parent PR
```

A completed child task does not implicitly authorize or perform a parent gitlink bump.

Parent gitlink mutation requires an exclusive parent writer boundary or equivalent serialization from the active Controller/process. If that boundary is not present in the current contract, report `WAIT_CONTROLLER` rather than racing another integration.

The mailbox result should reference both PRs when both exist:

```yaml
delivery:
  child_pr: <repo#pr>
  child_head_or_merge_sha: <sha>
  parent_gitlink_pr: <DW-SuperApps#pr-or-null>
```

## Safety

Normal execution forbids:

- direct source editing in `projects/<project>`;
- direct writes to protected/default branches;
- force-push;
- deleting `.git/modules/<project>`;
- using `--force` to defeat normal worktree branch ownership;
- silent parent gitlink mutation;
- history rewrite after SHA-bound PR/CI/approval/mailbox evidence without an explicit evidence reset/rebind.

Recovery operations such as destructive reset/clean or `git worktree repair` require a real recovery condition, preserved evidence, and the applicable repository/governance authority.

## Validation and closeout

Before semantic completion, validate the child repository and capture exact branch/head/CI evidence required by the active task.

When operating on a trusted local workspace, the Executor should also run:

```bash
python scripts/validate_workspace_worktree_policy.py --runtime
```

when the DW-SuperApps checkout and relevant worktree administration are available.

Cleanup uses `git worktree remove` followed by `git worktree prune` after the run no longer depends on that local worktree.

## Capability boundary

This policy is concurrency-safe by design, but it does not claim current TaskController supports multiple Executors or active lease management. Follow `controllers/taskcontroller.yaml` for current runtime topology. When LeaseManager/multi-executor routing are deferred, the Controller must not advertise them as active merely because this worktree model can support them later.
