# DW-PDIST-01 — Shared DW Power Distribution Foundation

Jira: `SCRUM-90`  
Repository: `nhatnguyenquang1838-coder/DW-SuperApps`  
Branch: `feat/dw-power-distribution-v1`  
Gate Control: **disabled**

## Objective

Create the provider-neutral foundation used by GWC, Task Me, and UA distributions. The output must be usable both by DW-SuperApps and by an independent application.

## Deliverables

- Versioned JSON/YAML contracts for package recipe, package manifest, and consumer binding.
- Deterministic allowlist-based package builder.
- Portable Bash and PowerShell runtime templates for install, configure, doctor, and uninstall.
- Reusable GitHub Actions publishing workflow.
- Negative tests for forbidden content and unsafe paths.

## Handoff rule

Complete this task before Tasks 02–04. Do not add provider-specific recipes here. Do not create a PR, merge, release, or GWC gate artifact as part of this task spec.
