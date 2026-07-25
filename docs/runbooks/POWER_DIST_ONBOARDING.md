# Power Dist Onboarding Runbook

## Purpose

Use this runbook when an agent must install, update, configure, activate, validate, doctor, repair, or invoke DW SUPER Powers for a consumer project.

The required lifecycle is:

```text
DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT
```

Do not stop after describing commands when the environment provides the necessary filesystem and execution capabilities. Do not report `READY` unless installation, required configuration, host activation, doctor checks, and one real invocation all pass.

## Related documents

- Global rules: `AGENTS.md`
- Portable host design: `docs/PORTABLE_MULTI_HOST_ROUTER.md`
- Online/general prompt: `prompts/power-dist/onboard.md`
- Offline ZIP prompt: `prompts/power-dist/onboard-offline-zip.md`
- Workspace registry: `workspace.yaml`
- Power manifests: `manifests/powers/<power-id>.yaml`

## Resolve inputs

Resolve available information instead of asking the user to repeat it.

1. **Control workspace:** current `DW-SuperApps` checkout.
2. **Target system:** explicit user target; otherwise matching system in `workspace.yaml`; otherwise the only enabled system; otherwise `BLOCKED_TARGET_AMBIGUOUS`.
3. **Target path:** the system `path`, unless the user supplied an external consumer path.
4. **Powers:** explicit list; otherwise the target system's `enabled_powers`.
5. **Host:** explicit host; otherwise detect the current IDE/agent host. A portable setup may prepare all configured native adapters once, but no global active-host switch is required.
6. **Source priority:**
   - explicit local package path;
   - valid local inbox ZIP when offline/manual mode applies;
   - manifest `defaultMode` through `--source auto` when online;
   - submodule only for explicitly requested migration or recovery.

Never replace a supplied local package with a Git checkout, release download, `power-dist` archive, or submodule.

## Source of truth

Read and reconcile:

1. local checkout and exact local HEAD;
2. root and target `AGENTS.md` files;
3. `workspace.yaml`;
4. selected Power manifests;
5. `manifests/power-distribution-evidence.json` when present;
6. supplied ZIP/checksum and internal `MANIFEST.json`;
7. existing `.dw/powers/<power-id>/MANIFEST.json`;
8. applicable Power/runtime documentation.

When online, verify the current default branch and exact `main` SHA. When GitHub connectivity is explicitly unavailable, record remote verification as `SKIPPED_OFFLINE`; do not block a valid local package install merely because remote state cannot be queried.

If package identity, version, checksum, manifest, entrypoint, or recorded evidence conflict, report `BLOCKED_DISTRIBUTION_DRIFT`.

## Preflight

Before installation:

1. detect OS, shell, Python, Git, network/GitHub availability, current host, and Node/npm when BMAD is selected;
2. verify the target path is correct and writable;
3. inspect `.dw/inbox/powers`, `.dw/powers`, `.dw/config`, `.dw/history`, `.dw/router`, host adapters, and runtime roots;
4. preserve existing consumer runtime data;
5. refuse unsafe overwrite of unmanaged package, configuration, router, or host files;
6. record the pre-install state for the completion report.

Do not initialize Power submodules during normal Power Dist or offline ZIP onboarding.

## Online installation

Run package lifecycle commands from the `DW-SuperApps` root.

### Bash, Zsh, Linux, macOS, or Git Bash

```bash
./bin/dw power install <power-id> --source auto --target <target-project>
./bin/dw power doctor <power-id> --target <target-project>
```

### Windows PowerShell

Probe whether `dw.ps1` dispatches package lifecycle commands. If not, use the repository-provided direct entrypoint.

```powershell
# Preferred when supported
.\dw.ps1 power install <power-id> --source auto --target <target-project>
.\dw.ps1 power doctor <power-id> --target <target-project>

# Compatibility fallback
py -3 .\scripts\dw_power_package.py install <power-id> `
  --source auto `
  --target <target-project>

py -3 .\scripts\dw_power_package.py doctor <power-id> `
  --target <target-project>
```

A launcher compatibility failure is not a Power failure when the direct runtime entrypoint works.

## Offline ZIP inbox

Use offline package mode when the user copied ZIPs manually or GitHub/package acquisition is blocked.

### Recommended target structure

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
│   ├── powers/                 # installer-managed packages
│   ├── config/                 # target-owned consumer configuration
│   ├── history/                # rollback history
│   └── router/                 # canonical DW router when implemented
├── .gwc/
├── .ua/
├── .task-me/
└── .bmad/
```

`.dw/inbox/powers/` is the user-managed drop zone. Never manually extract or copy package contents into `.dw/powers/`; that directory is installer-managed.

### Offline validation and installation

For each selected Power:

1. scan `<target-project>/.dw/inbox/powers/<power-id>/`;
2. require exactly one candidate ZIP and matching `.zip.sha256` sidecar unless the user named an exact path;
3. identify unconventional filenames using internal `MANIFEST.json`, not filename alone;
4. verify `MANIFEST.json.metadata.powerId` matches the requested Power;
5. verify the archive sidecar checksum before extraction;
6. verify every declared file size and SHA-256;
7. reject absolute paths, parent traversal, archive symlinks, unmanaged overwrite, and identity mismatch;
8. install using `--source package --package <zip> --checksum <sidecar>`;
9. preserve the inbox ZIP and checksum after installation;
10. continue through configuration, host routing, doctor, and invocation.

Use these blockers consistently:

- `BLOCKED_LOCAL_PACKAGE_MISSING`
- `BLOCKED_LOCAL_PACKAGE_AMBIGUOUS`
- `BLOCKED_LOCAL_CHECKSUM_MISSING`
- `BLOCKED_LOCAL_CHECKSUM_INVALID`
- `BLOCKED_PACKAGE_IDENTITY_MISMATCH`

### Offline commands

Bash, Zsh, or Git Bash:

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

### Offline no-network rule

During local/offline/manual package mode, do not acquire the supplied Power through the network. Do not run:

- `git pull`, `git fetch`, `git clone`, or Power submodule initialization;
- `gh release download` or GitHub API package acquisition;
- `curl`, `wget`, release URLs, or `power-dist` downloads;
- `--source auto`, `--source release`, or `--source power-dist` for a locally supplied Power;
- fallback to a Power repository checkout.

Local read-only Git inspection remains allowed. Lack of GitHub connectivity is not a blocker when a valid ZIP and checksum are present.

## Configuration and consumer contracts

After installation:

1. inspect the installed package manifest and declared distribution directories;
2. determine whether configuration is required;
3. use target-owned configuration and consumer contracts;
4. never invent credentials, secrets, or external authority;
5. run `power configure` only with verified inputs;
6. rerun doctor with `--require-config` when configuration is mandatory.

```bash
dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target <target-project>
```

Optional missing configuration is `optional-missing`, not failure.

## Portable multi-host activation

The desired portable profile allows all IDEs to be ready simultaneously without an active-host switch.

Canonical package code remains in:

```text
<target-project>/.dw/powers/<power-id>/
```

The target architecture is:

```text
canonical installed Powers
        -> one canonical DW router
        -> one thin native adapter per host
```

Read `docs/PORTABLE_MULTI_HOST_ROUTER.md` before creating or validating portable host adapters.

Rules:

1. do not copy Power logic into host folders;
2. each host adapter routes to one canonical router or installed Power entrypoint;
3. all native adapters may coexist;
4. opening another IDE must not require changing a global active-host setting;
5. a host must not load duplicate DW skills from compatibility roots;
6. detect duplicate skill names, duplicate Power identities, stale wrappers, broken targets, and cross-host discovery leakage;
7. do not claim the portable router runtime is implemented if the checked-out CLI still generates one adapter per Power;
8. when only the current per-Power generator exists, use it as a compatibility fallback, load only one canonical Power entrypoint for the task, and report router migration as pending rather than fabricating unsupported commands.

Do not use hypothetical commands such as `dw setup portable` unless they exist in the checked-out runtime.

## Host-specific guidance

| Host | Native location | Guidance |
|---|---|---|
| Codex | `.codex/skills/` | Keep one generated DW router wrapper when supported. |
| Kiro | `.kiro/skills/` | Keep one generated DW router wrapper when supported. |
| Claude Code | `.claude/skills/` + `CLAUDE.md` | `CLAUDE.md` should route to root policy; avoid copied policy. |
| GitHub Copilot | `.github/copilot-instructions.md` and supported skill root | Avoid publishing duplicate DW skills in every Copilot-compatible root. |
| Kilo Code | `.kilo/rules/` or `.kilo/skills/` | Isolate external compatibility roots when they produce duplicate discovery. |
| Cline | `.clinerules/` | Use a short routing rule, not copied Power content. |
| Custom | `.agents/` | Use only when the custom host actually needs this compatibility root. |

## BMAD handling

BMAD requires package-native bootstrap.

1. Install and doctor the managed BMAD package first.
2. Verify Node.js and npm.
3. Run `distribution/lib/bootstrap_bmad.py` for the selected host.
4. If bootstrap rejects a package inside the consumer target, copy the already verified package to a temporary directory outside the target, bootstrap from that verified copy, then remove it.
5. Validate generated host files and `.dw/bmad-bootstrap.json`.
6. Use `bmad-help` as the routing entrypoint.

Do not install the BMAD website, dashboard, repository tests, evals, generated web bundles, or source-project data.

## Runtime ownership

| Power | Target-owned runtime root |
|---|---|
| GWC | `.gwc/` |
| UA | `.ua/` |
| Task Me | `.task-me/` |
| BMAD | `.bmad/`, `_bmad/`, and `_bmad-output/` only when declared by the installed package/modules |

Uninstall preserves runtime by default. Runtime deletion requires explicit destructive authorization and confirmation flags.

## Doctor matrix

Validate every applicable gate:

| Gate | Required result |
|---|---|
| Source | Online distribution is valid, or local package mode is explicit. |
| Local package | ZIP and checksum are present, unambiguous, and valid when offline. |
| Integrity | Package identity, file sizes, and SHA-256 hashes pass. |
| Installation | `.dw/powers/<power-id>/` is managed and contains `.dw-managed.json`. |
| Entrypoint | At least one manifest-declared entrypoint exists. |
| Runtime | Target-owned runtime root exists and stays inside the target. |
| Configuration | Required config/contract is managed and valid. |
| Router | Canonical router exists when the portable profile is implemented. |
| Host | Current host adapter resolves one canonical router or package entrypoint. |
| Dedupe | No duplicate DW skill identity is visible to the current host. |
| Native bootstrap | Required package-specific marker and generated files exist. |
| Workspace | `dw validate` passes when applicable. |
| Safety | No secret, traversal, unmanaged overwrite, dashboard, task, plan, or unrelated-source contamination. |
| Network discipline | No remote Power acquisition ran during offline mode. |

Use statuses exactly:

- `READY`: installation, required configuration, activation, doctor, and invocation pass.
- `PARTIAL`: package is valid but config, bootstrap, routing, activation, or invocation is incomplete.
- `BLOCKED`: a required dependency, authority, package, checksum, target, or safety condition prevents progress.
- `FAILED`: an executed validation returned a real failure.

Never convert `PARTIAL` or `BLOCKED` into `READY`.

## Use after onboarding

Before executing a Power task:

1. confirm the Power is enabled for the target;
2. read target instructions;
3. read the installed package manifest;
4. route through the canonical router when implemented, otherwise select the first existing canonical Power entrypoint;
5. load only the selected Power workflow;
6. keep outputs in the target-owned runtime root;
7. follow Power authority boundaries;
8. record canonical evidence before external notification.

Installing a Power does not grant GitHub write, Jira write, Slack, deployment, merge, approval, or production authority.

## Completion report

Return:

| Power | Source | Package path | Version/SHA | Install | Config | Router/Host | Doctor | Runtime | Status |
|---|---|---|---|---|---|---|---|---|---|

Also include:

- target system and absolute target path;
- detected OS, shell, Python, Node/npm when applicable, host, and network mode;
- exact sanitized commands executed;
- created or changed paths;
- package, router, host, and invocation evidence;
- duplicate discovery findings;
- unresolved blockers and risks;
- rollback or uninstall commands;
- confirmation that runtime and inbox packages were preserved;
- confirmation that no remote acquisition command ran during offline mode;
- confirmation that no dashboard, task, plan, secret, test, eval, or unrelated source content was installed.
