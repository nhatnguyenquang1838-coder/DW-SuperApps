# Migrate an existing DW workspace

The current compatibility phase registers every existing source submodule as a project without moving its gitlink.

```text
projects/gwc            project role: power-source
projects/ua             project role: power-source
projects/task-me        project role: power-source
projects/rental-home   project roles: product
```

Migration sequence:

1. Pull the compatibility release.
2. Run `dw project list` and verify all existing submodules appear once.
3. Run `dw validate` and `dw doctor all --offline`.
4. Commit the registry-only change.
5. Move gitlinks into `projects/*` only in the later physical-migration PR.
6. Refresh generated adapters and absolute binding paths after the physical move.

Do not manually move dirty submodules. Do not migrate project runtime into `.dw/powers`.

The migration removes the duplicated top-level `systems[]` registry. Keep target
configuration under the product project entry as `powers.enabled` and
`orchestration`; the old `dw system` commands remain read-only compatibility aliases.

## Phase 2 source-project path migration

The canonical source-project paths are now `projects/gwc`, `projects/ua`, `projects/task-me`, and `projects/rental-home`.

For an existing clone, first preserve or commit any dirty child-repository changes. Then synchronize the renamed submodules:

```bash
git submodule deinit -f -- powers/gwc powers/ua powers/task-me systems/rental-home || true
git submodule sync --recursive
git submodule update --init --recursive
./bin/dw project list
./bin/dw validate
```

Do not delete or overwrite dirty legacy submodule worktrees automatically. UA now uses `nhatnguyenquang1838-coder/Understand-Anything` as the active source origin. `Egonex-AI/Understand-Anything` remains the documented upstream provenance. To roll back, reset the Super Project commit and run `git submodule sync --recursive` followed by `git submodule update --init --recursive`.
