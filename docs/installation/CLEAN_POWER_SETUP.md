# Clean Power setup

Preview the cleanup first:

```bash
./bin/dw power cleanup
```

Apply it only after reviewing the listed paths:

```bash
./bin/dw power cleanup --yes
```

This removes the workspace-owned Power setup:

- `.dw/powers`, `.dw/inbox/powers`, `.dw/cache`, `.dw/history/powers`, and `.dw/bindings`;
- local `.dw/distributions` build artifacts;
- generated host adapters only when they carry the DW generated marker.

The command preserves `workspace.yaml`, project/system registrations, Power source submodules,
target runtime roots, and legacy target `.dw` installations. It does not remove or edit source code.

To also remove declared system runtime roots, use the separate destructive confirmation:

```bash
./bin/dw power cleanup --include-runtime --yes
```

This command does not remove Power source submodules or rewrite the Power/project declarations in
`workspace.yaml`. It returns the package/control plane to an uninstalled state while keeping the
Super Project registry usable.
