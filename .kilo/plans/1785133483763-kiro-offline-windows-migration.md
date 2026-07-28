# Migration Plan: Kiro-Only Offline Windows Instance

## 1. Context & Constraints

**Source**: `/Users/mac/prj/DW-SuperApps` (current workspace HEAD)  
**Target**: Fresh isolated DW-SuperApps instance on Windows, Kiro host only  
**Transport**: Offline ZIP package only; no GitHub sync, no internet access  
**Shell**: Bash only (Git Bash / MSYS2 / WSL bash); no cmd.exe or PowerShell  
**Update model**: Versioned ZIP delta or full replacement; runtime data preserved  

---

## 2. Scope

- Deploy a self-contained DW-SuperApps workspace that boots without external network calls.
- Host adapter set: `kiro` only. Remove or omit `codex`, `copilot`, `cline`, `kilo`, `claude`, `custom`, and orchestrator adapters from the target package.
- Powers packaged: `gwc`, `task-me`, `bmad`, `ua` — full distribution payloads, not submodule pointers.
- System target: `rental-home` runtime roots (`.gwc/`, `.task-me/`, `.ua/`, `.bmad/`) created on first run; no pre-seeded runtime data required.
- Package must be relocatable to any Windows path containing only ASCII characters and no spaces (to avoid bash quoting issues).

**Out of scope**:
- Migrating existing runtime artifacts from a prior Windows instance (covered under backward-compat restore, not initial packaging).
- Jira/Slack/PR integrations (governance-only local workflow).
- GitHub write operations.

---

## 3. Spec-Driven Artifacts (task-me Methodology)

Use the `implementation-task-architect` runbook to generate the following Kiro-compatible, evidence-backed artifacts inside the package under `.kilo/plans/migration/`:

| Artifact | Purpose | Format |
|---|---|---|
| `MIGRATION-SPEC.yaml` | Canonical requirements, acceptance criteria, and design decisions for the offline Windows package | YAML with stable IDs |
| `MIGRATION-DESIGN.md` | Architecture of the package layout, bash bootstrap, zip update protocol, and backward-compat layer | Markdown with section IDs |
| `task-index.yaml` | Task decomposition: every migration step as a stable task with dependency DAG, complexity, risk, effort, and validation | YAML |
| `<task-slug>/task.yaml` | One folder per task with requirement/design traceability, implementation guidance, test commands, and decision record | YAML + companion files |
| `task-dag.mmd` | Mermaid DAG of migration tasks | MMD |
| `RUN-SUMMARY.md` | Human-readable execution summary with wave assignments and known risks | Markdown |
| `.ua/extensions/planning-graph.json` | Updated planning graph reflecting migration tasks | JSON |
| `.ua/extensions/traceability-graph.json` | Requirement-to-task traceability | JSON |

**Task-me quality rules applied**:
- Every task has a stable ID (e.g., `MIG-001`) and filesystem-safe slug.
- Dependencies validated; no circular references.
- Complexity / risk / three-point effort estimates per task.
- One task folder per task; no combined folders.
- Observable decision records (evidence, alternatives, rule, decision, confidence, unresolved uncertainty) inside each task folder.

---

## 4. Execution Plan

### Phase 0 — Repository Snapshot
1. Create a clean detached tree from current HEAD.
2. Remove host adapters other than `kiro` (`.codex/`, `.claude/`, `.clinerules/`, `.agents/custom`, etc.).
3. Remove `.kilo/worktrees/`, `.kilo/plans/`, and any session artifacts not needed at runtime.
4. Strip `.git/` metadata and submodule pointers to avoid accidental network fetches on Windows.
5. Verify the tree runs `dw --version` and `dw doctor all` in a Linux bash sandbox before packaging.

### Phase 1 — Offline Package Assembly
1. **Power payloads**: Copy the installed distributions from `.dw/powers/<power-id>/` into `packages/powers/<power-id>/` inside the package. Include `distribution/`, `skills/`, `lib/`, `MANIFEST.json`, `POWER.yaml`, and `VERSION`.
2. **Kiro adapter only**: Place the kiro host adapter in `hosts/kiro/`. Remove all other host directories.
3. **Bootstrap scripts**: Add `install.sh`, `update.sh`, `rollback.sh`, and `doctor.sh` under `scripts/` (see §5).
4. **Version manifest**: Write `PACKAGE-VERSION.yaml` with `package_version`, `base_sha`, `powers` map (id + version), and `min_workspace_version`.
5. **Zip layout validation**: Run a read-only script that asserts no symlinks, no `.git/`, no `projects/` submodule directories, and no Windows-unsafe characters in paths.

### Phase 2 — Windows Bash Installation
1. Transfer `dw-windows-kiro-<version>.zip` to the Windows machine.
2. Extract to a path without spaces, e.g., `/c/dw-superapps/` or `/d/dw/`.
3. Run `bash scripts/install.sh --target /c/dw-superapps --profile bash`.
4. Script creates `bin/dw` launcher, appends `~/.bashrc` PATH block, and validates Python interpreter availability.
5. Run `dw init all --skip-deps` to initialize empty runtime roots (`.gwc/`, `.task-me/`, `.ua/`, `.bmad/`) without fetching anything.
6. Run `dw doctor all` to verify READY/PARTIAL/BLOCKED status.

### Phase 3 — Update Mechanism
1. **Full replacement**: Each release is a complete ZIP named `dw-windows-kiro-<version>.zip`.
2. **Delta optionality**: A companion `dw-windows-kiro-<version>.delta.zip` may contain only changed files under `packages/powers/`, `hosts/`, `scripts/`, and `PACKAGE-VERSION.yaml`. Delta application requires a matching `BASE-VERSION` in the existing install.
3. **Update script**: `scripts/update.sh` performs:
   - Version compatibility check against installed `PACKAGE-VERSION.yaml`.
   - Backup of current runtime roots (`.gwc/`, `.task-me/`, `.ua/`, `.bmad/`) to `.backup/<timestamp>/`.
   - Extraction of new package over the workspace tree (excluding runtime roots).
   - Validation via `dw doctor all`.
   - Automatic rollback if validation returns FAILED.

### Phase 4 — Backward Compatibility
1. **Runtime data isolation**: All runtime data stays outside versioned package paths. The install script creates:
   - `workspace/.gwc/`
   - `workspace/.task-me/`
   - `workspace/.ua/`
   - `workspace/.bmad/`
2. **Version tolerance**: Each Power's `MANIFEST.json` declares `min_workspace_version`. The doctor gate compares installed workspace version against Power requirements and reports `PARTIAL` if ahead, `BLOCKED` if behind.
3. **Schema migration**: If a new package version requires schema changes inside runtime roots, a `scripts/migrate-runtime.sh` runs idempotent migrations and writes a `MIGRATION-APPLIED` marker. No runtime migration runs during a delta update unless explicitly flagged in `PACKAGE-VERSION.yaml`.
4. **Rollback**: Unzip the previous `dw-windows-kiro-<old-version>.zip` and restore runtime roots from `.backup/<timestamp>/`.

---

## 5. Artifacts for Offline Installation

### 5.1 Package Layout
```
dw-windows-kiro-<version>.zip
├── PACKAGE-VERSION.yaml
├── bin/
│   └── dw                      (bash launcher)
├── scripts/
│   ├── install.sh              (Windows bash installer)
│   ├── update.sh               (versioned update with backup)
│   ├── rollback.sh             (restore previous package + runtime backup)
│   ├── doctor.sh               (offline health check wrapper)
│   └── migrate-runtime.sh      (idempotent runtime schema migrations)
├── hosts/
│   └── kiro/                   (adapter only)
├── packages/
│   └── powers/
│       ├── gwc/
│       ├── task-me/
│       ├── bmad/
│       └── ua/
├── .dw/
│   └── powers/                 (symlink-free mirrors of packages/powers/)
├── .kilo/
│   └── rules/
│       └── dw-superapps.md     (Kilo adapter rules, Kiro-only)
├── workspace.yaml              (Kiro-only hosts list)
└── docs/
    └── OFFLINE-README.md       (Windows Bash quickstart)
```

### 5.2 Bash Scripts (no cmd, no PowerShell)

All scripts use `#!/usr/bin/env bash`, `set -euo pipefail`, and POSIX-compatible parameter expansion tested under Git Bash. No cmd.exe or PowerShell entrypoints are created.

### 5.3 Offline README (`docs/OFFLINE-README.md`)
- Prerequisites: Git Bash (or any bash with `unzip`, `python3`, `coreutils`).
- Step-by-step extraction, install, init, and doctor commands.
- Update and rollback procedures.
- Troubleshooting table (path-with-spaces failure, missing python, permission errors).

---

## 6. Validation Plan

| Check | Command | Pass Criteria |
|---|---|---|
| Package integrity | `unzip -t dw-windows-kiro-*.zip` | No errors |
| Install | `bash scripts/install.sh --target ./test-install --profile bash` | Launcher created, PATH block appended |
| Init | `dw init all --skip-deps` | Runtime roots created, no network calls |
| Doctor | `dw doctor all` | `READY` for all Powers, no `FAILED` |
| Update (full) | `bash scripts/update.sh ./new-version.zip` | Validates, backs up, extracts, doctor passes |
| Update (delta) | `bash scripts/update.sh ./new-version.delta.zip` | Validates base version, applies delta, doctor passes |
| Rollback | `bash scripts/rollback.sh <timestamp>` | Restores previous zip + runtime backup |
| Backward compat | Run doctor with old runtime data against new package | Reports `PARTIAL` or `READY`, never data loss |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Windows path with spaces breaks bash scripts | Installer rejects non-ASCII/space paths; documentation enforces `C:\dw-superapps` or `/d/dw/`. |
| Git Bash missing `python3` | Installer checks `python3` and `python`; fails fast with install instructions. |
| Submodule or git metadata leakage into ZIP | Phase 0 script strips `.git/`, `.gitmodules`, and `projects/*/.git` before zipping. |
| Power version mismatch after update | `PACKAGE-VERSION.yaml` enforces `min_workspace_version`; doctor gates compatibility. |
| Runtime data corruption during update | Atomic backup to `.backup/<timestamp>/` before extraction; rollback script restores it. |

---

## 8. Dependencies Between Tasks

```
MIG-001 (Snapshot & sanitize tree)
  -> MIG-002 (Assemble package layout)
    -> MIG-003 (Write bootstrap scripts)
      -> MIG-004 (Create offline README)
        -> MIG-005 (Package & integrity test)
          -> MIG-006 (Generate spec-driven artifacts)
            -> MIG-007 (Validate in Linux bash sandbox)
              -> MIG-008 (Sign & release ZIP)
```

---

## 9. Assumptions

1. The Windows target has Git Bash or an equivalent bash environment with `unzip`, `python3`, and basic coreutils.
2. No Power or system requires runtime data from the source macOS instance at first boot.
3. Kiro host adapter in the installed `gwc` distribution is sufficient; no custom host routing changes are needed beyond removing other adapters.
4. The `projects/` submodule directories are not needed at runtime because Power payloads are redistributed under `packages/powers/` and `.dw/powers/`.

---

## 10. Open Questions

1. Should the package include pre-built Python bytecode (`.pyc`) to avoid requiring a compiler on Windows, or rely on `python3` interpreter only?
2. Do we need a Windows-specific `install.bat` shim that launches Git Bash, or is `README` instruction to run `bash scripts/install.sh` sufficient?
3. Should delta updates be supported in v1, or should v1 ship full ZIPs only?
