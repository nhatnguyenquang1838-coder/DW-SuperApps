# DW-PDIST-02 — GWC Skills-Only Distribution

Jira: `SCRUM-91`  
Repository: `nhatnguyenquang1838-coder/gwc`  
Logical branch: `feat/dw-power-distribution-v1`  
Depends on: `DW-PDIST-01`  
Gate Control: **disabled**

## Objective

Publish GWC as a reusable skill source without shipping task history, plans, dashboards, or populated governance runtime data.

## Required output

- Strict allowlist package recipe.
- Config and consumer-contract templates.
- Provider-owned publishing workflow calling the shared DW workflow by immutable SHA.
- Deterministic release ZIP, checksum, manifest, source provenance, and `power-dist` branch.
- Standalone smoke installation and `doctor` validation.

The package may include governance contracts because the GWC skill needs them, but it must not activate a governance task or gate during installation.
