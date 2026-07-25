# DW SUPER Power Dist Onboarding Prompt

Use this prompt for normal onboarding. It automatically prefers a valid local package when one is explicitly supplied or when offline/manual package mode applies.

```text
Onboard DW SUPER Power Dist for the current target system and current host environment.

Treat the existing `DW-SuperApps` checkout as the working control project and repository state as the source of truth.

Read and follow:

1. `AGENTS.md`
2. `workspace.yaml`
3. `docs/runbooks/POWER_DIST_ONBOARDING.md`
4. `docs/PORTABLE_MULTI_HOST_ROUTER.md`
5. applicable target-system instructions and selected Power manifests

Resolve the target system, target path, enabled Powers, current host, online/offline mode, and available package sources without asking for information already present in the project.

Execute the complete lifecycle:

DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT

Requirements:

- Use a validated local package when an explicit package path is provided, a valid package is present in `<target-project>/.dw/inbox/powers/<power-id>/`, offline/manual ZIP mode is requested, or GitHub package acquisition is unavailable.
- In local/offline mode, use `--source package` with the local ZIP and matching `.zip.sha256` sidecar. Do not use Git pull/fetch/clone, GitHub release download, release URLs, power-dist download, curl, wget, or submodule initialization for Power acquisition.
- Otherwise use the distribution mode defined by the current Power manifests and publication evidence.
- Never silently fall back to a submodule or repository checkout.
- Install canonical packages under `<target-project>/.dw/powers/<power-id>/`; never manually extract package content there.
- Configure required target-owned consumer configuration and contracts.
- Prepare all configured native host adapters so the project can be opened in different IDEs without reinstalling Powers or switching a global active-host state.
- Follow `docs/PORTABLE_MULTI_HOST_ROUTER.md`: use one canonical router when the checked-out runtime supports it; otherwise use the current generated adapters as a compatibility fallback and report router migration as pending.
- Do not invent portable-router commands that do not exist in the checked-out runtime.
- Detect duplicate DW skill names, duplicate Power identities, cross-host compatibility leakage, stale adapters, and broken wrapper targets.
- Load only one selected canonical Power entrypoint for each task.
- Run package, checksum, runtime, entrypoint, configuration, native-bootstrap, host, dedupe, workspace, and real-invocation checks.
- Repair only safe generated setup issues. Never overwrite unmanaged host instructions or configuration.
- Preserve `.gwc`, `.ua`, `.task-me`, `.bmad`, `_bmad`, `_bmad-output`, package history, and inbox ZIP/checksum files.
- Do not install dashboards, project tasks, generated plans, tests, evals, secrets, or unrelated source content.
- Do not claim `READY` when any required package, configuration, routing, host, doctor, dedupe, or invocation check remains incomplete.
- Do not stop after providing instructions. Perform every available setup and validation action now.

Return:

- resolved target system and absolute project path;
- detected OS, shell, Python, Node/npm when applicable, current host, configured hosts, and online/offline mode;
- exact Power versions, source SHAs, package paths, and checksums;
- installation, configuration, router/adapter, doctor, dedupe, and invocation results;
- created or changed paths;
- sanitized commands executed;
- rollback and uninstall commands;
- unresolved blockers and risks;
- one evidence table with `READY`, `PARTIAL`, `BLOCKED`, or `FAILED` for every Power and host-routing layer.
```
