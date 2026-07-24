# DW SuperApps Setup and Optional Deployment Lanes

This guide sets up the governed DW SuperApps workspace for local AI hosts. GWC, Task Me, and UA now default to their validated `power-dist` distributions. Reviewed git submodules remain available as a migration and recovery fallback.

## 1. Clone the workspace

```bash
git clone --recurse-submodules \
  https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
```

For an existing clone:

```bash
git pull --ff-only
git submodule sync --recursive
git submodule update --init --recursive
```

The fallback submodule pins remain:

- GWC: `62689ce35e279751a3bf17b5255ac258dafbe7d7`
- Task Me: `ef0b890b1fb9140109c04cbb490b41d9aa94bfff`
- UA upstream: `6ae71878beb50226a1e4b7e2f52ac6468c86f74b`

The published distributions are:

- GWC: `main-20260725.1-62689ce`
- Task Me: `main-20260725.1-ef0b890`
- UA: `main-20260725.1-c0e4821`

## 2. Install the `dw` launcher

### macOS or Linux with Zsh

```bash
./bin/dw install --shell zsh --init
source ~/.zshrc
dw --version
```

### Bash or Git Bash

```bash
./bin/dw install --shell bash --init
source ~/.bashrc
dw --version
```

### Windows PowerShell

```powershell
.\dw.ps1 power init powers
.\dw.ps1 power status powers
```

The installer is idempotent. Runtime data remains system-owned under `.gwc`, `.task-me`, `.ua`, and `.bmad` in the target product repository.

## 3. Initialize and validate the workspace

```bash
dw power init powers
dw power status powers
dw validate
```

Submodules are not the default distribution source, but keeping them initialized provides an offline and rollback fallback during migration.

## 4. Initialize Kiro and Codex adapters

### Kiro

```bash
dw host install kiro --mode wrapper
dw host status kiro
```

### Codex

```bash
dw host install codex --mode wrapper
dw host status codex
```

Host adapters are generated discovery layers. Canonical instructions and tools remain in the Power distributions or provider repositories.

## 5. Generate Power prompts

### GWC governance

```bash
dw power prompt gwc \
  --system rental-home \
  --task "Recover the current governed task state and execute the next authorized gate"
```

### Understand Anything

```bash
dw power prompt ua \
  --system rental-home \
  --task "Refresh the Rental Home architecture and codebase knowledge graph"
```

### Task Me

```bash
dw power prompt task-me \
  --system rental-home \
  --task "Create an implementation plan with impact analysis for OPS-LEASE"
```

Useful discovery commands:

```bash
dw power list
dw power info gwc
dw power info task-me
dw power info ua
dw system powers rental-home
```

## 6. Distribution modes

The default for GWC, Task Me, and UA is now `power-dist`.

- `power-dist`: consumes the validated provider distribution branch.
- `release`: downloads the immutable provider ZIP and checksum.
- `submodule`: uses the reviewed gitlink as migration and recovery fallback.
- `package`: installs a locally validated package or ZIP.

All three providers have published immutable releases and synchronized `power-dist` branches. Switching the default does not remove the gitlinks or prevent explicit submodule use.

## 7. Task Me Vercel dashboard is optional

Task Me provider/package health is separate from its Vercel dashboard deployment.

Observed runs:

- `30110774540`: repository CI passed; only Vercel Preview failed during secret verification.
- `30110779783`: Vercel Production failed during secret verification.

The failures indicate missing deployment configuration, not a Task Me provider failure.

Required GitHub Actions secrets when Vercel deployment is enabled:

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

Vercel deploy jobs should be gated by:

```yaml
if: vars.VERCEL_DEPLOY_ENABLED == 'true'
```

Default state:

```text
VERCEL_DEPLOY_ENABLED is absent or false
```

In that state, Task Me CI and Power validation continue normally while preview and production deployment remain disabled.

Credential creation and repository-secret changes are outside the Power distribution lifecycle and require a separate authorized operational task.

## 8. Safety boundaries

Local setup and distribution consumption do not authorize:

- deploying the Task Me dashboard;
- modifying credentials or secrets;
- production configuration or migration changes;
- production-data operations.
