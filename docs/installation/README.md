# DW Super Project installation

For a standalone offline release, start with [Install Powers from a full offline release](INSTALL_POWERS.md)
and run the release-owned `offline_release_installer.py setup` command. It is the supported path for empty,
stale, or broken consumer projects and does not require this repository or its submodules.

Choose one path:

1. **Use DW-SuperApps directly:** clone with submodules and run `bash bin/dw install --shell auto --init`.
2. **Create another Super Project:** run `dw workspace init <target> --id <id> --name <name>` from an existing DW checkout.
3. **Initialize an existing management repository:** run the same command with target `.` and `--in-place`.

Then add projects, install selected Powers, activate hosts, and run doctor.

```bash
dw project list
dw power list
dw host install all --mode wrapper
dw validate
dw doctor all --offline
```

To return the package/control plane to a pre-Power-install state, preview and then apply:

```bash
./bin/dw power cleanup
./bin/dw power cleanup --yes
```

Runtime roots are preserved unless `--include-runtime --yes` is explicitly supplied.

A Super Project owns packages, bindings, host adapters, and project registrations. Child projects own their source, runtime roots, and project-specific configuration.
