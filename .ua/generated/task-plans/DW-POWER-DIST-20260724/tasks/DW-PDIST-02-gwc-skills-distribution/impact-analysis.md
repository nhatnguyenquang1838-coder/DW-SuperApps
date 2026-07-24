# Impact Analysis

## Direct impact

- Adds distribution metadata and CI publishing behavior to the GWC repository.
- Curates a dependency closure around `skills/gwc-g1/SKILL.md` and required fallback entrypoints.
- Introduces an empty consumer-owned `.gwc` runtime root during installation.

## Contract impact

GWC currently has an extensive project package containing governance instructions, schemas, tools, runbooks, and release fragments. The distribution recipe must not blindly reuse that full package because it includes historical and operational material outside the skills-only objective.

## Main risks

- Over-including the large governance catalog.
- Omitting a schema or validator referenced by a packaged contract.
- Accidentally shipping historical task/evidence records.
- Installing governance files outside approved consumer paths.

## Controls

- Start from skill entrypoints and calculate verified dependency closure.
- Use allowlists; do not use broad `core/**`, `schemas/**`, or `tools/**` without an explicit reviewed exception.
- Run forbidden-content scans and reference-resolution tests.
- Smoke install into an empty consumer repository and verify no gate state is created.
