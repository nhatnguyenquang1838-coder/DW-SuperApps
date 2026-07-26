# Troubleshooting

## Project is missing from `.gitmodules`

`dw validate` fails closed when a registered project path is not a Git submodule. Add it with `dw project add`, or repair `.gitmodules` and `workspace.yaml` together.

## Repository mismatch

The normalized `owner/repository` in `workspace.yaml` must match the submodule URL. Forks and upstream repositories must be declared deliberately rather than silently substituted.

## Workspace initialization refuses the target

Use an empty directory. Use `--in-place` only for a management repository that does not already contain `workspace.yaml`. Existing managed runtime paths are preserved.

## Power package is missing

Project registration is separate from package installation. Install the selected package, activate hosts, then run `dw power doctor`.

## Store/runtime overlap

The Super Project `.dw/powers` store must not be inside a child project target. Child projects receive runtime roots only.

## Source submodule is not initialized

Normal package onboarding should still use release, `power-dist`, or an explicit local package. Initialize source submodules only for development or compatibility work.
