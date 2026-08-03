# Session: Reinstall DW SuperApps Powers from Latest Source

**Date:** 2026-08-02T22:36+07:00
**Workspace:** /Users/mac/prj/DW-SuperApps
**Branch:** `chore/reinstall-powers-latest`
**Outcome:** Committed (8566180) + pushed + PR created (#43)
**Status:** PASS — all power doctors and workspace doctor validated cleanly

---

## 0. Objective

Reinstall all four registered DW SuperApps Powers (`gwc`, `ua`, `task-me`, `bmad`)
from the latest submodule sources, install them into `.dw/powers/`, update the
workspace manifests and the `power-compatibility-lock.json`, and land the change
as a feature-branch PR.

### Registered Powers (from `.kilo/agent/dw-superapps.md`)
- gwc → `.dw/powers/gwc` (entrypoint `skills/gwc-g0`); runtime `.gwc/`
- ua → `.dw/powers/ua` (entrypoint `understand-anything-plugin/skills/understand`); runtime `.ua/`
- task-me → `.dw/powers/task-me` (entrypoint `.kiro/skills/implementation-task-architect`); runtime `.task-me/`
- bmad → `.dw/powers/bmad`; runtime `.bmad/`

All are `defaultMode: power-dist` (GitHub power-dist branches).

---

## 1. Pre-flight discovery

### 1.1 Existing installation state (`dw power check` output, summarized)
| Power | Gitlink pin | Submodule HEAD | origin/main | Source-sha (installed) |
|-------|-------------|----------------|-------------|------------------------|
| gwc   | `2c4e8544`  | `aad17d2`      | `aad17d2`   | `3b6c22be`             |
| ua    | `f01391f7`  | `7b6a0a9`      | `7b6a0a9`   | `4d5fda706`            |
| task-me | `bfa0752` | `bfa0752`      | n/a         | `bfa0752`              |
| bmad  | `fdc47614`  | `fdc47614`     | n/a         | `fdc47614`             |

State: gwc/ua "working-copy-moved" (submodule HEAD ≠ gitlink pin);
task-me/bmad "pinned".

### 1.2 Manifest drift
- gwc manifest version `gwc-main-28-3b093806`, sourceCommit `3b093806…` (stale vs installed).
- ua manifest version `ua-main-f01391f7`, sourceCommit `f01391f7…` (stale vs installed).
- task-me manifest version `task-me-main-bfa0752d` (missing `3-` from tag).
- bmad manifest version `bmad-main-fdc47614` (already current).
- ua `skillCandidates`: only `understand-anything-plugin/skills/understand/SKILL.md`.
- `power-compatibility-lock.json` checked 2026-07-30, stale versions/SHAs/entrypoints.

### 1.3 Key decision
GitHub `power-dist` branches are stale for gwc/ua (they point at already-installed
commits). Local rebuild from submodule `main` is the only way to get genuinely
current content while online/offline. → Chose **Option C1**: local submodule
rebuild + staging + gitlink commit + PR.

---

## 2. Feature branch created
```
git checkout -b chore/reinstall-powers-latest
```

---

## 3. Submodules synchronized to latest main

```bash
# gwc
git -C projects/gwc checkout main
git -C projects/gwc pull --tags origin main       # → aad17d2 (Fast-forward, Merge PR #181)

# ua  (origin/main == HEAD, no pull needed)
git -C projects/ua status                          # current = remote = 7b6a0a9

# task-me / bmad (pinned at tags, no change)
```

### 3.1 Concurrent-agent discovery (mid-session)
While rebuilding, the gwc submodule HEAD moved from `aad17d2` to a feature branch
`hermes/scrum-202-checkpoint-capture-m5-20260802` → commit `234287d`
("implement runtime_checkpoint.checkpoint-capture node, M5_REPLAY_SAFE").

Reflog investigation:
```
520aa19 HEAD@{…: commit: feat(gwc): implement runtime_checkpoint.checkpoint-capture node (SCRUM-202, M5_REPLAY_SAFE)
aad17d2 HEAD@{…: checkout: moving from main to hermes/scrum-202-checkpoint-capture-m5-20260802
aad17d2 HEAD@{…: pull --ff-only --tags origin main: Fast-forward
```

A desktop **Hermes agent** process was found running concurrently:
`/Users/mac/.hermes/hermes-agent/.../hermes_cli.main serve`.
Agent worktrees existed at `.worktree/scrum-205` and `.worktrees/{fl-dwsuper-01-…,gg-oauth-e2e,scrum-229}`.

**Decision:** Reset gwc back to `origin/main` (`aad17d2`) for a clean, deterministic
rebuild (avoids silently incorporating an off-main feature-branch commit mid-build).

### 3.2 Re-pull to true latest (after merge discovery)
`dw doctor` later reported gwc `remote=520aa1968a08` (45 commits ahead of
`aad17d2`). Inspection showed `234287d` is an **ancestor** of `520aa19` — i.e.
the replay-safe checkpoint work + SCRUM-263 had been **merged into gwc `main`**
via PR #183/#184. This is exactly the work the prior session was converging on.

```bash
git -C projects/gwc checkout main
git -C projects/gwc pull --ff-only origin main    # aad17d2 → 520aa19 (45 commits)
git -C projects/gwc clean -fdx                    # remove runtime artifacts + pycache
```

Final submodule HEADs:
| Power | HEAD | describe |
|-------|------|----------|
| gwc | `520aa1968a0809001e8994192278e52a59c86c61` | `gwc-main-43-3b6c22be-375-g520aa19` |
| ua | `7b6a0a931a4f5c6f21eaf4a485738098b8f84286` | `ua-main-3-4d5fda706-4-g7b6a9` |
| task-me | `bfa0752d9ca2c4e57cfe219c16294e728fc6a16b` | `task-me-main-3-bfa0752d…` |
| bmad | `fdc47614b5903bf342ca92d9547ae4c49817aa3a` | `bmad-main-fdc47614` |

---

## 4. Workspace manifests updated

### gwc.yaml
- `metadata.version` → `gwc-main-43-3b6c22be933036887a7ae96002e5a48677583812-375-g520aa19`
- `distribution.providerState.sourceCommit` → `520aa1968a0809001e8994192278e52a59c86c61`
- note → "Local rebuild from latest submodule main (520aa19); power-dist branch on remote remains a compatibility fallback."

### ua.yaml
- `metadata.version` → `ua-main-3-4d5fda706fc9683d097cedc947a02011f11baa38-4-g7b6a0a9`
- `distribution.providerState.sourceCommit` → `7b6a0a931a4f5c6f21eaf4a485738098b8f84286`
- `entrypoints.skillCandidates` expanded from 1 to 9 SKILL.md paths (the latest ua source ships 8 companion skills: understand-chat/explain/diff/dashboard/domain/onboard/knowledge/figma, plus the original understand).
- note updated.

### task-me.yaml
- `metadata.version` normalized to `task-me-main-3-bfa0752d9ca2c4e57cfe219c16294e728fc6a16b`
  (matching the tag that `git describe` emits; sourceCommit + note unchanged in substance).

### bmad.yaml — unchanged
(version/sourceCommit already current; entrypoints now include `tools/power-help.js`.)

---

## 5. Distribution packages rebuilt

```bash
python3 scripts/distribution_builder.py \
  --foundation-ref "$(git rev-parse HEAD)" \
  --power gwc --power ua --power task-me --power bmad
```
(`distribution_build.sh` hard-codes `python`; only `python3` exists on this host,
so the Python scripts were invoked directly.)

> Note: a `git pull` on gwc during `main` rebuild re-fetched; final build ran after
> the `520aa19` pull. (The initial build artifact from `234287d` was discarded.)

Built assets in `.dw/distributions/assets/` (all checksums verified):
| Power | Archive | pkg sha256 |
|-------|---------|------------|
| gwc | `gwc-gwc-main-43-…-375-g520aa19.zip` | `42f632cb…` |
| ua | `ua-ua-main-3-…-4-g7b6a0a9.zip` | `03ada0dc…` |
| task-me | `task-me-task-me-main-3-bfa0752d…zip` | `fac7467c…` |
| bmad | `bmad-bmad-main-fdc47614.zip` | `d62c93ed…` |

Build summary written to `.kilo/staging/power-dist/build-summary.json`.

---

## 6. Packages installed into `.dw/powers/`

Consumer target = `projects/rental-home` (the single product project with all four
powers enabled in `workspace.yaml`).

```bash
./bin/dw power install <id> --source package \
  --package .dw/distributions/assets/<zip> \
  --checksum  .dw/distributions/assets/<zip>.sha256 \
  --target projects/rental-home
```

Results (JSON, abbreviated):
| Power | status | package_version | backup path |
|-------|--------|-----------------|-------------|
| gwc | INSTALLED | `gwc-main-43-…-375-g520aa19` | `.dw/history/powers/gwc/…` |
| ua | INSTALLED | `ua-main-3-…-4-g7b6a0a9` | `.dw/history/powers/ua/…` |
| task-me | INSTALLED | `task-me-main-3-bfa0752d…` | `.dw/history/powers/task-me/…` |
| bmad | INSTALLED | `bmad-main-fdc47614` | `.dw/history/powers/bmad/main-fdc47614-…` |

Runtime roots confirmed under `projects/rental-home/`: `.gwc/`, `.ua/`,
`.task-me/`, `.bmad/`. No `LEGACY_TARGET_INSTALL` detected (no
`.dw/powers/` inside the consumer project).

---

## 7. Compatibility lock regenerated

`manifests/power-compatibility-lock.json` (schema v1.0, validated by
`schemas/power-compatibility-lock.schema.json`) was rebuilt programmatically to
match the new packages and manifests:

| Field updated (gwc example) | Old | New |
|-----------------------------|-----|-----|
| `packageVersion` | `gwc-main-28-3b093806` | `gwc-main-43-…-375-g520aa19` |
| `publishedSourceSha` | `3b093806…` | `520aa19…` |
| `providerHeadSha` | `3b093806…` | `520aa19…` |
| `entrypoints` | `[gwc-g0, gwc-g1]` | `[gwc-g0, gwc-g1, tools/power_help.py]` |
| `status` | CURRENT | CURRENT (providerHeadSha == publishedSourceSha) |
| `note` | "Published release …" | "Local rebuild from latest submodule main (520aa19)…" |
| `checkedAt` | `2026-07-30T23:32:43+07:00` | `2026-08-02T…Z` |

Same regeneration applied to ua, task-me, bmad. `validate_lock` SKILL.md-subset
check passes for every power (ua manifest skillCandidates now cover all 9 SKILL.md
entrypoints).

---

## 8. Validation

### 8.1 Power doctors
```
dw power doctor <id> --target projects/rental-home  (×4)
```
| Power | status | compat | warnings |
|-------|--------|--------|----------|
| gwc | PASS | PASS | [] |
| ua | PASS | PASS | [] |
| task-me | PASS | PASS | [] |
| bmad | PASS | PASS | [] |

Each: package PASS, runtime PASS, binding managed.

### 8.2 Workspace doctor
```
dw doctor   →  PASS: 6 projects, 4 Powers, 1 runtime targets, 7 hosts,
             1 providers, 6 submodules, store=.dw/powers, compatibility=PASS
```
- Submodules gwc/ua: pinned (gitlink == working tree == origin/main).
- `projects/rental-home`: `working-copy-moved` (untouched by this PR — consumer project).
- All 7 host adapters `ready`.
- ollama provider `ready`.

### 8.3 Workspace validation
`validate-workspace.py` (invoked via `dw doctor`) → schema validation of
`power-compatibility-lock.json` **PASS**; `validate_lock` **PASS** (version,
sourceCommit, entrypoint, status all consistent across manifest ↔ lock ↔ package).

---

## 9. Git commit + PR

Only intended files staged; out-of-scope items left untacked/unstaged
(`projects/rental-home` gitlink, `.kiro/steering/gwc-governance.md`,
`.worktree/`, `.worktrees/`):

```
 M manifests/power-compatibility-lock.json
 M manifests/powers/gwc.yaml
 M manifests/powers/task-me.yaml
 M manifests/powers/ua.yaml
 M projects/gwc         (gitlink 2c4e854 → 520aa19)
 M projects/ua          (gitlink f01391f → 7b6a0a9)
```

The commit was amended twice (once to correct gwc from `aad17d2` → `520aa19`
after the merge was discovered). Final commit:

```
8566180 chore(powers): reinstall all 4 powers from latest source + sync compatibility lock
```

```bash
git push -u origin chore/reinstall-powers-latest
gh pr create --base main --head chore/reinstall-powers-latest \
  --title "chore(powers): reinstall all 4 powers from latest source + sync compatibility lock" \
  -F <pr-body>
```
→ **PR #43** — https://github.com/nhatnguyenquang1838-coder/DW-SuperApps/pull/43

---

## 10. Post-commit consistency (verified)

| Artifact | gwc | ua |
|----------|-----|-----|
| committed gitlink (HEAD:projects/gwc) | `520aa19…` | `7b6a0a9…` |
| installed package sourceSha | `520aa19…` | `7b6a0a9…` |
| lock publishedSourceSha | `520aa19…` | `7b6a0a9…` |
| lock providerHeadSha | `520aa19…` | `7b6a0a9…` |

All consistent.

---

## 11. Caveats / outstanding items

1. **Concurrent agent churn.** A Hermes desktop agent is actively pushing to
   `gwc` `main` and writing untracked `.gwc/tasks/SCRUM-*` runtime artifacts into
   the `projects/gwc` working copy. These are runtime/task-output data, **not**
   source, and are excluded from the committed gitlink (which pins the clean
   commit `520aa19`). If `gwc` `main` advances further, a follow-up reinstall
   cycle would be needed to capture newer commits. The current install is
   verified against `520aa19`.
2. **`projects/rental-home` gitlink** (`26b9ba64` → `e286b5ee`) was left
   untouched — it is the consumer product project, out of scope for this power
   reinstall.
3. **`.worktree/`** (singular, contains `scrum-205`) and **`.worktrees/`** are
   git-linked worktrees used by other agent sessions; left untracked.
4. **`distribution_build.sh` uses `python` (not `python3`)** — this host only has
   `python3`, so the build/installer scripts were invoked with `python3` directly.
5. PR approval/gating: per FastLane governance, the change proceeds through the
   **G4 merge** workflow for approval — no merge/deploy was performed by this
   session.
