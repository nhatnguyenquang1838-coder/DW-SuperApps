# Decisions

## D1 — Package source, not generated Task Me output

The distributable unit is the implementation-task-architect skill and verified dependencies. `.ua/generated/task-plans/**` and `.task-me/**` are explicitly excluded.

## D2 — Do not auto-run after installation

Installation only makes the skill available. Task generation requires a later explicit invocation against a configured consumer repository.

## D3 — Neutral config templates

Repository-specific Task Me configuration is evidence, not the default consumer configuration. The package provides neutral defaults and a schema.
