# Plan: Install (sync) `projects/ua` and `projects/rental-home` submodules

## Goal
Bring the two git submodules `projects/ua` and `projects/rental-home` into a consistent,
initialized state matching the DW-SuperApps superproject's recorded gitlinks, so the UA
power source and the rental-home product source are both present and usable.

## Current state (verified, read-only)

| Submodule | Recorded gitlink (superproject HEAD) | Local checkout | `.git/modules` | Init state | Working-tree effect |
|---|---|---|---|---|---|
| `projects/ua` | `f01391f` | `7b6a0a9` (+1 ahead) | yes | initialized | superproject dirty (`M projects/ua`) |
| `projects/rental-home` | `26b9ba6` | n/a (no modules dir) | no | **not initialized** | untracked runtime artifacts present on disk |

- `projects/ua` is 1 commit ahead with `7b6a0a9` "fix(distribution): ship UA companion skills (#10)".
- `projects/rental-home/` exists on disk but is **not** a functional submodule checkout. It holds
  only regenerable runtime artifacts (`.ua`, `.bmad`, `.gwc`, `.task-me`, `docs/architecture/`)
  that are **untracked** by the superproject (the gitlink is the only tracked entry).
- The UA **power package** is already installed at `.dw/powers/ua` and **already bound** to
  rental-home (`.dw/bindings/rental-home/ua.json` → store `.dw/powers/ua`, runtime
  `projects/rental-home/.ua`, packageVersion `ua-main-3-4d5fda706fc9683b…` = derived from `f01391f`).
- `bin/dw power install <power_id> --source auto --target projects/<project-id>` is the DW
  power-install entry point.

## Decisions

1. **UA submodule sync direction.** Reset `projects/ua` back to its recorded gitlink `f01391f`
   (discards the local `#10` distribution commit), OR advance the superproject gitlink to the
   current `7b6a0a9` and update the binding packageVersion.
   - **Recommendation: reset to `f01391f`.** The installed UA power package and binding were built
     from `f01391f`; the local `#10` commit is unrelated to "install the submodule" and would leave
     the package out of sync. Advancing the gitlink is a separate change (requires a branch + PR to
     the protected `main`, per AGENTS.md) and is out of scope for this install task.
2. **rental-home non-empty directory.** `git submodule update --init` will refuse to check out
   `26b9ba6` into the non-empty `projects/rental-home/` dir. The on-disk contents are regenerable
   runtime artifacts.
   - **Recommendation: back up then clear the untracked artifacts before checkout** (see steps).

## Steps

### 1. Sync `projects/ua` to recorded gitlink (reset, not advance)
```bash
cd /Users/mac/prj/DW-SuperApps
git -C projects/ua clean -fdx        # discard untracked files in the submodule
git -C projects/ua checkout -- .    # discard tracked edits
git -C projects/ua reset --hard f01391f   # match recorded gitlink
git submodule status projects/ua    # expect clean `f01391f` (no +/- prefix)
cd /Users/mac/prj/DW-SuperApps
git status --short projects/ua      # expect clean (no longer dirty)
```

### 2. Initialize `projects/rental-home` (currently not initialized)
```bash
cd /Users/mac/prj/DW-SuperApps
# 2a. Preserve existing regenerable artifacts (do NOT commit these).
mv projects/rental-home projects/rental-home.bak && mkdir projects/rental-home
# 2b. Initialize + checkout the recorded gitlink.
git submodule update --init --checkout projects/rental-home
git submodule status projects/rental-home  # expect clean `26b9ba6`
# 2c. Merge back any still-useful runtime artifacts IF their absence is harmless
#     (runtime dirs are recreatable via `dw power install`; the semantic-analysis
#     doc is regenerable by a UA refresh).
```

### 3. Verify UA power binding still holds (no reinstall needed)
```bash
cd /Users/mac/prj/DW-SuperApps
cat .dw/bindings/rental-home/ua.json   # confirm runtimePath/storePath/targetPath intact
ls .dw/powers/ua          # UA package present
```
If after Step 1 the UA package is regenerated, rebind/reinstall to keep binding packageVersion
in sync:
```bash
./bin/dw power install ua --source submodule --target projects/rental-home
```

### 4. Refresh UA against the now-present rental-home source
```bash
# regenerate .ua/knowledge-graph.json against projects/rental-home
# (command TBD from .dw/powers/ua entry point; rerun baseline analysis)
```

## Validation
- `git submodule status` shows `f01391f` (clean) for `projects/ua` and `26b9ba6` (clean) for
  `projects/rental-home` — **no leading `+`/`-`/`.` prefixes**.
- `git status` in the superproject no longer reports ` M projects/ua`.
- `projects/rental-home` contains the real source tree from commit `26b9ba6` (not just the
  runtime dirs).
- `.dw/bindings/rental-home/ua.json` is intact and its `packageVersion` matches the installed
  `.dw/powers/ua` package derived from `f01391f`.

## Risks / boundaries
- **Protected `main`:** do NOT commit gitlink changes to `main` directly. If Decision 1 flips to
  "advance gitlink", create a dedicated branch, stage only the gitlink change in
  `projects/ua`, and open a PR (AGENTS.md §Repository changes). This plan does not require any
  commit — all sync is local-only.
- **rental-home at `26b9ba6` had 0 analyzable source files** (per prior UA scan). Initializing it
  may still yield an empty/minimal tree; the source checkout from
  `nhatnguyenquang1838-coder/rental_home.git` must be confirmed in Step 2.
- **Store/runtime overlap is forbidden** (AGENTS.md): do not place `.dw/` payloads inside
  `projects/rental-home/`. The runtime dirs under `projects/rental-home/.ua` etc. are installed
  power runtimes, not the package store.
- **No credentials, checksums, or package identities are invented.** Any power-package checksum
  is taken from the existing `MANIFEST.json`/binding, not generated here.

## Out of scope
- Advancing `projects/ua` gitlink past `f01391f` / committing to `main`.
- Initializing the uninitialized submodules `projects/bmad`, `projects/task-me`,
  `projects/gwc`, `projects/dw-chatgpt-app`.
- Installing BMAD / GWC / task-me powers (already bound) or any new power into rental-home.
- Any PR creation, merge, or deployment.
