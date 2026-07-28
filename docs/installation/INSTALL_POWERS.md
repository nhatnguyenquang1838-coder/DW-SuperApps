# Install Powers

Power packages are installed once into the Super Project package store and bound to selected systems.

```bash
dw power install gwc --source auto --target projects/billing
dw power install ua --source auto --target projects/billing
dw power install task-me --source auto --target projects/billing
```

When using the current compatibility layout, the target may still be `systems/<system-id>`.

Complete the lifecycle:

```bash
dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target <project-path>
dw host install all --mode wrapper
dw power doctor <power-id> --target <project-path>
dw doctor all --offline
```

Expected ownership:

```text
Super Project/.dw/powers/<power-id>        package code
Super Project/.dw/bindings/<system>/       binding records
<project>/<runtime-root>/                  runtime and project configuration
Super Project/<host-adapter-root>/         thin adapter
```
