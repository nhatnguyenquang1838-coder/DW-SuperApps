# DW SuperApps Setup and Optional Deployment Lanes

This guide sets up the governed DW SuperApps workspace for local AI hosts. Local Power use is independent from provider release publication and from the optional Task Me Vercel dashboard.

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

The reviewed Power pins for this integration are:

- GWC: `62689ce35e279751a3bf17b5255ac258dafbe7d7`
- Task Me: `ef0b890b1fb9140109c04cbb490b41d9aa94bfff`
- UA legacy upstream submodule: `6ae71878beb50226a1e4b7e2f52ac6468c86f74b`
- UA controlled distribution provider: `c0e4821c519f564d6c8b353537cf121eb52a1617`

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
.\dw.ps1 init all
.\dw.ps1 status all
.\dw.ps1 doctor all
```

The installer is idempotent. Runtime data remains system-owned under `.gwc`, `.task-me`, `.ua`, and `.bmad` in the target product repository.

## 3. Validate the workspace

```bash
dw status all
dw doctor all
```

For offline validation without remote drift checks:

```bash
dw doctor all --offline
```

Daily flow:

```bash
dw status all
dw sync all
dw doctor all
```

`dw sync all` updates clean submodules but does not stage or commit gitlink changes. Use `dw sync all --pin` only when intentionally preparing reviewed pin changes.

## 4. Initialize Kiro and Codex adapters

### Kiro

```bash
dw init all --host kiro
dw host status kiro
```

Open the DW-SuperApps root in Kiro.

### Codex

```bash
dw init all --host codex
dw host status codex
```

Open the DW-SuperApps root in Codex.

Host adapters are generated discovery layers. Canonical instructions and tools remain in the Power repositories.

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

The migration default remains `submodule`.

- `submodule`: uses the reviewed gitlink in DW-SuperApps.
- `package`: installs a locally validated package or ZIP.
- `release`: downloads an immutable provider release and checksum.
- `power-dist`: consumes the provider distribution branch.

Provider releases and `power-dist` branches are currently `ready-unpublished`. Local submodule setup does not publish packages and does not require release credentials.

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

### Selected operating strategy

Vercel deploy jobs should be gated by an explicit repository variable:

```yaml
if: vars.VERCEL_DEPLOY_ENABLED == 'true'
```

Default state:

```text
VERCEL_DEPLOY_ENABLED is absent or false
```

In that state:

- Task Me CI and Power validation continue normally.
- Preview and production deploy jobs are skipped rather than failed.
- No Vercel credential is required for local DW SuperApps use.

To enable deployment later:

1. Create or import the Task Me project in Vercel.
2. Add the three required secrets to the `task-me` GitHub repository.
3. Set repository variable `VERCEL_DEPLOY_ENABLED=true`.
4. Re-run or trigger the applicable deployment workflow.

Credential creation and repository-secret changes are outside SCRUM-94 and require a separate authorized operational task.

## 8. Safety boundaries

Local setup does not authorize:

- merging the DW-SuperApps integration PR;
- publishing provider releases or `power-dist` branches;
- deploying the Task Me dashboard;
- modifying credentials, secrets, production configuration, migrations, or production data.
