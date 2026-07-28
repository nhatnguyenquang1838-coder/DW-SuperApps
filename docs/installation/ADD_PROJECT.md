# Add a project or system

## Add a product project

```bash
dw project add billing \
  --repo example-org/billing \
  --role product
```

This creates `projects/billing` as a Git submodule and adds a project entry to `workspace.yaml`.

## Add and register a system

```bash
dw project add billing \
  --repo example-org/billing \
  --role product \
  --role system \
  --system \
  --enable-powers gwc,ua,task-me
```

## Review before committing

```bash
git diff -- .gitmodules workspace.yaml
dw project info billing
dw validate
```

Project registration does not install Power packages. Use the Power installation lifecycle after reviewing the registry change.
