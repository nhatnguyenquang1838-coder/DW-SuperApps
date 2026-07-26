# Migrate an existing DW workspace

The current compatibility phase registers every existing source submodule as a project without moving its gitlink.

```text
powers/gwc            project role: power-source
powers/ua             project role: power-source
powers/task-me        project role: power-source
systems/rental-home   project roles: product, system
```

Migration sequence:

1. Pull the compatibility release.
2. Run `dw project list` and verify all existing submodules appear once.
3. Run `dw validate` and `dw doctor all --offline`.
4. Commit the registry-only change.
5. Move gitlinks into `projects/*` only in the later physical-migration PR.
6. Refresh generated adapters and absolute binding paths after the physical move.

Do not manually move dirty submodules. Do not migrate project runtime into `.dw/powers`.
