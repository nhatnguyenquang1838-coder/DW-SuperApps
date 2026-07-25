# DW SUPER Offline ZIP Onboarding Prompt

Use this prompt when Power ZIPs were copied manually and GitHub or outbound package acquisition is blocked.

```text
Onboard DW SUPER from local Power ZIPs for the current target system and current host environment.

GitHub and outbound Power acquisition are unavailable. Treat the existing local `DW-SuperApps` checkout as the working control project.

Read and follow:

1. `AGENTS.md`
2. `workspace.yaml`
3. `docs/runbooks/POWER_DIST_ONBOARDING.md`
4. `docs/PORTABLE_MULTI_HOST_ROUTER.md`
5. applicable target-system instructions and selected Power manifests

Resolve the target system, absolute target path, enabled Powers, current host, and configured hosts without asking for information already available locally.

For every selected Power, search only in:

<target-project>/.dw/inbox/powers/<power-id>/

Require exactly one valid ZIP and matching `.zip.sha256` sidecar per requested Power unless an exact local path was supplied. Verify the archive checksum, package identity, internal `MANIFEST.json`, every declared file size/hash, entrypoints, and target-owned runtime root.

Install with:

--source package --package <local-zip> --checksum <local-sidecar>

Do not run git pull, git fetch, git clone, GitHub API or release download, curl, wget, power-dist download, or submodule initialization for Power acquisition. Do not replace the local package with a repository checkout.

Execute the complete lifecycle:

DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT

Requirements:

- Install canonical packages under `<target-project>/.dw/powers/<power-id>/`; never manually extract package content there.
- Preserve the original inbox ZIP/checksum files unchanged.
- Configure required target-owned consumer contracts without inventing credentials or secrets.
- Prepare all configured native host adapters once so Codex, Kiro, Kilo Code, GitHub Copilot, Claude Code, Cline, or configured custom hosts can open the same project without reinstalling Powers or changing a global active-host setting.
- Follow `docs/PORTABLE_MULTI_HOST_ROUTER.md`: use one canonical router only when the checked-out runtime supports it. Otherwise use current generated adapters as a compatibility fallback and report router migration as pending.
- Do not invent unsupported commands such as `dw setup portable`.
- Detect duplicate DW skill identities, duplicate Power identities, cross-host compatibility leakage, stale wrappers, broken targets, and unmanaged conflicts.
- Load only one selected canonical Power entrypoint for each task.
- Run complete local-package, checksum, package, runtime, configuration, native-bootstrap, host, dedupe, workspace, and real-invocation checks.
- Repair only safe generated setup issues; do not overwrite unmanaged host files.
- Preserve `.gwc`, `.ua`, `.task-me`, `.bmad`, `_bmad`, `_bmad-output`, and package history.
- Do not install dashboards, tasks, plans, tests, evals, secrets, or unrelated source content.
- Do not claim `READY` when any required package, routing, host, dedupe, doctor, or invocation check remains incomplete.
- Do not stop after describing commands. Perform every available local setup and validation action now.

Return:

- resolved target system and absolute path;
- detected OS, shell, Python, Node/npm when applicable, current host, configured hosts, and `offline` network mode;
- exact local package paths, checksums, versions, and installed paths;
- configuration, router/adapter, doctor, dedupe, and invocation evidence;
- sanitized commands and changed paths;
- rollback and uninstall commands;
- unresolved blockers and risks;
- `READY`, `PARTIAL`, `BLOCKED`, or `FAILED` status for every Power and host-routing layer;
- explicit confirmation that no remote Power acquisition command ran.
```
