# Decisions

## D1 — Do not distribute the entire GWC repository or project package

- Reason: the source includes extensive historical, operational, and governance-delivery material outside the skills-only requirement.
- Decision: create a dedicated allowlist recipe derived from verified skill dependencies.

## D2 — Installation does not activate governance

- Decision: the package may install GWC skills and contracts and create an empty runtime root, but it may not create a task, gate, audit event, approval envelope, branch, PR, Jira issue, or Slack message.

## D3 — Same logical branch name

- Decision: implementation may use `feat/dw-power-distribution-v1` in the GWC repository. Task 05 records the provider commit and reconciles it into the DW-SuperApps integration branch.
