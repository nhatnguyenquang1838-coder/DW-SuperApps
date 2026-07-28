# DW Super Project installation

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

A Super Project owns packages, bindings, host adapters, and project registrations. Child projects own their source, runtime roots, and project-specific configuration.
