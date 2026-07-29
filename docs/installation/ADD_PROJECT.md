# Add a project or system

## Add a product project

```bash
dw project add billing \
  --repo example-org/billing \
  --role product
```

This creates `projects/billing` as a Git submodule and adds a project entry to `workspace.yaml`.

## Register an existing local project offline

Use this when the project directory is already present in the receiving Super Project. The repository
value is metadata only; no GitHub, Git, or submodule operation is performed.

```bash
./bin/dw project add billing \
  --repo example-org/billing \
  --path projects/billing \
  --role product \
  --role system \
  --system \
  --system-id billing \
  --enable-powers gwc,ua,task-me,bmad \
  --offline
```

`projects/billing` must already exist locally. This writes the project and system records to
`workspace.yaml` with `sourceMode: offline-local`, which allows Power bindings to resolve without a
`.gitmodules` entry.

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
